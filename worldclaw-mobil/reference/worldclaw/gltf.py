"""glTF (GLB) eksport — dunyoni haqiqiy 3D fayl qilib chiqaradi.

Chiqish .glb ni istalgan 3D ko'ruvchida ochish mumkin (Blender, brauzer,
telefon, Windows 3D Viewer). Faqat stdlib (struct, json).

Tarkib: relyef mesh (hisoblangan normal bilan) + obyektlar (tur bo'yicha bitta
bazaviy mesh, har nusxa alohida tugun sifatida). Obyektlar soni cheklansa,
konsolda ogohlantiradi (jimgina qisqartirmaydi).

Qurilmada Godot buni o'rnatilgan `GLTFDocument` bilan qiladi (bir necha qator);
bu referens platformalararo tekshirish uchun.
"""

from __future__ import annotations

import json
import struct

from .pipeline import WorldResult

# Obyekt turi -> bazaviy shakl va rang.
_KIND_SHAPE = {
    "tree": "cone", "palm": "cone", "cactus": "cone", "torch": "cone",
    "house": "box", "fence": "box", "rock": "octa",
}
_KIND_COLOR = {
    "tree": (0.16, 0.42, 0.20), "palm": (0.14, 0.52, 0.32),
    "cactus": (0.20, 0.55, 0.30), "torch": (0.95, 0.66, 0.16),
    "house": (0.78, 0.28, 0.20), "fence": (0.55, 0.40, 0.22),
    "rock": (0.45, 0.45, 0.48),
}
_BIOME_COLOR = {
    "snow": (0.85, 0.88, 0.92), "desert": (0.80, 0.66, 0.42),
    "island": (0.35, 0.55, 0.35), "canyon": (0.66, 0.40, 0.28),
    "volcano": (0.28, 0.20, 0.20), "grass": (0.40, 0.55, 0.35),
}


def _normalize(x, y, z):
    m = (x * x + y * y + z * z) ** 0.5 or 1.0
    return x / m, y / m, z / m


# --- Bazaviy shakllar (past-poli) --------------------------------------------

def _box():
    v = [
        (-.5, 0, -.5), (.5, 0, -.5), (.5, 1, -.5), (-.5, 1, -.5),
        (-.5, 0, .5), (.5, 0, .5), (.5, 1, .5), (-.5, 1, .5),
    ]
    faces = [
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1), (3, 2, 6), (3, 6, 7),
        (1, 5, 6), (1, 6, 2), (0, 3, 7), (0, 7, 4),
    ]
    return _flat(v, faces)


def _cone(segments=8):
    v = [(0, 1, 0)]  # cho'qqi
    for i in range(segments):
        a = 6.2831853 * i / segments
        v.append((0.5 * __import_cos(a), 0.0, 0.5 * __import_sin(a)))
    faces = []
    for i in range(segments):
        faces.append((0, 1 + i, 1 + (i + 1) % segments))
    # tag
    base_center = len(v)
    v.append((0, 0, 0))
    for i in range(segments):
        faces.append((base_center, 1 + (i + 1) % segments, 1 + i))
    return _flat(v, faces)


def _octa():
    v = [(0, 1, 0), (0.5, 0.5, 0), (0, 0.5, 0.5), (-0.5, 0.5, 0), (0, 0.5, -0.5), (0, 0, 0)]
    faces = [
        (0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
        (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4),
    ]
    return _flat(v, faces)


def __import_cos(a):
    import math
    return math.cos(a)


def __import_sin(a):
    import math
    return math.sin(a)


def _flat(verts, faces):
    """Yassi-soyali geometriya: har uchburchak o'z uchlariga ega."""
    positions, normals, indices = [], [], []
    for (a, b, c) in faces:
        pa, pb, pc = verts[a], verts[b], verts[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        nx, ny, nz = _normalize(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        base = len(positions)
        for p in (pa, pb, pc):
            positions.append(p)
            normals.append((nx, ny, nz))
        indices += [base, base + 1, base + 2]
    return positions, normals, indices


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
    import math
    return [0.0, math.sin(yaw * 0.5), 0.0, math.cos(yaw * 0.5)]


def export_glb(result: WorldResult, path: str, *, max_objects: int = 4000, terrain_stride: int = 1) -> dict:
    """WorldResult'ni .glb fayl qilib yozadi. Statistika qaytaradi."""
    b = _Builder()
    meshes, materials, nodes = [], [], []

    # Material yordamchisi.
    def add_material(color):
        materials.append({
            "pbrMetallicRoughness": {
                "baseColorFactor": [color[0], color[1], color[2], 1.0],
                "metallicFactor": 0.0, "roughnessFactor": 0.9,
            },
            "name": "mat_%d" % len(materials),
        })
        return len(materials) - 1

    def add_mesh(geo, mat):
        pos, nrm, idx = geo
        pa = b.add_vec3(pos)
        na = b.add_vec3(nrm)
        ia = b.add_indices(idx)
        meshes.append({"primitives": [{
            "attributes": {"POSITION": pa, "NORMAL": na}, "indices": ia, "material": mat,
        }]})
        return len(meshes) - 1

    # 1) Relyef.
    biome = result.plan.terrain.biome
    terrain_mat = add_material(_BIOME_COLOR.get(biome, (0.4, 0.5, 0.35)))
    terrain_mesh = add_mesh(_terrain_mesh(result, terrain_stride), terrain_mat)
    nodes.append({"mesh": terrain_mesh, "name": "terrain"})

    # 2) Obyekt bazaviy meshlari (tur bo'yicha, faqat kerak bo'lganda).
    shape_fns = {"box": _box, "cone": _cone, "octa": _octa}
    kind_mesh: dict[str, int] = {}
    for kind in set(p.kind for p in result.placements):
        shape = _KIND_SHAPE.get(kind, "box")
        mat = add_material(_KIND_COLOR.get(kind, (0.6, 0.6, 0.6)))
        kind_mesh[kind] = add_mesh(shape_fns[shape](), mat)

    # 3) Obyekt nusxalari (tugun sifatida). Cheklov bo'lsa ogohlantiramiz.
    placements = result.placements
    truncated = 0
    if len(placements) > max_objects:
        truncated = len(placements) - max_objects
        placements = placements[:max_objects]

    for p in placements:
        base_scale = 3.0 * p.scale  # bazaviy shakllar ~1 birlik balandlikда
        nodes.append({
            "mesh": kind_mesh[p.kind],
            "translation": [p.x, p.y, p.z],
            "rotation": _quat_yaw(p.yaw),
            "scale": [base_scale, base_scale, base_scale],
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
        f.write(struct.pack("<III", 0x46546C67, 2, total))          # magic "glTF", ver 2
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))     # "JSON"
        f.write(json_bytes)
        f.write(struct.pack("<II", len(bin_bytes), 0x004E4942))      # "BIN\0"
        f.write(bin_bytes)


def _file_size_bytes(gltf: dict, bin_data: bytearray) -> int:
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    pad = (4 - len(json_bytes) % 4) % 4
    return 12 + 8 + len(json_bytes) + pad + 8 + len(bin_data)
