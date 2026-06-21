# 🚀 Deploy dhanytv Web — Full Cloudflare

Dua bagian: **frontend** (Cloudflare Pages) + **stream-proxy** (Cloudflare Workers).
Keduanya gratis.

---

## A. Frontend → Cloudflare Pages

**Lewat dashboard (paling gampang):**
1. Cloudflare Dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
2. Pilih repo `dhasap/dhanytv`.
3. Build settings:
   - **Framework preset:** `None`
   - **Build command:** *(kosongkan)*
   - **Build output directory:** `web`
   - **Root directory:** `/` (biarkan)
4. **Save & Deploy**. Situs live di `https://<project>.pages.dev`.
5. File `web/_headers` otomatis dipakai Pages → memasang header keamanan + CSP.

> Setiap push ke `main` akan auto-deploy ulang.

---

## B. Stream-Proxy → Cloudflare Workers

```bash
cd web/proxy
npm install              # ambil wrangler (atau: npm i -g wrangler)
npx wrangler login       # login ke akun Cloudflare
# WAJIB: edit wrangler.toml → ALLOWED_ORIGINS = domain Pages kamu
npx wrangler deploy
```

Hasil: `https://dhanytv-proxy.<akun>.workers.dev`.

Lalu buka situs → **⚙ Pengaturan** → tempel URL Worker → **Simpan**.
Channel berheader/DRM otomatis lewat proxy; channel HLS biasa tetap langsung.

---

## 🔒 Keamanan yang sudah dipasang

**Frontend (`web/_headers`)**
- **CSP ketat**: `script-src` cuma `self` + `cdn.jsdelivr.net` (hls.js/Shaka). Tidak ada
  `unsafe-inline` di script → injeksi script diblokir. (Logo gagal-load di-fallback via
  event listener, bukan `onerror` inline.)
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy` mematikan kamera/mic/geo, `object-src 'none'`.
- Logo `http://` otomatis ditolak (anti mixed-content) → fallback ke inisial.
- Atribut M3U/EPG di-escape sebelum render (anti-XSS dari nama/logo channel).

**Proxy (`web/proxy/worker.js`)**
- **CORS allowlist** (`ALLOWED_ORIGINS`): situs lain tidak bisa "nebeng" proxy kamu.
- **Anti-SSRF**: target wajib `http(s)` publik; `localhost`, IP privat
  (`10/8`, `127/8`, `192.168/16`, `172.16-31`, CGNAT `100.64/10`), link-local/metadata
  (`169.254.169.254`), IPv6 loopback/ULA, port aneh → **ditolak**. Tidak bisa proxy ke
  dirinya sendiri.
- **Rate limit per-IP** (binding `RL`, 600 req/60 dtk) → balas `429` saat di-spam.
- Hanya method `GET/HEAD/OPTIONS`; hanya header `Referer/User-Agent/Origin` yang
  diteruskan (cookie/header sensitif dibuang); panjang URL dibatasi; `cpu_ms` dibatasi.

### Pengerasan tambahan (opsional, di dashboard Cloudflare)
- **WAF / Rate Limiting Rules** di depan Worker & Pages (free tier punya jatah).
- **Bot Fight Mode** (Security → Bots).
- **Custom domain** + **Always Use HTTPS** + **Cloudflare Access** kalau mau privat.
- Aktifkan **caching** segmen di Worker untuk hemat kuota.

> ⚠️ Cloudflare jalan di edge global, **bukan dijamin Indonesia** → channel geo-locked ID
> (IndiHome, Vision+, dll) bisa tetap `403`. Untuk itu butuh proxy di VPS Indonesia.
