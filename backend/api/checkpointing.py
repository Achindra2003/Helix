"""The LangGraph checkpointer that outlives a request — and the process.

Deep and agent runs pause. A guided deep run stops at a steer interrupt and
waits for a human; an agent turn stops at a sensitive tool call and waits for
approval. Both resume by continuing the graph from its checkpoint on the same
`thread_id`.

Until now that checkpoint was a `MemorySaver`, which is a dictionary. It made
"resume" mean "resume as long as nobody restarts the server" — and self-hosters
restart servers, which is the whole point of shipping a container. A person who
came back to their paused run after a deploy found it gone.

So the checkpointer is now SQLite, opened once for the life of the process:

- **Once, not per run.** `engine/ouroboros/checkpointing.py` exposes a
  context manager that opens and closes the connection around a single run,
  which is right for the engine's CLI and wrong for a server — a run resumed
  by a *later* request would find the connection closed.
- **Its own file**, not the application database. Checkpoints are engine
  working state with a schema LangGraph owns and migrates; the app's tables are
  ours. Mixing them would put a third party's migrations inside Alembic's
  territory.
- **Degrades, never blocks.** If the driver is missing, this falls back to the
  in-memory saver and says so once. A server that refuses to start because
  pauses would not survive a restart is worse than one where they do not.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

_saver: Any = None
_stack: Any = None


def _sqlite_path() -> str:
    """Beside the application database, so one volume carries both.

    The app DB may be Postgres (hosted) while checkpoints stay local — that is
    fine and even correct: a checkpoint is only meaningful to the process that
    can reach the run, and runs are in-process by design.

    "Beside the database" only names a directory when the database *is* a file.
    Against Postgres there is nowhere to derive, and the old fallback was a
    relative `./helix-checkpoints.db` — which in the container resolves to
    `/app`, the image layer, while the volume is mounted at `/data`. Paused
    runs were written somewhere that a container replacement deletes, which is
    exactly the failure this module exists to prevent, in the one configuration
    that had never been run. `CHECKPOINT_PATH` is set explicitly in the image
    for that reason; this stays as the last resort for a bare process.
    """
    if settings.checkpoint_path:
        return settings.checkpoint_path
    url = settings.database_url
    if url.startswith("sqlite") and ":///" in url:
        db_file = Path(url.split(":///", 1)[1])
        return str(db_file.with_name("helix-checkpoints.db"))
    return "./helix-checkpoints.db"


async def connect() -> None:
    """Open the durable checkpointer, or fall back loudly to memory."""
    global _saver, _stack
    if _saver is not None:
        return
    if _stack is not None:
        # A stack that outlived its saver. Overwriting the reference below
        # would strand the aiosqlite connection inside it, and that connection
        # owns a thread which goes on posting results to an event loop that has
        # since closed — `RuntimeError: Event loop is closed`, raised from a
        # thread, long after the code that caused it has finished.
        try:
            await _stack.aclose()
        except Exception:  # noqa: BLE001 — a loop that has gone is the case here
            pass
        _stack = None
    try:
        from contextlib import AsyncExitStack

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = _sqlite_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _stack = AsyncExitStack()
        _saver = await _stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(path)
        )
        log.info("Checkpoints persist to %s — paused runs survive a restart", path)
        if not settings.checkpoint_path and not settings.database_url.startswith(
            "sqlite"
        ):
            # A remote database means the operator has a persistence story;
            # a relative checkpoint file means the paused runs are not in it.
            # Durable-looking and not durable is worse than plainly in-memory,
            # because nothing complains until a deploy eats a waiting run.
            log.warning(
                "The application database is remote but checkpoints are at %s, "
                "relative to the working directory. Set CHECKPOINT_PATH to a "
                "persistent location or paused runs will not survive replacing "
                "the process.",
                path,
            )
    except Exception as exc:  # pragma: no cover - exercised by the fallback test
        from langgraph.checkpoint.memory import MemorySaver

        _saver = MemorySaver()
        log.warning(
            "Durable checkpointing unavailable (%s); paused runs will not survive "
            "a restart. Install langgraph-checkpoint-sqlite to enable it.",
            exc,
        )


async def disconnect() -> None:
    global _saver, _stack
    if _stack is not None:
        await _stack.aclose()
    _saver, _stack = None, None


def checkpointer() -> Any:
    """The live saver. Falls back to a memory saver if `connect` never ran —
    which is the case in unit tests that build a graph without an app."""
    global _saver
    if _saver is None:
        from langgraph.checkpoint.memory import MemorySaver

        _saver = MemorySaver()
    return _saver


def is_durable() -> bool:
    """Whether a paused run would actually survive a restart right now.

    The health endpoint reports this: an operator should be able to find out
    without pausing a run and rebooting to see what happens.
    """
    return type(checkpointer()).__name__ != "MemorySaver"
