// Token persistence. Kept tiny and framework-free so api.ts/sse.ts can import it
// without pulling in React/Zustand.
const KEY = "helix.token";

let memToken: string | null = null;

export function getToken(): string | null {
  if (memToken) return memToken;
  try { memToken = localStorage.getItem(KEY); } catch { /* ignore */ }
  return memToken;
}

export function setToken(token: string | null): void {
  memToken = token;
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch { /* ignore */ }
}
