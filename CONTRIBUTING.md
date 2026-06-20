# 🤝 Kontribusi ke dhanytv

Terima kasih sudah mau ikut menjaga playlist ini tetap hidup! Berikut cara berkontribusi.

## ➕ Menambah channel baru

Karena auto-update mingguan **menimpa `dhanytv.m3u` dengan source terbaru**, channel yang ditambahkan langsung ke `dhanytv.m3u` akan **hilang tiap Senin**. Tambahkan channel manual di satu tempat yang aman:

**`update-script/extra_channels.m3u`**

File itu di-inject ulang otomatis tiap update (oleh `merge_extra.py`), jadi channel-nya **dijamin tidak terhapus**.

Format tiap channel (HLS lebih disukai karena jalan di semua player):

```m3u
#EXTINF:-1 tvg-id="ContohID" tvg-logo="https://logo.png" group-title="Nama Grup",Nama Channel
https://contoh.com/stream.m3u8
```

Untuk channel berheader khusus (referrer / user-agent), tambahkan baris properti **sebelum** `#EXTINF`:

```m3u
#EXTVLCOPT:http-referrer=https://situs.com/
#EXTVLCOPT:http-user-agent=Mozilla/5.0 ...
#EXTINF:-1 tvg-id="..." group-title="...",Nama Channel
https://contoh.com/stream.m3u8
```

Lalu buka **Pull Request** atau **Issue** dengan detail channel.

## 🪲 Lapor channel mati / error

Buka **Issue** dan sebutkan:
- Nama channel
- Grup (group-title)
- Error yang muncul (mis. "tidak didukung", buffering, layar hitam)
- Player yang dipakai (TiviMate, VLC, Kodi, dll.)

> Catatan: channel **(V+) / (DASH/MPD)** memakai DRM dan butuh player yang support (TiviMate / OTT Navigator / Kodi). Itu **bukan** channel mati — lihat [README → FAQ](README.md#-faq).

## 🚫 Blocklist channel mati permanen

Channel yang **benar-benar mati** (HTTP 404/400/410/500) bisa dimasukkan ke
**`update-script/blocklist.txt`** supaya **otomatis dibuang setiap auto-update** —
walau source masih menyertakannya. Cukup tempel URL stream-nya satu per baris:

```text
https://contoh.com/stream-mati.m3u8
# komentar diabaikan
re:^https://server-mati\.com/    # awali "re:" untuk pola regex
```

`cleanup_playlist.py` membaca file ini di setiap run dan menghapus entry yang cocok
(lihat statistik `blocklist_removed` di log). Ini cara paling bersih melawan channel
mati yang terus muncul dari source.

## 🧪 Tes lokal sebelum PR

```bash
# Validasi & rapikan playlist (harus exit 0)
python3 update-script/cleanup_playlist.py dhanytv.m3u --write --ott-output dhanytv-ott.m3u --check

# Pastikan channel kurasi ter-inject
python3 update-script/merge_extra.py

# Generate EPG (opsional, butuh source EPG)
python3 update-script/generate_epg.py --m3u dhanytv.m3u --output epg.xml
```

## 📋 Aturan ringkas

- Prioritaskan stream **HLS (.m3u8)** tanpa DRM — paling kompatibel.
- Jangan commit `epg.xml` hasil generate lokal kalau tanpa source lengkap (nanti jadi placeholder semua).
- Jangan share URL **source rahasia** (`PLAYLIST_SOURCE`, `PLAYLIST_SOURCE_2`) di mana pun.
- Satu channel = satu blok rapi (properti → `#EXTINF` → URL).

Makasih sudah bantu! ⭐
