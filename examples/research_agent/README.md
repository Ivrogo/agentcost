# Synthetic research-agent sample

Eight made-up question ids (`q01`–`q08`). The file records token counts and tool steps only. It does not contain queries, pages, or model text.

- `A` uses `gpt-4o-mini`. Each attempt is search, then fetch, then an answer call. `q03` errors on fetch, spends a planning call, and succeeds on a second run.
- `B` uses `gpt-4o`. Each attempt is search, then an answer call. `q08` ends in an error and stays unsolved.

```bash
agentcost report examples/research_agent/traces.jsonl --compare A B
```

`otel_fragment.json` is one OTLP/JSON trace for the same shape of work. The `invoke_agent` span carries a large usage figure on purpose: agentcost drops that wrapper when the trace also has chat and tool spans, so those tokens are not billed twice. The fragment is not part of the A/B sample.
