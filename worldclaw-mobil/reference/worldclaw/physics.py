"""Fizika — Yer fizikasiga maksimal yaqin qattiq jism simulyatsiyasi.

Verifikatsiya qilinadigan referens: tortishish (9.81 m/s²), relyef bilan
to'qnashuv, ishqalanish (Coulomb), qaytish (restitution), qiyalikда sirg'anish
va cho'kish (settling). Qurilmada bu Godot Jolt/PhysicsServer bilan bo'ladi
(`WorldPhysics.gd`); bu modul mantiqni va Yer-parametrlarini tekshiradi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .terrain import Heightmap

# Yer konstantalari.
GRAVITY = 9.81                     # m/s²
AIR_DRAG = 0.02                    # yengil havo qarshiligi (soddalashtirilgan)
WATER_DENSITY = 1000.0            # kg/m³
WATER_DRAG = 3.0                   # suvда qarshilik (havodan kuchli)
FLOW_COUPLING = 1.5                # suv oqimi jismni qanchalik tortadi
WIND_K = 0.6                       # shamol kuchi koeffitsienti

# Material zichligi (kg/m³, Yer).
DENSITY = {
    "rock": 2700.0, "house": 800.0, "tree": 700.0, "palm": 650.0,
    "cactus": 500.0, "torch": 600.0, "fence": 650.0,
}
# Coulomb ishqalanish koeffitsienti (material -> relyef).
FRICTION = {
    "rock": 0.6, "house": 0.9, "tree": 0.8, "palm": 0.8,
    "cactus": 0.7, "torch": 0.7, "fence": 0.8,
}
RESTITUTION = {
    "rock": 0.35, "house": 0.05, "tree": 0.1, "palm": 0.1,
    "cactus": 0.15, "torch": 0.1, "fence": 0.1,
}


@dataclass
class Body:
    kind: str
    x: float
    y: float
    z: float
    radius: float = 2.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    resting: bool = False

    @property
    def mass(self) -> float:
        vol = (4.0 / 3.0) * 3.14159265 * self.radius ** 3
        return DENSITY.get(self.kind, 1500.0) * vol

    @property
    def speed(self) -> float:
        return (self.vx * self.vx + self.vy * self.vy + self.vz * self.vz) ** 0.5


class TerrainField:
    """Relyefni fizika uchun dunyo koordinatasida taqdim etadi."""

    def __init__(self, hm: Heightmap) -> None:
        self.hm = hm
        self.size = hm.size
        self.cell = hm.spec.world_scale / hm.size
        self.half = hm.spec.world_scale * 0.5
        self.hs = hm.spec.height_scale

    def _sample_norm(self, gx: float, gy: float) -> float:
        """Bilinear normallashgan balandlik."""
        size = self.size
        x0 = int(gx); y0 = int(gy)
        x1 = min(size - 1, x0 + 1); y1 = min(size - 1, y0 + 1)
        x0 = max(0, min(size - 1, x0)); y0 = max(0, min(size - 1, y0))
        tx = gx - x0; ty = gy - y0
        h00 = self.hm.get(x0, y0); h10 = self.hm.get(x1, y0)
        h01 = self.hm.get(x0, y1); h11 = self.hm.get(x1, y1)
        top = h00 + (h10 - h00) * tx
        bot = h01 + (h11 - h01) * tx
        return top + (bot - top) * ty

    @property
    def water_y(self) -> float:
        return self.hm.spec.water_level * self.hs

    def height_at(self, x: float, z: float) -> float:
        gx = (x + self.half) / self.cell
        gy = (z + self.half) / self.cell
        return self._sample_norm(gx, gy) * self.hs

    def flow_at(self, x: float, z: float) -> tuple[float, float]:
        """Suv oqimi yo'nalishi — relyef qiyaligiga qarab pastga (gradient)."""
        d = self.cell
        hl = self.height_at(x - d, z); hr = self.height_at(x + d, z)
        hd = self.height_at(x, z - d); hu = self.height_at(x, z + d)
        fx = (hl - hr)
        fz = (hd - hu)
        m = (fx * fx + fz * fz) ** 0.5
        if m < 1e-6:
            return 0.0, 0.0
        return fx / m, fz / m

    def normal_at(self, x: float, z: float) -> tuple[float, float, float]:
        d = self.cell
        hl = self.height_at(x - d, z); hr = self.height_at(x + d, z)
        hd = self.height_at(x, z - d); hu = self.height_at(x, z + d)
        nx = (hl - hr) / (2 * d)
        nz = (hd - hu) / (2 * d)
        ny = 1.0
        inv = 1.0 / (nx * nx + ny * ny + nz * nz) ** 0.5
        return nx * inv, ny * inv, nz * inv


