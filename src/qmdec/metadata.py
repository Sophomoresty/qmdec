"""Fetch and write complete music metadata from QQ Music API."""

import base64
import json
import urllib.request
from pathlib import Path

import music_tag


GENRE_MAP = {
    1: "Pop", 2: "Classical", 3: "Jazz", 4: "R&B/Soul", 5: "Rock",
    6: "Dance", 7: "Hip-Hop", 8: "Electronic", 9: "Folk", 10: "Country",
    11: "Blues", 12: "Latin", 13: "New Age", 14: "World Music", 15: "Reggae",
    16: "Metal", 17: "Punk", 19: "Light Music", 20: "Soundtrack",
    21: "Children", 22: "Anime", 24: "Chinese Style", 25: "Bossa Nova",
    34: "Pop", 36: "K-Pop",
}

LANG_MAP = {
    0: "Chinese", 1: "English", 2: "Japanese", 3: "Cantonese",
    4: "Korean", 5: "French", 6: "Other",
}


def _api_call(data, cookie="", timeout=10):
    url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    req = urllib.request.Request(url, json.dumps(data).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "QQMusic/21")
    if cookie:
        req.add_header("Cookie", cookie)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


def fetch_song_detail(song_mid: str, cookie: str = "", uin: str = "") -> dict | None:
    data = {
        "comm": {"cv": 4747474, "ct": 24, "format": "json", "uin": int(uin or 0)},
        "req_1": {
            "module": "music.search.SearchCgiService",
            "method": "DoSearchForQQMusicDesktop",
            "param": {"query": song_mid, "page_num": 1, "num_per_page": 1, "search_type": 0},
        },
    }
    try:
        r = _api_call(data, cookie)
        songs = r["req_1"]["data"]["body"]["song"]["list"]
        if songs:
            return songs[0]
    except Exception:
        pass
    return None


def fetch_metadata_from_album_song(song_info: dict, album_info: dict | None = None) -> dict:
    """Build complete metadata dict from album song list API response."""
    singers = [s.get("title", s.get("name", "")) for s in song_info.get("singer", [])]
    album = song_info.get("album", {})
    file_info = song_info.get("file", {})

    album_mid = album.get("mid", "")
    album_date = album.get("time_public", "") or song_info.get("time_public", "")

    genre_id = song_info.get("genre", 0)
    lang_id = song_info.get("language", 0)

    meta = {
        "title": song_info.get("title", song_info.get("name", "")),
        "artist": "/".join(singers),
        "albumartist": singers[0] if singers else "",
        "album": album.get("title", album.get("name", "")),
        "album_mid": album_mid,
        "song_mid": song_info.get("mid", ""),
        "track": song_info.get("index_album", 0),
        "disc": (song_info.get("index_cd", 0) or 0) + 1,
        "year": album_date[:4] if album_date else "",
        "genre": GENRE_MAP.get(genre_id, "K-Pop") if genre_id else "",
        "language": LANG_MAP.get(lang_id, ""),
        "cover_url": f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg" if album_mid else "",
    }

    if album_info:
        basic = album_info.get("basicInfo", {})
        if basic.get("genre"):
            meta["genre"] = basic["genre"]
        if basic.get("language"):
            meta["language"] = basic["language"]
        if not meta["year"] and basic.get("publishDate"):
            meta["year"] = basic["publishDate"][:4]

    return meta


def fetch_lyrics(song_mid: str, cookie: str = "", uin: str = "") -> str | None:
    data = {
        "comm": {"cv": 4747474, "ct": 24, "format": "json", "uin": int(uin or 0)},
        "req_1": {
            "module": "music.musichallSong.PlayLyricInfo",
            "method": "GetPlayLyricInfo",
            "param": {"songMID": song_mid, "songID": 0},
        },
    }
    try:
        r = _api_call(data, cookie)
        ld = r.get("req_1", {}).get("data", {})
        lyric_b64 = ld.get("lyric", "")
        trans_b64 = ld.get("trans", "")

        lyric = base64.b64decode(lyric_b64).decode("utf-8", errors="replace") if lyric_b64 else ""
        trans = base64.b64decode(trans_b64).decode("utf-8", errors="replace") if trans_b64 else ""

        if trans and lyric:
            return lyric.rstrip() + "\n" + trans.rstrip()
        return lyric if lyric else None
    except Exception:
        return None


def fetch_cover(url: str) -> bytes | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=15)
        data = resp.read()
        return data if len(data) > 1000 else None
    except Exception:
        return None


def fetch_metadata(song_mid: str) -> dict | None:
    """Legacy compat: fetch metadata by song_mid via search."""
    detail = fetch_song_detail(song_mid)
    if not detail:
        return None
    meta = fetch_metadata_from_album_song(detail)
    return meta


def write_metadata(filepath: Path, song_mid: str, meta: dict | None = None,
                   cookie: str = "", uin: str = "") -> dict:
    """Write complete metadata to a music file.

    Fields written: title, artist, albumartist, album, tracknumber, discnumber,
    year, genre, lyrics, artwork, comment (language).
    """
    if meta is None:
        meta = fetch_metadata(song_mid)
    if meta is None:
        return {"ok": False, "error": "metadata not found"}

    try:
        f = music_tag.load_file(str(filepath))
    except Exception as e:
        return {"ok": False, "error": f"cannot open file: {e}"}

    if meta.get("title"):
        f["title"] = meta["title"]
    if meta.get("artist"):
        f["artist"] = meta["artist"]
    if meta.get("albumartist"):
        f["albumartist"] = meta["albumartist"]
    if meta.get("album"):
        f["album"] = meta["album"]
    if meta.get("year"):
        f["year"] = int(meta["year"])
    if meta.get("track"):
        f["tracknumber"] = meta["track"]
    if meta.get("disc"):
        f["discnumber"] = meta["disc"]
    if meta.get("genre"):
        f["genre"] = meta["genre"]
    if meta.get("language"):
        f["comment"] = meta["language"]

    # Lyrics
    mid = meta.get("song_mid", song_mid)
    if mid:
        lyrics = fetch_lyrics(mid, cookie, uin)
        if lyrics and len(lyrics) > 20:
            f["lyrics"] = lyrics

    # Cover art
    cover = fetch_cover(meta.get("cover_url", ""))
    if cover:
        f["artwork"] = cover

    f.save()
    return {"ok": True, "title": meta.get("title", ""), "artist": meta.get("artist", ""),
            "album": meta.get("album", "")}
