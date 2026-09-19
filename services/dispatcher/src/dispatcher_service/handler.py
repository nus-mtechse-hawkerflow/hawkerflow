"""Dispatcher - transactional outbox (AD-07).

Reads the committed DynamoDB change stream and publishes domain events to the
notification and analytics queues. Publishing from the stream (not from the
Ordering function) avoids the dual-write problem: an order can never be saved
without its event eventually being delivered (at-least-once).
"""
import json
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer
from shared.observability import configure_logging, log_extra

log = configure_logging("dispatcher")

_DESERIALIZER = TypeDeserializer()
_STATUS_EVENT = {
    "ACCEPTED": "OrderAccepted",
    "REJECTED": "OrderRejected",
    "PREPARING": "OrderPreparing",
    "READY": "OrderReady",
    "COLLECTED": "OrderCollected",
    "CANCELLED": "OrderCancelled",
}


def _image(raw: dict) -> dict:
    return {k: _DESERIALIZER.deserialize(v) for k, v in (raw or {}).items()}


def to_event(record: dict):
    """Map one stream record to a domain event, or None if it is not order-relevant."""
    change = record.get("dynamodb", {})
    new = _image(change.get("NewImage"))
    if new.get("SK") != "META" or not str(new.get("PK", "")).startswith("ORDER#"):
        return None

    name = record.get("eventName")
    if name == "INSERT":
        event_type = "OrderPlaced"
    elif name == "MODIFY":
        old = _image(change.get("OldImage"))
        if old.get("status") == new.get("status"):
            return None  # not a lifecycle change (e.g. TTL bookkeeping)
        event_type = _STATUS_EVENT.get(str(new.get("status")))
        if event_type is None:
            return None
    else:
        return None

    return {
        "type": event_type,
        "orderId": new.get("orderId"),
        "stallId": new.get("stallId"),
        "stallName": new.get("stallName"),
        "userSub": new.get("userSub"),
        "status": new.get("status"),
        "totalCents": int(new.get("totalCents", 0)),
        "lines": [
            {"name": ln.get("name"), "qty": int(ln.get("qty", 0))}
            for ln in new.get("lines", [])
        ],
        "at": new.get("updatedAt") or new.get("createdAt"),
        "correlationId": new.get("correlationId") or new.get("orderId"),
    }


def lambda_handler(event, _context):
    sqs = boto3.client("sqs")
    queues = [os.environ["NOTIF_QUEUE_URL"], os.environ["ANALYTICS_QUEUE_URL"]]
    published = 0
    for record in event.get("Records", []):
        domain_event = to_event(record)
        if domain_event is None:
            continue
        body = json.dumps(domain_event)
        for queue_url in queues:
            sqs.send_message(QueueUrl=queue_url, MessageBody=body)
        published += 1
    log.info("published events", extra=log_extra("batch", event="events_published", published=published))
    return {"published": published}
