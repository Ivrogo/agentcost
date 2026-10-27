---
name: verify-agentcost
description: "Comprueba la CLI de agentcost como lo haría un usuario: venv limpio, pytest, ruff, matriz Python 3.10–3.12 y un informe real con examples/research_agent. Úsala al validar la CLI o al rellenar verification.json."
---

# Verificar agentcost

La superficie principal es la CLI `agentcost`. La biblioteca se cubre con pytest. No hay servidor, puerto, variables de entorno, autenticación ni migraciones. Cada ejecución usa sus propios venv bajo `$ROOT` y no comparte estado con otra: la CLI solo lee la traza que le pases y escribe donde diga `--output` o en stdout.

Los intérpretes de la matriz son los que declaran `pyproject.toml` y `.github/workflows/ci.yml`: Python 3.10, 3.11 y 3.12. Consíguelos con `uv python install 3.10 3.11 3.12` y `uv python find <versión>`. Si `uv` no está, usa `python3.10`, `python3.11` y `python3.12` del `PATH`. Una versión que no exista en la máquina es un check `skipped` con el motivo escrito; no es un `pass`.

## Launch

Estos bloques se ejecutan con bash, desde la raíz del repositorio. Doctor asume un venv de Unix (`bin/agentcost`); macOS y Windows los cubre la CI. Si una versión no está en la máquina, esa fila es un check `skipped` con el motivo, y no se lanza su bucle.

```bash
set -euo pipefail
REPO=$(git rev-parse --show-toplevel)
cd "$REPO"
RUN_ID=$(date +%Y%m%d%H%M%S)-$$
ROOT=/tmp/agentcost-verify-$RUN_ID
EVIDENCE=$ROOT/evidence
mkdir -p "$ROOT/work" "$EVIDENCE"
if command -v uv >/dev/null 2>&1; then
  uv python install 3.10 3.11 3.12
  PY310=$(uv python find 3.10)
  PY311=$(uv python find 3.11)
  PY312=$(uv python find 3.12)
else
  PY310=$(command -v python3.10)
  PY311=$(command -v python3.11)
  PY312=$(command -v python3.12)
fi
for spec in "3.10|$PY310" "3.11|$PY311" "3.12|$PY312"; do
  ver=${spec%%|*}
  py=${spec#*|}
  dev=$ROOT/venv-$ver
  clean=$ROOT/clean-$ver
  "$py" -m venv "$dev"
  "$dev/bin/python" -m pip install -q -U pip
  "$dev/bin/python" -m pip install -q -e "$REPO[dev]"
  "$py" -m venv "$clean"
  "$clean/bin/python" -m pip install -q -U pip
  "$clean/bin/python" -m pip install -q "$REPO"
done
{
  echo "repo=$REPO"
  echo "root=$ROOT"
  echo "py310=$PY310 $($PY310 --version)"
  echo "py311=$PY311 $($PY311 --version)"
  echo "py312=$PY312 $($PY312 --version)"
} > "$EVIDENCE/launch.txt"
```

Listo cuando Doctor pasa para el venv que vas a conducir. `pip install -e ".[dev]"` deja pytest y ruff. `pip install .` es la instalación limpia, sin editable y sin el extra `dev`. El venv de desarrollo y el limpio son distintos.

Pytest y ruff se ejecutan con el directorio de trabajo en `$REPO`. La CLI se ejecuta con el directorio de trabajo en `$ROOT/work`.

## Doctor

Comprueba de solo lectura el venv que vas a usar. `MODE` es `editable` o `clean`. No instala ni borra nada.

