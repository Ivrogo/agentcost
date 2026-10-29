"""Trace and report types."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal


class EventKind(str, Enum):
    LLM = "llm"
    TOOL = "tool"


class EventStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class Verdict(str, Enum):
    """How the first variant compares with the second on cost per solved task."""

    BETTER = "better"
    WORSE = "worse"
    NO_DIFFERENCE = "no_difference"
    INCONCLUSIVE = "inconclusive"


class PairingMode(str, Enum):
    """Whether the report matched variants on ``task_id``."""

    PAIRED = "paired"
    UNPAIRED = "unpaired"


@dataclass(frozen=True, slots=True)
class Event:
    """One LLM or tool call."""

    task_id: str
    variant: str
    run_id: str
    kind: EventKind
    input_tokens: int
    output_tokens: int
    model: str | None
    status: EventStatus


@dataclass(frozen=True, slots=True)
class Quantiles:
    p25: Decimal
    median: Decimal
    p75: Decimal


@dataclass(frozen=True, slots=True)
class Interval:
    low: Decimal
    high: Decimal


@dataclass(frozen=True, slots=True)
class MetricDifference:
    """Mean of first minus second over paired tasks, with a bootstrap interval.

    ``relative_percent`` is ``100 * mean_difference / mean(second)``. It is
    ``None`` when the second variant's mean is 0. ``includes_zero`` is true
    when the interval contains 0, including an endpoint that lands on 0.
    """

    mean_difference: Decimal
    interval: Interval
    relative_percent: Decimal | None
    relative_interval: Interval | None

    @property
    def includes_zero(self) -> bool:
        return self.interval.low <= 0 <= self.interval.high

    @property
    def relative_includes_zero(self) -> bool | None:
        if self.relative_interval is None:
            return None
        return self.relative_interval.low <= 0 <= self.relative_interval.high


@dataclass(frozen=True, slots=True)
class Pairing:
    """Paired-difference result. Metric fields are ``None`` when ``mode`` is unpaired.

    ``pairs`` is the number of task ids used in the paired comparison (0 when
    unpaired). ``shared`` is how many task ids the two variants have in common,
    whether or not they were matched. ``unmatched_first`` and
    ``unmatched_second`` count task ids that appear on only one side, in
    ``--compare`` order.
    """

    mode: PairingMode
    requested: Literal["auto", "paired", "unpaired"]
    pairs: int
    shared: int
    unmatched_first: int
    unmatched_second: int
    warning: str | None
    cost: MetricDifference | None
    tokens: MetricDifference | None
    steps: MetricDifference | None


@dataclass(frozen=True, slots=True)
class ArmReport:
    variant: str
    tasks: int
    successful_tasks: int
    runs: int
    successful_runs: int
    failed_runs: int
    success_rate: Decimal
    total_cost: Decimal
    failed_run_cost: Decimal
    failed_run_tokens: int
    cost_per_solved_task: Decimal | None
    cost: Quantiles
    tokens: Quantiles
    steps: Quantiles
    unpriced_models: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Report:
    schema_version: str
    price_table_version: str
    currency: str
    variants: tuple[str, str]
    metric: str
    verdict: Verdict
    verdict_reason: str
    arms: tuple[ArmReport, ArmReport]
    bootstrap_seed: int
    bootstrap_resamples: int
    bootstrap_level: float
    intervals: dict[str, Interval]
    pairing: Pairing

    def arm(self, variant: str) -> ArmReport:
        for item in self.arms:
            if item.variant == variant:
                return item
        raise KeyError(variant)
