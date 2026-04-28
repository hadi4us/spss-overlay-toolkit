# SPSS SAV Overlay Toolkit

Project baru untuk pengolahan data/overlay file `.sav` (SPSS) dengan Python atau R.

## Struktur Folder

- `src/overlay_sav.py` → engine utama (direkomendasikan)
- `src/overlay_sav.R` → versi R
- `requirements-python.txt` → dependency Python
- `data/` → taruh file input (`base.sav`, `overlay.sav`)
- `out/` → output hasil merge/overlay
- `examples/` → contoh command siap jalan
- `run.sh` → runner 1 perintah (default)
- `run_with_profile.sh` → runner dengan preset profile
- `profiles/*.env` → preset variabel per tipe dataset

## Quick Start (Python)

### Opsi A — 1 perintah (disarankan)

```bash
cd /root/.openclaw/workspace/projects/spss-overlay-toolkit
./run.sh
```

Default `run.sh`:
- base: `data/base.sav`
- overlay: `data/overlay.sav`
- keys: `id`
- how: `left`
- method: `replace`
- output: `out/hasil.sav`
- report: `out/report.json`

Override via ENV:

```bash
BASE_FILE=data/a.sav OVERLAY_FILE=data/b.sav KEYS=id,tanggal METHOD=coalesce ./run.sh
```

Atau tambah flag langsung:

```bash
./run.sh --include-cols alamat,no_hp --exclude-cols status --normalize-cols
```

### Opsi B — jalankan script Python langsung

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

## Mode Profile (Preset Cepat)

List profile:

```bash
./run_with_profile.sh --list
```

Lihat isi profile:

```bash
./run_with_profile.sh --show demografi
```

Jalankan profile:

```bash
./run_with_profile.sh demografi
./run_with_profile.sh survei
./run_with_profile.sh transaksi
```

Override base/overlay saat run:

```bash
BASE_FILE=data/my_base.sav OVERLAY_FILE=data/my_patch.sav ./run_with_profile.sh survei
```

Tambahkan argumen khusus:

```bash
./run_with_profile.sh transaksi --include-cols status,nominal --exclude-cols ingest_id
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
