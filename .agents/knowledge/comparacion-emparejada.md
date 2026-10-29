# Comparación emparejada por task_id

## Contexto

`compare` puede emparejar las dos variantes por `task_id`. El resultado vive en `report.pairing` (`Pairing`). `assess_pairing` devuelve el mismo objeto a partir de observaciones por tarea. El modo CI lee ese objeto.

## Motivo

La diferencia de una tarea es la primera variante menos la segunda, sobre el total de la tarea (todas las runs, fallos incluidos). Negativo en coste significa que la primera es más barata. El cambio relativo es `100 * media(primera - segunda) / media(segunda)`. Si la media de la segunda es 0, el relativo queda indefinido.

El veredicto emparejado usa el intervalo de `pairing.cost`, no el solape de `intervals`. `intervals` sigue siendo el IC de coste por tarea resuelta de cada brazo. No son el mismo número: uno divide por tareas resueltas y el otro es la media de las diferencias por tarea. Pueden discrepar cuando el número de éxitos no coincide.

`includes_zero` es verdadero si el extremo del IC toca el 0. Con menos de 5 pares el veredicto es `inconclusive` aunque el IC no contenga el 0. `--fail-if-worse` en coste lee ese veredicto. `--max-regression` lee el límite inferior de `relative_interval` y no aplica el suelo de 5 pares.

`auto` empareja si hay al menos un `task_id` en común. Si no hay ninguno, el modo es `unpaired` y `warning` lleva el texto que también se escribe en stderr. `--paired` sin ningún id en común es un error. `--unpaired` no avisa y no tira tareas. La semilla y los remuestreos son los de `--seed` y `--bootstrap` (42 y 1000). Cada métrica remuestrea con su propio `random.Random(seed)` sobre los ids ordenados.

Las trazas no tienen latencia. El resultado no trae esa métrica.
