# Changelog

Los cambios notables de este proyecto se anotan en este fichero.

El formato es [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added

- v0.2: el coste separa la entrada ordinaria, la salida, la lectura de caché y la escritura de caché. La escritura de Anthropic distingue 5 minutos y 1 hora. En OpenAI, `prompt_tokens` e `input_tokens` ya incluyen `cached_tokens`, y esa lectura se resta antes de cobrar. En Anthropic, `cache_read_input_tokens` y `cache_creation_input_tokens` van aparte de `input_tokens` y se suman. La tabla `2026-10-29` trae `cache_read`, `cache_write_5m` y `cache_write_1h` solo donde la página oficial de OpenAI o de Anthropic publica el precio, con `source` y `as_of`. Si falta esa tarifa, se usa la de entrada y el informe lo nombra. El informe (Markdown y JSON) muestra el desglose y el ahorro frente a pagar la caché a precio de entrada. Una traza v0.1 sin campos de caché conserva el coste. Las escrituras de OpenAI a 30 minutos y a 12 horas no tienen precio en esta tabla: si `cache_write_tokens` viene distinto de cero, la traza se rechaza.
- v0.2: comparación A/B emparejada por `task_id`. Si las dos variantes comparten algún `task_id`, el informe da la diferencia por tarea (coste, tokens y pasos), la media, un intervalo de confianza del 95 % por bootstrap y el cambio relativo en % con su intervalo. El modo por defecto empareja cuando hay al menos un id en común; si no hay ninguno, se mantiene la comparación no emparejada y se avisa en el informe y en stderr. `--paired` y `--unpaired` fuerzan el modo. La semilla y el número de remuestreos siguen siendo `--seed` y `--bootstrap` (por defecto 42 y 1000).
- v0.2: `agentcost import claude-code` y `agentcost import codex` leen los logs locales (el mismo formato que ccusage) y convierten cada sesión en una tarea. El `task_id` es el `sessionId` o el id del rollout, así que dos `--variant` con el mismo id entran en la comparación emparejada. Solo se guardan los números de uso. Claude deduplica `message.id` + `requestId` y mapea la caché de Anthropic. Codex usa `last_token_usage` cuando el acumulado avanza y resta `cached_input_tokens` de la entrada. Un modelo que no está en la tabla se avisa y no recibe un precio inventado. `costUSD`, si viene en el log, se copia como `logged_cost_usd` y no se cobra.

### Fixed

- `agentcost report --format both --output RUTA` rechaza una ruta que ya termina en `.json`. Antes el JSON pisaba al Markdown en el mismo fichero. Ahora el proceso sale con código 1, el stderr nombra la ruta y no se crea el fichero. Para los dos formatos usa una ruta como `informe.md` o `informe`. Si solo quieres JSON, usa `--format json --output informe.json`.
