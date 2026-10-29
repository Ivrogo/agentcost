# Logs locales de Claude Code y de Codex

## Contexto

`agentcost import` convierte un log local en eventos. El `task_id` es el id de la sesión, y `--variant` es el brazo. La comparación emparejada junta los brazos que comparten ese id.

## Motivo

El uso no se vuelve a interpretar en el informe. Claude Code trae el `usage` de Anthropic: `input_tokens` no incluye la caché, así que lectura y escritura se suman con la regla que ya aplica `provider: anthropic`. Codex trae `cached_input_tokens` dentro de `input_tokens`, así que se resta, como OpenAI. `total_token_usage` es un acumulado: si avanzó, el turno es `last_token_usage`; si no, restar el total anterior da cero y un snapshot repetido no se suma. `reasoning_output_tokens` ya va dentro de `output_tokens`.

Sin modelo en el rollout no se rellena `gpt-5`: un nombre inventado podría heredar un precio de la tabla. `costUSD` del log no es el coste. Una escritura de caché de Codex distinta de cero se rechaza, porque ya va dentro de `input_tokens` y la tabla no tiene esa tarifa.
