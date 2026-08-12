"""Critic — sahnani baholab kamchilik va tuzatish taklifini beradi.

Bu qurilmadagi Gemini Nano multimodal baholovchisining o'rnini bosadi: u
renderni "ko'rib" sifatni baholaydi. Bu yerda baho relyef + joylashuv
statistikasidan determinlashgan tarzda hisoblanadi (testlanadigan). Chiqish
`Critique` — refine sikli shunga qarab rejani tuzatadi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pipeline import WorldResult
from .scatter import counts_by_kind


# Maqsad diapazonlari — "yaxshi" dunyo mezoni.
TARGET_BUILDABLE_MIN = 0.22        # suvdan yuqori yer ulushi (kamida)
TARGET_POPULATED = (0.04, 0.18)    # obyekt/quruqlik-katak ulushi (band)
TARGET_SECTOR_COVERAGE = 0.85      # obyektli sektorlar ulushi
SECTORS = 6                        # NxN sektor to'ri


@dataclass
class Critique:
    score: float                             # umumiy sifat [0..1]
    metrics: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    density_scale: float = 1.0               # scatter zichligini ko'paytirish/kamaytirish
    water_delta: float = 0.0                 # suv sathiga tuzatish

    @property
    def acceptable(self) -> bool:
        return self.score >= 0.85


def _buildable_ratio(result: WorldResult) -> float:
    hm = result.heightmap
    water = hm.spec.water_level
    land = sum(1 for h in hm.data if h > water)
    return land / max(1, len(hm.data))


def _sector_coverage(result: WorldResult) -> float:
    """Quruqlik bor sektorlarning nechtasida obyekt bor."""
    hm = result.heightmap
    size = hm.size
    water = hm.spec.water_level
    sec = SECTORS
    cell = size / sec

    land_sectors = set()
    for sy in range(sec):
        for sx in range(sec):
            # sektor markazida quruqlik bormi (arzon tekshiruv).
            cx = int((sx + 0.5) * cell)
            cy = int((sy + 0.5) * cell)
            if hm.get(cx, cy) > water:
                land_sectors.add((sx, sy))
    if not land_sectors:
        return 0.0

    world = hm.spec.world_scale
    half = world * 0.5
    cell_world = world / size
    occupied = set()
    for p in result.placements:
        gx = int((p.x + half) / cell_world)
        gy = int((p.z + half) / cell_world)
        sx = min(sec - 1, int(gx / cell))
        sy = min(sec - 1, int(gy / cell))
        occupied.add((sx, sy))

    covered = len(land_sectors & occupied)
    return covered / len(land_sectors)


def _band_score(value: float, lo: float, hi: float) -> float:
    """Qiymat [lo,hi] bandида 1.0, tashqarida chiziqli pasayadi."""
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return max(0.0, value / lo) if lo > 0 else 0.0
    # value > hi: haddan tashqari ko'p
    over = (value - hi) / hi if hi > 0 else 1.0
    return max(0.0, 1.0 - over)


def evaluate(result: WorldResult) -> Critique:
    """WorldResult'ni baholab Critique qaytaradi."""
    hm = result.heightmap
    size = hm.size
    water = hm.spec.water_level

    buildable = _buildable_ratio(result)
    land_cells = max(1, int(buildable * size * size))
    obj_count = len(result.placements)
    populated = obj_count / land_cells
    coverage = _sector_coverage(result)

    # Suv ostidagi obyektlar (bo'lmasligi kerak — qoida buzilishi belgisi).
    water_conflicts = sum(1 for p in result.placements if p.height <= water)

    issues: list[str] = []
    density_scale = 1.0
    water_delta = 0.0

    # 1) Yetarli quruqlik bormi?
    build_score = min(1.0, buildable / TARGET_BUILDABLE_MIN)
    if buildable < TARGET_BUILDABLE_MIN:
        issues.append(f"quruqlik kam ({buildable:.2f}) — suv sathi pasaytirildi")
        water_delta = -min(0.08, (TARGET_BUILDABLE_MIN - buildable))

    # 2) Obyekt zichligi bandда?
    lo, hi = TARGET_POPULATED
    pop_score = _band_score(populated, lo, hi)
    if populated < lo:
        issues.append(f"obyekt siyrak ({populated:.3f}) — zichlik oshirildi")
        mid = (lo + hi) * 0.5
        density_scale = min(3.0, mid / max(populated, 1e-4))
    elif populated > hi:
        issues.append(f"obyekt qalin ({populated:.3f}) — zichlik kamaytirildi")
        density_scale = max(0.4, hi / populated)

    # 3) Sektor qamrovi yetarlimi?
    cov_score = min(1.0, coverage / TARGET_SECTOR_COVERAGE)
    if coverage < TARGET_SECTOR_COVERAGE:
        issues.append(f"bo'sh sektorlar bor (qamrov {coverage:.2f}) — zichlik oshirildi")
        density_scale = max(density_scale, 1.3)

    # 4) Suv buzilishi.
    conflict_score = 1.0 if water_conflicts == 0 else 0.5
    if water_conflicts:
        issues.append(f"{water_conflicts} obyekt suv ostida")

    score = (build_score * 0.3 + pop_score * 0.3 + cov_score * 0.3 + conflict_score * 0.1)

    return Critique(
        score=round(score, 4),
        metrics={
            "buildable": round(buildable, 4),
            "populated": round(populated, 4),
            "sector_coverage": round(coverage, 4),
            "object_count": obj_count,
            "water_conflicts": water_conflicts,
        },
        issues=issues,
        density_scale=round(density_scale, 4),
        water_delta=round(water_delta, 4),
    )
