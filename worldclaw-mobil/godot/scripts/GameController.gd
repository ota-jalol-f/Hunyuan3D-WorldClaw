extends Node3D
## Bosh orkestrator — promptdan dunyoni quradi (arxitektura hujjatidagi oqim).
##
##   1. Intent   — AICoreBridge (Gemini Nano) yoki ScenePlan zaxira rejalovchi
##   2. Terrain  — TerrainGenerator (Faza 1: CPU, keyin GPU compute)
##   3. Scatter  — ScatterSystem (MultiMesh instancing)
##   Detallar keshi — bir xil (prompt, seed, size) qayta hisoblanmaydi.

@export var default_prompt: String = "qorli qishloq, ikki yonida baland tog'lar"
@export var terrain_size: int = 256
@export var use_aicore: bool = true
@export var use_gpu_terrain: bool = true   # Faza 1.5: compute shader, aks holda CPU
@export var use_refine: bool = true        # Faza 2: agentli sifat sikli
@export var use_physics: bool = true       # Faza 3: relyef to'qnashuvi + dinamik jismlar

@onready var _terrain_holder: Node3D = $TerrainHolder
@onready var _scatter: ScatterSystem = $ScatterSystem
@onready var _camera_rig: CameraRig = $CameraRig
@onready var _status: Label = $UI/Status

var _cache: Dictionary = {}          # kalit -> {"heights", "plan", "mesh"}
var _aicore = null                    # AICoreBridge (Android'da mavjud)

# Joriy dunyo holati — real-vaqt tahrir uchun (qisman qayta hisoblash).
var _cur_heights: PackedFloat32Array
var _cur_plan: Dictionary
var _cur_placements: Array
@export var lifecycle: LifecycleDirector


func _ready() -> void:
	# AICore faqat Android qurilmada; boshqa joyda zaxira rejalovchi.
	if use_aicore and Engine.has_singleton("AICoreBridge"):
		_aicore = Engine.get_singleton("AICoreBridge")
	generate(default_prompt)


## Promptdan to'liq dunyoni quradi (asinxron intent bilan).
func generate(prompt: String) -> void:
	_set_status("Reja tuzilmoqda…")
	var plan := await _plan_for(prompt)
	if plan.is_empty():
		_set_status("Xato: reja tuzilmadi")
		return

	var key := "%s|%d|%d|%s" % [prompt, plan.terrain.get("seed", 0), terrain_size, str(use_refine)]
	var heights: PackedFloat32Array
	var mesh: ArrayMesh
	var placements: Array
	if _cache.has(key):
		var c: Dictionary = _cache[key]
		heights = c.heights
		mesh = c.mesh
		placements = c.placements
		plan = c.plan
		_set_status("Keshdan yuklandi")
	else:
		if use_refine:
			# Faza 2 — agentli sifat sikli (relyef + scatter tuzatiladi).
			_set_status("Sifat sikli…")
			var refined := RefinementAgent.refine(plan)
			plan = refined.plan
			heights = refined.heights
			placements = refined.placements
			_set_status("Refine: %d takror • sifat %.2f" % [refined.iterations, refined.score])
		else:
			_set_status("Relyef qurilmoqda…")
			heights = PackedFloat32Array()
			if use_gpu_terrain:
				heights = TerrainCompute.try_generate(plan.terrain)   # GPU (Faza 1.5)
			if heights.is_empty():
				heights = TerrainGenerator.generate_heightmap(plan.terrain)  # CPU zaxira
			placements = ScatterSystem.compute_placements(plan, heights)
		mesh = TerrainGenerator.build_mesh(heights, plan.terrain)
		_cache[key] = {"heights": heights, "plan": plan, "mesh": mesh, "placements": placements}

	_show_terrain(mesh, plan)
	var count := _scatter.build_instances(placements)
	# Joriy holatni saqlash (real-vaqt tahrir uchun).
	_cur_heights = heights
	_cur_plan = plan
	_cur_placements = placements
	if lifecycle != null:
		lifecycle.biome = plan.terrain.get("biome", "grass")

	if use_physics:
		# Relyef to'qnashuv jismi + suv sathi + bir necha dinamik tosh.
		var body := WorldPhysics.build_terrain_body(heights, plan.terrain)
		_terrain_holder.add_child(body)
		if plan.terrain.get("water_level", 0.0) > 0.01:
			_terrain_holder.add_child(WorldPhysics.water_surface(plan.terrain))
		for rb in WorldPhysics.spawn_dynamic(placements, "rock", 24):
			_terrain_holder.add_child(rb)

	_set_status("%s • %d obyekt%s" % [
		plan.terrain.get("biome", "?"), count, "  • fizika" if use_physics else ""])


## Intent bosqichi — AICore bo'lsa u orqali, aks holda zaxira rejalovchi.
func _plan_for(prompt: String) -> Dictionary:
	if _aicore != null:
		var json_text: String = await _aicore.plan_scene(prompt, terrain_size)
		var parsed := ScenePlan.parse_json(json_text)
		if not parsed.is_empty():
			return parsed
		push_warning("AICore rejasi yaroqsiz — zaxira rejalovchiga o'tildi")
	return ScenePlan.plan_from_prompt(prompt, terrain_size)


