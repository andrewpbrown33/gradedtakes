# Per-league configuration audit

Every number the engine shows is only as league-specific as its inputs. This
page tracks, for each per-league-sensitive computation, where its league input
actually comes from, and what has to happen when a new league is added.

Audited 2026-08-29 against `leagues/yahoo-main.yaml` (10-team, full PPR) and
`leagues/espn-1.yaml` (12-team template, half PPR, settings unconfirmed).

Verdicts:

- **KEYED** — derived from that league's own config at runtime; nothing to do.
- **SHARED-BUT-SAFE** — one file serves all leagues, and that is correct (or
  currently harmless) for what it carries; caveats noted.
- **FIXED** — was silently shared, now structurally separated (this audit).
- **USER-ACTION** — correct only after you run the reseed sequence below with
  the league's confirmed settings.

## The table

| # | Computation | League input, and where it enters | Verdict | Evidence / notes |
|---|-------------|-----------------------------------|---------|------------------|
| a | VBD replacement baselines | `recommend.replacement_levels()`: demand = `LeagueConfig.hard_starter_counts()` x `league.teams` plus `recommend.flex_allocation()` (each flex slot awarded to whichever eligible position offers the best remaining projection past its hard starters — read off this pool's own projections, never an even split); the Nth projection comes from `league.rankings_csv` | KEYED (demand) + FIXED (projection pool) | Demand math is live per config AND per pool: yahoo-main (2 hard WR x 10 teams + 12 of the 20 W/R/T slots) puts WR demand at 32 and RB at 28 in today's PPR pool. (`LeagueConfig.starter_counts()`'s even flex split is NOT this input — it now serves only `strip.league_demand()`'s roster meter, where a ceiling estimate is the point.) Both leagues used to read the same PPR csv, so espn-1's WR baseline computed 204.4 when its true half-PPR baseline is 168.3 — a 36.0-pt error (RB 20.2, TE 33.1) feeding a VBD term capped at +/-20 score. espn-1 now points at its own csv. |
| b | Projections scoring format | `proj_points` column of `league.rankings_csv`, filled by `engine/projections.apply_to_csv(csv, scoring)`; the scoring token is chosen at refill time — `LeagueConfig.scoring_label()` derives the right one (`ppr`/`half`/`std`) from the league's `reception` value | FIXED + USER-ACTION | `data/rankings.csv` is filled PPR (correct for yahoo-main only). espn-1 read it silently; it now requires `data/rankings-espn.csv`, absent on purpose until real ESPN settings are confirmed. Both CLIs refuse to start and print the exact fill commands. |
| c | Tier assignments | `tier` column of `league.rankings_csv`; Boris Chen tiers are per-scoring (`engine/tiers.apply_to_csv(csv, scoring)`), seed fallback is ADP-gap tiers | FIXED + USER-ACTION | Chen publishes separate PPR and HALF files for RB/WR/TE/FLX (QB/K/DST are format-free). PPR tiers in the shared csv were wrong for a half-PPR league. Caveat: there is no Chen feed for standard scoring — a `std` league keeps its seeded ADP-gap tiers, and the loud error says so. |
| d | Survival-model ADP source | `recommend.effective_adp/effective_sd` read the `adp`/`adp_stdev` columns of `league.rankings_csv`, seeded by `engine/adp.seed_rankings_csv(dest, scoring=, teams=)` | FIXED + USER-ACTION | Survival maps ADP onto overall pick numbers, so 10-team ADP geometry is wrong in a 12-team room even before scoring differences (FFC 12-team half-PPR verified live: 232 players). The `espn_adp` csv column is loaded into `Player` but unused by survival — informational only. |
| e | Intel / my_calls layering | `data/player_intel.yaml` then `data/my_calls.yaml`, hardcoded shared paths in both `warroom.py` and `espn_cli.py`; later file wins outright | SHARED-BUT-SAFE (with a trap) | Player theses are league-agnostic opinions, so sharing is intended — but the file's own header says "research assumes half-PPR; this league is full PPR", i.e. adjust magnitudes were tuned for yahoo-main. The real trap: `managers:` entries are keyed by draft SLOT and feed survival odds — they are inherently one-league data. Today the file has no managers section and no live `my_calls.yaml` (only `my_calls.yahoo-archive.yaml`). Keep manager reads out of the shared file; archive per league as already practiced. |
| f | Exposure exclusion | `Exposure.load(matcher, exclude_league_id=league.id)` in both CLIs; roster files are `data/rosters/<league-id>.yaml` | KEYED | The league being drafted is excluded by its config `id`, so drafting espn-1 correctly surfaces yahoo-main holdings and vice versa. Flags stay positive-only with coverage banners. Keep roster filenames matching config `id`s. |
| g | Snake geometry, saves, strategy | `teams`/`rounds`/`my_slot` from the config drive all pick math; saves are `saves/<league.id>-<date>.json`; `strategy_file` is a per-league path (absent -> empty tree) | KEYED | `tests/espn_replay.py` runs a 12-team slot-12 league end-to-end; saves never collide across leagues. `strategies/espn-1.yaml` does not exist yet — the engine degrades to best-available, loudly labeled on screen. |

## What changed in this audit

- `leagues/espn-1.yaml` now points at `data/rankings-espn.csv`. The file is
  **deliberately absent** until the real ESPN settings are known — do not
  create it by copying `data/rankings.csv`.
- `warroom.py` no longer auto-seeds a missing csv (the seeder's defaults are
  10-team PPR — one league's format). Both `warroom.py` and `espn_cli.py` now
  fail loudly on a missing csv, printing the exact per-league reseed commands
  (built by `engine.models.missing_rankings_message`, formats derived from the
  league's own `reception` value and `teams`).
- `LeagueConfig.scoring_label()` added: the single place a league's reception
  value becomes a fetcher scoring token.
- `./setup.sh` is unchanged and still seeds the default `data/rankings.csv`
  (10-team PPR — matches yahoo-main).

## Reseed + refill for a new league

Once — after the league's `teams` and `scoring.reception` are confirmed in its
yaml. Shown for espn-1 (12-team half PPR); substitute your csv path, FFC
scoring (`ppr` / `half-ppr` / `standard`), teams, and projection/tier token
(`ppr` / `half` / `std`):

```bash
# 1. ADP seed - survival odds and the value backbone (FFC, per-format ADP)
.venv/bin/python -c "from engine.adp import seed_rankings_csv; seed_rankings_csv('data/rankings-espn.csv', scoring='half-ppr', teams=12)"

# 2. Projections fill - VBD baselines and wait-cost math (ESPN + Sleeper)
.venv/bin/python engine/projections.py data/rankings-espn.csv half

# 3. Chen tiers - tier alerts and cliff warnings (skip for standard scoring)
.venv/bin/python -c "from engine.tiers import apply_to_csv; apply_to_csv('data/rankings-espn.csv', scoring='half')"
```

The order matters: the seed writes the file (overwriting what was there), the
other two fill columns in place. Rerunning the whole sequence is safe for
everything the three steps own — but step 1 rewrites the file wholesale, so
any `ecr`/`ecr_sd` columns (FantasyPros consensus, added by
`engine/nflverse.py`) are stripped and the engine silently falls back to
rank-only blending until you restore them:

```bash
# 4. Restore the ECR consensus columns after any reseed
.venv/bin/python -c "from engine.nflverse import apply_ecr_to_csv; print(apply_ecr_to_csv('data/rankings-espn.csv'))"
```

If you replace the csv with your own rankings export, run only steps 2-4
against it.

Sequence verified 2026-08-29 against a scratch copy with these exact
parameters: 232 rows seeded, 232/232 projections filled (half), 189 Chen tier
rows applied.
