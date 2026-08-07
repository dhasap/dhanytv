#!/usr/bin/env python3
"""Generate a dedicated SS IPTV variant of the dhanytv playlist.

SS IPTV (Samsung/LG Smart TV, Android, iOS) is a strict M3U consumer:
  - It does NOT understand #KODIPROP (Kodi) or #EXTHTTP (player-specific JSON).
  - Line-noise like that can make some parser builds skip/fumble a channel.

To maximise the chance header-protected channels still play, the script encodes
any header hints in the two forms the IPTV ecosystem actually reads:
  1. As `http-user-agent` / `http-referrer` / `http-origin` attributes *inside*
     the #EXTINF line (the iptv-org convention).
  2. As `|User-Agent=...|Referer=...|Origin=...` suffixes on the stream URL.
#EXTVLCOPT / #KODIPROP / #EXTHTTP lines are dropped.

All 741 channels of the source OTT playlist are kept. No DRM/DASH is present in
the OTT source, so everything here is HLS-only and format-safe for SS IPTV.

Usage:
  python3 update-script/make_ssiptv.py [--input dhanytv-ott.m3u] [--output dhanytv-ssiptv.m3u]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cleanup_playlist as cp  # noqa: E402

DEFAULT_SOURCE = "https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml"

_UA = re.compile(r"#EXTVLCOPT:http-user-agent=(.+)$")
_REFR = re.compile(r"#EXTVLCOPT:http-referrer=(.+)$")
_ORIG = re.compile(r"#EXTVLCOPT:http-origin=(.+)$")

# Existing header attrs already in EXTINF (from upstream) — don't duplicate.
_EXISTING_ATTR = re.compile(r'\s(?:http-user-agent|http-referrer|http-origin)="')
_STRIP_SUFFIX = re.compile(r"\|\s*(?:User-Agent|Referer|Origin|user-agent|referrer|origin)=", re.I)


def header_value(prop: str, rx: re.Pattern[str]) -> str | None:
    m = rx.search(prop)
    if not m:
        return None
    v = m.group(1).strip()
    return v if v else None


def collect_headers(entry: cp.Entry) -> dict[str, str]:
    headers: dict[str, str] = {}
    for prop in entry.props:
        for key, rx in (("User-Agent", _UA), ("Referer", _REFR), ("Origin", _ORIG)):
            if key not in headers:
                v = header_value(prop, rx)
                if v:
                    headers[key] = v
    return headers


def extend_extinf(extinf: str, headers: dict[str, str]) -> str:
    """Inject http-* header attributes into the #EXTINF line (iptv-org style)."""
    attr_map = {
        "User-Agent": ("http-user-agent", "http_user_agent"),
        "Referer": ("http-referrer", "http_referrer"),
        "Origin": ("http-origin", "http_origin"),
    }
    if not headers:
        return extinf
    # Insert before existing tvg-logo/group-title/name (right after tvg attributes,
    # but any position in EXTINF is fine). Append before the trailing channel name.
    comma = extinf.rfind(",")
    head = extinf[:comma]
    for key, val in headers.items():
        attr, _ = attr_map[key]
        if _EXISTING_ATTR.search(head) and re.search(rf'\s{re.escape(attr)}="', head):
            continue
        head += f' {attr}="{val}"'
    name = extinf[comma:]
    return head + name


def build_suffix(headers: dict[str, str]) -> str:
    parts = []
    if headers.get("User-Agent"):
        parts.append(f"User-Agent={headers['User-Agent']}")
    if headers.get("Referer"):
        parts.append(f"Referer={headers['Referer']}")
    if headers.get("Origin"):
        parts.append(f"Origin={headers['Origin']}")
    return "|".join(parts)


def transform_url(url: str, suffix: str) -> str:
    url_clean = _STRIP_SUFFIX.sub("|", url)
    url_clean = re.sub(r"\|{2,}", "|", url_clean).rstrip("|")
    if suffix:
        sep = "|" if not url_clean.endswith("|") else ""
        return url_clean + sep + suffix
    return url_clean


def to_ssiptv_lines(items: list[str | cp.Entry]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, str):
            lines.append(item)
            continue
        headers = collect_headers(item)
        suffix = build_suffix(headers)
        urls = [transform_url(u, suffix) for u in item.urls]
        extinf = extend_extinf(item.extinf, headers)
        lines.append(extinf)
        for u in urls:
            lines.append(u)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="dhanytv-ott.m3u")
    ap.add_argument("--output", default="dhanytv-ssiptv.m3u")
    ap.add_argument("--epg-url", default=DEFAULT_SOURCE)
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}")
        return 1

    text = in_path.read_text(encoding="utf-8").splitlines()
    header, items, stats = cp.extract_items(text)
    header_new = "#EXTM3U url-tvg=\"" + args.epg_url + "\""

    lines = to_ssiptv_lines(items)
    out_lines = [header_new, ""] + lines + [""]
    out_text = "\n".join(out_lines).rstrip() + "\n"

    out_path = Path(args.output)
    out_path.write_text(out_text, encoding="utf-8")

    total = sum(1 for i in items if isinstance(i, cp.Entry))
    suff = sum(1 for l in lines if l.startswith("http") and "|" in l)
    print(f"Wrote {out_path}")
    print(f"  total entries : {total}")
    print(f"  EXTINF lines  : {sum(1 for l in lines if l.startswith('#EXTINF'))}")
    print(f"  URL lines     : {sum(1 for l in lines if l.startswith('http'))}")
    print(f"  URL w/ suffix : {suff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
