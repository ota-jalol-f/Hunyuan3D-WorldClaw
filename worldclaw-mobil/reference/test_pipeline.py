#!/usr/bin/env python3
"""Referens pipeline testlari — tashqi kutubxonasiz (assert bilan).

Ishlatish:  python3 test_pipeline.py
Chiqish kodi 0 = hammasi o'tdi.
"""

from __future__ import annotations

import sys

from worldclaw import ScenePlan, generate_world, plan_from_prompt
from worldclaw.noise import ValueNoise, fbm
from worldclaw.pipeline import WorldCache
from worldclaw.scene_plan import ScatterRule, TerrainSpec
from worldclaw.terrain import generate_heightmap
from worldclaw.scatter import scatter_objects


_passed = 0
_failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  OK   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}  {detail}")


def test_noise_deterministic() -> None:
    a = ValueNoise(42)
    b = ValueNoise(42)
    c = ValueNoise(43)
    check("noise bir seed -> bir xil", a.at(1.3, 2.7) == b.at(1.3, 2.7))
    check("noise boshqa seed -> farq", a.at(1.3, 2.7) != c.at(1.3, 2.7))
    vals = [fbm(a, x * 0.1, x * 0.2) for x in range(200)]
    check("fbm [-1,1] oralig'ida", all(-1.01 <= v <= 1.01 for v in vals),
          f"min={min(vals):.3f} max={max(vals):.3f}")


def test_biome_detection() -> None:
    check("qor -> snow", plan_from_prompt("qorli tog'lar").terrain.biome == "snow")
    check("sahro -> desert", plan_from_prompt("issiq sahro qumlari").terrain.biome == "desert")
    check("orol -> island", plan_from_prompt("tropik orol dengiz").terrain.biome == "island")
    check("vulqon -> volcano", plan_from_prompt("lava vulqon").terrain.biome == "volcano")
    check("standart -> grass", plan_from_prompt("noma'lum joy").terrain.biome == "grass")


def test_plan_validation() -> None:
    try:
        TerrainSpec(biome="mars").validate()
        check("noto'g'ri biom rad etiladi", False)
    except ValueError:
        check("noto'g'ri biom rad etiladi", True)

    try:
        ScatterRule("ufo", 0.5).validate()
        check("noto'g'ri obyekt turi rad etiladi", False)
    except ValueError:
        check("noto'g'ri obyekt turi rad etiladi", True)

    try:
        ScatterRule("tree", 5.0).validate()
        check("density chegarasi tekshiriladi", False)
    except ValueError:
        check("density chegarasi tekshiriladi", True)


def test_plan_json_roundtrip() -> None:
    plan = plan_from_prompt("qorli qishloq tog'lar")
    text = plan.to_json()
    back = ScenePlan.from_json(text)
    check("JSON roundtrip: biom saqlanadi", back.terrain.biome == plan.terrain.biome)
    check("JSON roundtrip: scatter soni", len(back.scatter) == len(plan.scatter))


def test_heightmap_bounds() -> None:
    spec = TerrainSpec(biome="snow", seed=7, size=96)
    hm = generate_heightmap(spec)
    lo, hi = hm.min_max()
    check("heightmap o'lchami to'g'ri", len(hm.data) == 96 * 96)
    check("balandlik [0,1] oralig'ida", 0.0 <= lo and hi <= 1.0, f"[{lo:.3f},{hi:.3f}]")
    check("relyefda o'zgaruvchanlik bor", hi - lo > 0.1, f"diapazon={hi-lo:.3f}")


def test_heightmap_deterministic() -> None:
    s = TerrainSpec(biome="grass", seed=123, size=64)
    a = generate_heightmap(s).data
    b = generate_heightmap(TerrainSpec(biome="grass", seed=123, size=64)).data
    check("heightmap determinlashgan", a == b)


def test_scatter_respects_rules() -> None:
    plan = plan_from_prompt("qorli qishloq", size=128)
    hm = generate_heightmap(plan.terrain)
    placements = scatter_objects(plan, hm)
    check("obyektlar joylashtirildi", len(placements) > 0, f"soni={len(placements)}")

    rules = {r.kind: r for r in plan.scatter}
    ok_height = ok_water = ok_slope = True
    for p in placements:
        r = rules[p.kind]
        if not (r.min_height <= p.height <= r.max_height):
            ok_height = False
        if r.avoid_water and p.height <= plan.terrain.water_level:
            ok_water = False
        gx = int((p.x + plan.terrain.world_scale * 0.5) / (plan.terrain.world_scale / hm.size))
        gy = int((p.z + plan.terrain.world_scale * 0.5) / (plan.terrain.world_scale / hm.size))
        if hm.slope(min(hm.size - 1, gx), min(hm.size - 1, gy)) > r.max_slope + 1e-6:
            ok_slope = False
    check("obyektlar balandlik chegarasida", ok_height)
    check("obyektlar suvdan qochadi", ok_water)
    check("obyektlar qiyalik chegarasida", ok_slope)


