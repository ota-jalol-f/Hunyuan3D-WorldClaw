# Android ko'prigi — AICore / Gemini Nano

`IntentPlanner.kt` — Godot Android plugini (`AICoreBridge` singletoni). U Intent
bosqichini bajaradi: matnli promptdan `scene_plan` JSON (`docs/scene-plan-schema.json`).

## Qanday ishlaydi

- Godot GDScript `Engine.get_singleton("AICoreBridge").plan_scene(prompt, size)`
  ni chaqiradi va JSON matn oladi.
- **Faza 1:** to'liq oflayn `fallbackPlan` — determinlashgan, chip talab qilmaydi,
  referens `scene_plan.py` bilan bir xil qoidalar.
- **Faza 2:** `plan_scene` ichida AICore/Gemini Nano (ML Kit GenAI) chaqiruvi
  yoqiladi; Nano `buildPrompt` ko'rsatmasi bo'yicha sxemaga mos JSON qaytaradi,
  `validate` o'tmasa `fallbackPlan` ga tushadi.

## Integratsiya (qisqacha)

1. Godot Android plagin sifatida qadoqlash (`GodotPlugin`), `AndroidManifest`
   `<meta-data name="org.godotengine.plugin.v2.AICoreBridge" .../>`.
2. Bog'liqliklar (Faza 2): AICore-backed ML Kit GenAI, `org.json` (mavjud).
3. NPU/AICore imtiyozlari qurilma xizmati orqali; qo'shimcha model yuklanmaydi.

Bu skelet — haqiqiy Nano API sirtini Faza 2 da ulash uchun aniq joy
(`TODO(Faza 2)`) bilan belgilangan. Oflayn yo'l to'liq ishlaydi.
