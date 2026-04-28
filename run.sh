#!/usr/bin/env bash
set -euo pipefail

# One-command runner untuk overlay SAV (Python)
# Bisa override pakai ENV atau argumen flag tambahan.

BASE_FILE="${BASE_FILE:-data/base.sav}"
OVERLAY_FILE="${OVERLAY_FILE:-data/overlay.sav}"
KEYS="${KEYS:-id}"
HOW="${HOW:-left}"
METHOD="${METHOD:-replace}"
OUTPUT_FILE="${OUTPUT_FILE:-out/hasil.sav}"
REPORT_FILE="${REPORT_FILE:-out/report.json}"
NORMALIZE_COLS="${NORMALIZE_COLS:-false}"

if [[ ! -f "$BASE_FILE" ]]; then
  echo "[ERROR] File base tidak ditemukan: $BASE_FILE"
  echo "Taruh file .sav di folder data/ atau set BASE_FILE=..."
  exit 1
fi

if [[ ! -f "$OVERLAY_FILE" ]]; then
  echo "[ERROR] File overlay tidak ditemukan: $OVERLAY_FILE"
  echo "Taruh file .sav di folder data/ atau set OVERLAY_FILE=..."
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip -q install -r requirements-python.txt

CMD=(
  python src/overlay_sav.py
  --base "$BASE_FILE"
  --overlay "$OVERLAY_FILE"
  --keys "$KEYS"
  --how "$HOW"
  --method "$METHOD"
  --output "$OUTPUT_FILE"
  --report "$REPORT_FILE"
)

if [[ "$NORMALIZE_COLS" == "true" ]]; then
  CMD+=(--normalize-cols)
fi

# Teruskan argumen tambahan user, mis.:
# ./run.sh --include-cols col1,col2 --exclude-cols col3
CMD+=("$@")

"${CMD[@]}"

echo "[DONE] Output: $OUTPUT_FILE"
echo "[DONE] Report: $REPORT_FILE"
