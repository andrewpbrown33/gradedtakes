#!/usr/bin/env python3
"""Acceptance test: source performance + hot streaks (engine/performance.py).

The claims this file has to make good on are claims about HONESTY, so most
of the checks are about what the module REFUSES to say:

  * a 2-for-2 source is never HOT - the small-sample floor holds even at
    100%, and a source cannot be HOT at all until it has more graded weeks
    than the rolling window (before that, "recent form" and "baseline" are
    the same number, so the comparison is empty);
  * a thin week cannot start, extend or break a streak, but it is still
    RETURNED in the series so a chart cannot hide it;
  * creator sources REFUSE backfill by name, with a reason that differs
    from the reason an archive-less feed refuses, and neither writes a
    single row;
  * grading is hand-checkable: a fixture of eight calls with the arithmetic
    written out, tie included;
  * the replacement rule is recommend.replacement_levels and nothing else -
    proved against a hand-computed Nth-best on a two-team league;
  * live and backfilled bases are kept apart and never averaged.

Synthetic fixtures do the proving. The last section touches the real 2025
archives, and degrades to a printed note rather than a failure when the
network is down (same rule as weekly_test/durability_test).

NOTHING here writes the real data/performance_history.jsonl or the real
data/source_ledger.jsonl: HISTORY_PATH is redirected into a tempdir and
every ledger/registry read is handed an explicit temp path.

    .venv/bin/python tests/performance_test.py
"""

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import performance as perf                       # noqa: E402
from engine import recommend                                 # noqa: E402
from engine import sources as sources_mod                    # noqa: E402
from engine.models import LeagueConfig                       # noqa: E402

FAILURES = []
TMP = None
REGISTRY = None


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def tmp_path(name):
    return os.path.join(TMP, name)


# --- fixtures ---------------------------------------------------------------

def league(teams=2, spots=("QB", "RB", "RB", "BN"), lid="test-league"):
    return LeagueConfig({"id": lid, "name": lid, "teams": teams,
                         "roster_spots": list(spots),
                         "scoring": {"reception": 1}}, path="")


def graded_rows(source, spec, pos="RB", lid="espn-1", season=2025,
                provenance=None, edge=1.0):
    """[(week, calls, hits)] -> graded rows in performance's row shape."""
    provenance = provenance or perf.PROV_BACKFILL
    out = []
    for week, n, hits in spec:
        for i in range(n):
            hit = i < hits
            out.append({"source": source, "league": lid, "season": season,
                        "week": week, "player": "p%d-%d" % (week, i),
                        "player_key": "p%d-%d" % (week, i), "pos": pos,
                        "call": "start" if i % 2 else "sit",
                        "actual": 10.0, "replacement": 9.0,
                        "margin": edge, "edge": edge if hit else -edge,
                        "band": perf.band_of(edge), "hit": hit,
                        "provenance": provenance})
    return out


def temp_registry():
    """A registry with one of each species, written to the tempdir."""
    path = tmp_path("sources.yaml")
    sources_mod.save_sources([
        {"id": "espn-proj", "name": "ESPN Projections", "type": "feed",
         "handle": "espn-proj", "enabled": True, "weight": 17},
        {"id": "sleeper-proj", "name": "Sleeper Projections", "type": "feed",
         "handle": "sleeper-proj", "enabled": True, "weight": 11},
        {"id": "chen-tiers", "name": "Boris Chen Tiers", "type": "feed",
         "handle": "chen-tiers", "enabled": True, "weight": 11},
        {"id": "house-research", "name": "House Research", "type": "feed",
         "handle": "engine", "enabled": True, "weight": 10},
        {"id": "the-favorites", "name": "The Favorites", "type": "youtube",
         "handle": "https://example.invalid/@x", "enabled": True,
         "weight": 17},
        {"id": "sharp-or-square", "name": "Sharp or Square", "type": "rss",
         "handle": "https://example.invalid/rss", "enabled": True,
         "weight": 17},
        {"id": "off-air", "name": "Disabled Creator", "type": "youtube",
         "handle": "https://example.invalid/@off", "enabled": False,
         "weight": 5},
    ], path)
    return path


# --- 1. grading on a hand-computed fixture ----------------------------------

