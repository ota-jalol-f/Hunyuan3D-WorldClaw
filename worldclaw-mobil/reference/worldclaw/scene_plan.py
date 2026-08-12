"""scene_plan — butun pipeline'ning shartnomasi (contract).

`ScenePlan` — Intent bosqichi (qurilmada Gemini Nano) chiqaradigan strukturali
reja. Bu yerdagi `plan_from_prompt` esa qoidali zaxira rejalovchi: oflayn, chip
talab qilmaydi, testlar uchun determinlashgan. Qurilmada uning o'rnini
`android/IntentPlanner.kt` (AICore) egallaydi, ammo natija sxemasi bir xil.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any


# Qo'llab-quvvatlanadigan biom turlari — terrain va material shu ro'yxatga tayanadi.
BIOMES = ("snow", "desert", "island", "canyon", "volcano", "grass")

# Asset kutubxonasidagi obyekt turlari (geometriya tanlash uchun kalit).
OBJECT_KINDS = ("tree", "house", "rock", "fence", "torch", "cactus", "palm")


@dataclass
class TerrainSpec:
    """Relyef generatsiyasi parametrlari."""

    biome: str = "grass"
    seed: int = 0
    size: int = 256                 # heightmap qirrasi (tugunlar soni)
    world_scale: float = 400.0      # dunyoning metrdagi kengligi
    height_scale: float = 60.0      # maksimal balandlik (metr)
    mountain_strength: float = 0.6  # tizmali noise ulushi [0..1]
    water_level: float = 0.28       # normallashgan balandlikda suv sathi [0..1]
    roughness: float = 0.5          # fBm gain

    def validate(self) -> None:
        if self.biome not in BIOMES:
            raise ValueError(f"noma'lum biom: {self.biome!r} (mumkin: {BIOMES})")
        if not (16 <= self.size <= 2048):
            raise ValueError(f"size chegaradan tashqarida: {self.size}")
        if not (0.0 <= self.mountain_strength <= 1.0):
            raise ValueError("mountain_strength [0..1] bo'lishi kerak")
        if not (0.0 <= self.water_level < 1.0):
            raise ValueError("water_level [0..1) bo'lishi kerak")


@dataclass
class ScatterRule:
    """Bitta obyekt turini relyefga tarqatish qoidasi."""

    kind: str
    density: float                  # 1 tugunga to'g'ri keladigan o'rtacha son [0..1]
    min_height: float = 0.0         # normallashgan balandlik chegaralari [0..1]
    max_height: float = 1.0
    max_slope: float = 1.0          # ruxsat etilgan maksimal qiyalik [0..1]
    avoid_water: bool = True

    def validate(self) -> None:
        if self.kind not in OBJECT_KINDS:
            raise ValueError(f"noma'lum obyekt turi: {self.kind!r}")
        if not (0.0 <= self.density <= 1.0):
            raise ValueError("density [0..1] bo'lishi kerak")
        if self.min_height > self.max_height:
            raise ValueError("min_height > max_height")


@dataclass
class ScenePlan:
    """Promptdan olingan to'liq sahna rejasi."""

    prompt: str
    terrain: TerrainSpec = field(default_factory=TerrainSpec)
    scatter: list[ScatterRule] = field(default_factory=list)
    style: str = "cartoon"          # vizual uslub (NPR/realistik)
    notes: str = ""

    def validate(self) -> None:
        self.terrain.validate()
        seen = set()
        for rule in self.scatter:
            rule.validate()
            if rule.kind in seen:
                raise ValueError(f"takroriy scatter qoidasi: {rule.kind}")
            seen.add(rule.kind)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenePlan":
        terrain = TerrainSpec(**data.get("terrain", {}))
        scatter = [ScatterRule(**r) for r in data.get("scatter", [])]
        plan = cls(
            prompt=data.get("prompt", ""),
            terrain=terrain,
            scatter=scatter,
            style=data.get("style", "cartoon"),
            notes=data.get("notes", ""),
        )
        plan.validate()
        return plan

    @classmethod
    def from_json(cls, text: str) -> "ScenePlan":
        return cls.from_dict(json.loads(text))


# --- Qoidali zaxira rejalovchi (Gemini Nano stubi) -------------------------

# Kalit so'z -> biom. Qurilmada buni Nano semantik ravishda hal qiladi.
_BIOME_KEYWORDS = {
    "snow": ("snow", "qor", "ice", "muz", "winter", "qish", "frozen", "sovuq"),
    "desert": ("desert", "sahro", "dune", "qum", "sand", "arid"),
    "island": ("island", "orol", "ocean", "sea", "dengiz", "beach", "tropical"),
    "canyon": ("canyon", "kanyon", "gorge", "mesa", "cliff", "jarlik"),
    "volcano": ("volcano", "vulqon", "lava", "ember", "magma", "caldera"),
    "grass": ("grass", "forest", "o'rmon", "meadow", "valley", "vodiy", "green"),
}

