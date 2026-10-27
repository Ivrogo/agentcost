# Misiones

Cada misión vive en `missions/MNN-slug/`. `NN` son dos dígitos y crece de una en una. El slug va en minúsculas y con guiones. Ejemplo de ruta: `missions/M01-informe-json/`.

El proceso, la clasificación y el contrato de `verification.json` están en `AGENTS.md`. Este fichero solo fija el formato.

## Misión ligera

`light`: documentación repartida o configuración no sensible.

- `plan.md`
- `execution.md`
- `verification.json`

## Misión completa

`full`: feature, bugfix, comportamiento, seguridad, datos o trabajo transversal. Además de los tres ficheros de la misión ligera:

- `artifacts/` con la evidencia que cita `verification.json`
- entrada de changelog y documentación o knowledge cuando el cambio lo exija

`plan.md` se escribe antes de cualquier cambio funcional. `execution.md` se actualiza mientras se trabaja. Sin `verification.json` en `status: passed` la misión no está terminada.

Las clases `none` y `simple` no crean directorio de misión.
