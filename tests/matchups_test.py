#!/usr/bin/env python3
"""Acceptance test: positional matchup engine (engine/matchups.py).

Synthetic defenses prove the pure core - one unit that BLEEDS to TE and
STIFLES RB grades SMASH and AVOID in the same table and votes start/sit
accordingly; the neutral middle abstains; a top-percentile defense that is
NOT separated from the pack is softened by the magnitude gate; a thin
sample cannot earn an extreme grade; and a reception-heavy defense outranks
a yardage-heavy one in PPR and the order REVERSES in standard, which is the
whole reason scoring comes from LeagueConfig instead of the file's baked
fantasy_points columns.

Then the honesty contract: the 2025 basis label and caveat are present and
named on every table, matchup and evidence string; the blend weighting is
0%% current-season at zero weeks played and 50/50 at four; and the built-in
source ships DISABLED so opting in never silently re-normalizes the weights
already in data/sources.yaml.

FIXTURE RULE - read before editing this file:

    Acceptance tests assert INVARIANTS AND BEHAVIOR against controlled
    fixtures or an injected clock, never the contents of a live file or
    the real date. The points-allowed table is a FUNCTION OF THE CALENDAR:
    before week 1 it is prior-season-only ("2025 season, 17 games", loud
    caveat, 2026 at 0%); from the first 2026 game on it is a blend ("2026
    wk1-1 (20%%) + 2025 season (80%%)", softer caveat, 17+1 games). A check
    that pins the live table to ONE of those states is true on Sunday and
    false on Thursday - an expiry date, not a contract. So section 6b
    stands the assembly code on BOTH sides of week 1 through pa_table's
    own seam (rows_by_season=...) and pins every value exactly; the live
    sections then assert only what is true in ANY week - the basis is in
    matchups.py's grammar and names the prior season, the caveat is the
    one the basis form calls for, the blend is blend_weights() of the
    weeks actually on file, and every game count is prior + current.

Finally the live season: 32 defenses in a valid competition ranking at
each position (2025 really does contain an exact tie - CLE and GB allowed
identical TE points - and a shared rank is the correct answer to that, not
a bug), nflverse's 'LA' normalized to LAR, and score_row reproducing the
file's own fantasy_points_ppr column exactly on every QB/RB/WR/TE row.

register() is only ever pointed at a tempdir - this test never writes
data/sources.yaml (same discipline as consensus.LEDGER_PATH redirection).

    .venv/bin/python tests/matchups_test.py
"""

import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import matchups                                  # noqa: E402
from engine import nflverse                                  # noqa: E402
from engine import sources as sources_mod                    # noqa: E402
from engine.models import LeagueConfig, Player               # noqa: E402
from engine.projections import norm_team                     # noqa: E402

FAILURES = []

# The two seasons the engine blends. Named here, not spelled 2025/2026 in
# the calendar checks, so the checks describe the rule and not the year.
CUR, PRIOR = matchups.CURRENT_SEASON, matchups.PRIOR_SEASON


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- fixtures ---------------------------------------------------------------

ROSTER_SPOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "W/R/T",
                "K", "DEF", "BN", "BN", "BN", "BN", "BN", "BN"]


def _league(reception=1.0, lid="fixture"):
    """An 8-team league whose ONLY interesting knob is points per reception."""
    return LeagueConfig({
        "id": lid, "teams": 8, "roster_spots": list(ROSTER_SPOTS),
        "scoring": {"passing_yards_per_point": 25, "passing_td": 4,
                    "interception": -2, "rushing_yards_per_point": 10,
                    "rushing_td": 6, "reception": reception,
                    "receiving_yards_per_point": 10, "receiving_td": 6,
                    "fumble_lost": -2}}, path="")


def _row(defense, week, pos, **stats):
    row = {"position": pos, "week": str(week), "season_type": "REG",
           "opponent_team": defense, "team": "OFF",
           "game_id": "FX_%02d_%s" % (week, defense)}
    row.update(dict((k, str(v)) for k, v in stats.items()))
    return row


# Per-game points each defense allows, by position. CIN is the whole point of
# the fixture: it bleeds to TE (far and away the most) and stifles RB (far
# and away the least), in ONE table.
FIX_TE = {"CIN": 22.0, "ARI": 13.0, "PIT": 12.5, "MIA": 12.0, "WAS": 11.5,
          "TB": 11.0, "DAL": 10.5, "NYJ": 10.0, "DET": 9.5, "SEA": 9.0,
          "PHI": 8.5, "BUF": 8.0}
FIX_RB = {"NYJ": 26.0, "DAL": 25.0, "PIT": 24.0, "MIA": 23.0, "WAS": 22.0,
          "TB": 21.0, "ARI": 20.0, "DET": 19.0, "SEA": 18.0, "PHI": 17.0,
          "BUF": 16.0, "CIN": 8.0}
FIX_WR = dict((d, 30.0 + i) for i, d in enumerate(sorted(FIX_TE)))
FIX_QB = dict((d, 14.0 + i * 0.7) for i, d in enumerate(sorted(FIX_TE)))
FIX_WEEKS = 5


def fixture_rows(weeks=FIX_WEEKS, byes=False):
    """Weekly stat rows that reproduce FIX_* exactly as per-game rates.

    Reception counts are deliberately ZERO here, so every rate is identical
    in PPR and standard: these rows test the RANKING math, and the scoring
    fixture below owns the format question on its own.

    `byes` gives each defense one week off, so an 18-week fixture season
    yields 17 games apiece - the real NFL shape, and what the basis label
    has to say out loud.
    """
    order = sorted(FIX_TE)
    bye = dict((d, 5 + (i % 4)) for i, d in enumerate(order)) if byes else {}
    rows = []
    for week in range(1, weeks + 1):
        for d in order:
            if bye.get(d) == week:
                continue
            rows.append(_row(d, week, "QB", passing_yards=25 * FIX_QB[d]))
            rows.append(_row(d, week, "RB", rushing_yards=10 * FIX_RB[d]))
            rows.append(_row(d, week, "WR", receiving_yards=10 * FIX_WR[d]))
            rows.append(_row(d, week, "TE", receiving_yards=10 * FIX_TE[d]))
    return rows


def fixture_table(weeks=FIX_WEEKS, league=None, season=2025, byes=False):
    league = league or _league()
    part = matchups.season_part(fixture_rows(weeks, byes), season,
                                league.scoring)
    return matchups.build_table([part], scoring_label=league.scoring_label())


