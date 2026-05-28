<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="qmdec">
</p>

<h1 align="center">qmdec</h1>

<p align="center">QQ Music encrypted file decryptor with auto-tagging</p>

<p align="center">
  <a href="#installation">Install</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#commands">Commands</a> •
  <a href="#faq">FAQ</a> •
  <a href="#中文说明">中文</a>
</p>

---

## Installation

**Windows (recommended):** Download `qmdec.exe` from [Releases](../../releases). No Python needed.

**pip (requires Python 3.10+):**
```bash
pip install qmdec
```

## Quick Start

```bash
# 1. Make sure QQ Music is running and you're logged in (VIP account)

# 2. Run auth — automatically extracts your login cookie
qmdec auth

# 3. Decrypt your files
qmdec decrypt "C:\Users\You\Music\VipSongsDownload" -o "D:\Music"
```

That's it. Output files have full metadata (title, artist, album, cover art).

## Commands

### `qmdec auth`

Scans QQMusic.exe process memory and extracts the session cookie. Requires QQ Music to be running and logged in.

```bash
qmdec auth
```

### `qmdec decrypt <path> [-o output_dir] [--no-tag]`

Decrypts a single file or all encrypted files in a directory.

```bash
# Single file
qmdec decrypt "周杰伦 - 晴天.mflac"

# Entire directory
qmdec decrypt "C:\Users\You\Music\VipSongsDownload" -o "D:\Music\Decoded"

# Without metadata tagging (faster)
qmdec decrypt song.mflac --no-tag
```

### `qmdec cache-keys <path>`

Pre-fetches and caches ekeys for all encrypted files. After caching, decryption works offline (no cookie needed).

```bash
# Cache all keys while your cookie is still valid
qmdec cache-keys "C:\Users\You\Music\VipSongsDownload"

# Now you can decrypt anytime, even after cookie expires
qmdec decrypt "C:\Users\You\Music\VipSongsDownload" -o "D:\Music"
```

### `qmdec doctor`

Shows configuration status: cookie validity, cached ekey count.

```bash
qmdec doctor
```

### `qmdec init --cookie <cookie> --uin <uin>`

Manually set cookie (alternative to `qmdec auth`).

## How it works

1. **Auth** — Reads QQMusic.exe process memory using Win32 API (`ReadProcessMemory`). Zero external dependencies.
2. **Ekey fetch** — Uses the cookie to call QQ Music's API and get the decryption key for each song. Keys are cached locally.
3. **Decrypt** — QMC2 RC4 cipher (same algorithm QQ Music uses internally).
4. **Tag** — Fetches metadata from QQ Music's public API (no auth needed) and writes it into the output file.

## Supported formats

| Input | Output | Notes |
|-------|--------|-------|
| `.mflac` | `.flac` | musicex v1 (new format) |
| `.mgg` | `.ogg` | musicex v1 (new format) |
| `.mflac` / `.mgg` | `.flac` / `.ogg` | Legacy QTag/STag (old format) |

## Offline mode

Once ekeys are cached (`qmdec cache-keys` or after first successful decrypt), you can decrypt without network access and without a valid cookie. The cached keys never expire.

## FAQ

**Q: `qmdec auth` says "QQMusic.exe not running"**
A: Open QQ Music desktop client and log in first.

**Q: `qmdec auth` says "access denied"**
A: Run qmdec as Administrator (right-click → Run as administrator).

**Q: Decryption fails with "empty ekey" or "cookie expired"**
A: Your session expired. Run `qmdec auth` again (QQ Music must be open and logged in).

**Q: Can I decrypt files on a different computer?**
A: Yes. Run `qmdec cache-keys` on the computer with QQ Music to save all keys, then copy `~/.config/qmdec/ekeys/` to the other computer.

**Q: Does this work without VIP?**
A: No. The encrypted files are only downloadable with VIP, and the ekey API requires VIP authentication.

## Requirements

