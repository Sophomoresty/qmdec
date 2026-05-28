"""qmdec CLI - QQ Music encrypted file decryptor."""

import argparse
import base64
import json
import sys
from pathlib import Path

from .crypto import derive_key
from .musicex import get_ekey, parse_file_tail, EKEY_CACHE_DIR
from .rc4 import RC4Cipher
from .map_cipher import MapCipher

CONFIG_DIR = Path.home() / ".config" / "qmdec"
CONFIG_FILE = CONFIG_DIR / "config.json"
SUPPORTED_EXTS = {".mflac", ".mgg", ".qmc0", ".qmc2", ".qmc3", ".qmcflac", ".qmcogg"}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def sniff_ext(data: bytes) -> str:
    if data[:4] == b"fLaC":
        return ".flac"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return ".mp3"
    if data[4:8] == b"ftyp":
        return ".m4a"
    return ".bin"


def decrypt_file(filepath: Path, output_dir: Path, config: dict, no_tag: bool = False) -> dict:
    meta = parse_file_tail(filepath)
    if meta is None:
        return {"ok": False, "error": "unsupported file format", "file": str(filepath)}

    cookie = config.get("cookie", "")
    uin = config.get("uin", "")

    ekey_b64 = get_ekey(meta, cookie, uin)
    if not ekey_b64:
        if not cookie:
            return {"ok": False, "error": "no ekey available. Run: qmdec auth", "file": str(filepath)}
        return {"ok": False, "error": "empty ekey (cookie may be expired). Run: qmdec auth", "file": str(filepath)}

    return _decrypt_with_ekey(filepath, output_dir, ekey_b64, meta["audio_size"],
                              meta.get("song_mid", ""), no_tag)


def _decrypt_with_ekey(filepath: Path, output_dir: Path, ekey_b64: str,
                       audio_size: int, song_mid: str, no_tag: bool) -> dict:
    """Decrypt a file using a known ekey (works with or without musicex tail)."""
    try:
        raw_key_dec = base64.b64decode(ekey_b64)
    except Exception:
        return {"ok": False, "error": "invalid ekey encoding", "file": str(filepath)}

    final_key = derive_key(raw_key_dec)
    if final_key is None:
        return {"ok": False, "error": "key derivation failed", "file": str(filepath)}

    def make_cipher(key):
        if len(key) > 300:
            return RC4Cipher(key)
        return MapCipher(key)

    cipher = make_cipher(final_key)
    output_dir.mkdir(parents=True, exist_ok=True)

    preview_cipher = make_cipher(final_key)
    with open(filepath, "rb") as fin:
        preview = bytearray(fin.read(min(16, audio_size)))
    preview_cipher.decrypt(preview, 0)
    ext = sniff_ext(bytes(preview))

    stem = filepath.stem
    out_path = output_dir / f"{stem}{ext}"

    with open(filepath, "rb") as fin, open(out_path, "wb") as fout:
        offset = 0
        while offset < audio_size:
            read_size = min(5120 * 10, audio_size - offset)
            buf = bytearray(fin.read(read_size))
            cipher.decrypt(buf, offset)
            fout.write(buf)
            offset += read_size

    tag_result = None
    if not no_tag and song_mid:
        try:
            from .metadata import write_metadata
            tag_result = write_metadata(out_path, song_mid)
        except Exception as e:
            tag_result = {"ok": False, "error": str(e)}

    return {"ok": True, "file": str(filepath), "output": str(out_path), "format": ext[1:], "tag": tag_result}


def cmd_decrypt(args: argparse.Namespace) -> None:
    config = load_config()
    target = Path(args.input)
    output_dir = Path(args.output) if args.output else (target if target.is_dir() else target.parent)

    files = []
    if target.is_dir():
        for ext in SUPPORTED_EXTS:
            files.extend(target.glob(f"*{ext}"))
    elif target.is_file() and target.suffix in SUPPORTED_EXTS:
        files.append(target)
    else:
        print(json.dumps({"ok": False, "error": f"unsupported: {target}"}))
        sys.exit(1)

    if not files:
        print(json.dumps({"ok": False, "error": "no encrypted files found"}))
        sys.exit(1)

    results = []
    ok_count = 0
    for f in sorted(files):
        r = decrypt_file(f, output_dir, config, no_tag=args.no_tag)
        results.append(r)
        if r["ok"]:
            ok_count += 1
            print(f"  [{ok_count}/{len(files)}] {f.name} -> {r['format']}", file=sys.stderr)
        else:
            print(f"  [{ok_count}/{len(files)}] {f.name} -> FAIL: {r['error']}", file=sys.stderr)

    summary = {"ok": ok_count == len(files), "total": len(files), "success": ok_count, "results": results}
    print(json.dumps(summary, indent=2))


