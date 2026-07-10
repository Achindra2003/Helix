// Fixed parchment texture layers (grain + vignette + warm glow).
export function GrainOverlay() {
  return (
    <>
      <div className="tex-grain" aria-hidden>
        <svg width="100%" height="100%">
          <filter id="hxGrain">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} stitchTiles="stitch" />
          </filter>
          <rect width="100%" height="100%" filter="url(#hxGrain)" />
        </svg>
      </div>
      <div className="tex-vig" aria-hidden />
      <div className="tex-warm" aria-hidden />
    </>
  );
}
