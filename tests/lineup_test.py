#!/usr/bin/env python3
"""Acceptance test: lineup optimizer (engine/lineup.py).

FIXTURE RULE - read before editing this file:

    Acceptance tests assert INVARIANTS AND BEHAVIOR against controlled
    fixtures. They must NEVER depend on the contents of the user's live
    roster (data/rosters/), source registry (data/sources.yaml), or league
    (leagues/) files. Those files change every time the product is actually
    used - a name is added to a roster, a league is re-scored - and a suite
    that asserts today's contents fails for the wrong reason: it reports a
    regression when nothing regressed. Every roster/league scenario below is
    written into a tempdir and reached through the module's own seam
    (lineup.load_roster(dirpath=...), or the module-constant redirect in a
    try/finally that tests/mock_draft.py::test_persistence uses for
    save_state.SAVE_DIR).

Synthetic checks first - sigma estimation from planted xFP rows, the
normal-approx verdict math (a 0.2-pt edge must read ~50-60%, never 99%),
an obvious start that produces NO verdict, a flex contest that produces
one, bye/zero/no-projection starter alerts, DEF resolution through the
matcher, and the honest partial/missing-roster banners. Then BOTH roster
coverage states are driven from fixture roster files - a partial roster
(3 of 16: open slots plus the banner) and a complete one (every slot
filled, NO banner) - so neither state can regress unnoticed. Finally the
live cached feeds drive a fixture league in a temp project root, plus a
CLI smoke run against that same fixture.

No test here saves engine state, so no SAVE_DIR redirect is needed (same
as weekly_test); the only writes are fetcher caches in data/cache and
files inside tempfile.mkdtemp() dirs removed in finally blocks.

    .venv/bin/python tests/lineup_test.py
"""

import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import lineup                                    # noqa: E402
from engine.models import LeagueConfig, Player               # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


LEAGUE = LeagueConfig({
    "id": "test-lineup", "name": "Test League", "teams": 10,
    "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T",
                     "K", "DEF", "BN", "BN", "BN"],
    "scoring": {"reception": 1},
})

VERDICT_RE = re.compile(
    r"^Start .+ over .+ - (\d+)% - .+ median \d+\.\d \(\d+-\d+\) "
    r"vs .+ \d+\.\d \(\d+-\d+\) - .+$")


def _proj(entries):
    """[(name, pos, team, pts-or-None)] -> weekly projections dict."""
    out = {}
    for name, pos, team, pts in entries:
        if pts is None:
            continue
        out[name_key(name)] = {"proj": float(pts), "pos": pos, "team": team,
                               "source": "espn"}
    return out


class StubMatch(object):
    def __init__(self, player, score=100.0):
        self.player, self.score = player, score


class StubMatcher(object):
    """Exact-normalized-name matcher over a tiny pool - no rankings CSV."""

    def __init__(self, pool):
        self.pool = dict((name_key(p.name), p) for p in pool)

    def match(self, text):
        p = self.pool.get(name_key(text))
        return StubMatch(p) if p is not None else None


# --- fixtures ---------------------------------------------------------------
# A 10-starter / 6-bench league of our own, so no assertion below rides on
# whatever leagues/*.yaml happens to say today.

FIXTURE_LEAGUE_DATA = {
    "id": "fx-lineup", "name": "Fixture Lineup League", "teams": 10,
    "my_slot": 1,
    "roster_spots": ["QB", "WR", "WR", "RB", "RB", "TE", "W/R/T", "W/R/T",
                     "K", "DEF"] + ["BN"] * 6,
    "rounds": 16,
    "rankings_csv": "data/rankings.csv",
    "scoring": {"reception": 1},
}
FIXTURE_LEAGUE = LeagueConfig(FIXTURE_LEAGUE_DATA)
FIXTURE_STARTING_SLOTS = 10     # QB WR WR RB RB TE W/R/T W/R/T K DEF

