# RUNBOOK — Andrew's homework

Everything below needs YOU (credentials, your data, or a decision). The engine
work that didn't need you was built overnight and is covered in the debrief.
Ordered by leverage. Times are honest estimates.

## A. Unblock the data (do these first)

- [x] **A1 DONE — ESPN draft complete (Aug 29).** Full league captured:
      all 8 rosters, 136-pick record, tendencies mined for every rival. Everything in-season
      hangs off this: if it happened, paste your final roster (any format);
      if it didn't happen or got rescheduled, say when.
- [x] **A2 DONE (Sep 4) — full 16-man Yahoo roster on file** (read off your
      screenshots). Re-paste after roster moves, or paste the whole league's
      rosters in Model Settings -> Leagues to unlock rival trade targets there.
- [x] **A3 DONE — ESPN cookies connected (draft day).** — SETUP_ESPN.md steps 1-3 (league ID +
      espn_s2 + SWID into data/espn_secrets.json), then:
      `./espn.sh check`
      Unlocks: league settings pull, rival-tendency mining from draft history,
      FAAB history, %owned deltas, transactions feed — the in-season spine.
- [ ] **A4 (5 min) Yahoo OAuth** — SETUP_YAHOO.md (register app, one browser
      handshake), then `./yahoo.sh check`. Unlocks Yahoo roster/waiver sync.
      Lower priority than A3 if pressed for time.

## B. Decisions only you can make

- [ ] **B1 Review the market-study top-5** (artifact: War Room Market Study,
      "Your decision" box). I proceeded on all five as the likely decision —
      strike or reorder anything and I'll adjust.
- [ ] **B2 Confirm keeper rules.** Are either of your leagues keeper formats?
      The keep-vs-throwback calculator is built but idle until you confirm
      (and keeper deadlines can fall BEFORE draft day next season).
- [ ] **B3 League-2 reseed values.** When ESPN settings are known (A3 or
      screenshots), the per-league data rebuild is one command sequence —
      documented in docs/PER_LEAGUE.md. I can run it the moment settings land.

## C. Five-minute phone tasks

- [ ] **C1 Enable ESPN + Yahoo app push notifications for inactives.** This
      replaces the "Sunday-morning auto-swap failsafe" the market study
      recommended NOT building. 5 minutes, covers the kill case.

## D. When you have 20 minutes

- [ ] **D1 Yahoo paste-drill rehearsal** (before your next live Yahoo draft,
      not urgent now): run a Yahoo mock room and practice the bulk-paste flow
      end-to-end once, so the degraded path is muscle memory.

## E. Before your next live draft

- [ ] **E1 (2 min) Warm the data caches.** Both CLIs now do this automatically
      at startup ("warming data caches..."), but run it once the morning of a
      draft so the first startup of the day never waits on the ~16MB injury
      dump or the nflverse games files:
      ```
      .venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()"
      ```
- [ ] **E2 (5 min, needs A3 cookies) Mine rival tendencies from real ESPN
      draft history.** The miner is built and tested on synthetic drafts; the
      live ESPN pull is the one untested leg. After `./espn.sh check` works:
      ```
      .venv/bin/python -c "
      from engine import espn
      from engine.tendencies import Tendencies
      t = Tendencies.from_espn([espn.connect(2025)])
      print(t.summary())
      print('rows written:', t.emit_yaml('data/tendencies.espn-1.yaml'))"
      ```
      Add more seasons to the list for a stronger read. Manager ids are ESPN
      teamIds, NOT draft slots — pass `slot_map={teamId: this_years_slot}` to
      `emit_yaml` once the draft order is known. Nothing else to wire up:
      both CLIs auto-load `data/tendencies.<league-id>.yaml` at startup,
      merged AFTER `data/player_intel.yaml` and BEFORE `data/my_calls.yaml`,
      so your own manager reads always win (see engine/tendencies.py header).
- [ ] **E3 (1 min) Grade a draft afterward.** Works mid-draft or after:
      ```
      ./grade.sh                                  # latest save for $LEAGUE (default yahoo-main)
      ./grade.sh saves/yahoo-main-20260829.json   # a specific save
      LEAGUE=espn-1 ./grade.sh                    # latest save for another league
      ```
      Pick-by-pick steal/reach labels, best-lineup totals, positional gaps,
      and trade-ammo surpluses for every team, yours highlighted.

## F. The in-season weekly loop (built — nothing to set up, just run it)

