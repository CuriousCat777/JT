"""DoorDash Agent — Food delivery management.

Responsibilities:
- Place and track DoorDash orders
- Maintain favorite restaurants and reorder history
- Coordinate with Chronos for meal timing (avoid ordering during meetings)
- Coordinate with CFO for food budget tracking
- Delivery status alerts via notification system
- Suggest meals based on order history and dietary preferences
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.integrations.doordash_sync import (
    DoorDashDriveProvider,
    DeliveryRequest,
    DeliveryResponse,
)


class OrderStatus(Enum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    DRIVER_ASSIGNED = "driver_assigned"
    PICKED_UP = "picked_up"
    EN_ROUTE = "en_route"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class Restaurant:
    """A saved restaurant with preferences."""
    name: str
    cuisine: str
    address: str = ""
    rating: float = 0.0
    favorite_items: list[str] = field(default_factory=list)
    avg_delivery_minutes: int = 30
    tags: list[str] = field(default_factory=list)  # e.g. ["healthy", "quick", "comfort"]


@dataclass
class OrderItem:
    """A single item in an order."""
    name: str
    price: float
    quantity: int = 1
    special_instructions: str = ""


@dataclass
class Order:
    """A DoorDash order."""
    order_id: str
    restaurant: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PLACED
    subtotal: float = 0.0
    fees: float = 0.0
    tip: float = 0.0
    total: float = 0.0
    placed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    estimated_delivery: str = ""
    delivered_at: str | None = None
    delivery_address: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MealSchedule:
    """Preferred meal windows for Chronos coordination."""
    meal: str          # breakfast, lunch, dinner, snack
    window_start: str  # "12:00"
    window_end: str    # "13:00"
    preferred_cuisines: list[str] = field(default_factory=list)


class DoorDashAgent(BaseAgent):
    """Food delivery management agent for Jeremy."""

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._restaurants: dict[str, Restaurant] = {}
        self._orders: list[Order] = []
        self._active_orders: dict[str, Order] = {}
        self._meal_schedules: list[MealSchedule] = []
        self._monthly_budget: float = 0.0
        self._dietary_preferences: list[str] = []
        self._order_counter: int = 0
        self._provider: DoorDashDriveProvider | None = None

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self._setup_default_meal_windows()
        self._connect_provider()
        self.log("initialized", details={
            "restaurants": len(self._restaurants),
            "meal_schedules": len(self._meal_schedules),
            "api_connected": self.api_connected,
        })

    def _connect_provider(self) -> None:
        """Attempt to connect to the DoorDash Drive API using env vars."""
        provider = DoorDashDriveProvider()
        if provider.has_credentials:
            if provider.authenticate():
                self._provider = provider
                self.log("api_connected", details={"provider": "DoorDash Drive API"})
            else:
                self.log(
                    "api_auth_failed",
                    severity=Severity.WARNING,
                    details={"provider": "DoorDash Drive API"},
                )
        else:
            self.log(
                "api_no_credentials",
                severity=Severity.INFO,
                details={"hint": "Set DOORDASH_DEVELOPER_ID, DOORDASH_KEY_ID, DOORDASH_SIGNING_SECRET in .env"},
            )

    @property
    def api_connected(self) -> bool:
        return self._provider is not None and self._provider.is_authenticated

    def _setup_default_meal_windows(self) -> None:
        """Set up standard meal windows for Chronos coordination."""
        self._meal_schedules = [
            MealSchedule(
                meal="breakfast",
                window_start="07:00",
                window_end="09:00",
                preferred_cuisines=["cafe", "breakfast"],
            ),
            MealSchedule(
                meal="lunch",
                window_start="12:00",
                window_end="13:30",
                preferred_cuisines=["healthy", "quick"],
            ),
            MealSchedule(
                meal="dinner",
                window_start="18:00",
                window_end="20:00",
                preferred_cuisines=["any"],
            ),
        ]

    # ------------------------------------------------------------------
    # Restaurant management
    # ------------------------------------------------------------------

    def add_restaurant(self, restaurant: Restaurant) -> None:
        self._restaurants[restaurant.name] = restaurant
        self.log("restaurant_added", details={
            "name": restaurant.name,
            "cuisine": restaurant.cuisine,
        })

    def remove_restaurant(self, name: str) -> bool:
        if name in self._restaurants:
            del self._restaurants[name]
            self.log("restaurant_removed", details={"name": name})
            return True
        return False

    def get_restaurant(self, name: str) -> Restaurant | None:
        return self._restaurants.get(name)

    def search_restaurants(
        self,
        cuisine: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Restaurant]:
        results = list(self._restaurants.values())
        if cuisine:
            c = cuisine.lower()
            results = [r for r in results if c in r.cuisine.lower()]
        if tags:
            tag_set = {t.lower() for t in tags}
            results = [
                r for r in results
                if tag_set.intersection(t.lower() for t in r.tags)
            ]
        return results

    def favorite_restaurants(self) -> list[Restaurant]:
        """Return restaurants sorted by rating."""
        return sorted(
            self._restaurants.values(),
            key=lambda r: r.rating,
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"DD-{self._order_counter:06d}"

    def place_order(
        self,
        restaurant_name: str,
        items: list[OrderItem],
        delivery_address: str = "",
        tip: float = 0.0,
    ) -> Order:
        """Place a new DoorDash order."""
        restaurant = self._restaurants.get(restaurant_name)

        subtotal = sum(item.price * item.quantity for item in items)
        fees = round(subtotal * 0.15, 2)  # Estimated service + delivery fees
        total = round(subtotal + fees + tip, 2)

        eta_minutes = restaurant.avg_delivery_minutes if restaurant else 35
        now = datetime.now(timezone.utc)
        estimated = (now + timedelta(minutes=eta_minutes)).isoformat()

        order = Order(
            order_id=self._next_order_id(),
            restaurant=restaurant_name,
            items=items,
            subtotal=round(subtotal, 2),
            fees=fees,
            tip=round(tip, 2),
            total=total,
            estimated_delivery=estimated,
            delivery_address=delivery_address,
        )

        self._orders.append(order)
        self._active_orders[order.order_id] = order

        self.log(
            "order_placed",
            details={
                "order_id": order.order_id,
                "restaurant": restaurant_name,
                "total": total,
                "items": len(items),
            },
        )
        return order

    def update_order_status(self, order_id: str, status: OrderStatus) -> Order | None:
        order = self._active_orders.get(order_id)
        if order is None:
            return None

        order.status = status
        self.log("order_status_updated", details={
            "order_id": order_id,
            "status": status.value,
        })

        if status == OrderStatus.DELIVERED:
            order.delivered_at = datetime.now(timezone.utc).isoformat()
            del self._active_orders[order_id]
            self.log("order_delivered", details={
                "order_id": order_id,
                "delivered_at": order.delivered_at,
            })

        if status == OrderStatus.CANCELLED:
            del self._active_orders[order_id]
            self.log("order_cancelled", details={"order_id": order_id})

        return order

    def get_active_orders(self) -> list[Order]:
        return list(self._active_orders.values())

    def order_history(self, limit: int = 20) -> list[Order]:
        return self._orders[-limit:]

    # ------------------------------------------------------------------
    # Budget coordination (works with CFO)
    # ------------------------------------------------------------------

    def set_monthly_budget(self, amount: float) -> None:
        self._monthly_budget = amount
        self.log("budget_set", details={"monthly_budget": amount})

    def monthly_spending(self) -> float:
        """Total DoorDash spending for the current month."""
        current_month = datetime.now(timezone.utc).isoformat()[:7]
        return sum(
            o.total for o in self._orders
            if o.placed_at.startswith(current_month)
            and o.status != OrderStatus.CANCELLED
        )

    def budget_status(self) -> dict[str, Any]:
        spent = self.monthly_spending()
        remaining = self._monthly_budget - spent if self._monthly_budget > 0 else 0
        pct_used = (spent / self._monthly_budget * 100) if self._monthly_budget > 0 else 0
        return {
            "monthly_budget": self._monthly_budget,
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "percent_used": round(pct_used, 1),
            "over_budget": spent > self._monthly_budget > 0,
        }

    # ------------------------------------------------------------------
    # Meal scheduling (works with Chronos)
    # ------------------------------------------------------------------

    def set_meal_schedule(self, schedule: MealSchedule) -> None:
        old = next((s for s in self._meal_schedules if s.meal == schedule.meal), None)
        self._meal_schedules = [
            s for s in self._meal_schedules if s.meal != schedule.meal
        ]
        self._meal_schedules.append(schedule)
        self.log("meal_schedule_updated", details={
            "meal": schedule.meal,
            "old_window": f"{old.window_start}-{old.window_end}" if old else "none",
            "new_window": f"{schedule.window_start}-{schedule.window_end}",
        })

    def suggest_meal(self, meal: str) -> dict[str, Any]:
        """Suggest a restaurant and items for a given meal window."""
        schedule = next(
            (s for s in self._meal_schedules if s.meal == meal), None
        )
        if schedule is None:
            return {"error": f"No schedule found for meal '{meal}'."}

        # Find matching restaurants
        candidates: list[Restaurant] = []
        for r in self._restaurants.values():
            if "any" in schedule.preferred_cuisines:
                candidates.append(r)
            elif r.cuisine.lower() in (c.lower() for c in schedule.preferred_cuisines):
                candidates.append(r)
            elif any(t.lower() in (c.lower() for c in schedule.preferred_cuisines) for t in r.tags):
                candidates.append(r)

        if not candidates:
            candidates = list(self._restaurants.values())

        if not candidates:
            return {
                "meal": meal,
                "suggestion": None,
                "reason": "No restaurants saved. Add some favorites first.",
            }

        # Pick highest-rated
        best = max(candidates, key=lambda r: r.rating)
        return {
            "meal": meal,
            "window": f"{schedule.window_start}–{schedule.window_end}",
            "restaurant": best.name,
            "cuisine": best.cuisine,
            "favorite_items": best.favorite_items,
            "est_delivery": f"{best.avg_delivery_minutes} min",
        }

    def current_meal_window(self) -> MealSchedule | None:
        """Determine which meal window we're currently in (local approx)."""
        now_hour = datetime.now(timezone.utc).hour  # Approximate; config tz-aware in production
        for sched in self._meal_schedules:
            try:
                start_h = int(sched.window_start.split(":")[0])
                end_h = int(sched.window_end.split(":")[0])
            except (ValueError, IndexError):
                continue
            if start_h <= now_hour < end_h:
                return sched
        return None

    # ------------------------------------------------------------------
    # Dietary preferences
    # ------------------------------------------------------------------

    def set_dietary_preferences(self, preferences: list[str]) -> None:
        self._dietary_preferences = preferences
        self.log("dietary_preferences_set", details={"preferences": preferences})

    def get_dietary_preferences(self) -> list[str]:
        return list(self._dietary_preferences)

    # ------------------------------------------------------------------
    # Reorder support
    # ------------------------------------------------------------------

    def reorder_last(self, restaurant_name: str) -> Order | None:
        """Reorder the most recent order from a given restaurant."""
        for order in reversed(self._orders):
            if order.restaurant == restaurant_name and order.status != OrderStatus.CANCELLED:
                return self.place_order(
                    restaurant_name=restaurant_name,
                    items=order.items,
                    delivery_address=order.delivery_address,
                    tip=order.tip,
                )
        return None

    def most_ordered_items(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return the most frequently ordered items across all orders."""
        counts: dict[str, int] = {}
        for order in self._orders:
            if order.status == OrderStatus.CANCELLED:
                continue
            for item in order.items:
                key = f"{order.restaurant} — {item.name}"
                counts[key] = counts.get(key, 0) + item.quantity
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"item": k, "times_ordered": v} for k, v in sorted_items[:limit]]

    # ------------------------------------------------------------------
    # Live API operations (requires DoorDash Drive credentials)
    # ------------------------------------------------------------------

    def create_live_delivery(
        self,
        pickup_address: str,
        pickup_business_name: str,
        pickup_phone: str,
        dropoff_address: str,
        dropoff_phone: str,
        order_value_cents: int,
        tip_cents: int = 0,
        pickup_instructions: str = "",
        dropoff_instructions: str = "",
    ) -> DeliveryResponse | None:
        """Create a real delivery via the DoorDash Drive API.

        Returns a DeliveryResponse with tracking URL and status,
        or None if the API is not connected or the request fails.
        """
        if not self.api_connected or self._provider is None:
            self.log(
                "live_delivery_skipped",
                severity=Severity.WARNING,
                details={"reason": "API not connected"},
            )
            return None

        delivery_id = self._next_order_id()
        request = DeliveryRequest(
            external_delivery_id=delivery_id,
            pickup_address=pickup_address,
            pickup_business_name=pickup_business_name,
            pickup_phone_number=pickup_phone,
            pickup_instructions=pickup_instructions,
            dropoff_address=dropoff_address,
            dropoff_phone_number=dropoff_phone,
            dropoff_instructions=dropoff_instructions,
            order_value=order_value_cents,
            tip=tip_cents,
        )

        response = self._provider.create_delivery(request)
        if response:
            self.log("live_delivery_created", details={
                "delivery_id": delivery_id,
                "status": response.delivery_status,
                "tracking_url": response.tracking_url,
            })
        else:
            self.log("live_delivery_failed", severity=Severity.ERROR, details={
                "delivery_id": delivery_id,
            })
        return response

    def poll_live_delivery(self, delivery_id: str) -> DeliveryResponse | None:
        """Check status of a live delivery via the Drive API."""
        if not self.api_connected or self._provider is None:
            return None
        response = self._provider.get_delivery_status(delivery_id)
        if response:
            self.log("live_delivery_polled", details={
                "delivery_id": delivery_id,
                "status": response.delivery_status,
            })
        return response

    def cancel_live_delivery(self, delivery_id: str) -> bool:
        """Cancel a live delivery via the Drive API."""
        if not self.api_connected or self._provider is None:
            return False
        success = self._provider.cancel_delivery(delivery_id)
        self.log("live_delivery_cancelled", details={
            "delivery_id": delivery_id,
            "success": success,
        })
        return success

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # Active order tracking
        active = self.get_active_orders()
        if active:
            for order in active:
                actions.append(
                    f"Tracking order {order.order_id} from {order.restaurant} — {order.status.value}"
                )

        # Budget check
        budget = self.budget_status()
        if budget["over_budget"]:
            alerts.append(
                f"DoorDash budget exceeded: ${budget['spent']:.2f} / ${budget['monthly_budget']:.2f}"
            )
        elif budget["monthly_budget"] > 0 and budget["percent_used"] > 80:
            recommendations.append(
                f"DoorDash spending at {budget['percent_used']:.0f}% of monthly budget. "
                f"${budget['remaining']:.2f} remaining."
            )

        # Meal suggestion for current window
        window = self.current_meal_window()
        if window and self._restaurants:
            suggestion = self.suggest_meal(window.meal)
            if suggestion.get("restaurant"):
                recommendations.append(
                    f"It's {window.meal} time — consider {suggestion['restaurant']} "
                    f"({suggestion['cuisine']}, ~{suggestion['est_delivery']})"
                )

        # API connection status
        if not self.api_connected:
            recommendations.append(
                "DoorDash Drive API not connected. Set DOORDASH_DEVELOPER_ID, "
                "DOORDASH_KEY_ID, DOORDASH_SIGNING_SECRET in .env to enable live deliveries."
            )

        actions.append("Checked active orders, budget, and meal schedule.")
        self._set_status(AgentStatus.IDLE)

        api_label = "API connected" if self.api_connected else "API offline"
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=(
                f"{len(active)} active orders | "
                f"Month spend: ${budget['spent']:.2f} | "
                f"{len(self._restaurants)} saved restaurants | "
                f"{api_label}"
            ),
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "active_orders": len(active),
                "total_orders": len(self._orders),
                "restaurants": len(self._restaurants),
                "budget": budget,
                "api_connected": self.api_connected,
            },
        )

    def report(self) -> AgentReport:
        budget = self.budget_status()
        api_label = "API connected" if self.api_connected else "API offline"
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=(
                f"Managing {len(self._restaurants)} restaurants, "
                f"{len(self._orders)} orders, "
                f"${budget['spent']:.2f} spent this month. "
                f"({api_label})"
            ),
            data={
                "restaurants": list(self._restaurants.keys()),
                "active_orders": len(self._active_orders),
                "order_history_count": len(self._orders),
                "budget": budget,
                "dietary_preferences": self._dietary_preferences,
                "api_connected": self.api_connected,
            },
        )
