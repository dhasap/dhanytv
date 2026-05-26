#!/bin/bash
# =============================================================
# Script update manual untuk dhanytv.m3u
# Jalankan: bash update_playlist.sh
# =============================================================

TARGET_FILE="dhanytv.m3u"
# Simpan URL sumber di environment variable, JANGAN hardcode di file
SOURCE_URL="${PLAYLIST_SOURCE}"
SOURCE_FILE="source_latest.m3u"

if [ -z "$SOURCE_URL" ]; then
  echo "ERROR: Set PLAYLIST_SOURCE terlebih dahulu!"
  echo "  export PLAYLIST_SOURCE='URL_SUMBER_ANDA'"
  exit 1
fi

echo ">>> Mengunduh data terbaru..."
curl -sL "$SOURCE_URL" -o "$SOURCE_FILE"

if [ ! -f "$SOURCE_FILE" ] || [ ! -s "$SOURCE_FILE" ]; then
  echo "ERROR: Gagal mengunduh file sumber!"
  exit 1
fi

echo ">>> Download selesai. Ukuran: $(wc -c < "$SOURCE_FILE") bytes"

# Ambil header dari file asli
HEADER_LINE=$(grep -m1 '^#EXTM3U.*url-tvg' "$TARGET_FILE" || grep -m1 '^#EXTM3U' "$TARGET_FILE")
if [ -z "$HEADER_LINE" ]; then
  echo "ERROR: Header #EXTM3U tidak ditemukan!"
  exit 1
fi

OLD_COUNT=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
NEW_COUNT=$(grep -c '#EXTINF' "$SOURCE_FILE" || echo "0")
echo ">>> Channel lama: $OLD_COUNT | Channel baru: $NEW_COUNT"

# Merge: header lama + data baru
{
  echo "$HEADER_LINE"
  echo ""
  echo ""
  SKIP_HEADER=true
  while IFS= read -r line; do
    if [ "$SKIP_HEADER" = true ] && echo "$line" | grep -q '^#EXTM3U'; then
      continue
    fi
    SKIP_HEADER=false
    echo "$line"
  done < "$SOURCE_FILE"
} > "${TARGET_FILE}.new"

sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "${TARGET_FILE}.new"
echo "" >> "${TARGET_FILE}.new"
mv "${TARGET_FILE}.new" "$TARGET_FILE"

# ============================================================
# SANITASI: Bersihkan jejak sumber
# ============================================================
DEFAULT_EPG="https://raw.githubusercontent.com/AqFad2811/epg/refs/heads/main/indonesia.xml"

# Baca pola dari environment variable (format: pat1|pat2|pat3)
if [ -n "$SANITIZE_PATTERNS" ]; then
  IFS='|' read -ra PATTERNS <<< "$SANITIZE_PATTERNS"
  for pat in "${PATTERNS[@]}"; do
    echo ">>> Membersihkan jejak: $pat"
    sed -i "/^https.*${pat}/d" "$TARGET_FILE"
    sed -i "s| tvg-logo=\"[^\"]*${pat}[^\"]*\"| tvg-logo=\"\"|g" "$TARGET_FILE"
    sed -i "s| tvg-url=\"[^\"]*${pat}[^\"]*\"| tvg-url=\"${DEFAULT_EPG}\"|g" "$TARGET_FILE"
  done
fi

sed -i '/^$/N;/^\n$/d' "$TARGET_FILE"
rm -f "$SOURCE_FILE"

AFTER_SANITIZED=$(grep -c '#EXTINF' "$TARGET_FILE")
echo ">>> Setelah sanitasi: $AFTER_SANITIZED channels"

# ============================================================
# SMART CLEANUP: Dedup & hapus channel mati
# ============================================================
echo ">>> Menjalankan smart cleanup..."

python3 << 'PYEOF'
import re

target = "dhanytv.m3u"
with open(target, 'r', encoding='utf-8') as f:
    lines = f.readlines()

header = None
channels = []
cur_extinf = None
cur_props = []
cur_urls = []

