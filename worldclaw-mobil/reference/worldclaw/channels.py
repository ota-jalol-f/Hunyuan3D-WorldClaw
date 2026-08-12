"""Ko'rinish kanallari — depth / normal / instance (WorldClaw saytidagi kabi).

Yuqoridan ko'rinishда heightmap + placements'dan hosil qilinadi. Qurilmada bu
kanallar Godot renderining G-buferidan olinadi; bu yerda referens sifatida
CPU'да chiziladi va PNGга yoziladi.
"""

from __future__ import annotations

from .scatter import Placement
from .terrain import Heightmap


def _fill(px: bytearray, out_w: int, x: int, y: int, upscale: int, rgb: tuple[int, int, int]) -> None:
    for oy in range(upscale):
        row = ((y * upscale + oy) * out_w + x * upscale) * 3
        for ox in range(upscale):
            i = row + ox * 3
            px[i], px[i + 1], px[i + 2] = rgb


def render_depth(hm: Heightmap, *, upscale: int = 2) -> tuple[int, int, bytearray]:
    """Chuqurlik — balandlik kulrangда (baland = yorug')."""
    size = hm.size
    out_w = out_h = size * upscale
    px = bytearray(out_w * out_h * 3)
    for y in range(size):
        for x in range(size):
            v = int(hm.get(x, y) * 255)
            _fill(px, out_w, x, y, upscale, (v, v, v))
    return out_w, out_h, px


def render_normal(hm: Heightmap, *, upscale: int = 2, strength: float = 4.0) -> tuple[int, int, bytearray]:
    """Normal xarita — relyef qiyaligidan (RGB = XYZ normal)."""
    size = hm.size
    out_w = out_h = size * upscale
    px = bytearray(out_w * out_h * 3)
    for y in range(size):
        for x in range(size):
            dx = (hm.get(x + 1, y) - hm.get(x - 1, y)) * strength
            dy = (hm.get(x, y + 1) - hm.get(x, y - 1)) * strength
            # normal = normalize(-dx, -dy, 1)
            nz = 1.0
            inv = 1.0 / ((dx * dx + dy * dy + nz * nz) ** 0.5)
            nx = -dx * inv
            ny = -dy * inv
            nz *= inv
            rgb = (
                int((nx * 0.5 + 0.5) * 255),
                int((ny * 0.5 + 0.5) * 255),
                int((nz * 0.5 + 0.5) * 255),
            )
            _fill(px, out_w, x, y, upscale, rgb)
    return out_w, out_h, px


# Instance kanali uchun obyekt turi -> ajratuvchi rang.
_INSTANCE_RGB = {
    "tree": (60, 220, 90), "house": (240, 80, 60), "rock": (150, 150, 160),
    "fence": (200, 160, 70), "torch": (255, 210, 60), "cactus": (70, 200, 130),
    "palm": (40, 210, 160),
}


def render_instance(
    hm: Heightmap, placements: list[Placement], *, upscale: int = 2
) -> tuple[int, int, bytearray]:
    """Instance segmentatsiya — relyef qora, obyektlar tur rangida."""
    size = hm.size
    out_w = out_h = size * upscale
    px = bytearray(out_w * out_h * 3)  # fon qora (0)

    cell_world = hm.spec.world_scale / size
    half = hm.spec.world_scale * 0.5
    radius = max(1, upscale)
    for p in placements:
        gx = int((p.x + half) / cell_world)
        gy = int((p.z + half) / cell_world)
        cx = gx * upscale + upscale // 2
        cy = gy * upscale + upscale // 2
        rgb = _INSTANCE_RGB.get(p.kind, (255, 0, 255))
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                if ox * ox + oy * oy > radius * radius:
                    continue
                sx, sy = cx + ox, cy + oy
                if 0 <= sx < out_w and 0 <= sy < out_h:
                    i = (sy * out_w + sx) * 3
                    px[i], px[i + 1], px[i + 2] = rgb
    return out_w, out_h, px


def write_channels(hm: Heightmap, placements: list[Placement], prefix: str, *, upscale: int = 2) -> list[str]:
    """depth / normal / instance kanallarini PNGга yozadi. Yo'llar ro'yxati."""
    from .pngwriter import write_rgb_png

    out: list[str] = []
    for name, (w, h, buf) in {
        "depth": render_depth(hm, upscale=upscale),
        "normal": render_normal(hm, upscale=upscale),
        "instance": render_instance(hm, placements, upscale=upscale),
    }.items():
        path = f"{prefix}_{name}.png"
        write_rgb_png(path, w, h, buf)
        out.append(path)
    return out
