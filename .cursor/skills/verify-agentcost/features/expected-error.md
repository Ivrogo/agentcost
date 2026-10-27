# Errores de la CLI

Un formato que no existe y una comparación imposible terminan con un mensaje en stderr y el código 1, sin informe en stdout.

## Sub-features

- `format-invalid` rechaza un `--format` distinto de `md`, `json` y `both`.
- `otel-one-arm` rechaza comparar el fragmento OTel, que solo trae la variante A, contra B.

## How to get to it (user POV)

- En la terminal: `agentcost report <traza.jsonl> --compare A B --format yaml`.
- En la terminal: `agentcost report examples/research_agent/otel_fragment.json --compare A B`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- Existen `$REPO/examples/research_agent/traces.jsonl` y `$REPO/examples/research_agent/otel_fragment.json`.

- **Formato inválido.** Pide `yaml`. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" format-invalid -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B --format yaml`. `$EVIDENCE/format-invalid.exit` es `1`, stdout está vacío y stderr contiene `--format must be md, json, or both`.
- **Fragmento de una sola variante.** Compara A con B sobre el fragmento OTel. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" otel-one-arm -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/otel_fragment.json" --compare A B`. `$EVIDENCE/otel-one-arm.exit` es `1`, stdout está vacío y stderr contiene `variant 'B' has no events in the trace`.
- **Prueba.** Conserva los dos transcripts. Un código 1 con stdout vacío y sin esa frase no demuestra el fallo esperado.

## Gotchas

- El auxiliar sale 0 si guardó la evidencia. El 1 de la CLI está en el fichero `.exit`. Tratar el 0 del auxiliar como éxito de la CLI invalida el feature.
- El mensaje de formato empieza por `--`. `grep --format` se come el patrón como si fuera una opción. Hay que usar `grep -F -e '--format must be md, json, or both'`.
- `otel_fragment.json` no es la muestra A/B. No sustituye a `traces.jsonl` en el informe JSON.
- Este camino no demuestra que se descarte el span `invoke_agent`. Solo demuestra que la CLI carga el fragmento y rechaza la variante ausente. Aflojar la comparación para obtener un veredicto no es una prueba de este feature.
- Un fichero que no existe lo rechaza el propio parser de argumentos, con otro mensaje. No lo mezcles con estos dos fallos.
