"""Thin Typer CLI. ``agentcost report traces.jsonl --compare A B``."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from agentcost.errors import AgentCostError, CompareError, PriceError
from agentcost.local_logs import (
    ImportedEvent,
    load_claude_code,
    load_codex_cli,
    render_imported_jsonl,
)
from agentcost.pairing import RequestedPairing
from agentcost.parse import load_traces
from agentcost.pricing import ModelPrice, PriceTable
from agentcost.report import compare, render_json, render_markdown


def _prefer_utf8_stdio() -> None:
    """Help and reports use characters outside legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


_prefer_utf8_stdio()

app = typer.Typer(
    name="agentcost",
    help="Measure per-task LLM agent cost and compare two variants from traces.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Measure per-task LLM agent cost and compare two variants from traces."""


@app.command()
def report(
    path: Annotated[
        Path,
        typer.Argument(help="JSONL trace or OTel GenAI JSON export.", exists=True, dir_okay=False),
    ],
    compare_variants: Annotated[
        tuple[str, str],
        typer.Option(
            "--compare",
            help="Two variant names. The verdict is about the first versus the second.",
        ),
    ],
    output_format: Annotated[
        str,
        typer.Option("--format", help="md (default), json, or both."),
    ] = "md",
    prices: Annotated[
        Path | None,
        typer.Option("--prices", help="Price file merged on top of the bundled snapshot."),
    ] = None,
    set_price: Annotated[
        list[str] | None,
        typer.Option(
            "--set-price",
            help="MODEL=INPUT:OUTPUT, USD per 1,000,000 tokens. Repeatable.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write the report to this path instead of stdout."),
    ] = None,
    seed: Annotated[int, typer.Option("--seed", help="Bootstrap seed. Default is fixed.")] = 42,
    bootstrap: Annotated[int, typer.Option("--bootstrap", help="Bootstrap resamples.")] = 1000,
    allow_unpriced: Annotated[
        bool,
        typer.Option("--allow-unpriced", help="Price unknown models as zero and list them."),
    ] = False,
    paired: Annotated[
        bool,
        typer.Option(
            "--paired",
            help="Pair tasks that share a task_id. Default pairs when any task_id is shared.",
        ),
    ] = False,
    unpaired: Annotated[
        bool,
        typer.Option("--unpaired", help="Compare the arms without matching task_id."),
    ] = False,
) -> None:
    """Build an A/B cost report from a trace file."""
    try:
        _emit_report(
            path=path,
            compare_variants=compare_variants,
            output_format=output_format,
            prices=prices,
            set_price=set_price,
            output=output,
            seed=seed,
            bootstrap=bootstrap,
            allow_unpriced=allow_unpriced,
            paired=paired,
            unpaired=unpaired,
        )
    except AgentCostError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _emit_report(
    *,
    path: Path,
    compare_variants: tuple[str, str],
    output_format: str,
    prices: Path | None,
    set_price: list[str] | None,
    output: Path | None,
    seed: int,
    bootstrap: int,
    allow_unpriced: bool,
    paired: bool,
    unpaired: bool,
) -> None:
    if output_format not in {"md", "json", "both"}:
        raise PriceError("--format must be md, json, or both")
    pairing = _pairing_mode(paired, unpaired)
    table = PriceTable.bundled()
    if prices is not None:
        table = table.merge(PriceTable.load(prices))
    if set_price:
        table = table.override(
            {name: price for name, price in (_parse_set_price(item) for item in set_price)}
        )
    events = load_traces(path)
    built = compare(
        events,
        compare_variants,
        prices=table,
        seed=seed,
        resamples=bootstrap,
        on_missing="zero" if allow_unpriced else "error",
        pairing=pairing,
    )
    if built.pairing.warning:
        typer.echo(built.pairing.warning, err=True)
    markdown = render_markdown(built)
    payload = render_json(built)
    if output is None:
        if output_format in {"md", "both"}:
            typer.echo(markdown, nl=False)
        if output_format == "both":
            typer.echo()
        if output_format in {"json", "both"}:
            typer.echo(payload, nl=False)
        return
    json_path: Path | None = None
    if output_format == "both":
        json_path = output.with_suffix(".json")
        if json_path == output:
            raise AgentCostError(
                f"--format both would write Markdown and JSON to the same path: {output}"
            )
    if output_format == "json":
        output.write_text(payload, encoding="utf-8", newline="\n")
        return
    output.write_text(markdown, encoding="utf-8", newline="\n")
    if json_path is not None:
        json_path.write_text(payload, encoding="utf-8", newline="\n")


def _pairing_mode(paired: bool, unpaired: bool) -> RequestedPairing:
    if paired and unpaired:
        raise CompareError("Pass only one of --paired and --unpaired.")
    if paired:
        return "paired"
    if unpaired:
        return "unpaired"
    return "auto"


def _parse_set_price(raw: str) -> tuple[str, ModelPrice]:
    if "=" not in raw:
        raise PriceError(f"--set-price {raw!r} must look like MODEL=INPUT:OUTPUT")
    model, rest = raw.split("=", 1)
    if ":" not in rest:
        raise PriceError(f"--set-price {raw!r} must look like MODEL=INPUT:OUTPUT")
    raw_input, raw_output = rest.split(":", 1)
    model = model.strip()
    if not model:
        raise PriceError(f"--set-price {raw!r} is missing a model name")
    try:
        input_price = Decimal(raw_input.strip())
        output_price = Decimal(raw_output.strip())
    except Exception as exc:
        raise PriceError(f"--set-price {raw!r} has a non-numeric price") from exc
    if input_price < 0 or output_price < 0:
        raise PriceError(f"--set-price {raw!r} has a negative price")
    return model, ModelPrice(input_per_million=input_price, output_per_million=output_price)


import_app = typer.Typer(
    help="Read local Claude Code or Codex CLI logs into an agentcost JSONL trace.",
    add_completion=False,
    no_args_is_help=True,
)
app.add_typer(import_app, name="import")


def _import_logs(
    loader: Callable[..., Sequence[ImportedEvent]],
    path: str | None,
    variant: str,
    output: Path | None,
) -> None:
    try:
        items = loader(
            Path(path) if path else None,
            variant=variant,
            home=Path.home(),
            environ=os.environ,
        )
        text = render_imported_jsonl(items)
    except AgentCostError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if output is None:
        typer.echo(text, nl=False)
        return
    output.write_text(text, encoding="utf-8", newline="\n")


@import_app.command("claude-code")
def import_claude_code_logs(
    path: Annotated[
        str | None,
        typer.Argument(
            help="JSONL file or directory. Omit to read ~/.claude/projects or CLAUDE_CONFIG_DIR.",
        ),
    ] = None,
    variant: Annotated[
        str,
        typer.Option("--variant", help="Variant label stored on every imported session."),
    ] = "default",
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write the JSONL trace here instead of stdout."),
    ] = None,
) -> None:
    """Import Claude Code sessions. One session is one task."""
    _import_logs(load_claude_code, path, variant, output)


@import_app.command("codex")
def import_codex_logs(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Rollout file or directory. Omit to read ~/.codex/sessions or CODEX_HOME.",
        ),
    ] = None,
    variant: Annotated[
        str,
        typer.Option("--variant", help="Variant label stored on every imported rollout."),
    ] = "default",
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Write the JSONL trace here instead of stdout."),
    ] = None,
) -> None:
    """Import Codex CLI rollouts. One rollout is one task."""
    _import_logs(load_codex_cli, path, variant, output)
