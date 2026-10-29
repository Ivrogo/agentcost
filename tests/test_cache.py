"""Cache token accounting. Counts come from documented API payloads, not live calls."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from agentcost import (
    Event,
    EventKind,
    EventStatus,
    ModelPrice,
    ParseError,
    PriceError,
    PriceTable,
    compare,
    load_traces,
    parse_jsonl,
    parse_otel,
    render_json,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
MILLION = Decimal(1_000_000)

# OpenAI, "Prompt Caching in the API" (1 Oct 2024):
# prompt_tokens 2006 includes cached_tokens 1920; completion_tokens 300; total 2306.
OPENAI_USAGE = {
    "prompt_tokens": 2006,
    "completion_tokens": 300,
    "total_tokens": 2306,
    "prompt_tokens_details": {"cached_tokens": 1920},
}

# Anthropic prompt-caching guide: input_tokens excludes cache reads and writes.
ANTHROPIC_USAGE = {
    "input_tokens": 2048,
    "cache_read_input_tokens": 1800,
    "cache_creation_input_tokens": 248,
    "output_tokens": 503,
    "cache_creation": {
        "ephemeral_5m_input_tokens": 148,
        "ephemeral_1h_input_tokens": 100,
    },
}


def _line(**payload: object) -> str:
    body = {
        "task_id": "t",
        "variant": "cache",
        "run_id": "r",
        "kind": "llm",
        "status": "ok",
    }
    body.update(payload)
    return json.dumps(body) + "\n"


def _pad() -> Event:
    return Event(
        task_id="pad",
        variant="pad",
        run_id="r",
        kind=EventKind.TOOL,
        input_tokens=0,
        output_tokens=0,
        model=None,
        status=EventStatus.OK,
    )


def _priced(event: Event, prices: PriceTable | None = None):
    report = compare(
        [event, _pad()],
        ("cache", "pad"),
        prices=prices if prices is not None else PriceTable.bundled(),
        resamples=20,
    )
    return report.arm("cache")


def test_openai_usage_subtracts_cached_tokens_from_prompt_tokens() -> None:
    event = parse_jsonl(_line(model="gpt-4o", provider="openai", usage=OPENAI_USAGE))[0]
    assert event.input_tokens == 86
    assert event.cache_read_tokens == 1920
    assert event.cache_write_5m_tokens == 0
    assert event.cache_write_1h_tokens == 0
    assert event.output_tokens == 300
    # 86 * 2.50 + 1920 * 1.25 + 300 * 10 = 5615, per million.
    arm = _priced(event)
    assert arm.input_cost == Decimal("0.000215")
    assert arm.cache_read_cost == Decimal("0.0024")
    assert arm.output_cost == Decimal("0.003")
    assert arm.cache_write_5m_cost == Decimal("0")
    assert arm.cache_write_1h_cost == Decimal("0")
    assert arm.total_cost == Decimal("0.005615")
    counted_twice = (
        Decimal(2006) * Decimal("2.50")
        + Decimal(1920) * Decimal("1.25")
        + Decimal(300) * Decimal(10)
    ) / MILLION
    assert counted_twice == Decimal("0.010415")
    assert arm.total_cost != counted_twice
    assert arm.cache_savings == Decimal("0.0024")
    assert arm.tokens.median == Decimal(86 + 1920 + 300)


def test_openai_total_tokens_does_not_add_the_cached_count_again() -> None:
    usage = dict(OPENAI_USAGE)
    usage["total_tokens"] = 2306 + 1920
    with pytest.raises(ParseError, match="total_tokens"):
        parse_jsonl(_line(model="gpt-4o", provider="openai", usage=usage))


def test_openai_responses_shape_uses_the_same_subtraction() -> None:
    usage = {
        "input_tokens": 2006,
        "output_tokens": 300,
        "input_tokens_details": {"cached_tokens": 1920},
    }
    event = parse_jsonl(_line(model="gpt-4o", provider="openai", usage=usage))[0]
    assert event.input_tokens == 86
    assert event.cache_read_tokens == 1920
    assert event.output_tokens == 300


def test_openai_cache_writes_are_rejected_instead_of_billed_as_input() -> None:
    usage = {
        "input_tokens": 12000,
        "input_tokens_details": {
            "cached_tokens": 4000,
            "cache_write_tokens": 7000,
            "cache_write_tokens_details": {"ttl_30m_tokens": 3000, "ttl_12h_tokens": 4000},
        },
        "output_tokens": 10,
    }
    with pytest.raises(ParseError, match="cache_write_tokens"):
        parse_jsonl(_line(model="gpt-4o", provider="openai", usage=usage))


def test_anthropic_usage_keeps_input_tokens_separate_from_cache() -> None:
    event = parse_jsonl(
        _line(model="claude-sonnet-4", provider="anthropic", usage=ANTHROPIC_USAGE)
    )[0]
    assert event.input_tokens == 2048
    assert event.cache_read_tokens == 1800
    assert event.cache_write_5m_tokens == 148
    assert event.cache_write_1h_tokens == 100
    assert event.output_tokens == 503
    # 2048*3 + 1800*0.30 + 148*3.75 + 100*6 + 503*15 = 15384, per million.
    arm = _priced(event)
    assert arm.input_cost == Decimal("0.006144")
    assert arm.cache_read_cost == Decimal("0.00054")
    assert arm.cache_write_5m_cost == Decimal("0.000555")
    assert arm.cache_write_1h_cost == Decimal("0.0006")
    assert arm.cache_write_cost == Decimal("0.001155")
    assert arm.output_cost == Decimal("0.007545")
    assert arm.total_cost == Decimal("0.015384")
    subtracted = (
        Decimal(0) * Decimal(3)
        + Decimal(1800) * Decimal("0.30")
        + Decimal(148) * Decimal("3.75")
        + Decimal(100) * Decimal(6)
        + Decimal(503) * Decimal(15)
    ) / MILLION
    assert subtracted == Decimal("0.009240")
    assert arm.total_cost != subtracted
    assert arm.cache_savings == Decimal("0.004449")


def test_anthropic_creation_total_without_split_is_a_five_minute_write() -> None:
    usage = {
        "input_tokens": 10,
        "output_tokens": 4,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 100,
    }
    event = parse_jsonl(_line(model="claude-sonnet-4", provider="anthropic", usage=usage))[0]
    assert event.input_tokens == 10
    assert event.cache_write_5m_tokens == 100
    assert event.cache_write_1h_tokens == 0
    arm = _priced(event)
    # 100 * 3.75 / 1e6, not 100 * 3 / 1e6 and not 200 tokens.
    assert arm.cache_write_5m_cost == Decimal("0.000375")
    assert arm.cache_write_1h_cost == Decimal(0)
    assert arm.input_cost == Decimal("0.000030")


def test_anthropic_split_must_match_creation_total() -> None:
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_creation_input_tokens": 50,
        "cache_creation": {"ephemeral_5m_input_tokens": 10, "ephemeral_1h_input_tokens": 10},
    }
    with pytest.raises(ParseError, match="cache_creation"):
        parse_jsonl(_line(model="claude-sonnet-4", provider="anthropic", usage=usage))


def test_usage_and_tokens_together_are_rejected() -> None:
    with pytest.raises(ParseError, match="usage"):
        parse_jsonl(
            _line(
                model="gpt-4o",
                provider="openai",
                usage=OPENAI_USAGE,
                tokens={"input": 86, "output": 300, "cache_read": 1920},
            )
        )


def test_normalized_tokens_are_not_subtracted_again() -> None:
    raw = parse_jsonl(_line(model="gpt-4o", provider="openai", usage=OPENAI_USAGE))[0]
    normalized = parse_jsonl(
        _line(
            model="gpt-4o",
            provider="openai",
            tokens={"input": 2006, "output": 300, "cache_read": 1920},
        )
    )[0]
    assert normalized.input_tokens == 2006
    assert normalized.cache_read_tokens == 1920
    assert _priced(normalized).total_cost > _priced(raw).total_cost


def test_flat_cache_field_beside_tokens_object_is_not_dropped() -> None:
    with pytest.raises(ParseError, match="cache_read_tokens"):
        parse_jsonl(
            _line(
                model="gpt-4o",
                tokens={"input": 10, "output": 1},
                cache_read_tokens=5,
            )
        )
    event = parse_jsonl(
        _line(
            model="gpt-4o",
            tokens={"input": 10, "output": 1, "cache_read": 5},
            cache_read_tokens=5,
        )
    )[0]
    assert event.input_tokens == 10
    assert event.cache_read_tokens == 5


def test_flat_cache_fields_are_disjoint() -> None:
    event = parse_jsonl(
        _line(
            model="claude-sonnet-4",
            input_tokens=5,
            output_tokens=6,
            cache_read_tokens=7,
            cache_write_5m_tokens=8,
            cache_write_1h_tokens=9,
        )
    )[0]
    assert event.input_tokens == 5
    assert event.output_tokens == 6
    assert event.cache_read_tokens == 7
    assert event.cache_write_5m_tokens == 8
    assert event.cache_write_1h_tokens == 9


def test_v01_trace_has_the_same_cost_and_no_cache_savings() -> None:
    events = load_traces(ROOT / "examples" / "research_agent" / "traces.jsonl")
    assert all(event.cache_read_tokens == 0 for event in events)
    assert all(event.cache_write_5m_tokens == 0 for event in events)
    assert all(event.cache_write_1h_tokens == 0 for event in events)
    report = compare(events, ("A", "B"), resamples=1000)
    arm_a = report.arm("A")
    arm_b = report.arm("B")
    assert arm_a.cost_per_solved_task == Decimal("0.000498375")
    assert arm_b.cost_per_solved_task == Decimal("0.0104")
    assert arm_a.cache_savings == Decimal(0)
    assert arm_b.cache_savings == Decimal(0)
    assert arm_a.cache_read_cost == Decimal(0)
    assert arm_a.cache_write_cost == Decimal(0)
    assert arm_a.input_cost + arm_a.output_cost == arm_a.total_cost
    assert arm_b.input_cost + arm_b.output_cost == arm_b.total_cost
    bare = parse_jsonl(
        '{"task_id":"q1","variant":"A","run_id":"r1","kind":"llm",'
        '"tokens":{"input":120,"output":30},"model":"gpt-4o-mini","status":"ok"}\n'
    )[0]
    assert bare.input_tokens == 120
    assert bare.cache_read_tokens == 0


def test_missing_cache_price_uses_input_and_the_report_says_so() -> None:
    prices = PriceTable(
        version="lab",
        currency="USD",
        models={"m": ModelPrice(Decimal("2"), Decimal("8"))},
    )
    event = parse_jsonl(
        _line(model="m", tokens={"input": 0, "output": 0, "cache_read": 1_000_000})
    )[0]
    arm = _priced(event, prices)
    assert arm.total_cost == Decimal("2")
    assert arm.cache_read_cost == Decimal("2")
    assert arm.cache_savings == Decimal(0)
    assert arm.cache_priced_as_input == ("m cache_read",)
    text = render_markdown(compare([event, _pad()], ("cache", "pad"), prices=prices, resamples=20))
    assert "priced at the input rate" in text
    assert "`m`" in text
    payload = json.loads(
        render_json(compare([event, _pad()], ("cache", "pad"), prices=prices, resamples=20))
    )
    assert payload["arms"]["cache"]["cache_priced_as_input"] == ["m cache_read"]
    assert payload["arms"]["cache"]["cost_breakdown"]["cache_read"] == 2
    assert payload["arms"]["cache"]["cache_savings"] == 0


def test_explicit_zero_cache_price_is_free_and_does_not_warn() -> None:
    prices = PriceTable(
        version="lab",
        currency="USD",
        models={
            "m": ModelPrice(
                Decimal("2"),
                Decimal("8"),
                cache_read_per_million=Decimal("0"),
            )
        },
    )
    event = parse_jsonl(
        _line(model="m", tokens={"input": 0, "output": 0, "cache_read": 1_000_000})
    )[0]
    arm = _priced(event, prices)
    assert arm.total_cost == Decimal(0)
    assert arm.cache_savings == Decimal("2")
    assert arm.cache_priced_as_input == ()


def test_price_file_overrides_cache_rates(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "version": "lab-cache",
                "currency": "USD",
                "models": {
                    "gpt-4o": {
                        "input": 2.5,
                        "output": 10,
                        "cache_read": 0,
                        "source": "invoice",
                        "as_of": "2026-10-29",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    table = PriceTable.bundled().merge(PriceTable.load(path))
    price = table.lookup("gpt-4o")
    assert price is not None
    assert price.cache_read_per_million == Decimal(0)
    assert price.source == "invoice"
    event = parse_jsonl(_line(model="gpt-4o", provider="openai", usage=OPENAI_USAGE))[0]
    arm = _priced(event, table)
    assert arm.cache_read_cost == Decimal(0)
    assert arm.input_cost == Decimal("0.000215")
    assert arm.cache_priced_as_input == ()


def test_override_without_cache_keys_drops_the_bundled_cache_price(tmp_path: Path) -> None:
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            {
                "version": "lab",
                "currency": "USD",
                "models": {"gpt-4o": {"input": 2.5, "output": 10}},
            }
        ),
        encoding="utf-8",
    )
    table = PriceTable.bundled().merge(PriceTable.load(path))
    price = table.lookup("gpt-4o")
    assert price is not None
    assert price.cache_read_per_million is None
    event = parse_jsonl(_line(model="gpt-4o", provider="openai", usage=OPENAI_USAGE))[0]
    arm = _priced(event, table)
    assert arm.cache_read_cost == arm.input_cost / Decimal(86) * Decimal(1920)
    assert arm.cache_savings == Decimal(0)
    assert arm.cache_priced_as_input == ("gpt-4o cache_read",)


def test_negative_cache_price_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "version": "x",
                "currency": "USD",
                "models": {"m": {"input": 1, "output": 1, "cache_read": -1}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PriceError):
        PriceTable.load(path)
    with pytest.raises(PriceError):
        PriceTable.bundled().override(
            {"m": ModelPrice(Decimal("1"), Decimal("1"), cache_read_per_million=Decimal("-1"))}
        )


def test_bundled_cache_prices_match_the_cited_pages() -> None:
    table = PriceTable.bundled()
    assert table.version == "2026-10-29"
    openai = "https://developers.openai.com/api/docs/pricing"
    anthropic = "https://platform.claude.com/docs/en/about-claude/pricing"
    expected = {
        "gpt-4o": Decimal("1.25"),
        "gpt-4o-mini": Decimal("0.075"),
        "gpt-4.1": Decimal("0.50"),
        "gpt-4.1-mini": Decimal("0.10"),
        "gpt-4.1-nano": Decimal("0.025"),
        "o4-mini": Decimal("0.275"),
        "o3-mini": Decimal("0.55"),
    }
    for name, cache_read in expected.items():
        price = table.lookup(name)
        assert price is not None
        assert price.cache_read_per_million == cache_read
        assert price.cache_write_5m_per_million is None
        assert price.cache_write_1h_per_million is None
        assert price.source == openai
        assert price.as_of == "2026-10-29"
    sonnet = table.lookup("claude-sonnet-4")
    haiku = table.lookup("claude-3-5-haiku")
    assert sonnet is not None and haiku is not None
    assert sonnet.cache_read_per_million == Decimal("0.30")
    assert sonnet.cache_write_5m_per_million == Decimal("3.75")
    assert sonnet.cache_write_1h_per_million == Decimal("6")
    assert haiku.cache_read_per_million == Decimal("0.08")
    assert haiku.cache_write_5m_per_million == Decimal("1")
    assert haiku.cache_write_1h_per_million == Decimal("1.60")
    assert sonnet.source == anthropic
    assert haiku.source == anthropic
    assert sonnet.as_of == "2026-10-29"
    old = table.lookup("claude-3-5-sonnet")
    gemini = table.lookup("gemini-2.5-pro")
    assert old is not None and gemini is not None
    assert old.cache_read_per_million is None
    assert old.cache_write_5m_per_million is None
    assert gemini.cache_read_per_million is None
    assert gemini.input_per_million == Decimal("1.25")


def test_otel_cache_attributes_are_included_in_input_tokens() -> None:
    raw = json.dumps(
        {
            "spans": [
                {
                    "traceId": "t1",
                    "attributes": {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 1000,
                        "gen_ai.usage.output_tokens": 10,
                        "gen_ai.usage.cache_read.input_tokens": 400,
                        "gen_ai.usage.cache_write.input_tokens": 50,
                        "agentcost.task_id": "q",
                        "agentcost.variant": "cache",
                        "agentcost.run_id": "r",
                    },
                }
            ]
        }
    )
    event = parse_otel(raw)[0]
    assert event.input_tokens == 550
    assert event.cache_read_tokens == 400
    assert event.cache_write_5m_tokens == 50
    assert event.cache_write_1h_tokens == 0
    assert event.output_tokens == 10
    arm = _priced(event)
    assert arm.tokens.median == Decimal(1000 + 10)


def test_otel_cache_larger_than_input_is_rejected() -> None:
    raw = json.dumps(
        {
            "spans": [
                {
                    "traceId": "t1",
                    "attributes": {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": "claude-sonnet-4",
                        "gen_ai.usage.input_tokens": 100,
                        "gen_ai.usage.cache_read.input_tokens": 800,
                        "agentcost.task_id": "q",
                        "agentcost.variant": "cache",
                    },
                }
            ]
        }
    )
    with pytest.raises(ParseError, match="input_tokens"):
        parse_otel(raw)


def test_report_breaks_down_cache_cost_in_markdown_and_json() -> None:
    event = parse_jsonl(
        _line(model="claude-sonnet-4", provider="anthropic", usage=ANTHROPIC_USAGE)
    )[0]
    report = compare([event, _pad()], ("cache", "pad"), resamples=20)
    text = render_markdown(report)
    assert "| Input cost |" in text
    assert "| Output cost |" in text
    assert "| Cache read cost |" in text
    assert "| Cache write cost |" in text
    assert "5 min $0.000555" in text
    assert "1 h $0.0006" in text
    assert "| Cache savings vs input price |" in text
    assert "$0.004449" in text
    payload = json.loads(render_json(report))
    breakdown = payload["arms"]["cache"]["cost_breakdown"]
    assert breakdown["input"] == pytest.approx(0.006144)
    assert breakdown["output"] == pytest.approx(0.007545)
    assert breakdown["cache_read"] == pytest.approx(0.00054)
    assert breakdown["cache_write"] == pytest.approx(0.001155)
    assert breakdown["cache_write_5m"] == pytest.approx(0.000555)
    assert breakdown["cache_write_1h"] == pytest.approx(0.0006)
    assert payload["arms"]["cache"]["cache_savings"] == pytest.approx(0.004449)
    assert payload["schema_version"] == "0.1"


def test_cache_only_call_still_requires_a_price() -> None:
    event = parse_jsonl(
        _line(model="missing-model", tokens={"input": 0, "output": 0, "cache_read": 10})
    )[0]
    with pytest.raises(PriceError, match="missing-model"):
        compare([event, _pad()], ("cache", "pad"), prices=PriceTable.bundled())


def test_failed_run_cost_includes_cache() -> None:
    event = parse_jsonl(
        _line(
            model="gpt-4o",
            provider="openai",
            usage=OPENAI_USAGE,
            status="error",
        )
    )[0]
    arm = _priced(event)
    assert arm.failed_run_cost == arm.total_cost
    assert arm.failed_run_cost == Decimal("0.005615")
    # 2006 prompt + 300 completion. Cached tokens are already inside the 2006.
    assert arm.failed_run_tokens == 2306


def test_cache_write_premium_is_a_negative_saving() -> None:
    event = parse_jsonl(
        _line(
            model="claude-sonnet-4",
            tokens={"input": 0, "output": 0, "cache_write_1h": 100},
        )
    )[0]
    report = compare([event, _pad()], ("cache", "pad"), resamples=20)
    assert report.arm("cache").cache_savings == Decimal("-0.0003")
    assert "-$0.0003" in render_markdown(report)


def test_documented_example_file_matches_the_api_payloads() -> None:
    events = load_traces(ROOT / "examples" / "cache_usage" / "traces.jsonl")
    report = compare(events, ("openai", "anthropic"), resamples=20)
    assert report.arm("openai").total_cost == Decimal("0.005615")
    assert report.arm("openai").cache_savings == Decimal("0.0024")
    assert report.arm("anthropic").total_cost == Decimal("0.015384")
    assert report.arm("anthropic").cache_savings == Decimal("0.004449")