def test_cache() -> None:
    cache = WorldCache()
    r1 = generate_world("qorli qishloq", size=96, cache=cache)
    r2 = generate_world("qorli qishloq", size=96, cache=cache)
    check("birinchi hisob keshdan emas", r1.from_cache is False)
    check("ikkinchi hisob keshdan", r2.from_cache is True)
    check("kesh bir xil natija", len(r1.placements) == len(r2.placements))


def test_full_pipeline() -> None:
    r = generate_world("yashil vodiy o'rmon", size=96)
    check("pipeline reja qaytaradi", r.plan is not None)
    check("pipeline relyef qaytaradi", r.heightmap.size == 96)
    check("pipeline vaqtlarni o'lchaydi", "terrain_ms" in r.timings_ms)


def test_critic() -> None:
    from worldclaw import evaluate
    r = generate_world("yashil vodiy o'rmon", size=96)
    crit = evaluate(r)
    check("critic sifat [0,1]", 0.0 <= crit.score <= 1.0, f"score={crit.score}")
    check("critic metrikalar bor", "populated" in crit.metrics and "buildable" in crit.metrics)


def test_refine_improves() -> None:
    from worldclaw import evaluate, refine
    from worldclaw.pipeline import build_from_plan
    from worldclaw.scene_plan import plan_from_prompt
    from dataclasses import replace

    # Ataylab yomon reja — juda siyrak obyektlar.
    plan = plan_from_prompt("qorli qishloq tog'lar", size=128)
    bad_plan = replace(plan, scatter=[replace(r, density=r.density * 0.02) for r in plan.scatter])
    bad_world = build_from_plan(bad_plan)
    before = evaluate(bad_world).score

    rr = refine("qorli qishloq tog'lar", size=128, initial=bad_world, max_iters=6)
    after = rr.final_score

    check("refine sifatni oshiradi", after > before, f"{before:.3f} -> {after:.3f}")
    check("refine sikl tarixi bor", rr.iterations >= 1)
    check("refine sifat chegarasига yaqinlashadi", after >= 0.7, f"yakuniy={after:.3f}")


def test_refine_deterministic() -> None:
    from worldclaw import refine
    a = refine("cho'l sahro kaktus", size=96, max_iters=4)
    b = refine("cho'l sahro kaktus", size=96, max_iters=4)
    check("refine determinlashgan", a.final_score == b.final_score
          and a.iterations == b.iterations)


def test_texture() -> None:
    from worldclaw.texture import generate_material, generate_biome_set
    w, h, px = generate_material("snow", size=64, seed=1)
    check("tekstura o'lchami", w == 64 and h == 64 and len(px) == 64 * 64 * 3)
    _, _, px2 = generate_material("snow", size=64, seed=1)
    check("tekstura determinlashgan", px == px2)
    _, _, px3 = generate_material("snow", size=64, seed=2)
    check("boshqa seed -> boshqa tekstura", px != px3)
    mats = generate_biome_set("volcano", size=32)
    check("biom material to'plami", "lava" in mats and "rock" in mats)


def test_channels() -> None:
    from worldclaw import generate_world
    from worldclaw.channels import render_depth, render_normal, render_instance
    r = generate_world("yashil vodiy", size=64)
    dw, dh, dpx = render_depth(r.heightmap, upscale=1)
    check("depth o'lchami", dw == 64 and len(dpx) == 64 * 64 * 3)
    nw, nh, npx = render_normal(r.heightmap, upscale=1)
    check("normal o'lchami", nw == 64 and len(npx) == 64 * 64 * 3)
    iw, ih, ipx = render_instance(r.heightmap, r.placements, upscale=1)
    check("instance o'lchami", iw == 64 and len(ipx) == 64 * 64 * 3)
    # depth kulrang: R==G==B har pikselда
    grayscale = all(dpx[i] == dpx[i + 1] == dpx[i + 2] for i in range(0, len(dpx), 3))
    check("depth kulrang", grayscale)


def main() -> int:
    tests = [
        ("noise", test_noise_deterministic),
        ("biom aniqlash", test_biome_detection),
        ("reja validatsiyasi", test_plan_validation),
        ("JSON roundtrip", test_plan_json_roundtrip),
        ("heightmap chegaralari", test_heightmap_bounds),
        ("heightmap determinizm", test_heightmap_deterministic),
        ("scatter qoidalari", test_scatter_respects_rules),
        ("kesh", test_cache),
        ("to'liq pipeline", test_full_pipeline),
        ("critic baholovchi", test_critic),
        ("refine sifatni oshiradi", test_refine_improves),
        ("refine determinizm", test_refine_deterministic),
        ("generativ tekstura", test_texture),
        ("ko'rinish kanallari", test_channels),
    ]
    for title, fn in tests:
        print(f"[{title}]")
        fn()
        print()

    print(f"Natija: {_passed} o'tdi, {_failed} yiqildi")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
