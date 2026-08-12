extends RefCounted
class_name TerrainCompute
## Faza 1.5 — relyefni GPU'da hisoblash (compute shader + RenderingDevice).
##
## `shaders/terrain_height.glsl` ni lokal RenderingDevice orqali dispatch qiladi
## va balandlik buferini qaytaradi. Snapdragon Adreno GPU'da minglab tugun
## parallel hisoblanadi — CPU (GDScript) yo'lidan ancha tez.
##
## Foydalanish:
##     var heights := TerrainCompute.try_generate(plan.terrain)
##     if heights.is_empty():
##         heights = TerrainGenerator.generate_heightmap(plan.terrain)  # CPU zaxira

const SHADER_PATH := "res://shaders/terrain_height.glsl"
const LOCAL_SIZE := 8   # shaderdagi local_size_x/y bilan bir xil bo'lishi shart

const _BIOME_INDEX := {
	"snow": 0, "desert": 1, "island": 2, "canyon": 3, "volcano": 4, "grass": 5,
}


## Muvaffaqiyatda size*size PackedFloat32Array, xatoda bo'sh massiv qaytaradi.
static func try_generate(spec: Dictionary) -> PackedFloat32Array:
	var size: int = spec.get("size", 256)
	var rd := RenderingServer.create_local_rendering_device()
	if rd == null:
		push_warning("TerrainCompute: RenderingDevice yo'q — CPU yo'liga o'ting")
		return PackedFloat32Array()

	# Shaderni yuklash va kompilyatsiya.
	var shader_file: RDShaderFile = load(SHADER_PATH)
	if shader_file == null:
		push_error("TerrainCompute: shader yuklanmadi: %s" % SHADER_PATH)
		rd.free()
		return PackedFloat32Array()
	var spirv: RDShaderSPIRV = shader_file.get_spirv()
	var shader: RID = rd.shader_create_from_spirv(spirv)

	# Chiqish buferi (nol bilan to'ldirilgan).
	var byte_count := size * size * 4
	var zeros := PackedByteArray()
	zeros.resize(byte_count)
	var buffer: RID = rd.storage_buffer_create(byte_count, zeros)

	var uniform := RDUniform.new()
	uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER
	uniform.binding = 0
	uniform.add_id(buffer)
	var uniform_set: RID = rd.uniform_set_create([uniform], shader, 0)

	var pipeline: RID = rd.compute_pipeline_create(shader)

	# Push-konstanta — shaderdagi Params bilan bir xil tartib (32 bayt).
	var pc := _build_push_constant(spec)

	var groups := int(ceil(float(size) / float(LOCAL_SIZE)))
	var cl := rd.compute_list_begin()
	rd.compute_list_bind_compute_pipeline(cl, pipeline)
	rd.compute_list_bind_uniform_set(cl, uniform_set, 0)
	rd.compute_list_set_push_constant(cl, pc, pc.size())
	rd.compute_list_dispatch(cl, groups, groups, 1)
	rd.compute_list_end()

	rd.submit()
	rd.sync()

	var out_bytes := rd.buffer_get_data(buffer)
	var heights := out_bytes.to_float32_array()

	# Resurslarni bo'shatish.
	rd.free_rid(uniform_set)
	rd.free_rid(pipeline)
	rd.free_rid(buffer)
	rd.free_rid(shader)
	rd.free()

	return heights


static func _build_push_constant(spec: Dictionary) -> PackedByteArray:
	var pc := PackedByteArray()
	pc.resize(32)
	var biome: String = spec.get("biome", "grass")
	pc.encode_s32(0, spec.get("size", 256))
	pc.encode_u32(4, int(spec.get("seed", 0)) & 0xFFFFFFFF)
	pc.encode_s32(8, _BIOME_INDEX.get(biome, 5))
	pc.encode_float(12, spec.get("mountain_strength", 0.6))
	pc.encode_float(16, spec.get("roughness", 0.5))
	pc.encode_float(20, 4.0)   # base_freq — TerrainGenerator bilan bir xil
	pc.encode_float(24, 0.0)   # _pad0
	pc.encode_float(28, 0.0)   # _pad1
	return pc
