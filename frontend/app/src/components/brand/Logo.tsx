// The Helix mark: the product's namesake — a double helix held inside a gilt
// orbital ring. Same vocabulary as the Frontispiece (manuscript astronomy),
// scaled to a seal. No esoteric symbolism.
export function Logo({ size = 34 }: { size?: number }) {
  const cx = 22, top = 10, bot = 34, amp = 5.5, turns = 1.5;
  const N = 24;
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
  for (let i = 1; i < 4; i++) {
    const t = i / 4;
    const y = top + t * (bot - top);
    rungs.push([
      cx + amp * Math.sin(t * Math.PI * 2 * turns),
      cx + amp * Math.sin(t * Math.PI * 2 * turns + Math.PI),
      y,
    ]);
  }
  return (
    <svg viewBox="0 0 44 44" width={size} height={size} aria-hidden>
      <circle cx="22" cy="22" r="19" fill="none" stroke="var(--gilt)" strokeWidth="1.4" strokeDasharray="100 12" strokeLinecap="round" />
      <g fill="none" strokeWidth="1.5" strokeLinecap="round">
        <path d={strand(0)} stroke="var(--ink)" opacity="0.75" />
        <path d={strand(Math.PI)} stroke="var(--oxblood)" opacity="0.8" />
        {rungs.map(([x1, x2, y], i) => (
          <line key={i} x1={x1} y1={y} x2={x2} y2={y} stroke="var(--gilt-1)" strokeWidth="1" opacity="0.6" />
        ))}
      </g>
      <circle cx="3.5" cy="22" r="2.1" fill="var(--gilt-2)" />
    </svg>
  );
}
