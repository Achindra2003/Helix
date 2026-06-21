// The Helix mark: two intertwined strands (a double helix) drawn with the
// brand gradient, plus an optional gradient wordmark.

export function HelixMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="helix-grad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#7C5CFF" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      {/* two sine-like strands forming a helix */}
      <path
        d="M9 3 C 23 9, 9 14, 23 20 C 9 25, 23 29, 23 29"
        stroke="url(#helix-grad)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M23 3 C 9 9, 23 14, 9 20 C 23 25, 9 29, 9 29"
        stroke="url(#helix-grad)"
        strokeWidth="2.4"
        strokeLinecap="round"
        opacity="0.65"
      />
      {/* rungs */}
      {[8, 14, 20, 26].map((y) => (
        <line
          key={y}
          x1="11"
          y1={y}
          x2="21"
          y2={y}
          stroke="url(#helix-grad)"
          strokeWidth="1.4"
          strokeLinecap="round"
          opacity="0.45"
        />
      ))}
    </svg>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2 select-none">
      <HelixMark size={size} />
      <span className="text-helix text-lg font-semibold tracking-tight">
        Helix
      </span>
    </div>
  );
}
