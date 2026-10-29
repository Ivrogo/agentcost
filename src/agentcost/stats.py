"""Percentiles shared by the arm summary and the paired bootstrap."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal


def quantile(values: Sequence[Decimal], probability: float) -> Decimal:
    """Linear percentile. Same indexing as NumPy's linear method."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = Decimal(len(ordered) - 1) * Decimal(str(probability))
    low = int(rank.to_integral_value(rounding=ROUND_FLOOR))
    high = int(rank.to_integral_value(rounding=ROUND_CEILING))
    if low == high:
        return ordered[low]
    weight = rank - Decimal(low)
    return ordered[low] * (Decimal(1) - weight) + ordered[high] * weight
