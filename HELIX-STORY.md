# Helix — The Story (a guided scenario for the demo)

A single narrative to carry the whole demo. It tells the project's big idea but stays
on the rails of **what's actually built**. Use it as the spoken thread between clicks;
each scene names the **feature** it shows and the **requirement** it proves.

> The premise in one breath: *a small AI team has to make a hard technical call —
> together — and Helix is where that thinking happens, branches, and gets remembered.*

---

## The cast

- **Maren** — team lead. In Helix she's the **Owner** of the workspace.
- **Adiel** — engineer. A **Collaborator**.
- **Lia** — a product stakeholder who needs to follow along but not interfere. An
  **Observer**.

*(In the live app these map to whoever has signed into the workspace; you can invite
Adiel and Lia, or just narrate them.)*

---

## Act I — The problem (set the stage)

> "Cipher Labs is shipping a feature that answers questions over long PDFs. But their
> retrieval is wrong — it keeps citing the wrong paragraph. Maren, Adiel and Lia each
> have their own AI chats open in separate tabs. The good ideas are scattered, nobody
> can see anyone else's reasoning, and yesterday's breakthrough is already lost in
> someone's history. They need one place to think together."

**That place is Helix.** *(Show: the sign-in screen, green `api ✓` badge — "it's real
and connected.")*

---

## Act II — One shared room  ·  *Sign in → Workspace → Shared conversation*

> "Maren signs in — real account, real workspace. A workspace is the team's sealed
> room; nothing leaks to another team. She opens a shared conversation, **'Retrieval
> chunking strategy,'** and asks the question that's been blocking them."

**Show:** sign in → open the workspace → the conversation → type the question → the
answer **streams in live**. *(Proves FR-1 auth, FR-2 workspace, FR-4 streaming.)*

> "Adiel jumps into the *same* thread and asks a follow-up — *'given that, which is
> simplest to ship?'* — and Helix answers using the **whole** conversation, not just
> his last line. For the first time, their AI work is shared context, not three
> private monologues."

**Show:** the follow-up reply clearly builds on the earlier answer. *(Proves FR-4
shared context.)*

---

## Act III — Two roads, no commitment  ·  *Fork & branch*

> "Now the disagreement. Maren wants to try a structural split; Adiel thinks a
> semantic-similarity split is better. Old way: they'd argue, or fork the doc and lose
> the thread. In Helix, Adiel just **forks** the conversation."

**Show:** hover a message → **fork here** → name it `semantic-split`. *(Proves FR-6.)*

> "His branch **inherits everything up to that point** — all the shared context — then
> goes its own way. Maren keeps refining the main line. Two parallel explorations from
> one shared root, and neither one pollutes the other. This is the heart of Helix:
> **branchable team conversations — Git for your AI work.**"

**Show:** send a message on the fork; switch to **main** — it never saw it. The
**branch lineage** sidebar shows both roads. *(Proves FR-6 isolation.)*

---

## Act IV — Don't reinvent what worked  ·  *Prompt library*

> "Last month, Maren wrote a brilliant 'red-team this design' prompt that always
> surfaces hidden flaws. It's saved in the team's **prompt library** — tagged and
> searchable. Instead of rewriting it, Adiel searches, finds it, and **drops it
> straight into the branch** to stress-test the semantic-split idea."

**Show:** LIBR → search → **Insert →** → it runs that prompt as a turn. *(Proves FR-7.)*

> "A team's best prompts stop being lost in chat history and become a shared asset."

---

## Act V — The hard call, made trustworthy  ·  *Deep Reasoning*

> "They're still stuck on the real decision — and it's the kind of question that needs
> more than a one-shot answer. So Maren **escalates to Deep Reasoning**: a recursive
> engine that reasons, reflects, and synthesizes in a loop."

**Show:** type the hard question → **⟳ Deep Reasoning** → the monitor lights up:
topology, energy and budget meters, depth, the live step trace. *(Proves FR-9, FR-10.)*

> "Watch the right panel — you can *see* it think, step by step. And here's the part
> that makes it trustworthy: it's **self-halting**. It stops when the answer stabilizes
> — `converged` — not when it burns through a budget. It decided it was done."

**Show:** the **converged** badge + the crystallized answer (~7s). *(Proves FR-12,
NFR-6 cost-bounded self-halt.)*

> "And the team is always in control. If a run ever goes long, there's a kill switch."

**Show:** start another run → **◼ Kill switch** → stops on command. *(Proves FR-11
kill.)*

---

## Act VI — The decision becomes a record  ·  *Replay & Export · Roles*

> "The call is made. Because every message is persisted and ordered, anyone can
> **replay** how they got here, step by step — and **export** the whole thread as
> Markdown or JSON to drop into the design doc."

**Show:** the replay scrubber → then **↓ md / ↓ json**. *(Proves FR-13.)*

> "Meanwhile Lia, the stakeholder, has been watching as an **Observer** — she sees
> everything, but can't send, fork, or steer. Role is legible at a glance, and the
> whole workspace re-skins itself to match."

**Show:** TEAM → permission matrix → flip the role switch to **Observer** → the
workspace goes read-only. *(Proves FR-3, FR-2 multi-tenancy.)*

---

## Epilogue — The next chapter (honest roadmap)

> "Today the story is told turn by turn. The next chapter makes it **live**: a
> real-time presence layer so Maren sees Adiel typing the moment he does, steering a
> Deep Reasoning run mid-flight with a nudge, and server-enforced permissions across
> every route — then containerised and deployed. The foundation for all of it is
> already in place; the frontend is built to light up the moment those land."

> "But the core is real today: **a team that thinks together, branches fearlessly,
> reuses what works, and can trust the machine on the hard calls.** That's Helix."

---

## Story → feature → show (cheat sheet)

| Beat | Feature | Proves | Show |
|---|---|---|---|
| One shared room | Auth + workspace + shared chat | FR-1/2/4 | sign in → conversation → stream |
| Same thread, full context | Shared context | FR-4 | a context-dependent follow-up |
| Two roads | Fork & branch | FR-6 | fork here → switch branches |
| Don't reinvent | Prompt library | FR-7 | search → Insert → |
| The hard call | Deep Reasoning + converge | FR-9/10/12 | escalate → `converged` |
| Stay in control | Kill switch | FR-11 | kill mid-run |
| The record | Replay + export | FR-13 | scrubber → md/json |
| Who can do what | RBAC + tenancy | FR-2/3 | role switch → Observer |
| Next chapter | Presence / steer / deploy | (roadmap) | describe, don't click |

*Pairs with `HELIX-DEMO-SCRIPT.md` (who presents each beat) and `HELIX-USAGE.md`
(exact clicks).*
