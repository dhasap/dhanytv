#!/usr/bin/env python3
"""Merge and sanitize a source M3U playlist into dhanytv.m3u.

Handles:
  - Source trace removal (sanitization patterns)
  - dens.tv URL preservation (query params are required by some channels)
  - General http→https (with whitelist)
  - dens.tv referrer injection where missing
  - tvg-url removal from EXTINF
  - EPG tvg-id mapping (channel_to_epg dict)
  - guarded dens.tv broken channel replacement for legacy bare URLs only
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
_EPG_KEYS_LOWER: list[tuple[str, str]] = sorted(
    [(k.lower(), v) for k, v in CHANNEL_TO_EPG.items()],
    key=lambda x: -len(x[0]),  # longest keys first for matching
)
# Keys that are too short/generic for substring matching
_EPG_EXACT_ONLY: frozenset[str] = frozenset({
    "cnn", "tv", "tv1", "tv2", "tv6", "dw", "one", "hbo", "life",
})

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
_RE_TVG_URL_URL = re.compile(r'\s+tvg-url="(?:tvg-url=")?https?://[^"\s]+"*')
_RE_TVG_URL = re.compile(r'\s+tvg-url="[^"]*"')
_RE_TVG_ID = re.compile(r'tvg-id="([^"]*)"')
_RE_EMPTY_QUOTED_ATTR = re.compile(r'\s+""(?=\s|,)')
_RE_FIREFOX_UA_TYPO = re.compile(r'Firefox/(\d+(?:\.\d+)*)F\b')

# ── Config ───────────────────────────────────────────────────
# Source trace patterns are loaded at runtime from SANITIZE_PATTERNS
# secret — never hardcoded in source code.
SOURCE_TRACES: list[str] = []

HTTP_KEEP = frozenset([
    "122.248.43.242", "cdn6.163189.xyz", "45.64.97.211",
    "live.serverstreaming.net", "stream.radiojar.com",
    "103.58.160.157", "live-pv-ta.amazon",
    "202.80.222.20",  # Tvod: hanya layani http:// (https -> 000)
])

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
)

DEFAULT_REFERRER = "https://www.dens.tv/"

# ── ClearKey overrides (Widevine license servers yang mati) ──────────────
# Source menempelkan license URL Widevine pihak ketiga (bintangstreaming dll)
# yang 403. Clearkey berikut terverifikasi KID-nya cocok dengan manifest vidio.
CLEARKEY_OVERRIDES: dict[str, str] = {
    # TransTV / Trans7 (vidio CloudFront) — ClearKey overrides
    "7a69cfc9e135493f87ac4efd63000429": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "7b0404cd6a8a4a908123f10774854e46": "8ee7df15ff584967a3eb7b885bafc71e:9a297bf2200eee7dee21b9ace9f57c77",
}

# Widevine license server mapping: boti.my.id (poisoned) → bintangstreaming.my.id (correct)
# SOURCE_1 URL was tampered — keys replaced with fake boti.my.id URLs.
# This mapping restores the correct Widevine license server for each channel.
WIDEVINE_KEY_MAP: dict[str, str] = {
    "boti.my.id/saya.suka?id=1&": "bintangstreaming.my.id/rcti_pro/index.drm?id=1",   # RCTI
    "boti.my.id/saya.suka?id=2&": "bintangstreaming.my.id/rcti_pro/index.drm?id=2",   # MNCTV
    "boti.my.id/saya.suka?id=3&": "bintangstreaming.my.id/rcti_pro/index.drm?id=3",   # GTV
    "boti.my.id/saya.suka?id=6&": "bintangstreaming.my.id/rcti_pro/index.drm?id=6",   # TransTV
    "boti.my.id/saya.suka?id=7&": "bintangstreaming.my.id/rcti_pro/index.drm?id=7",   # Trans7
    "boti.my.id/saya.suka?id=23&": "bintangstreaming.my.id/rcti_pro/index.drm?id=23", # MDTV
    "boti.my.id/saya.suka?id=10&": "bintangstreaming.my.id/rcti_pro/index.drm?id=10", # ANTV
    "boti.my.id/saya.suka?id=4&": "bintangstreaming.my.id/rcti_pro/index.drm?id=4",   # iNews
    "boti.my.id/saya.suka?id=12&": "bintangstreaming.my.id/rcti_pro/index.drm?id=12", # TVOne
    "boti.my.id/saya.suka?id=5&": "bintangstreaming.my.id/rcti_pro/index.drm?id=5",   # SindoNews
    "boti.my.id/saya.suka?id=74&": "bintangstreaming.my.id/rcti_pro/index.drm?id=74", # ONE
    "boti.my.id/saya.suka?id=122&": "bintangstreaming.my.id/rcti_pro/index.drm?id=122",
    "boti.my.id/saya.suka?id=123&": "bintangstreaming.my.id/rcti_pro/index.drm?id=123",
    "boti.my.id/saya.suka?id=124&": "bintangstreaming.my.id/rcti_pro/index.drm?id=124",
    "boti.my.id/saya.suka?id=119&": "bintangstreaming.my.id/rcti_pro/index.drm?id=119",
    "boti.my.id/saya.suka?id=120&": "bintangstreaming.my.id/rcti_pro/index.drm?id=120",
    "boti.my.id/saya.suka?id=115&": "bintangstreaming.my.id/rcti_pro/index.drm?id=115",
    "boti.my.id/saya.suka?id=112&": "bintangstreaming.my.id/rcti_pro/index.drm?id=112",
    "boti.my.id/saya.suka?id=113&": "bintangstreaming.my.id/rcti_pro/index.drm?id=113",
    "boti.my.id/saya.suka?id=114&": "bintangstreaming.my.id/rcti_pro/index.drm?id=114",
    "boti.my.id/saya.suka?id=205&": "bintangstreaming.my.id/rcti_pro/index.drm?id=205",
    "boti.my.id/saya.suka?id=70&": "bintangstreaming.my.id/rcti_pro/index.drm?id=70",
}

# ── dens.tv replacement map ──────────────────────────────────
DENS_REPLACEMENTS: dict[str, dict] = {
    "h217": {  # SCTV
        "name": "SCTV",
        # Source query params are required by the dens.tv CDN. Only replace old
        # bare h217 URLs; keep exact source URLs such as
        # ?app_type=web&userid=lite&chname=SCTV.
        "replace_if_missing_query": True,
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

    # Word-boundary prefix match (longest keys checked first)
    # Strategy: only match if key covers the ENTIRE input (as prefix),
    # or the input covers the ENTIRE key (as prefix).
    # Single-word keys must not be a prefix of another key (ambiguity guard).
    for key_lower, epg_id in _EPG_KEYS_LOWER:
        if key_lower in _EPG_EXACT_ONLY:
            continue  # skip short/generic keys for fuzzy matching
        key_words = key_lower.split()
        input_words = lower.split()

        # Key is a prefix of the input
        # e.g. "bein sports 1" matches "bein sports 1 indonesia"
        # e.g. "tvri" matches "tvri nasional"
        # But "tv" does NOT match "tv2" (no space boundary)
        # But "al jazeera" does NOT match "al jazeera arabic" (ambiguous)
        if lower.startswith(key_lower) and (
            len(lower) == len(key_lower) or not lower[len(key_lower)].isalnum()
        ):
            # Skip if key is a prefix of another key (ambiguity guard)
            # e.g. "tv" is prefix of "tv one", "tvn" → skip
            # e.g. "al jazeera" is prefix of "al jazeera english" → skip
            # But "tvri" is NOT prefix of any other key → allow
            is_prefix_of_other = any(
                kl.startswith(key_lower) and kl != key_lower
                for kl, _ in _EPG_KEYS_LOWER
                if kl not in _EPG_EXACT_ONLY
            )
            if is_prefix_of_other:
                continue
            return epg_id

        # Input is a prefix of the key
        # e.g. "bbc news" matches "bbcnews" (no space variant)
        # But "bbc" alone should NOT match "bbc earth"
        if key_lower.startswith(lower) and (
            len(key_lower) == len(lower) or not key_lower[len(lower)].isalnum()
        ):
            # Single-word input must match single-word key exactly
            if len(input_words) == 1 and len(key_words) > 1:
                continue
            return epg_id
    return None


def _is_trace_url(url: str) -> bool:
    low = url.lower()
    return any(pat in low for pat in SOURCE_TRACES)


def _fix_dens_url(raw: str) -> tuple[str, int]:
    """Preserve dens.tv stream URLs exactly.

    dens.tv CDN query params (app_type/userid/chname) affect segment routing for
    some Indonesian users. Do not strip query params or force http→https here.
    """
    if "dens.tv" not in raw:
        return raw, 0
    return raw, 0


def _has_explicit_port(url: str) -> bool:
    """True when URL carries an explicit port other than :443."""
    m = re.search(r"://[^/]+:(\d+)(?:[/?|]|$)", url)
    return bool(m and m.group(1) != "443")


def _fix_http_url(raw: str) -> tuple[str, int]:
    """Convert http→https for URLs not in whitelist. Returns (fixed, changed).

    Never upgrades hosts on explicit non-443 ports (e.g. :80, :8080): most of
    those servers speak plain HTTP only, and forcing TLS breaks them entirely
    (confirmed dead: 013tv.com:8080, iptvtree.net:8080, dhoomtv.xyz:80).
    Staying on http is always safe — worst case the server also serves https.
    """
    if not raw.startswith("http://"):
        return raw, 0
    if any(d in raw for d in HTTP_KEEP):
        return raw, 0
    if _has_explicit_port(raw):
        return raw, 0
    return raw.replace("http://", "https://", 1), 1


def _fix_referrer_prop(raw: str) -> str:
    """Normalize dens.tv referrer in EXTVLCOPT lines."""
    raw = raw.replace("http://dens.tv", DEFAULT_REFERRER)
    raw = raw.replace("https://dens.tv/", DEFAULT_REFERRER)
    return raw


def _fix_extinf(raw: str) -> tuple[str, int]:
    """Remove tvg-url, fix tvg-id via EPG mapping. Returns (fixed, epg_mapped)."""
    raw = _RE_TVG_URL_URL.sub("", raw)
    raw = _RE_TVG_URL.sub("", raw)
    raw = _RE_EMPTY_QUOTED_ATTR.sub("", raw)
    name_match = re.search(r",(.+?)$", raw.strip())
    if name_match:
        name = name_match.group(1).strip()
        epg_id = get_epg_id(name)
        if epg_id:
            raw = _RE_TVG_ID.sub(f'tvg-id="{epg_id}"', raw)
            return raw, 1
    return raw, 0


def _add_missing_referrers(lines: list[str]) -> list[str]:
    """Inject dens.tv referrer + user-agent where missing.

    Scans both props BEFORE the EXTINF line (pending_props pattern)
    and props AFTER the EXTINF line for existing referrers.
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            # Check props BEFORE this EXTINF (in result list = pending_props)
            has_dens_referrer = False
            for k in range(len(result) - 1, max(len(result) - 15, -1), -1):
                prev = result[k]
                if prev.startswith("#EXTINF") or (not prev.startswith("#") and prev.strip()):
                    break
                if "dens.tv" in prev and "http-referrer" in prev:
                    has_dens_referrer = True

            # Check props AFTER this EXTINF and the URL
            j = i + 1
            has_dens_url = False
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
                if repl.get("replace_if_missing_query") and "?" in line:
                    new_lines.append(line)
                    i += 1
                    continue
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
                    for key, repl in DENS_REPLACEMENTS.items():
                        if f"/{key}/" in lines[k]:
                            is_before_replaced = not (
                                repl.get("replace_if_missing_query") and "?" in lines[k]
                            )
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


