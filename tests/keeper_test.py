#!/usr/bin/env python3
"""Acceptance test: keeper calculator (engine/keeper.py).

A synthetic pool with a known projection/ADP shape proves the verdict math:
a late-round stud is an obvious KEEP with a big margin, a fair-priced mid
player is marginal, an overpriced player is a THROW BACK. The CLI is then run
against the real yahoo-main pool end to end (single and --list modes),
including the honest-caveat line and loud failure on unknown names.

    .venv/bin/python tests/keeper_test.py
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.keeper import (MARGINAL_BAND, evaluate, expected_best,  # noqa: E402
                           forfeited_overall, load_keepers, resolve_slot)
from engine.models import (DraftState, LeagueConfig, Player,   # noqa: E402
                           team_on_clock)
from engine.recommend import (effective_adp, replacement_levels,  # noqa: E402
                              vbd)

PY = sys.executable
FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- synthetic pool ---------------------------------------------------------
ROSTER = ["QB", "WR", "WR", "RB", "RB", "TE", "W/R/T", "W/R/T", "K", "DEF",
          "BN", "BN", "BN", "BN", "BN", "BN"]

CURVES = {           # count, top projection, per-player dropoff
    "QB": (25, 380.0, 6.0),
    "RB": (55, 350.0, 4.0),
    "WR": (55, 340.0, 3.5),
    "TE": (25, 250.0, 5.0),
    "K": (12, 140.0, 2.0),
    "DEF": (12, 130.0, 2.0),
}


def build_synthetic(my_slot=4, pool_cap=None):
    """10-team full-PPR league over a pool whose ADP order IS its value (VBD)
    order - an efficient market - so expected-best at any pick is exactly the
    next value tick down and every verdict is predictable by construction."""
    league = LeagueConfig({"id": "synthetic", "name": "Synthetic", "teams": 10,
                           "my_slot": my_slot, "roster_spots": ROSTER,
                           "rounds": 16, "scoring": {"reception": 1}})
    players = []
    for pos, (count, top, drop) in CURVES.items():
        for i in range(count):
            players.append(Player(rank=1, name="%s Guy %02d" % (pos, i + 1),
                                  pos=pos, team="FA", adp_stdev=2.0,
                                  proj_points=top - drop * i))
    # Replacement levels depend only on projections and roster shape, so
    # they can be computed once and used to lay the market out by value.
    repl = replacement_levels(DraftState(league, players))
    players.sort(key=lambda p: -vbd(p, repl))
    if pool_cap:
        players = players[:pool_cap]
    for i, p in enumerate(players, start=1):
        p.rank = i
        p.adp = float(i)
    return DraftState(league, players)


def by_adp(state, overall):
    for p in state.players:
        if int(p.adp) == overall:
            return p
    raise AssertionError("no synthetic player at ADP %d" % overall)


# --- 1. snake math ----------------------------------------------------------
def test_snake_math():
    print("\n1. FORFEITED-PICK SNAKE MATH")
    ok = True
    for teams in (10, 12):
        for slot in (1, 4, teams):
            for rnd in range(1, 17):
                overall = forfeited_overall(rnd, slot, teams)
                if team_on_clock(overall, teams) != slot:
                    ok = False
    check(ok, "forfeited_overall lands on my slot for every round/slot/size")
    check(forfeited_overall(12, 4, 10) == 117,
          "round 12 from slot 4 of 10 = overall 117 (even-round reversal)")


# --- 2. synthetic verdicts --------------------------------------------------
def test_synthetic_verdicts():
    print("\n2. SYNTHETIC POOL VERDICTS")
    state = build_synthetic(my_slot=4)
    repl = replacement_levels(state)
    check(bool(repl), "replacement levels computed for synthetic pool")

    # Late-round stud: top-8 overall value offered at a round-12 price.
    stud = by_adp(state, 8)
    v = evaluate(state, stud, 12, 4, repl=repl)
    check(v.keep and v.tag() == "KEEP", "late-round stud verdict is KEEP")
    check(v.margin > 50.0,
          "stud margin is decisive (%.1f pts > 50)" % v.margin)
    check(v.comparison is not None and
          effective_adp(v.comparison) >= v.overall,
          "stud comparison player's ADP is at/after the forfeited pick")
    check(any("surplus" in r for r in v.reasons),
          "stud reasons name the rounds of price surplus")

    # Fair price: his ADP sits exactly on the forfeited pick (round 5 from
    # slot 4 of 10 = overall 44), so the alternative is the next tick down.
    fair = by_adp(state, forfeited_overall(5, 4, 10))
    v = evaluate(state, fair, 5, 4, repl=repl)
    check(abs(v.margin) < MARGINAL_BAND,
          "fair-priced mid player is marginal (%.1f pts)" % v.margin)
    check(v.marginal and any("coin flip" in r for r in v.reasons),
          "marginal verdict says coin flip out loud")
    check(any("still be there" in r for r in v.reasons),
          "own-ADP-past-the-pick warning fires on the fair-priced player")

    # Overpriced: an ADP-60 player offered at a round-3 (overall 24) price.
    dud = by_adp(state, 60)
    v = evaluate(state, dud, 3, 4, repl=repl)
    check((not v.keep) and v.tag() == "THROW BACK",
          "overpriced player verdict is THROW BACK")
    check(v.margin < -20.0,
          "overpriced margin is decisively negative (%.1f pts)" % v.margin)

    # Sanity: margin equals VBD(keeper) - VBD(comparison) by construction.
    comp = expected_best(state, v.overall, repl, exclude_key=dud.key)
    check(abs(v.margin - (vbd(dud, repl) - vbd(comp, repl))) < 1e-9,
          "margin is exactly VBD(keeper) - VBD(expected best)")


# --- 3. edges ---------------------------------------------------------------
def test_edges():
    print("\n3. EDGES AND LOUD FAILURES")
    # Pool truncated to 150 players: a round-16 pick (overall 157) has no
    # candidate ADPs left, so the forfeited pick prices as replacement level.
    state = build_synthetic(my_slot=4, pool_cap=150)
    repl = replacement_levels(state)
    stud = by_adp(state, 8)
    v = evaluate(state, stud, 16, 4, repl=repl)
    check(v.comparison is None and any("replacement level" in r
                                       for r in v.reasons),
          "empty ADP tail prices the forfeited pick at replacement level")

    state = build_synthetic()
    try:
        evaluate(state, by_adp(state, 8), 99, 4)
        check(False, "cost round outside 1-16 raises")
    except ValueError:
        check(True, "cost round outside 1-16 raises")

    ghost = Player(rank=999, name="No Projection Guy", pos="RB", adp=200.0)
    try:
        evaluate(state, ghost, 10, 4)
        check(False, "keeper without a projection raises, never guesses")
    except ValueError as exc:
        check("projection" in str(exc),
              "keeper without a projection raises, never guesses")

    slot, assumed = resolve_slot(LeagueConfig({"teams": 10}))
    check(slot == 5 and assumed,
          "unset my_slot assumes mid-slot 5 of 10 and flags it as assumed")
    slot, assumed = resolve_slot(LeagueConfig({"teams": 10, "my_slot": 2}))
    check(slot == 2 and not assumed, "configured my_slot is used untouched")
    slot, assumed = resolve_slot(LeagueConfig({"teams": 10, "my_slot": 2}), 7)
    check(slot == 7 and not assumed, "--slot override wins")


# --- 4. keepers.yaml loader -------------------------------------------------
def test_loader():
    print("\n4. KEEPERS.YAML LOADER")
    good = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    good.write("players:\n  - name: Jahmyr Gibbs\n    cost_round: 2\n"
               "  - name: Puka Nacua\n    cost_round: 5\n")
    good.close()
    rows = load_keepers(good.name)
    check(rows == [{"name": "Jahmyr Gibbs", "cost_round": 2},
                   {"name": "Puka Nacua", "cost_round": 5}],
          "well-formed keepers.yaml parses to name + int cost_round")
    os.unlink(good.name)

    bad = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    bad.write("players:\n  - name: Puka Nacua\n  - cost_round: 3\n")
    bad.close()
    try:
        load_keepers(bad.name)
        check(False, "malformed entries fail loudly, never skip silently")
    except ValueError as exc:
        check("malformed" in str(exc),
              "malformed entries fail loudly, never skip silently")
    os.unlink(bad.name)

    shipped = load_keepers(os.path.join(HERE, "data", "keepers.yaml"))
    check(shipped == [], "shipped data/keepers.yaml is a valid empty sheet")


# --- 5. CLI against the real pool -------------------------------------------
def run_cli(*args):
    proc = subprocess.run([PY, "-m", "engine.keeper"] + list(args),
                          cwd=HERE, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def test_cli():
    print("\n5. CLI ON THE REAL YAHOO-MAIN POOL")
    rc, out = run_cli("Jahmyr Gibbs", "--cost-round", "10",
                      "--league", "yahoo-main")
    check(rc == 0, "single-player run exits 0")
    check("KEEP" in out and "THROW BACK" not in out,
          "a top pick at a round-10 price is an obvious KEEP")
    check("margin +" in out, "positive margin printed")
    check("RUNBOOK B2" in out, "honest caveat cites RUNBOOK B2")
    check("expected best there instead" in out,
          "comparison player is named in the reasons")

    rc, out = run_cli("Jahmyr Gibbs", "--cost-round", "1",
                      "--league", "yahoo-main")
    m = re.search(r"margin ([+-]\d+\.\d+) pts", out)
    check(rc == 0 and m and abs(float(m.group(1))) < 25.0,
          "the 1.01 at a round-1 price is no bargain (margin %s)"
          % (m.group(1) if m else "?"))
    check("still be there" in out,
          "own-ADP warning fires when the keeper would be draftable anyway")

    sheet = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    sheet.write("players:\n  - name: Jahmyr Gibbs\n    cost_round: 8\n"
                "  - name: Jared Goff\n    cost_round: 2\n")
    sheet.close()
    rc, out = run_cli("--list", "--keepers", sheet.name,
                      "--league", "yahoo-main")
    os.unlink(sheet.name)
    check(rc == 0, "--list run exits 0")
    check("Jahmyr Gibbs" in out and "Goff" in out,
          "--list prints a verdict per keeper")
    check("KEEP" in out and "THROW BACK" in out,
          "--list separates the bargain from the reach")
    check(out.count("RUNBOOK B2") == 1, "caveat printed once per sheet")

    rc, out = run_cli("Zzyzx Nobody", "--cost-round", "5")
    check(rc == 1 and "no player in the pool matches" in out,
          "unknown player fails loudly with exit 1")

    rc, out = run_cli("--list", "--keepers", os.path.join(
        HERE, "data", "keepers.yaml"))
    check(rc == 1 and "no keepers listed" in out,
          "empty shipped sheet explains the format and exits 1")


def main():
    print("KEEPER CALCULATOR ACCEPTANCE TEST")
    test_snake_math()
    test_synthetic_verdicts()
    test_edges()
    test_loader()
    test_cli()
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES else
                    "%d FAILURE(S):\n  %s" % (len(FAILURES),
                                              "\n  ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
