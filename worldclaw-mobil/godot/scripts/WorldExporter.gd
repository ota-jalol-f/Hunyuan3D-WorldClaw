extends RefCounted
class_name WorldExporter
## Faza 3 — qurilgan dunyoni .glb faylga eksport (Godot o'rnatilgan GLTFDocument).
##
## Chiqish .glb ni istalgan 3D ko'ruvchida ochish mumkin (Blender, brauzer,
## telefon galereyasi, Windows 3D Viewer). Referens `gltf.py` bilan bir xil rol.
##
## Android'da `user://` yo'lidan foydalaning; keyin Storage Access Framework
## orqali ulashish/saqlash mumkin.

## `root` (relyef + scatter tugunlarini o'z ichiga olgan Node3D) ni .glb ga yozadi.
static func export_glb(root: Node3D, path: String) -> Error:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_scene(root, state)
	if err != OK:
		push_error("glTF: sahna o'qilmadi (kod %d)" % err)
		return err
	err = doc.write_to_filesystem(state, path)
	if err == OK:
		print("[WorldClaw] glTF yozildi: ", path)
	else:
		push_error("glTF: yozib bo'lmadi (kod %d)" % err)
	return err


## Faqat relyef va obyektlarni o'z ichiga olgan vaqtinchalik ildizni yig'ib
## eksport qiladi (UI/kamera fayltga tushmaydi).
static func export_world(terrain_holder: Node3D, scatter: Node3D, path: String) -> Error:
	var root := Node3D.new()
	root.name = "WorldClawScene"
	var t := terrain_holder.duplicate()
	var s := scatter.duplicate()
	root.add_child(t)
	root.add_child(s)
	var err := export_glb(root, path)
	root.free()
	return err
