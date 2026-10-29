# Informe A/B en Markdown

El informe por defecto resume el coste por tarea de dos variantes y da un veredicto sobre la primera frente a la segunda.

## Sub-features

- `report-md-default` escribe el informe Markdown de `examples/research_agent/traces.jsonl` al comparar A con B.
- `report-md-verdict` muestra el veredicto `better` y los costes por tarea resuelta de las dos ramas.

## How to get to it (user POV)

- En la terminal, desde un directorio que no es el repositorio: `agentcost report <traza.jsonl> --compare A B`.
- El formato por defecto es Markdown. No hace falta `--format`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- La traza es `$REPO/examples/research_agent/traces.jsonl`.

- **Informe por defecto.** Pide el informe de A frente a B. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" report-markdown -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B`. `$EVIDENCE/report-markdown.exit` es `0` y stdout contiene la línea `**Verdict:** better`.
- **Cifras del caso.** En ese mismo stdout están `| Tasks | 8 | 8 |`, `| Successful tasks | 8 | 7 |`, `$0.000498375` y `$0.0104`.
- **Emparejamiento.** El mismo stdout contiene `**Pairing:** paired (8 pairs).` y `The cost interval does not include 0.` stderr está vacío.
- **Prueba.** Conserva `$EVIDENCE/report-markdown.txt`. Ahí quedan el comando, el código y el informe completo.

## Gotchas

- El veredicto es de la primera variante frente a la segunda. `--compare B A` no es este caso.
- El guion de los percentiles es un guion largo (`–`). Afirma las líneas de arriba, no reescribas la tabla a mano.
- Estas cifras corresponden a la traza de ejemplo y a las tarifas de entrada y salida que ya estaban en la tabla `2026-10-01`. El fichero pasó a `2026-10-29` al añadir precios de caché; esta traza no tiene tokens de caché, así que el coste no cambia. Si cambian, actualiza este feature; no aflojes la comprobación.
- Lanzar el comando desde la raíz del repo no demuestra que el ejecutable instalado funcione fuera del árbol. El directorio de trabajo es `$ROOT/work`.
