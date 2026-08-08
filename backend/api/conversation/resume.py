"""Paused runs, across a restart.

`RunManager` holds live runs in a dict, which is the right shape for a run
that is *executing* — it owns an asyncio task and a queue slot, neither of
which means anything in another process. But a **paused** run is not
executing. It is waiting for a person: a guided deep run stopped at a steer
interrupt, an agent turn stopped at a sensitive tool call. That wait is
human-length — minutes, or until tomorrow morning — and it was bounded by the
server's uptime. A deploy in between turned "steer" into `404 deep run not
found (finished or expired)`, which was not even true: it had not finished and
it had not expired, it had been forgotten.

The fix is two halves, and neither works alone:

1. **The reasoning itself** lives in LangGraph's checkpoint, keyed by
   `thread_id`. That is `api/checkpointing.py` — a durable SQLite saver
   instead of a dictionary.
2. **Everything around it** — which branch, which conversation, who asked,
   what they asked, what has streamed so far — lived only in the handle. That
   is this module, and `ResumableRunRow`.

Flipping only the checkpointer would have been worse than doing nothing: the
engine would faithfully hold state that nothing could reach, and the 404 would
be unchanged while the code implied durability.

Scope, stated rather than implied: this covers **deep runs**, which pause for
guidance and are the ones people leave overnight. Agent approvals also pause,
but on a scale of seconds while a person looks at a dialog on screen; they get
the durable checkpointer and an honest error, not rehydration.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import delete as sa_delete

from ..db import SessionLocal
from .events import Grounding, from_dict, to_dict
from .models import ResumableRunRow

log = logging.getLogger(__name__)


async def remember(
    handle, *, kind: str, thread_id: str, prompt: str, steerable: bool, mode: str = ""
) -> None:
    """Write (or refresh) the row that lets `handle` be rebuilt later.

    Called when a run pauses, which is human-speed — so a whole-log write per
    pause costs nothing and keeps the reconnecting monitor's trace intact.
    """
    try:
        async with SessionLocal() as session:
            row = await session.get(ResumableRunRow, handle.run_id)
            payload = json.dumps([to_dict(e) for e in handle.events], ensure_ascii=False)
            parts = json.dumps(getattr(handle.run, "_parts", []), ensure_ascii=False)
            if row is None:
                session.add(
                    ResumableRunRow(
                        id=handle.run_id, kind=kind,
                        workspace_id=handle.workspace_id,
                        conversation_id=handle.conversation_id,
                        branch_id=handle.branch_id,
                        author_id=handle.author_id,
                        shared=handle.shared,
                        thread_id=thread_id, prompt=prompt, steerable=steerable,
                        mode=mode, answer_parts=parts, events=payload,
                    )
                )
            else:
                row.events = payload
                row.answer_parts = parts
            await session.commit()
    except Exception:  # never break a run to record it
        log.exception("Could not persist resumable run %s", handle.run_id)


async def forget(run_id: str) -> None:
    """Drop the row once the run is terminal. A row here means "still owed a
    human answer" — leaving finished ones behind would offer resumes that
    rebuild a graph only to discover it has nothing left to do."""
    try:
        async with SessionLocal() as session:
            await session.execute(
                sa_delete(ResumableRunRow).where(ResumableRunRow.id == run_id)
            )
            await session.commit()
    except Exception:
        log.exception("Could not clear resumable run %s", run_id)


async def rehydrate(run_id: str, runs) -> object | None:
    """Rebuild a paused deep run and hand back its handle, or None.

    Returns None for anything this cannot honestly restore — an unknown id, an
    agent run, or a workspace whose provider is no longer usable — so the
    caller's 404 stays a 404 rather than becoming a broken resume.
    """
    # Local imports: this module is reached from the router, which imports all
    # of these at module scope. Importing them here keeps the cycle from
    # forming while leaving the router free to import `resume` normally.
    from ..config import settings
    from ..models import WorkspaceSettings
    from ..provider_settings import resolve
    from ..reasoning_llm import make_reachability_probe
    from ..telemetry import make_llm_span_callback
    from . import engine
    from .deep_reasoning import DeepReasoningProducer, build_ouroboros_graph
    from .run_log import DeepRunRecorder
    from .runs import RunHandle

    async with SessionLocal() as session:
        row = await session.get(ResumableRunRow, run_id)
        if row is None or row.kind != "deep":
            return None
        settings_row = await session.get(WorkspaceSettings, row.workspace_id)

    resolved = resolve(settings_row)
    deep_llm = resolved.deep_llm
    if not deep_llm.api_key:
        # The workspace lost its key while the run was paused. Resuming would
        # fail on the first call; say nothing was found instead of pretending.
        log.warning("Cannot resume %s: workspace has no usable provider", run_id)
        return None

    reachability = make_reachability_probe()
    handle_box: list = []
    graph, graph_config, make_inputs, usage_reader = build_ouroboros_graph(
        # The same thread_id, which is the entire point: the graph is new, the
        # reasoning it continues is the one in the checkpoint.
        thread_id=row.thread_id,
        groq_api_key=deep_llm.api_key,
        groq_model=deep_llm.model,
        base_url=deep_llm.base_url,
        # The mode the run *started* under, not the instance default — resuming
        # into a different preset would change depth, energy and all four
        # prompts halfway through. Blank on rows written before the column
        # existed, which is exactly when the default is the right answer.
        mode=row.mode or settings.deep_reasoning_mode,
        adaptive=settings.deep_reasoning_adaptive,
        compute_budget=settings.deep_reasoning_compute_budget,
        stability_threshold=settings.deep_reasoning_stability_threshold,
        confidence_threshold=settings.deep_reasoning_confidence_threshold,
        adaptive_steer=row.steerable,
        allow_research=settings.deep_reasoning_allow_research,
        extra_callbacks=[
            make_llm_span_callback(
                workspace_id=row.workspace_id, run_id=run_id,
                provider=resolved.provider or "groq", model=deep_llm.model,
            ),
            reachability,
        ],
    )
    from .router import _grounder_for, _store  # set up at import time

    producer = DeepReasoningProducer(
        graph=graph,
        graph_config=graph_config,
        make_inputs=make_inputs,
        usage_reader=usage_reader,
        token_budget=settings.deep_reasoning_token_budget,
        deadline_s=settings.deep_reasoning_deadline_s,
        should_stop=lambda: bool(handle_box and handle_box[0].kill_requested),
        grounder=_grounder_for(row.workspace_id),
        reachability=reachability,
    )
    recorder = DeepRunRecorder(
        run_id=run_id,
        workspace_id=row.workspace_id,
        conversation_id=row.conversation_id,
        branch_id=row.branch_id,
        author_id=row.author_id,
        session_factory=SessionLocal,
        model=resolved.resolved_deep_model,
        provenance={"resumed_after_restart": True, "steerable": row.steerable},
    )

    events = [from_dict(d) for d in json.loads(row.events or "[]")]

    run = engine.ResumableRun(store=_store, producer=producer, branch_id=row.branch_id)
    # Grounding is announced once, in the run's first segment — which for a run
    # rebuilt after a restart is always *before* the pause, so it exists only in
    # the persisted log. Recovering it from there is what stops a restart from
    # publishing a grounded answer with its sources stripped off.
    cites = [e.items for e in events if isinstance(e, Grounding)]
    run.restore(parts=json.loads(row.answer_parts or "[]"), citations=cites[-1] if cites else None)
    # Replaying the log through the recorder rebuilds the trace, so the row
    # this run eventually writes covers the whole run rather than only the
    # part that happened after the restart.
    for event in events:
        recorder.observe(event)

    handle = RunHandle(
        run_id=run_id,
        workspace_id=row.workspace_id,
        conversation_id=row.conversation_id,
        branch_id=row.branch_id,
        author_id=row.author_id,
        shared=row.shared,
        run=run,
        recorder=recorder,
        status="paused",
        events=events,
    )
    handle_box.append(handle)
    runs.adopt(handle)
    log.info("Resumed paused run %s after a restart (%d events)", run_id, len(events))
    return handle
