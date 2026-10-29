# agentcost

agentcost v0.1 turns traces of LLM-agent runs into a per-task cost and an A/B comparison of two variants. It is a library plus a thin command-line interface. It does not call a model, host a dashboard, or ingest spans live.

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
| `task_id` | yes | Task identity. Shared ids are paired across variants unless you pass `--unpaired`. |
| `variant` | yes | Arm name used by `--compare`. Case-sensitive. |
| `run_id` | yes | One attempt. Several events can share it. |
| `kind` | no | `llm` or `tool`. Defaults to `llm` when `model` is set, otherwise `tool`. |
| `tokens.input`, `tokens.output` | no | Token counts. Missing counts are 0. Flat `input_tokens` / `output_tokens` also work. |
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

Cache breakdown attributes (`gen_ai.usage.cache_read.input_tokens` and similar) are not priced separately. Conventions already include those tokens in `gen_ai.usage.input_tokens`, and v0.1 bills that total at the input rate. There is no cache discount.

`invoke_agent`, `create_agent`, and `invoke_workflow` spans are dropped when the same trace also contains a chat, tool, or other GenAI span, so a parent usage total is not added on top of the children. A wrapper that is the only GenAI span in its trace is kept.

Spans with no `gen_ai.*` or `agentcost.*` attribute are ignored.

## Prices

Cost of one call, in the table currency (USD in the bundled file):

```text
(input_tokens * input_price + output_tokens * output_price) / 1_000_000
```

The bundled snapshot ships at `src/agentcost/data/prices.json`, version `2026-10-01`. It is a static table of public list prices, not a feed from a vendor. Override it whenever the figure needs to match an invoice.

Lookup is exact, then the longest table key that is a hyphen or dot prefix of the model id. `gpt-4o-mini-2024-07-18` matches `gpt-4o-mini`, not `gpt-4o`.

An override file uses the same schema and is merged on top of the bundled table: listed models replace, other models stay. `--set-price` is applied after the file.

```json
{
  "version": "lab-1",
  "currency": "USD",
  "models": {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60}
  }
}
```

`input` and `output` are USD per 1,000,000 tokens. Unknown models with a non-zero token count are an error. `--allow-unpriced` (or `on_missing="zero"`) prices them as zero and lists them on the report. A call with zero tokens does not need a price.

## Metrics and verdict

For each variant, observations are tasks. A task's cost, tokens, and steps are the sums across every run of that task, including failed runs. Tokens are input plus output. Steps are LLM calls plus tool calls.

Reported for each arm:

