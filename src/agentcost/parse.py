"""Parsers for agentcost JSONL and OTel GenAI JSON exports."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentcost.errors import ParseError
from agentcost.models import Event, EventKind, EventStatus

_TOOL_OPS = frozenset({"execute_tool", "retrieval"})
_WRAPPER_OPS = frozenset({"invoke_agent", "create_agent", "invoke_workflow"})


def load_traces(path: str | Path) -> list[Event]:
    """Load a JSONL trace or an OTel GenAI JSON export."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"cannot read {file}: {exc}") from exc
    return parse_traces(text, filename=str(file))


def parse_traces(text: str, filename: str = "<memory>") -> list[Event]:
    """Detect JSONL versus a single OTel JSON document."""
    stripped = text.strip()
    if not stripped:
        raise ParseError(f"{filename}: empty trace input")
    if stripped[0] not in "{[":
        return parse_jsonl(text, filename=filename)
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return parse_jsonl(text, filename=filename)
    if isinstance(document, dict) and "task_id" in document:
        return parse_jsonl(text, filename=filename)
    if (
        isinstance(document, list)
        and document
        and isinstance(document[0], dict)
        and "task_id" in document[0]
    ):
        events: list[Event] = []
        for index, item in enumerate(document, start=1):
            try:
                events.append(_event_from_object(item))
            except ParseError as exc:
                raise ParseError(f"{filename}: item {index}: {exc}") from exc
        return events
    return _events_from_otel(document, filename)


def parse_jsonl(text: str, filename: str = "<memory>") -> list[Event]:
    """Parse one event per line.

    Canonical object: ``task_id``, ``variant``, ``run_id``, ``kind`` (``llm`` or
    ``tool``), ``tokens`` (``input`` / ``output``, plus optional disjoint
    ``cache_read``, ``cache_write_5m``, and ``cache_write_1h``), ``model``,
    ``status`` (``ok`` or ``error``). Flat ``input_tokens`` / ``output_tokens``
    and a boolean ``ok`` field are accepted.

    ``provider`` plus ``usage`` copies a documented provider payload instead of
    the disjoint ``tokens`` object. OpenAI's ``prompt_tokens`` / ``input_tokens``
    already include ``cached_tokens``, so those are subtracted. Anthropic's
    ``cache_read_input_tokens`` and ``cache_creation_input_tokens`` are separate
    from ``input_tokens``, so they are added. The two shapes together are
    rejected.
    """
    events: list[Event] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseError(f"{filename}: line {line_number}: invalid JSON ({exc.msg})") from exc
        if not isinstance(payload, dict):
            raise ParseError(f"{filename}: line {line_number}: event must be a JSON object")
        try:
            events.append(_event_from_object(payload))
        except ParseError as exc:
            raise ParseError(f"{filename}: line {line_number}: {exc}") from exc
    if not events:
        raise ParseError(f"{filename}: no events")
    return events


