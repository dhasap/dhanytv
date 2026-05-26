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

FINAL_COUNT=$(grep -c '#EXTINF' "$TARGET_FILE")
echo ">>> Update selesai! Total channel: $FINAL_COUNT"
