<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="qmdec">
</p>

<h1 align="center">qmdec</h1>

<p align="center">QQ Music encrypted file decryptor with auto-tagging</p>

<p align="center">
  <a href="#installation">Install</a> •
  <a href="#usage">Usage</a> •
  <a href="#how-it-works">How it works</a> •
  <a href="#中文说明">中文</a>
</p>

---

## Installation

**Windows (recommended):** Download `qmdec.exe` from [Releases](../../releases).

**pip:**
```bash
pip install qmdec
```

## Usage

```bash
# Step 1: Open QQ Music and log in
# Step 2: Extract auth cookie (auto)
qmdec auth

# Step 3: Decrypt files
qmdec decrypt "C:\Users\You\Music\VipSongsDownload\song.mflac"

# Batch decrypt entire directory
qmdec decrypt "C:\Users\You\Music\VipSongsDownload\" -o "D:\Music\Decoded\"

# Skip metadata tagging
qmdec decrypt song.mflac --no-tag

# Check setup
qmdec doctor
```

## How it works

1. **Auth** — Scans QQMusic.exe process memory for the session cookie (zero external dependencies, pure Win32 API)
2. **Decrypt** — Parses musicex v1 file tail, fetches ekey from QQ Music API, decrypts audio with QMC2 RC4 cipher
3. **Tag** — Fetches metadata (title, artist, album, cover art) from QQ Music public API and writes it into the output file

## Supported formats

| Extension | Source | Output |
|-----------|--------|--------|
| `.mflac` | QQ Music FLAC | `.flac` |
| `.mgg` | QQ Music OGG | `.ogg` |

## Requirements

- Windows 10/11
- QQ Music desktop client (logged in with VIP)
- Cookie expires periodically — re-run `qmdec auth` when decryption fails

## License

MIT

---

# 中文说明

## 安装

**Windows:** 从 [Releases](../../releases) 下载 `qmdec.exe`, 无需安装 Python.

**pip 安装:**
```bash
pip install qmdec
```

## 使用方法

```bash
# 1. 打开 QQ 音乐并登录 (需要 VIP)
# 2. 自动提取登录凭证
qmdec auth

# 3. 解密文件 (自动写入歌曲信息和封面)
qmdec decrypt "周杰伦 - 晴天.mflac"

# 批量解密整个目录
qmdec decrypt "C:\Users\你\Music\VipSongsDownload\" -o "D:\音乐\解密\"

# 检查配置状态
qmdec doctor
```

## 工作原理

1. **认证** — 扫描 QQMusic.exe 进程内存提取 cookie (纯 Win32 API, 无外部依赖)
2. **解密** — 解析 musicex v1 文件尾部, 从 QQ 音乐 API 获取 ekey, 使用 QMC2 RC4 算法解密音频
3. **打标签** — 从 QQ 音乐公开 API 获取歌曲元信息 (标题/歌手/专辑/封面) 并写入文件

## 注意事项

- 需要 QQ 音乐客户端保持登录状态
- Cookie 会过期, 解密失败时重新运行 `qmdec auth`
- 解密后的文件可在任何播放器中播放
