#!/usr/bin/env bash
set -euo pipefail

PROFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/profiles" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Pakai preset profile untuk jalankan overlay:

  ./run_with_profile.sh <profile> [argumen tambahan]

Contoh:
  ./run_with_profile.sh demografi
  BASE_FILE=data/awal.sav OVERLAY_FILE=data/baru.sav ./run_with_profile.sh survei
  ./run_with_profile.sh transaksi --include-cols status,nominal

Perintah bantu:
  ./run_with_profile.sh --list
  ./run_with_profile.sh --show demografi
EOF
}

list_profiles() {
  echo "Profile tersedia:"
  for f in "$PROFILE_DIR"/*.env; do
    [[ -e "$f" ]] || continue
    basename "$f" .env
  done
}

show_profile() {
  local profile="$1"
  local f="$PROFILE_DIR/${profile}.env"
  if [[ ! -f "$f" ]]; then
    echo "[ERROR] Profile tidak ditemukan: $profile"
    exit 1
  fi
  cat "$f"
}

if [[ "${1:-}" == "--list" ]]; then
  list_profiles
  exit 0
fi

if [[ "${1:-}" == "--show" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "[ERROR] Gunakan: ./run_with_profile.sh --show <profile>"
    exit 1
  fi
  show_profile "$2"
  exit 0
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || -z "${1:-}" ]]; then
  usage
  exit 0
fi

PROFILE_NAME="$1"
shift || true
PROFILE_FILE="$PROFILE_DIR/${PROFILE_NAME}.env"

if [[ ! -f "$PROFILE_FILE" ]]; then
  echo "[ERROR] Profile tidak ditemukan: $PROFILE_NAME"
  echo
  list_profiles
  exit 1
fi

# shellcheck disable=SC1090
source "$PROFILE_FILE"

# Set dari profile hanya jika belum dioverride ENV dari user
export BASE_FILE="${BASE_FILE:-data/base.sav}"
export OVERLAY_FILE="${OVERLAY_FILE:-data/overlay.sav}"
export KEYS="${KEYS:-id}"
export HOW="${HOW:-left}"
export METHOD="${METHOD:-replace}"
export OUTPUT_FILE="${OUTPUT_FILE:-out/hasil_${PROFILE_NAME}.sav}"
export REPORT_FILE="${REPORT_FILE:-out/report_${PROFILE_NAME}.json}"
export NORMALIZE_COLS="${NORMALIZE_COLS:-false}"

EXTRA_ARGS=()
if [[ -n "${INCLUDE_COLS:-}" ]]; then
  EXTRA_ARGS+=(--include-cols "$INCLUDE_COLS")
fi
if [[ -n "${EXCLUDE_COLS:-}" ]]; then
  EXTRA_ARGS+=(--exclude-cols "$EXCLUDE_COLS")
fi

cd "$ROOT_DIR"
./run.sh "${EXTRA_ARGS[@]}" "$@"
