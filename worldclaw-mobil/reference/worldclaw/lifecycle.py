"""Hayot sikli — kun/tun, fasllar, ob-havo va ekotizim (reallikka yaqin).

Modellar:
  * Kun/tun — soat 0..24, quyosh balandligi.
  * Fasllar — yil kuni (0..360), harorat sinusoidasi (mavsumiy + sutkalik).
  * Ob-havo — haroratga bog'liq (sovuqда qor, iliqда yomg'ir), determinlashgan.
  * Ekotizim — Lotka-Volterra yirtqich-o'lja + o'simlik biomassasi (logistik
    o'sish, mavsumga bog'liq). Populyatsiyalar tebranadi (haqiqiy dinamika).

Qurilmада `LifecycleDirector.gd` bu holatni yorug'lik/rang/zarrachalar/o'simlik
zichligiga bog'laydi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

DAYS_PER_YEAR = 360.0
SEASONS = ("bahor", "yoz", "kuz", "qish")

# Biom -> (o'rtacha yillik harorat °C, mavsumiy amplituda).
_BIOME_CLIMATE = {
    "snow": (-8.0, 14.0), "desert": (26.0, 12.0), "island": (24.0, 6.0),
    "canyon": (18.0, 16.0), "volcano": (20.0, 10.0), "grass": (12.0, 15.0),
}


@dataclass
class EnvState:
    biome: str = "grass"
    day: float = 0.0                 # o'tgan kunlar (kasrли)
    time_of_day: float = 8.0         # soat 0..24
    day_of_year: float = 80.0        # 0..360 (80 ~ bahor)
    temperature: float = 12.0        # °C
    weather: str = "ochiq"           # ochiq / bulutli / yomg'ir / qor
    wind: tuple[float, float, float] = (1.0, 0.0, 2.0)   # (x, z, kuch m/s)
    # Ekotizim (nisbiy birliklar).
    vegetation: float = 0.6          # o'simlik biomassasi 0..1+
    herbivores: float = 0.4          # o'txo'rlar
    predators: float = 0.15          # yirtqichlar

    @property
    def season(self) -> str:
        return SEASONS[int(self.day_of_year / (DAYS_PER_YEAR / 4)) % 4]

    @property
    def is_night(self) -> bool:
        return self.time_of_day < 6.0 or self.time_of_day > 20.0

    @property
    def sun_elevation(self) -> float:
        """Quyosh balandligi [-1..1] (peshinда eng yuqori)."""
        return math.sin(math.pi * (self.time_of_day - 6.0) / 12.0)


# Lotka-Volterra + o'simlik koeffitsientlari (muvozanatли — populyatsiyalar
# musbat qoladi, mavsumiy majburlash bilan tebranadi).
# Muvozanat: herb* = PRED_DEATH/PRED_GAIN ≈ 0.36 (o'txo'rlar yetadigan daraja).
_VEG_GROWTH = 1.0
_VEG_CAP = 1.3
_GRAZE = 0.7
_HERB_GAIN = 0.8
_HERB_DEATH = 0.1
_PREDATION = 0.5
_PRED_GAIN = 0.6
_PRED_DEATH = 0.12
# O'z-o'zini cheklash (carrying capacity) — spiralning oldini oladi, barqaror
# mavsumiy tebranish beradi (Rosenzweig-MacArthur uslubida).
_SELF_HERB = 0.35
_SELF_PRED = 0.3


class LifecycleSim:
    """Muhit va ekotizimni vaqt bo'yicha yurituvchi."""

    def __init__(self, state: EnvState | None = None, *, seed: int = 0) -> None:
        self.state = state or EnvState()
        self._rng = (seed ^ 0x51F3) & 0xFFFFFFFF
        self._weather_timer = 0.0

    def _rand(self) -> float:
        self._rng = (self._rng * 1664525 + 1013904223) & 0xFFFFFFFF
        return self._rng / 4294967296.0

    def _update_temperature(self) -> None:
        s = self.state
        base, amp = _BIOME_CLIMATE.get(s.biome, (12.0, 15.0))
        # Mavsumiy (qish eng sovuq ~ day_of_year 270).
        seasonal = -amp * math.cos(2 * math.pi * (s.day_of_year - 15) / DAYS_PER_YEAR)
        diurnal = 5.0 * s.sun_elevation
        s.temperature = base + seasonal + diurnal

    def _update_weather(self, dt_days: float) -> None:
        self._weather_timer -= dt_days
        if self._weather_timer > 0:
            return
        self._weather_timer = 0.3 + self._rand() * 0.7   # har ~0.3-1 kun o'zgaradi
        s = self.state
        r = self._rand()
        if s.temperature < 1.0:
            s.weather = "qor" if r < 0.5 else ("bulutli" if r < 0.8 else "ochiq")
        elif r < 0.25:
            s.weather = "yomg'ir"
        elif r < 0.5:
            s.weather = "bulutli"
        else:
            s.weather = "ochiq"
        # Shamol biroz o'zgaradi.
        wx = math.cos(s.day_of_year * 0.1) * (1.5 + self._rand() * 3.0)
        wz = math.sin(s.day_of_year * 0.1) * (1.5 + self._rand() * 3.0)
        s.wind = (wx, wz, (wx * wx + wz * wz) ** 0.5)

    def _update_ecosystem(self, dt_days: float) -> None:
        s = self.state
        # Mavsumiy quyosh/namlik omili (yozда yuqori, qishда past).
        season_factor = 0.5 + 0.5 * math.cos(2 * math.pi * (s.day_of_year - 165) / DAYS_PER_YEAR)
        wet = 1.2 if s.weather in ("yomg'ir",) else (1.0 if s.weather == "bulutli" else 0.85)
        veg, herb, pred = s.vegetation, s.herbivores, s.predators

        # Ichki substepping — Euler barqarorligi uchun (katta dt_days da ham).
        steps = max(1, int(dt_days / 0.01))
        h = dt_days / steps
        for _ in range(steps):
            dveg = _VEG_GROWTH * season_factor * wet * veg * (1 - veg / _VEG_CAP) - _GRAZE * herb * veg
            dherb = (_HERB_GAIN * herb * veg - _HERB_DEATH * herb
                     - _PREDATION * pred * herb - _SELF_HERB * herb * herb)
            dpred = _PRED_GAIN * pred * herb - _PRED_DEATH * pred - _SELF_PRED * pred * pred
            veg = max(0.02, veg + dveg * h)
            herb = max(0.02, herb + dherb * h)
            pred = max(0.01, pred + dpred * h)

        s.vegetation, s.herbivores, s.predators = veg, herb, pred

    def step(self, dt_days: float) -> EnvState:
        """Muhitni dt_days kun oldinga suradi."""
        s = self.state
        s.day += dt_days
        s.day_of_year = (s.day_of_year + dt_days) % DAYS_PER_YEAR
        s.time_of_day = (s.time_of_day + dt_days * 24.0) % 24.0
        self._update_temperature()
        self._update_weather(dt_days)
        self._update_ecosystem(dt_days)
        return s

    def run(self, days: float, dt_days: float = 0.05) -> list[EnvState]:
        """Bir necha kun yurgizib, holat tarixini qaytaradi (kuzatuv/test uchun)."""
        from dataclasses import replace
        history = []
        n = int(days / dt_days)
        for _ in range(n):
            self.step(dt_days)
            history.append(replace(self.state))
        return history


def season_vegetation_scale(state: EnvState) -> float:
    """Faslга ko'ra ko'rinadigan o'simlik zichligi ko'paytirgichi (scatter uchun)."""
    base = {"bahor": 0.9, "yoz": 1.15, "kuz": 0.75, "qish": 0.35}[state.season]
    return base * min(1.3, 0.5 + state.vegetation)
