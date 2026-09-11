import json

from ordering_service import handler


def _event(body, message_id="message-1"):
    return {
        "Records": [
            {
                "messageId": message_id,
                "body": json.dumps(body),
                "messageAttributes": {
                    "userSub": {"stringValue": "diner-sub"},
                    "idempotencyKey": {"stringValue": "key-1"},
                },
            }
        ]
    }


def test_queue_message_creates_an_order(monkeypatch, stall, menu):
    monkeypatch.setattr(handler.repo, "get_stall_and_menu", lambda _: (stall, menu))
    created = []
    monkeypatch.setattr(
        handler.repo,
        "create_order",
        lambda order: created.append(order) or (order, True),
    )
    result = handler.lambda_handler(
        _event({"stallId": "stall-1", "items": [{"itemId": "cr", "qty": 1}]}),
        None,
    )
    assert result == {"batchItemFailures": []}
    assert created[0]["userSub"] == "diner-sub"


def test_invalid_queue_message_is_reported_for_retry(monkeypatch):
    monkeypatch.setattr(
        handler.repo,
        "get_stall_and_menu",
        lambda _: (_ for _ in ()).throw(AssertionError()),
    )
    result = handler.lambda_handler(
        {
            "Records": [
                {
                    "messageId": "bad-1",
                    "body": "not-json",
                    "messageAttributes": {},
                }
            ]
        },
        None,
    )
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-1"}]}
