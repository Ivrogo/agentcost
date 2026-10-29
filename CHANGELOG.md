# Changelog

Los cambios notables de este proyecto se anotan en este fichero.

El formato es [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added

- Comparación A/B emparejada por `task_id` (v0.2). Si las dos variantes comparten algún `task_id`, el informe da la diferencia por tarea (coste, tokens y pasos), la media, un intervalo de confianza del 95 % por bootstrap y el cambio relativo en % con su intervalo. El modo por defecto empareja cuando hay al menos un id en común; si no hay ninguno, se mantiene la comparación no emparejada y se avisa en el informe y en stderr. `--paired` y `--unpaired` fuerzan el modo. La semilla y el número de remuestreos siguen siendo `--seed` y `--bootstrap` (por defecto 42 y 1000).

### Fixed

- `agentcost report --format both --output RUTA` rechaza una ruta que ya termina en `.json`. Antes el JSON pisaba al Markdown en el mismo fichero. Ahora el proceso sale con código 1, el stderr nombra la ruta y no se crea el fichero. Para los dos formatos usa una ruta como `informe.md` o `informe`. Si solo quieres JSON, usa `--format json --output informe.json`.