# Schedule fixture: who plays whom. Offense abbreviations are distinct from
# the defensive ones so a lookup can never accidentally match itself.
FIX_SCHEDULE = {
    "ATL": {"opponent": "CIN", "home": False},   # faces the TE bleeder
    "LV":  {"opponent": "CIN", "home": True},
    "KC":  {"opponent": "TB", "home": True},     # faces a neutral unit
    "HOU": {"opponent": "ARI", "home": False},   # rank 2, but gated
    "IND": {"opponent": "BUF", "home": True},    # faces the TE wall
}


def _p(name, pos, team, proj=10.0):
    return Player(rank=1, name=name, pos=pos, team=team, proj_points=proj)


# --- 1. grades: one defense that bleeds to TE and stifles RB ---------------

def test_bleed_and_stifle():
    print("\n1. GRADES - one unit bleeding to TE and stifling RB")
    table = fixture_table()
    te = table["by_pos"]["TE"]["defenses"]
    rb = table["by_pos"]["RB"]["defenses"]

    check(te["CIN"]["rank"] == 1 and te["CIN"]["of"] == 12,
          "CIN is rank 1 of 12 against TE (the bleeder)")
    check(te["CIN"]["grade"] == "SMASH",
          "CIN grades SMASH vs TE (pctl %.1f, z %+.2f)"
          % (te["CIN"]["pctl"], te["CIN"]["z"]))
    check(rb["CIN"]["rank"] == 12,
          "the SAME defense is rank 12 of 12 against RB (the wall)")
    check(rb["CIN"]["grade"] == "AVOID",
          "CIN grades AVOID vs RB (pctl %.1f, z %+.2f)"
          % (rb["CIN"]["pctl"], rb["CIN"]["z"]))
    check(matchups.VOTE_ON[te["CIN"]["grade"]] == "start"
          and matchups.VOTE_ON[rb["CIN"]["grade"]] == "sit",
          "vote direction follows the grade: SMASH->start, AVOID->sit")
    check(abs(te["CIN"]["pa_per_game"] - 22.0) < 0.01
          and abs(rb["CIN"]["pa_per_game"] - 8.0) < 0.01,
          "per-game rates reproduce the fixture exactly (22.0 TE / 8.0 RB)")
    check(te["BUF"]["grade"] == "AVOID" and rb["NYJ"]["grade"] == "SMASH",
          "the other extremes grade too (BUF walls TE, NYJ bleeds RB)")
    check(table["by_pos"]["TE"]["ranked"][0] == "CIN"
          and table["by_pos"]["RB"]["ranked"][-1] == "CIN",
          "the ranked list is softest-first and puts CIN at both ends")


# --- 2. the magnitude gate and the thin-sample rule ------------------------

def test_gates():
    print("\n2. MAGNITUDE GATE + THIN SAMPLE (an extreme grade must earn it)")
    table = fixture_table()
    te = table["by_pos"]["TE"]["defenses"]

    ari = te["ARI"]
    check(ari["rank"] == 2 and ari["pctl"] >= 87.5,
          "ARI sits in the SMASH percentile band (rank 2, pctl %.1f)"
          % ari["pctl"])
    check(abs(ari["z"]) < matchups.EDGE_Z,
          "...but is only %+.2f SD off the mean, inside the %.1f gate"
          % (ari["z"], matchups.EDGE_Z))
    check(ari["grade"] == "GOOD",
          "so it is SOFTENED to GOOD, not sold as a SMASH")
    check(matchups.grade_for(100.0, 3.0) == "SMASH"
          and matchups.grade_for(100.0, 0.1) == "GOOD",
          "grade_for: same percentile, different separation, different grade")
    check(matchups.grade_for(0.0, -3.0) == "AVOID"
          and matchups.grade_for(0.0, -0.1) == "TOUGH",
          "the gate is symmetric on the AVOID side")
    check(matchups.grade_for(100.0, 3.0, thin=True) == "GOOD",
          "a thin sample cannot earn SMASH however extreme the rate looks")

    thin = fixture_table(weeks=matchups.MIN_GAMES - 1)
    cin = thin["by_pos"]["TE"]["defenses"]["CIN"]
    check(cin["thin"] is True and cin["rank"] == 1 and cin["grade"] == "GOOD",
          "a %d-game table flags thin and withholds SMASH from rank 1"
          % (matchups.MIN_GAMES - 1))
    check("thin sample" in matchups.evidence_for(cin, thin, "TE"),
          "the thin basis is stated in the evidence, not hidden")


# --- 3. abstention in the neutral middle -----------------------------------

def test_abstention():
    print("\n3. ABSTENTION - the neutral middle says nothing")
    table = fixture_table()
    te = table["by_pos"]["TE"]["defenses"]
    league = _league()

    neutral = [d for d, c in te.items() if c["grade"] == "NEUTRAL"]
    check(len(neutral) >= 1, "the fixture has a neutral band (%s)"
          % ", ".join(sorted(neutral)))
    check(all(matchups.VOTE_ON.get(g) is None
              for g in ("GOOD", "NEUTRAL", "TOUGH")),
          "GOOD, NEUTRAL and TOUGH all map to no vote at all")

    universe = {
        "smash te|TE": {"name": "Smash TE", "pos": "TE", "team": "ATL"},
        "neutral te|TE": {"name": "Neutral TE", "pos": "TE", "team": "KC"},
        "gated te|TE": {"name": "Gated TE", "pos": "TE", "team": "HOU"},
        "wall te|TE": {"name": "Wall TE", "pos": "TE", "team": "IND"},
        "wall rb|RB": {"name": "Wall RB", "pos": "RB", "team": "LV"},
    }
    votes = matchups.feed_votes(universe, 1, league, table=table,
                                schedule=FIX_SCHEDULE)
    check(votes.get("smash te|TE") == "start",
          "TE facing the bleeder votes start")
    check(votes.get("wall rb|RB") == "sit",
          "RB facing the same defense votes sit")
    check(votes.get("wall te|TE") == "sit",
          "TE facing the TE wall votes sit")
    check("neutral te|TE" not in votes,
          "a NEUTRAL matchup casts no vote (abstains, not a weak start)")
    check("gated te|TE" not in votes,
          "the magnitude-gated GOOD matchup abstains too")
    check(set(votes.values()) <= {"start", "sit"},
          "votes are only ever start or sit - consensus's own vocabulary")

    only = matchups.feed_votes(universe, 1, league, table=table,
                               schedule=FIX_SCHEDULE,
                               startable={"smash te|TE"})
    check(only == {"smash te|TE": "start"},
          "the startable gate silences votes on players you would not start")


