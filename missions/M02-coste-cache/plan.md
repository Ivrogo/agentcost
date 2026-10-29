# M02 — Coste de tokens cacheados por proveedor

## Clase y capacidad

- Clase: `full`. Cambia el cálculo del coste, el modelo de uso, la tabla de precios y el informe. No es un retoque de un solo fichero.
- Capacidad: `complex`. El cambio cruza parser, precios e informe (más de cinco ficheros) y el fallo que hay que evitar es contar dos veces el mismo token. No hay concurrencia, autenticación ni migraciones.
- `model_tier_used`: `complex`. Este runtime no permite elegir otro modelo para la fase.

## Knowledge base

Consultada `.agents/knowledge/README.md` y [formato-both-salida-json.md](../../.agents/knowledge/formato-both-salida-json.md).

- La ficha del sufijo `.json` no aplica: este cambio no toca `--format both`.
- No hay una ficha previa sobre precios ni sobre uso. La decisión de cómo se separan los tokens cacheados se escribe al documentar, porque la siguiente misión va a volver a tropezar con ella.

## Referencia

Langfuse desglosa `usage_details` y `cost_details` por tipo de uso (entrada, salida, lectura de caché, escritura de caché). Sirve de forma del desglose. No se importa código, ni precios, ni un cliente de Langfuse.

Otro agente cambia a la vez la comparación A/B emparejada. Aquí no se toca el veredicto, el bootstrap ni el emparejamiento. El coste de la tarea sigue siendo un número; ese número ahora incluye el desglose de caché.

## Hechos de las APIs (consultados el 2026-10-29)

