"""Yuqoridan ko'rinish preview renderi — heightmap + scatterni PNGga.

Bu faqat referens vizualizatsiyasi (tekshirish uchun). Ranglar biomga qarab
tanlanadi, relyef hillshade bilan soyalanadi, obyektlar nuqta bilan belgilanadi.
"""

from __future__ import annotations

from .scatter import Placement
from .terrain import Heightmap


# Biom rang gradienti: (past, o'rta, baland) RGB.
_BIOME_RAMP = {
    "snow":    ((70, 90, 120), (150, 165, 180), (245, 248, 252)),
    "desert":  ((120, 95, 60), (200, 165, 105), (238, 214, 165)),
    "island":  ((40, 90, 110), (90, 150, 90), (210, 200, 150)),
    "canyon":  ((90, 55, 45), (170, 100, 70), (225, 180, 140)),
    "volcano": ((40, 30, 32), (90, 55, 50), (180, 90, 60)),
    "grass":   ((60, 100, 70), (95, 150, 80), (200, 205, 160)),
}

_WATER_RGB = (46, 92, 138)

# Obyekt turi -> belgilash rangi.
_OBJECT_RGB = {
    "tree": (30, 70, 30), "house": (200, 60, 40), "rock": (90, 90, 95),
    "fence": (120, 90, 50), "torch": (240, 170, 40), "cactus": (40, 110, 60),
    "palm": (30, 120, 70),
}


def _lerp3(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _ramp(biome: str, h: float):
    lo, mid, hi = _BIOME_RAMP.get(biome, _BIOME_RAMP["grass"])
    if h < 0.5:
        return _lerp3(lo, mid, h * 2.0)
    return _lerp3(mid, hi, (h - 0.5) * 2.0)


def render_preview(
    hm: Heightmap,
    placements: list[Placement],
    *,
    upscale: int = 2,
) -> tuple[int, int, bytearray]:
    """Heightmap va obyektlarni rangli RGB bufferga chizadi.

    Qaytaradi: (width, height, pixels).
    """
    size = hm.size
    biome = hm.spec.biome
    water = hm.spec.water_level
    out_w = size * upscale
    out_h = size * upscale
    px = bytearray(out_w * out_h * 3)

    # Hillshade uchun yorug'lik yo'nalishi (yuqori-chapdan).
    for y in range(size):
        for x in range(size):
            h = hm.get(x, y)
            if h <= water:
                r, g, b = _WATER_RGB
                # Chuqurroq suv to'qroq.
                depth = (water - h) / max(water, 1e-4)
                shade = 1.0 - depth * 0.4
                r, g, b = int(r * shade), int(g * shade), int(b * shade)
            else:
                r, g, b = _ramp(biome, h)
                # Hillshade: qiyalik yo'nalishiga qarab yorug'lik.
                dx = hm.get(x + 1, y) - hm.get(x - 1, y)
                dy = hm.get(x, y + 1) - hm.get(x, y - 1)
                light = 0.5 + (-dx - dy) * 2.5
                light = 0.6 if light < 0.6 else 1.25 if light > 1.25 else light
                r = min(255, int(r * light))
                g = min(255, int(g * light))
                b = min(255, int(b * light))

            # upscale blokini to'ldirish.
            for oy in range(upscale):
                row = ((y * upscale + oy) * out_w + x * upscale) * 3
                for ox in range(upscale):
                    i = row + ox * 3
                    px[i] = r
                    px[i + 1] = g
                    px[i + 2] = b

    # Obyektlarni belgilash.
    cell_world = hm.spec.world_scale / size
    half = hm.spec.world_scale * 0.5
    radius = max(1, upscale)
    for p in placements:
        gx = int((p.x + half) / cell_world)
        gy = int((p.z + half) / cell_world)
        cx = gx * upscale + upscale // 2
        cy = gy * upscale + upscale // 2
        r, g, b = _OBJECT_RGB.get(p.kind, (255, 0, 255))
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                if ox * ox + oy * oy > radius * radius:
                    continue
                sx, sy = cx + ox, cy + oy
                if 0 <= sx < out_w and 0 <= sy < out_h:
                    i = (sy * out_w + sx) * 3
                    px[i] = r
                    px[i + 1] = g
                    px[i + 2] = b

    return out_w, out_h, px
