# Review M03

Revisión del código de la puerta CI y de `tests/test_gate.py`. No cubre artefactos de misión ni el README.

## Hallazgos

1. **Bloqueante, corregido.** `--markdown-summary` y `--output` podían ser la misma ruta. El informe se escribía y el resumen lo pisaba. `_reject_summary_collision` rechaza esa ruta (también la del JSON de `--format both`) antes de crear ficheros, con salida 1. Test: `test_markdown_summary_refuses_the_report_path`. Pytest completo después del arreglo: 86 passed.

2. **No bloqueante, corregido en el mismo ciclo.** Las etiquetas del resumen decían siempre «95%» aunque el nivel vive en el informe. Ahora usan `report.bootstrap_level`. Con el defecto de la CLI el texto sigue siendo `95%` y el snapshot no cambia.

## Comprobado

- El 3 solo sale de `decision.outcome == "regression"`. Un umbral ilegible y una puerta que no se puede aplicar siguen en el `except AgentCostError` con código 1. Typer conserva el 2.
- Sin flags, un veredicto `worse` sale 0. El test lo fija.
- `--fail-if-worse` en coste usa `report.verdict`, no un segundo criterio. Con menos de 5 pares no falla. `--max-regression` compara `relative_interval.low` con `>` y no usa ese suelo.
- Sin pares, el umbral sale 1 y el resumen se escribe con `Gate: error`. `--fail-if-worse` solo, si el veredicto no emparejado es `worse`, sale 3 y el aviso está en el resumen.
- El resumen se escribe antes del `Exit(3)`. El informe también.
- `drive.sh` solo añade `GITHUB_STEP_SUMMARY` cuando ya viene en el entorno. El resto de features no la definen.
- El workflow de ejemplo no está en `.github/workflows`, no nombra secretos y pone la candidata primero.

## Resultado

Sin bloqueantes abiertos.
