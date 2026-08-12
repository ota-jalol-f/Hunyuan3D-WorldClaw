extends Node3D
class_name CameraRig
## Dunyoni ko'rish kamerasi — orbit (aylanish) va yurish rejimlari.
## Sensorli boshqaruv: bir barmoq surish -> aylantirish, ikki barmoq -> zoom.

enum Mode { ORBIT, WALK }

@export var mode: Mode = Mode.ORBIT
@export var orbit_distance: float = 320.0
@export var orbit_height: float = 140.0
@export var rotate_speed: float = 0.005
@export var zoom_speed: float = 0.08
@export var walk_speed: float = 40.0

var _yaw: float = 0.0
var _pitch: float = -0.5
var _camera: Camera3D
var _last_pan_dist: float = -1.0


func _ready() -> void:
	_camera = Camera3D.new()
	_camera.current = true
	_camera.far = 4000.0
	add_child(_camera)
	_apply_orbit()


func set_mode(m: Mode) -> void:
	mode = m
	if mode == Mode.ORBIT:
		_apply_orbit()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenDrag:
		_yaw -= event.relative.x * rotate_speed
		_pitch = clampf(_pitch - event.relative.y * rotate_speed, -1.4, -0.05)
		if mode == Mode.ORBIT:
			_apply_orbit()
	elif event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			orbit_distance = maxf(40.0, orbit_distance * (1.0 - zoom_speed))
			_apply_orbit()
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			orbit_distance = minf(1200.0, orbit_distance * (1.0 + zoom_speed))
			_apply_orbit()


func _process(delta: float) -> void:
	if mode == Mode.WALK:
		var dir := Vector3.ZERO
		if Input.is_action_pressed("ui_up"):
			dir -= transform.basis.z
		if Input.is_action_pressed("ui_down"):
			dir += transform.basis.z
		if Input.is_action_pressed("ui_left"):
			dir -= transform.basis.x
		if Input.is_action_pressed("ui_right"):
			dir += transform.basis.x
		global_position += dir.normalized() * walk_speed * delta
		_camera.rotation = Vector3(_pitch, _yaw, 0.0)


func _apply_orbit() -> void:
	if _camera == null:
		return
	var offset := Vector3(
		sin(_yaw) * cos(_pitch),
		-sin(_pitch),
		cos(_yaw) * cos(_pitch)
	) * orbit_distance
	_camera.global_position = Vector3(0, orbit_height, 0) + offset
	_camera.look_at(Vector3(0, orbit_height * 0.3, 0), Vector3.UP)
