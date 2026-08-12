extends RefCounted
class_name MeshFactory
## Faza 3 — generativ obyekt meshlari (primitiv emas, haqiqiy shakllar).
##
## Referens `mesh.py` ning GDScript nusxasi: parametrik + seed variatsiyasi.
## Har mesh bir necha sirtдан iborat (masalan uy: devor + tom + eshik), har
## sirt o'z rangida.
##
## Ikki backend:
##   * PROCEDURAL (shu modul) — arzon, determinlashgan, on-device'ga qulay.
##   * NEURAL image-to-3D (NPU) — `neural_mesh` stub; kelajakda ulanadi.

const BASE_SIZE := 8.0   # birlik meshni dunyo o'lchamiga keltiradi (~8 birlik)
const TRUNK := Color(0.36, 0.26, 0.16)
const LEAF := Color(0.18, 0.44, 0.22)
const LEAF2 := Color(0.22, 0.52, 0.26)

static var _cache: Dictionary = {}   # "kind|seed" -> ArrayMesh


class _Rng:
	var state: int
	func _init(seed: int) -> void:
		state = (seed ^ 0x9E3779B1) & 0xFFFFFFFF
	func unit() -> float:
		state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
		return state / 4294967296.0
	func rng(lo: float, hi: float) -> float:
		return lo + (hi - lo) * unit()


## Tur uchun generativ mesh (keshlanadi). variant seed bilan farqlanadi.
static func generate(kind: String, seed: int = 0) -> ArrayMesh:
	var key := "%s|%d" % [kind, seed]
	if _cache.has(key):
		return _cache[key]
	# TODO(Faza 3+): NPU neural backend — mavjud bo'lsa shu yerда:
	#   var m := neural_mesh(kind, seed); if m: _cache[key]=m; return m
	var parts: Array = _parts_for(kind, _Rng.new(seed))
	var mesh := ArrayMesh.new()
	for part: Dictionary in parts:
		_add_surface(mesh, part.verts, part.faces, part.color)
	_cache[key] = mesh
	return mesh


## N variant — nusxalar orasida ulashiladi.
static func variants(kind: String, count: int = 4, seed: int = 0) -> Array:
	var out: Array = []
	for i in count:
		out.append(generate(kind, seed + i * 7919))
	return out


static func neural_mesh(_kind: String, _seed: int) -> ArrayMesh:
	return null   # Faza 3+ — NPU image-to-3D


# --- Sirt quruvchi (yassi soya) ----------------------------------------------

static func _add_surface(mesh: ArrayMesh, verts: Array, faces: Array, color: Color) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for f: Vector3i in faces:
		var a: Vector3 = verts[f.x] * BASE_SIZE
		var b: Vector3 = verts[f.y] * BASE_SIZE
		var c: Vector3 = verts[f.z] * BASE_SIZE
		var n := (b - a).cross(c - a).normalized()
		for p in [a, b, c]:
			st.set_normal(n)
			st.add_vertex(p)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.9
	st.set_material(mat)
	st.commit(mesh)


# --- Bazaviy shakllar --------------------------------------------------------

static func _cylinder(rb: float, rt: float, h: float, y0: float, seg: int, cx := 0.0, cz := 0.0) -> Dictionary:
	var verts: Array = []
	for i in seg:
		var a := TAU * i / seg
		verts.append(Vector3(cx + rb * cos(a), y0, cz + rb * sin(a)))
	for i in seg:
		var a := TAU * i / seg
		verts.append(Vector3(cx + rt * cos(a), y0 + h, cz + rt * sin(a)))
	var faces: Array = []
	for i in seg:
		var j := (i + 1) % seg
		faces.append(Vector3i(i, j, seg + i))
		faces.append(Vector3i(j, seg + j, seg + i))
	return {"verts": verts, "faces": faces}


static func _cone(r: float, h: float, y0: float, seg: int, cx := 0.0, cz := 0.0) -> Dictionary:
	var verts: Array = [Vector3(cx, y0 + h, cz)]
	for i in seg:
		var a := TAU * i / seg
		verts.append(Vector3(cx + r * cos(a), y0, cz + r * sin(a)))
	var faces: Array = []
	for i in seg:
		faces.append(Vector3i(0, 1 + i, 1 + (i + 1) % seg))
	return {"verts": verts, "faces": faces}


static func _box(w: float, h: float, d: float, cx: float, y0: float, cz: float) -> Dictionary:
	var x0 := cx - w / 2; var x1 := cx + w / 2
	var z0 := cz - d / 2; var z1 := cz + d / 2
	var y1 := y0 + h
	var verts := [
		Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y1, z0), Vector3(x0, y1, z0),
		Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x0, y1, z1)]
	var faces := [
		Vector3i(0, 1, 2), Vector3i(0, 2, 3), Vector3i(4, 6, 5), Vector3i(4, 7, 6),
		Vector3i(0, 4, 5), Vector3i(0, 5, 1), Vector3i(3, 2, 6), Vector3i(3, 6, 7),
		Vector3i(1, 5, 6), Vector3i(1, 6, 2), Vector3i(0, 3, 7), Vector3i(0, 7, 4)]
	return {"verts": verts, "faces": faces}


static func _prism_roof(w: float, h: float, d: float, cx: float, y0: float, cz: float) -> Dictionary:
	var x0 := cx - w / 2; var x1 := cx + w / 2
	var z0 := cz - d / 2; var z1 := cz + d / 2
	var verts := [
		Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(x0, y0, z1),
		Vector3(cx, y0 + h, z0), Vector3(cx, y0 + h, z1)]
	var faces := [
		Vector3i(0, 1, 4), Vector3i(1, 2, 5), Vector3i(1, 5, 4), Vector3i(2, 3, 5),
		Vector3i(3, 0, 4), Vector3i(3, 4, 5), Vector3i(0, 3, 1), Vector3i(1, 3, 2)]
	return {"verts": verts, "faces": faces}


