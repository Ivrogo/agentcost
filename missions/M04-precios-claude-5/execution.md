# M04 — Ejecución

## Decisiones

- Clase `full`, capacidad `standard`. `plan.md` está en `028bf86`, antes de las filas de precios.
- La rama parte de `805f8da` (`origin/main`, PR #9). No se hizo rebase ni force-push.
- Las cinco tarifas de cada id coinciden el 2026-10-29 en la página de precios y en la ficha del modelo. `source` es la página de precios, como el resto de filas de Anthropic. No hay alias documentado que añadir.
- El cálculo no cambia. `lookup` ya separa `claude-sonnet-5` de `claude-sonnet-4` porque el prefijo exige `-` o `.`.
- El sidechain no se deduplica. La propuesta queda en el README y en el CHANGELOG.
- Review y Validación son de esta sesión: el encargo pide self-review y no hay otro revisor. La Validación no editó código de producción. Documentación fue después y solo tocó Markdown.

## Comandos

RED, venv `/tmp/agentcost-m04-dev`, Python 3.12, antes de editar `prices.json`:

```text
pytest -q tests/test_cache.py::test_claude_5_rows_price_a_one_hour_cache_write
AssertionError: assert None == ModelPrice(... cache_write_1h_per_million=Decimal('4') ...)
EXIT:1
```

GREEN de implementación, el mismo venv, tras las filas: `pytest -q` 82 passed, `ruff check .` y `ruff format --check .` en 0. Commit `d11fb2d`.

Validación, sin reutilizar ese venv. Raíz `/tmp/agentcost-verify-20261029104524-3579`. Python 3.10.22, 3.11.18 y 3.12.16 vía `uv python find`. Doctor editable y clean en los tres. pytest 82 passed en cada desarrollo. ruff en el desarrollo 3.12. El informe JSON de `examples/research_agent` en los tres venv limpios: `better`, A `0.000498375`, B `0.0104`, 8 pares. El e2e de Claude usa las sesiones adjuntas (no se suben) y, otra vez, las fixtures del repo: `report --compare A B` sin `--allow-unpriced` sale 0, A `$0.1333972`, B `$1.883338`.

## Merge de origin/main

`main` avanzó al #10 (`84bc848`, modo CI, 101 tests). Merge de `origin/main` en esta rama, sin rebase y sin force-push. Git no dejó conflictos: README, CHANGELOG y la knowledge base quedaron con las dos entradas. `pytest -q` tras el merge: 102 passed (101 de main más el test de la tarifa de 1 hora).

E2E otra vez, venv limpio 3.12, cwd fuera del árbol, sesiones adjuntas, sin `--allow-unpriced`: salida 0, A `$0.1333972`, B `$1.883338`. El mismo informe con `--fail-if-worse --max-regression 5` sale 1: los precios se aplican y el veredicto es `inconclusive` (A no es peor; hay una tarea por brazo), y `--max-regression` pide un IC relativo emparejado que estas dos sesiones no tienen. No es un modelo sin precio.

## Escalados

Ninguno.
