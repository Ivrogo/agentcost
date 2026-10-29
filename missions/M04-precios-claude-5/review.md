# Review de código — M04

Self-review de la misma sesión. El encargo pide esa revisión antes de dar el PR por listo; no hay un segundo revisor en esta ejecución. El diff funcional es `src/agentcost/data/prices.json`, `tests/test_cache.py` y `tests/test_local_logs.py`, en `d11fb2d`. No entra `pricing.py`, `report.py` ni `local_logs.py`.

Regla cargada: `harness.mdc`. Se leyó `security-advisor.mdc`; sus globs no entran.

Skills cargadas: `verify-agentcost`, `principle-prove-it-works`, `principle-fix-root-causes`, `principle-subtract-before-you-add`.

## Veredicto

Aprobado. No queda un fallo bloqueante. No se reabre Implementación.

## Requisitos

1. `claude-sonnet-5` y `claude-fable-5` tienen entrada, salida, escritura a 5 minutos, escritura a 1 hora y lectura. Las cifras son las de https://platform.claude.com/docs/en/about-claude/pricing consultada el 2026-10-29, y el id de cada fila es el de la ficha del modelo (`claude-sonnet-5`, `claude-fable-5`) en la misma fecha. No se usó la lectura de Sonnet 5.5 (0.10) ni la de Fable 5.1 (0.25).
2. Un millón de tokens `cache_write_1h` cuesta 4 USD y 20 USD. `cache_priced_as_input` queda vacío, así que no cae a la tarifa de entrada.
3. Las fixtures deduplicadas se cobran sin `on_missing="zero"` y sin `--allow-unpriced`. El coste sale de `totales.json` por la tarifa, no de un literal suelto.
4. No se añadió un alias. La ficha no declara otro id para estos dos modelos.
5. `local_logs.py` no cambia. El sidechain con otro `requestId` sigue contándose otra vez. No se implementó la deduplicación propuesta.

## Causa y calidad

El fallo era una fila ausente, no un cálculo distinto. `lookup("claude-sonnet-5")` no es prefijo de `claude-sonnet-4`: la clave heredada tendría que ir seguida de `-` o `.`. La igualdad con `ModelPrice` lo fija, porque las tarifas de Sonnet 4 son otras (3 / 15 / 0.30 / 3.75 / 6).

El JSON de la CLI se compara con `Decimal(str(...))` contra la misma fórmula. No hay un segundo camino de precio.

## Alcance

No se tocan `pyproject.toml`, workflows, secretos ni autenticación. Security Advisor no aplica. No hay sincronización con LiteLLM ni con tokencost.

## Observaciones que no bloquean

- En el momento de esta review el README y `features/import-local-logs.md` aún decían que estos ids no tenían precio. Documentación lo corrigió después, sin tocar código ni tests. No reabre este gate.
- La deduplicación de sidechain queda propuesta en Documentación y fuera de este diff.
