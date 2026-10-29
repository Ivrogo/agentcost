"""Typer CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from agentcost.cli import app

runner = CliRunner()
EXAMPLE_TRACES = (
    Path(__file__).resolve().parents[1] / "examples" / "research_agent" / "traces.jsonl"
)


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


def _report(*args: str):
    return runner.invoke(
        app,
        ["report", str(EXAMPLE_TRACES), "--compare", "A", "B", *args],
    )


def test_report_help_lists_pairing_flags() -> None:
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    # Rich bolds each hyphen, so "--paired" is not contiguous when color is on.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--paired" in plain
    assert "--unpaired" in plain


def test_format_both_refuses_output_that_already_ends_in_json(tmp_path: Path) -> None:
    output = tmp_path / "informe.json"
    result = _report("--format", "both", "--output", str(output))
    assert result.exit_code == 1
    assert str(output) in result.stderr
    assert not output.exists()
    assert result.stdout == ""


def test_format_both_writes_markdown_and_json_for_md_output(tmp_path: Path) -> None:
    output = tmp_path / "informe.md"
    result = _report("--format", "both", "--output", str(output))
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    markdown = output.read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "informe.json").read_text(encoding="utf-8"))
    assert "**Verdict:** better" in markdown
    assert payload["verdict"] == "better"


def test_format_both_keeps_unsuffixed_output_as_markdown(tmp_path: Path) -> None:
    output = tmp_path / "informe"
    result = _report("--format", "both", "--output", str(output))
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "**Verdict:** better" in output.read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "informe.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == "better"


def test_shared_task_ids_are_paired_in_the_json_report(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _write_traces(traces)
    result = runner.invoke(
        app,
        ["report", str(traces), "--compare", "A", "B", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["pairing"]["mode"] == "paired"
    assert payload["pairing"]["pairs"] == 6
    assert payload["pairing"]["metrics"]["cost"]["includes_zero"] is False


def test_no_shared_task_id_warns_on_stdout_and_stderr(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    lines = []
    for variant, task_id in (("A", "only-a"), ("B", "only-b")):
        lines.append(
            json.dumps(
                {
                    "task_id": task_id,
                    "variant": variant,
                    "run_id": "r1",
                    "kind": "llm",
                    "tokens": {"input": 10, "output": 0},
                    "model": "gpt-4o-mini",
                    "status": "ok",
                }
            )
        )
    traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
    warning = "No shared task_id between 'A' and 'B'. Using the unpaired comparison."
    for output_format in ("md", "json"):
        result = runner.invoke(
            app,
            ["report", str(traces), "--compare", "A", "B", "--format", output_format],
        )
        assert result.exit_code == 0, result.output
        assert warning in result.stderr
        assert warning in result.stdout
        if output_format == "md":
            assert "**Pairing:** unpaired (0 pairs)." in result.stdout
        else:
            payload = json.loads(result.stdout)
            assert payload["pairing"]["mode"] == "unpaired"
            assert payload["pairing"]["pairs"] == 0


def test_pairing_flags_force_the_mode(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    _write_traces(traces)
    unpaired = runner.invoke(
        app,
        ["report", str(traces), "--compare", "A", "B", "--format", "json", "--unpaired"],
    )
    assert unpaired.exit_code == 0, unpaired.output
    assert unpaired.stderr == ""
    payload = json.loads(unpaired.stdout)
    assert payload["pairing"]["mode"] == "unpaired"
    assert payload["pairing"]["pairs"] == 0
    assert payload["pairing"]["shared"] == 6
    assert payload["pairing"]["warning"] is None

    both = runner.invoke(
        app,
        ["report", str(traces), "--compare", "A", "B", "--paired", "--unpaired"],
    )
    assert both.exit_code == 1
    assert "--paired" in both.stderr
    assert both.stdout == ""

    disjoint = tmp_path / "disjoint.jsonl"
    disjoint.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "a1",
                        "variant": "A",
                        "run_id": "r1",
                        "kind": "llm",
                        "tokens": {"input": 10, "output": 0},
                        "model": "gpt-4o-mini",
                        "status": "ok",
                    }
                ),
                json.dumps(
                    {
                        "task_id": "b1",
                        "variant": "B",
                        "run_id": "r1",
                        "kind": "llm",
                        "tokens": {"input": 10, "output": 0},
                        "model": "gpt-4o-mini",
                        "status": "ok",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    forced = runner.invoke(
        app,
        ["report", str(disjoint), "--compare", "A", "B", "--paired"],
    )
    assert forced.exit_code == 1
    assert "shared task_id" in forced.stderr
    assert forced.stdout == ""


def test_format_json_writes_only_the_json_file(tmp_path: Path) -> None:
    output = tmp_path / "informe.json"
    result = _report("--format", "json", "--output", str(output))
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    text = output.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["verdict"] == "better"
    assert "**Verdict:**" not in text
    assert list(tmp_path.iterdir()) == [output]


CACHE_TRACES = Path(__file__).resolve().parents[1] / "examples" / "cache_usage" / "traces.jsonl"


def test_cli_price_file_overrides_cache_read(tmp_path: Path) -> None:
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "version": "lab",
                "currency": "USD",
                "models": {"gpt-4o": {"input": 2.5, "output": 10, "cache_read": 0}},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "report",
            str(CACHE_TRACES),
            "--compare",
            "openai",
            "anthropic",
            "--format",
            "json",
            "--prices",
            str(prices),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    openai = payload["arms"]["openai"]
    assert openai["cost_breakdown"]["cache_read"] == 0
    assert openai["cache_priced_as_input"] == []
    assert openai["total_cost"] == 0.003215
    assert payload["arms"]["anthropic"]["total_cost"] == 0.015384


def test_cli_set_price_leaves_cache_rate_unset(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "report",
            str(CACHE_TRACES),
            "--compare",
            "openai",
            "anthropic",
            "--format",
            "json",
            "--set-price",
            "gpt-4o=2.5:10",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    openai = payload["arms"]["openai"]
    # 86 * 2.5 + 1920 * 2.5 + 300 * 10 = 8015, per million.
    assert openai["total_cost"] == 0.008015
    assert openai["cache_savings"] == 0
    assert openai["cache_priced_as_input"] == ["gpt-4o cache_read"]
    markdown = runner.invoke(
        app,
        [
            "report",
            str(CACHE_TRACES),
            "--compare",
            "openai",
            "anthropic",
            "--set-price",
            "gpt-4o=2.5:10",
        ],
    )
    assert markdown.exit_code == 0, markdown.output
    assert "priced at the input rate" in markdown.stdout
