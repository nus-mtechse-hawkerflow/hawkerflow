import json
import os

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-1")

from order_intake_service import handler


def _event(idempotency_key="key-1"):
    return {
        "routeKey": "POST /v1/orders",
        "headers": {"idempotency-key": idempotency_key},
        "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "diner-sub"}}}},
        "body": json.dumps(
            {"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}
        ),
    }


def test_order_intake_enqueues_trusted_order_envelope(monkeypatch):
    monkeypatch.setenv("ORDER_INGESTION_QUEUE_URL", "https://queue.example/orders")
    messages = []
    monkeypatch.setattr(handler.sqs, "send_message", lambda **kwargs: messages.append(kwargs))

    result = handler.lambda_handler(_event(), None)

    assert result["statusCode"] == 202
    assert json.loads(result["body"]) == {"accepted": True}
    assert messages == [
        {
            "QueueUrl": "https://queue.example/orders",
            "MessageBody": json.dumps(
                {
                    "userSub": "diner-sub",
                    "idempotencyKey": "key-1",
                    "order": {
                        "stallId": "stall-1",
                        "items": [{"itemId": "cr", "qty": 1}],
                    },
                }
            ),
        }
    ]


def test_order_intake_rejects_blank_idempotency_key_before_enqueue(monkeypatch):
    monkeypatch.setattr(
        handler.sqs,
        "send_message",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("SQS must not be called")),
    )

    result = handler.lambda_handler(_event("   "), None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"]) == {"error": "idempotency-key is required"}
