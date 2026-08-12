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

from worldclaw import generate_world, render_world_png, summary
from worldclaw.pipeline import WorldCache

_SAMPLES = [
    "qorli qishloq, ikki yonida baland tog'lar",
    "cho'l — qum barxanlari va kaktuslar",
    "tropik orol, dengiz va palma daraxtlari",
    "chuqur kanyon va qizil jarliklar",
    "vulqon, lava va qora toshlar",
    "yashil vodiy, o'rmon va uylar",
]


def _run_one(prompt: str, out_dir: str, cache: WorldCache, *, size: int) -> str:
    result = generate_world(prompt, size=size, cache=cache)
    print(summary(result))
    slug = result.plan.terrain.biome
    path = os.path.join(out_dir, f"world_{slug}.png")
    w, h = render_world_png(result, path, upscale=3)
    print(f"  -> yozildi: {path}  ({w}x{h})\n")
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="WorldClaw Mobil referens demo")
    ap.add_argument("prompt", nargs="?", help="matnli tavsif")
    ap.add_argument("--all", action="store_true", help="barcha namuna biomlar")
    ap.add_argument("--out", default="_out", help="chiqish papkasi")
    ap.add_argument("--size", type=int, default=192, help="heightmap qirrasi")
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    cache = WorldCache()

    if args.all:
        for prompt in _SAMPLES:
            _run_one(prompt, args.out, cache, size=args.size)
        return 0

    if not args.prompt:
        ap.print_help()
        return 2

    _run_one(args.prompt, args.out, cache, size=args.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