# --- 4. scoring-format sensitivity -----------------------------------------

# Reception-heavy vs yardage-heavy units. Under full PPR the order is CHI,
# GB, DEN, HOU; strip the point per reception and it REVERSES completely.
SCORING_WR = {"CHI": (16, 80), "GB": (10, 130), "HOU": (7, 155),
              "DEN": (2, 200)}
SCORING_RB = {"CHI": (12, 40), "GB": (8, 65), "DEN": (3, 110),
              "HOU": (1, 125)}


def scoring_rows(weeks=FIX_WEEKS):
    rows = []
    for week in range(1, weeks + 1):
        for d, (rec, yds) in SCORING_WR.items():
            rows.append(_row(d, week, "WR", receptions=rec,
                             receiving_yards=yds))
        for d, (rec, rush) in SCORING_RB.items():
            rows.append(_row(d, week, "RB", receptions=rec,
                             rushing_yards=rush))
    return rows


def test_scoring_sensitivity():
    print("\n4. SCORING SENSITIVITY - PPR and standard rank differently")
    rows = scoring_rows()
    ppr = matchups.build_table(
        [matchups.season_part(rows, 2025, _league(1.0).scoring)],
        scoring_label="ppr")
    std = matchups.build_table(
        [matchups.season_part(rows, 2025, _league(0.0).scoring)],
        scoring_label="std")

    wr_ppr = ppr["by_pos"]["WR"]["ranked"]
    wr_std = std["by_pos"]["WR"]["ranked"]
    rb_ppr = ppr["by_pos"]["RB"]["ranked"]
    rb_std = std["by_pos"]["RB"]["ranked"]
    print("      WR  ppr=%s  std=%s" % (wr_ppr, wr_std))
    print("      RB  ppr=%s  std=%s" % (rb_ppr, rb_std))

    check(wr_ppr != wr_std, "WR defense order CHANGES between PPR and standard")
    check(rb_ppr != rb_std, "RB defense order CHANGES between PPR and standard")
    check(wr_ppr[0] == "CHI" and wr_std[0] == "DEN",
          "the softest WR draw is the reception-heavy unit in PPR (CHI) and "
          "the yardage-heavy one in standard (DEN)")
    check(wr_ppr == list(reversed(wr_std)),
          "the WR order fully reverses - the format is not cosmetic")
    check(rb_ppr[0] == "CHI" and rb_std[0] == "HOU",
          "same flip at RB: pass-catching backs are worth a point each")
    check(rb_ppr == list(reversed(rb_std)),
          "the RB order fully reverses too")

    chi = ppr["by_pos"]["WR"]["defenses"]["CHI"]["pa_per_game"]
    chi_std = std["by_pos"]["WR"]["defenses"]["CHI"]["pa_per_game"]
    check(abs(chi - 24.0) < 0.01 and abs(chi_std - 8.0) < 0.01,
          "the rate itself is rescored, not just reordered (24.0 vs 8.0)")

    half = matchups.build_table(
        [matchups.season_part(rows, 2025, _league(0.5).scoring)],
        scoring_label="half")
    chi_half = half["by_pos"]["WR"]["defenses"]["CHI"]["pa_per_game"]
    check(abs(chi_half - 16.0) < 0.01,
          "half PPR lands exactly between the two (16.0) - the scoring "
          "dict is read, not a hardcoded ppr/std switch")


# --- 5. the 2025 basis label and the honest caveat -------------------------

def test_basis_label():
    print("\n5. BASIS LABEL - a 2025 grade is never dressed as 2026 fact")
    table = fixture_table()
    check(table["basis"] == "2025 wk1-5, 5 games",
          "partial-season basis names the season AND the weeks: %r"
          % table["basis"])

    full = fixture_table(weeks=18, byes=True)
    check(full["basis"] == "2025 season, 17 games",
          "a completed season reads '2025 season, 17 games': %r"
          % full["basis"])
    check(full["prior_only"] is True, "prior_only is set for a 2025-only table")
    check("2025" in full["caveat"] and "2026" in full["caveat"],
          "the caveat names both seasons")
    check("changed" in full["caveat"].lower(),
          "the caveat says the rosters/schemes have changed")

    cell = full["by_pos"]["TE"]["defenses"]["CIN"]
    ev = matchups.evidence_for(cell, full, "TE", "ppr")
    check("2025 season, 17 games" in ev,
          "the evidence string carries the basis verbatim")
    check("2026 rosters and schemes have changed" in ev,
          "and warns that 2026 has changed since: %r" % ev)
    check("PPR" in ev, "the evidence names the scoring it was computed in")

    league = _league()
    m = matchups.matchup_for(_p("Fixture TE", "TE", "ATL"), 1, league,
                             table=full, schedule=FIX_SCHEDULE)
    check(m["basis"] == full["basis"] and m["prior_only"] is True,
          "every matchup dict carries basis + prior_only")
    check("2025" in m["evidence"],
          "and its evidence string names 2025")


# --- 6. blending once 2026 weeks exist -------------------------------------

