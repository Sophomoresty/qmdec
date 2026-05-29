"""QMC2 RC4 stream cipher."""

import math


class RC4Cipher:
    SEGMENT_SIZE = 5120
    FIRST_SEGMENT_SIZE = 128

    def __init__(self, key: bytes):
        self.key = key
        self.n = len(key)
        self.box = [i & 0xFF for i in range(self.n)]
        j = 0
        for i in range(self.n):
            j = (j + self.box[i] + key[i]) % self.n
            self.box[i], self.box[j] = self.box[j], self.box[i]
        self.hash = self._compute_hash()

    def _compute_hash(self) -> int:
        h = 1
        for v in self.key:
            if v == 0:
                continue
            # QQMusic's native implementation stores this accumulator in a
            # uint32.  The wraparound value is part of the cipher state: some
            # valid 512-byte FLAC keys (for example 五月天/倔强) continue after
            # overflow instead of stopping at the first >uint32 product.
            nh = (h * v) & 0xFFFFFFFF
            if nh == 0 or nh <= h:
                break
            h = nh
        return h

    def _get_segment_skip(self, id_val: int) -> int:
        seed = int(self.key[id_val % self.n])
        if seed == 0:
            return 0
        idx = int(float(self.hash) / float((id_val + 1) * seed) * 100.0)
        return idx % self.n

    def decrypt(self, buf: bytearray, offset: int) -> None:
        to_process = len(buf)
        processed = 0

        if offset < self.FIRST_SEGMENT_SIZE:
            block_size = min(to_process, self.FIRST_SEGMENT_SIZE - offset)
            self._enc_first_segment(buf, 0, block_size, offset)
            processed += block_size
            offset += block_size
            to_process -= block_size
            if to_process == 0:
                return

        if offset % self.SEGMENT_SIZE != 0:
            block_size = min(to_process, self.SEGMENT_SIZE - offset % self.SEGMENT_SIZE)
            self._enc_a_segment(buf, processed, block_size, offset)
            processed += block_size
            offset += block_size
            to_process -= block_size
            if to_process == 0:
                return

        while to_process > self.SEGMENT_SIZE:
            self._enc_a_segment(buf, processed, self.SEGMENT_SIZE, offset)
            processed += self.SEGMENT_SIZE
            offset += self.SEGMENT_SIZE
            to_process -= self.SEGMENT_SIZE

        if to_process > 0:
            self._enc_a_segment(buf, processed, to_process, offset)

    def _enc_first_segment(self, buf: bytearray, buf_offset: int, length: int, stream_offset: int) -> None:
        for i in range(length):
            skip = self._get_segment_skip(stream_offset + i)
            buf[buf_offset + i] ^= self.key[skip]

    def _enc_a_segment(self, buf: bytearray, buf_offset: int, length: int, stream_offset: int) -> None:
        box_copy = self.box.copy()
        j, k = 0, 0
        skip_len = (stream_offset % self.SEGMENT_SIZE) + self._get_segment_skip(stream_offset // self.SEGMENT_SIZE)

        for i in range(-skip_len, length):
            j = (j + 1) % self.n
            k = (box_copy[j] + k) % self.n
            box_copy[j], box_copy[k] = box_copy[k], box_copy[j]
            if i >= 0:
                idx = (box_copy[j] + box_copy[k]) % self.n
                buf[buf_offset + i] ^= box_copy[idx]
