# Informe escrito a fichero

`--output` guarda el informe en un fichero y no lo repite por stdout. Quien lo pide puede leer ese fichero después, sin el proceso que lo escribió.

## Sub-features

- `report-output-json` escribe el JSON en la ruta pedida.
- `report-output-silent` deja stdout vacío cuando el informe va al fichero.

## How to get to it (user POV)

- En la terminal: `agentcost report <traza.jsonl> --compare A B --format json --output <ruta.json>`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- `$EVIDENCE/report-output/` existe y no contiene `report.json`.
- La traza es `$REPO/examples/research_agent/traces.jsonl`.

- **Escribir el fichero.** Pide el JSON en una ruta. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" report-output -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B --format json --output "$EVIDENCE/report-output/report.json"`. `$EVIDENCE/report-output.exit` es `0`.
- **Stdout vacío.** `$EVIDENCE/report-output.stdout.txt` está vacío.
- **Lectura posterior.** Abre `$EVIDENCE/report-output/report.json` con el Python del venv, fuera de `agentcost`. El objeto tiene `"verdict": "better"` y ramas `A` y `B`.
- **Prueba.** Conserva el transcript y el `report.json`. El fichero escrito forma parte de la evidencia.

## Gotchas

- Comprobar solo el código 0 no demuestra que el fichero exista. Hay que abrirlo.
- `--format both` con una ruta que ya termina en `.json` no es este feature: Markdown y JSON acabarían en el mismo path. No lo uses como atajo.
- La limpieza no debe borrar `$EVIDENCE/report-output/report.json`.
