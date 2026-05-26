# 📺 dhanytv

IPTV Playlist Indonesia & Internasional — Auto-update, Full EPG, Smart Cleanup.

> **340+ channels** | Update otomatis setiap Senin | EPG Indonesia lengkap

---

## 🔗 Link Playlist

Salin salah satu link di bawah ke IPTV player kamu:

| Link | Keterangan |
|------|------------|
| **https://bit.ly/dhanytv** | Short link (ringkas, mudah diingat) |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u` | Direct raw link |

---

## 📖 Cara Pakai

### Langkah 1: Install IPTV Player

Pilih salah satu app di bawah sesuai device kamu:

| App | Platform | Catatan |
|-----|----------|---------|
| **TiviMate** | Android TV / Fire TV | Paling recommended untuk TV |
| **IPTV Pro** | Android | Ringan, stabil |
| **Televizo** | Android | Support DASH/DRM |
| **Kodi** + PVR IPTV Simple Client | Semua platform | Gratis, support semua format |
| **VLC** | Semua platform | Paling universal |
| **OttPlayer** | Samsung TV / LG TV | Untuk Smart TV |
| **SS IPTV** | Smart TV (LG/Samsung) | Alternatif Smart TV |
| **GSE Smart IPTV** | iOS / Apple TV | Untuk pengguna Apple |

### Langkah 2: Tambah Playlist

1. Buka app IPTV player pilihan kamu
2. Cari menu **Add Playlist** / **Tambah Playlist** / **New Playlist**
3. Pilih opsi **M3U Link** atau **URL Playlist**
4. Paste link: `https://bit.ly/dhanytv`
5. Beri nama (contoh: "dhanytv") lalu simpan
6. Tunggu proses loading channel selesai

### Langkah 3: EPG (Otomatis)

EPG (jadwal acara TV) sudah otomatis tersedia karena URL EPG sudah tertanam di header playlist (`url-tvg`). Kebanyakan IPTV player akan otomatis load EPG.

Jika EPG tidak muncul otomatis, tambah URL EPG manual:
1. Di app IPTV player, cari menu **EPG** / **Electronic Program Guide**
2. Tambah URL EPG:
   ```
   https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml
   ```

### Tips untuk Channel DASH/DRM

Beberapa channel (yang bertanda V+) menggunakan format DASH dengan DRM ClearKey. Untuk memutar channel-channel ini:

- **Kodi**: Install addon `InputStream Adaptive` + `PVR IPTV Simple Client`
- **TiviMate**: Sudah support DASH/DRM secara native
- **VLC**: Sebagian channel DASH bisa diputar langsung
- **Smart TV**: Gunakan OttPlayer atau SS IPTV yang support format adaptif

---

## 🗂️ Kategori Channel

| Kategori | Contoh Channel |
|----------|---------------|
| 🇮🇩 Indonesia Channels | RCTI, SCTV, Trans TV, Trans 7, Indosiar, GTV, ANTV, Metro TV, MNCTV |
| 🇮🇩 Indonesia Regional | TVRI Nasional, Jawa Pos TV, JTV, Bali TV, dll. |
| 🎬 Premium Movies | HBO, HBO Hits, HBO Family, Cinemax, AXN, Galaxy, Studio Universal |
| 🎬 HBO Group | HBO, HBO Hits, HBO Family, HBO Signature, Cinemax |
| ⚽ Sports | BeIN Sports 1-5, SPOTV, SPOTV 2, Fight Sports, Soccer Channel |
| 📰 News | CNN Indonesia, CNBC Indonesia, iNews, tvOne, Metro TV, Al Jazeera |
| 👶 Kids | Nickelodeon, Nick Jr, Cartoon Network, DreamWorks, ZooMoo, CBeebies |
| 📚 Knowledge & Documentary | Discovery, National Geographic, BBC Earth, History, Love Nature |
| 🎵 Music & Radio | MTV Live, MTV 90s, Channel V, Internet Radio Indonesia |
| 🇲🇾 Malaysia | Astro Ria, Astro Awani, RTM, dll. |
| 🇸🇬 Singapore | Channel 5, Channel 8, Channel NewsAsia |
| 🇧🇳 Brunei | RTB |
| 🇨🇳 China | CCTV, Jiangsu TV |
| 🇰🇷 Korean | KBS, SBS, tvN, Arirang |
| ☪️ Moslem Channel | Makkah TV, Al Quran Kareem, Tawaf TV, Muslim TV |
| ✝️ Christian Channels | Various Christian channels |