These run today. Every one degrades honestly — a banner tells you exactly
what it does not know (e.g. "PARTIAL ROSTER: known 3/16" until A2 lands, and
%owned/FAAB history joins once A3 lands) — and they all sharpen automatically
the moment those items above are done.

- **F1 (1 command) Tuesday digest — the one to actually run each week:**
  ```
  ./season.sh                  # yahoo-main, current NFL week
  ./season.sh yahoo-main 3     # any league, any week
  ./season.sh espn-1 3 --force # force fresh feeds
  ```
  Warms the feed caches, writes `digest-<league>-week<N>.html` to the project
  root (self-contained HTML, no scripts, no external fetches), and opens it
  in your browser. One page: waiver shortlist + FAAB bands (burn-priority
  guidance instead in `waiver_mode: priority` leagues like espn-1), lineup
  verdicts, DEF/K streaming plan, trade constructs, injury flags. Writes only
  under data/cache/ (feed snapshots — with ESPN cookies that includes the
  %owned snapshot momentum needs) plus the digest HTML — never saves/ or the
  streaming log. If a feed is down the section renders with a visible
  "degraded" note instead of silently vanishing.
- **F2 Waiver deep-dive** (more rows + per-component scoring than the digest):
  ```
  .venv/bin/python -m engine.waivers --league yahoo-main --week 3
  ```
- **F3 Lineup check** (best legal lineup, every close call framed as a verdict):
  ```
  .venv/bin/python -m engine.lineup --league yahoo-main --week 3
  ```
- **F4 DEF/K streaming plan** (multi-week horizon; appends to the humility
  ledger `data/streaming_log.jsonl` unless you pass `--no-log`):
  ```
  .venv/bin/python -m engine.streaming --league yahoo-main --week 3
  ```
- **F5 Trade analyzer** (market vs. our projections; evaluate a real offer):
  ```
  .venv/bin/python -m engine.trades --league yahoo-main
  .venv/bin/python -m engine.trades --league yahoo-main \
      --offer "give: Player A | get: Player B"
  ```
- **F6 Keeper calculator** (when B2 confirms a keeper format):
  ```
  .venv/bin/python -m engine.keeper "Player Name" --cost-round 5
  .venv/bin/python -m engine.keeper --list      # batch from data/keepers.yaml
  ```
- **F7 The weekly cadence** (what to run on which day):
  | day | action |
  |---|---|
  | **Tue** morning | `./season.sh` — the digest. Waivers process Tuesday in Kid's Table (FAB), so FAAB bids go in **Monday night** off last week's digest; Tuesday's fresh digest confirms what cleared and queues this week's. |
  | **Wed** | claims settled — re-run `./season.sh` if you won/lost bids, so lineup and streaming reflect the real roster. |
  | **Thu** before kickoff | `.venv/bin/python -m engine.lineup --league yahoo-main --week N` — TNF starters lock first; the verdicts flag anyone kicking off Thursday. |
  | **Sun** morning | same lineup command for the final pass (late injury flags), plus a streaming sanity check: `.venv/bin/python -m engine.streaming --league yahoo-main --week N` before locking DEF/K. |
