#!/bin/bash
set -euo pipefail

# Stop streamlit process for this toolkit
pkill -f "streamlit run ui/app.py" || true

echo "[OK] Streamlit dihentikan (jika sedang berjalan)."
