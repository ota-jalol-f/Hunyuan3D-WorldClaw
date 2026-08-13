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


def test_gltf_export() -> None:
    import os, struct, json as _json, tempfile
    from worldclaw import generate_world
    from worldclaw.gltf import export_glb

    r = generate_world("qorli qishloq tog'lar", size=64)
    path = os.path.join(tempfile.gettempdir(), "wc_test.glb")
    stats = export_glb(r, path, max_objects=500, terrain_stride=2)

    with open(path, "rb") as f:
        data = f.read()
    magic, ver, total = struct.unpack("<III", data[:12])
    check("glb magic to'g'ri", magic == 0x46546C67)
    check("glb versiya 2", ver == 2)
    check("glb uzunlik mos", total == len(data))
    jlen, jtype = struct.unpack("<II", data[12:20])
    check("glb JSON chunk", jtype == 0x4E4F534A)
    gltf = _json.loads(data[20:20 + jlen])
    check("glb relyef mesh bor", len(gltf["meshes"]) >= 1)
    check("glb tugunlar bor", len(gltf["nodes"]) >= 1)
    # accessor chegaralari bufer ichida
    blen = struct.unpack("<I", data[20 + jlen:24 + jlen])[0]
    ok = all(gltf["bufferViews"][a["bufferView"]]["byteOffset"]
             + gltf["bufferViews"][a["bufferView"]]["byteLength"] <= blen
             for a in gltf["accessors"])
    check("glb accessorlar bufer ichida", ok)
    os.remove(path)