def test_grading():
    print("\n1. GRADING (score() against arithmetic done by hand)")
    line = 12.0

    g = perf.score({"call": "start", "replacement": line}, 15.5)
    check(g["hit"] is True and g["margin"] == 3.5 and g["edge"] == 3.5
          and g["band"] == "clear",
          "start + 15.5 vs 12.0 = hit, margin +3.5, clear band")

    g = perf.score({"call": "start", "replacement": line}, 12.0)
    check(g["hit"] is True and g["margin"] == 0.0 and g["band"] == "narrow",
          "start + exactly replacement = hit (tie to start, as the ledger "
          "rules), margin 0.0, narrow")

    g = perf.score({"call": "start", "replacement": line}, 4.0)
    check(g["hit"] is False and g["margin"] == -8.0 and g["edge"] == -8.0
          and g["band"] == "loud",
          "start + 4.0 = miss, edge -8.0, LOUD miss")

    g = perf.score({"call": "sit", "replacement": line}, 4.0)
    check(g["hit"] is True and g["margin"] == -8.0 and g["edge"] == 8.0
          and g["band"] == "loud",
          "sit + 4.0 = hit, same margin as the start call, edge flips to "
          "+8.0 (loud right)")

    g = perf.score({"call": "sit", "replacement": line}, 13.9)
    check(g["hit"] is False and g["edge"] == -1.9 and g["band"] == "narrow",
          "sit + 13.9 = miss by 1.9 - narrow, NOT the same as a loud miss")

    g = perf.score({"call": "flex", "replacement": line}, 13.0)
    check(g["hit"] is True and g["call"] == "start",
          "a flex call grades as start-side (consensus.VERDICT_VALUE > 0)")

    g = perf.score({"call": "rank", "replacement": line}, 13.0)
    check(g["hit"] is None and "start/sit" in (g.get("unscorable") or ""),
          "a rank call is unscorable here, exactly as consensus rules")

    g = perf.score({"call": "start", "replacement": line}, None)
    check(g["hit"] is None and "no actual filed" in (g.get("unscorable") or ""),
          "no actual filed -> unscorable, for BOTH directions (no free "
          "bye-week sit hits, no zero-punished start)")
    g = perf.score({"call": "sit", "replacement": line}, None)
    check(g["hit"] is None, "...the sit side is unscorable too (symmetric)")

    g = perf.score({"call": "start", "replacement": None}, 20.0)
    check(g["hit"] is None and "replacement" in (g.get("unscorable") or ""),
          "no replacement line -> unscorable, never a guessed grade")

    src = {"call": "start", "replacement": line, "player": "x"}
    perf.score(src, 20.0)
    check("hit" not in src, "score() does not mutate the call it is given")

    graded = perf.grade_calls(
        [{"call": "start", "replacement": 10.0, "player_key": "a"},
         {"call": "sit", "replacement": 10.0, "player_key": "b"},
         {"call": "start", "replacement": 10.0, "player_key": "gone"}],
        {"a": 14.0, "b": 3.0})
    check([g["hit"] for g in graded] == [True, True, None],
          "grade_calls: 2 graded, the missing actual comes back None")


# --- 2. the replacement rule ------------------------------------------------

def test_replacement_rule():
    print("\n2. REPLACEMENT RULE (recommend.replacement_levels, hand-checked)")
    lg = league(teams=2, spots=("QB", "RB", "RB", "BN"))
    rows = ([{"name": "qb%d" % i, "pos": "QB", "points": p}
             for i, p in enumerate([40.0, 35.0, 30.0])]
            + [{"name": "rb%d" % i, "pos": "RB", "points": p}
               for i, p in enumerate([30.0, 25.0, 20.0, 15.0, 10.0, 5.0])])

    line = perf.replacement_line(lg, rows)
    check(line.get("QB") == 35.0,
          "2 teams x 1 QB = QB2 is the line -> 35.0 (hand-computed)")
    check(line.get("RB") == 15.0,
          "2 teams x 2 RB = RB4 is the line -> 15.0 (hand-computed)")

    demand = perf.starter_demand(lg, rows)
    check(demand.get("QB") == 2 and demand.get("RB") == 4,
          "starter_demand matches the N behind those lines (2 QB, 4 RB)")
    check(perf.rosterable_depth(demand)["RB"] == 8,
          "rosterable depth = demand x %g -> 8 RBs are decision-relevant"
          % perf.ROSTERABLE_MULT)

    direct = recommend.replacement_levels(
        perf._PoolState(lg, perf._pool(rows)))
    check(direct == line,
          "replacement_line IS recommend.replacement_levels - no second "
          "implementation of the rule to drift")

    flex_lg = league(teams=2, spots=("QB", "RB", "RB", "W/R/T", "BN"))
    rows_wr = rows + [{"name": "wr%d" % i, "pos": "WR", "points": p}
                      for i, p in enumerate([28.0, 22.0, 18.0, 12.0])]
    flex_demand = perf.starter_demand(flex_lg, rows_wr)
    hard = flex_lg.hard_starter_counts()
    extra = sum(flex_demand.get(p, 0) - hard.get(p, 0) * flex_lg.teams
                for p in ("RB", "WR", "TE"))
    check(extra == 2,
          "a W/R/T slot x 2 teams adds exactly 2 to flex-eligible demand")
    check(perf.replacement_line(flex_lg, rows_wr).get("RB", 99) <= 15.0,
          "flex demand pushes the RB line DOWN (deeper starter pool), so an "
          "8-team and a 10-team league cannot share a grade")


