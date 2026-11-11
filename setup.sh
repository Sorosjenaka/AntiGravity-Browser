#!/usr/bin/env bash
set -euo pipefail

if [[ -d "$HOME/.cargo/bin" ]]; then
  export PATH="$HOME/.cargo/bin:$PATH"
fi

BROWSER="auto"
PROFILE=""
EXE_PATH=""
HANDLE=""
DISPLAY_NAME=""
PORT=""
NO_SHORTCUT=0
NO_DETECT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --browser) BROWSER="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --exe-path) EXE_PATH="$2"; shift 2 ;;
    --handle) HANDLE="$2"; shift 2 ;;
    --display-name) DISPLAY_NAME="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-shortcut) NO_SHORTCUT=1; shift ;;
    --no-detect) NO_DETECT=1; shift ;;
    -h|--help)
      echo "Usage: ./setup.sh [--browser auto|firefox|brave|chrome|edge|custom] [--profile NAME] [--exe-path PATH] [--handle @user --display-name 'Name'] [--port PORT] [--no-shortcut] [--no-detect]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

echo "[1/5] Checking Rust & building release binary..."
cargo test
cargo build --release

echo "[2/5] Checking Python & websockets dependency..."
PY_BIN=""
if [[ -x ".venv/bin/python" ]]; then
  PY_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PY_BIN="python"
else
  echo "Python 3 not found. Install python3 and python3-venv first." >&2
  exit 1
fi

if ! "$PY_BIN" -c "import websockets" >/dev/null 2>&1; then
  if ! "$PY_BIN" -m pip install websockets >/dev/null 2>&1; then
    echo "System pip restricted (PEP 668) or pip missing; creating local .venv..."
    "$PY_BIN" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip websockets
    PY_BIN=".venv/bin/python"
  fi
fi

echo "[3/5] Initializing local SQLite database..."
EXE="./target/release/x-social-draft-workflow"
"$EXE" init

echo "[4/5] Connecting browser ($BROWSER), creating isolated launcher, and auto-detecting X user..."
CONN_ARGS=(connect-browser --browser "$BROWSER")
[[ -n "$PROFILE" ]] && CONN_ARGS+=(--profile "$PROFILE")
[[ -n "$EXE_PATH" ]] && CONN_ARGS+=(--exe-path "$EXE_PATH")
[[ -n "$PORT" ]] && CONN_ARGS+=(--port "$PORT")
[[ "$NO_SHORTCUT" -eq 1 ]] && CONN_ARGS+=(--no-shortcut)
if [[ "$NO_DETECT" -eq 1 ]] || { [[ -n "$HANDLE" ]] && [[ -n "$DISPLAY_NAME" ]]; }; then
  CONN_ARGS+=(--no-detect)
fi

"$EXE" "${CONN_ARGS[@]}"

if [[ -n "$HANDLE" && -n "$DISPLAY_NAME" ]]; then
  "$EXE" confirm-account --handle "$HANDLE" --display-name "$DISPLAY_NAME"
fi

echo "[5/5] Current status:"
"$EXE" status
