# The Model page — design brief

Written 2026-09-10 for the designer doing the element-by-element mockup pass.
Theme is being decided separately, so this brief is theme-agnostic: structure,
hierarchy, interaction, copy and states only. No colours, no type sizes, no
radii. Where a component already exists in `engine/ui.py` it is named so the
mockup and the build agree.

Inputs: `design/model/UX_RESEARCH.md` (patterns, persistence, placement — 2026-09-10),
`design/model/library.yaml` + `LIBRARY_NOTES.md` (78 verified sources — 2026-09-10),
`design/plan/platform.md` (data rights, pushes, hosting), and the engine as it
stands (`engine/sources_ui.py`, `engine/sources_page.py`, `engine/consensus.py`,
`engine/performance.py`, `engine/ui.py`, `data/sources.yaml`). External claims
are cited through the research reports; anything not verified there is marked
**[unverified]** here too.

---

## 0. The decisions on one card

| Decision | Choice | Why (short) |
|---|---|---|
| Tab label | **Model** — replaces the Ledger tab, fifth of five | Apple caps tabs at five; the digest's signature section is already "YOUR MODEL"; `sources.html` has no tab today |
| Page title | **Your model** | The chips already say "Your model says START – 71%"; the Monday push says "Your model went 4-for-5" |
| The set of enabled voices | **your room** | `consensus.py`'s own word ("weigh every voice in the room"); "the room's split" is product vocabulary |
| Weights | relative 0–100, normalised, **share shown**; cap **8** voices, floor **1**; **Apply**, never auto-save | What the owner's panel already does; FFA is the only fantasy precedent; M1's sum-to-100 is wrong for opinions |
| Library | a **directory** of 78 real sources: name, link, metadata, ledger line; vertical lists; one search box that accepts a URL | Data-rights plan: link-only by default; nothing scraped |
| Suggest | link first, four states, reviewed Tuesdays, public list | Pocket Casts + Canny, minimum honest loop |
| Persistence | preview live → Apply → this page uses it now (A) → digest and pushes honour it once saving is on (B) | Research §6: hybrid, A now, B before the first stranger |
| Data rights | link-only creator = name, face with permission, link, ledger line; **no quotes until signed** | `platform.md`, decision 5 |
| Voice | the app speaks in **second person** ("your model"); controls are **bare verbs** ("Apply", "Add", "Share"); the word "my" appears nowhere | One voice on one screen |

---

## 1. Purpose, name, placement

### Purpose

The Model page is where a reader chooses which voices decide their lineup
verdicts and how much each one counts, and sees on the same screen whether
those voices have earned it. It turns "your model" from a phrase the chips
use into a thing the reader built and can check.

### Name — argued

Four candidates were on the table. The page needs two names anyway: a
one-word tab label and a page title, and the argument resolves once you
separate them.

- **"Sources"** — the owner's word and today's page name. It names the
  *inputs*. A reader does not own sources; they own a model. Keep "Sources"
  as the noun inside the page ("Your sources", "Suggest a source") and as
  nothing bigger.
- **"The Room"** — the engine's metaphor (`engine/consensus.py`: "weigh every
  voice in the room"; the digest's Room section). It is the best word for
  the *set* of enabled voices and it survives in copy: "5 voices in your
  room", "the room's split". On a tab bar next to Home / Lineup / Board it
  tells a stranger nothing. Rejected as the page name.
- **"My Model"** — first person. The app never speaks in the reader's first
  person: every chip says "Your model says", every Monday push says "Your
  model went 4-for-5". A "My Model" tab under a "Your model says" chip is two
  voices on one screen. Rejected, and the rule generalises: **no "my"
  anywhere** — the research's "Adjust my model →" becomes "Adjust your model →".
- **"Your Model"** — the product's own phrase, already load-bearing in the
  chips, the digest heading ("YOUR MODEL — source agreement matrix",
  `engine/digest.py`) and the board column. Right for the page title. Too
  long and too second-person for a tab label.

**So: the tab is "Model"; the page title is "Your model"; the enabled set is
"your room."** Tab labels are nouns (Home, Lineup, Board); the shell header
already carries context (`MODEL · WK 2`); the H1 says it in the app's voice.

### Placement — tab, not gear

Per `UX_RESEARCH.md` §7:

- Not a sixth tab: Apple's guidance is three to five; SwiftUI spawns a
  "More" tab past five **[HIG quoted via mirror, unverified against the live
  page]**.
- Not under the gear: settings are for rarely-changed, whole-app options;
  weights are task-specific and change weekly.
- Not Board or Trade Desk: each has content no other page carries.
- **The Ledger tab becomes Model.** Its page (the Tuesday digest) is a
  composition of the other tabs, and its one unique section is the model's
  agreement matrix. The digest keeps rendering; the Tuesday push deep-links
  to it; Home gains a "This week's brief" card. iOS: `Destination.ledger` →
  `.model`, title "Model", symbol `slider.horizontal.3`, path prefix
  `model`. (Engineering note, not a design task.)

**Two more entry points the designer must draw:**

1. **"Adjust your model →"** — the last line of the split popover behind every
   verdict chip everywhere (lineup, board, digest). Deep-links to this page
   with the dissenting voice's row scrolled into view and highlighted.
2. **First run — "Pick your voices"** — the page's own first-run state (§3),
   reached from the Home card "Build your model →" after a league is
   connected. Not a separate native screen.

The gear keeps what it has (link, notifications, saved copies, about) and
gains nothing.

---

## 2. The page, top to bottom

Everything below is one scrolling page. Width reference 390 pt; must hold at
375 and 430. Shell header and five-tab bar are the existing ones and are
hidden inside the native app (`docs/APP_MODE.md`).

