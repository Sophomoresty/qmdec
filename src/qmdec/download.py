"""Search and download songs from QQ Music."""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path


def search_songs(keyword: str, cookie: str, uin: str, limit: int = 20) -> list[dict]:
    url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    data = {
        "comm": {"cv": 4747474, "ct": 24, "format": "json", "uin": int(uin), "g_tk": 5381},
        "req_1": {
            "module": "music.search.SearchCgiService",
            "method": "DoSearchForQQMusicDesktop",
            "param": {"query": keyword, "page_num": 1, "num_per_page": limit, "search_type": 0},
        },
    }
    req = urllib.request.Request(url, json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "QQMusic/21")

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError):
        return []

    songs = result.get("req_1", {}).get("data", {}).get("body", {}).get("song", {}).get("list", [])
    out = []
    for s in songs:
        file_info = s.get("file", {})
        out.append({
            "title": s.get("title", ""),
            "singer": "/".join(x.get("title", "") for x in s.get("singer", [])),
            "album": s.get("album", {}).get("title", ""),
            "song_mid": s.get("mid", ""),
            "media_mid": file_info.get("media_mid", ""),
            "size_flac": file_info.get("size_flac", 0),
            "size_320": file_info.get("size_320mp3", 0),
            "size_128": file_info.get("size_128mp3", 0),
        })
    return out


def get_download_info(song_mid: str, media_mid: str, quality: str, cookie: str, uin: str) -> dict | None:
    """Get download URL and ekey for a song."""
    prefix_map = {"flac": "F0M0", "320": "M800", "128": "M500"}
    ext_map = {"flac": ".mflac", "320": ".mp3", "128": ".mp3"}

    prefix = prefix_map.get(quality, "F0M0")
    ext = ext_map.get(quality, ".mflac")
    filename = f"{prefix}{media_mid}{ext}"

    url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    data = {
        "comm": {"cv": 4747474, "ct": 24, "format": "json", "uin": int(uin), "g_tk": 5381},
        "req_1": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {
                "filename": [filename],
                "guid": "10000",
                "songmid": [song_mid],
                "songtype": [0],
                "uin": uin,
                "loginflag": 1,
                "platform": "20",
            },
        },
    }
    req = urllib.request.Request(url, json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "QQMusic/21")

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError):
        return None

    vkey_data = result.get("req_1", {}).get("data", {})
    sip = vkey_data.get("sip", [])
    midurlinfo = vkey_data.get("midurlinfo", [])

    if not midurlinfo or not sip:
        return None

    info = midurlinfo[0]
    purl = info.get("purl", "")
    ekey = info.get("ekey", "")

    if not purl:
        return None

    return {
        "url": sip[0] + purl,
        "ekey": ekey,
        "filename": filename,
        "quality": quality,
    }


def download_file(url: str, output_path: Path, callback=None) -> bool:
    """Download a file with optional progress callback."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "QQMusic/21")

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0

        with open(output_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if callback:
                    callback(downloaded, total)

        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
