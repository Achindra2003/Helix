"""Deep-run trace persistence: the observability the live monitor doesn't give.

`DeepRunRecorder` sits in the event stream the router is already relaying
(observe → yield), accumulates the run's signals, and writes one `DeepRunRow`
when a terminal `Complete` arrives. It never blocks or breaks the stream: a
recorder failure is logged state, not a failed run. Steerable runs span
multiple HTTP segments — the recorder lives in the router's run registry and
flushes only on the segment that actually completes.

Why persist: when someone reports "yesterday's deep run was weird", the answer
is a query, not a shrug — and the accumulated rows (real questions, stop
reasons, stability/confidence trajectories, token costs) are exactly the
dataset the eval harness samples from.
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from .models import DeepRunRow

# Keep step excerpts compact: the trace is for diagnosis, not archival replay.
_EXCERPT_CHARS = 300
_TEXT_FIELDS = ("thought", "synthesis", "surfaced_insight", "challenge")
_SIGNAL_FIELDS = ("stability", "confidence", "confidence_reported", "stop_reason", "provider_error")


class DeepRunRecorder:
    def __init__(
        self,
        *,
        run_id: str,
        workspace_id: str,
        conversation_id: str,
        branch_id: str,
        author_id: str,
        session_factory,
    ) -> None:
        self._sf = session_factory
        self._row_seed = dict(
            id=run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            branch_id=branch_id,
            author_id=author_id,
        )
        self._t0 = time.monotonic()
        self._question = ""
        self._token_parts: list[str] = []
        self._final_answer = ""
        self._steps: list[dict[str, Any]] = []
        self._stability_history: list[float] = []
        self._steers: list[str] = []
        self._tokens_used = 0
        self._depth = 0
        self._stability = 0.0
        self._confidence = 0.0
        self._status: str | None = None
        self._stop_reason = ""
        self._flushed = False

    def observe(self, event: Any) -> None:
        kind = getattr(event, "kind", "")
        if kind == "user_node" and not self._question:
            self._question = event.node.content
        elif kind == "token":
            self._token_parts.append(event.text)
        elif kind == "assistant_node":
            self._final_answer = event.node.content
        elif kind == "budget":
            self._tokens_used = int(event.tokens_used)
        elif kind == "step":
            payload = event.payload or {}
            entry: dict[str, Any] = {
                "idx": event.idx,
                "node": event.node,
                "depth": event.depth,
            }
            for key in _SIGNAL_FIELDS:
                if key in payload:
                    entry[key] = payload[key]
            for key in _TEXT_FIELDS:
                val = payload.get(key)
                if isinstance(val, str) and val:
                    entry[key] = val[:_EXCERPT_CHARS]
            self._steps.append(entry)
            self._depth = max(self._depth, int(event.depth or 0))
            stab = payload.get("stability")
            if isinstance(stab, (int, float)):
                self._stability = float(stab)
                if not self._stability_history or self._stability_history[-1] != stab:
                    self._stability_history.append(float(stab))
            conf = payload.get("confidence")
            if isinstance(conf, (int, float)):
                self._confidence = float(conf)
        elif kind == "complete":
            self._status = event.status
            self._stop_reason = event.stop_reason

    def note_steer(self, guidance: str) -> None:
        if guidance:
            self._steers.append(guidance[:_EXCERPT_CHARS])

    async def flush(self) -> None:
        """Persist the run — once, and only if it actually terminated.

        A segment that ended on `Waiting` (paused for steer) has no terminal
        status and is skipped; the registry keeps this recorder alive for the
        next segment. Persistence failures are swallowed: the run itself
        already succeeded/failed on its own terms.
        """
        if self._flushed or self._status is None:
            return
        self._flushed = True
        row = DeepRunRow(
            **self._row_seed,
            question=self._question,
            answer=self._final_answer or "".join(self._token_parts),
            status=self._status,
            stop_reason=self._stop_reason,
            depth=self._depth,
            stability=self._stability,
            confidence=self._confidence,
            tokens_used=self._tokens_used,
            duration_ms=int((time.monotonic() - self._t0) * 1000),
            trace=json.dumps(
                {
                    "steps": self._steps,
                    "stability_history": self._stability_history,
                    "steers": self._steers,
                },
                ensure_ascii=False,
            ),
        )
        try:
            async with self._sf() as session:
                session.add(row)
                await session.commit()
        except Exception:
            pass

    async def wrap(self, gen: AsyncIterator) -> AsyncIterator:
        """Relay `gen` unchanged while observing it; flush when the segment ends.

        `flush` is in a finally so a client disconnect after `Complete` was
        observed still persists; a segment cancelled before any terminal event
        simply records nothing (status is None).
        """
        try:
            async for event in gen:
                self.observe(event)
                yield event
        finally:
            await self.flush()
