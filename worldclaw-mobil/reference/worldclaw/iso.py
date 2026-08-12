"""Yumshoq izometrik 3D render — Godotsiz "tushunarli 3D" preview.

Relyef mesh + obyektlarni izometrik proyeksiyada z-bufer bilan rasterlaydi.
Bu haqiqiy 3D emas (real render Godot Vulkan'da), lekin top-down 2D'dan farqli
o'laroq balandlik va perspektivani ko'rsatadi. Faqat stdlib.
"""

from __future__ import annotations

import math

from .render import _BIOME_RAMP, _WATER_RGB, _ramp
from .scatter import Placement
from .terrain import Heightmap

_ISO_X = 0.8660254   # cos(30)
_ISO_Y = 0.5         # sin(30)

_OBJ_COLOR = {
    "tree": (36, 92, 40), "palm": (30, 120, 72), "cactus": (40, 120, 66),
    "torch": (240, 170, 40), "house": (190, 70, 52), "fence": (140, 100, 56),
    "rock": (110, 110, 118),
}


def _project(wx, wy, wz, scale, ox, oy):
    sx = (wx - wz) * _ISO_X * scale + ox
    sy = ((wx + wz) * _ISO_Y - wy) * scale + oy
    depth = (wx + wz) - wy   # kichik = kameraga yaqin
    return sx, sy, depth


def _tri(fb, zb, W, H, p0, p1, p2, color):
    """Uchburchakni z-bufer bilan rasterlaydi (yassi rang)."""
    x0, y0, d0 = p0
    x1, y1, d1 = p1
    x2, y2, d2 = p2
    minx = max(0, int(min(x0, x1, x2)))
    maxx = min(W - 1, int(math.ceil(max(x0, x1, x2))))
    miny = max(0, int(min(y0, y1, y2)))
    maxy = min(H - 1, int(math.ceil(max(y0, y1, y2))))
    if minx > maxx or miny > maxy:
        return
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-6:
        return
    inv = 1.0 / area
    r, g, b = color
    for py in range(miny, maxy + 1):
        for px in range(minx, maxx + 1):
            w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) * inv
            w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) * inv
            w2 = 1.0 - w0 - w1
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            depth = w0 * d0 + w1 * d1 + w2 * d2
            i = py * W + px
            if depth < zb[i]:
                zb[i] = depth
                j = i * 3
                fb[j] = r
                fb[j + 1] = g
                fb[j + 2] = b


def render_iso(
    hm: Heightmap,
    placements: list[Placement],
    *,
    width: int = 900,
    stride: int = 1,
) -> tuple[int, int, bytearray]:
    """Izometrik 3D preview RGB buffer qaytaradi."""
    size = hm.size
    spec = hm.spec
    cell = spec.world_scale / size
    half = spec.world_scale * 0.5
    hs = spec.height_scale
    water = spec.water_level
    biome = spec.biome

    # Ko'lam va markazni dunyo o'lchamiga moslash.
    scale = width / (spec.world_scale * 2.0 * _ISO_X)
    ox = width * 0.5
    H = int(width * 0.72)
    oy = H * 0.30

    fb = bytearray(width * H * 3)
    # Osmon foni (yumshoq gradient).
    for py in range(H):
        t = py / H
        sr = int(150 + 60 * (1 - t)); sg = int(180 + 50 * (1 - t)); sb = int(210 + 30 * (1 - t))
        for px in range(width):
            j = (py * width + px) * 3
            fb[j] = sr; fb[j + 1] = sg; fb[j + 2] = sb
    zb = [1e18] * (width * H)

    def world(gx, gy):
        h = hm.get(gx, gy)
        return (gx * cell - half, h * hs, gy * cell - half, h)

    # Relyef uchburchaklari.
    xs = list(range(0, size, stride))
    if xs[-1] != size - 1:
        xs.append(size - 1)
    for j in range(len(xs) - 1):
        for i in range(len(xs) - 1):
            gx0, gx1 = xs[i], xs[i + 1]
            gy0, gy1 = xs[j], xs[j + 1]
            wa = world(gx0, gy0); wb = world(gx1, gy0)
            wc = world(gx0, gy1); wd = world(gx1, gy1)
            avg_h = (wa[3] + wb[3] + wc[3] + wd[3]) * 0.25
            # Rang: suv yoki biom gradienti + qiyalik soyasi.
            if avg_h <= water:
                col = _WATER_RGB
            else:
                r, g, bb = _ramp(biome, avg_h)
                dx = (wb[1] - wa[1])
                dz = (wc[1] - wa[1])
                light = 0.72 + max(-0.28, min(0.28, (-dx - dz) * 0.03))
                col = (min(255, int(r * light)), min(255, int(g * light)), min(255, int(bb * light)))
            pa = _project(*wa[:3], scale, ox, oy)
            pb = _project(*wb[:3], scale, ox, oy)
            pc = _project(*wc[:3], scale, ox, oy)
            pd = _project(*wd[:3], scale, ox, oy)
            _tri(fb, zb, width, H, pa, pc, pb, col)
            _tri(fb, zb, width, H, pb, pc, pd, col)

    # Obyektlar — oddiy billbord (ustun + uch).
    for p in placements:
        col = _OBJ_COLOR.get(p.kind, (200, 60, 200))
        oh = 6.0 * p.scale
        ow = 2.2 * p.scale
        base = _project(p.x, p.y, p.z, scale, ox, oy)
        top = _project(p.x, p.y + oh, p.z, scale, ox, oy)
        # ustun: ikki uchburchakли tik to'rtburchak (billbord)
        bl = (base[0] - ow, base[1], base[2])
        br = (base[0] + ow, base[1], base[2])
        tl = (top[0] - ow * 0.4, top[1], top[2])
        tr = (top[0] + ow * 0.4, top[1], top[2])
        _tri(fb, zb, width, H, bl, tl, br, col)
        _tri(fb, zb, width, H, br, tl, tr, col)

    return width, H, fb


