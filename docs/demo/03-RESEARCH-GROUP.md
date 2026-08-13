# 03 — Room 3: a research group

> **What they do:** read papers, explore an approach across threads, compare
> methods, and produce claims that must be traceable to sources.

The best-served room, and the one with the clearest single climax: **reload the
page and the evidence is still attached to the claim.** `docs/SCENARIOS.md`
called that the most important finding in the whole document.

**Time:** ~12 minutes for the spine, ~18 with the deep run.
**Windows:** A (PI, Owner) and B (supervisor, **Observer**).
**Cost:** cheap unless you add the deep run.

---

## Two ways to run this room

**The seeded workspace** — log in as `research@christ.edu` /
`erisk-2025-demo`, workspace *"Depression Detection — eRisk 2025"*. A real eRisk
2025 paper is already ingested at 22 chunks, with three threads and a fork to
`experiment-focal-loss` for the Map. Fastest, and the corpus is genuinely
academic.

**A live upload** — better for a first-time audience, because watching a
document become searchable in fifteen seconds is more convincing than finding
one already there.

**Do both if you have time:** upload live to show ingestion, and keep the seeded
workspace open in another tab so the Map has real history.

**Either way, demo on fresh threads.** The seeded threads exist so resurfacing
and the Map stemma have something to find. Opening them on stage shows your
working instead of the product.

---

## The story you are telling

> *"A research group's output is claims that someone else has to be able to
> check. So the question for any AI tool in a lab isn't 'is the answer good' —
> it's 'can I still see where it came from tomorrow'."*

---

## Beat 1 — ingest a paper

`DOCS` → the drop zone: *"Drop a document here, or click to browse"*, accepting
*txt · md · code · pdf — up to 8 MB each*.

Drop a paper in. It appears as `processing`, then `ready`, with a **chunk
count**.

> *"That's chunking and embedding — the text is now retrievable, not just
> stored."*

**If you need a file:** any PDF or `.txt` works. `backend/paper.pdf` is the
eRisk paper. A short text file is actually better for a live demo because you
can read the sentence the answer will ground on, out loud, before you ask.

## Beat 2 — a filename is not a citation

Open the document. Fill in the metadata — the panel is titled *"How should this
be cited?"*:

| Field | Example |
|---|---|
| Authors — e.g. Vaswani et al. | `Lewis et al.` |
| Title of the work | `Retrieval-Augmented Generation` |
| Year | `2020` |
| DOI, arXiv id, or URL | `arXiv:2005.11401` |

Save. It now cites as **`Lewis et al. (2020)`**.

> *"None of that is inferred — a model guessing an author is how a bibliography
> becomes wrong. And there's exactly one rule producing that string, shared by
> the citation chip, the exports, and the model's own context, so they can't
> drift apart."*

Say what this fixes: before, a document was a filename, so *"cite this as…"* was
impossible, no bibliography could be produced, and two versions of a preprint
were two unrelated files.

## Beat 3 — ask, and watch it ground

New shared thread, **"Grounding"**. Ask something the paper actually answers:

```
What is the relevance floor calibrated on?
```

While it streams, **grounded on** chips appear naming the source.

> *"It's telling me what it's standing on while it's still talking."*

## Beat 4 — the climax: reload the page ⚑

**Reload the browser. Scroll back to the answer.**

The citations are still there.

> *"This is the thing that used to be broken, and it's worth being honest about
> why it mattered. The citations only ever existed in the live stream — a page
> refresh dropped the evidence for every grounded answer in the thread. For a
> research team the citation **is** the artifact. An answer you can't re-check
> tomorrow isn't evidence, it's a memory."*

> *"Now they're a table — not a column, a table, because 'which answers cite
> this paper?' is a question you ask — written in the same transaction as the
> reply, inherited when you fork, and carried into both exports."*

This is the single most valuable ten seconds in the research room. Do not narrate
over the reload; let it land.

## Beat 5 — the evidence is in both documents

Research groups hand over two different things, so the evidence has to be in
both.

- `⋯` → **Export this branch (Markdown)** — the fair copy of one path. Find
  *"Grounded on"* and `Lewis et al. (2020)` under the claim.
- `⋯` → **Export decision report** — the whole thread as a decision document.
  The citation is in there too.

> *"Same evidence, two audiences: a transcript for a collaborator, a report for
> a supervisor."*

## Beat 6 — the relevance floor is a feature

Ask something the paper has nothing to say about:

```
What is the capital of Portugal?
```

No grounding chips. In the knowledge-base search, an irrelevant query shows
*"Nothing relevant"*.

> *"There's a calibrated floor so an unrelated question can't drag the knowledge
> base into its prompt. Silence is the correct answer here — a tool that always
> finds a citation is a tool whose citations mean nothing."*

