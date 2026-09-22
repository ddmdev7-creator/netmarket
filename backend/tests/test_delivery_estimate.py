"""Unit tests for the delivery estimate window (no DB needed — pure
function). See app/common/delivery_estimate.py for the rationale."""

from datetime import date

from app.common.delivery_estimate import estimate_delivery_window


def test_window_is_preparation_plus_transit() -> None:
    result = estimate_delivery_window(transit_days=1, preparation_days=2, from_date=date(2026, 8, 10))

    assert result.min_date == date(2026, 8, 13)
    assert result.max_date == date(2026, 8, 14)


def test_zero_transit_ships_after_preparation_alone() -> None:
    result = estimate_delivery_window(transit_days=0, preparation_days=1, from_date=date(2026, 8, 10))

    assert result.min_date == date(2026, 8, 11)
    assert result.max_date == date(2026, 8, 12)


def test_negative_preparation_days_is_clamped_to_zero() -> None:
    result = estimate_delivery_window(transit_days=1, preparation_days=-3, from_date=date(2026, 8, 10))

    assert result.min_date == date(2026, 8, 11)


def test_negative_transit_days_is_clamped_to_zero() -> None:
    result = estimate_delivery_window(transit_days=-2, preparation_days=1, from_date=date(2026, 8, 10))

    assert result.min_date == date(2026, 8, 11)
