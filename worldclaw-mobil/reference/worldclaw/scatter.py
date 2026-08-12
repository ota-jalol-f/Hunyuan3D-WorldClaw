"""Scatter — obyektlarni relyefga qoidalar bo'yicha joylashtirish.

Har ScatterRule uchun jitterlangan panjara bo'ylab nomzod nuqtalar olinadi va
balandlik / qiyalik / suv chegaralari tekshiriladi. Godotda o'rnatish
MultiMesh instancing bilan bo'ladi; joylashuv mantiqi shu.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scene_plan import ScenePlan, ScatterRule
from .terrain import Heightmap


@dataclass
class Placement:
    """Bitta joylashtirilgan obyekt (dunyo koordinatasida)."""

    kind: str
    x: float          # dunyo X (metr)
    z: float          # dunyo Z (metr)
    height: float     # normallashgan balandlik [0..1]
    y: float          # dunyo Y (metr) — balandlik
    scale: float      # variatsiya ko'lami
    yaw: float        # aylanish (radian)


class _Rng:
    """Kichik determinlashgan LCG — platformalararo bir xil natija."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = (seed ^ 0x27D4EB2F) & 0xFFFFFFFF

    def next_u32(self) -> int:
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.state

    def unit(self) -> float:
        """[0, 1) oralig'ida float."""
        return self.next_u32() / 4294967296.0


def _place_rule(
    rule: ScatterRule,
    hm: Heightmap,
    spec_water: float,
    world_scale: float,
    height_scale: float,
    seed: int,
) -> list[Placement]:
    rule.validate()
    size = hm.size
    rng = _Rng(seed ^ (hash(rule.kind) & 0xFFFFFFFF))

    # Zichlikdan panjara qadamini olamiz: density=1 -> har tugun nomzod.
    step = max(1, int(round(1.0 / max(rule.density, 1e-4)) ** 0.5))
    cell_world = world_scale / size

    out: list[Placement] = []
    for gy in range(0, size, step):
        for gx in range(0, size, step):
            # Katak ichida jitter.
            jx = gx + rng.unit() * step
            jy = gy + rng.unit() * step
            ix = min(size - 1, int(jx))
            iy = min(size - 1, int(jy))

            h = hm.get(ix, iy)
            if rule.avoid_water and h <= spec_water:
                continue
            if h < rule.min_height or h > rule.max_height:
                continue
            if hm.slope(ix, iy) > rule.max_slope:
                continue

            # Qo'shimcha siyraklashtirish — density panjara qadamiga to'liq
            # sig'masa, ehtimollik bilan tashlab yuboriladi.
            if rng.unit() > _cell_accept(rule.density, step):
                continue

            wx = (jx - size * 0.5) * cell_world
            wz = (jy - size * 0.5) * cell_world
            wy = h * height_scale
            scale = 0.75 + rng.unit() * 0.6
            yaw = rng.unit() * 6.2831853
            out.append(Placement(rule.kind, wx, wz, h, wy, scale, yaw))

    return out


def _cell_accept(density: float, step: int) -> float:
    """Panjara qadami bilan haqiqiy zichlikni moslash uchun qabul ehtimoli."""
    expected = density * step * step
    return min(1.0, expected)


def scatter_objects(plan: ScenePlan, hm: Heightmap) -> list[Placement]:
    """Rejadagi barcha qoidalar bo'yicha obyektlarni joylashtiradi."""
    plan.validate()
    spec = plan.terrain
    placements: list[Placement] = []
    for rule in plan.scatter:
        placements.extend(
            _place_rule(
                rule, hm,
                spec_water=spec.water_level,
                world_scale=spec.world_scale,
                height_scale=spec.height_scale,
                seed=spec.seed,
            )
        )
    return placements


def counts_by_kind(placements: list[Placement]) -> dict[str, int]:
    result: dict[str, int] = {}
    for p in placements:
        result[p.kind] = result.get(p.kind, 0) + 1
    return result
