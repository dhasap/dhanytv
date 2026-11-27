#!/usr/bin/env python3
"""
patch_m3u.py — propose compatibility fixes for dhanytv playlists.

NEVER writes into the repo. Output goes to /tmp/qc/kompat/patched/.
Dry-run by default: prints the diff summary only.

Fixes:
  P1  header attributes inside #EXTINF -> #EXTVLCOPT (+ #EXTHTTP for OTT Navigator)
  P2  #KODIPROP:manifest_type=mpd on a non-.mpd URL -> line removed (URL self-describes)
  P3  grgroup-title= -> group-title=
  P4  tag order normalised: #EXTINF, #EXTVLCOPT, #KODIPROP, #EXTHTTP, URL
  P5  (--drop-dead) entries on verified-dead hosts removed
  P6  (--add-inputstream) #KODIPROP:inputstreamaddon=inputstream.adaptive on .mpd entries

Usage:
  python3 patch_m3u.py <in.m3u> <out.m3u> [--apply] [--drop-dead] [--add-inputstream]
"""
import re, sys, json, argparse, pathlib

HEADER_ATTRS = {"http-referrer", "http-user-agent", "http-origin"}
ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
DEAD_HOSTS = {"vidio123.mikrofast.web.id", "proxy-v.rctiplus.id", "nextgenz.my.id",
              "aspaltvpasti.top", "cdnbal1.indihometv.com"}
TAG_PRIORITY = {"#EXTVLCOPT": 1, "#KODIPROP": 2, "#EXTHTTP": 3, "#EXTGRP": 4}


def split_extinf(line):
    """Return (prefix_without_name, name) using the same rule Kodi uses:
    name starts after the first comma that follows the last double quote."""
    q = line.rfind('"')
    if q != -1:
        rest = line[q + 1:]
        c = rest.find(',')
        if c == -1:
            return None, None
        return line[:q + 1 + c], rest[c + 1:].strip()
    c = line.find(',')
    if c == -1:
        return None, None
    return line[:c], line[c + 1:].strip()