for line in lines:
    raw = line.rstrip('\n')
    if raw.startswith('#EXTM3U') and header is None:
        header = raw
        continue
    if raw.startswith('#EXTINF'):
        if cur_extinf is not None:
            channels.append({'extinf': cur_extinf, 'props': cur_props, 'urls': cur_urls})
        cur_extinf = raw
        cur_props = []
        cur_urls = []
    elif cur_extinf is not None and raw.startswith(('#EXTVLCOPT', '#KODIPROP', '#EXTGRP', '###')):
        cur_props.append(raw)
    elif cur_extinf is not None and raw.startswith('http'):
        cur_urls.append(raw)
    elif cur_extinf is not None and (raw.startswith('<') or (raw.startswith('#') and not raw.startswith('#EXTINF') and not raw.startswith('#EXTVLCOPT') and not raw.startswith('#KODIPROP'))):
        cur_props.append(raw)

if cur_extinf is not None:
    channels.append({'extinf': cur_extinf, 'props': cur_props, 'urls': cur_urls})

total_before = len(channels)

# Step 1: Hapus channel tanpa URL stream
channels = [ch for ch in channels if ch['urls']]
removed_nourl = total_before - len(channels)
print(f"    Channel tanpa URL dihapus: {removed_nourl}")

# Step 2: Dedup - nama sama + sumber sama = hapus
def get_name(extinf):
    m = re.search(r',(.+?)$', extinf.strip())
    return re.sub(r'\s+', ' ', m.group(1).strip().lower()) if m else ''

seen = {}
deduped = []
removed_dupes = 0
for ch in channels:
    name = get_name(ch['extinf'])
    url = ch['urls'][0].strip() if ch['urls'] else ''
    key = (name, url)
    if key in seen:
        removed_dupes += 1
        existing_idx = seen[key]
        if len(ch['props']) > len(deduped[existing_idx]['props']):
            deduped[existing_idx] = ch
    else:
        seen[key] = len(deduped)
        deduped.append(ch)

channels = deduped
print(f"    Duplikat (nama+sumber sama) dihapus: {removed_dupes}")

# Step 3: Fix dens.tv URLs (bukan hapus!)
# - http:// → https:// (hindari redirect browser)
# - Hapus ?app_type=web&userid=lite (trigger browser auth)
# - Tambah headers kalau belum ada
dens_fixed = 0
for ch in channels:
    new_urls = []
    for url in ch['urls']:
        if 'dens.tv' in url:
            if url.startswith('http://'):
                url = url.replace('http://', 'https://', 1)
                dens_fixed += 1
            url = re.sub(r'\?app_type=web&userid=lite&chname=[^\s]+', '', url)
            url = re.sub(r'\?app_type=web&userid=lite', '', url)
            new_urls.append(url)
        else:
            new_urls.append(url)
    ch['urls'] = new_urls
    ch['props'] = [p.replace('http-referrer=http://dens.tv', 'http-referrer=https://www.dens.tv/') for p in ch['props']]
    has_dens = any('dens.tv' in u for u in ch['urls'])
    has_referrer = any('dens.tv' in p and 'http-referrer' in p for p in ch['props'])
    if has_dens and not has_referrer:
        ch['props'].insert(0, '#EXTVLCOPT:http-referrer=https://www.dens.tv/')
        ch['props'].insert(1, '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36')
        dens_fixed += 1
print(f"    dens.tv URLs diperbaiki: {dens_fixed}")

# Write
with open(target, 'w', encoding='utf-8') as f:
    if header:
        f.write(header + '\n\n')
    for ch in channels:
        for prop in ch['props']:
            f.write(prop + '\n')
        f.write(ch['extinf'] + '\n')
        for url in ch['urls']:
            f.write(url + '\n')
        f.write('\n')

total_after = len(channels)
print(f"    Total: {total_before} -> {total_after} (dihapus: {total_before - total_after})")
PYEOF

FINAL_COUNT=$(grep -c '#EXTINF' "$TARGET_FILE")
echo ">>> Update selesai! Total channel: $FINAL_COUNT"
