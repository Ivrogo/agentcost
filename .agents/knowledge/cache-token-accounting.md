# Contabilidad de tokens de caché

## Contexto

OpenAI, Anthropic y OpenTelemetry no cuentan la caché igual. Cobrar el campo de entrada tal cual y, además, el de caché cuenta dos veces en un proveedor y se deja tokens fuera en el otro.

## Motivo

El modelo interno guarda cubos que no se solapan: entrada ordinaria, lectura, escritura a 5 minutos, escritura a 1 hora y salida. La regla se aplica al leer la traza, no al poner el precio.

- Forma canónica (`tokens` o campos planos, sin `usage`): ya viene disjunta. Una traza v0.1 no trae caché y el coste no cambia. `provider` sin `usage` no resta ni suma.
- `provider: openai` con `usage`: `prompt_tokens` e `input_tokens` ya incluyen `cached_tokens`. La entrada ordinaria es la resta. `total_tokens`, si viene, es esa entrada bruta más la salida, no una tercera suma de la caché.
- `provider: anthropic` con `usage`: `input_tokens` no incluye la caché. La lectura y la escritura se suman. El desglose `cache_creation` sustituye a `cache_creation_input_tokens`; no se suman los dos. Sin desglose, el total de escritura es de 5 minutos.
- OTel: `gen_ai.usage.cache_read.input_tokens` y `gen_ai.usage.cache_write.input_tokens` ya van dentro de `gen_ai.usage.input_tokens`. Se restan. La escritura, sin TTL en la convención, se anota como 5 minutos.

Un precio de caché ausente no es cero. Se usa el de entrada y el informe nombra el modelo. Un cero escrito en la tabla es gratis. No se inventa una tarifa para un modelo que la página oficial no lista.
