# Review de código — M03

Self-review de la misma sesión. El encargo pide esa revisión antes de dar el PR por listo; no hay un segundo revisor en esta ejecución. El diff funcional es `src/agentcost/local_logs.py`, `src/agentcost/cli.py`, `src/agentcost/__init__.py` y `tests/test_local_logs.py`, más las fixtures. No entran `report.py`, `pairing.py`, `parse.py`, `pricing.py` ni `models.py`.

Regla cargada: `harness.mdc`. Se leyó `security-advisor.mdc`; sus globs no entran.

Skills cargadas: `verify-agentcost`, `principle-prove-it-works`, `principle-fix-root-causes`, `principle-subtract-before-you-add`.

## Veredicto

Aprobado. No queda un fallo bloqueante. No se reabre Implementación.

## Requisitos

1. Las fixtures reales de Claude, 6 líneas con uso y 3 duplicados, dan los totales de `totales.json` después de deduplicar `message.id` + `requestId`. La entrada no se resta: es el `usage` de Anthropic. La escritura de 1 hora cae en `cache_write_1h_tokens`.
2. Codex no suma el snapshot repetido. Si el acumulado avanzó, el turno es `last_token_usage` aunque no coincida con la resta de totales. Sin `last_token_usage`, el turno es la resta. `cached_input_tokens` sale de `input_tokens`. `reasoning_output_tokens` no se suma a la salida. El modelo sale de `turn_context`.
3. Una sesión es un `task_id`. El mismo id importado con `--variant A` y `--variant B` y `--paired` da `pairs: 1`. Dos sesiones distintas no comparten id y `--paired` sale 1.
4. `claude-sonnet-5` y `claude-fable-5` no están en la tabla. El informe los nombra con `--allow-unpriced` y, sin el flag, sale 1. No se añadió ninguna fila a `prices.json`.
5. `CLAUDE_CONFIG_DIR` y `CODEX_HOME` sustituyen al directorio de casa. Una ruta explícita no lee la otra. Un enlace que resuelve fuera del directorio escaneado no se lee. El JSONL no contiene el texto del mensaje ni `costUSD` como coste.
6. El informe de `examples/research_agent` sigue en `better`, `0.000498375` y `0.0104`, ahora emparejado por los ocho `task_id` que ya compartían las variantes.

## Causa y calidad

El fallo que había que evitar es contar dos veces el mismo token: el duplicado de Claude y el acumulado de Codex. La deduplicación y la resta ocurren al leer el log, antes de emitir los cubos disjuntos que el #7 ya cobra. No hay un segundo contador de caché.

## Alcance

No se tocan `pyproject.toml`, workflows, secretos ni autenticación. Security Advisor no aplica. El código del veredicto y de `pairing.py` no cambia.

## Observaciones que no bloquean

- Un replay de sidechain con otro `requestId` se cuenta otra vez. ccusage lo descarta. Esta versión no, y el README lo dice.
- No se leen `archived_sessions`, compactions ni `~/.config/claude`.
- `logged_cost_usd` viaja en el JSONL importado y el informe no lo muestra. El coste es el de la tabla.
