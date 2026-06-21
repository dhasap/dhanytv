#!/bin/bash
# ============================================================
# dhanytv - Manual Update Script
# Playlist IPTV + International Merge + Custom EPG Generator
# ============================================================

set -e

TOKEN=""
REPO="dhasap/dhanytv"
TARGET_FILE="dhanytv.m3u"
EPG_OUTPUT="epg.xml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════╗"
    echo "║   dhanytv Manual Update Script       ║"
    echo "║   Playlist + Intl + EPG Generator    ║"
    echo "╚══════════════════════════════════════╝"
    echo -e "${NC}"
}

usage() {
    print_banner
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -s, --source URL    URL sumber playlist (wajib)"
    echo "  -t, --token TOKEN   GitHub personal access token (wajib untuk push)"
    echo "  -n, --no-push       Jangan push ke GitHub"
    echo "  --sanitize PATTERNS Pola sanitasi tambahan (pisahkan dengan |)"
    echo "  -h, --help          Tampilkan help"
    echo ""
    echo "Example:"
    echo "  $0 -s \"https://example.com/playlist.m3u\" -t ghp_xxxxx"
    exit 1
}

NO_PUSH=false
SANITIZE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source) SOURCE_URL="$2"; shift 2 ;;
        -t|--token) TOKEN="$2"; shift 2 ;;
        -n|--no-push) NO_PUSH=true; shift ;;
        --sanitize) SANITIZE="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage ;;
    esac
done

print_banner

if [ -z "$SOURCE_URL" ]; then
    echo -e "${RED}ERROR: URL sumber playlist wajib!${NC}"
    usage
fi

# Step 1: Clone repo
echo -e "${YELLOW}[1/6] Cloning repository...${NC}"
WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"

if [ "$NO_PUSH" = false ] && [ -n "$TOKEN" ]; then
    git clone "https://${TOKEN}@github.com/${REPO}.git" . 2>/dev/null || git clone "https://github.com/${REPO}.git" . 2>/dev/null
else
    git clone "https://github.com/${REPO}.git" . 2>/dev/null
fi

if [ ! -f "$TARGET_FILE" ]; then
    echo -e "${RED}ERROR: $TARGET_FILE tidak ditemukan di repo!${NC}"
    exit 1
fi

# Step 2: Download source
echo -e "${YELLOW}[2/6] Downloading source playlist...${NC}"
curl -sL "$SOURCE_URL" -o source_latest.m3u
echo "  Downloaded: $(wc -c < source_latest.m3u) bytes"

# Step 3: Merge with source using merge_source.py
echo -e "${YELLOW}[3/6] Merging & fixing playlist...${NC}"
BEFORE=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")

SANITIZE_ARG=()
if [ -n "$SANITIZE" ]; then
    SANITIZE_ARG=(--sanitize "$SANITIZE")
fi

python3 update-script/merge_source.py source_latest.m3u --target "$TARGET_FILE" "${SANITIZE_ARG[@]}"

rm -f source_latest.m3u

# Step 3b: Re-inject curated extra channels (World Cup, events). merge_source
# above REPLACES the playlist with the fresh source, so anything hand-added must
# be re-applied here or it disappears every run.
echo -e "${YELLOW}[3b] Injecting curated extra channels...${NC}"
if [ -f "update-script/merge_extra.py" ]; then
    python3 update-script/merge_extra.py --target "$TARGET_FILE" --ci
fi

# Step 4: Merge international channels from iptv-org
echo -e "${YELLOW}[4/7] Merging international channels...${NC}"
if [ -f "update-script/merge_international.py" ]; then
    INTL_BEFORE=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
    python3 update-script/merge_international.py --ci
    INTL_AFTER=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
    echo -e "  ${GREEN}International merge: $INTL_BEFORE → $INTL_AFTER${NC}"
else
    echo -e "${RED}ERROR: update-script/merge_international.py tidak ditemukan!${NC}"
    exit 1
fi

# Step 5: Normalize playlist and generate OTT-friendly variant
echo -e "${YELLOW}[5/7] Cleaning playlist syntax & generating OTT variant...${NC}"
if [ -f "update-script/cleanup_playlist.py" ]; then
    python3 update-script/cleanup_playlist.py "$TARGET_FILE" --write --ott-output dhanytv-ott.m3u --check "${SANITIZE_ARG[@]}"
else
    echo -e "${RED}ERROR: update-script/cleanup_playlist.py tidak ditemukan!${NC}"
    exit 1
fi

AFTER=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
OTT_COUNT=$(grep -c '#EXTINF' dhanytv-ott.m3u 2>/dev/null || echo "0")
echo -e "  ${GREEN}Channel: $BEFORE → $AFTER | OTT: $OTT_COUNT${NC}"