def _shade(color, ny):
    light = 0.55 + 0.45 * max(0.0, ny * 0.5 + 0.5)
    return (min(255, int(color[0] * 255 * light)),
            min(255, int(color[1] * 255 * light)),
            min(255, int(color[2] * 255 * light)))


def render_mesh_lineup(kinds: list[str], *, seed: int = 0, width: int = 980,
                       obj_scale: float = 1.7, scale: float = 66.0):
    """Har turdan bitta generativ meshni gorizontal qatorда, o'z platformasida
    rasterlaydi — haqiqiy generativ 3D shakllarni ko'rsatadi (primitiv emas)."""
    from .mesh import generate

    H = int(width * 0.42)
    fb = bytearray(width * H * 3)
    for py in range(H):                       # osmon foni
        t = py / H
        r = int(150 + 60 * (1 - t)); g = int(180 + 50 * (1 - t)); bl = int(210 + 30 * (1 - t))
        for px in range(width):
            j = (py * width + px) * 3
            fb[j] = r; fb[j + 1] = g; fb[j + 2] = bl
    zb = [1e18] * (width * H)

    n = len(kinds)
    spacing = 1.5
    ox = width * 0.5
    oy = H * 0.66

    for i, kind in enumerate(kinds):
        t = (i - (n - 1) * 0.5) * spacing
        bx, bz = t, -t                        # gorizontal qator (x = -z chizig'i)

        # kichik platforma
        s = 0.5
        plat = [(bx - s, 0, bz - s), (bx + s, 0, bz - s), (bx - s, 0, bz + s), (bx + s, 0, bz + s)]
        pp = [_project(*v, scale, ox, oy) for v in plat]
        _tri(fb, zb, width, H, pp[0], pp[2], pp[1], (118, 122, 118))
        _tri(fb, zb, width, H, pp[1], pp[2], pp[3], (118, 122, 118))

        parts = generate(kind, seed + i * 131)
        for part in parts:
            pos, nrm, idxs = part.positions, part.normals, part.indices
            for tri in range(0, len(idxs), 3):
                tri_pts = []
                ny_sum = 0.0
                for k in range(3):
                    vi = idxs[tri + k]
                    vx, vy, vz = pos[vi]
                    ny_sum += nrm[vi][1]
                    tri_pts.append(_project(bx + vx * obj_scale, vy * obj_scale,
                                            bz + vz * obj_scale, scale, ox, oy))
                _tri(fb, zb, width, H, tri_pts[0], tri_pts[1], tri_pts[2],
                     _shade(part.color, ny_sum / 3.0))
    return width, H, fb
