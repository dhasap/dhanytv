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
    
    The source file may have keys shifted by 1+ positions. This function
    corrects them by searching backwards from each EXTINF for the preceding
    license_key line and replacing it with the correct key.
    """
    # Correct keys from verified user source files
    # Format: channel_name -> correct_clearkey_value
    CORRECT = {
        "FUBO SPORTS 1": "dc69b6159a0f9f0a4e03b3ff91cbacd5:d0dcbcd7723bc40df0bf34c9c092d51f",
        "FUBO SPORTS 2": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
        "Disney Channel": "be9caaa813c5305e761c66ac63645901:3d40f2e87e2e6e4d201b845b2bb4b8c0",
        "TSN 1": "3dcfbec0e7146928baa55210bf2cb62f:bc85f74f815d9be5ae1dd6defaa05135",
        "TNT SPORTS 1": "e03f302ec4dabcccca82cc9f76731ec9:53ea1027d2bf2893a552cf15bc0366de",
        "SportTV 1": "0bbb23a5ad81427fa6817864b2383402:81e055a8d6ddf6392ae9033f0f037b98",
        "TSN SPORTS 1": "14eeabf30c14b7fbf3008c03099ce011:17d2ac8dbc5429bd70af3433aa12158d",
    }
    
    for i, line in enumerate(lines):
        if not line.strip().startswith("#EXTINF"):
            continue
        m = re.search(r",(.+)$", line)
        if not m:
            continue
        name = m.group(1).strip()
        if name not in CORRECT:
            continue
        # Search backwards for the license_key
        for j in range(i - 1, max(i - 15, -1), -1):
            prev = lines[j].strip()
            if prev.startswith("#EXTINF") or (not prev.startswith("#") and prev):
                break
            if "license_key=" in prev and "http" not in prev.split("license_key=", 1)[1][:10]:
                current_key = prev.split("license_key=", 1)[1].strip()
                if current_key != CORRECT[name]:
                    lines[j] = lines[j].replace(current_key, CORRECT[name])
                break

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
