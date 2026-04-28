# Security Checklist (Publik Internet)

Jika app dibuka via IP/domain publik, lakukan minimal ini:

1. Aktifkan login app (env):

```bash
export UI_USERNAME="admin"
export UI_PASSWORD="ganti-password-kuat"
./run_ui.sh
```

2. Gunakan HTTPS (reverse proxy Caddy/Nginx), **jangan HTTP langsung**.
3. Batasi port terbuka:
   - publik: 80/443
   - port 8501 hanya localhost/internal
4. Gunakan password panjang + unik.
5. Rotasi kredensial berkala.

---

## Contoh Caddy (auto HTTPS)

`/etc/caddy/Caddyfile`

```caddy
data.example.com {
    reverse_proxy 127.0.0.1:8501
}
```

Lalu restart Caddy:

```bash
sudo systemctl restart caddy
```

---

## Contoh Nginx (HTTPS + basic auth)

```nginx
server {
    listen 443 ssl;
    server_name data.example.com;

    ssl_certificate     /etc/letsencrypt/live/data.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/data.example.com/privkey.pem;

    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Catatan

- Sertifikat TLS umumnya untuk domain, bukan IP publik langsung.
- Untuk akses aman tanpa expose publik, pertimbangkan Cloudflare Tunnel / Tailscale.
