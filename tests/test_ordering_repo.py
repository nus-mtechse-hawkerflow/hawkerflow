"""Repository tests against a moto-mocked DynamoDB - proves the conditional-write design."""
import pytest
from ordering_service import domain, repo
from shared.http import ApiError

NOW = "2026-10-01T12:00:00.000000Z"
LATER = "2026-10-01T12:05:00.000000Z"


def _seed(table, stall, menu):
    table.put_item(Item={"PK": "STALL#stall-1", "SK": "PROFILE", "GSI1PK": "CENTRE#maxwell",
                         "GSI1SK": "STALL#stall-1", "GSI2PK": "OWNER#owner-sub",
                         "GSI2SK": "STALL#stall-1", "type": "STALL", **stall})
    for m in menu:
        table.put_item(Item={"PK": "STALL#stall-1", "SK": f"ITEM#{m['itemId']}", "type": "MENU_ITEM", **m})


def _new_order(stall, menu, key="k-1"):
    return domain.build_order("diner-sub", stall, menu, [{"itemId": "cr", "qty": 2}], key, NOW)


def test_duplicate_submission_returns_the_original_order(table, stall, menu):
    _seed(table, stall, menu)
    order = _new_order(stall, menu)
    first, created_first = repo.create_order(order)
    second, created_second = repo.create_order(_new_order(stall, menu))  # same idempotency key
    assert created_first is True and created_second is False
    assert first["orderId"] == second["orderId"]
    assert len(repo.list_for_user("diner-sub")) == 1


def test_get_stall_and_menu_splits_profile_and_items(table, stall, menu):
    _seed(table, stall, menu)
    profile, items = repo.get_stall_and_menu("stall-1")
    assert profile["name"] == stall["name"]
    assert {i["itemId"] for i in items} == {"cr", "laksa", "teh"}


def test_transition_moves_order_across_stall_queue_statuses(table, stall, menu):
    _seed(table, stall, menu)
    order, _ = repo.create_order(_new_order(stall, menu))
    assert [o["orderId"] for o in repo.list_for_stall("stall-1", "PLACED")] == [order["orderId"]]

    updated = repo.transition(order["orderId"], "ACCEPTED", "PLACED", LATER)
    assert updated["status"] == "ACCEPTED"
    assert updated["history"][-1] == {"status": "ACCEPTED", "at": LATER}
    assert repo.list_for_stall("stall-1", "PLACED") == []
    assert [o["orderId"] for o in repo.list_for_stall("stall-1", "ACCEPTED")] == [order["orderId"]]


def test_stale_transition_is_rejected_with_conflict(table, stall, menu):
    _seed(table, stall, menu)
    order, _ = repo.create_order(_new_order(stall, menu))
    repo.transition(order["orderId"], "ACCEPTED", "PLACED", LATER)
    with pytest.raises(ApiError) as exc:
        repo.transition(order["orderId"], "ACCEPTED", "PLACED", LATER)  # expected status is stale
    assert exc.value.status == 409


def test_missing_order_raises_not_found(table):
    with pytest.raises(ApiError) as exc:
        repo.get_order("does-not-exist")
    assert exc.value.status == 404