def _apply_clearkey_overrides(lines: list[str]) -> list[str]:
    """Replace dead Widevine license props with verified clearkeys."""
    out = list(lines)
    replaced = 0
    for frag, ck in CLEARKEY_OVERRIDES.items():
        url_idx = next((i for i, l in enumerate(out) if l.startswith("http") and frag in l), None)
        if url_idx is None:
            continue
        # walk backwards from the URL past all # comment lines to find the
        # license_type and license_key props belonging to this entry
        key_idx = None
        type_idx = None
        j = url_idx - 1
        while j >= 0:
            l = out[j]
            if not l.startswith("#") or "#EXTM3U" in l:
                break
            if "license_key=" in l:
                key_idx = j
            if "license_type=" in l:
                type_idx = j
            j -= 1
        if key_idx is None or type_idx is None:
            continue
        out[type_idx] = "#KODIPROP:inputstream.adaptive.license_type=org.w3.clearkey"
        out[key_idx] = f"#KODIPROP:inputstream.adaptive.license_key={ck}"
        replaced += 1
    if replaced:
        print(f"  clearkey overrides applied: {replaced}")
    return out



def _fix_poisoned_widevine_keys(lines: list[str]) -> list[str]:
    """Replace poisoned boti.my.id Widevine license keys with correct bintangstreaming keys.
    
    SOURCE_1 URL (Bluestraveller13/super-duper-spork) was tampered —
    all Widevine license_key URLs replaced with fake boti.my.id/saya.suka URLs.
    This function restores the correct license server for each channel.
    """
    import re as _re
    out = list(lines)
    fixed = 0
    for i, line in enumerate(out):
        if "boti.my.id" in line and "license_key=" in line:
            # Fix hhttps:// typo (double h prefix from poisoned source)
            if line.startswith("#KODIPROP:inputstream.adaptive.license_key=hhttps://"):
                line = line.replace("hhttps://", "https://", 1)
                out[i] = line
            # Replace entire license_key value: extract id number, build correct URL
            m = _re.search(r'license_key=https://boti\.my\.id/saya\.suka\?id=(\d+)', line)
            if m:
                channel_id = m.group(1)
                correct_key = f"https://bintangstreaming.my.id/rcti_pro/index.drm?id={channel_id}"
                line = _re.sub(
                    r'license_key=https://boti\.my\.id/saya\.suka\?id=\d+[^\s|"]*',
                    f'license_key={correct_key}',
                    line
                )
                out[i] = line
                fixed += 1
    if fixed:
        print(f"  poisoned widevine keys fixed: {fixed}")
    return out



