"""Proof tests for the shared, branchable context (P1) — the headline claim.

These assert the property the product is built on: a forked branch's assembled
context is *exactly* the ancestor spine up to the fork point plus that branch's
own turns — and nothing from sibling branches or from messages added to the
parent *after* the fork. The fork tree here is ≥3 levels deep so the cross-branch
`parent_id` walk is exercised, not just a single hop.
"""
from api.conversation.context import ReferenceBlock, build_messages, render_seed
from api.conversation.store import InMemoryStore


async def _seed():
    store = InMemoryStore()
    conv = await store.create_conversation(
        workspace_id="w1", author_id="alice", title="t", visibility="shared"
    )
    return store, conv


def _contents(history):
    """The message bodies a model would actually see for this branch."""
    return [m["content"] for m in build_messages(history)]


def _has(contents, needle):
    return any(needle in c for c in contents)


async def test_fork_inherits_ancestor_spine_and_isolates_siblings():
    store, conv = await _seed()
    main = conv.default_branch_id

    # Level 1: an exchange on main, then the fork point, then more on main.
    await store.add_node(branch_id=main, role="user", content="q-main-1", author_id="alice")
    a1 = await store.add_node(branch_id=main, role="assistant", content="a-main-1", author_id=None)
    # Fork happens at a1; these land on main *after* the fork and must NOT leak in.
    await store.add_node(branch_id=main, role="user", content="q-main-2", author_id="bob")
    await store.add_node(branch_id=main, role="assistant", content="a-main-2", author_id=None)

    # Level 2: fork at a1.
    lvl2 = await store.create_branch(conversation_id=conv.id, from_node_id=a1.id, name="explore")
    await store.add_node(branch_id=lvl2.id, role="user", content="q-lvl2", author_id="carol")
    a_lvl2 = await store.add_node(branch_id=lvl2.id, role="assistant", content="a-lvl2", author_id=None)

    # Level 3: fork the fork.
    lvl3 = await store.create_branch(conversation_id=conv.id, from_node_id=a_lvl2.id, name="deep")
    await store.add_node(branch_id=lvl3.id, role="user", content="q-lvl3", author_id="dave")

    lvl3_ctx = _contents(await store.get_history(lvl3.id))

    # Inherits the full ancestor spine across two fork boundaries...
    assert _has(lvl3_ctx, "q-main-1")
    assert _has(lvl3_ctx, "a-main-1")
    assert _has(lvl3_ctx, "q-lvl2")
    assert _has(lvl3_ctx, "a-lvl2")
    assert _has(lvl3_ctx, "q-lvl3")
    # ...and inherits NOTHING the parent added after the fork point.
    assert not _has(lvl3_ctx, "q-main-2")
    assert not _has(lvl3_ctx, "a-main-2")


async def test_parent_branch_never_sees_child_branch_nodes():
    store, conv = await _seed()
    main = conv.default_branch_id

    await store.add_node(branch_id=main, role="user", content="q-main-1", author_id="alice")
    a1 = await store.add_node(branch_id=main, role="assistant", content="a-main-1", author_id=None)

    fork = await store.create_branch(conversation_id=conv.id, from_node_id=a1.id, name="side")
    await store.add_node(branch_id=fork.id, role="user", content="q-fork-only", author_id="carol")

    main_ctx = _contents(await store.get_history(main))
    assert _has(main_ctx, "q-main-1")
    assert not _has(main_ctx, "q-fork-only")  # isolation holds both directions


async def test_build_messages_uses_real_roles_and_tags_authors():
    store, conv = await _seed()
    b = conv.default_branch_id
    await store.add_node(branch_id=b, role="user", content="hello", author_id="alice")
    await store.add_node(branch_id=b, role="assistant", content="hi", author_id=None)

    messages = build_messages(await store.get_history(b))
    assert [m["role"] for m in messages] == ["system", "user", "assistant"]
    # The user turn is author-tagged so teammates are distinguishable in a shared
    # thread; the assistant turn is not.
    assert messages[1]["content"] == "[alice] hello"
    assert messages[2]["content"] == "hi"


async def test_window_keeps_system_frame_and_most_recent_turns():
    store, conv = await _seed()
    b = conv.default_branch_id
    for i in range(10):
        await store.add_node(branch_id=b, role="user", content=f"turn-{i}", author_id="alice")

    messages = build_messages(await store.get_history(b), max_turns=3)
    assert messages[0]["role"] == "system"
    # The dropped turns are admitted in a system-side elision note (with any
    # relevant ones recalled as quoted data); the *dialogue* is the newest 3.
    bodies = [m["content"] for m in messages if m["role"] != "system"]
    assert len(bodies) == 3
    assert any("turn-9" in c for c in bodies)  # newest kept
    assert not any("turn-0" in c for c in bodies)  # oldest dropped from dialogue
    assert any("not shown below" in m["content"] for m in messages if m["role"] == "system")


async def test_linked_reference_context_grounds_reply_without_polluting_lineage():
    """A referenced conversation's context is visible to the model as background,
    but it does NOT become part of this thread's own user/assistant turn sequence."""
    store, conv = await _seed()
    me = conv.default_branch_id
    await store.add_node(branch_id=me, role="user", content="my own question", author_id="bob")

    # A separate thread the user links in for cross-thread grounding.
    other = await store.create_conversation(
        workspace_id="w1", author_id="alice", title="Retrieval strategy", visibility="shared"
    )
    ob = other.default_branch_id
    await store.add_node(branch_id=ob, role="user", content="chunk size is 512 tokens", author_id="alice")
    await store.add_node(branch_id=ob, role="assistant", content="noted: 512", author_id=None)

    ref = ReferenceBlock(title=other.title, history=await store.get_history(ob))
    messages = build_messages(await store.get_history(me), references=[ref])

    # The linked context rides in a system frame (background), titled by source...
    system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "Retrieval strategy" in system_text
    assert "512 tokens" in system_text
    # ...while the thread's own turns stay clean: one real user turn, no linked
    # messages masquerading as this conversation's history.
    non_system = [m for m in messages if m["role"] != "system"]
    assert [m["role"] for m in non_system] == ["user"]
    assert non_system[0]["content"] == "[bob] my own question"


async def test_no_references_leaves_messages_unchanged():
    store, conv = await _seed()
    b = conv.default_branch_id
    await store.add_node(branch_id=b, role="user", content="hi", author_id="alice")
    history = await store.get_history(b)
    assert build_messages(history, references=[]) == build_messages(history)


async def test_render_seed_carries_thread_context_for_deep_reasoning():
    store, conv = await _seed()
    b = conv.default_branch_id
    await store.add_node(branch_id=b, role="user", content="we're picking a database", author_id="alice")
    await store.add_node(branch_id=b, role="assistant", content="Postgres or SQLite?", author_id=None)
    await store.add_node(branch_id=b, role="user", content="which scales better for us?", author_id="bob")

    seed = render_seed(await store.get_history(b))
    assert "which scales better for us?" in seed  # the question
    assert "picking a database" in seed  # prior context, not just the last line
