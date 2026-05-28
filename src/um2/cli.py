"""um2 CLI - QQ Music musicex v1 decryptor."""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from .crypto import derive_key
from .musicex import fetch_ekey, parse_musicex_tail
from .rc4 import RC4Cipher

CONFIG_DIR = Path.home() / ".config" / "um2"
CONFIG_FILE = CONFIG_DIR / "config.json"
SUPPORTED_EXTS = {".mflac", ".mgg"}


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
    if data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return ".mp3"
    return ".bin"


def decrypt_file(filepath: Path, output_dir: Path, config: dict) -> dict:
    meta = parse_musicex_tail(filepath)
    if meta is None:
        return {"ok": False, "error": "not a musicex file", "file": str(filepath)}

    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    if not cookie or not uin:
        return {"ok": False, "error": "missing cookie/uin in config", "file": str(filepath)}

    file_mid = meta["filename"].replace(".mflac", "").replace(".mgg", "")
    ekey_b64 = fetch_ekey(meta["song_mid"], file_mid, cookie, uin)
    if not ekey_b64:
        return {"ok": False, "error": "empty ekey from API", "file": str(filepath)}

    raw_key_dec = base64.b64decode(ekey_b64)
    final_key = derive_key(raw_key_dec)
    if final_key is None:
        return {"ok": False, "error": "key derivation failed", "file": str(filepath)}

    cipher = RC4Cipher(final_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_size = meta["audio_size"]

    with open(filepath, "rb") as fin:
        first_chunk = bytearray(fin.read(min(4096, audio_size)))

    cipher_preview = RC4Cipher(final_key)
    preview = bytearray(first_chunk[:16])
    cipher_preview.decrypt(preview, 0)
    ext = sniff_ext(bytes(preview))

    stem = filepath.stem
    out_path = output_dir / f"{stem}{ext}"

    with open(filepath, "rb") as fin, open(out_path, "wb") as fout:
        offset = 0
        while offset < audio_size:
            read_size = min(5120, audio_size - offset)
            buf = bytearray(fin.read(read_size))
            cipher.decrypt(buf, offset)
            fout.write(buf)
            offset += read_size

    return {"ok": True, "file": str(filepath), "output": str(out_path), "format": ext[1:]}


def cmd_decrypt(args: argparse.Namespace) -> None:
    config = load_config()
    target = Path(args.input)
    output_dir = Path(args.output) if args.output else target.parent

    files = []
    if target.is_dir():
        for ext in SUPPORTED_EXTS:
            files.extend(target.glob(f"*{ext}"))
    elif target.is_file() and target.suffix in SUPPORTED_EXTS:
        files.append(target)
    else:
        print(json.dumps({"ok": False, "error": f"unsupported: {target}"}))
        sys.exit(1)

    results = []
    for f in sorted(files):
        r = decrypt_file(f, output_dir, config)
        results.append(r)
        status = "ok" if r["ok"] else f"FAIL: {r['error']}"
        print(f"  {f.name} -> {status}", file=sys.stderr)

    print(json.dumps({"ok": all(r["ok"] for r in results), "results": results}, indent=2))


def cmd_doctor(args: argparse.Namespace) -> None:
    config = load_config()
    checks = {
        "config_exists": CONFIG_FILE.exists(),
        "cookie_set": bool(config.get("cookie")),
        "uin_set": bool(config.get("uin")),
    }
    checks["ready"] = all(checks.values())
    if not checks["ready"]:
        checks["fix"] = f"Run: um2 init --cookie '<cookie>' --uin '<uin>'"
    print(json.dumps(checks, indent=2))


def cmd_init(args: argparse.Namespace) -> None:
    cfg = {"cookie": args.cookie, "uin": args.uin}
    save_config(cfg)
    print(json.dumps({"ok": True, "config_path": str(CONFIG_FILE)}))


def cmd_fetch_ekey(args: argparse.Namespace) -> None:
    config = load_config()
    cookie = config.get("cookie", "")
    uin = config.get("uin", "")
    ekey = fetch_ekey(args.song_mid, args.file_mid, cookie, uin)
    print(json.dumps({"ok": bool(ekey), "ekey": ekey or "", "length": len(ekey or "")}))


def cmd_auth(args: argparse.Namespace) -> None:
    from .auth import extract_cookie_from_process
    result = extract_cookie_from_process()
    if result["ok"]:
        save_config({"cookie": result["cookie"], "uin": result["uin"]})
        print(json.dumps({"ok": True, "uin": result["uin"], "config_path": str(CONFIG_FILE)}))
    else:
        print(json.dumps(result))
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="um2", description="QQ Music musicex v1 decryptor")
    sub = parser.add_subparsers(dest="command")

    p_decrypt = sub.add_parser("decrypt", help="Decrypt .mflac/.mgg files")
    p_decrypt.add_argument("input", help="File or directory to decrypt")
    p_decrypt.add_argument("-o", "--output", help="Output directory (default: same as input)")

    p_doctor = sub.add_parser("doctor", help="Check configuration")

    p_init = sub.add_parser("init", help="Configure cookie and uin")
    p_init.add_argument("--cookie", required=True)
    p_init.add_argument("--uin", required=True)

    p_ekey = sub.add_parser("fetch-ekey", help="Fetch ekey for a song")
    p_ekey.add_argument("song_mid")
    p_ekey.add_argument("file_mid")

    sub.add_parser("auth", help="Auto-extract cookie from running QQ Music")

    args = parser.parse_args()
    if args.command == "decrypt":
        cmd_decrypt(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "fetch-ekey":
        cmd_fetch_ekey(args)
    elif args.command == "auth":
        cmd_auth(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
