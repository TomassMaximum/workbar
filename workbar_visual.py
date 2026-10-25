"""Small Retina capsule images for SwiftBar, using only the standard library."""

from __future__ import annotations

import base64
import math
import struct
import zlib
from functools import lru_cache

WIDTH, HEIGHT, SCALE = 80, 22, 2


def _coverage(x: float, y: float, width: float, height: float) -> float:
    """Antialiased signed distance to a capsule, in device pixels."""
    radius = min(width, height) / 2
    dx = abs(x - width / 2) - (width / 2 - radius)
    dy = abs(y - height / 2) - (height / 2 - radius)
    distance = math.hypot(max(dx, 0), max(dy, 0)) + min(max(dx, dy), 0) - radius
    return max(0.0, min(1.0, 0.5 - distance))


def _chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + name + data + struct.pack("!I", zlib.crc32(name + data))


@lru_cache(maxsize=202)
def capsule_png(percent: int, dark: bool = False) -> bytes:
    """An 80 × 22 point transparent PNG with a continuous 74 × 8 point bar."""
    ratio = max(0, min(100, percent)) / 100
    width, height = WIDTH * SCALE, HEIGHT * SCALE
    left, top, track_width, track_height = 3 * SCALE, 7 * SCALE, 74 * SCALE, 8 * SCALE
    fill_width = track_width * ratio
    track = (240, 246, 255, 48) if dark else (31, 41, 55, 32)
    start, end = ((57, 199, 175), (117, 223, 182)) if dark else ((15, 158, 142), (50, 184, 149))
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            px, py = x + 0.5 - left, y + 0.5 - top
            track_coverage = _coverage(px, py, track_width, track_height)
            track_alpha = track_coverage * track[3] / 255
            fill_alpha = min(track_coverage, _coverage(px, py, fill_width, track_height)) if fill_width > 0 else 0
            alpha = fill_alpha + track_alpha * (1 - fill_alpha)
            if alpha == 0:
                row.extend((0, 0, 0, 0))
                continue
            blend = max(0, min(1, px / track_width))
            fill = [a + (b - a) * blend for a, b in zip(start, end)]
            rgb = [round((c * fill_alpha + bg * track_alpha * (1 - fill_alpha)) / alpha)
                   for c, bg in zip(fill, track[:3])]
            row.extend((*rgb, round(alpha * 255)))
        rows.append(b"\x00" + row)
    # pHYs tells AppKit this is a 2× image, so it stays 80 × 22 points.
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"sRGB", b"\x00")
            + _chunk(b"pHYs", struct.pack("!IIB", 5669, 5669, 1))
            + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + _chunk(b"IEND", b""))


def capsule_images(ratio: float | None) -> str:
    percent = 0 if ratio is None else int(round(ratio * 100))
    return ",".join(base64.b64encode(capsule_png(percent, dark)).decode("ascii")
                    for dark in (False, True))
