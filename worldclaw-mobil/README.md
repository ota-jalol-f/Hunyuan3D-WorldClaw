# WorldClaw Mobil

Galaxy S26 Ultra uchun **qurilma ichida (on-device)** ishlaydigan AI 3D dunyo
generatori. Bitta matnli promptdan — o'rganib bo'ladigan 3D dunyo. Tencent
WorldClaw usulining mobil, oflayn, real-vaqt moslashuvi.

> **Faza 1 (MVP) — ushbu skelet.** Ishlaydigan pipeline: prompt → reja →
> relyef → obyektlar → ko'rish. To'liq arxitektura hujjati loyihada alohida.

## Asosiy qarorlar

- **On-device** — internetsiz, maxfiy, kechikishsiz.
- **To'g'ridan-3D** — geometriya oraliq 2D rasm bosqichisiz quriladi.
- **Tekstura generativ** — sirtlar assetdan olinmaydi, qurilmada generatsiya
  qilinadi (Faza 2, NPU).
- **Kesh birinchi** — bir xil `(prompt, seed, size)` qayta hisoblanmaydi.

## Pipeline (arxitektura oqimi)

| Bosqich | Modul | Chip | Holat |
|---|---|---|---|
| 1. Intent (niyat → reja) | AICore / Gemini Nano | AICore | Faza 1: oflayn zaxira rejalovchi |
| 2. Terrain (relyef) | `TerrainCompute` / `TerrainGenerator` | GPU compute + CPU zaxira | Faza 1.5: GPU yo'li ulandi |
| 3. Assets + Scatter | `ScatterSystem` | GPU instancing | Faza 1: primitiv geometriya |
| 4. Refine (agentli sikl) | `RefinementAgent` / Nano multimodal | AICore | Faza 2: sikl ishlaydi |
| + Teksturalar (generativ) | `TextureGenerator` | NPU (Faza 2) | procedural zaxira |
| + Ko'rinish kanallari | depth / normal / instance | GPU G-bufer | referens tayyor |
| + Generativ mesh | `MeshFactory` / `mesh` | CPU (NPU keyin) | procedural shakllar |
| + Fizika (Yer) | `WorldPhysics` / `physics` | fizika serveri | 9.81, to'qnashuv, cho'kish |
| + 3D eksport (glTF) | `WorldExporter` / `gltf` | — | .glb, istalgan ko'ruvchi |
| + Izometrik 3D preview | `iso` | — | referens (Godotsiz) |

Relyefning **noise funksiyasi Python, GDScript va GLSL'da aynan bir xil**
(32-bitlik bit-hash), shuning uchun CPU va GPU yo'llari bir xil dunyoni beradi —
GPU mavjud bo'lmasa CPU zaxirasiga muammosiz o'tiladi.

## Tuzilma

```
worldclaw-mobil/
├─ reference/          Pure-Python referens (bu yerda ishga tushib TEKSHIRILADI)
│  ├─ worldclaw/       noise · terrain · scene_plan · scatter · render · pipeline
│  ├─ generate_demo.py CLI: promptdan preview PNG
│  └─ test_pipeline.py 27 test (deterministik, chegaralar, kesh, scatter)
├─ godot/              Godot 4 loyihasi (Android/Vulkan)
│  ├─ project.godot    mobil renderer sozlamalari
│  ├─ scenes/main.tscn sahna daraxti
│  ├─ scripts/         GameController · TerrainGenerator · ScatterSystem ·
│  │                   ScenePlan · CameraRig  (referens mantiqning aynan nusxasi)
│  ├─ shaders/         terrain_height.glsl  (Faza 1.5 GPU compute)
│  └─ assets/          library.json (asset manifesti)
├─ android/            IntentPlanner.kt  (AICore/Gemini Nano ko'prigi)
├─ docs/               scene-plan-schema.json  (pipeline shartnomasi)
└─ examples/           plan_snowy_village.json
```

## Referensni ishga tushirish (kutubxonasiz)

```bash
cd reference
python3 test_pipeline.py                 # 27 test
python3 generate_demo.py --all --out _out # barcha biomlar -> PNG
python3 generate_demo.py "qorli qishloq tog'lar"
```

