"""Paired A/B comparison by task_id."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from agentcost import (
    CompareError,
    Event,
    EventKind,
    EventStatus,
    MetricDifference,
    ModelPrice,
    PairingMode,
    PriceTable,
    Verdict,
    compare,
    render_json,
    render_markdown,
)

PRICES = PriceTable(
    version="test",
    currency="USD",
    models={"m": ModelPrice(Decimal("1"), Decimal("1"))},
)


def ev(
    *,
    task_id: str,
    variant: str,
    input_tokens: int,
    run_id: str = "r",
) -> Event:
    return Event(
        task_id=task_id,
        variant=variant,
        run_id=run_id,
        kind=EventKind.LLM,
        input_tokens=input_tokens,
        output_tokens=0,
        model="m",
        status=EventStatus.OK,
    )


def paired_events(costs: list[tuple[int, int]]) -> list[Event]:
    """One run per task. Cost in USD equals input tokens / 1e6. Pairs are (A, B)."""
    events: list[Event] = []
    for index, (left, right) in enumerate(costs, start=1):
        task_id = f"t{index}"
        events.append(ev(task_id=task_id, variant="A", input_tokens=left))
        events.append(ev(task_id=task_id, variant="B", input_tokens=right))
    return events


def test_constant_pairs_have_a_known_difference() -> None:
    # A costs 2, B costs 5. Difference is -3 on every task. Relative change is -60%.
    events = paired_events([(2_000_000, 5_000_000)] * 5)
    report = compare(events, ("A", "B"), prices=PRICES, seed=42, resamples=50)
    assert report.pairing.mode is PairingMode.PAIRED
    assert report.pairing.requested == "auto"
    assert report.pairing.pairs == 5
    assert report.pairing.unmatched_first == 0
    assert report.pairing.unmatched_second == 0
    assert report.pairing.warning is None
    cost = report.pairing.cost
    assert isinstance(cost, MetricDifference)
    assert cost.mean_difference == Decimal("-3")
    assert cost.interval.low == Decimal("-3")
    assert cost.interval.high == Decimal("-3")
    assert cost.includes_zero is False
    assert cost.relative_percent == Decimal("-60")
    assert cost.relative_interval is not None
    assert cost.relative_interval.low == Decimal("-60")
    assert cost.relative_interval.high == Decimal("-60")
    assert cost.relative_includes_zero is False
    tokens = report.pairing.tokens
    assert tokens is not None
    assert tokens.mean_difference == Decimal("-3000000")
    assert tokens.includes_zero is False
    steps = report.pairing.steps
    assert steps is not None
    assert steps.mean_difference == Decimal("0")
    assert steps.includes_zero is True
    assert steps.relative_percent == Decimal("0")
    assert report.verdict is Verdict.BETTER
    assert report.arm("A").tasks == 5
    assert report.arm("A").cost_per_solved_task == Decimal("2")

    payload = json.loads(render_json(report))
    assert payload["schema_version"] == "0.1"
    assert payload["pairing"]["mode"] == "paired"
    assert payload["pairing"]["pairs"] == 5
    assert payload["pairing"]["metrics"]["cost"]["includes_zero"] is False
    assert payload["pairing"]["metrics"]["cost"]["mean_difference"] == -3
    assert payload["pairing"]["metrics"]["cost"]["interval"] == {"low": -3, "high": -3}
    text = render_markdown(report)
    assert "**Pairing:** paired (5 pairs)." in text
    assert "The cost interval does not include 0." in text
    assert "Left out" not in text


def test_interval_includes_zero_when_the_paired_spread_crosses_it() -> None:
    # Differences 1, 1, 1, 1, -3. Mean 0.2. B is 4 on every task.
    # Seed 42 and 1000 resamples: cost CI [-1.4, 1], relative CI [-35, 25].
    events = paired_events(
        [
            (5_000_000, 4_000_000),
            (5_000_000, 4_000_000),
            (5_000_000, 4_000_000),
            (5_000_000, 4_000_000),
            (1_000_000, 4_000_000),
        ]
    )
    report = compare(events, ("A", "B"), prices=PRICES, seed=42, resamples=1000)
    cost = report.pairing.cost
    assert cost is not None
    assert cost.mean_difference == Decimal("0.2")
    assert cost.interval.low == Decimal("-1.4")
    assert cost.interval.high == Decimal("1")
    assert cost.includes_zero is True
    assert cost.relative_percent == Decimal("5")
    assert cost.relative_interval is not None
    assert cost.relative_interval.low == Decimal("-35")
    assert cost.relative_interval.high == Decimal("25")
    assert cost.relative_includes_zero is True
    assert report.verdict is Verdict.INCONCLUSIVE
    assert "includes 0" in report.verdict_reason
    assert "includes 0" in render_markdown(report)
    payload = json.loads(render_json(report))
    assert payload["pairing"]["metrics"]["cost"]["includes_zero"] is True


def test_interval_excludes_zero_for_a_uniform_gap() -> None:
    events = paired_events([(9_000_000, 1_000_000)] * 5)
    report = compare(events, ("A", "B"), prices=PRICES, seed=1, resamples=20)
    cost = report.pairing.cost
    assert cost is not None
    assert cost.mean_difference == Decimal("8")
    assert cost.includes_zero is False
    assert cost.interval.high < 0 or cost.interval.low > 0
    assert report.verdict is Verdict.WORSE


def test_partial_pairing_drops_tasks_that_are_only_on_one_side() -> None:
    events = [
        ev(task_id="t1", variant="A", input_tokens=1_000_000),
        ev(task_id="t2", variant="A", input_tokens=2_000_000),
        ev(task_id="t3", variant="A", input_tokens=3_000_000),
        ev(task_id="t2", variant="B", input_tokens=2_000_000),
        ev(task_id="t3", variant="B", input_tokens=4_000_000),
        ev(task_id="t4", variant="B", input_tokens=9_000_000),
    ]
    report = compare(events, ("A", "B"), prices=PRICES, resamples=10)
    assert report.pairing.mode is PairingMode.PAIRED
    assert report.pairing.pairs == 2
    assert report.pairing.shared == 2
    assert report.pairing.unmatched_first == 1
    assert report.pairing.unmatched_second == 1
    cost = report.pairing.cost
    assert cost is not None
    assert cost.mean_difference == Decimal("-0.5")
    assert report.arm("A").tasks == 2
    assert report.arm("B").tasks == 2
    assert report.arm("A").total_cost == Decimal("5")
    assert report.arm("B").total_cost == Decimal("6")
    text = render_markdown(report)
    assert "Left out: A 1, B 1." in text
    payload = json.loads(render_json(report))
    assert payload["pairing"]["unmatched"] == {"A": 1, "B": 1}
    assert payload["pairing"]["pairs"] == 2


def test_no_shared_task_id_falls_back_and_warns() -> None:
    events = [
        ev(task_id="a1", variant="A", input_tokens=1_000_000),
        ev(task_id="b1", variant="B", input_tokens=4_000_000),
    ]
    report = compare(events, ("A", "B"), prices=PRICES, resamples=10)
    assert report.pairing.mode is PairingMode.UNPAIRED
    assert report.pairing.pairs == 0
    assert report.pairing.shared == 0
    assert report.pairing.cost is None
    assert report.pairing.warning == (
        "No shared task_id between 'A' and 'B'. Using the unpaired comparison."
    )
    assert report.arm("A").tasks == 1
    assert report.arm("B").tasks == 1
    assert report.arm("A").total_cost == Decimal("1")
    text = render_markdown(report)
    assert "**Pairing:** unpaired (0 pairs)." in text
    assert report.pairing.warning in text
    payload = json.loads(render_json(report))
    assert payload["pairing"]["mode"] == "unpaired"
    assert payload["pairing"]["metrics"] is None
    assert payload["pairing"]["warning"] == report.pairing.warning
    assert report.verdict is Verdict.INCONCLUSIVE


def test_seed_fixes_the_interval_and_another_seed_moves_it() -> None:
    # Differences 1, 3, 4, 8, 10. With 200 resamples the percentile moves between seeds.
    events = paired_events(
        [
            (6_000_000, 5_000_000),
            (8_000_000, 5_000_000),
            (9_000_000, 5_000_000),
            (13_000_000, 5_000_000),
            (15_000_000, 5_000_000),
        ]
    )
    reversed_events = list(reversed(events))
    first = compare(events, ("A", "B"), prices=PRICES, seed=1, resamples=200)
    again = compare(reversed_events, ("A", "B"), prices=PRICES, seed=1, resamples=200)
    other = compare(events, ("A", "B"), prices=PRICES, seed=2, resamples=200)
    assert first.pairing.cost is not None
    assert again.pairing.cost is not None
    assert other.pairing.cost is not None
    assert first.pairing.cost.mean_difference == Decimal("5.2")
    assert first.pairing.cost.interval == again.pairing.cost.interval
    assert first.pairing.cost.relative_interval == again.pairing.cost.relative_interval
    assert first.pairing.cost.interval != other.pairing.cost.interval


def test_unpaired_flag_keeps_every_task_and_paired_flag_requires_a_pair() -> None:
    events = [
        ev(task_id="t1", variant="A", input_tokens=1_000_000),
        ev(task_id="t2", variant="A", input_tokens=2_000_000),
        ev(task_id="only-b", variant="B", input_tokens=9_000_000),
        ev(task_id="t2", variant="B", input_tokens=4_000_000),
    ]
    forced = compare(events, ("A", "B"), prices=PRICES, pairing="unpaired", resamples=10)
    assert forced.pairing.mode is PairingMode.UNPAIRED
    assert forced.pairing.requested == "unpaired"
    assert forced.pairing.warning is None
    assert forced.pairing.pairs == 0
    assert forced.pairing.shared == 1
    assert forced.arm("A").tasks == 2
    assert forced.arm("B").tasks == 2
    assert "not matched" in render_markdown(forced)

    disjoint = [
        ev(task_id="a1", variant="A", input_tokens=1_000_000),
        ev(task_id="b1", variant="B", input_tokens=1_000_000),
    ]
    with pytest.raises(CompareError, match="shared task_id"):
        compare(disjoint, ("A", "B"), prices=PRICES, pairing="paired")


def test_relative_change_is_undefined_when_the_baseline_mean_is_zero() -> None:
    events = paired_events([(1_000_000, 0)] * 5)
    report = compare(events, ("A", "B"), prices=PRICES, resamples=10)
    cost = report.pairing.cost
    assert cost is not None
    assert cost.mean_difference == Decimal("1")
    assert cost.relative_percent is None
    assert cost.relative_interval is None
    assert cost.relative_includes_zero is None
    payload = json.loads(render_json(report))
    metric = payload["pairing"]["metrics"]["cost"]
    assert metric["relative_change_percent"] is None
    assert metric["relative_interval"] is None
