"""File format parsers (musicex v1 + legacy QTag/STag) and ekey management."""

import base64
import json
import struct
import urllib.error
import urllib.request
from pathlib import Path

MUSICEX_MAGIC = b"musicex\x00"
QTAG_MAGIC = b"QTag"
STAG_MAGIC = b"STag"

EKEY_CACHE_DIR = Path.home() / ".config" / "qmdec" / "ekeys"


def parse_file_tail(filepath: Path) -> dict | None:
    """Parse encrypted file tail. Supports musicex v1 and legacy QTag/STag."""
    fsize = filepath.stat().st_size
    with open(filepath, "rb") as f:
        f.seek(-8, 2)
        tail8 = f.read(8)

        if tail8 == MUSICEX_MAGIC:
            return _parse_musicex(f, fsize)

        f.seek(-4, 2)
        tail4 = f.read(4)
        if tail4 == QTAG_MAGIC or tail4 == STAG_MAGIC:
            return _parse_legacy_tag(f, fsize, tail4)

    return None


def _parse_musicex(f, fsize: int) -> dict:
    f.seek(-16, 2)
    tail_size = struct.unpack("<I", f.read(4))[0]
    f.seek(-(16 + tail_size), 2)
    tail = f.read(tail_size)

    song_mid = tail[28:88].decode("utf-16-le").rstrip("\x00")
    filename = tail[88:184].decode("utf-16-le").rstrip("\x00")
    audio_size = fsize - 16 - tail_size
    return {
        "format": "musicex",
        "song_mid": song_mid,
        "filename": filename,
        "audio_size": audio_size,
        "ekey": None,
    }


def _parse_legacy_tag(f, fsize: int, tag_type: bytes) -> dict:
    """Parse QTag/STag format: [audio][ekey_data][ekey_len:4B LE][QTag/STag]"""
    f.seek(-8, 2)
    ekey_len = struct.unpack("<I", f.read(4))[0]
    if ekey_len <= 0 or ekey_len > 4096:
        return None

    audio_size = fsize - 8 - ekey_len
    f.seek(audio_size, 0)
    ekey_data = f.read(ekey_len)

    if tag_type == QTAG_MAGIC:
        parts = ekey_data.split(b",")
        song_mid = parts[0].decode("utf-8", errors="ignore") if len(parts) > 0 else ""
        ekey_b64 = parts[1].decode("utf-8", errors="ignore") if len(parts) > 1 else ""
    else:
        song_mid = ""
        ekey_b64 = ekey_data.decode("utf-8", errors="ignore")

    return {
        "format": "legacy",
        "song_mid": song_mid,
        "filename": "",
        "audio_size": audio_size,
        "ekey": ekey_b64,
    }


def get_ekey(meta: dict, cookie: str, uin: str) -> str | None:
    """Get ekey: check cache first, then fetch from API."""
    cache_key = meta.get("song_mid") or meta.get("filename", "")
    if not cache_key:
        return meta.get("ekey")

    if meta.get("ekey"):
        _cache_ekey(cache_key, meta["ekey"])
        return meta["ekey"]

    cached = _load_cached_ekey(cache_key)
    if cached:
        return cached

    if not cookie or not uin:
        return None

    file_mid = meta["filename"].replace(".mflac", "").replace(".mgg", "")
    ekey = _fetch_ekey_from_api(meta["song_mid"], file_mid, cookie, uin)
    if ekey:
        _cache_ekey(cache_key, ekey)
    return ekey


def _cache_ekey(key: str, ekey: str) -> None:
    EKEY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (EKEY_CACHE_DIR / f"{key}.txt").write_text(ekey)


def _load_cached_ekey(key: str) -> str | None:
    path = EKEY_CACHE_DIR / f"{key}.txt"
    if path.exists():
        content = path.read_text().strip()
        if content:
            return content
    return None


def _fetch_ekey_from_api(song_mid: str, file_mid: str, cookie: str, uin: str) -> str | None:
    ext = ".mflac"
    if not file_mid.startswith("F0"):
        ext = ".mgg"

    request_data = {
        "comm": {
            "cv": 4747474, "ct": 24, "format": "json",
            "inCharset": "utf-8", "outCharset": "utf-8",
            "notice": 0, "platform": "yqq.json", "needNewCode": 1,
            "uin": int(uin), "g_tk_new_20200303": 5381, "g_tk": 5381,
        },
        "req_1": {
            "module": "vkey.GetVkeyServer",
            "method": "CgiGetVkey",
            "param": {
                "filename": [f"{file_mid}{ext}"],
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

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError):
        return None

    midurlinfo = result.get("req_1", {}).get("data", {}).get("midurlinfo", [])
    if midurlinfo:
        ekey = midurlinfo[0].get("ekey", "")
        if ekey:
            return ekey
    return None


# Keep backward compat
def parse_musicex_tail(filepath: Path) -> dict | None:
    return parse_file_tail(filepath)


def fetch_ekey(song_mid: str, file_mid: str, cookie: str, uin: str) -> str | None:
    return _fetch_ekey_from_api(song_mid, file_mid, cookie, uin)
