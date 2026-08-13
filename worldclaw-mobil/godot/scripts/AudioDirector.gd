extends AudioStreamPlayer
class_name AudioDirector
## Faza 3 — biomga xos generativ audio (sample emas, sintez).
##
## Referens `audio.py` bilan bir xil: ambient (shamol/dron) + pentatonik
## melodiya, biomga ko'ra kayfiyat/temp. Godot `AudioStreamGenerator` orqali
## real-vaqtда push qilinadi. Qurilmада NPU audio modeli ham ulanishi mumkin.

const RATE := 22050.0

const BIOME_AUDIO := {
	"snow":    {"root": 220.00, "scale": "minor", "bpm": 64, "wind": 0.55},
	"desert":  {"root": 196.00, "scale": "major", "bpm": 72, "wind": 0.60},
	"island":  {"root": 261.63, "scale": "major", "bpm": 96, "wind": 0.40},
	"canyon":  {"root": 174.61, "scale": "minor", "bpm": 60, "wind": 0.50},
	"volcano": {"root": 146.83, "scale": "minor", "bpm": 54, "wind": 0.50},
	"grass":   {"root": 246.94, "scale": "major", "bpm": 88, "wind": 0.35},
}
const SCALES := {"major": [0, 2, 4, 7, 9], "minor": [0, 3, 5, 7, 10]}

var _cfg: Dictionary = BIOME_AUDIO["grass"]
var _playback: AudioStreamGeneratorPlayback
var _t := 0.0                 # global vaqt
var _lp := 0.0                # shamol past o'tkazgich holati
var _rng := RandomNumberGenerator.new()
var _note_end := 0.0
var _note_freq := 220.0


func setup(biome: String, seed: int) -> void:
	_cfg = BIOME_AUDIO.get(biome, BIOME_AUDIO["grass"])
	_rng.seed = seed
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = RATE
	gen.buffer_length = 0.25
	stream = gen
	play()
	_playback = get_stream_playback()


func _process(_delta: float) -> void:
	if _playback == null:
		return
	var frames := _playback.get_frames_available()
	var beat := 60.0 / _cfg.bpm
	var scale: Array = SCALES[_cfg.scale]
	for _i in frames:
		# Ambient shamol (past o'tkazgichли oq shovqin) + swell.
		var white := _rng.randf() * 2.0 - 1.0
		_lp += (white - _lp) * 0.05
		var swell: float = 0.6 + 0.4 * sin(_t * 0.4)
		var s: float = _lp * _cfg.wind * swell * 0.5
		# Dron (root + kvinta).
		s += sin(TAU * _cfg.root * 0.5 * _t) * 0.05
		s += sin(TAU * _cfg.root * 0.75 * _t) * 0.035
		# Melodiya — pentatonik seedlangan sayr.
		if _t >= _note_end:
			var deg := _rng.randi_range(0, scale.size() * 2 - 1)
			var semis: int = scale[deg % scale.size()] + 12 * (deg / scale.size())
			_note_freq = _cfg.root * pow(2.0, semis / 12.0)
			_note_end = _t + (beat if _rng.randf() > 0.3 else beat * 0.5)
		var tri := 4.0 * abs(fmod(_note_freq * _t, 1.0) - 0.5) - 1.0
		s += tri * 0.2
		s = clampf(s, -1.0, 1.0)
		_playback.push_frame(Vector2(s, s))
		_t += 1.0 / RATE
