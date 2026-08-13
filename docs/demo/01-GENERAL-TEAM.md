# 01 — Room 1: a general team, discussing and brainstorming

> **What they do:** open a question with no right answer, generate a lot of
> options quickly, argue, and leave with a decision and a reason.

This room owns Helix's signature move — **exploring several answers at once and
then converging on one** — and it ends with an artifact you can hand to someone
who was not in the meeting.

**Time:** ~12 minutes for the spine, ~20 with every aside.
**Windows:** A (you, Owner) and B (teammate, Collaborator), side by side.
**Cost:** cheap. No deep runs here unless you choose to add one.

---

## The story you are telling

> *"A team has to decide how onboarding should work. There is no right answer.
> Normally this is three people in three private AI tabs, and by Friday nobody
> can remember why the decision was made. Watch what happens when the thinking
> is in one place."*

---

## Beat 1 — a thread is a shared object, not a private tab

**Window A.** `CHAT` → new conversation → title **"How should onboarding
work?"** → visibility **shared**.

**Window B.** It is already in the list. Nobody sent anything.

> *"I made that thread a second ago and it's already his. That's the whole
> premise — the record is the workspace's, not mine."*

A **private** thread, by contrast, never appears in anyone else's lists,
fetches, or realtime room. Mention that; it is the reason "shared" is a
deliberate choice rather than a default nobody thought about.

## Beat 2 — the reply streams to everyone at once

**Window A.** Ask:

```
Give me three onboarding approaches for a team collaboration tool.
```

**Watch window B while you do it.** The tokens arrive there too, in a live
attribution banner naming you, with author-coloured margins.

> *"I'm typing in my window. He didn't refresh anything."*

This is the moment that sells the product, and it is worth being quiet for two
seconds while it happens. Point at window B, not window A.

**Also on screen:** the presence roster shows not just *who* is here but *which
branch* each person is reading.

## Beat 3 — a note is for the room; the model never reads it

**Window B.** In the composer, switch to a **note** — the control whose tooltip
reads *"Say this to your teammates instead of to Helix — it stays in the thread,
and the model never reads it."*

```
@you I think the second one is closest, but it's expensive.
```

The `@` opens a mention picker that resolves against the **workspace's own
members** — not a text convention, a real lookup.

**Window A.** The top bar's **What you missed** now carries a notice saying who
asked. Open it; it says who, and it survives closing the tab.

> *"Two kinds of speech in one thread. One goes to the model, one goes to the
> team, and the model structurally cannot read the second one. That's not a
> setting — a note never enters the model's context at all."*

This is also the mechanism that makes the Observer role safe in room 3.

## Beat 4 — the prompt library

**Window A.** `PROMPTS` → save a prompt:

- **Title:** `Adversarial`
- **Body:** `Argue the strongest case against the above.`
- **Tags:** `review`

Back in `CHAT`, use the composer's **Insert from prompt library** control and
run it — no retyping.

> *"A facilitator's moves become workspace property. 'Socratic critique' and
> 'Adversarial red-team' ship as starters."*

## Beat 5 — **Explore ways**: the signature move

This is the centrepiece. Do not rush it.

Hover the assistant's answer. Two actions appear:

| Control | Tooltip | When you use it |
|---|---|---|
| **Fork** | *"Fork a new branch from here"* | You are choosing between two serious options |
| **Explore** | *"Explore several angles from here, side by side"* | You want four cheap, disposable ideas at once |

Pick **Explore**. The dialog is *"Explore several ways at once"*. Type angles —
**a new row appears as you fill the last one**, so the list grows under your
hands:

```
guided product tour
sample data pre-loaded
a concierge first session
do nothing — let them explore
```

Confirm. The view becomes **"Exploring in parallel"**: four columns, four
answers arriving *simultaneously*.

**Say the two things that make this more than a layout:**

> *"Each column is a real branch — its own lineage, its own verdict, its own
> place on the Map. This isn't a comparison view bolted on; it's four forks
> being looked at four at a time."*

> *"And notice I never re-asked the question. Each branch inherits the thread up
> to the fork point, so the angle is the whole of what's new."*

Branches are **named from their angles** — a label nobody had to invent, and
the angle survives as the branch's intent, so a throwaway exploration can still
carry a meaningful verdict if it turns out to be the good one.

## Beat 6 — converge: backing is approval voting

Under each column: **back**.

**Window A.** Back *sample data*.
**Window B.** Back *sample data* too — the tally moves to `· 2`.
**Window B.** Also back *concierge*.

