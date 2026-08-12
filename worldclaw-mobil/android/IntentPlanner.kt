package uz.worldclaw.mobil

import org.godotengine.godot.Godot
import org.godotengine.godot.plugin.GodotPlugin
import org.godotengine.godot.plugin.UsedByGodot
import org.json.JSONArray
import org.json.JSONObject

/**
 * AICoreBridge — Intent bosqichi (qurilma ichida Gemini Nano / AICore).
 *
 * Godot bu singletonni `Engine.get_singleton("AICoreBridge")` orqali topadi va
 * `plan_scene(prompt, size)` ni chaqiradi. Natija — `scene_plan` sxemasidagi
 * JSON matn (docs/scene-plan-schema.json).
 *
 * Qurilmada asosiy yo'l — Google AICore'dagi Gemini Nano'ni ML Kit GenAI orqali
 * chaqirish (structured/constrained output bilan). AICore mavjud bo'lmasa yoki
 * xato bersa, `fallbackPlan` ishlaydi — u to'liq oflayn va determinlashgan
 * (referens `scene_plan.py` bilan bir xil qoidalar).
 */
class AICoreBridge(godot: Godot) : GodotPlugin(godot) {

    override fun getPluginName(): String = "AICoreBridge"

    /**
     * Godotdan chaqiriladi. Faza 1 da sinxron fallback qaytaradi; Faza 2 da
     * bu yerga haqiqiy Nano chaqiruvi (coroutine bilan) ulanadi va natija
     * `emitSignal` orqali asinxron yuboriladi.
     */
    @UsedByGodot
    fun plan_scene(prompt: String, size: Int): String {
        return try {
            // TODO(Faza 2): AICore/Gemini Nano — quyidagi shakl bo'yicha:
            //   val model = Generation.getClient(GenerationConfig(...))
            //   val out = model.generateContent(buildPrompt(prompt, size))
            //   validated(out.text) ?: fallbackPlan(prompt, size)
            // Hozircha to'g'ridan-to'g'ri oflayn reja:
            fallbackPlan(prompt, size)
        } catch (t: Throwable) {
            fallbackPlan(prompt, size)
        }
    }

    /**
     * Faza 2 — refine sikli uchun sifat bahosi (Gemini Nano multimodal).
     *
     * Godot renderni PNG sifatida beradi va joriy metrikalarni uzatadi. Nano
     * renderni "ko'rib" sifat/kamchiliklarni qaytaradi. Bu skeletda oddiy
     * zaxira: metrikadagi `score` bo'yicha qaror. Chiqish JSON:
     *   { "accept": bool, "score": float, "notes": [..], "density_scale", "water_delta" }
     */
    @UsedByGodot
    fun evaluate_scene(metricsJson: String, pngPath: String): String {
        return try {
            // TODO(Faza 2): Nano multimodal — pngPath rasmini + metricsJson ni
            // yuborib sifatli fikr olish. Hozircha metrikaga asoslangan zaxira:
            val m = JSONObject(metricsJson)
            val score = m.optDouble("score", 0.0)
            JSONObject()
                .put("accept", score >= 0.85)
                .put("score", score)
                .put("notes", JSONArray())
                .put("density_scale", m.optDouble("density_scale", 1.0))
                .put("water_delta", m.optDouble("water_delta", 0.0))
                .toString()
        } catch (t: Throwable) {
            JSONObject().put("accept", true).put("score", 1.0).toString()
        }
    }

    /** Nano uchun ko'rsatma — faqat sxemaga mos JSON chiqarishi shart. */
    private fun buildPrompt(userPrompt: String, size: Int): String = """
        Siz 3D dunyo rejalovchisiz. Foydalanuvchi tavsifidan FAQAT JSON qaytaring.
        Sxema: { "prompt", "terrain": { "biome"(snow|desert|island|canyon|volcano|grass),
        "seed", "size", "world_scale", "height_scale", "mountain_strength"(0..1),
        "water_level"(0..1), "roughness"(0..1) }, "scatter": [ { "kind"(tree|house|rock|
        fence|torch|cactus|palm), "density"(0..1), "min_height", "max_height",
        "max_slope", "avoid_water" } ], "style", "notes" }.
        size = $size. Tavsif: "$userPrompt"
    """.trimIndent()

    // --- Oflayn zaxira rejalovchi (referens scene_plan.py bilan bir xil) -----

