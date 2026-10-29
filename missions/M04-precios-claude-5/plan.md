# M04 — Precios de Claude Sonnet 5 y Claude Fable 5

## Clase y capacidad

- Clase: `full`. Cambia datos de producto: sin esas filas el informe de una sesión real sale 1, y con ellas el coste deja de ser cero. No es un retoque de un solo fichero ni documentación repartida.
- Capacidad: `standard`. La tarifa ya existe en `PriceTable` y en el cálculo de caché del #7. Aquí se añaden dos filas, los tests que las fijan y el texto del riesgo de sidechain. No hay parser nuevo, ni autenticación, ni concurrencia.
- `model_tier_used`: `standard`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultada `.agents/knowledge/README.md` y estas fichas:

- [Contabilidad de tokens de caché](../../.agents/knowledge/cache-token-accounting.md). La escritura de 1 hora ya es un cubo distinto y se cobra con `cache_write_1h`. No hace falta otro campo.
- [Logs locales de Claude Code y de Codex](../../.agents/knowledge/logs-locales-claude-codex.md). La deduplicación actual es `message.id` + `requestId`. No menciona el replay de sidechain. Se corrige al documentar, porque la ficha quedaría incompleta.
- [Sufijo `.json` con `--format both`](../../.agents/knowledge/formato-both-salida-json.md) y [Comparación emparejada por task_id](../../.agents/knowledge/comparacion-emparejada.md). No aplican: no se toca `--format both` ni `pairing.py`.

## Petición

Las sesiones reales de Claude Code que usan `claude-sonnet-5` y `claude-fable-5` tienen que dar coste sin `--allow-unpriced`. Cada tarifa (entrada, salida, escritura de caché a 5 minutos, escritura a 1 hora, lectura) sale de la documentación oficial de Anthropic, con `source` y `as_of` como el resto de la tabla. Si el id no coincide, no se inventa precio ni se copia de un tercero.

El README (import de Claude Code) y el CHANGELOG `Unreleased` tienen que decir que un sidechain o subagente con otro `requestId` se cuenta otra vez, cómo detectarlo y, si hay una deduplicación simple y segura, dejarla propuesta y sin implementar.

## Fuentes (consulta 2026-10-29)

Las cinco tarifas coinciden en las dos páginas. El id de API está en la ficha del modelo, no en la tabla de precios (allí el nombre es «Claude Sonnet 5» y «Claude Fable 5»).

| Id de API | Entrada | Salida | Escritura 5 min | Escritura 1 h | Lectura | Ficha del modelo |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `claude-sonnet-5` | 2 | 10 | 2.50 | 4 | 0.20 | https://platform.claude.com/docs/en/models/sonnet-5/overview |
| `claude-fable-5` | 10 | 50 | 12.50 | 20 | 1 | https://platform.claude.com/docs/en/models/fable-5/overview |

La misma tabla, con esos nombres de producto, está en https://platform.claude.com/docs/en/about-claude/pricing (notas al pie: la lectura de Fable 5 es 1 USD, no los 0.25 de Fable 5.1; la de Sonnet 5 es 0.20, no los 0.10 de Sonnet 5.5; los 2/10 de Sonnet 5 son ya el precio estándar). `source` de la fila es la página de precios, igual que `claude-sonnet-4` y `claude-3-5-haiku`. `as_of` es `2026-10-29`. La versión de la tabla sigue siendo `2026-10-29`: es el mismo día de consulta.

No se añade otro id. La ficha no declara un alias distinto de `claude-sonnet-5` ni de `claude-fable-5`. No se añade `claude-mythos-5`, `claude-fable-5-1` ni `claude-sonnet-5-5`: no son el id de las sesiones. Un sufijo con guion o punto hereda la fila por la regla que ya tiene `PriceTable.lookup`; no se documenta aquí un snapshot concreto.

## Cambio

1. Dos filas en `src/agentcost/data/prices.json`. Nada más en el cálculo.
2. Tests: las dos filas, y un coste con tokens de escritura de caché de 1 hora (1 000 000 tokens: 4 USD en Sonnet 5 y 20 USD en Fable 5). Las fixtures anonimizadas pasan a costar sin `--allow-unpriced`. El test que esperaba salida 1 se sustituye: esa salida era la ausencia de precio, que este cambio quita.
3. Documentación, después de Review y Validación: tabla del README, el párrafo que decía que esos ids no tenían precio, la sección de riesgo del import, CHANGELOG `Unreleased`, la ficha de logs locales y el feature `import-local-logs` (el mapa pide `--allow-unpriced` y dejaría de cumplirse).

