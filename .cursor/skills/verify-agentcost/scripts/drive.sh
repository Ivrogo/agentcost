#!/usr/bin/env bash
# Conduce un comando en una sesión de tmux con socket propio y guarda la evidencia.
# El código de salida de este script es 0 si la evidencia quedó escrita.
# El código del comando conducido está en <dir>/<nombre>.exit, no en este script.
# Uso: drive.sh <dir-evidencia> <nombre> -- <comando...>
set -euo pipefail

if [[ $# -lt 4 || "${3:-}" != "--" ]]; then
  echo "uso: drive.sh <dir-evidencia> <nombre> -- <comando...>" >&2
  exit 2
fi

evidence=$1
name=$2
shift 3

if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "nombre de check inválido: $name" >&2
  exit 2
fi

mkdir -p "$evidence"
work=$(mktemp -d "${TMPDIR:-/tmp}/agentcost-drive.XXXXXX")
sock="${TMPDIR:-/tmp}/agentcost-drive-${name}-$$.sock"
stdout="$work/stdout.txt"
stderr="$work/stderr.txt"
exitf="$work/exit.txt"
script="$work/cmd.sh"
cmd=$(printf '%q ' "$@")

kill_server() {
  if [[ -z "${sock:-}" || ! -S "$sock" ]]; then
    return 0
  fi
  tmux -S "$sock" kill-server 2>/dev/null || true
  # kill-server deja el fichero del socket. Solo borramos el que creó esta ejecución.
  if ! tmux -S "$sock" has-session 2>/dev/null; then
    rm -f "$sock"
  fi
}
trap kill_server EXIT

printf '%s\n' "$sock" > "$evidence/$name.socket"
rm -f "$sock"

{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'set -uo pipefail'
  printf 'export PATH=%q\n' "$PATH"
  printf 'export TERM=%q\n' "${TERM:-xterm}"
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    printf 'export VIRTUAL_ENV=%q\n' "$VIRTUAL_ENV"
  fi
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf 'export GITHUB_STEP_SUMMARY=%q\n' "$GITHUB_STEP_SUMMARY"
  fi
  printf 'cd %q\n' "$PWD"
  printf '%s > %q 2> %q\n' "$cmd" "$stdout" "$stderr"
  printf '%s\n' 'status=$?'
  printf 'printf %%s\\\\n "$status" > %q\n' "$exitf"
  printf '%s\n' 'exit "$status"'
} > "$script"
chmod +x "$script"

tmux -S "$sock" new-session -d -s drive -- "$script"

deadline=$((SECONDS + 120))
while [[ ! -f "$exitf" ]]; do
  if ((SECONDS > deadline)); then
    echo "tiempo agotado esperando a $name" >&2
    exit 1
  fi
  if ! tmux -S "$sock" has-session -t drive 2>/dev/null && [[ ! -f "$exitf" ]]; then
    echo "la sesión terminó sin código de salida ($name)" >&2
    exit 1
  fi
  sleep 0.1
done

code=$(tr -d '[:space:]' < "$exitf")

{
  printf 'command: %s\n' "$cmd"
  printf 'cwd: %s\n' "$PWD"
  printf 'exit: %s\n' "$code"
  printf '%s\n' '--- stdout ---'
  cat "$stdout" 2>/dev/null || true
  printf '%s\n' '--- stderr ---'
  cat "$stderr" 2>/dev/null || true
} > "$evidence/$name.txt"

if [[ -f "$stdout" ]]; then
  cp "$stdout" "$evidence/$name.stdout.txt"
else
  : > "$evidence/$name.stdout.txt"
fi
if [[ -f "$stderr" ]]; then
  cp "$stderr" "$evidence/$name.stderr.txt"
else
  : > "$evidence/$name.stderr.txt"
fi
printf '%s\n' "$code" > "$evidence/$name.exit"

rm -rf "$work"
work=""
exit 0
