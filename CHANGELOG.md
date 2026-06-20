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

### Changed
- Jadwal auto-update berjalan **harian (07:00 WIB)** agar EPG selalu segar.
- README, CONTRIBUTING, dan struktur repo diperbarui: 990+ channel, 700+ OTT,
  918 channel ber-EPG.

### Fixed
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