func _show_terrain(mesh: ArrayMesh, plan: Dictionary) -> void:
	for child in _terrain_holder.get_children():
		child.queue_free()
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = false
	mat.albedo_color = _biome_color(plan.terrain.get("biome", "grass"))
	mi.material_override = mat
	_terrain_holder.add_child(mi)


func _biome_color(biome: String) -> Color:
	match biome:
		"snow": return Color(0.85, 0.88, 0.92)
		"desert": return Color(0.80, 0.66, 0.42)
		"island": return Color(0.35, 0.55, 0.35)
		"canyon": return Color(0.66, 0.40, 0.28)
		"volcano": return Color(0.28, 0.20, 0.20)
		_: return Color(0.40, 0.55, 0.35)


func _set_status(text: String) -> void:
	if _status != null:
		_status.text = text
	print("[WorldClaw] ", text)


## UI tugmalari uchun (main.tscn dan ulanadi).
func _on_regenerate_pressed() -> void:
	generate(default_prompt)


func _on_orbit_pressed() -> void:
	_camera_rig.set_mode(CameraRig.Mode.ORBIT)


func _on_walk_pressed() -> void:
	_camera_rig.set_mode(CameraRig.Mode.WALK)


## Real-vaqt prompt tahriri — matndan dunyoni o'zgartiradi (minimal regen).
## Referens edit.py bilan bir xil darajalar: scatter/water relyefni qayta
## ishlatadi, terrain regen qiladi, biom to'liq qayta.
func apply_prompt(text: String) -> void:
	if _cur_plan.is_empty():
		generate(text)
		return
	var low := text.to_lower()
	var plan := _cur_plan.duplicate(true)
	var terr: Dictionary = plan.terrain
	var level := "env"
	var veg := ["tree", "palm", "cactus"]

	# Biom -> to'liq qayta.
	for key in {"sahro": 1, "desert": 1, "orol": 1, "island": 1, "vulqon": 1, "volcano": 1, "kanyon": 1, "canyon": 1}:
		if low.contains(key):
			generate(text)
			return

	# Relyef.
	var terrain_changed := false
	if low.contains("tog'") or low.contains("baland") or low.contains("mountain"):
		terr.mountain_strength = minf(1.0, terr.mountain_strength + 0.2)
		terr.height_scale = minf(120.0, terr.get("height_scale", 60.0) * 1.15)
		terrain_changed = true
	elif low.contains("tekis") or low.contains("flat"):
		terr.mountain_strength = maxf(0.1, terr.mountain_strength - 0.25)
		terrain_changed = true

	# Suv.
	var water_changed := false
	if low.contains("toshqin") or low.contains("ko'l") or low.contains("flood"):
		terr.water_level = minf(0.7, terr.get("water_level", 0.28) + 0.1)
		water_changed = true
	elif low.contains("qurit") or low.contains("drain"):
		terr.water_level = maxf(0.0, terr.get("water_level", 0.28) - 0.1)
		water_changed = true

	# O'simlik / fasl.
	var scatter_changed := false
	var scale := 1.0
	if low.contains("o'rmon") or low.contains("ko'p daraxt") or low.contains("forest"):
		scale = 1.6; scatter_changed = true
	elif low.contains("kes") or low.contains("yalang") or low.contains("clear"):
		scale = 0.4; scatter_changed = true
	if low.contains("qish") or low.contains("winter"):
		if lifecycle: lifecycle.day_of_year = 310.0
		scale *= 0.35; scatter_changed = true
	elif low.contains("yoz") or low.contains("summer"):
		if lifecycle: lifecycle.day_of_year = 130.0
		scale *= 1.15; scatter_changed = true
	if scatter_changed:
		for rule: Dictionary in plan.scatter:
			if rule.kind in veg:
				rule.density = clampf(rule.density * scale, 0.0, 1.0)

	# Vaqt (faqat lifecycle).
	if low.contains("tun") or low.contains("night"):
		if lifecycle: lifecycle.time_of_day = 23.0
	elif low.contains("kun") or low.contains("day"):
		if lifecycle: lifecycle.time_of_day = 12.0

	# Minimal qayta hisoblash.
	if terrain_changed:
		level = "terrain"
		_cur_heights = TerrainCompute.try_generate(terr)
		if _cur_heights.is_empty():
			_cur_heights = TerrainGenerator.generate_heightmap(terr)
		var mesh := TerrainGenerator.build_mesh(_cur_heights, terr)
		_show_terrain(mesh, plan)
	if terrain_changed or water_changed or scatter_changed:
		if level == "env":
			level = "water" if water_changed else "scatter"
		_cur_placements = ScatterSystem.compute_placements(plan, _cur_heights)
		_scatter.build_instances(_cur_placements)
	_cur_plan = plan
	_set_status("tahrir: %s (%s)" % [text, level])


func _on_prompt_submitted(text: String) -> void:
	if text.strip_edges() != "":
		apply_prompt(text)


func _on_export_pressed() -> void:
	# Faza 3 — joriy dunyoni .glb qilib saqlaydi (istalgan 3D ko'ruvchi ochadi).
	var path := "user://worldclaw_export.glb"
	var err := WorldExporter.export_world(_terrain_holder, _scatter, path)
	if err == OK:
		_set_status("Eksport: %s" % ProjectSettings.globalize_path(path))
	else:
		_set_status("Eksport xatosi (%d)" % err)
