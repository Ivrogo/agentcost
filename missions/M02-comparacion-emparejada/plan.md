# M02 — Comparación A/B emparejada por task_id

## Clase y capacidad

- Clase: `full`. Cambia el comportamiento de la comparación y de la CLI.
- Capacidad: `standard`. La lógica nueva cabe en un módulo y se engancha al informe que ya existe. No hay arquitectura nueva, concurrencia, datos persistentes ni secretos.
- `model_tier_used`: `standard`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultada `.agents/knowledge/README.md` y [Sufijo `.json` con `--format both`](../../.agents/knowledge/formato-both-salida-json.md).

Esa ficha no aplica: este cambio no elige rutas de salida. No hay otra ficha que describa la comparación. El comportamiento vigente está en `README.md` («Arms are unpaired: shared `task_id` values are not matched») y en `compare` (`src/agentcost/report.py`): cada brazo se remuestrea por separado y el veredicto mira si los intervalos de coste por tarea resuelta se solapan.

## Petición

Cuando A y B comparten `task_id`, el informe debe dar la diferencia por tarea (coste, tokens y pasos), la media de esas diferencias y un intervalo de confianza del 95 % por bootstrap de las diferencias emparejadas. También el cambio relativo en % con su intervalo. La semilla y el número de remuestreos se configuran. Si el emparejamiento es parcial, solo entran las tareas emparejadas y se dice cuántas quedan fuera por cada lado. Si no hay ninguna en común, se mantiene el modo actual y se avisa en la salida y en stderr. Un flag fuerza el modo. La salida (Markdown y JSON) muestra el modo, el número de pares, la diferencia media, el IC del 95 % y si el IC incluye el 0. El siguiente PR (`--fail-if-worse`) necesita un resultado tipado. No se implementa el modo CI. No se tocan precios ni el cálculo de coste.

## Decisiones

1. **Diferencia.** Por cada `task_id` compartido, la observación es la misma agregación que ya usa el informe: suma de coste, tokens y pasos de todas las runs de esa tarea, fallos incluidos. La diferencia es primera variante menos segunda (`A - B`). Negativo en coste significa que la primera es más barata.
2. **Cambio relativo.** `100 * media(A - B) / media(B)`. El IC relativo remuestrea ese cociente de medias, no la media de los cocientes por tarea. Si la media de B es 0, el relativo queda indefinido (`null`), sin inventar un porcentaje.
3. **Bootstrap.** `random.Random` de la biblioteca estándar, el mismo percentil lineal que ya usa el informe (función extraída a `stats.py` para no duplicarla). Cada métrica tiene su propio generador con la misma semilla, así el IC de coste no depende de tokens ni de pasos. Los pares se ordenan por `task_id` antes de remuestrear. Un extremo que toca el 0 cuenta como «incluye el 0», igual que el solape actual cuenta un extremo que toca.
4. **Semilla y remuestreos.** Se reutilizan `--seed` (42) y `--bootstrap` (1000). No se cambia el defecto de 1000: es el contrato ya documentado y un segundo defecto partiría el informe. 10 000 sigue siendo un valor razonable y se pasa con `--bootstrap 10000`.
5. **Modo.** `auto` (defecto), `paired` o `unpaired`. En la CLI, `--paired` y `--unpaired`; si no se pasa ninguno, `auto`. Los dos a la vez son un error. En Typer son flags sueltos, sin `--no-paired`, igual que el resto de flags de `report`.
6. **Auto.** Hay al menos un `task_id` en común → emparejado. No hay ninguno → no emparejado, con este aviso en Markdown, en el campo JSON `warning` y en stderr: `No shared task_id between 'A' and 'B'. Using the unpaired comparison.`
7. **Parcial.** El informe (ramas, veredicto emparejado y diferencias) usa solo los pares. `unmatched` cuenta las tareas que solo están en un lado. El Markdown las nombra como «Left out» cuando el recuento no es cero.
8. **Forzar.** `--paired` sin ningún `task_id` en común lanza `CompareError` (salida 1). No es el aviso de `auto`: el usuario pidió pares y no los hay. `--unpaired` ignora los ids compartidos, no avisa y conserva el cálculo actual sobre todas las tareas.
9. **Veredicto en modo emparejado.** Sigue siendo sobre el coste y sobre la primera variante. Con menos de 5 pares, `inconclusive`. Si la media emparejada es 0, `no_difference`. Si el IC del 95 % incluye el 0, `inconclusive`. Si el IC queda por debajo de 0, `better`. Si queda por encima, `worse`. `intervals` sigue siendo el IC de cada brazo (coste por tarea resuelta) sobre las tareas que entraron en el informe. El contraste emparejado vive en `pairing` y es el que lee el veredicto en ese modo. Así el siguiente PR no tiene que reinterpretar el solape de brazos.
10. **Latencia.** El modelo `Event` no tiene duración y el parser no lee ninguna. No se añade un campo vacío ni se toca el parser. El resultado no trae latencia.
11. **Esquema JSON.** Se mantiene `schema_version` `0.1` y se añade el objeto `pairing`. Las cifras que ya comprueba la skill (`cost_per_solved_task`, tareas, veredicto del ejemplo) no cambian: en `examples/research_agent/traces.jsonl` los ocho `task_id` están en los dos brazos.
12. **API.** `assess_pairing(...) -> Pairing` en `agentcost.pairing`. `compare(..., pairing="auto")` rellena `report.pairing`. `MetricDifference` expone la media, el intervalo, `includes_zero`, el % relativo y su intervalo. No hay `--fail-if-worse`.

