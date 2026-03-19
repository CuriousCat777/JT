# Session Handoff: DoorDash Agent (Meal Delivery Intelligence)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **DoorDash Agent** — Guardian One's meal delivery coordinator.
It manages restaurants, orders, meal scheduling, budget tracking, dietary preferences,
and integrates with the DoorDash Drive API for live deliveries.

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/doordash.py` | ~450 | Core agent — restaurants, orders, meals, budget |
| `guardian_one/integrations/doordash_sync.py` | ~400 | DoorDash Drive API — JWT auth, delivery CRUD |
| `tests/test_doordash.py` | ~400 | 49 tests — comprehensive coverage |

---

## Data Structures

```python
class OrderStatus(Enum):
    PLACED, CONFIRMED, PREPARING, DRIVER_ASSIGNED,
    PICKED_UP, EN_ROUTE, DELIVERED, CANCELLED

@dataclass
class Restaurant:
    name: str
    cuisine: str
    address: str
    rating: float                # 0-5
    favorite_items: list[str]
    avg_delivery_minutes: int
    tags: list[str]              # "healthy", "quick", "comfort", etc.

@dataclass
class OrderItem:
    name: str
    price: float
    quantity: int = 1
    special_instructions: str = ""

@dataclass
class Order:
    order_id: str                # "DD-000001"
    restaurant: str
    items: list[OrderItem]
    status: OrderStatus
    subtotal: float
    fees: float                  # 15% of subtotal
    tip: float
    total: float
    placed_at: str               # ISO timestamp
    estimated_delivery: str
    delivered_at: str | None
    delivery_address: str
    metadata: dict = {}

@dataclass
class MealSchedule:
    meal: str                    # breakfast, lunch, dinner, snack
    window_start: str            # "HH:MM"
    window_end: str
    preferred_cuisines: list[str]

# DoorDash Drive API models
@dataclass
class DeliveryRequest:
    external_delivery_id: str
    pickup_address: str
    pickup_business_name: str
    pickup_phone_number: str
    pickup_instructions: str
    dropoff_address: str
    dropoff_business_name: str
    dropoff_phone_number: str
    dropoff_instructions: str
    order_value: int             # cents
    tip: int                     # cents

@dataclass
class DeliveryResponse:
    external_delivery_id: str
    delivery_status: str
    tracking_url: str
    fee: int                     # cents
    pickup_time_estimated: str
    dropoff_time_estimated: str
    dasher_name: str
    dasher_phone: str
    raw: dict = {}
```

---

## Method Reference

### DoorDashAgent
```python
# Restaurant Management
agent.add_restaurant(restaurant: Restaurant) -> None
agent.remove_restaurant(name: str) -> bool
agent.get_restaurant(name: str) -> Restaurant | None
agent.search_restaurants(cuisine=None, tags=None) -> list[Restaurant]
agent.favorite_restaurants() -> list[Restaurant]  # sorted by rating DESC

# Order Management
agent.place_order(restaurant_name, items, delivery_address, tip) -> Order
agent.update_order_status(order_id, status: OrderStatus) -> Order | None
agent.get_active_orders() -> list[Order]
agent.order_history(limit=20) -> list[Order]

# Reorder
agent.reorder_last(restaurant_name) -> Order | None  # Same items/address/tip
agent.most_ordered_items(limit=5) -> list[dict]       # {item, times_ordered}

# Budget (CFO Coordination)
agent.set_monthly_budget(amount: float) -> None
agent.monthly_spending() -> float
agent.budget_status() -> dict  # monthly_budget, spent, remaining, percent_used, over_budget

# Meal Scheduling (Chronos Coordination)
agent.set_meal_schedule(schedule: MealSchedule) -> None
agent.suggest_meal(meal: str) -> dict  # restaurant, cuisine, window, favorite_items, est_delivery
agent.current_meal_window() -> MealSchedule | None

# Dietary Preferences
agent.set_dietary_preferences(preferences: list[str]) -> None
agent.get_dietary_preferences() -> list[str]

# Live DoorDash Drive API (requires credentials)
agent.create_live_delivery(...) -> DeliveryResponse | None
agent.poll_live_delivery(delivery_id) -> DeliveryResponse | None
agent.cancel_live_delivery(delivery_id) -> bool
agent.api_connected -> bool
```

### DoorDashDriveProvider
```python
provider = DoorDashDriveProvider(developer_id=None, key_id=None, signing_secret=None)
provider.authenticate() -> bool          # Creates JWT (DD-JWT-V1, HS256, 5-min expiry)
provider.create_delivery(request: DeliveryRequest) -> DeliveryResponse | None
provider.get_delivery_status(delivery_id) -> DeliveryResponse | None
provider.cancel_delivery(delivery_id) -> bool
provider.is_authenticated -> bool
provider.has_credentials -> bool
```

---

## Default Meal Windows

| Meal | Window | Preferred Cuisines |
|------|--------|-------------------|
| Breakfast | 7:00 – 9:00 | any |
| Lunch | 12:00 – 13:30 | any |
| Dinner | 18:00 – 20:00 | any |

---

## What's Working vs Stubbed

| Feature | Status |
|---------|--------|
| Restaurant CRUD + search | Working |
| Order creation with pricing (subtotal + 15% fees + tip) | Working |
| Order status transitions | Working |
| Budget tracking (monthly) | Working |
| Meal window scheduling + suggestions | Working |
| Dietary preferences | Working |
| Reorder last order | Working |
| Most ordered items ranking | Working |
| JWT token generation (DD-JWT-V1) | Working |
| DoorDash Drive API CRUD | Working (needs real creds) |
| **Cross-agent coordination** | **Not wired** |
| **ML meal recommendations** | **Not built** |
| **Notion sync** | **Not built** |

---

## Development Tracks

### Track 1: CFO Integration
- Export monthly DoorDash spending to CFO transaction ledger
- Sync budget limits FROM CFO (not just local)
- Categorize as "Food & Dining" in financial reports

### Track 2: Chronos Integration
- Check calendar for conflicts before suggesting orders
- Block ordering during meetings
- Coordinate delivery ETA with schedule gaps

### Track 3: DoorDash Drive API Testing
- Mock provider for CI (no real API calls)
- Validate JWT spec compliance
- Test error handling (network, 401, malformed)

### Track 4: Smart Recommendations
- Track item frequency per restaurant
- "You usually order X from Y" suggestions
- Predict delivery time accuracy

### Track 5: Notion Dashboard
- Active orders, favorite restaurants, monthly spend
- Write-only (no reading from Notion for decisions)

### Track 6: Vault Credentials
- Move from env vars to Vault-based storage
- Encrypt delivery history (addresses, phone numbers)

---

## Config (guardian_config.yaml)

```yaml
agents:
  doordash:
    enabled: true
    schedule_interval_minutes: 10
    allowed_resources: [orders, restaurants, meal_schedule, delivery_status]
    custom:
      monthly_budget: 300
      default_tip_pct: 0.20
      coordinate_with_chronos: true
      coordinate_with_cfo: true
```

**Env vars:** `DOORDASH_DEVELOPER_ID`, `DOORDASH_KEY_ID`, `DOORDASH_SIGNING_SECRET`

---

## Test Coverage (49 tests)

- Initialization: 1 test
- Restaurant management: 4 tests
- Order management: 6 tests
- Budget tracking: 2 tests
- Meal scheduling: 3 tests
- Dietary preferences: 1 test
- Reorder: 2 tests
- Most ordered items: 1 test
- Run/report: 2 tests
- API connection (defensive): 5 tests

All paths tested. API calls defensively return None/False without credentials.
