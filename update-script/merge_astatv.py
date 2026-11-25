#!/usr/bin/env python3
"""Merge channel dari astatv (astatv.pages.dev) ke playlist dhanytv.

Dipakai di CI sebagai sumber tambahan. Aman: tidak menghapus channel,
hanya menambah yang belum ada dan (opsional) mengganti URL mati.
"""
import argparse
import json
import re
import sys
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')

GROUP_BY_CAT = {
    'Sports': 'Sports Channels',
    'News': 'News Channel',
    'Kids': 'Kids',
    'Movies': 'Movies',
    'Entertainment': 'Entertainment',
    'Music': 'Music',
}
REGION_GROUP = {
    'ID': 'Indonesia Channels',
    'MY': 'Malaysia',
    'SG': 'Singapore',
    'SP': 'Sports',
    'BR': 'Brazil',
    'RI': 'TVRI',
}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def norm(s):
    s = s.lower()
    s = re.sub(r'\b(fhd|uhd|hd|sd|4k|8k|hevc|h265)\b', ' ', s)
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s


def parse_playlist(text):
    lines = text.splitlines()
    out = []
    for i, l in enumerate(lines):
        if not l.startswith('#EXTINF'):
            continue
        url = None
        j = i + 1
        while j < len(lines) and j < i + 6:
            nxt = lines[j]
            if nxt.startswith('#EXTINF'):
                break
            if nxt.strip() and not nxt.startswith('#'):
                url = nxt.strip()
                break
            j += 1
        out.append({
            'index': len(out),
            'attr': l,
            'url': url or '',
            'name': l.rsplit(',', 1)[-1].strip(),
            'id': (re.search(r'tvg-id="([^"]*)"', l) or [None, ''])[1],
            'logo': (re.search(r'tvg-logo="([^"]*)"', l) or [None, ''])[1],
            'group': (re.search(r'group-title="([^"]*)"', l) or [None, ''])[1],
        })
    return out


