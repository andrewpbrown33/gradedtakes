#!/usr/bin/env python3
"""Acceptance test: durability availability flags (engine/durability.py).

Synthetic games dicts prove the season-counting rules - a rookie is judged
only on seasons he was in the league (the classic bug), a mid-window lost
season counts hard, an ironman greens out - then the real nflverse data is
checked against players whose durability reputation was verified by web
search (Aug 2026): Derrick Henry and Bijan Robinson played all 17 games in
each of 2023-25, Amon-Ra St. Brown missed one game in three years, and
Rashee Rice lost most of 2024 to a knee and six 2025 games to suspension.

    .venv/bin/python tests/durability_test.py
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.durability import availability, load, score          # noqa: E402
from engine.ingest import Matcher                                # noqa: E402
from engine.models import load_players                           # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- 1. rookie neutrality ---------------------------------------------------
def test_rookie_neutrality():
    print("\n1. ROOKIE NEUTRALITY (absent-before-career is no info, not zero)")
    games = {
        "perfect rook": {2025: 17},
        "banged rook": {2025: 13},
        "second year": {2024: 17, 2025: 17},
        "ironman vet": {2023: 17, 2024: 17, 2025: 17},
    }

    got = score("perfect rook", games=games)
    check(got == ("GREEN", "17/17 gms 25"),
          "17-game 2025 rookie is GREEN with 1-season detail (got %s)" % (got,))
    check(availability(games["perfect rook"]) == 1.0
          and availability(games["ironman vet"]) == 1.0,
          "perfect rookie scores 1.0, identical to a 3-season ironman")
    check(availability(games["perfect rook"]) > 0.9,
          "rookie is NOT scored as 17/51 - pre-career seasons dropped")

    got = score("second year", games=games)
    check(got == ("GREEN", "34/34 gms 24-25"),
          "2024 entrant counts only 2024-25 (got %s)" % (got,))

    avail = availability(games["banged rook"])
    check(abs(avail - 13.0 / 17.0) < 1e-9,
          "13-game rookie scores 13/17, not 13/51 (got %.3f)" % avail)


# --- 2. lost seasons count hard --------------------------------------------
def test_lost_season():
    print("\n2. LOST SEASONS (absent AFTER first appearance = played zero)")
    games = {
        "acl guy": {2023: 16, 2025: 15},       # vanished for all of 2024
        "gone since": {2023: 16, 2024: 7},     # never resurfaced in 2025
    }

    got = score("acl guy", games=games)
    check(got is not None and got[0] == "RED",
          "2024-lost-season player flags RED (got %s)" % (got,))
    check(got == ("RED", "31/51 gms 23-25"),
          "lost season shows in the detail as 0 of 17 (got %s)" % (got,))
    avail = availability(games["acl guy"])
    check(avail is not None and avail < 0.65,
          "missing year drags weighted availability under 0.65 (got %.3f)" % avail)

    got = score("gone since", games=games)
    check(got == ("RED", "23/51 gms 23-25"),
          "trailing absence after appearing also counts as zeros (got %s)" % (got,))


# --- 3. ironman / thresholds ------------------------------------------------
def test_ironman():
    print("\n3. IRONMAN AND THRESHOLD SHAPE")
    games = {
        "ironman vet": {2023: 17, 2024: 17, 2025: 17},
        "nicked vet": {2023: 13, 2024: 13, 2025: 13},
        "glitch": {2023: 25, 2024: 17, 2025: 17},   # >17 games clamps
    }
    got = score("ironman vet", games=games)
    check(got == ("GREEN", "51/51 gms 23-25"),
          "51-of-51 ironman is GREEN (got %s)" % (got,))
    got = score("nicked vet", games=games)
    check(got is not None and got[0] == "YELLOW",
          "13-a-year vet lands YELLOW, between the extremes (got %s)" % (got,))
    got = score("glitch", games=games)
    check(got == ("GREEN", "51/51 gms 23-25"),
          "a >17 games data glitch clamps to a full season (got %s)" % (got,))


# --- 4. unknown = None, positive-only ---------------------------------------
def test_unknown(matcher):
    print("\n4. NO DATA MEANS NONE, NEVER A FLAG")
    games = {"someone": {2025: 17}, "empty guy": {}}
    check(score("total stranger", games=games) is None,
          "name absent from all seasons scores None")
    check(score("empty guy", games=games) is None,
          "empty seasons map scores None, not a crash")
    check(availability({}) is None, "availability({}) is None")

    chase = matcher.match("Ja'Marr Chase").player
    synth = {chase.nkey: {2023: 17, 2024: 17, 2025: 17}}
    flags = load(matcher, games=synth)
    check(list(flags.keys()) == [chase.key],
          "load() keys by Player.key and skips every no-data player")
    check(flags[chase.key] == ("GREEN", "51/51 gms 23-25"),
          "load() carries (flag, detail) through")


# --- 5. live nflverse data --------------------------------------------------
def test_live(matcher):
    print("\n5. LIVE DATA (nflverse 2023-25, reputations verified via web)")
    flags = load(matcher)
    check(len(flags) > 100,
          "real data flags a substantial pool (%d players)" % len(flags))
    check(all(f in ("GREEN", "YELLOW", "RED") for f, _ in flags.values()),
          "every live flag is GREEN/YELLOW/RED")

    def flag_of(name):
        m = matcher.match(name)
        assert m is not None, "test player %r missing from rankings pool" % name
        return m.player.key, flags.get(m.player.key)

    # Known durable (verified: Henry and Bijan all 17 three straight years,
    # St. Brown 50 of 51 across 2023-25).
    for name in ("Derrick Henry", "Bijan Robinson", "Amon-Ra St. Brown"):
        key, got = flag_of(name)
        check(got is not None and got[0] == "GREEN",
              "%s comes out GREEN (got %s)" % (name, got))

    key, got = flag_of("Derrick Henry")
    check(got == ("GREEN", "51/51 gms 23-25"),
          "Henry's detail is the full 51/51 (got %s)" % (got,))

    # Known availability risk (verified: Rice played 4 games in 2024 after a
    # knee injury and sat six 2025 games suspended).
    key, got = flag_of("Rashee Rice")
    check(got is not None and got[0] == "RED",
          "Rashee Rice comes out RED (got %s)" % (got,))
    check(got is not None and got[1].startswith("28/51"),
          "Rice's detail shows 28/51 so the WHY is on screen (got %s)" % (got,))

    # 2026 rookie: zero NFL seasons, must be absent (unknown), never RED.
    m = matcher.match("Jeremiyah Love")
    if m is not None:
        check(m.player.key not in flags,
              "2026 rookie (Jeremiyah Love) is absent from flags, not penalized")
    else:
        check(True, "no 2026 rookie in pool to test (skipped)")


def main():
    print("=" * 74)
    print("DURABILITY - availability flag acceptance test")
    print("=" * 74)

    players = load_players(os.path.join(HERE, "data", "rankings.csv"))
    matcher = Matcher(players)
    print("  pool: %d players | window: 2023-25" % len(players))

    test_rookie_neutrality()
    test_lost_season()
    test_ironman()
    test_unknown(matcher)
    test_live(matcher)

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
