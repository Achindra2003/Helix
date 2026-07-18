// Theme: light parchment (default) or nocturne dark. The choice persists per
// browser and is applied as data-theme on <html>, which tokens.css keys off.
export type Theme = "light" | "dark";

const KEY = "helix:theme";
const listeners = new Set<(t: Theme) => void>();

export function getTheme(): Theme {
  return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
}

export function setTheme(t: Theme) {
  localStorage.setItem(KEY, t);
  document.documentElement.dataset.theme = t;
  listeners.forEach((fn) => fn(t));
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === "dark" ? "light" : "dark";
  setTheme(next);
  return next;
}

export function onThemeChange(fn: (t: Theme) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Apply the stored theme before first paint (called from main.tsx). */
export function initTheme() {
  document.documentElement.dataset.theme = getTheme();
}
