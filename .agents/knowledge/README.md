# Knowledge base

Esta carpeta es la knowledge base de agentcost. En Plan se leen las entradas que apliquen y se citan en `plan.md`. Al documentar una misión se añade una entrada solo si el conocimiento sirve en otra misión.

Cabe aquí:

- una decisión de arquitectura, con el motivo
- un patrón que ya se haya probado en este repositorio
- un gotcha que vuelva a aparecer
- una convención que el código cumple y que no está escrita en otro sitio

No cabe aquí:

- una entrada vacía o un resumen que repita `AGENTS.md`, el README o una skill
- la evidencia de una misión (eso va en `missions/<id>/evidencias.log`)
- un secreto, una credencial o un dato de un entorno concreto

Una ficha nueva es un fichero Markdown junto a este README, con título, contexto y motivo. Si una entrada es incorrecta, se corrige en su sitio.

Entradas:

- [Sufijo `.json` con `--format both`](formato-both-salida-json.md). Un `--output` que ya termina en `.json` se rechaza, porque `with_suffix` no cambiaría la ruta.
- [Comparación emparejada por task_id](comparacion-emparejada.md). La diferencia es la primera variante menos la segunda. El veredicto emparejado lee `pairing.cost`, no el solape de `intervals`.
