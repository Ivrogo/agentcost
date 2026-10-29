"""Read local Claude Code and Codex CLI logs into agentcost events.

A session is one task. The trace keeps token counts, the model, and the
session id. Message text is not stored. Cost comes from the price table.
``costUSD`` on a Claude line is copied as ``logged_cost_usd`` and is not billed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agentcost.errors import ParseError
from agentcost.models import Event, EventKind, EventStatus
from agentcost.parse import _anthropic_usage, _non_negative_int


@dataclass(frozen=True, slots=True)
class ImportedEvent:
    """One imported call. ``logged_cost_usd`` is the log's figure, not the bill."""

    event: Event
    logged_cost_usd: int | float | None = None


def load_claude_code(
    path: str | Path | None = None,
    *,
    variant: str = "default",
    home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[ImportedEvent]:
    """Load Claude Code ``.jsonl`` sessions.

    Without ``path``, read ``~/.claude/projects/**/*.jsonl``. When
    ``CLAUDE_CONFIG_DIR`` is set it replaces that directory: comma-separated
    config directories that contain ``projects/``, or a ``projects/`` directory
    itself. An explicit file or directory is the only tree that is read.
    """
    label = _variant(variant)
    files = _claude_files(path, _home(home), _environ(environ))
    if not files:
        raise ParseError(f"no Claude Code usage files in {_looked_at(path, 'Claude Code')}")
    hits: list[_ClaudeHit] = []
    index: dict[tuple[object, ...], int] = {}
    unique = 0
    for file in files:
        for hit in _claude_file(file, label):
            unique += 1
            key = hit.key if hit.key is not None else ("row", unique)
            current = index.get(key)
            if current is None:
                index[key] = len(hits)
                hits.append(hit)
                continue
            if hit.weight > hits[current].weight:
                hits[current] = hit
    items = [hit.item for hit in hits]
    if not items:
        raise ParseError(f"no Claude Code assistant usage in {files[0]}")
    return items


def load_codex_cli(
    path: str | Path | None = None,
    *,
    variant: str = "default",
    home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[ImportedEvent]:
    """Load Codex CLI rollouts.

    Without ``path``, read ``~/.codex/sessions/**/rollout-*.jsonl``. ``CODEX_HOME``
    replaces that home and may be a comma-separated list. ``cached_input_tokens``
    is inside ``input_tokens`` and is subtracted. ``total_token_usage`` is
    cumulative: when it advances, ``last_token_usage`` is the turn; otherwise
    the delta is the difference of totals. A repeated snapshot adds nothing.
    ``reasoning_output_tokens`` is already inside ``output_tokens``.
    """
    label = _variant(variant)
    files = _codex_files(path, _home(home), _environ(environ))
    if not files:
        raise ParseError(f"no Codex rollout files in {_looked_at(path, 'Codex')}")
    items: list[ImportedEvent] = []
    for file in files:
        items.extend(_codex_file(file, label))
    if not items:
        raise ParseError(f"no Codex token usage in {files[0]}")
    return items


def render_imported_jsonl(items: Sequence[ImportedEvent]) -> str:
    """Canonical JSONL. ``logged_cost_usd`` is extra and is not a price."""
    lines = [json.dumps(_payload(item), ensure_ascii=False) for item in items]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class _ClaudeHit:
    item: ImportedEvent
    weight: int
    key: tuple[object, ...] | None


def _claude_file(path: Path, variant: str) -> Iterator[_ClaudeHit]:
    for line_number, line in _lines(path):
        if '"usage"' not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("type") != "assistant":
            continue
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            continue
        try:
            hit = _claude_hit(path, line_number, payload, message, variant)
        except _SkipLine:
            continue
        if hit is not None:
            yield hit


def _claude_hit(
    path: Path,
    line_number: int,
    payload: dict,
    message: dict,
    variant: str,
) -> _ClaudeHit | None:
    session_id = _optional_text(payload, "sessionId")
    request_id = _optional_text(payload, "requestId")
    message_id = _optional_text(message, "id")
    model = _optional_text(message, "model")
    if session_id is None:
        session_id = path.stem
    timestamp = payload.get("timestamp")
    stamp = timestamp if isinstance(timestamp, str) else ""
    try:
        input_tokens, output_tokens, cache_read, write_5m, write_1h = _anthropic_usage(
            message["usage"]
        )
    except ParseError as exc:
        raise ParseError(f"{path}: line {line_number}: {exc}") from exc
    status = EventStatus.ERROR if payload.get("isApiErrorMessage") is True else EventStatus.OK
    event = Event(
        task_id=session_id,
        variant=variant,
        run_id=session_id,
        kind=EventKind.LLM,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        status=status,
        cache_read_tokens=cache_read,
        cache_write_5m_tokens=write_5m,
        cache_write_1h_tokens=write_1h,
    )
    weight = input_tokens + output_tokens + cache_read + write_5m + write_1h
    return _ClaudeHit(
        item=ImportedEvent(event=event, logged_cost_usd=_logged_cost(payload)),
        weight=weight,
        key=_claude_key(message_id, request_id, session_id, stamp),
    )


def _claude_key(
    message_id: str | None,
    request_id: str | None,
    session_id: str,
    timestamp: str,
) -> tuple[object, ...] | None:
    """Same rule as ccusage ``usage_dedupe_hash`` for an exact match.

    A request id identifies one response across sessions. Without one, ``msg_``
    and ``resp_`` ids collapse inside the session across timestamps; other ids
    also keep the timestamp. Sidechain replays that change the request id are
    not folded together.
    """
    if message_id is None:
        return None
    if request_id is not None:
        return ("req", message_id, request_id)
    if message_id.startswith("msg_") or message_id.startswith("resp_"):
        return ("id", session_id, message_id)
    return ("ts", session_id, message_id, timestamp)


@dataclass(frozen=True, slots=True)
class _Snap:
    input_tokens: int
    cached: int
    output_tokens: int
    reasoning: int
    cache_write: int


def _codex_file(path: Path, variant: str) -> list[ImportedEvent]:
    session_id = _codex_session_id(path)
    current_model: str | None = None
    previous: _Snap | None = None
    items: list[ImportedEvent] = []
    for line_number, line in _lines(path):
        if (
            '"turn_context"' not in line
            and '"token_count"' not in line
            and '"session_meta"' not in line
        ):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        kind = payload.get("type")
        body = payload.get("payload")
        if not isinstance(body, dict):
            continue
        if kind == "turn_context":
            model = _model_name(body)
            if model is not None:
                current_model = model
            continue
        if kind != "event_msg" or body.get("type") != "token_count":
            continue
        info = body.get("info")
        info = info if isinstance(info, dict) else {}
        where = f"{path}: line {line_number}"
        try:
            delta, previous = _codex_delta(info, previous, where)
        except ParseError as exc:
            raise ParseError(f"{where}: {exc}") from exc
        if delta is None:
            continue
        if delta.cache_write:
            raise ParseError(
                f"{where}: Codex cache_write_input_tokens is not priced in this version. "
                "input_tokens already includes those writes, so ignoring the field would "
                "bill them as ordinary input."
            )
        model = _model_name(body) or _model_name(info) or current_model
        if model is not None:
            current_model = model
        items.append(
            ImportedEvent(
                event=Event(
                    task_id=session_id,
                    variant=variant,
                    run_id=session_id,
                    kind=EventKind.LLM,
                    input_tokens=delta.input_tokens - delta.cached,
                    output_tokens=delta.output_tokens,
                    model=model,
                    status=EventStatus.OK,
                    cache_read_tokens=delta.cached,
                )
            )
        )
    return items


def _codex_session_id(path: Path) -> str:
    for _line_number, line in _lines(path):
        if '"session_meta"' not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("type") != "session_meta":
            continue
        body = payload.get("payload")
        if not isinstance(body, dict):
            continue
        session_id = body.get("id")
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()
    return path.stem


def _codex_delta(
    info: dict,
    previous: _Snap | None,
    where: str,
) -> tuple[_Snap | None, _Snap | None]:
    """Prefer ``last_token_usage`` when the cumulative total moved.

    ccusage ``codex_token_count_usage``: a total that is missing counts as
    advanced, so ``last_token_usage`` is the turn. A total equal to the previous
    snapshot drops ``last_token_usage`` and the subtraction is zero. Without
    ``last_token_usage``, the turn is the saturating difference of totals.
    """
    total = _optional_snap(info.get("total_token_usage"), f"{where} total_token_usage")
    last = _optional_snap(info.get("last_token_usage"), f"{where} last_token_usage")
    advanced = total is None or previous is None or total != previous
    if last is not None and advanced:
        delta: _Snap | None = last
    elif total is not None:
        delta = _normalize(_subtract(total, previous))
    else:
        delta = None
    if total is not None:
        previous = total
    if delta is None or _snap_is_empty(delta):
        return None, previous
    return delta, previous


def _optional_snap(value: object, where: str) -> _Snap | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ParseError(f"{where} must be an object")
    return _snap(value, where)


def _snap(raw: dict, where: str) -> _Snap:
    gross = _first_int(raw, ("input_tokens", "prompt_tokens", "input"), where)
    output = _first_int(raw, ("output_tokens", "completion_tokens", "output"), where)
    reasoning = _first_int(raw, ("reasoning_output_tokens", "reasoning_tokens"), where)
    cached = min(
        _first_int(raw, ("cached_input_tokens", "cache_read_input_tokens", "cached_tokens"), where),
        gross,
    )
    write = min(
        _first_int(raw, ("cache_write_input_tokens", "cache_creation_input_tokens"), where),
        gross - cached,
    )
    return _Snap(gross, cached, output, reasoning, write)


def _first_int(raw: dict, names: tuple[str, ...], where: str) -> int:
    for name in names:
        if name in raw and raw[name] is not None:
            return _non_negative_int(raw[name], f"{where} {name}")
    return 0


def _snap_is_empty(snap: _Snap) -> bool:
    return snap.input_tokens == 0 and snap.cached == 0 and snap.output_tokens == 0


def _subtract(current: _Snap, previous: _Snap | None) -> _Snap:
    if previous is None:
        return current

    def sat(left: int, right: int) -> int:
        return left - right if left >= right else 0

    return _Snap(
        sat(current.input_tokens, previous.input_tokens),
        sat(current.cached, previous.cached),
        sat(current.output_tokens, previous.output_tokens),
        sat(current.reasoning, previous.reasoning),
        sat(current.cache_write, previous.cache_write),
    )


def _normalize(snap: _Snap) -> _Snap:
    cached = min(snap.cached, snap.input_tokens)
    write = min(snap.cache_write, snap.input_tokens - cached)
    return _Snap(snap.input_tokens, cached, snap.output_tokens, snap.reasoning, write)


def _model_name(container: dict) -> str | None:
    for key in ("model", "model_name"):
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = container.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload(item: ImportedEvent) -> dict[str, object]:
    event = item.event
    payload: dict[str, object] = {
        "task_id": event.task_id,
        "variant": event.variant,
        "run_id": event.run_id,
        "kind": event.kind.value,
        "tokens": {
            "input": event.input_tokens,
            "output": event.output_tokens,
            "cache_read": event.cache_read_tokens,
            "cache_write_5m": event.cache_write_5m_tokens,
            "cache_write_1h": event.cache_write_1h_tokens,
        },
        "model": event.model,
        "status": event.status.value,
    }
    if item.logged_cost_usd is not None:
        payload["logged_cost_usd"] = item.logged_cost_usd
    return payload


def _logged_cost(payload: dict) -> int | float | None:
    if "costUSD" not in payload:
        return None
    value = payload["costUSD"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


class _SkipLine(Exception):
    """A usage line failed the same non-empty-id checks ccusage uses."""


def _optional_text(container: dict, field: str) -> str | None:
    if field not in container or container[field] is None:
        return None
    value = container[field]
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise _SkipLine


def _variant(variant: str) -> str:
    if not isinstance(variant, str) or not variant.strip():
        raise ParseError("variant must be a non-empty string")
    return variant.strip()


def _home(home: str | Path | None) -> Path:
    return Path.home() if home is None else Path(home)


def _environ(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _looked_at(path: str | Path | None, kind: str) -> str:
    if path is not None:
        return str(path)
    return f"the default {kind} directory"


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if line.strip():
                    yield number, line
    except OSError as exc:
        raise ParseError(f"cannot read {path}: {exc}") from exc
    except UnicodeError as exc:
        raise ParseError(f"cannot read {path}: {exc}") from exc


def _claude_files(
    path: str | Path | None,
    home: Path,
    environ: Mapping[str, str],
) -> list[Path]:
    if path is not None:
        target = Path(path).expanduser()
        if target.is_file():
            return [target.resolve()]
        if not target.is_dir():
            raise ParseError(f"cannot read {target}: not a file or directory")
        projects = target / "projects"
        root = projects if projects.is_dir() else target
        return _contained(root, "*.jsonl")
    files: list[Path] = []
    for root in _claude_roots(home, environ):
        files.extend(_contained(root / "projects", "*.jsonl"))
    return _unique(files)


def _claude_roots(home: Path, environ: Mapping[str, str]) -> list[Path]:
    raw = environ.get("CLAUDE_CONFIG_DIR")
    if raw is None or not str(raw).strip():
        return [home / ".claude"]
    roots: list[Path] = []
    seen: set[str] = set()
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        candidate = Path(part).expanduser()
        if candidate.name == "projects" and candidate.is_dir():
            parent = candidate.parent
            if (parent / "projects").is_dir():
                candidate = parent
        if (candidate / "projects").is_dir():
            key = str(candidate.resolve())
            if key not in seen:
                seen.add(key)
                roots.append(candidate)
    if not roots:
        raise ParseError(
            "No valid Claude data directories found in CLAUDE_CONFIG_DIR. "
            "Expected each path to be a Claude config directory containing 'projects/', "
            f"or the 'projects/' directory itself: {raw}"
        )
    return roots


def _codex_files(
    path: str | Path | None,
    home: Path,
    environ: Mapping[str, str],
) -> list[Path]:
    if path is not None:
        target = Path(path).expanduser()
        if target.is_file():
            return [target.resolve()]
        if not target.is_dir():
            raise ParseError(f"cannot read {target}: not a file or directory")
        sessions = target / "sessions"
        root = sessions if sessions.is_dir() else target
        return _contained(root, "rollout-*.jsonl")
    files: list[Path] = []
    for root in _codex_homes(home, environ):
        files.extend(_contained(root / "sessions", "rollout-*.jsonl"))
    return _unique(files)


def _codex_homes(home: Path, environ: Mapping[str, str]) -> list[Path]:
    raw = environ.get("CODEX_HOME")
    if raw is None or not str(raw).strip():
        return [home / ".codex"]
    homes: list[Path] = []
    seen: set[str] = set()
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        candidate = Path(part).expanduser()
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            homes.append(candidate)
    if not homes:
        raise ParseError(f"CODEX_HOME has no paths: {raw}")
    return homes


def _contained(root: Path, pattern: str) -> list[Path]:
    if not root.is_dir():
        return []
    base = root.resolve()
    found: list[Path] = []
    for candidate in base.rglob(pattern):
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_relative_to(base):
            found.append(resolved)
    found.sort()
    return found


def _unique(files: Sequence[Path]) -> list[Path]:
    chosen: list[Path] = []
    seen: set[str] = set()
    for file in files:
        key = str(file)
        if key not in seen:
            seen.add(key)
            chosen.append(file)
    return chosen
