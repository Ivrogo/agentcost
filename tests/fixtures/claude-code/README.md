# Anonymized Claude Code sessions

`claude-session-a.jsonl` and `claude-session-b.jsonl` are real Claude Code transcripts reduced to usage. Message text is already gone. Identifiers are hashes and timestamps are shifted. Together they contain 6 assistant lines with `message.usage` and 3 duplicates of those lines.

`totales.json` is the expected per-model sum after deduplicating `message.id` + `requestId`. `costUSD` is absent on every line, so its total is 0.
