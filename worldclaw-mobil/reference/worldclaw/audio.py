"""Ovoz/musiqa — biomga xos generativ soundscape va musiqa.

MUHIM: sample'lar saqlanmaydi — sintez qilinadi (assetsiz, on-device'ga qulay).
Qurilmада Godot `AudioStreamGenerator` (yoki NPU audio model) bilan; bu referens
faqat stdlib bilan sintez qilib WAV yozadi, determinlashgan (seed).

Qatlamlar: ambient (shamol/to'lqin/gumburlash) + generativ musiqa (pentatonik
melodiya + dron), biomга ko'ra kayfiyat/temp/kalit.
"""

from __future__ import annotations

import math
import struct
import wave

RATE = 22050

# Biom -> musiqa/ambient konfiguratsiyasi.
BIOME_AUDIO = {
    "snow":    {"root": 220.00, "scale": "minor", "bpm": 64, "wind": 0.55, "extra": "shimmer"},
    "desert":  {"root": 196.00, "scale": "major", "bpm": 72, "wind": 0.60, "extra": "dry"},
    "island":  {"root": 261.63, "scale": "major", "bpm": 96, "wind": 0.40, "extra": "waves"},
    "canyon":  {"root": 174.61, "scale": "minor", "bpm": 60, "wind": 0.50, "extra": "drone"},
    "volcano": {"root": 146.83, "scale": "minor", "bpm": 54, "wind": 0.50, "extra": "rumble"},
    "grass":   {"root": 246.94, "scale": "major", "bpm": 88, "wind": 0.35, "extra": "birds"},
}
_SCALES = {"major": [0, 2, 4, 7, 9], "minor": [0, 3, 5, 7, 10]}


class _Rng:
    __slots__ = ("s",)
    def __init__(self, seed: int) -> None:
        self.s = (seed ^ 0x9E3779B1) & 0xFFFFFFFF
    def unit(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.s / 4294967296.0


def _tri(phase: float) -> float:
    """Uchburchak to'lqin [-1,1] — sinusdan boyroq tembr."""
    p = phase % 1.0
    return 4.0 * abs(p - 0.5) - 1.0


def _env(i: int, n: int, attack: float, release: float) -> float:
    """Oddiy hujum/so'nish konverti."""
    a = int(n * attack)
    r = int(n * release)
    if i < a:
        return i / max(1, a)
    if i > n - r:
        return max(0.0, (n - i) / max(1, r))
    return 1.0


def _add_note(buf: list[float], start: int, dur: int, freq: float, amp: float) -> None:
    n = len(buf)
    for i in range(dur):
        j = start + i
        if j >= n:
            break
        buf[j] += _tri(freq * j / RATE) * amp * _env(i, dur, 0.02, 0.4)


def _add_ambient(buf: list[float], biome: str, cfg: dict, seed: int) -> None:
    n = len(buf)
    rng = _Rng(seed ^ 0xA11CE)
    wind_amp = cfg["wind"]
    lp = 0.0
    extra = cfg["extra"]
    for i in range(n):
        t = i / RATE
        white = rng.unit() * 2.0 - 1.0
        lp += (white - lp) * 0.05                 # bir-polyusли past o'tkazgich (shamol)
        swell = 0.6 + 0.4 * math.sin(t * 0.4)
        s = lp * wind_amp * swell * 0.5
        if extra == "waves":                      # to'lqin — sekin amplituda modulatsiya
            s += lp * 0.4 * (0.5 + 0.5 * math.sin(t * 0.8))
        elif extra == "rumble":                   # past gumburlash
            s += math.sin(2 * math.pi * 48 * t) * 0.18 * (0.7 + 0.3 * math.sin(t * 0.6))
            s += lp * 0.3
        elif extra == "drone":
            s += math.sin(2 * math.pi * cfg["root"] * 0.5 * t) * 0.08
        elif extra == "shimmer":                  # yuqori jimirlash
            s += math.sin(2 * math.pi * cfg["root"] * 4 * t) * 0.03 * (0.5 + 0.5 * math.sin(t * 3))
        buf[i] += s


def _add_birds(buf: list[float], cfg: dict, seed: int) -> None:
    """Qisqa qush chiyillashи (grass)."""
    n = len(buf)
    rng = _Rng(seed ^ 0xB18D)
    t = 0.0
    while t < n / RATE - 0.5:
        t += 0.6 + rng.unit() * 1.8
        start = int(t * RATE)
        f0 = 1800 + rng.unit() * 1400
        dur = int(0.08 * RATE)
        for i in range(dur):
            j = start + i
            if j >= n:
                break
            f = f0 * (1.0 + 0.3 * i / dur)        # yuqoriга sirg'anish
            buf[j] += math.sin(2 * math.pi * f * i / RATE) * 0.12 * _env(i, dur, 0.1, 0.5)


def _add_music(buf: list[float], biome: str, cfg: dict, seed: int) -> None:
    n = len(buf)
    scale = _SCALES[cfg["scale"]]
    root = cfg["root"]
    beat = int(60.0 / cfg["bpm"] * RATE)
    rng = _Rng(seed ^ 0x3EED)

    # Dron akkord (root + kvinta), butun davomiylik.
    for i in range(n):
        t = i / RATE
        buf[i] += math.sin(2 * math.pi * root * 0.5 * t) * 0.05
        buf[i] += math.sin(2 * math.pi * root * 0.75 * t) * 0.035

    # Melodiya — pentatonikда seedlangan sayr.
    degree = 0
    pos = 0
    while pos < n:
        degree = max(0, min(len(scale) * 2 - 1, degree + int(rng.unit() * 5) - 2))
        octave = degree // len(scale)
        semis = scale[degree % len(scale)] + 12 * octave
        freq = root * (2.0 ** (semis / 12.0))
        length = beat if rng.unit() > 0.3 else beat // 2
        if rng.unit() > 0.15:                     # ba'zan pauza
            _add_note(buf, pos, length, freq, 0.22)
        pos += length


def _to_int16(buf: list[float]) -> list[int]:
    peak = max(1e-6, max(abs(x) for x in buf))
    g = 0.89 / peak
    out = []
    for x in buf:
        v = int(x * g * 32767)
        out.append(-32768 if v < -32768 else 32767 if v > 32767 else v)
    return out


def generate_soundscape(biome: str, *, seed: int = 0, seconds: float = 10.0) -> list[int]:
    """Biom uchun to'liq soundscape (ambient + musiqa), int16 sample'lar."""
    cfg = BIOME_AUDIO.get(biome, BIOME_AUDIO["grass"])
    n = int(seconds * RATE)
    buf = [0.0] * n
    _add_ambient(buf, biome, cfg, seed)
    _add_music(buf, biome, cfg, seed)
    if cfg["extra"] == "birds":
        _add_birds(buf, cfg, seed)
    return _to_int16(buf)


def write_wav(path: str, samples: list[int], rate: int = RATE) -> None:
    w = wave.open(path, "w")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    w.close()
