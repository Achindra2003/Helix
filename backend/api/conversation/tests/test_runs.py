"""Background deep-run manager: runs outlive subscribers, reconnect replays,
workspace caps queue fairly, and kill works in every state.

These drive `RunManager` directly with scripted generators — no HTTP, no
LangGraph — because the durability claim ("a dropped client does not kill the
run") is about the manager's task model, not the producer.
"""
import asyncio

import pytest

from api.conversation.events import Complete, Done, RunQueued, Token, Waiting
from api.conversation.runs import RunHandle, RunManager


class FakeRecorder:
    """Stands in for DeepRunRecorder: passthrough wrap, steer notes captured."""

    def __init__(self):
        self.steers = []

    def note_steer(self, guidance):
        self.steers.append(guidance)

    async def wrap(self, gen):
        async for event in gen:
            yield event


def _handle(run_id="r1", wid="w1", **kw):
    return RunHandle(
        run_id=run_id,
        workspace_id=wid,
        conversation_id="c1",
        branch_id="b1",
        author_id="u1",
        shared=False,  # keep the WS relay out of unit tests
        run=None,
        recorder=FakeRecorder(),
        **kw,
    )


async def _drain(manager, handle, after=0):
    return [e async for e in manager.stream(handle, after=after)]


async def _settle(handle):
    """Wait for the driving task to finish."""
    if handle._task is not None:
        await handle._task


@pytest.mark.asyncio
async def test_run_completes_with_no_subscriber_at_all():
    manager = RunManager(per_workspace=2)
    handle = _handle()

    async def gen():
        yield Token(text="answer")
        yield Complete(stop_reason="converged", status="done")
        yield Done()

    manager.launch(handle=handle, start=gen)
    await _settle(handle)  # nobody ever subscribed

    assert handle.status == "done"
    kinds = [e.kind for e in handle.events]
    assert kinds == ["token", "complete", "done"]


@pytest.mark.asyncio
async def test_subscriber_disconnect_does_not_stop_the_run():
    manager = RunManager(per_workspace=2)
    handle = _handle()
    step = asyncio.Event()

    async def gen():
        yield Token(text="a")
        await step.wait()  # run is mid-flight while the client vanishes
        yield Token(text="b")
        yield Complete(stop_reason="converged", status="done")
        yield Done()

    manager.launch(handle=handle, start=gen)

    async def subscriber():
        async for _ in manager.stream(handle):
            pass

    sub = asyncio.create_task(subscriber())
    await asyncio.sleep(0)  # let it attach and read the first token
    sub.cancel()  # the "dropped connection"
    step.set()
    await _settle(handle)

    assert handle.status == "done"
    assert [e.kind for e in handle.events][-1] == "done"


@pytest.mark.asyncio
async def test_reconnect_replays_from_after():
    manager = RunManager(per_workspace=2)
    handle = _handle()

    async def gen():
        yield Token(text="one")
        yield Token(text="two")
        yield Complete(stop_reason="converged", status="done")
        yield Done()

    manager.launch(handle=handle, start=gen)
    await _settle(handle)

    full = await _drain(manager, handle)
    assert [e.kind for e in full] == ["token", "token", "complete", "done"]
    # A reconnect that already saw 2 events gets exactly the tail.
    tail = await _drain(manager, handle, after=2)
    assert [e.kind for e in tail] == ["complete", "done"]


@pytest.mark.asyncio
async def test_workspace_cap_queues_then_promotes():
    manager = RunManager(per_workspace=1)
    first, second = _handle("r1"), _handle("r2")
    release = asyncio.Event()

    def slow():
        async def gen():
            await release.wait()
            yield Complete(stop_reason="converged", status="done")
            yield Done()
        return gen()

    def quick():
        async def gen():
            yield Complete(stop_reason="converged", status="done")
            yield Done()
        return gen()

    manager.launch(handle=first, start=slow)
    manager.launch(handle=second, start=quick)

    assert first.status == "running"
    assert second.status == "queued"
    assert isinstance(second.events[0], RunQueued)
    assert second.events[0].position == 1
    assert manager.queue_position(second) == 1

    release.set()
    await _settle(first)
    await _settle(second)  # promoted when the slot freed
    assert first.status == "done" and second.status == "done"


