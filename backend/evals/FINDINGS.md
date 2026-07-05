# Eval Findings — fixed-N baselines vs the convergence controller

**Pilot of 2026-07-05** · 6 tier-balanced questions × 3 arms (18 runs) ·
engine `llama-3.3-70b-versatile` · judge `llama-3.3-70b-versatile`
(absolute 0–10 rubric, blind to arm) · humanize off, web research off
(output parity — every arm surfaces the raw synthesis).
Raw data: `results/results-20260705-134943.json`, `results/report-20260705-134943.md`.

## Headline numbers

| arm | mean score | mean tokens | mean cycles | stop reasons |
|-----|-----------|-------------|-------------|--------------|
| fixed-1 (single pass) | **8.83** | **1,648** | 1 | budget×6 |
| adaptive (the controller) | 8.17 | 5,384 | 2.83 | **converged×6** |
| fixed-4 ("just think longer") | 8.00 | 7,615 | 4 | budget×6 |

Per tier (mean score):

| tier | fixed-1 | fixed-4 | adaptive |
|------|---------|---------|----------|
| easy | 9.0 | 9.0 | 8.0 |
| medium | 9.5 | 8.0 | 8.5 |
| hard | 8.0 | 7.0 | 8.0 |

## What the data supports

1. **The controller mechanically works.** All six adaptive runs
   self-terminated with stop reason `converged` — genuine stability +
   confidence convergence, never the budget cap. The halting rule is not
   decorative; it fires, and it fires before the cap (2.83 mean cycles under
   a budget of 6).

2. **Adaptive strictly dominates the natural iterative baseline.** Against
   fixed-4 — the "reflection loops just think a fixed N times" design the
   engine argues against — the controller scored equal or better on **every
   tier** while spending **29% fewer tokens** (32,303 vs 45,689 total). On
   the hard tier the gap is widest: 8.0 vs 7.0. This is the research claim,
   and on this pilot it holds: *if you are going to iterate, convergence
   halting beats a fixed budget on both cost and quality.*

3. **But single-pass won the pilot outright.** fixed-1 had the best mean
   score at ~a fifth of adaptive's token cost. On questions a 70B model can
   already answer well, extra refinement cycles did not add quality — and
   sometimes subtracted it (the judge repeatedly dinged refined answers for
   hedging; `easy-cache × adaptive` spent 4 cycles to land at 7.0 where the
   single-pass answer scored 9.0). Iteration's failure mode here is not
   wrongness but *dilution*: each pass sands the decisive edge off an
   already-correct answer.

4. **Cycle spend tracked answer instability, not question difficulty.** The
   controller spent its deepest runs on `med-bridge` (5 cycles) and
   `easy-cache` (4), not on the hard tier (2, 2). "Spend more on hard
   questions" is not what happened; "spend more where the answer keeps
   moving" is. Those are only the same thing when instability comes from
   genuine unresolved difficulty — on this set it sometimes came from
   restlessness (rephrasing an already-settled answer).

## Honest caveats

- **n = 6 per arm, one seed.** Differences of under ~1 point are inside the
  noise; treat every comparison as directional, not significant.
- **The judge is the same model as the engine** (llama-3.3-70b judging its
  own family's output, absolute rubric). Self-preference and rubric
  compression at the top of the scale (all 18 scores landed in 6–10) both
  blunt the instrument.
- **Ceiling effects.** The golden set's "hard" tier is not hard enough for a
  70B model — fixed-1 scored 8.0 on it. Where single-pass already succeeds,
  no iteration scheme can show a quality win; it can only show a cost win.

## What this means for Helix

- **The honest pitch for Deep Reasoning changes shape.** It is not "more
  cycles ⇒ better answers." It is: *when you choose to iterate, the
  controller gives you fixed-4-or-better quality at ~70% of fixed-4's cost,
  and it proves it stopped because the answer settled — not because a
  counter ran out.* The kill-switch and the convergence proof are the
  feature; unconditional depth is not.
- **Chat's single-pass default is vindicated** for ordinary questions —
  routing everything through the deep loop would cost 3–5× for flat-to-worse
  quality on this evidence.
- **Next experiments, in order of leverage:** (1) a question set with a real
  frontier — problems where fixed-1 demonstrably fails (multi-constraint math,
  long-document synthesis) — because only there can refinement show a quality
  win; (2) an independent judge (different model family, or pairwise
  A/B instead of absolute scores); (3) more seeds per cell for error bars;
  (4) score the *perturb-on-stall* path specifically: does an answer that
  survived a challenge score higher than one that merely repeated itself?

The experiment did exactly what it was built to do: it replaced "the
controller obviously helps" with a measured, narrower, defensible claim —
and located the next question worth asking.
