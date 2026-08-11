export const initialOf = (s?: string | null) => (s || "?").trim().charAt(0).toUpperCase();

export function timeOf(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export const nowTime = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// Deterministic accent colour per id/name, drawn from the manuscript palette.
// These are avatar *fills* carrying a white initial, so every one of them has
// to clear 4.5:1 against --on-author — a teammate should not get an unreadable
// avatar because of how their email happens to hash. Measured against white:
// #9a6b4b 4.59 · #8a6d26 4.89 · #a85a19 5.07 · #6e5aa8 5.69 · #46624c 6.75 ·
// #8c2b1e 8.47. The two that failed (#9a7a2c 4.04, #c5752a 3.53) were darkened
// a step and stay in the same earth family.
const PALETTE = ["#8a6d26", "#46624c", "#6e5aa8", "#9a6b4b", "#8c2b1e", "#a85a19"];
export function colorFor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
