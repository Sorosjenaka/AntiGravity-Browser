#!/usr/bin/env bash
set -euo pipefail

if [[ -d "$HOME/.cargo/bin" ]]; then
  export PATH="$HOME/.cargo/bin:$PATH"
fi

PLAN="${1:-data/action_plan.json}"
OUT="${2:-data/engage_results.json}"
VERIFY_OUT="${3:-data/verify_report.json}"
MIN_DELAY="${MIN_DELAY:-5.0}"
MAX_DELAY="${MAX_DELAY:-60.0}"
VERIFY_CONCURRENCY="${VERIFY_CONCURRENCY:-3}"
STRICT="${STRICT:-0}"

if [[ ! -f "$PLAN" ]]; then
  echo "File plan tidak ditemukan: $PLAN" >&2
  exit 1
fi

EXE="./target/release/x-social-draft-workflow"
if [[ ! -x "$EXE" ]]; then
  echo "Release CLI belum ada, menjalankan cargo build --release..."
  cargo build --release
fi

if [[ -x ".venv/bin/python" ]]; then
  PY_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
else
  PY_BIN="python"
fi

echo "[1/4] Menjalankan eksekusi headless terisolasi + auto-retry + audit paralel (jeda acak ${MIN_DELAY}-${MAX_DELAY} detik)..."
ENG_ARGS=(
  -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py
  --plan "$PLAN"
  --out "$OUT"
  --verify-out "$VERIFY_OUT"
  --min-delay "$MIN_DELAY"
  --max-delay "$MAX_DELAY"
  --verify-concurrency "$VERIFY_CONCURRENCY"
)
if [[ "$STRICT" == "1" ]]; then
  ENG_ARGS+=(--strict)
fi
"$PY_BIN" "${ENG_ARGS[@]}"

echo "[2/4] Menyinkronkan konfirmasi Like & Reply terverifikasi ke SQLite..."
"$PY_BIN" - "$OUT" "$EXE" <<'PYEOF'
import json, subprocess, sys
out_path, exe = sys.argv[1], sys.argv[2]
rows = json.load(open(out_path, encoding="utf-8"))
for row in rows:
    if row.get("liked") is True and row.get("replied") is True:
        if row.get("reply_note") != "already_replied":
            subprocess.run([exe, "confirm-posted", "--draft-id", str(row["draft_id"])], check=False)
        if row.get("like_note") in ("liked_now", "already_liked"):
            subprocess.run([exe, "confirm-liked", "--post-id", str(row["post_id"])], check=False)
PYEOF

echo "[3/4] Strict SQLite Completeness Audit (Tabel):"
AUDIT_ARGS=(audit --plan "$PLAN")
if [[ "$STRICT" == "1" ]]; then
  AUDIT_ARGS+=(--strict)
fi
"$EXE" "${AUDIT_ARGS[@]}"

echo "[4/4] Laporan hasil akhir (Tabel):"
"$EXE" report
