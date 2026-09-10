#!/usr/bin/env python3
"""Acceptance test: source consensus engine (engine/consensus.py).

FIXTURE RULE - read before editing this file:

    Acceptance tests assert INVARIANTS AND BEHAVIOR against controlled
    fixtures. They must NEVER depend on the contents of the user's live
    roster (data/rosters/), source registry (data/sources.yaml), or league
    (leagues/) files. Those files change every time the product is actually
    used - enabling one creator source used to flip this suite red - and a
    test that asserts today's contents fails for the wrong reason: it
    reports a regression when nothing regressed. Section [8] therefore
    builds TWO registries of its own (one with creator sources, one with
    only the built-in feeds) plus its own league and roster, and reaches
    them through build_consensus(registry_path=/roster_dir=/calls_dir=)
    and, for the CLI, the module-constant redirects that
    tests/mock_draft.py::test_persistence uses for save_state.SAVE_DIR.

Synthetic checks first: the weighted math is hand-checked against a planted
5-source setup (score = sum(weight * +1/-1/+0.5) over normalized weights),
LONE-DISSENT must name the dissenter, the top-weighted-disagrees flag must
fire against both the weighted verdict and the engine, rank calls must
convert through the positional starter demand, and the ledger scoring rule
(start-side hit = actual >= positional replacement) is checked on synthetic
actuals with a hand-computed replacement level. The ledger is keyed per
LEAGUE: two leagues sharing a week and a player must keep separate rows
with independent grades, old league-less rows must be graded once under
the first league that scores them (tagged legacy), and re-recording never
duplicates either shape. Then the lineup consensus
strip and the digest "Room" section render from synthetic rows, and a live
smoke builds consensus for yahoo-main week 1 from the cached feeds.

All ledger writes go to a mkdtemp dir removed in a finally block (the
consensus.LEDGER_PATH redirect - same discipline as streaming.LOG_PATH in
tests/mock_draft.py); data/sources.yaml and data/source_ledger.jsonl are
byte-checked untouched, as are the fixture registries (consensus reads a
registry, it never rewrites one).

    .venv/bin/python tests/consensus_test.py
"""

import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import consensus as C                            # noqa: E402
from engine import digest, lineup                            # noqa: E402
from engine.models import LeagueConfig, Player               # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _v(source, weight, verdict, name=None, **extra):
    d = {"source": source, "name": name or source, "weight": weight,
         "verdict": verdict}
    d.update(extra)
    return d


LEAGUE = LeagueConfig({
    "id": "test-cons", "name": "Consensus League", "teams": 10,
    "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T",
                     "K", "DEF", "BN", "BN", "BN"],
    "scoring": {"reception": 1},
})

# Five planted sources: engine + one creator + the three feed voices.
SOURCES5 = [
    {"id": "engine", "name": "War Room Engine", "type": "feed",
     "handle": "engine", "enabled": True, "weight": 40},
    {"id": "hot-takes", "name": "Hot Takes Weekly", "type": "youtube",
     "handle": "@hot-takes", "enabled": True, "weight": 30},
    {"id": "espn-proj", "name": "ESPN Projections", "type": "feed",
     "handle": "espn-proj", "enabled": True, "weight": 20},
    {"id": "sleeper-proj", "name": "Sleeper Projections", "type": "feed",
     "handle": "sleeper-proj", "enabled": True, "weight": 15},
    {"id": "chen-tiers", "name": "Boris Chen Tiers", "type": "feed",
     "handle": "chen-tiers", "enabled": True, "weight": 10},
]

DEMAND = C.starters_demand(LEAGUE)


# --- 1. weighted math -------------------------------------------------------

def test_math():
    print("\n[1] weighted verdict math - hand-checked")
    # 40 start - 30 sit + 20 start = +30/90 = 0.3333 -> 67% start-ward
    score, pct = C.weigh([_v("a", 40, "start"), _v("b", 30, "sit"),
                          _v("c", 20, "start")])
    check(abs(score - (40 - 30 + 20) / 90.0) < 1e-4,   # score rounds to 4dp
          "score = sum(w*v)/sum(w) (got %.4f, want %.4f)"
          % (score, 30 / 90.0))
    check(pct == 67, "start-ward pct 67 (got %d)" % pct)
    check(C.verdict_of(score) == "START", "positive score reads START")

    # flex counts half: 40 flex vs 40 sit -> (20-40)/80 = -0.25 -> SIT
    score, pct = C.weigh([_v("a", 40, "flex"), _v("b", 40, "sit")])
    check(abs(score + 0.25) < 1e-6, "flex-lean counts +0.5 (score %.2f)"
          % score)
    check(C.verdict_of(score) == "SIT", "flex cannot outvote an equal sit")

    # unanimous start = 100%; all-zero weights fall back to an equal split
    score, pct = C.weigh([_v("a", 40, "start"), _v("b", 10, "start")])
    check(pct == 100, "unanimous start reads 100%")
    score, _ = C.weigh([_v("a", 0, "start"), _v("b", 0, "sit")])
    check(score == 0.0, "all-zero weights split evenly, not crash")

    # display pct flips to the winning side
    row = {"verdict": "SIT", "pct": 36}
    check(C.display_pct(row) == 64, "SIT row displays the sit-ward share")


