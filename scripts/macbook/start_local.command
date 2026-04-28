#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 belum terpasang. Install dulu: brew install python@3.11"
  read -n 1 -s -r -p "Tekan tombol apa saja untuk keluar..."
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements-python.txt
pip install -q -r requirements-ui.txt

echo "[INFO] Menjalankan UI lokal di http://localhost:8501"
exec ./run_ui.sh
