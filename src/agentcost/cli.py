"""Thin Typer CLI. ``agentcost report traces.jsonl --compare A B``."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from agentcost.errors import AgentCostError, PriceError
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
) -> None:
    if output_format not in {"md", "json", "both"}:
        raise PriceError("--format must be md, json, or both")
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
    )
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
    if output_format == "json":
        output.write_text(payload, encoding="utf-8", newline="\n")
        return
    output.write_text(markdown, encoding="utf-8", newline="\n")
    if output_format == "both":
        json_path = output.with_suffix(".json")
        json_path.write_text(payload, encoding="utf-8", newline="\n")


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
