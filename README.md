# Graded Takes

The fantasy decision engine: your teams, read by one model, as pages you
open (`home.sh`, `lineup.sh`, `board.sh`, `season.sh`, `tradedesk.sh`),
as an installable web app, and as the Graded Takes iPhone app (`ios/`).
"War Room" was the working title; it survives only in internal names -
the repo folder, `warroom.py`, the `wr-` CSS prefix, cache and launchd
labels - never on a page.

It began as a local draft-day decision engine for live snake drafts. You
paste picks as they happen; when you are on the clock it tells you who to
take and why.

Built for **"Kid's Table"** — Yahoo, 10 teams, full PPR, two flex spots,
16 rounds, 30-second clock.

## In-season: the pages

`./home.sh` opens the landing page - both leagues, what needs you this
week (with deep links into ESPN/Yahoo), rosters, exposure. From there the
top bar reaches the Board, the Ledger, the Trade Desk, the Sources page and
Model Settings. See RUNBOOK.md section J for the page map.

The same pages run inside the iPhone app, which draws its own header and
tab bar: it stamps `<html data-app="ios">` and the pages hide their own
shell chrome in answer. The contract is one attribute, documented in
[`docs/APP_MODE.md`](docs/APP_MODE.md).

## Draft night, in three lines

```bash
./start.sh
```

Then, as soon as Yahoo shows the draft order:

```
slot 7
```

Then paste picks as they happen. That's the whole workflow.

## Setup (once)

```bash
./setup.sh
```

Creates the virtualenv, installs PyYAML (the only dependency), and seeds
player data from Fantasy Football Calculator's free ADP API.

## How you use it under the clock

**Pasting picks is the main loop.** Paste one pick or the entire Yahoo
draft-results panel — both work, in almost any format:

```
Pick 14: CeeDee Lamb
1.05 Puka Nacua
Christian McCaffrey RB - SF
Lamb, DAL
```

Pasting is **idempotent**: re-paste the same block, or an overlapping one, as
often as you like. Already-known picks are ignored, only new ones apply. If you
fall behind during a fast run of picks, select the whole results panel, paste
once, and you are caught up.

When the board reaches your pick, the recommendation block prints itself. No
command needed.

### The on-clock block

```
==========================================================================
 ON THE CLOCK   pick 24  (3.04)   round 3
  PICK >>  Zay Flowers (WR-BAL bye13)
           R3 TARGET; fills WR2; won't last (2%)
--------------------------------------------------------------------------
  ALTERNATES
   2. Garrett Wilson (WR-NYJ)     2% back  R3 TARGET; fills WR2
   3. Kenneth Walker (RB-KC)      4% back  fills RB2; LAST in RB Tier 3
   4. Trey McBride (TE-ARI)      17% back  fills TE1; LAST in TE Tier 1
--------------------------------------------------------------------------
  SURVIVAL to my next pick 4.07 (13 picks away)
   Flowers 2% | Wilson 2% | Walker 4% | McBride 17%
--------------------------------------------------------------------------
  TIERS
   ! RB: LAST in Tier 3 (Kenneth Walker) - next RB tier ~4 picks out
   ! WR RUN: 3 of the last 5 picks were WR
--------------------------------------------------------------------------
  STRATEGY  branch A (Elite RB anchor)   ON SCRIPT
   R3 plan: prefer WR; targets: CeeDee Lamb, Justin Jefferson, Rashee Rice
==========================================================================
```

Read it top down and stop whenever you are satisfied. Line one is the answer.

**"back" / "SURVIVAL"** is the rough chance that player is still there at your
*next* pick. It is the reason to take someone now rather than later: a 2% means
he will not come back to you, a 48% means you can wait a round.

### Commands

| Command | What it does |
|---|---|
| *(paste)* | apply one pick or a whole block |
| `sync` | bulk-paste mode: paste many lines, end with a blank line |
| `me` | reprint the on-clock block |
| `board [pos]` | best available (`board wr`, `board rb`) |
| `roster [n]` | your roster, or team n's |
| `needs` | what every team still needs to start — who is likely to take what |
| `status` | pick, round, branch, script adherence |
| `slot <n>` | set your draft slot |
| `pivot <branch>` | switch strategy branch (`pivot B`) |
| `undo` | undo the last pick |
| `find <name>` | look up a player: taken or available, and survival odds |
| `quit` | exit — state is already saved |