```
┌──────────────────────────────────────┐
│ MODEL                          WK 2  │  shell header (existing)
├──────────────────────────────────────┤
│ Your model                           │  H1
│ 5 voices in your room · applied Tue  │  population line
│ [▇▇▇▇▇▇▇|▇▇▇▇▇▇▇|▇▇▇▇▇▇|▇▇▇|▇▇▇]     │  share bar, a face on each wide segment
│ Engine 28% · ESPN 28% · Sharp or     │  the honesty sentence (wraps, max 2 lines)
│ Square 24% · Chen 10% · House 10%    │
│ Went 4-for-5 on your roster this     │  blend accuracy line
│ week · 63% over 41 graded calls      │
│ ⓘ Saved. This page uses your model   │  persistence line (§4)
│   now; Tuesday's digest will too.    │
├──────────────────────────────────────┤
│ YOUR SOURCES              5 of 8 ▸   │  section_header + count note
│ ◉ War Room Engine            28%     │  row line 1: face · name/type/for · share
│   Projections · lineup verdicts  STEADY 63% n41
│   [on] ═══════════●══════════ wt 17  │  row line 2: switch · slider · readout
│ ◉ ESPN Projections           28%     │
│   ...                                │
│ ○ Boris Chen Tiers      off · wt 11  │  ghost row (off), grouped at the bottom
│ Weights are relative — they          │  normalisation note
│ normalise. Only each voice's share   │
│ of the total reaches a verdict.      │
│ ▸ More: presets · reset · share      │  disclosure (§2.5)
├──────────────────────────────────────┤
│ THE LIBRARY          78 · 48 graded  │
│ [🔍 Search, or paste a link        ] │  one box: name, URL, @handle, model link
│ [ For you | Most followed | New | All ]  segmented (existing, 4 max)
│ ◧ The Fantasy Footballers   [ Add ]  │  card: face 36 · name · type · for
│   Weekdays · Free · Link-only · NO-DATA
│ ◧ Stealing Signals          [ Add ]  │
│ ◧ Sleeper Projections   Needs a deal │  unavailable: reason replaces Add
│ Podcasts · YouTube · Newsletters ·   │  category chips (wrap; "All" only)
│ Analysts · Projections · News        │
│ Not here? ▾ Suggest a source         │
├──────────────────────────────────────┤
│ SUGGEST A SOURCE                     │
│ [ Link or @handle                  ] │
│ [ Suggest ]  Reviewed Tuesdays.      │
│ SUGGESTED BY READERS            12   │
│ #A1F3 Fantasy Footballers  Reviewing │
│ #9C02 Underdog rankings    Added ✓   │
│ #7B10 (a tipster)  Declined — no     │
│       public record we can grade     │
├──────────────────────────────────────┤
│ RECEIPTS       8 graded · archive 60%│  existing cards, collapsed
│ ▸ Your model     4-for-5 · 63% n41   │  row one (FFA "Current Setting")
│ ▸ War Room Engine  STEADY 63% n41    │
│ ▸ Sharp or Square  NO-DATA           │
└──────────────────────────────────────┘
│ [ Discard ]   [ Apply 2 changes ]    │  sticky footer, only when dirty
│ ● Home ≡ Lineup ▦ Board ⚖ Model ⇄ Trade │  tab bar (existing)
```

### 2.0 Header and title

- Shell header as today: wordmark, league switcher, `WK n`, theme toggle,
  gear. Nothing new.
- H1 **"Your model"**. No subtitle; the population line does that job.

### 2.1 At a glance — your room

