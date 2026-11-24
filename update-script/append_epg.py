#!/usr/bin/env python3
"""Lengkapi epg.xml agar SETIAP tvg-id di playlist punya channel + programme.

Dipakai setelah generate_epg.py sebagai jaring pengaman: channel yang tidak
tercakup sumber EPG manapun tetap mendapat jadwal sintetis yang deterministik.
"""
import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

TITLES = {
    'Indonesia Channels': ['Berita Pagi', 'Sinetron Siang', 'Kabar Selebriti', 'Film Keluarga',
                           'Drama Seri', 'Talkshow Malam', 'Musik Indonesia', 'Documentary Nusantara'],
    'Sports': ['Live Match', 'Studio Analisis', 'Highlight', 'Klasemen & Berita', 'Replay Pertandingan',
               'Sports Center', 'Prewiew Liga', 'Magazine Olahraga'],
    'Sports Channels': ['Live Event', 'Analisa Pertandingan', 'Highlight', 'Berita Olahraga',
                        'Replay', 'Feature Atlet', 'Studio', 'Countdown'],
    'News Channel': ['Breaking News', 'Update Nasional', 'Liputan Khusus', 'Wawancara',
                     'Analisa Politik', 'Ekonomi Hari Ini', 'Internasional', 'Cuaca & Lalu Lintas'],
    'TVRI': ['Nusantara Hari Ini', 'Anak Ceria', 'Dokumenter Budaya', 'Dialog Publik',
             'Musik Tradisi', 'Kabar Daerah', 'Film Nasional', 'Kesehatan'],
    'Movies': ['Feature Film', 'Bioskop Malam', 'Film Klasik', 'Behind The Scene',
               'Short Movie', 'Movie Marathon', 'Animasi', 'Trailer Show'],
    'Kids': ['Kartun Pagi', 'Petualangan', 'Belajar Sambil Bermain', 'Kartun Siang',
             'Dongeng', 'Lagu Anak', 'Animasi CGI', 'Keluarga Ceria'],
    'Entertainment': ['Program Hiburan', 'Reality Show', 'Komedi', 'Musik Pilihan',
                      'Gaya Hidup', 'Kuliner', 'Traveling', 'Talkshow'],
}
DEFAULT = ['Program Reguler', 'Berita Singkat', 'Hiburan', 'Musik', 'Dokumenter',
           'Feature', 'Talkshow', 'Program Spesial']
TZ = timezone(timedelta(hours=7))


def assign_ids(path):
    """Isi tvg-id yang kosong dengan slug nama, unik, tanpa menabrak yang sudah ada."""
    lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    used = set()
    for l in lines:
        if l.startswith('#EXTINF'):
            m = re.search(r'tvg-id="([^"]*)"', l)
            if m and m.group(1).strip():
                used.add(m.group(1).strip())

    filled = 0
    out = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith('#EXTINF'):
            m = re.search(r'tvg-id="([^"]*)"', l)
            name = l.rsplit(',', 1)[-1].strip()
            cur = (m.group(1).strip() if m else '')
            if not cur:
                slug = re.sub(r'[^A-Za-z0-9]+', '', name).lower() or 'channel'
                cand = slug
                n = 2
                while cand in used:
                    cand = f'{slug}{n}'
                    n += 1
                used.add(cand)
                filled += 1
                if m:
                    l = l.replace(m.group(0), f'tvg-id="{cand}"', 1)
                else:
                    l = l.replace('#EXTINF:-1 ', f'#EXTINF:-1 tvg-id="{cand}" ', 1)
        out.append(l)
        i += 1
    open(path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print(f'tvg-id kosong diisi: {filled}')
    return filled


def norm_group(g):
    return (g or '').strip()


def progs_for(ch_id, group, start, hours=24):
    pool = TITLES.get(group, DEFAULT)
    seed = int(hashlib.md5(ch_id.encode()).hexdigest()[:8], 16)
    out = []
    t = start
    for i in range(hours):
        title = pool[(seed + i) % len(pool)]
        stop = t + timedelta(hours=1)
        out.append((title, t, stop))
        t = stop
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('playlist')
    ap.add_argument('epg')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--out')
    ap.add_argument('--assign-ids', action='store_true',
                    help='isi tvg-id yang kosong (turunan nama) lalu tulis playlist')
    a = ap.parse_args()

    if a.assign_ids:
        assign_ids(a.playlist)

    pl = open(a.playlist, encoding='utf-8', errors='replace').read()
    pl_lines = pl.splitlines()
    chans = []
    for i, l in enumerate(pl_lines):
        if not l.startswith('#EXTINF'):
            continue
        cid = (re.search(r'tvg-id="([^"]*)"', l) or [None, ''])[1].strip()
        name = l.rsplit(',', 1)[-1].strip()
        grp = (re.search(r'group-title="([^"]*)"', l) or [None, ''])[1].strip()
        logo = (re.search(r'tvg-logo="([^"]*)"', l) or [None, ''])[1].strip()
        if cid:
            chans.append({'id': cid, 'name': name, 'group': grp, 'logo': logo})

    seen = set()
    uniq = []
    for c in chans:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        uniq.append(c)

    tree = ET.parse(a.epg)
    root = tree.getroot()
    have = {ch.get('id') for ch in root.findall('channel')}
    has_prog = set()
    for p in root.findall('programme'):
        has_prog.add(p.get('channel'))

    now = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=6)

    added_ch, added_pr = 0, 0
    for c in uniq:
        if c['id'] not in have:
            el = ET.SubElement(root, 'channel', {'id': c['id']})
            ET.SubElement(el, 'display-name', {'lang': 'id'}).text = c['name']
            if c['logo']:
                ET.SubElement(el, 'icon', {'src': c['logo']})
            added_ch += 1
        if c['id'] in has_prog:
            continue
        for title, s, e in progs_for(c['id'], norm_group(c['group']), start, 24):
            pe = ET.SubElement(root, 'programme', {
                'start': s.strftime('%Y%m%d%H%M%S') + ' +0700',
                'stop': e.strftime('%Y%m%d%H%M%S') + ' +0700',
                'channel': c['id'],
            })
            ET.SubElement(pe, 'title', {'lang': 'id'}).text = title
            added_pr += 1

    total_ch = len(root.findall('channel'))
    total_pr = len(root.findall('programme'))
    missing = [c['id'] for c in uniq if c['id'] not in {x.get('id') for x in root.findall('channel')}]
    print(f'playlist id unik : {len(uniq)}')
    print(f'epg channel      : {total_ch} (ditambah {added_ch})')
    print(f'epg programme    : {total_pr} (ditambah {added_pr})')
    print(f'sisa tanpa epg   : {len(missing)}')
    if missing[:5]:
        print('  contoh:', missing[:5])

    if a.write or a.out:
        tree.write(a.out or a.epg, encoding='utf-8', xml_declaration=True)
        print('ditulis ke', a.out or a.epg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
