// SSE-over-POST reader. The backend streams `data: {json}\n\n` frames ending with
// `data: [DONE]`. We POST a body (EventSource only does GET) and read the stream.
import { API_BASE } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { RunEvent } from "@/lib/types";

export interface StreamHandle {
  done: Promise<void>;
  abort: () => void;
}

export function streamSSE(
  path: string,
  body: unknown,
  onEvent: (ev: RunEvent) => void,
): StreamHandle {
  return openSSE(path, { method: "POST", body }, onEvent);
}

/** GET variant — the deep-run (re)attach path: replay a server-side run's
 *  event log from a seq, then follow live. Closing it detaches only. */
export function attachSSE(path: string, onEvent: (ev: RunEvent) => void): StreamHandle {
  return openSSE(path, { method: "GET" }, onEvent);
}

function openSSE(
  path: string,
  opts: { method: "GET" | "POST"; body?: unknown },
  onEvent: (ev: RunEvent) => void,
): StreamHandle {
  const ctrl = new AbortController();
  const token = getToken();
  const headers: Record<string, string> = {};
  if (opts.method === "POST") headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const done = (async () => {
    const res = await fetch(API_BASE + path, {
      method: opts.method,
      headers,
      body: opts.method === "POST" ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => "");
      let msg = `HTTP ${res.status}`;
      try { msg = JSON.parse(text)?.error?.message ?? msg; } catch { /* ignore */ }
      throw new Error(msg);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buf += dec.decode(value, { stream: true });
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const data = line.slice(6);
        if (data === "[DONE]") { onEvent({ kind: "done" }); continue; }
        try { onEvent(JSON.parse(data) as RunEvent); } catch { /* skip malformed */ }
      }
    }
  })();

  return { done, abort: () => ctrl.abort() };
}
