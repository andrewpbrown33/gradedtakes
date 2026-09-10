#!/usr/bin/env python3
"""Acceptance test: rival-tendency miner (engine/tendencies.py).

Builds a synthetic 3-season history with two planted tells - an RB hoarder at
slot 3 (who also reaches ~8 picks ahead of ADP) and an early-QB manager at
slot 7 - and proves the miner finds both and nobody else, that the emitted
yaml round-trips through Intel.load + resolve, that the user's own my_calls
file still wins when merged after it, and that a mined read actually shifts
survival odds for the right position.

    .venv/bin/python tests/tendencies_test.py
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.ingest import Matcher                            # noqa: E402
from engine.intel import Intel                               # noqa: E402
from engine.models import (DraftState, LeagueConfig,         # noqa: E402
                           load_players, team_on_clock)
from engine.recommend import survival_odds                   # noqa: E402
from engine.tendencies import Tendencies                     # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- synthetic history -----------------------------------------------------
TEAMS = 10
ROUNDS = 15
HOARDER = 3     # RB rounds 1-6, every season, and reaches ~8 picks past ADP
EARLY_QB = 7    # QB in round 2, every season


def script(slot):
    """Position sequence (rounds 1..15) for one manager."""
    if slot == HOARDER:
        return (["RB"] * 6 +
                ["WR", "WR", "TE", "QB", "WR", "WR", "RB", "K", "DEF"])
    if slot == EARLY_QB:
        return ["WR", "QB", "RB", "WR", "RB", "WR", "TE", "RB",
                "WR", "WR", "RB", "QB", "WR", "K", "DEF"]
    # Generic room: RB/WR alternating, QB round 6-8, TE round 7-8, K/DEF last.
    pos = ["RB" if (slot + r) % 2 == 0 else "WR" for r in range(ROUNDS)]
    qb_rnd = 6 + (slot % 3)
    te_rnd = 7 + (slot % 2)
    if te_rnd == qb_rnd:
        te_rnd += 1
    pos[qb_rnd - 1] = "QB"
    pos[te_rnd - 1] = "TE"
    pos[13] = "K"
    pos[14] = "DEF"
    return pos


def build_history():
    """Three seasons of full 10-team snake drafts, positions per script().

    ADP tracks the pick number within +/-1 for everyone except the hoarder,
    whose targets always go ~8 picks later by market - a habitual reacher.
    Season 3 uses the alternate input key names (team_slot_or_id,
    adp_at_time) to exercise the loader contract.
    """
    seasons = []
    for season_i in range(3):
        picks = []
        for overall in range(1, TEAMS * ROUNDS + 1):
            slot = team_on_clock(overall, TEAMS)
            rnd = (overall - 1) // TEAMS + 1
            pos = script(slot)[rnd - 1]
            if slot == HOARDER:
                adp = overall + 8.0
            else:
                adp = overall + ((overall * 7) % 3) - 1.0
            if overall % 11 == 0 and slot != HOARDER:
                adp = None   # ADP is optional; the miner must shrug this off
            if season_i == 2:
                pick = {"overall": overall, "team_slot_or_id": slot,
                        "position": pos, "adp_at_time": adp}
            else:
                pick = {"overall": overall, "team": slot,
                        "position": pos, "adp": adp}
            picks.append(pick)
        seasons.append(picks)
    return seasons


# --- 1. the miner finds the planted tells ----------------------------------
def test_mining(t):
    print("\n1. MINER FINDS THE PLANTED TENDENCIES")
    check(len(t) == TEAMS, "profiles for all %d managers (got %d)"
          % (TEAMS, len(t)))
    check(all(p["drafts"] == 3 for p in t.profiles.values()),
          "every manager credited with 3 drafts")

    hoard = t.profile(HOARDER)
    check("RB" in hoard["favors_positions"],
          "slot %d flagged as RB hoarder (favors %s)"
          % (HOARDER, hoard["favors_positions"]))
    check("QB" not in hoard["favors_positions"],
          "hoarder (first QB rd %s) not called a QB guy"
          % hoard["earliest"].get("QB"))

    early = t.profile(EARLY_QB)
    check("QB" in early["favors_positions"],
          "slot %d flagged for early QB (favors %s)"
          % (EARLY_QB, early["favors_positions"]))
    check(early["earliest"]["QB"] == 2, "earliest QB round is 2 (got %s)"
          % early["earliest"].get("QB"))

    plain = t.profile(5)
    check("RB" not in plain["favors_positions"] and
          "QB" not in plain["favors_positions"],
          "generic slot 5 gets no RB/QB read (favors %s)"
          % plain["favors_positions"])
    check(plain["earliest"]["QB"] >= 6,
          "generic slot 5 first QB round >= 6 (got %s)"
          % plain["earliest"].get("QB"))

    check(hoard["earliest"]["K"] == 14 and hoard["earliest"]["TE"] == 9,
          "earliest TE/K rounds tracked (TE %s, K %s)"
          % (hoard["earliest"].get("TE"), hoard["earliest"].get("K")))
    check(all(hoard["pos_by_round"][r] == {"RB": 3} for r in range(1, 7)),
          "position-by-round shows RB x3 in every round 1-6")

    check(hoard["reach"] is not None and hoard["reach"] > 5,
          "hoarder's reach ~ +8 picks vs ADP (got %s)" % hoard["reach"])
    check(plain["reach"] is not None and abs(plain["reach"]) < 2,
          "generic slot 5 reach ~ 0 (got %.2f)" % plain["reach"])
    check("mined from 3 drafts" in hoard["note"],
          "note explains itself: %s" % hoard["note"][:70])


# --- 2. yaml round-trip through Intel --------------------------------------
def test_yaml_roundtrip(t, matcher, tmp):
    print("\n2. EMITTED YAML ROUND-TRIPS THROUGH Intel.load + resolve")
    path = os.path.join(tmp, "tendencies.test-league.yaml")
    n = t.emit_yaml(path)
    check(n == TEAMS, "emit_yaml wrote %d manager rows" % n)
    with open(path) as fh:
        text = fh.read()
    check("BEFORE data/my_calls.yaml" in text,
          "file header documents the merge order contract")

    intel = Intel.load(path)
    intel.resolve(matcher)
    check(len(intel.managers) == TEAMS,
          "Intel parsed %d managers" % len(intel.managers))
    check(intel.managers[HOARDER]["positions"] == set(["RB"]),
          "hoarder read survives the round trip (positions %s)"
          % sorted(intel.managers[HOARDER]["positions"]))
    check("QB" in intel.managers[EARLY_QB]["positions"],
          "early-QB read survives the round trip")
    check(intel.managers[HOARDER]["reach"] > 5,
          "reach number survives (%.1f)" % intel.managers[HOARDER]["reach"])
    check("mined" in intel.manager_note(HOARDER),
          "note comes back through manager_note()")
    return intel


# --- 3. the user's own file still wins -------------------------------------
def test_user_wins(t, matcher, tmp):
    print("\n3. MY_CALLS MERGED AFTER THE MINED FILE WINS PER SLOT")
    mined_path = os.path.join(tmp, "tendencies.test-league.yaml")
    user_path = os.path.join(tmp, "my_calls.yaml")
    with open(user_path, "w") as fh:
        fh.write('managers:\n'
                 '  - slot: %d\n'
                 '    name: "Steve"\n'
                 '    favors_positions: ["WR"]\n'
                 '    favors_teams: ["BAL"]\n'
                 '    note: "my own read - actually a WR guy"\n' % HOARDER)

    # Same ordering warroom.py uses: research base, then mined, then my_calls.
    base = Intel.empty()
    base.merge(Intel.load(mined_path), matcher)
    base.merge(Intel.load(user_path), matcher)

    m = base.managers[HOARDER]
    check(m["positions"] == set(["WR"]) and m["name"] == "Steve",
          "user's qualitative read replaced the mined one for slot %d" % HOARDER)
    check("my own read" in m["note"], "user's note wins outright")
    check("QB" in base.managers[EARLY_QB]["positions"],
          "slots the user did not override keep their mined read")


# --- 4. mined reads shift survival odds ------------------------------------
def test_survival_shift(intel):
    print("\n4. MINED READS SHIFT SURVIVAL FOR THE RIGHT POSITIONS")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    league.my_slot = 4
    players = load_players(os.path.join(HERE, league.rankings_csv))
    state = DraftState(league, players)

    # Park a flex-full roster on the hoarder's slot (his snake overalls) so
    # generic roster-need says he does NOT want another RB - then the mined
    # appetite is the only thing that can raise the hazard.
    team3_overalls = [n for n in range(1, state.total_picks() + 1)
                      if state.team_at(n) == HOARDER]
    parked = (state.available("RB")[15:17] + state.available("WR")[20:24] +
              [state.available("TE")[10]])
    for overall, player in zip(team3_overalls, parked):
        state.apply_pick(player, overall=overall)

    from engine.recommend import team_needs_pos
    check(not team_needs_pos(state, HOARDER, "RB"),
          "setup: hoarder's roster no longer needs RB by generic logic")

    rb = state.available("RB")[0]
    qb = state.available("QB")[0]
    check(intel.manager_appetite(HOARDER, rb) == 0.6,
          "manager_appetite bumps the hoarder for an RB (0.6)")
    check(intel.manager_appetite(HOARDER, qb) == 0.0,
          "no appetite bump for a QB from the RB read")
    check(intel.manager_appetite(EARLY_QB, qb) == 0.6,
          "early-QB manager bumps for a QB")

    # My next pick is overall 4; the hoarder picks in between at overall 3.
    s_rb_no = survival_odds(state, rb, intel=None)
    s_rb_yes = survival_odds(state, rb, intel=intel)
    check(0.0 < s_rb_yes < s_rb_no < 1.0,
          "top RB less likely to survive the hoarder (%.3f -> %.3f)"
          % (s_rb_no, s_rb_yes))
    s_qb_no = survival_odds(state, qb, intel=None)
    s_qb_yes = survival_odds(state, qb, intel=intel)
    check(abs(s_qb_yes - s_qb_no) < 1e-9,
          "QB survival untouched by the RB read (%.3f == %.3f)"
          % (s_qb_no, s_qb_yes))


# --- 5. from_saves on the real draft ---------------------------------------
def test_from_saves():
    print("\n5. FROM_SAVES ON THE REAL YAHOO DRAFT SAVE")
    save = os.path.join(HERE, "saves", "yahoo-main-20260829.json")
    t = Tendencies.from_saves([save])
    check(t.league == "yahoo-main", "league id read from the save (%s)" % t.league)
    check(len(t) == 10, "all 10 slots profiled from 33 picks (got %d)" % len(t))
    total = sum(p["picks"] for p in t.profiles.values())
    check(total == 33, "all 33 picks attributed (got %d)" % total)
    slot4 = t.profile(4)
    check(slot4 is not None and slot4["pos_by_round"],
          "positions parsed off player_key suffixes (slot 4 rounds: %s)"
          % sorted(slot4["pos_by_round"]) if slot4 else "no profile")
    tmp = tempfile.mkdtemp(prefix="tendencies-save-")
    try:
        n = t.emit_yaml(os.path.join(tmp, "tendencies.yahoo-main.yaml"))
        check(n == 10, "real-save profiles emit cleanly (%d rows)" % n)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("      " + t.summary().replace("\n", "\n      "))


def main():
    print("=" * 74)
    print("TENDENCY MINER - rival-read acceptance test")
    print("=" * 74)

    seasons = build_history()
    t = Tendencies(seasons, league="test-league")
    players = load_players(os.path.join(HERE, "data", "rankings.csv"))
    matcher = Matcher(players)

    tmp = tempfile.mkdtemp(prefix="tendencies-test-")
    try:
        test_mining(t)
        intel = test_yaml_roundtrip(t, matcher, tmp)
        test_user_wins(t, matcher, tmp)
        test_survival_shift(intel)
        test_from_saves()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