# --- 3. streak states -------------------------------------------------------

def test_streak_states():
    print("\n3. STREAK STATES (HOT / COLD / STEADY / NO-DATA)")

    hot = perf.summarize(graded_rows(
        "s", [(1, 20, 10), (2, 20, 10), (3, 20, 10), (4, 20, 10),
              (5, 20, 15), (6, 20, 15), (7, 20, 15), (8, 20, 15)]))
    check(hot["hit_rate"] == 0.625 and hot["sample_n"] == 160,
          "fixture baseline is 100/160 = 62.5%")
    check(hot["state"] == "HOT",
          "four straight weeks at 75%% over a 62.5%% baseline = HOT (%s)"
          % hot["state_reason"])
    check(hot["streak"] == 4 and hot["streak_dir"] == 1,
          "...streak reads 4 weeks, direction up")
    check(hot["rolling_rate"] == 0.75 and hot["rolling_calls"] == 80,
          "...rolling window is POOLED calls (60/80), not a mean of rates")

    cold = perf.summarize(graded_rows(
        "s", [(1, 20, 15), (2, 20, 15), (3, 20, 15), (4, 20, 15),
              (5, 20, 10), (6, 20, 10), (7, 20, 10), (8, 20, 10)]))
    check(cold["state"] == "COLD" and cold["streak_dir"] == -1,
          "the mirror fixture is COLD (%s)" % cold["state_reason"])

    steady = perf.summarize(graded_rows(
        "s", [(w, 20, 12) for w in range(1, 9)]))
    check(steady["state"] == "STEADY" and steady["streak"] == 0,
          "every week exactly on its own baseline = STEADY, streak 0 "
          "(a week ON the baseline is not a run week)")

    wobble = perf.summarize(graded_rows(
        "s", [(1, 20, 13), (2, 20, 11), (3, 20, 13), (4, 20, 11),
              (5, 20, 13), (6, 20, 11)]))
    check(wobble["state"] == "STEADY",
          "alternating above/below is STEADY, not a 1-week 'streak'")

    empty = perf.summarize([])
    check(empty["state"] == "NO-DATA" and empty["sample_n"] == 0
          and empty["hit_rate"] is None,
          "no rows = NO-DATA with hit_rate None, not 0%")

    check(set(perf.STATES) == {"HOT", "COLD", "STEADY", "LOW-CONFIDENCE",
                               "NO-DATA"},
          "the documented state vocabulary is the whole vocabulary")


# --- 4. the small-sample guard ----------------------------------------------

def test_small_sample_guard():
    print("\n4. SMALL-SAMPLE GUARD (a 2-for-2 source is NOT hot)")

    two = perf.summarize(graded_rows("s", [(1, 2, 2)]))
    check(two["hit_rate"] == 1.0 and two["sample_n"] == 2,
          "2-for-2 does report 100% over 2 calls - the number is not hidden")
    check(two["state"] == "LOW-CONFIDENCE",
          "...but the STATE is LOW-CONFIDENCE: %s" % two["state_reason"])
    check(two["state"] != "HOT", "...and it is emphatically NOT HOT")

    perfect = perf.summarize(graded_rows("s", [(1, 8, 8), (2, 8, 8),
                                               (3, 8, 8)]))
    check(perfect["sample_n"] == 24 and perfect["state"] == "LOW-CONFIDENCE",
          "24-for-24 across 3 weeks is still under the %d-call floor"
          % perf.MIN_GRADED_CALLS)

    thin_weeks = perf.summarize(graded_rows("s", [(1, 20, 18), (2, 20, 18)]))
    check(thin_weeks["sample_n"] == 40
          and thin_weeks["state"] == "LOW-CONFIDENCE",
          "40 calls but only 2 weeks is LOW-CONFIDENCE - the week floor "
          "(%d) binds independently of the call floor"
          % perf.MIN_GRADED_WEEKS)

    four = perf.summarize(graded_rows(
        "s", [(1, 10, 4), (2, 10, 8), (3, 10, 8), (4, 10, 8)]))
    check(four["state"] == "STEADY",
          "with only ROLLING_N weeks the rolling window IS the baseline, so "
          "no HOT claim is possible yet: %s" % four["state_reason"])

    floor = perf.summarize(graded_rows(
        "s", [(1, 6, 1), (2, 6, 5), (3, 6, 5), (4, 6, 5), (5, 6, 5)]))
    check(floor["sample_n"] == 30 and floor["state"] == "HOT",
          "exactly at the floor (30 calls, 5 weeks) HOT becomes reachable - "
          "the guard is a floor, not a ban")

    for state in ("HOT", "COLD"):
        crowned = [s for s in (two, perfect, thin_weeks, four)
                   if s["state"] == state]
        check(not crowned, "no under-floor fixture reaches %s" % state)


