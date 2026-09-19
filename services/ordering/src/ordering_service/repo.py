"""Ordering persistence: conditional writes give idempotent creation and safe transitions."""
import logging
import os
import time
from decimal import Decimal
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from shared.http import ApiError, table_name

logger = logging.getLogger(__name__)

_KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "type", "ttl")
DEFAULT_ORDER_TTL_DAYS = 90


@lru_cache(maxsize=1)
def _order_ttl_seconds() -> int:
    """Online retention: env override (tests/local) > SSM parameter > default."""
    env_days = os.environ.get("ORDER_TTL_DAYS")
    if env_days:
        return int(env_days) * 86400

    param = os.environ.get("ORDER_TTL_PARAM")
    if param:
        try:
            value = boto3.client("ssm").get_parameter(Name=param)["Parameter"]["Value"]
            return int(value) * 86400
        except (ClientError, ValueError, KeyError) as exc:
            logger.warning(
                "Unable to read valid order TTL from SSM parameter %s; "
                "using default of %d days: %s",
                param,
                DEFAULT_ORDER_TTL_DAYS,
                exc,
            )

    return DEFAULT_ORDER_TTL_DAYS * 86400

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


def clean(item: dict) -> dict:
    return {k: _undecimal(v) for k, v in item.items() if k not in _KEYS}


def create_order(order: dict) -> tuple:
    """Conditional put keyed by the idempotency-derived orderId.

    Returns (order, created). A duplicate submission returns the original order.
    """
    item = {
        "PK": f"ORDER#{order['orderId']}",
        "SK": "META",
        "GSI1PK": f"STALL#{order['stallId']}",
        "GSI1SK": f"STATUS#{order['status']}#{order['createdAt']}",
        "GSI2PK": f"USER#{order['userSub']}",
        "GSI2SK": f"ORDER#{order['createdAt']}",
        "type": "ORDER",
        "ttl": int(time.time()) + _order_ttl_seconds(),
        **order,
    }
    try:
        _table().put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
        return order, True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return get_order(order["orderId"]), False
        raise


def get_order(order_id: str) -> dict:
    out = _table().get_item(Key={"PK": f"ORDER#{order_id}", "SK": "META"})
    item = out.get("Item")
    if not item:
        raise ApiError(404, "order not found")
    return clean(item)


def transition(order_id: str, new_status: str, expected_status: str, at_iso: str) -> dict:
    """Optimistic concurrency: the write succeeds only if the status is still `expected_status`."""
    try:
        out = _table().update_item(
            Key={"PK": f"ORDER#{order_id}", "SK": "META"},
            UpdateExpression=(
                "SET #s = :new, GSI1SK = :gsi, updatedAt = :at, "
                "history = list_append(history, :h)"
            ),
            ConditionExpression="#s = :expected",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":new": new_status,
                ":expected": expected_status,
                ":gsi": f"STATUS#{new_status}#{at_iso}",
                ":at": at_iso,
                ":h": [{"status": new_status, "at": at_iso}],
            },
            ReturnValues="ALL_NEW",
        )
        return clean(out["Attributes"])
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(409, "order status changed concurrently - refresh and retry") from exc
        raise


def list_for_user(user_sub: str, limit: int = 25) -> list:
    out = _table().query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"USER#{user_sub}")
        & Key("GSI2SK").begins_with("ORDER#"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [clean(i) for i in out.get("Items", [])]


def list_for_stall(stall_id: str, status: str = None, limit: int = 50) -> list:
    prefix = f"STATUS#{status}#" if status else "STATUS#"
    out = _table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"STALL#{stall_id}")
        & Key("GSI1SK").begins_with(prefix),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [clean(i) for i in out.get("Items", [])]


def get_stall_and_menu(stall_id: str) -> tuple:
    out = _table().query(KeyConditionExpression=Key("PK").eq(f"STALL#{stall_id}"))
    profile, items = None, []
    for item in out.get("Items", []):
        if item["SK"] == "PROFILE":
            profile = clean(item)
        elif item["SK"].startswith("ITEM#"):
            items.append(clean(item))
    if profile is None:
        raise ApiError(404, "stall not found")
    return profile, items