def test_blending():
    print("\n6. BLENDING - documented weighting, prior season never faked")
    check(matchups.blend_weights(0) == (0.0, 1.0),
          "zero weeks played = 100% prior season (September 2026 today)")
    check(matchups.blend_weights(4) == (0.5, 0.5),
          "four weeks played = an even 50/50 split (halflife %g)"
          % matchups.PRIOR_HALFLIFE)
    cur8, pri8 = matchups.blend_weights(8)
    check(abs(cur8 - 2.0 / 3.0) < 0.001 and abs(cur8 + pri8 - 1.0) < 1e-9,
          "eight weeks = 2/3 current, and the pair always sums to 1")
    cur17, _ = matchups.blend_weights(17)
    check(0.75 < cur17 < 0.85,
          "even at week 17 the prior season keeps a real share (%.0f%%)"
          % (100 * (1 - cur17)))

    league = _league()
    prior = matchups.season_part(fixture_rows(), 2025, league.scoring)
    cur_rows = [_row(d, w, "TE", receiving_yards=10 * 10.0)
                for d in FIX_TE for w in range(1, 5)]
    cur_rows += [_row(d, w, "RB", rushing_yards=10 * 20.0)
                 for d in FIX_TE for w in range(1, 5)]
    current = matchups.season_part(cur_rows, 2026, league.scoring)
    prior["weight"], current["weight"] = 0.5, 0.5
    blend = matchups.build_table([current, prior], scoring_label="ppr")

    cin = blend["by_pos"]["TE"]["defenses"]["CIN"]
    check(abs(cin["pa_per_game"] - 16.0) < 0.01,
          "a 50/50 blend of 22.0 (2025) and 10.0 (2026) is 16.0, not 22.0")
    check(blend["prior_only"] is False,
          "prior_only clears once the current season carries weight")
    check("2026" in blend["basis"] and "2025" in blend["basis"]
          and "%" in blend["basis"],
          "the blended basis names both seasons and their shares: %r"
          % blend["basis"])
    check("young" in blend["caveat"] or "prior-season" in blend["caveat"],
          "the blended caveat still admits the prior season is carrying it")
    check(cin["games"] == FIX_WEEKS + 4,
          "games are summed across the blended parts (%d)" % cin["games"])


# --- 6b. the calendar boundary, through pa_table's own seam -----------------
#
# Section 6 proves build_table's arithmetic on hand-weighted parts. This
# section proves the ASSEMBLY that runs live - pa_table(): which seasons it
# reads, how many weeks it counts, the weights it derives, and every label
# it prints - on both sides of week 1, by handing it the rows through
# rows_by_season=... so nflverse is never touched. Every value the live
# section (10) can only assert as an invariant is pinned exactly here.

# Flat current-season rates for every fixture defense, so each blend below
# is one line of arithmetic against the FIX_* prior rates.
FIX_CUR = {"QB": 15.0, "RB": 20.0, "WR": 25.0, "TE": 10.0}


def cur_rows(weeks, season=CUR):
    """`weeks` of flat current-season rows for every fixture defense,
    with game ids that can never collide with the prior fixture's."""
    rows = []
    for w in range(1, weeks + 1):
        for d in sorted(FIX_TE):
            for pos, col in (("QB", "passing_yards"), ("RB", "rushing_yards"),
                             ("WR", "receiving_yards"),
                             ("TE", "receiving_yards")):
                mult = 25 if pos == "QB" else 10
                r = _row(d, w, pos, **{col: mult * FIX_CUR[pos]})
                r["game_id"] = "FX%d_%02d_%s" % (season, w, d)
                rows.append(r)
    return rows


def _cells(table, pos="TE"):
    return list(table["by_pos"][pos]["defenses"].values())


