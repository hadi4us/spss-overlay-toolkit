#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../.."

if ! command -v brew >/dev/null 2>&1; then
  echo "[ERROR] Homebrew belum terpasang. Install dulu dari https://brew.sh"
  read -n 1 -s -r -p "Tekan tombol apa saja untuk keluar..."
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[INFO] cloudflared belum ada. Menginstall via Homebrew..."
  brew install cloudflared
fi

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

# Proteksi dasar: jika user belum set env, pakai default sementara lalu tampilkan warning
if [ -z "${UI_USERNAME:-}" ] || [ -z "${UI_PASSWORD:-}" ]; then
  export UI_USERNAME="admin"
  export UI_PASSWORD="ganti-password-kuat"
  echo "[WARN] UI_USERNAME/UI_PASSWORD belum diset."
  echo "[WARN] Sementara dipakai admin / ganti-password-kuat (WAJIB diganti)."
fi

echo "[INFO] Start Streamlit di background..."
./run_ui.sh > /tmp/spss_overlay_ui.log 2>&1 &
UI_PID=$!
echo "[INFO] UI PID: $UI_PID"

sleep 3

echo "[INFO] Membuka tunnel publik ke http://localhost:8501"
echo "[INFO] Nanti akan muncul URL seperti https://xxxx.trycloudflare.com"

echo "[INFO] Tekan Ctrl+C untuk menghentikan tunnel (UI tetap jalan)."
cloudflared tunnel --url http://localhost:8501
