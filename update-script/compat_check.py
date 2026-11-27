#!/usr/bin/env python3
"""
compat_check.py — strict M3U/M3U8 linter for dhanytv playlists.

Rules encoded from vendor documentation (see REPORT.md "Bukti dokumentasi"):
  R1  first line must be exactly #EXTM3U, no BOM
  R2  LF only, UTF-8, no CR
  R3  every #EXTINF must be followed by exactly one URL before the next #EXTINF
  R4  no duplicate stream URL
  R5  attribute order: EXTINF -> #EXTVLCOPT -> #KODIPROP -> #EXTHTTP -> URL
  R6  header attributes must NOT live inside #EXTINF
  R7  #KODIPROP:inputstream.adaptive.manifest_type must not contradict the URL
  R8  .mpd (DASH) must not appear in the OTT build  (--no-dash)
  R9  group-title case-collisions
  R10 tvg-id duplicates (EPG will map wrong)
  R11 tvg-id must exist in epg.xml
  R12 known dead hosts

Usage:
  python3 compat_check.py dhanytv.m3u --epg epg.xml [--no-dash] [--json out.json]
Exit code: 0 clean, 1 findings.
"""
import re, sys, json, argparse, pathlib

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
KNOWN_ATTRS = {
    "tvg-id", "tvg-name", "tvg-logo", "tvg-chno", "tvg-shift", "tvg-country",
    "tvg-language", "tvg-rec", "tvg-type", "group-title", "radio", "timeshift",
    "catchup", "catchup-days", "catchup-source", "catchup-type", "catchup-correction",
    "catchup-enable", "provider", "provider-type", "provider-logo",
    "provider-countries", "provider-languages", "media", "media-dir", "media-size",
    "realtime", "ch-id", "ch-number", "group-logo", "cuid", "codec",
    "audio-track", "video-track", "event-start", "event-end", "expires",
}
HEADER_ATTRS = {"http-referrer", "http-user-agent", "http-origin", "referer", "referrer", "user-agent"}
DEAD_HOSTS = {
    "vidio123.mikrofast.web.id", "proxy-v.rctiplus.id", "nextgenz.my.id",
    "aspaltvpasti.top", "cdnbal1.indihometv.com",
}
TAG_ORDER = {"#EXTINF": 0, "#EXTVLCOPT": 1, "#KODIPROP": 2, "#EXTHTTP": 3, "#EXTGRP": 4}


class Stanza:
    __slots__ = ("tags", "url", "url_line", "extinf_line", "name", "attrs")

    def __init__(self):
        self.tags = []          # (lineno, tag, payload)
        self.url = None
        self.url_line = None
        self.extinf_line = None
        self.name = ""
        self.attrs = {}

    @property
    def ext(self):
        u = (self.url or "").split("|")[0]
        return u.lower().split("?")[0]


def load(path):
    raw = pathlib.Path(path).read_bytes()
    findings = []
    if raw[:3] == b"\xef\xbb\xbf":
        findings.append(("R1", 1, "BOM UTF-8 di awal file"))
    if b"\r" in raw:
        findings.append(("R2", raw[:raw.index(b"\r")].count(b"\n") + 1, "CRLF / CR ditemukan"))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        findings.append(("R2", 0, f"bukan UTF-8 valid: {e}"))
        text = raw.decode("utf-8", "replace")
    lines = text.split("\n")
    if raw[:3] != b"\xef\xbb\xbf" and lines and lines[0].strip() != "#EXTM3U":
        findings.append(("R1", 1, f"baris pertama bukan #EXTM3U: {lines[0][:40]!r}"))
    return text, lines, findings


def stanzas(lines, findings):
    out, buf = [], []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s == "#EXTM3U":
            continue
        if s.startswith("#"):
            if s.startswith("#EXTINF:"):
                name = s.split(",")[-1].strip()
                buf.append((i, "#EXTINF", s))
            elif s.startswith("#EXTVLCOPT:"):
                buf.append((i, "#EXTVLCOPT", s.split(":", 1)[1]))
            elif s.startswith("#KODIPROP:"):
                buf.append((i, "#KODIPROP", s.split(":", 1)[1]))
            elif s.startswith("#EXTHTTP:"):
                buf.append((i, "#EXTHTTP", s.split(":", 1)[1]))
            elif s.startswith("#EXTGRP:"):
                buf.append((i, "#EXTGRP", s.split(":", 1)[1]))
            else:
                findings.append(("R3", i, f"tag tak dikenal: {s[:50]}"))
                buf.append((i, s.split(":")[0], s))
            continue
        st = Stanza()
        st.url, st.url_line, st.tags = s, i, buf
        for ln, tag, payload in buf:
            if tag == "#EXTINF":
                st.extinf_line = ln
                head, _, name = payload.partition(",")
                st.name = name.strip()
                st.attrs = {k: v for k, v in ATTR_RE.findall(head)}
        out.append(st)
        buf = []
    if buf:
        findings.append(("R3", buf[0][0], f"{len(buf)} tag tanpa URL di akhir file"))
    return out


