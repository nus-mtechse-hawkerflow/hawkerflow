"""Analytics domain: pure fold of an OrderCollected event into a daily aggregate."""


def empty_aggregate() -> dict:
    return {"orders": 0, "revenueCents": 0, "items": {}}


def fold(aggregate: dict, event: dict) -> dict:
    """Return a new aggregate with one collected order folded in."""
    agg = {
        "orders": int(aggregate.get("orders", 0)) + 1,
        "revenueCents": int(aggregate.get("revenueCents", 0)) + int(event.get("totalCents", 0)),
        "items": dict(aggregate.get("items", {})),
    }
    for line in event.get("lines", []):
        name = line.get("name") or "unknown"
        agg["items"][name] = int(agg["items"].get(name, 0)) + int(line.get("qty", 0))
    return agg


def date_of(event: dict) -> str:
    return str(event.get("at", ""))[:10] or "unknown"
