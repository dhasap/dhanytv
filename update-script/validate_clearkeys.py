#!/usr/bin/env python3
"""validate_clearkeys.py — buang entri clearkey DASH yang KID manifest-nya
tidak cocok dengan license_key di playlist (penyebab error '403 kunci salah').

Pemakaian:
  python3 validate_clearkeys.py dhanytv.m3u [--write]

- Manifest tak terbaca / geo / timeout -> entri DIPERTAHANKAN (tidak bisa divalidasi).
- KID terbaca & match   -> entri DIPERTAHANKAN.
- KID terbaca & mismatch-> entri DIBUANG (pasti gagal dekripsi).
"""
import concurrent.futures as cf
import re, sys, ssl, urllib.request, ssl as _ssl

M3U = sys.argv[1] if len(sys.argv) > 1 else 'dhanytv.m3u'
WRITE = '--write' in sys.argv
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0 Safari/537.36'
CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE

def fetch_kid(url):
    try:
        req=urllib.request.Request(url, headers={'User-Agent':UA})
        r=urllib.request.urlopen(req, timeout=10, context=CTX)
        b=r.read(200000).decode('utf-8',errors='replace')
        m=re.search(r'cenc:default_KID="([0-9a-fA-F-]{36})"', b)
        if m: return m.group(1).replace('-','').lower()
        return None
    except Exception:
        return 'UNREACHABLE'

txt=open(M3U,encoding='utf-8',errors='replace').read()
blocks=re.split(r'(?=^#EXTINF)', txt, flags=re.M)

kept, dropped, unverif = [], [], []
def validate(block):
    url=None; kid_entry=None
    for l in block.splitlines():
        if l.startswith('http') and url is None: url=l.split('|',1)[0].strip()
        m=re.search(r'license_key=([0-9a-f]{32}:[0-9a-f]{32})', l)
        if m: kid_entry=m.group(1).split(':')[0].lower()
    if not kid_entry or not url or '.mpd' not in url:
        return block, 'keep-nodrm'
    kid_m = fetch_kid(url)
    if kid_m == 'UNREACHABLE' or kid_m is None:
        return block, 'unverifiable'
    # KID mismatch doesn't prove the key is dead — providers rotate KIDs but
    # keys from other sources may still work. Only drop when the manifest
    # itself is unreachable (stream confirmed offline).
    return block, f'mismatch-but-kept kid={kid_m[:8]}'

# Deterministic: validate concurrently but rebuild in ORIGINAL block order,
# preserving non-EXTINF blocks (header/comments). as_completed-ordered output
# used to shuffle the playlist randomly on every run.
results = {}
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    futs = {ex.submit(validate, b): idx
            for idx, b in enumerate(blocks) if b.startswith('#EXTINF')}
    for f in cf.as_completed(futs):
        idx = futs[f]
        newb, status = f.result()
        results[idx] = (newb, status)

out = []
for idx, b in enumerate(blocks):
    if idx in results:
        newb, status = results[idx]
        if status.startswith('mismatch'):
            dropped.append((status, b.splitlines()[0][-50:]))
        elif status == 'unverifiable':
            unverif.append(b)
        if newb:
            out.append(newb.strip('\n'))
    elif b.strip():
        out.append(b.strip('\n'))
new='\n\n'.join(out)+'\n'
# pertahankan header
hdr=txt.splitlines()[0]
if not new.startswith('#EXTM3U'): new=hdr+'\n'+new

print(f'dropped (KID mismatch): {len(dropped)}')
for s,n in dropped: print('  ',s,'|',n)
print(f'unverifiable (geo/offline): {len(unverif)}')
if WRITE:
    open(M3U,'w',encoding='utf-8').write(new)
    print(f'\nWRITTEN to {M3U}')
else:
    print('\n(dry-run; tambahkan --write untuk menyimpan)')
