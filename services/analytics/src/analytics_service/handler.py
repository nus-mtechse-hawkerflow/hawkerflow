"""Analytics service.

SQS consumer: folds OrderCollected events into per-stall daily aggregates.
HTTP route:   GET /v1/stalls/{stallId}/analytics?days=N (stall owner only)

Idempotency for at-least-once delivery: a conditional marker item per order
(ORDER#<id> / AGGDONE) guarantees each order is counted exactly once, so the
read-modify-write on the aggregate is safe to retry.
"""
import json
import logging
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from shared.http import ApiError, error, path_param, query_param, require_group, resp, sub, table_name

from . import domain

log = logging.getLogger()
log.setLevel(logging.INFO)


def _table():
    return boto3.resource("dynamodb").Table(table_name())


def _undecimal(value):
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, list):
        return [_undecimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _undecimal(v) for k, v in value.items()}
    return value


def lambda_handler(event, _context):
    if "Records" in event:
        return _consume(event)
    try:
        if event.get("routeKey") == "GET /v1/stalls/{stallId}/analytics":
            return _analytics_api(event)
        raise ApiError(404, "route not found")
    except ApiError as exc:
        return error(exc.status, exc.message)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error")
        return error(500, "internal error")


def _consume(event):
    table = _table()
    folded = 0
    for record in event["Records"]:
        evt = json.loads(record["body"])
        if evt.get("type") != "OrderCollected":
            continue
        if not _mark_processed(table, evt["orderId"]):
            continue  # already counted - safe redelivery
        date = domain.date_of(evt)
        key = {"PK": f"STALL#{evt['stallId']}", "SK": f"AGG#{date}"}
        current = _undecimal(table.get_item(Key=key).get("Item") or {})
        aggregate = domain.fold(current or domain.empty_aggregate(), evt)
        table.put_item(Item={**key, "type": "AGGREGATE", "date": date, **aggregate})
        folded += 1
    return {"folded": folded}


def _mark_processed(table, order_id: str) -> bool:
    try:
        table.put_item(
            Item={"PK": f"ORDER#{order_id}", "SK": "AGGDONE", "type": "AGG_MARKER"},
            ConditionExpression="attribute_not_exists(PK) OR attribute_not_exists(SK)",
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def _analytics_api(event):
    stall_id = path_param(event, "stallId")
    require_group(event, "stall-owner")
    stall = _table().get_item(Key={"PK": f"STALL#{stall_id}", "SK": "PROFILE"}).get("Item")
    if not stall:
        raise ApiError(404, "stall not found")
    if stall.get("ownerSub") != sub(event):
        raise ApiError(403, "not the owner of this stall")
    days = min(int(query_param(event, "days") or 7), 31)
    out = _table().query(
        KeyConditionExpression=Key("PK").eq(f"STALL#{stall_id}") & Key("SK").begins_with("AGG#"),
        ScanIndexForward=False,
        Limit=days,
    )
    daily = [
        {k: _undecimal(v) for k, v in item.items() if k in ("date", "orders", "revenueCents", "items")}
        for item in out.get("Items", [])
    ]
    return resp(200, {"stallId": stall_id, "daily": daily})
