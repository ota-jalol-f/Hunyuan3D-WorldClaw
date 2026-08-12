extends RefCounted
class_name ScenePlan
## scene_plan bilan ishlash — AICore (Kotlin) chiqargan JSON'ni tekshirib
## Dictionary'ga aylantiradi, hamda oflayn zaxira rejalovchini beradi.
##
## Sxema `docs/scene-plan-schema.json` bilan bir xil; mantiq referens
## `worldclaw/scene_plan.py` ni takrorlaydi.

const BIOMES := ["snow", "desert", "island", "canyon", "volcano", "grass"]
const OBJECT_KINDS := ["tree", "house", "rock", "fence", "torch", "cactus", "palm"]

const _BIOME_KEYWORDS := {
	"snow": ["snow", "qor", "ice", "muz", "winter", "qish", "frozen", "sovuq"],
	"desert": ["desert", "sahro", "dune", "qum", "sand", "arid"],
	"island": ["island", "orol", "ocean", "sea", "dengiz", "beach", "tropical"],
	"canyon": ["canyon", "kanyon", "gorge", "mesa", "cliff", "jarlik"],
	"volcano": ["volcano", "vulqon", "lava", "ember", "magma", "caldera"],
	"grass": ["grass", "forest", "o'rmon", "meadow", "valley", "vodiy", "green"],
}

const _BIOME_TERRAIN := {
	"snow": {"mountain_strength": 0.75, "height_scale": 80.0, "water_level": 0.28, "roughness": 0.5},
	"desert": {"mountain_strength": 0.35, "height_scale": 40.0, "water_level": 0.0, "roughness": 0.55},
	"island": {"mountain_strength": 0.45, "height_scale": 55.0, "water_level": 0.42, "roughness": 0.5},
	"canyon": {"mountain_strength": 0.85, "height_scale": 90.0, "water_level": 0.15, "roughness": 0.65},
	"volcano": {"mountain_strength": 0.8, "height_scale": 95.0, "water_level": 0.1, "roughness": 0.6},
	"grass": {"mountain_strength": 0.5, "height_scale": 50.0, "water_level": 0.25, "roughness": 0.5},
}

const _BIOME_SCATTER := {
	"snow": [
		{"kind": "tree", "density": 0.05, "min_height": 0.30, "max_height": 0.75, "max_slope": 0.5},
		{"kind": "house", "density": 0.004, "min_height": 0.30, "max_height": 0.55, "max_slope": 0.25},
		{"kind": "rock", "density": 0.02, "min_height": 0.28, "max_height": 0.95, "max_slope": 0.8},
		{"kind": "torch", "density": 0.003, "min_height": 0.30, "max_height": 0.55, "max_slope": 0.3},
		{"kind": "fence", "density": 0.01, "min_height": 0.30, "max_height": 0.55, "max_slope": 0.3},
	],
	"desert": [
		{"kind": "cactus", "density": 0.03, "min_height": 0.30, "max_height": 0.7, "max_slope": 0.4},
		{"kind": "rock", "density": 0.03, "min_height": 0.28, "max_height": 0.95, "max_slope": 0.9},
		{"kind": "house", "density": 0.002, "min_height": 0.30, "max_height": 0.5, "max_slope": 0.2},
	],
	"island": [
		{"kind": "palm", "density": 0.04, "min_height": 0.30, "max_height": 0.6, "max_slope": 0.5},
		{"kind": "rock", "density": 0.02, "min_height": 0.29, "max_height": 0.9, "max_slope": 0.9},
		{"kind": "house", "density": 0.003, "min_height": 0.31, "max_height": 0.5, "max_slope": 0.2},
	],
	"canyon": [
		{"kind": "rock", "density": 0.05, "min_height": 0.20, "max_height": 0.98, "max_slope": 1.0},
		{"kind": "cactus", "density": 0.015, "min_height": 0.25, "max_height": 0.6, "max_slope": 0.5},
	],
	"volcano": [
		{"kind": "rock", "density": 0.06, "min_height": 0.20, "max_height": 0.98, "max_slope": 1.0},
		{"kind": "torch", "density": 0.004, "min_height": 0.30, "max_height": 0.7, "max_slope": 0.5},
	],
	"grass": [
		{"kind": "tree", "density": 0.08, "min_height": 0.30, "max_height": 0.8, "max_slope": 0.6},
		{"kind": "house", "density": 0.004, "min_height": 0.30, "max_height": 0.5, "max_slope": 0.25},
		{"kind": "rock", "density": 0.02, "min_height": 0.29, "max_height": 0.95, "max_slope": 0.9},
		{"kind": "fence", "density": 0.012, "min_height": 0.30, "max_height": 0.5, "max_slope": 0.3},
	],
}


static func stable_seed(text: String) -> int:
	var h := 2166136261
	for i in text.length():
		h = ((h ^ text.unicode_at(i)) * 16777619) & 0xFFFFFFFF
	return h


static func detect_biome(prompt: String) -> String:
	var low := prompt.to_lower()
	var best := "grass"
	var best_hits := 0
	for biome in _BIOME_KEYWORDS:
		var hits := 0
		for w in _BIOME_KEYWORDS[biome]:
			if low.contains(w):
				hits += 1
		if hits > best_hits:
			best = biome
			best_hits = hits
	return best


## Oflayn zaxira rejalovchi (qurilmada Gemini Nano/AICore o'rnini bosadi).
static func plan_from_prompt(prompt: String, size: int = 256, seed_override: int = -1) -> Dictionary:
	var biome := detect_biome(prompt)
	var seed := seed_override if seed_override >= 0 else stable_seed(prompt)
	var terrain := {"biome": biome, "seed": seed, "size": size, "world_scale": 400.0}
	terrain.merge(_BIOME_TERRAIN[biome])
	return {
		"prompt": prompt,
		"terrain": terrain,
		"scatter": _BIOME_SCATTER[biome].duplicate(true),
		"style": "cartoon",
		"notes": "GDScript zaxira rejalovchi; biom: %s" % biome,
	}


## AICore/fayldan kelgan JSON matnini tekshirib Dictionary qaytaradi.
## Xato bo'lsa bo'sh Dictionary va push_error.
static func parse_json(text: String) -> Dictionary:
	var data = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		push_error("scene_plan: JSON obyekt emas")
		return {}
	if not validate(data):
		return {}
	return data


static func validate(plan: Dictionary) -> bool:
	var terrain: Dictionary = plan.get("terrain", {})
	if not BIOMES.has(terrain.get("biome", "")):
		push_error("scene_plan: noma'lum biom")
		return false
	var seen := {}
	for rule in plan.get("scatter", []):
		var kind: String = rule.get("kind", "")
		if not OBJECT_KINDS.has(kind):
			push_error("scene_plan: noma'lum obyekt turi: %s" % kind)
			return false
		if seen.has(kind):
			push_error("scene_plan: takroriy scatter: %s" % kind)
			return false
		seen[kind] = true
	return true