def cmd_doctor(args: argparse.Namespace) -> None:
    config = load_config()
    cached_keys = len(list(EKEY_CACHE_DIR.glob("*.txt"))) if EKEY_CACHE_DIR.exists() else 0
    checks = {
        "config_exists": CONFIG_FILE.exists(),
        "cookie_set": bool(config.get("cookie")),
        "uin_set": bool(config.get("uin")),
        "cached_ekeys": cached_keys,
    }
    checks["ready"] = checks["cookie_set"] and checks["uin_set"]
    if not checks["ready"]:
        checks["fix"] = "Run: qmdec auth"
    print(json.dumps(checks, indent=2))


def cmd_init(args: argparse.Namespace) -> None:
    cfg = {"cookie": args.cookie, "uin": args.uin}
    save_config(cfg)
    print(json.dumps({"ok": True, "config_path": str(CONFIG_FILE)}))


def cmd_auth(args: argparse.Namespace) -> None:
    from .auth import extract_cookie_from_process
    result = extract_cookie_from_process()
    if result["ok"]:
        save_config({"cookie": result["cookie"], "uin": result["uin"]})
        print(json.dumps({"ok": True, "uin": result["uin"], "config_path": str(CONFIG_FILE)}))
    else:
        print(json.dumps(result))
        sys.exit(1)


def cmd_cache_keys(args: argparse.Namespace) -> None:
    """Pre-fetch and cache ekeys for all encrypted files in a directory."""
    config = load_config()
    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    if not cookie or not uin:
        print(json.dumps({"ok": False, "error": "not authenticated. Run: qmdec auth"}))
        sys.exit(1)

    target = Path(args.input)
    files = []
    if target.is_dir():
        for ext in SUPPORTED_EXTS:
            files.extend(target.glob(f"*{ext}"))
    elif target.is_file():
        files.append(target)

    cached = 0
    failed = 0
    for f in sorted(files):
        meta = parse_file_tail(f)
        if meta is None:
            continue
        ekey = get_ekey(meta, cookie, uin)
        if ekey:
            cached += 1
            print(f"  {f.name} -> cached", file=sys.stderr)
        else:
            failed += 1
            print(f"  {f.name} -> FAIL", file=sys.stderr)

    print(json.dumps({"ok": failed == 0, "cached": cached, "failed": failed}))


def cmd_fetch_ekey(args: argparse.Namespace) -> None:
    config = load_config()
    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    from .musicex import _fetch_ekey_from_api
    ekey = _fetch_ekey_from_api(args.song_mid, args.file_mid, cookie, uin)
    print(json.dumps({"ok": bool(ekey), "ekey": ekey or "", "length": len(ekey or "")}))


def cmd_search(args: argparse.Namespace) -> None:
    config = load_config()
    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    if not cookie:
        print(json.dumps({"ok": False, "error": "not authenticated. Run: qmdec auth"}))
        sys.exit(1)

    from .download import search_songs
    songs = search_songs(args.keyword, cookie, uin, limit=args.limit)
    if not songs:
        print(json.dumps({"ok": False, "error": "no results"}))
        sys.exit(1)

    results = []
    for i, s in enumerate(songs):
        results.append({
            "n": i + 1,
            "title": s["title"],
            "singer": s["singer"],
            "album": s["album"],
            "song_mid": s["song_mid"],
            "quality": {
                "flac": f"{s['size_flac'] / 1024 / 1024:.1f}MB" if s["size_flac"] else "-",
                "320k": f"{s['size_320'] / 1024 / 1024:.1f}MB" if s["size_320"] else "-",
                "128k": f"{s['size_128'] / 1024 / 1024:.1f}MB" if s["size_128"] else "-",
            },
        })
        print(f"  [{i+1}] {s['title']} - {s['singer']} ({s['album']})", file=sys.stderr)

    print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2))


