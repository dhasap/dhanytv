#!/usr/bin/env python3
"""Merge and sanitize a source M3U playlist into dhanytv.m3u.

Handles:
  - Source trace removal (sanitization patterns)
  - dens.tv http→https + query param cleanup
  - General http→https (with whitelist)
  - dens.tv referrer injection where missing
  - tvg-url removal from EXTINF
  - EPG tvg-id mapping (channel_to_epg dict)
  - dens.tv broken channel replacement (SCTV → Indihometv DASH)
  - EXTVLCOPT/KODIPROP prop deduplication

This replaces the inline Python that was previously duplicated in
update_playlist.sh and .github/workflows/auto-update.yml.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence

# ── EPG mapping ──────────────────────────────────────────────
CHANNEL_TO_EPG: dict[str, str] = {
    "RCTI": "RCTI.id", "MNC TV": "MNCTV.id", "MNCTV": "MNCTV.id",
    "GTV": "GTV.id", "Indosiar": "Indosiar.id", "SCTV": "SCTV.id",
    "TransTV": "TransTV.id", "Trans TV": "TransTV.id",
    "Trans7": "Trans7.id", "Trans 7": "Trans7.id",
    "MDTV": "MDTV.id", "iNews": "iNews.id",
    "Kompas TV": "KompasTV.id", "KompasTV": "KompasTV.id",
    "Metro TV": "MetroTV.id", "MetroTV": "MetroTV.id",
    "TVOne": "tvOne.id", "TV One": "tvOne.id", "tvOne": "tvOne.id",
    "SindoNews": "SindoNewsTV.id", "ANTV": "ANTV.id",
    "IDX": "IDX.id", "IDX Channel": "IDX.id",
    "TVRI": "TVRI.id", "BTV": "BTV.id",
    "CNN Indonesia": "CNNIndonesia.id",
    "CNBC Indonesia": "CNBCIndonesia.id",
    "DAAI TV": "DAAITV.id",
    "RTV": "RTV.id", "Nusantara TV": "NusantaraTV.id",
    "Garuda TV": "GarudaTV.id", "BN Channel": "BNChannel.id",
    "MAGNA Channel": "MagnaChannel.id",
    "HITS": "HITS.id", "Hits": "HITS.id",
    "HITS Movies": "HitsMovies.id", "HitsMovies": "HitsMovies.id",
    "Studio Universal": "StudioUniversal.id",
    "AXN": "AXN.id", "GALAXY": "GALAXY.id",
    "GALAXY Premium": "GALAXYPremium.id",
    "Celestial Movies": "CelestialMovies.id",
    "Indonesia Movie Channel": "IMC.id", "IMC": "IMC.id",
    "Vision Prime": "VisionPrime.id", "VisionPrime": "VisionPrime.id",
    "Entertainment": "Ent.id", "Food Travel": "FoodTravel.id",
    "CelebritiesTV": "CelebritiesTV.id", "Celebrities TV": "CelebritiesTV.id",
    "Hanacaraka TV": "HanacarakaTV.id", "HanacarakaTV": "HanacarakaTV.id",
    "beIN Sports 1": "beInSports1.id", "beIN Sports 2": "beInSports2.id",
    "beIN Sports 3": "beInSports3.id",
    "Nickelodeon": "Nickelodeon.id", "Nick Jr": "NickJr.id",
    "ZooMoo": "ZooMoo.id", "CBeebies": "CBeebies.id",
    "DreamWorks": "DreamWorks.id", "Kids TV": "KidsTV.id",
    "History": "History.id", "Thrill": "Thrill.id",
    "Zee Bioskop": "ZeeBioskop.id",
    "tvN Movies": "tvNMovies.id", "tvN": "tvN.id",
    "CineEdge": "CineEdge.id", "Buddy Star": "BuddyStar.id",
    "Muslim TV": "MuslimTV.id", "Al Quran": "AlQuranKareem.id",
    "Tawaf TV": "TawafTV.id", "SPOTV": "SPOTV.id", "SPOTV 2": "SPOTV2.id",
    "SpoTV": "SPOTV.id", "SpoTV 2": "SPOTV2.id",
    "Lifetime": "Lifetime.id", "MTV 90s": "MTV90s.id", "MTV Live": "MTVLive.id",
    "Music TV": "MusicTV.id", "Soccer Channel": "SoccerChannel.id",
    "Fight Sports": "FightSports.id", "Outdoor Channel": "OutdoorChannel.id",
    "Love Nature": "LoveNature.id", "Global Trekker": "GlobalTrekker.id",
    "BBC Earth": "BBCEarth.id", "BBC News": "BBCNews.id",
    "Crime Investigation": "CrimeInvestigation.id", "KIX": "KIX.id",
    "ROCK Action": "ROCKAction.id", "ROCK Entertainment": "ROCKEntertainment.id",
    "Jak TV": "JakTV.id", "JakTV": "JakTV.id",
    "CNA": "CNA.id", "Channel News Asia": "CNA.id",
    "Al Jazeera English": "AlJazeeraEnglish.id", "Al Jazeera": "AlJazeeraEnglish.id",
    "NHK World Japan": "NHKWorldJapan.id", "NHK World": "NHKWorldJapan.id",
    "NHK World Premium": "NHKWorldPremium.id",
    "CGTN": "CGTN.id", "CGTN Documentary": "CGTNDocumentary.id",
    "DW English": "DWEnglish.id", "DW": "DWEnglish.id",
    "France 24": "France24English.id",
    "Euronews": "Euronews.id", "Bloomberg": "BloombergTV.id",
    "FOX News": "FOXNews.id", "Uniques": "Uniques.id",
    "Originals": "Originals.id", "Superrix": "Superrix.id",
    "LIFE": "LIFE.id", "CCM": "CCM.id", "Animax": "Animax.id",
    "ONE": "ONE.id", "Arirang": "Arirang.id",
    "Sportstars": "Sportstars.id", "Sportstars 2": "Sportstars2.id",
    "Sportstars 3": "Sportstars3.id", "Sportstars 4": "Sportstars4.id",
    "HGTV": "HGTV.id",
    "CNN": "CNN", "BBC News": "BBCNews",
    "Discovery Channel": "DiscoveryChannel", "Discovery": "DiscoveryChannel",
    "Cartoon Network": "CartoonNetwork", "Animal Planet": "Animal Planet",
    "Berita RTM": "Berita RTM", "TV1": "TV1", "TV2": "TV2",
    "TV6": "TV6", "Okey": "Okey",
    "Suria": "Suria", "Vasantham": "Vasantham",
    "HBO": "401", "HBO Hits": "402", "HBO Family": "403",
    "HBO Signature": "401", "Cinemax": "405",
}

# Pre-build lowercase lookup for fast fuzzy matching
_EPG_LOWER: dict[str, str] = {k.lower(): v for k, v in CHANNEL_TO_EPG.items()}
_EPG_KEYS_LOWER: list[tuple[str, str]] = [(k.lower(), v) for k, v in CHANNEL_TO_EPG.items()]

# ── Compiled regexes ─────────────────────────────────────────
_RE_VPLUS = re.compile(r"\s*\(V\+\)\s*")
_RE_CHANNEL_FEED = re.compile(r"\s*\(ChannelFeed\)\s*")
_RE_DENSTV = re.compile(r"\s*\(DensTV\)\s*")
_RE_DENS_TV = re.compile(r"\s*\(Dens TV\)\s*")
_RE_DENSTV_UPPER = re.compile(r"\s*\(DENSTV\)\s*")
_RE_CHANNEL_FEED2 = re.compile(r"\s*\(Channel Feed\)\s*")
_RE_VD = re.compile(r"\s*\(VD\)\s*")
_RE_HD_SUFFIX = re.compile(r"\s*HD\s*$")
_RE_LEADING_COMMA = re.compile(r"^\s*,")
_RE_TVG_URL = re.compile(r'\s*tvg-url="[^"]*"')
_RE_TVG_ID = re.compile(r'tvg-id="([^"]*)"')
_RE_DENS_QUERY = re.compile(r"\?app_type=web&userid=lite&chname=[^\s]+")
_RE_DENS_QUERY2 = re.compile(r"\?app_type=web&userid=lite")

# ── Config ───────────────────────────────────────────────────
SOURCE_TRACES = ["bluestraveller13", "super-duper-spork", "kitkatjoss"]

HTTP_KEEP = frozenset([
    "122.248.43.242", "cdn6.163189.xyz", "45.64.97.211",
    "live.serverstreaming.net", "stream.radiojar.com",
    "103.58.160.157", "live-pv-ta.amazon",
])

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
)

DEFAULT_REFERRER = "https://www.dens.tv/"

# ── dens.tv replacement map ──────────────────────────────────
DENS_REPLACEMENTS: dict[str, dict] = {
    "h217": {  # SCTV
        "name": "SCTV",
        "props": [
            "#KODIPROP:inputstreamaddon=inputstream.adaptive",
            "#KODIPROP:inputstream.adaptive.manifest_type=dash",
            f"#EXTVLCOPT:http-user-agent={DEFAULT_UA.replace('97.0.4692.99', '139.0.0.0')}",
        ],
        "url": "https://cdnbal1.indihometv.com/atm/DASH/sctv/sctv-avc1_2500000=7-3277707030000000.mpd",
        "extinf_template": (
            '#EXTINF:-1 tvg-id="SCTV.id" '
            'tvg-logo="https://thumbor.prod.vidiocdn.com/kH-K9J4cROqL0TZrAyQhw7P5pBk=/230x230/'
            'filters:quality(70)/vidio-web-prod-livestreaming/uploads/livestreaming/square_image/204/4e9f5c.png" '
            'group-title="Indonesia Channels",SCTV'
        ),
    },
}


def get_epg_id(name: str) -> str | None:
    """Map channel display name to EPG tvg-id with cleaning + fuzzy matching."""
    clean = name
    for regex in (_RE_VPLUS, _RE_CHANNEL_FEED, _RE_DENSTV, _RE_DENS_TV,
                  _RE_DENSTV_UPPER, _RE_CHANNEL_FEED2, _RE_VD):
        clean = regex.sub(" ", clean)
    clean = _RE_HD_SUFFIX.sub(" ", clean)
    clean = _RE_LEADING_COMMA.sub("", clean).strip()

    # Exact match (case-insensitive)
    if clean in CHANNEL_TO_EPG:
        return CHANNEL_TO_EPG[clean]
    lower = clean.lower()
    if lower in _EPG_LOWER:
        return _EPG_LOWER[lower]

    # Substring match
    for key_lower, epg_id in _EPG_KEYS_LOWER:
        if key_lower in lower or lower in key_lower:
            return epg_id
    return None


def _is_trace_url(url: str) -> bool:
    low = url.lower()
    return any(pat in low for pat in SOURCE_TRACES)


def _fix_dens_url(raw: str) -> tuple[str, int]:
    """Fix dens.tv URLs: http→https, strip query params. Returns (fixed, changed)."""
    if "dens.tv" not in raw:
        return raw, 0
    changed = 0
    if raw.startswith("http://"):
        raw = raw.replace("http://", "https://", 1)
        changed = 1
    raw = _RE_DENS_QUERY.sub("", raw)
    raw = _RE_DENS_QUERY2.sub("", raw)
    return raw, changed


def _fix_http_url(raw: str) -> tuple[str, int]:
    """Convert http→https for URLs not in whitelist. Returns (fixed, changed)."""
    if not raw.startswith("http://"):
        return raw, 0
    if any(d in raw for d in HTTP_KEEP):
        return raw, 0
    return raw.replace("http://", "https://", 1), 1


def _fix_referrer_prop(raw: str) -> str:
    """Normalize dens.tv referrer in EXTVLCOPT lines."""
    raw = raw.replace("http://dens.tv", DEFAULT_REFERRER)
    raw = raw.replace("https://dens.tv/", DEFAULT_REFERRER)
    return raw


def _fix_extinf(raw: str) -> tuple[str, int]:
    """Remove tvg-url, fix tvg-id via EPG mapping. Returns (fixed, epg_mapped)."""
    raw = _RE_TVG_URL.sub("", raw)
    name_match = re.search(r",(.+?)$", raw.strip())
    if name_match:
        name = name_match.group(1).strip()
        epg_id = get_epg_id(name)
        if epg_id:
            raw = _RE_TVG_ID.sub(f'tvg-id="{epg_id}"', raw)
            return raw, 1
    return raw, 0


def _add_missing_referrers(lines: list[str]) -> list[str]:
    """Inject dens.tv referrer + user-agent where missing."""
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            j = i + 1
            has_dens_url = False
            has_dens_referrer = False
            while j < len(lines):
                nl = lines[j]
                if nl.startswith(("#EXTVLCOPT", "#KODIPROP", "#EXTGRP", "###")):
                    if "dens.tv" in nl and "http-referrer" in nl:
                        has_dens_referrer = True
                    j += 1
                elif nl.startswith("http") and "dens.tv" in nl:
                    has_dens_url = True
                    break
                elif nl.startswith("http") or nl.strip() == "":
                    break
                else:
                    break
            if has_dens_url and not has_dens_referrer:
                result.append(f"#EXTVLCOPT:http-referrer={DEFAULT_REFERRER}")
                result.append(f"#EXTVLCOPT:http-user-agent={DEFAULT_UA}")
        result.append(line)
        i += 1
    return result


def _replace_broken_dens(lines: list[str]) -> list[str]:
    """Replace known broken dens.tv channels with working alternatives."""
    replaced: list[str] = []
    new_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("http") and "dens.tv" in line:
            matched_key = None
            for key in DENS_REPLACEMENTS:
                if f"/{key}/" in line:
                    matched_key = key
                    break
            if matched_key:
                repl = DENS_REPLACEMENTS[matched_key]
                # Find the EXTM3U line for this entry (look backwards)
                extinf_idx = None
                for k in range(i - 1, max(i - 20, -1), -1):
                    if lines[k].startswith("#EXTINF"):
                        extinf_idx = k
                        break
                    if not lines[k].startswith("#") and not lines[k].startswith("http"):
                        break
                if extinf_idx is not None:
                    new_lines.append("")
                    for p in repl["props"]:
                        new_lines.append(p)
                    new_lines.append(repl["extinf_template"])
                    new_lines.append(repl["url"])
                    replaced.append(f"{repl['name']} (dens.tv -> Indihometv DASH)")
                    # Skip old entry lines
                    while i < len(lines) and not (
                        lines[i].startswith("#EXTINF")
                        or (
                            lines[i].startswith("#")
                            and not lines[i].startswith("#EXTVLCOPT")
                            and not lines[i].startswith("#KODIPROP")
                            and not lines[i].startswith("#EXTGRP")
                        )
                    ):
                        i += 1
                        if i < len(lines) and (lines[i].startswith("#EXTINF") or lines[i].strip() == ""):
                            break
                    continue
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        elif line.startswith(("#EXTINF", "#EXTVLCOPT", "#KODIPROP", "#EXTGRP")):
            # Check if next URL is a dens.tv replacement target
            is_before_replaced = False
            for k in range(i + 1, min(i + 15, len(lines))):
                if lines[k].startswith("http") and "dens.tv" in lines[k]:
                    for key in DENS_REPLACEMENTS:
                        if f"/{key}/" in lines[k]:
                            is_before_replaced = True
                            break
                    break
                if lines[k].startswith("#EXTINF") or (
                    not lines[k].startswith("#") and not lines[k].startswith("http")
                ):
                    break
            if not is_before_replaced:
                new_lines.append(line)
        else:
            new_lines.append(line)
        i += 1

    if replaced:
        for r in replaced:
            print(f"  dens.tv replaced: {r}")
    return new_lines


def _dedupe_props(lines: list[str]) -> list[str]:
    """Remove consecutive duplicate EXTVLCOPT/KODIPROP lines."""
    cleaned: list[str] = []
    prev_lines: set[str] = set()
    for line in lines:
        if line.startswith("#EXTVLCOPT") or line.startswith("#KODIPROP"):
            if line in prev_lines:
                continue
            prev_lines.add(line)
        else:
            prev_lines = set()
        cleaned.append(line)
    return cleaned


def merge(
    source_path: Path,
    target_path: Path,
    sanitize_patterns: Sequence[str] = (),
) -> dict[str, int]:
    """Merge source playlist into target, applying all sanitization.

    Returns stats dict with counts of changes made.
    """
    # Read existing header from target
    header_line = ""
    for line in target_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#EXTM3U"):
            header_line = line.rstrip("\n")
            break

    # Build trace patterns
    traces = list(SOURCE_TRACES)
    for p in sanitize_patterns:
        p = p.strip()
        if p:
            traces.append(p.lower())

    # Read source
    lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()

    stats = {
        "trace_removed": 0,
        "dens_fixed": 0,
        "http_fixed": 0,
        "epg_fixed": 0,
        "channels": 0,
    }

    # Phase 1: Line-by-line sanitization
    output: list[str] = []
    for raw_line in lines:
        raw = raw_line.rstrip("\n")

        # Skip source header (we use our own)
        if raw.startswith("#EXTM3U"):
            continue

        # Skip source trace URLs
        if raw.startswith("http") and any(pat in raw.lower() for pat in traces):
            stats["trace_removed"] += 1
            continue

        # Fix dens.tv URLs
        if raw.startswith("http") and "dens.tv" in raw:
            raw, changed = _fix_dens_url(raw)
            stats["dens_fixed"] += changed

        # Fix http→https (safe only)
        if raw.startswith("http://"):
            raw, changed = _fix_http_url(raw)
            stats["http_fixed"] += changed

        # Fix dens.tv referrer in props
        if raw.startswith("#EXTVLCOPT:http-referrer="):
            raw = _fix_referrer_prop(raw)

        # Fix EXTINF: EPG tvg-id + remove tvg-url
        if raw.startswith("#EXTINF"):
            raw, mapped = _fix_extinf(raw)
            stats["epg_fixed"] += mapped

        output.append(raw)

    # Phase 2: Add missing dens.tv referrers
    output = _add_missing_referrers(output)

    # Phase 3: Replace broken dens.tv channels
    output = _replace_broken_dens(output)

    # Phase 4: Deduplicate props
    output = _dedupe_props(output)

    # Write output
    stats["channels"] = sum(1 for l in output if l.startswith("#EXTINF"))
    target_path.write_text(
        header_line + "\n\n" + "\n".join(output) + "\n",
        encoding="utf-8",
    )

    return stats


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge source M3U into dhanytv with sanitization"
    )
    parser.add_argument("source", help="Source M3U file to merge from")
    parser.add_argument("--target", default="dhanytv.m3u", help="Target playlist (default: dhanytv.m3u)")
    parser.add_argument(
        "--sanitize",
        default="",
        help="Additional sanitize patterns, pipe-separated (e.g. 'pattern1|pattern2')",
    )
    args = parser.parse_args()

    patterns = args.sanitize.split("|") if args.sanitize else []
    stats = merge(Path(args.source), Path(args.target), sanitize_patterns=patterns)

    print("=== Merge summary ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
