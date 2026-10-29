# Informe JSON

`--format json` escribe el mismo informe en JSON, con veredicto, ramas e intervalos, para que otra herramienta lo lea sin interpretar la tabla.

## Sub-features

- `report-json-ab` emite el JSON del caso `examples/research_agent/traces.jsonl` comparando A con B.
- `report-json-fields` deja el veredicto `better` y los costes por tarea resuelta en campos estables.

## How to get to it (user POV)

- En la terminal: `agentcost report <traza.jsonl> --compare A B --format json`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- La traza es `$REPO/examples/research_agent/traces.jsonl`.

- **Informe JSON.** Pide el JSON de A frente a B. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" report-json -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B --format json`. `$EVIDENCE/report-json.exit` es `0` y stderr está vacío.
- **Veredicto y ramas.** El stdout es JSON. Contiene `"schema_version": "0.1"`, `"verdict": "better"`, `"compare": [` seguido de `"A"` y `"B"`, `"cost_per_solved_task": 0.000498375` en la rama A y `"cost_per_solved_task": 0.0104` en la rama B. La rama A tiene `"tasks": 8` y `"successful_tasks": 8`. La rama B tiene `"tasks": 8` y `"successful_tasks": 7`.
- **Emparejamiento.** El mismo JSON trae `"mode": "paired"`, `"pairs": 8` y `"includes_zero": false` dentro de `pairing.metrics.cost`. `pairing.warning` es `null`. stderr sigue vacío: los ocho `task_id` están en las dos variantes.
- **Prueba.** Conserva `$EVIDENCE/report-json.txt` y `$EVIDENCE/report-json.stdout.txt`. Vuelve a parsear el stdout con el Python del mismo venv; no te fíes de que el proceso haya salido 0.

## Gotchas

- Sin `--format json` la salida es Markdown y `json.loads` falla. Eso no verifica este feature.
- El auxiliar sale 0 cuando guarda la evidencia. El 0 de la CLI está en `report-json.exit`.
- `0.000498375` y `0.0104` son los números de la tabla `2026-10-01` sobre esta traza. Si la tabla o la traza cambian, actualiza las cifras.
- Este feature es la prueba de punta a punta de la skill. Los otros features siguen siendo obligatorios cuando el mapa se recorre entero.
