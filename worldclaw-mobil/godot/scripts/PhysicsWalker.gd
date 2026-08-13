extends CharacterBody3D
class_name PhysicsWalker
## Faza 3 — character controller (yurish) Yer fizikasi bilan.
##
## Referens `physics.Character` bilan bir xil xulq: gravitatsiya 9.81, relyefga
## yopishadi, tik qiyalikда (>45°) ko'tarilmaydi, relyefdan o'tmaydi.
## Relyef StaticBody3D (HeightMapShape3D) bilan to'qnashadi.

@export var walk_speed: float = 30.0
@export var gravity: float = 9.81
@export var max_slope_deg: float = 45.0
@export var jump_speed: float = 14.0

var _move := Vector2.ZERO   # (x, z) yo'nalish; UI joystick yoki klaviatura beradi


func _ready() -> void:
	floor_max_angle = deg_to_rad(max_slope_deg)
	floor_snap_length = 1.5
	# Kapsula kollayder (agar sahnaда berilmagan bo'lsa).
	if get_child_count() == 0:
		var col := CollisionShape3D.new()
		var cap := CapsuleShape3D.new()
		cap.radius = 1.5
		cap.height = 6.0
		col.shape = cap
		add_child(col)


func set_move(dir: Vector2) -> void:
	_move = dir


func _physics_process(delta: float) -> void:
	# Kirish (joystick yo'q bo'lsa klaviaturadan).
	var dir := _move
	if dir == Vector2.ZERO:
		dir = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")

	# Gorizontal tezlik.
	velocity.x = dir.x * walk_speed
	velocity.z = dir.y * walk_speed

	# Gravitatsiya.
	if is_on_floor():
		if Input.is_action_just_pressed("ui_accept"):
			velocity.y = jump_speed
		else:
			velocity.y = -0.1        # yerга bosib turish
	else:
		velocity.y -= gravity * delta

	move_and_slide()   # floor_max_angle tik qiyalikда sirg'anadi