def cmd_download(args: argparse.Namespace) -> None:
    config = load_config()
    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    if not cookie:
        print(json.dumps({"ok": False, "error": "not authenticated. Run: qmdec auth"}))
        sys.exit(1)

    from .download import search_songs, get_download_info, download_file
    import tempfile

    songs = search_songs(args.keyword, cookie, uin, limit=args.pick)
    if not songs:
        print(json.dumps({"ok": False, "error": "no results"}))
        sys.exit(1)

    pick_idx = min(args.pick, len(songs)) - 1
    song = songs[pick_idx]
    print(f"  Downloading: {song['title']} - {song['singer']} [{args.quality}]", file=sys.stderr)

    info = get_download_info(song["song_mid"], song["media_mid"], args.quality, cookie, uin)
    if not info:
        print(json.dumps({"ok": False, "error": "cannot get download URL (VIP required for this quality)"}))
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.quality == "flac" and info["ekey"]:
        tmp_path = output_dir / f"{song['title']} - {song['singer']}.mflac"
        print(f"  Fetching encrypted file...", file=sys.stderr)

        def progress(downloaded, total):
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  [{pct}%] {downloaded // 1024}KB / {total // 1024}KB", end="", file=sys.stderr)

        ok = download_file(info["url"], tmp_path, callback=progress)
        print("", file=sys.stderr)

        if not ok:
            print(json.dumps({"ok": False, "error": "download failed"}))
            sys.exit(1)

        from .musicex import _cache_ekey, EKEY_CACHE_DIR
        _cache_ekey(song["song_mid"], info["ekey"])

        print(f"  Decrypting...", file=sys.stderr)
        audio_size = tmp_path.stat().st_size
        result = _decrypt_with_ekey(tmp_path, output_dir, info["ekey"], audio_size,
                                    song["song_mid"], args.no_tag)
        tmp_path.unlink(missing_ok=True)

        if result["ok"]:
            print(json.dumps({"ok": True, "output": result["output"], "format": result["format"],
                             "title": song["title"], "singer": song["singer"], "tag": result.get("tag")}))
        else:
            print(json.dumps(result))
            sys.exit(1)
    else:
        ext = ".mp3" if args.quality in ("320", "128") else ".flac"
        out_path = output_dir / f"{song['title']} - {song['singer']}{ext}"
        print(f"  Downloading directly...", file=sys.stderr)

        def progress(downloaded, total):
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  [{pct}%] {downloaded // 1024}KB / {total // 1024}KB", end="", file=sys.stderr)

        ok = download_file(info["url"], out_path, callback=progress)
        print("", file=sys.stderr)

        if not ok:
            print(json.dumps({"ok": False, "error": "download failed"}))
            sys.exit(1)

        tag_result = None
        if not args.no_tag:
            try:
                from .metadata import write_metadata
                tag_result = write_metadata(out_path, song["song_mid"])
            except Exception as e:
                tag_result = {"ok": False, "error": str(e)}

        print(json.dumps({"ok": True, "output": str(out_path), "format": ext[1:],
                         "title": song["title"], "singer": song["singer"], "tag": tag_result}))

def main():
    parser = argparse.ArgumentParser(prog="qmdec", description="QQ Music encrypted file decryptor")
    sub = parser.add_subparsers(dest="command")

    p_decrypt = sub.add_parser("decrypt", help="Decrypt .mflac/.mgg files")
    p_decrypt.add_argument("input", help="File or directory to decrypt")
    p_decrypt.add_argument("-o", "--output", help="Output directory")
    p_decrypt.add_argument("--no-tag", action="store_true", help="Skip metadata tagging")

    p_search = sub.add_parser("search", help="Search songs")
    p_search.add_argument("keyword", help="Search keyword")
    p_search.add_argument("-n", "--limit", type=int, default=10, help="Max results")

    p_dl = sub.add_parser("download", help="Search, download, decrypt and tag")
    p_dl.add_argument("keyword", help="Search keyword or song_mid")
    p_dl.add_argument("-o", "--output", help="Output directory", default=".")
    p_dl.add_argument("-q", "--quality", choices=["flac", "320", "128"], default="flac")
    p_dl.add_argument("-n", "--pick", type=int, default=1, help="Pick Nth result (default: 1st)")
    p_dl.add_argument("--no-tag", action="store_true", help="Skip metadata tagging")

    sub.add_parser("auth", help="Auto-extract cookie from running QQ Music")
    sub.add_parser("doctor", help="Check configuration status")

    p_cache = sub.add_parser("cache-keys", help="Pre-fetch ekeys for offline use")
    p_cache.add_argument("input", help="File or directory")

    p_init = sub.add_parser("init", help="Manually configure cookie and uin")
    p_init.add_argument("--cookie", required=True)
    p_init.add_argument("--uin", required=True)

    p_ekey = sub.add_parser("fetch-ekey", help="Fetch ekey for a song (debug)")
    p_ekey.add_argument("song_mid")
    p_ekey.add_argument("file_mid")

    args = parser.parse_args()
    commands = {
        "decrypt": cmd_decrypt,
        "search": cmd_search,
        "download": cmd_download,
        "auth": cmd_auth,
        "doctor": cmd_doctor,
        "cache-keys": cmd_cache_keys,
        "init": cmd_init,
        "fetch-ekey": cmd_fetch_ekey,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