# --- 5. thin weeks ----------------------------------------------------------

def test_thin_weeks():
    print("\n5. THIN WEEKS (kept in the series, barred from the streak)")
    rows = graded_rows("s", [(1, 20, 10), (2, 20, 10), (3, 20, 10),
                             (4, 20, 10), (5, 20, 15), (6, 20, 15),
                             (7, 20, 15), (8, 20, 15), (9, 2, 0)])
    s = perf.summarize(rows)
    check(s["state"] == "HOT",
          "a 0-for-2 final week does not break a HOT run (%s)"
          % s["state_reason"])
    weeks = dict((w["week"], w) for w in s["series"])
    check(weeks[9]["thin"] is True and weeks[9]["n"] == 2,
          "...but week 9 IS in the series, flagged thin - never dropped")
    check(9 not in s["sparkline_weeks"] and len(s["sparkline_values"]) == 8,
          "...and excluded from the sparkline a chart would draw")
    check(s["weeks_n"] == 9 and s["solid_weeks_n"] == 8,
          "weeks_n counts every graded week; solid_weeks_n counts evidence")


# --- 6. per-position splits -------------------------------------------------

def test_per_position():
    print("\n6. PER-POSITION SPLITS (does it read RBs better than WRs?)")
    rows = (graded_rows("s", [(1, 10, 8)], pos="RB")
            + graded_rows("s", [(1, 10, 3)], pos="WR")
            + graded_rows("s", [(1, 4, 2)], pos="TE"))
    pp = perf.per_position(rows)
    check(pp["RB"]["rate"] == 0.8 and pp["RB"]["n"] == 10,
          "RB 8/10 = 80%")
    check(pp["WR"]["rate"] == 0.3, "WR 3/10 = 30%")
    check(pp["TE"]["rate"] == 0.5 and pp["TE"]["n"] == 4, "TE 2/4 = 50%")
    check("QB" not in pp,
          "a position it never called is ABSENT, not reported as 0%")
    ungraded = perf.per_position([{"pos": "RB", "hit": None}])
    check(ungraded == {}, "unscorable rows never enter a positional rate")
    check(pp["RB"]["avg_edge"] is not None,
          "each position carries an average edge, so a 'barely right' "
          "position is distinguishable from a loud one")


# --- 7. backfill: what it produces, and what it refuses ---------------------

# Six RBs and four QBs so the graded universe carries BOTH directions.
# League is 2 teams x (1 QB, 2 RB): QB demand 2, RB demand 4.
#   projected RB line = 4th-best projection  = 3.0 -> 4 starts, 2 sits
#   projected QB line = 2nd-best projection  = 17.0 -> 2 starts, 2 sits
FAKE_WEEK = {
    "star rb": {"proj": 22.0, "pos": "RB", "team": "PHI", "name": "Star RB"},
    "mid rb": {"proj": 12.0, "pos": "RB", "team": "NYG", "name": "Mid RB"},
    "deep rb": {"proj": 6.0, "pos": "RB", "team": "DAL", "name": "Deep RB"},
    "bench rb": {"proj": 3.0, "pos": "RB", "team": "CHI", "name": "Bench RB"},
    "spare rb": {"proj": 2.0, "pos": "RB", "team": "LV", "name": "Spare RB"},
    "scrub rb": {"proj": 1.0, "pos": "RB", "team": "NYJ", "name": "Scrub RB"},
    "star qb": {"proj": 24.0, "pos": "QB", "team": "BUF", "name": "Star QB"},
    "mid qb": {"proj": 17.0, "pos": "QB", "team": "MIA", "name": "Mid QB"},
    "third qb": {"proj": 10.0, "pos": "QB", "team": "CLE", "name": "Third QB"},
    "fourth qb": {"proj": 8.0, "pos": "QB", "team": "TEN", "name": "Fourth QB"},
    "kicker": {"proj": 9.0, "pos": "K", "team": "SF", "name": "A Kicker"},
    "defense": {"proj": 8.0, "pos": "DEF", "team": "SEA", "name": "A D/ST"},
}

