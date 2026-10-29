# M03 — Importar logs locales de Claude Code y de Codex CLI

## Clase y capacidad

- Clase: `full`. Entra un origen de trazas nuevo y un subcomando de la CLI. No es un retoque de un fichero ni documentación repartida.
- Capacidad: `standard`. La lógica cabe en un módulo nuevo y en el cableado de la CLI. No se reescribe el coste, el veredicto ni el emparejamiento. No hay autenticación, concurrencia, migraciones ni secretos.
- `model_tier_used`: `standard`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultada `.agents/knowledge/README.md`, [formato-both-salida-json.md](../../.agents/knowledge/formato-both-salida-json.md) y [cache-token-accounting.md](../../.agents/knowledge/cache-token-accounting.md).

- La ficha del sufijo `.json` no aplica: este cambio no toca `--format both`.
- La ficha de caché sí aplica. Los cubos de `Event` (entrada ordinaria, lectura, escritura a 5 minutos, escritura a 1 hora, salida) ya no se solapan. Claude Code trae el `usage` de Anthropic: la caché va aparte de `input_tokens` y se suma. Codex trae `cached_input_tokens` dentro de `input_tokens`, igual que OpenAI, y se resta. No se añaden campos nuevos a `Event` ni a la tabla de precios.

## Qué no se toca

Otro agente cambia la comparación A/B emparejada. Aquí no se editan `report.py`, `pricing.py`, `models.py` ni `parse.py`, salvo para reutilizar `_anthropic_usage` o el JSONL canónico que `parse_jsonl` ya acepta. No se sincronizan precios con LiteLLM ni tokencost. No hay adaptador de Langfuse ni de Phoenix. No se usa codeine-mcp. No se menciona iRG.

Security Advisor: el cambio no toca los globs de `.cursor/rules/security-advisor.mdc` (auth, secretos, workflows, Docker, deploy, `pyproject.toml`). No aplica.

## Referencia de formato (ccusage, commit `757b457`)

No se copia el código. Se confirma el comportamiento que esta misión necesita.

- Claude, `rust/adapters/claude/src/lib.rs`, `usage_dedupe_hash`: con `message.id` y `requestId`, la clave es esa pareja y vale entre sesiones. Sin `requestId`, un id `msg_` o `resp_` se colapsa por sesión aunque cambie la marca de tiempo; otro id también lleva la marca de tiempo. `is_valid_usage_entry` no filtra `type`. El README del adaptador (`rust/adapters/claude/src/README.md`) describe además el replay de sidechain con otro `requestId`.
- Claude, `rust/adapters/claude/src/paths.rs`, `claude_paths`: si existe `CLAUDE_CONFIG_DIR`, son rutas separadas por comas y no se usa el directorio de casa. Cada ruta es un config con `projects/`, o el propio directorio `projects/`. Si la variable está puesta y ninguna ruta vale, es un error.
- Codex, `rust/adapters/codex/src/parser.rs`, `codex_token_count_usage`: `total_token_usage` es acumulado y `last_token_usage` es el delta del turno. Si el acumulado avanzó (o no hay acumulado), se usa `last_token_usage`. Si no, se resta el acumulado anterior. Un snapshot repetido no suma. `reasoning_output_tokens` ya va dentro de `output_tokens`. El modelo sale de `turn_context` (`payload.model`) y, si el evento lo trae, de `info.model`.
- Codex, `rust/adapters/codex/src/README.md` y `paths.rs`: los ficheros son `${CODEX_HOME:-~/.codex}/sessions/**/rollout-*.jsonl`. `CODEX_HOME` también admite comas. ccusage lee además `archived_sessions`, `~/.config/claude` y compactions. Esta misión no: el encargo nombra `~/.claude/projects/**/` y `~/.codex/sessions/**/rollout-*.jsonl`.

La fixture `apps/ccusage/test/fixtures/codex/sessions/project-alpha/session-alpha.jsonl` fija la forma del rollout: `turn_context`, luego `event_msg` / `token_count` con `last_token_usage` y `total_token_usage`.

## Alcance

