"""Uchidan-uchiga pipeline — promptdan renderlangan previewgacha.

Bosqichlar (arxitektura hujjatidagi tartibda):
  1. Intent   — plan_from_prompt (qurilmada: Gemini Nano / AICore)
  2. Terrain  — generate_heightmap (qurilmada: GPU compute shader)
  3. Assets   — kutubxonadan tanlash (bu yerda kind orqali)
  4. Scatter  — scatter_objects (qurilmada: MultiMesh instancing)
  (Refine bosqichi Faza 2 — bu yerda hali yo'q.)

Detallar keshi `WorldCache` orqali: bir xil (prompt, seed) natijasi qayta
hisoblanmaydi.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .render import render_preview
from .scatter import Placement, counts_by_kind, scatter_objects
from .scene_plan import ScenePlan, plan_from_prompt
from .terrain import Heightmap, generate_heightmap


@dataclass
class WorldResult:
    plan: ScenePlan
    heightmap: Heightmap
    placements: list[Placement]
    timings_ms: dict[str, float]
    from_cache: bool = False


class WorldCache:
    """Oddiy LRU kesh — (prompt, seed, size) -> WorldResult.

    Qurilmada bu diskka ham yoziladi; bu yerda faqat xotirada.
    """

    def __init__(self, capacity: int = 16) -> None:
        self.capacity = capacity
        self._store: dict[tuple, WorldResult] = {}
        self._order: list[tuple] = []

    def key(self, prompt: str, seed: int | None, size: int) -> tuple:
        return (prompt, seed, size)

    def get(self, key: tuple) -> WorldResult | None:
        if key in self._store:
            self._order.remove(key)
            self._order.append(key)
            return self._store[key]
        return None

    def put(self, key: tuple, value: WorldResult) -> None:
        if key in self._store:
            self._order.remove(key)
        elif len(self._order) >= self.capacity:
            oldest = self._order.pop(0)
            self._store.pop(oldest, None)
        self._store[key] = value
        self._order.append(key)


def generate_world(
    prompt: str,
    *,
    seed: int | None = None,
    size: int = 192,
    cache: WorldCache | None = None,
) -> WorldResult:
    """Promptdan to'liq dunyoni quradi (reja + relyef + obyektlar)."""
    if cache is not None:
        cached = cache.get(cache.key(prompt, seed, size))
        if cached is not None:
            # Saqlangan obyektni o'zgartirmaymiz — nusxa qaytaramiz, aks holda
            # from_cache bayrog'i avvalgi chaqiruvchining natijasini ham buzadi.
            return replace(cached, from_cache=True)

    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    plan = plan_from_prompt(prompt, seed=seed, size=size)
    timings["intent_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    hm = generate_heightmap(plan.terrain)
    timings["terrain_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    placements = scatter_objects(plan, hm)
    timings["scatter_ms"] = (time.perf_counter() - t0) * 1000

    result = WorldResult(plan=plan, heightmap=hm, placements=placements, timings_ms=timings)

    if cache is not None:
        cache.put(cache.key(prompt, seed, size), result)
    return result


def render_world_png(result: WorldResult, path: str, *, upscale: int = 3) -> tuple[int, int]:
    """WorldResult'ni yuqoridan ko'rinish PNGiga chizadi."""
    from .pngwriter import write_rgb_png

    w, h, px = render_preview(result.heightmap, result.placements, upscale=upscale)
    write_rgb_png(path, w, h, px)
    return w, h


def summary(result: WorldResult) -> str:
    lo, hi = result.heightmap.min_max()
    counts = counts_by_kind(result.placements)
    total_ms = sum(result.timings_ms.values())
    lines = [
        f"prompt   : {result.plan.prompt!r}",
        f"biom     : {result.plan.terrain.biome}",
        f"seed     : {result.plan.terrain.seed}",
        f"o'lcham  : {result.heightmap.size}x{result.heightmap.size}",
        f"balandlik: [{lo:.3f} .. {hi:.3f}] (norm)",
        f"obyektlar: {sum(counts.values())} ta -> {counts}",
        f"vaqt     : {total_ms:.1f} ms  {result.timings_ms}",
        f"keshdan  : {result.from_cache}",
    ]
    return "\n".join(lines)