@pytest.mark.asyncio
async def test_other_workspace_is_not_blocked_by_the_cap():
    manager = RunManager(per_workspace=1)
    busy, other = _handle("r1", wid="w1"), _handle("r2", wid="w2")
    release = asyncio.Event()

    def slow():
        async def gen():
            await release.wait()
            yield Done()
        return gen()

    def quick():
        async def gen():
            yield Done()
        return gen()

    manager.launch(handle=busy, start=slow)
    manager.launch(handle=other, start=quick)
    await _settle(other)
    assert other.status == "done"  # ran immediately despite w1 being full
    release.set()
    await _settle(busy)


@pytest.mark.asyncio
async def test_kill_running_run_cooperatively():
    manager = RunManager(per_workspace=2)
    handle = _handle()
    started = asyncio.Event()

    async def gen():
        # Mirrors the producer's should_stop contract: check between events.
        yield Token(text="thinking…")
        started.set()
        while not handle.kill_requested:
            await asyncio.sleep(0)
        yield Complete(stop_reason="stopped", status="killed")
        yield Done()

    manager.launch(handle=handle, start=gen)
    await started.wait()
    manager.kill(handle)
    await _settle(handle)
    assert handle.status == "killed"


@pytest.mark.asyncio
async def test_kill_queued_run_closes_it_and_promotion_skips_it():
    manager = RunManager(per_workspace=1)
    first, queued = _handle("r1"), _handle("r2")
    release = asyncio.Event()

    def slow():
        async def gen():
            await release.wait()
            yield Done()
        return gen()

    manager.launch(handle=first, start=slow)
    manager.launch(handle=queued, start=slow)
    manager.kill(queued)

    # Killed while queued: terminal frames appended so any stream ends clean.
    assert queued.status == "killed"
    assert [e.kind for e in queued.events] == ["queued", "complete", "done"]

    release.set()
    await _settle(first)
    assert queued._task is None  # promotion skipped the killed run


@pytest.mark.asyncio
async def test_paused_run_ends_segment_stream_then_steer_continues():
    manager = RunManager(per_workspace=2)
    handle = _handle()

    async def segment_one():
        yield Token(text="draft")
        yield Waiting(reason="steer")

    async def segment_two():
        yield Token(text="refined")
        yield Complete(stop_reason="converged", status="done")
        yield Done()

    manager.launch(handle=handle, start=segment_one)
    first_view = await _drain(manager, handle)  # ends at the pause, like old SSE
    assert [e.kind for e in first_view] == ["token", "waiting"]
    assert handle.status == "paused"

    resume_from = handle.seq
    manager.steer(handle, segment_two)
    continuation = await _drain(manager, handle, after=resume_from)
    assert [e.kind for e in continuation] == ["token", "complete", "done"]
    assert handle.status == "done"


@pytest.mark.asyncio
async def test_prune_drops_only_settled_handles():
    manager = RunManager(per_workspace=2, retention_s=0.0)
    done, running = _handle("r1"), _handle("r2")
    release = asyncio.Event()

    async def quick():
        yield Done()

    def slow():
        async def gen():
            await release.wait()
            yield Done()
        return gen()

    manager.launch(handle=done, start=quick)
    await _settle(done)
    manager.launch(handle=running, start=slow)

    done.ts = 0  # long past any retention window
    running.ts = 0  # ...but an in-flight run must survive regardless of age
    manager.prune()
    assert manager.get("r1") is None  # settled + past retention
    assert manager.get("r2") is not None  # in flight: never pruned
    release.set()
    await _settle(running)