## Criterios de aceptación

1. Pares constantes con resultado cerrado: media de coste `-3`, IC `[-3, -3]`, no incluye el 0, cambio relativo `-60` con el mismo IC, veredicto `better`.
2. IC conocido que incluye el 0 (media distinta de 0) y otro que no lo incluye.
3. Emparejamiento parcial: solo los ids comunes entran en la media y en las ramas; se informa de los excluidos por lado.
4. Sin ids comunes: modo no emparejado, aviso en la salida y en stderr, ramas intactas.
5. La misma semilla repite el intervalo; otra semilla, sobre datos en los que el percentil se mueve, lo cambia.
6. `--paired` / `--unpaired` / los dos a la vez se comportan como la decisión 5 y la 8.
7. README explica el emparejamiento y cómo leer el IC. CHANGELOG, en `[Unreleased]`, anota el cambio de la v0.2.

## Fuera de alcance

- `--fail-if-worse`, umbrales en % y cualquier modo CI.
- Precios, tokens de caché y `pricing.py`.
- Añadir latencia al parser o a `Event`.
- Subir el defecto de `--bootstrap` a 10 000.
- Bump de versión del paquete y release.

## Security Advisor

No aplica. El cambio no toca autenticación, concurrencia, migraciones, secretos, despliegue, workflows ni `pyproject.toml`. Los globs de `.cursor/rules/security-advisor.mdc` no entran.

## Pruebas

TDD en `tests/test_pairing.py` y casos de CLI en `tests/test_cli.py`. El caso cerrado y el IC con extremos conocidos se fijan con el percentil ya usado por el proyecto (`stats.quantile`) y `random.Random`, calculados aparte del código de producción.

La validación, con la skill `verify-agentcost`, corre después de la review: pytest en 3.10, 3.11 y 3.12, ruff, instalación limpia y la CLI real sobre `examples/research_agent/traces.jsonl`.

## Roles

| Fase | Dueño |
| --- | --- |
| Plan | Esta sesión. |
| Implementación/TDD | Esta sesión. |
| Review de código | Otro agente, sobre el diff de código y tests, sin artefactos de misión. |
| Validación | Fase distinta, con la skill `verify-agentcost`, sin editar código de producción. |
| Documentación | Después de Review y Validación en OK. |
| Publicación | Autorizada en la petición: rama, commits y PR. Sin merge, sin tag y sin release. |

## Riesgos

- Tratar el ejemplo como no emparejado dejaría el README mintiendo: `q01`–`q08` están en A y en B. El defecto `auto` empareja ese fichero. Las cifras de coste por tarea resuelta se conservan porque no se descarta ninguna tarea.
- Filtrar las ramas solo en el modo emparejado. En `--unpaired` las tareas sin pareja siguen dentro, que es el cálculo actual.
- Avisar también cuando el usuario pasó `--unpaired` haría ruido en un modo que pidió. El aviso de stderr es solo el fallback de `auto`.
