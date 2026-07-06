"""Background deep-run execution — runs decoupled from HTTP requests.

Deep runs used to live *inside* the SSE response: the StreamingResponse drove
the producer generator, so a dropped connection (laptop lid, flaky wifi, page
nav) cancelled a three-minute run mid-thought. This module inverts that:

- The run executes in a **server-side task**, appending every event to a
  per-run log. It finishes — persisting the assistant node and the durable
  `deep_runs` record — whether or not anyone is still watching.
- SSE responses become **subscribers**: replay the log from a sequence number,
  then follow live. The same call serves the initial stream and reconnects
  (`GET /conversations/deep/runs/{run_id}/stream?after=N`).
- The **workspace WS relay moves into the driver**, so teammates watching a
  shared branch keep seeing the trace even after the author disconnects.
- A **per-workspace concurrency cap** with a FIFO queue protects the
  workspace's own rate limits (BYO keys): runs beyond the cap wait as
  `queued` (a visible event, not a mystery) and start when a slot frees.

Scope note (single-instance by design): handles are in-process, like the
realtime rooms. A *process restart* still loses in-flight runs — the durable
record row is the evidence trail; restart-surviving runs need the LangGraph
sqlite checkpointer plus a persisted run registry, both documented seams.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable

from .. import realtime
from .events import Complete, Done, Event, RunQueued, Waiting, to_dict
from .run_log import DeepRunRecorder

# Terminal statuses: the run will never append another event.
_TERMINAL = ("done", "error", "killed")


@dataclass
class RunHandle:
    """One deep run's live state: the event log and everything control needs."""

    run_id: str
    workspace_id: str
    conversation_id: str
    branch_id: str
    author_id: str
    shared: bool  # private threads are never relayed to the room
    run: object  # engine.ResumableRun — steer/paused live here
    recorder: DeepRunRecorder
    status: str = "queued"  # queued | running | paused | done | error | killed
    events: list[Event] = field(default_factory=list)
    kill_requested: bool = False
    ts: float = field(default_factory=time.time)
    _wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    # Deferred first segment, held while the run waits in the queue.
    _start: Callable[[], AsyncIterator[Event]] | None = None
    _task: asyncio.Task | None = None

    def _notify(self) -> None:
        """Wake every subscriber; each re-arms the event after draining."""
        self._wakeup.set()
        self._wakeup = asyncio.Event()

    @property
    def seq(self) -> int:
        return len(self.events)

    @property
    def finished(self) -> bool:
        return self.status in _TERMINAL