def _correct_source_keys(lines: list[str]) -> None:
    """Correct ClearKey license_key values by matching channel names.
    
    Searches BOTH backwards and forwards from each EXTINF to find the
    associated license_key line, then replaces with the correct value.
    """
    print(f"  _correct_source_keys called, {len(lines)} lines")
    CORRECT_CLEARKEYS = {
    "&PICTURES HD": "de8045e9f0fb4d03845dcc4a8bd7712a:6807bd09bda34ada83152908192af6d6",
    "&TV HD": "67d18634ccb04875875c60fb8d9caaba:99a66471c09e4b8a8dc39a0de6803f75",
    "13 Bomb Di Jakarta": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "8TV Malaysia": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "ABC": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "ABC AUSTRALIA": "94f0b3d645c64f0dbe2e0990ec290cdf:0dc311915f9decffaf7dfee30c4d8482",
    "ABC Australia": "fbbccb9d1f9e402293b23dcf62322d83:63d828f9c104b74c1188a651ba39c812",
    "ABC Big Kids": "ab4a24725b1c47e7ae3c0f17ab020905:214f5979b5a30a0b3cda03085006a77f",
    "ABC Big Kids All Aussie": "47c13253f2ed45318e5b6e5d799c5956:38ddb989dfb05091db949ce404de52e5",
    "ABC Cartoons": "aec51cf82ef14226a097a4ff91b7b32e:652bcaec397fb789fa5138fd3461333c",
    "ABC Kids": "b70a4c3a102b47ec832d11da8a024161:8bd84110abda56e41511c16feaa2de69",
    "ABC Kids All Aussie": "5adc6dfdcbcf42638a64858190992fab:c036a7b9963ac34d89bbebe3ed071cc0",
    "ABC Kids Play Music": "ceeaf88efed649d898646d151439b6bd:e35e2727d4d8618247c1b2f223ed9cfa",
    "ABC Kids Play School": "593adcf2ed594c2ba2aeee9539b43f5c:b47e01622b87a37374dae5fb3645e4a8",
    "AFRICANEWS (VD)": "b5aaa8234c3544b78559537d5e5dd4e3:0521cdbcfb827d59a939381620096ea2",
    "AL QURAN KAREEM": "94f0b3d645c64f0dbe2e0990ec290cdf:0dc311915f9decffaf7dfee30c4d8482",
    "ALJAZEERA ENGLISH": "94f0b3d645c64f0dbe2e0990ec290cdf:0dc311915f9decffaf7dfee30c4d8482",
    "ALLPLAY ENT.": "3dd653fc7aa1e3075b7f0233620df68f:8573791fa55bff03a3094ff559fc1407&User-Agent=Mozilla/5.0 (Linux; Android 13; AndroidTV Build/V3.2025; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/136.0.7103.61 Mobile Safari/537.36",
    "ANTARA TV": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "ANTV": "8ee7df15ff584967a3eb7b885bafc71e:9a297bf2200eee7dee21b9ace9f57c77",
    "ANTV HD": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "APETITO": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "ARIRANG": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "ASTHA TV": "6224262601de437a81c99fdda7e2ea4a:7224fae0f679b70d22aca394a9084120",
    "ASTRO AWANI": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "ASTRO Badminton": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "ASTRO Football": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "ASTRO Premiere League": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "AT-X": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "AURA": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "AXN": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "AXN (IHT)": "2b095c9946d242cb9108e6a589a26072:8bc2cdfd0e86f7cfa935ef05978be229&User-Agent=referrer=https://www.visionplus.id/",
    "AXN (V+)": "2b095c9946d242cb9108e6a589a26072:8bc2cdfd0e86f7cfa935ef05978be229",
    "AXN (VS)": "d4126f7fd6134adfbedb3a0daefd7657:920f1adcca60069c887da7f1d225607d&User-Agent=referrer=https://www.visionplus.id/",
    "Agak Laen": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Al Jazeera Arabic": "8afcd53a12df4443ba4fba722a1771c8:b431e78b8bd1bcbbab3d06e22ac67afb",
    "Al Jazeera English": "1a1feb27e16048a59f39246a1321ea7e:979f770ca36fae07e287257bfa56bc4c",
    "Al Jazeera English (V+)": "d5c2df5b13c04708a89de814f5b73f8e:0a2678dca36ec3e46e223bb3aafdaf37",
    "Al Quran Al Kareem": "d856bf85229c4a42a7b0de45e4c91a31:5633e069ef585f73ccfe2dd6a85a6f48",
    "Algrafi": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Ali Topan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Alwan F1 FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 1 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 10 FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 2 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 3 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 4 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 5 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 6 HD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 6 SD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 7 FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 8 FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan Sport 9 FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan UFC FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Alwan WWE FHD": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Ancika": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Animax": "10bba49df37c42e78365a9995ca93f79:1d504b9bf2efa10d4d00058222b5020a&User-Agent=referrer=https://www.visionplus.id/",
    "Animax (V+)": "6f309276a94e45be89a8860159456e84:3fe2eec12885264556ca4e29aa6c0c40",
    "Animax (VS)": "ecc5bc0e2dec4b9495db147278fb3904:ca86d9fdad6a8e9b1c13368d734e2095&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Aniplus (IHT)": "6f309276a94e45be89a8860159456e84:3fe2eec12885264556ca4e29aa6c0c40&User-Agent=referrer=https://www.visionplus.id/",
    "Aniplus (ORG) (Beberapa Device Ga Support)": "f2c313fce55344e5a52389741d1f53f8:bae1e47db562b66895beb8fccdf2ad8a",
    "Aniplus (OSC)": "3dd653fc7aa1e3075b7f0233620df68f:8573791fa55bff03a3094ff559fc1407&User-Agent=Mozilla/5.0 (Linux; Android 13; AndroidTV Build/V3.2025; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/136.0.7103.61 Mobile Safari/537.36",
    "Antara TV": "87484c0b2a4c41b9b08249ef7817ad7f:ff4f3f232f747e5e7f616b4741fa5c32",
    "Ardan Radio Bandung": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Arirang (V+)": "d83df80b9af34e219404dea6bf7efd41:46dbfee377ea972b3e5914cbf6aa6122",
    "Asian Food Network": "367f9bf4d0684f109d74a9eeb68d32be:59983c58c1b0daa1dcc370f697ccaead",
    "Astro Awani": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Ayo Balikan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "BALI TV": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "BBC Earth (V+)": "5709bc59805c4f23b000306efea48438:1772cf06c2f5dd3980a3245cd31fd356",
    "BBC LIFESTYLE": "58b949986ed13294bc01b0f330abc527:23e8c5f2fe202906ac2d6554d9527299",
    "BBC NEWS": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "BBC Treasures": "a598d133e3ea508a29255f58e09758bf:ad64ce2c7864315dfd293f454f54bea0",
    "BBC World (V+)": "0e7c10b448444c53904de46d1a30f427:d638c2cb75ff93d38b5ec8b6f5098dea",
    "BERITA RTM": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "BERITASATU": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "BIOSKOP INDONESIA": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "BIZNET KIDS": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "BLOOMBERG": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "BN Channel": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "BN Channel (ChannelFeed)": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "BOOMERANG": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "BRTV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "BS Animax": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS Asahi": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS Fishing Vision": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS Fuji": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS NTV": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS TBS": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BS TV Tokyo": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "BTV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "BTV (V+)": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "BUDDY STAR (VS)": "3ffab3471a994535bdf7fc663792f08b:6e82876474df025c39ae804ba738ff17&User-Agent=referrer=https://www.visionplus.id/",
    "Baby Shark TV": "eabfbb7dd5ef461699c879b05941e18d:c2f7e8f9468def5266e01a4c646b76a6&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Bali TV": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "Bandung TV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "BanjarTV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "BantenTV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "BanyumasTV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Berita RTM": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Bioskop Indonesia": "a04c73e95eeb411dabcba8c35a5a58e8:3f9195dc468d3372f69c6bec5bfa75bb&User-Agent=referrer=https://www.visionplus.id/",
    "Bloomberg": "aed600d8f9c74267b03e7050bd442ffa:26065a2053d49dc3f07fd5d302eb4678",
    "Bloomberg (V+)": "e0d67e9e2641468d9daf3182c25bd40c:84663ccbdeba441f88c63d8573269fa1",
    "Boom TV": "601f58d4b7094d2baf78c85d1d9cb6c9:609e0cc03198455fa36fd2cc3e7f940d",
    "Boomerang Cartoon": "601f58d4b7094d2baf78c85d1d9cb6c9:609e0cc03198455fa36fd2cc3e7f940d",
    "Bu Tejo Sowan Jakarta": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Buddy Star (V+)": "2bfc3e059a9f4176b835a15c9a0c0dac:265c00f7fd825ad3e092b56081953b60",
    "Bungo TV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "CARTOON NETWORK (IHT)": "ec31647c5c3b490bbb5c840ca3e96c9e:a28271a4ba4d085efa1f7738e0f82ea1&User-Agent=referrer=https://www.visionplus.id/",
    "CARTOON NETWORK HD": "ab4a24725b1c47e7ae3c0f17ab020905:214f5979b5a30a0b3cda03085006a77f",
    "CARTOONITO": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "CBEEBIES BBC": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "CBS Champions": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "CBS Golazo Network": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "CBS Sports HQ": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "CCM (VS)": "cf861d26e7834166807c324d57df5119:64a81e30f6e5b7547e3516bbf8c647d0",
    "CCTV 4": "6224262601de437a81c99fdda7e2ea4a:7224fae0f679b70d22aca394a9084120",
    "CCTV4": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "CELEBRITIES TV (VS)": "2b095c9946d242cb9108e6a589a26072:8bc2cdfd0e86f7cfa935ef05978be229&User-Agent=referrer=https://www.visionplus.id/",
    "CGTN": "22dcc9a719a3411ca53b520236ded916:27425784e415cb5de6c857de6222b01b",
    "CGTN (V+)": "4c2c7834abd740669637bc4b029c9aee:2f7808671f1a6f63ebd86850d8d7cc5f",
    "CGTN DOC": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "CGTN DOCUMENTARY": "ab50469be8b740c699c6b2e2ce697447:94da89d6aefba50b779bf7aa2458a192",
    "CGTN DOCUMENTARY (V+)": "349ac1b8d5f2493d97ffd88d364de38c:92e769c36e60dcd8573c08fd9c27b9bf",
    "CHAMPIONS GOLF 1 HD": "c53012b08edf478187064665dde647cb:5390bb924b102d566b9e59afbdc08fab",
    "CHAMPIONS GOLF 2 HD": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "CHINA TRAVEL": "367f9bf4d0684f109d74a9eeb68d32be:59983c58c1b0daa1dcc370f697ccaead",
    "CINEEDGE (VS)": "5a6668f3a5d64338bce13307e5c570be:d0c76237c5ee38e7a420e9c83323023e&User-Agent=referrer=https://www.visionplus.id/",
    "CINEMAX (IHT)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "CITRA BIOSKOP": "be886ebe45024d4b80110269211b3adb:91b1858f34ece95c8377366fb87d99c4&User-Agent=referrer=https://www.visionplus.id/",
    "CITRA ENTERTAINMENT": "05cb4bbd91e34d858f6921e7196f7795:da3e19311e3a3d147607971a101c8dc3",
    "CNA": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "CNBC Asia (V+)": "f2ecb7420c48463c9c1eeb9a908825ed:2ddaa7bc8fcff832464ad874ab468c3f",
    "CNBC INDONESIA": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "CNBC Indonesia (ChannelFeed)": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "CNN INDONESIA": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "CNN Indonesia (ChannelFeed)": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "CNN Int HD": "1a1feb27e16048a59f39246a1321ea7e:979f770ca36fae07e287257bfa56bc4c",
    "CNN Japan": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Cartoon Network": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Cartoonito": "ab4a24725b1c47e7ae3c0f17ab020905:214f5979b5a30a0b3cda03085006a77f",
    "Caruban TV (1080p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "CarubanTV": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "Catholic TV": "b5aaa8234c3544b78559537d5e5dd4e3:0521cdbcfb827d59a939381620096ea2",
    "Cbeebies (V+)": "736777e5823249849d71a7d41ddc35aa:f831235372e07e24fb70f7336291c549",
    "Cek Ombak ( Lagi )": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "CelebritiesTV (V+)": "10bba49df37c42e78365a9995ca93f79:1d504b9bf2efa10d4d00058222b5020a",
    "Celestial Classic Movies (V+)": "974d4fb195224f66a2271de806e62018:0e92ec1a28d59da80161c3541c6eb8eb",
    "Celestial Movies": "12a34fccac944a19a14101a9009dae05:2d1543668411b31aec7269d889d4821c&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Celestial Movies (V+)": "de4a383599bb4ec4a24f8c61f2b9a3ba:5166677d7f6797bcf459cf7c8b66dcb9",
    "Channel 5": "cc3767ece98a4bdeb39b9ad6b7b8d2fe:769e78dc02d8f73811c97e0f9d5f12fe",
    "Channel 8": "560e2a97335148708010f6abc6e01ff9:004327cdad8609155073663a7e404df6",
    "Channel Jowo (DensTV)": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Channel News Asia": "8bf84ef1f79a4135bd20b7bb363ecb98:b15ad052e1d0e04f7b7bdf500fecd0e5",
    "Channel News Asia (V+)": "fb0dd5a64a3c45e086cb23f7f9649fbc:d68ee78a9b1703da869a983b57d95c60",
    "Channel U": "3769532992d643028eedc46cdde65929:03d5b8832a997377a032bc04c6d18add",
    "Cineedge (V+)": "c7b3852d9c84418f942923e41c31e633:ddb99755e0bebd98c92c7eab974bf161",
    "Cinemax": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "Citra Dangdut": "05cb4bbd91e34d858f6921e7196f7795:da3e19311e3a3d147607971a101c8dc3&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Citra Drama": "44a4c73921ea4f5f90eaaaf793d3f7cf:3be319093fec8a409fe0553128089671&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Citra Drama (OSC)": "eabfbb7dd5ef461699c879b05941e18d:c2f7e8f9468def5266e01a4c646b76a6&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Citra Entertainment": "94788bc937054090b216dc101e5fa5dc:297c97962ff8d9e99f1da178ea0083ec&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Citra Muslim": "f0bdfdef0f564819a2b43345b328f989:9f7555440fb310341ddb00cdbc638cea",
    "Crime Investigation (V+)": "ce73b28200934af786104ce175d0dc45:b3a7b83221ed0d8fe18b8fcf92b5861a",
    "DAAI TV (Dens)": "22bd0016090143f795a275629a6e7a0a:cae11accebe3ca7535141d35f4d41a1d",
    "DAZN RINGSIDE": "11223344556677889900112233445566:4b80724d0ef86bcb2c21f7999d67739d",
    "DEI KIDS": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "DGS 1": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "DGS 2": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "DGS 3": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "DGS 4": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "DISCOVERY CHANNEL": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "DISNEY Channel": "601f58d4b7094d2baf78c85d1d9cb6c9:609e0cc03198455fa36fd2cc3e7f940d",
    "DMI TV": "cf8d36bbfa904cb8a1c714dd74217cf2:97c0f4b08a496f8ab05e46f29a71c7c8",
    "DRAMA HEBAT": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "DRAMA HOTPOT": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "DREAMWORKS (FX)": "955574ee2b674f0fbbad818fb384c233:51d2893619bdd062fb4c0cdaafefbf27&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "DREAMWORKS (VS)": "f08c30b7ee114399b72e77b0c099244b:a33d496875d04510a9b3116ba51ae65d&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "DW (V+)": "44003e0bf3cc4cfa8a35cead51e34d42:a46e0bee874435aeb96fcac1177275a1",
    "DW ENGLISH": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "DZ PT 1": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DZ PT 2": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DZ PT 3": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DZ PT 4": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DZ PT 5": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DZ PT 6": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "DavikaTV Lampung": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "Demi Si Buah Hati": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Dens Food Channel (DensTV)": "c45d2c72ab7e41f7b368a3a09dacfd08:72d5dd7b3d92a23d81317a04ac25271a",
    "Dens Learning & Knowledge (DensTV)": "ce73b28200934af786104ce175d0dc45:b3a7b83221ed0d8fe18b8fcf92b5861a",
    "Dens Life & Style (DensTV)": "c45d2c72ab7e41f7b368a3a09dacfd08:72d5dd7b3d92a23d81317a04ac25271a",
    "Dens ShowBiz (DENSTV)": "c45d2c72ab7e41f7b368a3a09dacfd08:72d5dd7b3d92a23d81317a04ac25271a",
    "Dewan Negara": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Dhoho TV- Kediri": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Di Ambang Kematian": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Dinda": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Discovery Channel": "7800bfe7a7b4f5c983c9dc3c500b0357:2be6d286bb03f70e43e4019f9d7c1d34",
    "Discovery Kids": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Disney Channel": "be9caaa813c5305e761c66ac63645901:3d40f2990ec5362ca5be3a3c9bb8f8b4",
    "Disney Junior": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Dragon TV": "887d3f9e52b3432c8b1a79b1d44ab3fe:4ddc4cd97e7016485cb6d25bc2ba3cda",
    "Drama Hotpot": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Dreamworks HD (V+)": "ecd651d0872c46d6b75a902f3b796e6b:3915b032de12140475d2696ae734cf58",
    "Dunia Sinema": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "Dunia Sinema HD": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "EBS KIDS KR": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "ESPN 3": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "ESPN 4": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "ESPN 5": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "ESPN VIVO": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "ESPN VIVO 2": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "EWTN": "070756a16fd44081b6c2d64e40346b9e:d5fa9eaa7fd94f93d1b613d1ff0a5f91",
    "Elshinta TV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "Entertainment (V+)": "62f0fb29203c45419e2ea683c5c365e6:10b227a6ea7d65628f025e41318b927c",
    "Euronews (V+)": "79d66aca73d94db694964b1b3fb08533:71d8b26729d735d7d8b895e5d6a9bfcc",
    "F1 TV": "505616380de706936e493fdd1c25d0b6:5b313f49c63c682236eab3357400e216",
    "FANCODE TV 1": "c5e51f41ceac48709d0bdcd9c13a4d88:20b91609967e472c27040716ef6a8b9a",
    "FANCODE TV 2": "7e9239c1982d984a002df3ed049d0756:1b8a17598129a3618535c8fb05f103fe",
    "FASHION TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "FASHION TV 2": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "FIGHT SPORTS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "FILEM MANTAP": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "FITRAH": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "FLIK (IHT)": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd",
    "FOX News (V+)": "02a01b19989c4f6699b83aead96fff14:89ac6f2178c855ce6bf9e9b7e45eecbb",
    "FOX SPORTS 1": "8ce20e2a4b3dd04e0a6e5469b7cb47be:163c323b65d0597b13f037641fd67b1e",
    "FOX SPORTS 2": "2fbdaa3bea0d0323ae011b318d1db716:8726ef7eaf5b9dce15fb6aa9f80bd53f",
    "FOX SPORTS 3": "8836fb04d62dc64c9f8a39ef8640d5eb:d4f05ce56c5231b7cdf53455bea58621",
    "FOX SPORTS PREMIUM": "11c8c1c2ef0385cf1e64d44bb9c3a395:5769730ffbdc4b2fd8945929d9ace063",
    "FR: beIN Sports 3": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "FRANCE24": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "FUBO SPORTS 1": "dc69b6159a0f9f0a4e03b3ff91cbacd5:d0dcbcd7723bc40df0bf34c9c092d51f",
    "FUBO SPORTS 2": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
    "Fashion TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Fight Sports": "aa00f320f06247dcaf8e3cea1fb07f44:6169dd042bb5e59d709272b614011bbb",
    "Filem Mantap": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "First Lifestyle": "c45d2c72ab7e41f7b368a3a09dacfd08:72d5dd7b3d92a23d81317a04ac25271a",
    "Food Network": "6dc31ac1031242a8b0c37286acb66a37:648286167b494bf9ee122eced0e37de1",
    "Food Travel (V+)": "c263b43be6b94fb682b1d701e0aaf847:83491ecbe2968e91ed563ce2c41428dc",
    "Formosa": "04fb6c48c6b4498cb9d3b9ede0d48db7:94253cf1df2659c3ea253ba1091eca4d",
    "France 24 (V+)": "0750d198f4824ea7bbb82beede8f55d3:352108d6c83c5ea32c42b4f7465ad3ee",
    "GALAXY (VS)": "0d9539db24004da9ac36ea49a09e255c:30304533b5008ad7f33c25f225506bc0&User-Agent=referrer=https://www.visionplus.id/",
    "GALAXY PREMIUM (VS)": "1dc30f49888c4652897d9c998aa2cac1:8ccb6857157c1a01c5a47eb853f51aa2&User-Agent=referrer=https://www.visionplus.id/",
    "GAORA SPORTS": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "GTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Galaxy (V+)": "cfbae59795044563b5b9b4927a79a76e:ce57c9490bd772b390d78b9fedaf8d36",
    "Galaxy Premium (V+)": "0d9539db24004da9ac36ea49a09e255c:30304533b5008ad7f33c25f225506bc0",
    "Garuda TV (ChannelFeed)": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "Garuda TV HD": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "Global Trekker": "87ca873142174f2bbdcfadd878422c77:bb51816f7407f68830dcdc215416f385",
    "Global Trekker (V+)": "b826a2e05a5a4922b64019c17345a020:a532aa3aaf1b2f32daa66b4d165056c6",
    "HANACARAKA TV": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "HBO": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "HBO (IHT)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO (OSC)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO Boxing": "a4b2fe10c9d62d32220e8ea2dceda6f9:e6e1173c892f7fbd60a37a76a78935cb",
    "HBO FAMILY (IHT)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO FAMILY (OSC)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO Family": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "HBO HITS (IHT)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO HITS (OSC)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO Hits": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "HBO SIGNATURE (IHT)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO SIGNATURE (OSC)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "HBO Signature": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "HIP HIP HOREE!": "ab4a24725b1c47e7ae3c0f17ab020905:214f5979b5a30a0b3cda03085006a77f",
    "HISTORY US": "a598d133e3ea508a29255f58e09758bf:ad64ce2c7864315dfd293f454f54bea0",
    "HITS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "HITS (V+)": "17fb563c784848f09d8a1ea88a2fa989:1d0bd94eab5d5f56a950b784d9345439&User-Agent=referrer=https://www.visionplus.id/",
    "HITS MOVIES": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "HITS MOVIES (FX)": "07af9ce05d8f4960a1b9113e7fdb8e7e:12b66b374d9c804f7311cb6a8d421c8c&User-Agent=referrer=https://www.visionplustv.id/",
    "HITS MOVIES (V+)": "9e9d9ca2bb814de9bfd73d7c19bfe190:e8c178a885d1a1e042ca34ec5ea3b938&User-Agent=referrer=https://www.visionplustv.id/",
    "HOREE!": "780f283e8dd84dc195d93899ea9fcabe:59103ac45e9c5e411651e3fa26a2e6d9&User-Agent=referrer=https://www.visionplus.id/",
    "HUB PREMIER 1 (Server 1)": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 1 (Server 2)": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 11": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 3": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 4": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 5": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "HUB PREMIER 7": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hamka & Siti Raham Vol. 2": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Hanacaraka TV (V+)": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Hard Rock FM Bali": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Hard Rock FM Bandung": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Hard Rock FM Surabaya": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "History": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "History HD (V+)": "dc32fe8b8e0b4b849724d4a34e390c83:62a98c5670883a0a034df0c27b435a5e",
    "Hits (V+)": "9e9d9ca2bb814de9bfd73d7c19bfe190:e8c178a885d1a1e042ca34ec5ea3b938",
    "HitsMovies (V+)": "07af9ce05d8f4960a1b9113e7fdb8e7e:12b66b374d9c804f7311cb6a8d421c8c",
    "Home Crasher": "53ff5adf42d6c9bc1043248f17782efe:76252c668a94753e9a5a58c8e17880e3",
    "Hub Sports 1": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hub Sports 2": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hub Sports 3": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hub Sports 4": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hub Sports 5": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hub Sports 8": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Hunan TV": "3dd22058fcb94e3790660d256655663b:cacc2086a1ac693d6173084b942e751d",
    "IDX": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "IDX (V+)": "941717a97fe946069fd7ebc7afb48402:305d9297ec5797e7fd8aca03142b3b7e",
    "IMC (VS)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "INDOSIAR BRI Super LIG": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "INEWS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Imam Tanpa Makmum": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Indonesia Movie Channel (V+)": "a04c73e95eeb411dabcba8c35a5a58e8:3f9195dc468d3372f69c6bec5bfa75bb",
    "Indonesiana TV (ChannelFeed)": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "Indosiar": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "J SPORTS 1": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "J SPORTS 2": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "J SPORTS 3": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "J SPORTS 4": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "JAKTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "JAWAPOS TV": "6224262601de437a81c99fdda7e2ea4a:7224fae0f679b70d22aca394a9084120",
    "JAWAPOST TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "JITV Jogja": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "JOWO": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "JR.": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "JTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "JTV (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "JTV (V+)": "994121840707471a920b2e65bdf21b7e:0033ae3118a0153ad05fc9a066a8805c",
    "Jakarta Globe": "483c71dd36fd45dd965321e8c568ba42:719598f53c998c618adf76a8f4f17fd1&User-Agent=referrer=https://visionplus.id",
    "Jakarta GlobeNews Channel": "3fbf0d50c48a46bfbf287715296f17e5:b1e63bdfd4e89fc42ea41635ab2bc3a9",
    "Jawa Pos TV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "Jiangsu TV (V+)": "5ee5f4313ab54bce9f93cb166ea9d685:010f5ee14b27407c3691f73356ff32b1",
    "Jogja Istimewa TV (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Jogja TV": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "Jogja TV (720p) [Not 24/7]": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "K-DRAMA+": "be886ebe45024d4b80110269211b3adb:91b1858f34ece95c8377366fb87d99c4",
    "K-PLUS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "K-PLUS (IHT)": "be886ebe45024d4b80110269211b3adb:91b1858f34ece95c8377366fb87d99c4&User-Agent=referrer=https://www.visionplus.id/",
    "KARTOON CHANNEL": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "KIDS TV": "eabfbb7dd5ef461699c879b05941e18d:c2f7e8f9468def5266e01a4c646b76a6&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "KIDS TV STR": "ec31647c5c3b490bbb5c840ca3e96c9e:a28271a4ba4d085efa1f7738e0f82ea1&User-Agent=referrer=https://www.visionplus.id/",
    "KIDS ZONE PLUS Pakistan": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "KISI FM Bogor": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "KIX": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "KIX (IHT)": "be886ebe45024d4b80110269211b3adb:91b1858f34ece95c8377366fb87d99c4&User-Agent=referrer=https://www.visionplus.id/",
    "KIX (V+)": "85f74e4d84834605a4b01820091ea627:c2881a45f94ec6ecbec1303f4e3b1fd6",
    "KOMPAS TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Kansai TV": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Kawanua TV": "6224262601de437a81c99fdda7e2ea4a:7224fae0f679b70d22aca394a9084120",
    "Kawanua TV (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Kereta": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Kereta Berdarah": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Kids Staton TV": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Kids TV (V+)": "ec31647c5c3b490bbb5c840ca3e96c9e:a28271a4ba4d085efa1f7738e0f82ea1",
    "Kilisuci TV": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Kilisuci TV Kediri": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Kisah Tanah Jawa: Pocong Gundul": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Kompas TV": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "Kompas TV HD": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "Kutukan Sembilan Setan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Kuyang": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "LAWAK SENTRAL": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "LEAD": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "LIFE (V+)": "08e5cf90e8c04a7fa90f5c126768b239:b9406a99b9ea4b07149ecc582faf2613",
    "LIFETIME (Tanpa Sub IND)": "79698301a95740009531b1d53e3ad5fe:7240a4a29a54e6089b108fbcb95cb265",
    "Lawak Sentral": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Layangan Putus: The Movie": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Lifetime": "59de57168ce94a96bed1606f10c65f67:459fdec6262975e03adc82d62b749f44",
    "Lingkar TV": "9cf20a8618854bb8bf3b7891c6cb5606:7284d5c76c7f913632c715f3d5c5aa8a",
    "LingkarTV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Losmen Melati": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Love Nature (V+)": "6c4190749d6f4b51bde2df71715e843b:9dfc9803c0fdbb1cd6df2188a6f29064",
    "MAGNA Channel": "47d8c564b0eb4d6ba83f7b155c827024:098f10e1734d00c0177bae1236db60fc",
    "MAX EATS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MAX KIDS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MAX REELS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MAX SPORT": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MAX STREAK": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MAXSTREAM": "10bba49df37c42e78365a9995ca93f79:1d504b9bf2efa10d4d00058222b5020a&User-Agent=referrer=https://www.visionplus.id/",
    "MBS": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "MDTV": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "MENTARI TV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "MENTARI TV HD": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "MN+": "40f019b86241d23ef075633fd7f1e927:058dec845bd340178a388edd104a015e",
    "MNCTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MNX HD": "40f019b86241d23ef075633fd7f1e927:058dec845bd340178a388edd104a015e",
    "MOJI Pro Liga": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "MOJI TV (Dens)": "22bd0016090143f795a275629a6e7a0a:cae11accebe3ca7535141d35f4d41a1d",
    "MOJI TV (V+)": "22bd0016090143f795a275629a6e7a0a:cae11accebe3ca7535141d35f4d41a1d",
    "MOJI TV (Video)": "22bd0016090143f795a275629a6e7a0a:cae11accebe3ca7535141d35f4d41a1d",
    "MOJITV": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "MOONBUG (AMG)": "8b62ae389f0944d4a55daaad52de1f9d:ba145a1426491316010da87bfd69de05&User-Agent=referrer=https://www.visionplus.id/",
    "MOONBUG (VS)": "c1d5f77cd96049f78b6b253540b31722:ba8d0801fe81187d35633e1d3b3855d5&User-Agent=referrer=https://www.visionplus.id/",
    "MOTORVISION+": "aa00f320f06247dcaf8e3cea1fb07f44:6169dd042bb5e59d709272b614011bbb",
    "MQTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MTATV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MTV  japan": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "MUITV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "MUSICA": "55d8bf610e3142408ecfa5295d7eba39:0774f3ae6ea32f9b4c24896f1fb5bb40",
    "MY KIDZ": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Magna Channel": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "Malam Para Jahanam": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Max Kids": "2bfc3e059a9f4176b835a15c9a0c0dac:265c00f7fd825ad3e092b56081953b60",
    "Max Reels": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Melukis Luka": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Mentari TV": "ecd651d0872c46d6b75a902f3b796e6b:3915b032de12140475d2696ae734cf58",
    "Mentari TV FHD": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Metro TV": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "MetroTV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "Miramax Film": "5e08a6933238d3fb585c00a7d95e896c:2d55d1208eaeabcc57e3b7b92c4e9f09",
    "Mohon Doa Restu": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Monster": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Moonbug (V+)": "8b62ae389f0944d4a55daaad52de1f9d:ba145a1426491316010da87bfd69de05",
    "MotoGP Channel": "e03f302ec4dabcccca82cc9f76731ec9:53ea1027d2bf2893a552cf15bc0366de",
    "Movies Now": "40f019b86241d23ef075633fd7f1e927:058dec845bd340178a388edd104a015e",
    "Mukidi": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Music Information Channel (720p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Music JapanTV": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Musik TV": "55d8bf610e3142408ecfa5295d7eba39:0774f3ae6ea32f9b4c24896f1fb5bb40",
    "Muslim TV": "c2e6de6943ef47d08c2634a2df4bcece:badf619476b3bf0889ab545e8d3926f6",
    "My KIDZ": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "MyKidz": "ecd651d0872c46d6b75a902f3b796e6b:3915b032de12140475d2696ae734cf58",
    "NBA PHILIPPINES": "11223344556677889900112233445566:4b80724d0ef86bcb2c21f7999d67739d",
    "NBA TV": "c5e51f41ceac48709d0bdcd9c13a4d88:20b91609967e472c27040716ef6a8b9a",
    "NEW KFOOD": "367f9bf4d0684f109d74a9eeb68d32be:59983c58c1b0daa1dcc370f697ccaead",
    "NEW KMOVIES": "be886ebe45024d4b80110269211b3adb:91b1858f34ece95c8377366fb87d99c4",
    "NEW TV COMPREHENSIVE": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "NEW TV FINANCE": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "NEW TV VARIETY": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "NHK BS Premium 4K": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "NHK BS1": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "NHK G Osaka": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "NHK WORLD JAPAN": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "NHK World Japan (Channel Feed)": "989c2b64799145f3bbf19fade7f20380:6eb7e7a29e6e633a82a2af4449b93535",
    "NHK World Japan (V+)": "989c2b64799145f3bbf19fade7f20380:6eb7e7a29e6e633a82a2af4449b93535",
    "NHK World Premium": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "NHK World Premium (V+)": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f",
    "NICK": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "NICK JR (FX)": "676b60c2b84b49b6b316207a590203e4:da9878a96062ea105895f310e052fa7b&User-Agent=referrer=https://www.visionplus.id/",
    "NICK JR (VS)": "928de1d7673c4fdd8ff22287fbec3c14:3955eb1e2dd8ac29a778bc572dd64794&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "NUSANTARA TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "Nagaswara FM": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Nat Geo Sharks": "7800bfe7a7b4f5c983c9dc3c500b0357:2be6d286bb03f70e43e4019f9d7c1d34",
    "Natgeo Japan": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Nickelodeon (FX)": "ecd651d0872c46d6b75a902f3b796e6b:3915b032de12140475d2696ae734cf58&User-Agent=referrer=https://www.visionplus.id/",
    "Nickelodeon (V+)": "676b60c2b84b49b6b316207a590203e4:da9878a96062ea105895f310e052fa7b",
    "Nickelodeon (VS)": "ef4d19eafa0d4dcbb6a247e13753caab:a693256564fea641b5c4fc59adbdcf10&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Nickelodeon Junior (V+)": "c1d5f77cd96049f78b6b253540b31722:ba8d0801fe81187d35633e1d3b3855d5",
    "Nusantara TV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "Nusantara TV (ChannelFeed)": "87484c0b2a4c41b9b08249ef7817ad7f:ff4f3f232f747e5e7f616b4741fa5c32",
    "OH MY CERIA!": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "ONE (FX)": "844db5a3a7ff4339b22f93811b004148:de946a52bd1df1d8a9e6510b1e0b3576&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "ONE (V+)": "2e8cbd6f664b4ace966d3edfad94c18e:cff33777777f7e61078ae2ae41ed0636",
    "ONE (VS)": "a7e68d7c2667465f976361eb0d6bd0c1:32a856d04efbf93cee7b2c97643d7998&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "ONE SPORTS HD": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "ONE SPORTS+": "53c3bf2eba574f639aa21f2d4409ff11:3de28411cf08a64ea935b9578f6d0edd",
    "ORIGINALS (V+)": "33333f38930949b1af65b3361ad80d1d:b159847f9af0500738b01e91cf023e30",
    "ORIGINALS (VS)": "de4a383599bb4ec4a24f8c61f2b9a3ba:5166677d7f6797bcf459cf7c8b66dcb9&User-Agent=referrer=https://www.visionplus.id/",
    "OZ Radio FM": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Oh My Ceria!": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Outdoor Channel (V+)": "7efd32eb4765465c8a19aba6987770c8:733e8d3f4fb8f7ae021168d92f922645",
    "PBS Kids": "601f58d4b7094d2baf78c85d1d9cb6c9:609e0cc03198455fa36fd2cc3e7f940d",
    "PHOENIX CHINESE": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "PHOENIX INFONEWS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "PKTV (480p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "PLANET FUN": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "PONTV (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "PRAMBORS TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "PREMIER SPORTS": "322d06e9326f4753a7ec0908030c13d8:1e3e0ca32d421fbfec86feced0efefda",
    "Padang TV (720p) [Not 24/7]": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Pasutri Gaje": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Pemandi Jenazah": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Pemukiman Setan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Perjalanan Pembuktian Cinta": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Petualangan Sherina 2": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Prambors": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Prima Sport 1": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "Prima Sport 2": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "Prima Sport 3": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "Prima Sport 4": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "Prima Sport 5": "902e5ec0e3d05e665daa32fc23f4f59e:7b2322a273843921a43e2c61dac7cae3",
    "QA: beIN Sports Xtra 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "QVC JAPAN": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "RAI Italia": "b02e6c916cc9453fa23a6a71da29fbff:5459f15c2c1190d95fe4976ec69ae875",
    "RCTI": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "RCTI SPORTS": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "RCTV (576p) [Not 24/7]": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "ROCK ACTION": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "ROCK ACTION (IHT)": "d4126f7fd6134adfbedb3a0daefd7657:920f1adcca60069c887da7f1d225607d&User-Agent=referrer=https://www.visionplus.id/",
    "ROCK ACTION (VS)": "cfbae59795044563b5b9b4927a79a76e:ce57c9490bd772b390d78b9fedaf8d36&User-Agent=referrer=https://www.visionplus.id/",
    "ROCK ENTERTAINMENT": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "RODJA TV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "ROLL": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "ROMEDY NOW": "40f019b86241d23ef075633fd7f1e927:058dec845bd340178a388edd104a015e",
    "RT ENGLISH": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "RTB Aneka": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "RTB Aneka FHD": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "RTB Go Live": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "RTB Go Live FHD": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "RTB Sukmaindera": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "RTB Sukmaindera FHD": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "RTM ASEAN": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "RTM Asean": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "RTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "RTV (Dens)": "87484c0b2a4c41b9b08249ef7817ad7f:ff4f3f232f747e5e7f616b4741fa5c32",
    "RTV (V+)": "87484c0b2a4c41b9b08249ef7817ad7f:ff4f3f232f747e5e7f616b4741fa5c32",
    "RTV (Vidio)": "87484c0b2a4c41b9b08249ef7817ad7f:ff4f3f232f747e5e7f616b4741fa5c32",
    "Radar Tasikmalaya TV (720p) [Not 24/7]": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Reformed21 (V+)": "729e39db83984d58a23e16f2c05f915f:0d3871bf01b6d871c9882265fb78e8fa",
    "Riau TV (1080p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Ritual Tumbal Terakhir": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Rock Action (V+)": "d4126f7fd6134adfbedb3a0daefd7657:920f1adcca60069c887da7f1d225607d",
    "Rock Entertainment (V+)": "a44cd51b688a458d97f534c286e58243:d62302543075463e472e23d7e947f10b",
    "Russia Today (V+)": "b5aaa8234c3544b78559537d5e5dd4e3:0521cdbcfb827d59a939381620096ea2",
    "SCTV": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "SET (V+)": "04fb6c48c6b4498cb9d3b9ede0d48db7:94253cf1df2659c3ea253ba1091eca4d",
    "SHOP CHANNEL": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "SIN PO TV": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "SINDONEWS": "16ce4fb658cf41678c72cca871770da3:95509b2ad660b196310e93a0388a8a6b",
    "SKY SPORTS BUNDESLIGA": "c88dc6c668cac3b468d4a4c7e176ff3d:1aeb739de2c14ed0ad658ca8043208d8",
    "SKY SPORTS LALIGA": "9f327d24c66fbd84e15ab5c9ead7c7a4:83837185529c0c4048f81386c2d36426",
    "SLOVAKIA: Nova Sport 1": "cbb673fb120882354735ed57eeb05b4c:fe003f7aeec40eb65d20b14edfda2a86",
    "SLOVAKIA: Nova Sport 2": "11223344556677889900112233445566:4b80724d0ef86bcb2c21f7999d67739d",
    "SLOVAKIA: SPORT 1": "11223344556677889900112233445566:4b80724d0ef86bcb2c21f7999d67739d",
    "SLOVAKIA: SPORT 2": "11223344556677889900112233445566:4b80724d0ef86bcb2c21f7999d67739d",
    "SMTV (720p) [Not 24/7]": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "SNAP": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "SONY TEN 1 ᴴᴰ": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "SONY TEN 2 ᴴᴰ": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "SONY TEN 3 ᴴᴰ": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "SONY TEN 5 ᴴᴰ": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "SPACETOON ARAB": "0a3aaee779e940db8ff24f9f3eb5c98a:440e1c1ce9ba337844409c8bcad5a268&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "SPORTSTARS 3": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "STUDIO UNIVERSAL (V+)": "b4a7b3289eff493d8700becf2e2a1157:bfbcfcb8137dd565a7f4b5ce7800c1f0",
    "STUDIO UNIVERSAL (VS)": "c7b3852d9c84418f942923e41c31e633:ddb99755e0bebd98c92c7eab974bf161&User-Agent=referrer=https://www.visionplus.id/",
    "SUKAN RTM (X1)": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "SUKAN RTM (X2)": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "SUN TV": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "SUPERRIX (V+)": "1dc30f49888c4652897d9c998aa2cac1:8ccb6857157c1a01c5a47eb853f51aa2",
    "SUPERRIX (VS)": "2bfc3e059a9f4176b835a15c9a0c0dac:265c00f7fd825ad3e092b56081953b60&User-Agent=referrer=https://www.visionplus.id/",
    "Salam HD": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "Salira TV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Sampit TV": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Sangaji TV (720p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Sanlih": "04fb6c48c6b4498cb9d3b9ede0d48db7:94253cf1df2659c3ea253ba1091eca4d",
    "Saranjana: Kota Ghaib": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Sehidup Semati": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Selangor TV": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Sewu Dino": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Shenzen TV": "a51cbbc384a949f491c3e5a0bd8c7103:4db32e0ff4147db3d833fdcc1d3e123f",
    "Siksa Neraka": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Sinden Gaib": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Sindo News": "eab667a8f7f14ff7bf00d790314a10f0:1d6693bc942f036053fc1c3c3b3b5032",
    "SindoNews": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "Sky A": "2f699274d40f479d89804912c134830d:352d8c910649b4d332047cf2833bb43f&User-Agent=referrer=https://www.visionplus.id/",
    "Sky Sport F1": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "Sky Sport Racing": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportBundesliga": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportF1": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportMotoGP": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportsFootball": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportsLaliga": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "SkySportsPremiereLeague": "d8d5823d92a9ef9306a4cc4bd634b4b4:df9fbdaa0ef9e905b75f4692f213af19",
    "Smooth FM Jakarta": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Soccer Channel": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "SpoTV": "3197f7f5086c4315af2b7a94bc9201cb:17462a74739ae0d9855705ffc2c0e1b5",
    "SpoTV (V+)": "385ceb9714b75e0cef61254f80b31002:18dce92a2891fee68d21ede5173230f8",
    "SpoTV 1 PH": "1539f043249e413d91906036f305831e:671e24fd8d234c7f38d85055815f902a",
    "SpoTV 2": "1539f043249e413d91906036f305831e:671e24fd8d234c7f38d85055815f902a",
    "SpoTV 2 (V+)": "385ceb9714b75e0cef61254f80b31002:18dce92a2891fee68d21ede5173230f8",
    "SpoTV 2 PH": "ec7ee27d83764e4b845c48cca31c8eef:9c0e4191203fccb0fde34ee29999129e",
    "SportTV 1": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98&User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "SportTV 2": "eaea45512d137def15b209a089cafd14:8d42db746ed0c4df61729b0d68d42bd7",
    "SportTV 3": "9009b7189e3e68cc09d17811f2beb55a:dd3f96a94c909da48ff40c92aabf8cf3",
    "Sportstars 2ᴴᴰ": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "Sportstars 4": "ac900f4053fa420095fb84f491f7a331:59748725964ff275e524af73792c8ad4",
    "Sportstars 4 ᴴᴰ": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "Sportstarsᴴᴰ": "b2fbd6358a344dcba331c7c91742cd34:ee183e1a1b971b5a2f764c192ae52087",
    "Star Channel 1": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Stara TV (720p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Stara TV Bandung (1080p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Stara TV Cianjur (720p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "Stara TV Malang (1080p)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "StaraTV Cianjur": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "StaraTV Malang": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "StaraTV Sumedang": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Suara Surabaya FM": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Sujud Terakhir Bapak": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Surga Di Bawah Langit": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Suria": "ee8f2493cd55453d917222c1a85212fd:07f5c76b976657fbdcc2085861f649bd",
    "TAPMOVIES HD": "71cbdf02b595468bb77398222e1ade09:c3f2aa420b8908ab8761571c01899460",
    "TENNIS 2 FHD": "59f50679c9e60963bd0cb6640992aaaa:8685817c4d31f322e08940feeae2855a",
    "THRILL": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "THRILL (IHT)": "17fb563c784848f09d8a1ea88a2fa989:1d0bd94eab5d5f56a950b784d9345439&User-Agent=referrer=https://www.visionplus.id/",
    "THRILL (VS)": "b4a7b3289eff493d8700becf2e2a1157:bfbcfcb8137dd565a7f4b5ce7800c1f0&User-Agent=referrer=https://www.visionplus.id/",
    "TLC HD": "abac9e0bf2b448f8871145829c68a7fd:eebd1a86367df6c2c4aad70b7a6165a9",
    "TNT SPORTS 1": "e03f302ec4dabcccca82cc9f76731ec9:53ea1027d2bf2893a552cf15bc0366de",
    "TNT SPORTS 2": "69a5aa835a061ce64a630d1046727e40:d02feac8a999bd06bf4059bf33411749",
    "TOKYO MX1": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "TRANS 7 TV": "a898c1af1a76498788cb616d39e551a6:f4c0c13bb1b84004b32ae4e9042d1571",
    "TRAVEL & TASTE": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "TREEHOUSE": "6f0aeae5779f1dcaef23f0bfbc828220:7bcef3cf93de00e3daeb190d15b1ec05&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TRT World (V+)": "e4b5eab488e149e68f3e421615ffd0d2:2556a421a56e53ab9b6ccefdf464581e",
    "TSN 1": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
    "TSN 2": "7e99f734748d098cbfa2f7bde968dd44:98ea6088c3222e9abaf61e537804d6cc",
    "TSN 3": "362202eefc5d9e42eec6450998cce9e8:978dfdd53186ec587d940e0bd1e2ec42",
    "TSN 4": "d9097a1b7d04b7786b29f2b0e155316d:279695ebe0fb1bc5787422b6b59ce8a8",
    "TSN 5": "e1aa4c4daf6222a04f7ae80130495ea1:31bb1ee9a8d088f62b0103550c301449",
    "TSN SPORTS 1": "14eeabf30c14b7fbf3008c03099ce011:17d2ac8dbc5429bd70af3433aa12158d",
    "TSN SPORTS 2": "85b277daf5aae05833fe43a68f587968:d52d7e9bc0bcd98787efd547ac91eca0",
    "TSN SPORTS 3": "d3250252765347a0c2603c6cb4869f8c:0c19319460da7e9ed816db46ce839b37",
    "TSN SPORTS 4": "abc5b2883121012850ebda05b528c5ec:e5250924f4b738905f7163a0134587a7",
    "TSN SPORTS 5": "385ceb9714b75e0cef61254f80b31002:18dce92a2891fee68d21ede5173230f8",
    "TV 1": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "TV 2": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "TV 3": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "TV 6": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "TV Ikim": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "TV OKEY": "1cd0f33db5a826c850e0ef6ca9331a82:207f3ac36c8d5c85395c147154d41581",
    "TV Okey": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "TV Osaka": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "TV Tabalong": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "TV1": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "TV2": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "TV2000": "b5aaa8234c3544b78559537d5e5dd4e3:0521cdbcfb827d59a939381620096ea2",
    "TV5 MONDE ASIE": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TV5 Monde": "11d67d0e8b2a455a8358d3d3a23e7529:d5308e3b12a529c959beab1cddacdec4",
    "TV5 Monde (V+)": "8e1901f646584b92af0a1a4406ffce23:7d1ca6e0f4f0d3d1a57c74204e273d6c",
    "TV6": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "TV9": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TV9 NU": "730bf9b6641f4ca597fd0d2903ffc574:293446fd53697862b165984b860fd7b0",
    "TVBS NEWS": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TVMU": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TVMu": "94f0b3d645c64f0dbe2e0990ec290cdf:0dc311915f9decffaf7dfee30c4d8482",
    "TVN (FX)": "2e8cbd6f664b4ace966d3edfad94c18e:cff33777777f7e61078ae2ae41ed0636&User-Agent=referrer=https://www.visionplus.id/",
    "TVN (V+)": "2e8cbd6f664b4ace966d3edfad94c18e:cff33777777f7e61078ae2ae41ed0636",
    "TVN (VS)": "3fbf0d50c48a46bfbf287715296f17e5:b1e63bdfd4e89fc42ea41635ab2bc3a9&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 14) ExoPlayerLib/2.15.1",
    "TVN MOVIES (VS)": "e61523260c614746b25b9a5523fe9a39:72ddbf37f76f49acbb8e140e7279e7a1",
    "TVOne (DensTV)": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "TVOne (V+)": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "TVR Parlemen (720p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Aceh (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Bali (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Bangka Belitung (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Bengkulu (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Gorontalo (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Jambi (720p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Jawa Barat (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Jawa Tengah (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Jawa Timur (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Kalimantan Barat (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Kalimantan Selatan (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Kalimantan Tengah (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Kalimantan Timur (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Lampung (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Maluku (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI NASIONAL": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TVRI Nasional": "941717a97fe946069fd7ebc7afb48402:305d9297ec5797e7fd8aca03142b3b7e",
    "TVRI North Sulawesi (1080p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI North Sumatra (1080p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Nusa Tenggara Barat (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Nusa Tenggara Timur (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Papua (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Riau (720p) [Not 24/7]": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI SPORT": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "TVRI Sulawesi Barat (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Sulawesi Selatan (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Sulawesi Tengah (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Sulawesi Tenggara (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Sumatera Barat (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI Sumatera Selatan (480p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI WORLD": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "TVRI West Papua (1080p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVRI World": "941717a97fe946069fd7ebc7afb48402:305d9297ec5797e7fd8aca03142b3b7e",
    "TVRI Yogyakarta (720p)": "de9b995d2aba32bae1c5dbe38a46f2d9:a2d94fdff16e9c332164a73f8b170bd3&User-Agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "TVS": "065051b99bf5cf8d9a3bde5cbde6aaf9:214bd176832872339ce184338320f9a2",
    "Tanduk Setan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Tastemade": "9a149d8edbd85136248129dd3bbabc5f:45b4f449b8583890ad0b5a50694b16a3",
    "Thriil (V+)": "3ffab3471a994535bdf7fc663792f08b:6e82876474df025c39ae804ba738ff17",
    "Titip Surat Untuk Tuhan": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Trans TV": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "Trans TV cad": "764e726a234a435c87a82e4a1da6a69b:0de18199ebb3316e3aed8529e39542b7",
    "Trans7 HD": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "TransTV HD": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "Travel and Adventure": "3d4056f8f4078c5f5a5cfb283dd6cddc:c590b5ad9d3a6eac5cc27507ce34089e",
    "Travel&Taste": "4ee336861eed4840a555788dc54aea6e:f1f53644d4941d4ed31b4bb2478f8cf4",
    "Trax FM Jakarta": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "Trinil": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "TvN movies HD (V+)": "2e8cbd6f664b4ace966d3edfad94c18e:cff33777777f7e61078ae2ae41ed0636",
    "U-CHANNEL": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "UNIFI SPORTS": "b8b595299fdf41c1a3481fddeb0b55e4:cd2b4ad0eb286239a4a022e6ca5fd007",
    "UNIQUES (VS)": "33333f38930949b1af65b3361ad80d1d:b159847f9af0500738b01e91cf023e30&User-Agent=referrer=https://www.visionplus.id/",
    "USA MTV": "55d8bf610e3142408ecfa5295d7eba39:0774f3ae6ea32f9b4c24896f1fb5bb40",
    "Uniquest (V+)": "5a6668f3a5d64338bce13307e5c570be:d0c76237c5ee38e7a420e9c83323023e",
    "VISION PRIME": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a&User-Agent=referrer=https://www.indihometv.com/",
    "VTV": "ec31647c5c3b490bbb5c840ca3e96c9e:a28271a4ba4d085efa1f7738e0f82ea1",
    "VTV (OXY)": "780f283e8dd84dc195d93899ea9fcabe:59103ac45e9c5e411651e3fa26a2e6d9&User-Agent=referrer=https://www.visionplus.id/",
    "VTV (YTV)": "780f283e8dd84dc195d93899ea9fcabe:59103ac45e9c5e411651e3fa26a2e6d9&User-Agent=referrer=https://www.visionplus.id/",
    "Vasantham": "fb3e1afa8ae545f5a99d40baefd8a8d8:6432f742cd17eb5aedc3d68a3a61079c",
    "Virgo and the Sparklings": "0de1f882d278465abdba73a8b4cb2bda:7061f5e1115d6ef504726c3faa8bf146",
    "Vision Prime (V+)": "483c71dd36fd45dd965321e8c568ba42:719598f53c998c618adf76a8f4f17fd1",
    "WARNER TV": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "WB TV": "483c71dd36fd45dd965321e8c568ba42:719598f53c998c618adf76a8f4f17fd1&User-Agent=referrer=https://visionplus.id",
    "Warner TV": "ce73b28200934af786104ce175d0dc45:b3a7b83221ed0d8fe18b8fcf92b5861a",
    "Xing Kong (V+)": "04fb6c48c6b4498cb9d3b9ede0d48db7:94253cf1df2659c3ea253ba1091eca4d",
    "YTV": "be9caaa813c5305e761c66ac63645901:3d40f2990ec5362ca5be3a3c9bb8f8b4",
    "Yomiuri TV": "fc23c442355854992a264931a28fc1c5:3a3368fa385a049695ff4de3c36809cd&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Z BIOSKOP": "69646b755f3130303030303030303030:e4a2359b05563399f1d9adfce641724a",
    "ZOO MOO (AMG)": "780f283e8dd84dc195d93899ea9fcabe:59103ac45e9c5e411651e3fa26a2e6d9&User-Agent=referrer=https://www.visionplus.id/",
    "ZOO MOO (VS)": "736777e5823249849d71a7d41ddc35aa:f831235372e07e24fb70f7336291c549&User-Agent=referrer=https://www.visionplus.id/",
    "Zee BIOSKOP (FX)": "974d4fb195224f66a2271de806e62018:0e92ec1a28d59da80161c3541c6eb8eb&User-Agent=referrer=https://www.visionplus.id/",
    "Zee BIOSKOP (IHT)": "398ef14ec7014ad8ae75414a7efd2a0f:99a6225691aa669f0f22677b4536705e&User-Agent=referrer=https://www.visionplus.id/",
    "Zee BIOSKOP (VS)": "70d0197a8aca42589cf5df6daa576d86:ebd47832fd7251a09e3cc8eb36790ad5&User-Agent=ExoPlayerDemo/2.15.1 (Linux; Android 13) ExoPlayerLib/2.15.1",
    "Zee Bioskop (V+)": "398ef14ec7014ad8ae75414a7efd2a0f:99a6225691aa669f0f22677b4536705e",
    "Zee Bollywood (Tanpa Sub IND)": "f56beaac9f124616872c741c9ce4fa4e:5d40a903238f4ad98abbed1877d4e3d1",
    "Zee Cinema (Tanpa Sub IND)": "398ef14ec7014ad8ae75414a7efd2a0f:99a6225691aa669f0f22677b4536705e&User-Agent=referrer=https://www.visionplus.id/",
    "Zhejiang TV": "d397670017d94f648f4942d3f35b2f10:bd3353307516a1865bf83d6b1ac60368",
    "ZooMoo (V+)": "780f283e8dd84dc195d93899ea9fcabe:59103ac45e9c5e411651e3fa26a2e6d9",
    "bEIN SPORTS 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 3": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 4": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 5": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 6": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 7": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 8": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS 9": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS ENG 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS ENG 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS ENG 3": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS EX 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS EX 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS FR 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS FR 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS FR 3": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS GLOBAL": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS MAX 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS MAX 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS NEW": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS PH 1": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS PH 2": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "bEIN SPORTS PH 3": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 1": "335dad778109954503dcbb21dc92015f:24bfd75d436cbf73168a2a2dccd40281",
    "beIN Sports 1 (V+)": "7995c724a13748ed970840a8ab5bb9b3:67bdaf1e2175b9ff682fcdf0e2354b1e",
    "beIN Sports 1 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 2": "0b42be2664d7e811d04f3e504e0924c5:ae24090123b8c72ac5404dc152847cb8",
    "beIN Sports 2 (V+)": "7995c724a13748ed970840a8ab5bb9b3:67bdaf1e2175b9ff682fcdf0e2354b1e",
    "beIN Sports 2 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 3": "7995c724a13748ed970840a8ab5bb9b3:67bdaf1e2175b9ff682fcdf0e2354b1e",
    "beIN Sports 3 (V+)": "7995c724a13748ed970840a8ab5bb9b3:67bdaf1e2175b9ff682fcdf0e2354b1e",
    "beIN Sports 3 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 4 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 5 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 6 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 7 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 8 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "beIN Sports 9 ARAB (UK)": "4035323a7fe64767ab8f3345ed9b93be:67377b8d429603f8bf30c161bda269e5",
    "i-Radio Bandung": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "i-Radio Banjarmasin": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "i-Radio Jakarta": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "i-Radio Jogja": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "i-Radio Makasar": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "i-Radio Medan": "86e50e1506af46c780233c0091b67159:549788738d10df77094a0d4efaf0d567",
    "iNews": "6a8b65c83036329e7185b9cd8cbdee29:0eb2beb5633f8e35cafab45af3d21de0",
    "tvOne": "251c384e846841abafa1f7c723d57e66:e45b06a38cd261b74c5160f0912c042f",
    }
    
    fixed = 0
    for i, line in enumerate(lines):
        if not line.strip().startswith("#EXTINF"):
            continue
        m = re.search(r",(.+)$", line)
        if not m:
            continue
        name = m.group(1).strip()
        if name not in CORRECT_CLEARKEYS:
            continue
        
        # Search BACKWARDS
        for j in range(i - 1, max(i - 15, -1), -1):
            prev = lines[j].strip()
            if prev.startswith("#EXTINF") or (not prev.startswith("#") and prev):
                break
            if "license_key=" in prev and "http" not in prev.split("license_key=", 1)[1][:10]:
                current_key = prev.split("license_key=", 1)[1].strip()
                if current_key != CORRECT_CLEARKEYS[name]:
                    lines[j] = lines[j].replace(current_key, CORRECT_CLEARKEYS[name])
                    fixed += 1
                break
        else:
            # Search FORWARDS (KODIPROP after EXTINF)
            for j in range(i + 1, min(i + 10, len(lines))):
                nxt = lines[j].strip()
                if nxt.startswith("#EXTINF") or nxt.startswith("http"):
                    break
                if "license_key=" in nxt and "http" not in nxt.split("license_key=", 1)[1][:10]:
                    current_key = nxt.split("license_key=", 1)[1].strip()
                    if current_key != CORRECT_CLEARKEYS[name]:
                        lines[j] = lines[j].replace(current_key, CORRECT_CLEARKEYS[name])
                    fixed += 1
                    break
    if fixed:
        print(f"  correct_source_keys: {fixed} entries fixed")
    else:
        # Debug: check if FUBO is in CORRECT_CLEARKEYS
        if "FUBO SPORTS 1" in CORRECT_CLEARKEYS:
            print(f"  _correct_source_keys: 0 fixed, dict has FUBO1 key={CORRECT_CLEARKEYS['FUBO SPORTS 1'][:30]}")
        else:
            print(f"  _correct_source_keys: 0 fixed, FUBO1 NOT in dict")

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

    # Phase 0: Correct shifted ClearKey keys from source
    # The source file may have keys shifted by 1+ positions due to
    # processing. This pass corrects them before any further processing.
    _correct_source_keys(lines)

    # Phase 1: Line-by-line sanitization
    output: list[str] = []
    for raw_line in lines:
        raw = raw_line.rstrip("\n")
        raw = _RE_FIREFOX_UA_TYPO.sub(r"Firefox/\1", raw)

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
        if raw.startswith("http://") and "dens.tv" not in raw:
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

    # Phase 1b: apply ClearKey overrides (dead Widevine license URLs)
    output = _apply_clearkey_overrides(output)
    output = _fix_poisoned_widevine_keys(output)

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
