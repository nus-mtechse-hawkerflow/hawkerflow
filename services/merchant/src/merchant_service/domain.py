"""Merchant domain rules: producer (stall) onboarding and lifecycle."""
import re
import uuid

from shared.http import ApiError

STALL_STATUSES = {"OPEN", "CLOSED"}


def new_stall(owner_sub: str, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    centre_id = (payload.get("centreId") or "").strip().lower()
    if not 2 <= len(name) <= 60:
        raise ApiError(400, "stall name must be 2-60 characters")
    if not re.fullmatch(r"[a-z0-9-]{2,40}", centre_id):
        raise ApiError(400, "centreId must be a slug of 2-40 chars (a-z, 0-9, -)")
    return {
        "stallId": uuid.uuid4().hex[:12],
        "name": name,
        "centreId": centre_id,
        "ownerSub": owner_sub,
        "status": "OPEN",
        "description": (payload.get("description") or "").strip()[:200],
    }


def validate_status(status: str) -> str:
    if status not in STALL_STATUSES:
        raise ApiError(400, f"status must be one of {sorted(STALL_STATUSES)}")
    return status
