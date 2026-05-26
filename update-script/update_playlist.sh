#!/bin/bash
# ============================================================
# dhanytv - Manual Update Script
# Playlist IPTV + Custom EPG Generator
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

# Step 3: Merge
echo -e "${YELLOW}[3/6] Merging playlist...${NC}"
HEADER_LINE=$(grep -m1 '^#EXTM3U.*url-tvg' "$TARGET_FILE" || grep -m1 '^#EXTM3U' "$TARGET_FILE")

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
    done < source_latest.m3u
} > "${TARGET_FILE}.new"

sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "${TARGET_FILE}.new"
echo "" >> "${TARGET_FILE}.new"
mv "${TARGET_FILE}.new" "$TARGET_FILE"
rm -f source_latest.m3u

# Step 4: Smart Cleanup & EPG Mapping
echo -e "${YELLOW}[4/6] Smart cleanup & EPG mapping...${NC}"
BEFORE=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")

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

# Remove channels without URLs
channels = [ch for ch in channels if ch['urls']]
print(f"  Channel tanpa URL dihapus: {total_before - len(channels)}")

# Dedup
def get_name(extinf):
    m = re.search(r',(.+?)$', extinf.strip())
    return re.sub(r'\s+', ' ', m.group(1).strip().lower()) if m else ''

seen = {}
deduped = []
for ch in channels:
    name = get_name(ch['extinf'])
    url = ch['urls'][0].strip() if ch['urls'] else ''
    key = (name, url)
    if key in seen:
        existing_idx = seen[key]
        if len(ch['props']) > len(deduped[existing_idx]['props']):
            deduped[existing_idx] = ch
    else:
        seen[key] = len(deduped)
        deduped.append(ch)
channels = deduped

# Fix dens.tv
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
print(f"  dens.tv URLs diperbaiki: {dens_fixed}")

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
    'IDX': 'IDX.id', 'TVRI': 'TVRI.id', 'BTV': 'BTV.id',
    'HITS': 'HITS.id', 'Hits': 'HITS.id',
    'HITS Movies': 'HitsMovies.id', 'HitsMovies': 'HitsMovies.id',
    'Studio Universal': 'StudioUniversal.id', 'AXN': 'AXN.id',
    'GALAXY': 'GALAXY.id', 'GALAXY Premium': 'GALAXYPremium.id',
    'Celestial Movies': 'CelestialMovies.id', 'IMC': 'IMC.id',
    'Vision Prime': 'VisionPrime.id',
    'Entertainment': 'Ent.id', 'Food Travel': 'FoodTravel.id',
    'Celebrities TV': 'CelebritiesTV.id', 'Hanacaraka TV': 'HanacarakaTV.id',
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
    'HBO': '401', 'HBO Hits': '402', 'HBO Family': '403',
    'HBO Signature': '401', 'Cinemax': '405',
}

def clean_name(name):
    clean = re.sub(r'\s*\(V\+\)\s*', '', name).strip()
    clean = re.sub(r'\s*\(ChannelFeed\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(DensTV\)\s*', '', clean).strip()
    clean = re.sub(r'\s*\(Channel Feed\)\s*', '', clean).strip()
    clean = re.sub(r'\s*HD\s*$', '', clean).strip()
    return clean

def get_epg_id(name):
    cn = clean_name(name)
    if cn in channel_to_epg:
        return channel_to_epg[cn]
    for key, epg_id in channel_to_epg.items():
        if key.lower() == cn.lower():
            return epg_id
    for key, epg_id in channel_to_epg.items():
        if key.lower() in cn.lower() or cn.lower() in key.lower():
            return epg_id
    return None

epg_fixed = 0
epg_removed = 0
for ch in channels:
    name_match = re.search(r',(.+?)$', ch['extinf'].strip())
    if not name_match:
        continue
    name = name_match.group(1).strip()
    epg_id = get_epg_id(name)
    old_tvg_id = re.search(r'tvg-id="([^"]*)"', ch['extinf'])
    old_id = old_tvg_id.group(1) if old_tvg_id else ''
    if epg_id:
        if old_id != epg_id:
            ch['extinf'] = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{epg_id}"', ch['extinf'])
            epg_fixed += 1
    else:
        if old_id:
            ch['extinf'] = re.sub(r'tvg-id="[^"]*"', 'tvg-id=""', ch['extinf'])
            epg_removed += 1

print(f"  EPG tvg-id diperbaiki: {epg_fixed}")
print(f"  EPG tvg-id dihapus: {epg_removed}")

# Remove tvg-url
tvg_url_removed = 0
for ch in channels:
    if 'tvg-url=' in ch['extinf']:
        ch['extinf'] = re.sub(r'\s*tvg-url="[^"]*"', '', ch['extinf'])
        tvg_url_removed += 1
print(f"  tvg-url dihapus: {tvg_url_removed}")

# Write
with open(target, 'w', encoding='utf-8') as f:
    if header:
        custom_epg_url = 'https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml'
        header = re.sub(r'url-tvg="[^"]*"', f'url-tvg="{custom_epg_url}"', header)
        f.write(header + '\n\n')
    for ch in channels:
        for prop in ch['props']:
            f.write(prop + '\n')
        f.write(ch['extinf'] + '\n')
        for url in ch['urls']:
            f.write(url + '\n')
        f.write('\n')

print(f"  Total: {total_before} -> {len(channels)}")
PYEOF

AFTER=$(grep -c '#EXTINF' "$TARGET_FILE" || echo "0")
echo -e "  ${GREEN}Channel: $BEFORE -> $AFTER${NC}"

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