- **F8 (OPTIONAL, you run it — nothing is installed for you) Auto-digest
  every Tuesday 7am via launchd.** Save this as
  `~/Library/LaunchAgents/com.warroom.tuesday-digest.plist`:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
    <key>Label</key><string>com.warroom.tuesday-digest</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>-c</string>
      <string>cd "/Users/andrewbrown/Desktop/War Room" &amp;&amp; ./season.sh yahoo-main</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Weekday</key><integer>2</integer>
      <key>Hour</key><integer>7</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>/tmp/warroom-digest.log</string>
    <key>StandardErrorPath</key><string>/tmp/warroom-digest.log</string>
  </dict>
  </plist>
  ```
  Install / remove (your call, run by hand):
  ```
  launchctl load   ~/Library/LaunchAgents/com.warroom.tuesday-digest.plist
  launchctl unload ~/Library/LaunchAgents/com.warroom.tuesday-digest.plist
  ```
  Under launchd there is no terminal, so the page is written but not
  auto-opened — it waits at `digest-yahoo-main-week<N>.html` in the project
  root (run log: `/tmp/warroom-digest.log`). Weekday 2 = Tuesday in
  launchd's calendar (0 = Sunday).
- **F9 Reminder — fill `data/rosters/yahoo-main.yaml` to the full 16 to
  unlock everything.** Every F-section tool runs positive-only on the 3/16
  names known today: waiver candidates can include players you already own,
  the drop pick and trade ammo are drawn from 3 players, and the lineup
  shows open slots that aren't really open. One paste (A2, 1 minute) lifts
  the PARTIAL ROSTER banner everywhere at once. Same for any new league:
  `data/rosters/<league>.yaml` with `league`, `name`, `size`, `players:`.

## G. Post-draft (ESPN)

- [ ] **G1 (0 min — automatic) Tuesday digest** now covers the real league:
      `./season.sh espn-1`
- [x] **G2 Done:** this league's waivers are inverse-standings priority,
      NOT FAAB — `waiver_mode: priority` in leagues/espn-1.yaml now flips
      the waiver engine and digest to burn-priority guidance (opportunity
      cost vs the next-best free-agency fallback, plus the queue-position
      reminder: slot 1 starts the season 8th of 8, resets weekly by
      inverse standings). FAAB bands still apply to Yahoo
      (`waiver_mode: faab`).
- [ ] **G3 Week 1 lineups due before Thu Sep 4 kickoff:**
      `.venv/bin/python -m engine.lineup --league espn-1 --week 1`

## H. Your Model — your inputs, your weights, your formula (built; add your creators once, then it rides the weekly loop)

The engine's four built-in inputs (its own lineup verdict, ESPN and Sleeper
projections, Boris Chen tiers) already vote on every lineup decision. Add
the YouTubers/writers YOU trust and their start/sit calls join the same
weighted vote — your model's verdict ("Your model says START - 71%") under
each close call in `engine.lineup`, the "YOUR MODEL" agreement matrix in
the digest, and a per-source hit/miss ledger
that shows who has actually been right.

- [ ] **H1 (2 min) Add your creators:** `./sources.sh` (Model Settings) —
      paste a YouTube
      channel URL/@handle or an RSS/article URL, set a 0–100 weight
      (relative; normalized at vote time — weight a creator above the
      engine's 40 and the digest flags every player where your top voice
      disagrees with the math). Toggle and reweight any time; the four
      built-in feeds live in the same list (`data/sources.yaml`).
- [ ] **H2 Weekly, before the digest:** run
      ```
      .venv/bin/python -m engine.calls --week N
      ```
      It pulls each enabled creator's latest videos/articles (YouTube
      transcripts via caption tracks, no API key) and mines start/sit/rank
      calls into `data/creator_calls/week-N.yaml`. Extraction is crude ON
      PURPOSE: every auto-call carries a confidence tier and the verbatim
      quote it came from, and a failed source shows up as FAILED, never as
      silently-zero calls. Then `./season.sh` as usual — the digest's
      YOUR MODEL section banners itself when creators are enabled but no
      calls were ingested this week.
- **H3 X/Twitter is paste-only — permanently.** X's Terms of Service
  prohibit scraping, the API is paywalled, and logged-out HTML breaks
  silently, so nothing in this repo will ever fetch x.com (documented in
  engine/sources.py). To count a tweet: add a `paste`-type source in
  `./sources.sh` and paste the text in by hand; it flows through
  extraction like any transcript, provenance attached.
- **H4 (optional) The Claude pass:** the week file IS the API. When the
  regex extractor misses sarcasm or a hedge, read/watch the source
  yourself (or have Claude do it) and write calls straight into
  `data/creator_calls/week-N.yaml` in the same shape — `confidence: high`
  plus a real quote. Hand-written entries are never clobbered by a later
  auto-ingest (first write wins) and flow into your model identically.
- **H5 The receipts:** each digest render logs every input's votes to
  `data/source_ledger.jsonl` BEFORE outcomes are known (keyed per league —
  two leagues weighing the same player keep separate rows and separate
  grades), then scores last
  week's votes once actuals land (hit = a start-side call whose player
  outscored his positional replacement; rule documented in
  engine/consensus.py). After two scored weeks the digest shows the source
  scoreboard — including whether YOUR favorite creator beats the engine.

## I. Platform roadmap (sequenced per Andrew, Aug 30)

Priority order is deliberate - features/model first, brand polish second,
name last:

0. **DECIDED (Sep 2026):** digest-first product, league switcher,
   advise-only as principle, mobile-web quality. Platform path per Andrew:
   local now -> ONE WEEK of league beta with The Original 8 -> then
   public-platform setup (hosting, accounts, per-user credentials, and a
   hard-gate commercial re-audit of every data feed before launch).
0b. **DECIDED (Sep 10, 2026): per-user data lives in Supabase.** The owner's
   existing Supabase Pro org (Pro, not Free - Free pauses after 7 idle days
   and this product is idle Feb-Aug). First use: the Model page - each
   reader's source weights and enabled sources, keyed by their private-link
   fingerprint until real auth arrives; the weekly render reads them so the
   digest and notifications honour what the reader set. Write path = a
   small Vercel function holding the service key; pages never carry a
   Supabase key. Later: Yahoo tokens (Vault), the accuracy ledger,
   suggestions queue, magic-link auth.
1. **DONE - Model Settings** (creator inputs + weights + consensus):
   shipped, gated, branded.
2. **NEXT - grounded UI mockups**: navy/gold family (#101B33 / #182848 /
   #F2B722), patterns researched from ESPN/Action Network/Sleeper/Underdog
   - not AI defaults. New brand boards follow the research.
3. **DOWNSTREAM - one-click league connections**: guided connect flows for
   Yahoo, ESPN, and Sleeper (Sleeper is username-only - easiest); Andrew
   self-tests the onboarding with his own accounts when built.
4. **DOWNSTREAM - keeper leagues setting**: none of Andrew's leagues keep,
   but ship it as a per-league toggle (engine.keeper already exists).
5. **DONE - name + domain: Graded Takes, gradedtakes.com.** The pages'
   wordmark, the manifest, install.html and the docs say Graded Takes;
   "War Room" stays only in internal identifiers (repo folder, `warroom.py`,
   `wr-` CSS prefix, `com.warroom.*` launchd labels, cache names).
   (Candidates weighed as of Aug 30 whois: leaguewarroom, mymodelfantasy,
   sundayformula, myfantasymodel, modelroomhq, weightedroom, yourmodelhq,
   modelballhq, secretformulahq.)

## J. THE BOARD — the whole week as one picture (built; run it beside the digest)

The digest is a briefing you read top to bottom. **The board is a picture you
scan.** It answers one question in one screen: *who am I starting, benching,
adding and shopping — and where do the voices I listen to disagree with my
model?*

- **J1 (1 command) — run it:**
  ```
  ./board.sh                    # espn-1, current NFL week
  ./board.sh yahoo-main 3       # any league, any week
  ./board.sh espn-1 3 --force   # force fresh feeds
  ```
  Warms the caches, writes `board-<league>-week<N>.html` to the project root
  (self-contained HTML — nothing fetched at open time, the faces and the
  typefaces are embedded; light and dark via the shared CSS tokens), refreshes
  `sources.html` beside it, and opens it. One page **per league**; the shell's
  league switcher flips between the leagues' board files.
  ```
  ./sources_page.sh             # The Receipts alone: sources.html
  ./sources_page.sh 3 --league yahoo-main
  ```
  (`./sources_page.sh` is the READ page; `./sources.sh` is still Model
  Settings, the panel that edits the registry.)

- **J2 — what the five sections show:**
  1. **Header** — league, week, record, and the coverage line: how many
     rosters are actually known, plus every enabled source with its weight
     and its real share of the room.
  2. **My roster matrix** (the centrepiece) — rows are your players grouped
     STARTING / BENCH; columns are your **enabled sources ordered by
     weight**, then YOUR MODEL. Each column header is that source's **face**
     (its picture, or a monogram), its weight and its current form — hover
     for the name and the record. Every cell is a verdict chip encoded by
     *weight*, never hue: a gold fill is START, a ghost outline is SIT, a
     dashed outline is a lean, a hollow “—” is *no opinion filed*. Hover any
     chip for that source's quote or the reason behind its vote. There is no
     green and no red anywhere on the page.
  3. **Divergence panel** — the disagreements pulled out and sorted, **widest
     split first**, one card each: the START side and the SIT side as chips
     with the faces of the voices on each side and a one-line reason from
     **both**, the model's weighted call, and — when your heaviest voice is
     the dissenter — the alarm as a gold-rule callout. Expand “every voice on
     X” for the full row.
  3b. **Source scoreboard** — one row per source: face, weight, the
     decay-blended headline hit rate labelled with what it is made of
     (“63% · 2025 archive”, the mix in its tooltip), sample, current form,
     streak, sparkline and provenance. Creators who have never been graded
     read NO-DATA. The full receipt per source — position splits, start
     calls against sit calls, and the archive phase-out schedule (100% →
     60% → 30% → 0% by completed week) — is `sources.html`.
  4. **Wire** — waiver adds and named trade targets rendered in the **same
     matrix shape**, so a candidate reads exactly like an owned player and
     the two can be compared at a glance. The model column swaps start/sit
     for the add verdict (FAAB band, or burn-priority in espn-1) or the trade
     verdict.
  5. **League view** — every other team as a compact column with its
     positional surplus/hole tags, your cross-league holdings marked ALSO
     MINE, and your named trade targets marked TARGET on the roster that
     holds them.

- **J3 — the two markers worth acting on.** A row where the voices point both
  ways gets a slate **◆ SPLIT**. A row where your single **heaviest-weighted
  source** dissents from your model or from the engine gets the gold **◆ TOP
  SOURCE DISSENTS** — that is the alarm: the voice you trust most is telling
  you something your blend is outvoting. Both markers say so in words, not
  colour alone.

- **J4 — an empty column is the finding, not a bug.** A creator source with
  no chips in any row means *nothing was extracted from that source this
  week* — not that it agrees. When creator sources are enabled and the week's
  calls file is empty the matrix says so and prints the fix:
  ```
  .venv/bin/python -m engine.calls --week 3
  ```

- **J5 — what it degrades to.** Each section carries its own banner rather
  than vanishing. Today: **espn-1** is the full picture (8 of 8 rosters known
  from the draft capture, so trade targets are named and the waiver pool
  excludes the 119 players rivals hold); **yahoo-main** knows only your own
  roster of 10 teams, so the league view says “1 of 10 rosters known”, the
  wire prints RIVAL ROSTERS UNKNOWN and falls back to trade *constructs*
  (shapes, not named offers). Paste the missing rosters in Model Settings
  (`./sources.sh` → Leagues) to close that gap.

- **J6 — write discipline.** The board is **read-only** apart from the one
  HTML file. In particular it does **not** record source-ledger votes — that
  stays the digest's job, so opening the board twice can never inflate a
  source's track record.

Acceptance tests: `.venv/bin/python tests/board_test.py` and
`.venv/bin/python tests/sources_page_test.py`.

---
*Sections are appended as overnight waves complete; item IDs are stable.*

## J. The pages — what to open (v3 design, Sep 6)

Seven static pages, one navigation bar, one identity: light paper with navy
ink and a single gold accent. No green, no red anywhere - START is a gold
fill, SIT a ghost outline, a toss-up is dashed; attention is a gold rule.
Sources are faces (The Favorites' avatar, Sharp or Square's art, monograms
for the feeds). Dark mode is the toggle in the top-right; it remembers.
Every page fetches nothing at open time (fonts and faces are embedded).

| open | command | what it is |
|---|---|---|
| **home.html** | `./home.sh` | START HERE. Both leagues. "Needs you this week" inbox with a verb that deep-links into ESPN/Yahoo to fix it, the week's game windows with first lock marked, league cards, icon-driven rosters, cross-league exposure, source pulse, jump box. |
| lineup-<league>-week<N>.html | `./lineup.sh espn-1` | The Lineup Builder: your lineup as slots, a challenger line only under a contested slot, HOLD-vs-STREAM on D/ST and K against what is actually on the wire (each with its opponent), swap deltas, a Set-lineup verb into ESPN/Yahoo. Phone-first. |
| board-<league>-week<N>.html | `./board.sh espn-1` | The full breakdown: every player x every source (faces in the headers, form badges), your model's verdict, divergence cards, the wire, the league view, the source scoreboard. Rows expand; a player pops out. |
| digest-<league>-week<N>.html | `./season.sh espn-1` | The Ledger (Tuesday digest): waivers, lineup verdicts, streaming, trades, YOUR MODEL room. |
| tradedesk-<league>-week<N>.html | `./tradedesk.sh espn-1` | Trade Desk: league grid, needs matrix, ranked named trade targets (both valuations, both sides' points), waiver competition, needs over time (trend after 2+ weeks). |
| sources.html | `.venv/bin/python -m engine.sources_page` | The Receipts: per-source hit rate, streak, sparkline, positional splits, and the 2025-archive decay strip (100/60/30/0% by completed week). |
| Model Settings | `./sources.sh` | The panel: Inputs (faces, on/off, weight sliders) and Leagues (connections, roster paste). Add a YouTube/podcast input and `python -m engine.sources --avatars` fetches its face. |

The pages link to each other through the top bar; the Model Settings link
works while `./sources.sh` is running. Rendering is read-only - it never
advances the ownership snapshot or touches saves/, rosters, or the registry.

Defense and kicker calls are weekly hold-or-stream decisions (engine/dk.py): your D/ST or K measured against the best one genuinely available on the wire, each with its opponent; STREAM only past a documented margin, TOSS-UP when rival rosters are unknown. `python -m engine.dk --league espn-1` prints the call.