- OpenAI, [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) y el ejemplo de [Prompt Caching in the API](https://openai.com/index/api-prompt-caching/) (1 de octubre de 2024): `prompt_tokens` (Chat Completions) e `input_tokens` (Responses) **ya incluyen** `cached_tokens`. El ejemplo documentado es `prompt_tokens: 2006`, `completion_tokens: 300`, `total_tokens: 2306`, `prompt_tokens_details.cached_tokens: 1920`. La entrada ordinaria es `2006 - 1920 = 86`.
- OpenAI, misma guía, modelos recientes: `input_tokens` también puede incluir `cache_write_tokens` (30 min y 12 h). Los modelos de la tabla empaquetada no publican ese precio (la columna sale vacía o en otra tabla de modelos nuevos). Esta versión no inventa una tarifa de escritura de OpenAI.
- Anthropic, [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching): `input_tokens` **no** incluye la caché. `cache_read_input_tokens` y `cache_creation_input_tokens` van aparte. `cache_creation.ephemeral_5m_input_tokens` + `ephemeral_1h_input_tokens` suman `cache_creation_input_tokens`. El ejemplo documentado es `input_tokens: 2048`, lectura `1800`, escritura `248` (`5m: 148`, `1h: 100`), `output_tokens: 503`. El TTL por defecto, si no viene el desglose, es 5 minutos.
- OpenTelemetry GenAI: `gen_ai.usage.cache_read.input_tokens` y `gen_ai.usage.cache_write.input_tokens` **deben ir incluidos** en `gen_ai.usage.input_tokens`. El README de v0.1 ya lo dice. No se leen los subatributos `text` / `audio` / `image`, porque la convención los incluye en el agregado.

Precios por millón, páginas oficiales, 2026-10-29. Entrada y salida de la tabla `2026-10-01` coinciden con esas páginas en los modelos que siguen publicados. No se cambian esas cifras.

| Modelo en la tabla | cache_read | cache_write_5m | cache_write_1h | Fuente |
| --- | --- | --- | --- | --- |
| `gpt-4o` | 1.25 | — | — | https://developers.openai.com/api/docs/pricing |
| `gpt-4o-mini` | 0.075 | — | — | misma |
| `gpt-4.1` | 0.50 | — | — | misma |
| `gpt-4.1-mini` | 0.10 | — | — | misma |
| `gpt-4.1-nano` | 0.025 | — | — | misma |
| `o4-mini` | 0.275 | — | — | misma |
| `o3-mini` | 0.55 | — | — | misma |
| `claude-sonnet-4` | 0.30 | 3.75 | 6 | https://platform.claude.com/docs/en/about-claude/pricing |
| `claude-3-5-haiku` | 0.08 | 1 | 1.60 | misma (Claude Haiku 3.5) |
| `claude-3-5-sonnet` | — | — | — | No está en esa página. No se inventa tarifa de caché. |
| `gemini-2.5-flash`, `gemini-2.5-pro` | — | — | — | Esta misión no trae página de caché de Gemini. No se inventa tarifa. |

## Modelo interno

`Event` gana tres contadores, a 0 si la traza no los trae:

- `input_tokens`: entrada que se cobra a precio de entrada. No se solapa con la caché.
- `cache_read_tokens`: lectura. En OpenAI es `cached_tokens`. En Anthropic es `cache_read_input_tokens`.
- `cache_write_5m_tokens` y `cache_write_1h_tokens`: escritura de Anthropic. OpenAI no tiene estas dos tarifas en esta versión.

La suma de tokens de una tarea es entrada + salida + lectura + las dos escrituras. En una traza v0.1 los tres campos nuevos son 0 y la suma no cambia.

## Cómo entra una traza (sin romper el formato v0.1)

1. **`tokens` o campos planos, sin `usage`.** Forma canónica de agentcost, disjunta. `tokens.input` no incluye la caché. `tokens.cache_read`, `tokens.cache_write_5m` y `tokens.cache_write_1h` se suman. Una línea v0.1 no trae esas claves y sigue igual. `provider` sin `usage` no resta ni suma: no se adivina la convención.
2. **`provider` + `usage`, copiado de la respuesta documentada.** No puede convivir con `tokens` ni con `input_tokens` / `output_tokens` / los campos planos de caché: sería ambiguo y se rechaza.
   - `openai`: entrada = `prompt_tokens` o `input_tokens` menos `cached_tokens`. Salida = `completion_tokens` o `output_tokens`. `total_tokens`, si viene, tiene que ser entrada bruta + salida (el ejemplo 2306). `cache_write_tokens` distinto de cero es un error: va dentro de `input_tokens` y esta versión no tiene tarifa de escritura de OpenAI; ignorarlo los cobraría como entrada normal.
   - `anthropic`: `input_tokens` se queda. La lectura se suma. Si viene el desglose `cache_creation`, se usa ese y no se vuelve a sumar `cache_creation_input_tokens`. Si solo viene el total, todo va a 5 minutos. Si ambos vienen y no cuadran, error.
3. **OTel.** Se restan los dos atributos agregados de `gen_ai.usage.input_tokens`. La escritura, sin TTL en la convención, se anota como 5 minutos (el TTL por defecto de Anthropic). Si la caché supera a `input_tokens`, error: no hay forma honesta de separarlos.

## Precio y ahorro

`ModelPrice` gana `cache_read_per_million`, `cache_write_5m_per_million` y `cache_write_1h_per_million`, opcionales, y `source` / `as_of` opcionales. Un precio ausente no es cero.

Coste del evento:

```text
entrada * precio_entrada
+ salida * precio_salida
+ lectura * precio_lectura
+ escritura_5m * precio_5m
+ escritura_1h * precio_1h
```

todo dividido por 1_000_000. Si hay tokens de caché y el modelo no tiene ese precio, se usa el de entrada y el informe nombra el modelo y el componente. El ahorro de ese componente es cero. No se inventa un multiplicador.

Ahorro frente a cobrar lectura y escritura a precio de entrada:

```text
lectura * (entrada - lectura) + escritura_5m * (entrada - 5m) + escritura_1h * (entrada - 1h)
```

La escritura de Anthropic es más cara que la entrada (1,25× y 2×). El ahorro de esa parte sale negativo. El informe muestra el neto con signo. Una traza sin caché da ahorro 0.

La versión de la tabla pasa a `2026-10-29`. Entrada y salida no cambian, así que `examples/research_agent/traces.jsonl` conserva el coste.

## Sobrescritura

El mecanismo actual se queda:

- Un fichero `--prices` / `PriceTable.merge` sustituye el modelo entero. Para conservar o cambiar la caché hay que repetir las claves. Si no están, el precio de caché queda ausente.
- `PriceTable.override` y `ModelPrice` aceptan los tres precios.
- `--set-price MODEL=INPUT:OUTPUT` sigue fijando solo entrada y salida. No arrastra la caché del modelo anterior: el objeto que instala no la trae. Si la traza tiene caché, el informe avisa y usa el precio de entrada.

Un 0 explícito es gratis. No es lo mismo que omitir la clave.

## Informe

Markdown (el texto que ya existe) y JSON ganan, por brazo:

- coste de entrada, de salida, de lectura y de escritura
- la escritura muestra el reparto 5 min / 1 h cuando no es cero
- ahorro de caché frente al precio de entrada
- aviso `cache_priced_as_input` cuando hubo que usar el precio de entrada

`schema_version` sigue en `0.1`: se añaden claves. El veredicto y `cost_per_solved_task` de la traza v0.1 no se mueven. No hay un tercer formato de texto; no se crea uno.

`total_cost` es la suma del desglose. El bootstrap sigue usando ese total. Los tokens del brazo incluyen la caché.

## Criterios de aceptación

1. OpenAI, números del anuncio: 86 de entrada a 2,50, 1920 de lectura a 1,25 y 300 de salida a 10, por millón, cuestan `0.005615`. Cobrar `prompt_tokens` y `cached_tokens` a la vez daría `0.010415` y el test lo rechaza. El ahorro es `0.0024`.
2. Anthropic, números de la guía: la entrada se queda en 2048. El coste con `claude-sonnet-4` es `0.015384`. Restar la caché de `input_tokens` daría `0.009240` y el test lo rechaza. El ahorro neto es `0.004449`.
3. Sin el desglose 5m/1h, `cache_creation_input_tokens` va entero a 5 minutos y no se suma otra vez.
4. Una traza v0.1 (`examples/research_agent/traces.jsonl` y un evento sin campos de caché) da el mismo coste, los mismos tokens y ahorro 0.
5. Un modelo sin precio de caché, con tokens de caché, usa el de entrada, el ahorro de ese tramo es 0 y el informe lo nombra. `claude-3-5-sonnet` y Gemini no ganan precios inventados.
6. Un fichero de precios puede fijar `cache_read`, `cache_write_5m` y `cache_write_1h`, y ese valor gana al de la tabla.
7. OTel resta la caché de `input_tokens`. Si no cabe, la traza se rechaza.
8. README (caché y sobrescritura) y CHANGELOG `[Unreleased]` describen v0.2. La traza de punta a punta está construida a partir de las respuestas documentadas, no de una llamada en vivo, y el PR pega la salida de la CLI.

## Fuera de alcance

- Escrituras de OpenAI a 30 minutos y a 12 horas. Error de parseo si el contador viene distinto de cero, para no cobrarlas como entrada normal.
- Sincronizar con LiteLLM o tokencost. Precios nuevos de modelos que no estaban en la tabla.
- Emparejar tareas entre variantes, veredicto y bootstrap, salvo que el total de la tarea ahora suma la caché.
- Subir la versión del paquete, tag o release.
- Un formato de informe que no exista ya.

## Security Advisor

No aplica. No se tocan autenticación, secretos, workflows, Docker, `pyproject.toml` ni despliegue. Los globs de `.cursor/rules/security-advisor.mdc` no entran.

## Pruebas

TDD: los tests de los criterios 1 y 2 tienen que fallar antes de analizar `usage`. El criterio 4 tiene que pasar antes y después.

Validación con la skill `verify-agentcost`: pytest en 3.10, 3.11 y 3.12, ruff, instalación limpia y la CLI real sobre `examples/research_agent/traces.jsonl`. Además, la CLI sobre la traza de caché, con la salida pegada en el PR. `verification.json` con `status: passed` cierra la misión.

## Roles

Esta sesión recorre el ciclo porque el encargo pide el PR listo, no solo el plan. La review es una self-review escrita en `review.md` antes de dar el PR por listo. La validación repite los comandos y no se fía del pytest de la implementación.

## Riesgos

- Tratar `tokens.input` como si ya incluyera la caché rompería las trazas v0.1 que metieron ahí toda la entrada. La forma canónica sigue siendo disjunta. Solo `usage` aplica la regla del proveedor.
- Heredar por prefijo el `cache_read` de `gpt-4o` a un id fechado que la página marca sin caché. Ya se heredaba el precio de entrada. El README dice que un id que no deba heredar se sobrescribe con una fila propia.
- Sustituir un modelo en un fichero de override sin repetir la caché apaga el descuento. El informe avisa. El README lo dice.
- Borrar el coste de la traza de investigación al cambiar la versión de la tabla. Entrada y salida no cambian; el test de regresión fija `0.000498375` y `0.0104`.
