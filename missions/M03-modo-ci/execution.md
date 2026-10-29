# Ejecución M03

## Base

`origin/main` está en `93d2a32` (PR #8, que ya incluye el #7). La rama avanzó en fast-forward hasta ese commit. No hubo rebase ni force-push. Un `git fetch origin main` posterior no trajo commits nuevos.

## RED

`pytest -q tests/test_gate.py` antes de `gate.py` y de los flags: 17 failed. Los flags no existían y faltaba `examples/ci/agentcost.yml`.

## GREEN

Implementación en `src/agentcost/gate.py` y en la CLI. `pytest -q` con el venv `/tmp/agentcost-dev`: 86 passed. `ruff check .` y `ruff format --check .` en verde.

## Review

La pasada de review encontró que `--markdown-summary` podía pisar `--output`. Se rechaza esa ruta antes de escribir, con código 1. Tras el arreglo, `pytest -q` sigue en 86 passed. Sin bloqueantes abiertos. Ver `review.md`.

## Validación

Script en el entorno, evidencia bajo `/tmp/agentcost-verify-20261029103543-3751`. Resumen versionado en `evidencias.log`.

- pytest 3.10, 3.11 y 3.12: 86 passed, exit 0.
- ruff check y ruff format con el venv 3.12: exit 0.
- `pip install .` en venv limpio 3.10, 3.11 y 3.12. Doctor `clean` en los tres.
- CLI limpia 3.12, cwd fuera del árbol: informe JSON exit 0 (`better`, A `0.000498375`, B `0.0104`, 8 pares).
- `--compare A B --fail-if-worse --max-regression 5`: exit 0. El resumen y `$GITHUB_STEP_SUMMARY` coinciden.
- `--compare B A` con los mismos flags: exit 3. El resumen dice `regression`.
- `--format yaml`: exit 1.
- actionlint 1.7.12 sobre `examples/ci/agentcost.yml`: exit 0, sin avisos.

macOS, Windows y pipx no se ejecutan en esta máquina. Los cubre `.github/workflows/ci.yml`.

`verification.json` apunta al commit de código `133cd76267861877e785e096785c00c330dbacf1`. Este registro no cambia la CLI.