def patch(path, drop_dead=False, add_inputstream=False):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    lines = text.split("\n")
    # header line is emitted once, separately — it is not part of any stanza
    header = "#EXTM3U"
    if lines and lines[0].strip().startswith("#EXTM3U"):
        header = lines[0].strip()
        lines = lines[1:]
    # url-tvg: pemain (Kodi/TiviMate/OTT Nav) bisa auto-load EPG tanpa set manual
    if "url-tvg=" not in header:
        header += (' url-tvg="https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml"'
                   ' x-tvg-url="https://raw.githubusercontent.com/dhasap/dhanytv/main/epg.xml"')
    out, log = [header, ""], []
    i = 0
    n = len(lines)
    stats = {"P1": 0, "P2": 0, "P3": 0, "P4": 0, "P5": 0, "P6": 0}

    while i < n:
        # collect a stanza: tag lines until a URL line
        start = i
        buf = []
        url = None
        while i < n:
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if s.startswith("#"):
                buf.append(s)
                i += 1
                continue
            url = s
            i += 1
            break

        if not buf and url is None:
            break
        if url is None:
            # trailing tags — keep verbatim
            out.extend(buf)
            out.append("")
            continue

        extinf = next((b for b in buf if b.startswith("#EXTINF:")), None)
        others = [b for b in buf if not b.startswith("#EXTINF:")]

        if extinf is None:
            out.extend(buf + [url, ""])
            continue

        ln = start + 1
        # ---- P3 typo ----
        if "grgroup-title=" in extinf:
            extinf = extinf.replace("grgroup-title=", "group-title=")
            stats["P3"] += 1
            log.append(f"P3 baris {ln}: grgroup-title -> group-title")

        # ---- P1 header attrs out of EXTINF ----
        prefix, name = split_extinf(extinf)
        moved = {}
        if prefix and name is not None:
            def repl(m):
                if m.group(1) in HEADER_ATTRS:
                    moved[m.group(1)] = m.group(2)
                    return ""
                return m.group(0)
            new_prefix = ATTR_RE.sub(repl, prefix)
            if moved:
                new_prefix = re.sub(r'[ \t]{2,}', ' ', new_prefix).rstrip()
                extinf = f"{new_prefix},{name}"
                ua = moved.get("http-user-agent")
                ref = moved.get("http-referrer")
                org = moved.get("http-origin")
                if ua:
                    others.append(f"#EXTVLCOPT:http-user-agent={ua}")
                if ref:
                    others.append(f"#EXTVLCOPT:http-referrer={ref}")
                if org:
                    others.append(f"#EXTVLCOPT:http-origin={org}")
                if not any(o.startswith("#EXTHTTP:") for o in others) and (ua or ref):
                    hdrs = {}
                    if ref:
                        hdrs["Referer"] = ref
                        hdrs["referrer"] = ref
                    if org:
                        hdrs["Origin"] = org
                    if ua:
                        hdrs["User-Agent"] = ua
                    others.append("#EXTHTTP:" + json.dumps(hdrs))
                stats["P1"] += 1
                log.append(f"P1 baris {ln}: header attr {sorted(moved)} -> #EXTVLCOPT/#EXTHTTP ({name[:30]})")

        # ---- P2 manifest_type mismatch ----
        low = url.split("|")[0].lower().split("?")[0]
        keep = []
        for o in others:
            if o.startswith("#KODIPROP:inputstream.adaptive.manifest_type="):
                mt = o.split("=", 1)[1].strip().lower()
                if mt in ("mpd", "dash") and not low.endswith(".mpd"):
                    stats["P2"] += 1
                    log.append(f"P2 baris {ln}: hapus manifest_type={mt} (URL bukan .mpd: {url[:50]})")
                    continue
                if mt in ("hls", "m3u8") and not (low.endswith(".m3u8") or low.endswith(".m3u")):
                    stats["P2"] += 1
                    log.append(f"P2 baris {ln}: hapus manifest_type={mt} (URL bukan .m3u8)")
                    continue
            keep.append(o)
        others = keep

        # ---- P6 explicit inputstream for DASH ----
        if add_inputstream and low.endswith(".mpd") and \
                not any(o.startswith("#KODIPROP:inputstreamaddon=") for o in others):
            others.insert(0, "#KODIPROP:inputstreamaddon=inputstream.adaptive")
            stats["P6"] += 1
            log.append(f"P6 baris {ln}: tambah inputstreamaddon=inputstream.adaptive")

        # ---- P5 dead host ----
        host = re.sub(r'^https?://([^/:|]+).*', r'\1', url)
        if drop_dead and host in DEAD_HOSTS:
            stats["P5"] += 1
            log.append(f"P5 baris {ln}: buang entri host mati {host}")
            continue

        # ---- P4 normalise order (stable) ----
        before = list(others)
        others.sort(key=lambda o: TAG_PRIORITY.get(o.split(":")[0], 9))
        if others != before:
            stats["P4"] += 1

        out.extend([extinf] + others + [url, ""])

    return "\n".join(out).rstrip("\n") + "\n", stats, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--drop-dead", action="store_true")
    ap.add_argument("--add-inputstream", action="store_true")
    a = ap.parse_args()

    new, stats, log = patch(a.src, a.drop_dead, a.add_inputstream)
    for l in log[:200]:
        print(l)
    if len(log) > 200:
        print(f"... {len(log) - 200} log lain")
    print(f"\nTotal perubahan: {stats}")
    if a.apply:
        dst = pathlib.Path(a.dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(new, encoding="utf-8")
        print(f"ditulis: {dst} ({len(new.encode())} bytes)")
    else:
        print("DRY-RUN — tambahkan --apply untuk menulis")


if __name__ == "__main__":
    main()