@dataclass
class Environment:
    """Muhit kuchlari — shamol va suv oqimi."""
    wind: tuple[float, float, float] = (0.0, 0.0, 0.0)   # m/s
    flow_speed: float = 0.0                              # suv oqimi tezligi (m/s)
    use_terrain_flow: bool = True                        # oqim relyef gradienti bo'yicha


@dataclass
class SimStats:
    steps: int = 0
    max_penetration: float = 0.0
    settled: int = 0
    history_y: list[float] = field(default_factory=list)   # bitta jismni kuzatish


def _submerged_fraction(b: "Body", water_y: float) -> float:
    """Sharsimon jismning suv ostiдаgi ulushi [0..1]."""
    if b.radius <= 0:
        return 0.0
    top = b.y + b.radius
    bottom = b.y - b.radius
    if bottom >= water_y:
        return 0.0
    if top <= water_y:
        return 1.0
    return (water_y - bottom) / (2.0 * b.radius)


def step(bodies: list[Body], field_: TerrainField, dt: float,
         env: "Environment | None" = None) -> float:
    """Bitta fizika qadami. Qaytaradi: shu qadamdagi maksimal penetratsiya."""
    max_pen = 0.0
    water_y = field_.water_y
    for b in bodies:
        if b.resting:
            continue
        density = DENSITY.get(b.kind, 1500.0)
        area = 3.14159265 * b.radius * b.radius
        # Tortishish.
        b.vy -= GRAVITY * dt

        f_sub = _submerged_fraction(b, water_y)
        if f_sub > 0.0:
            # Arximed ko'tarish kuchi: a = g * f * ρ_suv/ρ_jism (yuqoriga).
            b.vy += GRAVITY * f_sub * (WATER_DENSITY / density) * dt
            # Suv qarshiligi (havodan kuchli).
            wd = WATER_DRAG * f_sub * dt
            b.vx *= max(0.0, 1.0 - wd)
            b.vy *= max(0.0, 1.0 - wd)
            b.vz *= max(0.0, 1.0 - wd)
            # Suv oqimi jismni tortadi.
            if env is not None:
                fx = fz = 0.0
                if env.use_terrain_flow:
                    fx, fz = field_.flow_at(b.x, b.z)
                sp = env.flow_speed
                b.vx += (fx * sp - b.vx) * FLOW_COUPLING * f_sub * dt
                b.vz += (fz * sp - b.vz) * FLOW_COUPLING * f_sub * dt
        else:
            b.vx *= (1.0 - AIR_DRAG * dt)
            b.vy *= (1.0 - AIR_DRAG * dt)
            b.vz *= (1.0 - AIR_DRAG * dt)

        # Shamol — havoда (suv ustida) ta'sir qiladi; yengil/katta jism ko'proq.
        if env is not None and f_sub < 1.0:
            wx, wy, wz = env.wind
            m = max(1e-3, b.mass)
            k = WIND_K * area / m * (1.0 - f_sub)
            b.vx += (wx - b.vx) * k * dt
            b.vy += (wy - b.vy) * k * dt
            b.vz += (wz - b.vz) * k * dt

        # Semi-implicit Euler.
        b.x += b.vx * dt
        b.y += b.vy * dt
        b.z += b.vz * dt

        # Suzuvchi muvozanat — sekin, QISMAN suvда (muvozanat), oqim yo'q -> to'xtash.
        # To'liq suv ostида (f≈1) hali ko'tarish kuchi bor -> to'xtamaydi.
        no_flow = env is None or env.flow_speed <= 0.0
        if 0.02 < f_sub < 0.97 and b.speed < 0.06 and no_flow:
            b.vx = b.vy = b.vz = 0.0
            b.resting = True
            continue

        ground = field_.height_at(b.x, b.z)
        pen = (ground + b.radius) - b.y
        if pen > 0.0:                       # to'qnashuv
            max_pen = max(max_pen, pen)
            b.y = ground + b.radius         # pozitsiyani tuzatish
            nx, ny, nz = field_.normal_at(b.x, b.z)
            vn = b.vx * nx + b.vy * ny + b.vz * nz
            rest = RESTITUTION.get(b.kind, 0.2)
            mu = FRICTION.get(b.kind, 0.6)
            if vn < 0.0:                    # yerga qarab
                # Normal komponentni qaytarish (bounce).
                b.vx -= (1.0 + rest) * vn * nx
                b.vy -= (1.0 + rest) * vn * ny
                b.vz -= (1.0 + rest) * vn * nz
            # Tangensial ishqalanish (Coulomb, soddalashtirilgan).
            tvx = b.vx - (b.vx * nx + b.vy * ny + b.vz * nz) * nx
            tvy = b.vy - (b.vx * nx + b.vy * ny + b.vz * nz) * ny
            tvz = b.vz - (b.vx * nx + b.vy * ny + b.vz * nz) * nz
            damp = max(0.0, 1.0 - mu)
            b.vx = (b.vx - tvx) + tvx * damp
            b.vy = (b.vy - tvy) + tvy * damp
            b.vz = (b.vz - tvz) + tvz * damp
            # Cho'kish: sekin + barqaror qiyalik -> to'xtash.
            slope = (1.0 - ny)              # 0 tekis, ~1 tik
            if b.speed < 0.15 and slope < mu * 0.5:
                b.vx = b.vy = b.vz = 0.0
                b.resting = True
    return max_pen


