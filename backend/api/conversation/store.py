"""The persistence seam: `ConversationStore`.

The engine reads and writes conversations, branches, and nodes *only* through
this interface. `InMemoryStore` below is the reference implementation used by the
engine's own tests; the DB-backed store (SQLite/Postgres) implements the same
Protocol later and is swapped in with no change to engine code.

The fork model lives here too: a branch is a *pointer* (`fork_node_id` +
`head_node_id`), and `get_history` walks `parent_id` from the head back to the
root — crossing branch boundaries — so forking copies no history (O(1) write,
O(depth) read). This is the read path the design flags as the riskiest part, so
it is the most heavily tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import uuid4

from .events import Node


def _uuid() -> str:
    return uuid4().hex


# One citation's shape, and the only place it is defined. Retrieval hands back
# whatever its ranker produced; this narrows it to the five fields the product
# renders and exports, so a change in a retriever cannot silently widen what
# gets persisted on every reply.
_CITATION_FIELDS = (
    "document_id",
    "filename",
    # How the source should be named — "Smith et al. (2019)" once catalogued.
    # Frozen at write time with everything else here: renaming a document must
    # not retroactively change what an old answer said it was citing.
    "cite_as",
    "chunk_index",
    "score",
    "excerpt",
)

# Excerpts are the citation's evidence, not the document. Long enough to show
# the sentence a claim rests on, short enough that a 6-source reply doesn't
# double the size of the history response.
_EXCERPT_CHARS = 600


def _clean_citations(items: list[dict] | None) -> list[dict]:
    """Narrow raw retrieval hits to the persisted citation shape."""
    out: list[dict] = []
    for item in items or []:
        cite = {k: item.get(k) for k in _CITATION_FIELDS if item.get(k) is not None}
        if not cite.get("document_id"):
            continue  # a citation that can't be traced back is not a citation
        cite["chunk_index"] = int(cite.get("chunk_index") or 0)
        cite["score"] = float(cite.get("score") or 0.0)
        cite["filename"] = str(cite.get("filename") or "")
        # Falls back to the filename so a citation always has a visible name,
        # including for replies written before cataloguing existed.
        cite["cite_as"] = str(cite.get("cite_as") or cite["filename"])
        cite["excerpt"] = str(cite.get("excerpt") or "")[:_EXCERPT_CHARS]
        out.append(cite)
    return out


@dataclass
class Conversation:
    id: str
    workspace_id: str
    author_id: str
    title: str
    visibility: str  # "shared" | "private"
    default_branch_id: str
    # What the thread concluded, written by a human (Helix can draft it).
    conclusion: str = ""
    concluded_by: str | None = None
    concluded_at: datetime | None = None


@dataclass
class Branch:
    id: str
    conversation_id: str
    name: str
    parent_branch_id: str | None
    fork_node_id: str | None
    head_node_id: str | None
    # What this exploration is trying, and what came of it. Defaulted so every
    # existing caller and fixture keeps working unchanged.
    intent: str = ""
    status: str = "open"  # open | adopted | abandoned
    resolution: str = ""
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    # Members who have said they'd back this exploration. Ids, not a count, so
    # the UI can show *you* whether you already voted without a second request
    # — and so a tally can name its backers when a verdict is being written.
    votes: list[str] = field(default_factory=list)


@runtime_checkable
class ConversationStore(Protocol):
    """The contract every store (in-memory, SQLite, Postgres) satisfies."""

    async def create_conversation(
        self, *, workspace_id: str, author_id: str, title: str, visibility: str
    ) -> Conversation:
        """Create a conversation and its root ('main') branch."""
        ...

    async def get_conversation(self, conversation_id: str) -> Conversation | None: ...

    async def list_conversations(
        self, workspace_id: str, viewer_id: str | None = None
    ) -> list[Conversation]:
        """Conversations in a workspace (creation order). A `private` conversation
        is visible only to its author; `shared` ones to everyone. `viewer_id=None`
        returns all (used by the engine/tests where there is no requesting user)."""
        ...

    async def get_branch(self, branch_id: str) -> Branch | None: ...

    async def list_branches(self, conversation_id: str) -> list[Branch]:
        """The branch tree for a conversation (creation order)."""
        ...

    async def add_node(
        self,
        *,
        branch_id: str,
        role: str,
        content: str,
        author_id: str | None,
        token_count: int = 0,
        citations: list[dict] | None = None,
    ) -> Node:
        """Append an immutable node to a branch, stamping a monotonic `seq` and
        chaining `parent_id` to the branch's current head; advances the head.

        `citations` are the document chunks a grounded reply drew on. Written
        in the same call as the content they justify, so a reply and its
        evidence can never be persisted apart.
        """
        ...

    async def get_history(self, branch_id: str) -> list[Node]:
        """Nodes root -> head for a branch, walking `parent_id` across branch
        boundaries (the fork read path). Nodes come back with their citations."""
        ...

    async def create_branch(
        self, *, conversation_id: str, from_node_id: str, name: str, intent: str = ""
    ) -> Branch:
        """Fork: one new branch row pointing at `from_node_id`; no history copied."""
        ...

    async def set_conclusion(
        self, *, conversation_id: str, conclusion: str, concluded_by: str
    ) -> Conversation | None:
        """Record (or clear, with an empty string) what the thread concluded."""
        ...

    async def resolve_branch(
        self, *, branch_id: str, status: str, resolution: str, resolved_by: str
    ) -> Branch | None:
        """Record what came of an exploration. `status="open"` reopens it.

        Never deletes: an abandoned branch stays readable forever, because the
        alternative you rejected is half of why the decision is defensible.
        """
        ...

    async def toggle_branch_vote(self, *, branch_id: str, user_id: str) -> bool:
        """Back this exploration, or withdraw backing. Returns the new state.

        Idempotent per member: clicking twice leaves no trace, which is what
        makes a vote safe to cast on a hunch.
        """
        ...

    async def add_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        """Link another conversation in as live background context (idempotent)."""
        ...

    async def remove_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        """Unlink a previously referenced conversation (no-op if absent)."""
        ...

    async def list_reference_ids(self, conversation_id: str) -> list[str]:
        """Referenced conversation ids for `conversation_id`, in link order."""
        ...

    async def delete_last_turn(self, *, branch_id: str, user_id: str) -> list[str]:
        """Remove the branch's trailing user message, and its assistant reply
        if one landed — the "delete/edit my last message" operation. Safe only
        when nothing has forked from either node, so the tree stays intact for
        anyone who already branched off it. Returns the removed node ids
        (reply first, then the user message, when both are removed).

        Raises ``KeyError`` if the branch is empty, ``PermissionError`` if the
        caller didn't author the trailing user turn, ``ValueError`` if a
        branch has forked from either node.
        """
        ...

    async def rename_conversation(
        self, conversation_id: str, title: str
    ) -> Conversation | None:
        """Set a conversation's title. Returns the updated conversation, or
        None if it doesn't exist."""
        ...

    async def delete_conversation(self, conversation_id: str) -> list[str]:
        """Delete a conversation with all its branches, nodes, and reference
        links (in both directions). Returns the removed node ids so callers
        can clean overlays (embeddings). KeyError if it doesn't exist."""
        ...

    async def rename_branch(self, branch_id: str, name: str) -> Branch | None:
        """Set a branch's name. Returns the updated branch, or None."""
        ...

    async def delete_branch(self, branch_id: str) -> list[str]:
        """Delete a fork branch and its own nodes (never inherited ancestors,
        which belong to other branches). Refused for the conversation's main
        branch and for any branch something else has forked from — the same
        keep-the-tree-intact rule as `delete_last_turn`. Returns the removed
        node ids. KeyError if missing; ValueError if refused."""
        ...


