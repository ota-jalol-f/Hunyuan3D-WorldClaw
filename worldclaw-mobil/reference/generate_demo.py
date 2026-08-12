#!/usr/bin/env python3
"""Demo: promptdan dunyo qurib, yuqoridan ko'rinish PNGini chiqaradi.

Ishlatish:
    python3 generate_demo.py "qorli qishloq, ikki yonida tog'lar"
    python3 generate_demo.py --all        # barcha biomlar uchun namuna
    python3 generate_demo.py --out ./_out "sahro karvon yo'li"
"""

from __future__ import annotations

import argparse
import os
import sys

from worldclaw import generate_world, refine, render_world_png, summary
from worldclaw.channels import write_channels
from worldclaw.gltf import export_glb
from worldclaw.iso import render_iso
from worldclaw.pipeline import WorldCache
from worldclaw.pngwriter import write_rgb_png
from worldclaw.refine import format_history
from worldclaw.texture import write_materials

_SAMPLES = [
    "qorli qishloq, ikki yonida baland tog'lar",
    "cho'l — qum barxanlari va kaktuslar",
    "tropik orol, dengiz va palma daraxtlari",
    "chuqur kanyon va qizil jarliklar",
    "vulqon, lava va qora toshlar",
    "yashil vodiy, o'rmon va uylar",
]


def _run_one(prompt: str, out_dir: str, cache: WorldCache, *, size: int,
             do_refine: bool = False, do_channels: bool = False,
             do_glb: bool = False, do_iso: bool = False) -> str:
    if do_refine:
        rr = refine(prompt, size=size)
        result = rr.world
        print(format_history(rr))
    else:
        result = generate_world(prompt, size=size, cache=cache)
        print(summary(result))

    slug = result.plan.terrain.biome
    path = os.path.join(out_dir, f"world_{slug}.png")
    w, h = render_world_png(result, path, upscale=3)
    print(f"  -> yozildi: {path}  ({w}x{h})")

    if do_channels:
        ch = write_channels(result.heightmap, result.placements, os.path.join(out_dir, slug), upscale=3)
        tx = write_materials(slug, os.path.join(out_dir, f"tex_{slug}"), seed=result.plan.terrain.seed)
        print(f"  -> kanallar: {[os.path.basename(c) for c in ch]}")
        print(f"  -> teksturalar: {[os.path.basename(t) for t in tx]}")

    if do_glb:
        glb_path = os.path.join(out_dir, f"world_{slug}.glb")
        stats = export_glb(result, glb_path, terrain_stride=2)
        print(f"  -> glTF: {os.path.basename(glb_path)}  ({stats['bytes'] // 1024} KB, "
              f"{stats['nodes']} tugun) — istalgan 3D ko'ruvchida oching")

    if do_iso:
        iso_path = os.path.join(out_dir, f"iso_{slug}.png")
        w, h, px = render_iso(result.heightmap, result.placements, width=760)
        write_rgb_png(iso_path, w, h, px)
        print(f"  -> izometrik 3D: {os.path.basename(iso_path)}  ({w}x{h})")
    print()
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="WorldClaw Mobil referens demo")
    ap.add_argument("prompt", nargs="?", help="matnli tavsif")
    ap.add_argument("--all", action="store_true", help="barcha namuna biomlar")
    ap.add_argument("--out", default="_out", help="chiqish papkasi")
    ap.add_argument("--size", type=int, default=192, help="heightmap qirrasi")
    ap.add_argument("--refine", action="store_true", help="Faza 2 agentli sifat sikli")
    ap.add_argument("--channels", action="store_true", help="depth/normal/instance + teksturalar")
    ap.add_argument("--glb", action="store_true", help="Faza 3: .glb 3D fayl eksport")
    ap.add_argument("--iso", action="store_true", help="Faza 3: izometrik 3D preview PNG")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    cache = WorldCache()

    if args.all:
        for prompt in _SAMPLES:
            _run_one(prompt, args.out, cache, size=args.size,
                     do_refine=args.refine, do_channels=args.channels,
                     do_glb=args.glb, do_iso=args.iso)
        return 0

    if not args.prompt:
        ap.print_help()
        return 2

    _run_one(args.prompt, args.out, cache, size=args.size,
             do_refine=args.refine, do_channels=args.channels,
             do_glb=args.glb, do_iso=args.iso)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
