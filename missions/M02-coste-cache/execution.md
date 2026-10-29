# M02 — Ejecución

## Decisiones

- Clase `full`, capacidad `complex`. Plan escrito antes del código de producción.
- La forma canónica `tokens` sigue disjunta. La regla de cada proveedor solo se aplica a `provider` + `usage`.
- OpenAI `cache_write_tokens` distinto de cero se rechaza. No hay tarifa empaquetada para la escritura a 30 min / 12 h y el contador ya va dentro de `input_tokens`.
- La escritura OTel, sin TTL en la convención, se anota como 5 minutos.
- `schema_version` se queda en `0.1`. La versión de la tabla pasa a `2026-10-29` porque entran precios nuevos. Entrada y salida no cambian.
- `--set-price` sigue siendo `INPUT:OUTPUT` y no rellena la caché. El fichero de precios y `ModelPrice` sí.

## Comandos

RED, antes de analizar `usage` (`/tmp/agentcost-dev`, Python 3.12):

```text
pytest -q tests/test_cache.py --tb=line
21 failed
```

El caso OpenAI devolvía `input_tokens == 0`. El caso Anthropic también. `Event` no tenía `cache_read_tokens`. La tabla seguía en `2026-10-01`.

GREEN, misma máquina, tras el parser, los precios y el desglose:

```text
ruff check .          All checks passed
ruff format --check . 38 files already formatted
pytest -q             56 passed
```

La CLI sobre `examples/cache_usage/traces.jsonl --compare openai anthropic` da entrada OpenAI `$0.000215`, lectura `$0.0024`, ahorro `$0.0024`, total `$0.005615` (2306 tokens). Anthropic: entrada `$0.006144`, lectura `$0.00054`, escritura `$0.001155` (5 min `$0.000555`, 1 h `$0.0006`), ahorro `$0.004449`, total `$0.015384` (4599 tokens). La traza de investigación sigue en `$0.000498375` y `$0.0104`.

## Validación

Directorio `/tmp/agentcost-verify-20261029100121-2860`. Intérpretes de uv: Python 3.10.22, 3.11.18 y 3.12.16. Doctor editable y clean en las tres versiones, salida 0. Pytest 56 passed en las tres. `ruff check` All checks passed. `ruff format --check` 39 files already formatted. La CLI limpia, con `drive.sh` y el directorio de trabajo fuera del árbol, repitió el informe JSON de `examples/research_agent` y el informe de `examples/cache_usage` en 3.10, 3.11 y 3.12. macOS, Windows y pipx no se ejecutaron aquí.

## Corrección antes de cerrar Implementación

Un `cache_read_tokens` plano junto a un objeto `tokens` se ignoraba. Eso perdía tokens sin avisar. Ahora es un error si no está repetido, con el mismo valor, dentro de `tokens`. La entrada y la salida planas siguen la regla de la v0.1.
