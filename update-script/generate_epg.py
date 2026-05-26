#!/usr/bin/env python3
"""Generate dhanytv custom XMLTV EPG with safe fallback coverage.

Real programme data is copied from upstream XMLTV sources when a playlist tvg-id
matches a source channel id. For playlist channels that have no upstream EPG,
this script still creates an XMLTV <channel> plus placeholder programmes so IPTV
players can map every channel instead of showing missing EPG metadata.
"""

from __future__ import annotations

import argparse
import copy
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

JAKARTA = timezone(timedelta(hours=7))
RE_ATTR = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')


@dataclass
class PlaylistChannel:
    tvg_id: str
    name: str
    logo: str = ""
    group: str = ""


def xmltv_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S +0700")


def parse_playlist(path: Path) -> OrderedDict[str, PlaylistChannel]:
    channels: OrderedDict[str, PlaylistChannel] = OrderedDict()
    used_auto = 0

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("#EXTINF"):
            continue

        attrs = dict(RE_ATTR.findall(line))
        name = line.rsplit(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "Channel").strip()
        tvg_id = attrs.get("tvg-id", "").strip()
        if not tvg_id:
            # cleanup_playlist.py should already fill tvg-id, but keep a safe fallback.
            used_auto += 1
            tvg_id = f"auto.channel.{used_auto}"
        if tvg_id not in channels:
            channels[tvg_id] = PlaylistChannel(
                tvg_id=tvg_id,
                name=attrs.get("tvg-name", "").strip() or name or tvg_id,
                logo=attrs.get("tvg-logo", "").strip(),
                group=attrs.get("group-title", "").strip(),
            )
        else:
            # Preserve first display-name, but fill missing logo/group if later entry has it.
            if not channels[tvg_id].logo and attrs.get("tvg-logo"):
                channels[tvg_id].logo = attrs["tvg-logo"].strip()
            if not channels[tvg_id].group and attrs.get("group-title"):
                channels[tvg_id].group = attrs["group-title"].strip()

    return channels


def read_sources(paths: Iterable[Path]) -> tuple[dict[str, ET.Element], dict[str, list[ET.Element]], int]:
    source_channels: dict[str, ET.Element] = {}
    source_programmes: dict[str, list[ET.Element]] = defaultdict(list)
    parsed = 0

    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            print(f"WARNING: gagal parse {path}: {exc}")
            continue
        parsed += 1

        for channel in root.findall("channel"):
            cid = channel.get("id", "").strip()
            if cid and cid not in source_channels:
                source_channels[cid] = channel

        for programme in root.findall("programme"):
            cid = programme.get("channel", "").strip()
            if cid:
                source_programmes[cid].append(programme)

    return source_channels, source_programmes, parsed


def make_channel_element(info: PlaylistChannel) -> ET.Element:
    channel = ET.Element("channel", {"id": info.tvg_id})
    display = ET.SubElement(channel, "display-name", {"lang": "id"})
    display.text = info.name or info.tvg_id
    if info.logo:
        ET.SubElement(channel, "icon", {"src": info.logo})
    url = ET.SubElement(channel, "url")
    url.text = "https://github.com/dhasap/dhanytv"
    return channel


def ensure_source_channel_metadata(channel: ET.Element, info: PlaylistChannel) -> ET.Element:
    channel = copy.deepcopy(channel)
    if info.logo and channel.find("icon") is None:
        ET.SubElement(channel, "icon", {"src": info.logo})
    if channel.find("display-name") is None:
        display = ET.SubElement(channel, "display-name", {"lang": "id"})
        display.text = info.name or info.tvg_id
    return channel


def make_placeholder_programmes(tvg_id: str, days_back: int = 1, days_forward: int = 7) -> list[ET.Element]:
    today = datetime.now(JAKARTA).date()
    programmes: list[ET.Element] = []
    for offset in range(-days_back, days_forward + 1):
        day = today + timedelta(days=offset)
        start = datetime.combine(day, time.min, tzinfo=JAKARTA)
        stop = start + timedelta(days=1)
        programme = ET.Element(
            "programme",
            {
                "start": xmltv_time(start),
                "stop": xmltv_time(stop),
                "channel": tvg_id,
            },
        )
        title = ET.SubElement(programme, "title", {"lang": "id"})
        title.text = "Jadwal belum tersedia"
        desc = ET.SubElement(programme, "desc", {"lang": "id"})
        desc.text = "EPG asli belum tersedia untuk channel ini. Channel dibuat agar tetap terbaca oleh IPTV player."
        programmes.append(programme)
    return programmes


def generate(m3u_path: Path, output_path: Path, source_paths: list[Path]) -> dict[str, int]:
    playlist_channels = parse_playlist(m3u_path)
    source_channels, source_programmes, parsed_sources = read_sources(source_paths)

    root = ET.Element(
        "tv",
        {
            "generator-info-name": "dhanytv-custom-epg",
            "generator-info-url": "https://github.com/dhasap/dhanytv",
        },
    )

    real_channel_count = 0
    fallback_channel_count = 0
    real_programme_count = 0
    placeholder_programme_count = 0

    # Add channels in playlist order so EPG order follows the M3U order.
    for tvg_id, info in playlist_channels.items():
        if tvg_id in source_channels:
            root.append(ensure_source_channel_metadata(source_channels[tvg_id], info))
            real_channel_count += 1
        else:
            root.append(make_channel_element(info))
            fallback_channel_count += 1

    # Add real programmes where available, then fallback placeholders for ids with
    # no programme data. This guarantees every tvg-id used by the playlist has EPG.
    for tvg_id in playlist_channels.keys():
        programmes = source_programmes.get(tvg_id, [])
        if programmes:
            for programme in programmes:
                root.append(copy.deepcopy(programme))
                real_programme_count += 1
        else:
            placeholders = make_placeholder_programmes(tvg_id)
            for programme in placeholders:
                root.append(programme)
            placeholder_programme_count += len(placeholders)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="unicode", xml_declaration=True)

    return {
        "playlist_tvg_ids": len(playlist_channels),
        "sources_parsed": parsed_sources,
        "source_channels_matched": real_channel_count,
        "fallback_channels_created": fallback_channel_count,
        "real_programmes": real_programme_count,
        "placeholder_programmes": placeholder_programme_count,
        "output_kb": round(output_path.stat().st_size / 1024),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dhanytv XMLTV EPG with fallback coverage")
    parser.add_argument("--m3u", default="dhanytv.m3u", help="Input M3U playlist")
    parser.add_argument("--output", default="epg.xml", help="Output XMLTV file")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=["indonesia.xml", "astro.xml", "singapore.xml", "rtmklik.xml", "unifitv.xml"],
        help="Downloaded XMLTV source files",
    )
    args = parser.parse_args()

    stats = generate(Path(args.m3u), Path(args.output), [Path(src) for src in args.sources])
    print("=== EPG generation summary ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
