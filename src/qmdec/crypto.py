"""QMC2 RC4 cipher and Tencent TEA for QQ Music musicex decryption."""

import math
import struct
from pathlib import Path


def simple_make_key(salt: int, length: int) -> bytes:
    buf = bytearray(length)
    for i in range(length):
        buf[i] = int(abs(math.tan(float(salt) + float(i) * 0.1)) * 100.0) & 0xFF
    return bytes(buf)


def tea_decrypt_block(block: bytes, key: bytes) -> bytes:
    v0, v1 = struct.unpack(">II", block)
    k0, k1, k2, k3 = struct.unpack(">4I", key)
    delta = 0x9E3779B9
    total = (delta * 16) & 0xFFFFFFFF
    for _ in range(16):
        v1 = (v1 - (((v0 << 4) + k2) ^ (v0 + total) ^ ((v0 >> 5) + k3))) & 0xFFFFFFFF
        v0 = (v0 - (((v1 << 4) + k0) ^ (v1 + total) ^ ((v1 >> 5) + k1))) & 0xFFFFFFFF
        total = (total - delta) & 0xFFFFFFFF
    return struct.pack(">II", v0, v1)


def decrypt_tencent_tea(in_buf: bytes, key: bytes) -> bytes | None:
    if len(in_buf) % 8 != 0 or len(in_buf) < 16:
        return None
    dest_buf = bytearray(tea_decrypt_block(in_buf[:8], key))
    pad_len = dest_buf[0] & 0x07
    out_len = len(in_buf) - 1 - pad_len - 2 - 7
    if out_len <= 0:
        return None
    out = bytearray(out_len)
    iv_prev, iv_cur = bytes(8), in_buf[:8]
    in_pos, dest_idx = 8, 1 + pad_len

    def crypt_block():
        nonlocal iv_prev, iv_cur, in_pos, dest_buf, dest_idx
        iv_prev = iv_cur
        iv_cur = in_buf[in_pos : in_pos + 8]
        dest_buf = bytearray(dest_buf[i] ^ in_buf[in_pos + i] for i in range(8))
        dest_buf = bytearray(tea_decrypt_block(bytes(dest_buf), key))
        in_pos += 8
        dest_idx = 0

    i = 0
    while i < 2:
        if dest_idx < 8:
            dest_idx += 1
            i += 1
        else:
            crypt_block()
    out_pos = 0
    while out_pos < out_len:
        if dest_idx < 8:
            out[out_pos] = dest_buf[dest_idx] ^ iv_prev[dest_idx]
            dest_idx += 1
            out_pos += 1
        else:
            crypt_block()
    return bytes(out)


def derive_key(raw_key_dec: bytes) -> bytes | None:
    simple_key = simple_make_key(106, 8)
    tea_key = bytearray(16)
    for i in range(8):
        tea_key[i * 2] = simple_key[i]
        tea_key[i * 2 + 1] = raw_key_dec[i]
    rs = decrypt_tencent_tea(raw_key_dec[8:], bytes(tea_key))
    if rs is None:
        return None
    return raw_key_dec[:8] + rs
