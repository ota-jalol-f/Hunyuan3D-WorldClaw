extends RefCounted
class_name TextureGenerator
## Faza 2 — generativ material teksturalari (assetdan olinmaydi).
##
## MUHIM: sirtlar saqlanmaydi, generatsiya qilinadi. Qurilmada asosiy yo'l —
## NPU'да (LiteRT + QNN) diffusion. Bu procedural generator determinlashgan
## zaxira va prototip: referens `texture.py` bilan bir xil rollni bajaradi.
## Natijalar `TextureCache` orqali keshlanadi (ko'p ishlatilganlari tez).

# Material -> [asosiy rang, tomir rang, dog' zichligi].
const _MATERIALS := {
	"snow": [Color(0.93, 0.96, 0.99), Color(0.80, 0.85, 0.93), 0.10],
	"rock": [Color(0.47, 0.46, 0.48), Color(0.31, 0.29, 0.31), 0.55],
	"sand": [Color(0.84, 0.71, 0.47), Color(0.74, 0.59, 0.36), 0.30],
	"grass": [Color(0.36, 0.55, 0.29), Color(0.24, 0.41, 0.20), 0.45],
	"lava": [Color(0.24, 0.12, 0.11), Color(0.82, 0.35, 0.16), 0.60],
	"bark": [Color(0.38, 0.27, 0.19), Color(0.26, 0.18, 0.12), 0.50],
}

const BIOME_MATERIALS := {
	"snow": ["snow", "rock", "bark"],
	"desert": ["sand", "rock"],
	"island": ["sand", "grass", "bark"],
	"canyon": ["rock", "sand"],
	"volcano": ["lava", "rock"],
	"grass": ["grass", "rock", "bark"],
}

static var _cache: Dictionary = {}   # "material|seed|size" -> ImageTexture


## Material uchun albedo teksturasini generatsiya qiladi (keshlanadi).
static func generate(material: String, size: int = 128, seed: int = 0) -> ImageTexture:
	var key := "%s|%d|%d" % [material, seed, size]
	if _cache.has(key):
		return _cache[key]

	# TODO(Faza 2): NPU diffusion yo'li — mavjud bo'lsa shu yerda chaqiriladi:
	#   var tex := NpuTextureBridge.diffuse(material, seed, size)
	#   if tex: _cache[key] = tex; return tex
	var params: Array = _MATERIALS.get(material, _MATERIALS["rock"])
	var base: Color = params[0]
	var vein: Color = params[1]
	var spots: float = params[2]

	var n1 := TerrainGenerator.ValueNoise.new(seed)
	var n2 := TerrainGenerator.ValueNoise.new(seed ^ 0x1234ABCD)
	var img := Image.create(size, size, false, Image.FORMAT_RGB8)
	var freq := 6.0
	for y in size:
		for x in size:
			var u := float(x) / size
			var v := float(y) / size
			var large := TerrainGenerator._fbm(n1, u * freq, v * freq, 4, 0.5) * 0.5 + 0.5
			var fine := TerrainGenerator._fbm(n2, u * freq * 4.0, v * freq * 4.0, 3, 0.5) * 0.5 + 0.5
			var t := large * (1.0 - spots) + fine * spots
			img.set_pixel(x, y, base.lerp(vein, t))

	var tex := ImageTexture.create_from_image(img)
	_cache[key] = tex
	return tex


## Biom uchun barcha material teksturalarini generatsiya qiladi.
static func generate_biome_set(biome: String, size: int = 128, seed: int = 0) -> Dictionary:
	var out: Dictionary = {}
	var mats: Array = BIOME_MATERIALS.get(biome, ["rock"])
	for i in mats.size():
		out[mats[i]] = generate(mats[i], size, seed + i * 101)
	return out