def test_calendar_boundary():
    print("\n6b. THE CALENDAR BOUNDARY - pa_table on both sides of week 1")
    league = _league()
    prior = fixture_rows(18, byes=True)         # a completed 17-game season
    pre_basis = "%d season, 17 games" % PRIOR

    # (a) PRE-SEASON. Two ways the current season can be "not played yet":
    #     no file at all, and a file with no rows. Both must read the same.
    for shape, rbs in (("no %d file" % CUR, {PRIOR: prior}),
                       ("an empty %d file" % CUR, {PRIOR: prior, CUR: []})):
        pre = matchups.pa_table(league, rows_by_season=rbs)
        check(pre["basis"] == pre_basis,
              "[%s] basis reads %r" % (shape, pre_basis))
        check(pre["prior_only"] is True,
              "[%s] the table is flagged prior_only" % shape)
        check(pre["caveat"].startswith("Basis is %s - NOT %d" % (pre_basis, CUR))
              and "changed" in pre["caveat"],
              "[%s] the loud caveat: names the basis, says NOT %d, says "
              "things have changed" % (shape, CUR))
        check(pre["blend"] == {"weeks_played": 0, "current": 0.0,
                               "prior": 1.0,
                               "halflife": matchups.PRIOR_HALFLIFE},
              "[%s] %d contributes 0%% - zero weeks played" % (shape, CUR))
        check(any("%d has no completed games on file" % CUR in n
                  for n in pre["notes"]),
              "[%s] the notes say the current season has no games" % shape)
    pre = matchups.pa_table(league, rows_by_season={PRIOR: prior, CUR: []})
    check(all(c["games"] == 17 and not c["thin"]
              for pos in matchups.PA_POSITIONS for c in _cells(pre, pos)),
          "pre-season: every defense at every position is graded on "
          "exactly the prior season's 17 games, none thin")
    cin = pre["by_pos"]["TE"]["defenses"]["CIN"]
    check(abs(cin["pa_per_game"] - FIX_TE["CIN"]) < 0.01,
          "pre-season: the rate IS the prior rate, unblended (22.0)")
    ev = matchups.evidence_for(cin, pre, "TE", "ppr")
    check(ev.endswith("basis: %s; %d rosters and schemes have changed since."
                      % (pre_basis, CUR)),
          "pre-season: the evidence carries the basis AND the "
          "schemes-have-changed warning: %r" % ev)
    m = matchups.matchup_for(_p("Fixture TE", "TE", "ATL"), 1, league,
                             table=pre, schedule=FIX_SCHEDULE)
    check(m["prior_only"] is True and m["basis"] == pre_basis
          and "have changed since" in m["evidence"],
          "pre-season: the matchup dict is prior_only with the same basis "
          "and warning")

    # (b) IN-SEASON, ONE WEEK - the real shape of the Thursday after the
    #     Wednesday-night opener. The documented weight at one week is 20%.
    one = matchups.pa_table(league,
                            rows_by_season={PRIOR: prior, CUR: cur_rows(1)})
    one_basis = "%d wk1-1 (20%%) + %d season (80%%)" % (CUR, PRIOR)
    check(one["blend"] == {"weeks_played": 1, "current": 0.2, "prior": 0.8,
                           "halflife": matchups.PRIOR_HALFLIFE},
          "one week played: the blend is blend_weights(1) = 20/80")
    check(one["basis"] == one_basis,
          "one week: the basis names both seasons, the week span and the "
          "documented shares: %r" % one["basis"])
    check(one["prior_only"] is False,
          "one week: prior_only clears the moment a current game is on file")
    check(one["caveat"].startswith("Blended basis (%s)" % one_basis)
          and "still young" in one["caveat"]
          and "NOT %d" % CUR not in one["caveat"],
          "one week: the caveat SOFTENS - 'still young', no longer "
          "'NOT %d': %r" % (CUR, one["caveat"]))
    check(not any("no completed games" in n for n in one["notes"]),
          "one week: the no-games note is gone")
    te_cin = one["by_pos"]["TE"]["defenses"]["CIN"]
    rb_cin = one["by_pos"]["RB"]["defenses"]["CIN"]
    check(abs(te_cin["pa_per_game"] - (0.2 * 10.0 + 0.8 * 22.0)) < 0.01
          and abs(rb_cin["pa_per_game"] - (0.2 * 20.0 + 0.8 * 8.0)) < 0.01,
          "one week: rates are the documented 20/80 blend (TE 19.6, RB 10.4)")
    check(all(c["games"] == 18 and not c["thin"]
              for pos in matchups.PA_POSITIONS for c in _cells(one, pos)),
          "one week: every defense is on 17 + 1 = 18 games, none thin")
    check(te_cin["rank"] == 1 and rb_cin["rank"] == 12,
          "one week: a one-game sample moves the rate but cannot flip a "
          "17-game ranking (CIN still 1st vs TE, 12th vs RB)")
    ev = matchups.evidence_for(te_cin, one, "TE", "ppr")
    check(ev.endswith("basis: %s." % one_basis)
          and "have changed since" not in ev,
          "one week: the evidence carries the blended basis and drops the "
          "schemes-have-changed warning: %r" % ev)
    m = matchups.matchup_for(_p("Fixture TE", "TE", "ATL"), 1, league,
                             table=one, schedule=FIX_SCHEDULE)
    check(m["prior_only"] is False and m["basis"] == one_basis,
          "one week: the matchup dict carries the blended basis, not "
          "prior_only")

    # (c) THE WEIGHTS TRACK THE DOCUMENTED TABLE as weeks accrue, the prior
    #     share falls monotonically, and it never reaches zero.
    expect = {2: (33, 67, 19), 4: (50, 50, 21), 8: (67, 33, 25),
              17: (81, 19, 34)}
    shares = [1.0, one["blend"]["prior"]]
    for weeks, (pc, pp, games) in sorted(expect.items()):
        t = matchups.pa_table(league, rows_by_season={PRIOR: prior,
                                                      CUR: cur_rows(weeks)})
        want = "%d wk1-%d (%d%%) + %d season (%d%%)" % (CUR, weeks, pc,
                                                       PRIOR, pp)
        check(t["basis"] == want,
              "%d weeks: basis %r" % (weeks, want))
        check(t["blend"]["weeks_played"] == weeks
              and (t["blend"]["current"], t["blend"]["prior"])
              == matchups.blend_weights(weeks),
              "%d weeks: the blend dict is blend_weights(%d) of the weeks "
              "on file" % (weeks, weeks))
        cin = t["by_pos"]["TE"]["defenses"]["CIN"]
        wc, wp = matchups.blend_weights(weeks)
        check(abs(cin["pa_per_game"] - (wc * 10.0 + wp * 22.0)) < 0.01
              and cin["games"] == games,
              "%d weeks: CIN TE rate is the weighted blend (%.1f) on %d "
              "games" % (weeks, cin["pa_per_game"], games))
        check(t["prior_only"] is False and "still young" in t["caveat"],
              "%d weeks: still a blend, still caveated" % weeks)
        shares.append(t["blend"]["prior"])
    check(all(a > b for a, b in zip(shares, shares[1:])),
          "the prior season's share falls strictly with every added week: "
          "%s" % " > ".join("%.0f%%" % (100 * s) for s in shares))
    check(shares[-1] > 0.15,
          "...and never vanishes (%.0f%% at 17 weeks)" % (100 * shares[-1]))
    full = matchups.pa_table(league, rows_by_season={PRIOR: prior,
                                                     CUR: cur_rows(18)})
    check(full["basis"] == "%d season (82%%) + %d season (18%%)"
          % (CUR, PRIOR),
          "a COMPLETED current season reads 'season', and still names the "
          "prior at 18%%: %r" % full["basis"])

    # (d) THE EDGES of "is week 1 on file": rows without a week number are
    #     not a played week; a current season with NO prior file is graded
    #     on itself alone and says so with a game count, no percentages.
    junk = [dict(r, week="") for r in cur_rows(1)]
    edge = matchups.pa_table(league, rows_by_season={PRIOR: prior,
                                                     CUR: junk})
    check(edge["basis"] == pre_basis and edge["prior_only"] is True
          and edge["blend"]["weeks_played"] == 0,
          "current rows with no week number do not count as a played "
          "week - the table stays prior-only")
    alone = matchups.pa_table(league, rows_by_season={CUR: cur_rows(4)})
    check(alone["basis"] == "%d wk1-4, 4 games" % CUR
          and alone["prior_only"] is False and alone["caveat"] == "",
          "no prior file: the current season stands alone with a game "
          "count and no blend caveat: %r" % alone["basis"])
    check(all(c["games"] == 4 and not c["thin"] for c in _cells(alone)),
          "...on exactly its own 4 games (the thin line is %d)"
          % matchups.MIN_GAMES)


# --- 7. the source ships DISABLED ------------------------------------------

