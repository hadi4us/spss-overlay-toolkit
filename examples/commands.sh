#!/usr/bin/env bash
set -euo pipefail

# Contoh 1: Overlay sederhana by id
python ../src/overlay_sav.py \
  --base ../data/base.sav \
  --overlay ../data/overlay.sav \
  --keys id \
  --how left \
  --method replace \
  --output ../out/hasil.sav \
  --report ../out/report.json

# Contoh 2: Multi key + normalisasi nama kolom
python ../src/overlay_sav.py \
  --base ../data/base.sav \
  --overlay ../data/overlay.sav \
  --keys id,tanggal \
  --method coalesce \
  --normalize-cols \
  --output ../out/hasil_multi_key.csv \
  --report ../out/report_multi_key.json