---

## 📡 EPG (Electronic Program Guide)

Playlist ini menggunakan **Custom EPG** yang di-generate otomatis dari [AqFad2811/epg](https://github.com/AqFad2811/epg), difilter hanya untuk channel yang ada di playlist:

| Info | Detail |
|------|--------|
| **EPG URL** | `https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml` |
| **Channel dengan EPG** | 114 channel |
| **File size** | ~4 MB (ringan, cepat loading) |

**Kenapa Custom EPG?** File EPG gabungan dari source asli berukuran 24+ MB — terlalu besar dan bikin timeout di banyak OTT TV player. Custom EPG kita hanya berisi channel yang ada di playlist, jadi ukurannya jauh lebih kecil dan loadingnya cepat.

**Sudah termasuk EPG dari:**

| Source | Cakupan |
|--------|---------|
| `indonesia.xml` | 80+ channel Indonesia (RCTI, SCTV, Trans TV, dll.) |
| `astro.xml` | 14 channel Malaysia/Astro |
| `singapore.xml` | 5 channel Mediacorp Singapore |
| `rtmklik.xml` | 3 channel RTM Malaysia |
| `unifitv.xml` | 11 channel UniFi TV (HBO, Cinemax, dll.) |

`tvg-id` sudah di-matching otomatis ke EPG source saat update berjalan. EPG URL sudah tercantum di header playlist (`url-tvg`), jadi kebanyakan player akan otomatis load EPG.

---

## ⚙️ Auto-Update

Playlist di-update otomatis setiap **Senin 07:00 WIB** via GitHub Actions.

Bisa juga trigger manual:
1. Buka tab **Actions** di repo ini
2. Pilih **Auto Update IPTV Playlist**
3. Klik **Run workflow**

### Fitur Smart Cleanup

Saat auto-update berjalan, sistem otomatis melakukan:

- **Dedup**: Channel dengan nama + URL sama hanya disimpan sekali
- **Dead channel removal**: Channel tanpa URL stream dihapus otomatis
- **dens.tv fix**: URL `http://` di-convert ke `https://` supaya tidak redirect ke browser
- **EPG auto-mapping**: `tvg-id` disesuaikan otomatis dengan EPG source
- **Custom EPG generation**: EPG difilter hanya untuk channel di playlist (~4MB vs 24MB+)
- **Sanitasi**: Jejak sumber playlist dibersihkan

### Setup Secrets (Untuk Fork/Clone)

Biar auto-update jalan, tambahin secrets di **Settings → Secrets and variables → Actions**:

| Secret | Isi | Contoh |
|--------|-----|--------|
| `PLAYLIST_SOURCE` | URL sumber playlist | `https://example.com/source.m3u` |
| `SANITIZE_PATTERNS` | Pola sanitasi (format: `pola1\|pola2`) | `sumber1\|sumber2` |

---

## 📁 Struktur Repo

```
├── dhanytv.m3u                    # Playlist utama
├── epg.xml                        # Custom EPG (auto-generated)
├── .github/
│   └── workflows/
│       └── auto-update.yml        # GitHub Actions workflow
└── update-script/
    └── update_playlist.sh         # Script update manual (lokal)
```

---

## 📝 Notes

- Channel bisa berubah atau kadaluarsa sewaktu-waktu tergantung ketersediaan server
- Beberapa channel mungkin perlu VPN tergantung region kamu
- Untuk channel DASH/DRM (bertanda V+), gunakan player yang support — Kodi + InputStream Adaptive atau TiviMate
- Update otomatis setiap Senin, tapi bisa juga di-trigger manual kapan saja
- Jangan share link sumber playlist, cukup share link repo ini

---

<p align="center">
  Made with ❤️ for Indonesian IPTV enthusiasts
</p>