class InMemoryStore:
    """Reference `ConversationStore` for the engine's tests (no database)."""

    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.branches: dict[str, Branch] = {}
        self.nodes: dict[str, Node] = {}
        self._next_seq: dict[str, int] = {}  # per-branch monotonic counter
        self.references: dict[str, list[str]] = {}  # conv_id -> linked conv_ids

    async def create_conversation(
        self, *, workspace_id: str, author_id: str, title: str, visibility: str
    ) -> Conversation:
        conv_id, branch_id = _uuid(), _uuid()
        self.branches[branch_id] = Branch(
            id=branch_id,
            conversation_id=conv_id,
            name="main",
            parent_branch_id=None,
            fork_node_id=None,
            head_node_id=None,
        )
        self._next_seq[branch_id] = 0
        conv = Conversation(
            id=conv_id,
            workspace_id=workspace_id,
            author_id=author_id,
            title=title,
            visibility=visibility,
            default_branch_id=branch_id,
        )
        self.conversations[conv_id] = conv
        return conv

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def list_conversations(
        self, workspace_id: str, viewer_id: str | None = None
    ) -> list[Conversation]:
        return [
            c
            for c in self.conversations.values()
            if c.workspace_id == workspace_id
            and (
                viewer_id is None
                or c.visibility != "private"
                or c.author_id == viewer_id
            )
        ]

    async def get_branch(self, branch_id: str) -> Branch | None:
        return self.branches.get(branch_id)

    async def list_branches(self, conversation_id: str) -> list[Branch]:
        return [b for b in self.branches.values() if b.conversation_id == conversation_id]

    async def add_node(
        self,
        *,
        branch_id: str,
        role: str,
        content: str,
        author_id: str | None,
        token_count: int = 0,
        citations: list[dict] | None = None,
    ) -> Node:
        branch = self.branches[branch_id]
        seq = self._next_seq[branch_id]
        self._next_seq[branch_id] = seq + 1
        node = Node(
            id=_uuid(),
            branch_id=branch_id,
            parent_id=branch.head_node_id,
            seq=seq,
            role=role,  # type: ignore[arg-type]
            content=content,
            author_id=author_id,
            token_count=token_count,
            citations=_clean_citations(citations),
        )
        self.nodes[node.id] = node
        branch.head_node_id = node.id
        return node

    async def get_history(self, branch_id: str) -> list[Node]:
        branch = self.branches[branch_id]
        out: list[Node] = []
        node_id = branch.head_node_id
        while node_id is not None:  # walk up the parent spine
            node = self.nodes[node_id]
            out.append(node)
            node_id = node.parent_id  # crosses into the parent branch transparently
        out.reverse()
        return out

    async def create_branch(
        self, *, conversation_id: str, from_node_id: str, name: str, intent: str = ""
    ) -> Branch:
        from_node = self.nodes[from_node_id]
        branch_id = _uuid()
        branch = Branch(
            id=branch_id,
            conversation_id=conversation_id,
            name=name,
            parent_branch_id=from_node.branch_id,
            fork_node_id=from_node_id,
            head_node_id=from_node_id,  # tip starts at the fork point
            intent=intent,
        )
        self.branches[branch_id] = branch
        # Continue numbering after the fork point so seq stays monotonic on the
        # logical history; uniqueness is per-branch regardless.
        self._next_seq[branch_id] = from_node.seq + 1
        return branch

    async def add_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        links = self.references.setdefault(conversation_id, [])
        if referenced_conversation_id not in links:
            links.append(referenced_conversation_id)

    async def remove_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        links = self.references.get(conversation_id)
        if links and referenced_conversation_id in links:
            links.remove(referenced_conversation_id)

    async def list_reference_ids(self, conversation_id: str) -> list[str]:
        return list(self.references.get(conversation_id, []))

    async def delete_last_turn(self, *, branch_id: str, user_id: str) -> list[str]:
        branch = self.branches.get(branch_id)
        if branch is None or branch.head_node_id is None:
            raise KeyError(branch_id)
        head = self.nodes[branch.head_node_id]
        if head.role == "assistant":
            user_node = self.nodes.get(head.parent_id) if head.parent_id else None
            if user_node is None or user_node.role != "user":
                raise ValueError("trailing pair is not a user/assistant turn")
            reply = head
        else:
            reply, user_node = None, head
        if user_node.role != "user" or user_node.author_id != user_id:
            raise PermissionError("only the author may remove their message")
        to_remove = [n for n in (reply, user_node) if n is not None]
        for n in to_remove:
            if any(b.fork_node_id == n.id for b in self.branches.values()):
                raise ValueError("a branch has forked from this message")
        branch.head_node_id = user_node.parent_id
        for n in to_remove:
            del self.nodes[n.id]
        return [n.id for n in to_remove]

    async def rename_conversation(
        self, conversation_id: str, title: str
    ) -> Conversation | None:
        conv = self.conversations.get(conversation_id)
        if conv is not None:
            conv.title = title
        return conv

    async def delete_conversation(self, conversation_id: str) -> list[str]:
        if conversation_id not in self.conversations:
            raise KeyError(conversation_id)
        branch_ids = {b.id for b in self.branches.values() if b.conversation_id == conversation_id}
        node_ids = [n.id for n in self.nodes.values() if n.branch_id in branch_ids]
        for nid in node_ids:
            del self.nodes[nid]
        for bid in branch_ids:
            self.branches.pop(bid, None)
            self._next_seq.pop(bid, None)
        self.references.pop(conversation_id, None)
        for links in self.references.values():
            if conversation_id in links:
                links.remove(conversation_id)
        del self.conversations[conversation_id]
        return node_ids

    async def rename_branch(self, branch_id: str, name: str) -> Branch | None:
        branch = self.branches.get(branch_id)
        if branch is not None:
            branch.name = name
        return branch

    async def set_conclusion(
        self, *, conversation_id: str, conclusion: str, concluded_by: str
    ) -> Conversation | None:
        conv = self.conversations.get(conversation_id)
        if conv is None:
            return None
        conv.conclusion = conclusion
        conv.concluded_by = concluded_by if conclusion else None
        conv.concluded_at = datetime.now(timezone.utc) if conclusion else None
        return conv

    async def resolve_branch(
        self, *, branch_id: str, status: str, resolution: str, resolved_by: str
    ) -> Branch | None:
        branch = self.branches.get(branch_id)
        if branch is None:
            return None
        branch.status = status
        if status == "open":
            # Reopening clears the verdict rather than leaving a stale reason
            # attached to a branch that is live again.
            branch.resolution = ""
            branch.resolved_by = None
            branch.resolved_at = None
        else:
            branch.resolution = resolution
            branch.resolved_by = resolved_by
            branch.resolved_at = datetime.now(timezone.utc)
        return branch

    async def toggle_branch_vote(self, *, branch_id: str, user_id: str) -> bool:
        branch = self.branches.get(branch_id)
        if branch is None:
            raise KeyError(branch_id)
        if user_id in branch.votes:
            branch.votes.remove(user_id)
            return False
        branch.votes.append(user_id)
        return True

    async def delete_branch(self, branch_id: str) -> list[str]:
        branch = self.branches.get(branch_id)
        if branch is None:
            raise KeyError(branch_id)
        conv = self.conversations.get(branch.conversation_id)
        if conv is not None and conv.default_branch_id == branch_id:
            raise ValueError("the main branch can't be deleted — delete the conversation")
        if any(b.parent_branch_id == branch_id for b in self.branches.values()):
            raise ValueError("a branch has forked from this one")
        node_ids = [n.id for n in self.nodes.values() if n.branch_id == branch_id]
        for nid in node_ids:
            del self.nodes[nid]
        del self.branches[branch_id]
        self._next_seq.pop(branch_id, None)
        return node_ids


