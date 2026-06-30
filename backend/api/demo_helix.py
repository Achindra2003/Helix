"""Narrated, no-UI end-to-end demo of the Helix engine — the live proof.

Run from `backend/`:
    ./.venv/Scripts/python.exe -m api.demo_helix

It exercises the whole product story as a team would, printing evidence at each
step (this *is* the no-UI live demo):

  1. A shared conversation: two teammates' turns; the assistant answers using the
     shared context (the messages it receives carry the whole thread).
  2. Fork & branch: teammate B forks A's thread at a node, inherits exactly the
     ancestor context, and diverges — B's branch never sees A's *later* messages,
     and A's branch never sees B's. (The "Git for your team's AI work" claim.)
  3. Shared prompt library: save a winning prompt, reuse it to drive a turn in a
     fresh conversation.
  4. Deep Reasoning (Ouroboros): escalate a hard question — live trace (steps +
     budget meter), the halt reason; then a cooperative kill; then steer
     (pause -> inject human input -> resume on the same thread).
  5. Export: a branch to Markdown + JSON (F9, light).

Chat uses Groq when a key is available (real multi-turn context), else the stub.
Deep Reasoning always needs Groq; that section is skipped with a clear note if no
key is present.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from .config import settings
from .conversation import engine
from .conversation.context import build_messages
from .conversation.deep_reasoning import DeepReasoningProducer, build_ouroboros_graph
from .conversation.events import (
    AssistantNode,
    Budget,
    Complete,
    Step,
    Token,
    UserNode,
    Waiting,
)
from .conversation.producer import ChatProducer
from .conversation.store import InMemoryStore
from .prompts.store import PromptStore
from .providers import get_provider

ARTIFACTS = Path(__file__).resolve().parent.parent / "demo_artifacts"


# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
def banner(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n  {title}\n{line}")


def sub(title: str) -> None:
    print(f"\n-- {title}")


def _load_groq_key() -> str:
    """Use the configured key, else fall back to the sibling Ouroboros/.env."""
    if settings.groq_api_key:
        return settings.groq_api_key
    env = Path(__file__).resolve().parent.parent.parent / "Ouroboros" / ".env"
    if env.exists():
        for raw in env.read_text(encoding="utf-8").splitlines():
            if raw.startswith("GROQ_API_KEY=") and raw.split("=", 1)[1].strip():
                return raw.split("=", 1)[1].strip()
    return ""


async def chat_turn(store, producer, branch_id, prompt, author_id, *, quiet=False):
    """Run one chat turn; print the streamed reply. Returns the assistant text."""
    if not quiet:
        print(f"   [{author_id}] {prompt}")
        print("   assistant> ", end="", flush=True)
    reply_parts: list[str] = []
    async for ev in engine.send(
        store=store, producer=producer, branch_id=branch_id, prompt=prompt, author_id=author_id
    ):
        if isinstance(ev, Token):
            reply_parts.append(ev.text)
            if not quiet:
                print(ev.text, end="", flush=True)
        elif isinstance(ev, AssistantNode) and quiet:
            reply_parts = [ev.node.content]
    if not quiet:
        print()
    return "".join(reply_parts)


# --------------------------------------------------------------------------- #
# 1 + 2 — shared context, fork & branch
# --------------------------------------------------------------------------- #
async def demo_shared_context_and_fork(store, producer):
    banner("1) SHARED, BRANCHABLE CONTEXT  +  2) FORK & BRANCH")

    conv = await store.create_conversation(
        workspace_id="acme", author_id="alice", title="DB choice", visibility="shared"
    )
    main = conv.default_branch_id

    sub("A shared thread — Alice opens it, Bob builds on it")
    await chat_turn(store, producer, main, "We're choosing a database for a small internal tool. Options?", "alice")
    # Bob's turn depends entirely on the shared context ("for that") — proof the
    # assistant is reasoning over the whole thread, not a single line.
    fork_point = (await store.get_history(main))[-1]  # fork B off Alice's answer
    await chat_turn(store, producer, main, "Given that, which is simplest to operate for us?", "bob")

    sub("What the model actually received on Bob's turn (shared context)")
    msgs = build_messages(await store.get_history(main))
    for m in msgs:
        preview = m["content"].replace("\n", " ")
        print(f"   {m['role']:>9}: {preview[:80]}")

    sub("Bob FORKS the thread at Alice's answer to explore a different angle")
    fork = await store.create_branch(conversation_id=conv.id, from_node_id=fork_point.id, name="explore-sqlite")
    print(f"   forked branch '{fork.name}' at node seq={fork_point.seq} (O(1) — no history copied)")
    await chat_turn(store, producer, fork.id, "Actually, could we just use SQLite and avoid a server entirely?", "bob")

    sub("Meanwhile Alice keeps going on the original branch")
    await chat_turn(store, producer, main, "Let's assume Postgres. What's the managed-hosting cost ballpark?", "alice")

    sub("Isolation proof — the two branches share ancestry but not each other's new turns")
    main_text = " ".join(n.content for n in await store.get_history(main))
    fork_text = " ".join(n.content for n in await store.get_history(fork.id))
    print(f"   main branch sees its own 'managed-hosting' turn:   {'managed-hosting' in main_text}")
    print(f"   fork branch does NOT see Alice's later turn:        {'managed-hosting' not in fork_text}")
    print(f"   fork branch sees its own 'SQLite' turn:             {'SQLite' in fork_text}")
    print(f"   main branch does NOT see Bob's fork turn:           {'avoid a server entirely' not in main_text}")
    print(f"   BOTH inherit Alice's shared opening turn:           "
          f"{'choosing a database' in main_text and 'choosing a database' in fork_text}")
    return conv, main


# --------------------------------------------------------------------------- #
# 3 — shared prompt library
# --------------------------------------------------------------------------- #
async def demo_prompt_library(store, producer):
    banner("3) SHARED PROMPT LIBRARY (save a winning prompt, reuse it)")

    db = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    from .conversation import models  # noqa: F401
    from .prompts import models as prompt_models  # noqa: F401
    from .db import Base

    async with db.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    prompts = PromptStore(async_sessionmaker(db, expire_on_commit=False))

    sub("Alice saves a prompt that worked well")
    winning = await prompts.save(
        workspace_id="acme", author_id="alice", title="Decision matrix",
        body="Give me a concise decision matrix (options as rows, criteria as columns) for this.",
        tags=["Decisions", "Template"],
    )
    print(f"   saved prompt '{winning.title}' (tags={winning.tags})")

    sub("Search the library")
    found = await prompts.list("acme", query="decision matrix")
    print(f"   search 'decision matrix' -> {[p.title for p in found]}")

    sub("Reuse the SAME prompt to drive a turn in a brand-new conversation")
    fresh = await store.create_conversation(
        workspace_id="acme", author_id="carol", title="Vendor pick", visibility="shared"
    )
    reused = await prompts.get(winning.id)
    await chat_turn(store, producer, fresh.default_branch_id, reused.body, "carol")
    first_turn = (await store.get_history(fresh.default_branch_id))[0]
    print(f"   the new conversation's first turn IS the saved prompt: {first_turn.content == winning.body}")
    await db.dispose()


# --------------------------------------------------------------------------- #
# 4 — deep reasoning: trace + convergence, kill, steer
# --------------------------------------------------------------------------- #
async def _deep_run(producer, history, *, label, limit=None):
    """Drive a deep-reasoning run, printing the live trace. Returns the Complete."""
    steps = 0
    final: Complete | None = None
    answer_parts: list[str] = []
    async for ev in producer.run(history):
        if isinstance(ev, Step):
            steps += 1
            thought = (ev.payload.get("thought") or ev.payload.get("synthesis") or "")[:60]
            print(f"   step {ev.idx:>2} [{ev.node:<11}] depth={ev.depth} energy={ev.energy:>5.1f}  {thought}")
        elif isinstance(ev, Budget):
            bar = "#" * int(ev.pct * 20)
            print(f"        budget |{bar:<20}| {ev.tokens_used} tok ({ev.pct*100:.1f}%)")
        elif isinstance(ev, Token):
            answer_parts.append(ev.text)
        elif isinstance(ev, Waiting):
            print(f"   >> PAUSED for {ev.reason} (awaiting human input)")
            return None, "".join(answer_parts)
        elif isinstance(ev, Complete):
            final = ev
    if answer_parts:
        print(f"   answer> {''.join(answer_parts)[:300]}")
    if final:
        print(f"   [{label}] status={final.status} stop_reason={final.stop_reason} steps={steps}")
    return final, "".join(answer_parts)


async def demo_deep_reasoning(groq_key):
    banner("4) DEEP REASONING (Ouroboros) — trace, convergence, kill, steer")
    if not groq_key:
        print("   (skipped — no GROQ_API_KEY available)")
        return

    store = InMemoryStore()
    conv = await store.create_conversation(
        workspace_id="acme", author_id="alice", title="Hard call", visibility="shared"
    )
    b = conv.default_branch_id
    # Build a little shared context so deep reasoning seeds over the thread.
    await store.add_node(branch_id=b, role="user", content="We keep flip-flopping between a monolith and microservices.", author_id="alice")
    await store.add_node(branch_id=b, role="assistant", content="Both have real trade-offs for a 4-person team.", author_id=None)
    question = "For a 4-person team shipping a v1 in 6 weeks, what's the right call and why?"
    await store.add_node(branch_id=b, role="user", content=question, author_id="bob")
    history = await store.get_history(b)

    sub("Escalate the question — adaptive controller ON (principled convergence)")
    graph, cfg, make_inputs, usage = build_ouroboros_graph(
        thread_id="demo-converge", groq_api_key=groq_key, groq_model=settings.groq_model,
        mode="analyze", adaptive=True, compute_budget=6,
        stability_threshold=0.78, confidence_threshold=0.7,
    )
    conv_producer = DeepReasoningProducer(
        graph=graph, graph_config=cfg, make_inputs=make_inputs, usage_reader=usage,
        token_budget=settings.deep_reasoning_token_budget,
    )
    await _deep_run(conv_producer, history, label="converge")

    await asyncio.sleep(3)  # be gentle on free-tier rate limits between runs
    sub("Cooperative KILL — stop the run mid-flight (RBAC-gated in the API)")
    graph2, cfg2, mk2, us2 = build_ouroboros_graph(
        thread_id="demo-kill", groq_api_key=groq_key, groq_model=settings.groq_model,
        mode="analyze", adaptive=True, compute_budget=6,
    )
    state = {"n": 0}

    def should_stop():
        state["n"] += 1
        return state["n"] > 3  # let a few steps through, then kill

    kill_producer = DeepReasoningProducer(
        graph=graph2, graph_config=cfg2, make_inputs=mk2, usage_reader=us2, should_stop=should_stop,
    )
    await _deep_run(kill_producer, history, label="kill")

    await asyncio.sleep(3)
    sub("STEER — pause for human input, then resume on the same thread")
    graph3, cfg3, mk3, us3 = build_ouroboros_graph(
        thread_id="demo-steer", groq_api_key=groq_key, groq_model=settings.groq_model,
        mode="analyze", adaptive=False, compute_budget=4,  # non-adaptive => steer fires
        steer_interval=1,  # pause at the first breathe so the demo doesn't run long
    )
    steer_producer = DeepReasoningProducer(
        graph=graph3, graph_config=cfg3, make_inputs=mk3, usage_reader=us3,
    )
    final, _ = await _deep_run(steer_producer, history, label="steer")
    if final is None:  # it paused at the steer interrupt
        print("   injecting human steer: 'Optimize for shipping speed over scalability.'")
        resumed_steps = 0
        async for ev in steer_producer.resume("Optimize for shipping speed over scalability."):
            if isinstance(ev, Step):
                resumed_steps += 1
                if "steer" in ev.payload.get("thought", "").lower() or resumed_steps <= 3:
                    print(f"   step {ev.idx:>2} [{ev.node:<11}] (resumed with human input)")
            elif isinstance(ev, Complete):
                print(f"   [steer] resumed -> status={ev.status} stop_reason={ev.stop_reason}")
                break
            elif isinstance(ev, Waiting):
                # Non-adaptive runs offer repeated steer points; one resume is enough
                # to prove the mechanism for the demo.
                print(f"   resumed and continued for {resumed_steps} steps "
                      f"(engine offers another steer point — steering is iterative)")
                break
    else:
        print("   (run completed without pausing this time)")


# --------------------------------------------------------------------------- #
# 5 — export
# --------------------------------------------------------------------------- #
def render_markdown(title: str, nodes) -> str:
    lines = [f"# {title}", ""]
    for n in nodes:
        who = n.author_id or n.role
        lines.append(f"**{who}** ({n.role}):\n\n{n.content}\n")
    return "\n".join(lines)


def render_json(title: str, nodes) -> str:
    return json.dumps(
        {"title": title, "nodes": [
            {"seq": n.seq, "role": n.role, "author_id": n.author_id, "content": n.content}
            for n in nodes
        ]},
        indent=2,
    )


async def demo_export(store, branch_id):
    banner("5) EXPORT (F9, light) — Markdown + JSON")
    nodes = await store.get_history(branch_id)
    ARTIFACTS.mkdir(exist_ok=True)
    md_path = ARTIFACTS / "conversation.md"
    json_path = ARTIFACTS / "conversation.json"
    md_path.write_text(render_markdown("DB choice (main branch)", nodes), encoding="utf-8")
    json_path.write_text(render_json("DB choice (main branch)", nodes), encoding="utf-8")
    print(f"   wrote {md_path}")
    print(f"   wrote {json_path}")
    print(f"   ({len(nodes)} nodes exported)")


# --------------------------------------------------------------------------- #
async def main():
    groq_key = _load_groq_key()
    if groq_key:
        settings.groq_api_key = groq_key
        settings.llm_provider = "groq"
        # Use the fast, high-rate-limit model so a live demo doesn't hit free-tier
        # throttling. Production can switch back to a larger model for quality.
        settings.groq_model = "llama-3.1-8b-instant"
        print(f"Chat provider: groq ({settings.groq_model})")
    else:
        print("Chat provider: stub (no GROQ_API_KEY found — chat is echoed)")

    store = InMemoryStore()
    producer = ChatProducer(get_provider())

    _, main_branch = await demo_shared_context_and_fork(store, producer)
    await demo_prompt_library(store, producer)
    await demo_deep_reasoning(groq_key)
    await demo_export(store, main_branch)

    banner("DEMO COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
