"""Cost per task for LLM agents, and an A/B comparison of two variants."""

from agentcost.errors import AgentCostError, CompareError, ParseError, PriceError
from agentcost.models import (
    ArmReport,
    Event,
    EventKind,
    EventStatus,
    Interval,
    Quantiles,
    Report,
    Verdict,
)
from agentcost.parse import load_traces, parse_jsonl, parse_otel, parse_traces
from agentcost.pricing import ModelPrice, PriceTable
from agentcost.report import compare, render_json, render_markdown

__version__ = "0.1.0"

__all__ = [
    "AgentCostError",
    "ArmReport",
    "CompareError",
    "Event",
    "EventKind",
    "EventStatus",
    "Interval",
    "ModelPrice",
    "ParseError",
    "PriceError",
    "PriceTable",
    "Quantiles",
    "Report",
    "Verdict",
    "__version__",
    "compare",
    "load_traces",
    "parse_jsonl",
    "parse_otel",
    "parse_traces",
    "render_json",
    "render_markdown",
]
