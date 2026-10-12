"""Trace and report types."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


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

    def arm(self, variant: str) -> ArmReport:
        for item in self.arms:
            if item.variant == variant:
                return item
        raise KeyError(variant)