Prepare this one. Nothing recovers a demo faster than a non-answer you predicted
out loud a second earlier.

## Beat 7 — search the shelf

`DOCS` → the search field: *"Search the knowledge base — the same ranking chat
grounding uses"*.

> *"Not a second search engine bolted on — literally the ranking that decides
> what an answer grounds on. If you want to know why a claim cited what it
> cited, you can ask the same question here."*

## Beat 8 — the supervisor who can speak but cannot steer

**Window A.** `TEAM` → invite **as Observer** → **copy link**.
**Window B.** Open the link, register as `prof@demo.helix`.

Now, in window B:

1. Try to send a message to the model → **refused**. An Observer cannot address
   Helix.
2. Leave a **note** → it works.

```
That floor needs a citation to the calibration set.
```

**Window A.** The note is there, in the thread, in the record.

> *"A supervisor who can comment but structurally cannot change a reply, spend
> the workspace's key, or alter a thread's lineage. And it's safe by
> construction, not by policy — a note never enters the model's context at all,
> so there's no rule to get wrong."*

Then, in window A, continue the conversation:

```
What did chunk overlap preserve?
```

It answers normally, with the note sitting in the thread, unread by the model.

> *"That's the proof. The note is visible to every human and invisible to the
> model."*

**Aside:** `TEAM` → **Permission Matrix**, tagged *policy as data* — the whole
role model as a table rather than scattered checks. And **See it as** in the top
bar previews the app as an Observer without logging out.

## Beat 9 — compare two methods

The room's real work. From an answer, **fork** two branches with real intents —
`class weights` and `focal loss` — carry each a turn or two, then give each a
verdict with a reason and adopt one.

If you have deep-run quota, escalate the harder one with **⟳ Deep Reasoning** in
**analyze** mode. Watch the monitor: live trace, stability sparkline, the
convergence meters, the Stop button.

> *"It halts when its answer converges rather than when a counter runs out — and
> you can watch it decide that, and stop it if you disagree."*

Provenance is recorded on the run: mode, model, depth, stability, confidence,
tokens, duration. It is findable months later in the run archive.

## Beat 10 — the record, and the closer

`MAP` — the stemma of competing methods, with the adopted one marked, and the
decisions ledger underneath.

Then the resurfacing closer, exactly as in room 1: start a new thread, type a
genuine rephrasing of a question this workspace already explored (**at least 18
characters, then pause**), and let the workspace remember for you.

---

## What this room proved

| Shown | Requirement |
|---|---|
| Upload, chunking, embedding, status | FR-15 |
| Document metadata and one shared `cite_as` rule | FR-15 |
| Relevance-gated grounding with citation chips | FR-15 |
| **Citations persisted on the node, surviving a reload** | the most important finding in `SCENARIOS.md` |
| Citations inherited across forks, in both exports | FR-13, FR-15 |
| Knowledge-base search on the grounding ranking | search/recall |
| Observer with exactly one write | FR-3 |
| Branch comparison, verdicts, provenance | FR-6, FR-9/10/11 |

## The scale answer, if someone asks

They will, if there is an academic in the room: *"does this work for a real
literature review?"*

> *"It was a genuine limit and it turned out not to be a scale problem. Both
> retrieval arms were being rebuilt from scratch on every single query — the
> dense arm decoded every stored vector into a Python list, and BM25 re-tokenised
> the whole corpus to answer one question. One grounded message at 10,000 chunks
> cost 1.28 seconds, and you paid it per message."*

> *"Now the workspace's vectors are one float32 matrix scored with a single
> matrix product, and BM25 keeps postings so it only visits documents that
> actually contain a query term. Same query, same machine: **2 ms at 10,000
> chunks**. On a harder corpus with realistic vocabulary, 19 ms at 10,000 and
> **55 ms at 50,000** — past a 500-paper literature review, in process, with no
> vector server."*

And the part that shows engineering maturity rather than a benchmark:

> *"A cache is the thing that rots, so the invariant has its own tests: a
> document is searchable the moment it lands, stops grounding the moment it's
> deleted, and never leaks into another workspace."*

An approximate index (pgvector, FAISS) is the next step up — and it is now a
scale decision rather than a workaround.

## Known limitation, state it before you're asked

Only extracted text is kept; the original file is not stored, so re-uploading
re-ingests. The workspace is a retrieval index over their papers, not a document
store. That is on the roadmap in the README, and naming it yourself costs you
nothing while being caught by it costs you the room.

---

Next: [`04-FEATURE-SWEEP.md`](04-FEATURE-SWEEP.md) — everything the three rooms
don't naturally reach.
