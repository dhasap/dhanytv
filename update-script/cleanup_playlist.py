#!/usr/bin/env python3
"""Clean and validate dhanytv M3U playlists.

The script is intentionally conservative: it does not invent stream URLs. It only
normalizes playlist syntax, removes entries without playable URLs, and generates
an optional OTT-friendly playlist that excludes DASH/DRM entries for players that
open .mpd links in an external browser.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# ── Pre-compiled regexes ──────────────────────────────────────────────
STREAM_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|plugin://|pipe://)", re.I)
PROP_PREFIXES = (
    "#EXTVLCOPT",
    "#KODIPROP",
    "#EXTGRP",
    "#EXTHTTP",
    "#EXT-X-",
)

DEFAULT_HEADER = '#EXTM3U url-tvg="https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml"'
DENS_REFERRER = "https://www.dens.tv/"
DENS_ORIGIN = "https://www.dens.tv"
DENS_REFERRER_PROP = f"#EXTVLCOPT:http-referrer={DENS_REFERRER}"
DENS_ORIGIN_PROP = f"#EXTVLCOPT:http-origin={DENS_ORIGIN}"
DENS_STREAM_HEADERS_PREFIX = "#KODIPROP:inputstream.adaptive.stream_headers="
DENS_EXTHTTP_PREFIX = "#EXTHTTP:"
DENS_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36"
)
DENS_SCTV_WEB_QUERY = {
    "app_type": "web",
    "userid": "lite",
    "chname": "SCTV",
}
VIDIO_REFERRER = "https://www.vidio.com/"
VIDIO_ORIGIN = "https://www.vidio.com"
VIDIO_USER_AGENT = "VidioPlayer/6.41.11"
SCTV_FALLBACK_URL = "https://aspaltvpasti.top/Drmvidbos/Akun121/bosstv.m3u8?id=204"
SCTV_FALLBACK_PROPS = (
    f"#EXTVLCOPT:http-referrer={VIDIO_REFERRER}",
    f"#EXTVLCOPT:http-origin={VIDIO_ORIGIN}",
    f"#EXTVLCOPT:http-user-agent={VIDIO_USER_AGENT}",
    "#KODIPROP:inputstreamaddon=inputstream.adaptive",
    "#KODIPROP:inputstream.adaptive.manifest_type=hls",
    f"#KODIPROP:inputstream.adaptive.stream_headers=origin={VIDIO_ORIGIN}&referer={VIDIO_REFERRER}&user-agent={VIDIO_USER_AGENT}",
    "#EXTHTTP:"
    + json.dumps(
        {
            "Referer": VIDIO_REFERRER,
            "referrer": VIDIO_REFERRER,
            "Origin": VIDIO_ORIGIN,
            "User-Agent": VIDIO_USER_AGENT,
            "user-agent": VIDIO_USER_AGENT,
        },
        separators=(",", ":"),
    ),
)

# Source trace URLs are not real maintained stream endpoints. merge_source.py
# already drops them from fresh source imports; cleanup must also drop stale
# instances that were committed before that merge-time sanitizer existed.
# Patterns are loaded from SANITIZE_PATTERNS secret at runtime — never hardcoded.
SOURCE_TRACES: tuple[str, ...] = ()

# ── Group normalisation ───────────────────────────────────────────────
GROUP_NORMALIZE_MAP: dict[str, str] = {
    "nasional": "Nasional",
    "hbo group": "HBO Group",
    "lokal": "Local Channels",
    "kids": "Kids",
    "kids channel": "Kids",
    "tv malaysia": "Malaysia",
    "tv jepang": "Japan",
    "korean channels": "Korea",
    "trial idh": "__TRIAL_IDH__",
}
_RE_GROUP_TITLE = re.compile(r'group-title="([^"]*)"')

# Channel-name → target group for Trial IDH members.
TRIAL_IDH_REMAP: dict[str, str] = {
    "RCTI": "Indonesia Channels",
    "Global TV": "Indonesia Channels",
    "MNC TV": "Indonesia Channels",
    "Indosiar": "Nasional",
    "Kompas TV": "Indonesia Channels",
    "TV One": "Indonesia Channels",
    "Nusantara TV": "Indonesia Channels",
    "Rajawali TV": "Indonesia Channels",
    "Berita Satu": "Indonesia Channels",
    "Jawa Pos": "Local Channels",
    "Bali TV": "Local Channels",
    "Jak TV": "Local Channels",
    "JTV": "Local Channels",
    "Prambors TV": "Internet Radio",
    "TVRI": "TVRI",
    "TVRI World": "TVRI",
    "Usee Sport": "Sports Indo",
    "Boomerang": "Kids",
    "CBeebies": "Kids",
    "IndiKids": "Kids",
    "My Kids": "Kids",
    "Nickelodeon": "Kids",
    "ABC Australia": "Australia",
    "Arirang": "Korea",
    "CCTV 4": "China",
    "CGTN Documentary": "China",
    "TV5 Monde": "France",
    "AXN": "MOVIES & ENTERTAINMENT",
    "HITS": "MOVIES & ENTERTAINMENT",
    "HITS Movies": "MOVIES & ENTERTAINMENT",
    "K+": "MOVIES & ENTERTAINMENT",
    "KIX": "MOVIES & ENTERTAINMENT",
    "Thrill": "MOVIES & ENTERTAINMENT",
    "Warner TV": "Entertainment & LifeStyle",
    "Fashion TV": "Entertainment & LifeStyle",
    "Rock Action": "MOVIES & ENTERTAINMENT",
    "Rock Entertainment": "MOVIES & ENTERTAINMENT",
    "Z Bioskop": "MOVIES & ENTERTAINMENT",
    "Fight Sport": "Sports",
    "IDX": "News",
    "Max Eats": "Entertainment & LifeStyle",
    "Max Streak": "Entertainment & LifeStyle",
    "New TV Comprehensive": "Entertainment & LifeStyle",
    "New TV Finance": "News",
    "New TV Variety": "Entertainment & LifeStyle",
}

def _extinf_channel_name(line: str) -> str:
    """Channel name = text after the first comma OUTSIDE quoted attributes."""
    in_quotes = False
    for idx, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            return line[idx + 1:].strip()
    return ""


def normalize_group_title(extinf: str) -> str:
    m = _RE_GROUP_TITLE.search(extinf)
    if not m:
        return extinf
    original = m.group(1)
    canonical = GROUP_NORMALIZE_MAP.get(original.lower(), original)
    # Trial IDH needs special handling: remap by channel name, not a single target.
    if canonical == "__TRIAL_IDH__":
        name = _extinf_channel_name(extinf)
        remap = TRIAL_IDH_REMAP.get(name, "MOVIES & ENTERTAINMENT")
        return extinf[: m.start(1)] + remap + extinf[m.end(1):]
    if canonical == original:
        return extinf
    return extinf[: m.start(1)] + canonical + extinf[m.end(1):]

# normalize_extinf compiled patterns
_RE_EPG_URL_AFTER_GROUP = re.compile(r'(group-title="[^"]+")\s*https?://[^"\s]+"?')
_RE_TVG_URL_URL = re.compile(r'\s+tvg-url="(?:tvg-url=")?https?://[^"\s]+"*')
_RE_TVG_URL = re.compile(r'\s+tvg-url="[^"]*"')
_RE_EMPTY_QUOTED_ATTR = re.compile(r'\s+""(?=\s|,)')
_RE_FIREFOX_UA_TYPO = re.compile(r'Firefox/(\d+(?:\.\d+)*)F\b')
# TVRI's OTT balancer rotates hard-coded bitrate-variant filenames (e.g.
# ".../eds/Aceh/hls/Aceh-avc1_900000=10005-mp4a_96000=20001.m3u8"), which makes
# pinned variant URLs return 404 over time. Rewrite them to the stable master
# playlist URL (".../eds/Aceh/hls/Aceh.m3u8") so streams keep working.
_RE_TVRI_VARIANT_URL = re.compile(
    r"(https?://ott-balancer\.tvri\.go\.id/live/eds/([^/]+)/hls/)\2-[^\"\s]+\.m3u8"
)
_RE_UNQUOTED_TVG_ID = re.compile(r'\btvg-id=([^"\s][^"]*?)"')
_RE_DUP_WHITESPACE = re.compile(r"\s+,")
_RE_MULTI_SPACE = re.compile(r"\s{2,}")
_RE_ATTR_PATTERNS: dict[str, re.Pattern] = {
    attr: re.compile(rf"\s+{attr}=\"[^\"]*\"")
    for attr in ("tvg-id", "tvg-name", "tvg-logo", "group-title", "group-logo")
}

# fallback_tvg_id compiled patterns
_RE_VPLUS_ETC = re.compile(
    r"\s*\((?:V\+|DASH/MPD|ChannelFeed|Channel Feed|DensTV|Dens TV|DENSTV|VD|Alt \d+)\)\s*",
    re.I,
)
_RE_HD_WORD = re.compile(r"\bHD\b", re.I)
_RE_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")

# ensure_tvg_id compiled patterns
_RE_TVG_ID_EXTRACT = re.compile(r'tvg-id="([^"]*)"')
_RE_EMPTY_TVG_ID = re.compile(r'\s*tvg-id=""')

# KODIPROP fix
_RE_KODIPROP_INPUTSTREAM = re.compile(r"^#KODIPROP:inputstream=(?!\.)")

# Section divider
_RE_SECTION_DIVIDER = re.compile(r"^<.*>$")


@dataclass
class Entry:
    props: list[str] = field(default_factory=list)
    extinf: str = ""
    urls: list[str] = field(default_factory=list)
    line_no: int = 0
    _dash: bool | None = field(default=None, repr=False)
    _drm: bool | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        if "," not in self.extinf:
            return ""
        return self.extinf.rsplit(",", 1)[1].strip()

    @property
    def url(self) -> str:
        return self.urls[0] if self.urls else ""

    @property
    def is_dash(self) -> bool:
        if self._dash is None:
            # Check the URL *before* the DRM pipe separator (`|`) which some
            # IPTV players use to embed DRM query params (e.g. `index.mpd|license_type=clearkey`).
            url_base = self.url.split("|", 1)[0] if "|" in self.url else self.url
            path = urlparse(url_base).path.lower()
            self._dash = path.endswith(".mpd")
        return self._dash

    @property
    def is_drm(self) -> bool:
        if self._drm is None:
            joined = "\n".join(self.props).lower()
            url_lower = self.url.lower()
            # Also check DRM params embedded after the pipe separator in the URL.
            url_tail = url_lower.split("|", 1)[1] if "|" in url_lower else ""
            self._drm = (
                "license_type=" in joined
                or "license_key=" in joined
                or "license_type=" in url_tail
                or "/cenc.mpd" in url_lower
            )
        return self._drm


def is_stream_line(line: str) -> bool:
    return bool(STREAM_RE.match(line)) and not line.startswith("#")


def is_prop_line(line: str) -> bool:
    return line.startswith(PROP_PREFIXES)


def build_trace_patterns(extra_patterns: Iterable[str] = ()) -> tuple[str, ...]:
    """Return normalized trace patterns used to drop stale source URLs."""
    patterns = [*SOURCE_TRACES]
    for pattern in extra_patterns:
        pattern = pattern.strip().lower()
        if pattern:
            patterns.append(pattern)
    return tuple(dict.fromkeys(patterns))


def is_trace_url(url: str, trace_patterns: Iterable[str]) -> bool:
    """True for raw source/trace URLs that should not ship as streams."""
    low = url.lower()
    return low.startswith("http") and any(pattern in low for pattern in trace_patterns)


# Path to the dead-stream blocklist, resolved relative to this script so it works
# both from the repo root (auto-update) and from inside update-script/.
BLOCKLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocklist.txt")


def load_blocklist(path: str = BLOCKLIST_PATH) -> tuple[frozenset[str], tuple[re.Pattern, ...]]:
    """Load confirmed-dead stream URLs to drop on every run.

    Lines are exact URL matches; blank lines and lines starting with '#' are
    ignored; lines prefixed with 're:' are compiled as regex patterns.
    Missing file => empty blocklist (no-op), so the pipeline never errors.
    """
    exact: set[str] = set()
    regexes: list[re.Pattern] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("re:"):
                    try:
                        regexes.append(re.compile(line[3:].strip()))
                    except re.error:
                        continue
                else:
                    exact.add(line)
                    # Also index the scheme-stripped form so http:// and
                    # https:// variants of the same dead URL both match.
                    stripped = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", line)
                    if stripped:
                        exact.add(stripped)
    except FileNotFoundError:
        pass
    return frozenset(exact), tuple(regexes)


_RE_URL_PIPE = re.compile(r"^(?P<base>[^|]+)(?:\|(?P<opts>.*))?$")
_RE_KEY_OPT = re.compile(r"(?:^|[|&,;])\s*license[_-]?key=", re.IGNORECASE)


def _drop_keyless_dash_duplicates(urls: list[str]) -> list[str]:
    """Remove keyless copies of URLs that exist elsewhere with a license key.

    A ClearKey DASH stream is unplayable without its key. When the same base
    URL appears both bare and with "|...license_key=...", keep only the keyed
    variant(s).
    """
    keyed_bases = set()
    for u in urls:
        m = _RE_URL_PIPE.match(u.strip())
        if m and m.group("opts") and _RE_KEY_OPT.search("|" + m.group("opts")):
            keyed_bases.add(m.group("base").strip())
    if not keyed_bases:
        return urls
    out = []
    for u in urls:
        m = _RE_URL_PIPE.match(u.strip())
        if (
            m
            and (not m.group("opts") or not _RE_KEY_OPT.search("|" + m.group("opts")))
            and m.group("base").strip() in keyed_bases
        ):
            continue  # keyless twin of a keyed entry — drop
        out.append(u)
    return out


def is_blocked(url: str, blocklist: tuple[frozenset[str], tuple[re.Pattern, ...]]) -> bool:
    """True when a stream URL is on the dead-stream blocklist.

    Scheme-insensitive: merge_source used to rewrite http:// to https://, so
    blocked http:// entries would silently stop matching their https:// twins.
    Compare on scheme-stripped form for exact matches; regex entries still see
    the full URL.
    """
    exact, regexes = blocklist
    u = url.strip()
    if u in exact:
        return True
    u_noscheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", u)
    if u_noscheme and u_noscheme in exact:
        return True
    return any(rx.search(u) for rx in regexes)


def fallback_tvg_id(name: str, used_ids: set[str] | None = None) -> str:
    """Create a stable synthetic tvg-id for channels missing one."""
    clean = _RE_VPLUS_ETC.sub(" ", name)
    clean = _RE_HD_WORD.sub(" ", clean)
    normalized = unicodedata.normalize("NFKD", clean)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _RE_NON_ALNUM.sub(".", ascii_name).strip(".").lower()
    if not slug:
        slug = "channel"
    base = f"auto.{slug}"
    if used_ids is None or base not in used_ids:
        return base
    idx = 2
    while f"{base}.{idx}" in used_ids:
        idx += 1
    return f"{base}.{idx}"


def ensure_tvg_id(line: str, used_ids: set[str]) -> str:
    if not line.startswith("#EXTINF"):
        return line
    m = _RE_TVG_ID_EXTRACT.search(line)
    if m and m.group(1).strip():
        used_ids.add(m.group(1).strip())
        return line
    # Remove empty tvg-id attributes before inserting a synthetic id.
    line = _RE_EMPTY_TVG_ID.sub("", line)
    name = line.rsplit(",", 1)[1].strip() if "," in line else "channel"
    tvg_id = fallback_tvg_id(name, used_ids)
    used_ids.add(tvg_id)
    return line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-id="{tvg_id}"', 1)


def normalize_extinf(line: str) -> str:
    """Fix common EXTINF typos without changing channel identity."""
    # tvg-url is non-standard and causes parser/UI bugs. Remove both normal
    # attributes and malformed nested variants like tvg-url="tvg-url="https://...".
    line = _RE_TVG_URL_URL.sub("", line)
    line = _RE_TVG_URL.sub("", line)
    # Drop orphan empty attributes accidentally injected by source scripts, e.g.
    # group-title="Local Channels" "" tvg-logo="...".
    line = _RE_EMPTY_QUOTED_ATTR.sub("", line)
    # Fix broken tvg-id quote: tvg-id="TV5Monde"Entertainment & LifeStyle"
    # → tvg-id="TV5Monde" group-title="Entertainment & LifeStyle"
    line = re.sub(
        r'(tvg-id="[^"]*")([A-Z][^"]*?")',
        lambda m: f'{m.group(1)} group-title="{m.group(2).rstrip(chr(34))}"',
        line,
    )
    # Remove accidentally pasted EPG URL after group-title="...".
    line = _RE_EPG_URL_AFTER_GROUP.sub(r"\1", line)
    # Fix unquoted tvg-id values such as: tvg-id=Dunia Sinema HD"
    line = _RE_UNQUOTED_TVG_ID.sub(lambda m: f'tvg-id="{m.group(1).strip()}"', line)
    # Collapse duplicate whitespace before the channel name comma.
    line = _RE_DUP_WHITESPACE.sub(",", line)
    # Normalise duplicate group-title variants (e.g. "KIDS" → "Kids").
    line = normalize_group_title(line)
    # Remove duplicate attributes, keeping the first occurrence.
    for attr, pattern in _RE_ATTR_PATTERNS.items():
        seen = False

        def repl(match: re.Match[str], _seen: list[bool] = [False]) -> str:
            if _seen[0]:
                return ""
            _seen[0] = True
            return match.group(0)

        # Reset the closure state
        repl.__defaults__ = ([False],)  # type: ignore[attr-defined]
        line = pattern.sub(repl, line)
    line = _RE_MULTI_SPACE.sub(" ", line)
    return line.strip()


def normalize_line(raw: str) -> str:
    line = raw.strip().lstrip("\ufeff")
    if not line:
        return ""
    # Fix malformed Firefox UA strings that break strict clients.
    line = _RE_FIREFOX_UA_TYPO.sub(r"Firefox/\1", line)
    # Rewrite pinned TVRI bitrate-variant URLs to the stable master playlist URL.
    line = _RE_TVRI_VARIANT_URL.sub(r"\1\2.m3u8", line)
    if line.startswith("KODIPROP:"):
        line = "#" + line
    # Fix KODIPROP typo: inputstream= should be inputstreamaddon=
    if _RE_KODIPROP_INPUTSTREAM.match(line):
        line = line.replace("#KODIPROP:inputstream=", "#KODIPROP:inputstreamaddon=", 1)
    if line.startswith("#EXTINF"):
        line = normalize_extinf(line)
    # Plain section dividers are invalid M3U items. Keep them as comments.
    if _RE_SECTION_DIVIDER.match(line):
        return "# " + line
    return line


def dedupe_keep_order(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def is_dens_url(url: str) -> bool:
    """Return True when a stream URL belongs to dens.tv."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host == "dens.tv" or host.endswith(".dens.tv")


