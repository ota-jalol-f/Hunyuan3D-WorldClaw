"""Refine — agentli sifat sikli (WorldClaw '/loop' ning mobil nusxasi).

Oqim:  yaratish → baholash (critic) → reja tuzatish → qayta yaratish …
sifat chegarasiga yetguncha yoki max_iters gacha.

Qurilmada baholovchi — Gemini Nano multimodal (renderni ko'radi). Bu yerda
`critic.evaluate` uni determinlashgan tarzda o'rnini bosadi, shuning uchun
sikl xulq-atvori testlanadi.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .critic import Critique, evaluate
from .pipeline import WorldResult, build_from_plan, generate_world
from .scene_plan import ScatterRule, ScenePlan


@dataclass
class RefineStep:
    iteration: int
    score: float
    metrics: dict
    issues: list[str]
    applied: str


@dataclass
class RefineResult:
    world: WorldResult
    history: list[RefineStep]

    @property
    def final_score(self) -> float:
        return self.history[-1].score if self.history else 0.0

    @property
    def iterations(self) -> int:
        return len(self.history)


def _apply(plan: ScenePlan, crit: Critique) -> ScenePlan:
    """Critique tavsiyalarini rejaga qo'llab, yangi reja qaytaradi."""
    new_scatter: list[ScatterRule] = []
    for r in plan.scatter:
        d = r.density
        if crit.density_scale != 1.0:
            d = max(0.0, min(1.0, d * crit.density_scale))
        new_scatter.append(replace(r, density=d))

    new_terrain = plan.terrain
    if crit.water_delta != 0.0:
        new_level = max(0.0, min(0.95, plan.terrain.water_level + crit.water_delta))
        new_terrain = replace(plan.terrain, water_level=new_level)

    return replace(plan, terrain=new_terrain, scatter=new_scatter)


def refine(
    prompt: str,
    *,
    seed: int | None = None,
    size: int = 192,
    max_iters: int = 5,
    initial: WorldResult | None = None,
) -> RefineResult:
    """Promptdan boshlab sifat siklini yuritadi.

    `initial` berilsa (masalan ataylab yomon reja bilan), o'shandan davom etadi.
    """
    result = initial if initial is not None else generate_world(prompt, seed=seed, size=size)
    history: list[RefineStep] = []

    for i in range(max_iters):
        crit = evaluate(result)
        applied = "qabul qilindi" if crit.acceptable else _describe(crit)
        history.append(RefineStep(i, crit.score, crit.metrics, list(crit.issues), applied))
        if crit.acceptable:
            break
        # Rejani tuzatib qayta yaratish.
        new_plan = _apply(result.plan, crit)
        result = build_from_plan(new_plan)

    return RefineResult(world=result, history=history)


def _describe(crit: Critique) -> str:
    parts = []
    if crit.density_scale != 1.0:
        parts.append(f"zichlik ×{crit.density_scale:.2f}")
    if crit.water_delta != 0.0:
        parts.append(f"suv {crit.water_delta:+.3f}")
    return ", ".join(parts) if parts else "o'zgarishsiz"


def format_history(rr: RefineResult) -> str:
    lines = [f"Refine: {rr.iterations} takror, yakuniy sifat {rr.final_score:.3f}"]
    for s in rr.history:
        lines.append(
            f"  #{s.iteration}: sifat={s.score:.3f} "
            f"obj={s.metrics.get('object_count')} "
            f"qamrov={s.metrics.get('sector_coverage')} -> {s.applied}"
        )
        for issue in s.issues:
            lines.append(f"       • {issue}")
    return "\n".join(lines)