static func _rock_solid(r: float, rng: _Rng) -> Dictionary:
	var base := [Vector3(0, r, 0), Vector3(r, 0, 0), Vector3(0, 0, r),
		Vector3(-r, 0, 0), Vector3(0, 0, -r), Vector3(0, -r * 0.5, 0)]
	var verts: Array = []
	for v: Vector3 in base:
		var k := rng.rng(0.75, 1.25)
		verts.append(Vector3(v.x * k, max(0.0, v.y * k + r * 0.5), v.z * k))
	var faces := [
		Vector3i(0, 1, 2), Vector3i(0, 2, 3), Vector3i(0, 3, 4), Vector3i(0, 4, 1),
		Vector3i(5, 2, 1), Vector3i(5, 3, 2), Vector3i(5, 4, 3), Vector3i(5, 1, 4)]
	return {"verts": verts, "faces": faces}


# --- Generatorlar ------------------------------------------------------------

static func _parts_for(kind: String, r: _Rng) -> Array:
	match kind:
		"tree": return _tree(r)
		"palm": return _palm(r)
		"house": return _house(r)
		"cactus": return _cactus(r)
		"torch": return _torch(r)
		"fence": return _fence(r)
		_: return _rock(r)


static func _tree(r: _Rng) -> Array:
	var trunk_h := r.rng(0.28, 0.42)
	var parts := [_with(_cylinder(0.06, 0.045, trunk_h, 0.0, 5), TRUNK)]
	var tiers := 2 + int(r.unit() * 2)
	var y := trunk_h * 0.75
	var rad := r.rng(0.26, 0.34)
	for t in tiers:
		parts.append(_with(_cone(rad, rad * 1.5, y, 6), LEAF if t % 2 == 0 else LEAF2))
		y += rad * 0.85
		rad *= 0.72
	return parts


static func _palm(r: _Rng) -> Array:
	var h := r.rng(0.7, 1.0)
	var lean := r.rng(-0.06, 0.06)
	var parts := [_with(_cylinder(0.05, 0.035, h, 0.0, 5, lean * 0.5, lean), Color(0.42, 0.32, 0.18))]
	var fronds := 5 + int(r.unit() * 3)
	for i in fronds:
		var a := TAU * i / fronds
		var tip := Vector3(lean + 0.34 * cos(a), h - 0.06, lean + 0.34 * sin(a))
		var l := Vector3(lean + 0.05 * cos(a + 1.5), h, lean + 0.05 * sin(a + 1.5))
		var rr := Vector3(lean + 0.05 * cos(a - 1.5), h, lean + 0.05 * sin(a - 1.5))
		parts.append({"verts": [l, rr, tip], "faces": [Vector3i(0, 1, 2)], "color": Color(0.20, 0.50, 0.28)})
	return parts


static func _house(r: _Rng) -> Array:
	var w := r.rng(0.5, 0.7); var h := r.rng(0.32, 0.44); var d := r.rng(0.5, 0.7)
	var wall := Color(r.rng(0.60, 0.80), r.rng(0.45, 0.60), r.rng(0.35, 0.45))
	var roof := Color(r.rng(0.55, 0.75), r.rng(0.20, 0.30), r.rng(0.18, 0.24))
	return [
		_with(_box(w, h, d, 0, 0, 0), wall),
		_with(_prism_roof(w * 1.08, r.rng(0.18, 0.26), d * 1.08, 0, h, 0), roof),
		_with(_box(w * 0.22, h * 0.55, 0.02, 0, 0, d / 2), Color(0.25, 0.16, 0.10)),
	]


static func _rock(r: _Rng) -> Array:
	var s := r.rng(0.40, 0.52)
	return [_with(_rock_solid(r.rng(0.18, 0.30), r), Color(s, s, s * 1.05))]


static func _cactus(r: _Rng) -> Array:
	var col := Color(0.20, 0.48, 0.28)
	var h := r.rng(0.45, 0.7)
	var parts := [_with(_cylinder(0.08, 0.07, h, 0.0, 6), col)]
	var arms := int(r.unit() * 3)
	for i in arms:
		var side := 1.0 if i % 2 == 0 else -1.0
		var y := r.rng(0.2, 0.4)
		parts.append(_with(_cylinder(0.05, 0.045, 0.12, y, 5, side * 0.09), col))
		parts.append(_with(_cylinder(0.05, 0.04, r.rng(0.12, 0.2), y + 0.1, 5, side * 0.14), col))
	return parts


static func _torch(r: _Rng) -> Array:
	var h := r.rng(0.4, 0.55)
	return [
		_with(_cylinder(0.03, 0.03, h, 0.0, 4), Color(0.35, 0.25, 0.15)),
		_with(_cone(0.08, 0.16, h, 5), Color(0.98, 0.62, 0.15)),
	]


static func _fence(r: _Rng) -> Array:
	var col := Color(0.52, 0.38, 0.22)
	var parts: Array = []
	for i in 2:
		parts.append(_with(_box(0.05, r.rng(0.28, 0.36), 0.05, -0.18 + i * 0.36, 0, 0), col))
	parts.append(_with(_box(0.42, 0.05, 0.03, 0, 0.22, 0), col))
	parts.append(_with(_box(0.42, 0.05, 0.03, 0, 0.12, 0), col))
	return parts


static func _with(shape: Dictionary, color: Color) -> Dictionary:
	shape["color"] = color
	return shape
