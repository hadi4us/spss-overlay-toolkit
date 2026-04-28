# Go Online dari MacBook (Publik Internet)

Panduan ini membuat aplikasi bisa diakses publik dari MacBook tanpa setup server VPS, menggunakan **Cloudflare Tunnel**.

## Metode yang dipakai
- Jalankan Streamlit lokal di `localhost:8501`
- Buka URL publik `https://xxxx.trycloudflare.com` lewat `cloudflared`

## 1) Prasyarat

```bash
brew install cloudflared
```

Pastikan toolkit sudah ter-clone dan dependency terpasang (lihat `INSTALL_MACOS.md`).

## 2) Cara cepat (one-click script)

Dari Finder:
- buka folder repo
- masuk `scripts/macbook/`
- double click `start_online.command`

Atau dari Terminal:

```bash
cd spss-overlay-toolkit
./scripts/macbook/start_online.command
```

## 3) Set login UI (WAJIB untuk publik)

Sebelum run, set credential sendiri:

```bash
export UI_USERNAME="admin"
export UI_PASSWORD="password-kuat-min-16-char"
./scripts/macbook/start_online.command
```

> Jika tidak diset, script akan pakai default sementara dan menampilkan warning.

## 4) Ambil URL publik

Saat script jalan, terminal akan menampilkan URL semacam:

- `https://random-name.trycloudflare.com`

URL ini bisa langsung dibagikan.

## 5) Stop service

- Stop tunnel: `Ctrl + C` di terminal tunnel
- Stop app lokal:

```bash
./scripts/macbook/stop_local.command
```

## 6) Keamanan minimum (wajib)

1. Selalu aktifkan `UI_USERNAME` + `UI_PASSWORD`
2. Jangan bagikan password di chat publik
3. Ganti password berkala
4. Jika dipakai tim, lebih aman deploy ke VPS dengan reverse proxy + HTTPS + basic auth tambahan

## 7) Troubleshooting

### URL tunnel tidak muncul
- Pastikan internet stabil
- Coba ulang command `cloudflared tunnel --url http://localhost:8501`

### Halaman tidak bisa dibuka
- Pastikan UI benar-benar jalan di `http://localhost:8501`
- Cek log:

```bash
tail -f /tmp/spss_overlay_ui.log
```

### Port 8501 bentrok
Jalankan port lain:

```bash
PORT=8502 ./run_ui.sh
cloudflared tunnel --url http://localhost:8502
```
