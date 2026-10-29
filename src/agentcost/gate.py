"""CI gate for ``agentcost report``.

Exit 0 when the report is fine. An inconclusive verdict also exits 0, with a
warning, unless the caller asked for ``--fail-if-inconclusive``. Exit 3 when
the first variant is a regression. Exit 4 when that flag is set and the verdict
is inconclusive. Exit 1 stays the caller's input error. Typer still uses 2 for
a bad command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from agentcost.errors import CompareError
from agentcost.models import MetricDifference, PairingMode, Report, Verdict
from agentcost.report import (
    MIN_TASKS,
    _fmt_cache_write,
    _fmt_diff,
    _fmt_interval,
    _fmt_money,
    _fmt_num,
    _same,
)

EXIT_OK = 0
EXIT_REGRESSION = 3
EXIT_INCONCLUSIVE = 4
_METRICS = ("cost", "tokens", "steps")


@dataclass(frozen=True, slots=True)
class GateDecision:
    """What the CLI should do after the report exists."""

    outcome: str
    exit_code: int
    reason: str
    metric: str
    fail_if_worse: bool
    threshold: Decimal | None
    compared: Decimal | None
    threshold_applied: bool


def parse_max_regression(raw: str) -> Decimal:
    """Parse ``5`` or ``5%`` into a percent. Negative values are rejected."""
    text = "".join(raw.split())
    if text.endswith("%"):
        text = text[:-1]
    if not text:
        raise CompareError(f"--max-regression {raw!r} is not a percent")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise CompareError(f"--max-regression {raw!r} is not a percent") from exc
    if not value.is_finite() or value < 0:
        raise CompareError(f"--max-regression must be zero or positive, got {raw!r}")
    return value


def evaluate_gate(
    report: Report,
    *,
    fail_if_worse: bool,
    max_regression: Decimal | None,
    metric: str = "cost",
    fail_if_inconclusive: bool = False,
) -> GateDecision:
    """Decide whether the first variant fails the gate.

    Cost uses ``report.verdict``. That is ``worse`` for a paired report only
    when there are at least five pairs and the 95% interval of the mean
    difference sits entirely above 0. Tokens and steps use that same paired
    rule on ``report.pairing``. ``max_regression`` compares the lower bound of
    the paired relative interval and does not use the five-pair floor.

    An ``inconclusive`` cost verdict is not an input error. With
    ``fail_if_worse`` it exits 0 and names the reason, or 4 when
    ``fail_if_inconclusive`` is set. A threshold that does find a regression
    still exits 3. A threshold that cannot be applied stays an input error
    when the verdict is not inconclusive.
    """
    if metric not in _METRICS:
        raise CompareError("--metric must be cost, tokens, or steps")
    if not fail_if_worse and max_regression is None:
        return GateDecision(
            outcome="not requested",
            exit_code=EXIT_OK,
            reason="No regression gate was requested.",
            metric=metric,
            fail_if_worse=False,
            threshold=None,
            compared=None,
            threshold_applied=False,
        )
    parts: list[str] = []
    outcome = "pass"
    compared: Decimal | None = None
    applied = False
    blocked: str | None = None
    threshold_sentence: str | None = None
    if fail_if_worse:
        worse, error, sentence = _worse_check(report, metric)
        if error is not None:
            return _error(report, metric, fail_if_worse, max_regression, error)
        parts.append(sentence)
        if worse:
            outcome = "regression"
    if max_regression is not None:
        status, bound, bound_applied, sentence = _threshold_check(report, metric, max_regression)
        if status == "error":
            # A check that cannot be applied still fails the command when the
            # other check already found a regression. An inconclusive verdict
            # only replaces that input error when nothing else failed.
            if outcome != "regression" and fail_if_worse and report.verdict is Verdict.INCONCLUSIVE:
                blocked = sentence
            else:
                return _error(report, metric, fail_if_worse, max_regression, sentence)
        else:
            compared = bound
            applied = bound_applied
            threshold_sentence = sentence
            parts.append(sentence)
            if status == "regression":
                outcome = "regression"
    if outcome != "regression" and fail_if_worse and report.verdict is Verdict.INCONCLUSIVE:
        detail = report.verdict_reason
        if blocked is not None:
            detail = f"{detail} {blocked}"
        elif threshold_sentence is not None:
            detail = f"{detail} {threshold_sentence}"
        return GateDecision(
            outcome="inconclusive",
            exit_code=EXIT_INCONCLUSIVE if fail_if_inconclusive else EXIT_OK,
            reason=f"Inconclusive: {detail}",
            metric=metric,
            fail_if_worse=fail_if_worse,
            threshold=max_regression,
            compared=compared,
            threshold_applied=applied,
        )
    exit_code = EXIT_REGRESSION if outcome == "regression" else EXIT_OK
    return GateDecision(
        outcome=outcome,
        exit_code=exit_code,
        reason=" ".join(parts),
        metric=metric,
        fail_if_worse=fail_if_worse,
        threshold=max_regression,
        compared=compared,
        threshold_applied=applied,
    )


def render_ci_summary(report: Report, decision: GateDecision) -> str:
    """Markdown comment for a pull request. The text is deterministic."""
    first, second = report.variants
    difference = _metric_difference(report, decision.metric)
    money = decision.metric == "cost"
    if report.pairing.mode is PairingMode.PAIRED:
        noun = "pair" if report.pairing.pairs == 1 else "pairs"
        mode = f"paired ({report.pairing.pairs} {noun})"
    else:
        mode = "unpaired (0 pairs)"
    if difference is None:
        diff_text = "n/a"
        interval = "n/a"
        includes = "n/a"
        relative = "n/a"
        relative_interval = "n/a"
    else:
        diff_text = _fmt_diff(difference.mean_difference, money=money)
        interval = _fmt_interval(difference.interval, money=money)
        includes = "yes" if difference.includes_zero else "no"
        relative = _relative(difference)
        relative_interval = _relative_interval(difference)
    percent = f"{report.bootstrap_level:.0%}"
    if decision.threshold is None:
        threshold = "none"
    elif decision.threshold_applied:
        threshold = (
            f"{_fmt_num(decision.threshold)}% on the lower bound of the relative {percent} CI"
        )
    else:
        threshold = f"{_fmt_num(decision.threshold)}%"
    compared = "n/a" if decision.compared is None else f"{_fmt_num(decision.compared)}%"
    lines = [
        "<!-- agentcost-ci -->",
        "# agentcost",
        "",
        f"**Verdict:** {report.verdict.value}",
        f"**Gate:** {decision.outcome}",
        f"**Mode:** {mode}",
        f"**Metric:** {decision.metric}",
        f"**Difference ({first} - {second}):** {diff_text}",
        f"**{percent} CI:** {interval}",
        f"**Includes 0:** {includes}",
        f"**Relative change:** {relative}",
        f"**Relative {percent} CI:** {relative_interval}",
        f"**Threshold:** {threshold}",
        f"**Compared value:** {compared}",
        f"**Fail if worse:** {'yes' if decision.fail_if_worse else 'no'}",
        "",
        report.verdict_reason,
        "",
        decision.reason,
        "",
    ]
    if report.pairing.warning:
        lines.extend([report.pairing.warning, ""])
    left, right = report.arms
    rows = [
        ("Tasks", str(left.tasks), str(right.tasks)),
        ("Successful tasks", str(left.successful_tasks), str(right.successful_tasks)),
        (
            "Cost per solved task",
            _fmt_money(left.cost_per_solved_task),
            _fmt_money(right.cost_per_solved_task),
        ),
        ("Total cost", _fmt_money(left.total_cost), _fmt_money(right.total_cost)),
    ]
    if _has_cache(report):
        rows.extend(
            [
                ("Input cost", _fmt_money(left.input_cost), _fmt_money(right.input_cost)),
                ("Output cost", _fmt_money(left.output_cost), _fmt_money(right.output_cost)),
                (
                    "Cache read cost",
                    _fmt_money(left.cache_read_cost),
                    _fmt_money(right.cache_read_cost),
                ),
                ("Cache write cost", _fmt_cache_write(left), _fmt_cache_write(right)),
                (
                    "Cache savings vs input price",
                    _fmt_money(left.cache_savings),
                    _fmt_money(right.cache_savings),
                ),
            ]
        )
    lines.extend(
        [
            f"| Metric | {first} | {second} |",
            "| --- | ---: | ---: |",
        ]
    )
    lines.extend(f"| {name} | {a} | {b} |" for name, a, b in rows)
    fallback = sorted(set(left.cache_priced_as_input) | set(right.cache_priced_as_input))
    if fallback:
        parts = []
        for item in fallback:
            model, component = item.rsplit(" ", 1)
            parts.append(f"`{model}` {component}")
        lines.extend(
            [
                "",
                "Cache tokens priced at the input rate (the table has no cache price): "
                + ", ".join(parts)
                + ".",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_ci_summary(text: str, path: Path | None, *, github: bool) -> None:
    """Write the summary to ``path`` and, when asked, to ``$GITHUB_STEP_SUMMARY``."""
    try:
        written: Path | None = None
        if path is not None:
            path.write_text(text, encoding="utf-8", newline="\n")
            written = path.resolve()
        if not github:
            return
        dest = os.environ.get("GITHUB_STEP_SUMMARY")
        if not dest:
            return
        target = Path(dest)
        if written is not None and target.resolve() == written:
            return
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        raise CompareError(f"cannot write the CI summary: {exc}") from exc


def _error(
    report: Report,
    metric: str,
    fail_if_worse: bool,
    threshold: Decimal | None,
    reason: str,
) -> GateDecision:
    return GateDecision(
        outcome="error",
        exit_code=1,
        reason=reason,
        metric=metric,
        fail_if_worse=fail_if_worse,
        threshold=threshold,
        compared=None,
        threshold_applied=False,
    )


def _metric_difference(report: Report, metric: str) -> MetricDifference | None:
    pairing = report.pairing
    if metric == "cost":
        return pairing.cost
    if metric == "tokens":
        return pairing.tokens
    return pairing.steps


def _worse_check(report: Report, metric: str) -> tuple[bool, str | None, str]:
    first, second = report.variants
    percent = f"{report.bootstrap_level:.0%}"
    if metric == "cost":
        worse = report.verdict is Verdict.WORSE
        if worse and report.pairing.mode is PairingMode.PAIRED:
            sentence = (
                f"{first} is worse than {second} on cost: "
                f"the {percent} CI of the mean difference is entirely above 0."
            )
        elif worse:
            sentence = f"{first} is worse than {second} on cost under the unpaired verdict."
        else:
            sentence = f"{first} is not worse than {second} on cost."
        return worse, None, sentence
    if report.pairing.mode is not PairingMode.PAIRED:
        return (
            False,
            f"--metric {metric} needs a paired comparison. The unpaired verdict only covers cost.",
            "",
        )
    difference = _metric_difference(report, metric)
    if difference is None:
        return False, f"Paired comparison has no {metric} difference.", ""
    worse = _paired_is_worse(difference, report.pairing.pairs)
    if worse:
        sentence = (
            f"{first} is worse than {second} on {metric}: "
            f"the {percent} CI of the mean difference is entirely above 0."
        )
    else:
        sentence = f"{first} is not worse than {second} on {metric}."
    return worse, None, sentence


def _paired_is_worse(difference: MetricDifference, pairs: int) -> bool:
    if pairs < MIN_TASKS:
        return False
    if _same(difference.mean_difference, Decimal(0)):
        return False
    if difference.includes_zero:
        return False
    return difference.interval.low > 0


def _threshold_check(
    report: Report,
    metric: str,
    threshold: Decimal,
) -> tuple[str, Decimal | None, bool, str]:
    percent = f"{report.bootstrap_level:.0%}"
    if report.pairing.mode is not PairingMode.PAIRED:
        return (
            "error",
            None,
            False,
            "--max-regression needs a paired comparison. "
            "This report is unpaired, so there is no relative CI.",
        )
    difference = _metric_difference(report, metric)
    if difference is None or difference.relative_interval is None:
        return (
            "error",
            None,
            False,
            "--max-regression cannot compare a relative change because "
            f"the relative interval for {metric} is undefined.",
        )
    low = difference.relative_interval.low
    shown = _fmt_num(low)
    limit = _fmt_num(threshold)
    if low > threshold:
        sentence = (
            f"The lower bound of the relative {percent} CI is {shown}%, "
            f"which exceeds the {limit}% threshold."
        )
        return "regression", low, True, sentence
    sentence = (
        f"The lower bound of the relative {percent} CI is {shown}%, "
        f"which does not exceed the {limit}% threshold."
    )
    return "pass", low, True, sentence


def _relative(difference: MetricDifference) -> str:
    if difference.relative_percent is None:
        return "n/a"
    return f"{_fmt_num(difference.relative_percent)}%"


def _relative_interval(difference: MetricDifference) -> str:
    interval = difference.relative_interval
    if interval is None:
        return "n/a"
    return f"[{_fmt_num(interval.low)}%, {_fmt_num(interval.high)}%]"


def _has_cache(report: Report) -> bool:
    for arm in report.arms:
        if (
            arm.cache_read_cost != 0
            or arm.cache_write_cost != 0
            or arm.cache_savings != 0
            or arm.cache_priced_as_input
        ):
            return True
    return False