## Riesgo de sidechain (solo documentación)

La clave actual es `("req", message_id, request_id)` cuando hay `requestId`. Un sidechain que repite el `message.id` del padre con otro `requestId` no entra en esa clave y se suma otra vez. El mensaje nuevo del subagente, con su propio `message.id`, es una llamada real y tiene que contarse.

Detección, en el JSONL de origen, antes de importar: agrupar las líneas `assistant` con `message.usage` por `message.id`. El mismo id con más de un `requestId`, y alguna línea con `isSidechain: true` (Claude Code también las escribe bajo `subagents/`, por ejemplo `agent-aside_question-*.jsonl`), es un replay. El JSONL importado no guarda `requestId` ni `isSidechain`, así que el informe ya no puede señalar el duplicado.

Propuesta, sin implementar: si el `message.id` ya está guardado y el `requestId` es otro, descartar la copia solo cuando una de las dos líneas tiene `isSidechain: true`, y conservar la que no es sidechain. No unir dos líneas que sean las dos de la sesión principal. Es la misma condición que usa ccusage (`is_sidechain` en el fallback por `message.id`). Colapsar solo por `message.id` no es seguro: borraría un caso que no hemos visto en las fixtures.

## Fuera de alcance

- No se implementa esa deduplicación.
- No se sincroniza con LiteLLM ni con tokencost.
- No se toca la rama del modo CI, ni workflows, ni `pyproject.toml`.
- No hay release, tag, merge ni force-push.
- No se suben las sesiones adjuntas: ya están en `tests/fixtures/claude-code/` y el e2e de esta misión usa las copias adjuntas, fuera del repo.
- Security Advisor: no aplica. No entran los globs de `.cursor/rules/security-advisor.mdc`.

## Criterios de aceptación

1. `PriceTable.bundled().lookup("claude-sonnet-5")` y `lookup("claude-fable-5")` devuelven las cinco tarifas, `source` y `as_of` de la tabla de arriba. `claude-sonnet-5` no hereda el precio de `claude-sonnet-4`.
2. Un evento con 1 000 000 tokens en `cache_write_1h` cuesta 4 USD con `claude-sonnet-5` y 20 USD con `claude-fable-5`, y `cache_priced_as_input` queda vacío.
3. Importar las dos sesiones y `report --compare A B` sin `--allow-unpriced` sale 0. El coste es la suma de las tarifas sobre los totales ya deduplicados de `totales.json`: A `0.1333972`, B `1.883338`.
4. README y CHANGELOG describen el doble conteo, la detección y la propuesta. El código de deduplicación no cambia.

## Pruebas

TDD: el test del criterio 1 y 2 falla en la tabla actual (`lookup` es `None` y `compare` lanza `PriceError`). Luego se añaden las filas.

La Validación repite, sin fiarse de esa ejecución, la skill `verify-agentcost` (pytest 3.10–3.12, ruff, instalación limpia, informe JSON de `examples/research_agent`) y el e2e de las dos sesiones adjuntas sin `--allow-unpriced`. macOS, Windows y pipx quedan en la CI.

## Roles

| Fase | Dueño |
| --- | --- |
| Plan | Esta sesión. |
| Implementación/TDD | Esta sesión. |
| Review de código | Esta sesión, como self-review: el encargo la pide y no hay un segundo revisor. |
| Validación | Esta sesión, repitiendo los checks sobre el código ya cerrado, sin editar producción. |
| Documentación | Esta sesión, después de esos dos gates. |
| Publicación | Autorizada en la petición: commit, push de `cursor/claude-5-prices-3155` y un PR contra `main`. Sin merge. |

## Riesgos

- Confundir Sonnet 5 con Sonnet 5.5, o Fable 5 con Fable 5.1, cambia la lectura de caché (0.20 frente a 0.10, y 1 frente a 0.25). El test fija el id exacto y las cinco cifras.
- `claude-sonnet-5` no es prefijo de `claude-sonnet-4` ni al revés: el guion del lookup exige `clave-` o `clave.`. El test lo comprueba al pedir la fila exacta.
- Dejar el párrafo del README que dice que esos modelos no tienen precio contradiría la tabla. Se borra en Documentación, no se deja al lado del párrafo nuevo.