One block, five lines, no card chrome around it (it is the page's masthead).

| Element | Content | Copy | Notes |
|---|---|---|---|
| Population line | count of enabled voices + when the model last took effect | "5 voices in your room · applied Tue 7am" | FantasyPros' "Consensus of 181 Experts" sentence. Variants in §4. |
| Share bar | one horizontal bar, one segment per enabled voice, width = share; a face (`ui.avatar`, ~20 px) sits on any segment ≥ 44 pt wide; narrower segments carry no face | — | Order = weight desc, ties by name. Live: updates on every drag before Apply. Never a legend of its own — the sentence below is the legend. |
| Honesty sentence | every enabled voice with its share, separated by " · " | "Engine 28% · ESPN 28% · Sharp or Square 24% · Chen 10% · House 10%" | Wraps to two lines max; beyond that "· +2 more" and the rest are in the rows anyway. Names use a short form (`short_name`, to be added to the library; registry name trimmed otherwise). Shares are rounded to whole numbers and may sum to 99 or 101 — never force them. |
| Blend accuracy line | how the reader's blend has graded, in the ledger's words | graded: "Went 4-for-5 on your roster this week · 63% over 41 graded calls" · thin: "58% over 12 graded calls — needs 30 before it can be called hot or cold" · none: "Not graded yet — grading starts after Week 1's games" | Tapping scrolls to the "Your model" receipt (§2.6). This line is only truthful for the *reader's* weights if the page ships per-call outcomes for the browser to re-grade (research §6 A.4); if it does not, it must say "House model went 4-for-5" — see §4. |
| Persistence line | which world the current weights live in | see §4 table | Always present. Never blank. |

### 2.2 Your sources

`section_header("Your sources", count_note="5 of 8")` — the count note is the
cap made visible. When at the cap: "8 of 8 · room is full".

**Row anatomy — two lines, three columns each, 44 pt face.** This is the one
component that must be drawn carefully (see §5 for the grid).

Line 1: `[face 44] [name / type · what-for] [share]`

- **Face**: `ui.nameplate` avatar at 44 px; initials monogram when no
  avatar; creators without face permission wear initials by design.
- **Name**: single line, ellipsised. Under it, one line: type tag
  (`Projections` · `Podcast` · `YouTube` · `Newsletter` · `Analyst` · `House`)
  then " · " then `what_for` from the library, ellipsised.
- **Share**: the big number. "28%". Under it, the **accuracy line** in the
  ledger's own vocabulary (`engine/performance.STATES`):
  - `HOT 71% · n38` / `COLD 44% · n35` — HOT/COLD use `ui.streak_badge`
  - `STEADY 63% · n41`
  - `LOW-CONFIDENCE 58% · n12` (title: "needs 30 graded calls")
  - `NO-DATA · starts week 1`
  Tapping the accuracy line scrolls to that source's receipt.
- A small **consent tag** after the type for creators: `Link-only` or
  `Licensed`. Feeds carry none.

Line 2: `[switch 44] [slider] [wt 17]`

- **Switch**: on/off. Off = weight 0 in the maths, weight *remembered* for
  turning back on. The last enabled voice cannot be switched off (floor of
  one): the switch stays on and a one-line note appears, "Your model needs
  at least one voice — turn another on first."
- **Slider**: 0–100, step 1, full width of the middle column, thumb usable
  with a thumb (§5). Dragging updates the share bar, this row's share, every
  other row's share and the honesty sentence live. Nothing is saved.
- **Readout**: "wt 17" — the raw relative weight (the nameplate already
  prints "wt 17"). Tapping it opens a numeric field for an exact value;
  Enter or blur commits to the slider. This replaces the owner's paired
  number box, which invites the keyboard on every row.

**Tap the row (line 1) → the source sheet** (§2.8). Long-press does nothing.

**Ghost rows.** Off sources render at reduced emphasis, grouped at the
bottom under a hairline with the label "Off · 2". Their line 2 shows the
switch and "off · wt 11 kept" instead of a slider. They still count against
nothing: the cap of eight is on *enabled* voices.

**Order**: enabled by weight desc; ties by name; then the ghost group. Order
changes only on Apply, never mid-drag (rows that jump under the thumb are a
classic phone bug).

**Under the list**, one line, always: "Weights are relative — they
normalise. Only each voice's share of the total reaches a verdict."

**Then the disclosure** "More: presets · reset · share" (§2.5).

### 2.3 The library

`section_header("The library", count_note="78 sources · 48 gradeable")`.
Right under the header, one sentence that is the data-rights contract in
plain English: "Every voice here is link-only unless marked Licensed: we
list the name, the link, and how their public calls graded. Nobody's words
are reproduced without their say-so."

**Search box** — one field, full width, 44 pt tall, placeholder "Search, or
paste a link". It accepts:

- a name fragment → filters the list below live;
- a URL or @handle (podcast RSS, Apple/Spotify page, YouTube channel,
  Substack, outlet page) → if it resolves to a library entry, that card is
  shown alone with "Already in the library"; if not, the box hands the
  link to **Suggest a source** with the field pre-filled and the page
  scrolls there;
- a Graded Takes model link (§2.5) → opens the "Use this model?" sheet.

**Segmented control** (`ui.segmented`, four segments, 44 pt): **For you ·
Most followed · New · All**.

- *For you*: library entries not in the reader's model with
  `suggested_default_weight ≥ 10`, ordered by ledger hit rate (graded
  first), then reach. Each card carries its one-line `weight_reason` as the
  blurb (Substack's "why I recommend this" moment).
- *Most followed*: ordered by reach (subscribers / stated readers from the
  library). It is labelled "Most followed", not "Popular", until reader
  counts exist and clear a privacy threshold (§6, open question 3).
- *New*: entries whose `added_on` is within 30 days. (The YAML has
  `verified_on` only today; `added_on` is a one-field addition.)
- *All*: the whole directory, with the **category chips** shown only here:
  Podcasts · YouTube · Newsletters · Analysts · Projections & data · News.
  Chips wrap onto two lines; they never scroll sideways.

Default segment: *For you* when the reader has fewer than three voices,
*All* otherwise, and *All* whenever the search box has text.

**Lists are vertical.** No horizontal rails. Each segment shows its first
six cards and a "Show 12 more" control; *All* shows everything, grouped by
category with a sticky-free group heading (six headings, no sticky).

**Library card** — one line plus one line, 36 pt face, three columns:

`[face 36] [name / type · what-for] [Add]`
`          [cadence · free/paid · consent · ledger]`

- Name ellipsised; type and `what_for` on the second line of the middle
  column, ellipsised.
- Meta line, in this order, separated by " · ": cadence ("Weekdays
  in-season"), price (`Free` · `Freemium` · `Paid`), consent (`Link-only` ·
  `Licensed`), ledger (`Graded 41 · 63%` or `NO-DATA`). Flags render as
  plain words appended: `Moved to Audacy Aug 2026` · `Hosts changed` ·
  `Quiet since 13 Mar` · `Unverified` — never as icons alone.
- **Add** (44 pt, right column) stages the source into Your sources at the
  library's `suggested_default_weight`, switched on. The card flips to
  "In your model · edit ↑" (tapping scrolls to the row), the new row
  appears at the top of Your sources with its slider focused and a one-line
  note under it: "Added at weight 12 — adjust if you like." The Apply footer
  appears. Nothing is saved until Apply.
- **Unavailable**: when a source cannot be added, the reason sits where Add
  would be, in words, and the card body still opens the sheet:
  - `Paid only — nothing public to grade` (`free_or_paid: paid`)
  - `No feed — link only` (no machine path; can be opened, not graded)
  - `Needs a deal` (`public_status: needs-deal` — "available once
    [Sleeper] says yes" in the sheet)
  - `Not in the public app` (`cannot-use-publicly`: ESPN, Chen — the
    owner's copy still shows them enabled; a stranger's copy shows this)
  - `Informs, doesn't vote` (news wires, default weight 0 — "Open" replaces
    Add)
  - `Room is full` (eight enabled — "remove one first" in the sheet)
  - A dormant or feed-down source is **still addable**; its card says
    "Quiet since 13 Mar — it won't vote until it speaks."
- Tap the card body → the source sheet (§2.8).

**Footer of the library**: "Not here? Suggest a source ▾" — an anchor to §2.4.

### 2.4 Suggest a source, and Suggested by readers

`section_header("Suggest a source")`. One field, one button, one sentence.

- **Link or @handle** — required. Placeholder "Podcast feed, Apple or
  Spotify page, YouTube @handle, newsletter, or an analyst's page".
- **Suggest** — 44 pt button beside or below the field (below at 375).
- Sentence under it, always visible: "Reviewed Tuesdays. Everything
  suggested shows in the list below with its status."

**On Suggest** the box expands in place (no new page):

1. "Reading the link…" (≤ 2 s expected).
2. Resolved: a preview card in the library-card shape — face (or initials),
   the name we read, the type we guessed as a dropdown (Podcast · YouTube ·
   Newsletter · Analyst · Projections & data · Other) — plus **Name**
   (pre-filled, editable, "fix it if we read it wrong") and **Why**
   (optional, 140 characters, counter shown). Button: **Send**.
3. Receipt, inline: "Got it — **#A1F3**, Received. We review on Tuesdays."
   The same id appears at the top of the list below immediately.

Failure copy (inline, under the field, field keeps its text):

- Unresolvable: "We couldn't read that as a source. Try the show's RSS, its
  Apple Podcasts page, or the channel's @handle."
- Duplicate: "Already in the library — add it to your model?" with the
  library card (and its Add) rendered inline.
- Rate limit: "You have 5 open suggestions — we'll review those first."

**Suggested by readers** — `section_header("Suggested by readers",
count_note="12")`, directly beneath the box. One row per suggestion, newest
first, three columns:

`[#id] [name / type] [status]`

- Status words, exactly four: **Received** · **Reviewing** · **Added ✓** ·
  **Declined — reason**. The reason is one of the pre-written set: "no
  public record we can grade" · "paywalled — nothing to link" · "not fantasy
  football" · "duplicate of [name]". A decline never says "low quality".
- "Added ✓" rows link to the library card.
- The reader's own suggestions carry a small "yours" mark; nobody else's
  name is shown (suggestions are attributable to the house via the token,
  not to other readers).
- Rows older than 30 days collapse under "Older · 7 ▸".
- The Monday ledger push carries one line when the reader's item changes
  state ("Your suggestion #A1F3 was added to the library"). No new push
  type; the weekly cap of three stands.

The owner reviews the same list from the YAML queue
(`data/library_suggestions.yaml`, `LIBRARY_NOTES.md` maintenance rhythm) —
that review surface is not on this page.

### 2.5 Advanced — the disclosure under Your sources

A single `<details>` row, 44 pt, summary "More: presets · reset · share".
Open, it shows four rows:

1. **Presets** → the Presets sheet. Four named sets, each drawn as faces +
   shares + one line:
   - **House model** — "The engine plus the voices the house grades."
     (the owner's public registry, weights as published)
   - **Engine only** — "One voice: the projections and lineup maths."
   - **Graded voices only** — "Everything with 30+ graded calls, weighted by
     hit rate." Disabled before any source reaches 30: "Available once a
     voice has 30 graded calls — about week 6."
   - **Best three + engine** — same gate, same disabled copy.
   Choosing a preset *stages* the change (rows update, footer appears).
   "Use this preset" is the sheet's only button.
2. **Reset to the house model** → a confirm sheet: "This replaces your 5
   voices and weights with the house model. Nothing changes until you
   Apply." Buttons: "Reset" / "Keep mine".
3. **Share your model** → copies a link that carries the weights, not the
   leagues or any page: `…/model.html#m=engine:17,sharp-or-square:8,…`.
   Sheet copy: "Copied. Anyone with a Graded Takes link can open it and use
   your weights. It carries your voices and weights — nothing about your
   leagues." Opening such a link (from the search box or directly) shows
   **"Use [first name]'s model?"** with faces + shares and one button, "Use
   this model", which stages it. Sources the recipient cannot use are listed
   under the faces: "ESPN Projections isn't available in your copy — skipped."
   This is the "subscribe to a formula" idea at its smallest: a static
   snapshot, not a live follow (§6).
4. **Normalisation**, restated once more for the curious, with the arithmetic:
   "share = weight ÷ sum of enabled weights. The engine's `consensus.py`
   applies exactly this."

The **data-rights honesty** is not a row here; it lives where it applies —
the library header sentence (§2.3), the consent tag on every creator row and
card, and the footnote on every creator sheet (§2.8).

### 2.6 Receipts

The existing `sources_page.py` cards, folded into this page, with three
changes:

1. Section header "Receipts" with the decay strip's current step in the
   count note ("8 graded · 2025 archive at 60%"); the decay strip itself
   sits inside the section as today.
2. **"Your model" is row one** — the reader's blend graded like a source:
   "4-for-5 this week · 63% over 41 graded calls · STEADY" with the same
   sparkline. NO-DATA when nothing is graded. This is FFA's "Current
   Setting" bar.
3. Cards are **collapsed** by default: summary = nameplate · headline ·
   state; expanding reveals the sparkline, per-position split and
   provenance line exactly as today. Enabled first by weight, then the
   quiet (off) cards, as today.

The accuracy line on every Your-sources row and the blend line at the top
both deep-link here (`#src-<id>`).

### 2.7 The sticky footer

Appears only when the page is dirty (any un-applied change); sits above the
tab bar; two controls, 44 pt each:

- **Discard** (secondary) — reverts every staged change; no confirm if the
  changes are under a minute old, confirm otherwise ("Discard 3 changes?").
- **Apply 2 changes** (primary) — the count is live: a weight drag, a
  switch, an add, a remove, a preset each count once per source.

After Apply, the footer becomes a one-line toast for four seconds with the
state copy from §4, then disappears.

### 2.8 Sheets

All sheets are `ui.sheet()` — a `<dialog>` bottom sheet under 700 px with the
`<details>` fallback.

**Source sheet** (from any row or card):

- Head: face 44, name, type tag, consent tag, outlet/network, hosts if the
  library lists them.
- `what_for` in full; cadence; price; the link as a visible domain
  ("thefantasyfootballers.com").
- **Ledger line**: state · hit rate · n · streak · sparkline (`ui.sparkline`)
  · provenance ("live 2026 calls" / "reconstructed 2025 archive, decaying").
  NO-DATA states the reason in `CREATOR_REASON`'s words: "no history — starts
  accumulating week 1. Nothing this source said in 2025 was ever recorded."
- Flags as sentences: "Left NBC for Audacy on 3 Aug 2026." "Hosts changed
  in July 2026; the feed's own credits are stale." "Last episode 13 Mar
  2026." "Some details unverified — see the note."
- "In 3 readers' models" — only when the privacy threshold is met (§6 Q3);
  otherwise omitted, never "in 0".
- Buttons: **Add to your model** / **Remove from your model** (removing
  returns it to the library and stages the change) and **Open link**
  (external, opens the outlet).
- **Footnote, creators only.** Link-only: "Link-only. We use this source's
  public titles and link — never their words — until they sign. Quotes
  appear only with permission." Licensed: "Licensed. Quotes and calls appear
  with the creator's permission." Feeds: none.

**Presets sheet**, **Reset confirm**, **Share sheet**, **Use this model?
sheet** — as described in §2.5.

**First-run sheet — "Pick your voices"** — see §3.

---

## 3. States, element by element

Every element below must be drawn in every state listed. "Copy" is verbatim.

### 3.1 Whole page

| State | What shows | Copy |
|---|---|---|
| **First run** (no model applied yet, after a league is connected) | The page renders with the **house model** staged but not applied, and a sheet opens: "Pick your voices" — the starter faces with shares, one paragraph, two buttons. Behind it, the library is set to *For you*. | Sheet: "Start with the house model — the engine plus the voices the house grades — or pick your own from the library. You can change any of it, any time." Buttons: **Use the house model** (applies, closes) · **Pick your own** (closes, scrolls to the library, footer shows once anything is added). |
| **Empty** (reader switched or removed everything but the engine) | Your sources shows the engine alone; a quiet line under it. | "One voice. Add more from the library below — a room of one is just the engine." |
| **Loading** | Static page: nothing loads but fonts. The one client-side step (reading applied weights, recomputing shares) is synchronous and instant. If the page arrives with baked server weights *and* the browser holds newer un-applied drafts, a banner shows above Your sources. | Banner: "You have 2 unapplied changes from Tuesday." Buttons: **Apply** · **Discard**. |
| **Offline** (iOS app serving its saved copy, or a browser with no network) | Everything on the page works except sending a suggestion and, in B, saving. A one-line notice at the top of the page. | "Offline — showing your saved copy from Tue 7:02am." Apply (B): "Offline — kept on this phone; saves when you're back." Suggest: field disabled, "Suggestions need a connection." |
| **Owner's copy vs a stranger's copy** | Same page. The owner sees ESPN / Chen as enabled feeds; a stranger's copy lists them in the library as `Not in the public app`. | — |
| **Degraded render** (the ledger or registry failed at render time) | The existing `degraded_banner` in the affected section; the rest of the page stands. | As today: the section title plus the error, verbatim. |

### 3.2 At a glance

| Element | State | Copy / behaviour |
|---|---|---|
| Population line | applied · previewing · saved-not-rendered · A-only | See §4 table — the persistence line is *this* line's second half. |
| Share bar | one voice | A single full-width segment with its face; sentence "Engine 100%". |
| Share bar | eight voices | Eight segments; faces only on segments ≥ 44 pt (at 390 pt roughly the top three); the sentence wraps to two lines and stops. |
| Blend line | no graded calls | "Not graded yet — grading starts after Week 1's games." |
| Blend line | thin (< 30 calls) | "58% over 12 graded calls — needs 30 before it can be called hot or cold." |
| Blend line | graded | "Went 4-for-5 on your roster this week · 63% over 41 graded calls" |
| Blend line | A-only without per-call outcomes shipped | "House model went 4-for-5 this week · your blend is graded once saving is on." |

### 3.3 Your sources — the row

| State | Line 1 | Line 2 |
|---|---|---|
| Enabled, graded | face · name · share · `STEADY 63% · n41` | switch on · slider · wt |
| Enabled, HOT / COLD | as above with `ui.streak_badge` | same |
| Enabled, thin | `LOW-CONFIDENCE 58% · n12` (title "needs 30 graded calls") | same |
| Enabled, **no accuracy yet** | `NO-DATA · starts week 1` | same |
| Enabled, **went dark** (feed 404 / empty this week) | a plain tag after the type: `No feed since Tue` | same; under the slider, one line: "Feed didn't answer this week (404) — no vote from this voice; weight kept." |
| Enabled, **dormant** (library flag) | tag `Quiet since 13 Mar` | same; note: "No episode since 13 Mar — it won't vote until it speaks." |
| Enabled, link-only creator | consent tag `Link-only` after the type | same |
| Enabled, **licensed** creator | consent tag `Licensed` | same |
| Enabled, top-weighted | a small "top" mark on the share number (this is the voice the TOP-WEIGHTED flag is about) | same |
| Off (ghost) | reduced emphasis; grouped under "Off · 2" | switch off · "off · wt 11 kept" |
| Last voice, switch tapped | switch stays on | note: "Your model needs at least one voice — turn another on first." |
| Just added from the library | row at top, highlighted for one scroll | slider focused; note "Added at weight 12 — adjust if you like." |
| Highlighted by deep link ("Adjust your model →") | row scrolled into view, highlighted until the next tap | — |
| Dragging | share on this row and all others update live; row order does **not** change | — |
| Readout tapped | — | numeric field replaces "wt 17"; Enter/blur commits |

### 3.4 The library

| Element | State | Copy / behaviour |
|---|---|---|
| Search | empty | placeholder "Search, or paste a link" |
| Search | name, no matches | "Nothing called that. Paste a link to suggest it." |
| Search | URL that matches an entry | the card alone, headed "Already in the library" |
| Search | URL that matches nothing | scrolls to Suggest with the field filled; the search box clears |
| Search | model link | opens "Use this model?" |
| For you | reader already has everything with weight ≥ 10 | "You've got the room we'd suggest. Browse All for more." |
| Most followed | always has content | — |
| New | nothing in 30 days | segment still present; body: "Nothing new this month. Suggestions that get added show here first." |
| New | launch week (everything is new) | body headed "The library opened 10 Sep 2026" and lists the six categories instead of 78 "new" cards |
| Card | addable | **Add** |
| Card | in the model | "In your model · edit ↑" |
| Card | in the model, off | "In your model (off) · edit ↑" |
| Card | unavailable | reason word in place of Add (§2.3 list); body still opens the sheet |
| Card | room full | Add replaced by "Room full"; sheet says "Eight voices is the most a room can hold — remove one first." |
| Card | dormant / feed down | addable; meta line carries `Quiet since 13 Mar` |
| Card | unverified details | meta line carries `Unverified`; sheet carries the note verbatim |
| Card | **creator signs** (consent flips) | consent tag `Link-only` → `Licensed`; nothing else on the card changes; the sheet gains the licensed footnote |
| Category chips | none selected | all groups shown |
| Category chips | one selected | that group only; chip shows selected; tap again clears |

### 3.5 Suggest a source

| State | Copy / behaviour |
|---|---|
| Idle | field + button + "Reviewed Tuesdays. Everything suggested shows in the list below with its status." |
| Reading | "Reading the link…" (button disabled) |
| Resolved | preview card; Name and Type editable; Why (0/140); **Send** |
| Sent | "Got it — **#A1F3**, Received. We review on Tuesdays." New row at top of the list, marked "yours". |
| Unresolvable | "We couldn't read that as a source. Try the show's RSS, its Apple Podcasts page, or the channel's @handle." |
| Duplicate | "Already in the library — add it to your model?" + the card inline |
| Rate-limited | "You have 5 open suggestions — we'll review those first." |
| Offline | field disabled; "Suggestions need a connection." |
| Phase A (no endpoint yet — see §4) | the same form; **Send** composes a pre-filled email to the house. Under the button: "Sends an email to the house. Reviewed Tuesdays; the list below updates with the weekly render." (The iOS web view already hands `mailto:` to the system — `ios/GradedTakes/Web/ExternalLinks.swift`.) |

### 3.6 Suggested by readers

| State | Copy / behaviour |
|---|---|
| Empty | "Nothing suggested yet. Be the first — the box is right above." |
| Received | `#A1F3 · Fantasy Footballers · Podcast · Received` |
| Reviewing | `… · Reviewing` |
| Added | `… · Added ✓` (links to the library card) |
| **Declined** | `#7B10 · (name) · Declined — no public record we can grade` — stays listed, collapses to "Older" after 30 days; the suggester's Monday line reads "Your suggestion #7B10 was declined: no public record we can grade." A second line under the row, suggester only: "Different link? Suggest it again." |
| Reader's own | "yours" mark on the row |
| Older than 30 days | collapsed under "Older · 7 ▸" |

### 3.7 Receipts

As today (`sources_page.py`): graded, LOW-CONFIDENCE, NO-DATA with reason,
quiet (off) cards, degraded section. Plus: "Your model" row one in the same
states as the blend line (§3.2).

### 3.8 Footer

| State | Copy |
|---|---|
| Clean | hidden |
| Dirty | **Discard** · **Apply 2 changes** |
| Applying (B) | "Saving…" (button disabled) |
| Applied | toast with the §4 line for the current world, four seconds |
| Failed (B) | "Couldn't save — kept on this phone. Try again." (stays dirty) |

---

## 4. Persistence — what changes where, and the words that say so

Per `UX_RESEARCH.md` §6: hybrid, built as **A now** (client-side: the page
ships each row's per-source votes and recomputes `consensus.weigh()` in the
browser; applied weights live in `localStorage`) and **B before the first
stranger** (a Cloudflare Pages Function writes `{token, weights, enabled,
updated}` to KV; `publish.py` reads it before rendering each person's pages,
so the digest, the four pushes and the widget's `needs.json` honour the
reader's model).

What the reader must be able to tell, at a glance, without knowing any of
that:

| World | What changes live in the browser | What waits for the weekly render | The line under the share bar (exact) |
|---|---|---|---|
| **A only** (this season's family pilot) | shares, this page, every verdict chip on lineup / board / digest pages already open on this device, the "Your model" blend line *if* per-call outcomes ship | the Tuesday digest as rendered, Wednesday / Sunday / Monday pushes, the widget count, any other device | "Adjusting here changes this page and your verdicts on this phone. Tuesday's digest and your notifications use the house model until saving is on." |
| **C, previewing** (dirty, before Apply) | the share bar and rows, live | everything else | "Previewing 2 changes — Apply to keep them." |
| **C, applied, before Tuesday** | this page and every chip, on every device once loaded | the already-rendered digest and this week's remaining pushes | "Saved. This page uses your model now; Tuesday's digest and your notifications will too." |
| **C, applied, after the render** | — | — | "Your model · applied Tue 7am" |
| **Offline, applied (B)** | this device | the save itself | "Offline — kept on this phone; saves when you're back." |

Three rules that stop silent pretending:

1. **Chips carry a tag until the render catches up.** After Apply and before
   Tuesday, every verdict chip that was recomputed in the browser shows a
   small "recomputed with your model" mark in its popover. When the render
   catches up the mark goes away. (Research §6 C.)
2. **The blend line never grades a model it didn't compute.** If per-call
   outcomes are not in the page, the line says "House model went 4-for-5"
   — it does not borrow the house's number under the reader's name.
3. **`localStorage` is a cache, not a store.** It holds un-applied drafts
   and, in A-only, the applied weights. The page must render correctly with
   it empty (private window, cleared data, another device) — that is the
   "You have 2 unapplied changes" banner and the house model, respectively,
   never a blank.

Apply's toast uses the same line as the table row it lands in. The
population line's second half ("applied Tue 7am" / "saved Thu" / "on this
phone") tracks the same state.

---

## 5. Phone rules, applied

The existing pages pass an iPhone-fit checklist at 375 / 390 / 430 with zero
horizontal overflow (`platform.md`); this page must pass the same one.

1. **Three columns max per row.** Every row on the page is drawn on one of
   two grids and nothing else:
   - identity rows: `44pt | 1fr | auto` (face · text · number-or-control)
   - control rows: `44pt | 1fr | 56pt` (switch · slider · readout)
   - list rows (suggestions): `auto | 1fr | auto` (id · text · status)
   The library card is the identity grid with a 36 pt face and the Add
   control in the third column. Meta lines belong to the middle column and
   wrap under it, never into a fourth column.
2. **44 pt targets, two-dimensional.** Faces, switches, Add, Suggest, Apply,
   Discard, segments, chips, the readout, the disclosure summary, each
   suggestion row and the sheet close button are all ≥ 44 × 44 pt hit areas
   (`ui.py`: "a tap target is two-dimensional"). The accuracy line and the
   blend line are tappable text: give them a 44 pt tall hit area even though
   the text is small.
3. **Names ellipsise.** Source names, `what_for`, host lists, suggestion
   names: single line, `text-overflow: ellipsis`. Never wrap a name; never
   shrink a name to fit. Short names come from the library's `short_name`
   where present (the honesty sentence and matrix columns need them).
4. **No horizontal scroll, anywhere.** The body never scrolls sideways; there
   are no rails; category chips wrap; the honesty sentence wraps; the share
   bar is 100% width with segments that shrink to zero rather than overflow;
   the receipts' meters are the existing ink meters. The one horizontal
   gesture on the page is the slider — a rail beneath rows full of sliders
   would be a gesture conflict, which is the second reason there are none.
5. **Sliders a thumb can use.** Track spans the middle column (≥ 200 pt at
   375); thumb ≥ 28 pt visible inside a 44 pt hit area; step 1; no snapping,
   no haptics; the row does not reorder while dragging; the readout is the
   place for precision, not the thumb. A slider is never the only way to
   set a value (the readout is the other). Off rows have no slider at all.
6. **Sheets, not pages.** Every detail is a bottom sheet (`ui.sheet`) so the
   reader never loses their scroll position in a list of 78. Sheets cap at
   80 vh and scroll inside themselves.
7. **The footer never covers content.** When the Apply footer is shown, the
   page gains bottom padding equal to its height plus the tab bar.

---

## 6. Scope guard, and the three open questions

### What not to build (this pass)

- **No content.** No transcripts, no quotes, no episode blurbs, no "latest
  take" previews on cards or sheets — for unsigned creators by the plan, and
  for signed ones not on this page (their quotes belong on the verdict
  popovers).
- **No marketplace.** No ratings, comments, reviews, follower counts of
  readers, creator profiles or creator dashboards. "Most followed" is a
  sort, not a social feature.
- **No live following.** "Share your model" is a snapshot link. Subscribing
  to someone's model so it changes when theirs does is a later feature that
  needs B and consent on both sides.
- **No per-position or per-league weights.** One model per person (open
  question 2). The league-size discount already lives in the vote
  (`weight_factor`), not in the UI.
- **No sum constraint, no equalise button.** Weights normalise; the share
  bar is the honesty check.
- **No free-text suggestions.** A suggestion is a link. The "why" is optional
  and 140 characters.
- **No CAPTCHA, no accounts on this page.** The per-person token and
  Cloudflare Access already attribute every action; the rate limit is five
  open suggestions.
- **No sixth tab, no gear entry, no "More" tab.**
- **No new push type.** Suggestion state changes ride in the Monday line.
- **No recommendations engine.** "People who add X also add Y" is the
  Substack moment and it is worth doing — after there are enough readers for
  the sentence to be true. *For you* is a sort with a blurb.
- **No editing of library entries by readers.** Corrections go through
  Suggest ("fix it if we read it wrong" is for the suggester's own entry
  only).
- **No owner review UI on this page.** The queue is reviewed from the YAML
  on the owner's schedule.

### Three open questions for the owner

1. **What does a link-only creator contribute to a verdict before they
   sign?** The research's sheet copy assumes calls are graded "from the
   creator's public episode titles and our own notes". If a link-only
   creator can vote (titles + house notes), then Add is meaningful for ~60
   of the 78 entries and the footnote is right as written. If a link-only
   creator contributes a face and a link and *no vote* until they sign, then
   most of the library is "Open link" rather than "Add", the room is mostly
   feeds until creators sign, and the page should say so at the top of the
   library. This decides the shape of the Add control and it is not a design
   question.
2. **One model per person, or one per league?** The brief assumes one per
   person: leagues differ in size and the engine already discounts calls per
   league (`leaguesize.py`), so the same weights produce league-appropriate
   verdicts. A per-league model doubles every state above and needs the
   league switcher to change the whole page. Recommend one per person; wants
   a yes.
3. **May the page show what other readers chose?** "Popular" / "in 3 readers'
   models" / the public suggestion list all reveal something about the
   handful of people on the pilot. In an eight-person family pilot "in 1
   reader's model" identifies a person. Proposal: reader counts appear only
   at ≥ 20 readers and the segment is labelled "Most followed" (reach) until
   then; the suggestion list shows ids and names of *sources*, never of
   suggesters, from day one. Needs a decision before the first render with
   more than one person on it.

### Hand-off notes (engineering, not design)

- New page `model.html` per person, ordered as §2; `sources.html` keeps
  rendering as an alias/redirect for one season so old links hold.
- `Destination.ledger` → `.model` in `SiteMap.swift`; `Router.swift` deep
  link `gradedtakes://open?path=model.html#src-row-<id>`.
- `library.yaml` needs `short_name` and `added_on`; `data/library_suggestions.yaml`
  is the queue (`LIBRARY_NOTES.md`).
- The JS/Python parity test for `weigh()` is the important part of A.

---

## 7. Sources

Internal (read 2026-09-10):
- `design/model/UX_RESEARCH.md` — §2 FantasyPros anatomy, §3 weighting
  precedents, §4 phone layout, §5 suggestion loop, §6 persistence, §7 placement
- `design/model/library.yaml`, `design/model/LIBRARY_NOTES.md` — entries,
  flags, `public_status`, maintenance rhythm
- `design/plan/platform.md` — data-rights table, creator programme (decision
  5), the four pushes and the three-a-week cap, Cloudflare hosting
- `engine/sources_ui.py` — the owner's row (36 px face, switch, slider +
  number, live share), the normalisation copy quoted in §2.2
- `engine/sources_page.py`, `engine/performance.py` — the five states,
  `MIN_GRADED_CALLS = 30`, `CREATOR_REASON`, NO-DATA discipline
- `engine/consensus.py` — `score = Σ(w·v)/Σw`, "the room", TOP-WEIGHTED,
  `weight_factor`, "Your model says START – 71%"
- `engine/ui.py` — `sheet()`, `segmented()`, `section_header()`,
  `nameplate()`, `streak_badge()`, `sparkline()`, the 44 pt rule
- `engine/digest.py` — "YOUR MODEL — source agreement matrix"
- `docs/APP_MODE.md`, `ios/GradedTakes/Model/SiteMap.swift` — five tabs;
  `sources.html` has no destination

External, via the research reports (all checked 2026-09-10 there; not
re-fetched for this brief):
- FantasyPros "Pick Experts" — https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php ; FAQ https://www.fantasypros.com/tools/
- Fantasy Football Analytics custom weights (2014-06) — https://fantasyfootballanalytics.net/2014/06/custom-rankings-and-projections-for-your-league.html ; accuracy tab — https://fantasyfootballanalytics.net/ffanalytics-web-app-accuracy-tab
- M1 Finance pie rules — https://help.m1.com/en/articles/9332119-edit-your-m1-portfolio
- Apple Podcasts row roles (2023-06-20) — https://podcasters.apple.com/5304-elevating-nine-podcast-subcategories-charts
- Feedly URL search and sorts — https://docs.feedly.com/article/287-how-to-find-and-add-follow-sources ; https://feedly.com/new-features/posts/how-to-discover-the-best-content-on-feedly
- Substack recommendations (2022-04-12) — https://on.substack.com/p/recommendations
- Pocket Casts submissions — https://support.pocketcasts.com/knowledge-base/submitting-podcasts/
- Canny statuses (2026-06-05) — https://help.canny.io/en/articles/673583-post-statuses
- Cloudflare Pages Functions bindings — https://developers.cloudflare.com/pages/functions/bindings/
- MDN `localStorage` — https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- Apple HIG tab bars / settings — https://developer.apple.com/design/human-interface-guidelines/tab-bars ; https://developer.apple.com/design/human-interface-guidelines/settings **[quoted via a mirror in the research; unverified against the live pages]**

Unverified in this brief: HIG quotations (mirror); the ≥ 20-reader privacy
threshold is a proposal, not a researched number. `short_name` and `added_on`
do not exist in `library.yaml` yet (checked 2026-09-10) — they are additions.
