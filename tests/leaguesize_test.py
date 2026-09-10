#!/usr/bin/env python3
"""Acceptance test: league-size normalization (engine/leaguesize.py).

The premise being tested: public fantasy advice is written for 10-12 team
leagues, the user's ESPN league has EIGHT, and the same sentence about the
same player is useful in one and noise in the other.

Everything runs against TWO synthetic leagues built from one identical
player pool - 8 teams and 12 teams, same roster shape, same scoring - so
every difference in the output is caused by league size and nothing else.
The depth numbers are hand-checked below against the roster math (they
must sum to teams x starting slots and teams x roster_spots exactly), the
STARTABLE-at-12 / IRRELEVANT-at-8 player is downgraded in exactly one of
the two leagues, a CORE player survives both, and the tag is then chased
all the way through consensus weighing into the RENDERED lineup strip.

A closing pass runs the real leagues/espn-1.yaml + data/rankings-espn.csv
and its 10-team neighbour yahoo-main, because the whole point is a claim
about the user's actual league.

Pure and offline: no network, no writes. data/sources.yaml and the
creator-calls directory are byte-checked untouched afterwards (the same
read-only discipline as tests/consensus_test.py); nothing here needs the
tempdir ledger redirect because nothing here records votes.

    .venv/bin/python tests/leaguesize_test.py
"""

import hashlib
import os
import re
import shutil
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import consensus as C                              # noqa: E402
from engine import leaguesize as L                             # noqa: E402
from engine import lineup                                      # noqa: E402
from engine.models import LeagueConfig, Player, load_players   # noqa: E402
from engine.projections import name_key                        # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- the two synthetic leagues ----------------------------------------------
#
# One roster shape, two team counts. QB/RB/RB/WR/WR/TE/FLEX/FLEX/K/DEF plus
# six bench = 16 spots, full PPR - deliberately the shape of BOTH of the
# user's real leagues, so the synthetic result reads across to them.

