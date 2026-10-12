"""JSONL trace parser."""

from __future__ import annotations

import pytest

from agentcost import EventKind, EventStatus, ParseError, parse_jsonl


def test_parses_nested_tokens_and_status() -> None:
    text = "\n".join(
        [
            "",
            '{"task_id":"q1","variant":"A","run_id":"r1","kind":"llm",'
            '"tokens":{"input":120,"output":30},"model":"gpt-4o-mini","status":"ok"}',
            '{"task_id":"q1","variant":"A","run_id":"r1","kind":"tool","status":"error"}',
        ]
    )
    events = parse_jsonl(text)
    assert len(events) == 2
    llm, tool = events
    assert llm.task_id == "q1"
    assert llm.variant == "A"
    assert llm.run_id == "r1"
    assert llm.kind is EventKind.LLM
    assert llm.input_tokens == 120
    assert llm.output_tokens == 30
    assert llm.model == "gpt-4o-mini"
    assert llm.status is EventStatus.OK
    assert tool.kind is EventKind.TOOL
    assert tool.input_tokens == 0
    assert tool.output_tokens == 0
    assert tool.model is None
    assert tool.status is EventStatus.ERROR


def test_accepts_flat_token_fields_and_ok_boolean() -> None:
    text = (
        '{"task_id":"q1","variant":"B","run_id":"r9","input_tokens":5,'
        '"output_tokens":2,"model":"gpt-4o","ok":false}\n'
    )
    event = parse_jsonl(text)[0]
    assert event.kind is EventKind.LLM
    assert event.input_tokens == 5
    assert event.output_tokens == 2
    assert event.status is EventStatus.ERROR


def test_invalid_line_includes_line_number() -> None:
    text = '{"task_id":"q1","variant":"A","run_id":"r1","status":"ok"}\n{not json}\n'
    with pytest.raises(ParseError, match=r"line 2"):
        parse_jsonl(text)


def test_missing_task_id_is_an_error() -> None:
    text = '{"variant":"A","run_id":"r1","status":"ok"}\n'
    with pytest.raises(ParseError, match="task_id"):
        parse_jsonl(text)
