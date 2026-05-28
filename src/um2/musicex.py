"""musicex v1 file format parser and ekey fetcher."""

import base64
import json
import struct
import urllib.request
from pathlib import Path

MUSICEX_MAGIC = b"musicex\x00"


def parse_musicex_tail(filepath: Path) -> dict | None:
    fsize = filepath.stat().st_size
    with open(filepath, "rb") as f:
        f.seek(-8, 2)
        if f.read(8) != MUSICEX_MAGIC:
            return None
        f.seek(-16, 2)
        tail_size = struct.unpack("<I", f.read(4))[0]
        version = struct.unpack("<I", f.read(4))[0]
        f.seek(-(16 + tail_size), 2)
        tail = f.read(tail_size)

    song_mid = tail[28:88].decode("utf-16-le").rstrip("\x00")
    filename = tail[88:184].decode("utf-16-le").rstrip("\x00")
    audio_size = fsize - 16 - tail_size
    return {
        "song_mid": song_mid,
        "filename": filename,
        "audio_size": audio_size,
        "version": version,
    }


def fetch_ekey(song_mid: str, file_mid: str, cookie: str, uin: str) -> str | None:
    request_data = {
        "comm": {
            "cv": 4747474,
            "ct": 24,
            "format": "json",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "notice": 0,
            "platform": "yqq.json",
            "needNewCode": 1,
            "uin": int(uin),
            "g_tk_new_20200303": 5381,
            "g_tk": 5381,
        },
        "req_1": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {
                "filename": [f"{file_mid}.mflac"],
                "guid": "10000",
                "songmid": [song_mid],
                "songtype": [0],
                "uin": uin,
                "loginflag": 1,
                "platform": "20",
            },
        },
    }

    url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    data = json.dumps(request_data).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "QQMusic/21")

    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())

    midurlinfo = result.get("req_1", {}).get("data", {}).get("midurlinfo", [])
    if midurlinfo:
        return midurlinfo[0].get("ekey", "")
    return None