## If something goes wrong

**State is saved after every single pick**, atomically, to `saves/`, plus an
append-only log of every pick. Nothing is ever lost.

If the terminal dies, the laptop reboots, or you need to restart:

```bash
./start.sh --resume
```

You are back exactly where you were. If a name matched the wrong player, type
`undo` and paste it again more specifically (add the position or team).

## The strategy file — the real point of this tool

`strategies/yahoo-main.yaml` is your contingency tree, written **before** the
draft. It defines:

- **branches** — opening-round scenarios (elite RB available, elite WR
  available, late-first best-available), each with round-by-round positional
  targets and named players
- **watch rules** — conditions checked after *every* pick, e.g. "8+ RBs gone by
  pick 20", "3 of the last 5 picks were WR", "both elite TEs gone"
- **pivots** — when the board says abandon the plan, and which branch to switch to
- **do_not_draft** — players you will not take at any price

During the draft the engine tracks which branch you are on, tells you whether
you are `ON SCRIPT`, and raises a `>> PIVOT` flag with the reason when a trigger
fires. You confirm with `pivot B`, or set `auto: true` on a rule to let it
switch by itself.

The shipped tree uses real 2026 ADP names but they are **placeholders for your
own opinions** — edit it before the draft.

## Player intel — your research, applied automatically

`data/player_intel.yaml` holds the conviction buys, fades, and injury watches
from your Four-Layer Deep Dive research. Each entry moves a player's score and
prints its reason on screen, so you see *why*:

```
  PICK >>  Jonathan Taylor (RB-IND bye13)
           R1 TARGET (reach OK); true bell cow (73.1% rush share) - prefer over McCaffrey
```

```
> find McCaffrey
  Christian McCaffrey  RB  SF  rank 7  tier 2  ADP 6.6  available | 1% to reach my next pick
     FADE -18  FADE at RB3: turns 30, league-high 413 touches in 2025, camp 'tightness'
```

Fades live here rather than in `do_not_draft` because they mean "not at this
price," not "never." `adjust` is in score units: roughly ±15 moves a player a
round, ±6 breaks a tie. Editing this file is the fastest way to act on news
right up until the draft — if McCaffrey is cleared at 8pm, soften his number.

The Weeks 15–17 playoff-schedule tilt (Commanders/Saints/Cardinals/49ers up,
Eagles/Seahawks down) applies only from round 8 on, as a tiebreaker.

### Your calls override the research

`data/my_calls.yaml` loads **after** the research and wins outright — an
explicit opinion is a replacement, not a second vote. Three things live there:

- **`players`** — your own adjustments. Disagree with the McCaffrey fade? Set
  him to `adjust: 0` and the research's −18 is gone.
- **`never_draft`** — hard exclusions, never recommended at any price.
- **`managers`** — what each of the other nine actually does. This is the one
  input no public research has, and it feeds straight into survival odds: the
  generic model assumes rivals draft by ADP and roster need, so it goes blind
  once a team's starters are full. Telling it "slot 4 hoards RBs" or "slot 7
  reaches for Ravens players" measurably sharpens the turn-pick math.

Editing this file mid-draft takes seconds — it is the fastest way to act on
news that breaks while you are drafting.

> **Format note:** the research was written for half-PPR. This league is **full
> PPR** (Receptions = 1, per the league settings). That pushes pass-catching
> backs, high-target WRs, and the elite TEs slightly further up than the doc's
> numbers imply — the strategy tree already leans that way.

## Your own rankings

Replace `data/rankings.csv` with your export. See
[data/RANKINGS_FORMAT.md](data/RANKINGS_FORMAT.md) — only `name` and `pos` are
required, and your `rank` and `tier` columns are what make the advice yours.

## Other leagues

Each league gets its own config in `leagues/` and its own strategy file. Same
player pool, different values, because scoring and roster shape change what a
position is worth.

```bash
LEAGUE=espn-1 ./start.sh
```

## Practice drafts (free, offline, your exact league)

```bash
./practice.sh
```

