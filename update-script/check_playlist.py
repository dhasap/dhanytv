#!/usr/bin/env python3
"""check_playlist.py — uji hidup/mati SETIAP entri playlist (HLS & DASH).

Rantai yang diuji:
  HLS  : manifest -> (master) varian -> segmen pertama  (harus > 2 KB)
  DASH : MPD -> init segment -> segmen pertama (SegmentTemplate Number/Time)
  RAW  : URL langsung (mis. .ts) -> byte pertama

Header dari #EXTVLCOPT / #KODIPROP ikut dikirim (User-Agent, Referer, Origin).

Contoh:
    python3 update-script/check_playlist.py dhanytv.m3u --workers 40 --out /tmp/tv_test.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

UA_DEFAULT = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36"
EXTINF_RE = re.compile(r'#EXTINF:-?\d+(?:\.\d+)?\s*(.*?),(.*)$')
ATTR_RE = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
MIN_SEG = 2000


@dataclass
class Entry:
    name: str
    url: str
    group: str = ""
    tvg_id: str = ""
    headers: dict = field(default_factory=dict)
    kind: str = "hls"      # hls | dash | raw
    kodiprops: dict = field(default_factory=dict)
    lineno: int = 0

    @property
    def host(self) -> str:
        try:
            return urllib.parse.urlsplit(self.url).hostname or ""
        except Exception:
            return ""


def parse_playlist(path: str) -> list[Entry]:
    entries: list[Entry] = []
    headers: dict = {}
    props: dict = {}
    pending = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTINF"):
                m = EXTINF_RE.search(line)
                attrs = dict(ATTR_RE.findall(line))
                pending = {
                    "name": (m.group(2).strip() if m else "") or attrs.get("tvg-name", ""),
                    "group": attrs.get("group-title", ""),
                    "tvg_id": attrs.get("tvg-id", ""),
                    "lineno": lineno,
                }
            elif line.startswith("#EXTVLCOPT:"):
                opt = line[len("#EXTVLCOPT:"):]
                if "=" in opt:
                    k, v = opt.split("=", 1)
                    k = k.strip().lower()
                    if k == "http-user-agent":
                        headers["User-Agent"] = v.strip()
                    elif k in ("http-referrer", "http-referer"):
                        headers["Referer"] = v.strip()
                    elif k == "http-origin":
                        headers["Origin"] = v.strip()
            elif line.startswith("#KODIPROP:"):
                prop = line[len("#KODIPROP:"):]
                if "=" in prop:
                    k, v = prop.split("=", 1)
                    props[k.strip()] = v.strip()
            elif line.startswith("#"):
                continue
            elif pending is not None:
                hdrs = dict(headers)
                sh = props.get("inputstream.adaptive.stream_headers", "")
                if sh:
                    sh = urllib.parse.unquote(sh)
                    for part in re.split(r"[&\n]", sh):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            k = k.strip()
                            if k.lower() == "referer":
                                hdrs.setdefault("Referer", v.strip())
                            elif k.lower() == "origin":
                                hdrs.setdefault("Origin", v.strip())
                            elif k.lower() in ("user-agent", "user_agent"):
                                hdrs.setdefault("User-Agent", v.strip())
                            else:
                                hdrs.setdefault(k, v.strip())
                low = line.lower()
                mt = props.get("inputstream.adaptive.manifest_type", "").lower()
                if low.split("?")[0].endswith(".mpd") or mt == "mpd" or "dash" in mt:
                    kind = "dash"
                elif low.split("?")[0].endswith((".m3u8", ".m3u")) or mt == "hls":
                    kind = "hls"
                else:
                    kind = "raw"
                entries.append(Entry(name=pending["name"], url=line, group=pending["group"],
                                     tvg_id=pending["tvg_id"], headers=hdrs, kind=kind,
                                     kodiprops=dict(props), lineno=pending["lineno"]))
                pending = None
                headers = {}
                props = {}
    return entries


def http_get(url: str, headers: dict, timeout: float = 12.0, method: str = "GET", limit: int = 0):
    """Kembalikan (status, content_type, panjang, teks/bytes)."""
    hdrs = {"User-Agent": UA_DEFAULT, "Accept": "*/*"}
    hdrs.update({k: v for k, v in headers.items() if v})
    req = urllib.request.Request(url, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        ctype = resp.headers.get("Content-Type", "")
        if method == "HEAD":
            return resp.status, ctype, int(resp.headers.get("Content-Length") or 0), b""
        data = resp.read(limit) if limit else resp.read()
        return resp.status, ctype, len(data), data


def resolve(base: str, rel: str) -> str:
    return urllib.parse.urljoin(base, rel)


def first_uri(manifest: str) -> str | None:
    for line in manifest.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
    return None


def numeric_attr(tag: str, name: str):
    m = re.search(rf'{name}="([^"]+)"', tag)
    return m.group(1) if m else None


def dash_probe(mpd_url: str, headers: dict) -> tuple[str, str]:
    st, ctype, _, raw = http_get(mpd_url, headers, limit=400_000)
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    if "<MPD" not in text[:2000]:
        return "empty", f"bukan MPD ({ctype or st})"

    # init segment
    init_m = re.search(r'initialization="([^"]+)"', text)
    if not init_m:
        return "dash-noinit", "MPD tanpa initialization"
    init_url = resolve(mpd_url, init_m.group(1))
    init_url = re.sub(r"\$Bandwidth\$", "1", init_url)
    for k in ("$RepresentationID$",):
        init_url = init_url.replace(k, "1")
    st_i, ct_i, len_i, _ = http_get(init_url, headers, limit=65536)
    if st_i >= 400 or len_i < 100:
        return "dash-init", f"init {st_i} {len_i}B"

    # segmen pertama
    tmpl = re.search(r'<SegmentTemplate[^>]*media="([^"]+)"', text)
    if not tmpl:
        base_m = re.search(r'<BaseURL>([^<]+)</BaseURL>', text)
        if base_m:
            seg_url = resolve(mpd_url, base_m.group(1).strip())
            st_s, ct_s, len_s, _ = http_get(seg_url, headers, limit=65536)
            return ("ok", f"{st_s} {len_s}B") if st_s < 400 and len_s >= MIN_SEG else ("dash-seg", f"{st_s} {len_s}B")
        return "ok-init-only", f"init {len_i}B (tanpa media template)"

    media = tmpl.group(1)
    seg_url = media
    if "$Time$" in seg_url:
        ast = re.search(r'availabilityStartTime="([^"]+)"', text)
        if ast:
            try:
                import datetime
                t0 = datetime.datetime.strptime(ast.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                t = int((now - t0).total_seconds()) + 2
            except Exception:
                t = 0
        else:
            t = 0
        seg_url = seg_url.replace("$Time$", str(t))
    else:
        seg_url = seg_url.replace("$Number$", "1")
    seg_url = re.sub(r"\$Bandwidth\$", "1", seg_url).replace("$RepresentationID$", "1")
    seg_url = resolve(mpd_url, seg_url)
    try:
        st_s, ct_s, len_s, _ = http_get(seg_url, headers, limit=65536)
    except urllib.error.HTTPError as e:
        return "dash-seg", f"HTTP {e.code}"
    if st_s < 400 and len_s >= MIN_SEG:
        return "ok", f"dash {len_s}B"
    return "dash-seg", f"{st_s} {len_s}B"


def hls_probe(entry: Entry) -> tuple[str, str]:
    url = entry.url
    st, ctype, _, body = http_get(url, entry.headers, limit=400_000)
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    if st >= 400:
        return classify_http(st), f"manifest {st}"
    if "#EXTM3U" not in text[:200]:
        # mungkin TS mentah
        if len(text) >= MIN_SEG:
            return "ok", f"raw {len(text)}B"
        return "empty", f"bukan m3u8 ({ctype or st})"

    # master playlist?
    if "#EXT-X-STREAM-INF" in text:
        variant = first_uri(text)
        if not variant:
            return "empty", "master tanpa varian"
        vurl = resolve(url, variant)
        st2, _, _, vbody = http_get(vurl, entry.headers, limit=400_000)
        vtext = vbody.decode("utf-8", "replace") if isinstance(vbody, bytes) else str(vbody)
        if st2 >= 400:
            return classify_http(st2), f"varian {st2}"
        if "#EXTM3U" not in vtext[:200]:
            return "empty", f"varian bukan m3u8 ({st2})"
        text, url = vtext, vurl

    seg = first_uri(text)
    if not seg:
        return "empty", "tanpa segmen"
    seg_url = resolve(url, seg)
    try:
        st3, _, len3, _ = http_get(seg_url, entry.headers, limit=65536)
    except urllib.error.HTTPError as e:
        return classify_http(e.code), f"segmen {e.code}"
    if st3 < 400 and len3 >= MIN_SEG:
        return "ok", f"seg {len3}B"
    return "seg-kecil", f"{st3} {len3}B"


def classify_http(code: int) -> str:
    if code in (401, 403):
        return "geo/auth 403"
    if code == 404:
        return "404"
    if code == 451:
        return "geo 451"
    if code in (500, 502, 503, 504):
        return f"server {code}"
    if code == 429:
        return "rate 429"
    return f"http {code}"


def probe(entry: Entry) -> dict:
    t0 = time.time()
    status, detail = "error", ""
    try:
        if entry.kind == "dash":
            status, detail = dash_probe(entry.url, entry.headers)
        elif entry.kind == "raw":
            st, ctype, ln, _ = http_get(entry.url, entry.headers, limit=65536)
            status, detail = ("ok", f"raw {ln}B") if st < 400 and ln >= 500 else (classify_http(st), f"{st} {ln}B")
        else:
            status, detail = hls_probe(entry)
    except urllib.error.HTTPError as e:
        status, detail = classify_http(e.code), f"HTTP {e.code}"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        txt = str(reason)
        status = "dns" if isinstance(reason, socket.gaierror) or "Name or service" in txt else "timeout/refused"
        detail = txt[:80]
    except (socket.timeout, TimeoutError):
        status, detail = "timeout", "timeout"
    except Exception as e:  # noqa: BLE001
        status, detail = "error", f"{type(e).__name__}: {e}"[:80]

    return {
        "name": entry.name, "group": entry.group, "tvg_id": entry.tvg_id,
        "url": entry.url, "host": entry.host, "kind": entry.kind,
        "status": status, "detail": detail, "ms": int((time.time() - t0) * 1000),
        "astatv": "astatv.pages.dev" in entry.url,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--out", default="/tmp/tv_test.json")
    ap.add_argument("--only", default=None, help="filter substring URL/nama")
    ap.add_argument("--retries", type=int, default=1)
    args = ap.parse_args()

    entries = parse_playlist(args.playlist)
    if args.only:
        entries = [e for e in entries if args.only.lower() in e.url.lower() or args.only.lower() in e.name.lower()]
    print(f"entri diuji: {len(entries)}  workers={args.workers}", flush=True)

    results: list[dict] = []
    done = 0
    t0 = time.time()
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(probe, e): e for e in entries}
        for fut in futures.as_completed(futs):
            r = fut.result()
            if r["status"] in ("timeout", "timeout/refused", "error") and args.retries:
                for _ in range(args.retries):
                    r2 = probe(futs[fut])
                    if r2["status"] not in ("timeout", "timeout/refused", "error"):
                        r = r2
                        break
            results.append(r)
            done += 1
            if done % 100 == 0:
                ok = sum(1 for x in results if x["status"] == "ok")
                print(f"  ... {done}/{len(entries)} ok {ok}  ({time.time()-t0:.0f}s)", flush=True)

    results.sort(key=lambda x: (x["status"] != "ok", x["group"], x["name"].lower()))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\nSELESAI {len(results)} entri, OK {ok} ({ok/max(1,len(results))*100:.1f}%)  waktu {time.time()-t0:.0f}s")
    from collections import Counter
    print("status:", Counter(r["status"] for r in results).most_common())
    print("astatv:", Counter(r["status"] for r in results if r["astatv"]).most_common())
    print(f"detail: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