def test_source_disabled():
    print("\n7. SOURCE REGISTRY - ships disabled, never re-weights silently")
    d = matchups.source_default()
    check(d["id"] == "matchup" and d["type"] == "feed"
          and d["handle"] == "matchup",
          "the row is a built-in feed source with id 'matchup'")
    check(d["enabled"] is False,
          "it ships DISABLED - the user opts in from the panel")
    check(isinstance(d["weight"], (int, float)) and 0 < d["weight"] <= 100,
          "it carries a weight SUGGESTION (%s), not an imposed weight"
          % d["weight"])
    check("disabled by default" in (d.get("notes") or "").lower(),
          "the notes say why it is off")

    tmp = tempfile.mkdtemp(prefix="wr-matchup-src-")
    try:
        path = os.path.join(tmp, "sources.yaml")
        sources_mod.save_sources([
            {"id": "engine", "name": "War Room Engine", "type": "feed",
             "handle": "engine", "enabled": True, "weight": 17},
            {"id": "espn-proj", "name": "ESPN", "type": "feed",
             "handle": "espn-proj", "enabled": True, "weight": 17},
        ], path)
        before = sources_mod.load_sources(path)

        row = matchups.register(path)
        after = sources_mod.load_sources(path)
        got = next(s for s in after if s["id"] == "matchup")
        check(row["id"] == "matchup" and got["enabled"] is False,
              "register() adds the row to a registry, disabled")
        check(len(after) == len(before) + 1,
              "exactly one row added")
        check(all(a["weight"] == b["weight"]
                  for a, b in zip(after, before)),
              "every pre-existing weight is untouched (no silent re-norm)")

        sources_mod.enable("matchup", path)
        sources_mod.set_weight("matchup", 33, path)
        matchups.register(path)
        again = next(s for s in sources_mod.load_sources(path)
                     if s["id"] == "matchup")
        check(again["enabled"] is True and again["weight"] == 33,
              "re-registering NEVER overwrites the user's own opt-in/weight")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    live = [s for s in sources_mod.load_sources() if s.get("id") == "matchup"]
    check(not live or not live[0].get("enabled"),
          "the real data/sources.yaml has no ENABLED matchup source "
          "(this test never writes it)")


# --- 8. consensus integration ----------------------------------------------

def _fake_cons():
    return {"week": 1, "league": "fixture",
            "sources": [{"id": "engine", "name": "War Room Engine",
                         "type": "feed", "handle": "engine",
                         "enabled": True, "weight": 17}],
            "rows": [
                {"player": "Smash TE", "player_key": "smash te|TE",
                 "pos": "TE", "score": -1.0, "pct": 0, "verdict": "SIT",
                 "agreement": "UNANIMOUS", "dissenter": None,
                 "engine": "sit", "vs_engine": False, "top_source": "engine",
                 "top_vote": "sit", "top_disagrees": False, "top_note": "",
                 "votes": [{"source": "engine", "name": "War Room Engine",
                            "weight": 17.0, "verdict": "sit"}]},
                {"player": "Neutral TE", "player_key": "neutral te|TE",
                 "pos": "TE", "score": 1.0, "pct": 100, "verdict": "START",
                 "agreement": "UNANIMOUS", "dissenter": None,
                 "engine": "start", "vs_engine": False,
                 "top_source": "engine", "top_vote": "start",
                 "top_disagrees": False, "top_note": "",
                 "votes": [{"source": "engine", "name": "War Room Engine",
                            "weight": 17.0, "verdict": "start"}]},
            ], "notes": []}


def test_consensus_integration():
    print("\n8. CONSENSUS - a weighted voice like any other")
    from engine import consensus as cons_mod

    league = _league()
    table = fixture_table()
    universe = {
        "smash te|TE": {"name": "Smash TE", "pos": "TE", "team": "ATL"},
        "neutral te|TE": {"name": "Neutral TE", "pos": "TE", "team": "KC"},
    }
    votes = matchups.feed_votes(universe, 1, league, table=table,
                                schedule=FIX_SCHEDULE)
    check(votes == {"smash te|TE": "start"},
          "feed_votes returns consensus's exact {player_key: verdict} shape")

    cons = _fake_cons()
    gap = matchups.consensus_gap(cons, votes)
    check(gap == "",
          "no warning when the source is not in the registry at all")

    enabled = _fake_cons()
    enabled["sources"].append(dict(matchups.source_default(), enabled=True))
    warn = matchups.consensus_gap(enabled, votes)
    check("cast no votes" in warn and "1 vote" in warn,
          "an enabled-but-unwired source is reported, not silently mute")

    out = matchups.augment_consensus(cons, votes)
    check(cons["rows"][0]["verdict"] == "SIT",
          "augment_consensus does not mutate the input result")
    smash = next(r for r in out["rows"] if r["player_key"] == "smash te|TE")
    neutral = next(r for r in out["rows"] if r["player_key"] == "neutral te|TE")
    mv = next(v for v in smash["votes"] if v["source"] == "matchup")
    check(mv["verdict"] == "start" and mv["weight"] == 12,
          "the matchup vote is appended at its registry weight")
    check(len(neutral["votes"]) == 1,
          "the abstained row gains no vote at all")
    check(smash["verdict"] == "SIT" and smash["agreement"] == "MAJORITY",
          "engine 17 outweighs matchup 12: verdict stays SIT, MAJORITY - a "
          "minority voice is heard without being allowed to flip the row")
    check(abs(smash["score"] - (12.0 - 17.0) / 29.0) < 0.001,
          "the score is the weighted average of the two voices (%.3f)"
          % smash["score"])

    heavy = matchups.augment_consensus(
        cons, votes, source=dict(matchups.source_default(), weight=90))
    smash_h = next(r for r in heavy["rows"] if r["player_key"] == "smash te|TE")
    check(smash_h["verdict"] == "START" and smash_h["top_source"] == "matchup",
          "at weight 90 it wins the row and becomes the top-weighted voice")
    check(smash_h["top_disagrees"] is True
          and "disagrees with the engine" in smash_h["top_note"],
          "and the top-weighted-dissent alarm fires: %r" % smash_h["top_note"])
    check(smash_h["vs_engine"] is True,
          "vs_engine flips too - the engine is now on the losing side")
    score, pct = cons_mod.weigh(smash_h["votes"])
    check(round(score, 3) == smash_h["score"] and pct == smash_h["pct"],
          "the re-weigh is consensus.weigh's own arithmetic, not a copy")


# --- 9. highlighting -------------------------------------------------------