# Biom -> odatiy scatter qoidalari.
_BIOME_SCATTER = {
    "snow": [
        ScatterRule("tree", 0.05, min_height=0.30, max_height=0.75, max_slope=0.5),
        ScatterRule("house", 0.004, min_height=0.30, max_height=0.55, max_slope=0.25),
        ScatterRule("rock", 0.02, min_height=0.28, max_height=0.95, max_slope=0.8),
        ScatterRule("torch", 0.003, min_height=0.30, max_height=0.55, max_slope=0.3),
        ScatterRule("fence", 0.01, min_height=0.30, max_height=0.55, max_slope=0.3),
    ],
    "desert": [
        ScatterRule("cactus", 0.03, min_height=0.30, max_height=0.7, max_slope=0.4),
        ScatterRule("rock", 0.03, min_height=0.28, max_height=0.95, max_slope=0.9),
        ScatterRule("house", 0.002, min_height=0.30, max_height=0.5, max_slope=0.2),
    ],
    "island": [
        ScatterRule("palm", 0.04, min_height=0.30, max_height=0.6, max_slope=0.5),
        ScatterRule("rock", 0.02, min_height=0.29, max_height=0.9, max_slope=0.9),
        ScatterRule("house", 0.003, min_height=0.31, max_height=0.5, max_slope=0.2),
    ],
    "canyon": [
        ScatterRule("rock", 0.05, min_height=0.20, max_height=0.98, max_slope=1.0),
        ScatterRule("cactus", 0.015, min_height=0.25, max_height=0.6, max_slope=0.5),
    ],
    "volcano": [
        ScatterRule("rock", 0.06, min_height=0.20, max_height=0.98, max_slope=1.0),
        ScatterRule("torch", 0.004, min_height=0.30, max_height=0.7, max_slope=0.5),
    ],
    "grass": [
        ScatterRule("tree", 0.08, min_height=0.30, max_height=0.8, max_slope=0.6),
        ScatterRule("house", 0.004, min_height=0.30, max_height=0.5, max_slope=0.25),
        ScatterRule("rock", 0.02, min_height=0.29, max_height=0.95, max_slope=0.9),
        ScatterRule("fence", 0.012, min_height=0.30, max_height=0.5, max_slope=0.3),
    ],
}

# Biom -> terrain o'ziga xosligi.
_BIOME_TERRAIN = {
    "snow": dict(mountain_strength=0.75, height_scale=80.0, water_level=0.28, roughness=0.5),
    "desert": dict(mountain_strength=0.35, height_scale=40.0, water_level=0.0, roughness=0.55),
    "island": dict(mountain_strength=0.45, height_scale=55.0, water_level=0.42, roughness=0.5),
    "canyon": dict(mountain_strength=0.85, height_scale=90.0, water_level=0.15, roughness=0.65),
    "volcano": dict(mountain_strength=0.8, height_scale=95.0, water_level=0.1, roughness=0.6),
    "grass": dict(mountain_strength=0.5, height_scale=50.0, water_level=0.25, roughness=0.5),
}


def _stable_seed(text: str) -> int:
    """Promptdan takrorlanuvchi seed (platformalararo bir xil)."""
    h = 2166136261
    for ch in text:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def detect_biome(prompt: str) -> str:
    """Kalit so'zlar bo'yicha biomni aniqlaydi; standart — grass."""
    low = prompt.lower()
    best, best_hits = "grass", 0
    for biome, words in _BIOME_KEYWORDS.items():
        hits = sum(1 for w in words if w in low)
        if hits > best_hits:
            best, best_hits = biome, hits
    return best


def plan_from_prompt(prompt: str, *, seed: int | None = None, size: int = 256) -> ScenePlan:
    """Matnli promptni ScenePlan'ga aylantiruvchi oflayn zaxira rejalovchi.

    Qurilmada bu funksiyaning o'rnini Gemini Nano (AICore) egallaydi; u boyroq,
    kontekstga sezgir reja beradi. Ikkalasi ham bir xil `ScenePlan` sxemasini
    chiqaradi, shuning uchun pastdagi pipeline ikkalasi bilan ham ishlaydi.
    """
    biome = detect_biome(prompt)
    resolved_seed = seed if seed is not None else _stable_seed(prompt)
    terrain = TerrainSpec(biome=biome, seed=resolved_seed, size=size, **_BIOME_TERRAIN[biome])
    scatter = [ScatterRule(**asdict(r)) for r in _BIOME_SCATTER[biome]]
    plan = ScenePlan(
        prompt=prompt,
        terrain=terrain,
        scatter=scatter,
        notes=f"qoidali zaxira rejalovchi; aniqlangan biom: {biome}",
    )
    plan.validate()
    return plan
