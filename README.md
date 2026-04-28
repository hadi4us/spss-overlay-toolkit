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
- `ui/app.py` → aplikasi web (UI/UX analisis data mirip SPSS)
- `run_ui.sh` → jalankan aplikasi UI
- `requirements-ui.txt` → dependency UI
- `.streamlit/config.toml` → batas upload + hardening dasar Streamlit
- `SECURITY.md` → panduan HTTPS/auth saat dipublikasikan

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

## UI/UX Analisis Data (Mirip SPSS)

Jalankan aplikasi web:

```bash
cd /root/.openclaw/workspace/projects/spss-overlay-toolkit
./run_ui.sh
```

Akses di browser:
- `http://localhost:8501`

Aktifkan login UI (opsional tapi disarankan):

```bash
UI_USERNAME=admin UI_PASSWORD='ganti-password-kuat' ./run_ui.sh
```

Untuk publik internet, baca `SECURITY.md` (HTTPS + reverse proxy + auth tambahan).

Menu yang tersedia di UI:
- Dataset Manager (upload `.sav/.csv/.xlsx/.parquet`)
- Variable View (tipe, missing, unique)
- Data Quality Center (missing, duplicate key, outlier IQR, schema compare)
- Transform (recode, compute, binning, missing handler, filter)
- Descriptive Statistics
- Frequencies
- Crosstabs
- Correlation Matrix + heatmap
- Inferential Stats (t-test, chi-square, ANOVA, linear/logistic regression)
- Charts interaktif
- Overlay / Merge Builder (2 file)
- Multi Overlay Builder (2+ file, berantai)
- Mapping key BASE → OVERLAY (nama kolom boleh berbeda antar file)
- Export dataset hasil analisis
- Report Generator (download Markdown/HTML)

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
- Overlay 2 file dan multi-file (berantai)
- Join mode: `left`, `inner`, `right`, `outer`
- Strategi kolom overlap:
  - `coalesce` (prioritas base)
  - `replace` (prioritas overlay)
  - `keep_base`
  - `keep_overlay`
- Data quality profiling + schema compare
- Transformasi data inti (recode, compute, binning, missing, filter)
- Inferential statistik utama (t-test, chi-square, ANOVA, regresi)
- Report generator (Markdown/HTML)

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