def normalize_dens_referrer_prop(prop: str) -> str:
    """Normalize dens.tv referrer variants to the canonical web origin."""
    if not prop.startswith("#EXTVLCOPT:http-referrer="):
        return prop
    if "dens.tv" not in prop.lower():
        return prop
    return DENS_REFERRER_PROP


def dens_user_agent(props: Iterable[str]) -> str:
    """Return the DensTV user-agent from props, or a stable browser UA fallback."""
    for prop in props:
        if prop.startswith("#EXTVLCOPT:http-user-agent="):
            ua = prop.split("=", 1)[1].strip()
            if ua:
                return ua
    return DENS_DEFAULT_UA


def dens_stream_headers_prop(user_agent: str) -> str:
    """Kodi/inputstream-adaptive compatible stream_headers variant."""
    headers = [
        f"Referer={DENS_REFERRER}",
        f"referrer={DENS_REFERRER}",
        f"Origin={DENS_ORIGIN}",
        f"User-Agent={user_agent}",
        f"user-agent={user_agent}",
    ]
    return DENS_STREAM_HEADERS_PREFIX + "|".join(headers)


def dens_ext_http_prop(user_agent: str) -> str:
    """EXTHTTP JSON header variant used by several IPTV/OTT clients."""
    return DENS_EXTHTTP_PREFIX + json.dumps(
        {
            "Referer": DENS_REFERRER,
            "referrer": DENS_REFERRER,
            "Origin": DENS_ORIGIN,
            "User-Agent": user_agent,
            "user-agent": user_agent,
        },
        separators=(",", ":"),
    )


