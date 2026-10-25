#!/usr/bin/env python3
"""Generate a small, original app mark with only Python's standard library."""
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parents[1]
size = 1024
pixels = bytearray()
for y in range(size):
    pixels.append(0)
    for x in range(size):
        dx, dy = x-512, y-512
        radius = (dx*dx + dy*dy)**0.5
        color = (8, 127, 108)
        if radius < 360: color = (31, 145, 126)
        if 282 < radius < 304: color = (231, 255, 244)
        if (dx*dx + (dy+7)**2)**0.5 < 71: color = (231, 255, 244)
        if (x-744)**2 + (y-329)**2 < 55**2: color = (252, 191, 91)
        pixels.extend(color)

def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data) & 0xffffffff)

png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
dest = root / 'iosApp/CircleGuard/Assets.xcassets/AppIcon.appiconset'
dest.mkdir(parents=True, exist_ok=True)
(dest / 'AppIcon.png').write_bytes(png)
