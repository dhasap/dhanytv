#!/usr/bin/env python3
"""Terapkan sumber pilihan (protected_channels.json) setelah semua merge.

Pipeline auto-update punya beberapa langkah yang saling menimpa URL dengan
kembaran astatv. Skrip ini dijalankan setelah merge dan sebelum cleanup supaya
sumber yang sudah diuji hidup (dens.tv, medcom, anixa, detik, cnnindonesia,
rtvstream, JTV) tidak dibalikkan oleh merge berikutnya.
"""
import argparse
import json
import os
import re
import sys

DEFAULT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'protected_channels.json')


def norm(s: str) -> str:
    s = (s or '').lower()
    s = re.sub(r'\([^)]*\)', ' ', s)
    s = re.sub(r'\b(hd|fhd|uhd|sd)\b', ' ', s)
    return re.sub(r'[^a-z0-9]+', '', s)


def attr(line: str, name: str):
    m = re.search(name + r'="([^"]*)"', line)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('playlist')
    ap.add_argument('--json', default=DEFAULT_JSON)
    ap.add_argument('--report')
    args = ap.parse_args()

    if not os.path.exists(args.json):
        print(f'protected: {args.json} tidak ada, dilewati')
        return 0

    prot = json.load(open(args.json, encoding='utf-8'))
    by_id = {p['tvg_id'].lower(): p for p in prot if p.get('tvg_id')}
    by_name = {norm(p['name']): p for p in prot}

    lines = open(args.playlist, encoding='utf-8').read().splitlines()
    out, used, i = [], set(), 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF'):
            out.append(line)
            i += 1
            continue
        name = line.rsplit(',', 1)[-1].strip()
        tid = (attr(line, 'tvg-id') or '').lower()
        # nama dulu, baru tvg-id: id generik (mis. Nickelodeon.id) sering
        # dipakai varian lain (Nickelodeon Junior), jangan sampai ketuker
        p = by_name.get(norm(name)) or by_id.get(tid)
        block = [line]
        j = i + 1
        while j < len(lines) and lines[j].startswith('#'):
            if not lines[j].startswith('#EXTVLCOPT'):
                block.append(lines[j])
            j += 1
        url = lines[j] if j < len(lines) else ''
        if p and url.startswith('http'):
            for k, v in (p.get('headers') or {}).items():
                key = k.lower().replace('_', '-')
                if key in ('referer', 'referrer', 'http-referrer'):
                    key = 'referrer'
                elif key in ('user-agent', 'http-user-agent'):
                    key = 'user-agent'
                block.append(f'#EXTVLCOPT:http-{key}={v}')
            out.extend(block)
            out.append(p['url'])
            used.add(p['tvg_id'])
            i = j + 1
            continue
        out.extend(block)
        if url:
            out.append(url)
            i = j + 1
        else:
            i += 1

    missing = [p for p in prot if p['tvg_id'] not in used]
    for p in missing:
        out.append(
            f'#EXTINF:-1 tvg-id="{p["tvg_id"]}" tvg-name="{p["name"]}" '
            f'group-title="{p.get("group", "General")}",{p["name"]}'
        )
        for k, v in (p.get('headers') or {}).items():
            out.append(f'#EXTVLCOPT:http-{k}={v}')
        out.append(p['url'])

    # dedupe tvg-id: entri kedua dst kehilangan id agar EPG tidak tertukar
    seen, deduped = set(), []
    for line in out:
        if line.startswith('#EXTINF'):
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m and m.group(1):
                if m.group(1) in seen:
                    line = re.sub(r'\s*tvg-id="[^"]*"', '', line, count=1)
                else:
                    seen.add(m.group(1))
        deduped.append(line)
    out = deduped

    open(args.playlist, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    if args.report:
        json.dump({'patched': sorted(used), 'added': [p['tvg_id'] for p in missing]},
                  open(args.report, 'w'), indent=1)
    print(f'protected: {len(used)} dipatch, {len(missing)} ditambah')
    return 0


if __name__ == '__main__':
    sys.exit(main())