    private val biomeKeywords = mapOf(
        "snow" to listOf("snow", "qor", "ice", "muz", "winter", "qish", "frozen", "sovuq"),
        "desert" to listOf("desert", "sahro", "dune", "qum", "sand", "arid"),
        "island" to listOf("island", "orol", "ocean", "sea", "dengiz", "beach", "tropical"),
        "canyon" to listOf("canyon", "kanyon", "gorge", "mesa", "cliff", "jarlik"),
        "volcano" to listOf("volcano", "vulqon", "lava", "ember", "magma", "caldera"),
        "grass" to listOf("grass", "forest", "o'rmon", "meadow", "valley", "vodiy", "green"),
    )

    private val biomeTerrain = mapOf(
        "snow" to doubleArrayOf(0.75, 80.0, 0.28, 0.5),
        "desert" to doubleArrayOf(0.35, 40.0, 0.0, 0.55),
        "island" to doubleArrayOf(0.45, 55.0, 0.42, 0.5),
        "canyon" to doubleArrayOf(0.85, 90.0, 0.15, 0.65),
        "volcano" to doubleArrayOf(0.8, 95.0, 0.1, 0.6),
        "grass" to doubleArrayOf(0.5, 50.0, 0.25, 0.5),
    )

    // kind, density, min_h, max_h, max_slope
    private val biomeScatter = mapOf(
        "snow" to listOf(
            arrayOf("tree", 0.05, 0.30, 0.75, 0.5),
            arrayOf("house", 0.004, 0.30, 0.55, 0.25),
            arrayOf("rock", 0.02, 0.28, 0.95, 0.8),
            arrayOf("torch", 0.003, 0.30, 0.55, 0.3),
            arrayOf("fence", 0.01, 0.30, 0.55, 0.3),
        ),
        "desert" to listOf(
            arrayOf("cactus", 0.03, 0.30, 0.7, 0.4),
            arrayOf("rock", 0.03, 0.28, 0.95, 0.9),
            arrayOf("house", 0.002, 0.30, 0.5, 0.2),
        ),
        "island" to listOf(
            arrayOf("palm", 0.04, 0.30, 0.6, 0.5),
            arrayOf("rock", 0.02, 0.29, 0.9, 0.9),
            arrayOf("house", 0.003, 0.31, 0.5, 0.2),
        ),
        "canyon" to listOf(
            arrayOf("rock", 0.05, 0.20, 0.98, 1.0),
            arrayOf("cactus", 0.015, 0.25, 0.6, 0.5),
        ),
        "volcano" to listOf(
            arrayOf("rock", 0.06, 0.20, 0.98, 1.0),
            arrayOf("torch", 0.004, 0.30, 0.7, 0.5),
        ),
        "grass" to listOf(
            arrayOf("tree", 0.08, 0.30, 0.8, 0.6),
            arrayOf("house", 0.004, 0.30, 0.5, 0.25),
            arrayOf("rock", 0.02, 0.29, 0.95, 0.9),
            arrayOf("fence", 0.012, 0.30, 0.5, 0.3),
        ),
    )

    private fun stableSeed(text: String): Long {
        var h = 2166136261L
        for (ch in text) {
            h = ((h xor ch.code.toLong()) * 16777619L) and 0xFFFFFFFFL
        }
        return h
    }

    private fun detectBiome(prompt: String): String {
        val low = prompt.lowercase()
        var best = "grass"; var bestHits = 0
        for ((biome, words) in biomeKeywords) {
            val hits = words.count { low.contains(it) }
            if (hits > bestHits) { best = biome; bestHits = hits }
        }
        return best
    }

    private fun fallbackPlan(prompt: String, size: Int): String {
        val biome = detectBiome(prompt)
        val t = biomeTerrain.getValue(biome)
        val terrain = JSONObject()
            .put("biome", biome)
            .put("seed", stableSeed(prompt))
            .put("size", size)
            .put("world_scale", 400.0)
            .put("mountain_strength", t[0])
            .put("height_scale", t[1])
            .put("water_level", t[2])
            .put("roughness", t[3])

        val scatter = JSONArray()
        for (r in biomeScatter.getValue(biome)) {
            scatter.put(
                JSONObject()
                    .put("kind", r[0] as String)
                    .put("density", r[1] as Double)
                    .put("min_height", r[2] as Double)
                    .put("max_height", r[3] as Double)
                    .put("max_slope", r[4] as Double)
                    .put("avoid_water", true)
            )
        }

        return JSONObject()
            .put("prompt", prompt)
            .put("terrain", terrain)
            .put("scatter", scatter)
            .put("style", "cartoon")
            .put("notes", "Kotlin oflayn zaxira rejalovchi; biom: $biome")
            .toString()
    }
}
