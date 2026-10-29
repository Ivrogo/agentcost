# Ejecución M02

## Decisiones

- Clase `full`, capacidad `standard`. `model_tier_used`: `standard`. Escalados: 0.
- Knowledge base: la ficha del sufijo `.json` no aplica. Queda citada en `plan.md`. Al documentar se añadió `comparacion-emparejada.md` para el PR siguiente.
- Security Advisor no aplica.
- Semilla y remuestreos: `--seed` y `--bootstrap`. El defecto sigue en 1000.
- Latencia fuera: `Event` no la tiene.
- `report.metric` sigue siendo `cost_per_solved_task`. El contraste emparejado está en `pairing` y es el que manda el veredicto en ese modo.

## Secuencia

1. `plan.md` antes de editar `src/` o `tests/`. Base `96ffb9d` (`main`).
2. Tests en `tests/test_pairing.py` y `tests/test_cli.py`. RED: la recogida fallaba al importar `MetricDifference`.
3. Implementación. GREEN local: `pytest -q` → 41 passed. `ruff check` y `ruff format --check` en 0.
4. Review de código, otro agente, sin bloqueantes. Notas aceptadas y escritas en el README: `intervals` no es el IC emparejado, y el relativo descarta remuestreos cuya media de B es 0.
5. Validación sobre el commit `28ea2d9`, con la skill `verify-agentcost`. Esta fase no editó código de producción. La documentación posterior no toca código, tests ni runtime.

## Review

Veredicto: aprobado, sin bloqueantes. El revisor no era el codificador.

## Validación

Directorio de la corrida: `/tmp/agentcost-verify-20261029100630-3300`. Intérpretes de `uv`: Python 3.10.22, 3.11.18 y 3.12.16. Commit validado: `28ea2d977bf57c29881d22907769b9fcb36ebf0c`.

| Check | Resultado |
| --- | --- |
| pytest 3.10, 3.11, 3.12 | 41 passed, salida 0 |
| ruff check / format (3.12) | All checks passed; 39 files already formatted; salida 0 |
| Doctor editable y clean, las tres versiones | version 0.1.0, módulo en el sitio esperado |
| CLI JSON limpia, 3.10, 3.11 y 3.12 | exit 0, stderr vacío, veredicto better, costes de ejemplo, pairing paired, 8 pares, el IC de coste no incluye el 0 |
| CLI Markdown limpia, 3.12 | `**Pairing:** paired (8 pairs).` y `The cost interval does not include 0.` |
| `report --help` limpio, 3.12 | contiene `--paired` y `--unpaired` |

macOS, Windows y pipx no se ejecutaron aquí. Los corre `.github/workflows/ci.yml`.
