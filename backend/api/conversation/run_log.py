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
import logging
import time
from typing import Any, AsyncIterator

from .models import DeepRunRow

log = logging.getLogger(__name__)

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
        model: str = "",
        provenance: dict[str, Any] | None = None,
    ) -> None:
        self._sf = session_factory
        self._row_seed = dict(
            id=run_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            branch_id=branch_id,
            author_id=author_id,
            # Stamped at launch: when behaviour shifts after a model/config
            # swap, old runs answer "what produced you?" — unretrofittable.
            model=model,
            provenance=json.dumps(provenance or {}, ensure_ascii=False),
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
        elif kind in ("tool_call", "tool_result"):
            # Agent runs were archived with an empty trace. The recorder only
            # ever understood `step` events, which deep runs emit and agent
            # runs do not — so a row existed saying an agent run happened and
            # nothing at all about what it did. The tool transcript *is* the
            # agent run's trace, in the same sense the reasoning steps are a
            # deep run's, and "the agent gave a weird answer yesterday" is only
            # answerable if the calls behind it were kept.
            entry: dict[str, Any] = {
                "idx": len(self._steps),
                "node": kind,
                "depth": 0,
                "tool": getattr(event, "name", ""),
            }
            if kind == "tool_call":
                # Arguments, not a digest: unlike the ledger, this trace is
                # workspace data already — it lives beside the conversation it
                # came from and is read by the same people.
                entry["arguments"] = getattr(event, "arguments", {})
                entry["sensitive"] = bool(getattr(event, "sensitive", False))
            else:
                entry["status"] = getattr(event, "status", "")
                entry["thought"] = str(getattr(event, "content", ""))[:_EXCERPT_CHARS]
            self._steps.append(entry)
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
            # Still swallowed — the run itself already succeeded on its own
            # terms, and losing its record must not fail it. But it is logged
            # now: this `except` used to be a bare `pass`, and that silence is
            # how "no deep run is ever recorded on Postgres" stayed invisible.
            # A history that quietly stops filling in is worse than one that
            # errors, because nobody goes looking for rows they think exist.
            log.exception("Failed to persist the record for deep run %s", row.id)

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