> *"He's backing two. Backing isn't a vote you spend — it's approval voting, so
> you can support everything you'd be happy with."*

**Window B.** Click *backing* again on *concierge* to withdraw it.

> *"And it's withdrawable, which is what makes it safe to back something on a
> hunch. This is a reading of the room, not a ballot."*

## Beat 7 — decide, and record what lost

Click **verdict** under *sample data*:

- **Status:** adopted
- **Why:** `Sample data gets them to value fastest.`

Then **verdict** under *guided tour*:

- **Status:** abandoned
- **Why:** `A tour teaches the UI, not the job.`

> *"The rejected one gets a reason too. That's half of why a decision holds up
> six months later — anyone can see the road not taken and why."*

Close the comparison with **Done**.

## Beat 8 — conclude the thread

**Stage header → Conclude.** The dialog says *"A reading of the room, not the
decision."*

```
Ship sample data first; revisit the tour after launch.
```

Conclude and Fork sit **outside** the `⋯` menu deliberately — everything rare
moved one click away so the two that matter stay visible.

## Beat 9 — the Map, and the ledger

`MAP`. The stemma shows main plus four explorations, with the adopted one
marked. Below it, the **decisions ledger** carries every verdict in the
workspace.

> *"Nobody wrote this. It's a by-product of deciding things in the open."*

## Beat 10 — the artifact

Stage header → `⋯` → **Export decision report**.

Read three lines out of it aloud:

- the decision — *Sample data gets them to value fastest*
- the rejection — *A tour teaches the UI, not the job*
- the conclusion — *Ship sample data first*

> *"That's the meeting's minutes, and nobody took minutes."*

Also in that menu: **Export this branch (Markdown)** and **(JSON)** — the fair
copy of one path, as opposed to the decision report's view of the whole thread.

## Beat 11 — the closer: resurfacing

The payoff for everything above. Start a **new** conversation in the same
workspace and begin typing:

```
what should new users see the first time they open the product
```

Pause. A strip appears offering the thread that already explored this.

> *"Nobody searched. I started typing, and the workspace remembered. That is the
> entire product in one gesture — the record compounds, so nobody re-asks what a
> colleague already solved."*

**Three things that will make this fail, so know them:**

1. **Type at least 18 characters.** Below that it does not even look.
2. **Pause after typing.** It is debounced; it fires when you stop.
3. **It is gated hard on relevance** (a 0.33 cosine floor, stricter than the
   0.20 floor used for document grounding). An adjacent-but-different question
   will correctly show nothing. This is unsolicited UI, so silence beats noise.

Rehearse this one. Use a question that is a genuine rephrasing of the original,
not a neighbouring topic.

---

## What this room proved

| Shown | Requirement |
|---|---|
| Register, workspace, invite by role | FR-1, FR-2, FR-3 |
| Shared thread, shared context, token streaming | FR-4 |
| Presence, live fan-out to the whole room | FR-5 |
| Fork, explore-in-parallel, lineage | FR-6 |
| Prompt library | FR-7 |
| Backing, verdicts, conclusion, decisions ledger | the converge half |
| Export decision report | FR-13 |
| Notes, @mentions, durable notices | the "speech that isn't a prompt" idea |
| Proactive resurfacing | the product's whole thesis |

## Asides you can take if the room is interested

- **Edit and resend** — hover your own message: *"removes this message (and its
  reply) and puts the text back in the composer"*. It is safe only when nothing
  has forked from it, because history stays append-only for anyone who already
  branched off.
- **Replay this thread** (`⋯`) — walk the conversation forward in time.
- **Link another thread's context** (`⋯`) — cross-conversation references, live
  in both threads.
- **`Ctrl+K`** — search across every conversation in the workspace.
- **Comparing explorations** — reopen the comparison later from the lineage. The
  question *"which of these did we like?"* gets asked again days later, and
  clicking between four branches to answer it is the work this view removes.

## The one thing this room asks for and does not get

Running the same question in **two reasoning modes** side by side. The columns
and the fan-out would carry it; three concurrent 120b recursive runs is the
opposite of cheap, disposable divergence. It is a cost decision, and it is the
only thing on `docs/SCENARIOS.md` that the general room asked for and did not
get. Escalating one column to Deep Reasoning already works.

Say it if asked. A team that knows exactly what it chose not to build reads as
more confident than one that claims everything.

---

Next: [`02-DEV-TEAM.md`](02-DEV-TEAM.md).