# Week 1 actual lines, hand-computed: RB 25/20/18/10/3/0.5 -> 4th = 10.0;
# QB 30/22/9/5 -> 2nd = 22.0. Week 2 drops "deep rb" entirely (no game row)
# to exercise the symmetric-unscorable rule.
FAKE_ACTUALS = {
    1: {"star rb": {"actual": 25.0, "pos": "RB"},
        "mid rb": {"actual": 3.0, "pos": "RB"},
        "deep rb": {"actual": 18.0, "pos": "RB"},
        "bench rb": {"actual": 10.0, "pos": "RB"},
        "spare rb": {"actual": 20.0, "pos": "RB"},
        "scrub rb": {"actual": 0.5, "pos": "RB"},
        "star qb": {"actual": 30.0, "pos": "QB"},
        "mid qb": {"actual": 9.0, "pos": "QB"},
        "third qb": {"actual": 22.0, "pos": "QB"},
        "fourth qb": {"actual": 5.0, "pos": "QB"}},
    2: {"star rb": {"actual": 3.0, "pos": "RB"},
        "mid rb": {"actual": 16.0, "pos": "RB"},
        "bench rb": {"actual": 11.0, "pos": "RB"},
        "spare rb": {"actual": 1.0, "pos": "RB"},
        "scrub rb": {"actual": 4.0, "pos": "RB"},
        "star qb": {"actual": 12.0, "pos": "QB"},
        "mid qb": {"actual": 21.0, "pos": "QB"},
        "third qb": {"actual": 14.0, "pos": "QB"},
        "fourth qb": {"actual": 19.0, "pos": "QB"}},
}


def fake_projections(source_id, season, week):
    return dict((k, dict(v)) for k, v in FAKE_WEEK.items())


def test_backfill_feed():
    print("\n7. BACKFILL (feeds reconstructed, creators refused)")
    lg = league(teams=2, spots=("QB", "RB", "RB", "BN"), lid="test-league")
    path = tmp_path("backfill.jsonl")

    res = perf.backfill_feed("espn-proj", league=lg, season=2025,
                             weeks=[1, 2], registry_path=REGISTRY,
                             projections_fn=fake_projections,
                             actuals=FAKE_ACTUALS, path=path)
    check(res["backfilled"] is True and res["rows"],
          "espn-proj backfills (%d rows over %d weeks)"
          % (len(res["rows"]), len(res["weeks"])))
    check(all(r["provenance"] == "backfill-2025" for r in res["rows"]),
          "EVERY row is tagged provenance='backfill-2025' - a reconstruction "
          "can never be mistaken for something the source said live")
    check(all(r["league"] == "test-league" and r["season"] == 2025
              for r in res["rows"]),
          "every row carries its league and season (grades are league-relative)")
    check(all(r["pos"] in perf.GRADED_POSITIONS for r in res["rows"]),
          "K and DEF are dropped - the actuals feed is offense-only")
    check(all(r.get("proj") is not None and r.get("proj_replacement") is not None
              for r in res["rows"]),
          "each row keeps the projection AND the projected line it implied, "
          "so the reconstructed call is auditable")

    wk1 = dict((r["player_key"], r) for r in res["rows"] if r["week"] == 1)
    wk2 = dict((r["player_key"], r) for r in res["rows"] if r["week"] == 2)
    check(sorted(c["call"] for c in wk1.values())
          == ["sit"] * 4 + ["start"] * 6,
          "week 1 universe splits 6 start / 4 sit - the reconstructed pool "
          "poses real questions, it is not a pile of free benchings")
    check(wk1["star rb"]["call"] == "start" and wk1["star rb"]["hit"] is True,
          "week 1 star RB: start, 25.0 over a 10.0 actual line -> hit")
    check(wk1["mid rb"]["call"] == "start" and wk1["mid rb"]["hit"] is False
          and wk1["mid rb"]["edge"] == -7.0,
          "week 1 mid RB: start, 3.0 vs the 10.0 line -> miss by 7 "
          "(hand-computed)")
    check(wk1["bench rb"]["hit"] is True and wk1["bench rb"]["band"] == "narrow",
          "week 1 bench RB IS the replacement (10.0 vs 10.0) - a hit, and a "
          "NARROW one, which is the whole point of carrying the band")
    check(wk1["spare rb"]["call"] == "sit" and wk1["spare rb"]["hit"] is False,
          "week 1 spare RB: sit call on a 20.0 week -> miss (hand-computed)")
    check(wk1["scrub rb"]["call"] == "sit" and wk1["scrub rb"]["hit"] is True,
          "week 1 scrub RB: sit call, 0.5 points -> hit")
    check(wk1["mid qb"]["call"] == "start" and wk1["mid qb"]["hit"] is False,
          "week 1 mid QB: 17.0 clears its projected line, 9.0 misses the "
          "22.0 actual line")
    check(wk1["third qb"]["call"] == "sit" and wk1["third qb"]["hit"] is False,
          "week 1 third QB: sit call on a QB2 week -> miss")
    check(sum(1 for r in wk1.values() if r["hit"]) == 6,
          "week 1 grades 6 of 10 by hand - and the module agrees")
    check(wk2["deep rb"]["hit"] is None
          and "no actual filed" in wk2["deep rb"]["unscorable"],
          "week 2 deep RB never took a snap: unscorable, kept, counted")

    on_disk = perf.read_history(path)
    check(len(on_disk) == len(res["rows"]),
          "rows land in the history file, not the ledger (%d)" % len(on_disk))
    check(not os.path.exists(perf.HISTORY_PATH)
          or perf.HISTORY_PATH.startswith(TMP),
          "the test never writes the real data/performance_history.jsonl")

    again = perf.backfill_feed("espn-proj", league=lg, season=2025,
                               weeks=[1, 2], registry_path=REGISTRY,
                               projections_fn=fake_projections,
                               actuals=FAKE_ACTUALS, path=path)
    check(len(perf.read_history(path)) == len(again["rows"]),
          "re-running REPLACES that league/source/season/week instead of "
          "stacking a second copy of the same reconstruction")

    missing = perf.backfill_feed("espn-proj", league=lg, season=2025,
                                 weeks=[1, 2, 3], registry_path=REGISTRY,
                                 projections_fn=fake_projections,
                                 actuals=FAKE_ACTUALS, path=path,
                                 write=False)
    check(any("week 3" in n and "no actuals" in n for n in missing["notes"]),
          "a week with no actuals is skipped WITH a note, never graded blind")


