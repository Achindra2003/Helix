// Fixed parchment texture layers (crumple relief + grain + vignette + warm glow).
export function GrainOverlay() {
  return (
    <>
      {/* Crumpled-parchment relief, synthesized (no image asset): low-frequency
          fractal noise lit as a surface — the soft creases and mottled clouds
          of a much-handled sheet. Static; renders once. */}
      <div className="tex-crumple" aria-hidden>
        <svg width="100%" height="100%">
          <filter id="hxCrumple" x="0" y="0" width="100%" height="100%">
            <feTurbulence type="turbulence" baseFrequency="0.006" numOctaves={5} seed={7} stitchTiles="stitch" result="n" />
            <feDiffuseLighting in="n" lightingColor="#ffffff" surfaceScale={3.4} result="lit">
              <feDistantLight azimuth={235} elevation={44} />
            </feDiffuseLighting>
            {/* deepen the midtones so the creases actually read through multiply */}
            <feComponentTransfer>
              <feFuncR type="gamma" exponent={1.8} amplitude={1} offset={0} />
              <feFuncG type="gamma" exponent={1.8} amplitude={1} offset={0} />
              <feFuncB type="gamma" exponent={1.8} amplitude={1} offset={0} />
            </feComponentTransfer>
          </filter>
          <rect width="100%" height="100%" filter="url(#hxCrumple)" />
        </svg>
      </div>
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