def test_highlighting():
    print("\n9. HIGHLIGHTING - the single best and worst on the board")
    league = _league()
    table = fixture_table()
    roster = [_p("Smash TE", "TE", "ATL"), _p("Wall RB", "RB", "LV"),
              _p("Neutral TE", "TE", "KC"), _p("Kicker Guy", "K", "ATL"),
              _p("Bye Guy", "WR", "NYG")]
    ms = matchups.matchups_for_roster(roster, 1, league, table=table,
                                      schedule=FIX_SCHEDULE)
    ex = matchups.roster_extremes(ms)
    check(ex["best"][0]["player"] == "Smash TE",
          "the roster's best matchup is the SMASH TE")
    check(ex["worst"][0]["player"] == "Wall RB",
          "the roster's worst is the AVOID RB")
    check(ex["graded"] == 3 and ex["skipped"] == 2,
          "the kicker and the bye player are counted as skipped, not dropped")

    bye = next(m for m in ms if m["player"] == "Bye Guy")
    check(bye["pa_grade"] is None and "bye" in bye["reason"],
          "a team with no game says bye - no grade guessed")
    kick = next(m for m in ms if m["player"] == "Kicker Guy")
    check(kick["opponent"] == "CIN" and kick["pa_grade"] is None,
          "a kicker still reports his real opponent, just no grade")

    wide = matchups.leaguewide_extremes(table, 1, schedule=FIX_SCHEDULE, n=3)
    check(wide["count"] == len(FIX_SCHEDULE) * len(matchups.PA_POSITIONS),
          "every (team, position) pair playing that week is considered (%d)"
          % wide["count"])
    best = wide["best"][0]
    check(best["pos"] == "TE" and best["opponent"] == "CIN"
          and best["pa_grade"] == "SMASH",
          "the best matchup leaguewide is any TE facing CIN")
    check(all(e["basis"] == table["basis"] for e in wide["best"]),
          "leaguewide entries carry the basis with them")
    check(wide["worst"][0]["pa_grade"] in ("AVOID", "TOUGH"),
          "the worst end is the stingy end (%s vs %s)"
          % (wide["worst"][0]["pos"], wide["worst"][0]["opponent"]))
    check(len(wide["best"]) == 3 and len(wide["worst"]) == 3,
          "top/bottom N is honoured (N=3)")


# --- 10. live season ---------------------------------------------------------
#
# Everything here is true in ANY week. The exact values for each side of
# week 1 are pinned in 6b; this section proves the live assembly obeys the
# same rules on whatever nflverse holds today, by cross-checking the table
# against the raw rows it was built from rather than against a calendar.

_BASIS_ONE = re.compile(r"^(\d{4}) (?:season|wk1-\d+), (\d+) games$")
_BASIS_BLEND = re.compile(r"^(\d{4}) (?:season|wk1-(\d+)) \((\d+)%\) \+ "
                          r"(\d{4}) season \((\d+)%\)$")


def _games_on_file(rows):
    """{defense: distinct game ids} straight from raw rows - the same count
    points_allowed() makes, recomputed here without it."""
    seen = {}
    for r in rows:
        opp = norm_team(r.get("opponent_team") or "")
        gid = str(r.get("game_id") or "")
        if opp and gid:
            seen.setdefault(opp, set()).add(gid)
    return dict((d, len(g)) for d, g in seen.items())


def test_live_season():
    print("\n10. LIVE - the real leaguewide table, whatever week it is")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    rows = nflverse.fetch_weekly_stats(PRIOR)
    check(len(rows) > 15000,
          "%d weekly stats fetched (%d rows)" % (PRIOR, len(rows)))
    check(all(r.get("season_type") == "REG" for r in rows),
          "REG filter applied - no playoff games in a per-game rate")

    bad = 0
    checked = 0
    for r in rows:
        if r.get("position") not in matchups.PA_POSITIONS:
            continue
        checked += 1
        if abs(matchups.score_row(r, league.scoring)
               - matchups._f(r.get("fantasy_points_ppr"))) > 0.02:
            bad += 1
    check(checked > 5000 and bad == 0,
          "score_row reproduces nflverse's own PPR column on all %d "
          "QB/RB/WR/TE rows (%d mismatches)" % (checked, bad))

    # Build the live table FIRST, then read the same cached files it just
    # read (same freshness windows), so the cross-checks below see exactly
    # the rows the table was assembled from.
    table = matchups.pa_table(league)
    try:
        cur_live = nflverse.fetch_weekly_stats(CUR, max_age_hours=24.0)
    except RuntimeError:
        cur_live = []
    weeks_on_file = set()
    for r in cur_live:
        try:
            weeks_on_file.add(int(str(r.get("week") or "").strip() or 0))
        except ValueError:
            pass
    weeks_on_file.discard(0)
    n_weeks = len(weeks_on_file)
    print("      today: %d %s week(s) on file (%s) -> basis %r"
          % (n_weeks, CUR, ", ".join(str(w) for w in sorted(weeks_on_file))
             or "none", table["basis"]))

    one = _BASIS_ONE.match(table["basis"])
    blend = _BASIS_BLEND.match(table["basis"])
    check(bool(one) != bool(blend),
          "the live basis is in matchups.py's grammar - one season with a "
          "game count, or two seasons with their shares: %r"
          % table["basis"])
    check(str(PRIOR) in table["basis"],
          "the basis names the prior season - it never leaves the blend")
    check(table["blend"]["weeks_played"] == n_weeks,
          "weeks_played (%d) is the count of distinct %d weeks on file "
          "(%d) - the engine read the same file this test did"
          % (table["blend"]["weeks_played"], CUR, n_weeks))
    check((table["blend"]["current"], table["blend"]["prior"])
          == matchups.blend_weights(n_weeks),
          "the live weights are blend_weights(%d) = %s - the documented "
          "formula applied to the weeks on file"
          % (n_weeks, matchups.blend_weights(n_weeks)))
    if n_weeks == 0:
        state = "PRE-SEASON"
        consistent = (bool(one) and one.group(1) == str(PRIOR)
                      and table["prior_only"] is True
                      and "NOT %d" % CUR in table["caveat"]
                      and str(CUR) not in table["basis"])
    else:
        state = "IN-SEASON"
        consistent = (bool(blend) and blend.group(1) == str(CUR)
                      and blend.group(4) == str(PRIOR)
                      and int(blend.group(3))
                      == round(100 * table["blend"]["current"])
                      and int(blend.group(5))
                      == round(100 * table["blend"]["prior"])
                      and table["prior_only"] is False
                      and "still young" in table["caveat"]
                      and "NOT %d" % CUR not in table["caveat"])
    check(consistent,
          "%s: basis, prior_only, caveat and shares all agree with the "
          "weeks on file (basis %r, prior_only %s)"
          % (state, table["basis"], table["prior_only"]))
    check(table["scoring"] == "ppr",
          "the table was built in espn-1's full-PPR scoring")

    prior_games = _games_on_file(rows)
    cur_games = _games_on_file(cur_live)
    check(len(prior_games) == 32 and set(prior_games.values()) == {17},
          "the %d file is a completed season: 32 defenses, 17 games each"
          % PRIOR)
    check(all(0 <= n <= n_weeks for n in cur_games.values()),
          "no defense has more %d games on file than weeks played (%d)"
          % (CUR, n_weeks))

    for pos in matchups.PA_POSITIONS:
        block = table["by_pos"][pos]
        cells = list(block["defenses"].values())
        ranks = sorted(c["rank"] for c in cells)
        check(block["n"] == 32 and len(ranks) == 32 and ranks[0] == 1
              and ranks[-1] <= 32,
              "%s: all 32 defenses ranked, softest at 1" % pos)
        check(all(sum(1 for c in cells if c["rank"] < r) == r - 1
                  for r in ranks),
              "%s: a valid competition ranking (ties share a rank and the "
              "next rank skips)" % pos)
        shared = sorted(set(r for r in ranks if ranks.count(r) > 1))
        tied_ok = all(len(set(round(c["pa_exact"], 9) for c in cells
                              if c["rank"] == r)) == 1 for r in shared)
        check(tied_ok,
              "%s: the only shared ranks are EXACT rate ties (%s) - ranking "
              "uses the full-precision rate, not the 2dp display value"
              % (pos, ", ".join(str(r) for r in shared) or "none"))
        off = [(c["defense"], c["games"],
                prior_games.get(c["defense"], 0)
                + cur_games.get(c["defense"], 0)) for c in cells
               if c["games"] != prior_games.get(c["defense"], 0)
               + cur_games.get(c["defense"], 0)]
        check(not off,
              "%s: every defense's game count is its %d games + its %d "
              "games on file (%s)"
              % (pos, PRIOR, CUR,
                 "; ".join("%s %d != %d" % o for o in off[:3]) or "all 32"))
        check(not any(c["thin"] for c in cells),
              "%s: no thin samples - a completed prior season underwrites "
              "every cell" % pos)
        grades = [c["grade"] for c in block["defenses"].values()]
        check(1 <= grades.count("SMASH") <= 4
              and 1 <= grades.count("AVOID") <= 4,
              "%s: extremes stay rare - %d SMASH, %d AVOID of 32"
              % (pos, grades.count("SMASH"), grades.count("AVOID")))

    defs = table["by_pos"]["WR"]["defenses"]
    check("LAR" in defs and "LA" not in defs,
          "nflverse's 'LA' is normalized to LAR (one Rams row, not two)")
    check(20.0 < table["by_pos"]["WR"]["mean"] < 45.0
          and 8.0 < table["by_pos"]["QB"]["mean"] < 25.0,
          "PPR means are in a sane NFL range (WR %.1f, QB %.1f)"
          % (table["by_pos"]["WR"]["mean"], table["by_pos"]["QB"]["mean"]))
    check(table["by_pos"]["WR"]["mean"] > table["by_pos"]["TE"]["mean"],
          "defenses allow more to WR groups than to TE groups, as they must")


