#!/usr/bin/env python3
"""Acceptance test: the on-clock strip (engine/strip.py).

Renders the strip from the REAL 33-pick Yahoo draft save (mid round 4,
my_slot 4) and proves the card carries the same answer the terminal engine
gives: the top recommendation by name, its survival number, my-next-pick
distance, and the roster meter counted against this league's demand. Then
renders the no-slot state and proves it degrades to "waiting for draft"
instead of guessing.

    .venv/bin/python tests/strip_test.py
"""

import html
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import state as save_state                       # noqa: E402
from engine import strip                                     # noqa: E402
from engine.exposure import Exposure                         # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.intel import Intel                               # noqa: E402
from engine.models import (DraftState, LeagueConfig,         # noqa: E402
                           load_players)
from engine.recommend import pct, recommend                  # noqa: E402
from engine.strategy import StrategyTree                     # noqa: E402

SAVE = os.path.join(HERE, "saves", "yahoo-main-20260829.json")

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def build(slot=4):
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    league.my_slot = slot
    players = load_players(os.path.join(HERE, league.rankings_csv))
    state = DraftState(league, players)
    matcher = Matcher(players)
    tree = StrategyTree.load(os.path.join(HERE, league.strategy_file))
    tree.resolve_names(matcher)
    intel = Intel.load(os.path.join(HERE, "data", "player_intel.yaml"))
    intel.resolve(matcher)
    return state, matcher, tree, intel


# --- 1. real mid-draft save -------------------------------------------------
def test_mid_draft(tmpdir):
    print("\n1. REAL SAVE, MID-DRAFT (saves/yahoo-main-20260829.json)")
    state, matcher, tree, intel = build(slot=4)
    restored = save_state.restore(state, SAVE)
    check(restored == 33, "restored 33 picks (got %d)" % restored)
    check(state.current_pick() == 34, "board sits at pick 34")

    exposure = Exposure.load(matcher, exclude_league_id=state.league.id)
    out = os.path.join(tmpdir, "strip.html")
    path = strip.render(state, tree, intel, exposure, matcher, path=out)
    check(path == out and os.path.exists(out), "wrote the requested path")
    check(not os.path.exists(out + ".tmp"), "no .tmp left behind")

    with open(out) as fh:
        doc = fh.read()

    # The strip must carry the SAME top pick the terminal engine recommends
    # for this exact state - computed here, not hardcoded, so a refreshed
    # ECR/projection cache cannot rot this test.
    recs = recommend(state, tree, top_n=1, intel=intel)
    top = recs[0]
    check(top.player.name in doc,
          "top pick '%s' is on the card" % top.player.name)
    check(pct(top.survival) in doc,
          "survival %s is on the card" % pct(top.survival))
    reason = top.reasons[0] if top.reasons else "best available"
    check(html.escape(reason)[:30] in doc, "top reason is on the card")

    # Roster meter vs league demand. My AUTHENTIC roster after 33 picks is
    # Chase, Rice, Flowers - WR 3, RB 0 (the real crashed-draft save, not
    # the mock). yahoo-main demand (2 RB + 2 WR starters, 2 W/R/T flex,
    # 6 bench) works out to 5 RB / 5 WR / 3 TE / 2 QB per
    # engine.strip.league_demand.
    demand = strip.league_demand(state.league)
    check(demand == {"QB": 2, "RB": 5, "WR": 5, "TE": 3, "K": 1, "DEF": 1},
          "league demand for yahoo-main (got %s)" % demand)
    meter = dict((pos, (have, want))
                 for pos, have, want in strip.roster_meter(state))
    check(meter["RB"] == (0, 5), "meter RB 0/5 (got %s/%s)" % meter["RB"])
    check(meter["WR"] == (3, 5), "meter WR 3/5 (got %s/%s)" % meter["WR"])
    check("0/5</b>RB" in doc, "RB 0/5 rendered on the card")
    check("3/5</b>WR" in doc, "WR 3/5 rendered on the card")
    check("0/3</b>TE" in doc, "TE 0/3 rendered on the card")

    # Glance context: pick 34 now, my next pick is 37 - three away.
    check(state.next_my_pick() == 37, "next my pick is 37")
    check("mine in 3" in doc, "next-pick distance on the card")
    check("PICK 34" in doc, "current pick on the card")

    # Always-glanceable machinery.
    check('http-equiv="refresh" content="3"' in doc, "auto-refresh every 3s")
    check("tabular-nums" in doc, "tabular numerals in the CSS")
    check("<link" not in doc and "<script src" not in doc,
          "self-contained: no external assets")


# --- 2. degraded states -----------------------------------------------------
def test_empty(tmpdir):
    print("\n2. EMPTY / NO-SLOT STATE")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    league.my_slot = None
    players = load_players(os.path.join(HERE, league.rankings_csv))
    state = DraftState(league, players)

    out = os.path.join(tmpdir, "strip-empty.html")
    strip.render(state, path=out)   # no tree/intel/exposure/matcher at all
    with open(out) as fh:
        doc = fh.read()
    check("waiting for draft" in doc, "no slot renders 'waiting for draft'")
    check('http-equiv="refresh" content="3"' in doc,
          "waiting card still auto-refreshes")

    # Same call again: the atomic replace must overwrite in place.
    strip.render(state, path=out)
    check(os.path.exists(out) and not os.path.exists(out + ".tmp"),
          "re-render replaces the file atomically")

    # Default target is strip.html in the project root.
    check(strip.DEFAULT_PATH == os.path.join(HERE, "strip.html"),
          "default path is project-root strip.html")


def main():
    print("=" * 74)
    print("ON-CLOCK STRIP TEST")
    print("=" * 74)
    tmpdir = tempfile.mkdtemp(prefix="strip-test-")

    test_mid_draft(tmpdir)
    test_empty(tmpdir)

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
