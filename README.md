# agentcost

agentcost turns traces of LLM-agent runs into a per-task cost, including cached tokens, and an A/B comparison of two variants. It is a library plus a thin command-line interface. It does not call a model, host a dashboard, or ingest spans live.

A **task** is one `task_id` inside a variant. A **run** is one attempt at that task. Each line or span is one LLM call or one tool call. Failed runs are part of the cost (you paid for them) and are also reported on their own rows, so a retry does not disappear into the average.

## Install

Python 3.10 or newer.

```bash
pip install -e ".[dev]"
```

The console script is `agentcost`. `python -m agentcost` is the same entry point.

## Trace formats

`load_traces` accepts either format. A `.jsonl` file is read as one event per line. A single JSON document is read as an OpenTelemetry export.

### JSONL

One JSON object per line. Blank lines are ignored.

| Field | Required | Notes |
| --- | --- | --- |
| `task_id` | yes | Task identity. Compared separately per variant. |
| `variant` | yes | Arm name used by `--compare`. Case-sensitive. |
| `run_id` | yes | One attempt. Several events can share it. |
| `kind` | no | `llm` or `tool`. Defaults to `llm` when `model` is set, otherwise `tool`. |
| `tokens.input`, `tokens.output` | no | Ordinary token counts. Missing counts are 0. Flat `input_tokens` / `output_tokens` also work. `input` does not include cache tokens. |
| `tokens.cache_read`, `tokens.cache_write_5m`, `tokens.cache_write_1h` | no | Disjoint cache counts. Flat `cache_read_tokens`, `cache_write_5m_tokens`, and `cache_write_1h_tokens` also work. See [Cache](#cache). |
| `provider`, `usage` | no | Raw provider payload. `openai` or `anthropic`. Do not combine with `tokens` or the flat counts. |
| `model` | no | Billed model id. Tool calls usually omit it. |
| `status` | yes | `ok` or `error`. A boolean `ok` is accepted. |

```json
{"task_id":"q01","variant":"A","run_id":"r1","kind":"tool","tokens":{"input":0,"output":0},"model":null,"status":"ok"}
{"task_id":"q01","variant":"A","run_id":"r1","kind":"llm","tokens":{"input":1480,"output":295},"model":"gpt-4o-mini","status":"ok"}
```

A run fails if any of its events has `status: "error"`. A task succeeds if any of its runs succeeded.

### OTel GenAI JSON

Supported documents:

- OTLP JSON (`resourceSpans` / `scopeSpans`, including `instrumentationLibrarySpans`)
- `{"spans": [ ... ]}`
- a JSON array of spans

Attributes may be an OTLP key/value list (`intValue` may be a string, as in ProtoJSON) or a flat object.

| agentcost field | Span attribute |
| --- | --- |
| model | `gen_ai.response.model`, else `gen_ai.request.model` |
| input tokens | `gen_ai.usage.input_tokens`, else legacy `gen_ai.usage.prompt_tokens` |
| output tokens | `gen_ai.usage.output_tokens`, else legacy `gen_ai.usage.completion_tokens` |
| tool vs llm | `gen_ai.operation.name` of `execute_tool` or `retrieval` is a tool step. `chat`, `generate_content`, `text_completion`, and `embeddings` are LLM calls. |
| error | span status `ERROR` / code `2`, or a non-empty `error.type` |
| `task_id` | `agentcost.task_id`, else `gen_ai.conversation.id` |
| `variant` | `agentcost.variant` on the span or the resource. Missing means `default`. |
| `run_id` | `agentcost.run_id`, else the trace id |

`agentcost.variant` is not part of the GenAI semantic conventions. Set it on the span or resource when you export the experiment, or the arm collapses to `default`.

`gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens` are priced on their own. The conventions already include those tokens in `gen_ai.usage.input_tokens`, so agentcost subtracts them before billing. If the cache counts are larger than the input count, the file is rejected. A cache write has no TTL in the conventions, so it is billed as a 5-minute write. A 1-hour Anthropic write needs the JSONL `usage` object. Modality subsets (`gen_ai.usage.text.cache_read.input_tokens` and the audio and image twins) are not read: the convention already includes them in the aggregate.

`invoke_agent`, `create_agent`, and `invoke_workflow` spans are dropped when the same trace also contains a chat, tool, or other GenAI span, so a parent usage total is not added on top of the children. A wrapper that is the only GenAI span in its trace is kept.

Spans with no `gen_ai.*` or `agentcost.*` attribute are ignored.

## Prices

Cost of one call, in the table currency (USD in the bundled file):

```text
(
  ordinary_input * input
  + output * output
  + cache_read * cache_read
  + cache_write_5m * cache_write_5m
  + cache_write_1h * cache_write_1h
) / 1_000_000
```

Output uses the output rate. Each cache term uses its own rate when the row has one. When a cache rate is absent, that term uses the input rate and the report names the model. See [Cache](#cache).

The bundled snapshot ships at `src/agentcost/data/prices.json`, version `2026-10-29`. It is a static table of public list prices, not a feed from a vendor. Input and output rates for the models that were already in the `2026-10-01` snapshot are unchanged. Override the file whenever the figure needs to match an invoice.

Lookup is exact, then the longest table key that is a hyphen or dot prefix of the model id. `gpt-4o-mini-2024-07-18` matches `gpt-4o-mini`, not `gpt-4o`. A dated id inherits that row's cache rates too. Add an explicit row when the invoice differs. OpenAI's page lists `gpt-4o-2024-05-13` without a cached-input price; the prefix `gpt-4o` does have one, so that dated id needs its own row if it must not inherit.

An override file uses the same schema and is merged on top of the bundled table: listed models replace the whole row, other models stay. `--set-price` is applied after the file. It only sets input and output (`MODEL=INPUT:OUTPUT`). It does not copy or set cache rates, so a cached trace priced that way falls back to the input rate and the report says so. To change a cache rate, put it in the file or pass `ModelPrice` with the cache fields.

```json
{
  "version": "lab-1",
  "currency": "USD",
  "models": {
    "gpt-4o-mini": {
      "input": 0.15,
      "output": 0.60,
      "cache_read": 0.075
    },
    "claude-sonnet-4": {
      "input": 3,
      "output": 15,
      "cache_read": 0.30,
      "cache_write_5m": 3.75,
      "cache_write_1h": 6
    }
  }
}
```

`input`, `output`, `cache_read`, `cache_write_5m`, and `cache_write_1h` are USD per 1,000,000 tokens. Omit a cache key to leave that rate unset. A present `0` is free and does not warn. Optional `source` and `as_of` are recorded on the row and are not required. Unknown models with a non-zero token count, cache included, are an error. `--allow-unpriced` (or `on_missing="zero"`) prices them as zero and lists them on the report. A call with zero tokens does not need a price.

## Cache

Ordinary input, cache reads, and cache writes are separate counts. The same tokens are not billed twice. Which rule applies depends on how the trace is written.

| Shape | Rule |
| --- | --- |
| `tokens` or the flat fields, no `usage` | Already disjoint. `tokens.input` is ordinary input. Cache fields are added. A v0.1 line has no cache fields, so its cost does not change. `provider` without `usage` does not subtract or add. |
| `provider: "openai"` and `usage` | `prompt_tokens` (Chat Completions) and `input_tokens` (Responses) already include `cached_tokens`. Ordinary input is that total minus `cached_tokens`. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) and the usage object in [Prompt Caching in the API](https://openai.com/index/api-prompt-caching/) (1 October 2024). |
| `provider: "anthropic"` and `usage` | `input_tokens` does not include the cache. `cache_read_input_tokens` and `cache_creation_input_tokens` are added. `cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` are the write split and are not added on top of the creation total. If only the total is present, it is a 5-minute write, which is Anthropic's default TTL. [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). |
| OTel GenAI | Cache attributes are included in `gen_ai.usage.input_tokens`. They are subtracted. Writes are billed as 5-minute writes. |

Do not pass `usage` and `tokens` on the same event. OpenAI `cache_write_tokens` (30-minute and 12-hour writes on newer models) is rejected when it is not zero: those tokens already sit inside `input_tokens`, and this table has no price for them. Putting a flat `cache_read_tokens` next to a `tokens` object is an error unless `tokens.cache_read` repeats the same number. Flat `input_tokens` next to `tokens` is still ignored, as in v0.1.

Cache savings are what those cache tokens would have cost at the input rate, minus what they cost at the cache rate. Anthropic writes are 1.25× (5 minutes) and 2× (1 hour) the input rate, so that part of the savings is negative. The report shows the signed net. A trace with no cache tokens shows `$0`.

Bundled cache rates, USD per 1,000,000 tokens, checked against the vendor page on 2026-10-29. Each of those rows stores `source` and `as_of`. Models with no published cache rate in this table are left blank on purpose. A cache token on one of them uses the input rate, and the report lists `cache_priced_as_input`.

| Model | cache_read | cache_write_5m | cache_write_1h | Source |
| --- | ---: | ---: | ---: | --- |
| `gpt-4o` | 1.25 | | | [OpenAI pricing](https://developers.openai.com/api/docs/pricing) |
| `gpt-4o-mini` | 0.075 | | | same |
| `gpt-4.1` | 0.50 | | | same |
| `gpt-4.1-mini` | 0.10 | | | same |
| `gpt-4.1-nano` | 0.025 | | | same |
| `o3-mini` | 0.55 | | | same |
| `o4-mini` | 0.275 | | | same |
| `claude-sonnet-4` | 0.30 | 3.75 | 6 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Claude Sonnet 4) |
| `claude-3-5-haiku` | 0.08 | 1 | 1.60 | same page (Claude Haiku 3.5) |
| `claude-3-5-sonnet` | | | | Not on that page. No cache rate is invented. |
| `gemini-2.5-flash`, `gemini-2.5-pro` | | | | No Gemini cache rate is published in this table. |

`examples/cache_usage/traces.jsonl` is built from those documented usage objects. It is not a live API call. OpenAI is the 2024 announcement (`prompt_tokens` 2006, `cached_tokens` 1920, `completion_tokens` 300). Anthropic is the prompt-caching guide (`input_tokens` 2048, read 1800, 5-minute write 148, 1-hour write 100, `output_tokens` 503).

```bash
agentcost report examples/cache_usage/traces.jsonl --compare openai anthropic
```

One task per variant is not enough for a verdict. The cost rows are `$0.005615` (OpenAI, cache savings `$0.0024`) and `$0.015384` (Anthropic, cache savings `$0.004449`). The Anthropic write row is `$0.001155 (5 min $0.000555, 1 h $0.0006)`. Markdown and JSON both carry the breakdown: input, output, cache read, cache write, and cache savings. JSON also splits the write into `cache_write_5m` and `cache_write_1h`.

## Metrics and verdict

For each variant, observations are tasks. A task's cost, tokens, and steps are the sums across every run of that task, including failed runs. Tokens are ordinary input, output, cache reads, and cache writes. Steps are LLM calls plus tool calls. The report also lists input cost, output cost, cache read cost, cache write cost, and cache savings versus the input rate.

Reported for each arm:

- task success rate (solved tasks / tasks)
- median and p25–p75 of cost, tokens, and steps per task (linear percentile, same indexing as NumPy's linear method)
- cost per solved task: total cost of the arm, failed runs included, divided by the number of solved tasks
- failed-run count, cost, and tokens

The verdict compares the **first** variant in `--compare A B` with the second, on cost per solved task. Lower is better.

| Result | When |
| --- | --- |
| `better` | At least 5 tasks in each arm, both arms solved at least one task, and the bootstrap 95% intervals are disjoint with the first arm cheaper. |
| `worse` | Same, with the first arm more expensive. |
| `no_difference` | At least 5 tasks in each arm, and the two cost-per-solved-task point estimates are equal. |
| `inconclusive` | Fewer than 5 tasks in either arm, an arm with no solved task, or overlapping bootstrap intervals. |

The bootstrap resamples tasks with replacement (1,000 resamples by default, seed 42, percentile interval). A resample with no solved task is dropped. If too many resamples are empty, the verdict is `inconclusive`. Arms are unpaired: shared `task_id` values are not matched across variants. Task order is sorted by `task_id` before resampling so the interval does not depend on file order. Touching interval endpoints count as overlap.

## CLI

```bash
agentcost report examples/research_agent/traces.jsonl --compare A B
agentcost report traces.jsonl --compare A B --format json
agentcost report traces.jsonl --compare A B --prices ./prices.json --set-price local-model=0.20:0.80
agentcost report traces.otel.json --compare A B --format both --output report.md --seed 42
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--compare A B` | required | Two variant names. Verdict is about A versus B. |
| `--format` | `md` | `md`, `json`, or `both`. |
| `--prices` | bundled table | JSON file merged onto the snapshot. |
| `--set-price` | none | `MODEL=INPUT:OUTPUT` in USD per 1,000,000 tokens. Repeatable. Wins over the file for input and output. Does not set cache rates. |
| `--output` | stdout | Write the report. With `--format both`, Markdown goes to this path and JSON to the same path with a `.json` suffix. |
| `--seed` | `42` | Bootstrap seed. |
| `--bootstrap` | `1000` | Resample count. |
| `--allow-unpriced` | off | Unknown models cost zero and are named in the report. |

`--format both` refuses an `--output` that already ends in `.json`, because the Markdown and JSON reports would be the same file. The command prints the path to stderr, exits 1, and creates nothing:

```text
--format both would write Markdown and JSON to the same path: informe.json
```

Ask for both reports with a path that does not end in `.json`. `informe.md` writes Markdown there and JSON to `informe.json`. `informe` writes Markdown to `informe` and JSON to `informe.json`. To write only JSON, use `--format json --output informe.json`.

Expected failures (missing variant, unknown model, bad JSON, or `--format both` with an `--output` that already ends in `.json`) print the message to stderr and exit 1.

## Library

```python
from decimal import Decimal

from agentcost import ModelPrice, PriceTable, compare, load_traces, render_json, render_markdown

events = load_traces("traces.jsonl")
prices = PriceTable.bundled().override(
    {"local-model": ModelPrice(Decimal("0.20"), Decimal("0.80"))}
)
report = compare(events, ("A", "B"), prices=prices)
print(render_markdown(report))
print(render_json(report))
```

`compare(..., on_missing="zero")` matches `--allow-unpriced`. `report.verdict.value` is `better`, `worse`, `no_difference`, or `inconclusive`.

## Example

`examples/research_agent/traces.jsonl` is a synthetic research agent: eight question ids, no real queries or pages. Variant `A` is `gpt-4o-mini` with search and fetch. `q03` errors once and retries. Variant `B` is `gpt-4o` with a single search step. `q08` never succeeds. `otel_fragment.json` shows the GenAI attribute mapping, including an `invoke_agent` wrapper that is not double-counted.

```bash
agentcost report examples/research_agent/traces.jsonl --compare A B
```

```text
# agentcost report

**Verdict:** better

A is cheaper per solved task than B; bootstrap 95% intervals do not overlap.

Lower cost per solved task is better. The denominator is solved tasks. Failed runs stay in the numerator and in the per-task distributions, and are also listed on their own rows.

| Metric | A | B |
| --- | ---: | ---: |
| Tasks | 8 | 8 |
| Successful tasks | 8 | 7 |
| Success rate | 100% | 87.5% |
| Cost per solved task | $0.000498375 | $0.0104 |
| Cost per task, median (p25–p75) | $0.0004935 ($0.0004515–$0.00053025) | $0.0091 ($0.00875–$0.00945) |
| Tokens per task, median (p25–p75) | 2202.5 (2012.5–2368.75) | 2245 (2157.5–2332.5) |
| Steps per task, median (p25–p75) | 3 (3–3) | 2 (2–2) |
| Runs | 9 | 8 |
| Failed runs | 1 | 1 |
| Failed-run cost | $0.000207 | $0.0098 |
| Failed-run tokens | 1020 | 2420 |
| Input cost | $0.002247 | $0.0356 |
| Output cost | $0.00174 | $0.0372 |
| Cache read cost | $0 | $0 |
| Cache write cost | $0 | $0 |
| Cache savings vs input price | $0 | $0 |

Price table `2026-10-29` (USD per 1,000,000 tokens). Bootstrap 95% intervals, 1000 resamples, seed 42.
```

`--format json` emits the same figures under `verdict`, `arms.<variant>.per_task`, `arms.<variant>.cost_per_solved_task`, and `intervals`. Schema version is `0.1`. Cache adds `cost_breakdown`, `cache_savings`, and `cache_priced_as_input` on each arm.

## Development

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

Dependencies are version ranges in `pyproject.toml`; this library does not commit a lockfile.

GitHub Actions runs the tests on Ubuntu, macOS, and Windows for Python 3.10, 3.11, and 3.12. The linter runs on Ubuntu with Python 3.12.

## Not in v0.1

Live ingestion, a dashboard, and adapters that pull traces from OpenAI, Anthropic, or LangGraph. Guardrail checks are out of scope. Export JSONL or OTel JSON yourself and point `agentcost report` at the file.

## License

MIT. See `LICENSE`.

<https://ivrogo.com>
