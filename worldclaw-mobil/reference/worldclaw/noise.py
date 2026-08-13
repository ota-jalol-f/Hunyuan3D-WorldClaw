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


_INV = 1.0 / 32767.5


class ValueNoise:
    """Seedlanadigan 2D qiymat-noise; natija taxminan [-1, 1] oralig'ida.

    `at()` ichki hash to'liq inline qilingan (tezlik uchun) — natija
    `_grad_val` bilan bit-bir xil (GDScript/GLSL parlik uchun saqlangan).
    """

    __slots__ = ("_seed",)

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed & _U32

    def _grad_val(self, ix: int, iy: int) -> float:
        """Referens/parlik uchun (at() inline versiyani ishlatadi)."""
        h = _hash_u((ix * 374761393 + iy * 668265263 + self._seed) & _U32)
        return (float(h & 0xFFFF) * _INV) - 1.0

    def at(self, x: float, y: float) -> float:
        x0 = int(x) if x >= 0 else int(x) - 1
        y0 = int(y) if y >= 0 else int(y) - 1
        tx = x - x0
        ty = y - y0
        fx = tx * tx * tx * (tx * (tx * 6.0 - 15.0) + 10.0)
        fy = ty * ty * ty * (ty * (ty * 6.0 - 15.0) + 10.0)
        s = self._seed
        m = _U32
        base = x0 * 374761393 + y0 * 668265263 + s
        # To'rt burchak — hash to'liq inline.
        n = base & m
        n ^= n >> 16; n = (n * 0x7FEB352D) & m; n ^= n >> 15; n = (n * 0x846CA68B) & m; n ^= n >> 16
        v00 = (n & 0xFFFF) * _INV - 1.0
        n = (base + 374761393) & m
        n ^= n >> 16; n = (n * 0x7FEB352D) & m; n ^= n >> 15; n = (n * 0x846CA68B) & m; n ^= n >> 16
        v10 = (n & 0xFFFF) * _INV - 1.0
        n = (base + 668265263) & m
        n ^= n >> 16; n = (n * 0x7FEB352D) & m; n ^= n >> 15; n = (n * 0x846CA68B) & m; n ^= n >> 16
        v01 = (n & 0xFFFF) * _INV - 1.0
        n = (base + 374761393 + 668265263) & m
        n ^= n >> 16; n = (n * 0x7FEB352D) & m; n ^= n >> 15; n = (n * 0x846CA68B) & m; n ^= n >> 16
        v11 = (n & 0xFFFF) * _INV - 1.0

        top = v00 + (v10 - v00) * fx
        bottom = v01 + (v11 - v01) * fx
        return top + (bottom - top) * fy


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
