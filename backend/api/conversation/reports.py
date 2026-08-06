"""The documents that leave Helix.

The product's claim is that a decision stays defensible later. A record that
can only be defended by logging in is not defensible — it is a UI. What makes
it defensible is a document you can hand to someone who was not there: a
reviewer, a new teammate, an auditor, the version of you in six months.

Until now the only export was one branch's transcript. That contradicted the
thesis directly, because a branch is a single path: the alternative that was
weighed and rejected — half of why the decision holds — was not in the file.
And there was no answer at all to "what has this team decided?", which is the
question the ledger exists to answer on screen.

So two reports, at the two scopes people actually ask about:

- **A conversation** — what was decided, every exploration including the ones
  abandoned, each verdict with its reason and who recorded it, the reasoning
  runs that informed it, and the threads it drew context from.
- **A workspace** — the same decisions, gathered, so the answer to "what did
  we settle?" is a file rather than a tour of the app.

Both are built once into a structured dict and then rendered. Markdown and
JSON are therefore the *same report* in two costumes, rather than two
renderings that drift apart — which is how the per-branch export came to say
things the JSON did not.

What is deliberately absent: per-message grounding citations. They exist only
in the live stream and were never persisted on nodes, so a report claiming to
list "the sources cited" would be inventing them. Linked threads are recorded
and are listed; documents cited in passing are not, and saying so is better
than a plausible fiction — which is a failure mode this product has already
had to design against once.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .events import Node
from .models import DeepRunRow
from .store import Branch, Conversation

COLOPHON = "❧ fair copy · exported from Helix on {today} ❧"


def filename_stem(title: str, fallback: str) -> str:
    """A filesystem-safe stem for `Content-Disposition`."""
    return "".join(c if c.isalnum() else "-" for c in title).strip("-") or fallback


class Names:
    """Author ids resolved to emails, each looked up at most once.

    A report attributes every verdict, so the same handful of ids recur on
    every line; without the cache a busy workspace would issue one query per
    mention.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cache: dict[str, str] = {}

    async def of(self, user_id: str | None) -> str:
        if not user_id:
            return ""
        if user_id not in self._cache:
            row = await self._session.get(User, user_id)
            self._cache[user_id] = row.email if row else user_id
        return self._cache[user_id]


def _stamp(who: str, when: datetime | None) -> str:
    """"Recorded by X on Y" — with whichever halves exist."""
    parts = []
    if who:
        parts.append(f"by {who}")
    if when:
        parts.append(f"on {when.date().isoformat()}")
    return ("Recorded " + " ".join(parts) + ".") if parts else ""


def _own_nodes(nodes: list[Node], fork_node_id: str | None) -> list[Node]:
    """The nodes this branch added, not the history it inherited.

    `get_history` walks across branch boundaries, so a fork's history begins
    with the whole trunk it grew from. Printing that for every branch would
    repeat the shared prefix once per exploration and bury the divergence —
    which is the one thing a reader is here to see.
    """
    if fork_node_id is None:
        return nodes
    for i, n in enumerate(nodes):
        if n.id == fork_node_id:
            return nodes[i + 1 :]
    return nodes


async def _turns(nodes: list[Node], names: Names) -> list[dict[str, Any]]:
    out = []
    for n in nodes:
        out.append(
            {
                "role": n.role,
                # A note is written by a person and never reaches the model; an
                # assistant turn has no author. Both facts have to survive into
                # the document, or a reader cannot tell what the model was
                # actually told.
                "author": "Helix" if n.role == "assistant" else await names.of(n.author_id),
                "content": n.content,
                "sent_to_model": n.role != "note",
            }
        )
    return out


