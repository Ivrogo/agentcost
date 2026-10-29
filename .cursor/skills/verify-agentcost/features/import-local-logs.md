# Importar logs locales

`agentcost import` lee un log de Claude Code o de Codex CLI y escribe una traza JSONL. Una sesión es una tarea. El informe se pide después con `agentcost report`.

## Sub-features

- `import-claude` importa las dos sesiones anonimizadas, una por variante, y el informe sin `--allow-unpriced` cobra `claude-sonnet-5` y `claude-fable-5`.
- `import-codex` importa los dos rollouts sintéticos y el informe JSON cobra `0.0002655` y `0.004125` sin modelos sin precio.
- `import-paired` importa el mismo id de sesión con `--variant A` y `--variant B` y `--paired` cuenta un par.

## How to get to it (user POV)

- Claude: `agentcost import claude-code <fichero> --variant A --output a.jsonl`, el otro fichero con `--variant B`, y `agentcost report` de los dos sin `--allow-unpriced`.
- Codex: lo mismo con `import codex` sobre `rollout-synthetic-a.jsonl` y `rollout-synthetic-b.jsonl`, luego `report --format json`.
- Emparejar: dos ficheros con el mismo id de sesión, `--variant` distinto, y `report --paired`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.
- Las fixtures están en `$REPO/tests/fixtures/claude-code/` y `$REPO/tests/fixtures/codex/`. La de Codex es sintética.

- **Claude.** Desde `$ROOT/work`, importa `claude-session-a.jsonl` con `--variant A --output claude-a.jsonl` y `claude-session-b.jsonl` con `--variant B --output claude-b.jsonl`. Concatena los dos ficheros en `claude.jsonl` y ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" import-claude -- "$VENV/bin/agentcost" report claude.jsonl --compare A B`. `$EVIDENCE/import-claude.exit` es `0`. stdout contiene `$0.1333972` y `$1.883338`, y no contiene `Unpriced models`. stderr avisa de que no hay `task_id` en común. Vuelve a leer `claude.jsonl`: no contiene `SYNTHETIC_PROMPT_DO_NOT_KEEP` ni un cuerpo de mensaje, y sí contiene `7476d544-4b62-5749-99de-aed6aa276c03`.
- **Codex.** Importa `rollout-synthetic-a.jsonl` y `rollout-synthetic-b.jsonl` igual, con `--variant A` y `B`. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" import-codex -- "$VENV/bin/agentcost" report codex.jsonl --compare A B --format json`. `$EVIDENCE/import-codex.exit` es `0`. El JSON tiene `arms.A.total_cost` `0.0002655`, `arms.B.total_cost` `0.004125` y `unpriced_models` vacío. `codex.jsonl` no contiene `SYNTHETIC_PROMPT_DO_NOT_KEEP`.
- **Par.** No hace falta una tercera conducción si `import-paired` se cubre en pytest con dos rollouts del mismo id y `--paired`. Si se conduce, el JSON trae `pairing.mode` `paired` y `pairing.pairs` `1`.

## Gotchas

- Las fixtures de Codex son sintéticas. No son un log real de un usuario.
- `claude-sonnet-5` y `claude-fable-5` están en la tabla `2026-10-29`. El informe no lleva `--allow-unpriced`. El coste por tarea resuelta es `$0.1333972` y `$1.883338`.
- Dos sesiones distintas no comparten `task_id`. `--paired` sale 1. El emparejado pide el mismo id en las dos variantes.
- El directorio de trabajo es `$ROOT/work`. Las rutas de las fixtures son absolutas, desde `$REPO`.