```bash
set -euo pipefail
test -x "$VENV/bin/agentcost"
test -x "$VENV/bin/python"
shebang=$(head -n 1 "$VENV/bin/agentcost")
test "$shebang" = "#!$VENV/bin/python"
installed=$("$VENV/bin/python" -c 'import agentcost, pathlib; print(pathlib.Path(agentcost.__file__).resolve())')
expected=$(sed -n 's/^version = "\(.*\)"/\1/p' "$REPO/pyproject.toml" | head -n 1)
got=$("$VENV/bin/python" -c 'import agentcost; print(agentcost.__version__)')
test "$got" = "$expected"
case "$MODE" in
  editable) [[ "$installed" == "$REPO/src/agentcost/"* ]] ;;
  clean) [[ "$installed" == "$VENV/"* ]] ;;
  *) echo "MODE debe ser editable o clean" >&2; exit 1 ;;
esac
PATH="$VENV/bin:$PATH" command -v agentcost >/dev/null
help_text=$("$VENV/bin/agentcost" --help)
grep -q 'report' <<<"$help_text"
{
  echo "mode=$MODE"
  echo "version=$got"
  echo "module=$installed"
  echo "python=$("$VENV/bin/python" --version)"
} | tee "$EVIDENCE/doctor-${MODE}-${VER}.txt"
```

`VER` es `3.10`, `3.11` o `3.12`. Si Doctor falla, no conduzcas ese venv.

## Drive

Arranca cada comando con el auxiliar, en su propia sesión de tmux y con el socket que el auxiliar crea. El directorio de trabajo de la CLI es `$ROOT/work`.

```bash
cd "$ROOT/work"
"$REPO/.cursor/skills/verify-agentcost/scripts/drive.sh" "$EVIDENCE" NOMBRE -- \
  "$VENV/bin/agentcost" report "$REPO/examples/research_agent/traces.jsonl" --compare A B --format json
```

El código de salida del auxiliar es 0 cuando la evidencia quedó escrita, también si la CLI salió con 1. El código de la CLI está en `$EVIDENCE/NOMBRE.exit`.

Antes de dar por buena la matriz, desde `$REPO` y con cada venv de desarrollo:

```bash
cd "$REPO"
"$ROOT/venv-3.10/bin/pytest" -q | tee "$EVIDENCE/pytest-3.10.txt"
"$ROOT/venv-3.11/bin/pytest" -q | tee "$EVIDENCE/pytest-3.11.txt"
"$ROOT/venv-3.12/bin/pytest" -q | tee "$EVIDENCE/pytest-3.12.txt"
"$ROOT/venv-3.12/bin/ruff" check . | tee "$EVIDENCE/ruff-check.txt"
"$ROOT/venv-3.12/bin/ruff" format --check . | tee "$EVIDENCE/ruff-format.txt"
```

`tee` oculta el código de salida de pytest y de ruff. Compruébalo aparte (`PIPESTATUS` o sin tubería) y no aceptes un 0 de ruff si la salida dice `No Python files found`. Pytest tiene que terminar en 0 y su resumen no puede decir `no tests ran` ni `failed`.

La prueba de punta a punta, en cada venv limpio y desde `$ROOT/work`, es el feature [Informe JSON](features/report-json.md) sobre `examples/research_agent/traces.jsonl`.

El mapa de features está en [features/README.md](features/README.md). Conducir un solo camino no cubre los demás.

## Evidence

Por cada conducción el auxiliar escribe, y no borra después:

- `$EVIDENCE/<nombre>.txt` — comando, directorio, código y las dos salidas
- `$EVIDENCE/<nombre>.stdout.txt`
- `$EVIDENCE/<nombre>.stderr.txt`
- `$EVIDENCE/<nombre>.exit`
- `$EVIDENCE/<nombre>.socket` — ruta del socket de esa sesión, para poder matarla

Pytest y ruff dejan su texto en los `.txt` del bloque anterior. `$EVIDENCE/launch.txt` y los `doctor-*.txt` también se quedan.

La prueba tiene que recorrer el camino de usuario: el ejecutable `agentcost` del venv, una traza real del repositorio y el estado que esa orden produce (stdout, stderr, código y, si hay `--output`, el fichero escrito). No sirve importar `compare` desde el test como sustituto de la CLI. Un fichero generado se vuelve a leer desde fuera del proceso que lo escribió.

Dentro de una misión, copia esa evidencia a `missions/<id>/evidencias.log` y haz que `verification.json` apunte ahí. La copia sobrevive aunque luego borres `$ROOT`.

## Cleanup

