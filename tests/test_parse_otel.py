"""OTel GenAI JSON export parser."""

from __future__ import annotations

import json

from agentcost import EventKind, EventStatus, parse_otel


def _otlp(spans: list[dict], resource_attributes: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {"attributes": resource_attributes or []},
                    "scopeSpans": [{"spans": spans}],
                }
            ]
        }
    )


def _attr(key: str, value: object) -> dict:
    if isinstance(value, str):
        encoded: dict = {"stringValue": value}
    elif isinstance(value, int):
        encoded = {"intValue": str(value)}
    else:
        encoded = {"doubleValue": value}
    return {"key": key, "value": encoded}


def test_reads_gen_ai_usage_and_agentcost_ids() -> None:
    raw = _otlp(
        [
            {
                "traceId": "trace-1",
                "spanId": "span-1",
                "name": "chat gpt-4o-mini",
                "attributes": [
                    _attr("gen_ai.operation.name", "chat"),
                    _attr("gen_ai.request.model", "gpt-4o-mini"),
                    _attr("gen_ai.usage.input_tokens", 200),
                    _attr("gen_ai.usage.output_tokens", 40),
                    _attr("agentcost.task_id", "q1"),
                    _attr("agentcost.run_id", "run-1"),
                ],
                "status": {"code": "STATUS_CODE_OK"},
            }
        ],
        resource_attributes=[_attr("agentcost.variant", "A")],
    )
    events = parse_otel(raw)
    assert len(events) == 1
    event = events[0]
    assert event.task_id == "q1"
    assert event.variant == "A"
    assert event.run_id == "run-1"
    assert event.kind is EventKind.LLM
    assert event.model == "gpt-4o-mini"
    assert event.input_tokens == 200
    assert event.output_tokens == 40
    assert event.status is EventStatus.OK


def test_legacy_prompt_tokens_tool_span_and_error_status() -> None:
    raw = _otlp(
        [
            {
                "traceId": "trace-9",
                "spanId": "span-tool",
                "attributes": [
                    _attr("gen_ai.operation.name", "execute_tool"),
                    _attr("gen_ai.tool.name", "search"),
                    _attr("agentcost.task_id", "q2"),
                    _attr("agentcost.variant", "B"),
                ],
                "status": {"code": 2},
            },
            {
                "traceId": "trace-9",
                "spanId": "span-chat",
                "attributes": [
                    _attr("gen_ai.operation.name", "chat"),
                    _attr("gen_ai.response.model", "gpt-4o"),
                    _attr("gen_ai.usage.prompt_tokens", 15),
                    _attr("gen_ai.usage.completion_tokens", 3),
                    _attr("agentcost.task_id", "q2"),
                    _attr("agentcost.variant", "B"),
                ],
                "status": {},
            },
        ]
    )
    tool, chat = parse_otel(raw)
    assert tool.kind is EventKind.TOOL
    assert tool.model is None
    assert tool.status is EventStatus.ERROR
    assert tool.run_id == "trace-9"
    assert chat.input_tokens == 15
    assert chat.output_tokens == 3
    assert chat.model == "gpt-4o"
    assert chat.status is EventStatus.OK


def test_invoke_agent_wrapper_is_dropped_when_child_spans_exist() -> None:
    raw = _otlp(
        [
            {
                "traceId": "trace-1",
                "spanId": "parent",
                "attributes": [
                    _attr("gen_ai.operation.name", "invoke_agent"),
                    _attr("gen_ai.request.model", "gpt-4o"),
                    _attr("gen_ai.usage.input_tokens", 99999),
                    _attr("gen_ai.usage.output_tokens", 99999),
                    _attr("agentcost.task_id", "q1"),
                    _attr("agentcost.variant", "A"),
                ],
            },
            {
                "traceId": "trace-1",
                "spanId": "child",
                "attributes": [
                    _attr("gen_ai.operation.name", "chat"),
                    _attr("gen_ai.request.model", "gpt-4o-mini"),
                    _attr("gen_ai.usage.input_tokens", 10),
                    _attr("gen_ai.usage.output_tokens", 2),
                    _attr("agentcost.task_id", "q1"),
                    _attr("agentcost.variant", "A"),
                ],
            },
        ]
    )
    events = parse_otel(raw)
    assert len(events) == 1
    assert events[0].input_tokens == 10
    assert events[0].model == "gpt-4o-mini"


def test_invoke_agent_kept_when_it_is_the_only_span() -> None:
    raw = _otlp(
        [
            {
                "traceId": "trace-only",
                "spanId": "parent",
                "attributes": [
                    _attr("gen_ai.operation.name", "invoke_agent"),
                    _attr("gen_ai.request.model", "gpt-4o-mini"),
                    _attr("gen_ai.usage.input_tokens", 8),
                    _attr("gen_ai.usage.output_tokens", 1),
                    _attr("agentcost.task_id", "q9"),
                    _attr("agentcost.variant", "A"),
                    _attr("agentcost.run_id", "solo"),
                ],
            }
        ]
    )
    events = parse_otel(raw)
    assert len(events) == 1
    assert events[0].run_id == "solo"
    assert events[0].input_tokens == 8


def test_flat_span_list() -> None:
    raw = json.dumps(
        [
            {
                "traceId": "t",
                "spanId": "s",
                "attributes": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "gpt-4o-mini",
                    "gen_ai.usage.input_tokens": 4,
                    "gen_ai.usage.output_tokens": 1,
                    "agentcost.task_id": "q",
                    "agentcost.variant": "A",
                    "agentcost.run_id": "r",
                },
            }
        ]
    )
    events = parse_otel(raw)
    assert events[0].input_tokens == 4
    assert events[0].variant == "A"
