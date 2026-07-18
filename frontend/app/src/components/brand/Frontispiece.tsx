// Scholarly frontispiece motif — a double helix inside orbital rings.
// Deliberately neutral (astronomy / manuscript vocabulary): no hexagram,
// pentagram, or esoteric symbolism. The helix ties to the product name.
export function Frontispiece({ size = 700, animate = true }: { size?: number; animate?: boolean }) {
  const cx = 350, top = 150, bot = 550, amp = 66, turns = 2.3;
  const N = 64;
  const strand = (phase: number) => {
    let d = "";
    for (let i = 0; i <= N; i++) {
      const t = i / N;
      const y = top + t * (bot - top);
      const x = cx + amp * Math.sin(t * Math.PI * 2 * turns + phase);
      d += (i === 0 ? "M" : " L") + x.toFixed(1) + " " + y.toFixed(1);
    }
    return d;
  };
  const rungs: [number, number, number][] = [];
  for (let i = 1; i < 9; i++) {
    const t = i / 9;
    const y = top + t * (bot - top);
    const x1 = cx + amp * Math.sin(t * Math.PI * 2 * turns);
    const x2 = cx + amp * Math.sin(t * Math.PI * 2 * turns + Math.PI);
    rungs.push([x1, x2, y]);
  }
  const drawn = (len: number, delay: number) =>
    animate ? ({ strokeDasharray: len, strokeDashoffset: len, animation: `hx-draw 3s ease forwards ${delay}s` } as const) : undefined;

  // After the draw completes, the instrument keeps living: the dashed ring and
  // its constellation precess imperceptibly slowly (a full turn takes minutes).
  const precess = animate
    ? ({ transformOrigin: "350px 350px", animation: "hx-spin 240s linear infinite" } as const)
    : undefined;

  return (
    <svg viewBox="0 0 700 700" width={size} height={size} style={{ color: "var(--ink)" }} aria-hidden>
      <g fill="none" stroke="currentColor" opacity="0.30">
        {/* orbital rings */}
        <circle cx="350" cy="350" r="300" strokeWidth="1.1" style={drawn(1885, 0.1)} />
        <g style={precess}>
          <circle cx="350" cy="350" r="236" strokeWidth="1" strokeDasharray="3 9" />
        </g>
        <circle cx="350" cy="350" r="172" strokeWidth="1.1" style={drawn(1080, 0.5)} />
      </g>
      {/* double helix */}
      <g fill="none" strokeWidth="1.6" strokeLinecap="round">
        <path d={strand(0)} stroke="var(--ink)" opacity="0.6" style={drawn(1400, 0.3)} />
        <path d={strand(Math.PI)} stroke="var(--oxblood)" opacity="0.55" style={drawn(1400, 0.55)} />
        {rungs.map(([x1, x2, y], i) => (
          <line key={i} x1={x1} y1={y} x2={x2} y2={y} stroke="var(--gilt)" strokeWidth="1" opacity="0.4" />
        ))}
      </g>
      {/* orbit nodes (constellation), not stars — they ride the precession */}
      <g style={precess}>
        <g fill="var(--gilt)" opacity="0.5">
          <circle cx="350" cy="50" r="3.2" />
          <circle cx="650" cy="350" r="2.6" />
          <circle cx="350" cy="650" r="2.6" />
          <circle cx="50" cy="350" r="3.2" />
        </g>
      </g>
    </svg>
  );
}
