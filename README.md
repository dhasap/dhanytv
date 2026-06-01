# 📺 dhanytv — Free IPTV Playlist Indonesia & Internasional

[![Auto Update](https://img.shields.io/github/actions/workflow/status/dhasap/dhanytv/auto-update.yml?label=auto-update&logo=github)](https://github.com/dhasap/dhanytv/actions)
[![Channels](https://img.shields.io/badge/channels-600+-blue)](#-channel-categories)
[![EPG](https://img.shields.io/badge/EPG-561%20channels-green)](#-epg-electronic-program-guide)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Free IPTV playlist Indonesia & internasional** dengan **600+ channel** live TV dari **27 negara**, **EPG jadwal lengkap**, dan **update otomatis** setiap minggu. Tersedia dalam format M3U untuk semua IPTV player — TiviMate, Kodi, VLC, IPTV Pro, OttPlayer, Smart TV, dan lainnya.

> 🇮🇩🇷🇨🇰🇷🇯🇵🇹🇷🇬🇧🇺🇸🇩🇪🇫🇷🇧🇷🇮🇳🇹🇭🇲🇾🇸🇬🇨🇳🇻🇳🇵🇭🇲🇽🇷🇺🇦🇪 — **600+ channel dari 27 negara**

---

## 🔗 Playlist Links

Salin salah satu link di bawah ke IPTV player kamu:

| Link | Keterangan |
|------|------------|
| **https://bit.ly/dhanytv** | ⭐ Short link playlist utama (lengkap, termasuk DASH/DRM) |
| **https://bit.ly/dhanytv-ott** | 📺 Short link playlist OTT-friendly (non-DASH/DRM, untuk Smart TV) |
| **https://bit.ly/dhanytv-epg** | 🗓️ Short link EPG (jadwal acara TV) |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u` | Direct raw link playlist utama |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv-ott.m3u` | Direct raw link playlist OTT |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml` | Direct raw link EPG |

---

## 📖 Cara Pakai

### Langkah 1: Install IPTV Player

| App | Platform | Rekomendasi |
|-----|----------|-------------|
| **TiviMate** | Android TV / Fire TV | ⭐ Paling recommended untuk TV |
| **IPTV Pro** | Android | Ringan, stabil |
| **Kodi** + PVR IPTV Simple Client | Semua platform | Gratis, support DASH/DRM |
| **VLC** | Semua platform | Paling universal |
| **OttPlayer** | Samsung TV / LG TV | Untuk Smart TV |
| **SS IPTV** | Smart TV (LG/Samsung) | Alternatif Smart TV |
| **GSE Smart IPTV** | iOS / Apple TV | Untuk pengguna Apple |

### Langkah 2: Tambah Playlist

1. Buka app IPTV player → **Add Playlist** / **Tambah Playlist**
2. Pilih **M3U Link** / **URL Playlist**
3. Paste: `https://bit.ly/dhanytv`
4. Simpan, tunggu loading selesai

**EPG** otomatis tersedia (tertanam di header playlist). Jika tidak muncul, tambah manual:
```
https://bit.ly/dhanytv-epg
```

### Tips Channel DASH/DRM

Channel bertanda **(DASH/MPD)** menggunakan format DASH dengan DRM ClearKey:
- **Kodi**: Install `InputStream Adaptive` + `PVR IPTV Simple Client`
- **TiviMate**: Support DASH/DRM native
- **Smart TV/OTT**: Gunakan `https://bit.ly/dhanytv-ott` jika `.mpd` tidak bisa diputar

---

## 🗂️ Channel Categories

### 🇮🇩 Indonesia

| Kategori | Contoh Channel |
|----------|---------------|
| **Nasional** | RCTI, SCTV, Trans TV, Trans 7, Indosiar, GTV, ANTV, Metro TV, MNCTV, TVRI, MDTV |
| **Regional** | Jawa Pos TV, JTV, Bali TV, Bandung TV, Jogja TV, Banjar TV, Sultra TV |
| **Berita** | CNN Indonesia, CNBC Indonesia, iNews, tvOne, Kompas TV, BTV |
| **Hiburan** | HITS, CelebritiesTV, Vision Prime, Ent, Food Travel, Hanacaraka TV |

### 🌏 Internasional

| Negara | Channel |
|--------|---------|
| 🇺🇸 **United States** | ABC, CBS, NBC, Fox, CNN, MSNBC, Bloomberg, C-SPAN |
| 🇬🇧 **United Kingdom** | BBC, ITV, Channel 4, Sky News |
| 🇯🇵 **Japan** | NHK World |
| 🇰🇷 **Korea** | KBS, MBC, SBS, Arirang, tvN |
| 🇮🇳 **India** | Star Plus, Zee TV, Colors, Sony, Aaj Tak |
| 🇹🇷 **Turkey** | TRT, Show TV, Star TV, ATV, Kanal D |
| 🇹🇭 **Thailand** | Channel 7, Workpoint, One31, Thairath TV |
| 🇵🇭 **Philippines** | GMA, TV5, PTV |
| 🇻🇳 **Vietnam** | VTV, HTV, THVL |
| 🇲🇾 **Malaysia** | Astro Ria, Astro Awani, RTM, TVB, Unifi TV |
| 🇸🇬 **Singapore** | Channel 5, Channel 8, Channel NewsAsia |
| 🇨🇳 **China** | CCTV, Hunan TV, Jiangsu TV, Zhejiang TV, Dragon TV |
| 🇷🇺 **Russia** | Russia 1, Channel One, NTV |
| 🇩🇪 **Germany** | ARD, ZDF, RTL, ProSieben, Deutsche Welle |
| 🇫🇷 **France** | France 2, TF1, M6, France 24 |
| 🇪🇸 **Spain** | TVE, Antena 3, Telecinco |
| 🇮🇹 **Italy** | RAI, Mediaset, La7 |
| 🇧🇷 **Brazil** | Globo, SBT, Record, Band |
| 🇲🇽 **Mexico** | Azteca, Televisa, Canal 5 |
| 🇦🇷 **Argentina** | Telefe, Canal 13, TN |
| 🇨🇴 **Colombia** | Caracol, RCN, Canal 1 |
| 🇦🇪 **UAE & Arab** | Dubai TV, MBC, Al Arabiya |
| 🇪🇬 **Egypt** | Nile TV, CBC, MBC Masr |
| 🇸🇦 **Saudi Arabia** | Saudi TV, Al Ekhbariya |
| 🇳🇬 **Nigeria** | NTA, Channels TV, TVC |
| 🇿🇦 **South Africa** | SABC, e.tv, News24 |
| 🇵🇰 **Pakistan** | Geo TV, ARY, Hum TV |
| 🇧🇩 **Bangladesh** | BTV, Channel i |
| 🇮🇷 **Iran** | IRIB, Manoto, PMC |

### ⚽🎬📰 Kategori Lain

| Kategori | Contoh Channel |
|----------|---------------|
| ⚽ **Sports** | beIN Sports 1-5, SPOTV, SPOTV 2, Sportstars 1-4, Fight Sports, Soccer Channel |
| 🎬 **Premium Movies** | HBO, HBO Hits, HBO Family, Cinemax, AXN, Galaxy, Studio Universal, Celestial Movies |
| 📰 **News** | CNN, BBC News, Al Jazeera, CNBC, Bloomberg, Euronews, France 24, DW |
| 👶 **Kids** | Nickelodeon, Nick Jr, Cartoon Network, Cartoonito, DreamWorks, ZooMoo, CBeebies |
| 📚 **Documentary** | Discovery, National Geographic, BBC Earth, History, Love Nature, Animal Planet |
| 🎵 **Music & Radio** | MTV Live, MTV 90s, Music TV, Internet Radio Indonesia, Hard Rock FM, Prambors |
| ☪️ **Muslim** | Makkah TV, Al Quran Kareem, Tawaf TV, Muslim TV |
| ✝️ **Christian** | EWTN, Reformed 21 |

---

## 📡 EPG (Electronic Program Guide)

**561 channel** punya EPG entry, dengan **18,600+ programme** jadwal acara asli:

| Statistik | Jumlah |
|-----------|--------|
| Channel dengan EPG | 561 |
| Programme entries | 18,600+ |
| File size | ~6.5 MB |

**Sumber EPG:**

| Source | Cakupan |
|--------|---------|
| epgshare01.online | Indonesia, Singapore, Malaysia, Canada, Italy, France, UAE, India, Al Jazeera |
| open-epg.com | 212 channel Indonesia |
| AqFad2811/epg | Indonesia, Malaysia, Singapore, Brunei, Astro, Sooka, RTM |

Channel tanpa jadwal asli tetap dibuatkan entry placeholder supaya terbaca oleh semua IPTV player.

---

## ⚙️ Auto-Update Pipeline

Playlist di-update otomatis setiap **Senin 07:00 WIB** via GitHub Actions.

```
Source M3U → merge_source.py → merge_international.py → cleanup_playlist.py → generate_epg.py → Git Push
             (sanitize)         (iptv-org 27 negara)     (validate + OTT)       (multi-source EPG)
```

**Fitur otomatis:**
- ✅ Merge dari sumber utama + sanitasi
- ✅ Tambah channel internasional dari iptv-org (27 negara)
- ✅ Deduplikasi channel
- ✅ Hapus channel mati
- ✅ Fix syntax M3U (KODIPROP typo, separator, dll)
- ✅ Generate OTT-friendly playlist (non-DASH/DRM)
- ✅ Multi-source EPG generation (17 source files)

Bisa trigger manual: tab **Actions** → **Auto Update IPTV Playlist** → **Run workflow**

---

## 📁 Struktur Repo

```
├── dhanytv.m3u                    # Playlist utama (600+ channel)
├── dhanytv-ott.m3u                # Playlist OTT-friendly (non-DASH/DRM)
├── epg.xml                        # Custom EPG (auto-generated, 6.5MB)
├── LICENSE                        # MIT License
├── .github/workflows/
│   └── auto-update.yml            # GitHub Actions auto-update
└── update-script/
    ├── merge_source.py            # Merge & sanitize source playlist
    ├── merge_international.py     # Merge international channels (iptv-org)
    ├── cleanup_playlist.py        # M3U validator + OTT generator
    ├── generate_epg.py            # Multi-source EPG generator
    └── update_playlist.sh         # Manual update script
```

---

## 🛠️ Development

```bash
# Clone
git clone https://github.com/dhasap/dhanytv.git && cd dhanytv

# Merge dari sumber
python3 update-script/merge_source.py <source.m3u> --target dhanytv.m3u

# Merge channel internasional (iptv-org)
python3 update-script/merge_international.py

# Cleanup + generate OTT
python3 update-script/cleanup_playlist.py dhanytv.m3u --write --ott-output dhanytv-ott.m3u --check

# Generate EPG (multi-source)
python3 update-script/generate_epg.py --m3u dhanytv.m3u --output epg.xml

# Atau pakai script shell (semua langkah)
bash update-script/update_playlist.sh -s "<source_url>" -t "<github_token>"
```

---

## 📝 Notes

- Channel bisa berubah sewaktu-waktu tergantung ketersediaan server
- Beberapa channel mungkin perlu VPN tergantung region
- Untuk DASH/DRM, gunakan player yang support (Kodi, TiviMate)
- Jangan share link sumber playlist, cukup share link repo ini

---

## ⭐ Support

Jika repo ini bermanfaat, bantu dengan **⭐ Star** repo ini supaya lebih banyak orang yang menemukannya!

---

## 📄 License

[MIT License](LICENSE) — bebas dipakai, modifikasi, dan distribusi.

---

<p align="center">
  Made with ❤️ for Indonesian IPTV enthusiasts<br>
  <a href="https://github.com/dhasap/dhanytv">github.com/dhasap/dhanytv</a>
</p>
