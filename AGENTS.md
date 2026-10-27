# AGENTS.md

Este fichero es el proceso de los agentes en agentcost. Los criterios de calidad no se copian aquí: viven en las skills de `.cursor/skills/`. La regla `.cursor/rules/harness.mdc` solo recuerda seguir este proceso.

## Entorno

- Python. `requires-python` es `>=3.10`. Los clasificadores de `pyproject.toml` y la matriz de `.github/workflows/ci.yml` fijan 3.10, 3.11 y 3.12.
- Tests: `pytest` sobre `tests/`, lanzado desde la raíz del repositorio.
- Lint y formato: `ruff check .` y `ruff format --check .`, también desde la raíz. En la CI solo corren en Ubuntu con Python 3.12.
- Desarrollo, en un venv nuevo: `python -m pip install -e ".[dev]"`.
- Instalación limpia, en otro venv nuevo, sin el extra `dev`: `python -m pip install .`. La CLI se ejecuta con el directorio de trabajo fuera del árbol de fuentes.
- No hay lockfile. Las dependencias son rangos en `pyproject.toml`.
- CI: `.github/workflows/ci.yml`, en `push` y en `pull_request`, sin filtro de rama. Matriz de Ubuntu, macOS y Windows por Python 3.10, 3.11 y 3.12. Incluye la instalación limpia del wheel, `agentcost report` sobre `examples/research_agent/traces.jsonl` y, en Ubuntu con 3.12, una prueba con pipx.
- Caso real de la CLI: `examples/research_agent/`.

Cómo ejecutar pytest, la instalación limpia, la matriz de versiones y la CLI, y cómo volcar cada ejecución a `verification.json`, está en la skill `verify-agentcost`.

## Clasificación

Antes de editar, clasifica el cambio. La clasificación mide solo el cambio funcional. Los artefactos de misión no cuentan. La petición orienta, pero no rebaja a `simple` un cambio que incumple sus límites.

| Clase | Cuándo | Qué obliga |
| --- | --- | --- |
| `none` | Consulta, diagnóstico o revisión de solo lectura. | No crea misión. |
| `simple` | Edición puntual, mecánica o documental de un único fichero, sin lógica de producto, runtime, dependencias, datos, seguridad, permisos, despliegue ni riesgo de regresión. | Se implementa directamente, sin misión, sin TDD, sin Review independiente y sin `verification.json`. Comprobación mínima: revisar el diff y el alcance, ejecutar el check de sintaxis o formato que aplique y confirmar el estado de Git. |
| `light` | Cambio trivial que excede `simple`: documentación repartida o configuración no sensible. | Misión ligera. |
| `full` | Feature, bugfix, cambio de comportamiento, seguridad, datos o trabajo transversal. | Misión completa. |

## Ciclo de vida

`Plan → Implementación/TDD → Review de código → Validación → Documentación → Publicación autorizada`. Cada fase tiene un dueño distinto. Los gates son explícitos.

1. **Plan (orquestador).** Alcance, criterios de aceptación, riesgos, clase, capacidad, roles, pruebas y artefactos. Consulta la knowledge base y cita las entradas que uses. Escribe `plan.md` antes de cualquier cambio funcional. Si pidieron implementar, sigue adelante salvo una decisión material abierta, un riesgo sensible sin aprobar o una petición de «solo plan».
2. **Implementación/TDD (codificador).** RED antes de tocar código de producción, cambio mínimo, GREEN y refactor manteniendo GREEN. Si el TDD no es viable, registra en `execution.md` la causa y la verificación alternativa antes de implementar.
3. **Review de código (revisor distinto del codificador).** Revisa solo código y elementos funcionales (tests, seguridad, datos, configuración de runtime): requisitos, calidad, antipatrones y alcance. No aprueba con bloqueantes abiertos. No revisa artefactos de misión ni documentación, salvo que contengan código ejecutable. Una vez por versión funcional del código.
4. **Validación (validador independiente del codificador).** Repite los checks sin fiarse de resultados previos. No edita código de producción. Emite `verification.json` con evidencia. Si algo falla, vuelve a Implementación.
5. **Documentación (documentador).** Tras Review y Validación en OK. Actualiza uso, configuración, pruebas, limitaciones y changelog. Persiste solo conocimiento reutilizable. Comprueba alcance, enlaces, formato y contradicciones.
6. **Publicación autorizada (responsable de entrega).** Solo la acción concreta autorizada, tras los gates.

Entre Documentación y Publicación hay una comprobación final acotada del estado de Git y de la coherencia de los artefactos. No es otra Review. Solo se reabren Review y Validación si en Documentación cambió código, tests, seguridad, datos, configuración funcional o runtime.

## Vuelta a Implementación y escalado

Si falla un gate de código o de validación funcional, se reabre Implementación y se repiten Review y Validación. Un defecto que solo afecta a documentación o artefactos se corrige en Documentación. Corregir y escalar la capacidad son decisiones separadas. El fallo se registra con evidencia.

Si la capacidad fue insuficiente se escala `trivial → standard → complex`. En `complex` se corrige y se revalida. No se inventa otro escalado.

| Tier | Señales | Capacidad |
| --- | --- | --- |
| `trivial` | Un fichero, sin lógica nueva ni riesgo. | Ligera, siguiendo las instrucciones al pie de la letra. |
| `standard` | 2 a 5 ficheros, lógica acotada, arreglo localizado. | Sólida de implementación y pruebas. |
| `complex` | Más de 5 ficheros, trabajo transversal, arquitectura, fallo que no se reproduce, seguridad, concurrencia o datos. | La máxima disponible. |

