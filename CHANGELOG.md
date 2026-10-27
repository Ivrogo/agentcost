# Changelog

Los cambios notables de este proyecto se anotan en este fichero.

El formato es [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Fixed

- `agentcost report --format both --output RUTA` rechaza una ruta que ya termina en `.json`. Antes el JSON pisaba al Markdown en el mismo fichero. Ahora el proceso sale con código 1, el stderr nombra la ruta y no se crea el fichero. Para los dos formatos usa una ruta como `informe.md` o `informe`. Si solo quieres JSON, usa `--format json --output informe.json`.
