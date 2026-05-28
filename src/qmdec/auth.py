"""Auto-extract QQ Music cookie from running process.

Supports two modes:
- Native Windows: uses ctypes ReadProcessMemory
- WSL: invokes frida.exe on Windows side via powershell.exe
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _find_frida() -> str | None:
    candidates = [
        r"D:\Tools\bin\frida.exe",
        r"C:\Tools\frida.exe",
    ]
    for c in candidates:
        wsl_path = c.replace("\\", "/")
        wsl_path = "/mnt/" + wsl_path[0].lower() + wsl_path[2:]
        if os.path.exists(wsl_path):
            return c
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", "where.exe frida"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[0].strip()
    return None


def _find_qqmusic_pid() -> int | None:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "Get-Process -Name QQMusic -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Id"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            return int(result.stdout.strip())
        except ValueError:
            pass
    return None


def _parse_cookie(raw: str) -> dict:
    cookie = raw.strip()
    if "\n" in cookie:
        cookie = cookie.split("\n")[0]
    if "\r" in cookie:
        cookie = cookie.split("\r")[0]
    uin_match = re.search(r"qqmusic_uin=(\d+)", cookie)
    uin = uin_match.group(1) if uin_match else ""
    return {"cookie": cookie, "uin": uin}


def extract_cookie_from_process() -> dict:
    pid = _find_qqmusic_pid()
    if pid is None:
        return {"ok": False, "error": "QQMusic.exe not running. Start QQ Music and log in first."}

    frida_path = _find_frida()
    if frida_path is None:
        return {"ok": False, "error": "frida.exe not found. Install Frida or place it in D:\\Tools\\bin\\"}

    hook_script = Path(__file__).parent / "auth_hook.js"
    if not hook_script.exists():
        return {"ok": False, "error": f"auth_hook.js not found at {hook_script}"}

    win_script_path = subprocess.run(
        ["wslpath", "-w", str(hook_script)],
        capture_output=True, text=True
    ).stdout.strip()

    cmd = f'& "{frida_path}" -p {pid} -l "{win_script_path}" -q'
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=30
    )

    output = result.stdout + result.stderr
    cookie_match = re.search(r"'value':\s*'(qqmusic_key=[^']+)'", output)
    if not cookie_match:
        cookie_match = re.search(r'"value":\s*"(qqmusic_key=[^"]+)"', output)
    if not cookie_match:
        for line in output.split("\n"):
            if "qqmusic_key=" in line:
                start = line.find("qqmusic_key=")
                end = line.find("'", start)
                if end < 0:
                    end = line.find('"', start)
                if end < 0:
                    end = len(line)
                raw_cookie = line[start:end]
                parsed = _parse_cookie(raw_cookie)
                if parsed["uin"]:
                    return {"ok": True, **parsed}

    if cookie_match:
        raw_cookie = cookie_match.group(1)
        parsed = _parse_cookie(raw_cookie)
        if parsed["uin"]:
            return {"ok": True, **parsed}

    return {"ok": False, "error": "Could not extract cookie. Is QQ Music logged in?", "debug": output[:500]}