SPOTS = (["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "W/R/T", "K", "DEF"]
         + ["BN"] * 6)


def league(teams):
    return LeagueConfig({"id": "synth-%d" % teams,
                         "name": "Synthetic %d" % teams,
                         "teams": teams, "roster_spots": SPOTS,
                         "rounds": 16, "scoring": {"reception": 1}})


# A flat, evenly-spaced pool so every positional rank is unambiguous and the
# flex allocation is decided by real projection comparisons, not by ties.
# Names encode the rank: "WR Player34" IS WR34.
POOL_SHAPE = [("QB", 20, 300.0, 5.0), ("RB", 60, 260.0, 3.0),
              ("WR", 60, 255.0, 3.0), ("TE", 20, 200.0, 5.0),
              ("K", 15, 150.0, 2.0), ("DEF", 15, 130.0, 3.0)]


def make_pool():
    out, r = [], 1
    for pos, n, top, step in POOL_SHAPE:
        for i in range(n):
            out.append(Player(rank=r, name="%s Player%02d" % (pos, i + 1),
                              pos=pos, team="FA",
                              proj_points=top - step * i))
            r += 1
    return out


POOL = make_pool()
L8 = league(8)
L12 = league(12)


def pkey(name, pos):
    from engine.models import norm_name
    return "%s|%s" % (norm_name(name), pos)


WR34 = pkey("WR Player34", "WR")     # the STARTABLE-at-12 / IRRELEVANT-at-8 guy
WR05 = pkey("WR Player05", "WR")     # CORE everywhere
WR28 = pkey("WR Player28", "WR")     # past the 8-team starters, still FRINGE
WR55 = pkey("WR Player55", "WR")     # deep sleeper: irrelevant in BOTH
DEF12 = pkey("DEF Player12", "DEF")  # streamed position, never irrelevant


# --- 1. replacement context -------------------------------------------------

def test_context():
    print("\n[1] replacement_context - depth of an 8 vs a 12 team league")
    c8 = L.replacement_context(L8, players=POOL)
    c12 = L.replacement_context(L12, players=POOL)

    # Hand-check, 8 teams: hard starters are QB1/RB2/WR2/TE1/K1/DEF1 per
    # team, so QB/TE/K/DEF = 8 flat and RB/WR = 16 before flex. Two flex
    # slots x 8 teams = 16 more, split by projection: RB wins 9, WR 7.
    check(c8.starter_rank == {"QB": 8, "RB": 25, "WR": 23, "TE": 8,
                              "K": 8, "DEF": 8},
          "8-team last-starter ranks (got %s)" % c8.starter_rank)
    check(c12.starter_rank == {"QB": 12, "RB": 37, "WR": 35, "TE": 12,
                               "K": 12, "DEF": 12},
          "12-team last-starter ranks (got %s)" % c12.starter_rank)

    # The invariant that proves the ranks are real starter demand and not a
    # fudge: they must total teams x STARTING slots (10 here), exactly.
    check(sum(c8.starter_rank.values()) == 8 * 10,
          "8-team starter ranks sum to teams x 10 starting slots")
    check(sum(c12.starter_rank.values()) == 12 * 10,
          "12-team starter ranks sum to teams x 10 starting slots")

    # ...and rostered depth must total teams x roster_spots (16), which is
    # what makes it a real "teams x roster_spots" estimate rather than a
    # per-position guess that happens to look plausible.
    check(sum(c8.rostered_depth.values()) == 8 * 16,
          "8-team rostered depth sums to teams x roster_spots (got %d)"
          % sum(c8.rostered_depth.values()))
    check(sum(c12.rostered_depth.values()) == 12 * 16,
          "12-team rostered depth sums to teams x roster_spots (got %d)"
          % sum(c12.rostered_depth.values()))

    # Every band widens with the league - the single claim the module makes.
    check(all(c12.starter_rank[p] > c8.starter_rank[p]
              for p in c8.starter_rank),
          "every position starts deeper at 12 teams than at 8")
    check(all(c12.fringe_rank[p] >= c8.fringe_rank[p] for p in c8.fringe_rank)
          and c12.fringe_rank["WR"] > c8.fringe_rank["WR"],
          "the fringe band widens with league size")

    # The replacement PROJECTION comes from recommend.replacement_levels and
    # the rank is read off the same board - so the Nth-best projection at a
    # position must equal that baseline exactly.
    wrs = sorted([p for p in POOL if p.pos == "WR"],
                 key=lambda x: -float(x.proj_points))
    check(abs(wrs[c8.starter_rank["WR"] - 1].proj_points
              - c8.repl_points["WR"]) < 1e-9,
          "rank N is exactly the player projecting at the replacement level")

    check(c8.rank_of(WR34) == 34 and c8.rank_of("nobody|WR") is None,
          "rank_of reads positional rank, None for a player off the board")
    check("23 start league-wide" in c8.describe("WR")
          and "deeper leagues past WR31" in c8.describe("WR"),
          "describe() states the depth in plain words (%s)"
          % c8.describe("WR"))
    check("never downgraded" in c8.describe("DEF")
          and "past DEF" not in c8.describe("DEF"),
          "describe() makes no downgrade claim for a streamed position (%s)"
          % c8.describe("DEF"))


# --- 2. relevance classes ---------------------------------------------------

def test_relevance():
    print("\n[2] relevance - CORE / STARTABLE / FRINGE / IRRELEVANT")
    c8 = L.replacement_context(L8, players=POOL)
    c12 = L.replacement_context(L12, players=POOL)

    # THE case the whole module exists for. WR34: inside the 12-team starter
    # pool (35 WR start there), past the 8-team fringe line (23 start, 31
    # including a bench round per team).
    check(L.relevance(WR34, c12) == L.STARTABLE,
          "WR34 is STARTABLE in a 12-team league")
    check(L.relevance(WR34, c8) == L.IRRELEVANT,
          "the same WR34 is IRRELEVANT in an 8-team league")

    check(L.relevance(WR05, c8) == L.CORE
          and L.relevance(WR05, c12) == L.CORE,
          "WR5 is CORE at both sizes")
    check(L.relevance(WR28, c8) == L.FRINGE,
          "WR28 is past the 8-team starters but still FRINGE, not dismissed")
    check(L.relevance(WR55, c8) == L.IRRELEVANT
          and L.relevance(WR55, c12) == L.IRRELEVANT,
          "a genuine deep sleeper (WR55) is irrelevant at BOTH sizes")

    # K/DEF are streamed from a 32-deep pool in every format: shallower
    # leagues make DEF advice MORE actionable, so it is never downgraded.
    check(L.relevance(DEF12, c8) == L.FRINGE,
          "DEF12 in an 8-team league is FRINGE, never IRRELEVANT")

    # Honest degradation: no projection in this league's pool = unjudged.
    check(L.relevance("ghost player|WR", c8) == L.UNKNOWN,
          "a player absent from the pool is UNKNOWN, not assumed irrelevant")

    # A Player object and its key must classify identically, and a bare
    # LeagueConfig must work as the second argument (the documented
    # convenience path that builds its own context).
    p = next(x for x in POOL if x.key == WR05)
    check(L.relevance(p, c8) == L.relevance(WR05, c8),
          "a Player and its player_key classify the same")
    check(L.relevance(p, L8, ctx=c8) == L.CORE,
          "relevance(player, league, ctx=...) accepts a LeagueConfig")


# --- 3. adjust_call ---------------------------------------------------------

def _call(key, name, verdict="start", confidence="high", quote="love him"):
    return {"source": "hot-takes", "player": name, "player_key": key,
            "verdict": verdict, "confidence": confidence, "quote": quote,
            "url": "https://example.invalid/ep", "fetched": "2026-09-01"}


def test_adjust_call():
    print("\n[3] adjust_call - downgraded, tagged, never dropped")
    c8 = L.replacement_context(L8, players=POOL)
    c12 = L.replacement_context(L12, players=POOL)

    call = _call(WR34, "WR Player34")
    before = dict(call)

    adj8 = L.adjust_call(call, c8)
    adj12 = L.adjust_call(call, c12)

    check(call == before, "the input call is never mutated")
    check(adj12 is call, "12-team league: STARTABLE, so the call is untouched")

    check(adj8 is not call and adj8["relevance"] == L.IRRELEVANT,
          "8-team league: the same call is downgraded")
    check(adj8["verdict"] == call["verdict"]
          and adj8["quote"] == call["quote"],
          "the call still SAYS what it said - only its weight changed")
    check(adj8["confidence"] == "med",
          "confidence drops exactly one tier (high -> med), not to zero")
    check(adj8["weight_factor"] == L.DOWNGRADE_WEIGHT
          and 0 < L.DOWNGRADE_WEIGHT < 1,
          "a real weight discount, not a mute (%.2f)" % L.DOWNGRADE_WEIGHT)
    check(adj8["sized_for"] == "advice sized for deeper leagues",
          "tagged with the reason: %r" % adj8["sized_for"])
    check(adj8["size_rank"] == "WR34", "tag names the rank that earned it")
    check("23 start league-wide" in adj8["size_note"]
          and "in an 8-team league" in adj8["size_note"]
          and "advice sized for deeper leagues" in adj8["size_note"],
          "size_note explains WHY: %s" % adj8["size_note"])
    check("already rostered here" in adj8["size_note"],
          "WR34 is inside the 8-team rostered depth (41): note says so")
    deep = L.adjust_call(_call(WR55, "WR Player55"), c8)
    check("not rostered in a league this shallow" in deep["size_note"],
          "WR55 is past rostered depth: the note distinguishes the two")

    # Never downgraded, at any size.
    core = _call(WR05, "WR Player05")
    check(L.adjust_call(core, c8) is core and L.adjust_call(core, c12) is core,
          "a CORE player's call is never downgraded, at either size")
    dst = _call(DEF12, "DEF Player12")
    check(L.adjust_call(dst, c8) is dst,
          "a DEF call is never downgraded for league size")
    ghost = _call("ghost player|WR", "Ghost Player")
    check(L.adjust_call(ghost, c8) is ghost,
          "an unrankable player is left alone (absence is not evidence)")

    # Floor and idempotence.
    low = L.adjust_call(_call(WR34, "WR Player34", confidence="low"), c8)
    check(low["confidence"] == "low", "confidence floors at 'low'")
    twice = L.adjust_call(adj8, c8)
    check(twice["confidence"] == "low"
          and twice["weight_factor"] == L.DOWNGRADE_WEIGHT,
          "re-adjusting does not compound the weight discount")

    # Malformed input must never raise.
    check(L.adjust_call({"source": "x"}, c8) == {"source": "x"}
          and L.adjust_call({"player_key": "bad"}, c8) == {"player_key": "bad"},
          "calls without a usable player_key pass through untouched")


def test_adjust_calls_notes():
    print("\n[4] adjust_calls - the honest-degradation note trail")
    c8 = L.replacement_context(L8, players=POOL)
    calls = [_call(WR05, "WR Player05"), _call(WR34, "WR Player34"),
             _call(WR55, "WR Player55")]
    out, notes = L.adjust_calls(calls, c8)
    check(len(out) == 3, "no call is ever dropped (3 in, 3 out)")
    check(sum(1 for c in out if c.get("sized_for")) == 2,
          "exactly the two irrelevant calls are tagged")
    check(notes and "2 creator call(s) downgraded for league size (8 teams)"
          in notes[0],
          "summary note counts the downgrades and names the size: %r"
          % (notes[0] if notes else None))
    check(any("WR Player34" in n and "hot-takes" in n for n in notes[1:]),
          "one note per downgrade, naming the source and the player")
    check(L.adjust_calls([], c8) == ([], []),
          "an empty week produces no notes at all")


# --- 5. consensus integration -----------------------------------------------

SOURCES = [
    {"id": "hot-takes", "name": "Hot Takes Weekly", "type": "youtube",
     "handle": "@hot-takes", "enabled": True, "weight": 50},
    {"id": "engine", "name": "War Room Engine", "type": "feed",
     "handle": "engine", "enabled": True, "weight": 40},
]


def test_consensus_weighting():
    print("\n[5] consensus - the downgrade changes the verdict, not the voice")
    c8 = L.replacement_context(L8, players=POOL)
    c12 = L.replacement_context(L12, players=POOL)
    universe = {WR34: {"name": "WR Player34", "pos": "WR"}}
    demand = C.starters_demand(L8)
    feed = {"engine": {WR34: "sit"}}
    raw = [_call(WR34, "WR Player34", verdict="start")]

    # 12 teams: creator 50 start vs engine 40 sit -> +10/90, weighted START.
    row12 = C.build_rows(SOURCES, universe,
                         L.adjust_calls(raw, c12)[0], feed, demand)[0]
    check(abs(row12["score"] - round((50 - 40) / 90.0, 3)) < 1e-9
          and row12["verdict"] == "START",
          "12 teams: the creator carries the row (score %.3f)"
          % row12["score"])

    # 8 teams: the same call is worth 50 x 0.4 = 20 -> (20 - 40)/60, SIT.
    adj8 = L.adjust_calls(raw, c8)[0]
    row8 = C.build_rows(SOURCES, universe, adj8, feed, demand)[0]
    check(abs(row8["score"] - round((20 - 40) / 60.0, 3)) < 1e-9
          and row8["verdict"] == "SIT",
          "8 teams: the discount flips the verdict (score %.3f)"
          % row8["score"])

    vote = next(v for v in row8["votes"] if v["source"] == "hot-takes")
    check(vote["weight"] == 20.0 and vote["weight_factor"] == 0.4,
          "the vote carries the discounted weight, not the raw 50")
    check(vote["confidence"] == "med",
          "the downgraded confidence reaches the vote")
    check(vote.get("sized_for") == "advice sized for deeper leagues"
          and vote.get("size_rank") == "WR34",
          "the tag reaches the vote so the strip can print it")

    # The SOURCE is not demoted - only this take is. Hot Takes still outweighs
    # the engine and is still the top-weighted voice being watched.
    check(row8["top_source"] == "hot-takes" and row8["top_disagrees"],
          "one badly-sized take does not cost the source its standing")

    # A hand-edited weight_factor of 0 must not become a FULL-strength vote:
    # zeroing the only vote's weight would hit weigh()'s "no weights
    # configured, split evenly" fallback and invert the discount entirely.
    muted = dict(adj8[0], weight_factor=0.0)
    solo = C.build_rows(SOURCES, universe, [muted], {}, demand)[0]
    mv = solo["votes"][0]
    check(mv["weight"] == 50 * C.MIN_WEIGHT_FACTOR and mv["weight"] > 0,
          "a 0 weight_factor floors above zero, never inverts to full weight")
    check(C.build_rows(SOURCES, universe,
                       [dict(adj8[0], weight_factor="nonsense")], {},
                       demand)[0]["votes"][0]["weight"] == 50.0,
          "an unparseable weight_factor falls back to no discount")

    # A CORE player's call is untouched all the way through the blend.
    uni5 = {WR05: {"name": "WR Player05", "pos": "WR"}}
    core_calls = L.adjust_calls([_call(WR05, "WR Player05",
                                       verdict="start")], c8)[0]
    row_core = C.build_rows(SOURCES, uni5, core_calls,
                            {"engine": {WR05: "sit"}}, demand)[0]
    cv = next(v for v in row_core["votes"] if v["source"] == "hot-takes")
    check(cv["weight"] == 50.0 and cv["confidence"] == "high"
          and "sized_for" not in cv,
          "a CORE player's vote keeps full weight, confidence, and no tag")


# --- 6. the tag reaches the rendered strip ----------------------------------

def test_rendered_strip():
    print("\n[6] the tag surfaces in the RENDERED consensus strip")
    c8 = L.replacement_context(L8, players=POOL)
    demand = C.starters_demand(L8)

    # An 8-team roster with one more flex-eligible body than flex slots, so
    # the last flex spot is genuinely contested and the strip renders.
    entries = [("QB Player01", "QB", 22.0), ("RB Player05", "RB", 18.0),
               ("RB Player10", "RB", 16.0), ("WR Player03", "WR", 17.0),
               ("WR Player08", "WR", 15.0), ("TE Player02", "TE", 11.0),
               ("RB Player30", "RB", 12.0), ("WR Player34", "WR", 11.5),
               ("RB Player31", "RB", 11.0), ("K Player01", "K", 8.0),
               ("DEF Player01", "DEF", 7.0)]
    proj = dict((name_key(n), {"proj": v, "pos": pos, "team": "FA",
                               "source": "espn"})
                for n, pos, v in entries)
    roster = {"name": "Size Test", "size": len(entries),
              "players": [e[0] for e in entries], "path": ""}

    calls = L.adjust_calls([_call(WR34, "WR Player34", verdict="start",
                                  quote="sneaky WR3 upside this week")], c8)[0]
    row = C.build_rows(SOURCES, {WR34: {"name": "WR Player34", "pos": "WR"}},
                       calls, {"engine": {WR34: "sit"}}, demand)[0]

    out = lineup.lineup_report(L8, roster, 1, proj, consensus={WR34: row},
                               color=False)
    check("WR Player34" in out and "Your model says" in out,
          "the contested flex call renders a consensus strip")
    check("advice sized for deeper leagues" in out,
          "the league-size tag reaches the rendered strip")
    check("[WR34 - advice sized for deeper leagues]" in out,
          "the strip shows the RANK that earned the downgrade, inline")
    check("Hot Takes Weekly start (med" in out,
          "the strip shows the downgraded confidence next to the vote")
    check(re.search(r"Your model says SIT", out),
          "with the creator discounted, the model reads SIT")

    # Control: the identical call at 12 teams renders with no tag at all.
    c12 = L.replacement_context(L12, players=POOL)
    calls12 = L.adjust_calls([_call(WR34, "WR Player34", verdict="start",
                                    quote="sneaky WR3 upside this week")],
                             c12)[0]
    row12 = C.build_rows(SOURCES, {WR34: {"name": "WR Player34", "pos": "WR"}},
                         calls12, {"engine": {WR34: "sit"}}, demand)[0]
    out12 = lineup.lineup_report(L8, roster, 1, proj,
                                 consensus={WR34: row12}, color=False)
    check("advice sized for deeper leagues" not in out12
          and "Hot Takes Weekly start (high" in out12,
          "the same call sized for 12 teams renders clean - no tag, no "
          "discount")


# --- 7. the real leagues ----------------------------------------------------

def test_real_leagues():
    print("\n[7] the user's real leagues - espn-1 (8) vs yahoo-main (10)")
    espn = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    yahoo = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    check(espn.teams == 8 and yahoo.teams == 10,
          "the fixture leagues really are 8 and 10 teams")

    ce = L.replacement_context(espn)
    cy = L.replacement_context(yahoo)
    check(ce.starter_rank == {"QB": 8, "RB": 22, "WR": 26, "TE": 8,
                              "K": 8, "DEF": 8},
          "espn-1 last-starter ranks (got %s)" % ce.starter_rank)
    check(sum(ce.starter_rank.values()) == 8 * 10
          and sum(ce.rostered_depth.values()) == 8 * 16,
          "espn-1 depth reconciles to teams x slots and teams x roster_spots")
    check(ce.fringe_rank["WR"] == 34 and ce.rostered_depth["WR"] == 44,
          "espn-1 WR: 26 start, 34 is the advice horizon, ~44 rostered")
    check(all(cy.starter_rank[p] > ce.starter_rank[p]
              for p in ce.starter_rank),
          "the 10-team league starts deeper at every position")

    # A real player who splits the two leagues. WR34 in the espn-1 pool is
    # past the 8-team horizon (34) but inside yahoo-main's (42).
    pool = load_players(os.path.join(HERE, espn.rankings_csv))
    wr36 = next(p for p in pool
                if p.pos == "WR" and ce.rank_of(p.key) == 36)
    check(L.relevance(wr36, ce) == L.IRRELEVANT
          and L.relevance(wr36, cy) in (L.FRINGE, L.STARTABLE),
          "%s (WR36) is irrelevant in The Original 8, live in Kid's Table"
          % wr36.name)

    call = _call(wr36.key, wr36.name, verdict="start")
    adj = L.adjust_call(call, ce)
    check(adj["sized_for"] == "advice sized for deeper leagues",
          "a real start call on %s is downgraded for espn-1" % wr36.name)
    check(L.adjust_call(call, cy) is call,
          "the identical call stands in the 10-team league")

    top = next(p for p in pool if p.pos == "RB" and ce.rank_of(p.key) == 1)
    check(L.relevance(top, ce) == L.CORE
          and L.adjust_call(_call(top.key, top.name), ce)
          is not None
          and "sized_for" not in L.adjust_call(_call(top.key, top.name), ce),
          "%s (RB1) is CORE in espn-1 and can never be downgraded" % top.name)

    print("      WORKED EXAMPLE - %s (%d teams)" % (espn.name, espn.teams))
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        print("        %s" % ce.describe(pos))
    print("        downgrade example: %s" % adj["size_note"])
    return wr36, top


def test_build_consensus_wiring(wr36, rb1):
    """The integration point itself: build_consensus must adjust calls.

    Everything above proves the parts. This proves the WIRING - that a call
    sitting in the week's calls file is downgraded by the time it reaches a
    consensus row, for the real espn-1 league. Registry and calls both come
    from a tempdir (the tests/mock_draft.py redirect pattern), so the
    shipped data/sources.yaml and data/creator_calls/ are never read or
    written by this check.
    """
    print("\n[8] build_consensus wiring - end to end on the real espn-1")
    tmpdir = tempfile.mkdtemp(prefix="leaguesize-")
    try:
        registry = os.path.join(tmpdir, "sources.yaml")
        with open(registry, "w") as fh:
            yaml.safe_dump({"sources": [
                {"id": "engine", "name": "War Room Engine", "type": "feed",
                 "handle": "engine", "enabled": True, "weight": 40},
                {"id": "hot-takes", "name": "Hot Takes Weekly",
                 "type": "youtube", "handle": "@hot-takes",
                 "enabled": True, "weight": 50},
            ]}, fh)

        calls_dir = os.path.join(tmpdir, "creator_calls")
        os.makedirs(calls_dir)
        with open(os.path.join(calls_dir, "week-1.yaml"), "w") as fh:
            yaml.safe_dump({"week": 1, "calls": [
                _call(wr36.key, wr36.name, verdict="start"),
                _call(rb1.key, rb1.name, verdict="start"),
            ]}, fh)

        cons = C.build_consensus("espn-1", 1, calls_dir=calls_dir,
                                 registry_path=registry)
        check(cons["size_context"]["teams"] == 8
              and cons["size_context"]["starter_rank"]["WR"] == 26,
              "the consensus result carries this league's size context")
        check(any("downgraded for league size (8 teams)" in n
                  for n in cons["notes"]),
              "the downgrade is announced in the result notes, not hidden")

        by_key = dict((r["player_key"], r) for r in cons["rows"])
        deep = by_key.get(wr36.key)
        check(deep is not None, "the downgraded call still produces a row "
                                "(downgraded, never dropped)")
        vote = next(v for v in deep["votes"] if v["source"] == "hot-takes")
        check(vote["weight"] == 50 * L.DOWNGRADE_WEIGHT
              and vote["confidence"] == "med",
              "%s's call arrives at the row already discounted" % wr36.name)
        check("advice sized for deeper leagues" in C.format_voices(deep),
              "the tag survives the whole pipeline into the strip")

        core_row = by_key.get(rb1.key)
        if core_row is not None:
            cv = next(v for v in core_row["votes"]
                      if v["source"] == "hot-takes")
            check(cv["weight"] == 50 and "sized_for" not in cv,
                  "the same source's CORE call in the same file is untouched")
        else:
            check(False, "the CORE call should also produce a row")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- 8. read-only discipline ------------------------------------------------

def _sha(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


WATCHED = [os.path.join(HERE, "data", "sources.yaml"),
           os.path.join(HERE, "data", "rankings-espn.csv"),
           os.path.join(HERE, "data", "creator_calls", "week-1.yaml")]


def main():
    print("=" * 74)
    print("LEAGUE-SIZE NORMALIZATION TEST")
    print("=" * 74)
    before = dict((p, _sha(p)) for p in WATCHED)

    test_context()
    test_relevance()
    test_adjust_call()
    test_adjust_calls_notes()
    test_consensus_weighting()
    test_rendered_strip()
    wr36, rb1 = test_real_leagues()
    test_build_consensus_wiring(wr36, rb1)

    print("\n[9] read-only discipline")
    for p in WATCHED:
        check(_sha(p) == before[p],
              "%s byte-identical (normalization never writes)"
              % os.path.relpath(p, HERE))

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d of %d check(s):" % (len(FAILURES), CHECKS[0]))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL %d CHECKS PASSED" % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
