"""Generativ teksturalar — biomga xos material sirtlari (albedo).

MUHIM: teksturalar assetdan olinmaydi — generatsiya qilinadi. Qurilmada bu
NPU'да (LiteRT + QNN) diffusion modeli bilan bo'ladi. Bu referens esa
determinlashgan protsedura noise'idan foydalanadi (testlanadi, kutubxonasiz).
Ikkalasi ham bir xil rolni bajaradi: sirt saqlanmaydi, generatsiya qilinadi.
"""

from __future__ import annotations

from .noise import ValueNoise, fbm

# Material -> (asosiy rang, tomir rang, dog' zichligi).
_MATERIALS = {
    "snow":   ((238, 244, 252), (205, 218, 236), 0.10),
    "rock":   ((120, 118, 122), (78, 74, 80),   0.55),
    "sand":   ((214, 182, 120), (188, 150, 92),  0.30),
    "grass":  ((92, 140, 74),  (60, 104, 52),   0.45),
    "lava":   ((60, 30, 28),   (210, 90, 40),   0.60),
    "bark":   ((96, 70, 48),   (66, 46, 30),    0.50),
}


def _mix(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def generate_material(material: str, *, size: int = 128, seed: int = 0) -> tuple[int, int, bytearray]:
    """Bitta material uchun albedo teksturasi (RGB buffer) generatsiya qiladi."""
    base, vein, spots = _MATERIALS.get(material, _MATERIALS["rock"])
    n1 = ValueNoise(seed)
    n2 = ValueNoise(seed ^ 0x1234ABCD)
    px = bytearray(size * size * 3)
    freq = 6.0
    for y in range(size):
        for x in range(size):
            u = x / size
            v = y / size
            # Ikki qatlam: yirik tomir + mayda dog'.
            large = fbm(n1, u * freq, v * freq, octaves=4) * 0.5 + 0.5
            fine = fbm(n2, u * freq * 4.0, v * freq * 4.0, octaves=3) * 0.5 + 0.5
            t = large * (1.0 - spots) + fine * spots
            rgb = _mix(base, vein, t)
            i = (y * size + x) * 3
            px[i], px[i + 1], px[i + 2] = rgb
    return size, size, px


# Biom -> shu biomда generatsiya qilinadigan materiallar.
BIOME_MATERIALS = {
    "snow": ["snow", "rock", "bark"],
    "desert": ["sand", "rock"],
    "island": ["sand", "grass", "bark"],
    "canyon": ["rock", "sand"],
    "volcano": ["lava", "rock"],
    "grass": ["grass", "rock", "bark"],
}


def generate_biome_set(biome: str, *, size: int = 128, seed: int = 0) -> dict[str, tuple[int, int, bytearray]]:
    """Biom uchun barcha material teksturalarini generatsiya qiladi."""
    out: dict[str, tuple[int, int, bytearray]] = {}
    for i, mat in enumerate(BIOME_MATERIALS.get(biome, ["rock"])):
        out[mat] = generate_material(mat, size=size, seed=seed + i * 101)
    return out


def write_materials(biome: str, prefix: str, *, size: int = 128, seed: int = 0) -> list[str]:
    from .pngwriter import write_rgb_png

    paths: list[str] = []
    for mat, (w, h, buf) in generate_biome_set(biome, size=size, seed=seed).items():
        path = f"{prefix}_{mat}.png"
        write_rgb_png(path, w, h, buf)
        paths.append(path)
    return paths
