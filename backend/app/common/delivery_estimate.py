"""Delivery estimate window: the vendor's own stated preparation time
(Vendor.preparation_days) plus transit_days, read from the same distance
grid as the delivery fee (see app/delivery/service.py::compute_transit_days)
rather than a separate heuristic — the duration shown to the buyer is
grounded in the same real geography as the price they see.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DeliveryEstimate:
    min_date: date
    max_date: date


def estimate_delivery_window(*, transit_days: int, preparation_days: int, from_date: date) -> DeliveryEstimate:
    min_days = max(preparation_days, 0) + max(transit_days, 0)
    return DeliveryEstimate(
        min_date=from_date + timedelta(days=min_days),
        max_date=from_date + timedelta(days=min_days + 1),
    )
