---
name: Helix
description: A shared, branchable AI workspace dressed as a scholarly manuscript — parchment, iron-gall ink, gilt rule, and a wax seal for the one action that matters.
colors:
  paper-0: "#efe8d4"
  paper: "#e6dcc2"
  paper-2: "#ded2b4"
  paper-3: "#d3c5a2"
  ink: "#241b12"
  ink-2: "#4b3d2a"
  ink-3: "#5d4e36"
  ink-faint: "#867351"
  rule: "rgba(36, 27, 18, 0.34)"
  rule-soft: "rgba(36, 27, 18, 0.2)"
  oxblood: "#8f3e13"
  cinnabar: "#b45f2a"
  gilt: "#9a7a2c"
  gilt-1: "#6b5316"
  gilt-2: "#c0992f"
  verde: "#46624c"
  violet: "#5d4796"
  ember: "#94500f"
  char: "#15110b"
  seal-from: "#a24f21"
  seal-to: "#8f3e13"
  seal-text: "#f4e9cf"
  seal-border: "#6e2f0d"
  on-accent: "#f4e9cf"
  on-gilt: "#1a1404"
  on-author: "#ffffff"
  on-char: "#ede3c8"
  accent-tint: "rgba(154, 122, 44, 0.16)"
  hover-tint: "rgba(36, 27, 18, 0.05)"
typography:
  brand:
    fontFamily: "Cinzel Decorative, Cinzel, serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.02em"
  display:
    fontFamily: "Cinzel, serif"
    fontSize: "clamp(38px, 6.4vw, 68px)"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Cinzel, serif"
    fontSize: "clamp(24px, 3.4vw, 36px)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "normal"
  title:
    fontFamily: "Cinzel, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "normal"
  body:
    fontFamily: "IM Fell English, Georgia, serif"
    fontSize: "15.5px"
    fontWeight: 400
    lineHeight: 1.62
    letterSpacing: "normal"
  instrument:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.005em"
  label:
    fontFamily: "Cinzel, serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.16em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  chip: "5px"
  md: "9px"
  lg: "13px"
  full: "50%"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.instrument}"
    rounded: "{rounded.md}"
    padding: "9px 15px"
  button-hover:
    backgroundColor: "{colors.paper-3}"
  button-primary:
    backgroundColor: "{colors.seal-to}"
    textColor: "{colors.seal-text}"
    typography: "{typography.instrument}"
    rounded: "{rounded.md}"
    padding: "9px 15px"
  button-gilt:
    backgroundColor: "transparent"
    textColor: "{colors.gilt-1}"
    typography: "{typography.instrument}"
    rounded: "{rounded.md}"
    padding: "9px 15px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.instrument}"
    rounded: "{rounded.md}"
    padding: "9px 15px"
  icon-act:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.chip}"
    padding: "0"
    width: "24px"
    height: "24px"
  input:
    backgroundColor: "{colors.paper-0}"
    textColor: "{colors.ink}"
    typography: "{typography.instrument}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
  chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-2}"
    typography: "{typography.mono}"
    rounded: "{rounded.chip}"
    padding: "2px 7px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "12px"
    padding: "17px 18px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-3}"
    rounded: "{rounded.md}"
    padding: "8px 0"
    width: "48px"
  nav-item-active:
    backgroundColor: "{colors.accent-tint}"
    textColor: "{colors.oxblood}"
  toast:
    backgroundColor: "{colors.char}"
    textColor: "{colors.on-char}"
    rounded: "{rounded.md}"
    padding: "10px 16px"
  dialog:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "22px 24px"
---

# Design System: Helix

## Overview

**Creative North Star: "The Scriptorium"**

Helix is a room where a team's thinking is written down and kept. The interface
takes that literally: the surface is parchment, the text is iron-gall ink, the
hairlines are ruled by hand, and the single action that commits something is
stamped in wax. It is a manuscript world drawn from bookmaking and astronomy —
the ruled page, the star chart, the orbital diagram — and explicitly not from
alchemy, hermeticism, or the occult. That line is a hard identity constraint,
not a stylistic preference.

The density is that of a working document rather than a marketing page. Panes
are opaque, bordered, and butt against one another; whitespace is generous
inside a pane and thin between them. Four fixed texture layers sit above the
panes so the whole surface reads as one continuous aged sheet instead of a stack
of cards — this is the reason the interface never looks like a generic dark-mode
SaaS shell despite having the same three-pane bones.