# Sixteen planted players that cover every starting slot with six left over.
FULL_ROSTER = [
    ("Quincy Quarter", "QB", "BUF", 20.0),
    ("Walt Whiskey", "WR", "CIN", 19.0),
    ("Xavier Xray", "WR", "MIA", 17.0),
    ("Aaron Alpha", "RB", "DET", 18.0),
    ("Bob Bravo", "RB", "SF", 15.0),
    ("Tom Tango", "TE", "KC", 11.0),
    ("Yani Yankee", "WR", "DAL", 13.0),      # flex 1
    ("Carl Charlie", "RB", "NYJ", 12.0),     # flex 2
    ("Kick Kappa", "K", "BAL", 8.0),
    ("Ravens D/ST", "DEF", "BAL", 7.0),
    ("Zulu Zephyr", "WR", "SEA", 6.0),       # bench
    ("Victor Victory", "RB", "GB", 5.5),     # bench
    ("Uniform Upton", "TE", "PHI", 5.0),     # bench
    ("Sierra Sloan", "QB", "LAR", 14.0),     # bench
    ("Papa Pike", "K", "NYG", 7.5),          # bench
    ("Broncos D/ST", "DEF", "DEN", 6.5),     # bench
]
assert len(FULL_ROSTER) == 16


def write_roster_file(dirpath, league_id, display, size, names):
    """Write one fixture data/rosters/<league>.yaml; returns its path."""
    path = os.path.join(dirpath, "%s.yaml" % league_id)
    with open(path, "w") as fh:
        fh.write("league: %s\n" % league_id)
        fh.write("name: \"%s\"\n" % display)
        fh.write("size: %d\n" % size)
        fh.write("players:\n")
        for n in names:
            fh.write("  - %s\n" % n)
    return path


# --- 1. sigma estimation ----------------------------------------------------
def _xfp_row(pos, xfp, actual):
    return {"position": pos, "total_fantasy_points_exp": str(xfp),
            "total_fantasy_points": str(actual)}


def test_sigma():
    print("\n1. SIGMA FROM XFP RESIDUALS (startable floor, position filter)")
    rows = []
    # 60 RB weeks alternating +/-4 around expectation -> sigma exactly 4.0
    for i in range(60):
        rows.append(_xfp_row("RB", 12.0, 12.0 + (4.0 if i % 2 else -4.0)))
    # 60 TE weeks alternating +/-2 -> sigma exactly 2.0
    for i in range(60):
        rows.append(_xfp_row("TE", 8.0, 8.0 + (2.0 if i % 2 else -2.0)))
    # mop-up weeks below the floor and junk positions must be ignored
    rows += [_xfp_row("RB", 1.0, 40.0)] * 30
    rows += [_xfp_row("DB", 10.0, 0.0)] * 60
    rows += [_xfp_row("NA", 10.0, 0.0)] * 60
    # a thin position (under MIN_SIGMA_SAMPLES) must not override defaults
    rows += [_xfp_row("QB", 10.0, 30.0)] * 5

    sigmas, counts = lineup._sigma_from_rows(rows)
    check(sigmas.get("RB") == 4.0, "RB sigma computed from residuals (4.0)")
    check(sigmas.get("TE") == 2.0, "TE sigma computed from residuals (2.0)")
    check(counts.get("RB") == 60,
          "sub-floor xfp weeks excluded (RB count stays 60)")
    check("DB" not in sigmas and "NA" not in sigmas,
          "non-fantasy position rows ignored")
    check("QB" not in sigmas and counts.get("QB") == 5,
          "a position with too few samples yields no override")


# --- 2. verdict math --------------------------------------------------------
def test_probability():
    print("\n2. NORMAL-APPROX P(A BEATS B)")
    p = lineup.p_first_beats(12.0, 10.0, 5.0, 5.0)
    q = lineup.p_first_beats(10.0, 12.0, 5.0, 5.0)
    check(abs(p + q - 1.0) < 1e-9, "P(A>B) and P(B>A) sum to 1")
    check(0.5 < p < 0.7, "a 2-pt edge at sigma 5 is a lean, not a lock")
    check(lineup.p_first_beats(10.0, 10.0, 5.0, 5.0) == 0.5,
          "equal medians = exactly 50%")
    check(lineup.p_first_beats(30.0, 5.0, 5.0, 5.0) > 0.99,
          "a 25-pt gap approaches certainty")
    check(lineup.p_first_beats(12.0, 10.0, 0.0, 0.0) == 1.0,
          "degenerate zero sigma falls back to a hard compare")


