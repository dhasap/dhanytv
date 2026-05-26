#!/bin/bash
# ============================================================
# dhanytv - Manual Update Script
# Playlist IPTV + Custom EPG Generator
# Minimal safe fixes - preserves ALL source props & URLs
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
    echo "║   Playlist + Custom EPG Generator    ║"
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
    echo "  -h, --help          Tampilkan help"
    echo ""
    echo "Example:"
    echo "  $0 -s \"https://example.com/playlist.m3u\" -t ghp_xxxxx"
    exit 1
}

NO_PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source) SOURCE_URL="$2"; shift 2 ;;
        -t|--token) TOKEN="$2"; shift 2 ;;
        -n|--no-push) NO_PUSH=true; shift ;;
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

# Step 3: Merge with minimal fixes
echo -e "${YELLOW}[3/6] Merging & fixing playlist...${NC}"
BEFORE=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
HEADER_LINE=$(grep -m1 '^#EXTM3U.*url-tvg' "$TARGET_FILE" || grep -m1 '^#EXTM3U' "$TARGET_FILE")

# Apply minimal fixes preserving ALL source props and URLs
python3 << 'PYEOF'
import re

source_file = "source_latest.m3u"
target_file = "dhanytv.m3u"
import sys

# Read header from existing file
with open(target_file, 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('#EXTM3U'):
            header_line = line.rstrip('\n')
            break

# EPG mapping
channel_to_epg = {
    'RCTI': 'RCTI.id', 'MNC TV': 'MNCTV.id', 'MNCTV': 'MNCTV.id',
    'GTV': 'GTV.id', 'Indosiar': 'Indosiar.id', 'SCTV': 'SCTV.id',
    'TransTV': 'TransTV.id', 'Trans TV': 'TransTV.id',
    'Trans7': 'Trans7.id', 'Trans 7': 'Trans7.id',
    'MDTV': 'MDTV.id', 'iNews': 'iNews.id',
    'Kompas TV': 'KompasTV.id', 'KompasTV': 'KompasTV.id',
    'Metro TV': 'MetroTV.id', 'MetroTV': 'MetroTV.id',
    'TVOne': 'tvOne.id', 'TV One': 'tvOne.id', 'tvOne': 'tvOne.id',
    'SindoNews': 'SindoNewsTV.id', 'ANTV': 'ANTV.id',
    'IDX': 'IDX.id', 'IDX Channel': 'IDX.id',
    'TVRI': 'TVRI.id', 'BTV': 'BTV.id',
    'CNN Indonesia': 'CNNIndonesia.id',
    'CNBC Indonesia': 'CNBCIndonesia.id',
    'DAAI TV': 'DAAITV.id',
    'RTV': 'RTV.id', 'Nusantara TV': 'NusantaraTV.id',
    'Garuda TV': 'GarudaTV.id', 'BN Channel': 'BNChannel.id',
    'MAGNA Channel': 'MagnaChannel.id',
    'HITS': 'HITS.id', 'Hits': 'HITS.id',
    'HITS Movies': 'HitsMovies.id', 'HitsMovies': 'HitsMovies.id',
    'Studio Universal': 'StudioUniversal.id',
    'AXN': 'AXN.id', 'GALAXY': 'GALAXY.id',
    'GALAXY Premium': 'GALAXYPremium.id',
    'Celestial Movies': 'CelestialMovies.id',
    'Indonesia Movie Channel': 'IMC.id', 'IMC': 'IMC.id',
    'Vision Prime': 'VisionPrime.id', 'VisionPrime': 'VisionPrime.id',
    'Entertainment': 'Ent.id', 'Food Travel': 'FoodTravel.id',
    'CelebritiesTV': 'CelebritiesTV.id', 'Celebrities TV': 'CelebritiesTV.id',
    'Hanacaraka TV': 'HanacarakaTV.id', 'HanacarakaTV': 'HanacarakaTV.id',
    'beIN Sports 1': 'beInSports1.id', 'beIN Sports 2': 'beInSports2.id',
    'beIN Sports 3': 'beInSports3.id',
    'Nickelodeon': 'Nickelodeon.id', 'Nick Jr': 'NickJr.id',
    'ZooMoo': 'ZooMoo.id', 'CBeebies': 'CBeebies.id',
    'DreamWorks': 'DreamWorks.id', 'Kids TV': 'KidsTV.id',
    'History': 'History.id', 'Thrill': 'Thrill.id',
    'Zee Bioskop': 'ZeeBioskop.id',
    'tvN Movies': 'tvNMovies.id', 'tvN': 'tvN.id',
    'CineEdge': 'CineEdge.id', 'Buddy Star': 'BuddyStar.id',
    'Muslim TV': 'MuslimTV.id', 'Al Quran': 'AlQuranKareem.id',
    'Tawaf TV': 'TawafTV.id', 'SPOTV': 'SPOTV.id', 'SPOTV 2': 'SPOTV2.id',
    'SpoTV': 'SPOTV.id', 'SpoTV 2': 'SPOTV2.id',
    'Lifetime': 'Lifetime.id', 'MTV 90s': 'MTV90s.id', 'MTV Live': 'MTVLive.id',
    'Music TV': 'MusicTV.id', 'Soccer Channel': 'SoccerChannel.id',
    'Fight Sports': 'FightSports.id', 'Outdoor Channel': 'OutdoorChannel.id',
    'Love Nature': 'LoveNature.id', 'Global Trekker': 'GlobalTrekker.id',
    'BBC Earth': 'BBCEarth.id', 'BBC News': 'BBCNews.id',
    'Crime Investigation': 'CrimeInvestigation.id', 'KIX': 'KIX.id',
    'ROCK Action': 'ROCKAction.id', 'ROCK Entertainment': 'ROCKEntertainment.id',
    'Jak TV': 'JakTV.id', 'CNA': 'CNA.id', 'Channel News Asia': 'CNA.id',
    'Al Jazeera English': 'AlJazeeraEnglish.id',
    'NHK World Japan': 'NHKWorldJapan.id', 'NHK World Premium': 'NHKWorldPremium.id',
    'CGTN': 'CGTN.id', 'CGTN Documentary': 'CGTNDocumentary.id',
    'DW English': 'DWEnglish.id', 'DW': 'DWEnglish.id',
    'France 24': 'France24English.id', 'Euronews': 'Euronews.id',
    'Bloomberg': 'BloombergTV.id', 'FOX News': 'FOXNews.id',
    'Uniques': 'Uniques.id', 'Originals': 'Originals.id', 'Superrix': 'Superrix.id',
    'LIFE': 'LIFE.id', 'CCM': 'CCM.id', 'Animax': 'Animax.id',
    'ONE': 'ONE.id', 'Arirang': 'Arirang.id',
    'Sportstars': 'Sportstars.id', 'Sportstars 2': 'Sportstars2.id',
    'Sportstars 3': 'Sportstars3.id', 'Sportstars 4': 'Sportstars4.id',
    'HGTV': 'HGTV.id',
    'CNN': 'CNN', 'BBC News': 'BBCNews',
    'Discovery Channel': 'DiscoveryChannel', 'Discovery': 'DiscoveryChannel',
    'Cartoon Network': 'CartoonNetwork', 'Animal Planet': 'Animal Planet',
    'Berita RTM': 'Berita RTM', 'TV1': 'TV1', 'TV2': 'TV2',
    'TV6': 'TV6', 'Okey': 'Okey',
    'Suria': 'Suria', 'Vasantham': 'Vasantham',
    'HBO': '401', 'HBO Hits': '402', 'HBO Family': '403',
    'HBO Signature': '401', 'Cinemax': '405',
}

def get_epg_id(name):
    clean = re.sub(r'\s*\(V\+\)\s*', '', name).strip()
    clean = re.sub(r'\s*\(ChannelFeed\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(DensTV\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(Dens TV\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(DENSTV\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(Channel Feed\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(VD\)\s*', '', clean).strip()
    clean = re.sub(r'\s*HD\s*$', '', clean).strip()
    clean = re.sub(r'^\s*,', '', clean).strip()
    if clean in channel_to_epg:
        return channel_to_epg[clean]
    for key, epg_id in channel_to_epg.items():
        if key.lower() == clean.lower():
            return epg_id
    for key, epg_id in channel_to_epg.items():
        if key.lower() in clean.lower() or clean.lower() in key.lower():
            return epg_id
    return None

source_traces = ['bluestraveller13', 'super-duper-spork', 'kitkatjoss']
http_keep = ['122.248.43.242', 'cdn6.163189.xyz', '45.64.97.211',
             'live.serverstreaming.net', 'stream.radiojar.com',
             '103.58.160.157', 'live-pv-ta.amazon']

with open(source_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

output = []
trace_removed = 0
dens_fixed = 0
http_fixed = 0
epg_fixed = 0

for line in lines:
    raw = line.rstrip('\n')

    if raw.startswith('#EXTM3U'):
        continue

    if raw.startswith('http') and any(pat in raw.lower() for pat in source_traces):
        trace_removed += 1
        continue

    if raw.startswith('http') and 'dens.tv' in raw:
        if raw.startswith('http://'):
            raw = raw.replace('http://', 'https://', 1)
            dens_fixed += 1
        raw = re.sub(r'\?app_type=web&userid=lite&chname=[^\s]+', '', raw)
        raw = re.sub(r'\?app_type=web&userid=lite', '', raw)

    if raw.startswith('http://') and not any(d in raw for d in http_keep):
        raw = raw.replace('http://', 'https://', 1)
        http_fixed += 1

    if raw.startswith('#EXTVLCOPT:http-referrer='):
        raw = raw.replace('http://dens.tv', 'https://www.dens.tv/')
        raw = raw.replace('https://dens.tv/', 'https://www.dens.tv/')

    if raw.startswith('#EXTINF'):
        raw = re.sub(r'\s*tvg-url="[^"]*"', '', raw)
        name_match = re.search(r',(.+?)$', raw.strip())
        if name_match:
            name = name_match.group(1).strip()
            epg_id = get_epg_id(name)
            if epg_id:
                raw = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{epg_id}"', raw)
                epg_fixed += 1

    output.append(raw)

# Add dens.tv referrer where missing
final = []
i = 0
while i < len(output):
    line = output[i]
    if line.startswith('#EXTINF'):
        j = i + 1
        has_dens_url = False
        has_dens_referrer = False
        while j < len(output):
            nl = output[j]
            if nl.startswith(('#EXTVLCOPT', '#KODIPROP', '#EXTGRP', '###')):
                if 'dens.tv' in nl and 'http-referrer' in nl:
                    has_dens_referrer = True
                j += 1
            elif nl.startswith('http') and 'dens.tv' in nl:
                has_dens_url = True
                break
            elif nl.startswith('http') or nl.strip() == '':
                break
            else:
                break
        if has_dens_url and not has_dens_referrer:
            final.append('#EXTVLCOPT:http-referrer=https://www.dens.tv/')
            final.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36')
    final.append(line)
    i += 1

with open(target_file, 'w', encoding='utf-8') as f:
    f.write(header_line + '\n\n')
    f.write('\n'.join(final) + '\n')

ch_count = sum(1 for l in final if l.startswith('#EXTINF'))
print(f"  Channel: {ch_count}")
print(f"  Source traces removed: {trace_removed}")
print(f"  dens.tv fixed: {dens_fixed}")
print(f"  HTTP→HTTPS: {http_fixed}")
print(f"  EPG tvg-id mapped: {epg_fixed}")
PYEOF

rm -f source_latest.m3u
AFTER=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
echo -e "  ${GREEN}Channel: $BEFORE → $AFTER${NC}"

# Step 5: Generate Custom EPG
echo -e "${YELLOW}[5/6] Generating custom EPG...${NC}"
EPG_BASE="https://raw.githubusercontent.com/AqFad2811/epg/refs/heads/main"

for f in indonesia.xml astro.xml singapore.xml rtmklik.xml unifitv.xml; do
    curl -sL "${EPG_BASE}/${f}" -o "${f}" 2>/dev/null || true
done

python3 << 'PYEOF'
import re, os
import xml.etree.ElementTree as ET

def get_tvg_ids(m3u_path):
    ids = set()
    with open(m3u_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m and m.group(1):
                ids.add(m.group(1))
    return ids

tvg_ids = get_tvg_ids("dhanytv.m3u")
all_ch = {}
all_prog = []

for src in ["indonesia.xml", "astro.xml", "singapore.xml", "rtmklik.xml", "unifitv.xml"]:
    if not os.path.exists(src):
        continue
    try:
        tree = ET.parse(src)
    except:
        continue
    root = tree.getroot()
    for ch in root.findall('channel'):
        cid = ch.get('id', '')
        if cid in tvg_ids and cid not in all_ch:
            all_ch[cid] = ch
    for prog in root.findall('programme'):
        if prog.get('channel', '') in all_ch:
            all_prog.append(prog)

new_root = ET.Element('tv')
new_root.set('generator-info-name', 'dhanytv-custom-epg')
new_root.set('generator-info-url', 'https://github.com/dhasap/dhanytv')
for cid in sorted(all_ch.keys()):
    new_root.append(all_ch[cid])
for prog in all_prog:
    new_root.append(prog)

new_tree = ET.ElementTree(new_root)
ET.indent(new_tree, space='  ')
new_tree.write('epg.xml', encoding='unicode', xml_declaration=True)

print(f"  EPG channels: {len(all_ch)}")
print(f"  EPG programmes: {len(all_prog)}")
print(f"  EPG size: {os.path.getsize('epg.xml') / 1024:.1f} KB")
PYEOF

rm -f indonesia.xml astro.xml singapore.xml rtmklik.xml unifitv.xml

# Step 6: Push
echo -e "${YELLOW}[6/6] Pushing to GitHub...${NC}"
if [ "$NO_PUSH" = true ]; then
    echo -e "${CYAN}Skipping push (--no-push)${NC}"
else
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}ERROR: Token diperlukan untuk push!${NC}"
        echo "Gunakan: $0 -t ghp_xxxxx"
    else
        git config user.name "dhanytv-updater"
        git config user.email "dhanytv-updater@users.noreply.github.com"
        git add "$TARGET_FILE" "$EPG_OUTPUT"
        CHANNEL_COUNT=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
        EPG_CHANNELS=$(grep -c '<channel ' "$EPG_OUTPUT" 2>/dev/null || echo "0")
        COMMIT_DATE=$(date -u '+%Y-%m-%d %H:%M UTC')
        git commit -m "manual-update: Playlist + EPG ($CHANNEL_COUNT ch, $EPG_CHANNELS EPG) - $COMMIT_DATE"
        git push "https://${TOKEN}@github.com/${REPO}.git" main
        echo -e "${GREEN}Push berhasil!${NC}"
    fi
fi

echo ""
echo -e "${GREEN}============================================"
echo "  Update Selesai!"
echo "============================================"
echo -e "  Channel  : $(grep -c '#EXTINF' dhanytv.m3u 2>/dev/null || echo 'N/A')"
echo -e "  EPG Ch   : $(grep -c '<channel ' epg.xml 2>/dev/null || echo 'N/A')"
echo -e "  EPG Size : $(du -h epg.xml 2>/dev/null | cut -f1 || echo 'N/A')"
echo -e "============================================${NC}"

# Cleanup
cd /
rm -rf "$WORK_DIR"
