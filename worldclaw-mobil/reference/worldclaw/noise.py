"""Deterministik qiymat-noise (value noise) va fraktal fBm.

Faqat standart kutubxona. Bu modul Godot tomonidagi `TerrainGenerator.gd`
ning aynan mantiqini takrorlaydi, shuning uchun ustidan yozilgan testlar
qurilmadagi relyef bilan bir xil xulq-atvorni tekshiradi.
"""

from __future__ import annotations

import math


# 8-bitlik permutatsiya jadvali — seed bilan aralashtiriladi.
_PERM_SIZE = 256


def _build_perm(seed: int) -> list[int]:
    """Seed asosida takrorlanuvchi permutatsiya jadvali."""
    perm = list(range(_PERM_SIZE))
    # LCG — tashqi bog'liqliksiz, platformalararo bir xil natija.
    state = (seed ^ 0x9E3779B1) & 0xFFFFFFFF
    for i in range(_PERM_SIZE - 1, 0, -1):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        j = state % (i + 1)
        perm[i], perm[j] = perm[j], perm[i]
    return perm + perm  # ikki marta — indeks o'ralishini yo'qotish uchun


def _fade(t: float) -> float:
    """Smoothstep (Perlin fade) — silliq interpolatsiya."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class ValueNoise:
    """Seedlanadigan 2D qiymat-noise; natija taxminan [-1, 1] oralig'ida."""

    def __init__(self, seed: int = 0) -> None:
        self._perm = _build_perm(seed)

    def _grad_val(self, ix: int, iy: int) -> float:
        """Panjara tugunidagi psevdo-tasodifiy qiymat, [-1, 1]."""
        h = self._perm[(self._perm[ix & 255] + iy) & 255]
        return (h / 127.5) - 1.0

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