def with_sctv_dens_query(url: str) -> tuple[str, bool]:
    """Add DensTV web query params for SCTV h217 when missing.

    The HLS manifest works without query params in curl, but some embedded player
    webviews redirect bare DensTV URLs to the browser page. The old DensTV web
    URL shape carries app_type/userid/chname, so keep it for SCTV.
    """
    if not is_dens_url(url) or "/h217/" not in urlparse(url).path:
        return url, False
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    before = dict(query)
    query.update(DENS_SCTV_WEB_QUERY)
    if query == before:
        return url, False
    return urlunparse(parsed._replace(query=urlencode(query))), True


def ensure_dens_headers(entry: Entry) -> tuple[bool, bool]:
    """Force DensTV streams to carry Referrer/Origin headers in multiple formats.

    Some IPTV players only pass DensTV HLS options when they are attached in a
    client-specific format. Emit EXTVLCOPT, KODIPROP stream_headers, and EXTHTTP
    so SCTV does not fall back to opening the DensTV browser page.
    """
    if not any(is_dens_url(url) for url in entry.urls):
        return False, False

    query_changed = False
    new_urls: list[str] = []
    for url in entry.urls:
        new_url, changed = with_sctv_dens_query(url)
        query_changed = query_changed or changed
        new_urls.append(new_url)
    if query_changed:
        entry.urls = new_urls
        entry._dash = None
        entry._drm = None

    user_agent = dens_user_agent(entry.props)
    user_agent_prop = f"#EXTVLCOPT:http-user-agent={user_agent}"

    non_header_props: list[str] = []
    for prop in entry.props:
        prop = normalize_dens_referrer_prop(prop)
        if prop.startswith((
            "#EXTVLCOPT:http-referrer=",
            "#EXTVLCOPT:http-origin=",
            "#EXTVLCOPT:http-user-agent=",
            DENS_STREAM_HEADERS_PREFIX,
            DENS_EXTHTTP_PREFIX,
        )):
            continue
        non_header_props.append(prop)

    new_props = dedupe_keep_order([
        DENS_REFERRER_PROP,
        DENS_ORIGIN_PROP,
        user_agent_prop,
        dens_stream_headers_prop(user_agent),
        dens_ext_http_prop(user_agent),
        *non_header_props,
    ])
    headers_changed = new_props != entry.props
    entry.props = new_props
    return headers_changed, query_changed


