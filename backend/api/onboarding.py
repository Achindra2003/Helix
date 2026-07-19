"""The example workspace every new account starts with (P4).

An empty account is the worst version of this product. Everything Helix is
actually *for* — branching a thread, watching a deep run, following a reference
edge, grounding an answer in a file — needs history to exist before it can be
seen, and a first-time visitor has none. Worse, the interesting features are the
ones that need a provider key, so a keyless visitor sees an empty screen and
concludes the app does nothing.

So: seed one workspace with a thread that has already been forked, a second
conversation referenced from it, a finished Deep Reasoning trace, and an
ingested document. All of it is static content written here, not generated — it
costs no tokens and needs no key, which is the point. The Map, the run replay,
grounding and resurfacing all have something real to render on first load.

Two rules this module holds to:

1. **Registration must never fail because seeding failed.** A user who cannot
   sign up because of demo content is a catastrophic trade for a nicety. Every
   error here is swallowed and logged, and the account survives.
2. **Nothing here reaches into the engine.** Content is written through the
   `ConversationStore` Protocol and the documents service's public `ingest`,
   which is the boundary the batons designate. The one exception is `deep_runs`,
   which has no store interface — a row is written directly, in the same shape
   `run_log.py` writes one, and that shape is asserted in the tests so a change
   to the real writer breaks here loudly rather than silently.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .conversation.models import DeepRunRow
from .models import Membership, Workspace

log = logging.getLogger(__name__)

WORKSPACE_NAME = "Example workspace"

# The seeded thread. Deliberately about a decision with more than one defensible
# answer — a fork only makes sense when the alternative is genuinely arguable.
_MAIN_THREAD = [
    ("user", "We need to pick a database for the new service. Postgres or SQLite?"),
    (
        "assistant",
        "It depends on what you are optimising for.\n\n"
        "**SQLite** is a file. No server, no connection pool, no ops. It handles "
        "far more load than people expect — the usual limit is concurrent "
        "*writers*, not volume.\n\n"
        "**Postgres** buys you concurrent writes, real types, extensions, and "
        "managed hosting with backups someone else runs.\n\n"
        "If this service is deployed by other people, SQLite makes their install "
        "one step. If you run it yourself and expect concurrent writers, "
        "Postgres.",
    ),
    ("user", "It'll be self-hosted by other teams, so installs need to be easy."),
    (
        "assistant",
        "Then SQLite is the better default, and the interesting question becomes "
        "how you avoid painting yourself into a corner.\n\n"
        "Keep every query behind an interface and avoid SQLite-only syntax. Then "
        "'move to Postgres' is a connection-string change for the teams that "
        "outgrow the default, rather than a rewrite.",
    ),
]

# The fork. Branched from the assistant's *first* answer, before the thread
# settled on SQLite — so the Map shows two live directions from one node, which
# is the entire "Git for your team's AI work" claim in one screen.
_FORK_NAME = "What if we assume Postgres?"
_FORK_THREAD = [
    ("user", "Assume we go with Postgres from day one. What does that cost us?"),
    (
        "assistant",
        "Mostly setup friction, paid by everyone who installs it.\n\n"
        "A new contributor now needs a running Postgres before the test suite "
        "passes. CI needs a service container. Self-hosters need a second "
        "container and a password.\n\n"
        "In exchange you get concurrent writes, real JSON and array types, and "
        "the option of a managed host with backups. If you expect teams rather "
        "than individuals, that trade is often worth it — just make sure it is "
        "chosen, not inherited.",
    ),
]

# The referenced conversation: separate thread, linked in as live background
# context. This is what puts an edge on the Map.
_REFERENCE_TITLE = "Deployment constraints"
_REFERENCE_THREAD = [
    ("user", "What are our constraints on where this runs?"),
    (
        "assistant",
        "Three that matter:\n\n"
        "1. **Install must be one command.** Anything else loses self-hosters.\n"
        "2. **It has to run on a small box** — assume 512 MB of RAM, not 8 GB.\n"
        "3. **No paid dependency at rest.** A free tier that expires is a "
        "deadline, not a plan.",
    ),
]

_DOCUMENT_NAME = "team-decisions.md"
_DOCUMENT_BODY = """# Team decisions

## Database
SQLite is the default. It keeps installs to a single command, which matters
more than write concurrency for our users. Postgres stays supported for teams
that outgrow it — every query goes through an interface so the swap is a
connection string, not a rewrite.

## Hosting
Must run in 512 MB of RAM. This rules out anything that loads a large model
into memory by default.

