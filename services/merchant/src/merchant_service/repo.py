"""Merchant persistence: stall profile items in the single platform table."""
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from shared.http import ApiError, table_name

_KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "type", "ttl")


def _table():
    return boto3.resource("dynamodb").Table(table_name())


def clean(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in _KEYS}


def put_stall(stall: dict) -> None:
    item = {
        "PK": f"STALL#{stall['stallId']}",
        "SK": "PROFILE",
        "GSI1PK": f"CENTRE#{stall['centreId']}",
        "GSI1SK": f"STALL#{stall['stallId']}",
        "GSI2PK": f"OWNER#{stall['ownerSub']}",
        "GSI2SK": f"STALL#{stall['stallId']}",
        "type": "STALL",
        **stall,
    }
    try:
        _table().put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ApiError(409, "stall already exists") from exc
        raise


def get_stall(stall_id: str) -> dict:
    out = _table().get_item(Key={"PK": f"STALL#{stall_id}", "SK": "PROFILE"})
    item = out.get("Item")
    if not item:
        raise ApiError(404, "stall not found")
    return clean(item)


def list_by_owner(owner_sub: str) -> list:
    out = _table().query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"OWNER#{owner_sub}")
        & Key("GSI2SK").begins_with("STALL#"),
    )
    return [clean(i) for i in out.get("Items", [])]


def set_status(stall_id: str, status: str) -> dict:
    out = _table().update_item(
        Key={"PK": f"STALL#{stall_id}", "SK": "PROFILE"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
        ReturnValues="ALL_NEW",
    )
    return clean(out["Attributes"])
