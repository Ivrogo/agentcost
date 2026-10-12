"""Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agentcost.cli import app

runner = CliRunner()


def _write_traces(path: Path) -> None:
    lines = []
    for variant, tokens in (("A", 1_000_000), ("B", 5_000_000)):
        for index in range(6):
            lines.append(
                json.dumps(
                    {
                        "task_id": f"q{index}",
                        "variant": variant,
                        "run_id": "r1",
                        "kind": "llm",
                        "tokens": {"input": tokens, "output": 0},
                        "model": "gpt-4o-mini",
                        "status": "ok",
                    }
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_report_compare_json_and_price_override(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _write_traces(traces)
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "version": "cli",
                "currency": "USD",
                "models": {"gpt-4o-mini": {"input": 1, "output": 1}},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "report",
            str(traces),
            "--compare",
            "A",
            "B",
            "--format",
            "json",
            "--prices",
            str(prices),
            "--set-price",
            "gpt-4o-mini=2:2",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "better"
    assert payload["compare"] == ["A", "B"]
    # --set-price wins over the file: 1_000_000 tokens * $2 / 1e6 = $2.
    assert payload["arms"]["A"]["cost_per_solved_task"] == 2
    assert payload["arms"]["B"]["cost_per_solved_task"] == 10


def test_report_markdown_is_the_default(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _write_traces(traces)
    result = runner.invoke(app, ["report", str(traces), "--compare", "A", "B", "--format", "md"])
    assert result.exit_code == 0, result.output
    assert "Verdict" in result.stdout
    assert "gpt-4o-mini" not in result.stdout or "Success rate" in result.stdout
