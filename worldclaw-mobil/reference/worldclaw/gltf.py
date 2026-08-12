"""glTF (GLB) eksport — dunyoni haqiqiy 3D fayl qilib chiqaradi.

Chiqish .glb ni istalgan 3D ko'ruvchida ochish mumkin (Blender, brauzer,
telefon, Windows 3D Viewer). Faqat stdlib (struct, json).

Tarkib: relyef mesh (hisoblangan normal bilan) + generativ obyekt meshlari
(`mesh.py` dan; tur bo'yicha bir necha variant ulashiladi). Obyektlar soni
cheklansa, konsolda ogohlantiradi (jimgina qisqartirmaydi).

Qurilmada Godot buni o'rnatilgan `GLTFDocument` bilan qiladi; bu referens
platformalararo tekshirish uchun.
"""

from __future__ import annotations

import json
import math
import struct

from .mesh import Part, variants
from .pipeline import WorldResult

_BIOME_COLOR = {
    "snow": (0.85, 0.88, 0.92), "desert": (0.80, 0.66, 0.42),
    "island": (0.35, 0.55, 0.35), "canyon": (0.66, 0.40, 0.28),
    "volcano": (0.28, 0.20, 0.20), "grass": (0.40, 0.55, 0.35),
}
_VARIANTS_PER_KIND = 4


def _normalize(x, y, z):
    m = (x * x + y * y + z * z) ** 0.5 or 1.0
    return x / m, y / m, z / m


# --- Relyef mesh -------------------------------------------------------------

def _terrain_mesh(result: WorldResult, stride: int):
    hm = result.heightmap
    size = hm.size
    spec = hm.spec
    cell = spec.world_scale / size
    half = spec.world_scale * 0.5
    hs = spec.height_scale

    xs = list(range(0, size, stride))
    if xs[-1] != size - 1:
        xs.append(size - 1)
    idx_of = {}
    positions, normals = [], []
    for gy in xs:
        for gx in xs:
            idx_of[(gx, gy)] = len(positions)
            h = hm.get(gx, gy)
            positions.append((gx * cell - half, h * hs, gy * cell - half))
            dx = (hm.get(gx + 1, gy) - hm.get(gx - 1, gy)) * hs / (2 * cell)
            dy = (hm.get(gx, gy + 1) - hm.get(gx, gy - 1)) * hs / (2 * cell)
            normals.append(_normalize(-dx, 1.0, -dy))

    indices = []
    for j in range(len(xs) - 1):
        for i in range(len(xs) - 1):
            a = idx_of[(xs[i], xs[j])]
            b = idx_of[(xs[i + 1], xs[j])]
            c = idx_of[(xs[i], xs[j + 1])]
            d = idx_of[(xs[i + 1], xs[j + 1])]
            indices += [a, c, b, b, c, d]
    return positions, normals, indices


# --- GLB yig'ish -------------------------------------------------------------

class _Builder:
    def __init__(self):
        self.bin = bytearray()
        self.bufferViews = []
        self.accessors = []

    def _align(self):
        while len(self.bin) % 4:
            self.bin.append(0)

    def add_vec3(self, data):
        self._align()
        offset = len(self.bin)
        flat = []
        for v in data:
            flat.extend(v)
        self.bin += struct.pack("<%df" % len(flat), *flat)
        self.bufferViews.append({"buffer": 0, "byteOffset": offset, "byteLength": len(flat) * 4, "target": 34962})
        mins = [min(v[i] for v in data) for i in range(3)]
        maxs = [max(v[i] for v in data) for i in range(3)]
        self.accessors.append({
            "bufferView": len(self.bufferViews) - 1, "componentType": 5126,
            "count": len(data), "type": "VEC3", "min": mins, "max": maxs,
        })
        return len(self.accessors) - 1

    def add_indices(self, data):
        self._align()
        offset = len(self.bin)
        self.bin += struct.pack("<%dI" % len(data), *data)
        self.bufferViews.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data) * 4, "target": 34963})
        self.accessors.append({
            "bufferView": len(self.bufferViews) - 1, "componentType": 5125,
            "count": len(data), "type": "SCALAR",
        })
        return len(self.accessors) - 1


