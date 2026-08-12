"""Deterministik qiymat-noise (value noise) va fraktal fBm.

Faqat standart kutubxona. Bu modul Godot tomonidagi `TerrainGenerator.gd`
ning aynan mantiqini takrorlaydi, shuning uchun ustidan yozilgan testlar
qurilmadagi relyef bilan bir xil xulq-atvorni tekshiradi.
"""

from __future__ import annotations

import math

_U32 = 0xFFFFFFFF


def _hash_u(x: int) -> int:
    """32-bitlik butun-hash (GLSL shaderdagi bilan aynan bir xil).

    Bu funksiya Python, GDScript va GLSL'da bir xil natija beradi — shuning
    uchun relyef CPU va GPU yo'llarida bir xil chiqadi.
    """
    x &= _U32
    x ^= x >> 16
    x = (x * 0x7FEB352D) & _U32
    x ^= x >> 15
    x = (x * 0x846CA68B) & _U32
    x ^= x >> 16
    return x & _U32


def _fade(t: float) -> float:
    """Smoothstep (Perlin fade) — silliq interpolatsiya."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class ValueNoise:
    """Seedlanadigan 2D qiymat-noise; natija taxminan [-1, 1] oralig'ida."""

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed & _U32

    def _grad_val(self, ix: int, iy: int) -> float:
        """Panjara tugunidagi psevdo-tasodifiy qiymat, [-1, 1]."""
        h = _hash_u((ix * 374761393 + iy * 668265263 + self._seed) & _U32)
        return (float(h & 0xFFFF) / 32767.5) - 1.0

    def at(self, x: float, y: float) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        fx = _fade(x - x0)
        fy = _fade(y - y0)

        v00 = self._grad_val(x0, y0)
        v10 = self._grad_val(x0 + 1, y0)
        v01 = self._grad_val(x0, y0 + 1)
        v11 = self._grad_val(x0 + 1, y0 + 1)

        top = _lerp(v00, v10, fx)
        bottom = _lerp(v01, v11, fx)
        return _lerp(top, bottom, fy)


def fbm(
    noise: ValueNoise,
    x: float,
    y: float,
    *,
    octaves: int = 5,
    lacunarity: float = 2.0,
    gain: float = 0.5,
    frequency: float = 1.0,
) -> float:
    """Fraktal Brownian motion — bir necha oktavani yig'ib boy relyef beradi.

    Natija ~[-1, 1] ga normallashtiriladi.
    """
    amplitude = 1.0
    freq = frequency
    total = 0.0
    norm = 0.0
    for _ in range(octaves):
        total += amplitude * noise.at(x * freq, y * freq)
        norm += amplitude
        amplitude *= gain
        freq *= lacunarity
    return total / norm if norm > 0 else 0.0


def ridged(
    noise: ValueNoise,
    x: float,
    y: float,
    *,
    octaves: int = 5,
    lacunarity: float = 2.0,
    gain: float = 0.5,
    frequency: float = 1.0,
) -> float:
    """Tizmali (ridged) noise — o'tkir tog' tizmalari uchun. Natija ~[0, 1]."""
    amplitude = 1.0
    freq = frequency
    total = 0.0
    norm = 0.0
    for _ in range(octaves):
        n = 1.0 - abs(noise.at(x * freq, y * freq))
        n *= n  # tizmalarni o'tkirlashtirish
        total += amplitude * n
        norm += amplitude
        amplitude *= gain
        freq *= lacunarity
    return total / norm if norm > 0 else 0.0