def test_backfill_refusals():
    print("\n8. REFUSALS (creators, and feeds with no archive, differ)")
    lg = league(lid="test-league")
    path = tmp_path("refusals.jsonl")

    creators = ["the-favorites", "sharp-or-square"]
    reasons = {}
    for sid in creators:
        res = perf.backfill_feed(sid, league=lg, weeks=[1, 2],
                                 registry_path=REGISTRY,
                                 projections_fn=fake_projections,
                                 actuals=FAKE_ACTUALS, path=path)
        reasons[sid] = res["reason"]
        check(res["backfilled"] is False and res["rows"] == [],
              "%s refuses backfill and produces ZERO rows" % sid)
        check("starts accumulating week 1" in res["reason"],
              "%s says so honestly: %.60s..." % (sid, res["reason"]))
    check(not os.path.exists(path),
          "a refusal writes NOTHING - the history file was never created")

    chen = perf.backfill_feed("chen-tiers", league=lg, weeks=[1],
                              registry_path=REGISTRY,
                              projections_fn=fake_projections,
                              actuals=FAKE_ACTUALS, path=path)
    check(chen["backfilled"] is False and "borischen" in chen["reason"],
          "chen-tiers refuses for a DIFFERENT reason - no published archive, "
          "not 'we never recorded it'")
    check(chen["reason"] != reasons["the-favorites"],
          "...and the two refusal reasons are not the same sentence")

    house = perf.backfill_feed("house-research", league=lg, weeks=[1],
                               registry_path=REGISTRY,
                               projections_fn=fake_projections,
                               actuals=FAKE_ACTUALS, path=path)
    check(house["backfilled"] is False and "2025" in house["reason"],
          "house-research is feed-typed but hand-written, so it has no "
          "archive either - classified on content, not on the type field")

    ghost = perf.backfill_feed("not-a-source", league=lg, weeks=[1],
                               registry_path=REGISTRY, path=path)
    check(ghost["backfilled"] is False and "registry" in ghost["reason"],
          "an unknown id is refused with a registry reason, never invented")

    caps = dict((s["id"], perf.backfill_capability(s)[0])
                for s in sources_mod.load_sources(REGISTRY))
    check(caps == {"espn-proj": True, "sleeper-proj": True,
                   "chen-tiers": False, "house-research": False,
                   "the-favorites": False, "sharp-or-square": False,
                   "off-air": False},
          "backfill_capability agrees source by source with the registry")

    every = perf.backfill_all(league=lg, weeks=[1], registry_path=REGISTRY,
                              path=path, quiet=True)
    check(len(every) == 6 and sum(1 for r in every if r["backfilled"]) == 2,
          "backfill_all covers the 6 ENABLED sources and backfills 2 - the "
          "refusals come back as results, not as silence")


# --- 9. the page API --------------------------------------------------------

