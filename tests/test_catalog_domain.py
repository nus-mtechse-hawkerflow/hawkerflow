import pytest
from catalog_service import domain
from shared.http import ApiError


def test_valid_item_defaults_available_to_true():
    item = domain.validate_item("cr", {"name": "Chicken rice", "priceCents": 450})
    assert item == {"itemId": "cr", "name": "Chicken rice", "priceCents": 450, "available": True}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "priceCents": 450},
        {"name": "x" * 61, "priceCents": 450},
        {"name": "ok", "priceCents": 0},
        {"name": "ok", "priceCents": 4.5},
        {"name": "ok", "priceCents": 200_000},
        {"name": "ok", "priceCents": 450, "available": "yes"},
    ],
)
def test_invalid_items_are_rejected(payload):
    with pytest.raises(ApiError) as exc:
        domain.validate_item("cr", payload)
    assert exc.value.status == 400