# --- 2. agreement classes ---------------------------------------------------

def test_agreement():
    print("\n[2] agreement classes")
    votes = [_v("a", 40, "start"), _v("b", 30, "start"), _v("c", 20, "flex")]
    score, _ = C.weigh(votes)
    check(C.agreement(votes, score) == ("UNANIMOUS", None),
          "start+start+flex all point the same way: UNANIMOUS")

    votes = [_v("a", 40, "start"), _v("b", 30, "start"),
             _v("c", 20, "sit", name="Boris Chen Tiers")]
    label, who = C.agreement(votes, C.weigh(votes)[0])
    check(label == "LONE-DISSENT", "one voice against three+: LONE-DISSENT")
    check(who == "Boris Chen Tiers", "dissenter named (got %r)" % who)

    votes = [_v("a", 40, "start"), _v("b", 41, "sit")]
    score, _ = C.weigh(votes)
    check(C.agreement(votes, score)[0] == "SPLIT",
          "two near-equal opposing voices: SPLIT (|score| < %.2f)"
          % C.SPLIT_BAND)

    votes = [_v("a", 40, "start"), _v("b", 10, "sit"), _v("c", 10, "sit")]
    score, _ = C.weigh(votes)
    check(C.agreement(votes, score)[0] == "MAJORITY",
          "two dissenters, clear margin: MAJORITY (not LONE-DISSENT)")


# --- 3. build_rows on the planted 5-source setup ----------------------------

def _key(name, pos):
    from engine.models import norm_name
    return "%s|%s" % (norm_name(name), pos)


def test_build_rows():
    print("\n[3] build_rows - planted calls + feed votes")
    k_a = _key("Alpha Back", "RB")
    k_b = _key("Beta Wideout", "WR")
    universe = {k_a: {"name": "Alpha Back", "pos": "RB"},
                k_b: {"name": "Beta Wideout", "pos": "WR"}}
    feed_votes = {
        "engine": {k_a: "start", k_b: "start"},
        "espn-proj": {k_a: "start", k_b: "start"},
        "sleeper-proj": {k_a: "start"},                # silent on Beta
        "chen-tiers": {k_a: "start", k_b: "sit"},
    }
    calls = [
        {"source": "hot-takes", "player": "Alpha Back", "player_key": k_a,
         "verdict": "sit", "confidence": "high",
         "quote": "bench Alpha Back, the matchup is brutal", "url": "x",
         "fetched": "2026-09-01"},
        # same source contradicts itself at lower confidence - must lose
        {"source": "hot-takes", "player": "Alpha Back", "player_key": k_a,
         "verdict": "start", "confidence": "low", "quote": "eh", "url": "x",
         "fetched": "2026-09-01"},
        # rank call: WR4 is inside the WR starter demand -> start
        {"source": "hot-takes", "player": "Beta Wideout", "player_key": k_b,
         "verdict": "rank", "value": 4, "confidence": "med",
         "quote": "Beta Wideout is my WR4", "url": "x",
         "fetched": "2026-09-01"},
        # unknown source: ignored, never a KeyError
        {"source": "nobody", "player": "Alpha Back", "player_key": k_a,
         "verdict": "start", "confidence": "high", "quote": "", "url": "",
         "fetched": "2026-09-01"},
    ]
    rows = C.build_rows(SOURCES5, universe, calls, feed_votes, DEMAND)
    by_key = dict((r["player_key"], r) for r in rows)
    check(set(by_key) == {k_a, k_b}, "one row per player, unknown-source "
                                     "call ignored")

    a = by_key[k_a]
    # engine 40 start, hot-takes 30 sit (high wins over low), espn 20 start,
    # sleeper 15 start, chen 10 start -> (40-30+20+15+10)/115
    want = (40 - 30 + 20 + 15 + 10) / 115.0
    check(abs(a["score"] - round(want, 3)) < 1e-9,
          "Alpha score hand-checked: %.3f" % want)
    check(a["verdict"] == "START" and a["agreement"] == "LONE-DISSENT"
          and a["dissenter"] == "Hot Takes Weekly",
          "Alpha: START, LONE-DISSENT names Hot Takes Weekly")
    ht = next(v for v in a["votes"] if v["source"] == "hot-takes")
    check(ht["verdict"] == "sit" and ht["confidence"] == "high"
          and "brutal" in ht["quote"],
          "contradiction resolved by confidence; quote carried as evidence")
    check([v["source"] for v in a["votes"]][0] == "engine",
          "votes ordered by weight desc (engine first)")
    check(a["top_source"] == "engine" and not a["top_disagrees"],
          "top-weighted engine agrees with itself: no flag")

    b = by_key[k_b]
    rank_vote = next(v for v in b["votes"] if v["source"] == "hot-takes")
    check(rank_vote["verdict"] == "start"
          and rank_vote.get("detail") == "rank WR4",
          "rank WR4 inside starter demand converts to start, detail kept")
    check(all(v["source"] != "sleeper-proj" for v in b["votes"]),
          "a silent source casts no vote (absence, not a sit)")

    # rank outside the demand converts to sit
    calls_out = [dict(calls[2], value=55)]
    rows2 = C.build_rows(SOURCES5, universe, calls_out, {}, DEMAND)
    v55 = rows2[0]["votes"][0]
    check(v55["verdict"] == "sit" and v55["detail"] == "rank WR55",
          "rank WR55 outside starter demand converts to sit")


