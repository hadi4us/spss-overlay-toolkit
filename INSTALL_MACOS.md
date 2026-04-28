# Instalasi SPSS Overlay Toolkit di MacBook (macOS)

Dokumen ini untuk setup dari nol di MacBook (Intel / Apple Silicon M1/M2/M3).

## 1) Prasyarat

Minimal yang dibutuhkan:
- macOS 12+ (Monterey atau lebih baru)
- Terminal
- Koneksi internet

Instal tools dasar:

```bash
# Xcode Command Line Tools
xcode-select --install

# Homebrew (jika belum ada)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Verifikasi Homebrew:

```bash
brew --version
```

## 2) Install Python

Disarankan Python 3.11 atau 3.12:

```bash
brew install python@3.11
python3 --version
```

> Jika `python3` belum mengarah ke versi brew, tutup-buka Terminal lalu cek ulang.

## 3) Clone Repository

```bash
cd ~/Documents
# atau folder kerja yang kamu suka

git clone https://github.com/hadi4us/spss-overlay-toolkit.git
cd spss-overlay-toolkit
```

## 4) Setup Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements-python.txt
pip install -r requirements-ui.txt
```

## 5) Jalankan Aplikasi Web (UI)

```bash
./run_ui.sh
```

Buka browser:
- http://localhost:8501

## 6) Jalankan Engine CLI (Tanpa UI)

Siapkan file input di folder `data/`, lalu:

```bash
./run.sh
```

Atau langsung script:

```bash
python src/overlay_sav.py \
  --base data/base.sav \
  --overlay data/overlay.sav \
  --keys id \
  --how left \
  --method replace \
  --output out/hasil.sav \
  --report out/report.json
```

## 7) Tips untuk Kasus Key Tidak Match (IDART vs IDRT)

Di menu Overlay UI:
1. Centang **"Nama key berbeda antara base & overlay"**
2. Mapping: `IDART (base)` -> `IDRT` atau `NO_INDIVIDU` (sesuai struktur file)
3. Centang **"Cleaning key sebelum merge"** agar trim spasi + normalisasi angka (`92.0 -> 92`)
4. Gunakan `left join` jika base harus tetap utuh

## 8) Jika Permission Script Ditolak

```bash
chmod +x run.sh run_ui.sh run_with_profile.sh
```

## 9) Troubleshooting

### A. `command not found: python3`
Install Python via brew, lalu restart Terminal:

```bash
brew install python@3.11
```

### B. Gagal install package tertentu
Coba update pip/setuptools/wheel:

```bash
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements-python.txt
```

### C. Port 8501 sudah dipakai
Jalankan di port lain:

```bash
PORT=8502 ./run_ui.sh
```

Akses:
- http://localhost:8502

### D. Upload file besar
Batas upload sudah diset 200MB di `.streamlit/config.toml`.
Kalau perlu lebih besar, ubah:
- `server.maxUploadSize`
- `server.maxMessageSize`

## 10) Rekomendasi Operasional

- Simpan data asli di folder terpisah sebagai backup.
- Gunakan format output `.sav` jika workflow lanjut di SPSS.
- Untuk data besar, gunakan `parquet` saat proses intermediate agar lebih cepat.

---

Kalau kamu mau, saya bisa lanjut bikin versi **one-click launch** untuk macOS (double-click `.command`) supaya tim non-teknis tinggal klik.