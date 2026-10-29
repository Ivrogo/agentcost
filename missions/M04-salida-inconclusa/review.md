# Review M04

Revisión del diff de `src/agentcost/gate.py`, `src/agentcost/cli.py` y `tests/test_gate.py`. No cubre artefactos de misión ni el README.

## Hallazgos

1. **No bloqueante, corregido en esta pasada.** Si `--metric` no es coste, el veredicto de coste puede ser `inconclusive` y a la vez el chequeo de esa métrica ya haber encontrado regresión, mientras `--max-regression` no se puede aplicar. La primera versión absorbía el error del umbral por el veredicto de coste y salía 3, ocultando que una de las dos puertas no se había podido aplicar. Ahora ese caso sigue en 1, igual que en M03. El inconcluso solo sustituye al 1 cuando el otro chequeo no ha fallado. El camino de coste no cambia: un veredicto `inconclusive` no puede ser a la vez `worse`.

## Comprobado

- El 4 solo sale de `decision.outcome == "inconclusive"` con el flag. El 3 solo sale de `regression`. El 1 de la herramienta sigue en `AgentCostError`.
- `--fail-if-inconclusive` sin `--fail-if-worse` se rechaza antes de leer la traza. Stdout queda vacío. Aunque vaya `--max-regression`, el código es 1 y no 3.
- Con `--fail-if-worse` y veredicto `inconclusive`, sin el flag, la salida es 0 y stderr lleva `Inconclusive:` más `verdict_reason`. Si el umbral no tiene intervalo relativo, la frase se añade y el código no es 1.
- Con menos de 5 pares, si el límite inferior supera el porcentaje, la salida sigue siendo 3, también con `--fail-if-inconclusive`.
- Un `worse` no emparejado con `--max-regression` sigue en 1. Un modelo sin precio, sin `--allow-unpriced`, sigue en 1.
- El informe y el resumen se escriben antes del `Exit`. `**Gate:**` dice `inconclusive`.
- `prices.json` no está en el diff.

## Resultado

Sin bloqueantes abiertos.
