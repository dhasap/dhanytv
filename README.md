<div align="center">

# 📺 dhanytv — IPTV Indonesia Gratis · Playlist M3U & EPG XMLTV

**Playlist IPTV Indonesia gratis** dengan **1040+ channel live TV** dari **27+ negara**, **EPG XMLTV** lengkap, dan **update otomatis tiap hari**. Siap pakai di **TiviMate, Kodi, VLC, OTT Navigator, Android TV & Smart TV**.

[![Auto Update](https://img.shields.io/github/actions/workflow/status/dhasap/dhanytv/auto-update.yml?label=auto-update&logo=githubactions&logoColor=white)](https://github.com/dhasap/dhanytv/actions)
[![Last Commit](https://img.shields.io/github/last-commit/dhasap/dhanytv?logo=git&logoColor=white)](https://github.com/dhasap/dhanytv/commits/main)
[![Stars](https://img.shields.io/github/stars/dhasap/dhanytv?style=flat&logo=github)](https://github.com/dhasap/dhanytv/stargazers)
[![Channels](https://img.shields.io/badge/channels-1040+-blue)](#-kategori-channel)
[![OTT](https://img.shields.io/badge/OTT--friendly-730+-purple)](#-link-playlist)
[![EPG](https://img.shields.io/badge/EPG-955%20channels-green)](#-epg-electronic-program-guide)
[![Format](https://img.shields.io/badge/format-M3U%20%7C%20M3U8%20%7C%20XMLTV-orange)](#-link-playlist)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

🇮🇩 🇰🇷 🇯🇵 🇹🇷 🇬🇧 🇺🇸 🇩🇪 🇫🇷 🇧🇷 🇮🇳 🇹🇭 🇲🇾 🇸🇬 🇨🇳 🇻🇳 🇵🇭 🇲🇽 🇷🇺 🇦🇪 🇪🇬 🇸🇦 🇳🇬 🇿🇦 🇵🇰 🇧🇩 🇮🇷

</div>

> **English:** Free Indonesia IPTV playlist — 1040+ M3U/M3U8 live TV channels from 27+ countries, XMLTV EPG guide, daily auto-update. Works with TiviMate, Kodi, VLC, OTT Navigator, Android TV & Smart TV.

---

## ⚽ Nonton Piala Dunia 2026 GRATIS

Piala Dunia FIFA 2026 (11 Juni – 19 Juli 2026). **TVRI memegang hak siar di Indonesia, tapi TIDAK menyiarkan online** via tvri.go.id — gratis hanya lewat **TV digital terestrial (DVB-T2)**, atau online berbayar via **MAXStream (Telkomsel) / Folaplay**. Channel sepak bola lain tersedia di playlist ini, grup **`WorldCup 2026`** + **`⚽ Bola Indonesia`**:

| Channel | Acara | Format |
|---------|-------|--------|
| **TVRI Nasional** | Siaran nasional FTA (bukan stream WC online) | HLS — jalan di semua player |
| **TVP Sport, JOJ Sport, ČT Sport** | Feed olahraga (ada EPG jadwal asli) | DASH/DRM — butuh TiviMate / OTT Navigator / Kodi |
| **RTB Go Live & Aneka** | Feed Brunei (geo-locked) | HLS — mungkin geo-block dari luar negeri |
| **TransTV, Trans7, Metro TV** | Bola Indonesia | HLS — jalan di semua player |
| **beIN Sports, SPOTV, Champions TV** | Liga top Eropa | DASH/DRM — butuh TiviMate / OTT Navigator / Kodi |

> 💡 Kalau muncul **"siaran ini tidak didukung"**, itu channel format **DASH + DRM** — pakai **TiviMate**, **OTT Navigator**, atau **Kodi** (bukan VLC). Atau pilih channel grup **⚽ Bola Indonesia** yang HLS dan jalan di player apa pun.

---

## 📑 Daftar Isi

- [Link Playlist](#-link-playlist)
- [Cara Pakai](#-cara-pakai)
- [Kategori Channel](#-kategori-channel)
- [EPG (Electronic Program Guide)](#-epg-electronic-program-guide)
- [Auto-Update Pipeline](#️-auto-update-pipeline)
- [Struktur Repo](#-struktur-repo)
- [Development](#️-development)
- [Kontribusi](#-kontribusi)
- [FAQ](#-faq)
- [Disclaimer](#️-disclaimer)
- [Lisensi](#-lisensi)

---

## 🔗 Link Playlist

Salin salah satu link di bawah ke IPTV player kamu:

| Link | Keterangan |
|------|------------|
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u` | ⭐ Playlist utama (lengkap, termasuk DASH/DRM) |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv-ott.m3u` | 📺 Playlist OTT-friendly / Smart TV (non-DASH/DRM, HLS saja) |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml` | 🗓️ EPG XMLTV (jadwal acara) |

**Short link:** [`bit.ly/dhanytv`](https://bit.ly/dhanytv) · [`bit.ly/dhanytv-ott`](https://bit.ly/dhanytv-ott) · [`bit.ly/dhanytv-epg`](https://bit.ly/dhanytv-epg)

| Statistik | Jumlah |
|-----------|--------|
| Channel playlist utama | **1040+** |
| Channel OTT-friendly | **730+** |
| Channel dengan EPG | **955** |
| Programme entries | **23.000+** |
| Negara | **27+** |
| Update | **Otomatis tiap hari** |

---

## 📖 Cara Pakai

### 1. Install IPTV Player

| App | Platform | Catatan |
|-----|----------|---------|
| **TiviMate** | Android TV / Fire TV | ⭐ Paling recommended, support DASH/DRM |
| **OTT Navigator** | Android / Android TV | Support DASH/DRM + EPG bagus |
| **Kodi** + PVR IPTV Simple Client | Semua platform | Gratis, butuh add-on InputStream Adaptive untuk DASH/DRM |
| **VLC** | Semua platform | Universal, **tapi tidak support DRM** |
| **OttPlayer / SS IPTV** | Samsung / LG TV | Untuk Smart TV |
| **GSE Smart IPTV** | iOS / Apple TV | Untuk pengguna Apple |

### 2. Tambah Playlist

1. Buka player → **Add Playlist** / **Tambah Playlist**
2. Pilih **M3U URL**
3. Paste: `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u`
4. Simpan, tunggu loading selesai.

EPG sudah tertanam di header playlist. Kalau jadwal tidak muncul, tambah URL EPG manual:
`https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml`

### 3. Channel "tidak didukung"?

Channel **(V+)** / **(DASH/MPD)** memakai format **DASH + DRM ClearKey**. Hanya jalan di player yang support DRM:
- ✅ **TiviMate**, **OTT Navigator** — native
- ✅ **Kodi** — install `InputStream Adaptive`
- ❌ **VLC / player bawaan Smart TV** — tidak support DRM → pakai playlist **OTT** atau channel grup **⚽ Bola Indonesia**

---

## 🗂️ Kategori Channel

### 🇮🇩 Indonesia

| Kategori | Contoh |
|----------|--------|
| **Nasional** | RCTI, SCTV, Trans TV, Trans 7, Indosiar, GTV, ANTV, Metro TV, MNCTV, TVRI, MDTV, MOJI |
| **Berita** | CNN Indonesia, CNBC Indonesia, iNews, tvOne, Kompas TV, BTV |
| **Olahraga / Bola** | TVRI, SCTV, MOJI, beIN Sports, SPOTV, Champions TV, Sportstars |
| **Regional** | Jawa Pos TV, JTV, Bali TV, Bandung TV, Jogja TV, Banjar TV, Sultra TV |
| **Hiburan** | HITS, CelebritiesTV, Vision Prime, Food Travel, Hanacaraka TV |

### 🌏 Internasional (27 negara)

🇺🇸 US · 🇬🇧 UK · 🇯🇵 Japan · 🇰🇷 Korea · 🇮🇳 India · 🇹🇷 Turkey · 🇹🇭 Thailand · 🇵🇭 Philippines · 🇻🇳 Vietnam · 🇲🇾 Malaysia · 🇸🇬 Singapore · 🇨🇳 China · 🇷🇺 Russia · 🇩🇪 Germany · 🇫🇷 France · 🇪🇸 Spain · 🇮🇹 Italy · 🇧🇷 Brazil · 🇲🇽 Mexico · 🇦🇷 Argentina · 🇨🇴 Colombia · 🇦🇪 UAE · 🇪🇬 Egypt · 🇸🇦 Saudi Arabia · 🇳🇬 Nigeria · 🇿🇦 South Africa · 🇵🇰 Pakistan

### ⚽🎬📰 Kategori Lain

| Kategori | Contoh |
|----------|--------|
| ⚽ **Sports** | beIN Sports 1-5, SPOTV, Sportstars 1-4, Premier Sports, TNT Sports, Fight Sports |
| 🎬 **Premium Movies** | HBO, HBO Hits, Cinemax, AXN, Galaxy, Studio Universal, Celestial Movies |
| 📰 **News** | CNN, BBC News, Al Jazeera, CNBC, Bloomberg, Euronews, France 24, DW |
| 👶 **Kids** | Nickelodeon, Nick Jr, Cartoon Network, DreamWorks, ZooMoo, CBeebies |
| 📚 **Documentary** | Discovery, National Geographic, BBC Earth, History, Animal Planet |
| 🎵 **Music & Radio** | MTV Live, MTV 90s, Music TV, Hard Rock FM, Prambors |

---

## 📡 EPG (Electronic Program Guide)

Jadwal acara dalam format **XMLTV** supaya muncul di TiviMate, Kodi, OTT Navigator, dan player lain. **Semua 955 channel punya entri EPG** (audit otomatis memastikan tidak ada yang bolong) dengan **23.000+ programme**; channel yang belum cocok dengan sumber EPG diberi placeholder *"Jadwal belum tersedia"* agar tetap terbaca player.

| Statistik | Nilai |
|-----------|-------|
| Channel dengan EPG | 955 (100%) |
| Programme entries | 23.000+ |
| File size | ~8.5 MB |
| Format | XMLTV (`epg.xml`) |

**Sumber EPG:** epgshare01.online (Indonesia, Singapore, Malaysia, Canada, Italia, Prancis, UAE, India, Al Jazeera, **Polandia, Ceko**) · open-epg.com · AqFad2811/epg (Indonesia, Malaysia, Singapore, Brunei, Astro, Sooka, RTM, dll).

Channel tanpa jadwal asli tetap dibuatkan entry placeholder supaya terbaca semua IPTV player.

---

## ⚙️ Auto-Update Pipeline

Playlist di-update otomatis setiap **hari 07:00 WIB** via GitHub Actions:

```
Source M3U (×2) → merge_source → merge_extra → merge_international → cleanup → generate_epg → safety-gate → Git Push
   (rahasia)       (sanitize)    (Bola/World Cup) (iptv-org 27 negara) (validate+OTT+blocklist) (EPG XMLTV)
```

- ✅ Tarik source terbaru + sanitasi link
- ✅ **URL source disimpan di GitHub Secrets** (`PLAYLIST_SOURCE`, `PLAYLIST_SOURCE_2`) — tidak pernah ditulis di kode
- ✅ **Channel Piala Dunia 2026 & Bola Indonesia selalu di-inject ulang** (tidak pernah terhapus)
- ✅ Tambah channel internasional dari [iptv-org](https://github.com/iptv-org/iptv) (27 negara)
- ✅ Deduplikasi + **buang channel mati otomatis lewat `blocklist.txt`** + fix syntax M3U
- ✅ Generate playlist OTT-friendly (HLS, non-DRM)
- ✅ Generate EPG XMLTV multi-source (19 sumber)
- ✅ **Safety gate:** commit dibatalkan kalau channel/EPG anjlok tidak wajar

Trigger manual: tab **Actions** → **Auto Update IPTV Playlist** → **Run workflow**.

---

## 📁 Struktur Repo

```
├── dhanytv.m3u                 # Playlist utama (1040+ channel)
├── dhanytv-ott.m3u             # Playlist OTT-friendly (730+ channel, non-DASH/DRM)
├── epg.xml                     # EPG XMLTV (auto-generated, ~9 MB)
├── LICENSE                     # MIT License
├── DISCLAIMER.md               # Catatan hukum / DMCA
├── CONTRIBUTING.md             # Cara menambah / melaporkan channel
├── .github/
│   ├── workflows/auto-update.yml   # GitHub Actions auto-update
│   └── ISSUE_TEMPLATE/             # Template request & report channel
└── update-script/
    ├── merge_source.py         # Merge & sanitasi source playlist
    ├── merge_extra.py          # Re-inject channel kurasi (World Cup, Bola)
    ├── extra_channels.m3u      # Daftar channel manual yang selalu ada
    ├── merge_international.py   # Merge channel internasional (iptv-org)
    ├── cleanup_playlist.py     # Validator M3U + generator OTT + blocklist
    ├── blocklist.txt           # Daftar URL stream mati (auto-dibuang saat update)
    ├── generate_epg.py         # Generator EPG multi-source
    └── update_playlist.sh      # Script update manual
```

---

## 🛠️ Development

```bash
git clone https://github.com/dhasap/dhanytv.git && cd dhanytv

# Merge dari source
python3 update-script/merge_source.py <source.m3u> --target dhanytv.m3u

# Inject channel kurasi (World Cup, Bola Indonesia)
python3 update-script/merge_extra.py

# Merge channel internasional (iptv-org)
python3 update-script/merge_international.py

# Cleanup + generate OTT
python3 update-script/cleanup_playlist.py dhanytv.m3u --write --ott-output dhanytv-ott.m3u --check

# Generate EPG multi-source
python3 update-script/generate_epg.py --m3u dhanytv.m3u --output epg.xml

# Atau semua langkah sekaligus:
bash update-script/update_playlist.sh -s "<source_url>" -t "<github_token>"
```

---

## 🤝 Kontribusi

Mau menambah channel atau lapor channel mati? Lihat **[CONTRIBUTING.md](CONTRIBUTING.md)**.

Channel manual (yang tidak ada di source) ditambahkan di **`update-script/extra_channels.m3u`** — itu satu-satunya tempat yang dijamin tidak terhapus saat auto-update harian.

---

## ❓ FAQ

<details>
<summary><b>Channel bola muncul "siaran ini tidak didukung", kenapa?</b></summary>

Channel itu format **DASH + DRM ClearKey**. Player seperti VLC dan player bawaan Smart TV tidak bisa dekripsi DRM. Pakai **TiviMate**, **OTT Navigator**, atau **Kodi** (+ InputStream Adaptive), atau pilih channel grup **⚽ Bola Indonesia** yang HLS.
</details>

<details>
<summary><b>Apakah ini gratis?</b></summary>

Ya, 100% gratis dan open-source. Tidak perlu langganan, login, atau bayar.
</details>

<details>
<summary><b>Channel-nya legal?</b></summary>

Semua link dikumpulkan dari sumber publik di internet. Repo ini tidak meng-host video apa pun. Lihat [DISCLAIMER.md](DISCLAIMER.md).
</details>

<details>
<summary><b>Kok ada channel yang mati/buffering?</b></summary>

Server stream berubah sewaktu-waktu. Auto-update harian membersihkan link mati. Beberapa channel mungkin butuh VPN tergantung region.
</details>

<details>
<summary><b>EPG / jadwal acara tidak muncul?</b></summary>

EPG sudah tertanam di header playlist. Kalau tidak muncul, tambah manual URL `epg.xml` di setting EPG player kamu, lalu refresh.
</details>

---

## ⚠️ Disclaimer

Repo ini **tidak meng-host, meng-upload, atau menyimpan konten media apa pun**. Semua link adalah playlist M3U yang mengarah ke stream yang sudah tersedia bebas di internet. Hak cipta tetap milik pemegang masing-masing. Baca lengkap di **[DISCLAIMER.md](DISCLAIMER.md)**.

---

## 📄 Lisensi

[MIT License](LICENSE) — bebas dipakai, dimodifikasi, dan didistribusikan.

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
