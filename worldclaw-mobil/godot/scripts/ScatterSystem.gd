extends Node3D
class_name ScatterSystem
## Obyektlarni relyefga qoidalar bo'yicha joylashtiradi (MultiMesh instancing).
##
## Joylashuv mantiqi referens `worldclaw/scatter.py` ning nusxasi. Har obyekt
## turi uchun bitta MultiMeshInstance3D — minglab nusxa bitta chizishda.

## kind -> yuklanadigan mesh sahnasi (asset kutubxonasi). Faza 1 da oddiy
## primitiv geometriya; keyin kutubxonadan almashtiriladi.
@export var asset_scenes: Dictionary = {}


class _Rng:
	var state: int
	func _init(seed: int) -> void:
		state = (seed ^ 0x27D4EB2F) & 0xFFFFFFFF
	func next_u32() -> int:
		state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
		return state
	func unit() -> float:
		return next_u32() / 4294967296.0


func clear() -> void:
	for child in get_children():
		child.queue_free()


## Mesh qurmasdan joylashuvlarni hisoblaydi (refine sikli uchun "quruq hisob").
## Har element: {kind, wx, wy, wz, height, xform}.  Referens scatter.py nusxasi.
static func compute_placements(plan: Dictionary, heights: PackedFloat32Array) -> Array:
	var spec: Dictionary = plan.get("terrain", {})
	var size: int = spec.get("size", 256)
	var world_scale: float = spec.get("world_scale", 400.0)
	var height_scale: float = spec.get("height_scale", 60.0)
	var water: float = spec.get("water_level", 0.28)
	var seed: int = spec.get("seed", 0)
	var cell := world_scale / float(size)

	var out: Array = []
	for rule: Dictionary in plan.get("scatter", []):
		var kind: String = rule.get("kind", "rock")
		var density: float = rule.get("density", 0.02)
		var min_h: float = rule.get("min_height", 0.0)
		var max_h: float = rule.get("max_height", 1.0)
		var max_slope: float = rule.get("max_slope", 1.0)
		var avoid_water: bool = rule.get("avoid_water", true)

		var rng := _Rng.new(seed ^ (hash(kind) & 0xFFFFFFFF))
		var step := maxi(1, int(round(pow(1.0 / maxf(density, 1e-4), 0.5))))
		var accept := minf(1.0, density * step * step)

		var gy := 0
		while gy < size:
			var gx := 0
			while gx < size:
				var jx := gx + rng.unit() * step
				var jy := gy + rng.unit() * step
				var ix := mini(size - 1, int(jx))
				var iy := mini(size - 1, int(jy))
				var h := heights[iy * size + ix]
				if not (avoid_water and h <= water) and h >= min_h and h <= max_h:
					if TerrainGenerator.slope_at(heights, size, ix, iy) <= max_slope:
						if rng.unit() <= accept:
							var wx := (jx - size * 0.5) * cell
							var wz := (jy - size * 0.5) * cell
							var wy := h * height_scale
							var sc := 0.75 + rng.unit() * 0.6
							var yaw := rng.unit() * TAU
							var basis := Basis(Vector3.UP, yaw).scaled(Vector3.ONE * sc)
							out.append({
								"kind": kind, "wx": wx, "wy": wy, "wz": wz,
								"height": h, "xform": Transform3D(basis, Vector3(wx, wy, wz)),
							})
				gx += step
			gy += step
	return out


## Tayyor joylashuvlardan MultiMesh instancelarini quradi (refine natijasi uchun).
func build_instances(placements: Array) -> int:
	clear()
	var by_kind: Dictionary = {}
	for p: Dictionary in placements:
		var k: String = p.kind
		if not by_kind.has(k):
			by_kind[k] = [] as Array[Transform3D]
		by_kind[k].append(p.xform)
	for kind: String in by_kind:
		_build_multimesh(kind, by_kind[kind])
	return placements.size()


## Qulaylik: rejadan hisoblab, darhol quradi.
func scatter(plan: Dictionary, heights: PackedFloat32Array) -> int:
	return build_instances(compute_placements(plan, heights))


func _build_multimesh(kind: String, xforms: Array[Transform3D]) -> void:
	if xforms.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = _mesh_for(kind)
	mm.instance_count = xforms.size()
	for i in xforms.size():
		mm.set_instance_transform(i, xforms[i])
	var inst := MultiMeshInstance3D.new()
	inst.name = "scatter_%s" % kind
	inst.multimesh = mm
	add_child(inst)


## Faza 1 primitivlari — asset kutubxonasi ulanmaguncha o'rin egallaydi.
func _mesh_for(kind: String) -> Mesh:
	if asset_scenes.has(kind):
		return asset_scenes[kind]
	match kind:
		"tree", "palm":
			var cone := CylinderMesh.new()
			cone.top_radius = 0.0
			cone.bottom_radius = 1.2
			cone.height = 4.0
			return cone
		"house":
			return BoxMesh.new()
		"rock":
			var s := SphereMesh.new()
			s.radius = 0.8
			s.height = 1.2
			return s
		"cactus":
			var c := CapsuleMesh.new()
			c.radius = 0.4
			c.height = 3.0
			return c
		"torch":
			var t := CylinderMesh.new()
			t.top_radius = 0.15
			t.bottom_radius = 0.15
			t.height = 2.0
			return t
		_:
			return BoxMesh.new()
