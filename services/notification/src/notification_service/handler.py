"""Notification service.

SQS consumer: turns domain events into notification items the diner app polls.
HTTP route:   GET /v1/me/notifications
Idempotent by design: notifications are keyed by (orderId, status), so an
at-least-once redelivery overwrites the same item instead of duplicating it.
"""
import json
import logging
import time

import boto3
from boto3.dynamodb.conditions import Key
from shared.http import ApiError, error, resp, sub, table_name

log = logging.getLogger()
log.setLevel(logging.INFO)

NOTIF_TTL_SECONDS = 30 * 24 * 3600

_MESSAGES = {
    "OrderPlaced": "Order received by {stall}. Waiting for the stall to accept.",
    "OrderAccepted": "{stall} accepted your order.",
    "OrderRejected": "{stall} could not take your order. You were not charged.",
    "OrderPreparing": "{stall} is preparing your food.",
    "OrderReady": "Your order at {stall} is ready for collection!",
    "OrderCollected": "Enjoy your meal from {stall}. See you again!",
    "OrderCancelled": "Your order at {stall} was cancelled.",
}


def _table():
    return boto3.resource("dynamodb").Table(table_name())


def lambda_handler(event, _context):
    if "Records" in event:  # SQS invocation
        return _consume(event)
    try:  # HTTP invocation
        if event.get("routeKey") == "GET /v1/me/notifications":
            return resp(200, {"notifications": _list_for_user(sub(event))})
        raise ApiError(404, "route not found")
    except ApiError as exc:
        return error(exc.status, exc.message)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error")
        return error(500, "internal error")


def _consume(event):
    table = _table()
    for record in event["Records"]:
        evt = json.loads(record["body"])
        template = _MESSAGES.get(evt.get("type"))
        if not template or not evt.get("userSub"):
            continue
        table.put_item(
            Item={
                "PK": f"USER#{evt['userSub']}",
                "SK": f"NOTIF#{evt['at']}#{evt['orderId']}#{evt['status']}",
                "type": "NOTIFICATION",
                "orderId": evt["orderId"],
                "status": evt["status"],
                "message": template.format(stall=evt.get("stallName", "the stall")),
                "at": evt["at"],
                "ttl": int(time.time()) + NOTIF_TTL_SECONDS,
            }
        )
    return {"processed": len(event["Records"])}


def _list_for_user(user_sub: str, limit: int = 20) -> list:
    out = _table().query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_sub}") & Key("SK").begins_with("NOTIF#"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [
        {k: v for k, v in item.items() if k in ("orderId", "status", "message", "at")}
        for item in out.get("Items", [])
    ]