def is_sctv_dens_entry(item: str | Entry) -> bool:
    return isinstance(item, Entry) and any(is_dens_url(url) and "/h217/" in urlparse(url).path for url in item.urls)


def is_sctv_entry(item: str | Entry) -> bool:
    if not isinstance(item, Entry):
        return False
    return item.name.upper().startswith("SCTV")


def prioritize_sctv_preferred(items: list[str | Entry]) -> bool:
    """Place the playable SCTV fallback before SCTV DASH/V+ duplicates.

    Several clients group duplicate tvg-id/name entries and auto-pick the first
    SCTV item. If the DASH/V+ SCTV comes first, those clients may open a browser
    or external handler. Prefer the segment-playable HLS fallback.
    """
    preferred_idx = next((idx for idx, item in enumerate(items) if is_sctv_preferred_entry(item)), None)
    first_sctv_idx = next((idx for idx, item in enumerate(items) if is_sctv_entry(item)), None)
    if preferred_idx is None or first_sctv_idx is None or preferred_idx <= first_sctv_idx:
        return False
    item = items.pop(preferred_idx)
    items.insert(first_sctv_idx, item)
    return True


def extract_items(lines: list[str]) -> tuple[str, list[str | Entry], dict[str, int]]:
    stats = {
        "plain_commented": 0,
        "orphan_urls": 0,
        "orphan_props": 0,
        "malformed_extinf_fixed": 0,
    }
    header = ""
    items: list[str | Entry] = []
    pending_props: list[str] = []
    used_tvg_ids: set[str] = set()
    current: Entry | None = None

    def finish_current() -> None:
        nonlocal current
        if current is not None:
            current.props = dedupe_keep_order([*current.props])
            items.append(current)
            current = None

    for line_no, raw in enumerate(lines, 1):
        stripped = raw.strip()
        normalized = normalize_line(raw)
        if not normalized:
            continue

        if stripped.startswith("#EXTINF") and normalized != stripped:
            stats["malformed_extinf_fixed"] += 1
        if stripped.startswith("<") and normalized.startswith("# <"):
            stats["plain_commented"] += 1

        if normalized.startswith("#EXTM3U"):
            if not header:
                header = normalized
            continue

        if normalized.startswith("#EXTINF"):
            # If the previous EXTINF never received a URL, it is an orphan/stray
            # duplicate (some upstream sources emit a bare EXTINF above the real
            # props+EXTINF+URL block). Carry its props forward instead of letting
            # them die with the discarded orphan -- otherwise DRM license keys /
            # headers placed before the real EXTINF are lost.
            if current is not None and not current.urls:
                pending_props = dedupe_keep_order([*current.props, *pending_props])
                current = None
            else:
                finish_current()
            normalized = ensure_tvg_id(normalized, used_tvg_ids)
            current = Entry(props=pending_props, extinf=normalized, line_no=line_no)
            pending_props = []
            continue

        if is_stream_line(normalized):
            if current is None:
                stats["orphan_urls"] += 1
                continue
            current.urls.append(normalized)
            # Invalidate cached dash/drm since urls changed
            current._dash = None
            current._drm = None
            continue

        if is_prop_line(normalized):
            if current is not None and not current.urls:
                current.props.append(normalized)
                # Invalidate cached drm since props changed
                current._drm = None
            else:
                pending_props.append(normalized)
            continue

        if normalized.startswith("#"):
            finish_current()
            if pending_props:
                stats["orphan_props"] += len(pending_props)
                pending_props = []
            # Drop commented-out channels/URLs/props (##http, ###EXTINF,
            # ####KODIPROP, ###https, ...), keep section/comments.
            if re.match(r"^#{2,}(?:https?://|EXTINF|KODIPROP|EXTVLCOPT|EXTGRP|EXTHTTP)", normalized):
                continue
            items.append(normalized)
            continue

        # Any remaining plain text is invalid in M3U. Preserve as comment.
        finish_current()
        if pending_props:
            stats["orphan_props"] += len(pending_props)
            pending_props = []
        items.append("# " + normalized)
        stats["plain_commented"] += 1

    finish_current()
    if pending_props:
        stats["orphan_props"] += len(pending_props)

    return header or DEFAULT_HEADER, items, stats


