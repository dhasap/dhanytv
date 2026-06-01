#!/usr/bin/env python3
"""Generate dhanytv custom XMLTV EPG with multi-source fallback coverage.

Sources (in priority order for programme data):
  1. epgshare01.online — ID1, SG1, MY1, CA2, IT1, FR1, AE1, IN1, ALJAZEERA1
  2. open-epg.com — indonesia.xml
  3. AqFad2811/epg — indonesia.xml, astro.xml, singapore.xml, rtmklik.xml, unifitv.xml, epg.xml, sooka.xml
"""

from __future__ import annotations

import argparse
import copy
import gzip
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

JAKARTA = timezone(timedelta(hours=7))
RE_ATTR = re.compile(r'([A-Za-z0-9_-]+)=\"([^\"]*)\"')

# Manual mapping: playlist tvg-id -> source_channel_id
# Used when exact match fails OR when source has better data under different ID.
MANUAL_ID_MAP: dict[str, str] = {
    # Sportstars (Indonesian sports)
    "Sportstars": "Sportstars.id",
    "Sportstars 2": "Sportstars2.id",
    "Sportstars 3": "Sportstars3.id",
    # International channels
    "Al Jazeera Arabic": "AL.Jazeera.in",
    "CNN International": "CNN.International.ae",
    "Animal Planet": "AnimalPlanet.id",
    "Aniplus": "ANIPLUS.HD.sg",
    "Cartoonito": "Cartoonito.fr",
    "Celestial Classic Movies": "Celestial.Classic.Movies.my",
    "CNBC Asia": "CNBCAsia",
    "Dragon TV": "Dragon.TV.Intl.sg",
    "FashionTV": "FashionTV.id",
    "HITSNow": "HITS.NOW.id",
    "NBA TV": "NBA.TV.Canada.HD.ca2",
    "RAI Italia": "Rai.Italia.ca2",
    "Russia Today": "Russia.Today..sg",
    "TRT World": "TRT.World.ae",
    "TSN1 HD.ca": "TSN.1.ca2",
    "TSN2 HD.ca": "TSN.2.ca2",
    "TSN3 HD.ca": "TSN.3.HD.ca2",
    "TSN4 HD.ca": "TSN.4.HD.ca2",
    "TSN5 HD.ca": "TSN.5.HD.ca2",
    "TV5Monde": "TV5.monde.fr",
    "TVBS News": "TVBS.News.sg",
    "Warner TV": "WarnerTV.id",
    "Uniques": "UNIQUES.id",
    "Moonbug": "Moonbug.id",
    # Champions TV
    "Champions.TV.1.id": "ChampionsTV1.id",
    "Champions.TV.2.id": "ChampionsTV2.id",
    "Champions.TV.3.id": "ChampionsTV3.id",
    "Champions.TV.5.id": "ChampionsTV5.id",
    "Champions.TV.6.id": "ChampionsTV6.id",
    # Indonesian channels from open-epg
    "Musik Indonesia": "MusikIndonesia.id",
    "CNBCIndonesia.id": "CNBCIndonesia.id",
    "CNNIndonesia.id": "CNNIndonesia.id",
    "DAAITV.id": "DAAITV.id",
    "GarudaTV.id": "GarudaTV.id",
    "NusantaraTV.id": "NusantaraTV.id",
    "RTV.id": "RTV.id",
    "HGTV.id": "HGTV",
    "Dunia Anak": "DuniaAnak.id",
    "Horee!": "HipHipHoree!.id",
    "BNChannel.id": "BNChannel.id",
    "MagnaChannel.id": "MagnaChannel.id",
    # TVRI regional channels (all share TVRI.id EPG)
    "TVRI.Aceh.id": "TVRI.id",
    "TVRI.BangkaBelitung.id": "TVRI.id",
    "TVRI.Bengkulu.id": "TVRI.id",
    "TVRI.Jambi.id": "TVRI.id",
    "TVRI.Lampung.id": "TVRI.id",
    "TVRI.JawaBarat.id": "TVRI.id",
    "TVRI.JawaTengah.id": "TVRI.id",
    "TVRI.JawaTimur.id": "TVRI.id",
    "TVRI.KalimantanBarat.id": "TVRI.id",
    "TVRI.KalimantanSelatan.id": "TVRI.id",
    "TVRI.KalimantanTengah.id": "TVRI.id",
    "TVRI.KalimantanTimur.id": "TVRI.id",
    "TVRI.Gorontalo.id": "TVRI.id",
    "TVRI.SulawesiBarat.id": "TVRI.id",
    "TVRI.SulawesiSelatan.id": "TVRI.id",
    "TVRI.SulawesiTengah.id": "TVRI.id",
    "TVRI.SulawesiTenggara.id": "TVRI.id",
    "TVRI.SulawesiUtara.id": "TVRI.id",
    "TVRI.Bali.id": "TVRI.id",
    "TVRI.NTT.id": "TVRI.id",
    "TVRI.Papua.id": "TVRI.id",
    # beInSports variants
    "beInSports1.au": "beInSports1.id",
    "beInSportsHD.id": "beInSports1.id",
    "beInSports3.au": "beInSports3.id",
    "beInSportsHD3.id": "beInSports3.id",
    # Jawapos TV regional
    "JawaposTV.Madiun.id": "Jawapos TV",
    "JawaposTV.Jakarta.id": "Jawapos TV",
    # Indian channels
    "&Pictures HD": "And.Pictures.HD.in",
    "&TV HD": "Anand.TV.in",
    # epgshare01 extras
    "Al Quran Al Kareem": "Al.Quran.Al.Kareem.id",
    "auto.spotv.now": "SPOTV.id",
    "auto.first.lifestyle": "LIFE.id",
    "auto.citra.entertainment": "Entertainment.id",
    "auto.muslim.tv": "Muslim.TV.id",
    "auto.brtv": "BRTV.International.sg",
    "auto.sin.po.tv": "SinpoTV.id",
    "auto.sin.po.tv.2": "SinpoTV.id",
    "auto.prambors": "Prambors.id",
    "auto.dmi.tv": "DMITV.id",
    "auto.bioskop.indonesia": "BioskopIndonesia.id",
    "auto.mnx": "MNX.HD.in",
    "auto.tbnasia": "TBNAsia.id",
    # AqFad epg.xml / sooka.xml
    "AstroAwani.my": "AstroAwani",
    "auto.aura": "AstroAura",
    "auto.big.stories": "WeDoTVBigStories",
    "auto.drama.hotpot": "DramaHotpot",
    "auto.filem.mantap": "FilemMantap",
    "auto.lawak.sentral": "LawakSentral",
    "auto.oh.my.ceria": "OhMyCeria",
    "auto.tvbs.asia": "TVBSAsia",
    "auto.tvb.xing.he": "TVBXingHe",
    "凤凰资讯": "PhoenixInfoNews",
    "凤凰中文": "PhoenixChinese",
    "凤凰香港": "PhoenixHongkong",
    # BBC News
    "BBC News": "BBC.World.News.id",
    "EWTN": "EWTN",
    # Additional channels from open-epg
    "Bali TV": "Bali.TV.id",
    "BandungTV.id": "BandungTV.id",
    "Citra Dangdut": "CitraDangdut.id",
    "CitraMuslim.id": "CitraMuslim.id",
    "JTV": "JTV.id",
    "Jawapos TV": "JawaPosTV.id",
    "Jogja TV": "JogjaTV.id",
    "Mentari TV": "MentariTV.id",
    "Moji": "Moji.id",
    "Music TV": "MusicTV.id",
    "Mykidz": "MyKidz.id",
    "Thrill": "Thrill.id",
    "Shenzen": "Shenzen.id",
    "Hunan TV": "Hunan.TV.fr",
    "Zhejiang": "ZhejiangInt.id",
    "Food Network (HD).sg": "Food.Network.ca2",
    "Dens ShowBiz": "DensShowbiz.id",
    "AllPlay Ent": "AllPlay.Ent.id",
    # Auto.* channels
    "auto.banjartv": "BanjarTV.id",
    "auto.lingkar.tv": "LingkarTV.id",
    "auto.lingkartv": "LingkarTV.id",
    "auto.bantentv": "BantenTV.id",
    "auto.jtv.kediri": "JTVKediri.id",
    "auto.surabaya.tv": "SurabayaTV.id",
    "auto.smtv.sumedang": "SMTVSumedang.id",
    "auto.staratv.cianjur": "StarATVCianjur.id",
    "auto.staratv.malang": "StarATVMalang.id",
    "auto.staratv.sumedang": "StarATVSumedang.id",
    "auto.timor.tv": "TimorTV.id",
    "auto.pon.tv": "PontianakTV.id",
    "auto.salira.tv": "SaliraTV.id",
    "auto.sampit.tv": "SampitTV.id",
    "auto.tv.tabalong": "TVTabalong.id",
    "auto.kawanua.tv": "KawanuaTV.id",
    "auto.dhoho.tv.kediri": "DhohoTVKediri.id",
    "auto.kilisuci.tv.kediri": "KilisuciTVKediri.id",
    "auto.jitv.jogja": "JITVJogja.id",
    "auto.dmtv.malang": "DMTVMalang.id",
    "auto.sultra.tv": "SultraTV.id",
    "auto.radar.tasikmalaya.tv": "RadarTasikmalayaTV.id",
    "auto.bungo.tv": "BungoTV.id",
    "auto.davikatv.lampung": "DavikaTVLampung.id",
    "auto.carubantv": "CarubanTV.id",
    "auto.banyumastv": "BanyumasTV.id",
    "auto.tv9.nu": "TV9NU.id",
}


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
            if not channels[tvg_id].logo and attrs.get("tvg-logo"):
                channels[tvg_id].logo = attrs["tvg-logo"].strip()
            if not channels[tvg_id].group and attrs.get("group-title"):
                channels[tvg_id].group = attrs["group-title"].strip()

    return channels


