extends RefCounted
class_name RefinementAgent
## Faza 2 — agentli sifat sikli (WorldClaw '/loop' nusxasi).
##
## Oqim: reja -> relyef -> quruq scatter -> baholash -> reja tuzatish -> qayta …
## sifat chegarasiga yetguncha yoki max_iters gacha. Mesh faqat yakunda quriladi.
##
## Baholovchi (`_evaluate`) referens `critic.py` ning nusxasi. Qurilmada bu yerga
## qo'shimcha Gemini Nano multimodal bahosi (AICoreBridge.evaluate_scene) ulanadi.

const TARGET_BUILDABLE_MIN := 0.22
const TARGET_POP_LO := 0.04
const TARGET_POP_HI := 0.18
const TARGET_SECTOR_COVERAGE := 0.85
const SECTORS := 6
const ACCEPT_SCORE := 0.85


## Rejani sifat chegarasига yetguncha tuzatadi.
## Qaytaradi: {plan, heights, placements, score, iterations, history}.
static func refine(plan: Dictionary, max_iters: int = 5) -> Dictionary:
	var history: Array = []
	var work := plan.duplicate(true)
	var heights := _make_heights(work.terrain)
	var placements := ScatterSystem.compute_placements(work, heights)

	for i in max_iters:
		var crit := _evaluate(work.terrain, heights, placements)
		history.append({"iter": i, "score": crit.score, "metrics": crit.metrics})
		if crit.score >= ACCEPT_SCORE:
			break
		# Rejani tuzatish.
		if crit.density_scale != 1.0:
			for rule: Dictionary in work.scatter:
				rule.density = clampf(rule.density * crit.density_scale, 0.0, 1.0)
		if crit.water_delta != 0.0:
			work.terrain.water_level = clampf(
				work.terrain.water_level + crit.water_delta, 0.0, 0.95)
			heights = _make_heights(work.terrain)  # suv o'zgardi -> qayta baholanadi
		placements = ScatterSystem.compute_placements(work, heights)

	var final_score: float = history[-1].score if history.size() > 0 else 0.0
	return {
		"plan": work, "heights": heights, "placements": placements,
		"score": final_score, "iterations": history.size(), "history": history,
	}


static func _make_heights(spec: Dictionary) -> PackedFloat32Array:
	var h := TerrainCompute.try_generate(spec)   # GPU (Faza 1.5)
	if h.is_empty():
		h = TerrainGenerator.generate_heightmap(spec)  # CPU zaxira
	return h


## Sahnani baholaydi. Qaytaradi: {score, metrics, density_scale, water_delta}.
static func _evaluate(spec: Dictionary, heights: PackedFloat32Array, placements: Array) -> Dictionary:
	var size: int = spec.size
	var water: float = spec.get("water_level", 0.28)

	# Quruqlik ulushi.
	var land := 0
	for h in heights:
		if h > water:
			land += 1
	var buildable := float(land) / float(max(1, heights.size()))
	var land_cells := max(1, int(buildable * size * size))
	var populated := float(placements.size()) / float(land_cells)
	var coverage := _sector_coverage(spec, heights, placements)

	var density_scale := 1.0
	var water_delta := 0.0

	var build_score := minf(1.0, buildable / TARGET_BUILDABLE_MIN)
	if buildable < TARGET_BUILDABLE_MIN:
		water_delta = -minf(0.08, TARGET_BUILDABLE_MIN - buildable)

	var pop_score := _band_score(populated, TARGET_POP_LO, TARGET_POP_HI)
	if populated < TARGET_POP_LO:
		var mid := (TARGET_POP_LO + TARGET_POP_HI) * 0.5
		density_scale = minf(3.0, mid / maxf(populated, 1e-4))
	elif populated > TARGET_POP_HI:
		density_scale = maxf(0.4, TARGET_POP_HI / populated)

	var cov_score := minf(1.0, coverage / TARGET_SECTOR_COVERAGE)
	if coverage < TARGET_SECTOR_COVERAGE:
		density_scale = maxf(density_scale, 1.3)

	var score := build_score * 0.3 + pop_score * 0.3 + cov_score * 0.3 + 0.1
	return {
		"score": score,
		"metrics": {"buildable": buildable, "populated": populated,
			"coverage": coverage, "objects": placements.size()},
		"density_scale": density_scale,
		"water_delta": water_delta,
	}


static func _sector_coverage(spec: Dictionary, heights: PackedFloat32Array, placements: Array) -> float:
	var size: int = spec.size
	var water: float = spec.get("water_level", 0.28)
	var world: float = spec.get("world_scale", 400.0)
	var cell := float(size) / float(SECTORS)
	var cell_world := world / float(size)
	var half := world * 0.5

	var land_sectors := {}
	for sy in SECTORS:
		for sx in SECTORS:
			var cx := int((sx + 0.5) * cell)
			var cy := int((sy + 0.5) * cell)
			if heights[cy * size + cx] > water:
				land_sectors[Vector2i(sx, sy)] = true
	if land_sectors.is_empty():
		return 0.0

	var occupied := {}
	for p: Dictionary in placements:
		var gx := int((p.wx + half) / cell_world)
		var gy := int((p.wz + half) / cell_world)
		var sx := mini(SECTORS - 1, int(gx / cell))
		var sy := mini(SECTORS - 1, int(gy / cell))
		occupied[Vector2i(sx, sy)] = true

	var covered := 0
	for k in land_sectors:
		if occupied.has(k):
			covered += 1
	return float(covered) / float(land_sectors.size())


static func _band_score(v: float, lo: float, hi: float) -> float:
	if v >= lo and v <= hi:
		return 1.0
	if v < lo:
		return maxf(0.0, v / lo) if lo > 0.0 else 0.0
	var over := (v - hi) / hi if hi > 0.0 else 1.0
	return maxf(0.0, 1.0 - over)