def test_top_weighted_flag():
    print("\n[4] top-weighted-disagrees flag")
    sources = [dict(s) for s in SOURCES5]
    sources[1]["weight"] = 50          # Hot Takes Weekly now outweighs engine
    k = _key("Alpha Back", "RB")
    universe = {k: {"name": "Alpha Back", "pos": "RB"}}
    calls = [{"source": "hot-takes", "player": "Alpha Back",
              "player_key": k, "verdict": "sit", "confidence": "high",
              "quote": "fade him", "url": "", "fetched": "2026-09-01"}]
    feed = {"engine": {k: "start"}, "espn-proj": {k: "start"}}
    row = C.build_rows(sources, universe, calls, feed, DEMAND)[0]
    # 50 sit vs 40+20 start -> score +10/110: weighted START, top says sit
    check(row["verdict"] == "START" and row["top_source"] == "hot-takes",
          "creator outweighs engine as the top source")
    check(row["top_disagrees"], "flag fires: top-weighted source says sit")
    check("the engine" in row["top_note"]
          and "the weighted verdict" in row["top_note"],
          "note names both disagreements (engine AND weighted verdict)")
    check("DISAGREES" in C.format_weighted(row),
          "strip says top-weighted source DISAGREES")

    # weighted verdict flips against the engine -> vs_engine highlight
    calls2 = [dict(calls[0])]
    feed2 = {"engine": {k: "start"}}
    sources2 = [dict(s) for s in SOURCES5]
    sources2[0]["weight"] = 10         # engine light, creator 30 heavy
    row2 = C.build_rows(sources2, universe, calls2, feed2, DEMAND)[0]
    check(row2["verdict"] == "SIT" and row2["vs_engine"],
          "weighted verdict against the engine sets vs_engine")


# --- 5. ledger --------------------------------------------------------------

