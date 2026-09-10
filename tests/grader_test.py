#!/usr/bin/env python3
"""Acceptance test: draft grader (engine/grader.py).

Four parts. (1) A synthetic FULL draft scripted by ADP with one obvious
steal and one obvious reach planted: the grader must call both out by name,
letter every team, and - since the rework - grade ROSTER quality, meaning
every letter stays within one step of the pure lineup-points curve.
(2) A planted league that reproduces the old curve's failure case: slot 1
builds the objectively best starting lineup but a bench of dead RBs (huge
negative VBD), while another team hoards backup QBs that never start. The
old slot/VBD-sum curve flunked the premium roster and rewarded the hoarder;
the roster grade must now give the best-lineup team the best grade, with
the old market read surviving only as the clearly-secondary DRAFT SKILL
line. (3) The real partial Yahoo save must still run clean, say loudly it
is partial, and grade on draft skill only. (4) The real completed ESPN
draft (the save where the bug was originally reproduced): Team 1's premium
roster must no longer be an F, and every grade must track lineup points
within one letter.

    .venv/bin/python tests/grader_test.py
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.grader import (DEPTH_CAP, LETTERS, bench_depth_credit,  # noqa: E402
                           best_fallen, best_lineup, curve, grade_report,
                           letter_for, load_from_save, pick_grades,
                           positional_gaps, team_grades)
from engine.models import DraftState, LeagueConfig, load_players  # noqa: E402
from engine.recommend import effective_adp                        # noqa: E402

FAILURES = []

REAL_YAHOO_SAVE = os.path.join(HERE, "saves", "yahoo-main-20260829.json")
REAL_ESPN_SAVE = os.path.join(HERE, "saves", "espn-1-20260829.json")


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def build_state(slot=4):
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    league.my_slot = slot
    players = load_players(os.path.join(HERE, league.rankings_csv))
    return DraftState(league, players)


def letter_gap(a, b):
    return abs(LETTERS.index(a) - LETTERS.index(b))


def lineup_letters(tgrades):
    """The pure lineup-points curve - the anchor every grade must track."""
    zs = curve([t.lineup_pts for t in tgrades])
    return dict((t.team, letter_for(z)) for t, z in zip(tgrades, zs))


# --- 1. synthetic full draft with planted steal + reach ---------------------
def script_full_draft(state):
    """Draft strictly by ADP except two planted picks.

    STEAL: the 3rd player by ADP is held off the board until overall 40.
    REACH: at overall 25 a team takes a player with ADP ~120.
    Both blow far past the grader's max(6, 12%%-of-pick) threshold, so the
    test asserts intent, not a lucky rounding.
    """
    by_adp = sorted(state.players, key=effective_adp)
    steal_player = by_adp[2]                 # top-3 talent, falls to pick 40
    reach_player = by_adp[119]               # ~ADP 120 taken at pick 25
    queue = [p for p in by_adp if p.key not in (steal_player.key,
                                                reach_player.key)]
    qi = 0
    for overall in range(1, state.total_picks() + 1):
        if overall == 40:
            state.apply_pick(steal_player, overall=overall)
        elif overall == 25:
            state.apply_pick(reach_player, overall=overall)
        else:
            state.apply_pick(queue[qi], overall=overall)
            qi += 1
    return steal_player, reach_player


def test_synthetic_full():
    print("\n1. SYNTHETIC FULL DRAFT (planted steal at 40, reach at 25)")
    state = build_state(slot=4)
    steal_player, reach_player = script_full_draft(state)
    check(state.is_complete(), "scripted draft is complete (160 picks)")

    grades = pick_grades(state)
    check(len(grades) == state.total_picks(),
          "every pick produced a grade row")
    by_overall = dict((g.overall, g) for g in grades)

    g40 = by_overall[40]
    check(g40.player.key == steal_player.key, "pick 40 is the planted player")
    check(g40.label == "STEAL",
          "planted steal flagged STEAL (fell %+.0f vs ADP)" % g40.adp_delta)
    g25 = by_overall[25]
    check(g25.label == "REACH",
          "planted reach flagged REACH (%.0f early vs ADP)" % -g25.adp_delta)
    check(g25.vbd_delta < -20,
          "reach shows real VBD left on the board (%.0f)" % g25.vbd_delta)
    check(all(g.vbd_delta <= 1e-9 for g in grades),
          "vbd-vs-slot is never positive (it is 'vs best available')")

    report = grade_report(state, color=False)
    check(steal_player.name in report and "STEAL" in report,
          "report calls out the steal by name")
    check(reach_player.name in report and "REACH" in report,
          "report calls out the reach by name")
    check("PARTIAL" not in report, "complete draft is not labeled partial")
    check("PROJ LINEUP" in report,
          "complete draft projects starting lineups")
    check("ROSTER" in report and "DRAFT SKILL" in report,
          "report labels roster grade and draft skill as separate reads")

    tgrades = team_grades(state, grades)
    check(len(tgrades) == 10 and
          all(t.grade in "ABCDF" for t in tgrades),
          "all 10 teams got a letter grade")
    letters = set(t.grade for t in tgrades)
    check(len(letters) > 1,
          "curve spreads grades (%s)" % ", ".join(sorted(letters)))
    check(all(t.draft_grade in "ABCDF" for t in tgrades),
          "every team also carries a secondary draft-skill letter")

    # The roster grade must track what wins matchups.
    anchors = lineup_letters(tgrades)
    check(all(letter_gap(t.grade, anchors[t.team]) <= 1 for t in tgrades),
          "every roster grade is within one letter of the lineup-points "
          "curve")
    # In an ADP-scripted draft the top lineups are near-ties (slot luck),
    # so starters-VBD may break the tie - but the lineup leader can slip at
    # most one letter, and must sit at the top of the curve.
    best = max(tgrades, key=lambda t: t.lineup_pts)
    top_letter = LETTERS[min(LETTERS.index(t.grade) for t in tgrades)]
    check(letter_gap(best.grade, top_letter) <= 1 and best.grade in "AB",
          "the best-lineup team sits at the top of the curve "
          "(%s, %.0f pts, %s)" % (best.label, best.lineup_pts, best.grade))

    my = [t for t in tgrades if t.team == 4][0]
    check(my.lineup_pts is not None and my.lineup_pts > 0,
          "my lineup projected (%.0f pts)" % (my.lineup_pts or 0))
    check(">>" in report, "my team row is highlighted")

    # Lineup legality: right number of starting slots, no player reused.
    rows, pts, missing = best_lineup(state.league, state.roster(1))
    n_start = len([s for s in state.league.roster_spots
                   if s.strip().upper() not in ("BN", "BE", "BENCH", "IR")])
    check(len(rows) == n_start, "lineup has one row per starting slot")
    filled = [p for _, p in rows if p is not None]
    check(len(set(id(p) for p in filled)) == len(filled),
          "no player starts in two slots")
    for slot, p in rows:
        if p is None or slot in ("W/R/T",):
            continue
        check(p.pos == slot, "hard slot %s holds a %s" % (slot, p.pos))


# --- 2. the old curve's failure case: slot-1 premium roster -----------------
def script_premium_vs_hoarder(state):
    """Build the exact roster shape the old curve got wrong.

    Team 1 (slot 1) drafts a PREMIUM starting lineup - best projection at
    every still-needed starting position, K/DEF once nothing else is open -
    then two best-available depth picks, then nothing but bottom-of-the-pool
    RBs whose deeply negative VBD wrecks the old whole-roster VBD sum.
    Team 5 drafts to ADP except rounds 12-15, where it hoards backup QBs
    that will never start (their VBD sits near zero, which the old sum
    loved). Everyone else drafts strictly to ADP.
    """
    by_adp = sorted(state.players, key=effective_adp)
    taken = set()
    need = dict(state.league.hard_starter_counts())
    nflex = [len(state.league.flex_spots())]
    depth_left = [2]

    def pool(pred):
        return [p for p in state.players
                if p.key not in taken and p.proj_points and pred(p)]

    def team1_pick():
        open_pos = set(pos for pos in ("QB", "RB", "WR", "TE")
                       if need.get(pos, 0) > 0)
        if nflex[0] > 0:
            open_pos |= set(("RB", "WR", "TE"))
        cands = pool(lambda p: p.pos in open_pos)
        if cands:
            best = max(cands, key=lambda p: float(p.proj_points))
            if need.get(best.pos, 0) > 0:
                need[best.pos] -= 1
            else:
                nflex[0] -= 1
            return best
        for pos in ("K", "DEF"):
            if need.get(pos, 0) > 0:
                cands = pool(lambda p, pos=pos: p.pos == pos)
                if cands:
                    need[pos] -= 1
                    return max(cands, key=lambda p: float(p.proj_points))
        if depth_left[0] > 0:
            depth_left[0] -= 1
            cands = pool(lambda p: p.pos in ("RB", "WR"))
            return max(cands, key=lambda p: float(p.proj_points))
        return min(pool(lambda p: p.pos == "RB"),
                   key=lambda p: float(p.proj_points))

    for overall in range(1, state.total_picks() + 1):
        team = state.team_at(overall)
        rnd = (overall - 1) // state.teams + 1
        if team == 1:
            pick = team1_pick()
        elif team == 5 and 12 <= rnd <= 15:
            qbs = [p for p in state.players
                   if p.key not in taken and p.pos == "QB"]
            pick = sorted(qbs, key=effective_adp)[0]
        else:
            pick = next(p for p in by_adp if p.key not in taken)
        taken.add(pick.key)
        state.apply_pick(pick, overall=overall)


def test_planted_slot1_premium():
    print("\n2. PLANTED FAILURE CASE (slot-1 premium lineup, dead bench, "
          "QB hoarder)")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    league.my_slot = 1
    players = load_players(os.path.join(HERE, league.rankings_csv))
    state = DraftState(league, players)
    script_premium_vs_hoarder(state)
    check(state.is_complete(), "planted draft is complete (136 picks)")

    tgrades = team_grades(state, pick_grades(state))
    t1 = tgrades[0]
    t5 = tgrades[4]

    check(all(t1.lineup_pts >= t.lineup_pts for t in tgrades),
          "team 1 built the objectively best lineup (%.0f pts)"
          % t1.lineup_pts)
    check(t1.draft_grade in ("D", "F"),
          "the OLD value curve (now the draft-skill line) still flunks it "
          "(%s, value %.0f) - that was the bug" % (t1.draft_grade, t1.value))
    check(all(LETTERS.index(t1.grade) <= LETTERS.index(t.grade)
              for t in tgrades),
          "FIXED: best-lineup team now gets the best roster grade (%s)"
          % t1.grade)
    check(t1.grade != "F", "the premium slot-1 roster is not an F")

    check(t5.lineup_pts < t1.lineup_pts and t5.value > t1.value,
          "hoarder has a worse lineup but a better old-style value "
          "(%.0f vs %.0f) - the bait the old curve took"
          % (t5.value, t1.value))
    check(LETTERS.index(t5.grade) >= LETTERS.index(t1.grade),
          "QB hoarding no longer outgrades the premium roster "
          "(hoarder %s vs %s)" % (t5.grade, t1.grade))

    anchors = lineup_letters(tgrades)
    check(all(letter_gap(t.grade, anchors[t.team]) <= 1 for t in tgrades),
          "all grades stay within one letter of the lineup-points curve")

    # Depth credit is a capped tiebreaker, never a grade driver.
    check(all(0.0 <= t.depth_credit for t in tgrades),
          "depth credit is never negative")
    rbs = sorted([p for p in players if p.pos == "RB" and p.proj_points],
                 key=lambda p: -float(p.proj_points))[:2]
    fake_repl = {"RB": float(rbs[0].proj_points) - 200.0}
    credited = bench_depth_credit(fake_repl, rbs, [])
    check(abs(credited - DEPTH_CAP) < 1e-9,
          "a monster backup is capped at DEPTH_CAP (%.0f pts, not 200)"
          % credited)


# --- 3. the real partial Yahoo save -----------------------------------------
def test_real_yahoo_partial():
    print("\n3. REAL YAHOO SAVE (saves/yahoo-main-20260829.json, 33 picks)")
    state, data = load_from_save(REAL_YAHOO_SAVE)
    check(len(state.picks) == 33, "restored all 33 picks")
    check(state.my_slot == 4,
          "my_slot taken from the SAVE (4), not the edited yaml")
    check(not state.is_complete(), "draft correctly seen as partial")

    report = grade_report(state, save_path=REAL_YAHOO_SAVE, color=False)
    check("PARTIAL DRAFT: 33 of 160" in report,
          "report says plainly it is partial (33 of 160)")
    check("lineup projections are skipped" in report,
          "lineup projection skipped, with the reason stated")
    check("PROJ LINEUP" not in report,
          "no lineup-points column on a partial draft")
    check("DRAFT SKILL only" in report,
          "partial grades are labeled as draft skill, not roster strength")
    check("ME (Team 4)" in report, "my team is named in the report")
    check("MY GAPS" in report, "report ends with my gap list")
    check("GAPS" in report, "per-team gaps shown instead of lineups")

    grades = pick_grades(state)
    check(len(grades) == 33, "all 33 real picks graded")
    tgrades = team_grades(state, grades)
    check(all(t.lineup_pts is None for t in tgrades),
          "no team got a lineup projection mid-draft")
    check(all(t.roster_z is None for t in tgrades),
          "no roster curve exists mid-draft")
    check(all(t.grade in "ABCDF" for t in tgrades),
          "letter grades still curve on a partial draft")
    check(all(t.grade == t.draft_grade for t in tgrades),
          "mid-draft the primary grade IS the draft-skill grade")

    # 3 rounds in, nobody should have K/DEF - gaps must reflect real demand.
    my_gaps = positional_gaps(state, 4)
    check(any(g.startswith("K") for g in my_gaps)
          and any(g.startswith("DEF") for g in my_gaps),
          "my gaps include the obviously unfilled K and DEF")

    fallen = best_fallen(state)
    check(all(state.drafted.get(p.key) is None for p, _ in fallen),
          "fallen list only holds players still available")


# --- 4. the real completed ESPN draft (where the bug was reproduced) --------
def test_real_espn_complete():
    print("\n4. REAL ESPN SAVE (saves/espn-1-20260829.json, the reproduced "
          "bug)")
    state, data = load_from_save(REAL_ESPN_SAVE)
    check(state.is_complete(), "the ESPN draft is complete (136 picks)")
    check(state.my_slot == 1, "my team is slot 1 ('AI')")

    tgrades = team_grades(state, pick_grades(state))
    t1 = [t for t in tgrades if t.team == 1][0]
    check(t1.grade != "F",
          "team 1's roster is no longer an F (%s, %.0f lineup pts)"
          % (t1.grade, t1.lineup_pts))

    anchors = lineup_letters(tgrades)
    check(all(letter_gap(t.grade, anchors[t.team]) <= 1 for t in tgrades),
          "every real-league grade is within one letter of the "
          "lineup-points curve")
    best = max(tgrades, key=lambda t: t.lineup_pts)
    check(all(LETTERS.index(best.grade) <= LETTERS.index(t.grade)
              for t in tgrades),
          "the best real lineup (%s, %.0f pts) holds the best grade (%s)"
          % (best.label, best.lineup_pts, best.grade))
    check(any(t.grade != t.draft_grade for t in tgrades),
          "roster grade and draft skill genuinely differ for someone - "
          "both reads earn their place")

    report = grade_report(state, save_path=REAL_ESPN_SAVE, color=False)
    check("ROSTER" in report and "DRAFT SKILL" in report,
          "report separates roster strength from draft skill")
    check("PARTIAL" not in report, "completed draft is not labeled partial")


def main():
    print("=" * 74)
    print("DRAFT GRADER - acceptance test")
    print("=" * 74)
    test_synthetic_full()
    test_planted_slot1_premium()
    test_real_yahoo_partial()
    test_real_espn_complete()
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