# --- 3. obvious start: right lineup, no verdict -----------------------------
OBVIOUS = [
    ("Quincy Quarter", "QB", "BUF", 20.0),
    ("Aaron Alpha", "RB", "DET", 18.0),
    ("Bob Bravo", "RB", "SF", 15.0),
    ("Carl Charlie", "RB", "NYJ", 5.0),      # planted: clearly benched
    ("Walt Whiskey", "WR", "CIN", 20.0),
    ("Xavier Xray", "WR", "MIA", 17.0),
    ("Yani Yankee", "WR", "DAL", 12.0),      # flex, 7 clear of Charlie
    ("Tom Tango", "TE", "KC", 9.0),
    ("Kick Kappa", "K", "BAL", 8.0),
    ("Ravens D/ST", "DEF", "BAL", 7.0),
]


def test_obvious_start():
    print("\n3. PLANTED OBVIOUS START (clear margins produce zero verdicts)")
    names = [e[0] for e in OBVIOUS]
    b = lineup.build(LEAGUE, names, 1, _proj(OBVIOUS),
                     sigmas=dict(lineup.DEFAULT_SIGMA))
    started = [p.name for _, p in b["rows"] if p is not None]
    check("Aaron Alpha" in started and "Bob Bravo" in started,
          "both top RBs start")
    check("Yani Yankee" in started, "third WR takes the flex")
    check("Carl Charlie" not in started
          and any(p.name == "Carl Charlie" for p in b["bench"]),
          "the planted 5-pt RB rides the bench")
    check(b["missing"] == [], "every slot fills from a full synthetic roster")
    check(abs(b["total"] - 126.0) < 1e-9,
          "lineup total is the sum of starters (126.0, got %.1f)" % b["total"])
    check(b["verdicts"] == [],
          "no verdicts - every call is outside the margins")
    check(b["alerts"] == [], "no alerts on a healthy, scheduled-agnostic run")


# --- 4. coin flip -----------------------------------------------------------
def test_coin_flip():
    print("\n4. COIN FLIP (0.2-pt RB gap must read ~50-60%, not 99%)")
    entries = list(OBVIOUS)
    entries[2] = ("Bob Bravo", "RB", "SF", 11.9)
    entries[3] = ("Carl Charlie", "RB", "NYJ", 11.7)
    names = [e[0] for e in entries]
    b = lineup.build(LEAGUE, names, 1, _proj(entries),
                     sigmas=dict(lineup.DEFAULT_SIGMA))
    rb = [v for v in b["verdicts"] if v["slot"] == "RB"]
    check(len(rb) == 1,
          "the contested RB slot draws exactly one verdict (got %d)"
          % len(rb))
    check(len(b["verdicts"]) == 2,
          "flex is also contested (Charlie within 5 of the flex WR)")
    if not rb:
        return
    v = rb[0]
    m = VERDICT_RE.match(v["text"])
    check(m is not None, "verdict follows the framing format: %r" % v["text"])
    check(v["text"].startswith("Start Bob Bravo over Carl Charlie"),
          "the higher median starts")
    check(50 <= v["pct"] <= 60,
          "confidence is honest: %d%% (a 0.2-pt edge is a coin flip)"
          % v["pct"])
    check("coin flip" in v["text"], "reason says coin flip")


