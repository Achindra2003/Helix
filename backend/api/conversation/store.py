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

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import uuid4

from .events import Node


def _uuid() -> str:
    return uuid4().hex


@dataclass
class Conversation:
    id: str
    workspace_id: str
    author_id: str
    title: str
    visibility: str  # "shared" | "private"
    default_branch_id: str


@dataclass
class Branch:
    id: str
    conversation_id: str
    name: str
    parent_branch_id: str | None
    fork_node_id: str | None
    head_node_id: str | None


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
    ) -> Node:
        """Append an immutable node to a branch, stamping a monotonic `seq` and
        chaining `parent_id` to the branch's current head; advances the head."""
        ...

    async def get_history(self, branch_id: str) -> list[Node]:
        """Nodes root -> head for a branch, walking `parent_id` across branch
        boundaries (the fork read path)."""
        ...

    async def create_branch(
        self, *, conversation_id: str, from_node_id: str, name: str
    ) -> Branch:
        """Fork: one new branch row pointing at `from_node_id`; no history copied."""
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
        self, *, conversation_id: str, from_node_id: str, name: str
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
        )

    async def create_conversation(
        self, *, workspace_id: str, author_id: str, title: str, visibility: str
    ) -> Conversation:
        from .models import BranchRow, ConversationRow

        async with self._sf() as s:
            conv_id, branch_id = _uuid(), _uuid()
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
            row = ConversationRow(
                id=conv_id,
                workspace_id=workspace_id,
                author_id=author_id,
                title=title,
                visibility=visibility,
                default_branch_id=branch_id,
            )
            s.add(row)
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
            return self._to_branch(row) if row else None

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
            return [self._to_branch(r) for r in rows]

    async def add_node(
        self,
        *,
        branch_id: str,
        role: str,
        content: str,
        author_id: str | None,
        token_count: int = 0,
    ) -> Node:
        from .models import BranchRow, NodeRow

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
            branch.head_node_id = row.id
            await s.commit()
            node = self._to_node(row)
            if self._on_node is not None:
                self._on_node(node)
            return node

    async def get_history(self, branch_id: str) -> list[Node]:
        from .models import BranchRow, NodeRow

        async with self._sf() as s:
            branch = await s.get(BranchRow, branch_id)
            if branch is None:
                raise KeyError(branch_id)
            out: list[Node] = []
            node_id = branch.head_node_id
            while node_id is not None:  # walk the parent spine across branches
                row = await s.get(NodeRow, node_id)
                out.append(self._to_node(row))
                node_id = row.parent_id
            out.reverse()
            return out

    async def create_branch(
        self, *, conversation_id: str, from_node_id: str, name: str
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
