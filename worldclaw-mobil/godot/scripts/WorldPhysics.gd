extends RefCounted
class_name WorldPhysics
## Faza 3 — Yer fizikasi (Godot fizika serveri / Jolt).
##
## Referens `physics.py` bilan bir xil Yer parametrlari (tortishish 9.81,
## material ishqalanish/qaytish). Relyef uchun HeightMapShape3D to'qnashuvi,
## dinamik obyektlar (masalan toshlar) uchun RigidBody3D.
##
## Tortishish loyiha sozlamasida: [physics] default_gravity = 9.81.

# Material -> (ishqalanish, qaytish) — physics.py bilan mos.
const PHYS_MAT := {
	"rock": [0.6, 0.35], "house": [0.9, 0.05], "tree": [0.8, 0.1],
	"palm": [0.8, 0.1], "cactus": [0.7, 0.15], "torch": [0.7, 0.1], "fence": [0.8, 0.1],
}
const DENSITY := {
	"rock": 2700.0, "house": 800.0, "tree": 700.0, "palm": 650.0,
	"cactus": 500.0, "torch": 600.0, "fence": 650.0,
}


## Relyef balandlik xaritasidan statik to'qnashuv jismini quradi.
static func build_terrain_body(heights: PackedFloat32Array, spec: Dictionary) -> StaticBody3D:
	var size: int = spec.size
	var hs: float = spec.get("height_scale", 60.0)
	var world_scale: float = spec.get("world_scale", 400.0)

	var data := PackedFloat32Array()
	data.resize(size * size)
	for i in size * size:
		data[i] = heights[i] * hs           # normallashgan -> dunyo balandligi

	var shape := HeightMapShape3D.new()
	shape.map_width = size
	shape.map_depth = size
	shape.map_data = data

	var col := CollisionShape3D.new()
	col.shape = shape

	var body := StaticBody3D.new()
	body.name = "TerrainBody"
	var mat := PhysicsMaterial.new()
	mat.friction = 0.9
	mat.bounce = 0.0
	body.physics_material_override = mat
	body.add_child(col)

	# Panjara qadamini dunyo o'lchamiga keltirish (markazlashgan).
	var cell := world_scale / float(size)
	body.scale = Vector3(cell, 1.0, cell)
	return body


## Berilgan turdan bir necha dinamik (tushib/dumalab tushadigan) jism yaratadi.
static func spawn_dynamic(placements: Array, kind: String = "rock", limit: int = 40,
						  drop: float = 18.0) -> Array[RigidBody3D]:
	var out: Array[RigidBody3D] = []
	var n := 0
	for p: Dictionary in placements:
		if p.kind != kind:
			continue
		if n >= limit:
			break
		n += 1
		var sc: float = 3.0 * (0.75 + 0.5 * (n % 3) / 3.0)
		var radius := 3.5 * sc / 3.0

		var rb := RigidBody3D.new()
		rb.name = "dyn_%s_%d" % [kind, n]
		# Massa = zichlik × hajm (Yer-realistik).
		var vol := (4.0 / 3.0) * PI * pow(radius, 3)
		rb.mass = DENSITY.get(kind, 1500.0) * vol / 1000.0   # tonna -> boshqariladigan
		var mp: Array = PHYS_MAT.get(kind, [0.6, 0.2])
		var mat := PhysicsMaterial.new()
		mat.friction = mp[0]
		mat.bounce = mp[1]
		rb.physics_material_override = mat

		var mi := MeshInstance3D.new()
		mi.mesh = MeshFactory.generate(kind, n * 131)
		mi.scale = Vector3(sc, sc, sc)
		rb.add_child(mi)

		var col := CollisionShape3D.new()
		var sph := SphereShape3D.new()
		sph.radius = radius
		col.shape = sph
		rb.add_child(col)

		rb.position = Vector3(p.wx, p.wy + drop, p.wz)   # tepadan tushadi
		out.append(rb)
	return out
