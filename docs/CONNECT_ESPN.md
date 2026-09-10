# Getting your ESPN league into the war room

This is for the person whose league it is. No technical knowledge assumed.
Ten minutes, most of it waiting.

**The one thing you will never be asked for: your ESPN password, and never
your `espn_s2` or `SWID` browser cookies.** Some fantasy tools ask you to dig
those out of your browser and paste them in. Those cookies are your whole
Disney/ESPN account — mail, subscriptions, everything — not a
fantasy-football-only key. Handing them to anyone breaks ESPN's terms for
*you*, and there is no way to take them back except changing your password.
This war room does not accept them, does not store them, and will not ask.
If anything ever does ask you for them, that is your cue to walk away.

There are two ways in. Pick either one; both end up with the same screens
working.

---

## Way 1 — Make the league viewable (best, updates itself)

**What it is.** ESPN has a per-league switch called *Make League Viewable to
Public*. Flip it on and ESPN itself will hand your league's pages to anyone
with the league's ID number — no login. The war room then just reads it, the
same way any person with the link could. Nothing is impersonated and nothing
is stored on your behalf.

**Who can do it.** Only the league manager (commissioner), and only on a
computer — the phone app cannot change this setting.

**The clicks** (ESPN's own wording):

1. Go to `fantasy.espn.com` and open your league.
2. Click the **League** tab.
3. Click **Settings**.
4. Click **Basic Settings**.
5. Click **Edit Basic Settings**.
6. Find **Make League Viewable to Public** and set it to **Yes**.
7. Click **Save Changes**.

**What it costs you — the honest version.** Once it is on, *anybody who knows
your league's ID number* can read the league without logging in: team names,
rosters, scores, box scores, standings, and the transaction log. The ID
number is not secret — it is sitting in your league's own web address — so
treat this as "the league is now public", because it is.

What stays private even then, per ESPN: **the list of team managers and the
league message boards are never shown to non-members.** Making the league
viewable also does **not** let anyone join it — your league is still
invite-only.

And it is reversible. Set it back to **No** at any time and ESPN goes back to
refusing outsiders immediately. If you turn it off later, the war room's next
refresh will fail loudly and say exactly why, rather than quietly serving you
stale numbers.

If your leaguemates would object to any of that, don't do it — use Way 2
instead. It works.

**What to send back.** Two things:

- **Your league ID** — the number in your league's web address. It looks
  like `.../leagueId=284298483` or `.../ffl/league?leagueId=284298483`. Just
  the number.
- **Your team name** (exactly as it appears in the league) — so the right
  roster gets treated as yours.

That is all. Nothing else, ever.

---

## Way 2 — Paste your roster (works on a private league)

Use this if you are not the commissioner, or if the league would rather stay
private. This path is fully supported — everything the war room does works
off a pasted roster. The only thing you give up is automatic refreshing.

**The clicks:**

1. Open your team's page on ESPN (web or phone).
2. Select the roster area — the player names, top to bottom, starters and
   bench.
3. Copy it.
4. Paste it into a plain email or message and send it. Do not screenshot it:
   a picture cannot be read, text can.

Do not worry about tidying it up. The slot labels (`QB`, `FLEX`, `D/ST`),
the bye weeks, the projections, the "vs PIT" columns, the injury tags — all
of that gets recognised and skipped. One player per line is ideal but not
required.

**What to send back:**

- **The pasted roster text.**
- **Your league ID** (the number in your league's web address — the files get
  named after it, so the same league updates in place next time).
- **How many teams** are in the league.
- **Points per catch**: `1` (PPR), `0.5` (half PPR), or `0` (standard). If
  you are not sure, look at any receiver's scoring in the box score, or just
  say "not sure" — a guess gets recorded *as a guess*, visibly, rather than
  passed off as fact.
- **Waivers**: FAAB bidding (a budget you spend), or waiver priority (a
  queue)?

**What it costs you.** A pasted league does not update itself. Every number
stays as old as your last paste. **Re-paste after every add, drop or trade**,
and before every draft or lineup decision you actually care about. The league
page will say `PASTE-FED` and show when it was last pasted, so nobody is ever
fooled about how fresh it is.

You can switch to Way 1 later at any time; nothing is lost.

---

## What happens on the other end

For the owner running this, the two paths are one command.

**Public league — list the teams first:**

```
python -m engine.espn_public --league 349
```

```
Beer Sliders Anonymous - ESPN league 349, 2026 season
  10 teams, standard (no PPR), priority waivers, lineup: QB, RB, RB, WR, WR, TE, W/R/T, K, DEF, BN, ... IR

  Which team is yours? Re-run with --team <id>:
    --team 1    The Wookie Has no Pants          16 players
    --team 2    Keep UR syphillis free           16 players
    ...
```

**Then import it:**

```
python -m engine.espn_public --league 349 --team 1
```

That writes `leagues/espn-349.yaml` (the real scoring, roster slots, team
count and waiver style, read from the league itself),
`data/rosters/espn-349.yaml` (the friend's own team),
`data/league-espn-349.json` (every team's roster) and rebuilds
`data/rankings-espn-349.csv` for that exact format. Re-run it any time to
refresh.

**Paste import:**

```
python -m engine.espn_public --league 284298483 --paste-file roster.txt \
    --teams 8 --reception 1 --waiver priority --name "The Original 8"
```

Same four files. The league yaml carries a `coverage:` block recording that
it is paste-fed, when it was pasted, and — if any of `--teams`,
`--reception`, `--waiver` or the roster slots were left out — exactly which
facts are defaults rather than readings.

Useful flags: `--season 2025` (past seasons of a public league are readable
too), `--overwrite` (replace a hand-written league yaml — refused without
it), `--force` (ignore the one-hour cache), `--no-rebuild` (skip the rankings
rebuild).

## When it does not work

| What you see | What it means | What to do |
| --- | --- | --- |
| `PRIVATE` | ESPN returned 401. The league is not viewable to the public — this is ESPN working correctly, not a bug. | Way 1 (flip the setting), or Way 2 (paste). |
| `NOT_FOUND` | ESPN returned 404. No league with that ID in that season. | Re-check the number in the league URL; try `--season <year>` for the season it was last played in. |
| `BAD_REQUEST` | ESPN returned 400. The ID or season is not a plain number. | Use the bare number from the URL. |
| `FEED_DOWN` | ESPN is having a bad minute (timeout or 5xx). | Wait and retry. The last good copy in `data/cache/` is used meanwhile, and it says out loud when it does that. |
| `NO_TEAM` | We will not guess which team is yours. | Re-run with `--team <id>` — the error lists every team and the flag to pick it. |
| `CONFLICT` | A league yaml with that name already exists and was not written by this tool. | Move it aside, or pass `--overwrite` deliberately. |

Every one of those messages prints the fix underneath it.

## What this reads, and what it refuses to

**Reads** (public leagues only, no credentials): league name, size, scoring
settings, lineup slots, waiver settings, draft order, team names, and every
team's roster.

**Deliberately does not keep**: owner display names and member email
addresses. ESPN includes them in the payload; they belong to people who never
asked to be in this database, so they are dropped on the floor. Team names —
which the league publishes anyway — are enough to identify a team.

**Never does**: send a cookie, a password, a token, or any other credential;
read the owner's own ESPN secrets file; write anything back to ESPN. Every
request is a plain `GET` to ESPN's read-only host carrying exactly two
headers, `User-Agent` and `Accept`. `tests/espn_public_test.py` proves this
twice — once by reading the module's own source, and once by capturing every
request the module builds and asserting on its headers.

This is advise-only. Nothing here can add, drop, trade, or set a lineup on
ESPN. It can only look.

## For the record: what was actually measured

Established on 2026-09-09 by fetching real leagues, not by reading docs:

- A **public** league answers `200` with everything, to a request carrying no
  authentication at all. Confirmed on 13 different real league IDs.
- Every one of those 200s carried `settings.isPublic: true`. Not one 200 came
  back with it false — so "answers 200" and "is viewable to the public" are
  the same fact.
- A **private** league answers `401 "You are not authorized to view this
  League."` on *every* view — `mTeam`, `mRoster`, `mSettings`, `mNav`,
  `mStatus`, `kona_player_info`. Nothing leaks around the edges.
- A **nonexistent** league answers `404 Not Found`; a malformed ID answers
  `400 Invalid parameter for 'leagueId'`.
- **Past seasons** of a public league are readable, and visibility is *per
  season*: one league answered 200 for 2019 through 2026 and 401 for 2018.
  So turning the setting on today makes this season readable — it does not
  retroactively open every past season.
- On a public league every ESPN view works unauthenticated, so the rosters,
  settings and scoring all come through. Nothing is missing versus the
  cookie path for the purposes of this war room.

See the docstring at the top of `engine/espn_public.py` for the league IDs,
the status codes, and how the lineup-slot and scoring-stat mappings were
derived from the data rather than guessed.
