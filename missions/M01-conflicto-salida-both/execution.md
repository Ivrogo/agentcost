# Ejecución M01

## Decisiones

- Clase `full`, capacidad `standard`. `model_tier_used`: `standard`.
- Knowledge base sin fichas (`.agents/knowledge/README.md`). Nada que citar como precedente.
- Security Advisor no aplica: no hay autenticación, secretos, despliegue, workflows ni cambios en `pyproject.toml`.
- El rechazo usa `AgentCostError`, ya capturada por `report`. No se añade un tipo de error.
- La condición es `output.with_suffix(".json") == output`, solo con `--format both`, y antes de cualquier `write_text`.
- Review, Validación y Documentación no son de esta sesión. No hay `verification.json`: el veredicto lo emite el validador. Sin `status: passed` la misión no está cerrada.

## Secuencia

1. `plan.md` escrito antes de editar `src/` o `tests/`. Base `6d78799` (`chore/harness-pstack`, igual que `origin/chore/harness-pstack`).
2. Tests de los cuatro criterios en `tests/test_cli.py`, sobre `examples/research_agent/traces.jsonl`.
3. RED del criterio 1, con el código de producción aún sin tocar.
4. Cambio en `_emit_report`. `ruff format` juntó el mensaje en una sola f-string; el texto no cambió.
5. GREEN local. No sustituye al gate de Validación.

## RED

Comando, desde la raíz, con el venv `/tmp/agentcost-dev` (`pip install -e ".[dev]"`, Python 3.12.3), antes de editar `src/agentcost/cli.py`:

```text
pytest -q tests/test_cli.py
```

Salida en `artifacts/pytest-red.txt`: 1 failed, 5 passed. Falla `test_format_both_refuses_output_that_already_ends_in_json` porque `exit_code` es 0. Los otros tres casos nuevos pasan: describen la conducta que ya existía.

## GREEN del codificador

Mismo venv, después del cambio. Salida en `artifacts/pytest-green.txt`.

- `pytest -q` → 29 passed, salida 0.
- `ruff check .` → `All checks passed!`, salida 0.
- `ruff format --check .` → 31 ficheros ya formateados, salida 0.

CLI real del mismo venv, directorio de trabajo `/tmp/agentcost-m01-cli` (fuera del árbol), traza `examples/research_agent/traces.jsonl`. Resumen en `artifacts/cli-coder.txt`.

| Caso | Salida | Qué se observó |
| --- | --- | --- |
| `--format both --output informe.json` | 1 | stderr: `--format both would write Markdown and JSON to the same path: informe.json`. stdout vacío. `informe.json` no existe. |
| `--format both --output informe.md` | 0 | `informe.md` contiene `**Verdict:** better`. `informe.json` tiene `"verdict": "better"`. |
| `--format both --output informe` | 0 | Markdown en `informe`, JSON en `informe.json`, mismo veredicto. |
| `--format json --output informe.json` | 0 | Solo `informe.json`, veredicto `better`, sin `**Verdict:**`. |

## Para el revisor

- Diff funcional: `src/agentcost/cli.py` y `tests/test_cli.py`.
- El mensaje de error está en inglés, como el resto de la CLI.
- No se rechaza `--format json` ni un `--output` cuyo sufijo no sea ya `.json`.
- No se compara con `resolve()` ni se pliega mayúsculas. `.JSON` sigue siendo otra ruta en un sistema que distingue mayúsculas.

## Para el validador

Emitir `missions/M01-conflicto-salida-both/verification.json` repitiendo los checks, sin fiarse de los artefactos de esta sesión. La skill es `verify-agentcost`.

En esta máquina, al codificar, solo estaba Python 3.12 (`/usr/bin/python3.12`). No había `python3.10`, `python3.11` ni `uv`. Si sigue siendo así, esas filas son `skipped` con ese motivo, no `pass`.

Queda sin comprobar aquí, y le toca a Validación:

- `pytest_3_10`, `pytest_3_11`, `pytest_3_12`
- `ruff_check`, `ruff_format` en el venv de desarrollo 3.12
- `clean_install_3_10`, `clean_install_3_11`, `clean_install_3_12` y Doctor en modo `clean`
- `e2e_cli_json` con el feature Informe JSON
- `ci_otros_sistemas` como `skipped` en Linux, con el motivo de la skill

Los cuatro casos de esta misión conviene repetirlos con el `agentcost` del venv limpio y `drive.sh`, leyendo el código en el fichero `.exit` y abriendo los ficheros desde fuera del proceso.

## Para el documentador

Después de Review y Validación en OK. El repositorio no tiene changelog.

- `README.md`, fila de `--output`: hoy dice que el JSON usa la misma ruta con sufijo `.json`, sin decir que la orden sale 1 si esa ruta ya termina en `.json`.
- `.cursor/skills/verify-agentcost/features/report-output.md`, gotcha de `--format both` con sufijo `.json`: describe el fallo antiguo. Hay que alinearlo con el rechazo y no usarlo como conducta esperada.
