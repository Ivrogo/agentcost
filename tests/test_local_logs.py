"""Claude Code and Codex CLI logs become one agentcost task per session."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentcost import PriceError, PriceTable, compare, load_traces, parse_jsonl
from agentcost.cli import app
from agentcost.errors import ParseError
from agentcost.local_logs import load_claude_code, load_codex_cli, render_imported_jsonl

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLAUDE = FIXTURES / "claude-code"
CODEX = FIXTURES / "codex"
PROMPT = "SYNTHETIC_PROMPT_DO_NOT_KEEP"


def _assistant(
    usage: dict,
    *,
    session_id: str = "sess-1",
    request_id: str | None = "req-1",
    message_id: str | None = "msg_1",
    model: str | None = "claude-sonnet-4",
    timestamp: str = "2026-01-01T00:00:00.000Z",
    content: str | None = None,
    cost_usd: float | None = None,
    include_cost: bool = False,
) -> str:
    message: dict = {"usage": usage}
    if message_id is not None:
        message["id"] = message_id
    if model is not None:
        message["model"] = model
    if content is not None:
        message["content"] = [{"type": "text", "text": content}]
    payload: dict = {
        "type": "assistant",
        "timestamp": timestamp,
        "sessionId": session_id,
        "message": message,
    }
    if request_id is not None:
        payload["requestId"] = request_id
    if include_cost:
        payload["costUSD"] = cost_usd
    return json.dumps(payload)


def _write(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _parts(event) -> tuple[int, int, int]:
    return event.input_tokens, event.cache_read_tokens, event.output_tokens


def _sums(items, model: str) -> dict[str, int | float]:
    selected = [item for item in items if item.event.model == model]
    events = [item.event for item in selected]
    return {
        "input_tokens": sum(event.input_tokens for event in events),
        "output_tokens": sum(event.output_tokens for event in events),
        "cache_creation_input_tokens": sum(
            event.cache_write_5m_tokens + event.cache_write_1h_tokens for event in events
        ),
        "cache_read_input_tokens": sum(event.cache_read_tokens for event in events),
        "ephemeral_1h_input_tokens": sum(event.cache_write_1h_tokens for event in events),
        "ephemeral_5m_input_tokens": sum(event.cache_write_5m_tokens for event in events),
        "costUSD": sum(item.logged_cost_usd or 0 for item in selected),
    }


def test_claude_fixtures_match_deduped_totals() -> None:
    items = load_claude_code(CLAUDE, variant="A", environ={})
    expected = json.loads((CLAUDE / "totales.json").read_text(encoding="utf-8"))
    sonnet = expected["claude-session-a"]["totales"]["claude-sonnet-5"]
    fable = expected["claude-session-b"]["totales"]["claude-fable-5"]
    assert _sums(items, "claude-sonnet-5") == sonnet
    assert _sums(items, "claude-fable-5") == fable
    assert len(items) == 3
    assert all(item.logged_cost_usd is None for item in items)
    by_task: dict[str, list] = {}
    for item in items:
        by_task.setdefault(item.event.task_id, []).append(item)
    assert set(by_task) == {
        "7476d544-4b62-5749-99de-aed6aa276c03",
        "f78039ce-cc5e-5037-97d8-f2bb8972ce7c",
    }
    sonnet = by_task["7476d544-4b62-5749-99de-aed6aa276c03"]
    assert len(sonnet) == 1
    assert sonnet[0].event.run_id == sonnet[0].event.task_id
    assert sonnet[0].event.input_tokens == 15396
    rendered = render_imported_jsonl(items)
    assert "msg_3bbaa0b1c6edefe4716f098b" not in rendered
    assert "req_1369dce5effa601eb809fb7e" not in rendered
    events = parse_jsonl(rendered)
    assert [(event.input_tokens, event.cache_write_1h_tokens) for event in events] == [
        (15396, 16485),
        (15319, 14132),
        (395, 19029),
    ]


def test_claude_dedupes_same_message_and_request_across_sessions(tmp_path: Path) -> None:
    usage = {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 3}
    first = tmp_path / "a.jsonl"
    second = tmp_path / "b.jsonl"
    _write(
        first,
        [
            _assistant(
                usage,
                session_id="sess-a",
                request_id="req-shared",
                message_id="msg_shared",
            ),
            _assistant(
                usage,
                session_id="sess-a",
                request_id="req-shared",
                message_id="msg_shared",
                timestamp="2026-01-01T00:00:05.000Z",
            ),
        ],
    )
    _write(
        second,
        [
            _assistant(
                {**usage, "output_tokens": 9},
                session_id="sess-b",
                request_id="req-shared",
                message_id="msg_shared",
            ),
            _assistant(usage, session_id="sess-b", request_id="req-other", message_id="msg_other"),
        ],
    )
    items = load_claude_code(tmp_path, variant="A", environ={})
    assert len(items) == 2
    kept = [
        item for item in items if item.event.task_id == "sess-b" and item.event.output_tokens == 9
    ]
    assert len(kept) == 1
    assert any(item.event.task_id == "sess-b" and item.event.output_tokens == 4 for item in items)


def test_claude_requestless_message_ids_follow_ccusage(tmp_path: Path) -> None:
    usage = {"input_tokens": 2, "output_tokens": 1}
    path = tmp_path / "s.jsonl"
    _write(
        path,
        [
            _assistant(
                usage, request_id=None, message_id="msg_block", timestamp="2026-01-01T00:00:01Z"
            ),
            _assistant(
                usage, request_id=None, message_id="msg_block", timestamp="2026-01-01T00:00:02Z"
            ),
            _assistant(
                usage, request_id=None, message_id="gateway-1", timestamp="2026-01-01T00:00:01Z"
            ),
            _assistant(
                usage, request_id=None, message_id="gateway-1", timestamp="2026-01-01T00:00:02Z"
            ),
        ],
    )
    other = tmp_path / "other.jsonl"
    _write(
        other,
        [_assistant(usage, session_id="sess-2", request_id=None, message_id="msg_block")],
    )
    items = load_claude_code(tmp_path, variant="A", environ={})
    assert len(items) == 4


def test_claude_maps_cache_split_and_keeps_logged_cost_beside_the_table(tmp_path: Path) -> None:
    split = {
        "input_tokens": 10,
        "output_tokens": 4,
        "cache_read_input_tokens": 3,
        "cache_creation_input_tokens": 9,
        "cache_creation": {"ephemeral_5m_input_tokens": 4, "ephemeral_1h_input_tokens": 5},
    }
    total_only = {
        "input_tokens": 10,
        "output_tokens": 4,
        "cache_read_input_tokens": 3,
        "cache_creation_input_tokens": 7,
    }
    path = tmp_path / "one.jsonl"
    _write(
        path,
        [
            _assistant(
                split,
                message_id="msg_split",
                request_id="req-split",
                content=PROMPT,
                cost_usd=9.99,
                include_cost=True,
            ),
            _assistant(total_only, message_id="msg_total", request_id="req-total"),
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "sess-1",
                    "message": {"role": "user", "content": PROMPT},
                }
            ),
        ],
    )
    items = load_claude_code(path, variant="lab", environ={})
    assert len(items) == 2
    split_event, total_event = items
    assert split_event.event.variant == "lab"
    assert split_event.event.task_id == "sess-1"
    assert split_event.event.cache_read_tokens == 3
    assert split_event.event.cache_write_5m_tokens == 4
    assert split_event.event.cache_write_1h_tokens == 5
    assert split_event.event.input_tokens == 10
    assert split_event.logged_cost_usd == 9.99
    assert total_event.event.cache_write_5m_tokens == 7
    assert total_event.event.cache_write_1h_tokens == 0
    rendered = render_imported_jsonl(items)
    assert PROMPT not in rendered
    assert "logged_cost_usd" in rendered
    trace = tmp_path / "trace.jsonl"
    trace.write_text(rendered, encoding="utf-8")
    loaded = load_traces(trace)
    assert loaded[0].input_tokens == 10
    assert loaded[0].cache_write_5m_tokens == 4
    priced = compare(
        [item.event for item in items if item.event.output_tokens == 4][:1]
        + _priced_partner(tmp_path),
        ("lab", "other"),
        prices=PriceTable.bundled(),
    )
    assert priced.arm("lab").total_cost != Decimal("9.99")
    assert priced.arm("lab").cache_write_5m_cost > 0
    assert priced.arm("lab").cache_write_1h_cost > 0


def _priced_partner(tmp_path: Path) -> list:
    usage = {"input_tokens": 1, "output_tokens": 1}
    path = tmp_path / "partner.jsonl"
    _write(
        path,
        [_assistant(usage, session_id="other-sess", request_id="req-p", message_id="msg_p")],
    )
    return [item.event for item in load_claude_code(path, variant="other", environ={})]


def test_claude_cache_split_must_match_the_creation_total(tmp_path: Path) -> None:
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_creation_input_tokens": 10,
        "cache_creation": {"ephemeral_5m_input_tokens": 1, "ephemeral_1h_input_tokens": 1},
    }
    path = _write(tmp_path / "bad.jsonl", [_assistant(usage)])
    with pytest.raises(ParseError, match="ephemeral_5m_input_tokens"):
        load_claude_code(path, variant="A", environ={})


def test_claude_default_directory_and_config_dir_do_not_escape(tmp_path: Path) -> None:
    usage = {"input_tokens": 8, "output_tokens": 1}
    home = tmp_path / "home"
    home_file = home / ".claude" / "projects" / "proj" / "home-sess.jsonl"
    _write(
        home_file,
        [_assistant(usage, session_id="from-home", request_id="req-home", message_id="msg_home")],
    )
    skipped = home / ".claude" / "not-projects" / "skip.jsonl"
    _write(
        skipped,
        [
            _assistant(
                {"input_tokens": 99, "output_tokens": 99},
                session_id="skipped",
                message_id="msg_skip",
            )
        ],
    )
    found = load_claude_code(home=home, environ={})
    assert [item.event.task_id for item in found] == ["from-home"]

    cfg = tmp_path / "cfg"
    _write(
        cfg / "projects" / "demo" / "cfg-sess.jsonl",
        [_assistant(usage, session_id="from-cfg", request_id="req-cfg", message_id="msg_cfg")],
    )
    via_env = load_claude_code(home=home, environ={"CLAUDE_CONFIG_DIR": str(cfg)})
    assert [item.event.task_id for item in via_env] == ["from-cfg"]

    projects = tmp_path / "custom" / "projects"
    _write(
        projects / "nested" / "p.jsonl",
        [
            _assistant(
                usage,
                session_id="from-projects",
                request_id="req-p",
                message_id="msg_projects",
            )
        ],
    )
    via_projects = load_claude_code(
        home=home,
        environ={"CLAUDE_CONFIG_DIR": str(projects)},
    )
    assert [item.event.task_id for item in via_projects] == ["from-projects"]

    with pytest.raises(ParseError, match="CLAUDE_CONFIG_DIR"):
        load_claude_code(home=home, environ={"CLAUDE_CONFIG_DIR": str(tmp_path / "missing")})

    explicit = load_claude_code(
        home_file,
        variant="A",
        home=home,
        environ={"CLAUDE_CONFIG_DIR": str(cfg)},
    )
    assert [item.event.task_id for item in explicit] == ["from-home"]

    outside = tmp_path / "outside.jsonl"
    _write(
        outside,
        [
            _assistant(
                {"input_tokens": 70, "output_tokens": 70},
                session_id="outside",
                message_id="msg_out",
            )
        ],
    )
    link_dir = home / ".claude" / "projects" / "proj"
    link = link_dir / "escape.jsonl"
    link.symlink_to(outside)
    linked = load_claude_code(home=home, environ={})
    assert [item.event.task_id for item in linked] == ["from-home"]
    assert all(item.event.input_tokens != 70 for item in linked)


def test_codex_fixture_subtracts_cache_and_does_not_replay_the_snapshot() -> None:
    items = load_codex_cli(CODEX / "rollout-synthetic-a.jsonl", variant="A", environ={})
    assert len(items) == 2
    first, second = items
    assert first.event.task_id == "synthetic-codex-session-a"
    assert first.event.run_id == first.event.task_id
    assert first.event.model == "gpt-4o-mini"
    assert _parts(first.event) == (600, 400, 100)
    assert _parts(second.event) == (0, 500, 80)
    assert first.event.cache_write_5m_tokens == 0
    rendered = render_imported_jsonl(items)
    assert PROMPT not in rendered
    events = [item.event for item in items]
    partner = load_codex_cli(CODEX / "rollout-synthetic-b.jsonl", variant="B", environ={})
    assert partner[0].event.model == "gpt-4o"
    assert (partner[0].event.input_tokens, partner[0].event.cache_read_tokens) == (500, 1500)
    report = compare(events + [item.event for item in partner], ("A", "B"))
    assert report.arm("A").total_cost == Decimal("0.0002655")
    assert report.arm("B").total_cost == Decimal("0.004125")
    assert report.arm("A").tokens.median == Decimal(1680)


def test_codex_prefers_last_usage_and_subtracts_totals(tmp_path: Path) -> None:
    path = tmp_path / "rollout-case.jsonl"
    _write(
        path,
        [
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {"id": "synthetic-delta", "synthetic": True},
                }
            ),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            json.dumps(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 0,
                                "output_tokens": 10,
                                "reasoning_output_tokens": 1,
                            },
                            "last_token_usage": {
                                "input_tokens": 80,
                                "cached_input_tokens": 10,
                                "output_tokens": 5,
                                "reasoning_output_tokens": 4,
                            },
                        },
                    },
                }
            ),
        ],
    )
    only = load_codex_cli(path, variant="A", environ={})
    assert _parts(only[0].event) == (70, 10, 5)

    totals = tmp_path / "rollout-totals.jsonl"
    _write(
        totals,
        [
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            _token_count(
                total={"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}
            ),
            _token_count(
                total={"input_tokens": 130, "cached_input_tokens": 40, "output_tokens": 25}
            ),
        ],
    )
    deltas = load_codex_cli(totals, variant="A", environ={})
    assert len(deltas) == 2
    assert deltas[0].event.task_id == "rollout-totals"
    assert _parts(deltas[0].event) == (80, 20, 10)
    assert _parts(deltas[1].event) == (10, 20, 15)


def _token_count(*, total: dict, last: dict | None = None) -> str:
    info: dict = {"total_token_usage": total}
    if last is not None:
        info["last_token_usage"] = last
    return json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": info}})


def test_codex_does_not_invent_a_model_and_rejects_cache_writes(tmp_path: Path) -> None:
    missing = tmp_path / "rollout-no-model.jsonl"
    _write(
        missing,
        [
            _token_count(
                total={"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 1},
                last={"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 1},
            )
        ],
    )
    items = load_codex_cli(missing, variant="A", environ={})
    assert items[0].event.model is None
    rendered = render_imported_jsonl(items)
    assert "gpt-5" not in rendered

    writes = tmp_path / "rollout-write.jsonl"
    _write(
        writes,
        [
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            _token_count(
                total={
                    "input_tokens": 100,
                    "cached_input_tokens": 20,
                    "cache_write_input_tokens": 10,
                    "output_tokens": 5,
                },
                last={
                    "input_tokens": 100,
                    "cached_input_tokens": 20,
                    "cache_write_input_tokens": 10,
                    "output_tokens": 5,
                },
            ),
        ],
    )
    with pytest.raises(ParseError, match="cache_write_input_tokens"):
        load_codex_cli(writes, variant="A", environ={})


def test_codex_default_directory_and_codex_home(tmp_path: Path) -> None:
    usage_line = _token_count(
        total={"input_tokens": 12, "cached_input_tokens": 2, "output_tokens": 3},
        last={"input_tokens": 12, "cached_input_tokens": 2, "output_tokens": 3},
    )
    home = tmp_path / "home"
    rollout = home / ".codex" / "sessions" / "2026" / "01" / "01" / "rollout-home.jsonl"
    _write(
        rollout,
        [
            json.dumps({"type": "session_meta", "payload": {"id": "from-home"}}),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            usage_line,
        ],
    )
    _write(home / ".codex" / "sessions" / "notes.jsonl", [usage_line])
    _write(home / ".codex" / "archived_sessions" / "rollout-archived.jsonl", [usage_line])
    found = load_codex_cli(home=home, environ={})
    assert [item.event.task_id for item in found] == ["from-home"]

    other = tmp_path / "other-home"
    _write(
        other / "sessions" / "rollout-env.jsonl",
        [
            json.dumps({"type": "session_meta", "payload": {"id": "from-env"}}),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            usage_line,
        ],
    )
    via_env = load_codex_cli(home=home, environ={"CODEX_HOME": str(other)})
    assert [item.event.task_id for item in via_env] == ["from-env"]

    loose = tmp_path / "loose-session.jsonl"
    _write(
        loose,
        [
            json.dumps({"type": "session_meta", "payload": {"id": "loose-file"}}),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            usage_line,
        ],
    )
    explicit = load_codex_cli(loose, variant="A", home=home, environ={"CODEX_HOME": str(other)})
    assert [item.event.task_id for item in explicit] == ["loose-file"]


def test_unpriced_claude_models_are_named() -> None:
    sonnet = load_claude_code(CLAUDE / "claude-session-a.jsonl", variant="A", environ={})
    fable = load_claude_code(CLAUDE / "claude-session-b.jsonl", variant="B", environ={})
    events = [item.event for item in sonnet + fable]
    with pytest.raises(PriceError, match="claude-fable-5"):
        compare(events, ("A", "B"))
    report = compare(events, ("A", "B"), on_missing="zero")
    assert report.arm("A").unpriced_models == ("claude-sonnet-5",)
    assert report.arm("B").unpriced_models == ("claude-fable-5",)
    assert report.arm("A").total_cost == 0
    assert report.arm("A").tokens.median == Decimal(58358)
    assert report.arm("B").tokens.median == Decimal(113674)


def test_cli_imports_fixtures_and_reports_them(tmp_path: Path) -> None:
    claude_a = tmp_path / "claude-a.jsonl"
    claude_b = tmp_path / "claude-b.jsonl"
    imported_a = runner.invoke(
        app,
        [
            "import",
            "claude-code",
            str(CLAUDE / "claude-session-a.jsonl"),
            "--variant",
            "A",
            "--output",
            str(claude_a),
        ],
    )
    imported_b = runner.invoke(
        app,
        [
            "import",
            "claude-code",
            str(CLAUDE / "claude-session-b.jsonl"),
            "--variant",
            "B",
            "--output",
            str(claude_b),
        ],
    )
    assert imported_a.exit_code == 0, imported_a.output
    assert imported_b.exit_code == 0, imported_b.output
    combined = tmp_path / "claude.jsonl"
    combined.write_text(
        claude_a.read_text(encoding="utf-8") + claude_b.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    refused = runner.invoke(app, ["report", str(combined), "--compare", "A", "B"])
    assert refused.exit_code == 1
    assert "claude-sonnet-5" in refused.stderr
    assert "claude-fable-5" in refused.stderr
    warned = runner.invoke(
        app,
        ["report", str(combined), "--compare", "A", "B", "--allow-unpriced"],
    )
    assert warned.exit_code == 0, warned.output
    assert "Unpriced models treated as zero cost" in warned.stdout
    assert "`claude-sonnet-5`" in warned.stdout
    assert "`claude-fable-5`" in warned.stdout

    codex_a = tmp_path / "codex-a.jsonl"
    codex_b = tmp_path / "codex-b.jsonl"
    assert (
        runner.invoke(
            app,
            [
                "import",
                "codex",
                str(CODEX / "rollout-synthetic-a.jsonl"),
                "--variant",
                "A",
                "--output",
                str(codex_a),
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "import",
                "codex",
                str(CODEX / "rollout-synthetic-b.jsonl"),
                "--variant",
                "B",
                "--output",
                str(codex_b),
            ],
        ).exit_code
        == 0
    )
    codex = tmp_path / "codex.jsonl"
    codex.write_text(
        codex_a.read_text(encoding="utf-8") + codex_b.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert PROMPT not in codex.read_text(encoding="utf-8")
    reported = runner.invoke(
        app,
        ["report", str(codex), "--compare", "A", "B", "--format", "json"],
    )
    assert reported.exit_code == 0, reported.output
    payload = json.loads(reported.stdout)
    assert payload["arms"]["A"]["total_cost"] == 0.0002655
    assert payload["arms"]["B"]["total_cost"] == 0.004125
    assert payload["arms"]["A"]["unpriced_models"] == []
    assert payload["pairing"]["mode"] == "unpaired"
    assert "No shared task_id" in reported.stderr


def test_imported_session_pairs_by_task_id(tmp_path: Path) -> None:
    shared = "shared-task"
    left = tmp_path / "rollout-left.jsonl"
    right = tmp_path / "rollout-right.jsonl"
    _write(
        left,
        [
            json.dumps({"type": "session_meta", "payload": {"id": shared, "synthetic": True}}),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            _token_count(
                total={"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0},
                last={"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 0},
            ),
        ],
    )
    _write(
        right,
        [
            json.dumps({"type": "session_meta", "payload": {"id": shared, "synthetic": True}}),
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-4o-mini"}}),
            _token_count(
                total={"input_tokens": 3_000_000, "cached_input_tokens": 0, "output_tokens": 0},
                last={"input_tokens": 3_000_000, "cached_input_tokens": 0, "output_tokens": 0},
            ),
        ],
    )
    out_a = tmp_path / "a.jsonl"
    out_b = tmp_path / "b.jsonl"
    assert (
        runner.invoke(
            app,
            ["import", "codex", str(left), "--variant", "A", "--output", str(out_a)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["import", "codex", str(right), "--variant", "B", "--output", str(out_b)],
        ).exit_code
        == 0
    )
    combined = tmp_path / "both.jsonl"
    combined.write_text(
        out_a.read_text(encoding="utf-8") + out_b.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["report", str(combined), "--compare", "A", "B", "--paired", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["pairing"]["mode"] == "paired"
    assert payload["pairing"]["pairs"] == 1
    assert payload["pairing"]["metrics"]["cost"]["mean_difference"] == -0.3
    assert payload["verdict"] == "inconclusive"
    assert shared in combined.read_text(encoding="utf-8")

    session_a = tmp_path / "session-a.jsonl"
    session_b = tmp_path / "session-b.jsonl"
    assert (
        runner.invoke(
            app,
            [
                "import",
                "claude-code",
                str(CLAUDE / "claude-session-a.jsonl"),
                "--variant",
                "A",
                "--output",
                str(session_a),
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "import",
                "claude-code",
                str(CLAUDE / "claude-session-b.jsonl"),
                "--variant",
                "B",
                "--output",
                str(session_b),
            ],
        ).exit_code
        == 0
    )
    unpaired_ids = tmp_path / "two-sessions.jsonl"
    unpaired_ids.write_text(
        session_a.read_text(encoding="utf-8") + session_b.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    refused = runner.invoke(
        app,
        [
            "report",
            str(unpaired_ids),
            "--compare",
            "A",
            "B",
            "--paired",
            "--allow-unpriced",
        ],
    )
    assert refused.exit_code == 1
    assert "No shared task_id" in refused.stderr
