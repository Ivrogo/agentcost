# Puerta de CI

`agentcost report` puede salir con código 3 cuando la primera variante es peor que la segunda, y escribe un resumen Markdown para un pull request.

## Sub-features

- `ci-pass` compara A con B en `examples/research_agent/traces.jsonl` con `--fail-if-worse` y `--max-regression 5`. A es más barata. Sale 0 y el resumen dice `pass`.
- `ci-fail` compara B con A sobre la misma traza. B es más cara. Sale 3 y el resumen dice `regression`. El informe sigue escribiéndose.

## How to get to it (user POV)

- En la terminal: `agentcost report examples/research_agent/traces.jsonl --compare A B --fail-if-worse --max-regression 5 --markdown-summary pass.md --github-step-summary`.
- En la terminal: `agentcost report examples/research_agent/traces.jsonl --compare B A --fail-if-worse --max-regression 5 --markdown-summary fail.md`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- La traza es `$REPO/examples/research_agent/traces.jsonl`.

- **Pasa.** Pide la puerta con A primero. Ejecuta `GITHUB_STEP_SUMMARY="$ROOT/work/ci-pass-step.md" "$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" ci-pass -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B --fail-if-worse --max-regression 5 --markdown-summary "$ROOT/work/ci-pass.md" --github-step-summary`. `$EVIDENCE/ci-pass.exit` es `0` y stderr está vacío. `$ROOT/work/ci-pass.md` y `$ROOT/work/ci-pass-step.md` son el mismo texto. Contienen `<!-- agentcost-ci -->`, `**Verdict:** better`, `**Gate:** pass` y `**Mode:** paired (8 pairs)`.
- **Falla.** Pide la puerta con B primero. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" ci-fail -- "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare B A --fail-if-worse --max-regression 5 --markdown-summary "$ROOT/work/ci-fail.md"`. `$EVIDENCE/ci-fail.exit` es `3`. Stdout contiene `**Verdict:** worse`. `$ROOT/work/ci-fail.md` contiene `**Gate:** regression` y `**Mode:** paired (8 pairs)`. Stderr no está vacío.
- **Prueba.** Vuelve a leer los Markdown desde fuera del proceso. El 0 del auxiliar no es el código de la CLI: está en el fichero `.exit`.

## Gotchas

- Sin los flags de puerta, el mismo `worse` sale 0. Este feature no cubre ese camino.
- `drive.sh` solo reenvía `GITHUB_STEP_SUMMARY` si el proceso que lo llama la tiene puesta. El prefijo de la orden de `ci-pass` hace eso.
- El código 1 sigue siendo un error de entrada (`expected-error`). El 3 no lo sustituye.
- El resumen de `ci-fail` es el comentario que se pega en el PR. No hace falta reproducir aquí cada cifra del IC: el fichero escrito es la evidencia.
