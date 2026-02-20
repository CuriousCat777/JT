"""Tests for the DoorDash agent."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.doordash import (
    DoorDashAgent,
    MealSchedule,
    Order,
    OrderItem,
    OrderStatus,
    Restaurant,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_agent() -> DoorDashAgent:
    agent = DoorDashAgent(AgentConfig(name="doordash"), _make_audit())
    agent.initialize()
    return agent


def _add_sample_restaurants(agent: DoorDashAgent) -> None:
    agent.add_restaurant(Restaurant(
        name="Pho Saigon",
        cuisine="Vietnamese",
        rating=4.7,
        favorite_items=["Pho Tai", "Spring Rolls"],
        avg_delivery_minutes=25,
        tags=["healthy", "quick"],
    ))
    agent.add_restaurant(Restaurant(
        name="Chipotle",
        cuisine="Mexican",
        rating=4.2,
        favorite_items=["Burrito Bowl", "Chips & Guac"],
        avg_delivery_minutes=20,
        tags=["quick", "filling"],
    ))
    agent.add_restaurant(Restaurant(
        name="Sweetgreen",
        cuisine="Salad",
        rating=4.5,
        favorite_items=["Harvest Bowl"],
        avg_delivery_minutes=30,
        tags=["healthy"],
    ))


# ---- Initialization ----

def test_initialize():
    agent = _make_agent()
    assert agent.status == AgentStatus.IDLE


def test_default_meal_schedules():
    agent = _make_agent()
    report = agent.report()
    # Should have breakfast, lunch, dinner by default
    assert report.agent_name == "doordash"


# ---- Restaurant management ----

def test_add_and_search_restaurants():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    assert len(agent.favorite_restaurants()) == 3

    vietnamese = agent.search_restaurants(cuisine="Vietnamese")
    assert len(vietnamese) == 1
    assert vietnamese[0].name == "Pho Saigon"


def test_search_by_tags():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    healthy = agent.search_restaurants(tags=["healthy"])
    names = {r.name for r in healthy}
    assert "Pho Saigon" in names
    assert "Sweetgreen" in names


def test_remove_restaurant():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    assert agent.remove_restaurant("Chipotle") is True
    assert agent.get_restaurant("Chipotle") is None
    assert agent.remove_restaurant("Nonexistent") is False


def test_favorite_restaurants_sorted_by_rating():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    favs = agent.favorite_restaurants()
    assert favs[0].name == "Pho Saigon"  # Highest rating (4.7)
    assert favs[-1].name == "Chipotle"   # Lowest rating (4.2)


# ---- Order management ----

def test_place_order():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    order = agent.place_order(
        restaurant_name="Pho Saigon",
        items=[
            OrderItem(name="Pho Tai", price=14.99),
            OrderItem(name="Spring Rolls", price=6.99, quantity=2),
        ],
        tip=5.00,
    )

    assert order.order_id == "DD-000001"
    assert order.restaurant == "Pho Saigon"
    assert order.subtotal == 28.97  # 14.99 + 6.99*2
    assert order.tip == 5.00
    assert order.total > order.subtotal  # Includes fees + tip
    assert order.status == OrderStatus.PLACED


def test_update_order_status():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    order = agent.place_order(
        restaurant_name="Chipotle",
        items=[OrderItem(name="Burrito Bowl", price=12.50)],
    )

    updated = agent.update_order_status(order.order_id, OrderStatus.PREPARING)
    assert updated is not None
    assert updated.status == OrderStatus.PREPARING

    # Deliver the order
    agent.update_order_status(order.order_id, OrderStatus.DELIVERED)
    assert len(agent.get_active_orders()) == 0


def test_cancel_order():
    agent = _make_agent()
    order = agent.place_order(
        restaurant_name="Test Place",
        items=[OrderItem(name="Item", price=10.00)],
    )

    agent.update_order_status(order.order_id, OrderStatus.CANCELLED)
    assert len(agent.get_active_orders()) == 0


def test_order_history():
    agent = _make_agent()
    for i in range(3):
        agent.place_order(
            restaurant_name=f"Restaurant {i}",
            items=[OrderItem(name=f"Item {i}", price=10.00)],
        )

    history = agent.order_history()
    assert len(history) == 3


# ---- Budget coordination ----

def test_budget_tracking():
    agent = _make_agent()
    agent.set_monthly_budget(300.0)

    agent.place_order(
        restaurant_name="Place A",
        items=[OrderItem(name="Meal", price=25.00)],
    )

    budget = agent.budget_status()
    assert budget["monthly_budget"] == 300.0
    assert budget["spent"] > 0
    assert budget["over_budget"] is False


def test_budget_over_limit():
    agent = _make_agent()
    agent.set_monthly_budget(10.0)

    agent.place_order(
        restaurant_name="Expensive",
        items=[OrderItem(name="Big Meal", price=50.00)],
    )

    budget = agent.budget_status()
    assert budget["over_budget"] is True


# ---- Meal scheduling ----

def test_suggest_meal():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    suggestion = agent.suggest_meal("lunch")
    assert suggestion.get("restaurant") is not None
    assert suggestion["meal"] == "lunch"


def test_suggest_meal_no_restaurants():
    agent = _make_agent()
    suggestion = agent.suggest_meal("lunch")
    assert suggestion.get("reason") is not None  # Should explain no restaurants


def test_custom_meal_schedule():
    agent = _make_agent()
    agent.set_meal_schedule(MealSchedule(
        meal="lunch",
        window_start="11:30",
        window_end="12:30",
        preferred_cuisines=["Vietnamese"],
    ))
    _add_sample_restaurants(agent)

    suggestion = agent.suggest_meal("lunch")
    assert suggestion["restaurant"] == "Pho Saigon"


# ---- Dietary preferences ----

def test_dietary_preferences():
    agent = _make_agent()
    agent.set_dietary_preferences(["no peanuts", "low sodium"])
    assert agent.get_dietary_preferences() == ["no peanuts", "low sodium"]


# ---- Reorder ----

def test_reorder_last():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    agent.place_order(
        restaurant_name="Pho Saigon",
        items=[OrderItem(name="Pho Tai", price=14.99)],
        tip=4.00,
    )

    reorder = agent.reorder_last("Pho Saigon")
    assert reorder is not None
    assert reorder.restaurant == "Pho Saigon"
    assert reorder.items[0].name == "Pho Tai"
    assert reorder.order_id != "DD-000001"  # New order ID


def test_reorder_nonexistent_restaurant():
    agent = _make_agent()
    assert agent.reorder_last("Never Ordered Here") is None


# ---- Most ordered items ----

def test_most_ordered_items():
    agent = _make_agent()
    for _ in range(3):
        agent.place_order(
            restaurant_name="Chipotle",
            items=[OrderItem(name="Burrito Bowl", price=12.50)],
        )
    agent.place_order(
        restaurant_name="Chipotle",
        items=[OrderItem(name="Tacos", price=10.00)],
    )

    top = agent.most_ordered_items()
    assert top[0]["item"] == "Chipotle — Burrito Bowl"
    assert top[0]["times_ordered"] == 3


# ---- Run / Report ----

def test_run():
    agent = _make_agent()
    _add_sample_restaurants(agent)
    agent.set_monthly_budget(300.0)

    agent.place_order(
        restaurant_name="Pho Saigon",
        items=[OrderItem(name="Pho Tai", price=14.99)],
    )

    report = agent.run()
    assert report.agent_name == "doordash"
    assert report.status == AgentStatus.IDLE.value
    assert "1 active orders" in report.summary


def test_report():
    agent = _make_agent()
    _add_sample_restaurants(agent)

    report = agent.report()
    assert "3 restaurants" in report.summary
    assert report.data["restaurants"] == ["Pho Saigon", "Chipotle", "Sweetgreen"]
    assert report.data["api_connected"] is False


# ---- API connection ----

def test_api_not_connected_without_credentials():
    agent = _make_agent()
    assert agent.api_connected is False


def test_live_delivery_returns_none_without_api():
    agent = _make_agent()
    result = agent.create_live_delivery(
        pickup_address="123 Main St",
        pickup_business_name="Test Restaurant",
        pickup_phone="+15551234567",
        dropoff_address="456 Oak Ave",
        dropoff_phone="+15559876543",
        order_value_cents=1500,
    )
    assert result is None


def test_poll_live_delivery_returns_none_without_api():
    agent = _make_agent()
    assert agent.poll_live_delivery("DD-000001") is None


def test_cancel_live_delivery_returns_false_without_api():
    agent = _make_agent()
    assert agent.cancel_live_delivery("DD-000001") is False


def test_run_shows_api_offline():
    agent = _make_agent()
    report = agent.run()
    assert "API offline" in report.summary
    assert any("Drive API not connected" in r for r in report.recommendations)