# --- 5. flex contest --------------------------------------------------------
def test_flex_contest():
    print("\n5. FLEX CONTEST (bench within 5 of the flex draws a verdict)")
    entries = list(OBVIOUS)
    entries[3] = ("Carl Charlie", "RB", "NYJ", 9.5)   # 2.5 behind the flex WR
    names = [e[0] for e in entries]
    lines = {"DAL": {"implied_total": 27.5, "game_total": 51.0},
             "NYJ": {"implied_total": 17.5, "game_total": 41.0}}
    b = lineup.build(LEAGUE, names, 1, _proj(entries), lines=lines,
                     sigmas=dict(lineup.DEFAULT_SIGMA))
    fv = [v for v in b["verdicts"] if v["slot"] == "W/R/T"]
    check(len(fv) == 1, "one flex verdict emitted")
    if not fv:
        return
    check(fv[0]["text"].startswith("Start Yani Yankee over Carl Charlie"),
          "flex verdict frames the WR over the bench RB")
    check("DAL implied 27.5 vs NYJ 17.5" in fv[0]["text"],
          "implied-total garnish becomes the reason when the gap is wide")


# --- 6. alerts --------------------------------------------------------------
def test_alerts():
    print("\n6. STARTER ALERTS (bye, filed zero, no projection, injury)")
    entries = [
        ("Quincy Quarter", "QB", "KC", 19.0),     # KC absent from schedule
        ("Aaron Alpha", "RB", "DET", 18.0),
        ("Walt Whiskey", "WR", "CIN", 20.0),
        ("Xavier Xray", "WR", "MIA", 17.0),
        ("Yani Yankee", "WR", "DAL", 12.0),
        ("Tom Tango", "TE", "KC", 0.0),           # filed zero
        ("Kick Kappa", "K", "BAL", 8.0),
        ("Ravens D/ST", "DEF", "BAL", 7.0),
        ("Ghost Runner", "RB", "DAL", None),      # no projection filed
    ]
    sched = dict((t, {"opponent": "OPP", "home": True,
                      "kickoff_iso": "2026-09-13T13:00:00-04:00"})
                 for t in ("DET", "SF", "CIN", "MIA", "DAL", "BAL"))
    pool = [Player(rank=1, name="Ghost Runner", pos="RB", team="DAL")]
    injuries = {name_key("Xavier Xray"): "Questionable",
                name_key("Walt Whiskey"): "Out"}
    b = lineup.build(LEAGUE, [e[0] for e in entries], 3, _proj(entries),
                     schedule=sched, injuries=injuries,
                     sigmas=dict(lineup.DEFAULT_SIGMA),
                     matcher=StubMatcher(pool))
    by_player = {}
    for a in b["alerts"]:
        by_player.setdefault(a["player"], []).append(a)

    qb = by_player.get("Quincy Quarter", [])
    check(any(a["level"] == "red" and "BYE" in a["text"] for a in qb),
          "bye-week starter (team absent from schedule) is a red alert")
    te = by_player.get("Tom Tango", [])
    check(any(a["level"] == "red" and "0.0" in a["text"] for a in te),
          "a filed 0.0 projection is a red alert")
    check(any(a["level"] == "red" and "OUT" in a["text"]
              for a in by_player.get("Walt Whiskey", [])),
          "an Out status is a red alert")
    check(any(a["level"] == "warn" and "Questionable" in a["text"]
              for a in by_player.get("Xavier Xray", [])),
          "Questionable is a warning, not a red alert")
    ghost = by_player.get("Ghost Runner", [])
    check(any(a["level"] == "warn" and "no weekly projection" in a["text"]
              for a in ghost),
          "a starter with no filed projection warns (matcher resolved pos)")
    started = [p.name for _, p in b["rows"] if p is not None]
    check("Ghost Runner" in started,
          "the unprojected RB still fills the open RB slot")

    # Schedule feed down: bye detection must be skipped, not guessed.
    b2 = lineup.build(LEAGUE, [e[0] for e in entries], 3, _proj(entries),
                      schedule=None, sigmas=dict(lineup.DEFAULT_SIGMA),
                      matcher=StubMatcher(pool))
    check(not any("BYE" in a["text"] for a in b2["alerts"]),
          "no schedule feed = no bye claims either way")