def _parse_xmltv_file(path: Path) -> tuple[dict[str, ET.Element], dict[str, list[ET.Element]]]:
    if not path.exists() or path.stat().st_size == 0:
        return {}, {}

    try:
        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8', errors='replace') as f:
                root = ET.parse(f).getroot()
        else:
            root = ET.parse(path).getroot()
    except Exception as exc:
        print(f"WARNING: gagal parse {path}: {exc}")
        return {}, {}

    channels: dict[str, ET.Element] = {}
    programmes: dict[str, list[ET.Element]] = defaultdict(list)

    for channel in root.findall("channel"):
        cid = channel.get("id", "").strip()
        if cid and cid not in channels:
            channels[cid] = channel

    for programme in root.findall("programme"):
        cid = programme.get("channel", "").strip()
        if cid:
            programmes[cid].append(programme)

    return channels, programmes


def read_sources(paths: Iterable[Path]) -> tuple[dict[str, ET.Element], dict[str, list[ET.Element]], int]:
    source_channels: dict[str, ET.Element] = {}
    source_programmes: dict[str, list[ET.Element]] = defaultdict(list)
    parsed = 0

    for path in paths:
        chs, progs = _parse_xmltv_file(path)
        if chs:
            parsed += 1
            for cid, ch in chs.items():
                if cid not in source_channels:
                    source_channels[cid] = ch
            for cid, prog_list in progs.items():
                source_programmes[cid].extend(prog_list)

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