- task success rate (solved tasks / tasks)
- median and p25–p75 of cost, tokens, and steps per task (linear percentile, same indexing as NumPy's linear method)
- cost per solved task: total cost of the arm, failed runs included, divided by the number of solved tasks
- failed-run count, cost, and tokens

The verdict compares the **first** variant in `--compare A B` with the second. Lower cost is better.

By default the report is **paired** when the two variants share at least one `task_id`. The difference on a task is the first variant minus the second (cost, tokens, and steps). Each of those is the sum across every run of that task, including failed runs. The report gives the mean of those differences and a 95% bootstrap interval, plus the relative change and its interval. With no shared `task_id`, the report stays unpaired and says so.

| Result | Paired | Unpaired |
| --- | --- | --- |
| `better` | At least 5 pairs, and the 95% interval of the mean cost difference is entirely below 0. | At least 5 tasks in each arm, both arms solved at least one task, and the bootstrap 95% intervals of cost per solved task are disjoint with the first arm cheaper. |
| `worse` | Same, with the cost interval entirely above 0. | Same, with the first arm more expensive. |
| `no_difference` | At least 5 pairs, and the mean cost difference is 0. | At least 5 tasks in each arm, and the two cost-per-solved-task point estimates are equal. |
| `inconclusive` | Fewer than 5 pairs, or the cost interval contains 0. | Fewer than 5 tasks in either arm, an arm with no solved task, or overlapping bootstrap intervals. |

The bootstrap resamples with replacement (1,000 resamples by default, seed 42, `--bootstrap` and `--seed`). In the paired test each draw resamples the paired differences. In the unpaired test each arm is resampled on its own; a resample with no solved task is dropped, and the verdict is `inconclusive` if too many resamples are empty. Task order is sorted by `task_id` before resampling, so the interval does not depend on file order. An interval that touches 0 counts as including 0. Touching endpoints of two arm intervals count as overlap.

### How to read the paired interval

The cost row is the test behind the verdict. A negative mean means the first variant is cheaper on the paired tasks. The 95% interval is a percentile interval of that mean: if it lies entirely below 0, the paired tasks separate the variants in that direction. If it contains 0, they do not, and the verdict is `inconclusive` even when the mean itself is not 0.

The relative change is `100 * mean(first - second) / mean(second)`, in percent. On the sample below, about -94.5% means the first variant's mean task cost is about 94.5% lower than the second. The relative interval is the same bootstrap applied to that ratio. It is omitted when the second variant's mean is 0.

Tokens and steps use the same differences. They do not change the verdict. The sample's token interval includes 0; the step interval does not (the first variant takes more steps).

Partial overlap uses only the shared ids. The report names how many tasks were left out of each variant. Those tasks are not in the arm table either. `--paired` requires at least one shared id and exits 1 otherwise. `--unpaired` ignores shared ids, keeps every task, and does not warn. Passing both flags is an error.

If `auto` finds no shared id, the report and stderr both say `No shared task_id between 'A' and 'B'. Using the unpaired comparison.`

JSON `intervals` is still each arm's cost-per-solved-task interval, on the tasks that entered the report. The paired interval is `pairing.metrics.cost`. Those two are not the same number: cost per solved task divides by solved tasks, and the paired mean divides by paired tasks. They can disagree when the success counts differ. `pairing.cost` (and `assess_pairing`) is the result a later gate should read. Traces have no latency field, so latency is not compared.

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
| `--set-price` | none | `MODEL=INPUT:OUTPUT` in USD per 1,000,000 tokens. Repeatable. Wins over the file. |
| `--output` | stdout | Write the report. With `--format both`, Markdown goes to this path and JSON to the same path with a `.json` suffix. |
| `--seed` | `42` | Bootstrap seed. |
| `--bootstrap` | `1000` | Resample count. `10000` is a reasonable setting when you want a finer percentile. |
| `--paired` | off | Force pairing. Exits 1 when the variants share no `task_id`. |
| `--unpaired` | off | Force the unpaired comparison, even when task ids match. |
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

`compare(..., on_missing="zero")` matches `--allow-unpriced`. `compare(..., pairing="paired")` and `pairing="unpaired"` match the flags; the default is `"auto"`. `report.verdict.value` is `better`, `worse`, `no_difference`, or `inconclusive`. `report.pairing` is the typed paired result: `mode`, `pairs`, `unmatched_first`, `unmatched_second`, `warning`, and `cost` / `tokens` / `steps`. Each metric's `includes_zero` is true when the 95% interval contains 0. `assess_pairing` returns that same object from per-task observations.

## Example

`examples/research_agent/traces.jsonl` is a synthetic research agent: eight question ids, no real queries or pages. Variant `A` is `gpt-4o-mini` with search and fetch. `q03` errors once and retries. Variant `B` is `gpt-4o` with a single search step. `q08` never succeeds. `otel_fragment.json` shows the GenAI attribute mapping, including an `invoke_agent` wrapper that is not double-counted.

```bash
agentcost report examples/research_agent/traces.jsonl --compare A B
```

```text
# agentcost report

**Verdict:** better

A costs less per paired task than B; the bootstrap 95% interval of the mean difference does not include 0.

**Pairing:** paired (8 pairs).

Each difference is the first variant minus the second on that task (failed runs stay in the task total). Negative cost means the first variant is cheaper.

| Metric | Mean difference (A - B) | 95% CI | Includes 0 | Relative change |
| --- | ---: | ---: | :---: | ---: |
| Cost | -$0.008601625 | [-$0.008896, -$0.0083295375] | no | -94.523351648352% [-94.911764705882%, -93.96694214876%] |
| Tokens | -10 | [-176.875, 239.375] | yes | -0.445434298441% [-8.035207268597%, 10.692350642099%] |
| Steps | 1.375 | [1, 2.125] | no | 68.75% [50%, 106.25%] |

The cost interval does not include 0.

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

Price table `2026-10-01` (USD per 1,000,000 tokens). Bootstrap 95% intervals, 1000 resamples, seed 42.
```

`--format json` emits the same figures under `verdict`, `arms.<variant>.per_task`, `arms.<variant>.cost_per_solved_task`, `intervals`, and `pairing`. Schema version is `0.1`. `pairing.metrics.cost` has `mean_difference`, `interval`, `includes_zero`, `relative_change_percent`, and `relative_interval`.

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
