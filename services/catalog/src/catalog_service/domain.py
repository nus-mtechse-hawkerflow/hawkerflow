"""Catalog domain rules: menu item validation."""
from shared.http import ApiError

MAX_PRICE_CENTS = 100_000  # S$1,000 cap - sanity bound for hawker food


def validate_item(item_id: str, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    price = payload.get("priceCents")
    available = payload.get("available", True)
    if not 1 <= len(name) <= 60:
        raise ApiError(400, "item name must be 1-60 characters")
    if not isinstance(price, int) or not 1 <= price <= MAX_PRICE_CENTS:
        raise ApiError(400, f"priceCents must be an integer between 1 and {MAX_PRICE_CENTS}")
    if not isinstance(available, bool):
        raise ApiError(400, "available must be a boolean")
    if not 1 <= len(item_id) <= 40:
        raise ApiError(400, "itemId must be 1-40 characters")
    return {"itemId": item_id, "name": name, "priceCents": price, "available": available}
