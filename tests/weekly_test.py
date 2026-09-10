#!/usr/bin/env python3
"""Acceptance test: weekly data layer (engine/weekly.py).

Synthetic payloads prove the pure transforms - Sleeper parsing with rookie
suffixes, accents, and city-named defenses; the one-DEF-per-team merge; the
schedule map with LA->LAR normalization and bye-by-absence; implied-total
math from both line sources; rest-of-season summing - then the real cached
feeds are checked for week 1 of 2026 (>=250 projected players incl DEF and
K, all 32 teams scheduled, lines that reconcile with their game totals).

No test here saves state, so no SAVE_DIR redirect is needed; live fetches
land in data/cache like every other fetcher (same as durability_test).

    .venv/bin/python tests/weekly_test.py
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import weekly                                    # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _sleeper_entry(first, last, pos, team, ppr=None, half=None, std=None):
    stats = {}
    if ppr is not None:
        stats["pts_ppr"] = ppr
    if half is not None:
        stats["pts_half_ppr"] = half
    if std is not None:
        stats["pts_std"] = std
    return {"player": {"first_name": first, "last_name": last, "position": pos},
            "team": team, "stats": stats}


# --- 1. sleeper parsing -----------------------------------------------------
def test_sleeper_parse():
    print("\n1. SLEEPER WEEKLY PARSE (names, positions, scorings)")
    payload = [
        _sleeper_entry("Marvin", "Harrison Jr.", "WR", "ARI", ppr=15.2),
        _sleeper_entry("Jose", "Pineiro", "K", "CHI", ppr=7.5),
        _sleeper_entry("Seattle", "Seahawks", "DEF", "SEA", ppr=8.1),
        _sleeper_entry("Kansas City", "Chiefs", "DST", "KC", ppr=7.0),
        _sleeper_entry("Blocking", "Fullback", "FB", "SF", ppr=1.1),
        _sleeper_entry("No", "Projection", "RB", "DAL"),
        _sleeper_entry("Dup", "Name", "RB", "NYG", ppr=3.0),
        _sleeper_entry("Dup", "Name", "RB", "NYJ", ppr=9.0),
        _sleeper_entry("Half", "Only", "TE", "MIA", ppr=4.0, half=3.5, std=3.0),
    ]
    out = weekly._weekly_from_sleeper(payload, "ppr")

    check(name_key("Marvin Harrison Jr.") == name_key("Marvin Harrison"),
          "name_key folds the Jr. suffix (rookie matches suffix-less sources)")
    check(name_key("Marvin Harrison") in out
          and out[name_key("Marvin Harrison")]["proj"] == 15.2,
          "suffixed rookie lands under the suffix-less key")
    check(name_key("José Piñeiro") in out,
          "accented spelling reaches the same key as Sleeper's plain ASCII")
    sea = out.get(name_key("Seattle Seahawks"))
    check(sea is not None and sea["pos"] == "DEF" and sea["team"] == "SEA",
          "city-named defense parsed with pos DEF and team SEA")
    kc = out.get(name_key("Kansas City Chiefs"))
    check(kc is not None and kc["pos"] == "DEF",
          "DST position label normalized to DEF")
    check(name_key("Blocking Fullback") not in out,
          "non-fantasy position (FB) filtered out")
    check(name_key("No Projection") not in out,
          "entry with no points for the scoring is skipped, not zeroed")
    check(out[name_key("Dup Name")]["proj"] == 9.0,
          "duplicate name keeps the larger projection")

    half = weekly._weekly_from_sleeper(payload, "half")
    check(half[name_key("Half Only")]["proj"] == 3.5,
          "scoring parameter selects pts_half_ppr")


# --- 2. merge ---------------------------------------------------------------
def test_merge():
    print("\n2. ESPN+SLEEPER MERGE (primary wins, one DEF per team)")
    espn = {
        name_key("Jahmyr Gibbs"): {"proj": 21.6, "pos": "RB", "team": "DET",
                                   "source": "espn"},
        name_key("Seahawks D/ST"): {"proj": 7.1, "pos": "DEF", "team": "SEA",
                                    "source": "espn"},
    }
    sleeper = {
        name_key("Jahmyr Gibbs"): {"proj": 19.0, "pos": "RB", "team": "DET",
                                   "source": "sleeper"},
        name_key("Seattle Seahawks"): {"proj": 8.1, "pos": "DEF", "team": "SEA",
                                       "source": "sleeper"},
        name_key("Chicago Bears"): {"proj": 6.0, "pos": "DEF", "team": "CHI",
                                    "source": "sleeper"},
        name_key("Deep Sleeper"): {"proj": 2.0, "pos": "WR", "team": "LV",
                                   "source": "sleeper"},
    }
    out = weekly._merge_weekly(espn, sleeper)

    check(out[name_key("Jahmyr Gibbs")]["source"] == "espn"
          and out[name_key("Jahmyr Gibbs")]["proj"] == 21.6,
          "ESPN wins a shared key")
    check(name_key("Seattle Seahawks") not in out,
          "Sleeper's city-named SEA defense dropped - ESPN already has SEA D/ST")
    n_sea_def = sum(1 for r in out.values()
                    if r["pos"] == "DEF" and r["team"] == "SEA")
    check(n_sea_def == 1, "exactly one SEA defense after the merge")
    check(name_key("Chicago Bears") in out,
          "Sleeper defense for a team ESPN lacks is kept")
    check(name_key("Deep Sleeper") in out,
          "Sleeper-only skill player fills in")


# --- 3. espn weekly extraction ----------------------------------------------
def test_espn_weekly():
    print("\n3. ESPN WEEKLY EXTRACTION (zero is a projection, absence is not)")
    records = {
        "a player": {"pos": "RB", "team": "DET", "proj": {"ppr": 100.0},
                     "weekly": {1: 10.5, 2: 0.0}},
        "no weekly": {"pos": "WR", "team": "MIA", "proj": {"ppr": 50.0},
                      "weekly": {}},
    }
    wk1 = weekly._weekly_from_espn(records, 1)
    wk2 = weekly._weekly_from_espn(records, 2)
    wk3 = weekly._weekly_from_espn(records, 3)
    check(wk1["a player"]["proj"] == 10.5 and wk1["a player"]["pos"] == "RB",
          "week 1 projection extracted with position")
    check("a player" in wk2 and wk2["a player"]["proj"] == 0.0,
          "a filed 0.0 (injured/bye) is kept, not treated as missing")
    check("a player" not in wk3 and "no weekly" not in wk1,
          "weeks with no filed entry are absent")


# --- 4. schedule ------------------------------------------------------------
SCHED_ROWS = [
    {"game_id": "2026_01_SF_LA", "season": "2026", "week": "1",
     "game_type": "REG", "gameday": "2026-09-10", "gametime": "20:35",
     "home_team": "LA", "away_team": "SF",
     "total_line": "47.5", "spread_line": "-2.5"},
    {"game_id": "2026_01_NE_SEA", "season": "2026", "week": "1",
     "game_type": "REG", "gameday": "2026-09-09", "gametime": "20:20",
     "home_team": "SEA", "away_team": "NE",
     "total_line": "44.5", "spread_line": "3.5"},
    {"game_id": "2026_02_KC_DEN", "season": "2026", "week": "2",
     "game_type": "REG", "gameday": "2026-09-17", "gametime": "13:00",
     "home_team": "DEN", "away_team": "KC",
     "total_line": "", "spread_line": ""},
    {"game_id": "2025_01_OLD", "season": "2025", "week": "1",
     "game_type": "REG", "gameday": "2025-09-04", "gametime": "20:20",
     "home_team": "PHI", "away_team": "DAL",
     "total_line": "48.5", "spread_line": "7.0"},
    {"game_id": "2026_POST", "season": "2026", "week": "1",
     "game_type": "POST", "gameday": "2027-01-10", "gametime": "13:00",
     "home_team": "GB", "away_team": "MIN",
     "total_line": "40.0", "spread_line": "1.0"},
]


def test_schedule_transform():
    print("\n4. SCHEDULE TRANSFORM (LA->LAR, home/away, bye by absence)")
    out = weekly._schedule_from_rows(SCHED_ROWS, 2026, 1)

    check(sorted(out) == ["LAR", "NE", "SEA", "SF"],
          "week 1 map holds exactly the four teams playing (got %s)" % sorted(out))
    check("LAR" in out and "LA" not in out,
          "nflverse 'LA' normalized to rankings.csv's 'LAR'")
    check(out["LAR"]["opponent"] == "SF" and out["LAR"]["home"] is True,
          "home side carries home=True and the right opponent")
    check(out["SF"]["opponent"] == "LAR" and out["SF"]["home"] is False,
          "away side reciprocates with home=False")
    check(out["SEA"]["kickoff_iso"].startswith("2026-09-09T20:20"),
          "kickoff_iso built from gameday+gametime (ET) - got %s"
          % out["SEA"]["kickoff_iso"])
    check(out["SEA"]["kickoff_iso"] == out["NE"]["kickoff_iso"],
          "both sides of a game share one kickoff")
    check("KC" not in out and "DEN" not in out,
          "a team with no game this week is absent (bye/other-week detection)")
    check("PHI" not in out and "GB" not in out,
          "other seasons and non-REG games are excluded")


# --- 5. lines ---------------------------------------------------------------
def test_lines_transform():
    print("\n5. IMPLIED TOTALS (nflverse and ESPN spread conventions)")
    out = weekly._lines_from_rows(SCHED_ROWS, 2026, 1)

    check(out.get("SEA", {}).get("implied_total") == 24.0
          and out.get("NE", {}).get("implied_total") == 20.5,
          "positive nflverse spread favors home: SEA 24.0 / NE 20.5")
    check(out.get("LAR", {}).get("implied_total") == 22.5
          and out.get("SF", {}).get("implied_total") == 25.0,
          "negative spread favors away: LAR 22.5 / SF 25.0")
    check(abs(out["SEA"]["implied_total"] + out["NE"]["implied_total"]
              - out["SEA"]["game_total"]) < 1e-9,
          "implied pair sums to the game total")
    empty = weekly._lines_from_rows(SCHED_ROWS, 2026, 2)
    check(empty == {}, "games with no filed line are skipped, week returns {}")

    sb = {"events": [{"competitions": [{
        "odds": [{"overUnder": 44.5, "spread": -3.5}],
        "competitors": [
            {"homeAway": "home", "team": {"abbreviation": "SEA"}},
            {"homeAway": "away", "team": {"abbreviation": "NE"}}],
    }]}]}
    out2 = weekly._lines_from_espn_scoreboard(sb)
    check(out2.get("SEA", {}).get("implied_total") == 24.0
          and out2.get("NE", {}).get("implied_total") == 20.5,
          "ESPN convention (negative home spread = favored) matches nflverse")


# --- 6. rest of season ------------------------------------------------------
def test_ros():
    print("\n6. REST OF SEASON (bye zero, week cap, unknown key)")
    records = {
        "steady eddie": {"pos": "RB", "team": "DET", "proj": {"ppr": 170.0},
                         # bye week 9 has no entry; a stray playoff week 19
                         # must not leak into the regular-season sum
                         "weekly": dict([(w, 10.0) for w in range(1, 19)
                                         if w != 9] + [(19, 99.0)])},
    }
    check(weekly.ros_projection("steady eddie", 1, records=records) == 170.0,
          "full-season sum skips the bye week naturally")
    check(weekly.ros_projection("steady eddie", 8, records=records) == 100.0,
          "from week 8: weeks 8-18 minus the week-9 bye = 10 games")
    check(weekly.ros_projection("steady eddie", 18, records=records) == 10.0,
          "final week sums just itself")
    check(weekly.ros_projection("steady eddie", 19, records=records) == 0.0,
          "past week 18 there is nothing left (playoff weeks excluded)")
    check(weekly.ros_projection("who dis", 1, records=records) == 0.0,
          "unknown name_key sums to 0.0 (no data, not a judgment)")


# --- 7. live week 1 ---------------------------------------------------------
def test_live_week1():
    print("\n7. LIVE/CACHED WEEK 1 (2026 feeds)")
    try:
        proj = weekly.fetch_weekly_projections(1, quiet=True)
    except RuntimeError as exc:
        check(False, "fetch_weekly_projections(1) unavailable: %s" % exc)
        return
    n_def = sum(1 for r in proj.values() if r["pos"] == "DEF")
    n_k = sum(1 for r in proj.values() if r["pos"] == "K")
    check(len(proj) >= 250,
          "week 1 has >=250 projected players (got %d)" % len(proj))
    check(n_def >= 20, "week 1 has >=20 defenses (got %d)" % n_def)
    check(n_k >= 20, "week 1 has >=20 kickers (got %d)" % n_k)
    check(all(r["pos"] in weekly.FANTASY_POS for r in proj.values()),
          "every record carries a fantasy position")
    check(all(isinstance(r["proj"], float) for r in proj.values()),
          "every projection is a float")
    def_teams = [r["team"] for r in proj.values() if r["pos"] == "DEF"]
    check(len(def_teams) == len(set(def_teams)),
          "no team fields two defenses after the merge")

    try:
        sched = weekly.fetch_schedule(1)
    except RuntimeError as exc:
        check(False, "fetch_schedule(1) unavailable: %s" % exc)
        return
    check(len(sched) == 32, "week 1 schedule has 32 teams (got %d)" % len(sched))
    check(all(sched[t]["opponent"] in sched
              and sched[sched[t]["opponent"]]["opponent"] == t
              for t in sched), "every opponent link is reciprocal")
    check(all(sched[t]["home"] != sched[sched[t]["opponent"]]["home"]
              for t in sched), "each game has one home and one away side")
    check(all(sched[t]["kickoff_iso"][:4] == "2026" for t in sched),
          "kickoffs are 2026 dates")
    check(weekly.byes(1) == [], "no byes in week 1")
    wk5 = weekly.fetch_schedule(5)
    check(len(wk5) < 32 and len(weekly.byes(5)) == 32 - len(wk5),
          "a bye week's byes() is exactly the complement of its schedule")

    lines = weekly.fetch_game_lines(1)
    if not lines:
        print("  note: no week-1 lines available - fetch_game_lines is "
              "documented optional garnish, so this is not a failure")
        return
    check(all("implied_total" in v for v in lines.values()),
          "every line entry carries implied_total (%d teams)" % len(lines))
    ok = all(abs(lines[t]["implied_total"]
                 + lines[sched[t]["opponent"]]["implied_total"]
                 - lines[t]["game_total"]) < 0.01
             for t in lines if t in sched and sched[t]["opponent"] in lines)
    check(ok, "implied pairs reconcile with their game totals")
    check(all(10.0 < v["implied_total"] < 45.0 for v in lines.values()),
          "implied totals are in a sane NFL range")


def main():
    print("=" * 74)
    print("WEEKLY DATA LAYER TEST")
    print("=" * 74)

    test_sleeper_parse()
    test_merge()
    test_espn_weekly()
    test_schedule_transform()
    test_lines_transform()
    test_ros()
    test_live_week1()

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
