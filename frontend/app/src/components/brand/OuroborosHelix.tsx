import { motion, useReducedMotion } from "framer-motion";

/**
 * The Ouroboros Helix — the landing instrument.
 *
 * Two strands wound as a double helix and bent until the figure closes on
 * itself: the product's two names in one mark. The helix is Helix; the closed
 * loop that re-enters where it began is the Ouroboros engine, which reasons,
 * reflects, synthesises and returns to the question with what it learned.
 *
 * It stays inside the manuscript vocabulary — ruled hairlines, orbital rings, a
 * star-chart constellation. There is no serpent's head, no alchemical or
 * hermetic figure; the recursion is expressed by the geometry closing and by
 * the light completing a lap, which is what the idea actually is.
 *
 * Motion, in three beats:
 *   1. the quill lays the figure down (a draw-in, once, on arrival);
 *   2. a single illumination travels the loop and re-enters the clasp it left —
 *      the authored moment, and the only continuous motion with any speed;
 *   3. the outer ring and its constellation precess, a full turn in four
 *      minutes, so the instrument is never quite dead but never asks for
 *      attention either.
 *
 * Under `prefers-reduced-motion` the figure renders complete and still: the
 * information here is the closed loop, and the closed loop is a shape, not a
 * movement. The travelling light is simply not drawn.
 */

const CX = 350;
const CY = 350;
/** Mean radius of the coil, and how far each strand swings either side of it. */
const R = 210;
const AMP = 33;
/** Winds around the ring — and the number the whole figure depends on. At seven
 *  the two strands cross fourteen times at the mean radius and the eye reads a
 *  daisy, not a coil: the pitch was longer than the coil was wide. Eighteen
 *  makes each wave shorter than its own amplitude, which is what a wound rope
 *  looks like. */
const TURNS = 18;
/** ~60 samples per wave. Below about 40 the crests visibly flatten. */
const SAMPLES = 1080;

/** One strand of the coil, as a closed polyline. θ starts at the top (the
 *  group is rotated -90°), so a path begins and ends at the clasp. */
function strand(phase: number): { d: string; length: number } {
  let d = "";
  let length = 0;
  let px = 0;
  let py = 0;
  for (let i = 0; i <= SAMPLES; i++) {
    const th = (i / SAMPLES) * Math.PI * 2;
    const r = R + AMP * Math.cos(TURNS * th + phase);
    const x = CX + r * Math.cos(th);
    const y = CY + r * Math.sin(th);
    if (i === 0) {
      d = `M${x.toFixed(1)} ${y.toFixed(1)}`;
    } else {
      d += ` L${x.toFixed(1)} ${y.toFixed(1)}`;
      length += Math.hypot(x - px, y - py);
    }
    px = x;
    py = y;
  }
  return { d: d + " Z", length };
}

/** The base pairs: hairlines across the coil where the strands are furthest
 *  apart, which is also where a coil reads as a coil rather than as two rings. */
function rungs() {
  const out: { x1: number; y1: number; x2: number; y2: number }[] = [];
  for (let m = 0; m < TURNS * 2; m++) {
    const th = (m * Math.PI) / TURNS;
    const rA = R + AMP * Math.cos(TURNS * th);
    const rB = R + AMP * Math.cos(TURNS * th + Math.PI);
    out.push({
      x1: CX + rA * Math.cos(th), y1: CY + rA * Math.sin(th),
      x2: CX + rB * Math.cos(th), y2: CY + rB * Math.sin(th),
    });
  }
  return out;
}

const A = strand(0);
const B = strand(Math.PI);
const RUNGS = rungs();
/** Arc of the strand that is lit at any moment — long enough to read as a
 *  travelling current, short enough that most of the coil is at rest. */
const LIT = Math.round(A.length * 0.13);

