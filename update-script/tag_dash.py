#!/usr/bin/env python3
"""tag_dash.py — tandai entri yang sebenarnya DASH tapi URL-nya berakhiran .m3u8.

Beberapa sumber (astatv) menyajikan MPD di balik path .m3u8. Tanpa penanda,
player menganggapnya HLS dan gagal ("nggak bisa play"), dan varian OTT ikut kotor.

Script ini HEAD setiap URL astatv; kalau content-type-nya DASH, entri diberi
    #KODIPROP:inputstream.adaptive.manifest_type=mpd
sehingga:
  * Kodi / VLC / OTT Navigator memakai parser DASH
  * cleanup_playlist.py tahu entri ini DASH -> tidak masuk dhanytv-ott.m3u

Pakai:
    python3 update-script/tag_dash.py dhanytv.m3u --write
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import re
import ssl
import sys
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36"
DASH_PROP = "#KODIPROP:inputstream.adaptive.manifest_type=mpd"
HLS_PROP = "#KODIPROP:inputstream.adaptive.manifest_type=hls"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def head_ct(url: str, timeout: float = 12.0) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return (r.headers.get("Content-Type") or "").lower()
    except Exception:
        return ""


def blocks(text: str) -> list[str]:
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith("#EXTINF"):
            if cur:
                out.append(cur)
            cur = [line]
        elif cur is not None:
            if line.startswith("#EXTM3U"):
                continue
            if cur or line.strip():
                cur.append(line)
    if cur:
        out.append(cur)
    return ["\n".join(b).strip("\n") for b in out if any(l.startswith("#EXTINF") for l in b)]


def url_of(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--host", default="astatv-api.pages.dev", help="hanya proses host ini")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    text = open(args.playlist, encoding="utf-8", errors="replace").read()
    parts = blocks(text)

    targets = {}
    for b in parts:
        u = url_of(b)
        if args.host in u and u.lower().split("?")[0].endswith((".m3u8", ".m3u")):
            targets[u] = True

    print(f"cek {len(targets)} URL {args.host} …", flush=True)
    dash = set()
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for u, ct in zip(targets, pool.map(head_ct, list(targets))):
            if "dash" in ct:
                dash.add(u)
    print(f"terdeteksi DASH di balik .m3u8: {len(dash)}")

    out, tagged = [], 0
    for b in parts:
        u = url_of(b)
        if u in dash:
            lines = b.splitlines()
            head = lines[0]
            keep = [l for l in lines[1:] if not l.strip().startswith("#KODIPROP:inputstream.adaptive.manifest_type")]
            url_line = keep[-1]
            extra = [l for l in keep[:-1]]
            extra.append(DASH_PROP)
            new = "\n".join([head] + extra + [url_line])
            if DASH_PROP not in b:
                tagged += 1
            out.append(new)
        else:
            out.append(b)
    # buang duplikasi HLS_PROP yang bertentangan
    out = [b.replace(HLS_PROP + "\n", "") if url_of(b) in dash else b for b in out]

    new_text = "#EXTM3U\n" + "\n\n".join(out) + "\n"
    print(f"entri ditandai: {tagged} | total: {text.count('#EXTINF')} -> {new_text.count('#EXTINF')}")

    if args.write:
        open(args.playlist, "w", encoding="utf-8").write(new_text)
        print(f"ditulis ke {args.playlist}")
    else:
        print("(dry-run — tambahkan --write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