Autenticación, concurrencia, migraciones de datos, secretos, configuración de despliegue o borrado de datos históricos fuerzan al menos `standard` y activan el Security Advisor. Solo se registra una selección de modelo si el runtime permite elegirla. Si no, se documenta la capacidad usada en `model_tier_used`.

## Artefactos de misión

Directorio `missions/MNN-slug/`. El índice y el formato están en `missions/README.md`.

- Misión ligera: `plan.md`, `execution.md`, `verification.json`.
- Misión completa: además `artifacts/`, entrada de changelog y documentación o knowledge cuando corresponda.
- `execution.md` se actualiza durante el trabajo: comandos, decisiones, reintentos, escalados y motivos.
- `plan.md` precede siempre a los cambios funcionales.
- La evidencia es concisa y versionable (`.txt`, `.json`): salida final, RED relevante y los diagnósticos necesarios. No se guardan logs repetitivos completos.
- `verification.json` es el gate de cierre. Sin `status: passed` la misión no está terminada.

## Contrato de `verification.json`

Cada check tiene `name`, `command`, `result` (`pass`, `fail` o `skipped`), `detail` y `evidence`. Todo `skipped` exige una justificación no vacía y aceptable. `status: passed` solo si no hay ningún `fail` y todos los skips están justificados. Cualquier `fail` obliga a `status: failed` y reabre Implementación.

El documento incluye también `task`, `environment` (`runtime`, versión de Python y `base_commit`), `model_tier_used`, `escalations` y la lista `evidence`.

La validación incluye tests unitarios, integración o punta a punta cuando el cambio cruza componentes, y lint, formato y build cuando apliquen.

```json
{
  "status": "passed",
  "task": "M01-ejemplo",
  "checks": [
    {"name": "unit_tests", "command": "pytest -q", "result": "pass", "detail": "exit 0", "evidence": "artifacts/pytest.txt"},
    {"name": "e2e_cli", "command": "not run", "result": "skipped", "detail": "No aplica: cambio solo documental", "evidence": "artifacts/scope.txt"}
  ],
  "environment": {"runtime": "venv limpio", "python": "3.12", "base_commit": "0123abc"},
  "model_tier_used": "standard",
  "escalations": 0,
  "evidence": ["artifacts/pytest.txt", "artifacts/scope.txt"]
}
```

## Seguridad

El Security Advisor revisa, antes de implementar, los cambios de autenticación, concurrencia, migraciones, secretos, despliegue y borrado histórico. Mira el alcance, la integridad, la pérdida de datos, los comandos, los contratos funcionales, las APIs y la sintaxis. La última línea del veredicto es `[YES] Reason: ...` o `[NO] Reason: ...`. La regla `.cursor/rules/security-advisor.mdc` exige esa línea cuando el cambio toca sus globs. Un `[NO]` bloquea Implementación: se enmienda el plan y se pide una revisión nueva hasta un `[YES]`. Los controles de interfaz o de cliente nunca sustituyen a los del servidor. Privilegio mínimo y validación de entradas en la capa que ejecuta la operación.

agentcost v0.1 no tiene autenticación ni despliegue propio. El asesor entra si el cambio introduce esos ficheros, toca workflows, Docker, secretos o las dependencias de `pyproject.toml`.

## Knowledge base

Ruta canónica: `.agents/knowledge/`. El README de esa carpeta dice qué se guarda. En Plan se consultan y se citan las entradas relevantes. Al documentar se guardan solo decisiones de arquitectura con motivo, patrones probados, gotchas y convenciones implícitas. Nada de entradas vacías, resúmenes duplicados ni evidencia específica de una misión. Si una entrada es incorrecta, se corrige.

## Commit, push y PR

Son acciones y autorizaciones separadas. Autorizar un commit no autoriza el push ni el PR. Autorizar el push no autoriza el PR. La autorización nombra la acción y el alcance. Pasar los tests, un commit local o una autorización anterior no amplían el permiso. Cada autorización de push es de un solo uso y queda ligada al remoto, a la rama y al alcance. No hay push a `main` ni merge sin una autorización explícita nueva del dueño del repositorio. No se hace push ni PR por iniciativa del agente.

## Qué citar en el PR

Todo agente cita en el cuerpo del PR, por su nombre, la regla `harness.mdc` y cada skill que haya cargado. Los nombres de las skills de este repositorio son `verify-agentcost`, `principle-prove-it-works`, `principle-fix-root-causes` y `principle-subtract-before-you-add`.

El bloque «Pruebas» del PR es un resumen de `verification.json`: lo que se hizo y lo que quedó «sin comprobar». No es un segundo sistema de verificación. Si la clase es `none` o `simple` y no existe `verification.json`, el bloque dice esa clase y la comprobación mínima.

## Skills

Los criterios de calidad están solo en:

- `.cursor/skills/principle-prove-it-works/`
- `.cursor/skills/principle-fix-root-causes/`
- `.cursor/skills/principle-subtract-before-you-add/`

Esos tres principios proceden de pstack. Licencia MIT, Copyright (c) 2026 Lauren Tan. El texto íntegro está en `.cursor/skills/LICENSE-pstack`.

La verificación ejecutable de la CLI, de pytest y de la instalación está en `.cursor/skills/verify-agentcost/`.