def esc(s):
    return (s.replace('&', '&amp;').replace('"', '&quot;')
             .replace('<', '&lt;').replace('>', '&gt;'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('playlist')
    ap.add_argument('--base', default='https://astatv.pages.dev')
    ap.add_argument('--dead-json', help='hasil tes: [{id,name,st,url}] — ganti yang mati')
    ap.add_argument('--replace-hosts', default='mncmedia.malingtv.workers.dev,proxy-v.rctiplus.id')
    ap.add_argument('--report', help='tulis ringkasan ke file json')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--prefer-astatv', action='store_true',
                    help='selalu pakai URL astatv untuk channel yang cocok (bukan hanya yang mati)')
    ap.add_argument('--keep-dupes', action='store_true',
                    help='jangan dedupe nama (default: dedupe, prioritaskan astatv)')
    ap.add_argument('--add-regions', default='*',
                    help='region astatv yang boleh DITAMBAH (koma) atau * untuk semua')
    ap.add_argument('--add-cats', default='*',
                    help='kategori astatv yang boleh DITAMBAH (koma) atau * untuk semua')
    ap.add_argument('--min-status', default='verified', choices=['verified', 'alive', 'all'],
                    help='kualitas minimum channel astatv yang dipakai (default: verified)')
    a = ap.parse_args()

    text = open(a.playlist, encoding='utf-8', errors='replace').read()
    ents = parse_playlist(text)

    try:
        chans = json.loads(fetch(a.base + '/api/channels?all=1'))['channels']
    except Exception as e:
        print(f'WARN: astatv tidak bisa dihubungi ({e}) — lewati merge', file=sys.stderr)
        return 0

    for c in chans:
        if not c.get('stream'):
            c['stream'] = f"{a.base}/api/s/{c['id']}.m3u8"
    if a.min_status == 'all':
        ast = list(chans)
    elif a.min_status == 'alive':
        ast = [c for c in chans if c.get('verified') or c.get('alive')]
    else:
        ast = [c for c in chans if c.get('verified')]
    by_key = {}
    for c in ast:
        by_key.setdefault(norm(c['name']), c)

    dead_keys = set()
    dead_urls = set()
    if a.dead_json:
        for r in json.load(open(a.dead_json)):
            if str(r.get('st', '')).startswith('ok'):
                continue
            dead_keys.add(r.get('id') or '')
            dead_keys.add(norm(r.get('name') or ''))
            if r.get('url'):
                dead_urls.add(r['url'].strip())

    replace_hosts = [h.strip() for h in a.replace_hosts.split(',') if h.strip()]
    add_regions = {x.strip() for x in a.add_regions.split(',') if x.strip()}
    add_cats = {x.strip() for x in a.add_cats.split(',') if x.strip()}

    have_key = {}
    have_url = set()
    for e in ents:
        have_key.setdefault(norm(e['name']), e)
        if e['id']:
            have_key.setdefault(norm(e['id']), e)
        have_url.add(e['url'])

    replaced, added, mapped = 0, [], []
    out_lines = []
    e_by_url = {}
    for e in ents:
        e_by_url.setdefault(e['url'], []).append(e)

    for e in ents:
        k_name = norm(e['name'])
        k_id = norm(e['id'])
        cand = by_key.get(k_name) or by_key.get(k_id)
        is_dead = (e['url'] in dead_urls or e['id'] in dead_keys or k_name in dead_keys
                   or any(h in e['url'] for h in replace_hosts))
        want = (a.prefer_astatv or is_dead)
        if cand and want and cand.get('stream') and 'astatv.pages.dev' not in e['url']:
            old = e['url']
            e['url'] = cand['stream']
            replaced += 1
            mapped.append({'name': e['name'], 'old': old, 'new': cand['stream'], 'astatv_id': cand['id']})

    used = {e['url'] for e in ents}
    for c in ast:
        k = norm(c['name'])
        if k in have_key or c['stream'] in used:
            continue
        if ('*' not in add_regions and c.get('region') not in add_regions
                and '*' not in add_cats and c.get('category') not in add_cats):
            continue
        grp = (REGION_GROUP.get(c.get('region', ''))
               or ('Sports Channels' if c.get('category') == 'Sports' else '')
               or (c.get('region_name') or '') or 'Other')
        line_attr = (f'#EXTINF:-1 tvg-id="{esc(c["id"])}" tvg-name="{esc(c["name"])}" '
                     f'tvg-logo="{esc(c.get("logo") or "")}" group-title="{esc(grp)}",{esc(c["name"])}')
        ents.append({'attr': line_attr, 'url': c['stream'], 'name': c['name'], 'id': c['id'], 'group': grp})
        used.add(c['stream'])
        added.append({'name': c['name'], 'id': c['id'], 'group': grp})

    if not a.keep_dupes:
        seen_n, keep = {}, []
        for e in ents:
            k = norm(e['name'])
            if k in seen_n:
                prev = seen_n[k]
                if 'astatv.pages.dev' in e['url'] and 'astatv.pages.dev' not in prev['url']:
                    keep[keep.index(prev)] = e
                    seen_n[k] = e
                continue
            seen_n[k] = e
            keep.append(e)
        dropped = len(ents) - len(keep)
        if dropped:
            print(f'  dedupe nama: {dropped} entri dibuang')
        ents = keep

    header = text.split('#EXTINF', 1)[0].rstrip('\n')
    body = []
    for e in ents:
        body.append(e['attr'])
        body.append(e['url'])
    new_text = header + '\n' + '\n'.join(body) + '\n'

    if not a.dry_run:
        open(a.playlist, 'w', encoding='utf-8').write(new_text)

    print(f'astatv: {len(ast)} channel terverifikasi sumber')
    print(f'  diganti: {replaced} | ditambah: {len(added)} | total hasil: {len(ents)}')
    for x in mapped[:12]:
        print(f'    GANTI {x["name"][:30]:32} -> astatv/{x["astatv_id"]}')
    for x in added[:12]:
        print(f'    TAMBAH {x["name"][:30]:32} [{x["group"]}]')
    if a.report:
        json.dump({'replaced': mapped, 'added': added, 'total': len(ents)},
                  open(a.report, 'w'), ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