class RunManager:
    """Owns every live deep run in the process: launch, subscribe, steer, kill."""

    def __init__(self, *, per_workspace: int = 2, retention_s: float = 30 * 60) -> None:
        self._handles: dict[str, RunHandle] = {}
        self._per_workspace = max(1, per_workspace)
        self._retention_s = retention_s
        self._active: dict[str, int] = {}  # workspace_id -> running count
        self._waiting: dict[str, deque[str]] = {}  # workspace_id -> queued run_ids

    # --- lifecycle -----------------------------------------------------------

    def launch(
        self,
        *,
        handle: RunHandle,
        start: Callable[[], AsyncIterator[Event]],
    ) -> RunHandle:
        """Register the run and start it now, or queue it behind the cap."""
        self.prune()
        self._handles[handle.run_id] = handle
        wid = handle.workspace_id
        if self._active.get(wid, 0) < self._per_workspace:
            self._begin(handle, start)
        else:
            handle._start = start
            queue = self._waiting.setdefault(wid, deque())
            queue.append(handle.run_id)
            self._append(handle, RunQueued(position=len(queue)))
        return handle

    def _begin(self, handle: RunHandle, start: Callable[[], AsyncIterator[Event]]) -> None:
        wid = handle.workspace_id
        self._active[wid] = self._active.get(wid, 0) + 1
        handle.status = "running"
        handle._task = asyncio.create_task(self._drive(handle, start()))

    async def _drive(self, handle: RunHandle, gen: AsyncIterator[Event]) -> None:
        """Run one segment to its end, whoever is (or isn't) watching.

        Sets the handle status from what the stream actually said: `Waiting`
        pauses (steer will start the next segment), `Complete` carries the
        engine's own status, a bare end without either is `done`.
        """
        segment_status = "done"
        paused = False
        try:
            async for event in handle.recorder.wrap(gen):
                if isinstance(event, Complete):
                    segment_status = event.status
                if isinstance(event, Waiting):
                    paused = True
                self._append(handle, event)
                await self._relay(handle, event)
        except asyncio.CancelledError:
            segment_status = "killed"
        except Exception:  # a driver bug must still release the slot
            segment_status = "error"
        finally:
            handle.status = "paused" if paused else segment_status
            handle.ts = time.time()
            handle._notify()
            wid = handle.workspace_id
            self._active[wid] = max(0, self._active.get(wid, 1) - 1)
            self._promote(wid)

    def _promote(self, workspace_id: str) -> None:
        """Start the next queued run in this workspace, if a slot is free."""
        queue = self._waiting.get(workspace_id)
        while (
            queue
            and self._active.get(workspace_id, 0) < self._per_workspace
        ):
            run_id = queue.popleft()
            handle = self._handles.get(run_id)
            if handle is None or handle._start is None or handle.kill_requested:
                continue
            start, handle._start = handle._start, None
            self._begin(handle, start)

    def _append(self, handle: RunHandle, event: Event) -> None:
        handle.events.append(event)
        handle._notify()

    async def _relay(self, handle: RunHandle, event: Event) -> None:
        """Fan out to the workspace room (shared threads only, author excluded)
        — the exact semantics `_streamed_run` had, moved off the HTTP stream."""
        if not handle.shared:
            return
        await realtime.broadcast(
            handle.workspace_id,
            {
                "kind": "run_event",
                "workspace_id": handle.workspace_id,
                "conversation_id": handle.conversation_id,
                "branch_id": handle.branch_id,
                "author_id": handle.author_id,
                "event": to_dict(event),
            },
            exclude_user=handle.author_id,
        )

    # --- control -------------------------------------------------------------

    def get(self, run_id: str) -> RunHandle | None:
        self.prune()
        return self._handles.get(run_id)

    def steer(self, handle: RunHandle, resume: Callable[[], AsyncIterator[Event]]) -> None:
        """Start the continuation segment of a paused run (caller validates)."""
        self._begin(handle, resume)

    def kill(self, handle: RunHandle) -> None:
        """Stop a run: cooperatively if running (the producer checks the flag
        between events), immediately if it's still queued or paused."""
        handle.kill_requested = True
        if handle.status in ("queued", "paused"):
            # No task is driving a queued/paused run; close it out directly with
            # well-formed terminal frames so every subscriber's stream ends clean.
            handle.status = "killed"
            self._append(handle, Complete(stop_reason="stopped", status="killed"))
            self._append(handle, Done())

    def queue_position(self, handle: RunHandle) -> int | None:
        """1-based position among this workspace's queued runs, if queued."""
        queue = self._waiting.get(handle.workspace_id)
        if not queue or handle.status != "queued":
            return None
        try:
            return list(queue).index(handle.run_id) + 1
        except ValueError:
            return None

    def prune(self) -> None:
        """Drop finished handles past retention (the DB row is the archive) and
        expired paused runs (same TTL the old registry enforced)."""
        cutoff = time.time() - self._retention_s
        for rid in [
            r
            for r, h in self._handles.items()
            if h.ts < cutoff and h.status in (*_TERMINAL, "paused")
        ]:
            self._handles.pop(rid, None)

    # --- subscription --------------------------------------------------------

    async def stream(self, handle: RunHandle, after: int = 0) -> AsyncIterator[Event]:
        """Replay the log from `after`, then follow live.

        Ends when the log is drained and the run is terminal *or paused* —
        a paused run ends the segment stream exactly like the old per-segment
        SSE did (the `Waiting` frame is in the log; the client steers next).
        Cancellation (client gone) detaches the subscriber only; the driver
        task is not touched.
        """
        seq = max(0, after)
        while True:
            while seq < len(handle.events):
                yield handle.events[seq]
                seq += 1
            if handle.finished or handle.status == "paused":
                return
            wakeup = handle._wakeup
            if seq >= len(handle.events):
                await wakeup.wait()