def test_ledger():
    print("\n[5] source ledger - record, score, scoreboard")
    tmpdir = tempfile.mkdtemp(prefix="consensus-ledger-")
    real = C.LEDGER_PATH
    C.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")
    try:
        k = _key("Alpha Back", "RB")
        universe = {k: {"name": "Alpha Back", "pos": "RB"}}
        feed = {"engine": {k: "start"}, "espn-proj": {k: "sit"}}
        rows = C.build_rows(SOURCES5, universe, [], feed, DEMAND)
        n = C.record_votes(3, rows, league="league-a")
        check(n == 2,
              "recorded one vote per (league, source, player): %d" % n)
        check(C.record_votes(3, rows, league="league-a") == 0,
              "re-recording the same league+week appends nothing "
              "(idempotent)")
        check(C.record_votes(3, rows, league="league-b") == 2,
              "a SECOND league, same week + same player, gets its own rows")
        entries = C.read_ledger()
        check(len(entries) == 4
              and sorted(set(e.get("league") for e in entries))
              == ["league-a", "league-b"],
              "ledger rows carry their league (no cross-league collision)")
        check(all(e["hit"] is None for e in entries),
              "votes land pending - outcomes unknown at log time")

        # legacy tolerance: a pre-league-tagging row IS the record for its
        # (week, source, player) - re-recording under a league adds nothing
        C._write_ledger([
            {"week": 5, "source": "engine", "player": "Alpha Back",
             "player_key": k, "pos": "RB", "verdict": "start",
             "logged": "old", "actual": None, "replacement": None,
             "hit": None}], C.LEDGER_PATH)
        rows5 = C.build_rows(SOURCES5, universe, [],
                             {"engine": {k: "start"}}, DEMAND)
        check(C.record_votes(5, rows5, league="league-a") == 0,
              "an old league-less row already IS the record - never "
              "duplicated by a league-tagged re-record")

        # synthetic actuals, hand-checked with an explicit RB demand of 4:
        # actuals 30,28,26,24,22,... -> replacement = 4th-best = 24.0
        positions = dict(("rb%d" % i, "RB") for i in range(10))
        positions["alpha back"] = "RB"
        pts = [30.0, 28.0, 26.0, 24.0, 22.0, 20.0, 18.0, 16.0, 14.0, 12.0]
        act = dict(("rb%d" % i, pts[i]) for i in range(10))
        act["alpha back"] = 15.0
        repl = C.replacement_points(act, positions, {"RB": 4})["RB"]
        check(repl == 24.0,
              "replacement = 4th-best actual (24.0, got %.1f)" % repl)

        entries = [
            {"week": 1, "source": "s1", "player_key": k, "pos": "RB",
             "verdict": "start", "hit": None},                 # 15.0 < 24
            {"week": 1, "source": "s2", "player_key": k, "pos": "RB",
             "verdict": "sit", "hit": None},
            {"week": 1, "source": "s3", "player_key": "rb0|RB", "pos": "RB",
             "verdict": "flex", "hit": None},                  # 30.0: hit
            {"week": 1, "source": "s4", "player_key": "ghost|K", "pos": "K",
             "verdict": "start", "hit": None},                 # no actual
            {"week": 1, "source": "s5", "player_key": k, "pos": "RB",
             "verdict": "rank", "hit": None},                  # defensive
        ]
        scored = C.score_entries(entries, {1: act}, positions, {"RB": 4})
        check(scored == 3, "scored 3 of 5 (K and raw-rank unscorable)")
        e1, e2, e3, e4, e5 = entries
        check(e1["hit"] is False and e2["hit"] is True,
              "start below replacement misses; the sit call on him hits")
        check(e1["actual"] == 15.0 and e1["replacement"] == 24.0,
              "actual and replacement recorded on the entry")
        check(e3["hit"] is True, "flex call is graded start-side")
        check(e4["hit"] is None and "offense-only" in e4["unscorable"],
              "missing actual marked unscorable, visibly, not deleted")
        check(e5["hit"] is None and e5.get("unscorable"),
              "a raw rank verdict is marked unscorable, not guessed")

        # score_ledger end-to-end with patched actuals + atomic rewrite
        C._write_ledger([
            {"week": 1, "source": "engine", "player": "Alpha Back",
             "player_key": k, "pos": "RB", "verdict": "start",
             "actual": None, "replacement": None, "hit": None},
            {"week": 2, "source": "engine", "player": "Alpha Back",
             "player_key": k, "pos": "RB", "verdict": "sit",
             "actual": None, "replacement": None, "hit": None},
        ], C.LEDGER_PATH)
        pool = [Player(rank=i + 1, name=n.title(), pos="RB")
                for i, n in enumerate(sorted(positions))]
        real_actuals = C.week_actuals
        C.week_actuals = lambda weeks, force=False: dict(
            (w, act) for w in weeks)
        try:
            out = C.score_ledger(LEAGUE, pool, upto_week=3)
        finally:
            C.week_actuals = real_actuals
        check(out["scored"] == 2 and out["weeks"] == [1, 2],
              "score_ledger scores both pending weeks")
        check(not os.path.exists(C.LEDGER_PATH + ".tmp"),
              "atomic rewrite leaves no .tmp behind")
        after = C.read_ledger()
        check(all(e["hit"] is not None for e in after)
              and after[0]["verdict"] == "start",
              "outcomes filled, verdicts untouched")
        check(all(e.get("league") == "test-cons" and e.get("legacy") is True
                  for e in after),
              "league-less rows graded ONCE under the league that scored "
              "them, tagged legacy")

        sb = C.scoreboard(after)
        check(sb["weeks"] == [1, 2], "scoreboard sees two scored weeks")
        eng = sb["rows"][0]
        check(eng["source"] == "engine" and eng["scored"] == 2,
              "per-source aggregation over scored entries")

        # cross-league grading separation: same week, same player, two
        # leagues -> two rows, each graded only by its own league's pass
        spots = ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T",
                 "K", "DEF", "BN", "BN", "BN"]
        lg_a = LeagueConfig({"id": "cons-a", "name": "League A",
                             "teams": 10, "roster_spots": spots,
                             "scoring": {"reception": 1}})
        lg_b = LeagueConfig({"id": "cons-b", "name": "League B",
                             "teams": 10, "roster_spots": spots,
                             "scoring": {"reception": 1}})
        C._write_ledger([
            {"league": "cons-a", "week": 1, "source": "engine",
             "player": "Alpha Back", "player_key": k, "pos": "RB",
             "verdict": "start", "actual": None, "replacement": None,
             "hit": None},
            {"league": "cons-b", "week": 1, "source": "engine",
             "player": "Alpha Back", "player_key": k, "pos": "RB",
             "verdict": "sit", "actual": None, "replacement": None,
             "hit": None},
        ], C.LEDGER_PATH)
        C.week_actuals = lambda weeks, force=False: dict(
            (w, act) for w in weeks)
        try:
            out_a = C.score_ledger(lg_a, pool, upto_week=3)
            mid = dict((e["league"], e) for e in C.read_ledger())
            out_b = C.score_ledger(lg_b, pool, upto_week=3)
        finally:
            C.week_actuals = real_actuals
        check(out_a["scored"] == 1 and mid["cons-b"]["hit"] is None,
              "league A's pass grades ONLY its own row - B stays pending")
        check(mid["cons-a"]["hit"] is not None,
              "league A's row graded by league A's pass")
        by_lg = dict((e["league"], e) for e in C.read_ledger())
        check(out_b["scored"] == 1 and by_lg["cons-b"]["hit"] is not None,
              "league B's pass grades league B's row")
        check(by_lg["cons-a"]["verdict"] == "start"
              and by_lg["cons-b"]["verdict"] == "sit"
              and by_lg["cons-a"]["hit"] != by_lg["cons-b"]["hit"],
              "same player, same week: two leagues keep two rows with "
              "independent grades")
        check(not any(e.get("legacy") for e in C.read_ledger()),
              "league-tagged rows are never marked legacy")
    finally:
        C.LEDGER_PATH = real
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- 6. lineup consensus strip ----------------------------------------------

