"""Authenticated HTTP order intake boundary."""
import json
import os

import boto3
from shared.http import ApiError, error, header, json_body, resp, sub
from shared.observability import configure_logging, correlation_id, log_extra

log = configure_logging("order-intake")
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

    request_correlation_id = correlation_id(event)
    envelope = {
        "userSub": sub(event),
        "idempotencyKey": idempotency_key,
        "correlationId": request_correlation_id,
        "order": order,
    }
    sqs.send_message(
        QueueUrl=os.environ["ORDER_INGESTION_QUEUE_URL"],
        MessageBody=json.dumps(envelope),
    )
    log.info("order accepted for processing", extra=log_extra(request_correlation_id, event="order_queued"))
    return resp(202, {"accepted": True})
