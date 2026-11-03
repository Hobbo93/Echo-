"""Draw a candlestick chart as a PNG (standard library only) for Telegram.

Green/red candles, blue entry line, red stop line, green target line.
"""
import struct
import zlib

BG = (11, 18, 32)
GRID = (30, 40, 58)
UP = (38, 166, 154)
DOWN = (239, 83, 80)
ENTRY = (66, 165, 245)
STOP = (239, 83, 80)
TARGET = (102, 187, 106)
FILL_MARK = (255, 213, 79)


class Canvas:
    def __init__(self, w, h, bg=BG):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))

    def rect(self, x0, y0, x1, y1, color):
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.w - 1, x1), min(self.h - 1, y1)
        row = bytes(color) * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def hline(self, y, color, dashed=False, thick=2):
        for x in range(0, self.w, 1):
            if dashed and (x // 8) % 2:
                continue
            self.rect(x, y, x, y + thick - 1, color)

    def png(self):
        raw = b"".join(b"\x00" + bytes(self.px[y * self.w * 3:(y + 1) * self.w * 3]) for y in range(self.h))

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def candle_chart(rows, entry=None, stop=None, target=None, mark_last=False, w=900, h=500, bars=60):
    """rows: [(t, open, high, low, close, volume), ...] -> PNG bytes."""
    rows = rows[-bars:]
    levels = [v for v in (entry, stop, target) if v]
    hi = max([r[2] for r in rows] + levels)
    lo = min([r[3] for r in rows] + levels)
    pad = (hi - lo) * .08 or 1
    hi, lo = hi + pad, lo - pad
    c = Canvas(w, h)
    y = lambda v: (hi - v) / (hi - lo) * (h - 20) + 10
    for k in range(1, 6):
        c.rect(0, h * k / 6, w, h * k / 6, GRID)
    step = (w - 40) / len(rows)
    body = max(2, step * .6)
    for i, (_, o, hgh, low, cl, _v) in enumerate(rows):
        x = 20 + i * step + step / 2
        col = UP if cl >= o else DOWN
        c.rect(x, y(hgh), x + 1, y(low), col)
        c.rect(x - body / 2, y(max(o, cl)), x + body / 2, y(min(o, cl)) + 1, col)
    if target:
        c.hline(y(target), TARGET, dashed=True)
    if stop:
        c.hline(y(stop), STOP, dashed=True)
    if entry:
        c.hline(y(entry), ENTRY, thick=3)
    if mark_last:
        x = 20 + (len(rows) - 1) * step + step / 2
        c.rect(x - 7, y(entry or rows[-1][4]) - 7, x + 7, y(entry or rows[-1][4]) + 7, FILL_MARK)
    return c.png()
