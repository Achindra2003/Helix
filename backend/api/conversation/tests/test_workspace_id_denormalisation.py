"""`workspace_id` is copied down the branch/node subtree — and must stay true.

Six tables carry a workspace id they could derive by joining (see
`BranchRow.workspace_id` and the `c8e41f7b3a26` migration). It is there so a
Row-Level Security policy is a one-line indexable predicate rather than a
three-level subquery on the table that holds one row per message.

Redundant data is only safe while it cannot drift, and the cost of drift here
is unusually nasty: a row with the wrong workspace is a *tenancy* bug, and a
row with a stale one becomes invisible the moment policies are switched on.
NOT NULL catches a write site that forgets the column outright. This catches
the subtler half — a write site that supplies the wrong value, or a new one
that guesses.

Written against the real routes rather than the store, because the point is to
notice a *new* write path that nobody thought to update, and a test that called
the store directly would only ever check the paths it already knew about.
"""
import pytest
from starlette.testclient import TestClient

from api.db import SessionLocal
from api.main import app

from .test_router import _create_conv

# (table, parent table, the column joining them). The invariant is the same
# sentence six times: this row's workspace is its parent's workspace.
_CHAINS = [
    ("branches", "conversations", "conversation_id"),
    ("conversation_references", "conversations", "conversation_id"),
    ("nodes", "branches", "branch_id"),
    ("branch_votes", "branches", "branch_id"),
    ("node_citations", "nodes", "node_id"),
    ("node_embeddings", "nodes", "node_id"),
]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


async def _mismatches() -> dict[str, int]:
    """Rows whose workspace disagrees with their parent's, per table."""
    from sqlalchemy import text

    out: dict[str, int] = {}
    async with SessionLocal() as s:
        for table, parent, fk in _CHAINS:
            n = await s.scalar(
                text(
                    f"SELECT COUNT(*) FROM {table} c JOIN {parent} p "
                    f"ON p.id = c.{fk} WHERE c.workspace_id <> p.workspace_id"
                )
            )
            out[table] = int(n or 0)
    return out


async def _counts() -> dict[str, int]:
    from sqlalchemy import text

    out: dict[str, int] = {}
    async with SessionLocal() as s:
        for table, _parent, _fk in _CHAINS:
            out[table] = int(await s.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0)
    return out


@pytest.mark.asyncio
async def test_every_write_path_stamps_the_right_workspace(client, make_workspace):
    """One workspace, exercised through the routes that write each of the six
    tables, then checked in one sweep."""
    import api.conversation.router as router_mod

    headers, _uid, wid = make_workspace(client)
    first = _create_conv(client, headers, wid, title="the change")
    second = _create_conv(client, headers, wid, title="context")
    cid, branch_id = first["conversation_id"], first["branch_id"]

    # nodes
    client.post(f"/conversations/{branch_id}/messages",
                json={"prompt": "what do we do here?"}, headers=headers)
    nodes = client.get(f"/conversations/branches/{branch_id}/history",
                       headers=headers).json()["nodes"]
    assert nodes

    # branches (a fork), and branch_votes on it
    fork = client.post(
        f"/conversations/{cid}/fork",
        json={"from_node_id": nodes[0]["id"], "name": "alt", "intent": "another way"},
        headers=headers,
    ).json()
    client.post(f"/conversations/branches/{fork['branch_id']}/vote", headers=headers)

    # conversation_references
    ref = client.post(f"/conversations/{cid}/references",
                      json={"referenced_conversation_id": second["conversation_id"]},
                      headers=headers)
    assert ref.status_code == 201, ref.text

    # node_citations — written by add_node, which the grounded send path feeds
    await router_mod._store.add_node(
        branch_id=branch_id, role="assistant", content="grounded answer",
        author_id=None,
        citations=[{
            "document_id": "doc-1", "filename": "paper.txt",
            "cite_as": "Lewis et al. (2020)", "chunk_index": 0,
            "score": 0.9, "excerpt": "retrieved passages",
        }],
    )

    # node_embeddings — normally fire-and-forget, awaited here so the assertion
    # is about the value written rather than about scheduling.
    from api.conversation.events import Node as DomainNode

    await router_mod._embeddings.ensure([
        DomainNode(id=n["id"], branch_id=branch_id, parent_id=None, seq=i,
                   role=n["role"], content=n["content"])
        for i, n in enumerate(nodes)
    ])

    counts = await _counts()
    empty = [t for t, n in counts.items() if n == 0]
    assert not empty, f"nothing written to {empty} — the test proves less than it claims"

    assert await _mismatches() == {t: 0 for t, _p, _f in _CHAINS}


@pytest.mark.asyncio
async def test_a_fork_does_not_borrow_another_workspace(client, make_workspace,
                                                        make_user):
    """Two workspaces at once, so a write site that reached for "the current
    workspace" from the wrong place would show up as a mismatch rather than as
    a value that happens to be right because there is only one."""
    headers_a, _uid_a, wid_a = make_workspace(client)
    headers_b, _uid_b, wid_b = make_workspace(client)
    assert wid_a != wid_b

    for headers, wid in ((headers_a, wid_a), (headers_b, wid_b)):
        created = _create_conv(client, headers, wid)
        client.post(f"/conversations/{created['branch_id']}/messages",
                    json={"prompt": "hello"}, headers=headers)
        nodes = client.get(
            f"/conversations/branches/{created['branch_id']}/history",
            headers=headers,
        ).json()["nodes"]
        fork = client.post(
            f"/conversations/{created['conversation_id']}/fork",
            json={"from_node_id": nodes[0]["id"], "name": "alt", "intent": "x"},
            headers=headers,
        ).json()
        client.post(f"/conversations/branches/{fork['branch_id']}/vote",
                    headers=headers)

    assert await _mismatches() == {t: 0 for t, _p, _f in _CHAINS}