def test_mesh_generators() -> None:
    from worldclaw.mesh import generate, variants, _GENERATORS
    for kind in _GENERATORS:
        parts = generate(kind, 1)
        tris = sum(len(p.indices) // 3 for p in parts)
        verts = sum(len(p.positions) for p in parts)
        ok_norm = all(len(p.normals) == len(p.positions) for p in parts)
        ok_idx = all(max(p.indices) < len(p.positions) for p in parts if p.indices)
        check(f"mesh '{kind}' geometriya", tris > 0 and verts > 0 and ok_norm and ok_idx,
              f"tris={tris} verts={verts}")
    a = generate("tree", 5)
    b = generate("tree", 5)
    ta = sum(len(p.positions) for p in a)
    tb = sum(len(p.positions) for p in b)
    check("mesh determinlashgan", ta == tb)
    vs = variants("house", count=4, seed=1)
    check("variantlar soni", len(vs) == 4)


def test_iso_render() -> None:
    from worldclaw import generate_world
    from worldclaw.iso import render_iso
    r = generate_world("yashil vodiy", size=48)
    w, h, px = render_iso(r.heightmap, r.placements, width=200, stride=1)
    check("iso o'lchami", w == 200 and len(px) == w * h * 3)
    # Fon bir xil emas — relyef chizilgan (turli piksellar bor)
    sample = set((px[i], px[i + 1], px[i + 2]) for i in range(0, len(px), 300))
    check("iso relyef chizilgan", len(sample) > 5, f"ranglar={len(sample)}")


def test_lifecycle() -> None:
    import statistics as st
    from worldclaw.lifecycle import LifecycleSim, EnvState
    sim = LifecycleSim(EnvState(biome="grass"), seed=3)
    hist = sim.run(days=720, dt_days=0.05)
    stable = [h for h in hist if h.day > 360]
    veg = [h.vegetation for h in stable]
    herb = [h.herbivores for h in stable]
    pred = [h.predators for h in stable]
    check("ekotizim yo'qolmaydi", min(veg) > 0.005 and min(herb) > 0.005 and min(pred) > 0.005)
    check("ekotizim portlamaydi", max(veg) < 3 and max(herb) < 3 and max(pred) < 3)
    check("populyatsiya tebranadi", (max(herb) - min(herb)) > 0.1 and (max(pred) - min(pred)) > 0.05)
    summer = [h.vegetation for h in stable if h.season == "yoz"]
    winter = [h.vegetation for h in stable if h.season == "qish"]
    check("o'simlik yozда qishдан ko'p", st.mean(summer) > st.mean(winter))
    check("tun/kun", EnvState(time_of_day=23).is_night and not EnvState(time_of_day=12).is_night)
    sw = LifecycleSim(EnvState(biome="snow", day_of_year=310, time_of_day=3))
    sw.step(0.01)
    check("qishда sovuq (< 0°C)", sw.state.temperature < 0, f"T={sw.state.temperature:.1f}")


def test_edit() -> None:
    from worldclaw import generate_world
    from worldclaw.edit import apply_edit
    from worldclaw.lifecycle import EnvState
    w = generate_world("yashil vodiy o'rmon uylar", size=96)
    n0 = len(w.placements)

    r = apply_edit(w, EnvState(biome="grass"), "ko'p daraxt o'rmon")
    check("o'simlik tahriri = scatter", r.level == "scatter")
    check("scatter relyefni QAYTA ISHLATADI", r.world.heightmap is w.heightmap)
    check("daraxtlar ko'paydi", len(r.world.placements) > n0)
    check("scatter tez (<200ms)", r.ms < 200, f"{r.ms:.0f}ms")

    r2 = apply_edit(w, EnvState(biome="grass"), "toshqin ko'l")
    check("suv tahriri = water", r2.level == "water")
    check("water relyefni qayta ishlatadi", r2.world.heightmap is w.heightmap)
    check("suv sathi oshdi", r2.world.plan.terrain.water_level > w.plan.terrain.water_level)

    r3 = apply_edit(w, EnvState(biome="grass"), "tog'larni baland qil")
    check("relyef tahriri = terrain", r3.level == "terrain")
    check("relyef qayta generatsiya qilindi", r3.world.heightmap is not w.heightmap)

    env = EnvState(biome="grass")
    apply_edit(w, env, "qish keldi qor")
    check("fasl tahriri qo'llandi", env.season == "qish")

    r5 = apply_edit(w, EnvState(biome="grass"), "sahroga aylantir")
    check("biom tahriri = full", r5.level == "full" and r5.world.plan.terrain.biome == "desert")


def test_audio() -> None:
    from worldclaw.audio import generate_soundscape, RATE
    s = generate_soundscape("grass", seed=1, seconds=2.0)
    check("audio uzunligi to'g'ri", len(s) == int(2.0 * RATE))
    check("audio int16 chegarasida", all(-32768 <= x <= 32767 for x in s[:2000]))
    nonsilent = sum(1 for x in s if abs(x) > 300)
    check("audio jim emas", nonsilent > len(s) * 0.3, f"non-silent={100*nonsilent//len(s)}%")
    s2 = generate_soundscape("grass", seed=1, seconds=2.0)
    check("audio determinlashgan", s == s2)
    v = generate_soundscape("volcano", seed=1, seconds=2.0)
    check("biomlar farq qiladi", s != v)


def test_neural_image_to_3d() -> None:
    from worldclaw.neural import neural_mesh, render_silhouettes, silhouette_iou, RES
    from worldclaw.mesh import generate
    # Rekonstruksiya mesh chiqaradi
    recon = neural_mesh("house", 1)
    tris = sum(len(p.indices) // 3 for p in recon)
    check("image-to-3D mesh chiqaradi", tris > 0 and len(recon[0].positions) > 0, f"tris={tris}")
    # Konveks shakl uchun siluet mos keladi (visual hull to'g'ri)
    src = generate("house", 1)
    ious = []
    for view in ("front", "side", "top"):
        a = render_silhouettes(src)[view]
        b = render_silhouettes(recon)[view]
        ious.append(silhouette_iou(a, b, RES))
    check("rekonstruksiya siluetга mos (IoU)", min(ious) > 0.85, f"IoU={[round(i,2) for i in ious]}")
    # Determinizm
    r2 = neural_mesh("house", 1)
    check("image-to-3D determinlashgan",
          sum(len(p.indices) for p in recon) == sum(len(p.indices) for p in r2))


def _flat_field(height_norm=0.3, size=32):
    from worldclaw.terrain import Heightmap
    from worldclaw.scene_plan import TerrainSpec
    from worldclaw.physics import TerrainField
    spec = TerrainSpec(biome="grass", size=size, world_scale=400.0, height_scale=60.0)
    hm = Heightmap(size, spec)
    for i in range(len(hm.data)):
        hm.data[i] = height_norm
    return TerrainField(hm), height_norm * spec.height_scale


def test_gravity_freefall() -> None:
    from worldclaw.physics import Body, TerrainField, simulate, GRAVITY
    field_, _ = _flat_field(0.0)
    b = Body(kind="rock", x=0, y=1000.0, z=0, radius=1.0)
    dt = 1.0 / 120.0
    steps = 60                              # 0.5 s
    for _ in range(steps):
        from worldclaw.physics import step
        step([b], field_, dt)
    t = steps * dt
    expected_drop = 0.5 * GRAVITY * t * t
    actual_drop = 1000.0 - b.y
    check("tortishish 9.81 (erkin tushish)", abs(actual_drop - expected_drop) / expected_drop < 0.05,
          f"kutilgan={expected_drop:.3f} haqiqiy={actual_drop:.3f}")


def test_settle_on_terrain() -> None:
    from worldclaw import generate_world
    from worldclaw.physics import TerrainField, drop_bodies_from_placements, simulate
    r = generate_world("yashil vodiy o'rmon", size=96)
    field_ = TerrainField(r.heightmap)
    bodies = drop_bodies_from_placements(r.placements, field_, drop_height=30.0, limit=40)
    stats = simulate(bodies, field_, max_steps=3000)
    check("jismlar cho'kdi", stats.settled == len(bodies), f"{stats.settled}/{len(bodies)}")
    # Har jism yer sirtida (radiusда) turadi
    ok_rest = True
    for b in bodies:
        g = field_.height_at(b.x, b.z)
        if not (g - 0.5 <= b.y - b.radius <= g + 1.0):
            ok_rest = False
    check("jismlar yer sirtida turadi", ok_rest)


def test_no_tunneling() -> None:
    from worldclaw import generate_world
    from worldclaw.physics import TerrainField, drop_bodies_from_placements, simulate
    r = generate_world("qorli tog'lar", size=96)
    field_ = TerrainField(r.heightmap)
    bodies = drop_bodies_from_placements(r.placements, field_, drop_height=60.0, limit=30)
    stats = simulate(bodies, field_, max_steps=3000)
    check("relyefdan o'tib ketmaydi (tunnel yo'q)", stats.max_penetration < 3.0,
          f"max_pen={stats.max_penetration:.3f}")


def test_restitution_energy_loss() -> None:
    from worldclaw.physics import Body, step
    field_, ground = _flat_field(0.3)
    drop_h = 40.0
    b = Body(kind="rock", x=0, y=ground + 1.0 + drop_h, z=0, radius=1.0)
    dt = 1.0 / 240.0
    ys = []
    for _ in range(3000):
        step([b], field_, dt)
        ys.append(b.y)
        if b.resting:
            break
    # Birinchi urilishdan keyin cho'qqi topamiz
    contacted = False
    bounce_peak = ground
    for i in range(1, len(ys)):
        if ys[i] <= ground + 1.2:
            contacted = True
        if contacted and ys[i] > ys[i - 1]:
            bounce_peak = max(bounce_peak, ys[i])
    check("qaytish energiya yo'qotadi (restitution<1)",
          bounce_peak - ground < drop_h * 0.5, f"sakrash={bounce_peak-ground:.2f} < {drop_h*0.5}")


def _ramp_field(size=48, lo=0.1, hi=0.6, water=0.4):
    from worldclaw.terrain import Heightmap
    from worldclaw.scene_plan import TerrainSpec
    from worldclaw.physics import TerrainField
    spec = TerrainSpec(biome="grass", size=size, world_scale=400.0, height_scale=60.0, water_level=water)
    hm = Heightmap(size, spec)
    for gy in range(size):
        for gx in range(size):
            hm.data[gy * size + gx] = lo + (hi - lo) * (gx / size)
    return TerrainField(hm)


def _wall_field(size=48, base=0.1, top=0.9, water=0.05):
    from worldclaw.terrain import Heightmap
    from worldclaw.scene_plan import TerrainSpec
    from worldclaw.physics import TerrainField
    spec = TerrainSpec(biome="grass", size=size, world_scale=400.0, height_scale=60.0, water_level=water)
    hm = Heightmap(size, spec)
    for gy in range(size):
        for gx in range(size):
            hm.data[gy * size + gx] = top if gx >= size // 2 else base
    return TerrainField(hm)


def test_buoyancy() -> None:
    from worldclaw.physics import Body, simulate, _submerged_fraction
    field_, ground = _flat_field(0.1)          # ground=6, suv sathi ~16.8
    wy = field_.water_y
    wood = Body("tree", 0, wy + 20, 0, radius=1.5)      # zichlik 700 < 1000 -> suzadi
    simulate([wood], field_, max_steps=8000)
    f = _submerged_fraction(wood, wy)
    check("yog'och suvда suzadi", wood.y - wood.radius > ground + 0.5 and 0.3 < f < 0.98,
          f"y={wood.y:.2f} ground={ground:.1f} f_sub={f:.2f}")
    rock = Body("rock", 5, wy + 20, 5, radius=1.5)      # zichlik 2700 -> cho'kadi
    simulate([rock], field_, max_steps=8000)
    check("tosh suvда cho'kadi", abs(rock.y - (ground + rock.radius)) < 1.2,
          f"y={rock.y:.2f} tub={ground+rock.radius:.2f}")


def test_water_flow() -> None:
    from worldclaw.physics import Body, Environment, simulate
    field_ = _ramp_field()
    env = Environment(flow_speed=6.0, use_terrain_flow=True)
    wood = Body("tree", -120.0, field_.water_y - 1.0, -0.0, radius=1.4)
    x0 = wood.x
    simulate([wood], field_, max_steps=1500, env=env)
    check("suv oqimi jismni pastga suradi", wood.x < x0 - 2.0, f"{x0:.1f} -> {wood.x:.1f}")


def test_wind_light_vs_heavy() -> None:
    from worldclaw.physics import Body, Environment, step
    field_, _ = _flat_field(0.0)
    env = Environment(wind=(15.0, 0.0, 0.0))
    light = Body("tree", 0, 100.0, 0, radius=1.5)       # yengil
    heavy = Body("rock", 0, 100.0, 0, radius=1.5)       # og'ir
    for _ in range(20):
        step([light, heavy], field_, 1.0 / 120.0, env)
    check("shamol yengil jismni ko'proq suradi", light.vx > heavy.vx > 0.0,
          f"yengil={light.vx:.3f} og'ir={heavy.vx:.3f}")


def test_character_falls_and_lands() -> None:
    from worldclaw import generate_world
    from worldclaw.physics import TerrainField, Character
    r = generate_world("yashil vodiy", size=96)
    field_ = TerrainField(r.heightmap)
    c = Character(x=0, y=250.0, z=0)
    for _ in range(4000):
        c.update(field_, (0.0, 0.0), 1.0 / 120.0)
        if c.on_ground and abs(c.vy) < 0.01:
            break
    ground = field_.height_at(c.x, c.z)
    check("character yerга tushadi", c.on_ground and abs(c.feet_y - ground) < 0.6,
          f"feet={c.feet_y:.2f} ground={ground:.2f}")


def test_character_walks_terrain() -> None:
    from worldclaw import generate_world
    from worldclaw.physics import TerrainField, Character
    r = generate_world("yashil vodiy", size=96)
    field_ = TerrainField(r.heightmap)
    c = Character(x=-100.0, y=250.0, z=0)
    for _ in range(600):                     # yerга tushirish
        c.update(field_, (0.0, 0.0), 1.0 / 120.0)
    x_start = c.x
    max_pen = 0.0                            # oyoq yerdan qancha PASTга o'tdi (yomon)
    for _ in range(1200):                    # oldinга yurish
        c.update(field_, (1.0, 0.0), 1.0 / 120.0)
        pen = field_.height_at(c.x, c.z) - c.feet_y   # >0 -> relyef ostida
        max_pen = max(max_pen, pen)
    check("character yurib relyefdan o'tmaydi", c.x > x_start + 20.0 and max_pen < 1.0,
          f"dx={c.x-x_start:.1f} max_pen={max_pen:.2f}")


def test_character_slope_limit() -> None:
    from worldclaw.physics import TerrainField, Character
    field_ = _wall_field()
    # Devor gx=size/2 da; dunyo x=0 da. Character chapdan yuradi.
    c = Character(x=-30.0, y=60.0, z=0, max_slope_deg=45.0)
    for _ in range(400):
        c.update(field_, (0.0, 0.0), 1.0 / 120.0)   # tushirish
    for _ in range(800):
        c.update(field_, (1.0, 0.0), 1.0 / 120.0)   # devorга qarab
    check("character tik devordan o'tolmaydi", c.x < 0.0, f"x={c.x:.1f} (devor 0 da)")


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
        ("generativ mesh", test_mesh_generators),
        ("neyron image-to-3D", test_neural_image_to_3d),
        ("generativ audio", test_audio),
        ("hayot sikli (ekotizim)", test_lifecycle),
        ("real-vaqt tahrir", test_edit),
        ("glTF eksport", test_gltf_export),
        ("izometrik render", test_iso_render),
        ("tortishish (erkin tushish)", test_gravity_freefall),
        ("relyefda cho'kish", test_settle_on_terrain),
        ("tunnel yo'q", test_no_tunneling),
        ("qaytish energiyasi", test_restitution_energy_loss),
        ("suvда suzish/cho'kish", test_buoyancy),
        ("suv oqimi", test_water_flow),
        ("shamol", test_wind_light_vs_heavy),
        ("character tushadi", test_character_falls_and_lands),
        ("character yuradi", test_character_walks_terrain),
        ("character qiyalik chegarasi", test_character_slope_limit),
    ]
    for title, fn in tests:
        print(f"[{title}]")
        fn()
        print()

    print(f"Natija: {_passed} o'tdi, {_failed} yiqildi")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