def test_scoreboard():
    print("\n9. source_scoreboard + history_series")
    path = tmp_path("board.jsonl")
    ledger = tmp_path("ledger.jsonl")
    lg = league(teams=2, spots=("QB", "RB", "RB", "BN"), lid="espn-1")

    perf.append_history(
        graded_rows("espn-proj", [(w, 20, 13) for w in range(1, 9)],
                    lid="espn-1")
        + graded_rows("sleeper-proj",
                      [(1, 20, 10), (2, 20, 10), (3, 20, 10), (4, 20, 10),
                       (5, 20, 15), (6, 20, 15), (7, 20, 15), (8, 20, 15)],
                      lid="espn-1")
        + graded_rows("espn-proj", [(1, 20, 20)], lid="other-league"),
        path=path)

    sb = perf.source_scoreboard(lg, registry_path=REGISTRY, path=path,
                                ledger_path=ledger)
    rows = dict((r["source"], r) for r in sb["rows"])
    check(len(sb["rows"]) == 6 and "off-air" not in rows,
          "one row per ENABLED source (6), disabled sources excluded")
    check([r["weight"] for r in sb["rows"]]
          == sorted((r["weight"] for r in sb["rows"]), reverse=True),
          "rows come back heaviest-weight first")

    for sid in ("the-favorites", "sharp-or-square", "chen-tiers",
                "house-research"):
        r = rows[sid]
        check(r["state"] == "NO-DATA" and r["sample_n"] == 0
              and r["hit_rate"] is None and r["provenance"] == "none",
              "%s is on the board at NO-DATA - never dropped, so the page "
              "cannot imply the feeds are all there is" % sid)

    e = rows["espn-proj"]
    check(e["provenance"] == "backfill-2025" and e["sample_n"] == 160,
          "espn-proj's headline numbers are labelled backfill-2025")
    check(e["sample_n"] == 160,
          "...and the other-league rows are NOT counted in this league's "
          "sample (160, not 180)")
    check(e["state"] == "NO-DATA" and "has not been played" in e["state_reason"],
          "STATE is a claim about NOW, so with an empty ledger it is "
          "NO-DATA even for a richly backfilled feed")
    check(e["backfill_state"] == "STEADY",
          "...the 2025 form read is carried separately as backfill_state")
    check(rows["sleeper-proj"]["backfill_state"] == "HOT"
          and rows["sleeper-proj"]["state"] == "NO-DATA",
          "a source that ENDED 2025 hot shows backfill_state HOT and current "
          "state NO-DATA - the badge cannot leak across seasons")
    for key in ("name", "weight", "state", "hit_rate", "sample_n", "streak",
                "sparkline_values", "per_position", "provenance"):
        check(key in e, "scoreboard row carries the documented key %r" % key)

    with open(ledger, "w") as fh:
        for wk in (1, 2, 3):
            for i in range(8):
                fh.write(json.dumps({
                    "league": "espn-1", "week": wk, "source": "espn-proj",
                    "player": "live%d" % i, "player_key": "live%d" % i,
                    "pos": "RB", "verdict": "start" if i % 2 else "sit",
                    "actual": 14.0, "replacement": 10.0,
                    "hit": i < 6}) + "\n")
    sb2 = perf.source_scoreboard(lg, registry_path=REGISTRY, path=path,
                                 ledger_path=ledger)
    e2 = dict((r["source"], r) for r in sb2["rows"])["espn-proj"]
    check(e2["provenance"] == "live" and e2["sample_n"] == 24,
          "once live rows exist they become the headline basis (24 calls)")
    check(set(e2["bases"]) == {"live", "backfill-2025"},
          "both bases are carried, broken out")
    check(e2["bases"]["live"]["sample_n"] == 24
          and e2["bases"]["backfill-2025"]["sample_n"] == 160,
          "...and never averaged into one undifferentiated number")
    check(e2["state"] == "LOW-CONFIDENCE",
          "24 live calls over 3 weeks is LOW-CONFIDENCE - a fat 2025 "
          "backfill sitting beside it does NOT promote the live read")
    check(e2["bases"]["live"]["hit_rate"] == 0.75,
          "the live basis grades off the ledger's OWN hit field - the "
          "ledger is read, never re-graded")

    series = perf.history_series("sleeper-proj", league=lg, path=path,
                                 ledger_path=ledger, basis="backfill-2025")
    check(len(series["weeks"]) == 8 and len(series["values"]) == 8,
          "history_series returns 8 weekly points for charting")
    check(series["weeks"][0]["week"] == 1
          and series["weeks"][-1]["rate"] == 0.75,
          "...ascending by week, with the realized rate per week")
    check(series["basis"] == "backfill-2025" and series["state"] == "HOT",
          "...labelled with its basis, and carrying that basis's state")
    empty = perf.history_series("the-favorites", league=lg, path=path,
                                ledger_path=ledger)
    check(empty["weeks"] == [] and empty["state"] == "NO-DATA",
          "a creator's series is honestly empty, not a flat line at zero")


# --- 10. the real 2025 archives --------------------------------------------

