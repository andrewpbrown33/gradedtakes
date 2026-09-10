#!/usr/bin/env python3
"""Acceptance test: simulate a full 10-team draft through the real ingest path.

Bots pick by ADP with roster need; my picks come from the recommendation
engine. Every pick is fed in as messy pasted text, in rotating formats, so the
parser and matcher are exercised the way they will be on draft night.

    .venv/bin/python tests/mock_draft.py
"""

import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import state as save_state                      # noqa: E402
from engine.ingest import Matcher, ingest_text, parse_line   # noqa: E402
from engine.intel import Intel                               # noqa: E402
from engine.models import (DraftState, LeagueConfig, fmt_pick,  # noqa: E402
                           load_players)
from engine.recommend import (on_clock_block, recommend,     # noqa: E402
                              run_warning, survival_odds, tier_alerts)
from engine.strategy import StrategyTree                     # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


INTEL = []   # populated by build() so tests can assert on it


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
    INTEL.append(intel)
    state.intel = intel
    return state, matcher, tree


# --- 1. parser -------------------------------------------------------------
def test_parser(state, matcher):
    print("\n1. PARSER AND MATCHER")
    cases = [
        ("Pick 14: CeeDee Lamb", "CeeDee Lamb"),
        ("14. CeeDee Lamb", "CeeDee Lamb"),
        ("Lamb, DAL", "CeeDee Lamb"),
        ("1.05 Puka Nacua", "Puka Nacua"),
        ("(7) Christian McCaffrey RB - SF", "Christian McCaffrey"),
        ("Team 3 selected Bijan Robinson", "Bijan Robinson"),
        ("Jaxon Smith-Njigba WR SEA", "Jaxon Smith-Njigba"),
        ("amon-ra st brown", "Amon-Ra St. Brown"),
        ("A.J. Brown", "A.J. Brown"),
        ("Travis Etienne", "Travis Etienne Jr."),
        ("James Cook", "James Cook III"),
        ("Ravens DEF", "Baltimore Defense"),
        ("Seattle D/ST", "Seattle Defense"),
        ("Jefferson", "Justin Jefferson"),
        ("Bijan Robinsn", "Bijan Robinson"),          # typo
        ("R3 P2 Nico Collins", "Nico Collins"),
    ]
    ok = 0
    for raw, expected in cases:
        parsed = parse_line(raw, state.teams)
        if parsed is None:
            print("      no parse: %r" % raw)
            continue
        m = matcher.match(parsed.name_text, parsed.pos_hint, parsed.team_hint)
        got = m.player.name if m else None
        if got == expected:
            ok += 1
        else:
            print("      %-38r -> %s (wanted %s)" % (raw, got, expected))
    check(ok == len(cases), "parsed %d/%d messy pick formats" % (ok, len(cases)))

    for junk in ("Round 3", "", "   ", "Draft Results", "-----"):
        check(parse_line(junk, state.teams) is None, "ignores noise line %r" % junk)


# --- 2. snake order --------------------------------------------------------
def test_snake(state):
    print("\n2. SNAKE ORDER")
    check(state.team_at(1) == 1 and state.team_at(10) == 10, "round 1 runs 1..10")
    check(state.team_at(11) == 10 and state.team_at(20) == 1, "round 2 reverses")
    check(state.team_at(21) == 1, "round 3 turns back")
    mine = state.my_picks_overall()
    check(mine[:4] == [4, 17, 24, 37], "slot 4 picks at 4, 17, 24, 37 (got %s)"
          % mine[:4])
    check(len(mine) == state.league.rounds, "one pick per round (%d)" % len(mine))


# --- 3. bot draft ----------------------------------------------------------
def bot_choice(state, team, rng):
    """ADP-driven bot with a nudge toward unfilled starting spots."""
    from engine.recommend import team_needs_pos
    pool = sorted(state.available(), key=lambda p: p.rank)[:18]
    rounds_left = state.league.rounds - state.current_round() + 1
    best, best_score = None, -1e9
    for p in pool:
        if p.pos in ("K", "DEF") and rounds_left > 2:
            continue
        score = -p.rank + rng.uniform(0, 6)
        if team_needs_pos(state, team, p.pos):
            score += 14
        counts = state.pos_counts(team)
        if p.pos == "QB" and counts.get("QB", 0) >= 1:
            score -= 40
        if p.pos == "TE" and counts.get("TE", 0) >= 1:
            score -= 30
        if score > best_score:
            best, best_score = p, score
    if best is None:
        best = pool[0] if pool else sorted(state.available(), key=lambda p: p.rank)[0]
    return best


