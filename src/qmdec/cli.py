"""qmdec CLI - QQ Music encrypted file decryptor."""

import argparse
import base64
import json
import sys
from pathlib import Path

from .crypto import derive_key
from .musicex import get_ekey, parse_file_tail, EKEY_CACHE_DIR
from .rc4 import RC4Cipher

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

    try:
        raw_key_dec = base64.b64decode(ekey_b64)
    except Exception:
        return {"ok": False, "error": "invalid ekey encoding", "file": str(filepath)}

    final_key = derive_key(raw_key_dec)
    if final_key is None:
        return {"ok": False, "error": "key derivation failed", "file": str(filepath)}

    cipher = RC4Cipher(final_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_size = meta["audio_size"]

    preview_cipher = RC4Cipher(final_key)
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
    if not no_tag and meta.get("song_mid"):
        try:
            from .metadata import write_metadata
            tag_result = write_metadata(out_path, meta["song_mid"])
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


def main():
    parser = argparse.ArgumentParser(prog="qmdec", description="QQ Music encrypted file decryptor")
    sub = parser.add_subparsers(dest="command")

    p_decrypt = sub.add_parser("decrypt", help="Decrypt .mflac/.mgg files")
    p_decrypt.add_argument("input", help="File or directory to decrypt")
    p_decrypt.add_argument("-o", "--output", help="Output directory")
    p_decrypt.add_argument("--no-tag", action="store_true", help="Skip metadata tagging")

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
