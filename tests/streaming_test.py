#!/usr/bin/env python3
"""Acceptance test: DEF/K streaming (engine/streaming.py).

Synthetic fixtures prove the pure pieces - matchup math (low opposing
implied total lifts a DEF, high own total lifts a K, missing lines and byes
degrade honestly), positive-only availability filtering with cross-host DEF
name dedupe, and the horizon planner where a TWO-WEEK HOLD BEATS GREEDY
CHAINING once moves cost points. The humility ledger is exercised entirely
inside a tempdir (LOG_PATH redirected with try/finally, the same discipline
mock_draft.py applies to save_state.SAVE_DIR) and the production ledger is
byte-checked untouched. A live smoke test then builds week 1 boards from
the real cached feeds and runs the CLI with --no-log.

    .venv/bin/python tests/streaming_test.py
"""

import io
import contextlib
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import streaming                                 # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def close(a, b, tol=0.02):
    return abs(a - b) <= tol


# --- synthetic week fixture -------------------------------------------------

PROJ = {
    name_key("Seahawks D/ST"): {"proj": 8.0, "pos": "DEF", "team": "SEA",
                                "source": "espn"},
    name_key("Bears D/ST"): {"proj": 6.0, "pos": "DEF", "team": "CHI",
                             "source": "espn"},
    name_key("Jets D/ST"): {"proj": 9.5, "pos": "DEF", "team": "NYJ",
                            "source": "espn"},          # NYJ on bye
    name_key("Cameron Dicker"): {"proj": 9.0, "pos": "K", "team": "LAC",
                                 "source": "espn"},
    name_key("Cairo Santos"): {"proj": 8.0, "pos": "K", "team": "CHI",
                               "source": "sleeper"},    # CHI has no line
    name_key("Some Receiver"): {"proj": 20.0, "pos": "WR", "team": "SEA",
                                "source": "espn"},      # never a streamer
}
SCHED = {
    "SEA": {"opponent": "CHI", "home": True, "kickoff_iso": "x"},
    "CHI": {"opponent": "SEA", "home": False, "kickoff_iso": "x"},
    "LAC": {"opponent": "DEN", "home": True, "kickoff_iso": "x"},
    "DEN": {"opponent": "LAC", "home": False, "kickoff_iso": "x"},
    # NYJ absent -> bye
}
LINES = {
    "SEA": {"implied_total": 26.5, "game_total": 44.0},
    "LAC": {"implied_total": 27.0, "game_total": 47.0},
    "DEN": {"implied_total": 20.0, "game_total": 47.0},
    # CHI: no line filed
}


def _board():
    return streaming.build_board(1, "ppr", proj=dict(PROJ), sched=SCHED,
                                 lines=LINES)


# --- 1. matchup math --------------------------------------------------------
def test_matchup_math():
    print("\n1. MATCHUP MATH (implied totals drive the adj, byes drop off)")
    board = _board()
    defs = dict((c["key"], c) for c in board["DEF"])
    ks = dict((c["key"], c) for c in board["K"])

    sea = defs.get(name_key("Seahawks D/ST"))
    check(sea is not None and sea["implied"] is None,
          "SEA DEF faces CHI, which has no line -> implied None")
    check(sea is not None and sea["adj"] == 0.0 and sea["note"] == "no line",
          "missing opponent line -> adj 0.0 with 'no line' note, not an error")

    chi = defs.get(name_key("Bears D/ST"))
    check(chi is not None and close(chi["adj"], (22.5 - 26.5) * 0.35),
          "CHI DEF vs SEA implied 26.5 -> negative adj (~-1.40)")
    check(chi is not None and close(chi["score"], 6.0 + chi["adj"]),
          "DEF score = proj + adj")

    check(name_key("Jets D/ST") not in defs,
          "team absent from the schedule (bye) drops off the board")
    check(name_key("Some Receiver") not in defs
          and name_key("Some Receiver") not in ks,
          "non-streaming positions never reach the board")

    dicker = ks.get(name_key("Cameron Dicker"))
    check(dicker is not None and close(dicker["adj"], (27.0 - 22.5) * 0.15),
          "K adj rides the OWN implied total (LAC 27.0 -> ~+0.68)")
    santos = ks.get(name_key("Cairo Santos"))
    check(santos is not None and santos["adj"] == 0.0
          and santos["note"] == "no line",
          "kicker on a line-less game -> adj 0.0, 'no line'")
    check([c["key"] for c in board["DEF"]]
          == sorted(defs, key=lambda k: (-defs[k]["score"], k)),
          "DEF board sorted best score first")
    check(sea is not None and sea["opp"] == "CHI" and sea["home"] is True,
          "opponent and home flag carried for rendering")