def check(path, epg_ids=None, no_dash=False):
    text, lines, findings = load(path)
    st = stanzas(lines, findings)

    # R3: EXTINF without URL is impossible here (we only emit on URL), but check
    # every stanza has an EXTINF
    for s in st:
        if s.extinf_line is None:
            findings.append(("R3", s.url_line, f"URL tanpa #EXTINF: {s.url[:60]}"))

    # R4 duplicate URL
    seen = {}
    for s in st:
        if s.url in seen:
            findings.append(("R4", s.url_line, f"URL ganda (pertama di baris {seen[s.url]}): {s.url[:70]}"))
        else:
            seen[s.url] = s.url_line

    # R5 tag order
    for s in st:
        order = [TAG_ORDER.get(t[1], 9) for t in s.tags if t[1] in TAG_ORDER]
        if order != sorted(order):
            seq = " -> ".join(t[1] for t in s.tags if t[1] in TAG_ORDER)
            findings.append(("R5", s.tags[0][0], f"urutan tag salah: {seq}"))

    # R6 header attrs inside EXTINF
    for s in st:
        for ln, tag, payload in s.tags:
            if tag == "#EXTINF":
                for k in ATTR_RE.findall(payload.split(",", 1)[0]):
                    if k[0] in HEADER_ATTRS:
                        findings.append(("R6", ln, f"atribut header '{k[0]}' di dalam #EXTINF "
                                                   f"(diabaikan Kodi/Jellyfin/VLC) — {s.name[:34]}"))
                    elif k[0] not in KNOWN_ATTRS:
                        findings.append(("R6b", ln, f"atribut non-standar '{k[0]}' — {s.name[:34]}"))

    # R7 manifest_type vs URL
    for s in st:
        mt = None
        for ln, tag, payload in s.tags:
            if tag == "#KODIPROP" and payload.startswith("inputstream.adaptive.manifest_type="):
                mt = payload.split("=", 1)[1].strip().lower()
                mt_line = ln
        if mt is None:
            continue
        is_mpd = s.ext.endswith(".mpd")
        is_m3u8 = s.ext.endswith(".m3u8") or s.ext.endswith(".m3u")
        if mt in ("mpd", "dash") and not is_mpd:
            findings.append(("R7", mt_line, f"manifest_type={mt} tapi URL bukan .mpd: {s.url[:64]}"))
        elif mt in ("hls", "m3u8") and not is_m3u8:
            findings.append(("R7", mt_line, f"manifest_type={mt} tapi URL bukan .m3u8: {s.url[:64]}"))

    # R8 DASH in OTT build
    if no_dash:
        for s in st:
            if s.ext.endswith(".mpd"):
                findings.append(("R8", s.url_line, f"DASH (.mpd) di build OTT: {s.url[:70]}"))
        for s in st:
            for ln, tag, payload in s.tags:
                if tag == "#KODIPROP" and "license_" in payload:
                    findings.append(("R8", ln, f"properti DRM di build OTT: {payload[:50]}"))

    # R9 group case collision
    g = {}
    for s in st:
        gt = s.attrs.get("group-title")
        if gt:
            g.setdefault(gt.lower(), set()).add(gt)
    for k, v in g.items():
        if len(v) > 1:
            findings.append(("R9", 0, f"grup bentrok kapitalisasi: {sorted(v)}"))

    # R10 duplicate tvg-id
    ids = {}
    for s in st:
        tid = s.attrs.get("tvg-id")
        if tid:
            ids.setdefault(tid, []).append((s.url_line, s.name))
    for tid, rows in ids.items():
        if len(rows) > 1:
            findings.append(("R10", rows[0][0],
                             f"tvg-id '{tid}' dipakai {len(rows)}x -> EPG semua kanal ini sama "
                             f"({', '.join(n for _, n in rows[:4])})"))

    # R11 tvg-id not in epg
    if epg_ids is not None:
        miss = [(s.url_line, s.attrs["tvg-id"], s.name) for s in st
                if s.attrs.get("tvg-id") and s.attrs["tvg-id"] not in epg_ids]
        for ln, tid, name in miss:
            findings.append(("R11", ln, f"tvg-id '{tid}' tidak ada di epg.xml — {name[:34]}"))

    # R12 dead host
    for s in st:
        host = re.sub(r'^https?://([^/:|]+).*', r'\1', s.url or "")
        if host in DEAD_HOSTS:
            findings.append(("R12", s.url_line, f"host mati (terverifikasi): {host}"))

    return st, findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("playlist")
    ap.add_argument("--epg")
    ap.add_argument("--no-dash", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()

    epg_ids = None
    if a.epg:
        epg_ids = set(re.findall(r'<channel id="([^"]*)"', pathlib.Path(a.epg).read_text(errors="replace")))
    st, findings = check(a.playlist, epg_ids, a.no_dash)

    by = {}
    for rule, ln, msg in findings:
        by.setdefault(rule, []).append((ln, msg))

    print(f"# {a.playlist}: {len(st)} entri, {len(findings)} temuan")
    for rule in sorted(by):
        print(f"\n[{rule}] {len(by[rule])} temuan")
        for ln, msg in sorted(by[rule])[:40]:
            print(f"  baris {ln:>5}: {msg}")
        if len(by[rule]) > 40:
            print(f"  ... {len(by[rule]) - 40} lagi")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(
            {"file": a.playlist, "entries": len(st),
             "findings": [{"rule": r, "line": l, "msg": m} for r, l, m in findings]}, indent=1))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