def clone_with_url(entry: Entry, url: str) -> Entry:
    return Entry(props=[*entry.props], extinf=entry.extinf, urls=[url], line_no=entry.line_no)


def label_sctv_dash(entry: Entry) -> None:
    # Label the known problematic SCTV DASH alternative so OTT users do not
    # confuse it with a universal HLS stream. The URL is valid DASH, but some
    # OTT TV apps open .mpd links in a browser/external handler.
    if entry.name == "SCTV" and entry.is_dash:
        entry.extinf = entry.extinf.rsplit(",", 1)[0] + ",SCTV (DASH/MPD)"


def is_broken_sctv_dens_url(url: str) -> bool:
    """True for the stale DensTV h217 SCTV endpoint.

    NOTE 2026-08-15: h217 is the DensTV (DENSGO) endpoint for Indonesian
    users — geo-locked to Indonesia (returns nothing from abroad) and
    still listed by iptv-org for SCTV.id. It used to serve 404 segments;
    re-verified: the endpoint is the intended source for ID users.
    Keep it so ensure_dens_headers() can attach the correct dens.tv headers.
    """
    return False


def replace_broken_sctv_dens(entry: Entry) -> bool:
    """Replace stale DensTV SCTV with the segment-playable Vidio HLS fallback."""
    # DISABLED: the old Vidio aspaltv fallback URL is now dead (404). The dens.tv
    # h217 SCTV stream is the working source (geo-locked to Indonesia); let it pass
    # through so ensure_dens_headers() can attach the correct dens.tv headers.
    return False
    if not any(is_broken_sctv_dens_url(url) for url in entry.urls):
        return False
    entry.props = list(SCTV_FALLBACK_PROPS)
    entry.urls = [SCTV_FALLBACK_URL]
    entry._dash = None
    entry._drm = None
    return True


