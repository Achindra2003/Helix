"""The eval harness: fixed-N baselines vs the convergence controller.

This is the experiment the engine's whole design rests on. Standard reflection
loops spend a *fixed* number of refinement cycles; Ouroboros claims a
content-aware controller (stability + confidence + perturb-on-stall) buys the
same or better answer quality for fewer tokens by halting when the answer has
settled. The harness measures exactly that trade:

    arm "fixed-1"   -> exactly 1 refine cycle (single-pass baseline)
    arm "fixed-2"   -> exactly 2 cycles
    arm "fixed-4"   -> exactly 4 cycles (the "just think longer" baseline)
    arm "adaptive"  -> the real controller, budget-capped at 6

Every run reuses the production wiring (`build_ouroboros_graph`) with
humanize off, so all arms surface the raw converged synthesis — output parity.
Scoring is an independent absolute LLM judge (see judge.py). Results land as
JSON (every run, every score, every token count) plus a Markdown summary.

Run (from backend/, venv active; needs GROQ_API_KEY in .env):
    python -m evals.harness --limit 6 --arms fixed-1,fixed-4,adaptive
Hermetic self-test: pytest evals/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from evals.judge import Judgment, judge_answer

# --- arms ----------------------------------------------------------------------

ARMS: dict[str, dict[str, Any]] = {
    # min_cycles == compute_budget pins the loop to exactly N cycles.
    "fixed-1": {"compute_budget": 1, "min_cycles": 1},
    "fixed-2": {"compute_budget": 2, "min_cycles": 2},
    "fixed-4": {"compute_budget": 4, "min_cycles": 4},
    # The real controller: converge/perturb/halt under the production budget.
    "adaptive": {"compute_budget": 6, "min_cycles": 1},
}


@dataclass
class RunResult:
    question_id: str
    tier: str
    arm: str
    answer: str
    depth: int
    stop_reason: str
    tokens: int
    duration_s: float
    score: float | None = None
    justification: str = ""
    error: str = ""


@dataclass
class Summary:
    arm: str
    n: int
    mean_score: float
    mean_tokens: float
    mean_cycles: float
    stop_reasons: dict[str, int] = field(default_factory=dict)


# --- the runner (graph factory injected so tests never touch the network) -------

GraphFactory = Callable[..., tuple]  # signature of build_ouroboros_graph


async def run_one(
    question: dict, arm: str, *, graph_factory: GraphFactory, model: str, api_key: str
) -> RunResult:
    """One (question, arm) cell: build an isolated graph, run to completion."""
    overrides = ARMS[arm]
    graph, graph_config, make_inputs, usage_reader = graph_factory(
        thread_id=uuid.uuid4().hex,
        groq_api_key=api_key,
        groq_model=model,
        mode="analyze",
        adaptive=True,
        compute_budget=overrides["compute_budget"],
        min_cycles=overrides["min_cycles"],
        allow_research=False,  # no web tools: measure the reasoning loop itself
        humanize=False,  # output parity: every arm surfaces the raw synthesis
    )
    t0 = time.monotonic()
    try:
        state = await graph.ainvoke(make_inputs(question["question"]), config=graph_config)
        answer = state.get("surfaced_insight") or state.get("synthesis") or ""
        return RunResult(
            question_id=question["id"],
            tier=question["tier"],
            arm=arm,
            answer=answer,
            depth=int(state.get("depth", 0) or 0),
            stop_reason=str(state.get("stop_reason") or "ended"),
            tokens=int(usage_reader()),
            duration_s=round(time.monotonic() - t0, 1),
        )
    except Exception as exc:
        return RunResult(
            question_id=question["id"],
            tier=question["tier"],
            arm=arm,
            answer="",
            depth=0,
            stop_reason="harness_error",
            tokens=int(usage_reader()),
            duration_s=round(time.monotonic() - t0, 1),
            error=f"{type(exc).__name__}: {exc}"[:300],
        )


async def run_experiment(
    questions: list[dict],
    arms: list[str],
    *,
    graph_factory: GraphFactory,
    judge: Callable[[str, str], Awaitable[Judgment]],
    model: str,
    api_key: str,
    pause_s: float = 0.0,
    progress: Callable[[str], None] = lambda msg: None,
) -> list[RunResult]:
    """Sequential over cells (rate-limit friendly); judged as it goes."""
    results: list[RunResult] = []
    for question in questions:
        for arm in arms:
            progress(f"[{question['id']} × {arm}] running…")
            result = await run_one(
                question, arm, graph_factory=graph_factory, model=model, api_key=api_key
            )
            if not result.error:
                verdict = await judge(question["question"], result.answer)
                result.score = verdict.score
                result.justification = verdict.justification
            progress(
                f"[{question['id']} × {arm}] score={result.score} "
                f"cycles={result.depth} tokens={result.tokens} "
                f"stop={result.stop_reason}{' ERROR ' + result.error if result.error else ''}"
            )
            results.append(result)
            if pause_s:
                await asyncio.sleep(pause_s)
    return results


# --- aggregation + report --------------------------------------------------------

def summarize(results: list[RunResult]) -> list[Summary]:
    out: list[Summary] = []
    for arm in sorted({r.arm for r in results}):
        scored = [r for r in results if r.arm == arm and r.score is not None]
        if not scored:
            continue
        reasons: dict[str, int] = {}
        for r in scored:
            reasons[r.stop_reason] = reasons.get(r.stop_reason, 0) + 1
        out.append(
            Summary(
                arm=arm,
                n=len(scored),
                mean_score=round(statistics.mean(r.score for r in scored), 2),
                mean_tokens=round(statistics.mean(r.tokens for r in scored), 0),
                mean_cycles=round(statistics.mean(r.depth for r in scored), 2),
                stop_reasons=reasons,
            )
        )
    return out


def render_report(
    results: list[RunResult], summaries: list[Summary], *, model: str, judge_model: str
) -> str:
    lines = [
        "# Deep Reasoning Eval — fixed-N baselines vs the convergence controller",
        "",
        f"Runs: {len(results)} · engine model: `{model}` · judge: `{judge_model}` "
        f"(absolute 0-10 rubric, blind to arm) · web research off · humanize off "
        "(all arms surface the raw synthesis).",
        "",
        "| arm | n | mean score | mean tokens | mean cycles | stop reasons |",
        "|-----|---|-----------|-------------|-------------|--------------|",
    ]
    for s in summaries:
        reasons = ", ".join(f"{k}×{v}" for k, v in sorted(s.stop_reasons.items()))
        lines.append(
            f"| {s.arm} | {s.n} | {s.mean_score} | {int(s.mean_tokens)} "
            f"| {s.mean_cycles} | {reasons} |"
        )
    lines += ["", "## Per-tier mean score", ""]
    tiers = sorted({r.tier for r in results})
    arms = [s.arm for s in summaries]
    lines.append("| tier | " + " | ".join(arms) + " |")
    lines.append("|------|" + "---|" * len(arms))
    for tier in tiers:
        cells = []
        for arm in arms:
            scored = [
                r.score for r in results if r.tier == tier and r.arm == arm and r.score is not None
            ]
            cells.append(f"{statistics.mean(scored):.1f}" if scored else "—")
        lines.append(f"| {tier} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Per-run detail",
        "",
        "| question | arm | score | cycles | tokens | stop | judge note |",
        "|----------|-----|-------|--------|--------|------|------------|",
    ]
    for r in results:
        note = (r.justification or r.error).replace("|", "/")[:140]
        lines.append(
            f"| {r.question_id} | {r.arm} | {r.score if r.score is not None else '—'} "
            f"| {r.depth} | {r.tokens} | {r.stop_reason} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------------

def _load_questions(path: Path, limit: int | None) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))["questions"]
    if not limit or limit >= len(data):
        return data
    # Tier-balanced subset: round-robin across tiers so a small pilot still
    # spans easy/medium/hard instead of exhausting one tier first.
    by_tier: dict[str, list[dict]] = {}
    for q in data:
        by_tier.setdefault(q["tier"], []).append(q)
    picked: list[dict] = []
    while len(picked) < limit and any(by_tier.values()):
        for tier in list(by_tier):
            if by_tier[tier] and len(picked) < limit:
                picked.append(by_tier[tier].pop(0))
    return picked


async def _amain() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=str(Path(__file__).parent / "questions.json"))
    parser.add_argument("--limit", type=int, default=None, help="tier-balanced subset size")
    parser.add_argument("--arms", default="fixed-1,fixed-4,adaptive")
    parser.add_argument("--model", default=None, help="engine model (default: settings)")
    parser.add_argument("--judge-model", default="llama-3.3-70b-versatile")
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between runs")
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"))
    args = parser.parse_args()

    from api.config import settings
    from api.conversation.deep_reasoning import build_ouroboros_graph
    from langchain_groq import ChatGroq

    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY is not configured (backend/.env)")
    model = args.model or settings.deep_reasoning_model
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arms: {unknown}; valid: {list(ARMS)}")
    questions = _load_questions(Path(args.questions), args.limit)

    judge_llm = ChatGroq(model=args.judge_model, temperature=0, api_key=settings.groq_api_key)

    async def judge(question: str, answer: str) -> Judgment:
        return await judge_answer(judge_llm, question, answer)

    print(f"{len(questions)} questions × {len(arms)} arms on {model}")
    results = await run_experiment(
        questions,
        arms,
        graph_factory=build_ouroboros_graph,
        judge=judge,
        model=model,
        api_key=settings.groq_api_key,
        pause_s=args.pause,
        progress=print,
    )
    summaries = summarize(results)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"results-{stamp}.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report = render_report(results, summaries, model=model, judge_model=args.judge_model)
    (out_dir / f"report-{stamp}.md").write_text(report, encoding="utf-8")
    print(f"\nwrote {out_dir / f'results-{stamp}.json'}")
    print(report)


if __name__ == "__main__":
    asyncio.run(_amain())
