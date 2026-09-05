"""Pure domain tests for the ordering state machine and pricing - no AWS needed."""
import pytest
from ordering_service import domain
from shared.http import ApiError

NOW = "2026-10-01T12:00:00.000000Z"


def _build(stall, menu, items, key="k-1"):
    return domain.build_order("diner-sub", stall, menu, items, key, NOW)


def test_order_id_is_deterministic_per_user_and_key():
    a = domain.order_id_for("u1", "key-1")
    assert a == domain.order_id_for("u1", "key-1")
    assert a != domain.order_id_for("u1", "key-2")
    assert a != domain.order_id_for("u2", "key-1")


def test_build_order_prices_come_from_the_server_catalog(stall, menu):
    order = _build(stall, menu, [{"itemId": "cr", "qty": 2, "priceCents": 1}, {"itemId": "laksa", "qty": 1}])
    assert order["totalCents"] == 2 * 450 + 600  # client-sent priceCents=1 is ignored
    assert order["status"] == "PLACED"
    assert order["paymentStatus"] == "SIMULATED_PAID"
    assert order["history"][0]["status"] == "PLACED"


@pytest.mark.parametrize(
    "items,status",
    [
        ([{"itemId": "nope", "qty": 1}], 400),
        ([{"itemId": "teh", "qty": 1}], 409),
        ([{"itemId": "cr", "qty": 0}], 400),
        ([{"itemId": "cr", "qty": 21}], 400),
        ([{"itemId": "cr", "qty": "2"}], 400),
        ([], 400),
    ],
)
def test_build_order_rejects_bad_lines(stall, menu, items, status):
    with pytest.raises(ApiError) as exc:
        _build(stall, menu, items)
    assert exc.value.status == status


def test_build_order_rejects_closed_stall(stall, menu):
    stall["status"] = "CLOSED"
    with pytest.raises(ApiError) as exc:
        _build(stall, menu, [{"itemId": "cr", "qty": 1}])
    assert exc.value.status == 409


def test_build_order_requires_idempotency_key(stall, menu):
    with pytest.raises(ApiError) as exc:
        _build(stall, menu, [{"itemId": "cr", "qty": 1}], key="")
    assert exc.value.status == 400


def test_unknown_action_is_rejected():
    with pytest.raises(ApiError) as exc:
        domain.next_status("explode")
    assert exc.value.status == 400


def test_stall_transitions_require_the_stall_owner():
    domain.check_transition("PLACED", "ACCEPTED", is_stall_owner=True, is_order_owner=False)
    with pytest.raises(ApiError) as exc:
        domain.check_transition("PLACED", "ACCEPTED", is_stall_owner=False, is_order_owner=True)
    assert exc.value.status == 403


def test_diner_can_cancel_only_before_preparation():
    domain.check_transition("PLACED", "CANCELLED", is_stall_owner=False, is_order_owner=True)
    domain.check_transition("ACCEPTED", "CANCELLED", is_stall_owner=False, is_order_owner=True)
    with pytest.raises(ApiError) as exc:
        domain.check_transition("PREPARING", "CANCELLED", is_stall_owner=False, is_order_owner=True)
    assert exc.value.status == 409


def test_terminal_states_admit_no_transitions():
    for terminal in ("COLLECTED", "REJECTED", "CANCELLED"):
        with pytest.raises(ApiError) as exc:
            domain.check_transition(terminal, "ACCEPTED", is_stall_owner=True, is_order_owner=True)
        assert exc.value.status == 409


def test_full_happy_path_is_permitted():
    path = ["PLACED", "ACCEPTED", "PREPARING", "READY", "COLLECTED"]
    for current, new in zip(path, path[1:], strict=False):
        domain.check_transition(current, new, is_stall_owner=True, is_order_owner=False)
