# 📝 Changelog

Semua perubahan penting pada project ini dicatat di sini.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/), dan project ini
memakai penamaan tanggal (rolling release, bukan versi semantik) karena playlist
diperbarui otomatis.

## [Unreleased] — 2026-06-21

### Added
- **Source sekunder (rahasia).** Auto-update kini menarik playlist dari dua source
  sekaligus. URL source kedua disimpan di GitHub Secret `PLAYLIST_SOURCE_2` dan
  **tidak pernah ditulis di kode**. Menambah **±345 channel baru** (beIN Sports,
  Sports, TV Jepang, Movies & Entertainment, Kids, VOD Indo, dll).
- **Blocklist channel mati** (`update-script/blocklist.txt`). Daftar URL stream
  yang sudah dikonfirmasi mati (HTTP 404/400/410/500). `cleanup_playlist.py`
  membuangnya otomatis di setiap run, jadi channel mati tidak muncul lagi walau
  masih ada di source. Statistik baru: `blocklist_removed`.
- **EPG asli untuk channel olahraga Piala Dunia.** Ditambah sumber epgshare01
  **Polandia (PL1)** & **Ceko (CZ1)**, lalu dipetakan di `generate_epg.py`:
  **TVP Sport**, **JOJ Sport**, dan **ČT Sport** kini punya jadwal acara asli
  (sebelumnya hanya placeholder). Total sumber EPG: 17 → **19**.

### Changed
- Jadwal auto-update berjalan **harian (07:00 WIB)** agar EPG selalu segar.
- README, CONTRIBUTING, dan struktur repo diperbarui: 1040+ channel, 730+ OTT,
  955 channel ber-EPG.

### Fixed
- **DRM key hilang akibat EXTINF orphan.** Sebagian source menaruh blok
  `#KODIPROP` (termasuk `license_key` ClearKey) **sebelum** `#EXTINF`, dan ada
  entri EXTINF ganda/orphan. Akibatnya `cleanup_playlist.py` menempelkan key ke
  EXTINF tanpa URL yang lalu dibuang — channel jadi gagal didekripsi (layar
  hitam). Diperbaiki dengan meneruskan props orphan ke channel berikutnya.
  Memulihkan key **beIN Sports 1 Indonesia, TSN 1, Celestial Movies (V+),
  BTV (V+)**, dll (`license_key` 273 → 281).
- **TVRI Nasional dipulihkan.** URL `…/Nasional/hls/Nasional.m3u8` (hidup + punya
  EPG asli) sempat masuk `blocklist.txt` sehingga terbuang tiap run. Dikeluarkan
  dari blocklist agar muncul lagi di grup `WorldCup 2026`.
- **TVRI Sports (SportHD) dihapus** dari `extra_channels.m3u`: URL `SportHD.m3u8`
  sudah 404, dan TVRI tidak menyiarkan Piala Dunia via stream OTT.
- **URL TVRI di-stabilkan.** URL varian bitrate TVRI yang di-hardcode
  (mis. `.../Aceh-avc1_900000=10005-...m3u8`) sering 404 karena nama varian
  dirotasi server. Sekarang otomatis ditulis ulang ke URL master
  (`.../Aceh/hls/Aceh.m3u8`) yang stabil — memulihkan 21 channel TVRI daerah.
- **52 channel mati** (404/400/500) dibersihkan dari playlist dan dimasukkan ke
  blocklist.

### Notes
- **Piala Dunia 2026:** TVRI tidak menyiarkan pertandingan via stream OTT gratis
  (batasan hak siar). Tonton gratis lewat **TV digital terestrial (DVB-T2)**, atau
  via **MAXStream / Folaplay** (berbayar). Lihat README → bagian Piala Dunia.

---

> Untuk riwayat commit lengkap, lihat
> [commits](https://github.com/dhasap/dhanytv/commits/main).
