"""Shared helpers for HTTP API (payload v2) Lambda handlers."""
import base64
import json
import os


class ApiError(Exception):
    """Error carrying an HTTP status, raised from any layer and mapped by handlers."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def resp(status: int, body=None):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": "*",
        },
        "body": json.dumps(body if body is not None else {}),
    }


def error(status: int, message: str):
    return resp(status, {"error": message})


def claims(event) -> dict:
    return event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}


def sub(event) -> str:
    s = claims(event).get("sub")
    if not s:
        raise ApiError(401, "unauthenticated")
    return s


def groups(event) -> list:
    raw = claims(event).get("cognito:groups", "")
    if isinstance(raw, list):
        return raw
    return [g for g in str(raw).strip("[]").replace(",", " ").split() if g]


def require_group(event, group: str):
    if group not in groups(event):
        raise ApiError(403, f"requires group {group}")


def json_body(event) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid JSON body") from exc


def header(event, name: str):
    return (event.get("headers") or {}).get(name.lower())


def path_param(event, name: str) -> str:
    v = (event.get("pathParameters") or {}).get(name)
    if not v:
        raise ApiError(400, f"missing path parameter {name}")
    return v


def query_param(event, name: str):
    return (event.get("queryStringParameters") or {}).get(name)


def table_name() -> str:
    return os.environ["TABLE_NAME"]