class StubMatch(object):
    def __init__(self, player, score=100.0):
        self.player, self.score = player, score


class StubMatcher(object):
    def __init__(self, pool):
        self.pool = dict((name_key(p.name), p) for p in pool)

    def match(self, text):
        p = self.pool.get(name_key(text))
        return StubMatch(p) if p is not None else None


def test_lineup_strip():
    print("\n[6] lineup report - consensus strip on close calls only")
    entries = [("Quincy Passer", "QB", "KC", 20.0),
               ("Rex Runner", "RB", "SF", 15.0),
               ("Ray Rusher", "RB", "DAL", 12.0),
               ("Walt Wide", "WR", "MIA", 14.0),
               ("Wes Wing", "WR", "BUF", 13.0),
               ("Tom Tight", "TE", "LV", 9.0),
               ("Flex Favorite", "WR", "NYJ", 11.5),
               ("Ben Bench", "RB", "NYG", 11.0),
               ("Kip Kicker", "K", "DEN", 8.0),
               ("Steel Defense", "DEF", "PIT", 7.0)]
    proj = dict((name_key(n), {"proj": p, "pos": pos, "team": t,
                               "source": "espn"})
                for n, pos, t, p in entries)
    names = [e[0] for e in entries]
    roster = {"name": "Strip Test", "size": len(names), "players": names,
              "path": ""}
    flex_key = _key("Flex Favorite", "WR")
    bench_key = _key("Ben Bench", "RB")
    cons = {
        flex_key: C.build_rows(
            SOURCES5, {flex_key: {"name": "Flex Favorite", "pos": "WR"}},
            [{"source": "hot-takes", "player": "Flex Favorite",
              "player_key": flex_key, "verdict": "sit",
              "confidence": "high", "quote": "cannot trust the volume",
              "url": "", "fetched": "2026-09-01"}],
            {"engine": {flex_key: "start"},
             "espn-proj": {flex_key: "start"}}, DEMAND)[0],
    }
    out = lineup.lineup_report(LEAGUE, roster, 1, proj, consensus=cons,
                               color=False)
    check("Start Flex Favorite over Ben Bench" in out,
          "the planted flex contest produces its verdict")
    check("ENGINE start" in out and "Hot Takes Weekly sit (high" in out,
          "strip shows one line per voice with confidence and quote")
    check(re.search(r"Your model says START - \d+% - top-weighted source "
                    r"AGREES", out),
          "'Your model says' line with the top-source verdict (branding)")
    check(bench_key not in cons and "Ben Bench:" not in out,
          "no strip for the bench player - silence is normal, not degraded")

    out_none = lineup.lineup_report(LEAGUE, roster, 1, proj, consensus=None,
                                    color=False)
    check("Your model says" not in out_none,
          "no consensus data, no strip - report unchanged otherwise")


# --- 7. digest room section --------------------------------------------------

def _cons_fixture(creator_enabled=True, calls_count=0, rows=None,
                  close_keys=None):
    return {"week": 3, "league": "test-cons", "sources": SOURCES5,
            "rows": rows or [], "close_keys": close_keys or [],
            "notes": [], "creator_enabled": creator_enabled,
            "calls_count": calls_count}