def is_sctv_preferred_entry(item: str | Entry) -> bool:
    if not isinstance(item, Entry):
        return False
    return SCTV_FALLBACK_URL in item.urls


def clean_items(
    items: list[str | Entry],
    trace_patterns: Iterable[str] = SOURCE_TRACES,
) -> tuple[list[str | Entry], dict[str, int]]:
    blocklist = load_blocklist()
    stats = {
        "entries_total": 0,
        "entries_kept": 0,
        "entries_no_url_removed": 0,
        "trace_urls_removed": 0,
        "blocklist_removed": 0,
        "fallback_entries_created": 0,
        "duplicates_removed": 0,
        "dens_headers_fixed": 0,
        "dens_sctv_query_fixed": 0,
        "sctv_dens_replaced": 0,
        "sctv_preferred_prioritized": 0,
        "sctv_dash_labeled": 0,
    }
    cleaned: list[str | Entry] = []
    seen: set[tuple[str, str]] = set()
    # Track URLs that are already in the playlist so that the same stream URL
    # is never shipped twice (even with different tvg-id or channel name).
    # Maps URL → index in cleaned, so we can replace with a preferred group.
    seen_urls: dict[str, int] = {}
    # Bare URLs (no pipe-header suffix) seen so far, for variant-insensitive dedupe.
    seen_bare_urls: set[str] = set()

    # Groups that should win when two entries share the same URL.
    PREFERRED_GROUPS = frozenset({
        "indonesia channels",
        "nasional",
        "bola indonesia",
    })

    for item in items:
        if isinstance(item, str):
            if cleaned and cleaned[-1] == item:
                continue
            cleaned.append(item)
            continue

        stats["entries_total"] += 1
        entry = item
        entry.props = dedupe_keep_order(entry.props)

        before_url_count = len(entry.urls)
        entry.urls = [url for url in entry.urls if not is_trace_url(url, trace_patterns)]
        removed_trace_urls = before_url_count - len(entry.urls)
        if removed_trace_urls:
            stats["trace_urls_removed"] += removed_trace_urls
            entry._dash = None
            entry._drm = None

        # Drop confirmed-dead streams listed in blocklist.txt so they never
        # re-enter the playlist via a source re-merge.
        before_block = len(entry.urls)
        entry.urls = [url for url in entry.urls if not is_blocked(url, blocklist)]
        removed_blocked = before_block - len(entry.urls)
        if removed_blocked:
            stats["blocklist_removed"] += removed_blocked
            entry._dash = None
            entry._drm = None

        # Keyless duplicates of ClearKey DASH entries are dropped by the
        # global pass below (they live in different entries).
        if not entry.urls:
            stats["entries_no_url_removed"] += 1
            continue

        # Keep multiple URLs as explicit fallback entries instead of leaving raw
        # extra URL lines under one #EXTINF. This is safer for strict M3U parsers.
        expanded = [clone_with_url(entry, url) for url in entry.urls]
        if len(expanded) > 1:
            stats["fallback_entries_created"] += len(expanded) - 1
            for idx, fallback in enumerate(expanded[1:], start=2):
                base, name = fallback.extinf.rsplit(",", 1)
                fallback.extinf = f"{base},{name.strip()} (Alt {idx})"

        for candidate in expanded:
            # dens.tv h217 SCTV redirects to the browser instead of playing, and the
            # old Vidio HLS mirror is dead (404). Drop it so only the reliable DRM
            # (V+) SCTV remains — one tvg-id per channel keeps EPG binding correct.
            if any(is_broken_sctv_dens_url(u) for u in candidate.urls):
                stats["sctv_dens_replaced"] += 1
                continue

            headers_changed, query_changed = ensure_dens_headers(candidate)
            if headers_changed:
                stats["dens_headers_fixed"] += 1
            if query_changed:
                stats["dens_sctv_query_fixed"] += 1

            before_name = candidate.name
            label_sctv_dash(candidate)
            if candidate.name != before_name:
                stats["sctv_dash_labeled"] += 1

            tvg_id = ""
            m = _RE_TVG_ID_EXTRACT.search(candidate.extinf)
            if m:
                tvg_id = m.group(1).strip().lower()
            key = (tvg_id, candidate.url)
            if key in seen:
                stats["duplicates_removed"] += 1
                continue
            # Same stream with a different pipe-header suffix (e.g. one entry
            # carries |User-Agent=...) is still the same channel — compare on
            # the bare URL so these variants dedupe too.
            # Clearkey entries always beat keyless duplicates of the same URL,
            # since only the keyed copy can decrypt. This check runs before
            # the generic duplicate removal below.
            bare_url = candidate.url.split("|", 1)[0]
            cand_has_ck = any("license_type=" in p for p in candidate.props)
            if cand_has_ck and bare_url in seen_bare_urls:
                # Replace the existing keyless entry with this keyed one
                for idx2, item2 in enumerate(cleaned):
                    if isinstance(item2, Entry) and item2.url.split("|",1)[0] == bare_url:
                        cleaned[idx2] = candidate
                        stats["duplicates_removed"] += 1
                        break
                continue
            # Also drop entries whose URL already appeared (regardless of
            # tvg-id) — the same stream should never ship twice.
            # Exception: if the new candidate is in a preferred group (e.g.
            # "Indonesia Channels"), replace the existing entry with it.
            if candidate.url in seen_urls:
                existing_idx = seen_urls[candidate.url]
                existing_entry = cleaned[existing_idx]
                existing_group = ""
                if isinstance(existing_entry, Entry):
                    gm = _RE_GROUP_TITLE.search(existing_entry.extinf)
                    existing_group = gm.group(1).lower() if gm else ""
                candidate_group_m = _RE_GROUP_TITLE.search(candidate.extinf)
                candidate_group = candidate_group_m.group(1).lower() if candidate_group_m else ""
                if candidate_group in PREFERRED_GROUPS and existing_group not in PREFERRED_GROUPS:
                    # Replace the existing entry with this preferred one
                    existing_tvg_id = ""
                    if isinstance(existing_entry, Entry):
                        em = _RE_TVG_ID_EXTRACT.search(existing_entry.extinf)
                        existing_tvg_id = em.group(1).strip().lower() if em else ""
                    seen.discard((existing_tvg_id, candidate.url))
                    cleaned[existing_idx] = candidate
                    seen.add((tvg_id, candidate.url))
                    stats["duplicates_removed"] += 1
                    continue
                stats["duplicates_removed"] += 1
                continue
            seen.add(key)
            seen_urls[candidate.url] = len(cleaned)
            seen_bare_urls.add(bare_url)
            cleaned.append(candidate)
            stats["entries_kept"] += 1

    # Global pass: drop keyless copies of ClearKey DASH URLs that also exist
    # (in any entry) with a "|...license_key=..." suffix. The keyless copy
    # can't decrypt; keeping both wastes a channel slot on the same stream.
    keyed_bases = {
        u.split("|", 1)[0].strip()
        for it in cleaned
        if isinstance(it, Entry)
        for u in it.urls
        if "|" in u and _RE_KEY_OPT.search(u.split("|", 1)[1])
    }
    if keyed_bases:
        for it in cleaned:
            if isinstance(it, Entry):
                before = len(it.urls)
                it.urls = [
                    u for u in it.urls
                    if not (
                        ("|" not in u or not _RE_KEY_OPT.search(u.split("|", 1)[1]))
                        and u.split("|", 1)[0].strip() in keyed_bases
                    )
                ]
                if len(it.urls) < before:
                    stats["keyless_dash_dupes_removed"] = stats.get("keyless_dash_dupes_removed", 0) + (before - len(it.urls))
        cleaned = [it for it in cleaned if not (isinstance(it, Entry) and not it.urls)]

    # Name-based dedup: when the same channel name appears multiple times,
    # remove entries whose URLs are on the blocklist (dead hosts). This fixes
    # the case where merge_source injects dead URLs first, then merge_extra
    # injects working URLs for the same channel — both survive the URL-based
    # dedup because they have different URLs.
    name_groups: dict[str, list[int]] = {}
    for idx, item in enumerate(cleaned):
        if isinstance(item, Entry):
            norm_name = item.name.strip().lower()
            # Normalize common suffixes for grouping
            norm_name = re.sub(r"\s*\(.*?\)\s*$", "", norm_name)
            norm_name = re.sub(r"\s+hd\s*$", "", norm_name)
            norm_name = re.sub(r"\s+", " ", norm_name).strip()
            if norm_name:
                name_groups.setdefault(norm_name, []).append(idx)

    indices_to_remove: set[int] = set()
    for norm_name, indices in name_groups.items():
        if len(indices) < 2:
            continue
        # Check if any entry has a blocked URL
        has_blocked = any(
            any(is_blocked(url, blocklist) for url in cleaned[idx].urls)
            for idx in indices
            if isinstance(cleaned[idx], Entry)
        )
        if not has_blocked:
            continue
        # Remove blocked entries; keep working ones
        for idx in indices:
            if isinstance(cleaned[idx], Entry):
                if any(is_blocked(url, blocklist) for url in cleaned[idx].urls):
                    indices_to_remove.add(idx)
                    stats["blocklist_removed"] += len(cleaned[idx].urls)

    if indices_to_remove:
        cleaned = [item for idx, item in enumerate(cleaned) if idx not in indices_to_remove]

    if prioritize_sctv_preferred(cleaned):
        stats["sctv_preferred_prioritized"] = 1

    # Reorder groups: priority groups first (keeping internal order intact),
    # then all remaining groups in their original order.
    PRIORITY_GROUPS = [
        "Indonesia Channels",
        "Sports",
        "Kids",
        "WorldCup 2026",
        "Local Channels",
    ]
    priority_set = {g.lower() for g in PRIORITY_GROUPS}
    prioritized: list[str | Entry] = []
    remaining: list[str | Entry] = []
    # Track which items go where based on their group
    for item in cleaned:
        if isinstance(item, Entry):
            gm = _RE_GROUP_TITLE.search(item.extinf)
            group = gm.group(1) if gm else ""
            if group.lower() in priority_set:
                prioritized.append(item)
                continue
        # Keep comments/dividers attached to the group that follows them.
        # If a comment is immediately before a priority entry, move it too.
        remaining.append(item)

    # Rebuild: priority groups first (in PRIORITY_GROUPS order), then remaining.
    # IMPORTANT: do NOT sort within groups — sorting reorders entries and shifts
    # KODIPROP license_key lines relative to their EXTINF entries, causing
    # "crypto key not available" errors in the player.
    reordered: list[str | Entry] = []
    for target in PRIORITY_GROUPS:
        group_items = [item for item in prioritized
                       if isinstance(item, Entry) and
                       _RE_GROUP_TITLE.search(item.extinf) and
                       _RE_GROUP_TITLE.search(item.extinf).group(1) == target]
        reordered.extend(group_items)
    reordered.extend(remaining)

    cleaned = reordered

    return cleaned, stats


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

