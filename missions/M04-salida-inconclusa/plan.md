# M04 — El veredicto inconcluso no es un error de uso

## Clase y capacidad

- Clase: `full`. Cambia el comportamiento de la CLI (código de salida y un flag).
- Capacidad: `standard`. La lógica cabe en `gate.py` y en el cableado de `cli.py`. Los tests viven en `tests/test_gate.py`.
- `model_tier_used`: `standard`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultadas:

- `.agents/knowledge/README.md`
- [Modo CI](../../.agents/knowledge/modo-ci.md). El 3 es regresión, el 1 es fallo de la herramienta y el 2 lo usa Typer. `--fail-if-worse` repite el veredicto de coste. `--max-regression` sin intervalo relativo sale 1. Esta misión separa el veredicto `inconclusive` de ese 1.
- [Comparación emparejada por task_id](../../.agents/knowledge/comparacion-emparejada.md). Sin `task_id` compartido no hay intervalo relativo. Con menos de 5 pares el veredicto es `inconclusive` aunque el intervalo absoluto no contenga el 0.
- [Sufijo `.json` con `--format both`](../../.agents/knowledge/formato-both-salida-json.md). No aplica: no se elige la ruta del informe.

`origin/main` está en `84bc848` (PR #10). El PR #11 (precios de `claude-sonnet-5` y `claude-fable-5`) sigue abierto. Esta misión no toca `prices.json`.

## Petición

En `agentcost report --compare A B --fail-if-worse [--max-regression N]`, un veredicto `inconclusive` sale hoy con código 1 cuando la puerta no puede aplicarse (no hay pares, o no hay intervalo relativo). Ese 1 es el mismo que un error de uso. Hay que separarlos.

## Decisiones

1. **Códigos.** 0 va bien. 1 es un error de uso o de entrada que ya calculaba la herramienta (traza, modelo sin precio, formato, umbral ilegible, métrica que no se puede aplicar, `--max-regression` que no se puede aplicar cuando el veredicto no es `inconclusive`). 2 lo sigue usando Typer para una línea inválida (flag desconocido, argumento ausente, fichero que no existe). 3 es regresión. 4 es inconcluso, y solo si se pide.
2. **Por defecto no falla.** Con `--fail-if-worse` y veredicto `inconclusive`, la salida es 0. Stderr recibe un aviso que empieza por `Inconclusive:` y copia `verdict_reason`. Si además `--max-regression` no se puede aplicar, el aviso añade esa frase (no hay `task_id` compartidos, o no hay intervalo relativo) y no se usa el código 1.
3. **Flag.** `--fail-if-inconclusive` exige `--fail-if-worse`. Con los dos y veredicto `inconclusive`, la salida es 4 y el aviso es el mismo. Sin `--fail-if-worse`, aunque vaya `--max-regression`, es un error de uso: código 1 y el mensaje `--fail-if-inconclusive requires --fail-if-worse.` No se escribe informe.
4. **La regresión gana.** Si `--max-regression` sí se aplica y el límite inferior supera el porcentaje, la salida sigue siendo 3 aunque el veredicto de coste sea `inconclusive` (menos de 5 pares) y aunque esté `--fail-if-inconclusive`. El cambio incompatible que se anota es el que hoy sale 1 y pasa a 0, no el 3.
5. **Lo que sigue en 1.** Un veredicto `worse` no emparejado con `--max-regression` sigue en 1: la puerta pedida no se puede aplicar y el veredicto no es inconcluso. `--metric tokens` o `steps` sin pares sigue en 1. Un modelo sin precio, sin `--allow-unpriced`, sigue en 1.
6. **Resumen.** Si el resultado de la puerta es inconcluso, `**Gate:**` dice `inconclusive`, no `pass` ni `error`. El informe y el resumen se escriben también con salida 4.
7. **El 2 no se reasigna.** Typer ya documenta el 2. Un fichero ausente y un flag desconocido no pasan a 1. El diseño hablaba de «argumentos inválidos» en el 1; los que valida esta herramienta (formato, umbral, flag nuevo sin su pareja) salen 1. Los que rechaza Typer siguen en 2.

## Criterios de aceptación

1. Mejora con `--fail-if-worse`: salida 0.
2. `--fail-if-worse` y veredicto `inconclusive`, sin el flag nuevo: salida 0 y el aviso en stderr.
3. Lo mismo con `--fail-if-inconclusive`: salida 4, informe escrito, aviso en stderr.
4. Regresión clara: salida 3. También si el veredicto es `inconclusive` por menos de 5 pares y el umbral sí se supera.
5. `--fail-if-inconclusive` sin `--fail-if-worse`: salida 1 y el mensaje que pide el otro flag.
6. Error de entrada real (umbral ilegible, modelo sin precio): salida 1, distinta de 3 y de 4.
7. Sin `task_id` común, veredicto `inconclusive`, `--fail-if-worse` y `--max-regression`: salida 0 (o 4 con el flag), no 1. El aviso dice que no hay intervalo relativo.
8. Sin `task_id` común y veredicto `worse`, los dos flags de puerta: sigue saliendo 1.
9. README, CHANGELOG (`[Unreleased]`, cambio incompatible), la ayuda y un comentario en `examples/ci/agentcost.yml`.

## Fuera de alcance

- Publicar release, tag o paquete en PyPI. Merge a `main`. Force-push.
- Precios de `claude-sonnet-5` y `claude-fable-5` (PR #11).
- Cambiar el cálculo del veredicto, del bootstrap o del emparejamiento.
- Mover el código 2 de Typer al 1.

## Security Advisor

No aplica. No hay autenticación, secretos, concurrencia, migraciones, borrado histórico ni dependencias nuevas. `examples/ci/agentcost.yml` solo gana un comentario; no entra en `.github/workflows`.

## Pruebas

TDD en `tests/test_gate.py`: un caso por código (0, 0 con aviso, 4, 3, 1 de uso, 1 del flag huérfano). La validación, con `verify-agentcost`, después de la review: pytest en 3.10–3.12, ruff, instalación limpia y la CLI real. El 0 y el 3 usan `examples/research_agent/traces.jsonl`. El inconcluso usa `examples/cache_usage/traces.jsonl` (un `task_id` distinto por variante, veredicto inconcluso, sin logs reales).

## Roles

| Fase | Dueño |
| --- | --- |
| Plan | Esta sesión, antes del código. |
| Implementación/TDD | Esta sesión. |
| Review de código | Pasada posterior de esta sesión, solo código y tests. |
| Validación | Fase distinta, con la skill `verify-agentcost`, sin editar código de producción. |
| Documentación | Después de Review y Validación en OK. |
| Publicación | Autorizada: rama, commits y PR contra `main`. Sin merge, sin tag y sin release. |

## Riesgos

- Tratar todo `inconclusive` como 0 también cuando el umbral detecta regresión ocultaría un 3. La decisión 4 lo evita y hay un test.
- Dejar el `worse` no emparejado con umbral en 1 conserva el contrato de M03. Solo el inconcluso cambia de 1 a 0.
- El comentario del PR que antes decía `Gate: pass` en un informe inconcluso pasa a decir `inconclusive`. El job, sin el flag nuevo, sigue en verde.
