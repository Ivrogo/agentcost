# Changelog

Los cambios notables de este proyecto se anotan en este fichero.

El formato es [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added

- v0.2: el coste separa la entrada ordinaria, la salida, la lectura de caché y la escritura de caché. La escritura de Anthropic distingue 5 minutos y 1 hora. En OpenAI, `prompt_tokens` e `input_tokens` ya incluyen `cached_tokens`, y esa lectura se resta antes de cobrar. En Anthropic, `cache_read_input_tokens` y `cache_creation_input_tokens` van aparte de `input_tokens` y se suman. La tabla `2026-10-29` trae `cache_read`, `cache_write_5m` y `cache_write_1h` solo donde la página oficial de OpenAI o de Anthropic publica el precio, con `source` y `as_of`. Si falta esa tarifa, se usa la de entrada y el informe lo nombra. El informe (Markdown y JSON) muestra el desglose y el ahorro frente a pagar la caché a precio de entrada. Una traza v0.1 sin campos de caché conserva el coste. Las escrituras de OpenAI a 30 minutos y a 12 horas no tienen precio en esta tabla: si `cache_write_tokens` viene distinto de cero, la traza se rechaza.
- v0.2: comparación A/B emparejada por `task_id`. Si las dos variantes comparten algún `task_id`, el informe da la diferencia por tarea (coste, tokens y pasos), la media, un intervalo de confianza del 95 % por bootstrap y el cambio relativo en % con su intervalo. El modo por defecto empareja cuando hay al menos un id en común; si no hay ninguno, se mantiene la comparación no emparejada y se avisa en el informe y en stderr. `--paired` y `--unpaired` fuerzan el modo. La semilla y el número de remuestreos siguen siendo `--seed` y `--bootstrap` (por defecto 42 y 1000).
- v0.2: modo CI. `--fail-if-worse` sale con código 3 si la primera variante es peor que la segunda en la métrica (coste por defecto): en emparejado, el veredicto `worse` (al menos 5 pares y el IC del 95 % de la diferencia entero por encima de 0); en no emparejado, el veredicto actual. `--max-regression` (por ejemplo `5` o `5%`) sale con 3 si el límite inferior del IC relativo emparejado supera ese porcentaje; no usa la estimación puntual, y sin pares sale con 1. El 0 es un informe sin regresión, el 1 un error de entrada y el 2 el uso inválido de Typer. `--markdown-summary` escribe un comentario para el PR; `--github-step-summary` lo añade a `$GITHUB_STEP_SUMMARY` si existe. El ejemplo `examples/ci/agentcost.yml` no está en `.github/workflows`.

### Fixed

- `agentcost report --format both --output RUTA` rechaza una ruta que ya termina en `.json`. Antes el JSON pisaba al Markdown en el mismo fichero. Ahora el proceso sale con código 1, el stderr nombra la ruta y no se crea el fichero. Para los dos formatos usa una ruta como `informe.md` o `informe`. Si solo quieres JSON, usa `--format json --output informe.json`.