def _fix_keys_in_render(items: list[str | Entry]) -> None:
    import sys as _sys
    ck_count = sum(1 for it in items if isinstance(it, Entry) and any('license_key=' in p for p in it.props))
    print(f"  _fix_keys_in_render called: {len(items)} items, {ck_count} with ClearKey", file=_sys.stderr)
    """Correct shifted ClearKey keys in rendered entries.

    For each entry with a ClearKey, check if the key matches the correct
    value from CORRECT_CLEARKEYS. If not, replace it.
    """
    for item in items:
        if not isinstance(item, Entry):
            continue
        for pi, prop in enumerate(item.props):
            if 'license_key=' in prop and 'http' not in prop.split('license_key=', 1)[1][:10]:
                current_key = prop.split('license_key=', 1)[1].strip()
                correct = CORRECT_CLEARKEYS.get(item.name, '')
                if correct and current_key != correct:
                    item.props[pi] = prop.replace(current_key, correct)
                elif item.name in ['FUBO SPORTS 1', 'FUBO SPORTS 2', 'Disney Channel']:
                    import sys as _sys
                    print(f"  DEBUG {item.name}: current={current_key[:20]} correct={correct[:20] if correct else 'NONE'}", file=_sys.stderr)
                break

def render(header: str, items: list[str | Entry]) -> str:
    _fix_keys_in_render(items)
    out: list[str] = [header, ""]
    last_blank = True
    for item in items:
        if isinstance(item, str):
            if item.startswith("# <"):
                if not last_blank:
                    out.append("")
                out.append(item)
                out.append("")
                last_blank = True
            else:
                out.append(item)
                last_blank = False
            continue

        if not last_blank:
            out.append("")
        # DensTV and the SCTV Vidio fallback are sensitive to HTTP headers. Put
        # their options directly between #EXTINF and the URL so strict players
        # bind them to the stream instead of treating them as orphan/pending props.
        if any(is_dens_url(url) or url == SCTV_FALLBACK_URL for url in item.urls):
            out.append(item.extinf)
            for prop in item.props:
                out.append(prop)
            out.append(item.url)
        else:
            for prop in item.props:
                out.append(prop)
            out.append(item.extinf)
            out.append(item.url)
        last_blank = False

    # Normalize to one trailing newline and avoid more than two consecutive blanks.
    compact: list[str] = []
    blank_count = 0
    for line in out:
        if line == "":
            blank_count += 1
            if blank_count > 2:
                continue
        else:
            blank_count = 0
        compact.append(line)
    return "\n".join(compact).rstrip() + "\n"


