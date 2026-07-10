// Crumpled-parchment relief, synthesized (no image asset): a turbulence field
// lit as a surface, with a gamma stage so the creases survive the blend.
// Scoped to whatever container positions it — currently only the chat canvas.
export function PaperTexture() {
  return (
    <svg width="100%" height="100%" aria-hidden>
      <filter id="hxPaper" x="0" y="0" width="100%" height="100%">
        <feTurbulence type="turbulence" baseFrequency="0.006" numOctaves={5} seed={7} stitchTiles="stitch" result="n" />
        <feDiffuseLighting in="n" lightingColor="#ffffff" surfaceScale={3.4}>
          <feDistantLight azimuth={235} elevation={44} />
        </feDiffuseLighting>
        <feComponentTransfer>
          <feFuncR type="gamma" exponent={1.8} amplitude={1} offset={0} />
          <feFuncG type="gamma" exponent={1.8} amplitude={1} offset={0} />
          <feFuncB type="gamma" exponent={1.8} amplitude={1} offset={0} />
        </feComponentTransfer>
      </filter>
      <rect width="100%" height="100%" filter="url(#hxPaper)" />
    </svg>
  );
}
