# Sufijo `.json` con `--format both`

## Contexto

Con `--format both`, el Markdown se escribe en la ruta de `--output` y el JSON en esa misma ruta tras `Path.with_suffix(".json")`. Si el sufijo ya es `.json`, `with_suffix` deja la ruta igual. Las dos escrituras serían el mismo fichero y la segunda pisaría a la primera sin avisar.

## Motivo

Esa combinación se rechaza antes de crear el fichero. La CLI sale con código 1 y el stderr nombra la ruta recibida:

```text
--format both would write Markdown and JSON to the same path: <ruta>
```

Para los dos informes, `--output` no puede terminar en `.json`. `informe.md` deja el Markdown ahí y el JSON en `informe.json`. `informe` deja el Markdown en `informe` y el JSON en `informe.json`. Si solo hace falta el JSON, `--format json --output informe.json` sigue escribiendo ese único fichero.

La comparación es la del sufijo que usa `with_suffix`, no una ruta resuelta ni un plegado de mayúsculas. En un sistema que las distingue, `.JSON` no es `.json` y no dispara este rechazo.
