"""ORM models for conversations, branches, and nodes (the M2 schema).

These persist the same shapes the engine works in (`store.Conversation` /
`store.Branch` / `events.Node`). `DbStore` maps rows <-> those DB-agnostic
dataclasses, so the engine never imports SQLAlchemy. The fork model is a pointer
(`fork_node_id` + `head_node_id`) with `parent_id` chaining across branches —
identical semantics to `InMemoryStore`, just durable.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import _now


def _uuid() -> str:
    return uuid4().hex


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    author_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(String, default="shared")  # shared|private
    default_branch_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # What the thread concluded. A branch verdict says which exploration won;
    # this says what the team now believes, which is the thing someone asks for
    # when they say "so what did we land on?". Empty until a human writes it —
    # Helix can draft it from the branches, but a draft nobody accepted is not
    # a conclusion.
    conclusion: Mapped[str] = mapped_column(Text, default="")
    concluded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    concluded_at: Mapped[datetime | None] = mapped_column(nullable=True)


class BranchRow(Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String, default="main")
    parent_branch_id: Mapped[str | None] = mapped_column(String, nullable=True)
    fork_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    head_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # --- the exploration's own lifecycle -------------------------------------
    # A branch used to record only where it came from. It could be created and
    # never finished, which is why a tree of them was a pile of experiments
    # rather than a decision record. `intent` is what this exploration is
    # trying (asked at fork time); the resolution fields are what came of it.
    #
    # Deliberately NOT enforced: that one branch per fork point is adopted.
    # Two siblings can both be adopted — a team really can take something from
    # each — and having the system infer a verdict nobody recorded would defeat
    # the purpose of recording verdicts.
    intent: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="open")  # open|adopted|abandoned
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ConversationReferenceRow(Base):
    """A live link from one conversation to another it pulls context from.

    Distinct from a fork (a branch *inside* one conversation tree): this points at a
    separate conversation in the same workspace whose current context is folded into
    the linking conversation's turns at send time. Directional and non-recursive — a
    reference's own references are not followed, so links can't loop.
    """

    __tablename__ = "conversation_references"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    referenced_conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id")
    )
    created_at: Mapped[datetime] = mapped_column(default=_now)


class DeepRunRow(Base):
    """One persisted Deep Reasoning run: signals, outcome, and a compact trace.

    The monitor shows a run live and then it's gone — this row is the durable
    record ("the deep run gave a weird answer yesterday" becomes inspectable),
    and accumulated rows are the raw material for evals: real questions, real
    stop reasons, real stability/confidence trajectories.
    """

    __tablename__ = "deep_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # the run_id
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    branch_id: Mapped[str] = mapped_column(String)
    author_id: Mapped[str] = mapped_column(String)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String)  # done|killed|error
    stop_reason: Mapped[str] = mapped_column(String, default="")
    depth: Mapped[int] = mapped_column(Integer, default=0)
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    trace: Mapped[str] = mapped_column(Text, default="[]")  # JSON: steps/steers/history
    # Provenance: which model/prompts/thresholds produced this run. When
    # behaviour shifts after a model or config swap, attribution is a query —
    # this cannot be retrofitted onto old runs, so it is stamped on every one.
    model: Mapped[str] = mapped_column(String, default="")
    provenance: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(default=_now)


class NodeRow(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String)  # user|assistant|system
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class BranchVoteRow(Base):
    """One member saying "I'd back this exploration".

    Branching is the product's signature move and it had no counter-move: a
    team could fork four ways and then had nothing but prose to narrow it
    again. `resolve_branch` recorded the verdict, but a verdict is the *end* of
    converging — one person writing down a decision the room never got to
    express an opinion on.

    Approval voting, deliberately: a member may back any number of branches,
    and backing one says nothing about the others. Single-choice would force a
    false precision ("rank these four") when the useful signal is usually
    "either of these two works, the other two don't" — and it would make the
    write a read-modify-write across sibling rows instead of one insert.

    A vote is not a verdict and does not resolve anything. It is the reading
    someone takes *before* deciding, which is why the tally is shown in the
    adopt dialog rather than driving it.
    """

    __tablename__ = "branch_votes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    branch_id: Mapped[str] = mapped_column(ForeignKey("branches.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    __table_args__ = (
        # One member, one voice per branch. Enforced here rather than by a
        # read-then-write, which races two clicks from two tabs.
        UniqueConstraint("branch_id", "user_id", name="uq_branch_votes_branch_user"),
    )


class NodeCitationRow(Base):
    """One document chunk an assistant node was grounded on.

    A table rather than a JSON column on `NodeRow`, because the question the
    research room actually asks is "which answers cited this paper?" — that is
    a query over `document_id`, not a field to render. A blob would answer the
    render and refuse the query.

    Until this existed, citations lived *only* in the browser: the `grounding`
    SSE frame reached the client, was held in a module-level record in
    ChatView, and was gone on the next reload. The reply survived; the evidence
    for it did not, which is the one thing a grounded answer cannot afford.

    Denormalised on purpose. `filename` and the document's own metadata are
    copied in at write time so a citation still reads correctly after the
    document is renamed or deleted — the claim was made against *that* text on
    *that* day, and a dangling join would quietly rewrite history.
    """

    __tablename__ = "node_citations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.id"), index=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String, default="")
    # How the source is named in the chip and the export: "Smith et al. (2019)"
    # once someone has catalogued the document, the filename until then.
    cite_as: Mapped[str] = mapped_column(String, default="")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    # Position in the citation list as the retriever ranked it, so the chips
    # render in relevance order without re-sorting on a float.
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ResumableRunRow(Base):
    """A run that is paused and waiting for a human, held across a restart.

    `deep_runs` is the archive of runs that *finished*; this is the much
    smaller set that has not. A guided deep run stops at a steer interrupt and
    an agent turn stops at a sensitive tool call, and both then wait for as
    long as a person takes — minutes, or overnight. Until this table existed
    that wait was bounded by the server's uptime: `RunManager` held the handle
    in a dict, so a deploy or a reboot turned "steer" into a 404 and the work
    was simply gone.

    Everything here is what it takes to build that run again: `thread_id` is
    where LangGraph's own checkpoint lives (the reasoning itself), and `events`
    is the log a reconnecting monitor replays so the trace does not restart
    blank. Rows are deleted the moment a run reaches a terminal state — a row
    here means "still owed a human answer", nothing else.
    """

    __tablename__ = "resumable_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # the run_id
    kind: Mapped[str] = mapped_column(String)  # deep | agent
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    branch_id: Mapped[str] = mapped_column(String)
    author_id: Mapped[str] = mapped_column(String)
    # Private threads are never relayed to the workspace room; the rebuilt
    # handle has to remember that or a resume would leak one.
    shared: Mapped[bool] = mapped_column(Boolean, default=True)
    # The LangGraph checkpoint key. Without it the engine cannot be told where
    # to continue from, and every other column here is useless.
    thread_id: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(Text, default="")
    steerable: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which reasoning preset the run started under. Rebuilt runs used to take
    # the instance default, so a paused Explore run came back as Analyze — a
    # different depth, energy curve and set of four prompts, silently, halfway
    # through. Empty means "whatever the instance default is", which is what
    # every row written before this column existed meant.
    mode: Mapped[str] = mapped_column(String, default="")
    # Token text streamed before the pause. The final assistant node is built
    # from every segment's tokens joined, so dropping this would silently
    # publish a reply missing its first half.
    answer_parts: Mapped[str] = mapped_column(Text, default="")
    events: Mapped[str] = mapped_column(Text, default="[]")  # JSON: the log
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
