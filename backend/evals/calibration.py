"""Confidence calibration readout over accumulated deep_runs rows.

The engine reports a confidence with every converged answer, and the
convergence gate trusts it (an unreported confidence can't satisfy the gate).
This script asks the follow-up question the product's honesty depends on:
*when the model says 0.9, how often is it right?* Runs entirely on data the
product already collects.

Two modes:

- **Offline (default, free):** buckets runs by reported confidence and prints
  the signals that travel with them (stability, stop reasons, depth, tokens)
  — the drift dashboard. Detects e.g. "confidence inflated after the model
  swap" when read alongside the provenance column.
- **Judged (--judge, spends tokens):** scores each run's answer against its
  question with the eval harness's blind judge, then prints mean judged score
  per confidence bucket. Calibrated = monotone, roughly linear. Needs
  GROQ_API_KEY.

Usage (from backend/, venv active):
    python -m evals.calibration              # offline readout
    python -m evals.calibration --judge      # judged calibration curve
    python -m evals.calibration --db ./helix.db
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path


def load_runs(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, question, answer, status, stop_reason, depth, stability,"
            " confidence, tokens_used, duration_ms, model, provenance"
            " FROM deep_runs WHERE status = 'done' AND answer != ''"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def bucket_of(confidence: float) -> str:
    if confidence <= 0:
        return "unreported"
    lo = min(int(confidence * 10) / 10, 0.9)
    return f"{lo:.1f}-{lo + 0.1:.1f}"


def offline_report(runs: list[dict]) -> None:
    print(f"{len(runs)} completed runs with answers\n")
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        buckets[bucket_of(r["confidence"] or 0.0)].append(r)
    print(f"{'confidence':>12} {'n':>4} {'stability':>10} {'depth':>6} "
          f"{'tokens':>8}  stop reasons")
    for name in sorted(buckets):
        rs = buckets[name]
        stab = statistics.mean(r["stability"] or 0.0 for r in rs)
        depth = statistics.mean(r["depth"] or 0 for r in rs)
        toks = statistics.mean(r["tokens_used"] or 0 for r in rs)
        stops = defaultdict(int)
        for r in rs:
            stops[r["stop_reason"] or "?"] += 1
        stop_str = ", ".join(f"{k}×{v}" for k, v in sorted(stops.items()))
        print(f"{name:>12} {len(rs):>4} {stab:>10.3f} {depth:>6.1f} "
              f"{toks:>8.0f}  {stop_str}")
    models = defaultdict(int)
    for r in runs:
        models[r["model"] or "(unstamped)"] += 1
    print("\nby model:", dict(models))


async def judged_report(runs: list[dict], judge_model: str) -> None:
    from langchain_groq import ChatGroq

    from api.config import settings
    from evals.judge import judge_answer

    judge_llm = ChatGroq(
        model=judge_model, temperature=0, api_key=settings.groq_api_key
    )
    print(f"judging {len(runs)} answers with {judge_model} (blind, absolute)…")
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for i, r in enumerate(runs):
        judgment = await judge_answer(judge_llm, r["question"], r["answer"])
        if judgment.score is not None:
            by_bucket[bucket_of(r["confidence"] or 0.0)].append(judgment.score)
        await asyncio.sleep(2)  # free-tier pacing
        print(f"  {i + 1}/{len(runs)}", end="\r")
    print(f"\n{'confidence':>12} {'n':>4} {'judged score (0-10)':>20}")
    for name in sorted(by_bucket):
        scores = by_bucket[name]
        print(f"{name:>12} {len(scores):>4} {statistics.mean(scores):>20.2f}")
    print("\ncalibrated = higher confidence buckets score higher, roughly linearly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="./helix.db")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--judge-model", default="llama-3.3-70b-versatile")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"no database at {args.db}")
    runs = load_runs(args.db)
    if args.limit:
        runs = runs[-args.limit:]
    if not runs:
        raise SystemExit("no completed deep runs recorded yet")

    offline_report(runs)
    if args.judge:
        asyncio.run(judged_report(runs, args.judge_model))


if __name__ == "__main__":
    main()
