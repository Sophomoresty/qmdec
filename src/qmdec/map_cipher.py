"""QMC2 Map cipher (for keys <= 300 bytes)."""


class MapCipher:
    def __init__(self, key: bytes):
        self.key = key
        self.n = len(key)

    @staticmethod
    def _rotate(value: int, bits: int) -> int:
        # Match QQMusic/unlock-music's historical byte shift expression:
        # (value << ((bits + 4) % 8)) | (value >> ((bits + 4) % 8)).
        # It is not a normal rotate-left by 8-r.
        shift = (bits + 4) % 8
        return ((value << shift) | (value >> shift)) & 0xFF

    def _get_mask(self, offset: int) -> int:
        if self.n == 0:
            return 0
        if offset > 0x7FFF:
            offset %= 0x7FFF
        idx = (offset * offset + 71214) % self.n
        return self._rotate(self.key[idx], idx & 0x07)

    def decrypt(self, buf: bytearray, offset: int) -> None:
        for i in range(len(buf)):
            buf[i] ^= self._get_mask(offset + i)