async def build_conversation_report(
    *,
    conv: Conversation,
    branches: list[Branch],
    histories: dict[str, list[Node]],
    deep_runs: list[DeepRunRow],
    references: list[Conversation],
    names: Names,
) -> dict[str, Any]:
    """Everything the conversation report states, in one structure."""
    # The trunk first, then the forks in the order they were made — the order
    # the thinking actually happened in.
    ordered = sorted(branches, key=lambda b: b.id != conv.default_branch_id)

    explorations = []
    for b in ordered:
        nodes = _own_nodes(histories.get(b.id, []), b.fork_node_id)
        explorations.append(
            {
                "name": b.name,
                "is_trunk": b.id == conv.default_branch_id,
                "intent": b.intent,
                "status": b.status,
                "resolution": b.resolution,
                "resolved_by": await names.of(b.resolved_by),
                "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
                "turns": await _turns(nodes, names),
            }
        )

    runs = []
    for r in deep_runs:
        runs.append(
            {
                "question": r.question,
                "status": r.status,
                "stop_reason": r.stop_reason,
                "passes": r.depth,
                "stability": round(r.stability, 2),
                "confidence": round(r.confidence, 2),
                "tokens_used": r.tokens_used,
                "model": r.model,
                "asked_by": await names.of(r.author_id),
                "at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {
        "kind": "conversation_report",
        "title": conv.title,
        "conversation_id": conv.id,
        "visibility": conv.visibility,
        "exported_on": date.today().isoformat(),
        "conclusion": {
            "text": conv.conclusion,
            "recorded_by": await names.of(conv.concluded_by),
            "recorded_at": conv.concluded_at.isoformat() if conv.concluded_at else None,
        },
        "explorations": explorations,
        "reasoning_runs": runs,
        "context_from": [{"id": c.id, "title": c.title} for c in references],
    }


def render_conversation_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [f"# {report['title']}", ""]
    lines += [f"*Helix decision report · exported {report['exported_on']}*", ""]

    # The decision leads. Someone handed this file opens it to find out what was
    # settled — making them infer that from a transcript is the copy-paste
    # problem the export exists to replace.
    lines += ["## What was decided", ""]
    conclusion = report["conclusion"]
    if conclusion["text"]:
        lines += [conclusion["text"], ""]
        stamp = _stamp(
            conclusion["recorded_by"],
            _parse(conclusion["recorded_at"]),
        )
        if stamp:
            lines += [f"*{stamp}*", ""]
    else:
        # Said plainly rather than omitted: an absent section reads like an
        # export bug, while "nothing yet" is a true and useful statement about
        # the thread.
        lines += ["*Nothing concluded yet — this thread is still open.*", ""]

    explorations = report["explorations"]
    lines += ["## How it was decided", ""]
    lines += [_explorations_summary(explorations), ""]

    for e in explorations:
        # The trunk is named for what it is, so a reader does not go looking
        # for a verdict on it — only forks are resolved.
        suffix = " *(the original thread)*" if e["is_trunk"] else ""
        lines += [f"### {e['name']}{suffix}", ""]
        if e["intent"]:
            lines += [f"**Was trying:** {e['intent']}", ""]
        if e["status"] != "open":
            verdict = f"**Verdict: {e['status'].capitalize()}**"
            if e["resolution"]:
                verdict += f" — {e['resolution']}"
            lines += [verdict, ""]
            stamp = _stamp(e["resolved_by"], _parse(e["resolved_at"]))
            if stamp:
                lines += [f"*{stamp}*", ""]
        if not e["turns"]:
            lines += ["*No messages on this branch.*", ""]
        for t in e["turns"]:
            if not t["sent_to_model"]:
                # Quoted, and labelled with why it is quoted. A note read as a
                # prompt would misrepresent what the model was told, which is
                # the one thing a transcript exists to record faithfully.
                lines += [
                    f"> **Note from {t['author'] or 'a teammate'}** — written for the team, never sent to the model",
                    ">",
                ]
                lines += [f"> {line}" for line in t["content"].splitlines()]
                lines += [""]
                continue
            lines += [f"**{t['author'] or 'Unknown'}**", "", t["content"], ""]

    runs = report["reasoning_runs"]
    if runs:
        lines += ["## Reasoning runs", ""]
        lines += [
            f"{_count(len(runs), 'Deep Reasoning run')} informed this thread.",
            "",
        ]
        for r in runs:
            detail = [
                f"stopped on *{r['stop_reason']}*" if r["stop_reason"] else r["status"],
                f"{r['passes']} passes" if r["passes"] else "",
                f"stability {r['stability']}",
                f"{r['tokens_used']:,} tokens" if r["tokens_used"] else "",
                r["model"],
            ]
            lines += [
                f"- **“{r['question']}”** — " + " · ".join(d for d in detail if d),
            ]
        lines += [""]

    refs = report["context_from"]
    if refs:
        lines += ["## Context drawn from", ""]
        # Named, not just counted: these are the threads whose content was in
        # the model's context, so they are part of why the answers read as they
        # do.
        lines += [f"- {r['title']}" for r in refs]
        lines += [""]

    lines += ["---", "", COLOPHON.format(today=report["exported_on"]), ""]
    return "\n".join(lines)


async def build_workspace_report(
    *,
    workspace_name: str,
    conversations: list[Conversation],
    branches_by_conv: dict[str, list[Branch]],
    names: Names,
) -> dict[str, Any]:
    """Every decision the caller may see, gathered by thread.

    Same scoping as the on-screen ledger, and the same rule about what counts:
    a conclusion is a decision, a resolved branch is a decision, an open
    exploration is not.
    """
    threads = []
    decisions = 0
    for conv in conversations:
        verdicts = []
        for b in branches_by_conv.get(conv.id, []):
            if b.status == "open":
                continue
            verdicts.append(
                {
                    "name": b.name,
                    "intent": b.intent,
                    "status": b.status,
                    "resolution": b.resolution,
                    "recorded_by": await names.of(b.resolved_by),
                    "recorded_at": b.resolved_at.isoformat() if b.resolved_at else None,
                }
            )
        if not conv.conclusion and not verdicts:
            continue
        decisions += len(verdicts) + (1 if conv.conclusion else 0)
        threads.append(
            {
                "conversation_id": conv.id,
                "title": conv.title,
                "conclusion": {
                    "text": conv.conclusion,
                    "recorded_by": await names.of(conv.concluded_by),
                    "recorded_at": conv.concluded_at.isoformat()
                    if conv.concluded_at
                    else None,
                },
                "verdicts": verdicts,
            }
        )

    return {
        "kind": "workspace_report",
        "workspace": workspace_name,
        "exported_on": date.today().isoformat(),
        "decision_count": decisions,
        "threads": threads,
    }


def render_workspace_markdown(report: dict[str, Any]) -> str:
    threads = report["threads"]
    lines = [f"# {report['workspace']} — what the team has decided", ""]
    lines += [
        f"*Helix decision report · {_count(report['decision_count'], 'decision')} "
        f"across {_count(len(threads), 'thread')} · exported {report['exported_on']}*",
        "",
    ]

    if not threads:
        lines += [
            "*No decisions recorded yet. A thread reaches this report once it "
            "has a conclusion, or once one of its explorations has a verdict.*",
            "",
        ]

    for t in threads:
        lines += [f"## {t['title']}", ""]
        conclusion = t["conclusion"]
        if conclusion["text"]:
            lines += [f"**Concluded:** {conclusion['text']}", ""]
            stamp = _stamp(conclusion["recorded_by"], _parse(conclusion["recorded_at"]))
            if stamp:
                lines += [f"*{stamp}*", ""]
        if t["verdicts"]:
            # Labelled, because otherwise the list runs straight on from the
            # conclusion and reads as part of it rather than as the
            # explorations the conclusion was drawn from.
            lines += [f"**{_count(len(t['verdicts']), 'exploration')} resolved:**", ""]
        for v in t["verdicts"]:
            entry = f"- **{v['name']}** — {v['status'].capitalize()}"
            if v["resolution"]:
                entry += f" — {v['resolution']}"
            lines.append(entry)
            if v["intent"]:
                lines.append(f"  - *Was trying:* {v['intent']}")
            stamp = _stamp(v["recorded_by"], _parse(v["recorded_at"]))
            if stamp:
                lines.append(f"  - *{stamp}*")
        lines += [""]

    lines += ["---", "", COLOPHON.format(today=report["exported_on"]), ""]
    return "\n".join(lines)


# --- small shared helpers -------------------------------------------------------


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _explorations_summary(explorations: list[dict]) -> str:
    """One line describing the shape of the thinking.

    The trunk is not counted as an exploration. It is the thread itself, it
    never carries a verdict, and counting it would report "2 explorations, 1
    still open" for what is really one fork that was closed.
    """
    forks = [e for e in explorations if not e["is_trunk"]]
    if not forks:
        return "No forks — a single line of thinking."
    tally = {"adopted": 0, "abandoned": 0, "open": 0}
    for f in forks:
        tally[f["status"]] = tally.get(f["status"], 0) + 1
    tail = [f"{n} {name}" for name, n in tally.items() if n]
    return (
        f"{_count(len(forks), 'exploration')} off the trunk — " + ", ".join(tail) + "."
    )
