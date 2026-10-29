# Modo CI

## Contexto

`agentcost report` puede fallar un job. La diferencia emparejada sigue siendo la primera variante menos la segunda. El veredicto de coste ya distingue `better`, `worse`, `no_difference` e `inconclusive`.

## Motivo

El código 3 está reservado a una regresión. El 1 sigue siendo un fallo de la herramienta y el 2 el uso inválido de Typer. Así un job no trata un percentil ilegible como si la candidata hubiera empeorado.

`--fail-if-worse` en coste repite el veredicto. En emparejado eso exige al menos 5 pares y un IC del 95 % entero por encima de 0. `--max-regression` no usa ese suelo ni la media: compara el límite inferior de `relative_interval` con el porcentaje, y solo falla si lo supera. Sin pares no hay ese intervalo, así que el umbral sale con código 1 en vez de comparar la estimación puntual.

En un pull request la candidata va primero (`--compare candidate baseline`), porque «peor» es la primera variante.