export function OuroborosHelix({ size = 560, still = false }: { size?: number; still?: boolean }) {
  const reduce = useReducedMotion();
  const quiet = still || !!reduce;

  const drawn = (len: number, delay: number) =>
    quiet ? undefined : ({
      strokeDasharray: len,
      strokeDashoffset: len,
      animation: `hx-draw 2.4s var(--ease-quill) forwards ${delay}s`,
    } as const);

  const precess = quiet
    ? undefined
    : ({ transformOrigin: `${CX}px ${CY}px`, animation: "hx-spin 240s linear infinite" } as const);

  /** The lit arc. `--hx-len` carries the measured path length into the
   *  keyframe, so a lap is exactly one circuit and the loop is seamless —
   *  a guessed length would show a jump every time it wrapped. */
  const current = (delay: number) => ({
    strokeDasharray: `${LIT} ${Math.round(A.length) - LIT}`,
    animation: `hx-current 13s linear ${delay}s infinite`,
    ["--hx-len" as string]: Math.round(A.length),
  }) as React.CSSProperties;

  return (
    <svg viewBox="0 0 700 700" width={size} height={size} aria-hidden>
      <g transform={`rotate(-90 ${CX} ${CY})`}>
        {/* the ruled sky the instrument is drawn on */}
        <circle cx={CX} cy={CY} r="300" fill="none" stroke="var(--ink)" strokeWidth="1"
          opacity="0.26" style={drawn(1885, 0.1)} />
        <g style={precess}>
          <circle cx={CX} cy={CY} r="266" fill="none" stroke="var(--ink)" strokeWidth="1"
            strokeDasharray="3 10" opacity="0.24" />
          <g fill="var(--gilt)" opacity="0.55">
            <circle cx={CX} cy={CY - 266} r="3.4" />
            <circle cx={CX + 266} cy={CY} r="2.6" />
            <circle cx={CX} cy={CY + 266} r="2.6" />
            <circle cx={CX - 266} cy={CY} r="3.4" />
          </g>
        </g>

        {/* base pairs, drawn first so the strands cross them unbroken */}
        <g stroke="var(--gilt)" strokeWidth="1" opacity="0.3">
          {RUNGS.map((r, i) => (
            <line key={i} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} />
          ))}
        </g>

        {/* The coil. Each strand is laid down twice: a wide stroke in the
            paper's own colour, then the line itself. The halo is what gives the
            figure a front and a back — without it the strands cross flat at
            every wave and the coil reads as a flat braid pattern. With it, the
            russet strand passes cleanly in front and the figure winds. */}
        <g fill="none" strokeLinecap="round">
          <path d={A.d} stroke="var(--paper)" strokeWidth="5" opacity="0.92" style={drawn(Math.round(A.length), 0.25)} />
          <path d={A.d} stroke="var(--ink)" strokeWidth="2.2" opacity="0.78" style={drawn(Math.round(A.length), 0.25)} />
          <path d={B.d} stroke="var(--paper)" strokeWidth="5" opacity="0.92" style={drawn(Math.round(B.length), 0.5)} />
          <path d={B.d} stroke="var(--oxblood)" strokeWidth="2.2" opacity="0.75" style={drawn(Math.round(B.length), 0.5)} />
        </g>

        {/* the current: one lit arc per strand, half a lap apart, leaving the
            clasp and arriving back into it */}
        {!quiet && (
          <motion.g
            fill="none"
            strokeWidth="2.6"
            strokeLinecap="round"
            stroke="var(--gilt-2)"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.9 }}
            transition={{ delay: 2.3, duration: 1.1, ease: [0.22, 0.61, 0.21, 1] }}
          >
            <path d={A.d} style={current(0)} />
            <path d={B.d} style={current(-6.5)} />
          </motion.g>
        )}

        {/* the clasp — where the figure closes, at the top of the ring */}
        <g style={{ transformOrigin: `${CX}px ${CY}px` }} transform={`rotate(90 ${CX} ${CY})`}>
          <circle cx={CX} cy={CY - R} r="7.5" fill="var(--paper-0)" stroke="var(--gilt-1)" strokeWidth="1.3" />
          <circle cx={CX} cy={CY - R} r="2.6" fill="var(--oxblood)" opacity="0.85" />
        </g>
      </g>
    </svg>
  );
}
