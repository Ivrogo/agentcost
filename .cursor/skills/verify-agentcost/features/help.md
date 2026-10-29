# Ayuda

La ayuda muestra el comando `report` y las opciones con las que se pide un informe, sin leer ninguna traza.

## Sub-features

- `help-root` muestra el comando `report` en la ayuda general.
- `help-report` muestra `--compare`, `--format`, `--paired` y `--unpaired` en la ayuda del comando.

## How to get to it (user POV)

- En la terminal: `agentcost --help`.
- En la terminal: `agentcost report --help`.

## Driving it with verify-agentcost

Preconditions:

- Doctor ha pasado para `$VENV` en modo `clean`.
- El directorio de trabajo es `$ROOT/work`.

- **Ayuda general.** Pide la ayuda del programa. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" help-root -- "$VENV/bin/agentcost" --help`. `$EVIDENCE/help-root.exit` es `0` y stdout contiene `report` y `Build an A/B cost report from a trace file.`
- **Ayuda del informe.** Pide la ayuda del comando. Ejecuta `"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" help-report -- "$VENV/bin/agentcost" report --help`. `$EVIDENCE/help-report.exit` es `0` y stdout contiene `--compare`, `--format`, `--paired` y `--unpaired`.
- **Prueba.** Conserva los dos transcripts. La ayuda no escribe ficheros.

## Gotchas

- La ayuda usa cajas Unicode. Busca el texto `report`, `--compare` y `--format`, no el borde.
- `agentcost` sin argumentos también enseña la ayuda, porque el programa no tiene un comando por defecto. Este feature pide `--help` de forma explícita.
- Doctor ya ejecuta `--help`. Esta conducción vuelve a hacerlo dentro del aislado y guarda el transcript; no se da por hecha por el resultado de Doctor.
