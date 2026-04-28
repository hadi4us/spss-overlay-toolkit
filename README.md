# SPSS SAV Overlay Toolkit

Project baru untuk pengolahan data/overlay file `.sav` (SPSS) dengan Python atau R.

## Struktur Folder

- `src/overlay_sav.py` → engine utama (direkomendasikan)
- `src/overlay_sav.R` → versi R
- `requirements-python.txt` → dependency Python
- `data/` → taruh file input (`base.sav`, `overlay.sav`)
- `out/` → output hasil merge/overlay
- `examples/` → contoh command siap jalan

## Quick Start (Python)

```bash
cd /root/.openclaw/workspace/projects/spss-overlay-toolkit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-python.txt

python src/overlay_sav.py \
  --base data/base.sav \
  --overlay data/overlay.sav \
  --keys id \
  --how left \
  --method replace \
  --output out/hasil.sav \
  --report out/report.json
```

## Fitur

- Input: `.sav`, `.csv`, `.xlsx`, `.parquet` (Python)
- Output: `.sav`, `.csv`, `.xlsx`, `.parquet` (Python)
- Join mode: `left`, `inner`, `right`, `outer`
- Strategi kolom overlap:
  - `coalesce` (prioritas base)
  - `replace` (prioritas overlay)
  - `keep_base`
  - `keep_overlay`

## Quick Start (R)

Install package di R:

```r
install.packages(c("optparse", "dplyr", "haven", "readr", "jsonlite"))
```

Run:

```bash
Rscript src/overlay_sav.R \
  --base data/base.sav \
  --overlay data/overlay.sav \
  --keys id \
  --how left \
  --method replace \
  --output out/hasil.sav \
  --report out/report.json
```