# --- 2. availability filtering ----------------------------------------------
def test_availability_filter():
    print("\n2. AVAILABILITY FILTER (positive-only, cross-host DEF names)")
    board = _board()
    roster = {name_key("Seattle Seahawks"), name_key("Ja'Marr Chase"),
              name_key("Cameron Dicker")}
    out = streaming.filter_available(board, roster)
    def_keys = [c["key"] for c in out["DEF"]]
    k_keys = [c["key"] for c in out["K"]]
    check(name_key("Seahawks D/ST") not in def_keys,
          "roster's 'Seattle Seahawks' excludes ESPN's 'Seahawks D/ST' "
          "(nickname token match)")
    check(name_key("Bears D/ST") in def_keys,
          "unlisted defense survives (no information != free agent)")
    check(name_key("Cameron Dicker") not in k_keys
          and name_key("Cairo Santos") in k_keys,
          "exact-key exclusion for kickers")

    wl = {name_key("Bears D/ST")}
    out2 = streaming.filter_available(board, set(), whitelist=wl)
    check([c["key"] for c in out2["DEF"]] == [name_key("Bears D/ST")]
          and out2["K"] == [],
          "host whitelist keeps only host-confirmed free agents")

    out3 = streaming.filter_available(board, set())
    check(len(out3["DEF"]) == len(board["DEF"])
          and len(out3["K"]) == len(board["K"]),
          "empty roster file excludes nothing (banner carries the caveat)")


# --- 3. horizon planning ----------------------------------------------------
def _cand(key, score):
    return {"key": key, "name": key.upper(), "pos": "DEF", "team": "XX",
            "opp": "YY", "home": True, "proj": score, "implied": None,
            "adj": 0.0, "score": score, "note": ""}


def _maps(spec):
    """spec: [(week, {key: score})] -> planner-shaped week_maps."""
    return [(w, dict((k, _cand(k, s)) for k, s in m.items()))
            for w, m in spec]


def test_horizon_planning():
    print("\n3. HORIZON PLANNING (two-week hold beats greedy chaining)")
    maps = _maps([
        (1, {"a def": 8.0, "b def": 8.5}),
        (2, {"a def": 8.0, "b def": 5.0}),
        (3, {"a def": 6.0, "b def": 5.5, "c def": 9.0}),
    ])

    greedy = streaming.greedy_chain(maps, move_cost=1.0)
    check([k for _, k, _ in greedy["path"]] == ["b def", "a def", "c def"],
          "greedy takes each week's top name (B, A, C)")
    check(greedy["gross"] == 25.5 and greedy["moves"] == 3
          and greedy["net"] == 23.5,
          "greedy: 25.5 gross, 3 moves -> 23.5 net after the tax")

    chain = streaming.best_chain(maps, move_cost=1.0)
    check([k for _, k, _ in chain["path"]] == ["a def", "a def", "c def"],
          "optimal chain HOLDS A two weeks, then flips to C")
    check(chain["gross"] == 25.0 and chain["moves"] == 2
          and chain["net"] == 24.0,
          "optimal chain nets 24.0 (25.0 gross, one extra move)")
    check(chain["net"] > greedy["net"],
          "two-week hold beats greedy chaining once moves cost points")

    free = streaming.best_chain(maps, move_cost=0.0)
    check(free["gross"] == greedy["gross"] and free["net"] == 25.5,
          "with free moves the optimal chain matches greedy's gross")

    pricey = streaming.best_chain(maps, move_cost=3.0)
    check([k for _, k, _ in pricey["path"]] == ["a def"] * 3
          and pricey["moves"] == 1,
          "a big move tax collapses the chain into the pure hold (ties "
          "prefer fewer moves)")

    hold = streaming.best_hold(maps)
    check(hold["key"] == "a def" and hold["total"] == 22.0
          and hold["weeks_covered"] == 3,
          "best hold is A at 22.0 across all three weeks")

    plan = streaming.plan_position(maps, move_cost=1.0)
    check(plan["recommendation"] == "chain",
          "planner recommends the chain when its net beats the hold")

    # holding through a bye: present wk1+wk3, absent wk2
    bye_maps = _maps([
        (1, {"d def": 10.0, "a def": 8.0}),
        (2, {"a def": 2.0}),
        (3, {"d def": 10.0, "a def": 6.0}),
    ])
    bhold = streaming.best_hold(bye_maps)
    check(bhold["key"] == "d def" and bhold["total"] == 20.0
          and bhold["per_week"][1][1] is None,
          "hold sums absent weeks as 0.0 and marks them None (bye-honest)")
    bchain = streaming.best_chain(bye_maps, move_cost=1.0)
    check([k for _, k, _ in bchain["path"]] == ["d def"] * 3
          and bchain["moves"] == 1 and bchain["net"] == 20.0,
          "chain may hold THROUGH a bye at 0.0 rather than pay two moves")

    check(streaming.best_hold([(1, {}), (2, {})]) is None
          and streaming.best_chain([(1, {})], 1.0) is None
          and streaming.plan_position([(1, {})], 1.0) is None,
          "empty horizon -> None, never a crash")