def test_room_section():
    print("\n[7] digest - YOUR MODEL agreement matrix")
    k = _key("Alpha Back", "RB")
    universe = {k: {"name": "Alpha Back", "pos": "RB"}}
    calls = [{"source": "hot-takes", "player": "Alpha Back",
              "player_key": k, "verdict": "sit", "confidence": "high",
              "quote": "fade", "url": "", "fetched": "2026-09-01"}]
    feed = {"engine": {k: "start"}, "espn-proj": {k: "start"}}
    rows = C.build_rows(SOURCES5, universe, calls, feed, DEMAND)
    cons = _cons_fixture(calls_count=1, rows=rows, close_keys=[k])
    html = digest.render_room(cons, 3, {"weeks": [], "rows": []}, [])
    check("YOUR MODEL - source agreement matrix" in html,
          "section title (branding: the user's proprietary model)")
    # v3 (engine/ui.py): the phrase is a label over the system's verdict
    # chip, which carries the word and the pct in its own spans
    check("Your model says" in html and ">START</span>" in html
          and re.search(r'wr-chip-pct">\d+%', html),
          "weighted chip phrased 'Your model says START - NN%'")
    check("wr-chip-start" in html and "wr-chip-sit" in html,
          "start and sit verdict chips rendered")
    check("&mdash;" in html, "a silent source renders an em-dash cell, "
                             "never a guessed verdict")
    check("./sources.sh" in html, "manage-sources footer present")
    check("engine.calls" in html and "--week 3" in html,
          "ingest command in the footer")
    check("DEGRADED" not in html,
          "no degradation banner when calls exist this week")
    # the xmlns on the chips' inline <svg> is a string constant no user
    # agent resolves - the only http-shaped text a v3 section may carry
    check("http" not in html.lower().replace("hot-takes", "")
          .replace("http://www.w3.org/2000/svg", ""),
          "no URLs leak into the page (provenance stays in the yaml)")

    # empty week + enabled creators -> the one honest degradation banner
    html2 = digest.render_room(_cons_fixture(calls_count=0), 3,
                               {"weeks": [], "rows": []}, [])
    check("DEGRADED - no creator calls ingested this week" in html2
          and "python -m engine.calls --week 3" in html2,
          "banner names the exact ingest command")
    html3 = digest.render_room(
        _cons_fixture(creator_enabled=False, calls_count=0), 3,
        {"weeks": [], "rows": []}, [])
    check("DEGRADED" not in html3,
          "no banner when only feed sources are enabled (nothing missing)")

    # highlight: top source flipped to the creator saying sit
    hot_sources = [dict(s) for s in SOURCES5]
    hot_sources[1]["weight"] = 50
    hot_rows = C.build_rows(hot_sources, universe, calls, feed, DEMAND)
    cons_hot = _cons_fixture(calls_count=1, rows=hot_rows)
    cons_hot["sources"] = hot_sources
    html4 = digest.render_room(cons_hot, 3, {"weeks": [], "rows": []}, [])
    check("class=\"dg-hot\"" in html4 and "top-weighted" in html4,
          "row highlighted when the heaviest voice differs from the engine")

    # scoreboard: hidden at 1 scored week, table at 2
    sb1 = {"weeks": [1], "rows": [{"source": "engine", "hits": 1,
                                   "scored": 2, "weeks": 1, "pct": 50.0}]}
    html5 = digest.render_room(cons, 3, sb1, [])
    check("Source scoreboard" not in html5 and "one week is noise" in html5,
          "one scored week: honest note, no hit-rate table")
    sb2 = {"weeks": [1, 2], "rows": [{"source": "engine", "hits": 3,
                                      "scored": 4, "weeks": 2, "pct": 75.0}]}
    html6 = digest.render_room(cons, 3, sb2, [])
    check("Source scoreboard" in html6 and "75%" in html6,
          "two scored weeks: scoreboard table with hit rates")


# --- 8. registry scenarios against a fixture league --------------------------

FX_LEAGUE_ID = "fx-cons"

FX_LEAGUE_DATA = {
    "id": FX_LEAGUE_ID, "name": "Fixture Consensus League", "teams": 10,
    "my_slot": 1, "waiver_mode": "faab",
    "roster_spots": ["QB", "WR", "WR", "RB", "RB", "TE", "W/R/T", "W/R/T",
                     "K", "DEF"] + ["BN"] * 6,
    "rounds": 16,
    "rankings_csv": "data/rankings.csv",
    "scoring": {"reception": 1, "passing_td": 4, "rushing_td": 6,
                "receiving_td": 6, "interception": -1, "fumble_lost": -2,
                "passing_yards_per_point": 25, "rushing_yards_per_point": 10,
                "receiving_yards_per_point": 10},
}

_FEEDS_YAML = """- id: engine
  name: War Room Engine
  type: feed
  handle: engine
  enabled: true
  weight: 40
- id: espn-proj
  name: ESPN Projections
  type: feed
  handle: espn-proj
  enabled: true
  weight: 20
- id: sleeper-proj
  name: Sleeper Projections
  type: feed
  handle: sleeper-proj
  enabled: true
  weight: 15
- id: chen-tiers
  name: Boris Chen Tiers
  type: feed
  handle: chen-tiers
  enabled: true
  weight: 10
"""

# Registry A: the built-in feeds PLUS two enabled creator sources.
REGISTRY_WITH_CREATORS = "sources:\n" + _FEEDS_YAML + """- id: fx-creator-a
  name: Fixture Creator A
  type: youtube
  handle: https://www.youtube.com/@fixture-creator-a
  enabled: true
  weight: 25
- id: fx-creator-b
  name: Fixture Creator B
  type: rss
  handle: https://example.invalid/fixture.rss
  enabled: true
  weight: 12
- id: fx-creator-off
  name: Fixture Creator (disabled)
  type: youtube
  handle: https://www.youtube.com/@fixture-creator-off
  enabled: false
  weight: 30
"""

# Registry B: only the built-in feed voices - no creator anywhere.
REGISTRY_FEEDS_ONLY = "sources:\n" + _FEEDS_YAML


