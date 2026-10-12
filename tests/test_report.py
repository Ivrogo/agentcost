"""Aggregation, failed runs, and A/B verdict."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentcost import (
    Event,
    EventKind,
    EventStatus,
    ModelPrice,
    PriceError,
    PriceTable,
    Verdict,
    compare,
    render_json,
    render_markdown,
)

PRICES = PriceTable(
    version="test",
    currency="USD",
    models={
        "m": ModelPrice(Decimal("1"), Decimal("1")),
        "other": ModelPrice(Decimal("1"), Decimal("1")),
    },
)


def ev(
    *,
    task_id: str,
    variant: str,
    run_id: str = "r",
    input_tokens: int = 0,
    output_tokens: int = 0,
    status: EventStatus = EventStatus.OK,
    kind: EventKind = EventKind.LLM,
    model: str | None = "m",
) -> Event:
    return Event(
        task_id=task_id,
        variant=variant,
        run_id=run_id,
        kind=kind,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        status=status,
    )


def arm(
    variant: str, costs_million_tokens: list[int], *, failed: set[str] | None = None
) -> list[Event]:
    """One successful single-event run per task. Cost in USD equals tokens / 1e6."""
    failed = failed or set()
    events: list[Event] = []
    for index, tokens in enumerate(costs_million_tokens, start=1):
        task_id = f"{variant}{index}"
        events.append(
            ev(
                task_id=task_id,
                variant=variant,
                run_id="r1",
                input_tokens=tokens,
                status=EventStatus.ERROR if task_id in failed else EventStatus.OK,
            )
        )
    return events


def test_percentiles_and_cost_use_the_price_table() -> None:
    events = [
        ev(task_id="t1", variant="A", input_tokens=1_000_000, output_tokens=0),
        ev(task_id="t2", variant="A", input_tokens=2_000_000),
        ev(task_id="t3", variant="A", input_tokens=3_000_000),
        ev(task_id="t4", variant="A", input_tokens=4_000_000),
        ev(task_id="t5", variant="A", input_tokens=5_000_000),
        *arm("B", [1_000_000] * 5),
    ]
    report = compare(events, ("A", "B"), prices=PRICES, resamples=200)
    arm_a = report.arm("A")
    assert arm_a.cost.p25 == Decimal("2")
    assert arm_a.cost.median == Decimal("3")
    assert arm_a.cost.p75 == Decimal("4")
    assert arm_a.tokens.median == Decimal("3000000")
    assert arm_a.steps.median == Decimal("1")
    assert arm_a.cost_per_solved_task == Decimal("3")
    assert arm_a.success_rate == Decimal("1")


def test_failed_runs_count_toward_cost_and_are_reported_separately() -> None:
    events = [
        ev(
            task_id="t1",
            variant="A",
            run_id="attempt-1",
            input_tokens=1_000_000,
            status=EventStatus.ERROR,
        ),
        ev(task_id="t1", variant="A", run_id="attempt-2", input_tokens=2_000_000),
        ev(
            task_id="t1",
            variant="A",
            run_id="attempt-2",
            kind=EventKind.TOOL,
            model=None,
            status=EventStatus.OK,
        ),
        ev(task_id="t2", variant="A", input_tokens=1_000_000),
        ev(task_id="t3", variant="A", input_tokens=1_000_000),
        ev(task_id="t4", variant="A", input_tokens=1_000_000),
        ev(
            task_id="t5",
            variant="A",
            run_id="only",
            input_tokens=4_000_000,
            status=EventStatus.ERROR,
        ),
        *arm("B", [1_000_000] * 5),
    ]
    report = compare(events, ("A", "B"), prices=PRICES, resamples=50)
    arm_a = report.arm("A")
    # t1 succeeds on the second attempt; t5 never succeeds.
    assert arm_a.tasks == 5
    assert arm_a.successful_tasks == 4
    assert arm_a.failed_runs == 2
    assert arm_a.successful_runs == 4
    assert arm_a.failed_run_cost == Decimal("5")
    # All run cost, including failures, divided by solved tasks: (1+2+1+1+1+4) / 4.
    assert arm_a.total_cost == Decimal("10")
    assert arm_a.cost_per_solved_task == Decimal("2.5")
    # t1 has two runs and an extra tool step: 3 steps. Others have 1.
    assert arm_a.steps.median == Decimal("1")
    text = render_markdown(report)
    assert "Failed runs" in text
    assert "2" in text


def test_unknown_model_is_an_error_unless_explicitly_zeroed() -> None:
    events = [
        *arm("A", [1_000_000] * 5),
        ev(task_id="b1", variant="B", model="missing", input_tokens=100),
        *arm("B", [1_000_000] * 4),
    ]
    with pytest.raises(PriceError, match="missing"):
        compare(events, ("A", "B"), prices=PRICES)
    report = compare(events, ("A", "B"), prices=PRICES, on_missing="zero", resamples=20)
    assert report.arm("B").unpriced_models == ("missing",)
    assert report.arm("B").total_cost == Decimal("4")


def test_verdict_better_when_intervals_are_disjoint() -> None:
    events = arm("A", [1_000_000] * 6) + arm("B", [10_000_000] * 6)
    report = compare(events, ("A", "B"), prices=PRICES)
    assert report.verdict is Verdict.BETTER
    assert report.intervals["A"].low == report.intervals["A"].high == Decimal("1")
    assert report.intervals["B"].low == Decimal("10")
    payload = render_json(report)
    assert '"verdict": "better"' in payload


def test_verdict_worse_is_from_the_first_variant() -> None:
    events = arm("A", [10_000_000] * 6) + arm("B", [1_000_000] * 6)
    report = compare(events, ("A", "B"), prices=PRICES)
    assert report.verdict is Verdict.WORSE


def test_verdict_inconclusive_when_sample_is_below_five() -> None:
    events = arm("A", [1_000_000] * 4) + arm("B", [10_000_000] * 4)
    report = compare(events, ("A", "B"), prices=PRICES)
    assert report.verdict is Verdict.INCONCLUSIVE
    assert "5" in report.verdict_reason


def test_verdict_inconclusive_when_bootstrap_intervals_overlap() -> None:
    events = arm("A", [1_000_000, 1_000_000, 1_000_000, 1_000_000, 50_000_000]) + arm(
        "B", [2_000_000, 2_000_000, 2_000_000, 2_000_000, 40_000_000]
    )
    report = compare(events, ("A", "B"), prices=PRICES, seed=42, resamples=1000)
    assert report.verdict is Verdict.INCONCLUSIVE
    assert "overlap" in report.verdict_reason
    again = compare(events, ("A", "B"), prices=PRICES, seed=42, resamples=1000)
    assert again.intervals["A"] == report.intervals["A"]
    assert again.intervals["B"] == report.intervals["B"]


def test_verdict_no_difference_when_point_estimates_match() -> None:
    events = arm("A", [3_000_000] * 6) + arm("B", [3_000_000] * 6)
    report = compare(events, ("A", "B"), prices=PRICES)
    assert report.verdict is Verdict.NO_DIFFERENCE


def test_tool_only_events_add_steps_and_no_cost() -> None:
    events = []
    for index in range(5):
        events.append(
            ev(
                task_id=f"t{index}",
                variant="A",
                kind=EventKind.TOOL,
                model=None,
            )
        )
        events.append(ev(task_id=f"t{index}", variant="A", input_tokens=1_000_000))
    events.extend(arm("B", [1_000_000] * 5))
    report = compare(events, ("A", "B"), prices=PRICES, resamples=20)
    assert report.arm("A").steps.median == Decimal("2")
    assert report.arm("A").total_cost == Decimal("5")
