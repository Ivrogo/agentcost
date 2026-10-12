"""The checked-in synthetic research-agent sample stays comparable."""

from __future__ import annotations

from pathlib import Path

from agentcost import EventKind, Verdict, compare, load_traces, parse_otel

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "research_agent"


def test_research_agent_sample_prefers_the_smaller_model() -> None:
    events = load_traces(EXAMPLE / "traces.jsonl")
    report = compare(events, ("A", "B"))
    assert report.verdict is Verdict.BETTER
    assert report.arm("A").tasks >= 5
    assert report.arm("B").tasks >= 5
    assert report.arm("A").failed_runs > 0
    assert report.arm("B").successful_tasks < report.arm("B").tasks
    assert report.arm("A").cost_per_solved_task is not None
    assert report.arm("B").cost_per_solved_task is not None
    assert report.arm("A").cost_per_solved_task < report.arm("B").cost_per_solved_task


def test_otel_fragment_drops_the_agent_wrapper() -> None:
    events = parse_otel((EXAMPLE / "otel_fragment.json").read_text(encoding="utf-8"))
    assert [event.kind for event in events] == [EventKind.TOOL, EventKind.LLM]
    assert events[1].input_tokens == 1480
    assert all(event.input_tokens < 10_000 for event in events)