The system rejects the aesthetic it was first built in. The original direction
was a dark "Alchemical Noir"; it was replaced with light parchment, and dark was
re-admitted only as **Nocturne** — the same scriptorium after dark, in leather
and candlelight. Light is the default and the identity; dark is a courtesy.
Gold-on-cream was tried as the primary action fill and failed contrast, which is
why gilt survives as an outline and never as a fill behind text.

**Key Characteristics:**

- Parchment surfaces that darken outward, never a flat neutral gray
- One reading voice and one instrument voice, never mixed inside an element
- Gilt as line, oxblood as seal — the two accents do different jobs
- Depth from ruled borders and tonal layering, not from drop shadows
- Every text-on-fill pair measured, none hard-coded
- Motion in one easing voice with three beats, and reduced-motion keeps the
  information while removing the travel

## Colors

Warm, low-chroma, and entirely within one earth family — the accents are the
parchment's own pigments (seal wax, brass leaf, verdigris) rather than a
separate brand palette laid on top.

### Primary

- **Seal Russet** (`oxblood`): the wax seal. The single hero action on any
  surface, and the color of a link. Deliberately re-tempered out of true
  oxblood into the parchment's earth family so it belongs to the paper.
- **Kindled Cinnabar** (`cinnabar`): the focus color. Every focus ring and every
  input's focused border. Lives in the action family on purpose — violet is
  reserved and must not be borrowed for focus.

### Secondary

- **Brass Leaf** (`gilt`): illumination. Borders, hairline ornaments, the
  chapter rule, the workspace mark. Decorative weight.
- **Brass as Ink** (`gilt-1`): the same brass darkened until it can legally be
  text or a line — holds ≥4.5:1 on `paper` and `paper-2`.
- **Bright Brass** (`gilt-2`): highlight marks and gradient ends only. Never
  text.

### Tertiary

- **Verdigris** (`verde`): the "ready / healthy / within budget" signal.
- **Steer Violet** (`violet`): reserved, exclusively, for human intervention in
  a reasoning run — the steer affordance. Reserving one hue for the one moment a
  person interrupts the machine is what makes that moment legible.
- **Ember** (`ember`): warnings and cost pressure, short of failure.

### Neutral

- **Parchment ramp** (`paper-0` → `paper-3`): `paper-0` is the bright input
  well, and surfaces darken outward from it — the page you write on is the
  lightest thing on screen. `paper-3` carries the chrome (rail, topbar).
- **Iron-Gall Ink ramp** (`ink` → `ink-faint`): `ink` for body, `ink-2` for
  secondary, `ink-3` for the small-text floor. `ink-faint` is **decorative
  only** and is never information-bearing text.
- **Ruled hairlines** (`rule`, `rule-soft`): translucent ink, strong enough to
  survive the grain overlay above them.
- **Char** (`char`): the toast chip, dark in both themes.

### Named Rules

**The Measured Pair Rule.** Never hard-code a color for text that sits on a
filled accent. Use the `on-*` family (`on-accent`, `on-gilt`, `on-author`,
`on-char`). Only `on-accent` flips between themes, because only the accents
invert — cream on light oxblood measures 6.07:1 and is correct; the same cream
on Nocturne's lit oxblood measures 2.20:1 and is not.

**The Gilt-Is-A-Line Rule.** Brass is an outline, a hairline, or a mark. It is
never a fill behind text. This was tested: gold-on-cream failed contrast, and
the primary action became the wax seal instead.

**The Reserved Violet Rule.** Violet means a human steered a running system.
Nothing else may use it — not focus, not selection, not a decorative accent.

## Typography

**Display Font:** Cinzel (serif) — with Cinzel Decorative for the wordmark alone
**Body Font:** IM Fell English (with Georgia fallback)
**Instrument Font:** Inter (with system-ui fallback)
**Mono Font:** JetBrains Mono

**Character:** IM Fell English is a 17th-century book face with real irregularity
in the letterforms — it makes long AI output read as a document rather than a
chat log. Cinzel is Roman capital, quiet and inscriptional, so headings feel
carved rather than styled. Inter carries no period character at all, which is
exactly its job: the controls should disappear so the manuscript reads.

All four faces are self-hosted (`src/styles/fonts.css`, latin + latin-ext
subsets), because a self-hosted Helix must render its own typography offline and
must not make every visitor's browser call a third party on page load.

### Hierarchy

- **Brand** (Cinzel Decorative, 700, 22px): the Helix wordmark. Nowhere else.
- **Display** (Cinzel, 600, `clamp(38px, 6.4vw, 68px)`, 1.02): the landing hero,
  once per page.
- **Headline** (Cinzel, 600, `clamp(24px, 3.4vw, 36px)`, 1.1): section titles on
  the landing page.
