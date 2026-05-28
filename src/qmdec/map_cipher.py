"""QMC2 Map cipher (for keys <= 300 bytes)."""


class MapCipher:
    def __init__(self, key: bytes):
        self.key = key
        self.n = len(key)

    def _rotate(self, offset: int) -> int:
        if self.n == 0:
            return 0
        v = self.key[offset % self.n]
        return ((v & 0x0F) << 4) | ((v & 0xF0) >> 4)

    def _get_mask(self, offset: int) -> int:
        if self.n == 0:
            return 0
        offset_key = offset % self.n
        idx = (offset * offset + self._rotate(offset_key)) % self.n
        return self.key[idx]

    def decrypt(self, buf: bytearray, offset: int) -> None:
        for i in range(len(buf)):
            buf[i] ^= self._get_mask(offset + i)
