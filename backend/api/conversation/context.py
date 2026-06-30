"""Context assembly — turning a branch's node history into the model's input.

This is the heart of the "shared, branchable context" claim. `get_history`
already walks the `parent_id` spine across fork boundaries, so a forked branch
inherits exactly its ancestors' nodes and nothing from sibling branches. This
module turns that lineage into a well-formed, role-structured chat context:

- proper `system` framing (it's a *shared team workspace*, not a private chat),
- real `user`/`assistant` roles (not a flattened "user: …" string), so the model
  uses the inherited context the way it was actually authored, and
- a bounded window so long threads stay within the model's context limit while
  always preserving the system frame and the most recent turns.

Both producers consume this: chat streams `build_messages` to the provider;
deep reasoning seeds Ouroboros with `render_seed` (recent context + the question)
so it reasons over the thread, not just the last line.
"""
from __future__ import annotations

from dataclasses import dataclass

from .events import Node

Message = dict[str, str]  # OpenAI/Groq shape: {"role": ..., "content": ...}


@dataclass
class ReferenceBlock:
    """A *linked* conversation's context, pulled in live for cross-thread grounding.

    Unlike a fork (which inherits an ancestor spine *inside* one conversation tree),
    a reference is a live pointer to a **separate** shared conversation: at send time
    the router resolves the linked thread's current history into one of these, so the
    model can answer the user's turn using context from another team thread without
    that thread's messages becoming part of this branch's own lineage.
    """

    title: str
    history: list[Node]

SYSTEM_PROMPT = (
    "You are the single shared AI assistant inside a team's collaborative workspace. "
    "Different teammates may have written the user messages in this thread; each user "
    "message is prefixed with the author's name in brackets, e.g. '[alice] ...', so you "
    "can tell who said what. These are for your understanding only. "
    "Respond ONLY as the assistant, in your own voice — give one direct, helpful answer. "
    "Do NOT impersonate teammates, do NOT prefix your reply with a name, and do NOT "
    "fabricate messages from other people. Use the full shared context (a branch may "
    "inherit context forked from an earlier point) to ground your answer."
)

# Default rolling window: keep the system frame + the most recent turns. Bounds
# token cost on long shared threads without losing the immediate context.
DEFAULT_MAX_TURNS = 40

_ROLE_MAP = {"user": "user", "assistant": "assistant", "system": "system"}


def render_references(references: list[ReferenceBlock], *, max_turns: int = 20) -> str:
    """Render linked conversations as one background block for the system frame.

    Each linked thread is a compact, labelled transcript. This is *supporting*
    context the user pulled in from other threads — explicitly framed as separate
    from this thread's own turn-by-turn history so the model grounds on it without
    treating it as messages in the current branch.
    """
    sections: list[str] = [
        "The user has linked other conversations from this workspace as background "
        "context. Use them as supporting reference, but they are NOT part of this "
        "thread's own turn-by-turn history — do not attribute their turns to this chat."
    ]
    for ref in references:
        if not ref.history:
            continue
        sections.append(
            f'--- Referenced conversation: "{ref.title}" ---\n'
            + render_transcript(ref.history, max_turns=max_turns)
        )
    return "\n\n".join(sections)


def build_messages(
    history: list[Node],
    *,
    system: str | None = SYSTEM_PROMPT,
    max_turns: int = DEFAULT_MAX_TURNS,
    references: list[ReferenceBlock] | None = None,
) -> list[Message]:
    """Render branch history (root -> head) into role-structured chat messages.

    Keeps the system frame plus the most recent `max_turns` nodes. Authorship is
    annotated inline for user turns so the model can tell teammates apart in a
    shared thread without us inventing non-standard roles. Any linked conversations
    (`references`) are folded into a second system message *before* this thread's
    turns, so cross-thread context grounds the reply without polluting the lineage.
    """
    turns = history[-max_turns:] if max_turns and len(history) > max_turns else history

    messages: list[Message] = []
    if system:
        messages.append({"role": "system", "content": system})
    if references:
        block = render_references(references)
        if block:
            messages.append({"role": "system", "content": block})

    for node in turns:
        role = _ROLE_MAP.get(node.role, "user")
        content = node.content
        if role == "user" and node.author_id:
            content = f"[{node.author_id}] {content}"
        messages.append({"role": role, "content": content})
    return messages


def render_transcript(history: list[Node], *, max_turns: int = DEFAULT_MAX_TURNS) -> str:
    """A compact plain-text transcript of recent context (for prompts/seeds)."""
    turns = history[-max_turns:] if max_turns and len(history) > max_turns else history
    lines = []
    for node in turns:
        who = node.author_id or node.role
        lines.append(f"{who} ({node.role}): {node.content}")
    return "\n".join(lines)


def render_seed(history: list[Node], *, context_turns: int = 12) -> str:
    """Build a context-aware seed for Deep Reasoning.

    The latest user message is the question; the preceding turns are supplied as
    background so the engine reasons over the thread rather than one line in
    isolation. Falls back to just the question when there's no prior context.
    """
    if not history:
        return ""
    question = history[-1].content
    prior = history[:-1][-context_turns:]
    if not prior:
        return question
    background = render_transcript(prior, max_turns=context_turns)
    return (
        f"Discussion so far:\n{background}\n\n"
        f"Question to reason about:\n{question}"
    )
