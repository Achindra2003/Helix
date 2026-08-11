"""Tool observability — spans around every call, and a durable ledger.

The LLM layer has had this since the telemetry pass (`api/telemetry.py`): opt-in
OpenTelemetry GenAI spans plus a durable `llm_calls` ledger, kept deliberately
separate because sampling kills billing maths. The *tool* layer had none of it.
`run_tools` executed a handler, caught whatever came back, and returned a
string; the only record a call ever happened was a 400-character preview on an
ephemeral event stream. Nothing was queryable an hour later.

That gap is small while the catalog is three functions we wrote. It stops being
small the moment MCP lands, because then the workspace is running tools written
by someone else against someone else's server — and "which tool did what, on
whose approval, and how long did it take" becomes the question you cannot
answer during an incident. So this exists before that does.

Two instruments, mirroring the LLM layer rather than inventing a second design:

- **Spans** (GenAI semconv, `gen_ai.operation.name = execute_tool`): one per
  call, carrying the tool name, its source, and `helix.run_id` so a tool call
  groups under the run that requested it. Export stays opt-in and env-gated —
  no OTLP endpoint, no SDK, no cost, hermetic tests untouched.

- **The ledger** (`tool_calls`): one row per call. Spans are sampled and
  ephemeral; "what has this workspace's agent actually been doing" is a query,
  and it has to survive.

**Arguments are digested, never stored.** A tool's arguments routinely contain
workspace content — a search query is a sentence someone typed. The ledger is
an operational record, not a second copy of the conversation, so it keeps a
short hash: enough to tell two calls apart and spot a retry loop, useless for
reading anyone's data back out.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from opentelemetry import trace
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now
from ..telemetry import tracer

# Terminal states a call can reach. `denied` is not an error: a human refusing
# a tool is the approval gate working, and counting it as a failure would make
# the product's own safety feature look like a fault in the dashboards.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_DENIED = "denied"


def _uuid() -> str:
    return uuid4().hex


class ToolCallRow(Base):
    """One tool call's operational record."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    tool_name: Mapped[str] = mapped_column(String, index=True)
    # "builtin" today; "mcp:<server>" once the catalog has a second source.
    # Recorded from the first row so the question "what is this workspace
    # running that we didn't write" never needs a backfill.
    source: Mapped[str] = mapped_column(String, default="builtin")
    status: Mapped[str] = mapped_column(String, default=STATUS_OK)
    # Empty unless status is error. The exception type and message, clipped —
    # enough to group failures, not enough to become a log sink.
    error: Mapped[str] = mapped_column(String, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Result size rather than the result: a tool that suddenly returns 6 kB
    # where it used to return 200 bytes has changed behaviour, and that is
    # visible from the number alone.
    result_chars: Mapped[int] = mapped_column(Integer, default=0)
    args_digest: Mapped[str] = mapped_column(String, default="")
    # Set only for sensitive calls: who approved or denied it. The approval
    # gate is the product's safety story and it used to leave no trace at all —
    # "who let the agent call the web?" should be answerable a month later.
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


def digest(args: Any) -> str:
    """A short, stable fingerprint of a call's arguments.

    Not reversible and not meant to be. Two identical calls share a digest, so
    a model stuck retrying the same search is visible in the ledger without the
    ledger holding anyone's text.
    """
    try:
        canonical = json.dumps(args or {}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = repr(args)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def record_tool_call(
    *,
    workspace_id: str,
    run_id: str,
    tool_name: str,
    source: str = "builtin",
    status: str = STATUS_OK,
    error: str = "",
    latency_ms: int = 0,
    result_chars: int = 0,
    args_digest: str = "",
    decided_by: str | None = None,
) -> None:
    """Fire-and-forget ledger write.

    Same rule as `record_llm_call`: observability is an overlay. A lost row is a
    gap in a dashboard; a blocked or failed tool call would be a product bug.
    """

    async def _write() -> None:
        try:
            from ..db import SessionLocal

            async with SessionLocal() as session:
                session.add(
                    ToolCallRow(
                        workspace_id=workspace_id,
                        run_id=run_id,
                        tool_name=tool_name,
                        source=source,
                        status=status,
                        error=error[:500],
                        latency_ms=latency_ms,
                        result_chars=result_chars,
                        args_digest=args_digest,
                        decided_by=decided_by,
                    )
                )
                await session.commit()
        except Exception:
            pass

    try:
        asyncio.get_running_loop().create_task(_write())
    except RuntimeError:  # no loop (sync context) — skip, never block
        pass


class ToolObserver:
    """Everything the graph needs to record a call, bound to one run.

    Passed into `build_agent_graph` rather than read from a global, because the
    graph is also built by tests against a fake LLM — and an observer that
    needed process state would make those tests need it too. A `None` observer
    is a valid, silent one (see `NULL_OBSERVER`), so the graph never branches on
    whether telemetry is configured.
    """

    def __init__(self, *, workspace_id: str = "", run_id: str = "") -> None:
        self.workspace_id = workspace_id
        self.run_id = run_id
        # Who decided the pending approval, set by the resume path just before
        # the gate runs. Cleared after each gate pass so a later automatic call
        # can never inherit an earlier human's name.
        self.decided_by: str | None = None

    def call(self, *, name: str, args: Any, sensitive: bool, source: str = "builtin"):
        """A context manager around one tool execution: span in, ledger out."""
        return _ToolCall(self, name=name, args=args, sensitive=sensitive, source=source)

    def record_decision(self, *, name: str, approved: bool, decided_by: str | None) -> None:
        """A human's verdict on a sensitive call.

        Written as its own ledger row rather than folded into the call's row,
        because a *denied* call never executes — there would be no row to fold
        it into, and the denial is the more interesting event of the two.
        """
        span = tracer().start_span(
            f"approval {name}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "helix.approved": approved,
                "helix.run_id": self.run_id,
                "helix.workspace_id": self.workspace_id,
            },
        )
        span.add_event("approval.decided", {"approved": approved})
        span.end()
        if not approved:
            record_tool_call(
                workspace_id=self.workspace_id,
                run_id=self.run_id,
                tool_name=name,
                status=STATUS_DENIED,
                decided_by=decided_by,
            )


class _ToolCall:
    """One execution, timed and recorded however it ends."""

    def __init__(self, obs: ToolObserver, *, name: str, args: Any, sensitive: bool, source: str) -> None:
        self._obs = obs
        self._name = name
        self._digest = digest(args)
        self._sensitive = sensitive
        self._source = source
        self._span: trace.Span | None = None
        self._started = 0.0
        self.status = STATUS_OK
        self.error = ""
        self.result_chars = 0

    def __enter__(self) -> "_ToolCall":
        self._span = tracer().start_span(
            f"execute_tool {self._name}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": self._name,
                "helix.tool.source": self._source,
                "helix.tool.sensitive": self._sensitive,
                "helix.tool.args_digest": self._digest,
                "helix.run_id": self._obs.run_id,
                "helix.workspace_id": self._obs.workspace_id,
            },
        )
        self._started = time.monotonic()
        return self

    def failed(self, exc: BaseException) -> None:
        self.status = STATUS_ERROR
        self.error = f"{type(exc).__name__}: {exc}"

    def __exit__(self, exc_type, exc, tb) -> bool:
        latency_ms = int((time.monotonic() - self._started) * 1000)
        if self._span is not None:
            self._span.set_attribute("helix.tool.status", self.status)
            self._span.set_attribute("helix.tool.result_chars", self.result_chars)
            if self.status == STATUS_ERROR:
                self._span.set_attribute("error.type", self.error.split(":")[0])
            self._span.end()
        record_tool_call(
            workspace_id=self._obs.workspace_id,
            run_id=self._obs.run_id,
            tool_name=self._name,
            source=self._source,
            status=self.status,
            error=self.error,
            latency_ms=latency_ms,
            result_chars=self.result_chars,
            args_digest=self._digest,
            # Only sensitive calls had a human in the loop; stamping a name on
            # an automatic call would invent an approval nobody gave.
            decided_by=self._obs.decided_by if self._sensitive else None,
        )
        return False  # never swallow: the graph turns failures into results


# The graph always has an observer. This one records into a workspace-less,
# run-less void, which is exactly right for a unit test driving a fake graph.
NULL_OBSERVER = ToolObserver()
