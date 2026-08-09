"""Deleting a thread that has children — the half foreign keys were hiding.

`nodes`, `branches` and `conversations` all have real foreign keys pointing at
them, and the delete paths remove rows in the right order for the ones anybody
tested: nodes before branches, branches before the conversation.

What nothing checked is the tables that hang *off* that spine and are not part
of the walk — `node_citations` on a node, `branch_votes` on a branch. Deleting
the parent leaves them pointing at nothing. SQLite accepted that silently for
as long as it was not asked to enforce foreign keys (it is now, see
`api/db.py`); Postgres would have refused the delete outright, which is a 500
on "delete this thread" for any thread containing a grounded answer or a
backed exploration — the two features most likely to be present in a thread
worth deleting.

These go through the HTTP API rather than the store, because the ordering bug
they guard is in the store and a test that called it directly would be writing
down the same assumption twice.
"""
import pytest
from starlette.testclient import TestClient

from api.conversation.models import BranchVoteRow, DeepRunRow, NodeCitationRow
from api.db import SessionLocal
from api.main import app

from .test_router import _create_conv


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


async def _cite(node_id: str, workspace_id: str) -> None:
    """One grounded citation on a node, written the way `add_node` writes it."""
    async with SessionLocal() as s:
        s.add(
            NodeCitationRow(
                node_id=node_id,
                workspace_id=workspace_id,
                document_id="doc-1",
                filename="grounding.txt",
                cite_as="Lewis et al. (2020)",
                chunk_index=0,
                score=0.9,
                excerpt="retrieved passages",
                ordinal=0,
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_a_thread_with_a_grounded_answer_can_be_deleted(client, make_workspace):
    headers, _uid, wid = make_workspace(client)
    created = _create_conv(client, headers, wid, title="grounded")
    cid, branch_id = created["conversation_id"], created["branch_id"]

    client.post(f"/conversations/{branch_id}/messages",
                json={"prompt": "what does the paper say?"}, headers=headers)
    nodes = client.get(f"/conversations/branches/{branch_id}/history",
                       headers=headers).json()["nodes"]
    assert nodes, "the turn should have produced nodes"
    await _cite(nodes[-1]["id"], wid)

    resp = client.delete(f"/conversations/{cid}", headers=headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_a_backed_exploration_can_be_abandoned(client, make_workspace):
    """Voting and deleting are both ordinary moves; a branch people liked is
    exactly the kind you fork, lose the argument on, and then clear away."""
    headers, _uid, wid = make_workspace(client)
    created = _create_conv(client, headers, wid, title="voted")
    branch_id = created["branch_id"]

    client.post(f"/conversations/{branch_id}/messages",
                json={"prompt": "seed"}, headers=headers)
    nodes = client.get(f"/conversations/branches/{branch_id}/history",
                       headers=headers).json()["nodes"]
    fork = client.post(
        f"/conversations/{created['conversation_id']}/fork",
        json={"from_node_id": nodes[0]["id"], "name": "alt", "intent": "another way"},
        headers=headers,
    )
    assert fork.status_code in (200, 201), fork.text
    fork_id = fork.json()["branch_id"]

    voted = client.post(f"/conversations/branches/{fork_id}/vote", headers=headers)
    assert voted.status_code == 200, voted.text

    resp = client.delete(f"/conversations/branches/{fork_id}", headers=headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_a_workspace_with_everything_in_it_can_be_deleted(client, make_workspace):
    """The owner's cascading delete, which walks the same spine and missed the
    same two tables — plus one of its own: it cleared `conversations` before
    `deep_runs`, and an archived run points at the conversation it ran on."""
    headers, uid, wid = make_workspace(client)
    created = _create_conv(client, headers, wid, title="everything")
    cid, branch_id = created["conversation_id"], created["branch_id"]

    client.post(f"/conversations/{branch_id}/messages",
                json={"prompt": "seed"}, headers=headers)
    nodes = client.get(f"/conversations/branches/{branch_id}/history",
                       headers=headers).json()["nodes"]
    await _cite(nodes[-1]["id"], wid)
    client.post(f"/conversations/branches/{branch_id}/vote", headers=headers)

    async with SessionLocal() as s:
        s.add(
            DeepRunRow(
                id="run-1", workspace_id=wid, conversation_id=cid,
                branch_id=branch_id, author_id=uid, question="q", status="done",
            )
        )
        await s.commit()

    resp = client.delete(f"/api/workspaces/{wid}", headers=headers)
    assert resp.status_code == 204, resp.text
