#!/usr/bin/env python3
"""normalize_groups.py — rapikan nama grup playlist dhanytv.

- Gabungkan grup duplikat/sinonim (Sports Channels + Sports Indo -> Sports, dst).
- Buang grup sampah (shortener seperti "1 bit.ly", "Sports Indo").
- Buang entri yang URL-nya shortener (bit.ly, s.id, tinyurl, dll).

Idempotent: menjalankan dua kali tidak mengubah hasil.

Pakai:
    python3 update-script/normalize_groups.py dhanytv.m3u            # laporan saja
    python3 update-script/normalize_groups.py dhanytv.m3u --write    # tulis ulang
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

GROUP_MAP = {
    # olahraga
    "Sports Channels": "Sports",
    "Sports Indo": "Sports",
    "Sport": "Sports",
    # berita
    "News Channels": "News",
    "News Channel": "News",
    # anak
    "Kids Channels": "Kids",
    # dokumenter
    "Documentary Channels": "Documentary",
    "Knowledge and Documentary": "Documentary",
    # hiburan
    "Entertainment Channels": "Entertainment",
    "Entertainment & LifeStyle": "Entertainment",
    "Entertainment": "Entertainment",
    "TV HIBURAN": "Entertainment",
    "MOVIES & ENTERTAINMENT": "Entertainment",
    "Comedy Channels": "Entertainment",
    # film
    "Movies Channels": "Premium Movies",
    # musik
    "Music Channels": "Music",
    # lokal
    "TV Lokal": "Local Channels",
    "Nasional": "Local Channels",
    # religi
    "Christian Channels": "Religious",
    "Religious Channels": "Religious",
    # negara / wilayah
    "Italy Channels": "Italy",
    "South Korea": "Korea",
    "Mediacorp Singapore": "Singapore",
    # lain-lain
    "Auto / Motor / Otomotif Channels": "Auto / Motor",
    "Animation / Anime Channels": "Animation & Anime",
    "Series Channels": "Series",
    "Family Channels": "Family",
    "General Channels": "General",
}

# Grup yang memang sampah — dibuang seluruhnya.
DROP_GROUPS_DEFAULT = {"Sports Indo", "1 bit.ly"}

SHORTENER_RE = re.compile(
    r"^https?://(?:www\.)?(?:bit\.ly|bitly\.com|tinyurl\.com|s\.id|t\.co|goo\.gl|"
    r"is\.gd|ow\.ly|rb\.gy|shorturl\.at|cutt\.ly|rebrand\.ly|tiny\.one|shorte\.st)\b",
    re.I,
)

GROUPS_RE = re.compile(r'group-title="([^"]*)"')


def is_junk_group(name: str, extra_drop: set[str]) -> bool:
    low = (name or "").strip().lower()
    if not low:
        return False
    if name in extra_drop:
        return True
    if "bit.ly" in low or low.startswith("1 bit"):
        return True
    return False


def split_blocks(text: str) -> list[str]:
    """Pisahkan playlist menjadi blok: komentar/EXTINF + URL + baris kosong."""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.startswith("#EXTINF"):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append(cur)
    return ["\n".join(b) for b in blocks]


def normalize(text: str, extra_drop: set[str]) -> tuple[str, Counter, Counter, list[str]]:
    header = "#EXTM3U"
    stat_map: Counter = Counter()
    stat_drop: Counter = Counter()
    dropped: list[str] = []

    out_blocks: list[str] = []
    for block in split_blocks(text):
        m = GROUPS_RE.search(block)
        group = m.group(1) if m else ""
        url = ""
        for line in block.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                url = s
                break

        if is_junk_group(group, extra_drop):
            stat_drop[f"grup sampah: {group}"] += 1
            dropped.append(block.splitlines()[0][:110])
            continue
        if url and SHORTENER_RE.match(url):
            stat_drop["url shortener"] += 1
            dropped.append(block.splitlines()[0][:110])
            continue

        new_group = GROUP_MAP.get(group, group)
        if new_group != group:
            stat_map[f"{group} -> {new_group}"] += 1
            block = block.replace(f'group-title="{group}"', f'group-title="{new_group}"', 1)
        out_blocks.append(block.strip("\n"))

    body = "\n\n".join(out_blocks)
    return header + "\n" + body + "\n", stat_map, stat_drop, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--write", action="store_true", help="simpan kembali ke file")
    ap.add_argument("--out", default=None, help="tulis ke path lain")
    ap.add_argument("--drop-group", action="append", default=[], help="grup tambahan yang dibuang")
    args = ap.parse_args()

    try:
        text = open(args.path, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        print(f"ERROR: {args.path} tidak ada", file=sys.stderr)
        return 1

    extra = set(DROP_GROUPS_DEFAULT) | set(args.drop_group)
    new_text, stat_map, stat_drop, dropped = normalize(text, extra)

    before = text.count("#EXTINF")
    after = new_text.count("#EXTINF")

    print("== normalisasi grup ==")
    for k, v in stat_map.most_common():
        print(f"  {v:4d}  {k}")
    if stat_drop:
        print("== entri dibuang ==")
        for k, v in stat_drop.most_common():
            print(f"  {v:4d}  {k}")
    print(f"entri: {before} -> {after} (buang {before - after})")

    if args.write or args.out:
        target = args.out or args.path
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        print(f"ditulis ke {target}")
    else:
        print("(dry-run — tambahkan --write untuk menyimpan)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
