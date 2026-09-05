"""Catalog persistence: stall profiles (read) and menu items."""
import boto3
from boto3.dynamodb.conditions import Key
from shared.http import ApiError, table_name

_KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "type", "ttl")


def _table():
    return boto3.resource("dynamodb").Table(table_name())


def clean(item: dict) -> dict:
    out = {k: v for k, v in item.items() if k not in _KEYS}
    if "priceCents" in out:
        out["priceCents"] = int(out["priceCents"])
    return out


def get_stall(stall_id: str) -> dict:
    out = _table().get_item(Key={"PK": f"STALL#{stall_id}", "SK": "PROFILE"})
    item = out.get("Item")
    if not item:
        raise ApiError(404, "stall not found")
    return clean(item)


def list_stalls_by_centre(centre_id: str) -> list:
    out = _table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"CENTRE#{centre_id}")
        & Key("GSI1SK").begins_with("STALL#"),
    )
    return [clean(i) for i in out.get("Items", [])]


def get_menu(stall_id: str) -> list:
    out = _table().query(
        KeyConditionExpression=Key("PK").eq(f"STALL#{stall_id}") & Key("SK").begins_with("ITEM#")
    )
    return [clean(i) for i in out.get("Items", [])]


def put_item(stall_id: str, item: dict) -> dict:
    _table().put_item(
        Item={
            "PK": f"STALL#{stall_id}",
            "SK": f"ITEM#{item['itemId']}",
            "type": "MENU_ITEM",
            **item,
        }
    )
    return item
