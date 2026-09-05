"""Ordering service - order intake and lifecycle API."""
import logging
from datetime import datetime, timezone

from shared.http import (
    ApiError,
    error,
    groups,
    header,
    json_body,
    path_param,
    query_param,
    resp,
    sub,
)

from . import domain, repo

log = logging.getLogger()
log.setLevel(logging.INFO)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def lambda_handler(event, _context):
    try:
        return _route(event)
    except ApiError as exc:
        return error(exc.status, exc.message)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error")
        return error(500, "internal error")


def _route(event):
    key = event.get("routeKey", "")

    if key == "POST /v1/orders":
        user = sub(event)
        body = json_body(event)
        stall_id = body.get("stallId") or ""
        stall, menu = repo.get_stall_and_menu(stall_id)
        order = domain.build_order(
            user, stall, menu, body.get("items"), header(event, "idempotency-key"), _now_iso()
        )
        saved, created = repo.create_order(order)
        return resp(201 if created else 200, saved)

    if key == "GET /v1/orders/{orderId}":
        order = repo.get_order(path_param(event, "orderId"))
        _authorize_read(event, order)
        return resp(200, order)

    if key == "GET /v1/me/orders":
        return resp(200, {"orders": repo.list_for_user(sub(event))})

    if key == "GET /v1/stalls/{stallId}/orders":
        stall_id = path_param(event, "stallId")
        _require_stall_owner(event, stall_id)
        status = query_param(event, "status")
        return resp(200, {"orders": repo.list_for_stall(stall_id, status)})

    if key == "PATCH /v1/orders/{orderId}":
        order = repo.get_order(path_param(event, "orderId"))
        new_status = domain.next_status(json_body(event).get("action"))
        domain.check_transition(
            order["status"],
            new_status,
            is_stall_owner=_is_stall_owner(event, order["stallId"]),
            is_order_owner=order["userSub"] == sub(event),
        )
        updated = repo.transition(order["orderId"], new_status, order["status"], _now_iso())
        return resp(200, updated)

    raise ApiError(404, "route not found")


def _is_stall_owner(event, stall_id: str) -> bool:
    if "stall-owner" not in groups(event):
        return False
    stall, _ = repo.get_stall_and_menu(stall_id)
    return stall.get("ownerSub") == sub(event)


def _require_stall_owner(event, stall_id: str):
    if not _is_stall_owner(event, stall_id):
        raise ApiError(403, "not the owner of this stall")


def _authorize_read(event, order: dict):
    if order["userSub"] == sub(event):
        return
    if _is_stall_owner(event, order["stallId"]):
        return
    raise ApiError(403, "not allowed to view this order")
