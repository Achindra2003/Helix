/**
 * Every mark Helix draws, named once.
 *
 * The interface had grown 62 distinct glyphs, chosen per component, which is
 * what happens when marks are picked at the moment they are needed. That
 * produced four kinds of defect:
 *
 *   - marks from unrelated worlds — ⌘ (the Mac Command key) for documents, ♔
 *     (a chess king) for the owner, ⚒ (a mining hammer) for the agent, ☁
 *     (weather) for the provider, and an 👁 emoji in a live status string;
 *   - ☷ (U+2637, an I Ching trigram) labelling the run archive — a divinatory
 *     mark, against the project's identity constraint, on the screen most
 *     likely to be examined closely;
 *   - a collision: ⌇ was both the rail's CHAT and the Fork action;
 *   - near-identical circles (◍ ⊙ ◉ ● ○ ◌ ◆ ◈ ❖ ◱ ◫ ◷ ⊘) carrying unrelated
 *     meanings at 11–13px, where they are not distinguishable.
 *
 * THE RULE. Every mark comes from the world of books and the ruled page, from
 * astronomy, or from the helix itself. One meaning per mark, one mark per
 * meaning. Nothing from another product's keyboard, no emoji, and nothing
 * drawn from alchemical or divinatory traditions.
 *
 * One deliberate exception: SETUP keeps a gear. A settings gear is understood
 * everywhere, and a private mark invented in its place would cost a reader more
 * than the consistency gains.
 *
 * Anything ornamental (fleurons, rules) is `aria-hidden` at the call site and
 * the accessible name comes from the text beside it.
 */

/** The rail: places you can be. Each is a different kind of object. */
export const PLACE = {
  /** A thread of talk. */
  chat: "⌇",
  /** An asterism — the workspace's threads as a constellation. */
  map: "⁂",
  /** A ruled grid: saved openings. */
  prompts: "▦",
  /** A ruled page: the knowledge base. Was ⌘, the Mac Command key. */
  docs: "▤",
  /** A gathering. Was ♔, a chess king. */
  team: "⁙",
  /** The one convention-over-consistency exception (see above). */
  setup: "⚙",
  /** Search. */
  find: "⌕",
} as const;

/** Things you do. */
export const ACTION = {
  /** Split the thread here. Takes ⎇ — the branch mark — which used to label
   *  the map; Fork previously shared ⌇ with the rail's CHAT. */
  fork: "⎇",
  /** Record what came of an exploration. */
  verdict: "⚖",
  /** Escalate: the loop that returns to itself. */
  deep: "⟳",
  /** Steer a paused run. */
  steer: "⟂",
  /** The model searches before it speaks. Was ⚒, a mining hammer. */
  agent: "⌖",
  /** Say it to the room, not to the model. */
  note: "❝",
  edit: "✎",
  remove: "✕",
  confirm: "✓",
  stop: "◼",
  more: "⋯",
} as const;

/** Roles, as one hierarchy rather than three unrelated shapes: solid, hollow,
 *  empty. Owner was ♔ (chess) and collaborator was ⌇ (which also meant CHAT). */
export const ROLE_SIGIL = {
  owner: "◆",
  collaborator: "◇",
  observer: "○",
} as const;

/** States something can be in. */
export const STATE = {
  /** Someone is reading — including you watching a teammate's run. Replaces
   *  the 👁 emoji that was rendered into a live status string. */
  watching: "◉",
  /** The archive of finished runs, as a shelf of records. Was ☷, an I Ching
   *  trigram. */
  archive: "▥",
  /** A live, unresolved thing. */
  live: "●",
  /** A thread whose context another thread draws on. The double dagger is the
   *  page's own mark for "this refers elsewhere"; it replaced ⛓, which most
   *  platforms render as a colour emoji. */
  linked: "‡",
  /** A tool call held for approval. Was ⚿ (U+26BF, a squared key) — a mark
   *  from the emoji block that renders differently on every platform. */
  waiting: "⧗",
  /** A tool call the workspace's policy refused. */
  denied: "⊘",
  /** A tool call in flight. */
  running: "◌",
} as const;

/** Ornament. Never carries meaning, always `aria-hidden`.
 *  `leaf` closes a section; `bud` marks a smaller break inside one. The two
 *  fleurons were previously used interchangeably. */
export const ORNAMENT = {
  leaf: "❦",
  bud: "❧",
} as const;
