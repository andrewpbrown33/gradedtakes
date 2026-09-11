#!/usr/bin/env python3
"""Acceptance test: waiver engine (engine/waivers.py).

Synthetic fixtures prove the pure pieces - the component math (xFP gap,
trend log-scaling, FAAB bands, scarcity), the scoring core where a planted
high-xFP/low-actual trending player MUST outrank a name-brand faller, the
starter-baseline logic (displacement bar vs replacement fallback), roster
loading with honest partial/missing banners, the starter-protected drop
pick, the no-cookies guard paths, and the %owned baseline's read/advance
split (a read must leave data/cache/espn-owned-snapshot.json byte- and
mtime-identical; only an explicit advance rolls it forward) - then the
real report is built for yahoo-main week 1 against the live/cached feeds.

No test here saves state, so no SAVE_DIR redirect is needed (same as
weekly_test); live fetches land in data/cache like every other fetcher.
Roster fixtures go to a mkdtemp dir removed in a finally block - never
into data/rosters/.

FIXTURE RULE - read before editing the live report check:

    The xFP signal is a FUNCTION OF THE CALENDAR: until the current season
    files a week, fetch_xfp_signal() falls back to last season and every
    line carries the '2025 signal' label plus a header saying so; from the
    first filed week on it uses the current season and the label is gone.
    A check that pins the live report to one of those states is true on
    Sunday and false on Thursday - an expiry date, not a contract. So
    section 7b stands fetch_xfp_signal() AND build_report() on both sides
    of week 1 through the xfp_by_season seam (fixture maps, no network)
    and pins the label, the header line and WHICH season's numbers reach
    the shortlist; the live report then asserts only the rule - its label
    matches what the current-season file actually holds today.

    .venv/bin/python tests/waivers_test.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import waivers                                   # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.models import LeagueConfig, Player, load_players  # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _p(rank, name, pos, team="", proj=None):
    return Player(rank=rank, name=name, pos=pos, team=team, proj_points=proj)


def _weeks(pairs):
    return [{"week": i + 1, "xfp": x, "actual": a}
            for i, (x, a) in enumerate(pairs)]


def _roster_coverage(league_id):
    """(known, expected) for a real roster file - read, never hardcoded."""
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "%s.yaml" % league_id))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    roster, _ = waivers.load_my_roster(league_id, Matcher(players))
    return (len(roster.keys), roster.size) if roster else (0, 0)


# --- 1. component math ------------------------------------------------------
def test_component_math():
    print("\n1. COMPONENT MATH (xFP gap, trend scaling, FAAB bands)")
    check(waivers.xfp_gap([]) is None, "no filed weeks -> gap is None, not 0")
    gap = waivers.xfp_gap(_weeks([(10, 14), (10, 14), (10, 14), (10, 14)]))
    check(abs(gap - (-4.0)) < 1e-9, "gap averages xfp-actual (-4.0/wk)")
    six = _weeks([(0, 50), (0, 50), (12, 9), (12, 9), (12, 9), (12, 9)])
    check(abs(waivers.xfp_gap(six) - 3.0) < 1e-9,
          "gap uses only the latest %d weeks" % waivers.XFP_WEEKS)
    check(waivers.xfp_points(None) == 0.0, "None gap contributes 0 points")
    check(abs(waivers.xfp_points(2.0) - 8.0) < 1e-9,
          "gap +2.0/wk -> +8.0 pts (4x weight)")
    check(waivers.xfp_points(50.0) == waivers.XFP_CAP
          and waivers.xfp_points(-50.0) == -waivers.XFP_CAP,
          "xFP points cap at +/-%.0f" % waivers.XFP_CAP)

    check(waivers.trend_points(0) == 0.0, "no adds -> 0 trend points")
    check(0 < waivers.trend_points(1000) < waivers.trend_points(50000),
          "trend points grow with adds (log scale)")
    check(waivers.trend_points(10 ** 9) == waivers.TREND_CAP,
          "trend points cap at %.0f - hype cannot outvote real points"
          % waivers.TREND_CAP)

    check(waivers.faab_band(-5.0) == "pass" and waivers.faab_band(0.0) == "pass",
          "non-positive scaled score -> pass")
    bands = [waivers.faab_band(s) for s in (1, 5, 10, 20, 30, 100)]
    check(bands == ["1-3%", "4-8%", "9-15%", "16-25%", "26-40%", "41-60%"],
          "FAAB bands step monotonically: %s" % ", ".join(bands))
    check(waivers.scarcity_factor(2) == 1.5
          and waivers.scarcity_factor(5) == 1.25
          and waivers.scarcity_factor(9) == 1.0,
          "scarcity factor: 1.5x thin, 1.25x mid, 1.0x deep")


# --- 2. scoring core: planted riser vs name-brand faller --------------------
def test_riser_beats_faller():
    print("\n2. SCORING CORE (planted high-xFP trending riser vs name-brand "
          "faller)")
    faller = _p(1, "Name Brand", "WR", "DAL")
    riser = _p(50, "Planted Riser", "WR", "SEA")
    baselines = {"WR": {"value": 100.0,
                        "basis": "my worst WR-eligible starter: X (ROS 100)"}}
    ros = {faller.key: 115.0, riser.key: 108.0}   # brand has MORE raw ROS
    xfp = {faller.nkey: _weeks([(10, 14)] * 4),   # -4/wk: outscored his usage
           riser.nkey: _weeks([(15, 9.5)] * 4)}   # +5.5/wk: usage says buy
    trending = {riser.nkey: 40000}

    ranked = waivers.score_pool([faller, riser], ros, baselines, xfp,
                                trending, xfp_label="2025 signal")
    names = [c.player.name for c in ranked]
    check(names[0] == "Planted Riser",
          "riser outranks the name-brand faller despite less raw ROS")
    r = ranked[0]
    f = ranked[1]
    check(abs(r.ros_gain - 8.0) < 1e-9 and abs(f.ros_gain - 15.0) < 1e-9,
          "ROS component: riser +8.0, faller +15.0 over the same bar")
    check(r.xfp_pts == waivers.XFP_CAP,
          "riser's +5.5/wk gap hits the xFP cap (+%.0f)" % waivers.XFP_CAP)
    check(abs(f.xfp_pts - (-16.0)) < 1e-9,
          "faller's -4.0/wk gap costs -16.0 points")
    check(r.trend_pts > 13.0 and f.trend_pts == 0.0,
          "40k Sleeper adds worth %.1f pts; faller not trending" % r.trend_pts)
    check("2025 signal" in r.xfp_detail,
          "xFP detail carries the '2025 signal' label")
    check(r.score > f.score and abs(r.score - (8.0 + 20.0 + r.trend_pts)) < 0.1,
          "score is the plain sum of its printed components")
    check(r.faab != "pass" and f.faab == "pass",
          "riser gets a FAAB band; the faller's negative score is a pass")
    check(r.scarcity == 1.5,
          "2 WRs clear the bar -> 1.5x scarcity on the band")


# --- 3. starter baselines ---------------------------------------------------
def _league():
    return LeagueConfig({"id": "test", "name": "Test", "teams": 2,
                         "roster_spots": ["QB", "RB", "RB", "W/R/T", "BN"],
                         "rounds": 5})


def test_baselines():
    print("\n3. STARTER BASELINES (displacement bar vs replacement fallback)")
    league = _league()
    rb1 = _p(1, "Aaron Alpha", "RB", "DET", proj=200)
    rb2 = _p(2, "Bob Beta", "RB", "ATL", proj=150)
    wr1 = _p(3, "Carl Gamma", "WR", "SEA", proj=170)
    qb1 = _p(4, "Dan Delta", "QB", "BUF", proj=320)
    qb2 = _p(5, "Ed Epsilon", "QB", "KC", proj=300)
    qb3 = _p(6, "Frank Zeta", "QB", "NYJ", proj=250)
    roster = [rb1, rb2, wr1]                       # no QB captured
    pool = roster + [qb1, qb2, qb3]
    ros = {rb1.key: 180.0, rb2.key: 140.0, wr1.key: 160.0,
           qb1.key: 300.0, qb2.key: 280.0, qb3.key: 250.0}

    bl = waivers.starter_baselines(league, roster, ros, pool)
    check(bl["RB"]["value"] == 140.0 and "Bob Beta" in bl["RB"]["basis"],
          "all RB-eligible slots known-filled -> bar = worst such starter")
    check(bl["WR"]["value"] == 160.0 and "Carl Gamma" in bl["WR"]["basis"],
          "WR bar = the flex starter a pickup would displace")
    check(bl["TE"]["value"] == 160.0,
          "TE (flex-only here) shares the displacement bar")
    check(bl["QB"]["value"] == 280.0
          and "replacement" in bl["QB"]["basis"].lower(),
          "open QB slot -> replacement bar (2nd-best QB ROS, 2 teams), "
          "labeled honestly")
    check(bl["K"]["value"] == 0.0 and "no K slot" in bl["K"]["basis"],
          "position with no slot in this lineup says so")


# --- 4. roster loading (honest banners) -------------------------------------
def test_roster_loading():
    print("\n4. ROSTER LOADING (missing / partial / invalid files)")
    pool = [_p(1, "Aaron Alpha", "RB", "DET"), _p(2, "Bob Beta", "WR", "ATL")]
    matcher = Matcher(pool)
    tmp = tempfile.mkdtemp(prefix="waivers-rosters-")
    try:
        roster, banner = waivers.load_my_roster("nope", matcher, dirpath=tmp)
        check(roster is None and "grading the full pool" in banner,
              "missing roster file -> None + grade-anyway banner")
        check("NO roster file" in banner,
              "missing-file banner names the gap loudly")

        with open(os.path.join(tmp, "part.yaml"), "w") as fh:
            fh.write("league: part\nname: Part League\nsize: 16\n"
                     "players:\n  - Aaron Alpha\n  - Zzz Unknown Guy\n")
        roster, banner = waivers.load_my_roster("part", matcher, dirpath=tmp)
        check(roster is not None and len(roster.keys) == 1,
              "partial file: 1 of 2 names resolved against the pool")
        check("1/16" in banner and "positive-only" in banner,
              "partial banner carries known/expected count and semantics")
        check(roster.unresolved == ["Zzz Unknown Guy"],
              "unmatched name lands in unresolved, not silently dropped")

        with open(os.path.join(tmp, "bad.yaml"), "w") as fh:
            fh.write("- just\n- a\n- list\n")
        roster, banner = waivers.load_my_roster("bad", matcher, dirpath=tmp)
        check(roster is None and "grading the full pool" in banner,
              "invalid roster yaml -> None + grade-anyway banner")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 5. drop candidate ------------------------------------------------------
def test_drop_candidate():
    print("\n5. DROP CANDIDATE (starters protected, bench first)")
    league = _league()
    rb1 = _p(1, "Aaron Alpha", "RB", "DET", proj=200)
    rb2 = _p(2, "Bob Beta", "RB", "ATL", proj=150)
    wr1 = _p(3, "Carl Gamma", "WR", "SEA", proj=170)
    wr2 = _p(4, "Gil Eta", "WR", "MIA", proj=90)
    ros = {rb1.key: 180.0, rb2.key: 100.0, wr1.key: 160.0, wr2.key: 120.0}

    victim, note = waivers.drop_candidate(league, [rb1, rb2, wr1, wr2], ros)
    check(victim is wr2 and note == "bench",
          "bench player dropped even though a starter has lower ROS")
    victim, note = waivers.drop_candidate(league, [rb1, rb2, wr1], ros)
    check(victim is rb2 and "starter" in note,
          "all known players start -> worst starter, note says so")
    victim, note = waivers.drop_candidate(league, [], ros)
    check(victim is None and "cannot suggest" in note,
          "empty known roster -> honest refusal, not a crash")


# --- 6. no-cookies guard paths ----------------------------------------------
def test_no_cookies():
    print("\n6. NO-COOKIES PATHS (guarded, clean, RUNBOOK A3 pointer)")
    matcher = Matcher([_p(1, "Aaron Alpha", "RB", "DET")])
    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")
    taken, note = waivers.espn_taken_keys(matcher, secrets_path=bogus)
    check(taken == set() and "RUNBOOK A3" in note,
          "taken-players filter: empty set + RUNBOOK A3 note, no exception")
    owned, note = waivers.owned_momentum(secrets_path=bogus)
    check(owned is None and "RUNBOOK A3" in note,
          "%owned momentum: None (component absent) + RUNBOOK A3 note")

    # PLATFORM GUARD: ESPN facts never touch a Yahoo pool - and a Yahoo run
    # never WRITES the ESPN baseline, even when asked to advance.
    class _Yahoo(object):
        platform = "yahoo"
    snap = os.path.join(tempfile.gettempdir(), "guard-owned-snap-%d.json"
                        % os.getpid())
    if os.path.exists(snap):
        os.remove(snap)
    taken, note = waivers.espn_taken_keys(matcher, secrets_path=bogus,
                                          league=_Yahoo())
    check(taken == set() and "not applied" in note and "yahoo" in note,
          "taken-players filter is NOT applied to a Yahoo league, and says so")
    owned, note = waivers.owned_momentum(secrets_path=bogus, advance=True,
                                         snapshot_path=snap, league=_Yahoo())
    check(owned is None and "not applied" in note,
          "%owned momentum is NOT applied to a Yahoo league")
    check(not os.path.exists(snap),
          "...and a Yahoo run never writes the ESPN baseline, even with "
          "advance=True")

    class _Espn(object):
        platform = "espn"
    taken, note = waivers.espn_taken_keys(matcher, secrets_path=bogus,
                                          league=_Espn())
    check(taken == set() and "RUNBOOK A3" in note,
          "an ESPN league without cookies still points at RUNBOOK A3")

    class _Unset(object):
        platform = ""
    taken, note = waivers.espn_taken_keys(matcher, secrets_path=bogus,
                                          league=_Unset())
    check("RUNBOOK A3" in note,
          "an unset platform keeps the legacy path (synthetic leagues)")

    ok, why = waivers.claim_gate(None)
    check(ok is False and "No claim is surfaced" in why,
          "claim_gate refuses without rival rosters, with the reason")

    class _View(object):
        available = True
    ok, why = waivers.claim_gate(_View())
    check(ok is True and why == "",
          "claim_gate allows claims once rival rosters are known")


# --- 6b. the %owned baseline is a WRITE, and a write must be asked for -------

class _FakeFA(object):
    """The two attributes owned_momentum reads off an espn free agent."""

    def __init__(self, name, pct):
        self.name = name
        self.percent_owned = pct


class _FakeLeague(object):
    def __init__(self, agents):
        self._agents = agents

    def free_agents(self, size=60, position=None):
        return self._agents[:size]


class _FakeEspn(object):
    """Stand-in for engine.espn: authenticated, deterministic, offline."""

    EspnError = RuntimeError

    def __init__(self, secrets, agents):
        self.SECRETS = secrets
        self._agents = agents
        self.connects = 0

    def connect(self, season=None):
        self.connects += 1
        return _FakeLeague(self._agents)

    def free_agents(self, lg, size=60, position=None):
        return lg.free_agents(size=size, position=position)


def _fake_espn(tmp, pcts):
    """Install a fake engine.espn; returns (fake, restore)."""
    import engine.espn as real
    secrets = os.path.join(tmp, "espn_secrets.json")
    with open(secrets, "w") as fh:
        fh.write("{}")
    fake = _FakeEspn(secrets, [_FakeFA(n, p) for n, p in pcts])
    saved = {}
    for attr in ("SECRETS", "connect", "free_agents"):
        saved[attr] = getattr(real, attr)
        setattr(real, attr, getattr(fake, attr))

    def restore():
        for k, v in saved.items():
            setattr(real, k, v)
    return fake, restore


def _snapshot(path):
    """(bytes, mtime_ns) - the two ways a file can be said to have moved."""
    with open(path, "rb") as fh:
        return fh.read(), os.stat(path).st_mtime_ns


def test_momentum_baseline():
    print("\n6b. %owned BASELINE (a read must not move it - A2)")
    import json
    import time
    tmp = tempfile.mkdtemp(prefix="waivers-owned-")
    fake, restore = _fake_espn(tmp, [("Aaron Alpha", 42.0),
                                     ("Bob Beta", 11.0)])
    snap = os.path.join(tmp, "espn-owned-snapshot.json")
    try:
        # (a) no baseline yet. A READ stores nothing and says so; only the
        #     refresh gesture creates one.
        owned, note = waivers.owned_momentum(snapshot_path=snap)
        check(owned is None and not os.path.exists(snap),
              "no baseline + read-only -> nothing written, component absent")
        check("read-only" in note and "engine.waivers" in note,
              "...and the note names the run that WOULD store one (got %r)"
              % note)

        owned, note = waivers.owned_momentum(snapshot_path=snap, advance=True)
        check(owned is None and os.path.exists(snap),
              "advance=True on a cold start stores the baseline")
        check("baseline snapshot stored" in note,
              "...and says the baseline was stored, not that momentum is on")

        # (b) age the baseline and move the wire under it.
        with open(snap, "w") as fh:
            json.dump({"ts": time.time() - 7200,
                       "owned": {waivers.name_key("Aaron Alpha"): 30.0,
                                 waivers.name_key("Bob Beta"): 20.0}}, fh)
        before = _snapshot(snap)

        first, note1 = waivers.owned_momentum(snapshot_path=snap)
        check(first is not None
              and round(first[waivers.name_key("Aaron Alpha")], 3) == 12.0
              and round(first[waivers.name_key("Bob Beta")], 3) == -9.0,
              "a read measures the real delta against the stored baseline")
        check(_snapshot(snap) == before,
              "READ IS READ-ONLY: the snapshot's bytes AND mtime are "
              "unchanged")

        # (c) the defect: a second read used to compare against a snapshot
        #     the first read had just written, so every delta collapsed.
        second, note2 = waivers.owned_momentum(snapshot_path=snap)
        check(second == first,
              "reading twice reports the SAME deltas - no collapse to ~0")
        check(max(abs(v) for v in second.values()) > 0,
              "...and those deltas are still non-zero (got %r)" % second)
        check(_snapshot(snap) == before,
              "two reads later the baseline file is still byte-identical")
        check("momentum active" in note1 and note1 == note2,
              "the note is stable across reads too (got %r / %r)"
              % (note1, note2))

        # (d) the refresh DOES move it, on purpose.
        third, _ = waivers.owned_momentum(snapshot_path=snap, advance=True,
                                          min_age_h=0)
        check(third == first,
              "the refresh reports against the OLD baseline it just read, "
              "never against the one it is writing")
        after = _snapshot(snap)
        check(after != before,
              "advance=True rolls the baseline forward (that is its job)")
        rolled, _ = waivers.owned_momentum(snapshot_path=snap)
        check(rolled == dict((k, 0.0) for k in rolled),
              "and the next read measures against the NEW baseline (all "
              "zero until the wire moves again) - which is exactly what "
              "every render used to report")

        # (e) the module default is the user's real cache path, untouched.
        check(waivers.OWNED_SNAP.endswith("espn-owned-snapshot.json")
              and "data/cache" in waivers.OWNED_SNAP.replace(os.sep, "/"),
              "the default snapshot still lives in data/cache/")
    finally:
        restore()
        shutil.rmtree(tmp, ignore_errors=True)


# --- 7. live report ---------------------------------------------------------
def test_live_report():
    print("\n7. LIVE REPORT (yahoo-main week 1, real feeds/cache)")
    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")
    report = waivers.build_report("yahoo-main", 1, top_n=8, color=False,
                                  secrets_path=bogus)
    check("WAIVER WIRE" in report and "week 1" in report,
          "report renders for yahoo-main week 1")
    # The capture file grows as names are added, so assert the RULE rather
    # than today's count: partial coverage must banner, full must not.
    known, size = _roster_coverage("yahoo-main")
    if known < size:
        check("roster known %d/%d" % (known, size) in report,
              "honest partial banner names the exact coverage (%d/%d)"
              % (known, size))
    else:
        check("roster known" not in report,
              "roster fully captured (%d/%d) - no partial banner to print"
              % (known, size))
    check(waivers.NO_COMPETITION in report,
          "no rival rosters for Kid's Table: the competition read says so "
          "instead of showing a zero")
    check("not applied - this is a yahoo league" in report,
          "ESPN taken-players / %owned reads are NOT applied to a Yahoo "
          "league, and the report says so (platform guard)")
    check(report.count("\n       ros ") >= 8,
          "every shortlist row shows its ROS component")
    check(report.count("\n       xfp ") >= 8
          and report.count("\n       trend ") >= 8,
          "every shortlist row shows xFP and trend components")
    check("FAAB" in report and "judgment calls" in report,
          "FAAB bands present and labeled as judgment calls")
    check("bid history calibration needs cookies" in report,
          "bid-history calibration gap stays on screen")
    check("DROP CANDIDATE" in report,
          "a drop candidate is named")
    # THE LABEL IS A FUNCTION OF THE CALENDAR (FIXTURE RULE, module
    # docstring): assert the rule against the file the report read, not a
    # date. Section 7b pins both sides exactly.
    from engine import nflverse
    try:
        cur_on_file = nflverse.fetch_xfp(waivers.SEASON)
    except RuntimeError:
        cur_on_file = {}
    cur_weeks = sorted(set(w["week"] for ws in cur_on_file.values()
                           for w in ws))
    expect_label = not cur_on_file
    print("      today: %d %d xFP week(s) on file (%s) -> %s"
          % (len(cur_weeks), waivers.SEASON,
             ", ".join(str(w) for w in cur_weeks) or "none",
             "prior-season label" if expect_label else "no label"))
    check(("2025 signal" in report) == expect_label
          and ("2026 weeks not yet filed" in report) == expect_label,
          "the xFP label and its header line appear exactly when the %d "
          "file has no weeks (%s today)"
          % (waivers.SEASON, "labelled" if expect_label else "unlabelled"))


# --- 7b. the calendar boundary: which season feeds xFP, and how it is labelled
def _xfp_fixture(nkeys, gap):
    """A fetch_xfp-shaped map giving every name the same 4-week gap."""
    return dict((k, _weeks([(10.0 + gap, 10.0)] * 4)) for k in nkeys)


def test_xfp_calendar_boundary():
    print("\n7b. XFP CALENDAR BOUNDARY (prior-season fallback vs current "
          "season, pure + report)")
    cur, prior = waivers.SEASON, waivers.SEASON - 1
    P = {"prior guy": _weeks([(12, 10)] * 4)}
    C = {"current guy": _weeks([(12, 10)])}

    # (a) the pure rule, through fetch_xfp_signal's own seam.
    for shape, rbs in (("no %d file" % cur, {prior: P}),
                       ("an empty %d file" % cur, {prior: P, cur: {}})):
        got, label = waivers.fetch_xfp_signal(xfp_by_season=rbs)
        check(got is P and label == "2025 signal",
              "[%s] falls back to the %d map, labelled '2025 signal'"
              % (shape, prior))
    got, label = waivers.fetch_xfp_signal(xfp_by_season={prior: P, cur: C})
    check(got is C and label == "",
          "one %d week filed: the %d map is used and the label is gone"
          % (cur, cur))
    got, label = waivers.fetch_xfp_signal(xfp_by_season={cur: C})
    check(got is C and label == "",
          "...and it does not need the prior file to be there")
    try:
        waivers.fetch_xfp_signal(xfp_by_season={})
        raised = False
    except RuntimeError:
        raised = True
    check(raised, "neither season on file raises - a failure, never an "
                  "empty signal dressed as 'no xFP data'")

    # (b) the report, on both sides. The fixture covers every ranked name
    #     so the shortlist ALWAYS has xFP lines, whoever is on it today;
    #     the two seasons carry different gaps so the numbers say which
    #     one reached the page.
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "yahoo-main.yaml"))
    nkeys = [p.nkey for p in load_players(os.path.join(HERE,
                                                       league.rankings_csv))]
    prior_map = _xfp_fixture(nkeys, +2.0)     # 2025: +2.0/wk everywhere
    cur_map = _xfp_fixture(nkeys, -1.0)       # 2026: -1.0/wk everywhere
    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")

    def _report(rbs):
        return waivers.build_report("yahoo-main", 1, top_n=8, color=False,
                                    secrets_path=bogus, xfp_by_season=rbs)

    def _xfp_lines(report):
        return [ln for ln in report.split("\n") if ln.startswith("       xfp ")]

    pre = _report({prior: prior_map, cur: {}})
    lines = _xfp_lines(pre)
    check(len(lines) >= 8 and all("(2025 signal)" in ln for ln in lines),
          "pre-season report: every shortlist xfp line carries the "
          "'(2025 signal)' label (%d lines)" % len(lines))
    check(all("avg +2.0 xfp-actual/wk over last 4 wks" in ln for ln in lines),
          "pre-season report: the numbers are the PRIOR season's (+2.0/wk)")
    check(" xFP regression uses 2025 signal data - %d weeks not yet filed"
          % cur in pre,
          "pre-season report: the header says which season and why")

    mid = _report({prior: prior_map, cur: cur_map})
    lines = _xfp_lines(mid)
    check(len(lines) >= 8 and not any("2025 signal" in ln for ln in lines),
          "in-season report: the label is gone from every xfp line "
          "(%d lines)" % len(lines))
    check(all("avg -1.0 xfp-actual/wk over last 4 wks" in ln for ln in lines),
          "in-season report: the numbers are the CURRENT season's (-1.0/wk)")
    check("2025 signal" not in mid and "not yet filed" not in mid,
          "in-season report: no prior-season label or header anywhere")
    check(pre.count("\n       xfp ") == mid.count("\n       xfp ")
          and "WAIVER WIRE" in pre and "WAIVER WIRE" in mid,
          "both sides render the same shortlist shape - only the season "
          "behind the xFP column moved")


# --- 8. priority-mode guidance (pure) ---------------------------------------
def test_priority_guidance():
    print("\n8. PRIORITY MODE (burn-priority opportunity cost, pure)")

    def _cand(rank, name, pos, score):
        c = waivers.Candidate(_p(rank, name, pos))
        c.score = score
        return c

    top = _cand(1, "Top Dog", "WR", 30.0)          # gap 3.0 to Close Second
    close = _cand(2, "Close Second", "WR", 27.0)   # gap 12.0 to Distant Third
    lone = _cand(3, "Lone Back", "RB", 12.0)       # no RB fallback at all
    third = _cand(4, "Distant Third", "WR", 15.0)
    neg = _cand(5, "Negative Ned", "TE", -3.0)
    ranked = [top, close, third, lone, neg]
    ranked.sort(key=lambda c: -c.score)
    waivers.priority_guidance(ranked)

    check(top.burn == "NO" and "Close Second" in top.burn_detail,
          "gap +3.0 under the %.0f-pt bar -> NO, fallback named as evidence"
          % waivers.PRIORITY_GAP)
    check(close.burn == "YES" and "Distant Third" in close.burn_detail
          and "+12.0" in close.burn_detail,
          "gap +12.0 over the next-best WR who'd survive to FA -> YES")
    check(lone.burn == "YES" and "no other RB" in lone.burn_detail,
          "no same-position fallback -> whole score is the gap, says so")
    check(neg.burn == "NO" and "score <= 0" in neg.burn_detail,
          "non-positive score -> NO at any queue cost")

    league = LeagueConfig({"id": "p", "name": "P", "teams": 8, "my_slot": 1,
                           "roster_spots": ["QB", "BN"], "rounds": 2,
                           "waiver_mode": "priority"})
    note = waivers.priority_position_note(league)
    check("8th of 8" in note and "inverse standings" in note,
          "structural note: slot 1 of 8 starts the season 8th of 8")
    check(LeagueConfig({"id": "x", "name": "X"}).waiver_mode == "faab",
          "LeagueConfig without waiver_mode tolerantly defaults to 'faab'")


# --- 9. priority-mode live report (espn-1) ----------------------------------
def test_priority_live_report():
    print("\n9. PRIORITY-MODE LIVE REPORT (espn-1 week 1, real feeds/cache)")
    import re
    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")
    report = waivers.build_report("espn-1", 1, top_n=8, color=False,
                                  secrets_path=bogus)
    check("WAIVER WIRE" in report and "The Original 8" in report,
          "report renders for espn-1 week 1")
    check(report.count("worth burning priority?") >= 8,
          "every shortlist row carries a burn-priority verdict")
    check(report.count("\n       prio  ") >= 8,
          "every row shows the opportunity-cost evidence line")
    check("FAAB" not in report,
          "priority league: the word FAAB never appears")
    check(re.search(r"\b\d+-\d+%", report) is None,
          "priority league: no FAAB percentage bands anywhere")
    check("8th of 8" in report and "inverse standings" in report,
          "structural reminder: starts the season 8th of 8, weekly "
          "inverse-standings reset")
    check("survive" in report or "no other" in report,
          "verdicts cite the free-agency fallback comparison")


# --- 10. waiver competition (synthetic rivals, pure) ------------------------
COMP_REPL = {"QB": 100.0, "RB": 100.0, "WR": 100.0, "TE": 100.0}


def _comp_league():
    return LeagueConfig({"id": "comp", "name": "Comp League", "teams": 4,
                         "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE",
                                          "W/R/T", "BN"], "rounds": 8})


def _comp_world():
    """4 teams: mine, one WR-starved, one WR-deep, one with a weak flex."""
    mine = [_p(1, "My Quarter", "QB", "AAA", 200), _p(2, "My Rush", "RB", "AAA", 300),
            _p(3, "My Rush Two", "RB", "AAA", 290), _p(4, "My Wide", "WR", "AAA", 250),
            _p(5, "My Wide Two", "WR", "AAA", 240), _p(6, "My Tight", "TE", "AAA", 150),
            _p(7, "My Flex", "RB", "AAA", 285)]
    waste = [_p(11, "Waste Quarter", "QB", "BBB", 200),
             _p(12, "Waste Rush", "RB", "BBB", 300),
             _p(13, "Waste Rush Two", "RB", "BBB", 290),
             _p(14, "Waste Rush Three", "RB", "BBB", 285),
             _p(15, "Waste Wide", "WR", "BBB", 195),
             _p(16, "Waste Scrub", "WR", "BBB", 40),
             _p(17, "Waste Tight", "TE", "BBB", 150)]
    deep = [_p(21, "Deep Quarter", "QB", "CCC", 200),
            _p(22, "Deep Rush", "RB", "CCC", 300),
            _p(23, "Deep Rush Two", "RB", "CCC", 290),
            _p(24, "Deep Rush Three", "RB", "CCC", 285),
            _p(25, "Deep Wide", "WR", "CCC", 250),
            _p(26, "Deep Wide Two", "WR", "CCC", 240),
            _p(27, "Deep Tight", "TE", "CCC", 150)]
    thin = [_p(31, "Thin Quarter", "QB", "DDD", 200),
            _p(32, "Thin Rush", "RB", "DDD", 300),
            _p(33, "Thin Rush Two", "RB", "DDD", 290),
            _p(34, "Thin Flexer", "RB", "DDD", 120),
            _p(35, "Thin Wide", "WR", "DDD", 250),
            _p(36, "Thin Wide Two", "WR", "DDD", 240),
            _p(37, "Thin Tight", "TE", "DDD", 150)]
    free = _p(41, "Free Willy", "WR", "EEE", 200)
    players = mine + waste + deep + thin + [free]
    teams = {"1": {"name": "Us", "players": [p.name for p in mine]},
             "2": {"name": "WR Wasteland", "players": [p.name for p in waste]},
             "3": {"name": "Deep Everywhere", "players": [p.name for p in deep]},
             "4": {"name": "Thin Flex", "players": [p.name for p in thin]}}
    ros = dict((p.key, float(p.proj_points)) for p in players)
    return _comp_league(), players, mine, teams, free, ros


def test_competition():
    print("\n10. WAIVER COMPETITION (which rivals would actually bid)")
    from engine import trades
    league, players, mine, teams, free, ros = _comp_world()
    view = trades.load_rival_view(league, Matcher(players), players,
                                  my_keys=set(p.key for p in mine),
                                  loader=lambda _id: teams)
    check(view.available and len(view.teams) == 3,
          "3 rivals load; my own team is excluded from the competition set")

    comp = waivers.waiver_competition(league, view, [free], ros, players,
                                      repl=COMP_REPL)
    read = comp[free.key]
    check(read.count == 2,
          "2 of 3 rivals would actually use a WR like this (got %d)"
          % read.count)
    check(read.teams == ["WR Wasteland", "Thin Flex"],
          "the two are named, in board order (got %s)" % read.teams)
    check("Deep Everywhere" not in read.teams,
          "the WR-deep rival is NOT counted - his worst WR starter is better")
    check(read.structural == ["WR Wasteland"],
          "the structurally short roster is flagged as such")
    check(read.upgrade == ["WR Wasteland", "Thin Flex"],
          "both would start him over their worst WR-eligible starter")
    check("2 rivals need WR" in read.detail("WR")
          and "WR Wasteland" in read.detail("WR"),
          "the printed line counts AND names: %s" % read.detail("WR"))

    check(waivers.competition_factor(0) == 1.0,
          "no competition -> no bid pressure (1.00x)")
    check(abs(waivers.competition_factor(2) - 1.24) < 1e-9,
          "2 rivals -> 1.24x bid pressure")
    check(waivers.competition_factor(50) == waivers.COMP_CAP,
          "bid pressure caps at %.2fx - a scramble is not a blank cheque"
          % waivers.COMP_CAP)

    cand = waivers.Candidate(free)
    cand.score, cand.scarcity = 7.0, 1.0
    cand.faab = waivers.faab_band(7.0)
    before = cand.faab
    waivers.apply_competition([cand], comp)
    check(before == "4-8%" and cand.faab == "9-15%",
          "the FAAB band moves up a step for a contested pickup (%s -> %s)"
          % (before, cand.faab))
    check(cand.rivals == 2 and cand.rival_names == ["WR Wasteland",
                                                    "Thin Flex"],
          "the candidate carries the count AND the names into the report")
    check(abs(cand.score - 7.0) < 1e-9,
          "competition changes the PRICE, never the score - the player is "
          "no better for being wanted")

    note = waivers.drop_rival_note(free, comp)
    check("2 rivals need WR" in note and "hands them the upgrade" in note,
          "a droppable player wanted by rivals gets a warning: %s" % note)


# --- 11. competition degrades honestly with no rival data -------------------
def test_competition_unknown():
    print("\n11. NO RIVAL DATA (competition read absent, never a fake zero)")
    from engine import trades
    league, players, mine, teams, free, ros = _comp_world()

    def boom(_id):
        raise ImportError("engine/leagueview.py not present")

    dead = trades.load_rival_view(league, Matcher(players), players,
                                  loader=boom)
    check(waivers.waiver_competition(league, dead, [free], ros, players,
                                     repl=COMP_REPL) == {},
          "unavailable rival view -> empty competition map")
    check(waivers.waiver_competition(league, None, [free], ros, players,
                                     repl=COMP_REPL) == {},
          "no view at all -> empty competition map, not a crash")

    cand = waivers.Candidate(free)
    cand.score, cand.scarcity, cand.faab = 7.0, 1.0, "4-8%"
    waivers.apply_competition([cand], {})
    check(cand.faab == "4-8%" and cand.rivals == 0 and cand.comp_detail == "",
          "with no data the band is untouched and comp_detail stays EMPTY - "
          "the report prints the unknown line instead of '0 rivals'")
    check(waivers.drop_rival_note(free, {}) == "",
          "no rival data -> no drop warning invented")
    check(waivers.NO_COMPETITION.startswith("rival rosters unknown"),
          "the degradation line is the honest one: %s"
          % waivers.NO_COMPETITION)

    ranked = [waivers.Candidate(free)]
    ranked[0].score = 9.0
    waivers.priority_guidance(ranked)
    before = ranked[0].burn
    waivers.priority_competition(ranked, {})
    check(ranked[0].burn == before,
          "priority verdicts are unchanged when nothing is known about "
          "rivals")


# --- 12. priority mode: a contested fallback changes the verdict ------------
def test_priority_competition():
    print("\n12. PRIORITY MODE + COMPETITION (a claimed fallback is no "
          "fallback)")

    def _cand(rank, name, pos, score):
        c = waivers.Candidate(_p(rank, name, pos))
        c.score = score
        return c

    top = _cand(1, "Top Dog", "WR", 9.0)         # gap 3.0 - under the bar
    fall = _cand(2, "Fall Back", "WR", 6.0)
    ranked = [top, fall]
    waivers.priority_guidance(ranked)
    check(top.burn == "NO", "gap +3.0 alone does not justify burning priority")

    quiet = waivers.Competition()
    waivers.priority_competition(ranked, {fall.player.key: quiet})
    check(top.burn == "NO",
          "an UNCONTESTED fallback leaves the verdict alone")

    hot = waivers.Competition()
    hot.teams = ["Team Three", "Team Seven"]
    hot.count = 2
    waivers.priority_competition(ranked, {fall.player.key: hot})
    check(top.burn == "YES",
          "%d rivals needing the fallback flips the verdict - passing no "
          "longer leaves a similar player behind"
          % waivers.FALLBACK_CONTESTED)
    check("Fall Back" in top.burn_detail and "Team Three" in top.burn_detail
          and "full 9.0" in top.burn_detail,
          "the flip is argued, not asserted: %s" % top.burn_detail)

    thin = _cand(3, "Small Fry", "TE", 2.0)
    thin_fb = _cand(4, "Smaller Fry", "TE", 1.0)
    thin_ranked = [thin, thin_fb]
    waivers.priority_guidance(thin_ranked)
    waivers.priority_competition(thin_ranked, {thin_fb.player.key: hot})
    check(thin.burn == "NO" and "still under" in thin.burn_detail,
          "a contested fallback cannot promote a claim that is too small "
          "to matter at all")


# --- 13. live report with rival rosters (integration) -----------------------
def test_live_report_with_rivals():
    print("\n13. LIVE REPORT WITH RIVAL ROSTERS (espn-1, injected loader in "
          "the leagueview shape)")
    import json
    path = os.path.join(HERE, "data", "league-espn-1.json")
    if not os.path.exists(path):
        check(False, "data/league-espn-1.json present for the integration run")
        return

    def loader(league_id):
        with open(os.path.join(HERE, "data",
                               "league-%s.json" % league_id)) as fh:
            return json.load(fh)["teams"], {"teams_known": 8}

    def dead_loader(_league_id):
        raise ImportError("engine/leagueview.py not present")

    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")
    plain = waivers.build_report("espn-1", 1, top_n=6, color=False,
                                 secrets_path=bogus,
                                 rival_loader=dead_loader)
    rich = waivers.build_report("espn-1", 1, top_n=6, color=False,
                                secrets_path=bogus, rival_loader=loader)
    check(waivers.NO_COMPETITION in plain
          and waivers.NO_COMPETITION not in rich,
          "the unknown-rivals line appears only when rivals really are "
          "unknown")
    check("rival-rostered names excluded" not in plain
          and "\n       rival   " not in plain,
          "with no rival data the report shows no competition rows at all - "
          "not rows full of zeroes")
    # The real module, through the real default path - this is the leg that
    # breaks if engine/leagueview.py changes shape under us.
    live = waivers.build_report("espn-1", 1, top_n=6, color=False,
                                secrets_path=bogus)
    check("rival rosters known" in live,
          "the DEFAULT loader reaches the shipped engine/leagueview.py")
    check("rival-rostered names excluded" in rich,
          "rival-held players drop out of the free-agent pool")
    check("rival rosters known: 8 of 8 teams" in rich,
          "the report says how much of the league it can see")
    check(rich.count("\n       rival   ") >= 6,
          "every shortlist row carries its own competition read")
    check("worth burning priority?" in rich and "FAAB" not in rich,
          "priority-mode framing survives the rival upgrade")
    import re
    check(re.search(r"\b\d+-\d+%", rich) is None,
          "still no FAAB percentage bands in a priority league")
    check("DROP CANDIDATE" in rich,
          "the drop pick still renders with rival data present")


def main():
    print("WAIVER ENGINE TEST")
    test_component_math()
    test_riser_beats_faller()
    test_baselines()
    test_roster_loading()
    test_drop_candidate()
    test_no_cookies()
    test_momentum_baseline()
    test_live_report()
    test_xfp_calendar_boundary()
    test_priority_guidance()
    test_priority_live_report()
    test_competition()
    test_competition_unknown()
    test_priority_competition()
    test_live_report_with_rivals()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0]
                    if not FAILURES else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