def test_live_archive():
    print("\n10. LIVE ARCHIVE (real 2025 feeds - degrades to a note offline)")
    lg = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    path = tmp_path("live.jsonl")
    try:
        res = perf.backfill_feed("espn-proj", league=lg, season=2025,
                                 weeks=[1, 2, 3], path=path)
    except RuntimeError as exc:
        print("  note: 2025 archive unreachable (%s) - documented honest "
              "degradation, not a failure" % exc)
        return
    if not res["backfilled"] or not res["rows"]:
        print("  note: no rows returned (%s) - offline or archive moved"
              % (res["notes"][:1] or res["reason"]))
        return
    check(len(res["weeks"]) == 3, "three real 2025 weeks graded")
    check(all(r["provenance"] == "backfill-2025" for r in res["rows"]),
          "real rows carry the backfill provenance tag too")
    rate = perf.summarize(res["rows"])["hit_rate"]
    check(rate is not None and 0.35 < rate < 0.85,
          "ESPN's reconstructed 2025 hit rate is %.1f%% - a plausible "
          "number, not a suspicious 90%%+ that would mean the graded "
          "universe is too easy" % (100 * rate))
    pp = perf.summarize(res["rows"])["per_position"]
    check(set(pp) <= set(perf.GRADED_POSITIONS) and len(pp) >= 3,
          "positional splits cover the offense-only graded positions: %s"
          % ", ".join(sorted(pp)))
    starts = perf._direction_split(res["rows"], "start")
    sits = perf._direction_split(res["rows"], "sit")
    check(starts["n"] > 0 and sits["n"] > 0,
          "the graded universe contains BOTH real start calls (%d) and real "
          "sit calls (%d) - not a pile of free benchings"
          % (starts["n"], sits["n"]))
    check(perf.season_actuals(2025).get(1),
          "season_actuals(2025) yields week-1 actuals from nflverse")


# --- backfill decay schedule (owner spec: retire the archive by week 3) -----
def test_backfill_decay():
    print("\nBACKFILL DECAY SCHEDULE")
    from engine import performance as P

    # The schedule itself.
    for weeks, want in ((0, 1.00), (1, 0.60), (2, 0.30), (3, 0.0),
                        (4, 0.0), (17, 0.0)):
        got = P.backfill_weight(weeks)
        check(abs(got - want) < 1e-9,
              "week %d -> archive carries %.0f%% (got %.0f%%)"
              % (weeks, 100 * want, 100 * got))

    # Blended headline moves monotonically from archive toward live.
    live = {"hit_rate": 0.50}
    back = {"hit_rate": 0.70}
    bases = {P.PROV_LIVE: live, P.PROV_BACKFILL: back}
    seen = [P.blend_bases(bases, w)["hit_rate"] for w in (0, 1, 2, 3)]
    check(abs(seen[0] - 0.70) < 1e-9, "pre-season headline is the archive")
    check(abs(seen[3] - 0.50) < 1e-9, "week 3 headline is live only")
    check(seen[0] > seen[1] > seen[2] > seen[3],
          "headline decays monotonically toward the live record")

    # Retirement is absolute: a gaudy archive cannot leak back in.
    late = P.blend_bases({P.PROV_LIVE: {"hit_rate": 0.40},
                          P.PROV_BACKFILL: {"hit_rate": 0.99}}, 6)
    check(abs(late["hit_rate"] - 0.40) < 1e-9,
          "a retired archive cannot inflate a live number")
    check(late["retired"] and "retired" in late["note"],
          "retirement is stated, not silent")

    # Creators own no archive, so decay never touches them.
    solo = P.blend_bases({P.PROV_LIVE: {"hit_rate": 0.55}}, 0)
    check(solo["weight_backfill"] == 0.0 and solo["label"] == "this season",
          "a creator's number is never diluted by an archive it lacks")

    # Every blend says what it is made of.
    for weeks in (0, 1, 2, 3):
        b = P.blend_bases(bases, weeks)
        check(bool(b["label"]) and bool(b["note"]),
              "week %d blend carries a label and a note" % weeks)

    # The pure bases survive blending - a reader can still see each alone.
    check(bases[P.PROV_LIVE]["hit_rate"] == 0.50
          and bases[P.PROV_BACKFILL]["hit_rate"] == 0.70,
          "blending never mutates the underlying bases")


def main():
    global TMP, REGISTRY
    print("=" * 74)
    print("SOURCE PERFORMANCE + HOT STREAKS TEST")
    print("=" * 74)
    TMP = tempfile.mkdtemp(prefix="perf-test-")
    real_history = perf.HISTORY_PATH
    perf.HISTORY_PATH = os.path.join(TMP, "performance_history.jsonl")
    try:
        REGISTRY = temp_registry()
        test_grading()
        test_replacement_rule()
        test_streak_states()
        test_small_sample_guard()
        test_thin_weeks()
        test_per_position()
        test_backfill_feed()
        test_backfill_refusals()
        test_scoreboard()
        test_live_archive()
        test_backfill_decay()
    finally:
        perf.HISTORY_PATH = real_history
        shutil.rmtree(TMP, ignore_errors=True)

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
