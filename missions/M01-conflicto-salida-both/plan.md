# M01 — Conflicto de salida con `--format both`

## Clase y capacidad

- Clase: `full`. Es un bugfix que cambia el comportamiento de la CLI.
- Capacidad: `standard`. La lógica cabe en `src/agentcost/cli.py` y los cuatro casos en `tests/test_cli.py`. No hay arquitectura nueva, concurrencia, datos persistentes ni secretos.
- `model_tier_used`: `standard`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultada `.agents/knowledge/README.md`. No hay fichas. No existe una decisión reutilizable que aplicar ni que corregir.

La conducta actual está descrita en dos sitios, y ninguno la da por buena cuando las rutas coinciden:

- `README.md`, fila de `--output`: con `--format both`, el JSON usa la misma ruta con sufijo `.json`.
- `.cursor/skills/verify-agentcost/features/report-output.md`, gotcha: un `--output` que ya termina en `.json` haría coincidir Markdown y JSON. Pide no usar ese caso como atajo del feature de escritura. Documenta el fallo; no es el comportamiento que hay que conservar.

## Petición

Con `agentcost report ... --format both --output RUTA`, el Markdown se escribe en `RUTA` y el JSON en `RUTA.with_suffix('.json')`. Si `RUTA` ya termina en `.json`, las dos escrituras son el mismo fichero y el JSON pisa al Markdown sin avisar.

## Causa

En `_emit_report` (`src/agentcost/cli.py`), tras escribir el Markdown, se hace `json_path = output.with_suffix(".json")` y se escribe el JSON. `Path.with_suffix(".json")` deja igual una ruta cuyo sufijo ya es `.json`. El estado es legítimo: el usuario puede pedir esa combinación. El fallo es no decidir, antes de crear nada, que los dos destinos son el mismo.

No es un fallo de `render_markdown` ni de `render_json`. Esos renderizados hacen lo que se les pide. El primer sitio que hace algo que no debe es la elección del segundo destino y la escritura que le sigue.

## Cambio

Solo con `--format both`, si `output.with_suffix(".json") == output`, lanzar `AgentCostError` antes de cualquier `write_text`. El `except AgentCostError` de `report` ya escribe el mensaje en stderr y sale con código 1.

El mensaje nombra la ruta en conflicto, la que recibió `--output`:

```text
--format both would write Markdown and JSON to the same path: <ruta>
```

`AgentCostError` ya existe y ya es la excepción que la CLI convierte en salida 1. No hace falta un tipo nuevo. `PriceError` no describe este caso.

No se normalizan mayúsculas ni se resuelven enlaces simbólicos. El criterio es el sufijo `.json` que `with_suffix` deja intacto. `.JSON` no es ese caso.

## Criterios de aceptación

1. `agentcost report examples/research_agent/traces.jsonl --compare A B --format both --output informe.json` sale con código 1, el stderr contiene la ruta en conflicto y `informe.json` no se crea.
2. `--output informe.md --format both` sigue creando `informe.md` (contiene `**Verdict:** better`) e `informe.json` (contiene `"verdict": "better"`).
3. `--output informe --format both` mantiene el comportamiento actual: Markdown en `informe`, JSON en `informe.json`.
4. `--format json --output informe.json` sigue escribiendo solo JSON y sale 0.
5. Los cuatro casos tienen test en pytest, en `tests/test_cli.py`, sobre `examples/research_agent/traces.jsonl`.

## Fuera de alcance

- Review de código y `verification.json`. Los emite otro agente. Esta misión no se cierra aquí.
- Documentación de uso: la fila de `--output` en `README.md`, el gotcha de `features/report-output.md` y un changelog que el repositorio aún no tiene. Corresponden a Documentación, después de Review y Validación.
- `.github/`, secretos, `pyproject.toml`, precios y el renderizado.

## Security Advisor

No aplica. El cambio no toca autenticación, concurrencia, migraciones, secretos, despliegue, workflows ni dependencias. Los globs de `.cursor/rules/security-advisor.mdc` no entran.

## Pruebas que pide el codificador

TDD: el test del criterio 1 tiene que fallar en el código actual (el fichero se crea y el proceso sale 0). Los criterios 2, 3 y 4 describen conducta que ya existe y deben pasar antes y después del arreglo.

La Validación, con la skill `verify-agentcost`, queda para el otro agente: pytest en 3.10, 3.11 y 3.12, ruff, instalación limpia y la CLI real. Esta sesión no emite ese veredicto.

## Roles

| Fase | Dueño |
| --- | --- |
| Plan | Esta sesión, porque no había misión previa y `plan.md` tiene que existir antes del cambio funcional. |
| Implementación/TDD | Esta sesión. El usuario asignó el papel de codificador. |
| Review de código | Otro agente. |
| Validación | Otro agente. |
| Documentación | Pendiente de esos dos gates. |
| Publicación | Autorizada en la petición: commit, push a `fix/report-output-conflict`, un PR con base `chore/harness-pstack`. Sin merge. |

## Riesgos

- Comprobar el conflicto después de escribir el Markdown dejaría `informe.json` creado. El rechazo va antes de las dos escrituras.
- Rechazar también `--format json` rompería el criterio 4. La comprobación solo corre con `both`.
- Comparar el nombre con `endswith(".json")` en vez de la igualdad de `Path` no es la decisión que toma el código. La condición del fallo es `with_suffix(".json") == output`.