def make_placeholder_programmes(tvg_id: str, days_back: int = 1, days_forward: int = 1) -> list[ET.Element]:
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


def _resolve_channel(tvg_id: str, info: PlaylistChannel,
                     source_channels: dict[str, ET.Element]) -> ET.Element:
    """Find the best channel element for a playlist tvg-id."""
    # Priority 1: manual mapping (curated, higher quality)
    if tvg_id in MANUAL_ID_MAP:
        mapped_id = MANUAL_ID_MAP[tvg_id]
        if mapped_id in source_channels:
            ch = ensure_source_channel_metadata(source_channels[mapped_id], info)
            ch.set("id", tvg_id)
            return ch

    # Priority 2: exact match
    if tvg_id in source_channels:
        return ensure_source_channel_metadata(source_channels[tvg_id], info)

    # Priority 3: fallback placeholder
    return make_channel_element(info)


def _resolve_programmes(tvg_id: str,
                        source_programmes: dict[str, list[ET.Element]]) -> list[ET.Element]:
    """Get programmes for a playlist tvg-id, merging from multiple sources."""
    seen_starts: set[str] = set()
    merged: list[ET.Element] = []

    def _add_programmes(progs: list[ET.Element], remap_to: str | None = None):
        for prog in progs:
            prog_copy = copy.deepcopy(prog)
            if remap_to:
                prog_copy.set("channel", remap_to)
            start = prog_copy.get("start", "")
            if start not in seen_starts:
                seen_starts.add(start)
                merged.append(prog_copy)

    # Priority 1: manual mapping (curated, higher quality)
    if tvg_id in MANUAL_ID_MAP:
        mapped_id = MANUAL_ID_MAP[tvg_id]
        mapped_progs = source_programmes.get(mapped_id, [])
        if mapped_progs:
            _add_programmes(mapped_progs, remap_to=tvg_id)

    # Priority 2: exact match (merge additional programmes)
    exact_progs = source_programmes.get(tvg_id, [])
    if exact_progs:
        _add_programmes(exact_progs)

    return merged


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
    manual_mapped_count = 0
    real_programme_count = 0
    placeholder_programme_count = 0

    for tvg_id, info in playlist_channels.items():
        ch = _resolve_channel(tvg_id, info, source_channels)
        root.append(ch)

        if tvg_id in MANUAL_ID_MAP and MANUAL_ID_MAP[tvg_id] in source_channels:
            manual_mapped_count += 1
            real_channel_count += 1
        elif tvg_id in source_channels:
            real_channel_count += 1
        else:
            fallback_channel_count += 1

    for tvg_id in playlist_channels.keys():
        programmes = _resolve_programmes(tvg_id, source_programmes)
        if programmes:
            for programme in programmes:
                root.append(programme)
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
        "manual_mapped": manual_mapped_count,
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
        default=[
            # epgshare01.online (highest quality, most programmes)
            "epgshare01_ID1.xml", "epgshare01_SG1.xml", "epgshare01_MY1.xml",
            "epgshare01_CA2.xml", "epgshare01_IT1.xml", "epgshare01_FR1.xml",
            "epgshare01_AE1.xml", "epgshare01_IN1.xml", "epgshare01_ALJAZEERA1.xml",
            # open-epg.com
            "open_epg_indonesia.xml",
            # AqFad2811/epg
            "indonesia.xml", "astro.xml", "singapore.xml", "rtmklik.xml",
            "unifitv.xml", "aqfad_epg.xml", "sooka.xml",
        ],
        help="XMLTV source files (.xml or .xml.gz)",
    )
    args = parser.parse_args()

    stats = generate(Path(args.m3u), Path(args.output), [Path(src) for src in args.sources])
    print("=== EPG generation summary ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
