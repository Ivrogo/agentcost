# Ejecución M04

## Base

`origin/main` en `84bc848` (PR #10). Fast-forward desde `96ffb9d`. Rama `cursor/ci-inconclusive-exit-4a4d`. El PR #11 sigue abierto; no se toca el pricing.

## Plan

`plan.md` escrito antes de editar `src/` o `tests/`.

## RED

`pytest -q tests/test_gate.py` con el venv `/tmp/agentcost-dev` antes de la implementación: 7 failed, 19 passed. El flag no existía (Typer salía 2). El inconcluso sin pares y con `--max-regression` salía 1. Con `--fail-if-worse` y menos de 5 pares, stderr estaba vacío.

## GREEN

`evaluate_gate` distingue el inconcluso. `pytest -q` : 107 passed. `ruff check .` y `ruff format --check .` en verde.

## Review

Sin bloqueantes. El umbral que no se puede aplicar sigue en 1 si el otro chequeo ya encontró regresión. Ver `review.md`.

## Validación

Entorno `/tmp/agentcost-verify-20261029110941-3533`. Resumen en `evidencias.log`.

- pytest 3.10, 3.11 y 3.12: 107 passed, exit 0. Se repitió después de asertar el comentario del workflow: otra vez 107 passed.
- ruff check y ruff format con el venv 3.12: exit 0.
- `pip install .` en venv nuevo de 3.10, 3.11 y 3.12. Doctor `clean` en los tres.
- CLI limpia 3.12, cwd fuera del árbol: informe JSON exit 0 (`better`, A `0.000498375`, B `0.0104`, 8 pares).
- `--compare A B --fail-if-worse --max-regression 5`: exit 0.
- `--compare B A` con los mismos flags: exit 3.
- `examples/cache_usage/traces.jsonl` con `--fail-if-worse --max-regression 5`: exit 0 y el aviso de que no hay `task_id` compartido ni intervalo relativo.
- La misma muestra con `--fail-if-worse --fail-if-inconclusive`: exit 4.
- `--fail-if-inconclusive` sin `--fail-if-worse`: exit 1, sin informe.
- `agentcost report --help` lista el flag nuevo.

macOS, Windows y pipx no se ejecutan en esta máquina. Los cubre `.github/workflows/ci.yml`.

## Merge de origin/main

El PR #11 llegó a `main` (`2f4aa54`) durante el trabajo. `git merge origin/main` creó `25957b6` (padres `763e855` y `2f4aa54`), sin rebase, sin force-push y sin conflictos. No se tocaron las tarifas de `claude-sonnet-5` ni de `claude-fable-5`. Pytest en 3.10, 3.11 y 3.12: 108 passed. Ruff en verde. El e2e limpio se repitió: mismos códigos y mismas cifras del caso `research_agent`.

## Documentación

README, CHANGELOG (cambio incompatible), comentario en `examples/ci/agentcost.yml`, knowledge `modo-ci.md` y el mapa de `ci-gate`. No cambia el cálculo. No se reabre la review de código: el único test nuevo es un aserto del comentario, y pytest se repitió.