def _fx_root():
    """Throwaway project root: leagues/, rankings CSV, roster, registries."""
    import yaml
    root = tempfile.mkdtemp(prefix="consensus-root-")
    os.makedirs(os.path.join(root, "leagues"))
    os.makedirs(os.path.join(root, "data", "rosters"))
    os.makedirs(os.path.join(root, "calls-with"))
    os.makedirs(os.path.join(root, "calls-empty"))
    shutil.copy(os.path.join(HERE, "data", "rankings.csv"),
                os.path.join(root, "data", "rankings.csv"))
    with open(os.path.join(root, "leagues",
                           "%s.yaml" % FX_LEAGUE_ID), "w") as fh:
        yaml.safe_dump(FX_LEAGUE_DATA, fh, default_flow_style=False,
                       sort_keys=False)
    with open(os.path.join(root, "registry-creators.yaml"), "w") as fh:
        fh.write(REGISTRY_WITH_CREATORS)
    with open(os.path.join(root, "registry-feeds.yaml"), "w") as fh:
        fh.write(REGISTRY_FEEDS_ONLY)
    return root


def _fx_roster(root):
    """Three real pool names (one QB/RB/WR) written as the fixture roster.

    WHICH players is never asserted - real names are used only so the live
    projection feeds and the fuzzy matcher can resolve them. They come from
    the shipped rankings pool, not from any roster file.
    """
    from engine.models import load_players
    by = {}
    for p in load_players(os.path.join(root, "data", "rankings.csv")):
        by.setdefault(p.pos, []).append(p)
    if any(not by.get(pos) for pos in ("QB", "RB", "WR")):
        return None
    picks = [by["QB"][0], by["RB"][0], by["WR"][0]]
    path = os.path.join(root, "data", "rosters", "%s.yaml" % FX_LEAGUE_ID)
    with open(path, "w") as fh:
        fh.write("league: %s\nname: \"Fixture Roster\"\nsize: 16\n"
                 "players:\n" % FX_LEAGUE_ID)
        for p in picks:
            fh.write("  - %s\n" % p.name)
    return picks


def _write_calls(path, target, source_id="fx-creator-a"):
    """One creator call on a rostered player, plus one from an alien source."""
    import yaml
    doc = {"week": 1, "calls": [
        {"source": source_id, "player": target.name,
         "player_key": target.key, "verdict": "sit", "confidence": "high",
         "quote": "fixture fade - planted by the test", "url": "",
         "fetched": "2026-09-01"},
        {"source": "fx-not-in-any-registry", "player": target.name,
         "player_key": target.key, "verdict": "start", "confidence": "high",
         "quote": "should be ignored", "url": "", "fetched": "2026-09-01"},
    ]}
    with open(path, "w") as fh:
        yaml.safe_dump(doc, fh, default_flow_style=False, sort_keys=False)


def _redirect_for_cli(root):
    """(restore-callable) point the CLI's module constants at the fixture."""
    from engine import calls as calls_mod
    from engine import lineup as lineup_mod
    from engine import sources as sources_mod
    saved = (C.HERE, lineup_mod.ROSTER_DIR, sources_mod.SOURCES_PATH,
             calls_mod.CALLS_DIR)

    def restore():
        (C.HERE, lineup_mod.ROSTER_DIR, sources_mod.SOURCES_PATH,
         calls_mod.CALLS_DIR) = saved
    return restore, lineup_mod, sources_mod, calls_mod


