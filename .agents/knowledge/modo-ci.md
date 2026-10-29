# Modo CI

## Contexto

`agentcost report` puede fallar un job. La diferencia emparejada sigue siendo la primera variante menos la segunda. El veredicto de coste ya distingue `better`, `worse`, `no_difference` e `inconclusive`.

## Motivo

El código 3 está reservado a una regresión. El 1 es un fallo de la herramienta y el 2 el uso inválido de Typer. El 4 es un veredicto `inconclusive`, y solo con `--fail-if-inconclusive` junto a `--fail-if-worse`. Sin ese flag el inconcluso sale 0 y el motivo va a stderr, así que un job no lo confunde con un error de uso ni con una regresión.

`--fail-if-worse` en coste repite el veredicto. En emparejado eso exige al menos 5 pares y un IC del 95 % entero por encima de 0. Con menos pares el veredicto es `inconclusive` y, por defecto, no falla. `--max-regression` no usa ese suelo ni la media: compara el límite inferior de `relative_interval` con el porcentaje, y solo falla si lo supera. Sin pares no hay ese intervalo. Si el veredicto es `inconclusive` y se pidió `--fail-if-worse`, eso sale 0 (o 4), no 1. Si el veredicto no es inconcluso, el umbral sin pares sigue saliendo 1.

En un pull request la candidata va primero (`--compare candidate baseline`), porque «peor» es la primera variante.
