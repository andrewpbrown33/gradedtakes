# Build-your-own-model UX — research and recommendations

Written 2026-09-10 for Graded Takes. Scope: the "Model" page where a reader
picks sources, weights them, browses a library of real sources, and suggests
new ones. Every external claim carries a URL and the date it was checked;
anything I could not verify against a primary page is marked **[unverified]**.
Internal claims cite the file in this repository.

Constraints this design honours (decided in `design/plan/platform.md`):
the YouTube transcript pipeline is deleted before hosting; creators are
link-only (name, avatar with permission, link, ledger line) until they sign a
licence; podcast RSS and YouTube channel *metadata* are fine. So the library
below is a **directory of links and metadata with a graded ledger line**, not
a content feed.

---

## 0. The recommendations, up front

1. **Copy FantasyPros' shape, not its scale.** Their "Pick Experts" is a
   checkbox table with accuracy-rank columns, recency filter, accuracy
   presets ("Top 10 in-season"), a live "N experts selected" counter and an
   Apply button. It is include/exclude only. We keep the same anatomy and add
   the one thing nobody in fantasy ships: a weight per source with a live
   *share* readout (`engine/sources_ui.py` already draws this for the owner).
2. **Weights are relative, normalised, and shown as share.** Do not make the
   reader keep a total at 100 (M1's hard-constraint model is right for money,
   wrong for opinions). Do cap the number of enabled voices at eight and show
   the share bar so the total is honest by construction.
3. **The library is a phone directory, not a marketplace.** Search box that
   accepts a URL, four sections (In your model / Suggested for you / Popular /
   New), one card layout, one detail sheet. Feedly's four sorts and Apple
   Podcasts' row structure are the models.
4. **The suggestion box is a URL field with a public status list.** Submit →
   receipt with an id → the same id appears on a "Suggested" list with one of
   four states (Received / Reviewing / Added / Declined + one-line reason) →
   the Monday ledger notification carries "your suggestion was added".
   Canny and Pocket Casts show the minimum honest loop.
5. **Persistence: Hybrid (C), sequenced A-then-B.** Ship client-side
   reweighting this season (per-row votes are ~8 KB per page; the browser
   recomputes `engine/consensus.py`'s weighted mean). Persist to a
   Cloudflare Pages Function + KV keyed by the person's publish token — the
   platform plan's own vendor, not a new Vercel + Supabase pair — and have
   `publish.py` read those weights before it renders. The digest and the
   Monday ledger notification then honour the reader's model.
6. **Placement: the fifth tab becomes "Model".** Not a sixth tab (Apple's
   guidance and the audit both cap at five), not under the gear (Apple's
   settings guidance says frequently-changed, task-specific options do not
   belong there). The current "Ledger" tab opens the Tuesday digest, whose
   unique content is *already* the "YOUR MODEL" source-agreement matrix;
   make that tab the model itself (matrix → sources and weights → receipts),
   and reach the rest of the digest from Home and from notifications.
   Today `sources.html` has no native destination at all
   (`ios/GradedTakes/Model/SiteMap.swift`, `Destination.of` returns nil for
   it) — the differentiator is currently unreachable from the tab bar.

---

## 1. What exists today (the baseline the design must fit)

| Piece | Where | What it does |
|---|---|---|
| Registry | `data/sources.yaml` | 7 sources: engine 17, ESPN proj 17, Sharp or Square 17, The Favorites 17, Sleeper proj 11, Chen tiers 11, house research 10. Comment: "weight 0-100, relative — normalized at consensus time". |
| Verdict maths | `engine/consensus.py` | `score = Σ(w_i·v_i)/Σw_i`, v = +1 start / −1 sit / +0.5 flex-lean; pct = 50·(1+score); SPLIT when both sides present and abs(score) < 0.15; LONE-DISSENT names the single loser; TOP-WEIGHTED flag when the reader's heaviest voice disagrees. All-zero weights fall back to an even split. |
| Owner's panel | `engine/sources_ui.py` | Localhost only. Per row: 36 px avatar, name, live weight, handle, type tag, enable switch, 0–100 slider paired with a number box, a live **share** readout (weight / sum of enabled weights), fetch-now. Add-by-URL/handle, paste creator content. Bound to localhost, no sessions, no CSRF (platform plan, "What gets rewritten"). |
| Receipts page | `engine/sources_page.py` → `sources.html` | Read-only. One card per source: 44 px face, weight, form state, blended hit rate, sample size, streak, sparkline, per-position split, provenance line. NO-DATA is stated, never filled. |
| Digest ("Ledger" tab) | `engine/digest.py` | Tuesday brief. Its "YOUR MODEL" section is the source-agreement matrix: rows = contested calls, columns = enabled sources by weight, cells = verdict chips, headline "Your model says START – 71%". |
| Per-person publish | `users.yaml`, `publish.py` | One entry per person: name, email, 256-bit token, leagues. Pages render to `public/<token>/`, served behind Cloudflare Access. There is no per-person source or weight field yet. |
| Phone shell | `docs/APP_MODE.md`, `SiteMap.swift` | Five tabs: Home, Lineup, Board, Ledger (= digest), Trade Desk. Settings lives behind a gear (`SettingsView.swift`: link, notifications, saved copies, about). |

Two facts from this baseline shape everything below: the maths is a
weighted mean of ±1 votes (trivial to recompute in a browser), and each
reader already has a stable private identifier (the token) that the
publisher walks weekly.

---

## 2. Pattern: FantasyPros "Pick Experts" (observed live, 2026-09-10)

I opened `https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php`
in a browser on 2026-09-10 and read the DOM of the experts control and the
"Pick Experts" modal. What is there:

**The header states the population.** "Consensus of 181 Experts (201
available) – Sep 9, 2026". The default set is not everyone; 20 experts are
out because they have not updated recently (the unchecked rows in the modal
were last updated 08/16–08/24).

