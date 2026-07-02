from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mood(str, Enum):
    CURIOUS = "curious"
    ANXIOUS = "anxious"
    OBSESSED = "obsessed"
    MELANCHOLIC = "melancholic"
    SERENE = "serene"
    ECSTATIC = "ecstatic"


class Mode(str, Enum):
    EXPLORE = "explore"
    ANALYZE = "analyze"
    CREATE = "create"
    SOLVE = "solve"
    PHILOSOPHIZE = "philosophize"


class OuroborosConfig(BaseModel):
    mode: Mode = Mode.EXPLORE
    max_depth: int = Field(default=4, ge=1, le=10)
    starting_energy: float = Field(default=80, ge=20, le=100)
    energy_drain_think: float = Field(default=5, ge=1, le=20)
    energy_drain_reflect: float = Field(default=3, ge=1, le=15)
    energy_recovery_breathe: float = Field(default=25, ge=5, le=50)
    mood_shift_chance: float = Field(default=0.15, ge=0, le=1)
    max_loop_guard: int = Field(default=15, ge=3, le=30)
    max_memories: int = Field(default=8, ge=2, le=20)
    steer_interval: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.7, ge=0, le=2)

    # --- Metacognitive adaptive controller (Wedge A) ---
    # When enabled, the loop becomes a convergent self-refine cycle whose halting
    # is decided by content-aware signals (answer stability + self-confidence)
    # under a compute budget, instead of fixed depth / random routing. Off by
    # default so the legacy engine and existing tests are unchanged.
    adaptive: bool = False
    compute_budget: int = Field(default=6, ge=1, le=30)  # hard cap on refine cycles
    min_cycles: int = Field(default=1, ge=1, le=10)  # always refine at least this many
    stability_threshold: float = Field(default=0.92, ge=0, le=1)  # cosine → converged
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)  # self-reported settle

    # When enabled, the `surface` node rewrites the converged (terse, anchored)
    # synthesis into a warm, conversational final answer for a human reader, and
    # streams it token-by-token. Off by default so the benchmark keeps output
    # parity (surfacing the raw synthesis); Helix turns it on for the chat surface.
    humanize: bool = False

    # Guided mode: pause the *adaptive* refinement loop at the human steer
    # checkpoint after each cycle (unless it is about to halt), so a person can
    # inject guidance mid-flight — the injected text becomes the next thought.
    # Off by default: an unguided adaptive run never pauses (the convergence
    # controller is the whole point). Distinct from the non-adaptive
    # `steer_interval`, which paces pauses in the mood/energy loop.
    adaptive_steer: bool = False

    # Tool permission (FR-14): whether the run may take the web-research detour
    # at all. The host application sets this from its own policy; even when
    # True, research still requires a live search backend (Tavily key).
    allow_research: bool = True


class SessionMeta(BaseModel):
    id: str
    seed: str
    mode: Mode
    created_at: str
    insight_count: int = 0
    total_ticks: int = 0


class SessionExport(BaseModel):
    meta: SessionMeta
    thoughts: list[dict]
    insights: list[str]
    final_state: dict
