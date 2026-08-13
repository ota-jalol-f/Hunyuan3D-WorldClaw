"""Generativ mesh — obyektlar uchun haqiqiy 3D shakllar (primitiv emas).

Ikki backend:
  * PROCEDURAL (shu modul) — parametrik + seed bilan variatsiya. Arzon,
    determinlashgan, on-device'ga qulay. Blokli primitivlarni almashtiradi.
  * NEURAL image-to-3D (NPU) — `neural_mesh` stub; kelajakda distillangan model.

Har generator `Part` ro'yxatini qaytaradi: (pozitsiyalar, normallar, indekslar,
rang). Bir mesh bir necha qismдан iborat bo'lishi mumkin (masalan uy: devor +
tom + eshik), har biri o'z rangi bilan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Part:
    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    indices: list[int]
    color: tuple[float, float, float]


class _Rng:
    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = (seed ^ 0x9E3779B1) & 0xFFFFFFFF

    def unit(self) -> float:
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.state / 4294967296.0

    def range(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.unit()


def _norm(x, y, z):
    m = (x * x + y * y + z * z) ** 0.5 or 1.0
    return x / m, y / m, z / m


def _flat(verts, faces, color) -> Part:
    """Yassi-soyali qism: har uchburchak mustaqil uchlarga ega."""
    positions, normals, indices = [], [], []
    for (a, b, c) in faces:
        pa, pb, pc = verts[a], verts[b], verts[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        nx, ny, nz = _norm(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        base = len(positions)
        for p in (pa, pb, pc):
            positions.append(p)
            normals.append((nx, ny, nz))
        indices += [base, base + 1, base + 2]
    return Part(positions, normals, indices, color)


# --- Bazaviy shakllar --------------------------------------------------------

def _cylinder(rb, rt, h, y0, color, seg=6, cx=0.0, cz=0.0):
    verts, faces = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + rb * math.cos(a), y0, cz + rb * math.sin(a)))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + rt * math.cos(a), y0 + h, cz + rt * math.sin(a)))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + i))
        faces.append((j, seg + j, seg + i))
    return _flat(verts, faces, color)


def _cone(r, h, y0, color, seg=6, cx=0.0, cz=0.0):
    verts = [(cx, y0 + h, cz)]
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + r * math.cos(a), y0, cz + r * math.sin(a)))
    faces = [(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)]
    return _flat(verts, faces, color)


def _box(w, h, d, cx, y0, cz, color):
    x0, x1 = cx - w / 2, cx + w / 2
    z0, z1 = cz - d / 2, cz + d / 2
    y1 = y0 + h
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1),
         (3, 2, 6), (3, 6, 7), (1, 5, 6), (1, 6, 2), (0, 3, 7), (0, 7, 4)]
    return _flat(v, f, color)


def _prism_roof(w, h, d, cx, y0, cz, color):
    """Uchburchak tomли prizma."""
    x0, x1 = cx - w / 2, cx + w / 2
    z0, z1 = cz - d / 2, cz + d / 2
    ridge0 = (cx, y0 + h, z0)
    ridge1 = (cx, y0 + h, z1)
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), ridge0, ridge1]
    f = [(0, 1, 4), (1, 2, 5), (1, 5, 4), (2, 3, 5), (3, 0, 4), (3, 4, 5), (0, 3, 1), (1, 3, 2)]
    return _flat(v, f, color)


def _rock_solid(r, color, rng: _Rng):
    """Noise bilan buzilgan oktaedr — tabiiy tosh."""
    base = [(0, r, 0), (r, 0, 0), (0, 0, r), (-r, 0, 0), (0, 0, -r), (0, -r * 0.5, 0)]
    verts = []
    for (x, y, z) in base:
        k = rng.range(0.75, 1.25)
        verts.append((x * k, max(0.0, y * k + r * 0.5), z * k))
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
             (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
    return _flat(verts, faces, color)


# --- Obyekt generatorlari ----------------------------------------------------

_TRUNK = (0.36, 0.26, 0.16)
_LEAF = (0.18, 0.44, 0.22)
_LEAF2 = (0.22, 0.52, 0.26)


def gen_tree(seed: int) -> list[Part]:
    r = _Rng(seed)
    trunk_h = r.range(0.28, 0.42)
    parts = [_cylinder(0.06, 0.045, trunk_h, 0.0, _TRUNK, seg=5)]
    tiers = 2 + int(r.unit() * 2)          # 2-3 qavat barg
    y = trunk_h * 0.75
    rad = r.range(0.26, 0.34)
    for t in range(tiers):
        col = _LEAF if t % 2 == 0 else _LEAF2
        parts.append(_cone(rad, rad * 1.5, y, col, seg=6))
        y += rad * 0.85
        rad *= 0.72
    return parts


def gen_palm(seed: int) -> list[Part]:
    r = _Rng(seed)
    h = r.range(0.7, 1.0)
    lean = r.range(-0.06, 0.06)
    parts = [_cylinder(0.05, 0.035, h, 0.0, (0.42, 0.32, 0.18), seg=5, cx=lean * 0.5, cz=lean)]
    fronds = 5 + int(r.unit() * 3)
    for i in range(fronds):
        a = 2 * math.pi * i / fronds
        tip = (lean + 0.34 * math.cos(a), h - 0.06, lean + 0.34 * math.sin(a))
        left = (lean + 0.05 * math.cos(a + 1.5), h, lean + 0.05 * math.sin(a + 1.5))
        right = (lean + 0.05 * math.cos(a - 1.5), h, lean + 0.05 * math.sin(a - 1.5))
        parts.append(_flat([left, right, tip], [(0, 1, 2)], (0.20, 0.50, 0.28)))
    return parts


def gen_house(seed: int) -> list[Part]:
    r = _Rng(seed)
    w = r.range(0.5, 0.7)
    h = r.range(0.32, 0.44)
    d = r.range(0.5, 0.7)
    wall = (r.range(0.60, 0.80), r.range(0.45, 0.60), r.range(0.35, 0.45))
    roof = (r.range(0.55, 0.75), r.range(0.20, 0.30), r.range(0.18, 0.24))
    parts = [
        _box(w, h, d, 0, 0, 0, wall),
        _prism_roof(w * 1.08, r.range(0.18, 0.26), d * 1.08, 0, h, 0, roof),
        _box(w * 0.22, h * 0.55, 0.02, 0, 0, d / 2, (0.25, 0.16, 0.10)),  # eshik
    ]
    return parts


def gen_rock(seed: int) -> list[Part]:
    r = _Rng(seed)
    shade = r.range(0.40, 0.52)
    return [_rock_solid(r.range(0.18, 0.30), (shade, shade, shade * 1.05), r)]


def gen_cactus(seed: int) -> list[Part]:
    r = _Rng(seed)
    col = (0.20, 0.48, 0.28)
    h = r.range(0.45, 0.7)
    parts = [_cylinder(0.08, 0.07, h, 0.0, col, seg=6)]
    arms = int(r.unit() * 3)               # 0-2 qo'l
    for i in range(arms):
        side = 1.0 if i % 2 == 0 else -1.0
        y = r.range(0.2, 0.4)
        parts.append(_cylinder(0.05, 0.045, 0.12, y, col, seg=5, cx=side * 0.09))
        parts.append(_cylinder(0.05, 0.04, r.range(0.12, 0.2), y + 0.1, col, seg=5, cx=side * 0.14))
    return parts


def gen_torch(seed: int) -> list[Part]:
    r = _Rng(seed)
    h = r.range(0.4, 0.55)
    return [
        _cylinder(0.03, 0.03, h, 0.0, (0.35, 0.25, 0.15), seg=4),
        _cone(0.08, 0.16, h, (0.98, 0.62, 0.15), seg=5),   # alanga
    ]


def gen_fence(seed: int) -> list[Part]:
    r = _Rng(seed)
    col = (0.52, 0.38, 0.22)
    parts = []
    for i in range(2):
        x = -0.18 + i * 0.36
        parts.append(_box(0.05, r.range(0.28, 0.36), 0.05, x, 0, 0, col))
    parts.append(_box(0.42, 0.05, 0.03, 0, 0.22, 0, col))   # yuqori reyka
    parts.append(_box(0.42, 0.05, 0.03, 0, 0.12, 0, col))   # pastki reyka
    return parts


_GENERATORS = {
    "tree": gen_tree, "palm": gen_palm, "house": gen_house, "rock": gen_rock,
    "cactus": gen_cactus, "torch": gen_torch, "fence": gen_fence,
}


def generate(kind: str, seed: int = 0) -> list[Part]:
    """Berilgan tur uchun generativ mesh (procedural backend)."""
    fn = _GENERATORS.get(kind, gen_rock)
    return fn(seed)


def variants(kind: str, count: int = 4, seed: int = 0) -> list[list[Part]]:
    """Bir tur uchun bir necha variant — nusxalar orasida ulashiladi."""
    return [generate(kind, seed + i * 7919) for i in range(count)]


def neural_mesh(kind: str, image=None, seed: int = 0) -> list[Part] | None:
    """Image-to-3D backend — obyekt tasviridan mesh.

    `neural.py` ga topshiradi: qurilmada NPU distillangan model (Faza 3+), aks
    holda visual hull rekonstruksiyasi (rasm -> siluet -> voksel -> mesh).
    """
    from . import neural
    return neural.neural_mesh(kind, seed, image)