Mata solo los servidores anotados en `$EVIDENCE/*.socket`. Borra los venv y el directorio de trabajo. No borres `$EVIDENCE`.

```bash
shopt -s nullglob
for record in "$EVIDENCE"/*.socket; do
  sock=$(<"$record")
  if [[ -S "$sock" ]]; then
    tmux -S "$sock" kill-server 2>/dev/null || true
    if ! tmux -S "$sock" has-session >/dev/null 2>&1; then
      rm -f "$sock"
    fi
  fi
done
rm -rf "$ROOT/venv-3.10" "$ROOT/venv-3.11" "$ROOT/venv-3.12" \
  "$ROOT/clean-3.10" "$ROOT/clean-3.11" "$ROOT/clean-3.12" \
  "$ROOT/work"
test -d "$EVIDENCE"
test -f "$EVIDENCE/launch.txt"
```

No uses `kill` por nombre de proceso ni `rm -rf "$ROOT"`: ahí dentro está la evidencia. Los restos de un intento fallido se limpian igual, y la evidencia de ese intento se conserva.

## Helpers

`.cursor/skills/verify-agentcost/scripts/drive.sh` es el único auxiliar. Tiene que ser ejecutable.

```bash
.cursor/skills/verify-agentcost/scripts/drive.sh <dir-evidencia> <nombre> -- <comando...>
```

`<nombre>` solo admite letras, números, punto, guion y guion bajo. El auxiliar crea una sesión tmux con un socket en el temporal del sistema, ejecuta el comando con el `PATH` y el directorio de trabajo del llamador, guarda las salidas y mata ese servidor. No toca ningún otro tmux.

## Checks y `verification.json`

Cada check de abajo es un objeto de `checks`. `command` es el comando real. `result` es `pass`, `fail` o `skipped`. `detail` dice qué se observó, y en un `skipped` la justificación no puede ir vacía. `evidence` es la ruta versionada, normalmente bajo `missions/<id>/evidencias.log`.

| `name` | Qué tiene que haber pasado |
| --- | --- |
| `pytest_3_10` | `pytest -q` con el venv de desarrollo 3.10, cwd `$REPO`, salida 0 |
| `pytest_3_11` | igual en 3.11 |
| `pytest_3_12` | igual en 3.12 |
| `ruff_check` | `ruff check .` con el venv de desarrollo 3.12, cwd `$REPO`, salida 0 y texto `All checks passed` |
| `ruff_format` | `ruff format --check .` en las mismas condiciones, salida 0, sin `No Python files found` |
| `clean_install_3_10` | `python -m pip install .` en un venv nuevo de 3.10 y Doctor en modo `clean` |
| `clean_install_3_11` | igual en 3.11 |
| `clean_install_3_12` | igual en 3.12 |
| `e2e_cli_json` | el feature Informe JSON, en el venv limpio, con `examples/research_agent/traces.jsonl` |
| `ci_otros_sistemas` | `skipped` en una máquina que no es ese sistema: la matriz de macOS, Windows y pipx la corre `.github/workflows/ci.yml` |

`status` es `passed` solo si ninguno es `fail` y cada `skipped` tiene motivo. Un `fail` deja `status` en `failed` y reabre Implementación. `environment.python` lista las versiones que de verdad se ejecutaron, con el texto de `python --version`. `environment.runtime` es `venv limpio`. `environment.base_commit` es `git rev-parse HEAD`.

```json
{
  "name": "e2e_cli_json",
  "command": "agentcost report examples/research_agent/traces.jsonl --compare A B --format json",
  "result": "pass",
  "detail": "exit 0; verdict better; A 0.000498375; B 0.0104",
  "evidence": "evidencias.log#report-json.txt"
}
```

```json
{
  "name": "ci_otros_sistemas",
  "command": "not run",
  "result": "skipped",
  "detail": "Esta máquina es Linux. macOS, Windows y pipx los ejecuta .github/workflows/ci.yml.",
  "evidence": "evidencias.log#scope.txt"
}
```

Cuando la CLI o los precios cambien, actualiza las cifras del mapa de features. Mantener el mapa al día es el trabajo de `/maintain-verification-skill`.