def _quat_yaw(yaw):
    return [0.0, math.sin(yaw * 0.5), 0.0, math.cos(yaw * 0.5)]


def export_glb(result: WorldResult, path: str, *, max_objects: int = 4000, terrain_stride: int = 1) -> dict:
    """WorldResult'ni .glb fayl qilib yozadi. Statistika qaytaradi."""
    b = _Builder()
    meshes, materials, nodes = [], [], []
    mat_cache: dict[tuple, int] = {}

    def material_for(color):
        key = tuple(round(c, 3) for c in color)
        if key in mat_cache:
            return mat_cache[key]
        materials.append({
            "pbrMetallicRoughness": {
                "baseColorFactor": [color[0], color[1], color[2], 1.0],
                "metallicFactor": 0.0, "roughnessFactor": 0.9,
            },
            "name": "mat_%d" % len(materials),
        })
        mat_cache[key] = len(materials) - 1
        return mat_cache[key]

    def mesh_from_geo(pos, nrm, idx, mat):
        pa = b.add_vec3(pos)
        na = b.add_vec3(nrm)
        ia = b.add_indices(idx)
        meshes.append({"primitives": [{
            "attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia, "material": mat,
        }]})
        return len(meshes) - 1

    def mesh_from_parts(parts: list[Part]):
        prims = []
        for p in parts:
            pa = b.add_vec3(p.positions)
            na = b.add_vec3(p.normals)
            ia = b.add_indices(p.indices)
            prims.append({"attributes": {"POSITION": pa, "NORMAL": na},
                          "indices": ia, "material": material_for(p.color)})
        meshes.append({"primitives": prims})
        return len(meshes) - 1

    # 1) Relyef.
    biome = result.plan.terrain.biome
    seed = result.plan.terrain.seed
    tm = material_for(_BIOME_COLOR.get(biome, (0.4, 0.5, 0.35)))
    pos, nrm, idx = _terrain_mesh(result, terrain_stride)
    nodes.append({"mesh": mesh_from_geo(pos, nrm, idx, tm), "name": "terrain"})

    # 2) Generativ obyekt meshlari — tur bo'yicha bir necha variant (ulashiladi).
    kind_variants: dict[str, list[int]] = {}
    for kind in sorted(set(p.kind for p in result.placements)):
        vs = variants(kind, count=_VARIANTS_PER_KIND, seed=seed)
        kind_variants[kind] = [mesh_from_parts(parts) for parts in vs]

    # 3) Obyekt nusxalari (tugun sifatida, variantга havola).
    placements = result.placements
    truncated = 0
    if len(placements) > max_objects:
        truncated = len(placements) - max_objects
        placements = placements[:max_objects]

    for i, p in enumerate(placements):
        vlist = kind_variants[p.kind]
        vidx = (hash((round(p.x, 2), round(p.z, 2))) & 0x7FFFFFFF) % len(vlist)
        s = 3.0 * p.scale
        nodes.append({
            "mesh": vlist[vidx],
            "translation": [p.x, p.y, p.z],
            "rotation": _quat_yaw(p.yaw),
            "scale": [s, s, s],
            "name": p.kind,
        })

    gltf = {
        "asset": {"version": "2.0", "generator": "WorldClaw Mobil"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": b.accessors,
        "bufferViews": b.bufferViews,
        "buffers": [{"byteLength": len(b.bin)}],
    }
    _write_glb(path, gltf, b.bin)

    if truncated:
        print(f"  DIQQAT: {truncated} obyekt eksportдан chiqarildi (max_objects={max_objects})")
    return {
        "path": path, "nodes": len(nodes), "meshes": len(meshes),
        "objects_exported": len(placements), "objects_truncated": truncated,
        "bytes": _file_size_bytes(gltf, b.bin),
    }


def _write_glb(path: str, gltf: dict, bin_data: bytearray) -> None:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4:
        json_bytes += b" "
    bin_bytes = bytes(bin_data)
    while len(bin_bytes) % 4:
        bin_bytes += b"\x00"
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
        f.write(bin_bytes)


def _file_size_bytes(gltf: dict, bin_data: bytearray) -> int:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    pad = (4 - len(json_bytes) % 4) % 4
    return 12 + 8 + len(json_bytes) + pad + 8 + len(bin_data)
