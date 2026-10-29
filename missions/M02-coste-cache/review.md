# Review de código — M02

Self-review de la misma sesión. El encargo pide esa revisión antes de dar el PR por listo; no hay un segundo revisor en esta ejecución. SHA de trabajo: el árbol aún no está commiteado. El diff funcional es `src/agentcost/{models,parse,pricing,report}.py`, `src/agentcost/data/prices.json`, `tests/test_cache.py`, `tests/test_cli.py` y `tests/test_pricing.py`.

Regla cargada: `harness.mdc`. Se leyó `security-advisor.mdc`; sus globs no entran.

Skills cargadas: `verify-agentcost`, `principle-fix-root-causes`, `principle-prove-it-works`, `principle-subtract-before-you-add`.

## Veredicto

Aprobado. No queda un fallo bloqueante. No se reabre Implementación.

## Requisitos

1. OpenAI, uso documentado `prompt_tokens` 2006 con `cached_tokens` 1920: la entrada ordinaria queda en 86. El coste con `gpt-4o` es `0.005615`. Sumar otra vez los 1920 daría `0.010415` y el test lo rechaza. El ahorro es `0.0024`. Los tokens del brazo son 2306, el `total_tokens` publicado, no 4226.
2. Anthropic, uso documentado: `input_tokens` se queda en 2048. Lectura 1800, escritura 148 a 5 minutos y 100 a 1 hora. El coste con `claude-sonnet-4` es `0.015384`. Restar la caché de la entrada daría `0.009240` y el test lo rechaza. Los tokens del brazo son 4599 (2048+1800+148+100+503): el total de escritura no se suma otra vez.
3. Sin el objeto `cache_creation`, `cache_creation_input_tokens` va entero a 5 minutos.
4. `examples/research_agent/traces.jsonl` sigue en `0.000498375` y `0.0104`, con ahorro 0 y filas de caché a `$0`.
5. Sin precio de caché se usa el de entrada, el ahorro de ese tramo es 0 y el informe nombra el modelo. `claude-3-5-sonnet` y Gemini no tienen tarifa de caché en la tabla. Un 0 explícito es gratis y no avisa.
6. Un fichero de precios sustituye `cache_read`. `--set-price` solo fija entrada y salida: la caché queda ausente y el informe avisa. La CLI lo demuestra con `0.008015` frente a `0.005615`.
7. OTel resta `gen_ai.usage.cache_read.input_tokens` y `gen_ai.usage.cache_write.input_tokens` de la entrada. Si no caben, la traza se rechaza. La escritura sin TTL queda en el cubo de 5 minutos.
8. Markdown y JSON desglosan entrada, salida, lectura y escritura, y muestran el ahorro. No hay un tercer formato de texto. `schema_version` sigue en `0.1`. El veredicto y el bootstrap no se han reescrito.

## Causa y calidad

El fallo que había que evitar es cobrar dos veces el mismo token. El primer sitio donde el sistema decide eso es el parser, no el informe: OpenAI resta, Anthropic suma, OTel resta porque la convención ya mete la caché en `input_tokens`. El precio solo ve cubos disjuntos.

Durante esta lectura se corrigió un descarte silencioso: un `cache_read_tokens` plano al lado de un objeto `tokens` se ignoraba. Ahora es un error, salvo que el objeto traiga el mismo número. Entrada y salida planas siguen ignorándose cuando hay `tokens`, que es la conducta de la v0.1.

No se añadió un formato nuevo, ni un cliente de Langfuse, ni tarifas para modelos que la página oficial no lista. `compare` sigue devolviendo un coste por tarea; ese coste es la suma de los cubos.

## Alcance

No se tocan `pyproject.toml`, workflows, secretos ni autenticación. Security Advisor no aplica. El código del veredicto (`_verdict`, `_bootstrap`) no cambia. Otro PR puede seguir emparejando tareas sobre `task.cost`.

## Observaciones que no bloquean

- `cache_write_tokens` de OpenAI distinto de cero se rechaza. Esas escrituras (30 min y 12 h) ya van dentro de `input_tokens` y la tabla no publica su precio. Ignorarlas las cobraría como entrada.
- La escritura OTel, sin atributo de TTL, se anota como 5 minutos. Una escritura de 1 hora que solo llegue por OTel se cobra a tarifa de 5 minutos si el modelo la tiene. El `usage` de Anthropic sí separa la hora.
- `--set-price MODEL=INPUT:OUTPUT` no arrastra la caché del modelo sustituido. El fichero de precios sí puede fijarla. Hay que decirlo en el README.
- Un id que hereda por prefijo hereda también la caché. `gpt-4o-2024-05-13` en la página de OpenAI no tiene cached input; el prefijo `gpt-4o` sí. Ya heredaba la entrada. El README tiene que decir que un id que no deba heredar se sobrescribe con una fila propia.
