#!/usr/bin/env python3
"""Inject curated extra channels into dhanytv.m3u.

The weekly auto-update REPLACES dhanytv.m3u with a freshly downloaded source
(see merge_source.py). Any channel that is not in that source — World Cup feeds,
event channels, anything hand-added — would silently disappear every Monday.

This script re-injects the channels listed in update-script/extra_channels.m3u
right after the #EXTM3U header, so they always survive the weekly run. It is:
  - idempotent: an extra channel already present (same stream URL) is skipped,
    so running it twice will not duplicate entries;
  - non-destructive: it never removes existing channels;
  - safe in CI: with --ci it always exits 0 even if the extras file is missing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROP_PREFIXES = ("#EXTVLCOPT", "#KODIPROP", "#EXTGRP", "#EXTHTTP", "#EXT-X-")


def _is_url(line: str) -> bool:
    s = line.strip()
    return s.startswith(("http://", "https://", "rtmp://", "rtsp://", "plugin://", "pipe://"))


def parse_entries(lines: list[str]) -> tuple[list[str], list[dict]]:
    """Split extras into leading section dividers and channel entries.

    Returns (dividers, entries). Each entry is a dict with 'props' (list),
    'extinf' (str) and 'url' (str). Instructional comments (lines that start
    with '#' but are not props, EXTINF, or a '# <...>' divider) are dropped.
    """
    dividers: list[str] = []
    entries: list[dict] = []
    pending_props: list[str] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.get("url"):
            entries.append(current)
        current = None

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# <") and stripped.endswith(">"):
            dividers.append(line)
            continue
        if stripped.startswith("#EXTINF"):
            flush()
            current = {"props": pending_props, "extinf": line, "url": ""}
            pending_props = []
            continue
        if stripped.startswith(PROP_PREFIXES):
            if current is not None and not current["url"]:
                current["props"].append(line)
            else:
                pending_props.append(line)
            continue
        if _is_url(line):
            if current is not None and not current["url"]:
                current["url"] = stripped
                flush()
            continue
        # Any other comment / instructional line is ignored.
    flush()
    return dividers, entries


def existing_urls(text: str) -> set[str]:
    urls = set()
    for line in text.splitlines():
        if _is_url(line):
            urls.add(line.strip())
    return urls


def inject(target: Path, extras: Path) -> dict:
    target_text = target.read_text(encoding="utf-8", errors="replace")
    extras_lines = extras.read_text(encoding="utf-8", errors="replace").splitlines()

    dividers, entries = parse_entries(extras_lines)
    # Inject at the TOP of the playlist (just under the header). We intentionally
    # do NOT skip channels that also exist in the source: cleanup_playlist.py
    # dedupes by (tvg-id, url) keeping the FIRST occurrence, so a curated copy
    # placed here wins and the channel is relocated into its curated group.
    seen_urls: set[str] = set()

    block: list[str] = []
    for div in dividers:
        block.append("")
        block.append(div)
    added = 0
    skipped = 0
    for entry in entries:
        if entry["url"] in seen_urls:
            skipped += 1
            continue
        block.append("")
        block.extend(entry["props"])
        block.append(entry["extinf"])
        block.append(entry["url"])
        seen_urls.add(entry["url"])
        added += 1

    if added == 0:
        return {"added": 0, "skipped": skipped}

    lines = target_text.splitlines()
    # Find the #EXTM3U header so we can inject directly beneath it.
    header_idx = next((i for i, l in enumerate(lines) if l.startswith("#EXTM3U")), -1)
    insert_at = header_idx + 1 if header_idx >= 0 else 0
    new_lines = lines[:insert_at] + block + lines[insert_at:]
    target.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    return {"added": added, "skipped": skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject curated extra channels into dhanytv.m3u")
    parser.add_argument("--target", default="dhanytv.m3u", help="Target playlist (default: dhanytv.m3u)")
    parser.add_argument("--extras", default="update-script/extra_channels.m3u",
                        help="Extra channels file (default: update-script/extra_channels.m3u)")
    parser.add_argument("--ci", action="store_true", help="CI mode: never fail, exit 0 even on errors")
    args = parser.parse_args()

    target = Path(args.target)
    extras = Path(args.extras)

    if not target.exists():
        print(f"ERROR: {target} not found")
        return 0 if args.ci else 1
    if not extras.exists():
        print(f"INFO: {extras} not found, nothing to inject")
        return 0

    try:
        result = inject(target, extras)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: inject failed: {e}")
        return 0 if args.ci else 1

    print(f"=== Extra channels merge: {result['added']} injected, {result['skipped']} already present ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
