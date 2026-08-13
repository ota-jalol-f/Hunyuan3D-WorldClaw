"""Image-to-3D — rasmdan 3D mesh (WorldClaw'ning generativ mesh yadrosi).

IKKI backend:
  * NEURAL (qurilmada) — NPU'да distillangan/kvantlangan model (Hunyuan3D/TripoSR
    uslubida): obyekt rasmi -> mesh. Katta model, NPU R&D. `_neural_infer` stub.
  * CLASSICAL (shu modul, verifikatsiya qilinadi) — visual hull rekonstruksiyasi:
    rasm(lar) -> siluet -> voksel(ovosti) -> mesh. Neyron model shu pipeline'ni
    o'rgangan; bu esa uning tekshiriladigan, og'irliksiz o'rnini bosuvchisi.

Oqim: obyekt tasviri (bu yerда procedural meshdan rasterlanadi; qurilmada
diffusion yoki sahna renderидан keladi) -> 3 ortogonal siluet -> visual hull
voksel panjarasi -> chegara yuzalari meshi.
"""

from __future__ import annotations

from .mesh import Part, generate

RES = 30   # voksel panjarasi qirrasi

_KIND_COLOR = {
    "tree": (0.20, 0.46, 0.24), "palm": (0.18, 0.50, 0.30),
    "house": (0.72, 0.40, 0.30), "rock": (0.46, 0.46, 0.49),
    "cactus": (0.22, 0.50, 0.30), "torch": (0.55, 0.40, 0.22),
    "fence": (0.52, 0.38, 0.22),
}


def _bbox(parts: list[Part]):
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for p in parts:
        for (x, y, z) in p.positions:
            lo[0] = min(lo[0], x); lo[1] = min(lo[1], y); lo[2] = min(lo[2], z)
            hi[0] = max(hi[0], x); hi[1] = max(hi[1], y); hi[2] = max(hi[2], z)
    # kichik marja
    for i in range(3):
        d = (hi[i] - lo[i]) * 0.05 + 1e-4
        lo[i] -= d; hi[i] += d
    return lo, hi


def _fill_tri(mask: list[bytearray], res: int, a, b, c) -> None:
    """2D siluet niqobiga uchburchak (u,v [0,res)) to'ldiradi."""
    minx = max(0, int(min(a[0], b[0], c[0])))
    maxx = min(res - 1, int(max(a[0], b[0], c[0]) + 1))
    miny = max(0, int(min(a[1], b[1], c[1])))
    maxy = min(res - 1, int(max(a[1], b[1], c[1]) + 1))
    area = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
    if abs(area) < 1e-9:
        return
    inv = 1.0 / area
    for py in range(miny, maxy + 1):
        for px in range(minx, maxx + 1):
            w0 = ((b[0] - px) * (c[1] - py) - (c[0] - px) * (b[1] - py)) * inv
            w1 = ((c[0] - px) * (a[1] - py) - (a[0] - px) * (c[1] - py)) * inv
            w2 = 1.0 - w0 - w1
            if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                mask[py][px] = 1


def render_silhouettes(parts: list[Part], res: int = RES):
    """Meshdan 3 ortogonal siluet niqobi (front XY, side ZY, top XZ)."""
    lo, hi = _bbox(parts)
    sx = (res - 1) / (hi[0] - lo[0])
    sy = (res - 1) / (hi[1] - lo[1])
    sz = (res - 1) / (hi[2] - lo[2])
    front = [bytearray(res) for _ in range(res)]   # (y, x)
    side = [bytearray(res) for _ in range(res)]    # (y, z)
    top = [bytearray(res) for _ in range(res)]     # (z, x)

    def U(v, lo_, s): return (v - lo_) * s

    for p in parts:
        pos, idx = p.positions, p.indices
        for t in range(0, len(idx), 3):
            v0 = pos[idx[t]]; v1 = pos[idx[t + 1]]; v2 = pos[idx[t + 2]]
            fx = [(U(v[0], lo[0], sx), U(v[1], lo[1], sy)) for v in (v0, v1, v2)]
            sd = [(U(v[2], lo[2], sz), U(v[1], lo[1], sy)) for v in (v0, v1, v2)]
            tp = [(U(v[0], lo[0], sx), U(v[2], lo[2], sz)) for v in (v0, v1, v2)]
            _fill_tri(front, res, *fx)
            _fill_tri(side, res, *sd)
            _fill_tri(top, res, *tp)
    return {"front": front, "side": side, "top": top, "bbox": (lo, hi)}


def visual_hull(masks, res: int = RES):
    """3 siluetdan voksel egallanish panjarasi (visual hull)."""
    front, side, top = masks["front"], masks["side"], masks["top"]
    grid = [[[False] * res for _ in range(res)] for _ in range(res)]  # [x][y][z]
    for x in range(res):
        for y in range(res):
            if not front[y][x]:
                continue
            for z in range(res):
                if side[y][z] and top[z][x]:
                    grid[x][y][z] = True
    return grid


def _occ(grid, res, x, y, z):
    return 0 <= x < res and 0 <= y < res and 0 <= z < res and grid[x][y][z]


def voxels_to_parts(grid, res, bbox, color) -> list[Part]:
    """Egallangan vokselларning chegara yuzalarini meshга aylantiradi."""
    lo, hi = bbox
    cell = [(hi[i] - lo[i]) / res for i in range(3)]
    positions, normals, indices = [], [], []
    faces = [
        ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
        ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
        ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
        ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
        ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
        ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ]
    for x in range(res):
        for y in range(res):
            for z in range(res):
                if not grid[x][y][z]:
                    continue
                for (nrm, quad) in faces:
                    if _occ(grid, res, x + nrm[0], y + nrm[1], z + nrm[2]):
                        continue
                    wq = []
                    for (dx, dy, dz) in quad:
                        wq.append((lo[0] + (x + dx) * cell[0],
                                   lo[1] + (y + dy) * cell[1],
                                   lo[2] + (z + dz) * cell[2]))
                    base = len(positions)
                    for w in wq:
                        positions.append(w)
                        normals.append((float(nrm[0]), float(nrm[1]), float(nrm[2])))
                    indices += [base, base + 1, base + 2, base, base + 2, base + 3]
    return [Part(positions, normals, indices, color)]


def _neural_infer(image, kind: str, seed: int):
    """NPU distillangan image-to-3D modeli (Faza 3+). Hozircha None."""
    return None   # TODO: LiteRT/QNN model -> mesh


def neural_mesh(kind: str, seed: int = 0, image=None, res: int = RES) -> list[Part] | None:
    """Image-to-3D: obyekt tasviridan mesh.

    Avval NPU neyron model (agar bo'lsa), aks holda visual hull rekonstruksiyasi.
    `image` berilmasa, procedural meshdan siluet olinadi (qurilmada bu diffusion
    yoki sahna renderidan keladi).
    """
    m = _neural_infer(image, kind, seed)
    if m is not None:
        return m
    source = generate(kind, seed)                 # "kirish tasviri" manbasi
    masks = render_silhouettes(source, res)
    grid = visual_hull(masks, res)
    color = _KIND_COLOR.get(kind, (0.5, 0.5, 0.5))
    return voxels_to_parts(grid, res, masks["bbox"], color)


def silhouette_iou(mask_a, mask_b, res: int) -> float:
    """Ikki niqob orasidagi IoU — rekonstruksiya sifatini tekshirish uchun."""
    inter = union = 0
    for y in range(res):
        for x in range(res):
            a = mask_a[y][x]; b = mask_b[y][x]
            if a or b:
                union += 1
                if a and b:
                    inter += 1
    return inter / union if union else 1.0
