"""Minimal PNG yozuvchi — faqat stdlib (zlib, struct).

Referens previewlarini tashqi kutubxonasiz ko'rish uchun. Bu ishlab chiqarish
kodi emas; qurilmada render Godot Vulkan orqali bo'ladi.
"""

from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_rgb_png(path: str, width: int, height: int, pixels: bytearray) -> None:
    """`pixels` — uzunligi width*height*3 bo'lgan RGB bayt massivi."""
    if len(pixels) != width * height * 3:
        raise ValueError("pixels o'lchami width*height*3 ga teng bo'lishi kerak")

    # Har qatordan oldin filtr bayti (0 = None).
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, truecolor
    idat = zlib.compress(bytes(raw), 9)

    with open(path, "wb") as f:
        f.write(sig)
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", idat))
        f.write(_chunk(b"IEND", b""))
