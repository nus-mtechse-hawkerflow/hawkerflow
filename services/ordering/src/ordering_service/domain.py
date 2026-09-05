"""Ordering domain: order construction, pricing and the lifecycle state machine.

Pure logic - no AWS imports - so it is unit-testable in isolation (see tests/).
"""
import uuid

from shared.http import ApiError

# Deterministic namespace so (userSub, Idempotency-Key) always maps to the same orderId.
_NAMESPACE = uuid.UUID("2f1c4b58-7a30-4a56-9d3e-8c2a7d5e1b09")

MAX_QTY = 20
MAX_LINES = 15

# (current, new) -> actor allowed to perform the transition
TRANSITIONS = {
    ("PLACED", "ACCEPTED"): "stall",
    ("PLACED", "REJECTED"): "stall",
    ("PLACED", "CANCELLED"): "diner",
    ("ACCEPTED", "PREPARING"): "stall",
    ("ACCEPTED", "CANCELLED"): "diner",
    ("PREPARING", "READY"): "stall",
    ("READY", "COLLECTED"): "stall",
}

ACTIONS = {
    "accept": "ACCEPTED",
    "reject": "REJECTED",
    "preparing": "PREPARING",
    "ready": "READY",
    "collected": "COLLECTED",
    "cancel": "CANCELLED",
}

TERMINAL = {"COLLECTED", "REJECTED", "CANCELLED"}


def order_id_for(user_sub: str, idempotency_key: str) -> str:
    return uuid.uuid5(_NAMESPACE, f"{user_sub}:{idempotency_key}").hex


def next_status(action: str) -> str:
    status = ACTIONS.get((action or "").lower())
    if not status:
        raise ApiError(400, f"unknown action, expected one of {sorted(ACTIONS)}")
    return status


def check_transition(current: str, new: str, *, is_stall_owner: bool, is_order_owner: bool) -> None:
    actor = TRANSITIONS.get((current, new))
    if actor is None:
        raise ApiError(409, f"cannot move order from {current} to {new}")
    if actor == "stall" and not is_stall_owner:
        raise ApiError(403, "only the stall owner can perform this action")
    if actor == "diner" and not is_order_owner:
        raise ApiError(403, "only the diner who placed the order can cancel it")


def build_order(
    user_sub: str,
    stall: dict,
    menu_items: list,
    requested: list,
    idempotency_key: str,
    now_iso: str,
) -> dict:
    """Validate the request against the server-side catalog and price it there.

    The client is never trusted with prices or totals (see report section 4.3).
    """
    if stall.get("status") != "OPEN":
        raise ApiError(409, "stall is currently closed")
    if not idempotency_key or len(idempotency_key) > 80:
        raise ApiError(400, "Idempotency-Key header is required (max 80 chars)")
    if not isinstance(requested, list) or not 1 <= len(requested) <= MAX_LINES:
        raise ApiError(400, f"order must contain 1-{MAX_LINES} lines")

    by_id = {m["itemId"]: m for m in menu_items}
    lines, total = [], 0
    for req in requested:
        item = by_id.get((req or {}).get("itemId"))
        if item is None:
            raise ApiError(400, f"unknown menu item: {(req or {}).get('itemId')}")
        if not item.get("available", True):
            raise ApiError(409, f"item is unavailable: {item['name']}")
        qty = req.get("qty")
        if not isinstance(qty, int) or not 1 <= qty <= MAX_QTY:
            raise ApiError(400, f"qty must be an integer between 1 and {MAX_QTY}")
        line_total = int(item["priceCents"]) * qty
        total += line_total
        lines.append(
            {
                "itemId": item["itemId"],
                "name": item["name"],
                "priceCents": int(item["priceCents"]),
                "qty": qty,
                "lineTotalCents": line_total,
            }
        )

    return {
        "orderId": order_id_for(user_sub, idempotency_key),
        "userSub": user_sub,
        "stallId": stall["stallId"],
        "stallName": stall["name"],
        "status": "PLACED",
        "paymentStatus": "SIMULATED_PAID",  # AD-09: payment is simulated in this phase
        "lines": lines,
        "totalCents": total,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "history": [{"status": "PLACED", "at": now_iso}],
    }