# --- 7. DEF resolution ------------------------------------------------------
def test_def_resolution():
    print("\n7. DEF RESOLUTION (city name -> team's D/ST projection)")
    proj = _proj([("Seahawks D/ST", "DEF", "SEA", 7.7)])
    pool = [Player(rank=1, name="Seattle Seahawks", pos="DEF", team="SEA")]
    players, meta, unresolved = lineup.resolve_roster(
        ["Seattle Seahawks"], proj, matcher=StubMatcher(pool))
    check(len(players) == 1 and unresolved == [],
          "city-named defense resolves through the matcher")
    check(players and players[0].proj_points == 7.7,
          "and picks up the ESPN D/ST weekly projection by team")
    _, _, miss = lineup.resolve_roster(["Total Nobody"], proj, matcher=None)
    check(miss == ["Total Nobody"],
          "an unmatchable name lands in unresolved, not silently dropped")


# --- 8. report banners ------------------------------------------------------
def test_banners():
    print("\n8. HONEST BANNERS (partial roster, missing file)")
    roster = {"name": "Fixture Roster", "size": 16,
              "players": [e[0] for e in OBVIOUS][:3], "path": ""}
    entries = OBVIOUS[:3]
    sched = dict((e[2], {"opponent": "OPP", "home": False,
                         "kickoff_iso": "2026-09-13T13:00:00-04:00"})
                 for e in entries)
    text = lineup.lineup_report(LEAGUE, roster, 1, _proj(entries),
                                schedule=sched,
                                sigmas=dict(lineup.DEFAULT_SIGMA),
                                color=False)
    check("PARTIAL ROSTER: 3 of 16" in text,
          "partial roster banner names the exact coverage")
    check("open - no known player fits" in text,
          "open slots say 'no KNOWN player', never 'you have nobody'")
    check("09/13 1:00pm ET" in text,
          "kickoff lock times render from the schedule ISO")
    check("LOCKS:" in text, "earliest-lock line present")

    missing = lineup.lineup_report(LEAGUE, None, 1, {}, color=False)
    check("NO ROSTER FILE" in missing,
          "missing roster file is loud, not an empty lineup")