A full mock draft against 9 bots that pick using live ADP plus roster-need
logic, each with a different temperament every run — so every practice draft
plays out differently. Your picks work exactly like the real draft console: type a
name, read the block, decide. `fast` auto-picks the engine's #1 for a round if
you want to skim ahead; `undo` rewinds your last pick (and the bots after it).
Practice state is separate from the real draft and never touches it.

## Self-test

Simulates a full 10-team draft through the real ingest path and checks the
parser, snake order, tiers, survival odds, pivots, crash recovery, and
idempotent syncing:

```bash
.venv/bin/python tests/mock_draft.py
```

## After the draft: grade it

```bash
./grade.sh                                  # latest save for $LEAGUE (default yahoo-main)
./grade.sh saves/yahoo-main-20260829.json   # a specific save
LEAGUE=espn-1 ./grade.sh                    # another league
```

Works mid-draft or after: pick-by-pick steal/reach labels, best-lineup
totals, positional gaps, and trade-ammo surpluses for every team, yours
highlighted.

## In-season: the weekly loop

One command produces the whole week ahead as a single self-contained HTML
page — waiver shortlist with FAAB bid bands (or burn-priority guidance when
the league yaml says `waiver_mode: priority`), lineup verdicts and red alerts,
a DEF/K streaming plan, trade constructs, and injury flags on your roster:

```bash
./season.sh                  # yahoo-main, current NFL week
./season.sh yahoo-main 3     # any league, any week
./season.sh espn-1 3 --force # force fresh feeds even when caches look fine
```

It writes `digest-<league>-week<N>.html` to the project root and opens it.
The page is honest about what it does not know: a coverage banner rides on
top whenever your roster file is partial, and any section whose feed is down
renders with a visible "degraded" note instead of silently vanishing. The
digest writes only under `data/cache/` (feed snapshots — with ESPN cookies
present that includes the `%owned` snapshot momentum needs) plus the HTML
page itself; it never touches `saves/`, rosters, or the streaming log.

Each section is a standalone CLI when you want more depth than the digest
shows (all support `--help`):

```bash
.venv/bin/python -m engine.waivers   --league yahoo-main --week 3   # per-component waiver scoring + drop candidate
.venv/bin/python -m engine.lineup    --league yahoo-main --week 3   # best legal lineup, close calls as verdicts
.venv/bin/python -m engine.streaming --league yahoo-main --week 3   # DEF/K plan over a multi-week horizon
.venv/bin/python -m engine.trades    --league yahoo-main            # market vs. our values; --offer "give: A | get: B"
.venv/bin/python -m engine.keeper    "Player Name" --cost-round 5   # keep-vs-throwback verdict
```

Roster files live in `data/rosters/<league-id>.yaml`; the more of your roster
they know, the sharper every verdict gets. RUNBOOK.md section F walks the
weekly loop; sections A1–A4 are the five-minute unlocks (rosters, ESPN
cookies, Yahoo OAuth) that lift the coverage banners.

### The board — the same week as one picture

Where the digest is a briefing you read, **the board is a picture you scan**:

```bash
./board.sh                    # espn-1, current NFL week
./board.sh yahoo-main 3       # any league, any week
```

It writes `board-<league>-week<N>.html` — one page per league — and opens it.
The centrepiece is a matrix: **rows are your players** (STARTING, then
BENCH), **columns are your enabled sources** ordered by weight, then YOUR
MODEL. Each column header is that source's face (picture or monogram), its
weight and its current form. Every cell is a verdict chip encoded by weight,
never hue — a gold fill for START, a ghost outline for SIT, a hollow dash
for *no opinion filed* — and hovering one shows that source's quote or the
reason behind its vote. Rows where the voices point both ways carry a
**◆ SPLIT** marker; rows where your single heaviest-weighted source dissents
from your model or the engine carry the gold **◆ TOP SOURCE DISSENTS** — the
alarm worth acting on. Below the matrix: a divergence panel that sorts those
disagreements widest-split-first with a one-line reason from *both* sides,
your waiver adds and named trade targets in the same matrix shape (so a
candidate reads exactly like the player he would replace), and every other
team in the league with its positional surplus/hole tags, your cross-league
holdings marked ALSO MINE, and your trade targets marked on the roster that
holds them. Same honesty rules as the digest: each section degrades with a
visible banner, an empty source column means *nothing was extracted*, and the
board is read-only — it never records source-ledger votes. The scoreboard
links to `sources.html` (The Receipts — `./sources_page.sh`): one card per
source with its decay-blended hit rate, sample, streak, sparkline, position
and start/sit splits, and the archive phase-out schedule. RUNBOOK.md section
J has the detail.

