# M03 — Modo CI para el pull request

## Clase y capacidad

- Clase: `full`. Cambia el comportamiento de la CLI (códigos de salida, flags y un resumen para comentar).
- Capacidad: `complex`. Cruza la CLI, el informe emparejado, un ejemplo de workflow y la verificación. La lógica nueva cabe en un módulo.
- `model_tier_used`: `complex`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultadas:

- `.agents/knowledge/README.md`
- [Comparación emparejada por task_id](../../.agents/knowledge/comparacion-emparejada.md). La diferencia es la primera variante menos la segunda. El veredicto emparejado lee `pairing.cost`, no el solape de `intervals`. Con menos de 5 pares el veredicto es `inconclusive` aunque el intervalo no contenga el 0.
- [Contabilidad de tokens de caché](../../.agents/knowledge/cache-token-accounting.md). El informe ya separa lectura, escritura y ahorro. El resumen de CI puede mostrar esas filas; no vuelve a interpretar la traza.
- [Sufijo `.json` con `--format both`](../../.agents/knowledge/formato-both-salida-json.md). No aplica: este cambio no elige la ruta del informe completo.

`main` está en `93d2a32` (PR #8) e incluye el PR #7. Esta rama ya lo tiene por avance rápido. No hay dependencia abierta.

## Petición

Un modo CI para usar `agentcost report` como puerta de un pull request: `--fail-if-worse`, un umbral en %, códigos de salida que no confundan una regresión con un fallo de la herramienta, un resumen Markdown y un workflow de ejemplo que no se ejecute en este repositorio.

## Decisiones

1. **Qué variante tiene que mejorar.** El veredicto ya habla de la primera frente a la segunda. «Peor» es ese veredicto: en emparejado, el IC del 95 % de la diferencia (primera menos segunda) queda entero por encima de 0; en no emparejado, el criterio actual de intervalos por brazo. `--fail-if-worse` sale 3 cuando el veredicto de coste es `worse`. En un pull request la candidata va primero: `--compare candidate baseline`.
2. **Mínimo de 5 pares.** El veredicto emparejado ya es `inconclusive` con menos de 5 pares, aunque el intervalo no contenga el 0. `--fail-if-worse` no falla en ese caso: usa el veredicto, no un segundo criterio. El umbral en % no usa ese suelo: si el límite inferior del IC relativo supera el %, falla igual.
3. **Umbral.** `--max-regression` acepta `5` y `5%`. Se compara el límite inferior del IC relativo del 95 % (`relative_interval.low`), no la estimación puntual, para no fallar por ruido. Falla solo si ese límite es estrictamente mayor que el umbral. Igual al umbral no falla.
4. **Sin emparejar, el umbral no se inventa.** No hay IC relativo. `--max-regression` sale 1 y lo dice. No se usa la estimación puntual. `--fail-if-worse` sí aplica el veredicto no emparejado, y el resumen repite el aviso de que no hubo pares.
5. **Métrica.** `--metric` es `cost` (defecto), `tokens` o `steps`. En coste, emparejado o no, manda el veredicto. En tokens o pasos solo hay regla emparejada (el mismo criterio del veredicto de coste, leído de `pairing.tokens` o `pairing.steps`). Sin pares, `--metric` distinto de `cost` sale 1.
6. **Combinar flags.** Si los dos están puestos, sale 3 cuando cualquiera de los dos falla. Si uno no se puede aplicar, sale 1 aunque el otro hubiera fallado: la puerta pedida no llegó a ejecutarse.
7. **Sin flags no hay puerta.** Un veredicto `worse` sigue saliendo 0. El resumen, si se pide, dice que no se pidió puerta.
8. **Códigos.** 0 va bien. 1 es el error de entrada o de comparación que ya existía (traza, precios, umbral ilegible, puerta que no se puede aplicar). 2 lo sigue usando Typer cuando la línea de comandos es inválida. 3 es regresión. El 3 no pisa al 1 ni al 2. El informe y el resumen se escriben también cuando se sale con 3, y cuando la puerta no se puede aplicar (1) si el informe ya existe.
9. **Resumen.** `--markdown-summary PATH`. Lleva la marca `<!-- agentcost-ci -->`, la tabla A frente a B (tareas, tareas resueltas, coste por tarea resuelta y coste total), el modo y el número de pares, la diferencia, el IC, el relativo, el umbral, el veredicto y el aviso si no hay emparejamiento. Las filas de caché (entrada, salida, lectura, escritura, ahorro) entran solo cuando algún brazo tiene importe de caché, ahorro o un precio de caché caído a la tarifa de entrada. `--github-step-summary` añade el mismo texto a `$GITHUB_STEP_SUMMARY` si existe; si no existe, no hace nada y no falla.
10. **Varios ficheros.** `report` acepta una o más trazas y las concatena. El ejemplo de CI pasa dos. Los nombres de variante siguen saliendo del campo `variant`, no del orden de los ficheros.
11. **Workflow.** `examples/ci/agentcost.yml`, fuera de `.github/workflows`. Instala con `python -m pip install agentcost`, compara dos ficheros, comenta el PR con `actions/github-script` (crea o actualiza por la marca) y el job falla si el proceso no sale 0. Permisos: `contents: read` y `pull-requests: write`. Sin secretos. `contents: read` hace falta para el checkout cuando el token por defecto no lee el repo.
12. **PyPI.** Este cambio no publica release. El ejemplo usa el nombre del paquete. El README dice que, hasta que exista en PyPI, el paso de instalación puede apuntar a un commit de git.

## Criterios de aceptación

1. Mejora con los dos flags: salida 0.
2. Regresión clara (`--fail-if-worse` con veredicto `worse`): salida 3, informe escrito.
3. Empeoramiento cuyo límite inferior no supera el umbral, sin `--fail-if-worse`: salida 0.
4. Sin `task_id` común, `--fail-if-worse` y veredicto no emparejado `worse`: salida 3 y el aviso en el resumen.
5. Umbral ilegible, o `--max-regression` sin pares: salida 1, distinta de 3.
6. El Markdown del caso cerrado es estable.
7. README y CHANGELOG (`[Unreleased]`, v0.2) documentan los dos criterios, los códigos y el ejemplo.
8. La validación corre la matriz de la skill y el workflow de ejemplo se comprueba con actionlint si se puede instalar.

## Fuera de alcance

- Publicar release o tag. Merge a `main`. Force-push.
- El PR #7 y el adaptador de logs de Claude Code y Codex.
- Cambiar el cálculo de coste, el bootstrap o el veredicto.
- Instalar el workflow en `.github/workflows` de este repositorio.

## Security Advisor

El ejemplo pide `contents: read` y `pull-requests: write`, comenta con el `GITHUB_TOKEN` del job y no recibe secretos. No está en `.github/workflows`, así que aquí no se ejecuta. No cambia dependencias, autenticación ni despliegue. El cuerpo del comentario es el resumen numérico; no ejecuta la traza.

[YES] Reason: the example workflow is not installed in this repo, uses the job token with contents read and pull-requests write only, and adds no secrets or dependencies.

## Pruebas

TDD en `tests/test_gate.py`: un caso por código de salida y un snapshot del Markdown. La validación, con `verify-agentcost`, después de la review: pytest en 3.10–3.12, ruff, instalación limpia y la CLI real sobre `examples/research_agent/traces.jsonl` (un caso que pasa y otro que sale 3).

## Roles

| Fase | Dueño |
| --- | --- |
| Plan | Esta sesión. |
| Implementación/TDD | Esta sesión. |
| Review de código | Esta sesión, en una pasada posterior, solo código y tests. |
| Validación | Fase distinta, con la skill `verify-agentcost`, sin editar código de producción. |
| Documentación | Después de Review y Validación en OK. |
| Publicación | Autorizada: rama, commits y PR contra `main`. Sin merge, sin tag y sin release. |

## Riesgos

- Tratar el 3 como fallo de herramienta haría rojo un job que no distingue. El README separa 0, 1, 2 y 3.
- Poner la base primero en `--compare` invertiría la puerta. El ejemplo nombra la candidata primero.
- Comparar el umbral con la media, y no con el límite inferior, fallaría por ruido. El código usa el límite inferior.