1. Claude Code. Solo líneas `type: assistant` con `message.usage`. El resto, incluido el texto del mensaje, no se guarda. Se deduplica por `message.id` + `requestId` como el hash exacto de ccusage, también el caso sin `requestId`. No se implementa el replay de sidechain con otro `requestId`: la clave que pide el encargo no los une, y las fixtures no lo traen. Se deja escrito en el README.
2. El `usage` de Claude se mapea con la regla Anthropic ya implementada en el PR #7: `input_tokens` se queda, `cache_read_input_tokens` es lectura, y `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` son las dos escrituras. Sin desglose, el total de `cache_creation_input_tokens` es escritura a 5 minutos. `costUSD`, si viene, se copia al JSONL importado como `logged_cost_usd` y no entra en el coste. El coste lo calcula la tabla.
3. Codex. Por fichero se mantiene el acumulado. `cached_input_tokens` se resta de `input_tokens`. `reasoning_output_tokens` no se suma a la salida. `cache_write_input_tokens` o `cache_creation_input_tokens` distintos de cero se rechazan: van dentro de `input_tokens` y esta tabla no publica esa tarifa de escritura, igual que el `cache_write_tokens` de OpenAI del #7. No se inventa el modelo `gpt-5` cuando falta `turn_context`: el evento queda sin modelo y el informe avisa.
4. Una sesión es una tarea y una ejecución. En Claude el `task_id` es `sessionId` y, si falta, el nombre del fichero. En Codex es `payload.id` de `session_meta` y, si falta, el nombre del rollout. `run_id` es ese mismo id. La variante es `--variant` (por defecto `default`).
5. CLI, en el estilo de Typer actual: `agentcost import claude-code|codex [RUTA] --variant NOMBRE [--output FICHERO]`. Sin ruta se usan los directorios de arriba. Con ruta se lee ese fichero o ese directorio y nada más. La salida es JSONL canónico, para `agentcost report`.
6. Un modelo que no está en la tabla no gana un precio. Las fixtures reales usan `claude-sonnet-5` y `claude-fable-5`. El informe, con `--allow-unpriced`, los nombra y los cobra a cero. Sin el flag, el comando sale 1 y los nombra en stderr.

## Fuera de alcance, a propósito

- Sidechain con otro `requestId`, iteraciones `advisor_message`, `archived_sessions`, `~/.config/claude`, compactions de Codex, `token_usage_record` y el fallback `gpt-5` / `codex-auto-review`.
- No se lee ni se escribe fuera de la ruta indicada al adaptador. Un enlace que resuelva fuera del directorio raíz se salta.
- No se sube ningún log. Las fixtures de Claude son las adjuntas, ya anonimizadas. La de Codex es sintética.

## Criterios de aceptación

- Las dos sesiones reales, juntas, dan los totales de `totales.json` después de quitar los 3 duplicados (6 líneas con uso).
- Una sesión es un `task_id`. Dos importaciones con `--variant` distinto se comparan con `report`. Si el id coincide, `--paired` cuenta el par. Si no, `--paired` sale 1. No se modifica `pairing.py`: el id de la sesión es el `task_id` que esa comparación ya lee.
- Codex: dos `token_count` con acumulado creciente cuentan el delta una vez; un snapshot repetido no suma; la lectura cacheada no se cobra también como entrada; el razonamiento no se suma a la salida; el modelo es el de `turn_context`.
- `CLAUDE_CONFIG_DIR` y `CODEX_HOME`, si existen, sustituyen al directorio de casa y no se leen los dos.
- Modelo ausente de la tabla: el informe lo nombra. No se añade ninguna fila a `prices.json`.
- El JSONL importado no contiene el texto de los mensajes.

## Pruebas

Unitarias en `tests/test_local_logs.py` sobre las fixtures y sobre ficheros temporales. Punta a punta: la CLI en un venv limpio, desde un directorio de trabajo fuera del árbol, sobre las fixtures de Claude y sobre la de Codex. La matriz de la skill `verify-agentcost` (pytest 3.10–3.12, ruff, instalación limpia, informe JSON de `examples/research_agent`) sigue siendo obligatoria: este cambio no puede romper el informe que ya existe.
