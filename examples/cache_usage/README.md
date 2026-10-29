# Cache usage constructed from documented API responses

These two lines are not a live call. Each `usage` object is copied from a published example and wrapped with the agentcost fields (`task_id`, `variant`, `run_id`, `model`, `status`, `provider`).

- `openai` / `gpt-4o` uses the Chat Completions usage from OpenAI's [Prompt Caching in the API](https://openai.com/index/api-prompt-caching/) (1 October 2024): `prompt_tokens` 2006 already includes `cached_tokens` 1920, `completion_tokens` 300, `total_tokens` 2306. Ordinary input is 86. The bundled read price is $1.25 per million, so this call costs $0.005615 and the cache saves $0.0024 against the input rate.
- `anthropic` / `claude-sonnet-4` uses the usage object from Anthropic's [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) guide: `input_tokens` 2048 does not include the cache. Reads are 1800. Writes are 248, split into 148 at 5 minutes and 100 at 1 hour. Output is 503. With the bundled Sonnet 4 rates this call costs $0.015384. Net cache savings against the input rate are $0.004449 (reads are cheaper than input; the two writes are a premium).

```bash
agentcost report examples/cache_usage/traces.jsonl --compare openai anthropic
```

The sample has one task per variant and the task ids differ, so the comparison is unpaired and the verdict is inconclusive. The report says there is no shared `task_id`. The cost rows are the point of the file.