## Secrets
Every deployment generates its own signing secret on first boot. Shipping a
known default is the same as shipping no secret at all.
"""

# A finished Deep Reasoning run. Written in the shape run_log.py persists — see
# the module docstring on why that shape is pinned by tests. The numbers tell a
# real story: stability climbs as the answer stops changing, and the run halts
# because it converged rather than because it ran out of budget.
_DEEP_QUESTION = "Should we support both SQLite and Postgres, or pick one?"
_DEEP_ANSWER = (
    "Support both, but make SQLite the default and Postgres the documented "
    "upgrade.\n\n"
    "The two audiences want opposite things: someone evaluating the project "
    "wants it running in one command, and a team running it in production wants "
    "concurrent writes and managed backups. Picking one abandons an audience.\n\n"
    "The cost of supporting both is a query layer with no dialect-specific SQL "
    "and a test suite that runs against both — real work, but bounded, and it "
    "is work that also keeps the schema honest."
)
_DEEP_TRACE = {
    "steps": [
        {
            "idx": 0,
            "node": "decompose",
            "depth": 1,
            "stability": 0.31,
            "confidence": 0.40,
            "thought": (
                "The question assumes a single choice is required. Worth testing "
                "that assumption: the two options serve different audiences."
            ),
        },
        {
            "idx": 1,
            "node": "critique",
            "depth": 2,
            "stability": 0.58,
            "confidence": 0.55,
            "challenge": (
                "Supporting both doubles the test matrix and invites subtle "
                "dialect bugs. Is the second audience real, or hypothetical?"
            ),
        },
        {
            "idx": 2,
            "node": "synthesize",
            "depth": 2,
            "stability": 0.79,
            "confidence": 0.71,
            "synthesis": (
                "Both audiences are real: evaluators install, teams deploy. The "
                "cost is bounded if no dialect-specific SQL is written."
            ),
        },
        {
            "idx": 3,
            "node": "converge",
            "depth": 3,
            "stability": 0.94,
            "confidence": 0.86,
            "surfaced_insight": (
                "Default and support are different decisions. Defaulting to "
                "SQLite serves the evaluator without abandoning the team."
            ),
            "stop_reason": "stability_threshold_reached",
        },
    ],
    "stability_history": [0.31, 0.58, 0.79, 0.94],
    "steers": [],
}


async def seed_example_workspace(session: AsyncSession, user_id: str) -> str | None:
    """Give `user_id` a populated workspace. Returns its id, or None.

    Never raises: a failure here must not cost the user their account. The
    caller has already committed the user row.
    """
    if not settings.seed_example_workspace:
        return None
    try:
        return await _seed(session, user_id)
    except Exception:  # pragma: no cover - defensive; see module docstring
        log.exception("Failed to seed the example workspace for user %s", user_id)
        return None


async def _seed(session: AsyncSession, user_id: str) -> str:
    # Imported here rather than at module scope: this pulls in the conversation
    # package, and importing it from api.models' neighbourhood at startup makes
    # a circular import out of what is otherwise a leaf module.
    from .conversation.router import _store

    workspace = Workspace(name=WORKSPACE_NAME, owner_id=user_id)
    session.add(workspace)
    await session.flush()
    session.add(
        Membership(user_id=user_id, workspace_id=workspace.id, role="owner")
    )
    await session.commit()

    # --- the referenced thread, first: the main thread links to it ------------
    reference = await _store.create_conversation(
        workspace_id=workspace.id,
        author_id=user_id,
        title=_REFERENCE_TITLE,
        visibility="shared",
    )
    await _add_turns(reference.default_branch_id, _REFERENCE_THREAD, user_id)

    # --- the main thread ------------------------------------------------------
    conversation = await _store.create_conversation(
        workspace_id=workspace.id,
        author_id=user_id,
        title="Choosing a database",
        visibility="shared",
    )
    nodes = await _add_turns(
        conversation.default_branch_id, _MAIN_THREAD, user_id
    )

    # Fork from the first assistant answer — before the thread committed to
    # SQLite, so the branch is a genuine alternative rather than a continuation.
    branch = await _store.create_branch(
        conversation_id=conversation.id,
        from_node_id=nodes[1].id,
        name=_FORK_NAME,
    )
    await _add_turns(branch.id, _FORK_THREAD, user_id)

    await _store.add_reference(
        conversation_id=conversation.id,
        referenced_conversation_id=reference.id,
    )

    # --- a finished deep run, attached to the main thread ---------------------
    session.add(
        DeepRunRow(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            branch_id=conversation.default_branch_id,
            author_id=user_id,
            question=_DEEP_QUESTION,
            answer=_DEEP_ANSWER,
            status="done",
            stop_reason="stability_threshold_reached",
            depth=3,
            stability=0.94,
            confidence=0.86,
            tokens_used=4820,
            duration_ms=31_400,
            trace=json.dumps(_DEEP_TRACE, ensure_ascii=False),
            model="seeded-example",
            provenance=json.dumps({"seeded": True}),
        )
    )
    await session.commit()

    await _seed_document(session, workspace.id, user_id)
    return workspace.id


async def _add_turns(branch_id: str, turns, author_id: str):
    """Append (role, content) pairs, attributing only the user's own turns."""
    from .conversation.router import _store

    return [
        await _store.add_node(
            branch_id=branch_id,
            role=role,
            content=content,
            author_id=author_id if role == "user" else None,
        )
        for role, content in turns
    ]


async def _seed_document(session: AsyncSession, workspace_id: str, user_id: str) -> None:
    """Ingest the example document so file grounding has something to retrieve.

    Ingestion embeds, which is the slowest thing in this module. It is still
    done inline: a document that appears seconds after the workspace does looks
    broken, and the text is a few hundred words — the cost is small next to the
    password hash registration already pays.
    """
    from .documents.models import DocumentRow
    from .documents.router import _index

    data = _DOCUMENT_BODY.encode("utf-8")
    doc = DocumentRow(
        workspace_id=workspace_id,
        author_id=user_id,
        filename=_DOCUMENT_NAME,
        mime="text/markdown",
        size_bytes=len(data),
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    await _index.ingest(doc.id, doc.filename, data)
