"""Relyef (heightmap) generatsiyasi — ScenePlan.terrain'dan.

Chiqish: [0, 1] ga normallashgan balandliklar kvadrat panjarasi. Godotda bu
GPU compute shaderda bajariladi (`shaders/terrain_height.gdshader`); mantiq
aynan shu — bir xil natijani tekshirish uchun.
"""

from __future__ import annotations

from .noise import ValueNoise, fbm, ridged
from .scene_plan import TerrainSpec


class Heightmap:
    """Kvadrat balandlik panjarasi va uning yordamchi so'rovlari."""

    __slots__ = ("size", "data", "spec")

    def __init__(self, size: int, spec: TerrainSpec) -> None:
        self.size = size
        self.spec = spec
        self.data = [0.0] * (size * size)

    def get(self, x: int, y: int) -> float:
        x = 0 if x < 0 else self.size - 1 if x >= self.size else x
        y = 0 if y < 0 else self.size - 1 if y >= self.size else y
        return self.data[y * self.size + x]

    def slope(self, x: int, y: int) -> float:
        """Markaziy farq bilan taxminiy qiyalik (balandlik birligida)."""
        dx = self.get(x + 1, y) - self.get(x - 1, y)
        dy = self.get(x, y + 1) - self.get(x, y - 1)
        return (dx * dx + dy * dy) ** 0.5

    def min_max(self) -> tuple[float, float]:
        return min(self.data), max(self.data)


def _biome_shape(biome: str, base: float, mountains: float, strength: float) -> float:
    """Biomga xos balandlik aralashmasi. Natija ~[0, 1].

    (island alohida ishlov oladi — generate_heightmap ichida, chunki u
    markazdan masofaga bog'liq.)
    """
    base01 = base * 0.5 + 0.5  # [-1,1] -> [0,1]
    if biome == "canyon":
        # Zinapoyali mesa platosi + tor chuqur o'yiqlar (tizmali noise cho'qqilarida).
        terraces = 6.0
        plat = 0.45 + base01 * 0.4
        stepped = int(plat * terraces) / terraces
        plat = stepped * 0.8 + plat * 0.2          # asosan zinapoya, biroz silliq
        m = _clamp((mountains - 0.55) / 0.25)       # faqat tor tizma chiziqlari
        channel = m * m * (3.0 - 2.0 * m)           # smoothstep — yumshoq chekka
        return _clamp(plat - channel * strength * 0.8)
    if biome == "volcano":
        # Markazga qarab ko'tarilib, cho'qqida krater.
        return _clamp(base01 * 0.3 + mountains * strength)
    # snow / grass / desert — bazaviy relyef + tizmalar.
    return _clamp(base01 * (1.0 - strength * 0.5) + mountains * strength)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def generate_heightmap(spec: TerrainSpec) -> Heightmap:
    """TerrainSpec'dan normallashgan balandlik xaritasini quradi."""
    spec.validate()
    size = spec.size
    hm = Heightmap(size, spec)

    base_noise = ValueNoise(spec.seed)
    ridge_noise = ValueNoise(spec.seed ^ 0x5A5A5A5A)

    # Panjara koordinatasi -> noise koordinatasi. Frekvensiya dunyoni ~4-6
    # yirik shakl kesib o'tadigan qilib tanlangan.
    inv = 1.0 / max(1, size)
    base_freq = 4.0
    center = 0.5

    for y in range(size):
        for x in range(size):
            nx = x * inv
            ny = y * inv

            base = fbm(
                base_noise, nx * base_freq, ny * base_freq,
                octaves=5, gain=spec.roughness,
            )
            mountains = ridged(
                ridge_noise, nx * base_freq, ny * base_freq,
                octaves=5, gain=spec.roughness,
            )

            if spec.biome == "island":
                # Markazda suvdan baland gumbaz, chekkalar dengizga tushadi.
                dx = (nx - center) * 2.0
                dy = (ny - center) * 2.0
                dist = (dx * dx + dy * dy) ** 0.5
                dome = _clamp(1.15 - dist)  # keng markaz plato + silliq chekka
                h = dome * (0.5 + mountains * spec.mountain_strength)
                h += (base * 0.5 + 0.5) * 0.05  # yengil tekstura
                hm.data[y * size + x] = _clamp(h)
                continue

            hm.data[y * size + x] = _biome_shape(
                spec.biome, base, mountains, spec.mountain_strength
            )

    return hm
