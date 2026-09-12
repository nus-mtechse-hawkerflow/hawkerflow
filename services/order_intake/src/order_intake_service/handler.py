"""Authenticated HTTP order intake boundary."""
import json
import logging
import os

import boto3
from shared.http import ApiError, error, header, json_body, resp, sub

log = logging.getLogger()
log.setLevel(logging.INFO)
sqs = boto3.client("sqs")


def lambda_handler(event, _context):
    try:
        return _route(event)
    except ApiError as exc:
        return error(exc.status, exc.message)
    except Exception:  # noqa: BLE001 - last-resort guard, details go to logs only
        log.exception("unhandled error")
        return error(500, "internal error")


def _route(event):
    if event.get("routeKey", "") != "POST /v1/orders":
        raise ApiError(404, "route not found")

    idempotency_key = (header(event, "idempotency-key") or "").strip()
    if not idempotency_key:
        raise ApiError(400, "idempotency-key is required")

    if event.get("body") in (None, ""):
        raise ApiError(400, "order body is required")

    order = json_body(event)
    if not isinstance(order, dict):
        raise ApiError(400, "order body must be a JSON object")

    envelope = {
        "userSub": sub(event),
        "idempotencyKey": idempotency_key,
        "order": order,
    }
    sqs.send_message(
        QueueUrl=os.environ["ORDER_INGESTION_QUEUE_URL"],
        MessageBody=json.dumps(envelope),
    )
    return resp(202, {"accepted": True})