def test_registry_scenarios():
    print("\n[8] registry scenarios - creator sources present, then absent")
    real_reg = os.path.join(HERE, "data", "sources.yaml")
    real_led = os.path.join(HERE, "data", "source_ledger.jsonl")
    reg_before = (open(real_reg, "rb").read()
                  if os.path.exists(real_reg) else None)
    led_before = (open(real_led, "rb").read()
                  if os.path.exists(real_led) else None)

    root = _fx_root()
    try:
        picks = _fx_roster(root)
        if not picks:
            check(False, "rankings pool too thin to build a fixture roster")
            return
        target = picks[1]                       # the RB gets the creator call
        creators_reg = os.path.join(root, "registry-creators.yaml")
        feeds_reg = os.path.join(root, "registry-feeds.yaml")
        roster_dir = os.path.join(root, "data", "rosters")
        calls_with = os.path.join(root, "calls-with")
        calls_empty = os.path.join(root, "calls-empty")
        _write_calls(os.path.join(calls_with, "week-1.yaml"), target)
        creators_before = open(creators_reg, "rb").read()

        real_here = C.HERE
        C.HERE = root                            # leagues/ + rankings CSV
        try:
            # --- A. a registry WITH creator sources -----------------------
            cons = C.build_consensus(FX_LEAGUE_ID, 1, roster_dir=roster_dir,
                                     calls_dir=calls_with,
                                     registry_path=creators_reg)
            ids = [s.get("id") for s in cons["sources"]]
            check(cons["creator_enabled"],
                  "creator_enabled True when the registry enables a "
                  "non-feed source")
            check("fx-creator-a" in ids and "fx-creator-b" in ids,
                  "both enabled creators are in the source list (got %s)"
                  % ids)
            check("fx-creator-off" not in ids,
                  "a DISABLED creator never joins the room")
            check(ids[0] == "engine" and ids[1] == "fx-creator-a",
                  "sources ordered by weight desc (engine 40, creator 25)")
            check(cons["calls_count"] == 1,
                  "exactly the one call from an enabled source counts "
                  "(got %d)" % cons["calls_count"])
            check(any("from disabled/unknown sources ignored" in n
                      for n in cons["notes"]),
                  "the alien source's call is reported as ignored, not "
                  "silently dropped (notes: %s)" % cons["notes"])
            check(len(cons["rows"]) == 3,
                  "one row per resolved roster player (3 fixture names, "
                  "got %d)" % len(cons["rows"]))
            engine_rows = [r for r in cons["rows"]
                           if any(v["source"] == "engine" for v in r["votes"])]
            check(len(engine_rows) == len(cons["rows"]),
                  "the engine voices an opinion on every rostered player")

            row = next((r for r in cons["rows"]
                        if r["player_key"] == target.key), None)
            check(row is not None,
                  "the called player has a row (key %s)" % target.key)
            if row is not None:
                cv = next((v for v in row["votes"]
                           if v["source"] == "fx-creator-a"), None)
                check(cv is not None and cv["verdict"] == "sit",
                      "the creator's planted SIT lands as a vote on that row")
                check(cv is not None and "planted by the test" in cv["quote"],
                      "the creator's quote rides along as evidence")
                check(all(v["source"] != "fx-not-in-any-registry"
                          for v in row["votes"]),
                      "the alien source casts no vote")

            # --- A2. creators enabled but NO calls this week ---------------
            empty = C.build_consensus(FX_LEAGUE_ID, 1, roster_dir=roster_dir,
                                      calls_dir=calls_empty,
                                      registry_path=creators_reg)
            check(empty["creator_enabled"] and empty["calls_count"] == 0,
                  "creators enabled with an empty week: the degradation "
                  "precondition")
            check(len(empty["rows"]) == 3,
                  "feed voices still produce rows with no creator calls")
            check(all(all(v["source"] not in ("fx-creator-a", "fx-creator-b")
                          for v in r["votes"]) for r in empty["rows"]),
                  "a silent creator casts NO vote - absence, never a guess")

            # --- B. a registry with ONLY feed sources ---------------------
            feeds = C.build_consensus(FX_LEAGUE_ID, 1, roster_dir=roster_dir,
                                      calls_dir=calls_with,
                                      registry_path=feeds_reg)
            check(not feeds["creator_enabled"],
                  "creator_enabled False when only feed sources are enabled")
            check(len(feeds["sources"]) == 4,
                  "the four built-in feed voices (got %d)"
                  % len(feeds["sources"]))
            check(feeds["calls_count"] == 0,
                  "creator calls are ignored when no creator is enabled")
            check(any("from disabled/unknown sources ignored" in n
                      for n in feeds["notes"]),
                  "and the drop is reported in the notes")
            check(len(feeds["rows"]) == 3,
                  "feed-only rows still cover every rostered player")

            # --- CLI on both registries -----------------------------------
            restore, lineup_mod, sources_mod, calls_mod = _redirect_for_cli(root)
            try:
                lineup_mod.ROSTER_DIR = roster_dir
                calls_mod.CALLS_DIR = calls_empty
                sources_mod.SOURCES_PATH = creators_reg
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = C.main(["--league", FX_LEAGUE_ID, "--week", "1"])
                out = buf.getvalue()
                check(rc == 0 and "CONSENSUS - %s week 1" % FX_LEAGUE_ID in out,
                      "CLI exits 0 with the header")
                check("Your model says" in out,
                      "CLI prints the weighted strip")
                check("DEGRADED: no creator calls ingested this week" in out
                      and "python -m engine.calls --week 1" in out,
                      "creators enabled + empty week: CLI names the exact "
                      "ingest command")

                sources_mod.SOURCES_PATH = feeds_reg
                buf2 = io.StringIO()
                with contextlib.redirect_stdout(buf2):
                    rc2 = C.main(["--league", FX_LEAGUE_ID, "--week", "1"])
                out2 = buf2.getvalue()
                check(rc2 == 0 and "DEGRADED" not in out2,
                      "feed-only registry: nothing is missing, so no "
                      "degradation banner")
                check("Fixture Creator A" not in out2,
                      "and no creator is named in a feed-only run")
            finally:
                restore()
        finally:
            C.HERE = real_here

        check(open(creators_reg, "rb").read() == creators_before,
              "the fixture registry is byte-identical after every read "
              "(consensus never rewrites a registry)")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    reg_after = (open(real_reg, "rb").read()
                 if os.path.exists(real_reg) else None)
    led_after = (open(real_led, "rb").read()
                 if os.path.exists(real_led) else None)
    check(reg_after == reg_before,
          "the user's data/sources.yaml is untouched by the whole suite")
    check(led_after == led_before,
          "production ledger untouched (only the digest records)")


def main():
    print("=" * 74)
    print("SOURCE CONSENSUS TEST")
    print("=" * 74)

    test_math()
    test_agreement()
    test_build_rows()
    test_top_weighted_flag()
    test_ledger()
    test_lineup_strip()
    test_room_section()
    test_registry_scenarios()

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