def parse_otel(text: str, filename: str = "<memory>") -> list[Event]:
    """Parse an OTel JSON export that uses ``gen_ai.*`` span attributes.

    Accepted shapes: OTLP ``resourceSpans``, ``{"spans": [...]}``, or a list of
    spans. Attributes may be an OTLP key/value list or a flat object.

    Experiment identity is not part of the GenAI semantic conventions. Set
    ``agentcost.task_id``, ``agentcost.variant``, and ``agentcost.run_id`` on
    the span or resource. ``gen_ai.conversation.id`` is a fallback task id, and
    the trace id is a fallback run id.

    ``invoke_agent``, ``create_agent``, and ``invoke_workflow`` spans are
    dropped when the same trace also has a chat, tool, or other GenAI span, so
    parent usage is not added on top of the child calls. A wrapper that is the
    only GenAI span in its trace is kept.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"{filename}: invalid OTel JSON ({exc.msg})") from exc
    return _events_from_otel(document, filename)


def _event_from_object(payload: dict[str, Any]) -> Event:
    task_id = _required_str(payload, "task_id")
    variant = _required_str(payload, "variant")
    run_id = _required_str(payload, "run_id")
    model = payload.get("model")
    if model is not None:
        model = str(model).strip() or None
    kind = _kind(payload, model)
    input_tokens, output_tokens, cache_read, cache_write_5m, cache_write_1h = _tokens(payload)
    status = _status(payload)
    return Event(
        task_id=task_id,
        variant=variant,
        run_id=run_id,
        kind=kind,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        status=status,
        cache_read_tokens=cache_read,
        cache_write_5m_tokens=cache_write_5m,
        cache_write_1h_tokens=cache_write_1h,
    )


def _required_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ParseError(f"missing or empty {field}")
    return value.strip()


def _kind(payload: dict[str, Any], model: str | None) -> EventKind:
    if "kind" not in payload:
        return EventKind.LLM if model else EventKind.TOOL
    raw = str(payload["kind"]).strip().lower()
    if raw == EventKind.LLM.value:
        return EventKind.LLM
    if raw == EventKind.TOOL.value:
        return EventKind.TOOL
    raise ParseError(f"kind must be 'llm' or 'tool', got {payload['kind']!r}")


_DIRECT_TOKEN_KEYS = (
    "tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
)


def _tokens(payload: dict[str, Any]) -> tuple[int, int, int, int, int]:
    usage = payload.get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            raise ParseError("usage must be an object")
        if any(key in payload for key in _DIRECT_TOKEN_KEYS):
            raise ParseError(
                "usage cannot be combined with tokens or input_tokens; "
                "pass the provider usage or the disjoint token counts, not both"
            )
        return _tokens_from_usage(payload.get("provider"), usage)
    nested = payload.get("tokens")
    if isinstance(nested, dict):
        cache_read = _non_negative_int(nested.get("cache_read", 0), "tokens.cache_read")
        cache_write_5m = _non_negative_int(nested.get("cache_write_5m", 0), "tokens.cache_write_5m")
        cache_write_1h = _non_negative_int(nested.get("cache_write_1h", 0), "tokens.cache_write_1h")
        _same_cache_count(nested, payload, "cache_read", cache_read, "cache_read_tokens")
        _same_cache_count(
            nested, payload, "cache_write_5m", cache_write_5m, "cache_write_5m_tokens"
        )
        _same_cache_count(
            nested, payload, "cache_write_1h", cache_write_1h, "cache_write_1h_tokens"
        )
        return (
            _non_negative_int(nested.get("input", 0), "tokens.input"),
            _non_negative_int(nested.get("output", 0), "tokens.output"),
            cache_read,
            cache_write_5m,
            cache_write_1h,
        )
    return (
        _non_negative_int(payload.get("input_tokens", 0), "input_tokens"),
        _non_negative_int(payload.get("output_tokens", 0), "output_tokens"),
        _non_negative_int(payload.get("cache_read_tokens", 0), "cache_read_tokens"),
        _non_negative_int(payload.get("cache_write_5m_tokens", 0), "cache_write_5m_tokens"),
        _non_negative_int(payload.get("cache_write_1h_tokens", 0), "cache_write_1h_tokens"),
    )


def _same_cache_count(
    nested: dict[str, Any],
    payload: dict[str, Any],
    nested_name: str,
    nested_value: int,
    flat_name: str,
) -> None:
    """A ``tokens`` object is the source of truth. A flat cache field must match it.

    Dropping the flat field would bill those tokens at the ordinary input rate, or
    not at all, without a signal. Input and output keep the v0.1 rule: when
    ``tokens`` is present, flat ``input_tokens`` / ``output_tokens`` are ignored.
    """
    if flat_name not in payload:
        return
    flat_value = _non_negative_int(payload[flat_name], flat_name)
    if nested_name not in nested:
        raise ParseError(
            f"{flat_name} is set alongside tokens; put {nested_name} inside tokens "
            "so that count is not dropped"
        )
    if flat_value != nested_value:
        raise ParseError(
            f"tokens.{nested_name} ({nested_value}) and {flat_name} ({flat_value}) disagree"
        )


def _tokens_from_usage(provider: object, usage: dict[str, Any]) -> tuple[int, int, int, int, int]:
    if not isinstance(provider, str) or not provider.strip():
        raise ParseError("usage requires provider 'openai' or 'anthropic'")
    name = provider.strip().lower()
    if name == "openai":
        return _openai_usage(usage)
    if name == "anthropic":
        return _anthropic_usage(usage)
    raise ParseError(f"usage provider must be 'openai' or 'anthropic', got {provider!r}")


def _openai_usage(usage: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """OpenAI includes cached tokens in the prompt/input total. Subtract them."""
    prompt_details = _details(usage, "prompt_tokens_details")
    input_details = _details(usage, "input_tokens_details")
    gross = _agree(
        "usage.prompt_tokens",
        _optional_int(usage, "prompt_tokens"),
        "usage.input_tokens",
        _optional_int(usage, "input_tokens"),
    )
    output = _agree(
        "usage.completion_tokens",
        _optional_int(usage, "completion_tokens"),
        "usage.output_tokens",
        _optional_int(usage, "output_tokens"),
    )
    cached = _agree(
        "usage.prompt_tokens_details.cached_tokens",
        _optional_int(prompt_details, "cached_tokens"),
        "usage.input_tokens_details.cached_tokens",
        _optional_int(input_details, "cached_tokens"),
    )
    gross = 0 if gross is None else gross
    output = 0 if output is None else output
    cached = 0 if cached is None else cached
    writes = _openai_write_tokens(prompt_details) + _openai_write_tokens(input_details)
    if writes:
        raise ParseError(
            "OpenAI cache_write_tokens is not priced in this version. "
            "input_tokens already includes those writes, so ignoring the field would "
            "bill them as ordinary input. This version prices cached_tokens reads, "
            "and Anthropic 5-minute and 1-hour writes."
        )
    if "total_tokens" in usage:
        total = _non_negative_int(usage["total_tokens"], "usage.total_tokens")
        if total != gross + output:
            raise ParseError(
                f"usage.total_tokens is {total} but prompt/input plus completion/output "
                f"is {gross + output}. Cached tokens are already inside the input count."
            )
    if cached > gross:
        raise ParseError(
            f"cached_tokens ({cached}) exceed prompt/input tokens ({gross}). "
            "OpenAI includes cached_tokens in that total."
        )
    return gross - cached, output, cached, 0, 0


def _openai_write_tokens(details: dict[str, Any]) -> int:
    write = _optional_int(details, "cache_write_tokens") or 0
    nested = details.get("cache_write_tokens_details")
    if nested is None:
        return write
    if not isinstance(nested, dict):
        raise ParseError("cache_write_tokens_details must be an object")
    parts = (_optional_int(nested, "ttl_30m_tokens") or 0) + (
        _optional_int(nested, "ttl_12h_tokens") or 0
    )
    if write and parts and write != parts:
        raise ParseError(
            f"cache_write_tokens is {write} but ttl_30m_tokens plus ttl_12h_tokens is {parts}"
        )
    return write or parts


def _anthropic_usage(usage: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """Anthropic reports cache reads and writes separately from input_tokens."""
    input_tokens = _non_negative_int(usage.get("input_tokens", 0), "usage.input_tokens")
    output_tokens = _non_negative_int(usage.get("output_tokens", 0), "usage.output_tokens")
    cache_read = _non_negative_int(
        usage.get("cache_read_input_tokens", 0), "usage.cache_read_input_tokens"
    )
    has_total = "cache_creation_input_tokens" in usage
    total = (
        _non_negative_int(usage["cache_creation_input_tokens"], "usage.cache_creation_input_tokens")
        if has_total
        else None
    )
    creation = usage.get("cache_creation")
    if creation is None:
        split = False
        five = 0
        one = 0
    elif not isinstance(creation, dict):
        raise ParseError("usage.cache_creation must be an object")
    else:
        split = "ephemeral_5m_input_tokens" in creation or "ephemeral_1h_input_tokens" in creation
        five = _non_negative_int(
            creation.get("ephemeral_5m_input_tokens", 0),
            "usage.cache_creation.ephemeral_5m_input_tokens",
        )
        one = _non_negative_int(
            creation.get("ephemeral_1h_input_tokens", 0),
            "usage.cache_creation.ephemeral_1h_input_tokens",
        )
    if split:
        if has_total and five + one != total:
            raise ParseError(
                f"cache_creation_input_tokens is {total} but ephemeral_5m_input_tokens "
                f"({five}) plus ephemeral_1h_input_tokens ({one}) is {five + one}. "
                "Those fields are the same writes, not an extra count."
            )
    elif has_total:
        five, one = total or 0, 0
    return input_tokens, output_tokens, cache_read, five, one


def _details(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ParseError(f"{field} must be an object")
    return value


def _agree(
    left_name: str,
    left: int | None,
    right_name: str,
    right: int | None,
) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    if left != right:
        raise ParseError(f"{left_name} ({left}) and {right_name} ({right}) disagree")
    return left


def _optional_int(payload: dict[str, Any], field: str) -> int | None:
    if field not in payload or payload[field] is None:
        return None
    return _non_negative_int(payload[field], field)


def _non_negative_int(value: object, field: str) -> int:
    number = _as_int(value, field)
    if number < 0:
        raise ParseError(f"{field} must be >= 0")
    return number


def _as_int(value: object, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ParseError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ParseError(f"{field} must be an integer")
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ParseError(f"{field} must be an integer") from exc
    raise ParseError(f"{field} must be an integer")


def _status(payload: dict[str, Any]) -> EventStatus:
    if "status" in payload:
        raw = str(payload["status"]).strip().lower()
        if raw in {"ok", "success"}:
            return EventStatus.OK
        if raw in {"error", "failed", "failure"}:
            return EventStatus.ERROR
        raise ParseError(f"status must be 'ok' or 'error', got {payload['status']!r}")
    if "ok" in payload:
        return EventStatus.OK if bool(payload["ok"]) else EventStatus.ERROR
    if "error" in payload and isinstance(payload["error"], bool):
        return EventStatus.ERROR if payload["error"] else EventStatus.OK
    raise ParseError("missing status")


@dataclass(frozen=True, slots=True)
class _RawSpan:
    event: Event
    trace_id: str
    wrapper: bool


def _events_from_otel(document: object, filename: str) -> list[Event]:
    raw_spans = list(_iter_raw_spans(document, filename))
    if not raw_spans:
        raise ParseError(f"{filename}: no GenAI spans found")
    grouped: dict[str, list[_RawSpan]] = {}
    for raw in raw_spans:
        grouped.setdefault(raw.trace_id, []).append(raw)
    events: list[Event] = []
    for group in grouped.values():
        concrete = [item for item in group if not item.wrapper]
        chosen = concrete if concrete else group
        events.extend(item.event for item in chosen)
    return events


def _iter_raw_spans(document: object, filename: str) -> Iterator[_RawSpan]:
    if isinstance(document, list):
        for index, span in enumerate(document, start=1):
            raw = _span_to_raw(span, {}, filename, index)
            if raw is not None:
                yield raw
        return
    if not isinstance(document, dict):
        raise ParseError(f"{filename}: OTel export must be a JSON object or span list")
    resource_spans = document.get("resourceSpans", document.get("resource_spans"))
    if isinstance(resource_spans, list):
        index = 0
        for resource_span in resource_spans:
            if not isinstance(resource_span, dict):
                continue
            resource_attributes = _decode_attributes(
                (resource_span.get("resource") or {}).get("attributes")
            )
            scopes = resource_span.get("scopeSpans", resource_span.get("scope_spans"))
            if scopes is None:
                scopes = resource_span.get("instrumentationLibrarySpans", [])
            for scope in scopes or []:
                if not isinstance(scope, dict):
                    continue
                for span in scope.get("spans") or []:
                    index += 1
                    raw = _span_to_raw(span, resource_attributes, filename, index)
                    if raw is not None:
                        yield raw
        return
    spans = document.get("spans")
    if isinstance(spans, list):
        for index, span in enumerate(spans, start=1):
            raw = _span_to_raw(span, {}, filename, index)
            if raw is not None:
                yield raw
        return
    raise ParseError(
        f"{filename}: unsupported OTel JSON (expected resourceSpans, spans, or a span list)"
    )


def _span_to_raw(
    span: object,
    resource_attributes: dict[str, Any],
    filename: str,
    index: int,
) -> _RawSpan | None:
    if not isinstance(span, dict):
        raise ParseError(f"{filename}: span {index} is not an object")
    attributes = _decode_attributes(span.get("attributes"))
    merged = {**resource_attributes, **attributes}
    if not any(key.startswith("gen_ai.") or key.startswith("agentcost.") for key in merged):
        return None
    operation = str(merged.get("gen_ai.operation.name") or "")
    model_value = merged.get("gen_ai.response.model") or merged.get("gen_ai.request.model")
    model = str(model_value).strip() if model_value else None
    if operation in _TOOL_OPS:
        kind = EventKind.TOOL
        if "gen_ai.request.model" not in merged and "gen_ai.response.model" not in merged:
            model = None
    else:
        kind = EventKind.LLM
    input_tokens = _usage_tokens(merged, "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")
    output_tokens = _usage_tokens(
        merged, "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens"
    )
    cache_read = _optional_usage(merged, "gen_ai.usage.cache_read.input_tokens")
    cache_write = _optional_usage(merged, "gen_ai.usage.cache_write.input_tokens")
    if cache_read or cache_write:
        if cache_read + cache_write > input_tokens:
            raise ParseError(
                f"{filename}: span {index}: gen_ai.usage.cache_read.input_tokens ({cache_read}) "
                f"and gen_ai.usage.cache_write.input_tokens ({cache_write}) exceed "
                f"gen_ai.usage.input_tokens ({input_tokens}). "
                "OpenTelemetry includes cache tokens in input tokens."
            )
        input_tokens -= cache_read + cache_write
    task_id = merged.get("agentcost.task_id") or merged.get("gen_ai.conversation.id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ParseError(
            f"{filename}: span {index} is missing agentcost.task_id "
            "(gen_ai.conversation.id is accepted as a fallback)"
        )
    variant_value = merged.get("agentcost.variant")
    variant = str(variant_value).strip() if variant_value else "default"
    if not variant:
        variant = "default"
    trace_id = str(span.get("traceId") or span.get("trace_id") or "")
    run_value = merged.get("agentcost.run_id")
    if isinstance(run_value, str) and run_value.strip():
        run_id = run_value.strip()
    elif trace_id:
        run_id = trace_id
    else:
        span_id = span.get("spanId") or span.get("span_id") or index
        run_id = str(span_id)
    group_id = trace_id or run_id
    return _RawSpan(
        event=Event(
            task_id=task_id.strip(),
            variant=variant,
            run_id=run_id,
            kind=kind,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or None,
            status=_span_status(span, merged),
            cache_read_tokens=cache_read,
            cache_write_5m_tokens=cache_write,
        ),
        trace_id=group_id,
        wrapper=operation in _WRAPPER_OPS,
    )


def _optional_usage(attributes: dict[str, Any], name: str) -> int:
    if name not in attributes:
        return 0
    return _non_negative_int(attributes[name], name)


def _usage_tokens(attributes: dict[str, Any], primary: str, legacy: str) -> int:
    if primary in attributes:
        return _non_negative_int(attributes[primary], primary)
    if legacy in attributes:
        return _non_negative_int(attributes[legacy], legacy)
    return 0


def _span_status(span: dict[str, Any], attributes: dict[str, Any]) -> EventStatus:
    error_type = attributes.get("error.type")
    if error_type not in (None, ""):
        return EventStatus.ERROR
    status = span.get("status")
    code = status.get("code") if isinstance(status, dict) else status
    if code in (2, "2", "ERROR", "STATUS_CODE_ERROR"):
        return EventStatus.ERROR
    return EventStatus.OK


def _decode_attributes(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        decoded: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict) or "key" not in item:
                raise ParseError("OTLP attribute is missing a key")
            decoded[str(item["key"])] = _decode_value(item.get("value"))
        return decoded
    raise ParseError("span attributes must be an object or an OTLP key/value list")


def _decode_value(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    return value
