"""ORM models for conversations, branches, and nodes (the M2 schema).

These persist the same shapes the engine works in (`store.Conversation` /
`store.Branch` / `events.Node`). `DbStore` maps rows <-> those DB-agnostic
dataclasses, so the engine never imports SQLAlchemy. The fork model is a pointer
(`fork_node_id` + `head_node_id`) with `parent_id` chaining across branches —
identical semantics to `InMemoryStore`, just durable.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, Text
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
