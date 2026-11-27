#!/usr/bin/env python3
"""repair_playlist.py — buang / ganti entri mati berdasarkan hasil check_playlist.py.

Aturan:
  * status `geo/auth 403`, `geo 451`, `dash-seg`, `ok`  -> DIPERTAHANKAN
    (geo tidak bisa diuji dari VPS luar Indonesia; di jaringan user biasanya jalan)
  * status mati (404, dns, timeout, empty, 414, 5xx, 4xx lain)
      - kalau ada kembaran astatv di playlist yang statusnya `ok` -> URL diganti
      - kalau tidak ada -> entri dibuang
  * header #EXTVLCOPT/#KODIPROP dibuang saat URL diganti ke astatv (CORS terbuka)

Pakai:
    python3 update-script/repair_playlist.py dhanytv.m3u /tmp/full2.json --write --report /tmp/repair.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

KEEP_OK = {"ok", "geo/auth 403", "geo 451", "dash-seg"}
DEAD = {
    "404", "dns", "timeout", "timeout/refused", "empty", "error", "seg-kecil",
    "http 414", "http 400", "http 302", "http 200", "server 500", "server 502",
    "server 503", "server 504", "rate 429", "http 401", "http 405", "http 406",
}

SAFE_ONLY_DEAD = {
    "404", "empty", "seg-kecil", "http 414", "http 400", "http 302", "http 200",
    "server 500", "server 502", "server 503", "server 504", "http 405", "http 406",
}

ATTR_RE = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
AST_RE = re.compile(r"astatv(?:-api)?\.pages\.dev|astatv\.karaa\.web\.id", re.I)


def norm(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"\([^)]*\)", " ", n)
    n = re.sub(r"\b(fhd|uhd|hd|sd|4k|8k|alt|backup|mirror)\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


def split_blocks(text: str) -> list[str]:
    out, cur = [], []
    for line in text.splitlines():
        if line.startswith("#EXTINF"):
            if cur:
                out.append(cur)
            cur = [line]
        elif cur is not None and (cur or line.strip()):
            if line.startswith("#EXTM3U"):
                continue
            cur.append(line)
    if cur:
        out.append(cur)
    return ["\n".join(b).strip("\n") for b in out if any(l.startswith("#EXTINF") for l in b)]


def block_url(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def block_name(block: str) -> str:
    first = block.splitlines()[0]
    parts = first.rsplit(",", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def block_attrs(block: str) -> dict:
    return dict(ATTR_RE.findall(block.splitlines()[0]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist")
    ap.add_argument("report_json")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--report", default=None, help="ringkasan aksi ke JSON")
    ap.add_argument("--safe-only", action="store_true",
                    help="hanya buang status yang pasti mati (404/empty/4xx/5xx); "
                         "timeout & DNS dibiarkan (bisa transient)")
    ap.add_argument("--max-drop-pct", type=int, default=60,
                    help="batalkan (exit 2) kalau entri yang dibuang > N%% dari yang diuji; 0 = mati")
    args = ap.parse_args()

    text = open(args.playlist, encoding="utf-8", errors="replace").read()
    results = json.load(open(args.report_json, encoding="utf-8"))

    by_url: dict[str, dict] = {}
    for r in results:
        by_url[r["url"].strip()] = r

    # indeks kembaran astatv yang sehat
    astatv_ok: dict[str, str] = {}
    for r in results:
        if not AST_RE.search(r["url"]):
            continue
        if r["status"] != "ok":
            continue
        if r.get("tvg_id"):
            astatv_ok.setdefault("id:" + r["tvg_id"].lower(), r["url"])
        astatv_ok.setdefault("n:" + norm(r["name"]), r["url"])

    kept, dropped, replaced = [], [], []
    drop_stat: Counter = Counter()

    for block in split_blocks(text):
        url = block_url(block)
        res = by_url.get(url)
        if not res:
            kept.append(block)          # entri baru / tidak teruji
            continue
        st = res["status"]
        if st in KEEP_OK:
            kept.append(block)
            continue
        dead_set = SAFE_ONLY_DEAD if args.safe_only else DEAD
        if st not in dead_set:
            kept.append(block)          # status tak dikenal / transient -> dibiarkan
            continue

        attrs = block_attrs(block)
        name = block_name(block)
        twin = astatv_ok.get("id:" + (attrs.get("tvg-id", "") or "").lower()) or astatv_ok.get("n:" + norm(name))

        if twin:
            head = block.splitlines()[0]
            new_block = f"{head}\n{twin}"
            replaced.append({"name": name, "from": url, "to": twin, "status": st})
            kept.append(new_block)
        else:
            drop_stat[st] += 1
            dropped.append({"name": name, "url": url, "status": st, "detail": res.get("detail", "")})

    out = "#EXTM3U\n" + "\n\n".join(kept) + "\n"
    print("== repair ==")
    print(f"  dipertahankan: {len(kept)}")
    print(f"  diganti ke astatv: {len(replaced)}")
    print(f"  dibuang: {len(dropped)}  {drop_stat.most_common()}")
    print(f"  total: {text.count('#EXTINF')} -> {out.count('#EXTINF')}")

    # Guard: kalau hampir semua yang diuji mati, kemungkinan besar checker-nya
    # yang gagal (DNS/network), bukan channel-nya. Jangan tulis apa pun.
    tested = len(kept) + len(replaced) + len(dropped)
    if args.max_drop_pct > 0 and tested:
        pct = (len(dropped) * 100) // tested
        if pct > args.max_drop_pct:
            print(f"ABORT: {len(dropped)}/{tested} entri ({pct}%) akan dibuang "
                  f"> batas {args.max_drop_pct}%. File TIDAK diubah.")
            return 2
    if not kept:
        print("ABORT: hasil kosong (0 entri). File TIDAK diubah.")
        return 2

    if args.write or args.out:
        target = args.out or args.playlist
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(out)
        os.replace(tmp, target)
        print(f"ditulis ke {target}")
    else:
        print("(dry-run)")

    if args.report:
        json.dump({"replaced": replaced, "dropped": dropped,
                   "dropped_by_status": drop_stat.most_common()},
                  open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"laporan: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