**A preset dropdown before the modal.** Label "Experts", options in this
order:

- *Latest ECR* (marked Default) — sub-label "More accurate experts with
  recent updates"
- *2025 Draft Accuracy* → Top 10 Overall / Top 20 Overall
- *2025 In-Season Accuracy* → Top 10 Overall / Top 20 Overall
- *2024 In-Season Accuracy* → Top 10 Overall / Top 20 Overall
- *Sites* → one row per outlet with its expert count (FantasyPros 15,
  RotoBaller 6, Draft Sharks 5, FTN 5, Fantasy In Frames 5, Yahoo! Sports 5,
  Fantasy Six Pack 4, … 29 sites)
- *Custom Experts* → "Click here to pick experts"

**The modal.** `h1` "Pick Experts"; a live counter "181 experts selected";
a Close button; the same preset selector; a "Recency" filter (showing
"All"); a sortable table with a "Select all experts" checkbox and these
columns:

| ☐ | EXPERTS | Twitter | 2025 Draft | 2025 In-Season | Rankings | LAST UPDATED |
|---|---|---|---|---|---|---|
| ☑ | avatar · **Dalton Del Don** · The Deep Shot | @daltondeldon | #53 | #6 | View | 09/09 |
| ☑ | avatar · **Chris Dell** · The Fantasy Edge | @maddjournalist | #169 | #67 | View | 09/09 |
| ☑ | avatar · **Owen MacCarrick** · Chop Fantasy Football | @ItsChopFF | – | – | View | 09/09 |

Name links to an expert profile ("View Expert Profile" info card with name,
@handle, site). Experts with no graded history show "–", not a fabricated
rank. Sorted by last-updated descending. Footer button: **Apply**. There are
202 checkboxes for 201 experts (one is Select-all).

**Gating.** As an anonymous visitor, clicking the Recency control navigated
to `Sign In | FantasyPros`. A third-party feature matrix (Fantasy Joes,
2026-06-11) lists "Hand-pick which experts feed a custom consensus — No
[Free] / PRO and up [Paid]" — **[unverified against FantasyPros; their
support articles returned HTTP 403 to my fetches]**.
https://fantasyjoes.gg/blog/fantasypros-cheat-sheet-creator-free-alternatives

**Stated rules (FantasyPros' own FAQ, fetched 2026-09-10).**
https://www.fantasypros.com/tools/
- "We allow you to combine anywhere from 2 to all of the experts we track."
- "Use one of our accuracy filters or hand pick the experts you trust."
- "Our Cheat Sheet Wizard even allows you to filter out experts that have
  not updated their rankings recently."

**How the accuracy rank behind the "#6" is built.** In-season methodology
(fetched 2026-09-10): each rank slot gets a point value from historical
production, the gap to actual points is the error, gaps are converted to
z-scores, each expert's worst week is dropped from week 8, and the overall
board sums QB/RB/WR/TE only ("DST and K are excluded because (a) many
experts do not produce rankings for these positions…").
https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/
The 2025 results article (2026-01-07) ranked 159+ experts and presents them
as Rank · Expert · Site, with prose badges such as "#1 ranker for Wide
Receivers" and "Four consecutive years finishing in the top 4".
https://www.fantasypros.com/2026/01/2025-fantasy-football-rankings-most-accurate-experts/

**How the weighted result is shown.** It is not weighted — every selected
expert counts once; the consensus is the average rank, the heading tells you
how many experts are in it, and a separate "Dissenting Opinions" page lets
you compare any two experts or ECR sources side by side (two dropdowns
labelled "Choose an expert or ECR source…", ~300 entries of name + site).
https://www.fantasypros.com/nfl/rankings/compare-experts.php (fetched
2026-09-10)

**What to take.**
- The population sentence at the top ("Your model: 5 voices, updated Tue").
- Accuracy-rank columns with "–" for no history — this is exactly our
  NO-DATA discipline, in a column.
- A recency filter and a "last updated" column: our equivalent is
  "last call graded" and "calls this week".
- Presets that are *sets*, not weights: "Engine only", "Everything graded ≥
  30 calls", "Most accurate 3 + engine".
- A live counter and a single Apply. No auto-save while dragging.
- Minimum two voices (their floor) — ours should be one, because "engine
  only" is a legitimate model (platform plan, item 5: "render week 1 with
  `engine` alone").

**What not to take.** 201 rows on a phone. Our library will be tens of
entries, and the *model* is a handful; the modal-with-table pattern is for
the library, not the weights.

---

## 3. Pattern: weighting sources, not just including them

Almost nobody lets the user weight. The ones that do, and how they keep the
total honest:

### 3.1 Fantasy Football Analytics — relative numeric weights, accuracy defaults

Their projections app (article 2014-06, tool still live) is the one fantasy
product with user weights. Quotes (fetched 2026-09-10):
https://fantasyfootballanalytics.net/2014/06/custom-rankings-and-projections-for-your-league.html
- "You can choose which projection sources to include and, if weighted
  average, the weights for each analyst."
- "if you want to exclude ESPN projections, you would give them a weight of
  0. If you want to give Yahoo projections twice the weight of CBS, you would
  give Yahoo a weight of 2 and CBS a weight of 1."
- "The default weights reflect historical accuracy (higher = more
  accurate)." FantasyPros defaults to 0 "to avoid double-counting their
  aggregated sources".

