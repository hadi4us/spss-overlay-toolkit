#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip -q install -r requirements-python.txt
pip -q install -r requirements-ui.txt

PORT="${PORT:-8501}"

if [[ -n "${UI_USERNAME:-}" || -n "${UI_PASSWORD:-}" ]]; then
  echo "[INFO] UI auth: ENABLED (env UI_USERNAME/UI_PASSWORD terdeteksi)"
else
  echo "[WARN] UI auth: DISABLED (set UI_USERNAME/UI_PASSWORD untuk proteksi login)"
fi

echo "[INFO] Menjalankan UI di http://localhost:${PORT}"
exec streamlit run ui/app.py --server.port "$PORT" --server.address 0.0.0.0
