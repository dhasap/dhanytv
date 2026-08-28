#!/usr/bin/env python3
"""Fix shifted ClearKey license keys in dhanytv.m3u.

The cleanup pipeline sometimes shifts KODIPROP license_key lines by 1+ positions
when processing complex source formats. This script corrects the shifts by
comparing each entry's key against the known correct keys from the source files.

Usage: python3 fix_clearkeys.py dhanytv.m3u [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def load_correct_keys(source_dir: Path) -> dict[str, str]:
    """Load ClearKey mappings from source files."""
    correct: dict[str, str] = {}
    for fname in ["source1.m3u", "source2.m3u"]:
        fpath = source_dir / fname
        if not fpath.exists():
            continue
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
    source_dir = Path(__file__).parent  # update-script/

    correct_keys = load_correct_keys(source_dir)
    if not correct_keys:
        print("ERROR: No source keys found", file=sys.stderr)
        return 1

    fixed = fix_keys(playlist_path, correct_keys, args.dry_run)
    print(f"Fixed {fixed} ClearKey entries (source_keys={len(correct_keys)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
