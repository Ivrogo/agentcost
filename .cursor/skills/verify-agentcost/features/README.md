# Mapa de verificación de agentcost

Este directorio es la fuente de la verificación de cara al usuario. Lee el índice y sigue el fichero del feature. La puesta en marcha, Doctor y el volcado a `verification.json` están en `../SKILL.md`.

## Precondiciones de partida

- `$REPO` es la raíz del checkout (`git rev-parse --show-toplevel`).
- `$ROOT` es el directorio de esta ejecución, creado en Launch.
- `$EVIDENCE` es `$ROOT/evidence`. La limpieza no lo borra.
- `$VENV` es un venv limpio (`pip install .`) para el que Doctor ha pasado con `MODE=clean`.
- El directorio de trabajo de la CLI es `$ROOT/work`, vacío y fuera del árbol de fuentes.
- Pytest y ruff no son features de usuario. Se lanzan desde `$REPO` con el venv de desarrollo, como dice la skill.
- No conduzcas un `agentcost` que no haya instalado esta ejecución.

## Convenciones al conducir

- Empieza cada receta desde esas precondiciones.
- Trata cada comando como literal. No cambies comillas ni flags.
- Lanza la CLI solo a través de `$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh`.
- El auxiliar sale 0 si escribió la evidencia. El código de la CLI se lee en `$EVIDENCE/<nombre>.exit`.
- Una mutación (`--output`) se comprueba leyendo el fichero otra vez, desde fuera del proceso.
- No borres la evidencia al limpiar.
- Anota en cada artefacto el id del feature y la entrada usada.

## Prueba y omisiones

- Guarda la orden y el estado resultante, no solo el pantallazo final.
- La prueba de CLI incluye comando, stdout, stderr y código de salida.
- Si una entrada no se puede alcanzar, registra el comando intentado y la precondición que faltó.
- No des por verificada una entrada que se saltó usando otro camino.

## Contrato de cada feature

Cada fichero empieza con un H1 y un párrafo. Después van exactamente cuatro H2, en este orden: `Sub-features`, `How to get to it (user POV)`, `Driving it with verify-agentcost`, `Gotchas`.

## Features

- [Informe A/B en Markdown](./report-markdown.md) cubre el informe por defecto sobre `examples/research_agent/traces.jsonl`.
- [Informe JSON](./report-json.md) cubre `--format json` con el mismo caso y el veredicto `better`.
- [Informe escrito a fichero](./report-output.md) cubre `--output` y la lectura posterior del fichero.
- [Errores de la CLI](./expected-error.md) cubre un formato inválido y el fragmento OTel de una sola variante.
- [Ayuda](./help.md) cubre `agentcost --help` y `agentcost report --help`.
- [Importar logs locales](./import-local-logs.md) cubre `agentcost import` de Claude Code y de Codex, y el informe que sale de esa traza.
