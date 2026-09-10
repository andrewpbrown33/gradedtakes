#!/usr/bin/env python3
"""Acceptance test: cross-league exposure flags (engine/exposure.py).

FIXTURE RULE - read before editing this file:

    Acceptance tests assert INVARIANTS AND BEHAVIOR against controlled
    fixtures. They must NEVER depend on the contents of the user's live
    roster (data/rosters/), source registry (data/sources.yaml), or league
    (leagues/) files. Those files change every time the product is actually
    used - a name is added to a roster, a source is enabled - and a suite
    that asserts today's contents fails for the wrong reason: it reports a
    regression when nothing regressed. Every scenario below builds its own
    roster/league fixture in a tempdir and points the engine at it through
    the module's own seam (Exposure.load(dirpath=...)); the one test that
    touches the live rosters dir asserts structural invariants only and
    names no player.

Proves the flag-only, positive-only contract on planted data: a player on
two fixture rosters flags BOTH leagues, a player on one flags one, a
player on neither flags empty - and that empty is byte-identical to the
no-data-at-all answer, so it can never be rendered as clearance. Coverage
math and the banner are checked at 3/16 (partial) and 16/16 (complete),
unresolvable names are reported rather than counted, and bad input
degrades loudly.

Writes nothing outside tempfile.mkdtemp() dirs removed in finally blocks
(the isolation discipline tests/mock_draft.py applies to save_state.SAVE_DIR).

    .venv/bin/python tests/exposure_test.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.exposure import Exposure                        # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.models import DraftState, LeagueConfig, Player   # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- planted player pool ----------------------------------------------------
# Invented names, so no assertion below can ride on whichever real players
# happen to be in data/rankings.csv this week. The matcher resolves them
# exactly and rejects junk (verified by test_unresolved).

PLANTED = [
    ("Alpha Ashford", "QB", "BUF"),
    ("Bravo Bexley", "RB", "DET"),
    ("Charlie Colter", "RB", "SF"),
    ("Delta Danforth", "WR", "CIN"),
    ("Echo Eastwick", "WR", "MIA"),
    ("Foxtrot Fenwick", "WR", "DAL"),
    ("Golf Garrity", "TE", "KC"),
    ("Hotel Hollis", "K", "BAL"),
    ("India Ingersoll", "RB", "NYJ"),
    ("Juliet Jessup", "WR", "SEA"),
    ("Kilo Kingsley", "QB", "LAR"),
    ("Lima Lockhart", "TE", "PHI"),
    ("Mike Marchetti", "RB", "GB"),
    ("November Norwood", "WR", "HOU"),
    ("Oscar Ottoway", "TE", "DEN"),
    ("Papa Pemberton", "K", "NYG"),
    ("Quebec Quarles", "QB", "ATL"),
    ("Romeo Radcliffe", "RB", "CHI"),
    ("Sierra Stallworth", "WR", "TB"),
    ("Tango Thistle", "RB", "LV"),
]

FIXTURE_LEAGUE = LeagueConfig({
    "id": "fx-draft", "name": "Fixture Draft League", "teams": 10,
    "my_slot": 1,
    "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T",
                     "K", "DEF", "BN", "BN", "BN"],
    "scoring": {"reception": 1},
})


def build_pool():
    pool = [Player(rank=i + 1, name=n, pos=p, team=t)
            for i, (n, p, t) in enumerate(PLANTED)]
    pool.append(Player(rank=len(pool) + 1, name="Baltimore Defense",
                       pos="DEF", team="BAL"))
    return pool


def name_of(i):
    return PLANTED[i][0]


def write_roster(dirpath, filename, league_id, display, size, names):
    """Write one fixture roster yaml; returns its path."""
    path = os.path.join(dirpath, filename)
    with open(path, "w") as fh:
        fh.write("league: %s\n" % league_id)
        fh.write("name: \"%s\"\n" % display)
        fh.write("size: %d\n" % size)
        fh.write("players:\n")
        for n in names:
            fh.write("  - %s\n" % n)
    return path


def key(matcher, name):
    m = matcher.match(name)
    assert m is not None, "fixture player %r missing from the planted pool" % name
    return m.player.key


# --- 1. a known player on two fixture rosters -------------------------------
def test_cross_league_flag(matcher):
    print("\n1. CROSS-LEAGUE FLAG (two fixture leagues, one shared player)")
    tmp = tempfile.mkdtemp(prefix="exposure-cross-")
    try:
        # SHARED = the planted player deliberately placed on BOTH rosters.
        shared, solo_a, solo_b = name_of(1), name_of(0), name_of(9)
        write_roster(tmp, "a-alpha.yaml", "fx-alpha", "Alpha League", 12,
                     [solo_a, shared, name_of(2), name_of(3)])
        write_roster(tmp, "b-bravo.yaml", "fx-bravo", "Bravo League", 12,
                     [shared, solo_b, name_of(10)])

        exp = Exposure.load(matcher, dirpath=tmp)
        check(exp.available, "both fixture rosters loaded (available True)")
        check(len(exp.leagues) == 2, "two leagues in the fixture dir")

        flags = exp.flag(key(matcher, shared))
        check(flags == ["Alpha League", "Bravo League"],
              "a player on BOTH rosters flags BOTH leagues in load order "
              "(got %s)" % (flags,))
        check(exp.flag(key(matcher, solo_a)) == ["Alpha League"],
              "a player on one roster flags exactly that league")
        check(exp.flag(key(matcher, solo_b)) == ["Bravo League"],
              "and the other league's exclusive holding flags only it")

        # Never leak the internal list: a caller mutating the answer must not
        # corrupt the next query.
        got = exp.flag(key(matcher, shared))
        got.append("Injected League")
        check(exp.flag(key(matcher, shared)) == ["Alpha League",
                                                 "Bravo League"],
              "flag() returns a copy - a mutating caller cannot poison state")

        unrostered = name_of(19)   # in the pool, on neither fixture roster
        check(exp.flag(key(matcher, unrostered)) == [],
              "a pool player on neither roster flags empty = NO INFORMATION")
        check(exp.flag("nobody|XX") == [], "unknown key flags empty, no crash")
        check(len(exp) == 6,
              "six distinct flagged keys across the two rosters (got %d)"
              % len(exp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 2. partial coverage math and banner ------------------------------------
def test_partial_coverage(matcher):
    print("\n2. PARTIAL COVERAGE (3 known of a declared 16)")
    tmp = tempfile.mkdtemp(prefix="exposure-partial-")
    try:
        write_roster(tmp, "partial.yaml", "fx-partial", "Partial League", 16,
                     [name_of(0), name_of(1), name_of(2)])
        exp = Exposure.load(matcher, dirpath=tmp)
        check(exp.coverage() == [("Partial League", 3, 16)],
              "coverage is (league, known, declared size) = 3/16 (got %s)"
              % (exp.coverage(),))
        check(exp.partial(), "partial() True while known < size")
        banner = exp.banner_text()
        check("3/16" in banner, "banner names the exact coverage: %r" % banner)
        check("no flag does NOT mean not rostered" in banner,
              "banner carries the positive-only caveat")
        check("Partial League" in banner, "banner names the short league")
        check(exp.unresolved() == [], "every fixture name resolved")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n2b. AN UNRESOLVABLE NAME IS NOT A KNOWN PLAYER")
    tmp = tempfile.mkdtemp(prefix="exposure-partial2-")
    try:
        write_roster(tmp, "partial.yaml", "fx-partial", "Partial League", 16,
                     [name_of(0), "Zzyzx Quorblatt", name_of(1), name_of(2)])
        exp = Exposure.load(matcher, dirpath=tmp)
        check(exp.coverage() == [("Partial League", 3, 16)],
              "4 listed names, 1 unresolvable -> still 3 KNOWN of 16")
        check(exp.unresolved() == [("Partial League", ["Zzyzx Quorblatt"])],
              "the unresolvable name is reported, not silently counted")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 3. complete coverage is still not clearance ----------------------------
def test_complete_is_not_clearance(matcher):
    print("\n3. COMPLETE COVERAGE (16/16) IS NOT A CLEARANCE SIGNAL")
    tmp = tempfile.mkdtemp(prefix="exposure-full-")
    try:
        full = [name_of(i) for i in range(16)]
        write_roster(tmp, "full.yaml", "fx-full", "Full League", 16, full)
        exp = Exposure.load(matcher, dirpath=tmp)
        check(exp.coverage() == [("Full League", 16, 16)],
              "a complete roster reports 16/16 (got %s)" % (exp.coverage(),))
        check(not exp.partial(), "partial() False at full coverage")
        check(exp.banner_text() == "",
              "no coverage banner when nothing is missing")
        check(exp.flag(key(matcher, full[0])) == ["Full League"],
              "a rostered player still flags at full coverage")

        # THE INVARIANT: an empty flag list is the SAME answer with complete
        # data and with no data at all. Nothing in the API turns "no positive
        # hit" into "not rostered elsewhere" - a caller that wants to know how
        # much is known must read coverage(), never an empty flag.
        absent = key(matcher, name_of(19))
        nodata = Exposure.empty()
        check(exp.flag(absent) == nodata.flag(absent) == [],
              "absence of a flag is identical with full data and with NO "
              "data - it can never be rendered as clearance")
        check(exp.coverage() != nodata.coverage(),
              "coverage() IS the honest difference between the two states")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 4. exclusion of the league being drafted -------------------------------
def test_exclusion(matcher):
    print("\n4. EXCLUDING THE LEAGUE BEING DRAFTED")
    tmp = tempfile.mkdtemp(prefix="exposure-exclude-")
    try:
        shared = name_of(1)
        write_roster(tmp, "a-alpha.yaml", "fx-alpha", "Alpha League", 12,
                     [name_of(0), shared])
        write_roster(tmp, "b-bravo.yaml", "fx-bravo", "Bravo League", 12,
                     [shared, name_of(9)])

        exp = Exposure.load(matcher, exclude_league_id="fx-alpha", dirpath=tmp)
        check(exp.flag(key(matcher, name_of(0))) == [],
              "a player held ONLY by the excluded league stops flagging")
        check(exp.flag(key(matcher, shared)) == ["Bravo League"],
              "the shared player still flags the league that is not excluded")
        check(all(n != "Alpha League" for n, _, _ in exp.coverage()),
              "excluded league absent from coverage")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Excluding the ONLY league must go dark rather than render empty flags.
    tmp = tempfile.mkdtemp(prefix="exposure-solo-")
    try:
        write_roster(tmp, "solo.yaml", "fx-solo", "Solo League", 12,
                     [name_of(0), name_of(1)])
        solo = Exposure.load(matcher, exclude_league_id="fx-solo", dirpath=tmp)
        check(not solo.available,
              "excluding the only league leaves no data (available False)")
        check(solo.coverage() == [], "coverage is empty after exclusion")
        check(solo.banner_text() == "", "no banner without data")
        check(not solo.partial(), "partial() False without data")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 5. missing dir / empty semantics ---------------------------------------
def test_empty(matcher):
    print("\n5. MISSING DIRECTORY AND Exposure.empty()")
    exp = Exposure.load(matcher,
                        dirpath=os.path.join(tempfile.gettempdir(),
                                             "war-room-no-such-dir"))
    check(not exp.available, "missing rosters dir yields available False")
    check(exp.flag(key(matcher, name_of(0))) == [] and exp.coverage() == [],
          "missing dir: flag() [] and coverage() []")

    e = Exposure.empty()
    check(not e.available and e.flag("x|WR") == [] and e.coverage() == []
          and e.banner_text() == "" and not e.partial(),
          "Exposure.empty() is inert on every query")


# --- 6. unresolved names and junk files are reported, not fatal -------------
def test_unresolved(matcher):
    print("\n6. UNRESOLVED NAMES AND JUNK FILES (temp roster dir)")
    tmp = tempfile.mkdtemp(prefix="exposure-unres-")
    try:
        write_roster(tmp, "work.yaml", "fx-work", "Work League", 14,
                     [name_of(4), "Zzyzx Quorblatt", name_of(5)])
        # A junk yaml must be skipped, not counted as a league.
        with open(os.path.join(tmp, "notes.yaml"), "w") as fh:
            fh.write("just a string, not a roster\n")

        exp = Exposure.load(matcher, dirpath=tmp)
        check(exp.available, "temp dir loads (available True)")
        check(len(exp.leagues) == 1, "junk yaml skipped, 1 valid league")
        check(exp.flag(key(matcher, name_of(4))) == ["Work League"],
              "real names still flag despite the bogus one")
        unres = exp.unresolved()
        check(unres == [("Work League", ["Zzyzx Quorblatt"])],
              "bogus name reported as unresolved (got %s)" % (unres,))
        check(exp.coverage() == [("Work League", 2, 14)],
              "unresolved name does not count as known (2/14)")
        check("2/14" in exp.banner_text(), "banner reflects the temp league")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 7. overlap with a drafted roster ---------------------------------------
def test_overlap(pool, matcher):
    print("\n7. OVERLAP WITH MY DRAFTED ROSTER (fixture league + rosters)")
    tmp = tempfile.mkdtemp(prefix="exposure-overlap-")
    try:
        held, not_held = name_of(1), name_of(19)
        write_roster(tmp, "other.yaml", "fx-other", "Other League", 12,
                     [held, name_of(2)])

        state = DraftState(FIXTURE_LEAGUE, pool)
        p_held = matcher.match(held).player
        p_free = matcher.match(not_held).player
        state.apply_pick(p_held, 1)    # slot 1 picks 1st overall
        state.apply_pick(p_free, 20)   # snake: pick 20 is slot 1 in a 10-teamer

        exp = Exposure.load(matcher, dirpath=tmp)
        pairs = exp.overlap(state)
        check(len(pairs) == 1 and pairs[0][0].key == p_held.key,
              "only the cross-rostered pick overlaps (got %s)"
              % ([p.name for p, _ in pairs],))
        check(pairs and pairs[0][1] == ["Other League"],
              "overlap names the holding league")
        check(Exposure.empty().overlap(state) == [],
              "empty exposure overlaps nothing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 8. the shipped rosters dir: structure only, never contents -------------
def test_live_dir_structural():
    """Read-only smoke over data/rosters: it must PARSE, nothing more.

    Deliberately asserts no player, league name, or coverage number - those
    are the user's live data and change with every real use of the product.
    Only the invariants the loader itself promises are checked.
    """
    print("\n8. SHIPPED data/rosters - STRUCTURAL INVARIANTS ONLY")
    from engine.models import load_players
    csv_path = os.path.join(HERE, "data", "rankings.csv")
    rosters_dir = os.path.join(HERE, "data", "rosters")
    if not (os.path.exists(csv_path) and os.path.isdir(rosters_dir)):
        check(True, "no shipped rankings/rosters to smoke - skipped")
        return
    live_matcher = Matcher(load_players(csv_path))
    exp = Exposure.load(live_matcher)
    check(isinstance(exp.available, bool), "load() over the live dir returns")
    cov = exp.coverage()
    check(all(isinstance(n, str) and 0 <= k <= s
              for n, k, s in cov),
          "every live league reports 0 <= known <= declared size (got %d "
          "league(s))" % len(cov))
    check(exp.partial() == any(k < s for _, k, s in cov),
          "partial() agrees with the live coverage math")
    check((exp.banner_text() == "") is not exp.partial(),
          "a banner appears exactly when the live data is partial")
    check(all(isinstance(names, list) for _, names in exp.unresolved()),
          "unresolved() is well-formed for the live dir")


def main():
    print("=" * 74)
    print("EXPOSURE - cross-league roster flag acceptance test")
    print("=" * 74)

    pool = build_pool()
    matcher = Matcher(pool)
    print("  planted pool: %d players | every scenario builds its own "
          "roster fixture" % len(pool))

    test_cross_league_flag(matcher)
    test_partial_coverage(matcher)
    test_complete_is_not_clearance(matcher)
    test_exclusion(matcher)
    test_empty(matcher)
    test_unresolved(matcher)
    test_overlap(pool, matcher)
    test_live_dir_structural()

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
