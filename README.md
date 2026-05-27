# 📺 dhanytv

IPTV Playlist Indonesia & Internasional — Auto-update, Full EPG, Smart Cleanup.

> **370+ channels** | Update otomatis setiap Senin | EPG Indonesia lengkap

---

## 🔗 Link Playlist

Salin salah satu link di bawah ke IPTV player kamu:

| Link | Keterangan |
|------|------------|
| **https://bit.ly/dhanytv** | Short link playlist utama (lengkap, termasuk DASH/DRM) |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv.m3u` | Direct raw link playlist utama |
| `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv-ott.m3u` | Playlist OTT-friendly: hanya stream non-DASH/non-DRM supaya lebih aman untuk app yang sering membuka `.mpd` ke browser |

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
4. Paste link playlist:
   - Playlist lengkap: `https://bit.ly/dhanytv`
   - Jika app kamu sering membuka channel `.mpd`/DASH ke browser, pakai playlist OTT-friendly: `https://raw.githubusercontent.com/dhasap/dhanytv/main/dhanytv-ott.m3u`
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
- **Smart TV/OTT TV**: jika app membuka link `.mpd` ke browser atau tidak mau play, gunakan `dhanytv-ott.m3u` karena file ini hanya berisi stream non-DASH/non-DRM.

Catatan SCTV: entry `SCTV (DASH/MPD)` adalah stream DASH valid, tetapi beberapa app OTT TV tidak menangani `.mpd` dan melemparkannya ke browser. Itu bukan redirect dari server; gunakan playlist OTT-friendly atau player yang support DASH.

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
| **Channel dengan EPG** | 271 channel |
| **File size** | ~2–4 MB (tergantung jumlah channel & jadwal upstream) |

**Kenapa Custom EPG?** File EPG gabungan dari source asli berukuran 24+ MB — terlalu besar dan bikin timeout di banyak OTT TV player. Custom EPG kita hanya berisi channel yang ada di playlist. Channel yang tidak punya jadwal asli dari upstream tetap dibuatkan entry EPG placeholder (`Jadwal belum tersedia`) supaya semua channel bisa terbaca/mapping oleh IPTV player.

**Sudah termasuk EPG dari:**

| Source | Cakupan |
|--------|---------|
| `indonesia.xml` | 80+ channel Indonesia (RCTI, SCTV, Trans TV, dll.) |
| `astro.xml` | 14 channel Malaysia/Astro |
| `singapore.xml` | 5 channel Mediacorp Singapore |
| `rtmklik.xml` | 3 channel RTM Malaysia |
| `unifitv.xml` | 11 channel UniFi TV (HBO, Cinemax, dll.) |

`tvg-id` sudah di-matching otomatis ke EPG source saat update berjalan. Untuk channel yang tidak punya `tvg-id`, sistem membuat ID stabil `auto.*`; untuk channel yang tidak ada jadwal asli, sistem membuat programme placeholder harian. EPG URL sudah tercantum di header playlist (`url-tvg`), jadi kebanyakan player akan otomatis load EPG.

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
- **M3U syntax cleanup**: separator kategori diubah jadi komentar, `#KODIPROP` typo diperbaiki, dan `#EXTINF` malformed dinormalisasi
- **Fallback URL cleanup**: beberapa URL dalam satu channel dipecah jadi entry `Alt` agar parser M3U ketat tidak bingung
- **OTT playlist generation**: `dhanytv-ott.m3u` dibuat otomatis tanpa DASH/DRM untuk app yang membuka `.mpd` ke browser
- **dens.tv fix**: URL `http://` di-convert ke `https://` supaya tidak redirect ke browser
- **EPG auto-mapping**: `tvg-id` disesuaikan otomatis dengan EPG source dan channel tanpa `tvg-id` diberi ID `auto.*`
- **Custom EPG generation**: EPG difilter hanya untuk channel yang ada di playlist, plus fallback placeholder untuk channel tanpa jadwal upstream
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
├── dhanytv.m3u                    # Playlist utama lengkap
├── dhanytv-ott.m3u                # Playlist OTT-friendly (non-DASH/non-DRM)
├── epg.xml                        # Custom EPG (auto-generated)
├── LICENSE                        # MIT License
├── .github/
│   └── workflows/
│       └── auto-update.yml        # GitHub Actions workflow
└── update-script/
    ├── merge_source.py            # Merge & sanitize source playlist
    ├── cleanup_playlist.py        # Cleaner/validator M3U + generator dhanytv-ott.m3u
    ├── generate_epg.py            # Generator XMLTV + fallback EPG placeholder
    └── update_playlist.sh         # Script update manual (lokal)
```

---

## 🛠️ Development

### Menjalankan Manual

```bash
# Clone repo
git clone https://github.com/dhasap/dhanytv.git
cd dhanytv

# Merge dari sumber
python3 update-script/merge_source.py <source.m3u> --target dhanytv.m3u

# Cleanup + generate OTT
python3 update-script/cleanup_playlist.py dhanytv.m3u --write --ott-output dhanytv-ott.m3u --check

# Generate EPG
python3 update-script/generate_epg.py --m3u dhanytv.m3u --output epg.xml

# Atau pakai script shell (semua langkah di atas)
bash update-script/update_playlist.sh -s "<source_url>" -t "<github_token>"
```

### Pipeline

```
Source M3U → merge_source.py → cleanup_playlist.py → generate_epg.py → Push
               (sanitize)         (validate+OTT)        (EPG XML)
```

---

## 📝 Notes

- Channel bisa berubah atau kadaluarsa sewaktu-waktu tergantung ketersediaan server
- Beberapa channel mungkin perlu VPN tergantung region kamu
- Untuk channel DASH/DRM (bertanda V+), gunakan player yang support — Kodi + InputStream Adaptive atau TiviMate
- Jika pakai OTT TV/Smart TV app yang tidak support DASH, gunakan `dhanytv-ott.m3u`
- Update otomatis setiap Senin, tapi bisa juga di-trigger manual kapan saja
- Jangan share link sumber playlist, cukup share link repo ini

---

## 📄 License

[MIT License](LICENSE) — bebas dipakai, modifikasi, dan distribusi.

---

<p align="center">
  Made with ❤️ for Indonesian IPTV enthusiasts
</p>