Their Accuracy tab (screenshots dated May 2025) shows a mean-absolute-error
bar per source with three comparison bars: *FFA Average*, *FFA Weighted*
("gives more influence to historically more accurate sources") and *Current
Setting* — i.e. it grades **the user's own blend** next to the defaults.
https://fantasyfootballanalytics.net/ffanalytics-web-app-accuracy-tab
Their FAQ frames the reason to reweight: "you might look at the individual
projection sources … and you can exclude them or give them less weight."
https://fantasyfootballanalytics.net/about-the-site/faq

**Honesty mechanism: normalise.** Weights are ratios; 0 excludes; nothing
sums to anything. This is our engine's model already.

### 3.2 M1 Finance pies — hard cap at 100, save disabled otherwise

https://help.m1.com/en/articles/9332119-edit-your-m1-portfolio (fetched
2026-09-10): "Total target percentages for all Slices must equal 100%. Each
Slice must be set to at least 1%." Adjust with "the '+' and '–' buttons or
manually adjust the numbers". "You cannot save your updated Pie until all
percentages total 100%." Third-party write-ups mention a "select all →
equalize" affordance **[unverified — not in the M1 help articles I
fetched]**.

**Honesty mechanism: cap.** Right when the number is money. For opinions it
turns every slider drag into arithmetic homework, which is why the owner's
panel already chose normalise-and-show-share.

### 3.3 Numerai — weight is stake

The hedge fund's Meta Model is "the stake-weighted average of every
signal"; a larger stake means a larger weight, computed by "multiplying
predictions by stakes and dividing by the sum of stakes" (Numerai forum /
docs via search, 2026-09-10; https://docs.numer.ai/ and
https://forum.numer.ai/t/about-the-stake-weighted-meta-model/6858 —
**[quotes from search summaries, pages not fetched]**). The lesson is
conceptual: **weight is a statement of confidence with a cost**. Our
analogue is the ledger: a reader who over-weights a cold source *sees* it in
"your model went 2-for-5", which is the cost.

### 3.4 Action Network — blended by the house, followed by the user

PRO projections "are projection blends of several of our key betting
experts, including Sean Koerner and Stuckey"; the page shows an edge
("the percentage difference between a sportsbook's odds vs. our
projections") and an A–F grade; there is no user weighting.
https://www.actionnetwork.com/nfl/projections (fetched 2026-09-10)
The social side is *follow*, not weight: Follow tab → Explore Users →
Verified Experts → sort by sport → Follow; PRO users get instant pick
alerts, non-PRO get them 30 minutes later.
https://actionnetworkhq.zendesk.com/hc/en-us/articles/360030878072-How-do-I-follow-Experts
and …/29108340279821-What-are-PRO-Instant-Expert-Alerts **[both from
search snippets; pages returned 403 to direct fetch]**.

### 3.5 Betstamp — follow with a verified record

App Store listing (v2.8, 2025-01-08): "Connect with friends, receive updates
on their bets"; bets use "real-time verified lines" and "You cannot edit,
delete, use fake lines".
https://apps.apple.com/us/app/betstamp-bet-tracker-props/id1525948689
FAQ: "follow your friends or favourite handicappers"; "Build credibility by
verifying your betting record". https://www.betstamp.com/faqs (fetched
2026-09-10). Pattern worth copying: the **verified badge on the record**,
not on the person. Our ledger line is that badge.

### 3.6 What this means for our slider

- **Relative 0–100, normalised, share shown** (keep `sources_ui.py`'s
  design). The slider's label is the share, not the raw number: "Sharp or
  Square · 24% of your model".
- **Live total line under the list**: "5 voices · engine 28% · ESPN 28% ·
  Sharp or Square 24% · …" — that sentence is the honesty check; a reader
  never has to add anything.
- **Cap the count, not the sum.** Maximum eight enabled voices. The
  digest's agreement matrix is already documented as a "9-column" table
  that stacks into one card per row under 700 px (`engine/digest.py`, the
  phone CSS comment); more voices than that fit on no screen and dilute
  every share below 10%. FantasyPros' floor of two becomes our floor of
  one.
