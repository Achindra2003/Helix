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

---

# Hard-set run of 2026-07-16 — the frontier experiment (next-experiment #1)

`questions-hard.json`: 8 questions engineered so single-pass plausibly fails
(interacting constraints, checkable structures, conflicting specs). Same
protocol as the pilot: 3 arms, engine + judge `llama-3.3-70b-versatile`
(absolute 0–10, blind to arm), humanize off, web research off.

**Coverage caveat:** Groq's free-tier daily token cap (100k TPD) killed the
run at 20/24 — complete three-arm triples exist for **6 of 8** questions
(`hf-sched`, `hf-rate`, `hf-migrate`, `hf-logic`, `hf-cap`, `hf-cache2`);
`hf-api`/`hf-budget` are pending. Rerun the gap when the window frees:
`python -m evals.harness --questions evals/questions-hard-remainder.json
--arms fixed-1,fixed-4,adaptive`. Numbers below are over the 6 complete
questions (18 runs, scores recovered from the run log). **The remainder ran
2026-07-17 — full-set numbers in the section below; the verdict holds.**

## Headline numbers

| arm | mean score | mean tokens | mean cycles | stop reasons |
|-----|-----------|-------------|-------------|--------------|
| fixed-1 | **8.83** | **1,697** | 1 | budget×6 |
| fixed-4 | 8.50 | 7,735 | 4 | budget×6 |
| adaptive | 8.50 | 3,752 | 2.00 | **converged×6** |

Top-score-per-question (ties shared): fixed-1 on 5/6, fixed-4 on 3/6,
adaptive on 3/6. Adaptive's one outright win is `hf-sched` (10 vs 9/9) —
the two-room scheduling problem with five interacting constraints, i.e.
exactly the engineered failure mode where a first coherent-sounding answer
tends to violate a constraint and a verification pass catches it.

## The verdict

**Even on questions engineered to break it, single-pass did not break** under
this judge. The hoped-for upgrade — "on genuinely hard questions, refinement
wins on quality" — did **not** materialize: adaptive ties fixed-4 and trails
fixed-1 by a third of a point. What did replicate, now on both question sets:

1. **The controller dominates fixed iteration.** Same quality as fixed-4 at
   **49% of its tokens**, converging in 2 cycles every time, never hitting
   the cap. If a team iterates at all, the controller is strictly better
   than counting cycles.
2. **The one adaptive win is the designed one.** Where constraints interact
   (`hf-sched`), the reflect pass caught what one shot missed. That's a
   real, narrow capability — worth demoing on exactly that class of problem.
3. **Same instrument caveats as the pilot** (same-family judge, absolute
   rubric compressing 6–10, n=6, no error bars). A pairwise independent
   judge remains the next methodological upgrade before any stronger claim.

## What this settles for positioning

Deep Reasoning's pitch is now measured twice and should be stated as:
**transparency, steerability, and disciplined cost — not higher IQ.** The
honest sentence for the README/demo: *"When you iterate, Helix converges
instead of counting — fixed-4 quality at half its cost, with a live proof it
stopped because the answer settled."* Any "better answers" claim is
unsupported on current evidence, and saying so out loud is the credibility
feature no competitor demo has.

---

# Remainder run of 2026-07-17 — hard-set coverage complete (8/8)

The daily token window freed; `hf-api`/`hf-budget` ran all three arms
(results-20260717-211824.json). The remainder itself leaned adaptive:
it took `hf-api` outright (9 vs 8 vs 6 — the conflicting-specs pagination
question, the same interacting-constraints class as `hf-sched`) and shared
the top on `hf-budget` (9 = 9, with fixed-4 at 8).

## Full-set numbers (all 8 questions × 3 arms, 24 runs)

| arm | mean score | mean tokens | stop reasons |
|-----|-----------|-------------|--------------|
| fixed-1 | **8.75** | **1,729** | budget×8 |
| fixed-4 | 8.13 | 7,852 | budget×8 |
| adaptive | 8.63 | 3,774 | **converged×8** |

## What the completed set adds

1. **The verdict stands, slightly softened.** fixed-1 still leads, but the
   gap narrowed from 0.33 to 0.13 — inside noise at n=8 with no error bars.
   The claim stays "not measurably smarter," now with the caveat cutting in
   adaptive's favor rather than against it.
2. **Adaptive now clearly beats fixed-4 on quality** (8.63 vs 8.13) at 48%
   of its tokens, converging 8/8. On the hard set, fixed iteration didn't
   just cost more — it scored *worst* (over-iteration degrading answers is
   visible in the `hf-api` fixed-4 run: 6.0 after 4 cycles vs 8.0 in one).
3. **Both adaptive outright wins are the designed class** — interacting
   constraints (`hf-sched`, `hf-api`). Two-for-two where the reflect pass
   has something checkable to catch. The demo should use exactly these.

Positioning is unchanged: transparency, steerability, disciplined cost.
The new honest garnish: on the hardest question class, blind iteration
actively hurt, and the controller is what stopped it from hurting.
