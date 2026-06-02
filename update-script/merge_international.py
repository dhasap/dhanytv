#!/usr/bin/env python3
"""Merge international channels from iptv-org/iptv into dhanytv.m3u.

Downloads country-specific playlists, filters duplicates, and appends
curated channels to the existing dhanytv playlist.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

# ── Target countries ──────────────────────────────────────────
# (country_code, group_name, max_channels)
# Countries already in dhanytv: ID, MY, SG, CN, KR (partial), BN
TARGET_COUNTRIES = [
    ("jp", "Japan", 30),
    ("kr", "Korea", 20),
    ("in", "India", 25),
    ("th", "Thailand", 15),
    ("ph", "Philippines", 10),
    ("vn", "Vietnam", 10),
    ("tr", "Turkey", 20),
    ("pk", "Pakistan", 10),
    ("bd", "Bangladesh", 8),
    ("ir", "Iran", 8),
    ("ae", "UAE & Arab", 15),
    ("eg", "Egypt", 10),
    ("sa", "Saudi Arabia", 8),
    ("ng", "Nigeria", 10),
    ("za", "South Africa", 8),
    ("ke", "Kenya", 5),
    # iptv-org uses the exceptional country slug "uk" for United Kingdom.
    ("uk", "United Kingdom", 20),
    ("us", "United States", 25),
    ("de", "Germany", 15),
    ("fr", "France", 15),
    ("es", "Spain", 10),
    ("it", "Italy", 10),
    ("br", "Brazil", 20),
    ("mx", "Mexico", 15),
    ("ar", "Argentina", 10),
    ("co", "Colombia", 8),
    ("ru", "Russia", 15),
]

IPTV_ORG_BASE = "https://iptv-org.github.io/iptv/countries"
RE_ATTR = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')


def download_playlist(country_code: str) -> list[str]:
    """Download country playlist from iptv-org."""
    url = f"{IPTV_ORG_BASE}/{country_code}.m3u"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0 and result.stdout.strip():
            if not result.stdout.lstrip().startswith("#EXTM3U"):
                print(f"  WARNING: {country_code} did not return an M3U playlist")
                return []
            return result.stdout.splitlines()
    except Exception as e:
        print(f"  WARNING: Failed to download {country_code}: {e}")
    return []


def parse_m3u(lines: list[str]) -> list[dict]:
    """Parse M3U lines into channel entries."""
    channels = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            attrs = dict(RE_ATTR.findall(line))
            name = line.rsplit(",", 1)[-1].strip() if "," in line else "Channel"
            # Get URL (next non-comment, non-empty line)
            url = ""
            props = []
            for j in range(i + 1, min(i + 5, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith("#EXTVLCOPT") or next_line.startswith("#KODIPROP"):
                    props.append(next_line)
                elif next_line.startswith("http") and not next_line.startswith("#"):
                    url = next_line
                    break
                elif next_line == "":
                    continue
            if url:
                channels.append({
                    "extinf": line,
                    "url": url,
                    "props": props,
                    "tvg_id": attrs.get("tvg-id", ""),
                    "tvg_name": attrs.get("tvg-name", ""),
                    "tvg_logo": attrs.get("tvg-logo", ""),
                    "name": name,
                })
        i += 1
    return channels


def read_existing_tvg_ids(m3u_path: Path) -> set[str]:
    """Read existing tvg-ids and names from dhanytv.m3u."""
    existing = set()
    if not m3u_path.exists():
        return existing
    for line in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#EXTINF"):
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m and m.group(1):
                existing.add(m.group(1).strip())
            # Also add channel name for dedup
            if "," in line:
                name = line.rsplit(",", 1)[-1].strip().lower()
                existing.add(f"name:{name}")
    return existing


def read_existing_urls(m3u_path: Path) -> set[str]:
    """Read existing stream URLs for dedup."""
    urls = set()
    if not m3u_path.exists():
        return urls
    for line in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("http") and not line.startswith("#"):
            urls.add(line)
    return urls


def is_duplicate(channel: dict, existing_ids: set[str], existing_urls: set[str],
                 added_names: set[str]) -> bool:
    """Check if channel already exists."""
    # By URL
    if channel["url"] in existing_urls:
        return True
    # By tvg-id
    if channel["tvg_id"] and channel["tvg_id"] in existing_ids:
        return True
    # By name (case-insensitive)
    name_lower = channel["name"].lower()
    if f"name:{name_lower}" in existing_ids:
        return True
    if name_lower in added_names:
        return True
    return False


def is_quality_channel(channel: dict) -> bool:
    """Filter out low-quality or problematic channels."""
    name = channel["name"].lower()
    url = channel["url"].lower()

    # Skip [Not 24/7] channels
    if "[not 24/7]" in name:
        return False
    # Skip test channels
    if "test" in name and len(name) < 15:
        return False
    # Skip channels with no logo (often low quality)
    # Actually, keep them — some good channels lack logos
    # Skip very low resolution
    if "(240p)" in name or "(360p)" in name:
        return False
    # Skip radio channels (we already have enough)
    if "radio" in name.lower() and "tv" not in name.lower():
        return False
    # Skip channels pointing to obviously dead CDNs
    if "example.com" in url or "localhost" in url:
        return False
    return True


def format_group_entry(channel: dict, group_name: str) -> str:
    """Format channel entry with proper group-title."""
    extinf = channel["extinf"]

    # Update or add group-title
    if 'group-title="' in extinf:
        extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', extinf)
    else:
        # Add group-title before the comma
        if "," in extinf:
            parts = extinf.rsplit(",", 1)
            extinf = f'{parts[0]} group-title="{group_name}",{parts[1]}'

    # Remove quality suffix like (1080p), (720p) from display name for cleaner look
    # Actually keep it — it's useful info

    lines = []
    # Add props
    for prop in channel["props"]:
        lines.append(prop)
    lines.append(extinf)
    lines.append(channel["url"])
    return "\n".join(lines)


def merge_international(m3u_path: Path, output_path: Path | None = None) -> dict:
    """Main merge function."""
    if output_path is None:
        output_path = m3u_path

    existing_ids = read_existing_tvg_ids(m3u_path)
    existing_urls = read_existing_urls(m3u_path)
    added_names: set[str] = set()

    # Read existing content
    existing_content = m3u_path.read_text(encoding="utf-8", errors="replace")

    # Find insertion point (before the last line or after Internet Radio)
    lines = existing_content.rstrip().split("\n")

    # Find the last section divider or end
    insert_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("# <") or lines[i].strip() == "":
            insert_idx = i
        else:
            break

    new_entries = []
    stats = {}

    for country_code, group_name, max_channels in TARGET_COUNTRIES:
        print(f"  Downloading {group_name} ({country_code})...")
        raw_lines = download_playlist(country_code)
        if not raw_lines:
            stats[country_code] = {"downloaded": 0, "added": 0}
            continue

        channels = parse_m3u(raw_lines)
        added = 0

        for ch in channels:
            if added >= max_channels:
                break
            if not is_quality_channel(ch):
                continue
            if is_duplicate(ch, existing_ids, existing_urls, added_names):
                continue

            entry = format_group_entry(ch, group_name)
            new_entries.append(entry)
            added_names.add(ch["name"].lower())
            existing_urls.add(ch["url"])
            if ch["tvg_id"]:
                existing_ids.add(ch["tvg_id"])
            added += 1

        stats[country_code] = {"downloaded": len(channels), "added": added}
        print(f"    {len(channels)} downloaded, {added} added")

    if not new_entries:
        print("No new channels to add.")
        return {"total_added": 0, "by_country": stats}

    # Insert new entries
    # Add section divider
    divider = "\n# <============================================================== International Channels ==================================================>\n"
    lines.insert(insert_idx, divider)

    for i, entry in enumerate(new_entries):
        for j, line in enumerate(entry.split("\n")):
            lines.insert(insert_idx + 1 + i * 4 + j, line)  # Approximate spacing

    # Actually, let's just append to the end (simpler, less error-prone)
    output_lines = existing_content.rstrip().split("\n")

    # Add blank line + divider
    output_lines.append("")
    output_lines.append("# <============================================================== International Channels ==================================================>")
    output_lines.append("")

    for entry in new_entries:
        output_lines.append("")
        for line in entry.split("\n"):
            output_lines.append(line)

    output_lines.append("")

    output_path.write_text("\n".join(output_lines), encoding="utf-8")

    total_added = sum(s["added"] for s in stats.values())
    return {"total_added": total_added, "by_country": stats}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Merge international channels from iptv-org")
    parser.add_argument("--ci", action="store_true", help="CI mode: never fail, exit 0 even on errors")
    args = parser.parse_args()

    m3u_path = Path("dhanytv.m3u")

    if not m3u_path.exists():
        print(f"ERROR: {m3u_path} not found")
        return 0 if args.ci else 1

    print("=== Merging international channels from iptv-org ===")
    print(f"Target: {len(TARGET_COUNTRIES)} countries")
    print()

    try:
        result = merge_international(m3u_path)
    except Exception as e:
        print(f"ERROR: merge failed: {e}")
        return 0 if args.ci else 1

    print()
    print("=== Merge Summary ===")
    print(f"Total channels added: {result['total_added']}")
    print()
    print("By country:")
    for code, s in result["by_country"].items():
        status = f"{s['added']}/{s['downloaded']}" if s["downloaded"] > 0 else "FAILED"
        print(f"  {code}: {status}")

    # Count total channels
    total = sum(1 for line in m3u_path.read_text().splitlines() if line.strip().startswith("#EXTINF"))
    print(f"\nTotal channels in playlist: {total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