- **Defaults are accuracy-informed, like FFA**, but only once a source has
  ≥ 30 graded calls (the ledger's own threshold, platform plan §"death
  valley"). Before that, defaults are the owner's registry weights and the
  card says so.
- **Grade the reader's blend, like FFA's "Current Setting" bar.** The
  ledger already computes "your model went 4-for-5"; put "Your model" as the
  first row of the receipts, above the individual voices.
- **Zero is exclude, and the switch is zero.** One control fewer than the
  owner's panel: the enable switch and weight 0 are the same state, drawn as
  a ghost row.
- **Apply, don't auto-save.** A sticky footer "Apply to my model" with the
  count of changes, exactly like FantasyPros; every drag before Apply is
  previewed, not committed (this is what makes option A in §6 feel
  instant).

---

## 4. Pattern: a source library on a phone

### 4.1 Apple Podcasts — rows by role, charts by category

Category pages carry "easy to navigate rows for charts and additional
subcategories": "Apple Podcasts Essentials — all-time favorite podcasts for
each category curated by our global editorial teams", charts of "Top Shows
and Top Episodes", plus rows for "New & Noteworthy shows, standout Shows of
the Month, Featured Channels, Creators We Love".
https://podcasters.apple.com/5304-elevating-nine-podcast-subcategories-charts
(2023-06-20, fetched 2026-09-10). Sports has a **Fantasy Sports**
subcategory ("Sports distributes content by sport including Wilderness and
Fantasy Sports") — https://appleinsider.com/articles/19/08/01/apples-podcasts-app-introduces-new-content-categories
(2019-08-01). Categories live under "Browse by Category"; on iPhone all
categories are also reachable from the Search tab.

Take: **rows have jobs** (curated / popular / new), and the *chart* is a
separate, honest, numeric list. Our chart is the ledger.

### 4.2 Feedly — search that accepts a URL, four sorts, bundles

Docs (2022-07-16): "On top of the discover page, you will find a search box
allowing you to search for any topic, hashtag, website name or URL"; a
"SIMILAR SOURCES link to find similar sources to those you like".
https://docs.feedly.com/article/287-how-to-find-and-add-follow-sources
Blog (2020-08-14): sorts are *Best Match* ("a balance of popularity and
relevance"), *Followers*, *Articles per week*, *Relevance* ("great for
finding niche industry experts because it considers focus instead of
popularity"); plus "industry bundles" of "hand-picked" sources.
https://feedly.com/new-features/posts/how-to-discover-the-best-content-on-feedly
Feedly auto-detects RSS from a pasted site URL (docs, 2026-09-10 search
summary of https://docs.feedly.com/article/768-follow-sources-in-feedly —
**[not fetched directly]**).

Take: **one search box that accepts a URL** — that is both discovery and
the front door of "suggest a source". Sorts map to ours: Best match →
*Suggested for you*; Followers → *Popular* (readers who enabled it);
Articles per week → *Calls per week*; Relevance → *Graded ≥ 30 calls*.

### 4.3 Substack — recommendations with a blurb, at the moment of subscribing

"Introducing recommendations" (2022-04-12): a writer selects publications
and can "add a personal blurb — a chance to describe why they endorse the
publication"; readers see recommendations "after they subscribe to a
publication" and optionally on the homepage; "The recommended writer will
receive an email with details of how the endorsement has impacted their
subscriber numbers."
https://on.substack.com/p/recommendations (fetched 2026-09-10)

Take: **the moment after "Add to my model" is the recommendation moment**
("People who weight Sharp or Square also add …"), and **the creator gets
told** — which is our link-only creator programme's hook: "12 Graded Takes
readers have you in their model; here is your ledger line".

### 4.4 The phone layout (375–430 px, matching the existing fit checklist)

Components are the ones `engine/ui.py` already has: `section_header`,
`player_row`-style rows, `stat_pill`, `sparkline`, `verdict_chip`,
`sheet()` (a `<dialog>` that is a bottom sheet under 700 px).

```
┌─────────────────────────────────────┐
│ MODEL                        WK 2   │  shell header (existing)
├─────────────────────────────────────┤
│ Your model · 5 voices · applied Tue │  population line (FantasyPros)
│ ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇  │  share bar, one segment per voice
│ engine 28 · ESPN 28 · S/S 24 · …    │  the honesty sentence
├─────────────────────────────────────┤
│ IN YOUR MODEL                  edit │
│ ◉ War Room Engine        28%  4-1 ▁▃▅│  44px face · name · share · form
│   ═══════════●═══        [17]        │  slider + number (owner panel's pair)
│ ◉ ESPN Projections       28%  3-2 ▃▂▄│
│ ◉ Sharp or Square        24%  –  NO-DATA│
│ ○ Boris Chen tiers        0%  (ghost row = excluded)                     │
├─────────────────────────────────────┤
│ 🔍 Search sources, or paste a link  │  Feedly's box; a URL routes to §5
├─────────────────────────────────────┤
│ SUGGESTED FOR YOU              see all│  Substack-style, blurb per card
│ ◧◧◧ horizontally scrolling cards ◧◧◧ │  each: face · name · type tag ·
│                                     │  "graded 41 calls · 63%" or NO-DATA
│ POPULAR · readers' models      see all│  Apple "Top Shows" == ledger-sorted
│ NEW THIS MONTH                 see all│  Apple "New & Noteworthy"
│ BROWSE  Podcasts · YouTube · Newsletters · Projections · Analysts  │ chips
├─────────────────────────────────────┤
│ SUGGESTED BY READERS           12    │  §5's public status list
│ #A1F3 Fantasy Footballers  Reviewing│
│ #9C02 Underdog rankings    Added ✓  │
│ #7B10 (some tipster)       Declined — no public record to grade │
├─────────────────────────────────────┤
│ RECEIPTS                             │  the existing sources_page cards,
│ Your model      4-for-5 this week    │  with "Your model" as row one (FFA)
│ War Room Engine  63% · n=41 · ▁▃▅▇  │
│ …                                    │
└─────────────────────────────────────┘
│ ● Home  ≡ Lineup  ▦ Board  ⚖ Model  ⇄ Trade │  five tabs (see §7)
        [ Apply 2 changes to my model ]          sticky footer when dirty
```

Per-card detail is a **bottom sheet**, not a page: face, name, type,
outlet link (the link-only creator contract), "in N readers' models",
ledger line (hit rate · sample · streak · sparkline · provenance
"live 2026 calls"), and two buttons: *Add to my model* (lands at the
registry default weight, then the row's slider is focused) and *Open
link*. For a creator who has not signed, the sheet has **no quote and no
transcript**, by design — say so in a footnote line: "Link-only. Calls are
graded from the creator's public episode titles and our own notes; quotes
appear only if the creator opts in."

Row density: 44 px face rows for the model (there are ≤ 8), 36 px faces for
library cards (the owner's panel uses 36 px), horizontally scrolling card
rails at 148 px wide so 2.4 cards show at 375 px — the "half a card"
convention that signals scrollability.

---

## 5. Pattern: a suggestion box that is honest

### 5.1 What works elsewhere

**Podchaser / Pocket Casts — the input is a feed, not a free-text wish.**
Podchaser's add form takes "an RSS feed, Apple Link, or Spotify link",
requires login, then "Podchaser will then pull your information from your
RSS feed and create a listing" (Riverside guide via search, 2026-09-10;
https://www.podchaser.com/add returned 403 to direct fetch —
**[unverified]**). Pocket Casts takes a "Podcast RSS feed URL" or "Apple
Podcasts link", de-duplicates on "Title, Author, Website URL, Thumbnail URL",
and on success "you should see the Pocket Casts share link at the bottom of
the page"; timing is honest but vague: "it can take a little while before it
appears in search".
https://support.pocketcasts.com/knowledge-base/submitting-podcasts/ (fetched
2026-09-10, undated)

**Canny — six states and an email to every voter.** Default statuses
(help article last updated 2026-06-05): "Open — (No status)", "Under Review —
(We are considering this)", "Planned — (We are planning to work on this)",
"In Progress — (We are actively working on this)", "Complete — (We are done
working on this)", "Closed — (We will not work on this)". On a status change
voters "will get a custom-branded email" with the new status and comment.
https://help.canny.io/en/articles/673583-post-statuses

**Spotify Idea Exchange — the same idea with plainer words.** "Under
Consideration" = "This feature is coming"; "Not Right Now" = "We talked
about this internally but it's not on our timeline right now"; ideas get
"Closed" when they fail the guidelines. (Search summaries of
https://community.spotify.com/t5/FAQs/Idea-Exchange-Guidelines-What-do-I-need-to-know-before/ta-p/5171172
— **[page returned 403 to direct fetch]**.)

**GitHub issue forms — structure at the point of entry.** A YAML form has
`name`, `description`, `body`, optional `title`, `labels`, `assignees`;
fields are `markdown`, `input`, `textarea`, `dropdown`, `checkboxes`,
`upload`; `validations: required: true` blocks submission without the
field. https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms
(fetched 2026-09-10). The lesson is that **a required URL field plus a
dropdown for type does most of the anti-spam work** before any moderation.

### 5.2 The minimum honest loop for us

```
paste link ─► we resolve it ─► "Got it. #A1F3, Reviewing." ─► weekly review
                 │                        │                        │
       not a feed/channel/         appears at once on the      Added → in library,
       newsletter/analyst page →   public "Suggested by         suggester's Monday
       "We couldn't read that as   readers" list, status        ledger line says so
       a source. Try the show's    Received                      Declined → one-line
       RSS or channel link."                                     reason, stays listed
```

- **Input: one URL field, one type dropdown, optional 140-char "why".**
  No free-text-only submissions. The URL must resolve to something the
  resolver can name: podcast RSS, Apple/Spotify show page, YouTube
  channel/@handle, Substack/newsletter home, or an analyst's outlet page.
  `engine/sources_ui.guess_type()` and `host_of()` already classify handles.
- **Dedupe on resolve** against the library by canonical URL and by
  Pocket Casts' four fields (title, author, site, artwork). If it exists:
  "Already in the library — add it to your model?" with the card sheet.
- **Receipt = an id and a state**, shown inline and copied into the
  public list. States, in our words: *Received* · *Reviewing* · *Added* ·
  *Declined — reason*. Four, not six; we have no "Planned".
- **Every state change is visible without an account**, because the list is
  part of the rendered page. The Monday ledger notification (platform plan,
  capped at three pushes a week) carries one line when the suggester's item
  changes state — no new notification type.
- **Decline reasons are pre-written**, and they are the data-rights plan
  in plain English: "no public record we can grade", "paywalled — nothing
  to link", "not fantasy football", "duplicate of …". A decline never
  says "low quality".
- **Anti-spam without a CAPTCHA**: the page is behind Cloudflare Access
  with a per-person token (`users.yaml`), so every suggestion is already
  attributable; rate-limit to 5 open suggestions per token; require the
  resolver to succeed; honeypot field; the review is a human once a week,
  which is the cap on damage. For public launch the FastAPI tenant table
  replaces the token with the account.
- **The library grows on the owner's schedule.** "Reviewed weekly" is
  written on the box. Pocket Casts' "a little while" is the honest
  benchmark; do not promise a day.

Data-rights note: a suggestion adds a **metadata row** (name, link, type,
avatar only if the creator's page offers one under terms we can use —
otherwise initials). Nothing is fetched beyond the feed/channel metadata the
plan already allows.

---

## 6. Persistence: A, B or C for our architecture

The constraint: pages are static HTML rendered weekly per person from the
owner's Mac into `public/<token>/` (`publish.py`), served by Cloudflare
Pages behind Cloudflare Access (`design/plan/platform.md`, Phase 0). Weights
live in `data/sources.yaml`. Notifications are four pushes a week, computed
at render time.

### A. Client-side reweighting

*Ship each row's raw per-source votes in the page; recompute in the
browser; persist weights in `localStorage`.*

- **What the user sees.** Sliders move, the "Your model says START – 71%"
  chip on the lineup page, the digest matrix headline and the Model page's
  share bar all update instantly. Weights survive reloads on that device.
- **Feasibility.** The maths is `weigh()` in `engine/consensus.py`: a
  weighted mean of ±1/±0.5 votes, sign → START/SIT/EVEN, abs < 0.15 → SPLIT,
  lone-dissent by counting sides. Fifty lines of JavaScript. The payload is
  a `data-votes` attribute per row: 7 sources × ~40 bytes ≈ 300 bytes per
  row; a lineup page with 30 rows adds ~9 KB, a digest matrix similar —
  well under the platform plan's 48 KB per-tenant state budget. The
  league-size downgrade factor ships with each vote (`weight_factor`,
  already on the vote dict) so the browser multiplies rather than recomputes
  it.
- **What breaks.** (1) The Tuesday digest, the Sunday 11:15 "two changes
  since Tuesday" push and the Monday "your model went 4-for-5" push are
  computed on the Mac with the *owner's* weights — the reader's model is a
  fiction the moment they close the tab. (2) `localStorage` is per-origin
  and per-browser: the phone and the laptop disagree, the native app's
  WKWebView and Safari disagree, and users "can block storage or configure
  browsers to prevent persistence"
  (https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage,
  fetched 2026-09-10). (3) The offline copy the iOS app caches
  (`OfflineStore.swift`) is the *rendered* page; it recomputes fine, but
  the widget reads `needs.json` ("2 calls need you", `NeedsState.swift`),
  which the publisher computes with the owner's weights — a reader whose
  model has no contested calls still sees the house count. (4) The
  Receipts' "Your model 4-for-5" line can be recomputed client-side only if
  the ledger page also ships per-call, per-source outcomes — another ~5 KB
  and worth doing, but it must be shipped deliberately.
- **Effort.** Renderer: emit votes and a small script (two to three days
  across lineup, digest, sources pages). iOS: none (the page recomputes
  inside the web view). Tests: one JS/Python parity test that both
  implementations agree on the same fixtures — that test is the important
  part.

### B. Server-side weights

*A tiny endpoint stores per-person weights; the weekly render reads them.*

- **What the user sees.** Sliders, Apply, a toast "Saved. Your model
  applies from Tuesday's render." Every page, every push, every device
  agrees — a week later. Between Apply and Tuesday, the page still shows
  the old model unless A exists.
- **Which endpoint.** The ask names Vercel Functions → Supabase. The
  platform plan already chose Cloudflare Pages + Access for Phase 0 and a
  FastAPI-plus-SQLite box for Phase 1, and it rejected extra vendors on
  principle ("one droplet, one service, one cron is a system you can
  reason about at 11pm on a Sunday"). Cloudflare Pages Functions bind
  directly to KV and D1 ("A binding enables your Pages Functions to interact
  with resources on the Cloudflare developer platform" — KV, D1, R2, Durable
  Objects, …; https://developers.cloudflare.com/pages/functions/bindings/,
  fetched 2026-09-10), and the function sits behind the same Cloudflare
  Access policy that already gates the page. So: **`/api/model` as a Pages
  Function writing `{token, weights, enabled, updated}` to KV**, and
  `publish.py` pulls KV for each person before `render_person()`. Supabase's
  free tier would do the job (500 MB, 50,000 MAU, but "Free projects are
  paused after 1 week of inactivity" — https://supabase.com/pricing, fetched
  2026-09-10), and that pause is exactly the failure a weekly cron would hit
  in a quiet week. Not worth a second vendor.
- **What breaks.** (1) Latency of a week between intent and effect — the
  single worst UX in the three options unless paired with A. (2) A new write
  path into the render, which today is read-only by design; it needs the
  same validation `sources_ui.apply_updates()` does (integer 0–100, known
  ids, no half-applied batches). (3) The renderer becomes per-person in a
  new way: today per-person differs by *league*; now it differs by
  *weights*, so the shared feed cache is unchanged (good) but the consensus
  step runs once per person (fine — it is arithmetic). (4) In Phase 1 this
  moves into the FastAPI tenant table; design the KV record so it is the
  same JSON.
- **Effort.** Function + KV + Access: one day. `publish.py`/`consensus`
  reading per-person weights with a fallback to the registry: one to two
  days. Heartbeat assertion that the per-person weights were honoured
  (`publish.py check-heartbeat` already exists): half a day. Ops: a KV
  namespace to back up — small, but new.

### C. Hybrid

*A for instant feedback, B to persist and feed the render.*

- **What the user sees.** Drag → instant preview everywhere on the page →
  Apply → "Saved. This page is already using your model; Tuesday's digest
  and your notifications will too." One sentence, true on both halves.
  On a fresh device, the page loads with server weights baked into the
  render *and* the script reads them from the page — no `localStorage`
  dependence except as a cache of un-applied drags.
- **What breaks.** Two implementations of one formula (mitigated by the
  parity test in A). A brief window where the rendered page's baked
  verdicts and the applied weights differ (the page shows a small
  "recomputed with your model" tag on the chips until Tuesday, which is
  honest and also a nice thing to see).
- **Effort.** A + B; the overlap is the JSON shape.

### Recommendation: C, built as A now and B before the first stranger

Reasoning:

1. The differentiator is *feeling* the model move. A is the only option
   that makes a slider drag change a verdict within the same second, and it
   needs no backend — it ships this season on Cloudflare Pages as-is.
2. But the product thesis is not "a toy that recomputes"; it is "your model
   tells you Sunday at 11:15 that Rice is out". The four pushes are the
   retention loop (platform plan, Phase 2), and they are rendered on the
   Mac. Without B, "your model" is a lie in the notification that "must
   never be wrong".
3. B without A is a week-long feedback loop; nobody tunes anything with a
   week-long loop.
4. Sequencing: A is renderer-only and testable against the Python
   implementation; B is the first write path the platform plan says to hand
   to a contractor (the settings panel's "server half"). Ship A for the
   family pilot; ship B before the eight strangers, and put it in Cloudflare
   KV so Phase 1's FastAPI box inherits a JSON record, not a vendor.

What the page must say, in each state, so the reader is never misled:

| State | Line under the share bar |
|---|---|
| A only | "Adjusting here changes this page now. Your Tuesday digest and notifications use the house model until saving is on." |
| C, before Apply | "Previewing 2 changes — Apply to keep them." |
| C, after Apply, before Tuesday | "Saved. This page uses your model now; Tuesday's digest and your notifications will too." |
| C, after Tuesday | "Your model · applied Tue 7am" |

---

## 7. Where the Model page lives on a five-tab phone

### The constraints

- Apple's tab-bar guidance: "In general, use three to five tabs in iOS";
  "Each additional tab increases the complexity of your app"; "Use the
  minimum number of tabs required" (Human Interface Guidelines, Tab bars —
  the official page renders only via JavaScript; quotes are from a mirror
  of the same text, https://codershigh.github.io/guidelines/ios/human-interface-guidelines/ui-bars/tab-bars/index.html
  and the search summary of https://developer.apple.com/design/human-interface-guidelines/tab-bars,
  2026-09-10 — **[mirror, not the live page]**). SwiftUI's `TabView` with
  more than five tabs spawns a "More" tab, which has its own reported
  navigation-bar problems (https://developer.apple.com/forums/thread/764293).
- Apple's settings guidance: "People don't tend to visit an app's settings
  area very often, so it's important to include only rarely-changed options
  that affect the experience as a whole"; "let people modify task-specific
  options without going to a settings area … make these options available
  in the screens they affect, where they're discoverable and convenient"
  (HIG, Settings — same caveat: quotes via mirror/search summary of
  https://developer.apple.com/design/human-interface-guidelines/settings,
  2026-09-10 — **[mirror, not the live page]**).
- iOS 26 gives the tab bar a floating Liquid Glass style that "can minimize
  on scroll" and a dedicated `role: .search` tab
  (https://www.donnywals.com/exploring-tab-bars-on-ios-26-with-liquid-glass/,
  https://jorgemrht.dev/2025/09/18/liquid-glass-tab-bar, 2025) — it changes
  how five tabs feel, not how many fit.
- The audit capped the app at five: Home / Lineup / Board / Ledger / Trade
  Desk (`docs/APP_MODE.md`, `SiteMap.swift`). `sources.html` — the
  Receipts, the only page the platform plan says the league may see in
  weeks 1–5 — has no destination in the native tab bar.

### The options

| Option | For | Against |
|---|---|---|
| **Sixth tab** | Nothing moves. | Breaks Apple's five, breaks the audit, spawns "More", shrinks every tap target. The differentiator becomes the smallest button. |
| **Under the gear** | Cheap; the gear exists. | Apple's own words: settings are for rarely-changed, whole-app options. Weights are task-specific and change weekly. A product whose thesis is "your model" cannot file the model under Settings next to "Clear saved copies". |
| **Replace a tab** | Keeps five; puts the thesis on the bar. | Something loses its tab. |
| **Absorb into Ledger, renamed "Model"** (recommended) | The Ledger tab already opens the digest whose signature section is *YOUR MODEL* — the source-agreement matrix with the reader's weights as columns. The Receipts grade those same columns. Weights, matrix and receipts are one object: *who you trust, what they said, whether they earned it.* | The rest of the digest (waivers, streaming, trade constructs) needs a home: it is composed from Board, Lineup and Trade Desk already (`engine/digest.py`, "COMPOSITION, NOT REIMPLEMENTATION"), and the Tuesday push deep-links to it regardless of tabs. Home gets a "This week's brief" card. |

### Recommendation, argued from the thesis

"Your model" is the sentence the product says about itself. On a phone the
tab bar is the sentence the app says about itself. If the model is not on
the bar, the app says "here are five views of a league" — Sleeper says that
already, for free. So the model must be a tab, the count must stay five,
and the tab that yields is the one whose unique content *is* the model: the
Ledger.

Concretely:

1. `Destination.ledger` becomes `Destination.model`, title "Model", symbol
   `slider.horizontal.3` (or keep `book.closed` if the ledger identity
   should survive — the receipts are still there). Its page is a new
   `model.html` per person (or `sources.html` grown up), ordered as §4.4:
   population line and share bar → in your model (weights) → library →
   suggested by readers → receipts.
2. The digest keeps rendering as `digest-<league>-week<N>.html`; the Tuesday
   push deep-links to it (`Router.swift` already handles
   `gradedtakes://open?path=<page.html>`); Home shows "Tuesday brief" as a
   card. Nothing about the digest's content or the notification contract
   changes.
3. Every verdict chip everywhere ("Your model says START – 71%") opens the
   existing split popover with one new last line: **"Adjust my model →"**,
   deep-linking to the Model tab with that row's dissenter highlighted.
   That is the in-context entry point Apple's settings guidance asks for,
   and it is where a reader first *wants* to move a slider — the moment a
   voice they trust loses.
4. First run: after the reader connects a league, one screen — "Pick your
   voices" — shows the library's *Suggested for you* rail with the engine
   pre-enabled and the accuracy-informed defaults, and an "I'll use the house
   model" skip. FantasyPros' default is "More accurate experts with recent
   updates"; ours is "the engine, plus anything with 30 graded calls".
5. The gear keeps what it has (link, notifications, saved copies, about) and
   gains nothing from this feature.

If the name "Ledger" must survive, keep it and put the model at the top of
that tab anyway — the content recommendation is the same under either
name. Do not take the slot from Board (the scan-view of every decision,
`engine/board.py`) or Trade Desk (the page with the most strategy in it):
both have content no other tab carries, whereas the digest is by its own
docstring a composition of the others.

---

## 8. Open items and what I could not verify

- FantasyPros' tier gating for custom experts (PRO vs MVP) — third-party
  source only; their support centre blocks fetches. Confirm in a paid
  account before quoting it in marketing comparisons.
- M1's "Equalize" control — third-party mention; not in M1's help articles.
- Action Network's follow flow and the 30-minute non-PRO delay — search
  snippets of Zendesk articles that return 403.
- Spotify Idea Exchange status definitions — same.
- Apple HIG quotations — from a mirror of the HIG text, because the live
  pages are JavaScript-only; the guidance ("three to five tabs"; settings
  for rarely-changed options) is long-standing and consistent across
  mirrors, but re-check against the live HIG before citing Apple in an App
  Store review note.
- Numerai's stake-weighting formula — from search summaries of the forum
  and docs.
- Podchaser's add-podcast form — their page returned 403; the flow is from
  a third-party guide.
- Payload estimate for option A (~9 KB per lineup page) is arithmetic on
  seven sources × thirty rows, not a measurement; measure on a rendered
  week-2 page before committing to the `data-votes` shape.

---

## 9. Sources (all checked 2026-09-10)

FantasyPros
- Consensus cheat sheet page, experts control and "Pick Experts" modal, read
  live in a browser — https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php
- Tools FAQ ("2 to all of the experts", accuracy filters, recency filter) —
  https://www.fantasypros.com/tools/
- In-season accuracy methodology — https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/
- 2025 most accurate experts (2026-01-07) — https://www.fantasypros.com/2026/01/2025-fantasy-football-rankings-most-accurate-experts/
- Dissenting Opinions — https://www.fantasypros.com/nfl/rankings/compare-experts.php
- Cheat Sheet Creator posts (2023-08-03; 2026-08-01) — https://blog.fantasypros.com/08-03-2023-making-the-most-of-the-cheat-sheet-creator/ ; https://www.fantasypros.com/2026/07/how-to-build-a-fantasy-football-cheat-sheet/
- Tier matrix, third party (2026-06-11) [unverified] — https://fantasyjoes.gg/blog/fantasypros-cheat-sheet-creator-free-alternatives

Weighting
- Fantasy Football Analytics: custom weights (2014-06) — https://fantasyfootballanalytics.net/2014/06/custom-rankings-and-projections-for-your-league.html ; accuracy tab (2025-05) — https://fantasyfootballanalytics.net/ffanalytics-web-app-accuracy-tab ; FAQ — https://fantasyfootballanalytics.net/about-the-site/faq
- M1 Finance: edit portfolio — https://help.m1.com/en/articles/9332119-edit-your-m1-portfolio ; custom pies — https://help.m1.com/en/articles/9332122-creating-and-adding-custom-pies-to-your-m1-portfolio
- Numerai docs / forum [search summaries] — https://docs.numer.ai/ ; https://forum.numer.ai/t/about-the-stake-weighted-meta-model/6858
- Action Network projections — https://www.actionnetwork.com/nfl/projections ; follow experts / PRO alerts [403, search snippets] — https://actionnetworkhq.zendesk.com/hc/en-us/articles/360030878072-How-do-I-follow-Experts ; https://actionnetworkhq.zendesk.com/hc/en-us/articles/29108340279821-What-are-PRO-Instant-Expert-Alerts
- Betstamp App Store (v2.8, 2025-01-08) — https://apps.apple.com/us/app/betstamp-bet-tracker-props/id1525948689 ; FAQ — https://www.betstamp.com/faqs

Library UX
- Apple Podcasts for Creators (2023-06-20) — https://podcasters.apple.com/5304-elevating-nine-podcast-subcategories-charts
- AppleInsider, categories incl. Fantasy Sports (2019-08-01) — https://appleinsider.com/articles/19/08/01/apples-podcasts-app-introduces-new-content-categories
- Feedly docs (2022-07-16) — https://docs.feedly.com/article/287-how-to-find-and-add-follow-sources ; Feedly discovery post (2020-08-14) — https://feedly.com/new-features/posts/how-to-discover-the-best-content-on-feedly
- Substack recommendations (2022-04-12) — https://on.substack.com/p/recommendations

Suggestion loops
- Pocket Casts submitting podcasts — https://support.pocketcasts.com/knowledge-base/submitting-podcasts/
- Podchaser add [403; third-party guide] — https://www.podchaser.com/add ; https://riverside.com/blog/podchaser-submit-podcast
- Canny post statuses (2026-06-05) — https://help.canny.io/en/articles/673583-post-statuses
- Spotify Idea Exchange guidelines [403; search snippets] — https://community.spotify.com/t5/FAQs/Idea-Exchange-Guidelines-What-do-I-need-to-know-before/ta-p/5171172
- GitHub issue forms syntax — https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms

Persistence and platform
- MDN `localStorage` — https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- Cloudflare Pages Functions bindings — https://developers.cloudflare.com/pages/functions/bindings/
- Supabase pricing — https://supabase.com/pricing
- Apple HIG tab bars [live page JS-only; mirror] — https://developer.apple.com/design/human-interface-guidelines/tab-bars ; https://codershigh.github.io/guidelines/ios/human-interface-guidelines/ui-bars/tab-bars/index.html ; SwiftUI >5 tabs thread — https://developer.apple.com/forums/thread/764293
- Apple HIG settings [live page JS-only; mirror/search] — https://developer.apple.com/design/human-interface-guidelines/settings
- iOS 26 tab bar behaviour — https://www.donnywals.com/exploring-tab-bars-on-ios-26-with-liquid-glass/ ; https://jorgemrht.dev/2025/09/18/liquid-glass-tab-bar

Internal
- `design/plan/platform.md` (hosting, creator programme, notifications, Phase 1 architecture)
- `data/sources.yaml`, `engine/consensus.py`, `engine/sources_ui.py`, `engine/sources_page.py`, `engine/digest.py`, `publish.py`, `users.yaml`, `docs/APP_MODE.md`, `ios/GradedTakes/Model/SiteMap.swift`, `ios/GradedTakes/UI/SettingsView.swift`
