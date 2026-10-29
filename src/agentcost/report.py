"""Per-task aggregation, bootstrap verdict, and Markdown/JSON rendering."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from agentcost.errors import CompareError, PriceError
from agentcost.models import (
    ArmReport,
    Event,
    EventStatus,
    Interval,
    MetricDifference,
    PairingMode,
    Quantiles,
    Report,
    Verdict,
)
from agentcost.pairing import RequestedPairing, TaskObservation, assess_pairing
from agentcost.pricing import PriceTable
from agentcost.stats import quantile

SCHEMA_VERSION = "0.1"
METRIC = "cost_per_solved_task"
MIN_TASKS = 5
DEFAULT_SEED = 42
DEFAULT_RESAMPLES = 1000
DEFAULT_LEVEL = 0.95
_TIE = Decimal("1e-9")
_JSON_QUANTUM = Decimal("0.000000000001")


def compare(
    events: Sequence[Event],
    variants: tuple[str, str] | Sequence[str],
    prices: PriceTable | None = None,
    *,
    seed: int = DEFAULT_SEED,
    resamples: int = DEFAULT_RESAMPLES,
    level: float = DEFAULT_LEVEL,
    on_missing: Literal["error", "zero"] = "error",
    pairing: RequestedPairing = "auto",
) -> Report:
    """Compare two variants on cost per solved task.

    A task succeeds when at least one of its runs succeeds. A run fails when
    any of its events has status ``error``. Failed runs are included in cost,
    tokens, and steps, and are also reported on their own.

    ``pairing="auto"`` matches variants on ``task_id`` when they share at
    least one. The paired verdict uses the bootstrap interval of the mean
    per-task cost difference (first minus second). ``pairing="unpaired"``
    keeps the per-arm intervals. With fewer than five tasks (or five pairs),
    the verdict is ``inconclusive``. Equal point estimates are
    ``no_difference``.

    The verdict is about the first variant relative to the second. Lower cost
    is better.
    """
    if len(variants) != 2:
        raise CompareError("compare expects exactly two variants")
    left, right = variants[0], variants[1]
    if left == right:
        raise CompareError("variants must be different")
    if not events:
        raise CompareError("no events to compare")
    if resamples < 1:
        raise CompareError("resamples must be >= 1")
    if not 0 < level < 1:
        raise CompareError("bootstrap level must be between 0 and 1")
    table = prices if prices is not None else PriceTable.bundled()
    selected = [event for event in events if event.variant in {left, right}]
    if on_missing == "error":
        _require_prices(selected, table)
    left_tasks = _tasks(selected, left, table, on_missing)
    right_tasks = _tasks(selected, right, table, on_missing)
    if not left_tasks:
        raise CompareError(f"variant {left!r} has no events in the trace")
    if not right_tasks:
        raise CompareError(f"variant {right!r} has no events in the trace")
    assessed = assess_pairing(
        [_observation(task) for task in left_tasks],
        [_observation(task) for task in right_tasks],
        first_name=left,
        second_name=right,
        requested=pairing,
        seed=seed,
        resamples=resamples,
        level=level,
    )
    if assessed.mode is PairingMode.PAIRED:
        shared_ids = {task.task_id for task in left_tasks} & {task.task_id for task in right_tasks}
        left_tasks = [task for task in left_tasks if task.task_id in shared_ids]
        right_tasks = [task for task in right_tasks if task.task_id in shared_ids]
    arms = (
        _arm_from_tasks(left, left_tasks),
        _arm_from_tasks(right, right_tasks),
    )
    raw_intervals = {
        left: _bootstrap(
            [task.cost for task in left_tasks],
            [task.success for task in left_tasks],
            seed=seed,
            resamples=resamples,
            level=level,
        ),
        right: _bootstrap(
            [task.cost for task in right_tasks],
            [task.success for task in right_tasks],
            seed=seed,
            resamples=resamples,
            level=level,
        ),
    }
    if assessed.mode is PairingMode.PAIRED:
        verdict, reason = _paired_verdict(arms[0], arms[1], assessed.cost, assessed.pairs, level)
    else:
        verdict, reason = _verdict(arms[0], arms[1], raw_intervals, level)
    intervals = {key: value for key, value in raw_intervals.items() if value is not None}
    return Report(
        schema_version=SCHEMA_VERSION,
        price_table_version=table.version,
        currency=table.currency,
        variants=(left, right),
        metric=METRIC,
        verdict=verdict,
        verdict_reason=reason,
        arms=arms,
        bootstrap_seed=seed,
        bootstrap_resamples=resamples,
        bootstrap_level=level,
        intervals=intervals,
        pairing=assessed,
    )


def render_json(report: Report) -> str:
    return json.dumps(_report_dict(report), indent=2) + "\n"


def render_markdown(report: Report) -> str:
    left, right = report.arms
    headers = (left.variant, right.variant)
    rows = [
        ("Tasks", str(left.tasks), str(right.tasks)),
        ("Successful tasks", str(left.successful_tasks), str(right.successful_tasks)),
        ("Success rate", _fmt_rate(left.success_rate), _fmt_rate(right.success_rate)),
        (
            "Cost per solved task",
            _fmt_money(left.cost_per_solved_task),
            _fmt_money(right.cost_per_solved_task),
        ),
        (
            "Cost per task, median (p25–p75)",
            _fmt_span(left.cost, money=True),
            _fmt_span(right.cost, money=True),
        ),
        ("Tokens per task, median (p25–p75)", _fmt_span(left.tokens), _fmt_span(right.tokens)),
        ("Steps per task, median (p25–p75)", _fmt_span(left.steps), _fmt_span(right.steps)),
        ("Runs", str(left.runs), str(right.runs)),
        ("Failed runs", str(left.failed_runs), str(right.failed_runs)),
        ("Failed-run cost", _fmt_money(left.failed_run_cost), _fmt_money(right.failed_run_cost)),
        ("Failed-run tokens", str(left.failed_run_tokens), str(right.failed_run_tokens)),
    ]
    unpriced = sorted(set(left.unpriced_models) | set(right.unpriced_models))
    lines = [
        "# agentcost report",
        "",
        f"**Verdict:** {report.verdict.value}",
        "",
        report.verdict_reason,
        "",
    ]
    lines.extend(_pairing_lines(report))
    lines.extend(
        [
            "",
            "Lower cost per solved task is better. The denominator is solved tasks. "
            "Failed runs stay in the numerator and in the per-task distributions, and "
            "are also listed on their own rows.",
            "",
            f"| Metric | {headers[0]} | {headers[1]} |",
            "| --- | ---: | ---: |",
        ]
    )
    lines.extend(f"| {name} | {a} | {b} |" for name, a, b in rows)
    lines.extend(
        [
            "",
            f"Price table `{report.price_table_version}` "
            f"({report.currency} per 1,000,000 tokens). "
            f"Bootstrap {report.bootstrap_level:.0%} intervals, "
            f"{report.bootstrap_resamples} resamples, seed {report.bootstrap_seed}.",
        ]
    )
    if unpriced:
        lines.append(
            "Unpriced models treated as zero cost: "
            + ", ".join(f"`{name}`" for name in unpriced)
            + "."
        )
    lines.append("")
    return "\n".join(lines)


@dataclass
class _Run:
    task_id: str
    variant: str
    run_id: str
    cost: Decimal = Decimal(0)
    tokens: int = 0
    steps: int = 0
    ok: bool = True
    unpriced: set[str] = field(default_factory=set)


def _require_prices(events: Sequence[Event], prices: PriceTable) -> None:
    missing: set[str] = set()
    for event in events:
        if event.input_tokens + event.output_tokens <= 0:
            continue
        if not event.model:
            missing.add("<no model>")
            continue
        if prices.lookup(event.model) is None:
            missing.add(event.model)
    if missing:
        names = ", ".join(sorted(missing))
        raise PriceError(
            f"No price for model(s): {names}. "
            "Add them to a price file or override, or set on_missing='zero'."
        )


def _observation(task: _Task) -> TaskObservation:
    return TaskObservation(
        task_id=task.task_id,
        cost=task.cost,
        tokens=task.tokens,
        steps=task.steps,
    )


def _arm_from_tasks(variant: str, tasks: Sequence[_Task]) -> ArmReport:
    if not tasks:
        raise CompareError(f"variant {variant!r} has no events in the trace")
    successful = [task for task in tasks if task.success]
    total_cost = sum((task.cost for task in tasks), start=Decimal(0))
    failed_cost = sum((task.failed_cost for task in tasks), start=Decimal(0))
    failed_tokens = sum(task.failed_tokens for task in tasks)
    solved = len(successful)
    cost_per = (total_cost / Decimal(solved)) if solved else None
    unpriced = tuple(sorted({model for task in tasks for model in task.unpriced}))
    return ArmReport(
        variant=variant,
        tasks=len(tasks),
        successful_tasks=solved,
        runs=sum(task.runs for task in tasks),
        successful_runs=sum(task.successful_runs for task in tasks),
        failed_runs=sum(task.failed_runs for task in tasks),
        success_rate=Decimal(solved) / Decimal(len(tasks)),
        total_cost=total_cost,
        failed_run_cost=failed_cost,
        failed_run_tokens=failed_tokens,
        cost_per_solved_task=cost_per,
        cost=_quantiles([task.cost for task in tasks]),
        tokens=_quantiles([Decimal(task.tokens) for task in tasks]),
        steps=_quantiles([Decimal(task.steps) for task in tasks]),
        unpriced_models=unpriced,
    )


@dataclass(frozen=True, slots=True)
class _Task:
    task_id: str
    cost: Decimal
    tokens: int
    steps: int
    success: bool
    runs: int
    successful_runs: int
    failed_runs: int
    failed_cost: Decimal
    failed_tokens: int
    unpriced: frozenset[str]


def _tasks(
    events: Sequence[Event],
    variant: str,
    prices: PriceTable,
    on_missing: Literal["error", "zero"],
) -> list[_Task]:
    runs: dict[tuple[str, str], _Run] = {}
    for event in events:
        if event.variant != variant:
            continue
        key = (event.task_id, event.run_id)
        run = runs.get(key)
        if run is None:
            run = _Run(task_id=event.task_id, variant=variant, run_id=event.run_id)
            runs[key] = run
        cost, unpriced = _price_event(event, prices, on_missing)
        run.cost += cost
        run.tokens += event.input_tokens + event.output_tokens
        run.steps += 1
        if event.status is EventStatus.ERROR:
            run.ok = False
        if unpriced:
            run.unpriced.add(unpriced)
    by_task: dict[str, list[_Run]] = {}
    for run in runs.values():
        by_task.setdefault(run.task_id, []).append(run)
    tasks: list[_Task] = []
    for task_id in sorted(by_task):
        grouped = by_task[task_id]
        failed = [run for run in grouped if not run.ok]
        tasks.append(
            _Task(
                task_id=task_id,
                cost=sum((run.cost for run in grouped), start=Decimal(0)),
                tokens=sum(run.tokens for run in grouped),
                steps=sum(run.steps for run in grouped),
                success=any(run.ok for run in grouped),
                runs=len(grouped),
                successful_runs=sum(1 for run in grouped if run.ok),
                failed_runs=len(failed),
                failed_cost=sum((run.cost for run in failed), start=Decimal(0)),
                failed_tokens=sum(run.tokens for run in failed),
                unpriced=frozenset(model for run in grouped for model in run.unpriced),
            )
        )
    return tasks


def _price_event(
    event: Event,
    prices: PriceTable,
    on_missing: Literal["error", "zero"],
) -> tuple[Decimal, str | None]:
    if event.input_tokens + event.output_tokens <= 0:
        return Decimal(0), None
    price = prices.lookup(event.model) if event.model else None
    if price is None:
        if on_missing == "zero":
            return Decimal(0), event.model or "<no model>"
        name = event.model or "<no model>"
        raise PriceError(f"No price for model(s): {name}.")
    cost = (
        Decimal(event.input_tokens) * price.input_per_million
        + Decimal(event.output_tokens) * price.output_per_million
    ) / Decimal(1_000_000)
    return cost, None


def _bootstrap(
    costs: Sequence[Decimal],
    solved: Sequence[bool],
    *,
    seed: int,
    resamples: int,
    level: float,
) -> Interval | None:
    rng = random.Random(seed)
    count = len(costs)
    samples: list[Decimal] = []
    for _ in range(resamples):
        total = Decimal(0)
        successes = 0
        for _ in range(count):
            index = rng.randrange(count)
            total += costs[index]
            if solved[index]:
                successes += 1
        if successes:
            samples.append(total / Decimal(successes))
    if len(samples) < max(100, resamples // 2):
        return None
    alpha = (1 - level) / 2
    return Interval(low=quantile(samples, alpha), high=quantile(samples, 1 - alpha))


def _quantiles(values: Sequence[Decimal]) -> Quantiles:
    return Quantiles(
        p25=quantile(values, 0.25),
        median=quantile(values, 0.5),
        p75=quantile(values, 0.75),
    )


def _paired_verdict(
    left: ArmReport,
    right: ArmReport,
    cost: MetricDifference | None,
    pairs: int,
    level: float,
) -> tuple[Verdict, str]:
    if cost is None:
        raise CompareError("paired comparison has no cost difference")
    if pairs < MIN_TASKS:
        return (
            Verdict.INCONCLUSIVE,
            f"Fewer than 5 paired tasks ({pairs}).",
        )
    if _same(cost.mean_difference, Decimal(0)):
        return (
            Verdict.NO_DIFFERENCE,
            f"Mean paired cost difference ({left.variant} - {right.variant}) is 0.",
        )
    percent = f"{level:.0%}"
    span = f"[{_fmt_num(cost.interval.low)}, {_fmt_num(cost.interval.high)}]"
    if cost.includes_zero:
        return (
            Verdict.INCONCLUSIVE,
            f"Bootstrap {percent} interval of the mean cost difference "
            f"({left.variant} - {right.variant}) includes 0 ({span}).",
        )
    if cost.interval.high < 0:
        return (
            Verdict.BETTER,
            f"{left.variant} costs less per paired task than {right.variant}; "
            f"the bootstrap {percent} interval of the mean difference does not include 0.",
        )
    return (
        Verdict.WORSE,
        f"{left.variant} costs more per paired task than {right.variant}; "
        f"the bootstrap {percent} interval of the mean difference does not include 0.",
    )


def _verdict(
    left: ArmReport,
    right: ArmReport,
    intervals: Mapping[str, Interval | None],
    level: float,
) -> tuple[Verdict, str]:
    if left.tasks < MIN_TASKS or right.tasks < MIN_TASKS:
        return (
            Verdict.INCONCLUSIVE,
            f"Fewer than 5 tasks in at least one variant "
            f"({left.variant}={left.tasks}, {right.variant}={right.tasks}).",
        )
    if left.cost_per_solved_task is None or right.cost_per_solved_task is None:
        missing = [arm.variant for arm in (left, right) if arm.cost_per_solved_task is None]
        if len(missing) == 1:
            detail = f"{missing[0]} has no solved tasks"
        else:
            detail = f"{missing[0]} and {missing[1]} have no solved tasks"
        return (
            Verdict.INCONCLUSIVE,
            f"{detail}, so cost per solved task is undefined.",
        )
    if _same(left.cost_per_solved_task, right.cost_per_solved_task):
        return Verdict.NO_DIFFERENCE, "Cost per solved task is the same for both variants."
    left_interval = intervals.get(left.variant)
    right_interval = intervals.get(right.variant)
    percent = f"{level:.0%}"
    if left_interval is None or right_interval is None:
        return (
            Verdict.INCONCLUSIVE,
            "Bootstrap could not estimate a stable interval because too many "
            "resamples contained no solved task.",
        )
    if left_interval.low <= right_interval.high and right_interval.low <= left_interval.high:
        return (
            Verdict.INCONCLUSIVE,
            f"Bootstrap {percent} intervals overlap "
            f"({left.variant} [{_fmt_num(left_interval.low)}, {_fmt_num(left_interval.high)}], "
            f"{right.variant} [{_fmt_num(right_interval.low)}, {_fmt_num(right_interval.high)}]).",
        )
    if left_interval.high < right_interval.low:
        return (
            Verdict.BETTER,
            f"{left.variant} is cheaper per solved task than {right.variant}; "
            f"bootstrap {percent} intervals do not overlap.",
        )
    return (
        Verdict.WORSE,
        f"{left.variant} is more expensive per solved task than {right.variant}; "
        f"bootstrap {percent} intervals do not overlap.",
    )


def _same(left: Decimal, right: Decimal) -> bool:
    scale = max(abs(left), abs(right), Decimal(1))
    return abs(left - right) <= scale * _TIE


def _report_dict(report: Report) -> dict[str, object]:
    return {
        "schema_version": report.schema_version,
        "price_table_version": report.price_table_version,
        "currency": report.currency,
        "compare": list(report.variants),
        "metric": report.metric,
        "verdict": report.verdict.value,
        "verdict_reason": report.verdict_reason,
        "bootstrap": {
            "seed": report.bootstrap_seed,
            "resamples": report.bootstrap_resamples,
            "level": report.bootstrap_level,
        },
        "arms": {arm.variant: _arm_dict(arm) for arm in report.arms},
        "intervals": {
            name: {"low": _json_number(interval.low), "high": _json_number(interval.high)}
            for name, interval in report.intervals.items()
        },
        "pairing": _pairing_dict(report),
    }


def _pairing_dict(report: Report) -> dict[str, object]:
    pairing = report.pairing
    first, second = report.variants
    metrics: dict[str, object] | None = None
    if pairing.mode is PairingMode.PAIRED:
        metrics = {}
        for name, metric in (
            ("cost", pairing.cost),
            ("tokens", pairing.tokens),
            ("steps", pairing.steps),
        ):
            if metric is not None:
                metrics[name] = _metric_dict(metric)
    return {
        "mode": pairing.mode.value,
        "requested": pairing.requested,
        "pairs": pairing.pairs,
        "shared": pairing.shared,
        "unmatched": {first: pairing.unmatched_first, second: pairing.unmatched_second},
        "warning": pairing.warning,
        "metrics": metrics,
    }


def _metric_dict(metric: MetricDifference) -> dict[str, object]:
    relative_interval = None
    if metric.relative_interval is not None:
        relative_interval = {
            "low": _json_number(metric.relative_interval.low),
            "high": _json_number(metric.relative_interval.high),
        }
    return {
        "mean_difference": _json_number(metric.mean_difference),
        "interval": {
            "low": _json_number(metric.interval.low),
            "high": _json_number(metric.interval.high),
        },
        "includes_zero": metric.includes_zero,
        "relative_change_percent": None
        if metric.relative_percent is None
        else _json_number(metric.relative_percent),
        "relative_interval": relative_interval,
        "relative_includes_zero": metric.relative_includes_zero,
    }


def _pairing_lines(report: Report) -> list[str]:
    pairing = report.pairing
    first, second = report.variants
    if pairing.mode is PairingMode.UNPAIRED:
        if pairing.requested == "unpaired" and pairing.shared:
            noun = "task id" if pairing.shared == 1 else "task ids"
            headline = (
                f"**Pairing:** unpaired (0 pairs; {pairing.shared} shared {noun} not matched)."
            )
        else:
            headline = "**Pairing:** unpaired (0 pairs)."
        lines = [headline]
        if pairing.warning:
            lines.extend(["", pairing.warning])
        return lines
    headline = f"**Pairing:** paired ({pairing.pairs} pairs)."
    if pairing.unmatched_first or pairing.unmatched_second:
        headline += (
            f" Left out: {first} {pairing.unmatched_first}, {second} {pairing.unmatched_second}."
        )
    percent = f"{report.bootstrap_level:.0%}"
    difference = f"Mean difference ({first} - {second})"
    lines = [
        headline,
        "",
        "Each difference is the first variant minus the second on that task "
        "(failed runs stay in the task total). Negative cost means the first variant is cheaper.",
        "",
        f"| Metric | {difference} | {percent} CI | Includes 0 | Relative change |",
        "| --- | ---: | ---: | :---: | ---: |",
    ]
    for name, metric, money in (
        ("Cost", pairing.cost, True),
        ("Tokens", pairing.tokens, False),
        ("Steps", pairing.steps, False),
    ):
        if metric is None:
            continue
        included = "yes" if metric.includes_zero else "no"
        cells = (
            name,
            _fmt_diff(metric.mean_difference, money=money),
            _fmt_interval(metric.interval, money=money),
            included,
            _fmt_relative(metric),
        )
        lines.append("| " + " | ".join(cells) + " |")
    if pairing.cost is not None:
        if pairing.cost.includes_zero:
            lines.extend(["", "The cost interval includes 0."])
        else:
            lines.extend(["", "The cost interval does not include 0."])
    return lines


def _arm_dict(arm: ArmReport) -> dict[str, object]:
    return {
        "tasks": arm.tasks,
        "successful_tasks": arm.successful_tasks,
        "runs": arm.runs,
        "successful_runs": arm.successful_runs,
        "failed_runs": arm.failed_runs,
        "success_rate": _json_number(arm.success_rate),
        "total_cost": _json_number(arm.total_cost),
        "failed_run_cost": _json_number(arm.failed_run_cost),
        "failed_run_tokens": arm.failed_run_tokens,
        "cost_per_solved_task": None
        if arm.cost_per_solved_task is None
        else _json_number(arm.cost_per_solved_task),
        "unpriced_models": list(arm.unpriced_models),
        "per_task": {
            "cost": _quantile_dict(arm.cost),
            "tokens": _quantile_dict(arm.tokens),
            "steps": _quantile_dict(arm.steps),
        },
    }


def _quantile_dict(quantiles: Quantiles) -> dict[str, int | float]:
    return {
        "p25": _json_number(quantiles.p25),
        "median": _json_number(quantiles.median),
        "p75": _json_number(quantiles.p75),
    }


def _json_number(value: Decimal) -> int | float:
    quantized = value.quantize(_JSON_QUANTUM, rounding=ROUND_HALF_UP)
    integral = quantized.to_integral_value(rounding=ROUND_HALF_UP)
    if quantized == integral:
        return int(integral)
    return float(quantized)


def _fmt_num(value: Decimal) -> str:
    quantized = value.quantize(_JSON_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(int(quantized))
    return format(quantized.normalize(), "f")


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return f"${_fmt_num(value)}"


def _fmt_diff(value: Decimal, *, money: bool) -> str:
    if not money:
        return _fmt_num(value)
    if value < 0:
        return f"-${_fmt_num(-value)}"
    return f"${_fmt_num(value)}"


def _fmt_interval(interval: Interval, *, money: bool) -> str:
    return f"[{_fmt_diff(interval.low, money=money)}, {_fmt_diff(interval.high, money=money)}]"


def _fmt_relative(metric: MetricDifference) -> str:
    if metric.relative_percent is None or metric.relative_interval is None:
        return "n/a"
    low = _fmt_num(metric.relative_interval.low)
    high = _fmt_num(metric.relative_interval.high)
    return f"{_fmt_num(metric.relative_percent)}% [{low}%, {high}%]"


def _fmt_span(quantiles: Quantiles, *, money: bool = False) -> str:
    fmt = _fmt_money if money else _fmt_num
    return f"{fmt(quantiles.median)} ({fmt(quantiles.p25)}–{fmt(quantiles.p75)})"


def _fmt_rate(value: Decimal) -> str:
    percent = (value * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = format(percent, "f")
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"
