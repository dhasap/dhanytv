# 📺 dhanytv Web — Nonton TV Live di Browser

Front-end pemutar (SPA statis) untuk playlist **dhanytv**. Membaca `dhanytv-ott.m3u`
/ `dhanytv.m3u` + `epg.xml` langsung dari repo (`raw.githubusercontent.com`) lalu
memutar stream **HLS / DASH (DRM)** langsung di browser — tanpa install aplikasi IPTV.

## 🔐 Fase 2 — DRM + Stream Proxy

- **DASH (`.mpd`) via Shaka Player** dengan EME.
- **ClearKey**: parse `license_key` (JSON `{"kid":"key"}` atau `kid:key` hex) → `drm.clearKeys` Shaka.
- **Widevine**: `license_key` berupa URL → license server EME (`com.widevine.alpha`). *Tidak jalan di iOS/Safari.*
- Toggle mode **OTT (kompatibel)** ↔ **Lengkap (1042 channel, DRM aktif)**.
- **Stream Proxy** (`proxy/worker.js`, Cloudflare Worker): inject header `Referer`/`User-Agent`/`Origin`, tambah CORS, proxy manifest + segmen, **rewrite URL di dalam manifest** (HLS & DASH) agar ikut lewat proxy. Atur URL-nya di **Pengaturan (⚙)**.
- Channel berheader / DRM otomatis dirutekan lewat proxy (request filter Shaka & manifest rewrite untuk HLS).

## ✨ Fitur (MVP)

- **731+ channel HLS** dari playlist OTT, grid kartu dengan logo + badge `HLS`/`DRM` + indikator `LIVE`.
- **Kategori & negara** dari `group-title` (sidebar desktop + chips mobile) dengan jumlah channel.
- **Pencarian real-time** (debounce) berdasarkan nama + grup.
- **EPG now/next** dari `epg.xml` (XMLTV) di tiap kartu + progress bar acara berjalan (zona `Asia/Jakarta`), di-parse di **Web Worker** agar UI tidak nge-freeze.
- **Player hls.js** (fallback HLS native di Safari) dengan overlay loading/error yang ramah + retry otomatis.
- **Halaman player**: video besar, judul + acara now/next, channel terkait (grup sama), tombol **favorit** (localStorage).
- **Deep-link** per channel: `#/channel/<tvg-id>` (bisa dibagikan).
- **Responsif** 360px → desktop → TV, **dark mode** (ikut OS + toggle), kartu fokusable untuk navigasi keyboard/remote.
- **Caching** playlist di localStorage (TTL 1 jam).
- Toggle mode **OTT (kompatibel)** ↔ **Lengkap** (channel lengkap; DRM-nya aktif di Fase 2).

## 🚀 Menjalankan

Tanpa build step — cukup serve folder ini sebagai file statis:

```bash
cd web
python3 -m http.server 8080
# buka http://localhost:8080
```

> Harus lewat HTTP server (bukan `file://`) karena memakai ES modules + Web Worker.

## 🗂️ Struktur

```
web/
├── index.html            # entry SPA (CSS sendiri; hls.js + Shaka via CDN)
├── _headers              # header keamanan + CSP (Cloudflare Pages)
├── README.md
├── DEPLOY.md             # panduan deploy Cloudflare + keamanan
├── src/
│   ├── main.js           # bootstrap: routing hash, grid, search, player, tema, settings
│   ├── styles.css        # design system (neutral + biru, dark mode)
│   └── lib/
│       ├── m3u.js        # parser M3U (#EXTINF / #EXTVLCOPT / #KODIPROP + DRM)
│       ├── epg.js        # store EPG + now/next
│       ├── epgWorker.js  # parser XMLTV di Web Worker
│       ├── player.js     # hls.js (HLS) + Shaka (DASH/DRM) + proxy
│       └── proxy.js      # helper stream-proxy (localStorage)
└── proxy/
    ├── worker.js         # Cloudflare Worker (inject header + CORS + rewrite manifest)
    ├── wrangler.toml     # config deploy + rate-limit binding
    └── package.json
```

## 🌐 Deploy

Full Cloudflare (Pages + Workers) — lihat panduan lengkap di [`DEPLOY.md`](DEPLOY.md).
Singkatnya: **frontend** → Cloudflare Pages (output dir `web`, header keamanan via
`_headers`), **proxy** → Cloudflare Workers (`cd web/proxy && npx wrangler deploy`).

## 🔒 Keamanan

CSP ketat + header keamanan (`_headers`), anti-XSS (escape atribut M3U/EPG), dan proxy
yang di-hardening (CORS allowlist, anti-SSRF, rate-limit per-IP). Detail di [`DEPLOY.md`](DEPLOY.md).

## ⚠️ Catatan kejujuran

Sebagian channel butuh header `Referer`/`User-Agent` atau kena CORS/geo-block — putar
lewat **stream proxy** (aktifkan URL Worker di ⚙ Pengaturan). Channel **Widevine** tidak
jalan di iOS/Safari, dan channel **geo-locked Indonesia** bisa tetap `403` dari edge
global Cloudflare (butuh proxy di VPS Indonesia). Channel HLS biasa diputar langsung.

Website ini **tidak meng-host konten apa pun** — hanya memutar tautan publik dari
playlist repo. Lihat [`DISCLAIMER.md`](../DISCLAIMER.md).
