extends Node3D
class_name LifecycleDirector
## Faza 3 — hayot sikli: kun/tun, fasllar, ob-havo, ekotizim.
##
## Referens `lifecycle.py` bilan bir xil: harorat/fasl/populyatsiya modellari.
## Muhitni ko'rinishга bog'laydi: quyosh burilishi/rangi, osmon, ob-havo
## zarrachalari, faslга ko'ra o'simlik zichligi.

const DAYS_PER_YEAR := 360.0
const SEASONS := ["bahor", "yoz", "kuz", "qish"]
const BIOME_CLIMATE := {
	"snow": [-8.0, 14.0], "desert": [26.0, 12.0], "island": [24.0, 6.0],
	"canyon": [18.0, 16.0], "volcano": [20.0, 10.0], "grass": [12.0, 15.0],
}

@export var biome: String = "grass"
@export var day_length_sec: float = 120.0   # 1 o'yin kuni = shuncha real soniya
@export var sun: DirectionalLight3D
@export var env: WorldEnvironment

var day := 0.0
var time_of_day := 8.0
var day_of_year := 80.0
var temperature := 12.0
var weather := "ochiq"
# Ekotizim
var vegetation := 0.6
var herbivores := 0.4
var predators := 0.15

var _rain: GPUParticles3D
var _rng := RandomNumberGenerator.new()
var _weather_timer := 0.0

signal state_changed(summary: String)


func _ready() -> void:
	if sun == null:
		sun = DirectionalLight3D.new()
		add_child(sun)
	_rng.randomize()


func _process(delta: float) -> void:
	var dt_days := delta / day_length_sec
	day += dt_days
	day_of_year = fmod(day_of_year + dt_days, DAYS_PER_YEAR)
	time_of_day = fmod(time_of_day + dt_days * 24.0, 24.0)
	_update_temperature()
	_update_weather(dt_days)
	_update_ecosystem(dt_days)
	_apply_lighting()


func season() -> String:
	return SEASONS[int(day_of_year / (DAYS_PER_YEAR / 4)) % 4]


func sun_elevation() -> float:
	return sin(PI * (time_of_day - 6.0) / 12.0)


func _update_temperature() -> void:
	var c: Array = BIOME_CLIMATE.get(biome, [12.0, 15.0])
	var seasonal := -c[1] * cos(TAU * (day_of_year - 15.0) / DAYS_PER_YEAR)
	temperature = c[0] + seasonal + 5.0 * sun_elevation()


func _update_weather(dt_days: float) -> void:
	_weather_timer -= dt_days
	if _weather_timer > 0.0:
		return
	_weather_timer = 0.3 + _rng.randf() * 0.7
	var r := _rng.randf()
	if temperature < 1.0:
		weather = "qor" if r < 0.5 else "ochiq"
	elif r < 0.25:
		weather = "yomg'ir"
	elif r < 0.5:
		weather = "bulutli"
	else:
		weather = "ochiq"
	_apply_weather()
	state_changed.emit("%s • %s • %.0f°C" % [season(), weather, temperature])


func _update_ecosystem(dt_days: float) -> void:
	var season_factor := 0.5 + 0.5 * cos(TAU * (day_of_year - 165.0) / DAYS_PER_YEAR)
	var wet := 1.2 if weather == "yomg'ir" else (1.0 if weather == "bulutli" else 0.85)
	var steps := maxi(1, int(dt_days / 0.01))
	var h := dt_days / steps
	for _i in steps:
		var dveg := 1.0 * season_factor * wet * vegetation * (1.0 - vegetation / 1.3) - 0.7 * herbivores * vegetation
		var dherb := 0.8 * herbivores * vegetation - 0.1 * herbivores - 0.5 * predators * herbivores - 0.35 * herbivores * herbivores
		var dpred := 0.6 * predators * herbivores - 0.12 * predators - 0.3 * predators * predators
		vegetation = maxf(0.02, vegetation + dveg * h)
		herbivores = maxf(0.02, herbivores + dherb * h)
		predators = maxf(0.01, predators + dpred * h)


func _apply_lighting() -> void:
	if sun == null:
		return
	# Quyoshni soat bo'yicha burish (sharqdan g'arbga).
	var ang := PI * (time_of_day - 6.0) / 12.0
	sun.rotation = Vector3(-ang, deg_to_rad(-40.0), 0.0)
	var e := sun_elevation()
	sun.light_energy = clampf(e, 0.0, 1.0) * 1.2
	# Rang: tong/kech issiq, peshin oq, tun ko'k.
	if e <= 0.0:
		sun.light_color = Color(0.3, 0.4, 0.7)          # tun
	elif e < 0.3:
		sun.light_color = Color(1.0, 0.7, 0.45)         # tong/kech
	else:
		sun.light_color = Color(1.0, 0.97, 0.9)


func _apply_weather() -> void:
	var raining := weather == "yomg'ir" or weather == "qor"
	if raining and _rain == null:
		_rain = GPUParticles3D.new()
		_rain.amount = 800
		_rain.lifetime = 2.0
		var pm := ParticleProcessMaterial.new()
		pm.direction = Vector3(0.1, -1, 0)
		pm.gravity = Vector3(0, -30 if weather == "yomg'ir" else -6, 0)
		pm.initial_velocity_min = 10.0
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
		pm.emission_box_extents = Vector3(200, 1, 200)
		_rain.process_material = pm
		_rain.position = Vector3(0, 150, 0)
		add_child(_rain)
	elif not raining and _rain != null:
		_rain.queue_free()
		_rain = null


## Faslga ko'ra ko'rinadigan o'simlik zichligi ko'paytirgichi (scatter uchun).
func season_vegetation_scale() -> float:
	var base := {"bahor": 0.9, "yoz": 1.15, "kuz": 0.75, "qish": 0.35}[season()]
	return base * minf(1.3, 0.5 + vegetation)