### Your Model — your inputs, your weights, your formula

Register the model inputs you trust in `./sources.sh` (Model Settings:
YouTube channels, RSS, article URLs — X/Twitter is paste-only, by ToS)
with 0–100 weights, run
`.venv/bin/python -m engine.calls --week N` to mine their start/sit calls
(every auto-extracted call carries a confidence tier and the verbatim
quote), and every lineup decision becomes your model's weighted vote: the
engine's own verdict, ESPN and Sleeper projections, Boris Chen tiers, and
your creators. Close calls in `engine.lineup` grow a strip of your model's
inputs (`ENGINE start | YourCreator sit (high, "…") | ESPN start` →
`Your model says START - 71%`), the digest gains "YOUR MODEL" — an
agreement matrix that flags UNANIMOUS /
MAJORITY / SPLIT / LONE-DISSENT and highlights when your top-weighted voice
disagrees with the engine — and `data/source_ledger.jsonl` keeps receipts:
votes are logged before games, scored against positional replacement after,
and a per-source hit-rate scoreboard appears once two weeks are graded.

## League connections

**Nobody is ever asked for a password or a browser cookie.** Not a friend, not
a leaguemate, not "just for testing". A pasted session cookie is credential
sharing, not consent, and it breaks the host platform's terms for the person
who sends it. Every route below is either public data, an OAuth grant the
person makes on the platform's own consent screen, or text they chose to send.
All three are read-only: nothing here ever writes to ESPN, Yahoo or Sleeper.

- **Sleeper** — a username, and nothing else (`engine/connections.py`). Public
  read-only API: no auth, no keys, no setting for them to change. Resolves the
  handle, lists their leagues, imports one. This is the model the other two
  are held to.
- **ESPN, anyone's league** — no credential, two ways, both in
  [`docs/CONNECT_ESPN.md`](docs/CONNECT_ESPN.md) (the note you send *them*):
  - *Public league* — the commissioner flips **Make League Viewable to
    Public**, sends the `leagueId=` number, and `engine/espn_public.py` reads
    it with no login and refreshes itself.
  - *Roster paste* — they send the roster text instead. Same pages; the league
    is stamped `PASTE-FED`, `auto_refresh: false`, and every value we had to
    default is listed in `assumed:` rather than passed off as a reading.
- **ESPN, the owner's own league** — cookie API (`SETUP_ESPN.md`, then
  `./espn.sh check`), using the ESPN account signed in on this Mac and no
  other. Built: settings pull, live-draft auto-ingest (`./espn.sh draft`),
  draft-history tendency mining. That file is for the owner only — for anyone
  else's league it is the two cookie-free routes above.
- **Yahoo** — OAuth, one registered app, many people
  ([`SETUP_YAHOO.md`](SETUP_YAHOO.md) is the owner's one-time registration;
  [`docs/CONNECT_YAHOO.md`](docs/CONNECT_YAHOO.md) is the note you send them).
  Their cost is one link, one **Allow** on Yahoo's own page, and a short code
  read back — never a password, and they can revoke it from their Yahoo
  account settings without asking. Read-only scope (`fspt-r`) only. Built:
  connection check and league/roster pull. Live Yahoo drafts still ingest by
  paste — deliberately, because paste is faster than Yahoo's API tick.
  **Requires the owner to have registered the app**; Yahoo's Fantasy API
  access is a reviewed application and is not instant.

Cross-league exposure (the `expo` command in the draft console, and banners in the
in-season tools) reads every `data/rosters/*.yaml`, so your other league's
holdings surface while you draft or set lineups.

## What it deliberately does not do

No automated Sunday lineup auto-swap: enable ESPN/Yahoo app push
notifications for inactives instead (RUNBOOK C1) — five minutes, covers the
kill case without a robot touching your lineup. And nothing here ever writes
to your league sites: every tool is read-only toward Yahoo/ESPN; you make the
actual clicks.
