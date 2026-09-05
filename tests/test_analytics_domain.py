from analytics_service import domain

EVENT = {
    "type": "OrderCollected", "at": "2026-10-01T13:10:00Z", "totalCents": 900,
    "lines": [{"name": "Chicken rice", "qty": 2}, {"name": "Laksa", "qty": 1}],
}


def test_fold_accumulates_orders_revenue_and_item_counts():
    first = domain.fold(domain.empty_aggregate(), EVENT)
    second = domain.fold(first, {**EVENT, "totalCents": 600, "lines": [{"name": "Laksa", "qty": 2}]})
    assert second["orders"] == 2
    assert second["revenueCents"] == 1500
    assert second["items"] == {"Chicken rice": 2, "Laksa": 3}


def test_fold_does_not_mutate_the_input_aggregate():
    base = domain.empty_aggregate()
    domain.fold(base, EVENT)
    assert base == domain.empty_aggregate()


def test_date_of_extracts_the_day():
    assert domain.date_of(EVENT) == "2026-10-01"
    assert domain.date_of({}) == "unknown"
