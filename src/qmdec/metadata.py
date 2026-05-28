"""Fetch and write music metadata from QQ Music API."""

import json
import urllib.request
from pathlib import Path

import music_tag


def fetch_metadata(song_mid: str) -> dict | None:
    url = f"https://c.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg?songmid={song_mid}&format=json"
    req = urllib.request.Request(url)
    req.add_header("Referer", "https://y.qq.com")
    req.add_header("User-Agent", "Mozilla/5.0")

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
    except Exception:
        return None

    data = result.get("data", [])
    if not data:
        return None

    song = data[0]
    artists = [s.get("name", "") for s in song.get("singer", [])]
    album_mid = song.get("album", {}).get("mid", "")

    return {
        "title": song.get("name", ""),
        "artist": ", ".join(artists),
        "album": song.get("album", {}).get("name", ""),
        "album_mid": album_mid,
        "year": song.get("time_public", "")[:4],
        "track_number": song.get("index_album", 0),
        "genre": song.get("genre", 0),
        "cover_url": f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg" if album_mid else "",
    }


def fetch_cover(url: str) -> bytes | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.read()
    except Exception:
        return None


def write_metadata(filepath: Path, song_mid: str) -> dict:
    meta = fetch_metadata(song_mid)
    if meta is None:
        return {"ok": False, "error": "metadata not found"}

    try:
        f = music_tag.load_file(str(filepath))
    except Exception as e:
        return {"ok": False, "error": f"cannot open file: {e}"}

    if meta["title"]:
        f["title"] = meta["title"]
    if meta["artist"]:
        f["artist"] = meta["artist"]
    if meta["album"]:
        f["album"] = meta["album"]
    if meta["year"]:
        f["year"] = int(meta["year"])
    if meta["track_number"]:
        f["tracknumber"] = meta["track_number"]

    cover_data = fetch_cover(meta["cover_url"])
    if cover_data:
        f["artwork"] = cover_data

    f.save()
    return {"ok": True, "title": meta["title"], "artist": meta["artist"], "album": meta["album"]}
