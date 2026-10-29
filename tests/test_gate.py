"""CI gate: exit codes and the pull-request summary."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from agentcost.cli import app

runner = CliRunner()
REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / "examples" / "ci" / "agentcost.yml"
SNAPSHOT = (REPO / "tests" / "snapshots" / "ci_summary.md").read_text(encoding="utf-8")


def _pairs(path: Path, pairs: list[tuple[int, int]]) -> None:
    lines = []
    for index, (left, right) in enumerate(pairs, start=1):
        for variant, tokens in (("A", left), ("B", right)):
            lines.append(
                json.dumps(
                    {
                        "task_id": f"t{index}",
                        "variant": variant,
                        "run_id": "r",
                        "kind": "llm",
                        "tokens": {"input": tokens, "output": 0},
                        "model": "m",
                        "status": "ok",
                    }
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(path: Path, *args: str):
    return runner.invoke(
        app,
        ["report", str(path), "--compare", "A", "B", "--set-price", "m=1:1", *args],
    )


def test_improvement_exits_zero(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(2_000_000, 5_000_000)] * 5)
    summary = tmp_path / "summary.md"
    result = _run(
        traces,
        "--fail-if-worse",
        "--max-regression",
        "5",
        "--markdown-summary",
        str(summary),
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    text = summary.read_text(encoding="utf-8")
    assert "**Verdict:** better" in text
    assert "**Gate:** pass" in text
    assert "**Mode:** paired (5 pairs)" in text
    assert "does not exceed the 5% threshold" in text


def test_clear_regression_exits_three(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(4_200_000, 4_000_000)] * 5)
    result = _run(traces, "--fail-if-worse")
    assert result.exit_code == 3, result.output
    assert "worse" in result.stderr
    assert "**Verdict:** worse" in result.stdout


def test_regression_within_threshold_exits_zero(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(4_200_000, 4_000_000)] * 5)
    summary = tmp_path / "summary.md"
    result = _run(traces, "--max-regression", "10", "--markdown-summary", str(summary))
    assert result.exit_code == 0, result.output
    text = summary.read_text(encoding="utf-8")
    assert "**Verdict:** worse" in text
    assert "**Gate:** pass" in text
    assert "does not exceed the 10% threshold" in text


def test_threshold_equal_to_the_lower_bound_passes(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(4_200_000, 4_000_000)] * 5)
    result = _run(traces, "--max-regression", "5%")
    assert result.exit_code == 0, result.output


def test_unpaired_worse_exits_three_and_warns(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    lines = []
    for index in range(6):
        for variant, task_id, tokens in (
            ("A", f"a{index}", 5_000_000),
            ("B", f"b{index}", 1_000_000),
        ):
            lines.append(
                json.dumps(
                    {
                        "task_id": task_id,
                        "variant": variant,
                        "run_id": "r",
                        "kind": "llm",
                        "tokens": {"input": tokens, "output": 0},
                        "model": "m",
                        "status": "ok",
                    }
                )
            )
    traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    result = _run(traces, "--fail-if-worse", "--markdown-summary", str(summary))
    assert result.exit_code == 3, result.output
    warning = "No shared task_id between 'A' and 'B'. Using the unpaired comparison."
    assert warning in result.stderr
    text = summary.read_text(encoding="utf-8")
    assert "**Mode:** unpaired (0 pairs)" in text
    assert "**Gate:** regression" in text
    assert warning in text
    assert "under the unpaired verdict" in text


def test_negative_threshold_is_an_input_error(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(8_000_000, 4_000_000)] * 5)
    result = _run(traces, "--max-regression", "-1")
    assert result.exit_code == 1
    assert result.exit_code != 3
    assert "--max-regression" in result.stderr
    assert result.stdout == ""


def test_ci_summary_snapshot(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(8_000_000, 4_000_000)] * 5)
    summary = tmp_path / "summary.md"
    result = _run(
        traces,
        "--fail-if-worse",
        "--max-regression",
        "5",
        "--markdown-summary",
        str(summary),
    )
    assert result.exit_code == 3, result.output
    assert summary.read_text(encoding="utf-8") == SNAPSHOT
    assert "**Verdict:** worse" in result.stdout


def test_worse_verdict_stays_zero_without_a_gate(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(8_000_000, 4_000_000)] * 5)
    summary = tmp_path / "summary.md"
    result = _run(traces, "--markdown-summary", str(summary))
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    text = summary.read_text(encoding="utf-8")
    assert "**Verdict:** worse" in text
    assert "**Gate:** not requested" in text


def test_four_pairs_do_not_trip_fail_if_worse_but_can_trip_the_threshold(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(8_000_000, 4_000_000)] * 4)
    held = _run(traces, "--fail-if-worse")
    assert held.exit_code == 0, held.output
    assert "Fewer than 5" in held.stdout
    tripped = _run(traces, "--max-regression", "5")
    assert tripped.exit_code == 3, tripped.output


def test_unpaired_threshold_exits_one_and_writes_the_summary(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    lines = []
    for index in range(6):
        for variant, task_id, tokens in (
            ("A", f"a{index}", 5_000_000),
            ("B", f"b{index}", 1_000_000),
        ):
            lines.append(
                json.dumps(
                    {
                        "task_id": task_id,
                        "variant": variant,
                        "run_id": "r",
                        "kind": "llm",
                        "tokens": {"input": tokens, "output": 0},
                        "model": "m",
                        "status": "ok",
                    }
                )
            )
    traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    result = _run(
        traces,
        "--fail-if-worse",
        "--max-regression",
        "5",
        "--markdown-summary",
        str(summary),
    )
    assert result.exit_code == 1, result.output
    assert result.exit_code != 3
    assert "--max-regression" in result.stderr
    text = summary.read_text(encoding="utf-8")
    assert "**Gate:** error" in text
    assert "**Mode:** unpaired (0 pairs)" in text
    assert "No shared task_id" in text


def test_tokens_metric_uses_the_paired_token_interval(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    lines = []
    for index in range(5):
        lines.append(
            json.dumps(
                {
                    "task_id": f"t{index}",
                    "variant": "A",
                    "run_id": "r",
                    "kind": "llm",
                    "tokens": {"input": 5_000_000, "output": 0},
                    "model": "m",
                    "status": "ok",
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "task_id": f"t{index}",
                    "variant": "B",
                    "run_id": "r",
                    "kind": "llm",
                    "tokens": {"input": 0, "output": 1_000_000},
                    "model": "m",
                    "status": "ok",
                }
            )
        )
    traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cost = runner.invoke(
        app,
        [
            "report",
            str(traces),
            "--compare",
            "A",
            "B",
            "--set-price",
            "m=0:1",
            "--fail-if-worse",
            "--metric",
            "cost",
        ],
    )
    assert cost.exit_code == 0, cost.output
    tokens = runner.invoke(
        app,
        [
            "report",
            str(traces),
            "--compare",
            "A",
            "B",
            "--set-price",
            "m=0:1",
            "--fail-if-worse",
            "--metric",
            "tokens",
        ],
    )
    assert tokens.exit_code == 3, tokens.output
    assert "tokens" in tokens.stderr


def test_two_trace_files_are_concatenated(tmp_path: Path) -> None:
    left = tmp_path / "a.jsonl"
    right = tmp_path / "b.jsonl"
    left_lines = []
    right_lines = []
    for index in range(5):
        left_lines.append(
            json.dumps(
                {
                    "task_id": f"t{index}",
                    "variant": "A",
                    "run_id": "r",
                    "kind": "llm",
                    "tokens": {"input": 2_000_000, "output": 0},
                    "model": "m",
                    "status": "ok",
                }
            )
        )
        right_lines.append(
            json.dumps(
                {
                    "task_id": f"t{index}",
                    "variant": "B",
                    "run_id": "r",
                    "kind": "llm",
                    "tokens": {"input": 5_000_000, "output": 0},
                    "model": "m",
                    "status": "ok",
                }
            )
        )
    left.write_text("\n".join(left_lines) + "\n", encoding="utf-8")
    right.write_text("\n".join(right_lines) + "\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "report",
            str(left),
            str(right),
            "--compare",
            "A",
            "B",
            "--format",
            "json",
            "--set-price",
            "m=1:1",
            "--fail-if-worse",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["pairing"]["pairs"] == 5
    assert payload["verdict"] == "better"


def test_github_step_summary_appends_when_the_variable_is_set(tmp_path: Path, monkeypatch) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(2_000_000, 5_000_000)] * 5)
    step = tmp_path / "step.md"
    step.write_text("previous\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step))
    result = _run(traces, "--github-step-summary", "--fail-if-worse")
    assert result.exit_code == 0, result.output
    text = step.read_text(encoding="utf-8")
    assert text.startswith("previous\n")
    assert "<!-- agentcost-ci -->" in text
    assert "**Gate:** pass" in text


def test_github_step_summary_is_a_noop_without_the_variable(tmp_path: Path, monkeypatch) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(2_000_000, 5_000_000)] * 5)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    result = _run(traces, "--github-step-summary")
    assert result.exit_code == 0, result.output
    assert list(tmp_path.iterdir()) == [traces]


def test_cache_rows_appear_when_a_trace_has_cache_cost(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    lines = []
    for variant, cached in (("A", 2_000_000), ("B", 1_000_000)):
        lines.append(
            json.dumps(
                {
                    "task_id": "t1",
                    "variant": variant,
                    "run_id": "r",
                    "kind": "llm",
                    "tokens": {"input": 0, "output": 0, "cache_read": cached},
                    "model": "m",
                    "status": "ok",
                }
            )
        )
    traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "version": "test",
                "currency": "USD",
                "models": {"m": {"input": 1, "output": 1, "cache_read": 0.5}},
            }
        ),
        encoding="utf-8",
    )
    summary = tmp_path / "summary.md"
    result = runner.invoke(
        app,
        [
            "report",
            str(traces),
            "--compare",
            "A",
            "B",
            "--prices",
            str(prices),
            "--markdown-summary",
            str(summary),
        ],
    )
    assert result.exit_code == 0, result.output
    text = summary.read_text(encoding="utf-8")
    assert "| Cache read cost | $1 | $0.5 |" in text
    assert "| Cache savings vs input price | $1 | $0.5 |" in text
    assert "Cache read cost" not in SNAPSHOT


def test_markdown_summary_refuses_the_report_path(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _pairs(traces, [(2_000_000, 5_000_000)] * 5)
    output = tmp_path / "out.md"
    result = _run(
        traces,
        "--output",
        str(output),
        "--markdown-summary",
        str(output),
    )
    assert result.exit_code == 1
    assert result.exit_code != 3
    assert "same path" in result.stderr
    assert not output.exists()
    assert result.stdout == ""


def test_help_lists_the_gate_flags() -> None:
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--fail-if-worse" in plain
    assert "--max-regression" in plain
    assert "--markdown-summary" in plain
    assert "--github-step-summary" in plain
    assert "--metric" in plain


def test_example_workflow_is_a_copyable_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert not (REPO / ".github" / "workflows" / "agentcost.yml").exists()
    assert "pull-requests: write" in text
    assert "contents: read" in text
    assert "--fail-if-worse" in text
    assert "--max-regression" in text
    assert "--markdown-summary" in text
    assert "--github-step-summary" in text
    assert "actions/github-script@" in text
    assert "candidate.jsonl" in text
    assert "baseline.jsonl" in text
    assert "--compare candidate baseline" in text
    assert "secrets." not in text
