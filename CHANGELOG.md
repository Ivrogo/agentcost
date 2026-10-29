# Changelog

Los cambios notables de este proyecto se anotan en este fichero.

El formato es [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added

- v0.2: el coste separa la entrada ordinaria, la salida, la lectura de caché y la escritura de caché. La escritura de Anthropic distingue 5 minutos y 1 hora. En OpenAI, `prompt_tokens` e `input_tokens` ya incluyen `cached_tokens`, y esa lectura se resta antes de cobrar. En Anthropic, `cache_read_input_tokens` y `cache_creation_input_tokens` van aparte de `input_tokens` y se suman. La tabla `2026-10-29` trae `cache_read`, `cache_write_5m` y `cache_write_1h` solo donde la página oficial de OpenAI o de Anthropic publica el precio, con `source` y `as_of`. Si falta esa tarifa, se usa la de entrada y el informe lo nombra. El informe (Markdown y JSON) muestra el desglose y el ahorro frente a pagar la caché a precio de entrada. Una traza v0.1 sin campos de caché conserva el coste. Las escrituras de OpenAI a 30 minutos y a 12 horas no tienen precio en esta tabla: si `cache_write_tokens` viene distinto de cero, la traza se rechaza.

### Fixed

- `agentcost report --format both --output RUTA` rechaza una ruta que ya termina en `.json`. Antes el JSON pisaba al Markdown en el mismo fichero. Ahora el proceso sale con código 1, el stderr nombra la ruta y no se crea el fichero. Para los dos formatos usa una ruta como `informe.md` o `informe`. Si solo quieres JSON, usa `--format json --output informe.json`.
