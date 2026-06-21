# 📺 PRD — dhanytv Web (Website Nonton TV)

> **Product Requirements Document**
> Status: **Draft / Perencanaan** · Eksekusi: *menyusul*
> Sumber data: repo [`dhasap/dhanytv`](https://github.com/dhasap/dhanytv)
> Terakhir diperbarui: 2026-06-21

---

## 1. Ringkasan (Overview)

**dhanytv Web** adalah website nonton TV (live streaming) berbasis browser yang
memutar channel dari playlist `dhanytv.m3u` / `dhanytv-ott.m3u` dan menampilkan
jadwal acara dari `epg.xml` milik repo ini. Pengguna bisa browsing channel per
kategori/negara, mencari channel, melihat EPG (acara sekarang & berikutnya), lalu
memutar stream langsung di browser — tanpa perlu install aplikasi IPTV.

Website ini adalah **front-end pemutar** untuk data yang sudah dihasilkan pipeline
auto-update repo. Ia **tidak** meng-host konten apa pun (lihat `DISCLAIMER.md`),
hanya membaca file playlist + EPG yang sudah publik di repo.

---

## 2. Tujuan & Sasaran (Goals)

| # | Tujuan | Metrik sukses |
|---|--------|---------------|
| G1 | Nonton channel langsung di browser tanpa app | Channel HLS non-DRM bisa diputar < 5 detik time-to-first-frame |
| G2 | Navigasi channel mudah (kategori, negara, search) | Temukan channel apa pun dalam ≤ 3 klik |
| G3 | Tampilkan EPG (acara sekarang/berikutnya) | ≥ 95% channel menampilkan status EPG (acara atau placeholder) |
| G4 | Responsif di desktop, tablet, HP, Smart TV browser | Layout usable dari lebar 360px s/d 4K |
| G5 | Dukung sebanyak mungkin channel (HLS + DASH/DRM) | Maksimalkan channel yang bisa diputar lewat proxy + DRM |

**Non-goals (eksplisit di luar scope):**
- Tidak meng-host/menyimpan video.
- Tidak ada akun/login, langganan, atau pembayaran (MVP).
- Tidak menggantikan TiviMate/Kodi untuk fitur DVR/timeshift kompleks.
- Tidak membuat playlist sendiri — sumber tetap dari pipeline repo.

---

## 3. Target Pengguna (Personas)

1. **Penonton kasual (mayoritas)** — buka web di HP/laptop, mau cepat nonton TV
   nasional / bola tanpa ribet. Prioritas: channel HLS yang "tinggal klik".
2. **Power user IPTV** — paham DRM/DASH, mau akses channel premium (V+, beIN)
   lewat browser yang support Widevine/ClearKey.
3. **Pengguna Smart TV / TV Box browser** — butuh UI besar, navigasi remote
   (focus state, arrow-key), dan player yang ringan.

---

## 4. Sumber Data (dari repo)

| File | Isi | Dipakai untuk |
|------|-----|---------------|
| `dhanytv.m3u` | ~1.040 channel lengkap (HLS + DASH/DRM, lengkap `#KODIPROP` license_key, header `#EXTVLCOPT`) | Mode "Lengkap" (butuh DRM/proxy) |
| `dhanytv-ott.m3u` | ~730 channel HLS non-DRM | Mode "OTT" (paling kompatibel browser) |
| `epg.xml` | EPG XMLTV, 955 channel, 23rb+ programme | Jadwal acara, "now/next" |

**Atribut M3U yang harus diparse:**
- `#EXTINF` → `tvg-id`, `tvg-logo`, `group-title`, nama channel
- `#EXTVLCOPT:http-referrer=`, `http-user-agent=`, `http-origin=` → header stream
- `#KODIPROP:inputstream.adaptive.license_type=` (`clearkey` / `com.widevine.alpha`)
- `#KODIPROP:inputstream.adaptive.license_key=` (ClearKey `kid:key` atau URL license server)
- URL stream: `.m3u8` (HLS) atau `.mpd` (DASH), bisa pakai sufiks pipe `|Header=value`

**Pemetaan EPG:** channel di-link ke EPG via `tvg-id` → `<channel id>` di `epg.xml`.

---

## 5. Scope & MVP

### 5.1 MVP (Fase 1)
- Parse `dhanytv-ott.m3u` (HLS non-DRM) + `epg.xml`.
- Grid channel dengan logo, nama, grup; filter kategori + search.
- Player HLS (hls.js) dengan info "now/next" dari EPG.
- Responsif desktop/HP. Deploy statis (GitHub Pages).

### 5.2 Fase 2 — Channel lengkap + DRM
- Parse `dhanytv.m3u`; dukung DASH (dash.js / Shaka) + ClearKey & Widevine.
- **Stream proxy** untuk inject header (`Referer`/`User-Agent`) & atasi CORS.
- Toggle mode "OTT (kompatibel)" vs "Lengkap (butuh DRM)".

### 5.3 Fase 3 — Pengalaman
- Halaman EPG/guide timeline per channel.
- Favorit (localStorage), "terakhir ditonton", riwayat.
- Mode remote-friendly (navigasi panah) untuk Smart TV.
- PWA (installable, offline shell).

---

## 6. Functional Requirements

### FR-1 Daftar & Kategori Channel
- Tampilkan channel sebagai kartu (logo, nama, badge grup, indikator DRM/HLS).
- Filter berdasarkan `group-title` (mis. Nasional, Sports, WorldCup 2026) & negara.
- Pencarian channel real-time (nama + grup), debounce.
- Tandai channel yang butuh DRM/player khusus dengan badge jelas.

### FR-2 Pemutar (Player)
- HLS via **hls.js** (fallback `native` di Safari).
- DASH via **Shaka Player** (preferensi) atau dash.js — support EME DRM.
- ClearKey: parse `kid:key` hex dari `license_key` → konfigurasi `clearKeys`.
- Widevine: gunakan URL `license_key` sebagai license server (EME).
- Terapkan header `Referer`/`User-Agent`/`Origin` lewat **proxy** (lihat FR-6).
- Kontrol: play/pause, volume, fullscreen, pilih kualitas (level HLS/representation DASH), retry otomatis saat error.
- Indikator status: loading, buffering, error (dengan pesan ramah + saran).

### FR-3 EPG (Electronic Program Guide)
- Parse `epg.xml` (XMLTV) → index `channel id` → daftar `programme`.
- Tampilkan **now/next** di kartu channel & overlay player.
- Halaman guide: timeline horizontal (jam) × channel (Fase 3).
- Tangani placeholder `"Jadwal belum tersedia"` (tampilkan label netral).
- Progress bar acara berjalan (start/stop vs waktu sekarang, zona `Asia/Jakarta`).

### FR-4 Pencarian & Navigasi
- Search global channel.
- Deep-link per channel (`/#/channel/<tvg-id>`), bisa dibagikan.
- Breadcrumb kategori, tombol back.

### FR-5 Responsif & Aksesibilitas
- Layout fluid 360px → desktop → TV (grid auto-fill).
- Dark mode (ikuti OS) + light mode.
- Navigasi keyboard/remote (focus ring, arrow keys) untuk mode TV.

### FR-6 Stream Proxy (Backend kecil — Fase 2)
- Endpoint proxy yang:
  - Menambahkan header `Referer`/`User-Agent`/`Origin` sesuai `#EXTVLCOPT`.
  - Menambah header CORS (`Access-Control-Allow-Origin`) agar browser bisa fetch.
  - Mem-proxy manifest + segmen (HLS `.m3u8`+`.ts`/`.m4s`, DASH `.mpd`).
  - Menulis ulang URL relatif di manifest agar lewat proxy juga.
  - **Opsional:** lokasi server di Indonesia untuk mengatasi geo-block channel ID.
- Channel yang tidak butuh header/CORS diputar langsung (tanpa proxy) demi performa.

---

## 7. Arsitektur Teknis

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (dhanytv Web — SPA statis)                          │
│  ┌───────────┐  ┌────────────┐  ┌─────────────────────────┐  │
│  │ Parser M3U │  │ Parser EPG │  │ Player (hls.js / Shaka) │  │
│  │  + EPG     │  │  (XMLTV)   │  │  + DRM (ClearKey/WV)    │  │
│  └─────┬──────┘  └─────┬──────┘  └───────────┬─────────────┘  │
└────────┼───────────────┼─────────────────────┼───────────────┘
         │ fetch raw      │ fetch raw           │ stream
         ▼                ▼                     ▼
  raw.githubusercontent (dhanytv.m3u / -ott.m3u / epg.xml)
                                               │
                                   ┌───────────▼────────────┐
                                   │  Stream Proxy (Fase 2)  │
                                   │  inject header + CORS   │
                                   │  (Cloudflare Worker /   │
                                   │   VPS Indonesia)        │
                                   └───────────┬────────────┘
                                               ▼
                                      Origin CDN channel
```

### Keputusan arsitektur
- **Front-end statis** (tanpa server) untuk MVP → host gratis di GitHub Pages.
- **Data langsung dari `raw.githubusercontent.com`** (selalu sinkron dengan pipeline auto-update). Cache di client (localStorage + ETag) untuk hemat.
- **Proxy terpisah & opsional** (Fase 2) — hanya untuk channel yang butuh header/CORS/geo. Diimplementasikan sebagai Cloudflare Worker (murah/serverless) atau VPS kecil di Indonesia.

---

## 8. Tech Stack (usulan)

| Layer | Pilihan | Alasan |
|-------|---------|--------|
| Framework UI | **Vanilla JS + Vite**, atau React/Svelte | MVP ringan; bisa statis. (Selaras gaya HTML repo) |
| Styling | **Tailwind CSS** | Cepat, responsif, dark mode |
| HLS | **hls.js** | Standar de-facto, ringan |
| DASH + DRM | **Shaka Player** | Dukungan EME (Widevine) + ClearKey matang |
| EPG parse | `DOMParser` / `fast-xml-parser` | XMLTV = XML |
| Proxy (F2) | **Cloudflare Workers** atau Node/Express di VPS ID | Serverless murah / kontrol geo |
| Hosting | **GitHub Pages** (front-end) | Gratis, sejalan dengan repo |
| Build | Vite + GitHub Actions | Auto-deploy saat push |

---

## 9. UI/UX Requirements

- **Beranda:** baris "Sedang tayang" (now), pintasan kategori populer (Nasional,
  Sports, WorldCup 2026, Bola Indonesia), grid channel.
- **Kartu channel:** logo, nama, badge grup, badge `HLS` / `DRM`, judul acara "now"
  + progress bar.
- **Halaman player:** video besar, judul channel + acara now/next, daftar channel
  terkait (grup sama) di sidebar, tombol favorit.
- **Sidebar/menu kategori:** daftar `group-title` + negara dengan jumlah channel.
- **Empty/error states** yang jelas: "Channel butuh player DRM", "Stream geo-locked,
  coba VPN Indonesia", "Stream sedang offline".
- **Visual:** netral/bersih (abu-abu, putih, aksen biru) + dark mode; hindari gradien
  ungu generik. Logo channel dari `tvg-logo`.

---

## 10. Non-Functional Requirements

- **Performa:** parse 1.000+ channel & EPG besar (8 MB) tanpa nge-freeze →
  parsing via streaming/worker, virtualisasi grid (render yang terlihat saja).
- **Caching:** simpan playlist+EPG di localStorage dengan TTL (mis. 1 jam) + cek ETag.
- **Keamanan:** sanitasi atribut M3U/EPG sebelum render (cegah XSS dari nama/logo).
  Jangan pernah bocorkan URL source rahasia (tidak relevan di front-end — data sudah publik).
- **Kompatibilitas:** Chrome/Edge/Firefox terbaru; Safari (HLS native, Widevine→FairPlay tidak didukung); browser Android TV.
- **Legal:** tampilkan tautan `DISCLAIMER.md`; website hanya memutar tautan publik, tidak meng-host.

---

## 11. Tantangan Teknis & Solusi

| Tantangan | Dampak | Solusi |
|-----------|--------|--------|
| Browser tak bisa set `Referer`/`User-Agent` (forbidden headers) | Channel berheader gagal | **Proxy** inject header (Fase 2) |
| CORS di banyak origin CDN | `fetch`/playback diblokir | Proxy tambah header CORS |
| Geo-block channel Indonesia (IndiHome, dens, Vision+) | 403 dari luar ID | Proxy di **VPS Indonesia** (opsional) |
| DRM ClearKey (`.mpd`) | Tak jalan di player polos | Shaka `clearKeys` dari `license_key` |
| DRM Widevine (license server) | Butuh EME + CDM | Shaka EME; **tidak jalan di iOS/Safari** |
| EPG 8 MB | Parsing berat | Web Worker + lazy index per channel |
| 1.000+ kartu | Lag render | Virtual scroll + lazy-load logo |
| Mixed content (http stream di https web) | Diblokir browser | Proxy via https / utamakan https |

> **Catatan jujur:** sebagian channel (geo-locked + Widevine + iOS) tetap tidak bisa
> diputar di semua kondisi browser. MVP fokus ke channel HLS non-DRM yang paling
> kompatibel; channel premium ditangani bertahap via proxy + DRM.

---

## 12. Roadmap / Fase Eksekusi

| Fase | Lingkup | Output |
|------|---------|--------|
| **F0 — Setup** | Scaffold Vite+Tailwind di `web/`, struktur folder, CI deploy GitHub Pages | Web kosong ter-deploy |
| **F1 — MVP** | Parse OTT m3u + EPG, grid+kategori+search, player hls.js, now/next, responsif | Nonton channel HLS di browser |
| **F2 — DRM + Proxy** | Parse m3u lengkap, Shaka+ClearKey/Widevine, stream proxy header/CORS, toggle mode | Channel premium/DASH bisa diputar |
| **F3 — Pengalaman** | Halaman guide EPG, favorit, mode remote/TV, PWA | Pengalaman lengkap multi-device |

---

## 13. Metrik Sukses

- ≥ 90% channel **HLS non-DRM** dari `dhanytv-ott.m3u` bisa diputar di browser (lewat proxy bila perlu).
- Time-to-first-frame channel HLS < 5 detik (koneksi normal).
- ≥ 95% channel menampilkan status EPG (acara atau placeholder).
- Lighthouse: Performance ≥ 80, Accessibility ≥ 90 (desktop).

---

## 14. Risiko & Mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Stream sering mati / berubah | Web baca data live dari repo (sudah ada blocklist + auto-update harian) |
| Proxy kena abuse / biaya | Rate-limit, cache, hanya proxy channel yang perlu |
| Masalah legal/hak cipta | Disclaimer jelas + mekanisme takedown (sudah ada di `DISCLAIMER.md`) |
| DRM Widevine tak jalan di iOS | Beri pesan jelas + arahkan ke mode OTT / channel HLS |
| EPG/playlist besar bikin lambat | Worker parsing + virtualisasi + caching |

---

## 15. Rencana Struktur Folder `web/`

```
web/
├── PRD.md                 # dokumen ini
├── index.html             # entry SPA
├── package.json
├── vite.config.js
├── tailwind.config.js
├── src/
│   ├── main.js            # bootstrap app
│   ├── lib/
│   │   ├── m3u.js         # parser M3U + #EXTVLCOPT/#KODIPROP
│   │   ├── epg.js         # parser XMLTV + index now/next
│   │   ├── player.js      # hls.js + Shaka + DRM
│   │   └── proxy.js       # helper URL proxy (Fase 2)
│   ├── components/        # grid, kartu, sidebar, player UI
│   ├── views/             # beranda, player, guide
│   └── styles.css
├── proxy/                 # Fase 2 — Cloudflare Worker / Node proxy
│   └── worker.js
└── public/                # ikon, manifest PWA
```

---

> **Langkah berikutnya:** setelah PRD ini disetujui, mulai **Fase 0 (scaffold)** lalu
> **Fase 1 (MVP)**. Eksekusi koding menyusul sesuai instruksi.
