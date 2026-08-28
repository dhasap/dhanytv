# 📝 Changelog

Semua perubahan penting pada project ini dicatat di sini.
Format mengikuti [Keep a Changelog](https://keepachangelog.com/), dan project ini
memakai penamaan tanggal (rolling release, bukan versi semantik) karena playlist
diperbarui otomatis.

## [Unreleased] — 2026-08-28

### Added
- **163 channel baru dari iptv-org categories.** Tindak lanjut issue #23
  (beIN Sports hilang) — beIN Sports 1/2/3 region-locked MENA tidak bisa
  ditambah, sebagai gantinya ekspansi dari 14 kategori: sports, auto, news,
  entertainment, music, kids, family, documentary, animation, movies,
  religious, general, series, comedy. Semua URL di-verify HEAD 200 HLS
  (Content-Type `application/vnd.apple.mpegurl`). Total playlist: 666 → 841
  EXTINF, EPG tetap 100% ter-cover.
- **iNews HD backup dari `live.i-news.tv`** (official iNews website) sebagai
  sumber kedua selain DensTV dan mncmedia workers. Eksplorasi 50+ repo GitHub
  untuk SCTV/Indosiar/MNCTV/GTV alternatif — tidak ada HLS publik lain yang
  verified, sehingga DensTV tetap satu-satunya sumber untuk channel-channel
  tersebut.
- **beIN Sports XTRA (4 source):** bein-xtra-xumo, bein-esp-xumo (1080p &
  720p), bein-xtra-bein, amg01334-beinsportsllc-beinxtra-localnow. Untuk
  Sportstars & channel bola international lain, eksplorasi menemukan sumber
  `amagi.tv` dan `tubi.video` yang reliable.
- **Pipeline safety gate berlapis:**
  - Syntax-check `python3 -m py_compile update-script/*.py` di awal workflow
    (mencegah `SyntaxError`/`NameError` crash mid-pipeline seperti yang
    terjadi 28-08-2026 run 04:51 & 05:00 UTC).
  - `merge_source.py` anti-wipe guard: refuse overwrite kalau merge result
    0 channel.
  - 4 over-broad regex di blocklist (streamlock.net, 122.248.43.242,
    103.255.15.222, live.cnbcindonesia.com) diganti dengan exact-URL — beberapa
    channel hidup dari host yang sama ikut ter-block sebelumnya.

### Fixed
- **SCTV (DASH/MPD) redirect ke browser.** 2 entry DIHAPUS (INDIHOME DASH
  CDN `.mpd` — bikin VLC/TiviMate player M3U8 murni redirect ke browser
  eksternal). User sekarang hanya melihat "SCTV HD" (DensTV HLS) dan "SCTV"
  (masterplayer DRM) — keduanya non-DASH.
- **Indosiar buffering.** Hapus 1 entry masterplayer DRM (Vidio) + 1 entry
  INDIHOME DASH. Tambah "Indosiar (SD 720p)" dari DensTV h207/02.m3u8 untuk
  internet lambat.
- **MNCTV HD / GTV HD / iNews HD dari server mncmedia workers sering 429
  rate-limit.** Tambah backup dari DensTV (h21, h20, h19) untuk semua 3
  channel.
- **Channel Indosiar, MDTV, DAAI TV, ANTV, TVOne, SCTV, Channel Jowo, Dens
  Life, Dens Food, Dens Learning, Dens Show, MAGNA, Garuda TV, RTV, MetroTV**
  dari DensTV — semua stabil, verified HLS non-DRM.
- **Channel mati (13 channel radio i-Radio, Trax FM, Hard Rock FM, BBC
  Treasures, Kids TV, ATV Avrupa, +SBT Novelas, Aupur TV)** ditambahkan ke
  blocklist.txt supaya otomatis terbuang di auto-update berikutnya.

### Changed
- Playlist stats: 666 → **923 channel** (+257 net: 109 ekspansi Indo/IT/SA +
  163 iptv-org categories + 82 dari auto-update berikutnya), 534 → **743
  OTT**, 622 → **877 EPG channels**, 30.821 → **32.922 programmes**.
- Auto-update workflow jalan harian 07:00 WIB + `workflow_dispatch` (manual
  trigger). Run terakhir 28-08-2026 12:19 UTC: **completed, success** ✅.

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