# --- 11. live week-1 grades for the user's espn-1 starters -----------------

def test_live_roster():
    print("\n11. LIVE - week-1 grades for the espn-1 roster, whatever week it is")
    from engine import lineup as lineup_mod
    from engine import weekly
    from engine.ingest import Matcher
    from engine.models import load_players

    league = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    roster = lineup_mod.load_roster("espn-1")
    if not roster:
        print("  note: no data/rosters/espn-1.yaml - live roster check skipped")
        return
    table = matchups.pa_table(league)
    pool = load_players(os.path.join(HERE, league.rankings_csv))
    merged = weekly.fetch_weekly_projections(1, scoring=league.scoring_label(),
                                             quiet=True)
    b = lineup_mod.build(league, roster["players"], 1, merged,
                         matcher=Matcher(pool))
    players = [p for _, p in b["rows"] if p is not None] + b["bench"]
    ms = matchups.matchups_for_roster(players, 1, league, table=table)

    check(len(ms) == len(players),
          "one matchup row per rostered player (%d)" % len(ms))
    graded = [m for m in ms if m["pa_grade"]]
    check(graded, "at least one player is graded (%d of %d)"
          % (len(graded), len(ms)))
    check(all(m["pa_grade"] in matchups.GRADES for m in graded),
          "every grade is one of %s" % ", ".join(matchups.GRADES))
    check(all(m["opponent"] for m in graded),
          "every graded player has a real week-1 opponent from the schedule")
    check(all(str(PRIOR) in m["evidence"] for m in graded),
          "every graded evidence string names the prior season - it never "
          "leaves the blend, whatever the week")
    check(all(m["prior_only"] == table["prior_only"]
              and m["basis"] == table["basis"] for m in graded),
          "every graded row carries the table's own basis and prior_only "
          "flag (today: prior_only=%s, %r)"
          % (table["prior_only"], table["basis"]))
    check(all(("rosters and schemes have changed since" in m["evidence"])
              == m["prior_only"] for m in graded),
          "the schemes-have-changed warning rides on the evidence exactly "
          "when the grade is prior-only, and only then")
    check(all(m["vote"] == matchups.VOTE_ON.get(m["pa_grade"])
              for m in graded),
          "the vote on every row matches the published grade->vote rule")

    startable = matchups.startable_keys(league, players)
    check(startable and startable <= set(p.key for p in players),
          "startable_keys returns roster keys only (%d of %d)"
          % (len(startable), len(players)))
    starters = set(p.key for _, p in b["rows"] if p is not None)
    check(starters <= startable,
          "every best-lineup starter is startable")
    check(len(startable) > len(starters),
          "plus the one-snap-away cushion (%d starters -> %d startable)"
          % (len(starters), len(startable)))

    ex = matchups.roster_extremes(ms)
    if ex["best"]:
        print("      BEST : %-20s %s" % (ex["best"][0]["player"],
                                         ex["best"][0]["evidence"]))
    if ex["worst"]:
        print("      WORST: %-20s %s" % (ex["worst"][0]["player"],
                                         ex["worst"][0]["evidence"]))


def main():
    print("=" * 74)
    print("POSITIONAL MATCHUP ENGINE TEST")
    print("=" * 74)

    test_bleed_and_stifle()
    test_gates()
    test_abstention()
    test_scoring_sensitivity()
    test_basis_label()
    test_blending()
    test_calendar_boundary()
    test_source_disabled()
    test_consensus_integration()
    test_highlighting()
    test_live_season()
    test_live_roster()

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
