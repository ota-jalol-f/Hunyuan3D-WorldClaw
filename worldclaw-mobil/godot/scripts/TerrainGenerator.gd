extends RefCounted
class_name TerrainGenerator
## Relyef generatsiyasi — ScenePlan.terrain'dan balandlik xaritasi va ArrayMesh.
##
## Bu GDScript mantiqi referens `worldclaw/terrain.py` va `noise.py` ning aynan
## nusxasi (bir xil natija). Faza 1 da CPU'da ishlaydi; Faza 1.5 da og'ir qism
## `shaders/terrain_height.glsl` compute shaderiga ko'chiriladi.

const PERM_SIZE := 256


static func _build_perm(seed: int) -> PackedInt32Array:
	var perm := PackedInt32Array()
	perm.resize(PERM_SIZE)
	for i in PERM_SIZE:
		perm[i] = i
	var state := (seed ^ 0x9E3779B1) & 0xFFFFFFFF
	for i in range(PERM_SIZE - 1, 0, -1):
		state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
		var j := state % (i + 1)
		var t := perm[i]
		perm[i] = perm[j]
		perm[j] = t
	var doubled := PackedInt32Array()
	doubled.append_array(perm)
	doubled.append_array(perm)
	return doubled


static func _fade(t: float) -> float:
	return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


class ValueNoise:
	var _perm: PackedInt32Array

	func _init(seed: int) -> void:
		_perm = TerrainGenerator._build_perm(seed)

	func _grad_val(ix: int, iy: int) -> float:
		var h := _perm[(_perm[ix & 255] + iy) & 255]
		return (h / 127.5) - 1.0

	func at(x: float, y: float) -> float:
		var x0 := int(floor(x))
		var y0 := int(floor(y))
		var fx := TerrainGenerator._fade(x - x0)
		var fy := TerrainGenerator._fade(y - y0)
		var v00 := _grad_val(x0, y0)
		var v10 := _grad_val(x0 + 1, y0)
		var v01 := _grad_val(x0, y0 + 1)
		var v11 := _grad_val(x0 + 1, y0 + 1)
		var top := lerpf(v00, v10, fx)
		var bottom := lerpf(v01, v11, fx)
		return lerpf(top, bottom, fy)


static func _fbm(n: ValueNoise, x: float, y: float, octaves: int, gain: float) -> float:
	var amp := 1.0
	var freq := 1.0
	var total := 0.0
	var norm := 0.0
	for _i in octaves:
		total += amp * n.at(x * freq, y * freq)
		norm += amp
		amp *= gain
		freq *= 2.0
	return total / norm if norm > 0.0 else 0.0


static func _ridged(n: ValueNoise, x: float, y: float, octaves: int, gain: float) -> float:
	var amp := 1.0
	var freq := 1.0
	var total := 0.0
	var norm := 0.0
	for _i in octaves:
		var v := 1.0 - absf(n.at(x * freq, y * freq))
		v *= v
		total += amp * v
		norm += amp
		amp *= gain
		freq *= 2.0
	return total / norm if norm > 0.0 else 0.0


static func _biome_shape(biome: String, base: float, mountains: float, strength: float) -> float:
	var base01 := base * 0.5 + 0.5
	match biome:
		"canyon":
			var carve := 1.0 - mountains
			return clampf(0.6 + base01 * 0.2 - carve * strength * 0.55, 0.0, 1.0)
		"volcano":
			return clampf(base01 * 0.3 + mountains * strength, 0.0, 1.0)
		_:
			return clampf(base01 * (1.0 - strength * 0.5) + mountains * strength, 0.0, 1.0)


## Normallashgan balandliklar (PackedFloat32Array, size*size) qaytaradi.
static func generate_heightmap(spec: Dictionary) -> PackedFloat32Array:
	var size: int = spec.get("size", 256)
	var biome: String = spec.get("biome", "grass")
	var seed: int = spec.get("seed", 0)
	var strength: float = spec.get("mountain_strength", 0.6)
	var roughness: float = spec.get("roughness", 0.5)

	var base_noise := ValueNoise.new(seed)
	var ridge_noise := ValueNoise.new(seed ^ 0x5A5A5A5A)

	var out := PackedFloat32Array()
	out.resize(size * size)
	var inv := 1.0 / float(max(1, size))
	var base_freq := 4.0
	var center := 0.5

	for y in size:
		for x in size:
			var nx := x * inv
			var ny := y * inv
			var base := _fbm(base_noise, nx * base_freq, ny * base_freq, 5, roughness)
			var mountains := _ridged(ridge_noise, nx * base_freq, ny * base_freq, 5, roughness)
			var h: float
			if biome == "island":
				var dx := (nx - center) * 2.0
				var dy := (ny - center) * 2.0
				var dist := sqrt(dx * dx + dy * dy)
				var dome := clampf(1.15 - dist, 0.0, 1.0)
				h = dome * (0.5 + mountains * strength)
				h += (base * 0.5 + 0.5) * 0.05
				h = clampf(h, 0.0, 1.0)
			else:
				h = _biome_shape(biome, base, mountains, strength)
			out[y * size + x] = h
	return out


## Balandlik xaritasidan ArrayMesh quradi (Y = balandlik * height_scale).
static func build_mesh(heights: PackedFloat32Array, spec: Dictionary) -> ArrayMesh:
	var size: int = spec.get("size", 256)
	var world_scale: float = spec.get("world_scale", 400.0)
	var height_scale: float = spec.get("height_scale", 60.0)
	var cell := world_scale / float(size)
	var half := world_scale * 0.5

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for y in size - 1:
		for x in size - 1:
			var i00 := y * size + x
			var i10 := y * size + x + 1
			var i01 := (y + 1) * size + x
			var i11 := (y + 1) * size + x + 1
			var p00 := Vector3(x * cell - half, heights[i00] * height_scale, y * cell - half)
			var p10 := Vector3((x + 1) * cell - half, heights[i10] * height_scale, y * cell - half)
			var p01 := Vector3(x * cell - half, heights[i01] * height_scale, (y + 1) * cell - half)
			var p11 := Vector3((x + 1) * cell - half, heights[i11] * height_scale, (y + 1) * cell - half)
			st.add_vertex(p00); st.add_vertex(p01); st.add_vertex(p10)
			st.add_vertex(p10); st.add_vertex(p01); st.add_vertex(p11)
	st.generate_normals()
	return st.commit()


## Qiyalik (referens bilan bir xil) — scatter qoidalari uchun.
static func slope_at(heights: PackedFloat32Array, size: int, x: int, y: int) -> float:
	var xm := clampi(x - 1, 0, size - 1)
	var xp := clampi(x + 1, 0, size - 1)
	var ym := clampi(y - 1, 0, size - 1)
	var yp := clampi(y + 1, 0, size - 1)
	var dx := heights[y * size + xp] - heights[y * size + xm]
	var dy := heights[yp * size + x] - heights[ym * size + x]
	return sqrt(dx * dx + dy * dy)
