#!/usr/bin/env bash
set -euo pipefail

# Jalankan dari folder project: projects/spss-overlay-toolkit

./run_with_profile.sh --list
./run_with_profile.sh --show demografi

# Contoh run preset
./run_with_profile.sh demografi

# Contoh override file input + argumen tambahan
BASE_FILE=data/base_2026.sav OVERLAY_FILE=data/patch_2026.sav \
  ./run_with_profile.sh transaksi --include-cols status,nominal,channel