def make_ott_items(items: list[str | Entry]) -> tuple[list[str | Entry], dict[str, int]]:
    stats = {"dash_or_drm_removed": 0, "entries_kept": 0}
    out: list[str | Entry] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
            continue
        if item.is_dash or item.is_drm:
            stats["dash_or_drm_removed"] += 1
            continue
        out.append(item)
        stats["entries_kept"] += 1
    return out, stats


def validate_items(items: list[str | Entry]) -> dict[str, int]:
    """Validate using structured data — no re-parsing needed."""
    stats = {"entries": 0, "entries_without_url": 0, "plain_invalid_lines": 0, "multi_url_entries": 0}
    for item in items:
        if isinstance(item, str):
            if item.startswith("#") or not item.strip():
                continue
            stats["plain_invalid_lines"] += 1
            continue
        stats["entries"] += 1
        if not item.urls:
            stats["entries_without_url"] += 1
        elif len(item.urls) > 1:
            stats["multi_url_entries"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and validate a dhanytv M3U playlist")
    parser.add_argument("playlist", help="Path to the M3U playlist")
    parser.add_argument("--write", action="store_true", help="Overwrite playlist with cleaned output")
    parser.add_argument("--output", help="Write cleaned output to this path instead of stdout/overwrite")
    parser.add_argument("--ott-output", help="Also write HLS/non-DRM OTT-friendly playlist to this path")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if cleaned playlist still has structural errors")
    parser.add_argument(
        "--sanitize",
        default="",
        help="Additional trace URL patterns to remove, pipe-separated",
    )
    args = parser.parse_args()

    path = Path(args.playlist)
    original = path.read_text(encoding="utf-8", errors="replace")
    header, raw_items, parse_stats = extract_items(original.splitlines())
    extra_patterns = args.sanitize.split("|") if args.sanitize else []
    trace_patterns = build_trace_patterns(extra_patterns)
    items, clean_stats = clean_items(raw_items, trace_patterns)
    cleaned = render(header, items)
    validation = validate_items(items)

    target = Path(args.output) if args.output else path
    if args.write or args.output:
        target.write_text(cleaned, encoding="utf-8")
    else:
        print(cleaned, end="")

    ott_stats: dict[str, int] = {}
    if args.ott_output:
        ott_items, ott_stats = make_ott_items(items)
        ott_text = render(header, ott_items)
        Path(args.ott_output).write_text(ott_text, encoding="utf-8")

    print("=== Playlist cleanup summary ===")
    for group in (parse_stats, clean_stats, validation):
        for key, value in group.items():
            print(f"{key}: {value}")
    if ott_stats:
        for key, value in ott_stats.items():
            print(f"ott_{key}: {value}")

    has_errors = validation["entries_without_url"] or validation["plain_invalid_lines"] or validation["multi_url_entries"]
    return 1 if args.check and has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
