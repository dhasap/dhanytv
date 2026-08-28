#!/usr/bin/env python3
"""Fix shifted ClearKey license keys in dhanytv.m3u.

Downloads source playlists from the configured URLs (PLAYLIST_SOURCE /
PLAYLIST_SOURCE_2), extracts correct ClearKey mappings, and corrects any
shifted keys in the generated playlist.

Usage:
  python3 fix_clearkeys.py dhanytv.m3u [--dry-run]
  FIX_CLEARKEY_URLS="url1|url2" python3 fix_clearkeys.py dhanytv.m3u

Environment:
  FIX_CLEARKEY_URLS  Pipe-separated source URLs (overrides defaults)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

# Default source URLs — same as PLAYLIST_SOURCE / PLAYLIST_SOURCE_2 secrets.
# Overridden by FIX_CLEARKEY_URLS env var at runtime.
DEFAULT_URLS = [
    "https://raw.githubusercontent.com/Bluestraveller13/super-duper-spork/refs/heads/main/KITKATJOSS",
    "https://bit.ly/4rSRTpn",
]


def download_source(url: str, tmp_dir: str) -> str | None:
    """Download a source M3U from URL, return path to temp file or None."""
    try:
        path = os.path.join(tmp_dir, f"src_{hash(url) & 0xFFFF:04x}.m3u")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())
        # Validate it looks like M3U (skip blank/CRLF lines at start)
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    if line.startswith(("#EXTM3U", "#EXTINF")):
                        return path
                    break
    except Exception:
        pass
    return None


def load_correct_keys(source_paths: list[str]) -> dict[str, str]:
    """Load ClearKey mappings from downloaded source files."""
    correct: dict[str, str] = {}
    for fpath in source_paths:
        try:
            with open(fpath, encoding="utf-8") as fh:
                lines = fh.readlines()
            ck = ""
            for line in lines:
                line = line.strip()
                if "license_key=" in line:
                    tail = line.split("license_key=", 1)[1]
                    if "http" not in tail[:10]:
                        ck = tail.strip()
                if line.startswith("#EXTINF") and ck:
                    m = re.search(r",(.+)$", line)
                    if m:
                        name = m.group(1).strip()
                        if name not in correct:
                            correct[name] = ck
        except Exception:
            continue
    return correct


def fix_keys(playlist_path: Path, correct_keys: dict[str, str], dry_run: bool = False) -> int:
    """Fix wrong ClearKey keys by matching channel names."""
    content = playlist_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    fixed = 0

    for i, line in enumerate(lines):
        if "license_key=" not in line:
            continue
        tail = line.split("license_key=", 1)[1]
        if "http" in tail[:10]:
            continue

        # Find the NEXT EXTINF to get channel name
        for j in range(i + 1, min(i + 10, len(lines))):
            if lines[j].strip().startswith("#EXTINF"):
                m = re.search(r",(.+)$", lines[j])
                if m:
                    name = m.group(1).strip()
                    current_key = tail.strip()
                    if name in correct_keys and current_key != correct_keys[name]:
                        lines[i] = line.replace(current_key, correct_keys[name])
                        fixed += 1
                break

    if fixed > 0 and not dry_run:
        playlist_path.write_text("\n".join(lines), encoding="utf-8")

    return fixed


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix shifted ClearKey keys")
    parser.add_argument("playlist", help="Path to M3U playlist")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    args = parser.parse_args()

    playlist_path = Path(args.playlist)

    # Get source URLs from env or defaults
    urls_env = os.environ.get("FIX_CLEARKEY_URLS", "")
    if urls_env:
        urls = [u.strip() for u in urls_env.split("|") if u.strip()]
    else:
        urls = DEFAULT_URLS

    # Download sources to temp directory
    source_paths = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for url in urls:
            path = download_source(url, tmp_dir)
            if path:
                source_paths.append(path)
                print(f"  Downloaded source: {url[:60]}...")
            else:
                print(f"  WARNING: Failed to download {url[:60]}...", file=sys.stderr)

        if not source_paths:
            print("ERROR: No source files downloaded", file=sys.stderr)
            return 1

        correct_keys = load_correct_keys(source_paths)

    if not correct_keys:
        print("ERROR: No source keys found", file=sys.stderr)
        return 1

    fixed = fix_keys(playlist_path, correct_keys, args.dry_run)
    print(f"Fixed {fixed} ClearKey entries (source_keys={len(correct_keys)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
