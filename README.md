# 📺 dhanytv

IPTV Playlist — Kumpulan channel TV Indonesia & Internasional dalam format M3U.

> **363+ channels** | Auto-update setiap Senin | EPG ready

## 📋 Link Playlist

Salin link raw ini ke player kamu:

```
https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u
```

## 🗂️ Kategori Channel

| Kategori | Contoh Channel |
|----------|---------------|
| 🇮🇩 Indonesia Channels | RCTI, SCTV, Trans TV, Indosiar, GTV, ANTV, Metro TV, dll. |
| 🇮🇩 TVRI Group | TVRI Nasional, TVRI Daerah |
| 🎬 Premium Movies | HBO, HBO Hits, HBO Family, Cinemax, AXN, Galaxy, dll. |
| 🎬 HBO Group | HBO, HBO Hits, HBO Family, HBO Signature, Cinemax |
| 🎭 Entertainment & Lifestyle | Hits, Hits Movies, Studio Universal |
| ⚽ Sports | BeIN Sports, SPOTV, dll. |
| 📰 News | CNN Indonesia, CNBC Indonesia, iNews, dll. |
| 👶 Kids | Nickelodeon, Cartoon Network, dll. |
| 📚 Knowledge & Documentary | Discovery, National Geographic, dll. |
| 🎵 Music & Radio | MTV, Channel V, Internet Radio |
| 🇲🇾 Malaysia | Astro, RTM, dll. |
| 🇸🇬 Mediacorp Singapore | Channel 5, Channel 8, dll. |
| 🇧🇳 Brunei | RTB |
| 🇨🇳 China | CCTV, dll. |
| 🇰🇷 Korean | KBS, SBS, dll. |
| ☪️ Moslem Channel | Makkah TV, dll. |
| ✝️ Christian Channels | dll. |

## 📡 EPG

Playlist sudah include EPG dari [AqFad2811/epg](https://github.com/AqFad2811/epg):

- `indonesia.xml`
- `astro.xml`
- `singapore.xml`
- `unifitv.xml`
- `rtmklik.xml`

## 🎥 Cara Pakai

Buka link playlist di app favorit kamu:

| App | Platform |
|-----|----------|
| **TiviMate** | Android TV / Fire TV |
| **IPTV Pro** | Android |
| **VLC** | Semua platform |
| **Kodi** (PVR IPTV Simple Client) | Semua platform |
| **OttPlayer** | Samsung TV / LG TV |
| **Televizo** | Android |
| **SS IPTV** | Smart TV |

## ⚙️ Auto-Update

Playlist di-update otomatis setiap **Senin 07:00 WIB** via GitHub Actions.

Bisa juga trigger manual: tab **Actions** → **Run workflow**.

### Setup Secrets

Biar auto-update jalan, tambahin secrets di **Settings → Secrets and variables → Actions**:

| Secret | Isi |
|--------|-----|
| `PLAYLIST_SOURCE` | URL sumber playlist |
| `SANITIZE_PATTERNS` | Pola sanitasi (format: `pola1\|pola2\|pola3`) |

## 📁 Struktur Repo

```
├── dhanytv.m3u                   # Playlist utama
├── .github/workflows/
│   └── auto-update.yml           # GitHub Actions workflow
└── update-script/
    └── update_playlist.sh        # Script update manual
```

## 📝 Notes

- Channel bisa berubah/kadaluarsa sewaktu-waktu
- Beberapa channel mungkin perlu VPN tergantung region
- Untuk channel DASH/DRM, gunakan player yang support (Kodi + InputStream Adaptive, TiviMate, dll.)

---

<p align="center">
  Made with ❤️ for Indonesian IPTV enthusiasts
</p>