- **Title** (Cinzel, 600, 20px, 1.1): dialog titles, empty-state titles, card
  headings. The conversation title runs 24px.
- **Body** (IM Fell English, 400, 15.5px, 1.62): message bodies and all prose.
  Rendered markdown holds the same 1.62.
- **Instrument** (Inter, 600, 13px): button labels, inputs, selects.
- **Label** (Cinzel, 600, 11px, 0.16em, uppercase): the `.eyebrow` — section
  kickers and small caps.
- **Mono** (JetBrains Mono, 400, 11px): ids, model names, chips, timestamps,
  rail labels, anything machine-shaped.

### The Declared Scale

`tokens.css` declares a six-step px ramp: `--t-micro` 12, `--t-meta` 14,
`--t-body` 16, `--t-card` 20, `--t-title` 26, `--t-hero` 42.

Be aware that the components have drifted off it. Real sizes in use include
9.5px (rail labels), 11px, 11.5px, 12.5px, 13px, 15px, 15.5px, 18px and 24px,
most of them set as literals rather than tokens. Each was chosen for a specific
surface and none is wrong on its own, but the ramp above no longer describes the
system it names. **New work should take a step from the ramp**; reconciling the
existing literals is open work, and worth doing in one pass rather than
opportunistically, because moving a size changes layout.

### Named Rules

**The Two Voices Rule.** IM Fell English is what Helix *says*; Inter is what
Helix *is operated by*. Prose, message bodies and epigraphs take the reading
voice. Buttons, inputs, selects and labels take the instrument voice. They are
never mixed inside one element. The one deliberate crossing: the composer
textarea opts back into the reading voice, because what you type there becomes
the document.

**The Mono-Means-Machine Rule.** JetBrains Mono marks values a human did not
write — ids, model names, token counts, branch names. If a person authored the
string, it is not mono.

## Layout

The app shell is a two-column grid: a fixed **68px rail** and a fluid main
column. Chat splits the main column three ways using golden-ratio pane widths —
`--pane-left: 248px` for threads, a fluid stage, and `--pane-right: 360px` for
the monitor.

Spacing runs on an 8px grid (`s1` 4px through `s7` 48px). Density is high in
chrome and low in reading surfaces: the rail packs to 6px gaps, message bodies
breathe at 1.62 line-height.

The main column requires `min-width: 0; min-height: 0; overflow: hidden` so it
can shrink below its content and hand scrolling to the inner panes. Without
that, the column grows unbounded and the root's `overflow: hidden` simply clips
it, so nothing scrolls at all.

**Responsive behavior.** The layout adapts by relocating, never by removing.
Below **1100px** the side panes become drawers rather than disappearing. At
**≤760px** the topbar wraps to multiple lines and the conversation title claims
a full line so its actions wrap beneath it. Content that cannot compress —
the role capability matrix, wide tables — scrolls inside its own container so
the page body never scrolls horizontally. Verified with no document-level
horizontal scroll at 1440 / 1280 / 1100 / 1024 / 900 / 760 / 560 / 390.

Note that small-screen support is **not** an established product requirement
(see PRODUCT.md); the commitment here is reachability of every control, not a
designed phone layout.

### Named Rules

**The Adaptation-Not-Subtraction Rule.** A control that does not fit gets moved,
wrapped, or put behind a drawer. It is never dropped. A pane that clips rather
than scrolls will hide a control while still reporting it as laid out — that
failure is invisible to code review and only shows up in a browser.

## Elevation & Depth

**This system is border-first, not shadow-first.** Depth comes from tonal
layering (the parchment ramp darkening outward) and ruled hairlines. Panes sit
flat against each other and are separated by a 1px `rule`, the way a ruled page
divides columns. A surface at rest almost never casts a shadow.