# --- 4. humility ledger (tempdir isolation) ---------------------------------
def test_ledger():
    print("\n4. HUMILITY LEDGER (append + summary, isolated in a tempdir)")
    real_path = streaming.LOG_PATH
    before = (os.path.exists(real_path),
              os.path.getsize(real_path) if os.path.exists(real_path) else 0)
    # Redirect LOG_PATH for the whole test: appends on the real path would
    # pollute data/streaming_log.jsonl, the production record of what we
    # recommended before outcomes were known. Same rule as SAVE_DIR.
    tmpdir = tempfile.mkdtemp(prefix="streaming-ledger-")
    streaming.LOG_PATH = os.path.join(tmpdir, "streaming_log.jsonl")
    try:
        e1 = {"ts": "t", "season": 2026, "week": 1, "league": "yahoo-main",
              "pos": "DEF", "pick_key": "bears dst", "score": 7.1,
              "baseline_key": None, "actual": None, "baseline_actual": None}
        p = streaming.log_top_pick(e1)
        check(p == streaming.LOG_PATH and p.startswith(tmpdir),
              "append landed in the tempdir, not production data/")
        streaming.log_top_pick({"ts": "t2", "week": 2, "pos": "DEF",
                                "pick_key": "jets dst",
                                "actual": None, "baseline_actual": None})
        entries = streaming.read_ledger()
        check(len(entries) == 2 and entries[0]["pick_key"] == "bears dst",
              "entries round-trip through the jsonl in order")
        check("no scored weeks yet" in streaming.ledger_summary(entries)
              and "2 pick(s)" in streaming.ledger_summary(entries),
          "summary is honest while no actuals exist")

        streaming.log_top_pick({"week": 3, "pos": "DEF", "pick_key": "x",
                                "actual": 12.0, "baseline_actual": 8.0})
        streaming.log_top_pick({"week": 4, "pos": "DEF", "pick_key": "y",
                                "actual": 3.0, "baseline_actual": 9.0})
        summary = streaming.ledger_summary(streaming.read_ledger())
        check("1/2" in summary and "2 unscored" in summary,
              "backfilled actuals score hits vs the baseline (1/2, 50%)")

        with open(streaming.LOG_PATH, "a") as fh:
            fh.write("{corrupt json\n")
        check(len(streaming.read_ledger()) == 4,
              "a corrupt ledger line is skipped, not fatal")
    finally:
        streaming.LOG_PATH = real_path
    after = (os.path.exists(real_path),
             os.path.getsize(real_path) if os.path.exists(real_path) else 0)
    check(before == after, "production ledger untouched by the test")


# --- 5. live week 1 + CLI smoke ---------------------------------------------
def test_live():
    print("\n5. LIVE WEEK 1 BOARDS + CLI (--no-log; cached feeds ok)")
    try:
        board = streaming.build_board(1, "ppr", quiet=True)
    except Exception as exc:
        check(False, "live build_board failed: %s" % exc)
        return
    check(len(board["DEF"]) >= 25, "week 1: >=25 defenses on the board "
          "(%d)" % len(board["DEF"]))
    check(len(board["K"]) >= 25, "week 1: >=25 kickers on the board "
          "(%d)" % len(board["K"]))
    check(all(c["opp"] for c in board["DEF"] + board["K"]),
          "every candidate carries an opponent from the schedule")
    scores = [c["score"] for c in board["DEF"]]
    check(scores == sorted(scores, reverse=True), "live DEF board sorted")

    real_path = streaming.LOG_PATH
    tmpdir = tempfile.mkdtemp(prefix="streaming-cli-")
    streaming.LOG_PATH = os.path.join(tmpdir, "streaming_log.jsonl")
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = streaming.main(["--league", "yahoo-main", "--week", "1",
                                 "--horizon", "2", "--no-log"])
        out = buf.getvalue()
        check(rc == 0, "CLI exits 0 for yahoo-main week 1 horizon 2")
        check("AVAILABILITY IS BEST-EFFORT" in out
              and "may still be rostered" in out,
              "CLI prints the honest partial-roster banner")
        check("MULTI-WEEK PLAN - DEF" in out
              and "MULTI-WEEK PLAN - K" in out,
              "CLI prints multi-week plans for both positions")
        check("no scored weeks yet" in out or "humility ledger" in out,
              "CLI prints the humility-ledger status")
        check(not os.path.exists(streaming.LOG_PATH),
              "--no-log leaves the ledger unwritten")
    finally:
        streaming.LOG_PATH = real_path


def main():
    print("STREAMING ACCEPTANCE TEST")
    test_matchup_math()
    test_availability_filter()
    test_horizon_planning()
    test_ledger()
    test_live()
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
