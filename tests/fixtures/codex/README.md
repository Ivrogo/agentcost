# Synthetic Codex CLI rollouts

These files are not real Codex sessions. They follow the rollout shape ccusage reads (`session_meta`, `turn_context`, `event_msg` / `token_count` with `total_token_usage` and `last_token_usage`), checked against `ccusage` `rust/adapters/codex` at commit `757b457`. Names start with `rollout-synthetic` so a directory scan picks them up, and each `session_meta.payload.synthetic` flag is `true`.

`response_item` lines carry the marker `SYNTHETIC_PROMPT_DO_NOT_KEEP`. Import must drop that text and keep token counts only.

`rollout-synthetic-a.jsonl` repeats the second `token_count` snapshot. The cumulative total does not advance, so the copy is not a second turn. `rollout-synthetic-b.jsonl` is a separate one-turn session on `gpt-4o`.