def _surname(p):
    """Last name a human would actually type - suffixes stripped, DEF left whole."""
    if p.pos == "DEF":
        return p.name
    from engine.models import norm_name
    return norm_name(p.name).split()[-1]


FORMATS = [
    lambda p, n, s: "Pick %d: %s" % (n, p.name),
    lambda p, n, s: "%s" % p.name,
    lambda p, n, s: "%s %s - %s" % (p.name, p.pos, p.team),
    lambda p, n, s: "%s, %s" % (_surname(p), p.team),
    lambda p, n, s: "%s %s" % (fmt_pick(n, s.teams), p.name),
    lambda p, n, s: "(%d) %s" % (n, p.name),
]


def test_full_draft(state, matcher, tree, rng):
    print("\n3. FULL 10-TEAM DRAFT THROUGH THE INGEST PATH")
    my_picks_made = []
    alerts_seen = []
    unmatched_total = 0
    block_printed = None

    while not state.is_complete():
        n = state.current_pick()
        team = state.on_the_clock()

        if not state.active_branch:
            bid = tree.choose_branch(state, matcher)
            if bid:
                state.active_branch = bid

        if team == state.my_slot:
            recs = recommend(state, tree, top_n=5, intel=state.intel)
            assert recs, "engine produced no recommendation at pick %d" % n
            if block_printed is None and state.current_round() == 3:
                block_printed = on_clock_block(state, tree,
                                               list(state.pending_alerts),
                                               color=False, intel=state.intel)
            player = recs[0].player
            my_picks_made.append((n, player, recs[0].reason_text()))
        else:
            player = bot_choice(state, team, rng)

        text = FORMATS[n % len(FORMATS)](player, n, state)
        result = ingest_text(text, state, matcher)
        unmatched_total += len(result.unmatched)

        if not result.applied:
            # Parser could not place it; fail loudly rather than silently stall.
            raise AssertionError("pick %d (%s) did not apply from %r"
                                 % (n, player.name, text))

        got_pick, got_player = result.applied[0]
        if got_player.key != player.key:
            raise AssertionError("pick %d round-tripped %s as %s (from %r)"
                                 % (n, player.name, got_player.name, text))

        for a in tree.evaluate(state, matcher):
            state.fired_triggers.append(a.trigger_id)
            alerts_seen.append(a)
            if a.goto and a.auto and a.goto in tree.branches:
                state.active_branch = a.goto

    check(len(state.picks) == state.teams * state.league.rounds,
          "all %d picks applied" % (state.teams * state.league.rounds))
    check(unmatched_total == 0, "no unmatched lines across the whole draft")
    check(len(state.my_roster()) == state.league.rounds,
          "my roster has %d players" % len(state.my_roster()))
    check(len(set(p.key for p in state.my_roster())) == len(state.my_roster()),
          "no duplicate players on my roster")

    counts = state.pos_counts(state.my_slot)
    check(counts.get("QB", 0) >= 1 and counts.get("TE", 0) >= 1,
          "engine filled QB and TE (QB %d, TE %d)"
          % (counts.get("QB", 0), counts.get("TE", 0)))
    check(counts.get("RB", 0) >= 2 and counts.get("WR", 0) >= 2,
          "engine filled RB/WR starters (RB %d, WR %d)"
          % (counts.get("RB", 0), counts.get("WR", 0)))
    check(counts.get("K", 0) == 1 and counts.get("DEF", 0) == 1,
          "exactly one K and one DEF")

    early = [p for n, p, _ in my_picks_made if n <= state.teams * 12]
    check(not any(p.pos in ("K", "DEF") for p in early),
          "no K/DEF taken before the last two rounds")

    check(len(alerts_seen) > 0, "strategy triggers fired during the draft (%d)"
          % len(alerts_seen))
    print("      triggers: %s" % ", ".join(
        sorted(set(a.trigger_id for a in alerts_seen))[:6]))
    print("      my first five picks:")
    for n, p, why in my_picks_made[:5]:
        print("        %-6s %-24s %s" % (fmt_pick(n, state.teams), p.label(), why[:60]))
    return block_printed