Shadows appear in exactly three situations: something floats above the page
(dialog, toast, floating toggle), something is being lifted by the pointer
(card hover), or something is pressed inward (the seal button's active state).

### Shadow Vocabulary

- **Card at rest** (`0 1px 3px rgba(36, 27, 18, 0.06)`): barely there; enough to
  lift a card off the parchment without implying it floats.
- **Card lifted** (`0 4px 14px rgba(36, 27, 18, 0.1)`): the hover response.
- **Seal** (`inset 0 1px 0 rgba(255, 240, 215, 0.16), 0 2px 9px rgba(143, 62, 19, 0.3)`):
  the primary button. An inner highlight plus a warm-tinted cast, so the wax
  reads as a raised material rather than a colored rectangle.
- **Seal pressed** (`inset 0 2px 5px rgba(80, 20, 12, 0.4)`): the fill inverts
  to an inset — the seal takes the impression.
- **Overlay** (`0 24px 70px rgba(21, 17, 11, 0.4)` dialog, `0 8px 28px rgba(0, 0, 0, 0.35)` toast):
  the only genuinely large shadows in the system.

### The Texture Stack

Three fixed, `pointer-events: none` layers sit **above** the opaque panes and
below modals — a drifting grain (z-index 6), a vignette (5), and a warm wash
(4). They are what make the interface read as one continuous sheet.

### Named Rules

**The No-Blend Rule.** The grain layer carries no `mix-blend-mode`. A
full-viewport blended layer recomposites against its backdrop on every frame
anything beneath it paints, which in a streaming interface is every frame.
Measured on the production build during a stream: with the blend, 70 of 82
frames arrived at a 33ms p95; without it, 82 of 82 at 16.7ms. At 7% opacity the
two are visually indistinguishable in both themes.

**The Flat-At-Rest Rule.** If you are reaching for a shadow to separate two
surfaces, use a `rule` hairline or the next step on the parchment ramp instead.

## Shapes

Corners are softly rounded and consistent: **9px** (`--radius`) is the default
for buttons, inputs, and rail items; **13px** (`--radius-lg`) for dialogs; 12px
for cards; **5px** for chips and small marks; full circles for round instruments
(the theme toggle, avatars, presence dots).

Borders are the primary structural device. Nearly every surface carries a 1px
`rule` or `rule-soft` edge. The form language is rectangular and ruled — this is
a page with columns drawn on it, not a card deck.

The one recurring non-rectangular motif is **orbital**: concentric rings and arcs
(the spinner, the workspace mark, the branch topology, the geometric watermark
behind an empty stage). It is astronomical, from star charts and armillary
spheres. Corner brackets on dialogs were tried and removed — they fought the
border radius and read as stray marks.

## Components

### Buttons

- **Shape:** softly rounded (9px), 1px bordered, 9px 15px padding, instrument
  voice at 600 weight
- **Default:** parchment fill on a `rule` border; hover darkens one step on the
  ramp and the border firms to `ink-faint`
- **Primary (the seal):** a vertical gradient from `seal-from` to `seal-to` with
  a `seal-border` edge and `seal-text` label, weight 700. Hover brightens by
  12%; active swaps the cast shadow for an inset. Its light end is a shade under
  `oxblood-2` specifically because the gradient's light end is what the label
  actually sits on. **One per surface.**
- **Gilt:** transparent with a brass border and `gilt-1` text — secondary
  emphasis, an outline by doctrine
- **Oxblood:** a 10% russet wash with a russet border — a destructive or
  cautionary action that is not the hero
- **Ghost:** transparent on `rule-soft`, `ink-2` text — tertiary
- **Press:** every button translates 1px down on `:active`. Disabled drops to
  0.45 opacity.

### Icon Actions

The `.icon-act` utility. A small glyph (11.5–13px) with a hit area that is never
small: `min-width` and `min-height` of 24px, centered, zero padding. The
component keeps only color and reveal behavior; the utility owns the target.

Use it for a **bare glyph**, where growing the box is invisible because there is
no background or border to grow. Do not apply it to a chip-shaped button — those
carry a visible border, so padding them to 24px tall changes the design. Chip
buttons clear WCAG 2.2 SC 2.5.8 on its **spacing** exception instead: at roughly
60×18 in well-separated rows, a 24px circle centred on each one touches nothing
else. `e2e/responsive.mjs` tests the criterion including that exception, so it
tells the two cases apart rather than reporting every small control.

### Chips

- **Style:** parchment fill, `rule` border, 5px radius, 2px 7px padding, mono at
  11px, `ink-2` text
- **Use:** citations, model ids, branch names, counts — machine-shaped metadata
  attached to prose

### Cards / Containers

- **Corner Style:** 12px
- **Background:** `paper` on `rule`
- **Shadow Strategy:** resting whisper, hover lift (see Elevation)
- **Internal Padding:** 17px 18px
- **Entrance:** `hx-rise` over 0.45s on the shared easing

### Inputs / Fields

- **Style:** `paper-0` — the brightest surface in the system — on a `rule`
  border, 9px radius, 12px 14px padding, full width
- **Focus:** border shifts to `cinnabar` plus a 3px translucent cinnabar ring
- **Placeholders:** `ink-3` italic. They hold the small-text contrast floor
  because several carry real instruction; the italic does the "this is a hint"
  work, not a lighter color.
- **Search wells:** the vertical padding lives on the input, not the well, so the
  field's hit area is the full height of what looks clickable
- **Container:** `.field` carries `min-width: 0` so it can shrink inside a narrow
  grid track. An input's intrinsic width (~200px) will otherwise hold a track
  open and push the control off a card that clips.

### Navigation

The rail is a 68px column of stacked glyph-over-label items in mono at 9.5px
with 0.08em tracking. Active items turn `oxblood`. The active highlight is a
**single element that slides between items** rather than a class toggled on each
— a layout animation, so the highlight travels. The rail is a `<nav>` landmark
with an accessible name, and the active item carries `aria-current`.

At phone widths the rail keeps every destination — nothing moves into a hamburger
— and gives the stage back its gutter instead.

### Author Swatches

The one place color is chosen by code rather than by a token. Each teammate gets
a deterministic avatar fill hashed from their id, drawn from a six-entry palette
in `lib/format.ts`. It has to be a JS array because the choice is an index into
a list, which a CSS custom property cannot express.

Every entry carries a white initial, so every entry is measured against
`on-author`: `#8a6d26` 4.89, `#46624c` 6.75, `#6e5aa8` 5.69, `#9a6b4b` 4.59,
`#8c2b1e` 8.47, `#a85a19` 5.07. Two candidates that failed (`#9a7a2c` at 4.04
and `#c5752a` at 3.53) were darkened a step rather than dropped, so the palette
stays inside the manuscript's earth family. **A new swatch must be measured
against `on-author` before it is added** — a teammate should not get an
unreadable avatar because of how their email happens to hash.

### The Chapter Rule

A hairline ornament under page titles: two gradient rules fading out from a
centered brass fleuron. It is the system's signature mark of "a new section
begins here" and appears on route headers.

### Motion

One easing voice, `--ease-quill` (`cubic-bezier(0.22, 0.61, 0.21, 1)`) — the
quill lands, then settles. Three beats: **140ms** for hover and press, **260ms**
for an element entering, **480ms** for a page turn. Long ambient motions (grain
drift at 9s, ring precession) define their own durations.

Routes enter with `.folio` — a page being turned, one shared beat for every
route.

### Named Rules

**The Reduced-Motion Keeps-The-Information Rule.** `prefers-reduced-motion` asks
for no vestibular load; it does not ask for an interface that stops telling you
when something changed. Animations here are ambient (grain, precession,
breathing, entrances) and are stopped — with `hx-rise` redefined as a pure fade
so anything mid-flight resolves visible rather than blank. Transitions are
feedback (the rail pill settling, a composer frame warming, a meter falling) and
are shortened to 90ms rather than deleted. A spinner is the explicit exception:
a loading indicator that has stopped moving reads as hung, so it is given an
opacity alternative instead of being switched off.

## Do's and Don'ts

### Do:

- **Do** use the `on-*` token family for any text sitting on a filled accent, and
  measure a new pair before shipping it.
- **Do** keep gilt as an outline, a hairline, or a mark.
- **Do** reach for a `rule` hairline or the next step on the parchment ramp when
  you need to separate two surfaces.
- **Do** give every bare-glyph control the `.icon-act` utility so its target
  reaches 24×24 regardless of glyph size. A chip-shaped button keeps its size and
  passes SC 2.5.8 on spacing instead — check with `e2e/responsive.mjs` rather
  than padding it.
- **Do** put `min-width: 0` on any flex or grid child that contains an input or
  long unbroken text.
- **Do** make content that cannot compress scroll inside its own container.
- **Do** shorten transitions under `prefers-reduced-motion`; stop animations
  entirely.
- **Do** keep the seal to one primary action per surface.

### Don't:

- **Don't** use occult, alchemical, or hermetic motifs. The manuscript vocabulary
  is bookmaking and astronomy — ruled pages, star charts, orbital diagrams. This
  is a binding identity constraint, not a preference.
- **Don't** hard-code a hex value in a component or route stylesheet. Every color
  comes from a token; there are currently zero raw hex values in any CSS outside
  `tokens.css`. The single exception is the author swatch palette in
  `lib/format.ts`, which is documented below and has to be a JS array.
- **Don't** use `ink-faint` for text a user needs to read. It is ≥3.0:1 and
  decorative by definition.
- **Don't** use `gilt-2` for text, and don't put text on a gilt fill outside the
  `on-gilt` pair.
- **Don't** borrow violet for anything but human intervention in a running
  reasoning process.
- **Don't** add `mix-blend-mode` to a full-viewport layer.
- **Don't** mix the reading voice and the instrument voice inside one element.
- **Don't** remove a control to make a narrow layout fit. Move it, wrap it, or
  drawer it.
- **Don't** treat the dark theme as the identity. Light parchment is the default
  and the presentation surface; Nocturne is an opt-in courtesy.
