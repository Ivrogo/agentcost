# Review de código — M01

Revisor distinto del codificador. SHA revisado: `874132434a6a0e15727cfa7ec6fad9e3205e7511`.

Alcance revisado: `src/agentcost/cli.py` y `tests/test_cli.py`. Los artefactos de misión y la documentación no forman parte de esta Review.

Regla cargada: `harness.mdc`. Se leyó `security-advisor.mdc`; sus globs no entran en el diff.

Skills del repositorio cargadas: `verify-agentcost`, `principle-fix-root-causes`, `principle-prove-it-works`, `principle-subtract-before-you-add`.

## Veredicto

Aprobado. No hay fallos bloqueantes. La Review no reabre Implementación.

## Requisitos

1. Con `--format both` y un `--output` cuyo `with_suffix(".json")` es la misma ruta, `_emit_report` lanza `AgentCostError` antes de cualquier `write_text`. `report` ya escribe ese mensaje en stderr y sale con código 1. El texto es `--format both would write Markdown and JSON to the same path: <ruta>`.
2. `--output` con sufijo `.md` sigue escribiendo Markdown en esa ruta y JSON en la ruta con sufijo `.json`. El test pide `**Verdict:** better` y `"verdict": "better"`.
3. `--output` sin sufijo sigue dejando el Markdown en esa ruta y el JSON en la ruta con sufijo `.json`.
4. `--format json` no entra en la comprobación y escribe solo el JSON.
5. Los cuatro casos están en `tests/test_cli.py` y usan `examples/research_agent/traces.jsonl`.

## Causa y calidad

El estado es legítimo: el usuario puede pedir `--format both` con una ruta que ya termina en `.json`. El primer sitio que hacía algo indebido era elegir el segundo destino y escribirlo. El rechazo está ahí, no en el renderizado, y reutiliza `AgentCostError`. No añade un tipo nuevo ni un validador de mayúsculas o de enlaces simbólicos. Eso coincide con el plan y con `principle-fix-root-causes` y `principle-subtract-before-you-add`.

No hay otra escritura de informe en `src/`. La rama de stdout no crea ficheros.

## Alcance

El diff funcional es solo la CLI y sus tests. No toca `pyproject.toml`, workflows, secretos, autenticación ni despliegue. Security Advisor no aplica.

## Prueba de regresión, repetida fuera del árbol

En un worktree desacoplado de `6d78799`, con `tests/test_cli.py` de este SHA y un venv nuevo de Python 3.12, `pytest -q tests/test_cli.py` terminó en 1 failed, 5 passed. Falló `test_format_both_refuses_output_that_already_ends_in_json` porque `exit_code` era 0. Los otros tres casos nuevos pasaron sobre el código anterior. El test del conflicto distingue el arreglo del fallo. El worktree se borró; no quedó en esta rama.

`Path.with_suffix(".json") == path` en este Linux es verdadero para `informe.json`, `./informe.json`, `informe.json/` y `dir/../informe.json`, y falso para `informe.md`, `informe` e `informe.JSON`. Es la condición que fija el plan.

## Observaciones que no bloquean

- El test del rechazo comprueba que la ruta está en stderr, el código es 1, stdout está vacío y el fichero no existe. No fija la frase entera. La frase del código es la del plan, y el criterio 1 pide la ruta.
- La comprobación va después de cargar la traza y renderizar, y antes de `write_text`. El plan pide eso último.
- Un nombre que es solo `.json` tiene sufijo vacío para `pathlib`, así que no es este conflicto. Queda fuera de los criterios; la condición pedida es la igualdad de `Path`.