- Windows 10/11
- QQ Music desktop client (logged in with VIP) — only needed for `auth` and first-time ekey fetch
- After keys are cached, QQ Music is not needed

## Acknowledgments

- [linux.do](https://linux.do) — Community & inspiration

## License

MIT

---

# 中文说明

## 安装

**Windows:** 从 [Releases](../../releases) 下载 `qmdec.exe`, 双击即可使用, 无需安装 Python.

**pip:**
```bash
pip install qmdec
```

## 快速开始

```bash
# 1. 打开 QQ 音乐客户端, 确保已登录 VIP 账号

# 2. 提取登录凭证 (自动从 QQ 音乐进程内存读取)
qmdec auth

# 3. 解密文件 (自动写入歌曲信息和封面)
qmdec decrypt "C:\Users\你\Music\VipSongsDownload" -o "D:\音乐"
```

输出的文件包含完整元信息 (标题, 歌手, 专辑, 封面), 可直接在任何播放器中使用.

## 命令说明

### `qmdec auth` — 提取登录凭证

扫描 QQMusic.exe 进程内存, 自动提取 cookie. 需要 QQ 音乐正在运行且已登录.

### `qmdec decrypt <路径> [-o 输出目录] [--no-tag]` — 解密

```bash
# 解密单个文件
qmdec decrypt "周杰伦 - 晴天.mflac"

# 批量解密整个目录
qmdec decrypt "C:\Users\你\Music\VipSongsDownload" -o "D:\音乐\解密"

# 不写入元信息 (更快)
qmdec decrypt song.mflac --no-tag
```

### `qmdec cache-keys <路径>` — 预缓存密钥

一次性获取所有文件的解密密钥并保存到本地. 缓存后即使 cookie 过期也能解密.

```bash
# 趁 cookie 有效时缓存所有密钥
qmdec cache-keys "C:\Users\你\Music\VipSongsDownload"

# 之后随时可以离线解密
qmdec decrypt "C:\Users\你\Music\VipSongsDownload" -o "D:\音乐"
```

### `qmdec doctor` — 检查状态

显示配置状态, cookie 是否有效, 已缓存的密钥数量.

## 离线模式

密钥一旦缓存 (通过 `cache-keys` 或首次解密成功后自动缓存), 后续解密不需要网络, 也不需要有效的 cookie. 缓存的密钥永不过期.

## 常见问题

**Q: 提示 "QQMusic.exe not running"**
A: 先打开 QQ 音乐客户端并登录.

**Q: 提示 "access denied"**
A: 以管理员身份运行 (右键 → 以管理员身份运行).

**Q: 解密失败, 提示 "cookie expired"**
A: Cookie 过期了, 重新运行 `qmdec auth` (需要 QQ 音乐在线).

**Q: 能在没有 QQ 音乐的电脑上解密吗?**
A: 可以. 先在有 QQ 音乐的电脑上运行 `qmdec cache-keys` 缓存密钥, 然后把 `~/.config/qmdec/ekeys/` 目录复制到另一台电脑.

**Q: 没有 VIP 能用吗?**
A: 不能. 加密文件只有 VIP 才能下载, ekey 接口也需要 VIP 认证.

## 工作原理

1. **认证** — 使用 Win32 API (`ReadProcessMemory`) 读取 QQ 音乐进程内存, 提取 session cookie
2. **获取密钥** — 用 cookie 调用 QQ 音乐 API 获取每首歌的解密密钥 (ekey), 自动缓存到本地
3. **解密** — QMC2 RC4 算法 (与 QQ 音乐客户端内部使用的相同算法)
4. **写标签** — 从 QQ 音乐公开 API 获取元信息 (无需认证) 写入文件

## 致谢

- [linux.do](https://linux.do) — 社区支持

## 系统要求

- Windows 10/11
- QQ 音乐桌面客户端 (已登录 VIP) — 仅 `auth` 和首次获取密钥时需要
- 密钥缓存后, 不再需要 QQ 音乐
