#!/usr/bin/env python3
"""Clean and validate dhanytv M3U playlists.

The script is intentionally conservative: it does not invent stream URLs. It only
normalizes playlist syntax, removes entries without playable URLs, and generates
an optional OTT-friendly playlist that excludes DASH/DRM entries for players that
open .mpd links in an external browser.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
import unicodedata

STREAM_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|plugin://|pipe://)", re.I)
PROP_PREFIXES = (
    "#EXTVLCOPT",
    "#KODIPROP",
    "#EXTGRP",
    "#EXTHTTP",
    "#EXT-X-",
)

DEFAULT_HEADER = '#EXTM3U url-tvg="https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml"'


@dataclass
class Entry:
    props: list[str] = field(default_factory=list)
    extinf: str = ""
    urls: list[str] = field(default_factory=list)
    line_no: int = 0

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
        path = urlparse(self.url).path.lower()
        return path.endswith(".mpd")

    @property
    def is_drm(self) -> bool:
        joined = "\n".join(self.props).lower()
        return "license_type=clearkey" in joined or "license_key=" in joined or "/cenc.mpd" in self.url.lower()


def is_stream_line(line: str) -> bool:
    return bool(STREAM_RE.match(line)) and not line.startswith("#")


def is_prop_line(line: str) -> bool:
    return line.startswith(PROP_PREFIXES)


def fallback_tvg_id(name: str, used_ids: set[str] | None = None) -> str:
    """Create a stable synthetic tvg-id for channels missing one."""
    clean = re.sub(r"\s*\((?:V\+|DASH/MPD|ChannelFeed|Channel Feed|DensTV|Dens TV|DENSTV|VD|Alt \d+)\)\s*", " ", name, flags=re.I)
    clean = re.sub(r"\bHD\b", " ", clean, flags=re.I)
    normalized = unicodedata.normalize("NFKD", clean)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", ".", ascii_name).strip(".").lower()
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
    m = re.search(r'tvg-id="([^"]*)"', line)
    if m and m.group(1).strip():
        used_ids.add(m.group(1).strip())
        return line
    # Remove empty tvg-id attributes before inserting a synthetic id.
    line = re.sub(r'\s+tvg-id=""', "", line)
    name = line.rsplit(",", 1)[1].strip() if "," in line else "channel"
    tvg_id = fallback_tvg_id(name, used_ids)
    used_ids.add(tvg_id)
    return line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-id="{tvg_id}"', 1)


def normalize_extinf(line: str) -> str:
    """Fix common EXTINF typos without changing channel identity."""
    # Remove accidentally pasted EPG URL after group-title="...".
    line = re.sub(r'(group-title="[^"]+")\s*https?://[^"\s]+"?', r"\1", line)
    # Fix unquoted tvg-id values such as: tvg-id=Dunia Sinema HD"
    line = re.sub(r'\btvg-id=([^"\s][^"]*?)"', lambda m: f'tvg-id="{m.group(1).strip()}"', line)
    # Collapse duplicate whitespace before the channel name comma.
    line = re.sub(r"\s+,", ",", line)
    # Remove duplicate attributes, keeping the first occurrence.
    for attr in ("tvg-id", "tvg-name", "tvg-logo", "group-title", "group-logo"):
        seen = False

        def repl(match: re.Match[str]) -> str:
            nonlocal seen
            if seen:
                return ""
            seen = True
            return match.group(0)

        line = re.sub(rf"\s+{attr}=\"[^\"]*\"", repl, line)
    line = re.sub(r"\s{2,}", " ", line)
    return line.strip()


def normalize_line(raw: str) -> str:
    line = raw.strip().lstrip("\ufeff")
    if not line:
        return ""
    if line.startswith("KODIPROP:"):
        line = "#" + line
    # Fix KODIPROP typo: inputstream= should be inputstreamaddon=
    if line.startswith("#KODIPROP:inputstream=") and not line.startswith("#KODIPROP:inputstream."):
        line = line.replace("#KODIPROP:inputstream=", "#KODIPROP:inputstreamaddon=", 1)
    if line.startswith("#EXTINF"):
        line = normalize_extinf(line)
    # Plain section dividers are invalid M3U items. Keep them as comments.
    if line.startswith("<") and line.endswith(">"):
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
            continue

        if is_prop_line(normalized):
            if current is not None and not current.urls:
                current.props.append(normalized)
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


def clean_items(items: list[str | Entry]) -> tuple[list[str | Entry], dict[str, int]]:
    stats = {
        "entries_total": 0,
        "entries_kept": 0,
        "entries_no_url_removed": 0,
        "fallback_entries_created": 0,
        "duplicates_removed": 0,
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
            before_name = candidate.name
            label_sctv_dash(candidate)
            if candidate.name != before_name:
                stats["sctv_dash_labeled"] += 1

            tvg_id = ""
            m = re.search(r'tvg-id="([^"]+)"', candidate.extinf)
            if m:
                tvg_id = m.group(1).strip().lower()
            key = (tvg_id, candidate.url)
            if key in seen:
                stats["duplicates_removed"] += 1
                continue
            seen.add(key)
            cleaned.append(candidate)
            stats["entries_kept"] += 1

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


def validate_text(text: str) -> dict[str, int]:
    lines = text.splitlines()
    stats = {"entries": 0, "entries_without_url": 0, "plain_invalid_lines": 0, "multi_url_entries": 0}
    current_has_url = False
    current_url_count = 0
    in_entry = False

    def close_entry() -> None:
        nonlocal in_entry, current_has_url, current_url_count
        if in_entry:
            if not current_has_url:
                stats["entries_without_url"] += 1
            if current_url_count > 1:
                stats["multi_url_entries"] += 1
        in_entry = False
        current_has_url = False
        current_url_count = 0

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#EXTINF"):
            close_entry()
            stats["entries"] += 1
            in_entry = True
            continue
        if is_stream_line(s):
            if in_entry:
                current_has_url = True
                current_url_count += 1
            continue
        if s.startswith("#"):
            continue
        stats["plain_invalid_lines"] += 1
    close_entry()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and validate a dhanytv M3U playlist")
    parser.add_argument("playlist", help="Path to the M3U playlist")
    parser.add_argument("--write", action="store_true", help="Overwrite playlist with cleaned output")
    parser.add_argument("--output", help="Write cleaned output to this path instead of stdout/overwrite")
    parser.add_argument("--ott-output", help="Also write HLS/non-DRM OTT-friendly playlist to this path")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if cleaned playlist still has structural errors")
    args = parser.parse_args()

    path = Path(args.playlist)
    original = path.read_text(encoding="utf-8", errors="replace")
    header, raw_items, parse_stats = extract_items(original.splitlines())
    items, clean_stats = clean_items(raw_items)
    cleaned = render(header, items)
    validation = validate_text(cleaned)

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