class DbStore:
    """Durable `ConversationStore` on SQLAlchemy (SQLite dev / Postgres prod).

    Same contract and same fork semantics as `InMemoryStore` — it is the store
    swapped in for production with no change to engine code, and it passes the
    identical store test suite. A fresh session per operation keeps the engine's
    streaming loop from holding a long-lived transaction open.

    The per-branch `seq` needs no counter: it is `head.seq + 1` (or `0` for an
    empty branch), which also gives a fork its `fork_node.seq + 1` start for free,
    since a fresh fork's head *is* the fork node.
    """

    def __init__(self, session_factory, on_node=None) -> None:
        self._sf = session_factory
        # Post-persist hook (e.g. fire-and-forget node embedding). It must be
        # non-blocking and never raise — nodes are the product, anything hooked
        # onto their persistence is an overlay.
        self._on_node = on_node

    @staticmethod
    def _to_node(row) -> Node:
        return Node(
            id=row.id,
            branch_id=row.branch_id,
            parent_id=row.parent_id,
            seq=row.seq,
            role=row.role,  # type: ignore[arg-type]
            content=row.content,
            author_id=row.author_id,
            token_count=row.token_count,
        )

    @staticmethod
    def _to_branch(row) -> Branch:
        return Branch(
            id=row.id,
            conversation_id=row.conversation_id,
            name=row.name,
            parent_branch_id=row.parent_branch_id,
            fork_node_id=row.fork_node_id,
            head_node_id=row.head_node_id,
            intent=row.intent or "",
            status=row.status or "open",
            resolution=row.resolution or "",
            resolved_by=row.resolved_by,
            resolved_at=row.resolved_at,
        )

    @staticmethod
    def _to_conversation(row) -> Conversation:
        return Conversation(
            id=row.id,
            workspace_id=row.workspace_id,
            author_id=row.author_id,
            title=row.title,
            visibility=row.visibility,
            default_branch_id=row.default_branch_id,
            conclusion=row.conclusion or "",
            concluded_by=row.concluded_by,
            concluded_at=row.concluded_at,
        )

    async def create_conversation(
        self, *, workspace_id: str, author_id: str, title: str, visibility: str
    ) -> Conversation:
        from .models import BranchRow, ConversationRow

        async with self._sf() as s:
            conv_id, branch_id = _uuid(), _uuid()
            # The conversation is inserted before the branch that references
            # it, and the `flush` is what makes that true — not the order of
            # the `add` calls.
            #
            # `branches.conversation_id` is a real foreign key, but no
            # `relationship()` joins the two mappers, and the ORM derives flush
            # ordering from relationships rather than from table constraints.
            # With no dependency to honour it falls back to sorting mappers by
            # name, and `BranchRow` sorts before `ConversationRow` — so the
            # child was always written first, whatever this method did.
            #
            # SQLite never objected, because it does not enforce foreign keys
            # unless a connection asks it to. Postgres does, so every attempt
            # to start a conversation died on `branches_conversation_id_fkey`.
            row = ConversationRow(
                id=conv_id,
                workspace_id=workspace_id,
                author_id=author_id,
                title=title,
                visibility=visibility,
                default_branch_id=branch_id,
            )
            s.add(row)
            await s.flush()
            s.add(
                BranchRow(
                    id=branch_id,
                    conversation_id=conv_id,
                    name="main",
                    parent_branch_id=None,
                    fork_node_id=None,
                    head_node_id=None,
                )
            )
            await s.commit()
            return self._to_conversation(row)

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        from .models import ConversationRow

        async with self._sf() as s:
            row = await s.get(ConversationRow, conversation_id)
            return self._to_conversation(row) if row else None

    async def list_conversations(
        self, workspace_id: str, viewer_id: str | None = None
    ) -> list[Conversation]:
        from sqlalchemy import or_, select

        from .models import ConversationRow

        async with self._sf() as s:
            stmt = select(ConversationRow).where(
                ConversationRow.workspace_id == workspace_id
            )
            if viewer_id is not None:
                stmt = stmt.where(
                    or_(
                        ConversationRow.visibility != "private",
                        ConversationRow.author_id == viewer_id,
                    )
                )
            rows = (
                await s.execute(stmt.order_by(ConversationRow.created_at))
            ).scalars().all()
            return [self._to_conversation(r) for r in rows]

    async def get_branch(self, branch_id: str) -> Branch | None:
        from .models import BranchRow

        async with self._sf() as s:
            row = await s.get(BranchRow, branch_id)
            if row is None:
                return None
            branch = self._to_branch(row)
            await self._attach_votes(s, [branch])
            return branch

    async def list_branches(self, conversation_id: str) -> list[Branch]:
        from sqlalchemy import select

        from .models import BranchRow

        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(BranchRow)
                    .where(BranchRow.conversation_id == conversation_id)
                    .order_by(BranchRow.created_at)
                )
            ).scalars().all()
            branches = [self._to_branch(r) for r in rows]
            await self._attach_votes(s, branches)
            return branches

    @staticmethod
    async def _attach_votes(s, branches: list[Branch]) -> None:
        """Hydrate who is backing each branch, in one query for the whole tree."""
        from sqlalchemy import select

        from .models import BranchVoteRow

        ids = [b.id for b in branches]
        if not ids:
            return
        rows = (
            await s.execute(
                select(BranchVoteRow)
                .where(BranchVoteRow.branch_id.in_(ids))
                .order_by(BranchVoteRow.created_at)
            )
        ).scalars().all()
        if not rows:
            return
        by_branch: dict[str, list[str]] = {}
        for r in rows:
            by_branch.setdefault(r.branch_id, []).append(r.user_id)
        for branch in branches:
            branch.votes = by_branch.get(branch.id, [])

    async def toggle_branch_vote(self, *, branch_id: str, user_id: str) -> bool:
        from sqlalchemy import delete, select

        from .models import BranchVoteRow

        async with self._sf() as s:
            existing = (
                await s.execute(
                    select(BranchVoteRow).where(
                        BranchVoteRow.branch_id == branch_id,
                        BranchVoteRow.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                await s.execute(
                    delete(BranchVoteRow).where(BranchVoteRow.id == existing.id)
                )
                await s.commit()
                return False
            s.add(BranchVoteRow(branch_id=branch_id, user_id=user_id))
            await s.commit()
            return True

    async def add_node(
        self,
        *,
        branch_id: str,
        role: str,
        content: str,
        author_id: str | None,
        token_count: int = 0,
        citations: list[dict] | None = None,
    ) -> Node:
        from .models import BranchRow, NodeCitationRow, NodeRow

        cites = _clean_citations(citations)
        async with self._sf() as s:
            branch = await s.get(BranchRow, branch_id)
            if branch is None:
                raise KeyError(branch_id)
            if branch.head_node_id is not None:
                head = await s.get(NodeRow, branch.head_node_id)
                seq = head.seq + 1
            else:
                seq = 0
            row = NodeRow(
                id=_uuid(),
                branch_id=branch_id,
                parent_id=branch.head_node_id,
                seq=seq,
                role=role,
                content=content,
                author_id=author_id,
                token_count=token_count,
            )
            s.add(row)
            # Same transaction as the content: a reply that survives without
            # its sources is exactly the failure this table exists to end.
            for ordinal, cite in enumerate(cites):
                s.add(
                    NodeCitationRow(
                        node_id=row.id,
                        document_id=cite["document_id"],
                        filename=cite["filename"],
                        cite_as=cite["cite_as"],
                        chunk_index=cite["chunk_index"],
                        score=cite["score"],
                        excerpt=cite["excerpt"],
                        ordinal=ordinal,
                    )
                )
            branch.head_node_id = row.id
            await s.commit()
            node = self._to_node(row)
            node.citations = cites
            if self._on_node is not None:
                self._on_node(node)
            return node

    async def get_history(self, branch_id: str) -> list[Node]:
        """The branch's turns, oldest first, inherited across every fork above it.

        Still a walk up the `parent_id` spine — that walk *is* the inheritance
        feature, and it crosses branch boundaries for free. What changed is how
        the rows are fetched. One `session.get` per node meant a 500-turn branch
        issued 500 queries: invisible on SQLite's page cache, 500 network round
        trips on Postgres, on the hot path of every single send.

        So the spine is read a branch at a time instead. `create_branch` sets
        `parent_branch_id` to the branch owning the node it forked from, so when
        the walk runs off the end of one branch's rows, the node it is reaching
        for is in the parent branch — fetch that branch's rows and carry on.
        Queries now scale with the number of forks above this branch (typically
        one to three), not with the number of turns.

        The per-node fallback is kept for the case the invariant doesn't hold:
        an older row written before `parent_branch_id` was populated, or a
        repaired database. Slow, but it still returns the right history rather
        than a truncated one, and a silently short history is the worst
        possible failure here — it would quietly change what the model sees.
        """
        from sqlalchemy import select

        from .models import BranchRow, NodeRow

        async with self._sf() as s:
            branch = await s.get(BranchRow, branch_id)
            if branch is None:
                raise KeyError(branch_id)

            out: list[Node] = []
            node_id = branch.head_node_id
            seen_branches: set[str] = set()

            while node_id is not None and branch is not None:
                if branch.id in seen_branches:
                    break  # cycle in parent_branch_id; fall through to the walk
                seen_branches.add(branch.id)

                rows = (
                    await s.execute(
                        select(NodeRow).where(NodeRow.branch_id == branch.id)
                    )
                ).scalars().all()
                by_id = {r.id: r for r in rows}

                while node_id is not None and node_id in by_id:
                    row = by_id[node_id]
                    out.append(self._to_node(row))
                    node_id = row.parent_id

                if node_id is None:
                    break
                branch = (
                    await s.get(BranchRow, branch.parent_branch_id)
                    if branch.parent_branch_id
                    else None
                )

            # Whatever the segment walk could not account for, one node at a time.
            while node_id is not None:
                row = await s.get(NodeRow, node_id)
                if row is None:
                    break
                out.append(self._to_node(row))
                node_id = row.parent_id

            out.reverse()
            await self._attach_citations(s, out)
            return out

    @staticmethod
    async def _attach_citations(s, nodes: list[Node]) -> None:
        """Hydrate every node's sources in one query.

        One query for the whole history, not one per node: the walk above was
        already rewritten to stop issuing a query per turn, and re-introducing
        that pattern for citations would undo it. Assistant nodes only — a user
        message has no sources by definition, and on a long thread that halves
        the id list.
        """
        from sqlalchemy import select

        from .models import NodeCitationRow

        ids = [n.id for n in nodes if n.role == "assistant"]
        if not ids:
            return
        rows = (
            await s.execute(
                select(NodeCitationRow)
                .where(NodeCitationRow.node_id.in_(ids))
                .order_by(NodeCitationRow.node_id, NodeCitationRow.ordinal)
            )
        ).scalars().all()
        if not rows:
            return
        by_node: dict[str, list[dict]] = {}
        for r in rows:
            by_node.setdefault(r.node_id, []).append(
                {
                    "document_id": r.document_id,
                    "filename": r.filename,
                    "cite_as": r.cite_as or r.filename,
                    "chunk_index": r.chunk_index,
                    "score": r.score,
                    "excerpt": r.excerpt,
                }
            )
        for node in nodes:
            if node.id in by_node:
                node.citations = by_node[node.id]

    async def create_branch(
        self, *, conversation_id: str, from_node_id: str, name: str, intent: str = ""
    ) -> Branch:
        from .models import BranchRow, NodeRow

        async with self._sf() as s:
            from_node = await s.get(NodeRow, from_node_id)
            if from_node is None:
                raise KeyError(from_node_id)
            row = BranchRow(
                id=_uuid(),
                conversation_id=conversation_id,
                name=name,
                parent_branch_id=from_node.branch_id,
                fork_node_id=from_node_id,
                head_node_id=from_node_id,  # tip starts at the fork point
                intent=intent,
            )
            s.add(row)
            await s.commit()
            return self._to_branch(row)

    async def add_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        from sqlalchemy import select

        from .models import ConversationReferenceRow

        async with self._sf() as s:
            existing = (
                await s.execute(
                    select(ConversationReferenceRow).where(
                        ConversationReferenceRow.conversation_id == conversation_id,
                        ConversationReferenceRow.referenced_conversation_id
                        == referenced_conversation_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                s.add(
                    ConversationReferenceRow(
                        id=_uuid(),
                        conversation_id=conversation_id,
                        referenced_conversation_id=referenced_conversation_id,
                    )
                )
                await s.commit()

    async def remove_reference(
        self, *, conversation_id: str, referenced_conversation_id: str
    ) -> None:
        from sqlalchemy import delete

        from .models import ConversationReferenceRow

        async with self._sf() as s:
            await s.execute(
                delete(ConversationReferenceRow).where(
                    ConversationReferenceRow.conversation_id == conversation_id,
                    ConversationReferenceRow.referenced_conversation_id
                    == referenced_conversation_id,
                )
            )
            await s.commit()

    async def list_reference_ids(self, conversation_id: str) -> list[str]:
        from sqlalchemy import select

        from .models import ConversationReferenceRow

        async with self._sf() as s:
            rows = (
                await s.execute(
                    select(ConversationReferenceRow)
                    .where(ConversationReferenceRow.conversation_id == conversation_id)
                    .order_by(ConversationReferenceRow.created_at)
                )
            ).scalars().all()
            return [r.referenced_conversation_id for r in rows]

    async def delete_last_turn(self, *, branch_id: str, user_id: str) -> list[str]:
        from sqlalchemy import select

        from .models import BranchRow, NodeRow

        async with self._sf() as s:
            branch = await s.get(BranchRow, branch_id)
            if branch is None or branch.head_node_id is None:
                raise KeyError(branch_id)
            head = await s.get(NodeRow, branch.head_node_id)
            if head.role == "assistant":
                user_row = await s.get(NodeRow, head.parent_id) if head.parent_id else None
                if user_row is None or user_row.role != "user":
                    raise ValueError("trailing pair is not a user/assistant turn")
                reply, user_node = head, user_row
            else:
                reply, user_node = None, head
            if user_node.role != "user" or user_node.author_id != user_id:
                raise PermissionError("only the author may remove their message")
            to_remove = [n for n in (reply, user_node) if n is not None]
            for n in to_remove:
                forked = await s.scalar(
                    select(BranchRow.id).where(BranchRow.fork_node_id == n.id)
                )
                if forked is not None:
                    raise ValueError("a branch has forked from this message")
            branch.head_node_id = user_node.parent_id
            ids = [n.id for n in to_remove]
            for n in to_remove:
                await s.delete(n)
            await s.commit()
            return ids

    async def rename_conversation(
        self, conversation_id: str, title: str
    ) -> Conversation | None:
        from .models import ConversationRow

        async with self._sf() as s:
            row = await s.get(ConversationRow, conversation_id)
            if row is None:
                return None
            row.title = title
            await s.commit()
            return self._to_conversation(row)

    async def delete_conversation(self, conversation_id: str) -> list[str]:
        from sqlalchemy import delete, or_, select

        from .models import BranchRow, ConversationReferenceRow, ConversationRow, NodeRow

        async with self._sf() as s:
            conv = await s.get(ConversationRow, conversation_id)
            if conv is None:
                raise KeyError(conversation_id)
            branch_ids = select(BranchRow.id).where(
                BranchRow.conversation_id == conversation_id
            )
            node_ids = list(
                (
                    await s.execute(
                        select(NodeRow.id).where(NodeRow.branch_id.in_(branch_ids))
                    )
                ).scalars()
            )
            await s.execute(delete(NodeRow).where(NodeRow.id.in_(node_ids)))
            await s.execute(delete(BranchRow).where(BranchRow.conversation_id == conversation_id))
            await s.execute(
                delete(ConversationReferenceRow).where(
                    or_(
                        ConversationReferenceRow.conversation_id == conversation_id,
                        ConversationReferenceRow.referenced_conversation_id == conversation_id,
                    )
                )
            )
            await s.delete(conv)
            await s.commit()
            return node_ids

    async def rename_branch(self, branch_id: str, name: str) -> Branch | None:
        from .models import BranchRow

        async with self._sf() as s:
            row = await s.get(BranchRow, branch_id)
            if row is None:
                return None
            row.name = name
            await s.commit()
            return self._to_branch(row)

    async def set_conclusion(
        self, *, conversation_id: str, conclusion: str, concluded_by: str
    ) -> Conversation | None:
        from .models import ConversationRow

        async with self._sf() as s:
            row = await s.get(ConversationRow, conversation_id)
            if row is None:
                return None
            row.conclusion = conclusion
            row.concluded_by = concluded_by if conclusion else None
            row.concluded_at = datetime.now(timezone.utc) if conclusion else None
            await s.commit()
            return self._to_conversation(row)

    async def resolve_branch(
        self, *, branch_id: str, status: str, resolution: str, resolved_by: str
    ) -> Branch | None:
        from .models import BranchRow

        async with self._sf() as s:
            row = await s.get(BranchRow, branch_id)
            if row is None:
                return None
            row.status = status
            if status == "open":
                row.resolution = ""
                row.resolved_by = None
                row.resolved_at = None
            else:
                row.resolution = resolution
                row.resolved_by = resolved_by
                row.resolved_at = datetime.now(timezone.utc)
            await s.commit()
            return self._to_branch(row)

    async def delete_branch(self, branch_id: str) -> list[str]:
        from sqlalchemy import delete, select

        from .models import BranchRow, ConversationRow, NodeRow

        async with self._sf() as s:
            branch = await s.get(BranchRow, branch_id)
            if branch is None:
                raise KeyError(branch_id)
            conv = await s.get(ConversationRow, branch.conversation_id)
            if conv is not None and conv.default_branch_id == branch_id:
                raise ValueError("the main branch can't be deleted — delete the conversation")
            child = await s.scalar(
                select(BranchRow.id).where(BranchRow.parent_branch_id == branch_id)
            )
            if child is not None:
                raise ValueError("a branch has forked from this one")
            node_ids = list(
                (
                    await s.execute(
                        select(NodeRow.id).where(NodeRow.branch_id == branch_id)
                    )
                ).scalars()
            )
            await s.execute(delete(NodeRow).where(NodeRow.branch_id == branch_id))
            await s.delete(branch)
            await s.commit()
            return node_ids
