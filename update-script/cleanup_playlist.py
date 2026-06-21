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

# ── Pre-compiled regexes ─────────────────────────────────────
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
SOURCE_TRACES = ("bluestraveller13", "super-duper-spork", "kitkatjoss")

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
_RE_EMPTY_TVG_ID = re.compile(r'\s+tvg-id=""')

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
            path = urlparse(self.url).path.lower()
            self._dash = path.endswith(".mpd")
        return self._dash

    @property
    def is_drm(self) -> bool:
        if self._drm is None:
            joined = "\n".join(self.props).lower()
            self._drm = (
                "license_type=clearkey" in joined
                or "license_key=" in joined
                or "/cenc.mpd" in self.url.lower()
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
    except FileNotFoundError:
        pass
    return frozenset(exact), tuple(regexes)


def is_blocked(url: str, blocklist: tuple[frozenset[str], tuple[re.Pattern, ...]]) -> bool:
    """True when a stream URL is on the dead-stream blocklist."""
    exact, regexes = blocklist
    u = url.strip()
    if u in exact:
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
            # Drop commented-out channels/URLs, keep section/comments.
            if not normalized.startswith(("##http", "###EXTINF", "##https")):
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

    h217 still returns master/variant playlists, but the media segments referenced
    by those playlists are 404. Do not ship it as SCTV because clients either
    fail playback or open the DensTV web page in a browser.
    """
    parsed = urlparse(url)
    return is_dens_url(url) and "/h217/" in parsed.path


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
            seen.add(key)
            cleaned.append(candidate)
            stats["entries_kept"] += 1

    if prioritize_sctv_preferred(cleaned):
        stats["sctv_preferred_prioritized"] = 1

    return cleaned, stats


def render(header: str, items: list[str | Entry]) -> str:
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