# --- 9. both coverage states, from fixture roster FILES ---------------------
def test_coverage_states():
    """A partial roster and a complete one, both through load_roster().

    Covers the two states that can regress into each other: a partial
    roster must leave slots honestly OPEN and raise the banner; a complete
    roster must fill every slot and raise NO banner. Projections are
    planted, so the only variable is the roster file.
    """
    print("\n9. ROSTER COVERAGE STATES (fixture roster files on disk)")
    proj = _proj(FULL_ROSTER)
    sigmas = dict(lineup.DEFAULT_SIGMA)
    tmp = tempfile.mkdtemp(prefix="lineup-rosters-")
    try:
        # --- partial: 3 of a declared 16 ---------------------------------
        partial_names = [e[0] for e in FULL_ROSTER[:3]]
        write_roster_file(tmp, "fx-partial", "Partial Fixture", 16,
                          partial_names)
        roster = lineup.load_roster("fx-partial", dirpath=tmp)
        check(roster is not None and roster["size"] == 16
              and len(roster["players"]) == 3,
              "load_roster reads the fixture file: 3 names, declared size 16")

        b = lineup.build(FIXTURE_LEAGUE, roster["players"], 1, proj,
                         sigmas=sigmas)
        check(b["unresolved"] == [],
              "every fixture name resolves (got %s)" % b["unresolved"])
        started = [p.name for _, p in b["rows"] if p is not None]
        check(len(started) == 3,
              "3 known players -> exactly 3 filled slots (got %d)"
              % len(started))
        check(len(b["missing"]) == FIXTURE_STARTING_SLOTS - 3,
              "%d of %d starting slots honestly open (got %d)"
              % (FIXTURE_STARTING_SLOTS - 3, FIXTURE_STARTING_SLOTS,
                 len(b["missing"])))
        check(sum(1 for _, p in b["rows"] if p is None) == len(b["missing"]),
              "every open slot is a None row, not a filled-in guess")

        text = lineup.lineup_report(FIXTURE_LEAGUE, roster, 1, proj,
                                    sigmas=sigmas, color=False)
        check("PARTIAL ROSTER: 3 of 16" in text,
              "partial report carries the coverage banner")
        check("open - no known player fits" in text,
              "open slots say 'no KNOWN player', never 'you have nobody'")
        check("NOT that the slot is truly empty" in text,
              "banner spells out what an open slot does and does not mean")

        # --- complete: 16 of 16 -------------------------------------------
        full_names = [e[0] for e in FULL_ROSTER]
        write_roster_file(tmp, "fx-full", "Full Fixture", 16, full_names)
        roster_f = lineup.load_roster("fx-full", dirpath=tmp)
        check(roster_f is not None and roster_f["size"] == 16
              and len(roster_f["players"]) == 16,
              "load_roster reads the complete fixture: 16 of 16")

        bf = lineup.build(FIXTURE_LEAGUE, roster_f["players"], 1, proj,
                          sigmas=sigmas)
        check(bf["missing"] == [],
              "a complete roster fills every starting slot (open: %s)"
              % (bf["missing"],))
        started_f = [p.name for _, p in bf["rows"] if p is not None]
        check(len(started_f) == FIXTURE_STARTING_SLOTS,
              "all %d starting slots filled (got %d)"
              % (FIXTURE_STARTING_SLOTS, len(started_f)))
        check(len(bf["bench"]) == 16 - FIXTURE_STARTING_SLOTS,
              "the remaining %d players ride the bench (got %d)"
              % (16 - FIXTURE_STARTING_SLOTS, len(bf["bench"])))

        text_f = lineup.lineup_report(FIXTURE_LEAGUE, roster_f, 1, proj,
                                      sigmas=sigmas, color=False)
        check("PARTIAL ROSTER" not in text_f,
              "a complete roster raises NO partial banner")
        check("open - no known player fits" not in text_f,
              "and no slot is reported open")
        check("LINEUP" in text_f and "STARTERS" in text_f,
              "the complete report still renders the lineup itself")

        # --- no file at all -----------------------------------------------
        check(lineup.load_roster("fx-nothing", dirpath=tmp) is None,
              "a league with no roster file loads as None, not an empty one")
        missing = lineup.lineup_report(FIXTURE_LEAGUE, None, 1, proj,
                                       color=False)
        check("NO ROSTER FILE" in missing,
              "missing roster file is loud, not an empty lineup")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 10. live/cached feeds against a fixture league -------------------------
def _fixture_root(roster_names, league_id="fx-lineup"):
    """A throwaway project root: leagues/, data/rankings.csv, data/rosters/.

    Real player names (drawn from the shipped rankings pool by position, so
    the live projection feeds can resolve them) but a roster and a league of
    OUR construction - nothing here reads the user's files.
    """
    import yaml
    root = tempfile.mkdtemp(prefix="lineup-root-")
    os.makedirs(os.path.join(root, "leagues"))
    os.makedirs(os.path.join(root, "data", "rosters"))
    shutil.copy(os.path.join(HERE, "data", "rankings.csv"),
                os.path.join(root, "data", "rankings.csv"))
    with open(os.path.join(root, "leagues", "%s.yaml" % league_id), "w") as fh:
        data = dict(FIXTURE_LEAGUE_DATA)
        data["id"] = league_id
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
    write_roster_file(os.path.join(root, "data", "rosters"), league_id,
                      "Fixture Roster", 16, roster_names)
    return root


def _pool_names_by_pos():
    """{pos: [names]} from the shipped rankings pool - names, never asserted."""
    from engine.models import load_players
    csv_path = os.path.join(HERE, "data", "rankings.csv")
    if not os.path.exists(csv_path):
        return None
    by = {}
    for p in load_players(csv_path):
        by.setdefault(p.pos, []).append(p.name)
    return by