def simulate(bodies: list[Body], field_: TerrainField, *, dt: float = 1.0 / 120.0,
             max_steps: int = 2000, track: int = 0, env: "Environment | None" = None) -> SimStats:
    """Barcha jismlar cho'kkuncha yoki max_steps gacha simulyatsiya."""
    stats = SimStats()
    for s in range(max_steps):
        pen = step(bodies, field_, dt, env)
        stats.max_penetration = max(stats.max_penetration, pen)
        if 0 <= track < len(bodies):
            stats.history_y.append(bodies[track].y)
        stats.steps = s + 1
        if all(b.resting for b in bodies):
            break
    stats.settled = sum(1 for b in bodies if b.resting)
    return stats


@dataclass
class Character:
    """Kinematik character controller — relyefда gravitatsiya bilan yuradi.

    Qurilmада Godot CharacterBody3D (`WorldPhysics` / CameraRig walk) bilan
    bir xil xulq: yerга yopishadi, tik qiyalikда ko'tarilmaydi (sirg'anadi),
    relyefdan o'tib ketmaydi.
    """
    x: float
    y: float
    z: float
    radius: float = 2.0
    height: float = 6.0
    vy: float = 0.0
    walk_speed: float = 30.0
    max_slope_deg: float = 45.0
    on_ground: bool = False

    @property
    def feet_y(self) -> float:
        return self.y - self.height * 0.5

    def update(self, field_: TerrainField, move: tuple[float, float], dt: float) -> None:
        """move = (dx, dz) birlik yo'nalish; gravitatsiya + relyef bilan yuradi."""
        # Gorizontal harakat — qiyalik chegarasi bilan.
        mx, mz = move
        mlen = (mx * mx + mz * mz) ** 0.5
        if mlen > 1e-6:
            mx, mz = mx / mlen, mz / mlen
            nx = self.x + mx * self.walk_speed * dt
            nz = self.z + mz * self.walk_speed * dt
            cur = field_.height_at(self.x, self.z)
            nxt = field_.height_at(nx, nz)
            horiz = self.walk_speed * dt
            rise = nxt - cur
            slope_deg = _slope_degrees(rise, horiz)
            if slope_deg <= self.max_slope_deg:      # ko'tarilsa bo'ladi
                self.x, self.z = nx, nz

        # Gravitatsiya + yerга yopishish.
        self.vy -= GRAVITY * dt
        self.y += self.vy * dt
        ground = field_.height_at(self.x, self.z)
        if self.feet_y <= ground:
            self.y = ground + self.height * 0.5
            self.vy = 0.0
            self.on_ground = True
        else:
            self.on_ground = False


def _slope_degrees(rise: float, run: float) -> float:
    import math
    if run <= 1e-6:
        return 90.0 if rise > 0 else 0.0
    return math.degrees(math.atan2(rise, run))


def drop_bodies_from_placements(placements, field_: TerrainField, *, drop_height: float = 40.0,
                                limit: int = 200) -> list[Body]:
    """Joylashuvlardan tushiriladigan jismlar yaratadi (relyef ustidan)."""
    bodies: list[Body] = []
    for p in placements[:limit]:
        r = 1.2 + p.scale * 0.8
        bodies.append(Body(kind=p.kind, x=p.x, y=p.y + drop_height, z=p.z, radius=r))
    return bodies
