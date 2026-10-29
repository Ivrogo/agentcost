# M03 — Ejecución

## Decisiones

- Clase `full`, capacidad `standard`. Plan escrito antes del código de producción.
- `origin/main` se fusionó dos veces con fast-forward, sin rebase ni force-push: `9587315` (PR #7) y `93d2a32` (PR #8). La rama parte de `main`. El PR no depende de otro PR abierto.
- El coste no se recalcula aquí. Claude reutiliza `_anthropic_usage`. Codex resta `cached_input_tokens` y emite cubos disjuntos.
- `costUSD` del log se conserva como `logged_cost_usd` en el JSONL importado. `report` lo ignora.
- Sin modelo en Codex no se rellena `gpt-5`.
- Escritura de caché de Codex distinta de cero: error, por la misma razón que OpenAI en el #7.
- Sidechain con otro `requestId`, compactions y `archived_sessions` quedan fuera. El README lo dice.
- El `task_id` es el id de la sesión. `pairing.py` no se toca. `--variant` distingue el brazo, así que el mismo id en las dos variantes entra en `--paired`.

## Comandos

RED, antes del módulo (`/tmp/agentcost-dev`, Python 3.12):

```text
pytest -q tests/test_local_logs.py
ModuleNotFoundError: No module named 'agentcost.local_logs'
```

GREEN, misma máquina, tras el adaptador y la CLI:

```text
ruff check .          All checks passed
ruff format --check . 52 files already formatted
pytest -q             81 passed
```

Validación independiente, venvs nuevos bajo `/tmp/agentcost-verify-20261029103012-3966`:

```text
pytest 3.10  81 passed
pytest 3.11  81 passed
pytest 3.12  81 passed
ruff check   All checks passed
ruff format  54 files already formatted
```

Doctor `editable` y `clean` pasó en 3.10, 3.11 y 3.12. La CLI limpia de 3.12 importó las fixtures y escribió los informes. `report-json` en los tres venvs limpios salió 0 con el mismo JSON (`better`, pares 8, costes `0.000498375` y `0.0104`).