def test_live_fixture():
    print("\n10. LIVE/CACHED FEEDS AGAINST A FIXTURE LEAGUE (week 1)")
    from engine import weekly
    from engine.models import load_players
    from engine.ingest import Matcher

    sigmas = lineup.position_sigma()
    check(all(p in sigmas for p in ("QB", "RB", "WR", "TE", "K", "DEF")),
          "sigma table covers all six positions")
    check(all(2.0 <= sigmas[p] <= 12.0 for p in sigmas),
          "sigmas are in a sane weekly range (got %s)" % sigmas)

    by_pos = _pool_names_by_pos()
    if not by_pos:
        check(False, "data/rankings.csv missing - cannot smoke live feeds")
        return
    # Three real names, one per position: WHICH players is irrelevant and
    # never asserted; only that the pipeline resolves and counts them.
    picks = [by_pos["QB"][0], by_pos["RB"][0], by_pos["WR"][0]]

    root = _fixture_root(picks)
    try:
        league = LeagueConfig.load(os.path.join(root, "leagues",
                                                "fx-lineup.yaml"))
        roster = lineup.load_roster("fx-lineup",
                                    dirpath=os.path.join(root, "data",
                                                         "rosters"))
        check(roster is not None and roster["size"] == 16,
              "fixture roster file loads with its declared size")
        try:
            proj = weekly.fetch_weekly_projections(
                1, scoring=league.scoring_label(), quiet=True)
            sched = weekly.fetch_schedule(1)
        except RuntimeError as exc:
            check(False, "live feeds unavailable: %s" % exc)
            return
        matcher = Matcher(load_players(os.path.join(root,
                                                    league.rankings_csv)))
        b = lineup.build(league, roster["players"], 1, proj, schedule=sched,
                         lines=weekly.fetch_game_lines(1) or None,
                         sigmas=sigmas, matcher=matcher)
        check(b["unresolved"] == [],
              "real pool names resolve against the live feeds (got %s)"
              % b["unresolved"])
        started = [p.name for _, p in b["rows"] if p is not None]
        check(len(started) == 3,
              "3 known players -> exactly 3 filled slots (got %d)"
              % len(started))
        check(len(b["missing"]) == FIXTURE_STARTING_SLOTS - 3,
              "%d starting slots honestly open (got %d)"
              % (FIXTURE_STARTING_SLOTS - 3, len(b["missing"])))

        text = lineup.lineup_report(league, roster, 1, proj, schedule=sched,
                                    sigmas=sigmas, matcher=matcher,
                                    color=False)
        check("PARTIAL ROSTER: 3 of 16" in text,
              "live report carries the partial-coverage banner")

        # CLI smoke run. lineup.main() resolves leagues/ and data/rosters/
        # off its module constants, so they are redirected at the fixture
        # root for the duration (mock_draft's SAVE_DIR discipline).
        real_here, real_dir = lineup.HERE, lineup.ROSTER_DIR
        lineup.HERE = root
        lineup.ROSTER_DIR = os.path.join(root, "data", "rosters")
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = lineup.main(["--league", "fx-lineup", "--week", "1",
                              "--no-color"])
        finally:
            sys.stdout = old
            lineup.HERE, lineup.ROSTER_DIR = real_here, real_dir
        out = buf.getvalue()
        check(rc == 0, "CLI exits 0")
        check("LINEUP" in out and "PARTIAL ROSTER: 3 of 16" in out,
              "CLI renders the report with the honesty banner")
        check("Fixture Lineup League" in out,
              "CLI read the fixture league, not the user's")
        check("UNRESOLVED:" not in out,
              "CLI resolved every fixture roster name")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    print("=" * 74)
    print("LINEUP OPTIMIZER TEST")
    print("=" * 74)

    test_sigma()
    test_probability()
    test_obvious_start()
    test_coin_flip()
    test_flex_contest()
    test_alerts()
    test_def_resolution()
    test_banners()
    test_coverage_states()
    test_live_fixture()

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
