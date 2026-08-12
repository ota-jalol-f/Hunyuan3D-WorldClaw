#[compute]
#version 450

// WorldClaw Mobil — relyef balandligi compute shaderi (Faza 1.5 GPU yo'li).
//
// Bu TerrainGenerator.gd (va referens terrain.py) mantiqining GPU nusxasi.
// RenderingDevice orqali dispatch qilinadi; natija Heights buferiga yoziladi,
// so'ng ArrayMesh yoki heightmap teksturasi sifatida o'qiladi.
//
// Ishga tushirish: local_size 8x8, guruhlar soni = ceil(size/8) har o'qda.

layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

layout(set = 0, binding = 0, std430) restrict buffer Heights {
    float data[];
};

layout(push_constant, std430) uniform Params {
    int size;
    int seed;
    int biome;            // 0 snow, 1 desert, 2 island, 3 canyon, 4 volcano, 5 grass
    float mountain_strength;
    float roughness;
    float base_freq;
    float _pad0;
    float _pad1;
} p;

// --- permutatsiyasiz hash-asosidagi qiymat-noise (GPU'ga qulay) --------------
uint hash_u(uint x) {
    x ^= x >> 16; x *= 0x7feb352dU;
    x ^= x >> 15; x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}

float grad_val(int ix, int iy, int seed) {
    uint h = hash_u(uint(ix) * 374761393U + uint(iy) * 668265263U + uint(seed));
    return (float(h & 0xFFFFU) / 32767.5) - 1.0;
}

float fade(float t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

float value_noise(vec2 pos, int seed) {
    int x0 = int(floor(pos.x));
    int y0 = int(floor(pos.y));
    float fx = fade(pos.x - float(x0));
    float fy = fade(pos.y - float(y0));
    float v00 = grad_val(x0,     y0,     seed);
    float v10 = grad_val(x0 + 1, y0,     seed);
    float v01 = grad_val(x0,     y0 + 1, seed);
    float v11 = grad_val(x0 + 1, y0 + 1, seed);
    float top = mix(v00, v10, fx);
    float bot = mix(v01, v11, fx);
    return mix(top, bot, fy);
}

float fbm(vec2 pos, int seed, float gain) {
    float amp = 1.0, freq = 1.0, total = 0.0, norm = 0.0;
    for (int i = 0; i < 5; i++) {
        total += amp * value_noise(pos * freq, seed);
        norm += amp; amp *= gain; freq *= 2.0;
    }
    return norm > 0.0 ? total / norm : 0.0;
}

float ridged(vec2 pos, int seed, float gain) {
    float amp = 1.0, freq = 1.0, total = 0.0, norm = 0.0;
    for (int i = 0; i < 5; i++) {
        float v = 1.0 - abs(value_noise(pos * freq, seed));
        v *= v;
        total += amp * v;
        norm += amp; amp *= gain; freq *= 2.0;
    }
    return norm > 0.0 ? total / norm : 0.0;
}

float biome_shape(float base, float mountains, float strength) {
    float base01 = base * 0.5 + 0.5;
    if (p.biome == 3) {                       // canyon
        float carve = 1.0 - mountains;
        return clamp(0.6 + base01 * 0.2 - carve * strength * 0.55, 0.0, 1.0);
    }
    if (p.biome == 4) {                       // volcano
        return clamp(base01 * 0.3 + mountains * strength, 0.0, 1.0);
    }
    return clamp(base01 * (1.0 - strength * 0.5) + mountains * strength, 0.0, 1.0);
}

void main() {
    uint gx = gl_GlobalInvocationID.x;
    uint gy = gl_GlobalInvocationID.y;
    if (gx >= uint(p.size) || gy >= uint(p.size)) return;

    float inv = 1.0 / float(max(1, p.size));
    vec2 n = vec2(float(gx), float(gy)) * inv * p.base_freq;

    float base = fbm(n, p.seed, p.roughness);
    float mountains = ridged(n, p.seed ^ 0x5A5A5A5A, p.roughness);

    float h;
    if (p.biome == 2) {                       // island
        vec2 c = (vec2(float(gx), float(gy)) * inv - 0.5) * 2.0;
        float dome = clamp(1.15 - length(c), 0.0, 1.0);
        h = dome * (0.5 + mountains * p.mountain_strength);
        h += (base * 0.5 + 0.5) * 0.05;
        h = clamp(h, 0.0, 1.0);
    } else {
        h = biome_shape(base, mountains, p.mountain_strength);
    }

    data[gy * uint(p.size) + gx] = h;
}