# Step 6: Generate Custom EPG (multi-source)
echo -e "${YELLOW}[6/7] Downloading EPG sources & generating custom EPG...${NC}"

# AqFad2811/epg sources
# NOTE: epg.xml renamed to aqfad_epg.xml to avoid collision with output
AQFAD_BASE="https://raw.githubusercontent.com/AqFad2811/epg/refs/heads/main"
for f in indonesia.xml astro.xml singapore.xml rtmklik.xml unifitv.xml sooka.xml; do
    curl -sL "${AQFAD_BASE}/${f}" -o "${f}" 2>/dev/null || true
done
curl -sL "${AQFAD_BASE}/epg.xml" -o "aqfad_epg.xml" 2>/dev/null || true

# epgshare01.online sources (gzipped)
EPGSHARE_BASE="https://epgshare01.online/epgshare01"
for f in ID1 SG1 MY1 CA2 IT1 FR1 AE1 IN1 ALJAZEERA1 PL1 CZ1; do
    curl -sL "${EPGSHARE_BASE}/epg_ripper_${f}.xml.gz" -o "epgshare01_${f}.xml.gz"
    gunzip -f "epgshare01_${f}.xml.gz" 2>/dev/null || rm -f "epgshare01_${f}.xml.gz"
done

# open-epg.com
curl -sL "https://www.open-epg.com/files/indonesia.xml" -o "open_epg_indonesia.xml" 2>/dev/null || true

# Generate EPG
python3 update-script/generate_epg.py --m3u "$TARGET_FILE" --output "$EPG_OUTPUT" \
    --sources \
        epgshare01_ID1.xml epgshare01_SG1.xml epgshare01_MY1.xml \
        epgshare01_CA2.xml epgshare01_IT1.xml epgshare01_FR1.xml \
        epgshare01_AE1.xml epgshare01_IN1.xml epgshare01_ALJAZEERA1.xml \
        epgshare01_PL1.xml epgshare01_CZ1.xml \
        open_epg_indonesia.xml \
        indonesia.xml astro.xml singapore.xml rtmklik.xml unifitv.xml \
        aqfad_epg.xml sooka.xml

# Cleanup source files ONLY (not output epg.xml!)
rm -f indonesia.xml astro.xml singapore.xml rtmklik.xml unifitv.xml sooka.xml
rm -f aqfad_epg.xml epgshare01_*.xml open_epg_indonesia.xml

# Step 7: Push
echo -e "${YELLOW}[7/7] Pushing to GitHub...${NC}"
if [ "$NO_PUSH" = true ]; then
    echo -e "${CYAN}Skipping push (--no-push)${NC}"
else
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}ERROR: Token diperlukan untuk push!${NC}"
        echo "Gunakan: $0 -t ghp_xxxxx"
    else
        git config user.name "dhanytv-updater"
        git config user.email "dhanytv-updater@users.noreply.github.com"
        git add "$TARGET_FILE" "dhanytv-ott.m3u" "$EPG_OUTPUT" "update-script/"
        CHANNEL_COUNT=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
        OTT_CHANNEL_COUNT=$(grep -c '#EXTINF' dhanytv-ott.m3u 2>/dev/null || echo "0")
        EPG_CHANNELS=$(grep -c '<channel ' "$EPG_OUTPUT" 2>/dev/null || echo "0")
        COMMIT_DATE=$(date -u '+%Y-%m-%d %H:%M UTC')
        git commit -m "manual-update: Playlist + OTT + EPG ($CHANNEL_COUNT ch, $OTT_CHANNEL_COUNT OTT, $EPG_CHANNELS EPG) - $COMMIT_DATE"
        git push "https://${TOKEN}@github.com/${REPO}.git" main
        echo -e "${GREEN}Push berhasil!${NC}"
    fi
fi

echo ""
echo -e "${GREEN}============================================"
echo "  Update Selesai!"
echo "============================================"
echo -e "  Channel  : $(grep -c '#EXTINF' dhanytv.m3u 2>/dev/null || echo 'N/A')"
echo -e "  OTT Ch   : $(grep -c '#EXTINF' dhanytv-ott.m3u 2>/dev/null || echo 'N/A')"
echo -e "  EPG Ch   : $(grep -c '<channel ' epg.xml 2>/dev/null || echo 'N/A')"
echo -e "  EPG Size : $(du -h epg.xml 2>/dev/null | cut -f1 || echo 'N/A')"
echo -e "============================================${NC}"

# Cleanup
cd /
rm -rf "$WORK_DIR"