# --- 4. tiers, survival, runs ---------------------------------------------
def test_signals(rng):
    print("\n4. TIER / SURVIVAL / RUN SIGNALS")
    state, matcher, tree = build(slot=4)
    state.active_branch = tree.choose_branch(state, matcher)

    for n in range(1, 22):
        p = sorted(state.available(), key=lambda x: x.rank)[0]
        state.apply_pick(p)
    check(len(state.available()) > 0, "board still has players after 21 picks")

    alerts = tier_alerts(state)
    check(isinstance(alerts, list), "tier alerts computed (%d)" % len(alerts))

    top = sorted(state.available(), key=lambda p: p.rank)[0]
    deep = sorted(state.available(), key=lambda p: p.rank)[45]
    s_top = survival_odds(state, top)
    s_deep = survival_odds(state, deep)
    check(0.0 <= s_top <= 1.0 and 0.0 <= s_deep <= 1.0, "survival odds in [0,1]")
    check(s_deep > s_top, "a deeper player is likelier to survive (%.2f > %.2f)"
          % (s_deep, s_top))

    # Force an RB run and confirm the warning fires.
    state2, matcher2, tree2 = build(slot=4)
    for p in [x for x in state2.available("RB")][:4]:
        state2.apply_pick(p)
    warn = run_warning(state2)
    check(warn is not None and "RB" in warn, "RB run warning fires: %s" % warn)

    # position_gone trigger -> pivot flag with a reason. The threshold is read
    # from the strategy file so tuning the config cannot silently break this.
    state3, matcher3, tree3 = build(slot=4)
    state3.active_branch = "C"
    rule = [w for w in tree3.watch if w.get("id") == "early-rb-run"][0]
    need = int(rule["when"]["at_least"])
    for p in [x for x in state3.available("RB")][:need + 1]:
        state3.apply_pick(p)
    fired = tree3.evaluate(state3, matcher3)
    pivots = [a for a in fired if a.goto]
    check(any(a.trigger_id == "early-rb-run" for a in fired),
          "early-rb-run trigger fires after %d+ RBs go" % need)
    check(pivots and pivots[0].goto == "B",
          "pivot points at branch B with reason: %s"
          % (pivots[0].text[:60] if pivots else "none"))


# --- 5. persistence --------------------------------------------------------
def test_persistence(rng):
    print("\n5. CRASH RECOVERY")
    # Redirect SAVE_DIR for the whole test: save() on the real league id
    # would otherwise clobber saves/yahoo-main-<today>.json - the REAL
    # draft save other tests (and draft night) depend on. This once
    # poisoned the strip_test fixture; never write into production saves/.
    import tempfile
    real_save_dir = save_state.SAVE_DIR
    save_state.SAVE_DIR = tempfile.mkdtemp(prefix="mock-draft-saves-")
    try:
        state, matcher, tree = build(slot=4)
        state.active_branch = tree.choose_branch(state, matcher)
        for n in range(1, 34):
            p = bot_choice(state, state.on_the_clock(), rng)
            state.apply_pick(p)
        state.fired_triggers.append("early-rb-run")
        path = save_state.save(state)
        check(os.path.exists(path),
              "snapshot written to %s" % os.path.basename(path))
        check(path.startswith(save_state.SAVE_DIR),
              "snapshot landed in the temp dir, not production saves/")

        fresh, _, _ = build(slot=4)
        n = save_state.restore(fresh, path)
        check(n == len(state.picks), "restored %d/%d picks" % (n, len(state.picks)))
        check(fresh.current_pick() == state.current_pick(),
              "same pick on the clock after restore (%d)" % fresh.current_pick())
        check([p.name for p in fresh.my_roster()] == [p.name for p in state.my_roster()],
              "my roster identical after restore")
        check(fresh.active_branch == state.active_branch, "branch survived restore")
        check(fresh.fired_triggers == state.fired_triggers, "fired triggers survived")

        # undo
        before = fresh.current_pick()
        pick = fresh.undo_last()
        check(pick is not None and fresh.current_pick() == before - 1,
              "undo rolls the board back one pick")
        check(pick.player_key not in fresh.drafted, "undone player is available again")
    finally:
        save_state.SAVE_DIR = real_save_dir


