"""Real-vaqt prompt tahriri — matn yozib dunyoni/tabiatni o'zgartirish.

Optimizatsiya: har tahrir faqat KERAKLI qismni qayta hisoblaydi:
  * env      — faqat muhit holati (fasl/vaqt/ob-havo). Relyef/scatter tegmaydi.
  * scatter  — o'simlik/obyekt zichligi. Relyef qayta ishlatiladi (~ms).
  * water    — suv sathi. Relyef qayta ishlatiladi.
  * terrain  — relyef parametrlari. Relyef qayta generatsiya (sekin).
  * full     — biom o'zgardi. To'liq qayta.

Qurilmада promptni Gemini Nano tahlil qiladi; bu qoidали parser oflayn
zaxira (rejalovchi bilan bir xil naqsh).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .lifecycle import EnvState, season_vegetation_scale
from .pipeline import WorldResult
from .scatter import scatter_objects
from .scene_plan import ScenePlan, plan_from_prompt
from .terrain import generate_heightmap


@dataclass
class EditResult:
    world: WorldResult
    env: EnvState
    changed: str
    level: str
    ms: float


# Kalit so'z -> (intent, param). Uz/En sinonimlar.
_SEASONS = {
    "bahor": 40, "spring": 40, "yoz": 130, "summer": 130,
    "kuz": 220, "autumn": 220, "fall": 220, "qish": 310, "winter": 310,
}
_TIMES = {"tong": 6.5, "morning": 6.5, "kun": 12.0, "peshin": 12.0, "noon": 12.0,
          "day": 12.0, "kech": 19.0, "evening": 19.0, "tun": 23.0, "night": 23.0}
_WEATHER = {"yomg'ir": "yomg'ir", "rain": "yomg'ir", "qor yog": "qor", "snow": "qor",
            "ochiq": "ochiq", "clear": "ochiq", "bulut": "bulutli", "cloud": "bulutli"}


def _has(text: str, *words: str) -> bool:
    return any(w in text for w in words)


def apply_edit(world: WorldResult, env: EnvState, prompt: str) -> EditResult:
    """Promptni tahlil qilib, minimal qayta hisoblash bilan qo'llaydi."""
    t0 = time.perf_counter()
    low = prompt.lower()
    plan = world.plan
    hm = world.heightmap
    level = "env"
    changed = "o'zgarishsiz"

    # --- Muhit / hayot sikli (relyef tegmaydi) ---
    season_changed = False
    for key, doy in _SEASONS.items():
        if key in low:
            env.day_of_year = float(doy)
            season_changed = True
            changed = f"fasl: {env.season}"
            break
    for key, tod in _TIMES.items():
        if key in low:
            env.time_of_day = tod
            changed = f"vaqt: {tod:.0f}:00 ({'tun' if env.is_night else 'kun'})"
    for key, w in _WEATHER.items():
        if key in low:
            env.weather = w
            changed = f"ob-havo: {w}"

    # --- Biom almashtirish (to'liq qayta) ---
    biome_words = {"sahro": "desert", "desert": "desert", "qor": "snow", "snow": "snow",
                   "orol": "island", "island": "island", "kanyon": "canyon", "canyon": "canyon",
                   "vulqon": "volcano", "volcano": "volcano", "o'rmon": "grass", "vodiy": "grass"}
    new_biome = None
    for key, b in biome_words.items():
        if key in low and b != plan.terrain.biome and not season_changed:
            new_biome = b
            break
    if new_biome:
        from .pipeline import generate_world
        env.biome = new_biome
        new_world = generate_world(prompt, size=plan.terrain.size)
        return EditResult(new_world, env, f"biom: {new_biome}", "full",
                          (time.perf_counter() - t0) * 1000)

    # --- Relyef tahriri (qayta generatsiya) ---
    terr = plan.terrain
    terrain_changed = False
    if _has(low, "tog'", "mountain", "baland", "higher"):
        terr = replace(terr, mountain_strength=min(1.0, terr.mountain_strength + 0.2),
                       height_scale=min(120.0, terr.height_scale * 1.15))
        terrain_changed = True; changed = "tog'lar balandroq"
    elif _has(low, "tekis", "flat", "flatten", "pasayt"):
        terr = replace(terr, mountain_strength=max(0.1, terr.mountain_strength - 0.25))
        terrain_changed = True; changed = "relyef tekisroq"
    if _has(low, "g'adir", "rough", "qoya"):
        terr = replace(terr, roughness=min(0.9, terr.roughness + 0.15))
        terrain_changed = True; changed = "relyef g'adir-budurroq"
    elif _has(low, "silliq", "smooth"):
        terr = replace(terr, roughness=max(0.3, terr.roughness - 0.15))
        terrain_changed = True; changed = "relyef silliqroq"

    # --- Suv tahriri (relyef qayta ishlatiladi) ---
    water_changed = False
    if _has(low, "toshqin", "flood", "suv ko'tar", "ko'l"):
        terr = replace(terr, water_level=min(0.7, terr.water_level + 0.1))
        water_changed = True; changed = "suv ko'tarildi"
    elif _has(low, "qurit", "drain", "suv kamayt"):
        terr = replace(terr, water_level=max(0.0, terr.water_level - 0.1))
        water_changed = True; changed = "suv kamaydi"

    # --- Scatter / o'simlik tahriri ---
    new_scatter = list(plan.scatter)
    scatter_changed = False
    veg_kinds = ("tree", "palm", "cactus")
    if _has(low, "ko'p daraxt", "more tree", "o'rmon", "forest", "ko'kalamzor"):
        new_scatter = [replace(r, density=min(1.0, r.density * 1.6)) if r.kind in veg_kinds else r
                       for r in new_scatter]
        scatter_changed = True; changed = "o'simlik ko'paydi"
    elif _has(low, "kes", "clear", "kam daraxt", "less tree", "yalang"):
        new_scatter = [replace(r, density=r.density * 0.4) if r.kind in veg_kinds else r
                       for r in new_scatter]
        scatter_changed = True; changed = "o'simlik kamaydi"
    if _has(low, "uy", "house", "qishloq", "village", "shahar"):
        new_scatter = [replace(r, density=min(1.0, r.density * 2.0)) if r.kind == "house" else r
                       for r in new_scatter]
        scatter_changed = True; changed = "binolar ko'paydi"

    # Fasl o'simlik zichligini vizual o'zgartiradi (qish -> siyrak).
    if season_changed:
        vs = season_vegetation_scale(env)
        new_scatter = [replace(r, density=min(1.0, r.density * vs)) if r.kind in veg_kinds else r
                       for r in new_scatter]
        scatter_changed = True

    new_plan = replace(plan, terrain=terr, scatter=new_scatter)

    # --- Minimal qayta hisoblash ---
    if terrain_changed:
        level = "terrain"
        hm = generate_heightmap(terr)
        placements = scatter_objects(new_plan, hm)
    elif water_changed:
        level = "water"
        placements = scatter_objects(new_plan, hm)   # relyef o'sha
    elif scatter_changed:
        level = "scatter"
        placements = scatter_objects(new_plan, hm)   # relyef o'sha
    else:
        placements = world.placements                # hech nima regen qilinmaydi

    new_world = WorldResult(plan=new_plan, heightmap=hm, placements=placements,
                            timings_ms=dict(world.timings_ms))
    return EditResult(new_world, env, changed, level, (time.perf_counter() - t0) * 1000)
