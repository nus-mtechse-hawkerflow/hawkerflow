"""Stream-record -> domain-event mapping (the outbox translation, AD-07)."""
from dispatcher_service import handler


def _order_image(status, updated=None):
    return {
        "PK": {"S": "ORDER#abc"}, "SK": {"S": "META"},
        "orderId": {"S": "abc"}, "stallId": {"S": "stall-1"},
        "stallName": {"S": "Ah Hock"}, "userSub": {"S": "diner-sub"},
        "status": {"S": status}, "totalCents": {"N": "900"},
        "createdAt": {"S": "2026-10-01T12:00:00Z"},
        **({"updatedAt": {"S": updated}} if updated else {}),
        "lines": {"L": [{"M": {"name": {"S": "Chicken rice"}, "qty": {"N": "2"}}}]},
    }


def test_insert_maps_to_order_placed():
    event = handler.to_event({"eventName": "INSERT", "dynamodb": {"NewImage": _order_image("PLACED")}})
    assert event["type"] == "OrderPlaced"
    assert event["totalCents"] == 900
    assert event["lines"] == [{"name": "Chicken rice", "qty": 2}]


def test_status_change_maps_to_lifecycle_event():
    event = handler.to_event({
        "eventName": "MODIFY",
        "dynamodb": {
            "OldImage": _order_image("PLACED"),
            "NewImage": _order_image("ACCEPTED", "2026-10-01T12:05:00Z"),
        },
    })
    assert event["type"] == "OrderAccepted"
    assert event["at"] == "2026-10-01T12:05:00Z"


def test_non_status_modify_is_ignored():
    images = {"OldImage": _order_image("PLACED"), "NewImage": _order_image("PLACED")}
    record = {"eventName": "MODIFY", "dynamodb": images}
    assert handler.to_event(record) is None


def test_non_order_items_are_ignored():
    stall = {"PK": {"S": "STALL#s1"}, "SK": {"S": "PROFILE"}, "status": {"S": "OPEN"}}
    assert handler.to_event({"eventName": "INSERT", "dynamodb": {"NewImage": stall}}) is None


def test_removes_are_ignored():
    assert handler.to_event({"eventName": "REMOVE", "dynamodb": {"NewImage": _order_image("PLACED")}}) is None
