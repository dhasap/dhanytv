# 📺 dhanytv Web — Nonton TV Live di Browser

Front-end pemutar (SPA statis) untuk playlist **dhanytv**. Membaca `dhanytv-ott.m3u`
/ `dhanytv.m3u` + `epg.xml` langsung dari repo (`raw.githubusercontent.com`) lalu
memutar stream **HLS** langsung di browser — tanpa install aplikasi IPTV.

> Implementasi **Fase 1 (MVP)** + **Fase 2 (DRM & Proxy)** dari [`web/PRD.md`](PRD.md).

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
├── index.html            # entry SPA (Tailwind-free, CSS sendiri; hls.js via CDN)
├── src/
│   ├── main.js           # bootstrap: routing hash, grid, search, player, tema
│   ├── styles.css        # design system (neutral + biru, dark mode)
│   └── lib/
│       ├── m3u.js        # parser M3U (#EXTINF / #EXTVLCOPT / #KODIPROP)
│       ├── epg.js        # store EPG + now/next
│       ├── epgWorker.js  # parser XMLTV di Web Worker
│       └── player.js     # pembungkus hls.js (+ hook DRM Fase 2)
└── PRD.md
```

## 🌐 Deploy (GitHub Pages)

Workflow `.github/workflows/pages.yml` mem-publish isi folder `web/` ke GitHub Pages
otomatis saat ada push ke `main` yang menyentuh `web/`. Aktifkan **Settings → Pages →
Source: GitHub Actions**. Situs akan tersedia di `https://dhasap.github.io/dhanytv/`.

## ⚠️ Catatan kejujuran

Sebagian channel butuh header `Referer`/`User-Agent` atau kena CORS/geo-block — ini
**tidak bisa** diputar langsung dari browser tanpa **stream proxy** (Fase 2). Channel
DRM (ClearKey/Widevine, `.mpd`) juga menyusul via Shaka Player di Fase 2. MVP fokus ke
channel **HLS non-DRM** yang paling kompatibel.

Website ini **tidak meng-host konten apa pun** — hanya memutar tautan publik dari
playlist repo. Lihat [`DISCLAIMER.md`](../DISCLAIMER.md).