# --- 6. idempotent bulk sync ----------------------------------------------
def test_bulk_sync():
    print("\n6. BULK SYNC IS IDEMPOTENT")
    state, matcher, tree = build(slot=4)
    block = """Round 1
1. Jahmyr Gibbs RB - DET
2. Bijan Robinson RB - ATL
3. Puka Nacua WR - LAR
4. Ja'Marr Chase WR - CIN
5. Jaxon Smith-Njigba WR - SEA
"""
    r1 = ingest_text(block, state, matcher)
    check(len(r1.applied) == 5, "first sync applied 5 picks")
    r2 = ingest_text(block, state, matcher)
    check(len(r2.applied) == 0 and len(r2.duplicates) == 5,
          "re-pasting the same block changes nothing")

    overlap = block + "6. Amon-Ra St. Brown WR - DET\n7. Christian McCaffrey RB - SF\n"
    r3 = ingest_text(overlap, state, matcher)
    check(len(r3.applied) == 2, "overlapping paste applies only the new picks")
    check(state.current_pick() == 8, "board advanced to pick 8")
    names = [state.by_key[state.picks[i].player_key].name for i in range(1, 8)]
    check(names[0] == "Jahmyr Gibbs" and names[6] == "Christian McCaffrey",
          "picks landed in the right order")

    # Rapid-entry forms discovered during the live rehearsal.
    r4 = ingest_text("drake london, cook, jeanty", state, matcher)
    check([p.name for _, p in r4.applied] ==
          ["Drake London", "James Cook III", "Ashton Jeanty"],
          "comma-separated quick entry applies one pick per name")
    r5 = ingest_text("Lamb, DAL", state, matcher)
    check(len(r5.applied) == 1 and r5.applied[0][1].name == "CeeDee Lamb",
          "'Lamb, DAL' still parses as a single pick with a team hint")
    r6 = ingest_text("/var/folders/T/Screenshot 2026-08-23 at 5.44.24 PM.png",
                     state, matcher)
    check(not r6.applied and not r6.unmatched,
          "dragged-in file paths are ignored silently")


def test_intel():
    """The research doc must actually move recommendations, not just sit there."""
    print("\n7. RESEARCH INTEL")
    state, matcher, tree = build(slot=4)
    intel = state.intel
    check(len(intel) >= 30, "loaded %d player theses" % len(intel))
    check(not intel.unresolved,
          "every intel name resolved to a real player%s"
          % ("" if not intel.unresolved else ": " + ", ".join(intel.unresolved)))

    from engine.models import norm_name
    key = lambda nm: matcher.match(nm).player.key
    cmc = intel.for_player(key("Christian McCaffrey"))
    hall = intel.for_player(key("Breece Hall"))
    check(cmc is not None and cmc[0] < -10, "McCaffrey carries a real fade penalty")
    # Hall's magnitude moves with the live research (Aug 29 verdict: +10 -> +4
    # on the groin caveat); the invariant is that he stays a positive buy.
    check(hall is not None and hall[0] > 0, "Breece Hall carries a positive buy bonus")

    # The fade must change the ordering, not merely annotate it.
    with_intel = recommend(state, tree, top_n=12, intel=intel)
    without = recommend(state, tree, top_n=12, intel=None)
    def place(recs, name):
        for i, r in enumerate(recs):
            if r.player.name == name:
                return i
        return 99
    check(place(with_intel, "Christian McCaffrey") > place(without, "Christian McCaffrey"),
          "McCaffrey ranks lower once the fade is applied")
    top = with_intel[0]
    check(any("FADE" in x or "BUY" in x or "workhorse" in x or "bell cow" in x
              for r in with_intel for x in r.reasons),
          "intel notes surface as on-screen reasoning")

    # Playoff-schedule tiebreaker must stay late-round only.
    from engine.models import Player
    was = Player(rank=50, name="Test Guy", pos="WR", team="WAS")
    early = intel.playoff_adjust(was, 3)[0]
    late = intel.playoff_adjust(was, 10)[0]
    check(early == 0 and late > 0,
          "Wk15-17 schedule is a late-round tiebreaker only (R3 %+.0f, R10 %+.0f)"
          % (early, late))


def main():
    rng = random.Random(20260823)
    print("=" * 74)
    print("MOCK DRAFT - Fantasy Draft War Room acceptance test")
    print("=" * 74)

    state, matcher, tree = build(slot=4)
    print("  league: %s | %d teams | %d rounds | %d players | branches %s"
          % (state.league.name, state.teams, state.league.rounds,
             len(state.players), ", ".join(sorted(tree.branches))))
    if tree.unresolved:
        print("  ! unresolved strategy names: %s"
              % ", ".join(sorted(set(tree.unresolved))))

    test_parser(state, matcher)
    test_snake(state)
    block = test_full_draft(state, matcher, tree, rng)
    test_signals(rng)
    test_persistence(rng)
    test_bulk_sync()
    test_intel()

    if block:
        print("\n8. SAMPLE ON-CLOCK BLOCK (round 3 of the simulated draft)")
        print(block)

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
