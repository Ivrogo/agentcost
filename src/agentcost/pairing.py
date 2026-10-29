"""Paired A/B differences by task_id.

The CI gate reads :class:`Pairing`. ``--fail-if-worse`` on cost uses the
report verdict, which already uses the paired cost interval.
``--max-regression`` uses the lower bound of ``relative_interval``.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from agentcost.errors import CompareError
from agentcost.models import Interval, MetricDifference, Pairing, PairingMode
from agentcost.stats import quantile

RequestedPairing = Literal["auto", "paired", "unpaired"]


@dataclass(frozen=True, slots=True)
class TaskObservation:
    """One variant's aggregate for a single task_id."""

    task_id: str
    cost: Decimal
    tokens: int
    steps: int


def assess_pairing(
    first: Sequence[TaskObservation],
    second: Sequence[TaskObservation],
    *,
    first_name: str,
    second_name: str,
    requested: RequestedPairing = "auto",
    seed: int = 42,
    resamples: int = 1000,
    level: float = 0.95,
) -> Pairing:
    """Compare paired task differences, or record that pairing was not used.

    Differences are first minus second. Each metric is resampled with its own
    ``random.Random(seed)`` over task ids sorted lexicographically, so the
    cost interval does not depend on tokens, steps, or input order.

    Latency is omitted: trace events do not carry a duration.
    """
    if requested not in {"auto", "paired", "unpaired"}:
        raise CompareError("pairing must be auto, paired, or unpaired")
    if resamples < 1:
        raise CompareError("resamples must be >= 1")
    if not 0 < level < 1:
        raise CompareError("bootstrap level must be between 0 and 1")
    left = _by_id(first)
    right = _by_id(second)
    shared_ids = sorted(set(left) & set(right))
    shared = len(shared_ids)
    unmatched_first = len(left) - shared
    unmatched_second = len(right) - shared
    if requested == "paired" and shared == 0:
        raise CompareError(f"No shared task_id between {first_name!r} and {second_name!r}.")
    if requested == "unpaired" or shared == 0:
        warning = None
        if requested == "auto":
            warning = (
                f"No shared task_id between {first_name!r} and {second_name!r}. "
                "Using the unpaired comparison."
            )
        return Pairing(
            mode=PairingMode.UNPAIRED,
            requested=requested,
            pairs=0,
            shared=shared,
            unmatched_first=unmatched_first,
            unmatched_second=unmatched_second,
            warning=warning,
            cost=None,
            tokens=None,
            steps=None,
        )
    left_rows = [left[task_id] for task_id in shared_ids]
    right_rows = [right[task_id] for task_id in shared_ids]
    return Pairing(
        mode=PairingMode.PAIRED,
        requested=requested,
        pairs=shared,
        shared=shared,
        unmatched_first=unmatched_first,
        unmatched_second=unmatched_second,
        warning=None,
        cost=_difference(
            [row.cost for row in left_rows],
            [row.cost for row in right_rows],
            seed=seed,
            resamples=resamples,
            level=level,
        ),
        tokens=_difference(
            [Decimal(row.tokens) for row in left_rows],
            [Decimal(row.tokens) for row in right_rows],
            seed=seed,
            resamples=resamples,
            level=level,
        ),
        steps=_difference(
            [Decimal(row.steps) for row in left_rows],
            [Decimal(row.steps) for row in right_rows],
            seed=seed,
            resamples=resamples,
            level=level,
        ),
    )


def _by_id(tasks: Sequence[TaskObservation]) -> dict[str, TaskObservation]:
    found: dict[str, TaskObservation] = {}
    for task in tasks:
        if task.task_id in found:
            raise CompareError(f"duplicate task_id {task.task_id!r} in one variant")
        found[task.task_id] = task
    return found


def _difference(
    first: Sequence[Decimal],
    second: Sequence[Decimal],
    *,
    seed: int,
    resamples: int,
    level: float,
) -> MetricDifference:
    count = len(first)
    if count == 0 or count != len(second):
        raise CompareError("paired difference expects the same non-empty tasks on both sides")
    width = Decimal(count)
    diffs = [left - right for left, right in zip(first, second, strict=True)]
    mean = sum(diffs, start=Decimal(0)) / width
    mean_second = sum(second, start=Decimal(0)) / width
    relative = None if mean_second == 0 else mean / mean_second * Decimal(100)
    rng = random.Random(seed)
    means: list[Decimal] = []
    relatives: list[Decimal] = []
    for _ in range(resamples):
        total = Decimal(0)
        baseline = Decimal(0)
        for _ in range(count):
            index = rng.randrange(count)
            total += diffs[index]
            baseline += second[index]
        sampled = total / width
        means.append(sampled)
        sampled_baseline = baseline / width
        if sampled_baseline != 0:
            relatives.append(sampled / sampled_baseline * Decimal(100))
    alpha = (1 - level) / 2
    relative_interval = None
    if relatives:
        relative_interval = Interval(
            low=quantile(relatives, alpha),
            high=quantile(relatives, 1 - alpha),
        )
    return MetricDifference(
        mean_difference=mean,
        interval=Interval(low=quantile(means, alpha), high=quantile(means, 1 - alpha)),
        relative_percent=relative,
        relative_interval=relative_interval,
    )
