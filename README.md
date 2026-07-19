<div align="center">

# 📺 dhanytv — IPTV Indonesia Gratis · Playlist M3U & EPG XMLTV

**Playlist IPTV Indonesia gratis** dengan **1040+ channel live TV** dari **27+ negara**, **EPG XMLTV** lengkap, dan **update otomatis tiap hari**. Siap pakai di **TiviMate, Kodi, VLC, OTT Navigator, Android TV & Smart TV**.

[![Auto Update](https://img.shields.io/github/actions/workflow/status/dhasap/dhanytv/auto-update.yml?label=auto-update&logo=githubactions&logoColor=white)](https://github.com/dhasap/dhanytv/actions)
[![Last Commit](https://img.shields.io/github/last-commit/dhasap/dhanytv?logo=git&logoColor=white)](https://github.com/dhasap/dhanytv/commits/main)
[![Stars](https://img.shields.io/github/stars/dhasap/dhanytv?style=flat&logo=github)](https://github.com/dhasap/dhanytv/stargazers)
[![Channels](https://img.shields.io/badge/channels-1040+-blue)](#-kategori-channel)
[![OTT](https://img.shields.io/badge/OTT--friendly-730+-purple)](#-link-playlist)
[![EPG](https://img.shields.io/badge/EPG-955%20channels-green)](#-epg-electronic-program-guide)
[![Format](https://img.shields.io/badge/format-M3U%20%2F%20M3U8-orange)](#-link-playlist)
[![License](https://img.shields.io/github/license/dhasap/dhanytv)](LICENSE)

</div>

---

## 🔗 Link Playlist

> ⚠️ **Playlist ini di-generate otomatis setiap hari** dari berbagai sumber publik. Beberapa channel mungkin membutuhkan player khusus (DRM ClearKey) — lihat bagian [Player yang Didukung](#-player-yang-didukung).

### Playlist Utama (Semua Channel)
```
https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u
```

### Playlist OTT-Friendly (Tanpa DASH/DRM — untuk player yang tidak support ClearKey)
```
https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv-ott.m3u
```

### EPG XMLTV (Jadwal Program)
```
https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml
```

---

## 📱 Cara Pakai

### TiviMate
1. Buka **Settings → Playlists → Add playlist**
2. Pilih **M3U Playlist**, masukkan URL playlist di atas
3. Buka **Settings → EPG → Add source**, masukkan URL EPG XMLTV

### Kodi (PVR IPTV Simple Client)
1. Install addon **PVR IPTV Simple Client**
2. Masukkan URL M3U di **M3U Play List URL**
3. Masukkan URL EPG di **XMLTV URL**

### VLC / OTT Navigator / Player Lainnya
Langsung buka/import URL playlist M3U di atas.

---

## 🎮 Player yang Didukung

| Player | DASH/DRM (ClearKey) | HLS/MP4 biasa |
|---|---|---|
| **TiviMate** | ✅ (butuh addon) | ✅ |
| **OTT Navigator** | ✅ | ✅ |
| **Kodi (inputstream.adaptive)** | ✅ | ✅ |
| **Televizo** | ✅ | ✅ |
| **VLC** | ❌ | ✅ |
| **MX Player** | ❌ | ✅ |

Beberapa channel Indonesia (RCTI, MNCTV, GTV, dll versi V+) menggunakan **DRM ClearKey** dan hanya bisa diputar di player yang mendukungnya. Gunakan **playlist OTT-friendly** (`dhanytv-ott.m3u`) jika player kamu tidak mendukung DRM.

---

## 📂 Kategori Channel

Playlist ini mencakup channel dari kategori:

- 🇮🇩 **Indonesia** — Nasional, Lokal, TVRI, Sports Indo
- ⚽ **Sports** — bein Sports, Sportstars, dan lainnya
- 🌍 **Internasional** — 27+ negara (Malaysia, Singapura, India, Jepang, Korea, USA, UK, dll)
- 🏆 **WorldCup 2026** — channel siaran Piala Dunia 2026
- 🎥 **Movies & Entertainment**
- 📡 **News**
- 👶 **Kids**
- 🎬 **VOD Indo**

---

## 📄 EPG (Electronic Program Guide)

EPG di-generate otomatis dari multi-sumber (epgshare01.online, open-epg.com, AqFad2811/epg) dengan fallback placeholder untuk channel yang belum punya jadwal asli, sehingga **setiap channel selalu memiliki entri EPG**.

---

## 🤖 Auto-Update

Playlist & EPG di-generate ulang otomatis setiap hari (00:00 UTC / 07:00 WIB) lewat GitHub Actions:
1. Download sumber playlist terbaru
2. Merge & sanitize (hapus channel mati, perbaiki syntax)
3. Inject channel event khusus (World Cup, dll)
4. Merge channel internasional dari iptv-org
5. Generate ulang EPG dari 18+ sumber
6. **Safety gate** — abort otomatis jika ada penurunan channel/EPG drastis (mencegah playlist rusak ter-publish)

---

## ⚠️ Disclaimer

Lihat [DISCLAIMER.md](DISCLAIMER.md) untuk informasi lengkap. Playlist ini mengumpulkan link publik yang tersedia di internet; kami tidak menghosting konten apapun.

---

## 🤝 Kontribusi

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk cara melaporkan channel mati atau request channel baru.

---

## 📝 Changelog

Lihat [CHANGELOG.md](CHANGELOG.md) untuk riwayat perubahan.

---

## 📄 Lisensi

Lihat [LICENSE](LICENSE). Playlist ini disediakan apa adanya untuk tujuan edukasi/personal, boleh dipakai, dimodifikasi, dan didistribusikan.

---

<div align="center">

### ⭐ Kalau repo ini bermanfaat, kasih Star ya!

Star membantu lebih banyak orang menemukan playlist IPTV Indonesia gratis ini.

<a href="https://github.com/dhasap/dhanytv/stargazers">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=dhasap/dhanytv&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=dhasap/dhanytv&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=dhasap/dhanytv&type=Date" width="700" />
  </picture>
</a>

**Kata kunci:** IPTV Indonesia gratis · playlist M3U Indonesia · M3U8 TV Indonesia · TV online gratis · EPG XMLTV Indonesia · nonton Piala Dunia 2026 gratis · IPTV Smart TV · TiviMate Indonesia · Kodi IPTV · VLC IPTV playlist · streaming bola Indonesia

Made with ❤️ for Indonesian IPTV enthusiasts · [github.com/dhasap/dhanytv](https://github.com/dhasap/dhanytv)

</div>