Referens — qurilmadagi tizimning mantiqiy nusxasi. GDScript va Kotlin
modullari aynan shu algoritmlarni takrorlaydi, shuning uchun referens
testlari qurilma xulq-atvorini ham tasdiqlaydi.

## Godot loyihasini ochish

1. Godot 4.3+ oching → *Import* → `godot/` papkasini tanlang.
2. `scenes/main.tscn` ni ishga tushiring (F5).
3. Android eksporti: *Project → Export → Android* (Gradle build yoqilgan).

Sukut bo'yicha `AICoreBridge` singletoni bo'lmasa (masalan, desktop), GDScript
oflayn rejalovchisi ishlaydi — loyiha har joyda ochiladi.

## Fazalar holati

- **Faza 1** ✅ — reja → relyef → obyektlar → ko'rish (referens 27/27 test).
- **Faza 1.5** ✅ (ulandi) — `TerrainCompute.gd` + `terrain_height.glsl` GPU
  compute yo'li, CPU zaxira bilan. *Godot editorda va qurilmada sinash kerak.*
- **Faza 2** ✅ (referens) — agentli refine sikli (`RefinementAgent` /
  `critic` + `refine`), generativ teksturalar (`TextureGenerator` / `texture`),
  ko'rinish kanallari (depth/normal/instance). Nano multimodal ko'prigi
  (`evaluate_scene`) ulash uchun tayyor.
- **Faza 3** — on-device generativ mesh, dunyoni saqlash/eksport (glTF).

- **Faza 3** ⏳ (davom etmoqda):
  - **3D eksport va ko'rish** ✅ — `.glb` eksport (`WorldExporter` / `gltf`),
    izometrik 3D preview (`iso`).
  - **Generativ mesh** ✅ (procedural) — `mesh.py` / `MeshFactory.gd`:
    primitiv konus/quti o'rniga haqiqiy shakllar (shoxli daraxt, tomли uy,
    qirrali tosh, qo'lли kaktus…), seed variatsiyasi, variantlar ulashiladi.
  - **Neyron image-to-3D** ⏳ — NPU distillangan model (`neural_mesh` stub).
    Eng og'ir, R&D qismi; procedural backend hozir ishlaydi.
  - **Yer fizikasi** ✅ — `physics.py` / `WorldPhysics.gd`: tortishish 9.81,
    material zichligi/ishqalanish/qaytish, relyef to'qnashuvi (HeightMapShape3D),
    dinamik jismlar (dumalab tushadi), qiyalikда sirg'anish, cho'kish.
  - **Relyef detali** ✅ — yuqori chastotali detal qatlami (uch impl bir xil).

Mesh shakllarini ko'rish: `render_mesh_lineup` (referens) yoki `.glb` ni oching.
Fizikани sinash: `test_pipeline.py` (erkin tushish, cho'kish, tunnel, qaytish).

### Faza 2–3 ni sinash

```bash
cd reference
python3 generate_demo.py --refine "qorli qishloq"        # agentli sifat sikli
python3 generate_demo.py --channels --all --out _out     # depth/normal/instance + teksturalar
python3 generate_demo.py --glb --iso "tropik orol"       # .glb 3D fayl + izometrik preview
```

**"Tushunarli 3D" qachon?** Haqiqiy 3D Faza 1'dan Godot kodida bor (relyef
mesh + orbit/yurish kamera). Godotsiz ko'rish uchun: `--iso` izometrik preview
beradi, `--glb` esa istalgan 3D ko'ruvchida (Blender, brauzer, telefon)
ochiladigan fayl beradi. Sifat fazalar bilan oshadi: blokli → teksturali →
generativ mesh.

### Godot skripting eslatmasi

GDScript va GLSL kodi bu muhitda Godot editori bo'lmagani uchun kompilyatorda
tekshirilmagan. Ular verifikatsiya qilingan Python referens mantiqini aynan
takrorlaydi; Godot 4.3+ da ochib bir marta ishga tushirish tavsiya etiladi.
