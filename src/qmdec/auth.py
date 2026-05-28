"""Auto-extract QQ Music cookie from running process.

Supports two modes:
- Native Windows: uses ctypes Win32 API (zero external dependencies)
- WSL: invokes powershell.exe with inline C# to scan process memory
"""

import os
import re
import subprocess
import sys

COOKIE_MARKER = b"qqmusic_key="
IS_WINDOWS = sys.platform == "win32"
IS_WSL = not IS_WINDOWS and os.path.exists("/proc/version")


def _parse_cookie(raw: str) -> dict:
    cookie = raw.strip()
    for sep in ("\n", "\r", "\x00"):
        if sep in cookie:
            cookie = cookie.split(sep)[0]
    uin_match = re.search(r"qqmusic_uin=(\d+)", cookie)
    uin = uin_match.group(1) if uin_match else ""
    return {"cookie": cookie, "uin": uin}


def _extract_windows_native() -> dict:
    """Extract cookie using Win32 API directly (runs on native Windows)."""
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_INFORMATION = 0x0400
    MAX_PATH = 260

    enum_buf = (ctypes.wintypes.DWORD * 4096)()
    cb_needed = ctypes.wintypes.DWORD()
    psapi.EnumProcesses(ctypes.byref(enum_buf), ctypes.sizeof(enum_buf), ctypes.byref(cb_needed))

    num_procs = cb_needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
    qqmusic_pid = None

    for i in range(num_procs):
        pid = enum_buf[i]
        if pid == 0:
            continue
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        try:
            name_buf = (ctypes.c_char * MAX_PATH)()
            if psapi.GetModuleBaseNameA(h, None, name_buf, MAX_PATH):
                if name_buf.value == b"QQMusic.exe":
                    qqmusic_pid = pid
                    break
        finally:
            kernel32.CloseHandle(h)

    if qqmusic_pid is None:
        return {"ok": False, "error": "QQMusic.exe not running. Start QQ Music and log in first."}

    h_proc = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, qqmusic_pid)
    if not h_proc:
        return {"ok": False, "error": f"Cannot open QQMusic process (PID {qqmusic_pid}). Try running as Administrator."}

    try:
        class MEMORY_BASIC_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", ctypes.wintypes.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", ctypes.wintypes.DWORD),
                ("Protect", ctypes.wintypes.DWORD),
                ("Type", ctypes.wintypes.DWORD),
            ]

        MEM_COMMIT = 0x1000
        PAGE_READABLE = {0x02, 0x04, 0x06, 0x20, 0x40, 0x60, 0x80}

        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        bytes_read = ctypes.c_size_t()

        while addr < 0x7FFFFFFFFFFFFFFF:
            if kernel32.VirtualQueryEx(h_proc, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
                break
            if (mbi.State == MEM_COMMIT and mbi.Protect in PAGE_READABLE and 0x1000 <= mbi.RegionSize <= 50 * 1024 * 1024):
                buf = (ctypes.c_char * mbi.RegionSize)()
                if kernel32.ReadProcessMemory(h_proc, ctypes.c_void_p(mbi.BaseAddress), buf, mbi.RegionSize, ctypes.byref(bytes_read)):
                    data = bytes(buf[: bytes_read.value])
                    pos = data.find(COOKIE_MARKER)
                    if pos >= 0:
                        raw = data[pos : pos + 512].split(b"\x00")[0].decode("utf-8", errors="ignore")
                        parsed = _parse_cookie(raw)
                        if parsed["uin"]:
                            return {"ok": True, **parsed}
            addr = mbi.BaseAddress + mbi.RegionSize

        return {"ok": False, "error": "Cookie not found in QQMusic memory. Is QQ Music logged in?"}
    finally:
        kernel32.CloseHandle(h_proc)


_WSL_PS_SCRIPT = r'''
Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
public class QMEx {
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a,bool b,int p);
    [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h,IntPtr a,byte[] b,int s,out int r);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern int VirtualQueryEx(IntPtr h,IntPtr a,out MBI m,int l);
    [StructLayout(LayoutKind.Sequential)] public struct MBI {
        public IntPtr BaseAddress,AllocationBase; public uint AllocationProtect;
        public IntPtr RegionSize; public uint State,Protect,Type;
    }
    public static string Run() {
        var ps=Process.GetProcessesByName("QQMusic");
        if(ps.Length==0) return "ERROR:not_running";
        IntPtr h=OpenProcess(0x0410,false,ps[0].Id);
        if(h==IntPtr.Zero) return "ERROR:access_denied";
        try {
            byte[] mk=Encoding.ASCII.GetBytes("qqmusic_key=");
            IntPtr addr=IntPtr.Zero; MBI mbi;
            while(VirtualQueryEx(h,addr,out mbi,Marshal.SizeOf(typeof(MBI)))!=0) {
                long sz=mbi.RegionSize.ToInt64();
                if(mbi.State==0x1000 && sz>0 && sz<50*1024*1024) {
                    uint p2=mbi.Protect&0xFF;
                    if(p2==2||p2==4||p2==6||p2==0x20||p2==0x40||p2==0x60) {
                        byte[] buf=new byte[sz]; int rd;
                        if(ReadProcessMemory(h,mbi.BaseAddress,buf,buf.Length,out rd)) {
                            for(int i=0;i<=rd-mk.Length;i++) {
                                bool ok=true;
                                for(int j=0;j<mk.Length;j++) if(buf[i+j]!=mk[j]){ok=false;break;}
                                if(ok) {
                                    int end=Math.Min(i+512,rd);
                                    return Encoding.UTF8.GetString(buf,i,end-i).Split('\0')[0];
                                }
                            }
                        }
                    }
                }
                long next=mbi.BaseAddress.ToInt64()+sz;
                if(next<=addr.ToInt64()) break;
                addr=new IntPtr(next);
            }
            return "ERROR:not_found";
        } finally { CloseHandle(h); }
    }
}
"@
[QMEx]::Run()
'''


def _extract_wsl() -> dict:
    """Extract cookie from WSL by invoking PowerShell with inline C#."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", _WSL_PS_SCRIPT],
        capture_output=True, text=True, timeout=30,
    )
    output = (result.stdout + result.stderr).strip()

    if output.startswith("ERROR:"):
        error_map = {
            "ERROR:not_running": "QQMusic.exe not running. Start QQ Music and log in first.",
            "ERROR:access_denied": "Cannot open QQMusic process. Try running as Administrator.",
            "ERROR:not_found": "Cookie not found in QQMusic memory. Is QQ Music logged in?",
        }
        return {"ok": False, "error": error_map.get(output, output)}

    if "qqmusic_key=" in output:
        parsed = _parse_cookie(output)
        if parsed["uin"]:
            return {"ok": True, **parsed}

    return {"ok": False, "error": "Could not extract cookie.", "debug": output[:300]}


def extract_cookie_from_process() -> dict:
    if IS_WINDOWS:
        return _extract_windows_native()
    elif IS_WSL:
        return _extract_wsl()
    else:
        return {"ok": False, "error": "Unsupported platform. Requires Windows or WSL."}
