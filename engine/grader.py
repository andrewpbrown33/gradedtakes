"""Draft grader: score any completed-or-partial draft from a save JSON.

    python -m engine.grader [saves/yahoo-main-20260829.json] [--league yahoo-main]

For every pick it reports the market delta vs ADP (steal/reach) and the
VBD-vs-slot delta (what the pick earned versus the best player still on the
board at that moment). Per team it totals draft value, curves letter grades
against THIS league's distribution, fills the best legal starting lineup
(completed drafts only - see below), and lists positional gaps against league
demand. Ends with MY team's gap list, which later feeds trade targets.

Judgment calls, documented once here rather than sprinkled around:

* STEAL / REACH thresholds scale with draft depth: a pick is flagged when it
  beats/trails ADP by max(6, 12% of the overall pick number). Six picks is a
  round-trip of noise in the first two rounds; by pick 100 the market itself
  disagrees by a dozen spots, so a fixed threshold would flag half the
  endgame.
* VBD-vs-slot compares the pick against the best-VBD player still available
  at that exact moment (replayed in overall order). It is always <= 0; near
  zero means "took the best thing on the board", a big negative means value
  was left sitting there. It feeds the DRAFT SKILL line only - never the
  roster grade.
* ROSTER GRADE (the primary grade on a completed draft) measures roster
  quality, not slot luck. Three inputs, each z-scored against THIS league's
  teams, then combined and re-curved:
    (a) best-legal-lineup projected points (weight 0.50) - the number that
        actually wins matchups;
    (b) starters-only VBD vs league replacement (weight 0.35) - bench
        players contribute nothing here, so hoarding QB2s that never start
        earns nothing;
    (c) a small depth credit (weight 0.15): per position, the best BENCH
        player's points above replacement, capped at DEPTH_CAP points -
        a 5th startable RB adds little in a shallow league, so the cap
        keeps depth a tiebreaker, not a grade driver.
  The final letter is anchored to the pure lineup-points curve: it may
  differ from that curve's letter by at most one step, because lineup
  points are the thing that wins games. Historical bug this replaces: a
  slot-adjusted vbd-vs-slot sum once handed the roster with near-best
  lineup points an F while rewarding rosters stuffed with backup QBs.
* DRAFT SKILL (the secondary line) is the old market read: total VBD of all
  picks + 0.25 * total ADP delta, curved the same way. It answers "did you
  pick well for where you picked", which is a DIFFERENT question - a team
  can draft skillfully and still be outgunned, or luck into a monster
  roster while reaching. The report states both and labels them apart.
* All curves are RELATIVE to this league's distribution (z-scores):
  A >= +1.0 sigma, B >= +0.35, C >= -0.35, D >= -1.0, F below. Someone
  always looks bad on a curve - that is the point of grading against the
  room instead of an absolute scale. If every team somehow ties
  (sigma ~ 0), everyone is average: straight C's.
* PARTIAL drafts have no honest roster grade (a mostly-empty lineup would
  rank teams by draft-slot luck), so mid-draft the letter shown IS the
  draft-skill curve, and the report says so.
* PARTIAL drafts are graded honestly: picks made so far get the full
  steal/reach and value treatment, but the starting-lineup projection is
  SKIPPED, not rendered "(incomplete)". Three rounds into a 16-round draft
  every lineup has seven empty starting slots; a projected-points number
  built mostly of zeros would rank teams by draft-slot luck and mean
  nothing. Positional gaps are shown instead - they are exactly the honest
  statement of what an incomplete roster is missing. When pick counts differ
  mid-round, the header says so: the team with the extra pick carries an
  extra pick's worth of value.

No network calls anywhere in this module - grading must work on draft night
with the wifi down.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

from .models import (DraftState, FLEX_ELIGIBLE, LeagueConfig, Player,
                     fmt_pick, load_players, norm_pos, POSITIONS)
from .recommend import Ansi, effective_adp, replacement_levels, vbd
from . import state as save_state

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRADE_STEPS = [(1.0, "A"), (0.35, "B"), (-0.35, "C"), (-1.0, "D")]
LETTERS = "ABCDF"

# Roster-grade knobs (see module docstring for the reasoning).
DEPTH_CAP = 25.0                      # max depth credit per position, points
ROSTER_WEIGHTS = (0.50, 0.35, 0.15)   # lineup pts, starters VBD, depth


def steal_reach_threshold(overall: int) -> float:
    """Picks-past-ADP needed before a pick is worth calling out."""
    return max(6.0, 0.12 * overall)


# --- loading ----------------------------------------------------------------
def load_from_save(save_path: str, league_id: Optional[str] = None
                   ) -> Tuple[DraftState, dict]:
    """Build a DraftState from a save JSON. Returns (state, raw save data).

    The save is the record of the draft as it actually happened, so its
    my_slot beats the league yaml's (the yaml may have been edited for a
    later draft since this one was played).
    """
    with open(save_path, "r") as fh:
        data = json.load(fh)

    lid = league_id or data.get("league_id")
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % lid) if lid else ""
    if not os.path.exists(league_path):
        league_path = data.get("league_path", "")
    if not league_path or not os.path.exists(league_path):
        raise SystemExit("cannot find league yaml for save %s (tried id %r "
                         "and the save's league_path)" % (save_path, lid))

    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, data.get("rankings_csv")
                            or league.rankings_csv)
    players = load_players(csv_path)
    state = DraftState(league, players)
    save_state.restore(state, save_path)
    if data.get("my_slot"):
        state.league.my_slot = int(data["my_slot"])
    return state, data


# --- per-pick grading -------------------------------------------------------
class PickGrade(object):
    __slots__ = ("overall", "team", "player", "adp_delta", "vbd_delta",
                 "player_vbd", "label")

    def __init__(self, overall, team, player, adp_delta, vbd_delta,
                 player_vbd, label):
        self.overall = overall
        self.team = team
        self.player = player
        self.adp_delta = adp_delta      # overall - ADP: +N = taken N picks
                                        # past his ADP (steal side), -N = N
                                        # picks early (reach side)
        self.vbd_delta = vbd_delta      # vs best VBD available then; <= 0
        self.player_vbd = player_vbd
        self.label = label              # "STEAL" | "REACH" | ""


def pick_grades(state: DraftState) -> List[PickGrade]:
    """Grade every known pick, replaying the board in overall order.

    Placeholder picks ('__skipped__') and picks that never matched a ranked
    player hold their slot on the board but produce no grade row.
    """
    repl = replacement_levels(state)
    taken = set()
    grades = []
    for pick in sorted(state.picks.values(), key=lambda p: p.overall):
        player = state.by_key.get(pick.player_key)
        if player is None:
            continue
        best_vbd = None
        for p in state.players:
            if p.key in taken:
                continue
            v = vbd(p, repl)
            if best_vbd is None or v > best_vbd:
                best_vbd = v
        taken.add(player.key)

        adp_delta = pick.overall - effective_adp(player)
        player_vbd = vbd(player, repl)
        vbd_delta = (player_vbd - best_vbd) if best_vbd is not None else 0.0
        thresh = steal_reach_threshold(pick.overall)
        label = ("STEAL" if adp_delta >= thresh
                 else "REACH" if -adp_delta >= thresh else "")
        grades.append(PickGrade(pick.overall, pick.team, player,
                                adp_delta, vbd_delta, player_vbd, label))
    return grades


# --- lineup fill ------------------------------------------------------------
def best_lineup(league: LeagueConfig, roster: List[Player]
                ) -> Tuple[List[Tuple[str, Optional[Player]]], float, List[str]]:
    """Fill the best legal starting lineup from a roster.

    Hard slots take the top projections at their position; flex groups fill
    most-restrictive-first from what remains (same ordering argument as
    flex_allocation in recommend.py - overlapping eligibilities must not
    double-count a player). Returns (slot, player-or-None) rows, the total
    projected points of the filled slots, and the list of unfilled slots.
    """
    pool = sorted(roster, key=lambda p: -(float(p.proj_points or 0.0)))
    used = set()
    rows = []

    hard_slots = []
    flex_groups = []
    for spot in league.roster_spots:
        s = spot.strip().upper()
        if s in ("BN", "BE", "BENCH", "IR"):
            continue
        if s in FLEX_ELIGIBLE:
            flex_groups.append((s, FLEX_ELIGIBLE[s]))
        else:
            hard_slots.append(norm_pos(s))

    for slot in hard_slots:
        cand = next((p for p in pool if id(p) not in used and p.pos == slot),
                    None)
        if cand is not None:
            used.add(id(cand))
        rows.append((slot, cand))

    for slot, elig in sorted(flex_groups, key=lambda g: len(g[1])):
        cand = next((p for p in pool if id(p) not in used and p.pos in elig),
                    None)
        if cand is not None:
            used.add(id(cand))
        rows.append((slot, cand))

    total = sum(float(p.proj_points or 0.0) for _, p in rows if p is not None)
    missing = [slot for slot, p in rows if p is None]
    return rows, total, missing


def positional_gaps(state: DraftState, team: int) -> List[str]:
    """Unfilled starting demand for a team: hard slots first, then flex."""
    counts = state.pos_counts(team)
    hard = state.league.hard_starter_counts()
    gaps = []
    for pos in POSITIONS:
        deficit = hard.get(pos, 0) - counts.get(pos, 0)
        if deficit > 0:
            gaps.append("%s x%d" % (pos, deficit))
    # Flex demand: extras beyond hard starters, consumed most-restrictive-first.
    extras = dict((pos, max(0, counts.get(pos, 0) - hard.get(pos, 0)))
                  for pos in POSITIONS)
    open_flex = 0
    for elig in sorted(state.league.flex_spots(), key=len):
        filled = False
        for pos in sorted(elig, key=lambda p: -extras.get(p, 0)):
            if extras.get(pos, 0) > 0:
                extras[pos] -= 1
                filled = True
                break
        if not filled:
            open_flex += 1
    if open_flex:
        gaps.append("FLEX x%d" % open_flex)
    return gaps


def surplus_positions(state: DraftState, team: int) -> List[str]:
    """Positions held beyond ANY possible starting use - the trade ammo side.

    Generous on purpose: every flex slot the position is eligible for counts
    as potential starting use, so a listed surplus really is bench-only depth.
    """
    counts = state.pos_counts(team)
    hard = state.league.hard_starter_counts()
    out = []
    for pos in ("RB", "WR", "TE", "QB"):
        flex_share = sum(1 for elig in state.league.flex_spots() if pos in elig)
        over = counts.get(pos, 0) - hard.get(pos, 0) - flex_share
        if over > 0:
            out.append("%s +%d" % (pos, over))
    return out


# --- team grading -----------------------------------------------------------
class TeamGrade(object):
    __slots__ = ("team", "label", "picks", "total_vbd", "total_adp_delta",
                 "value", "grade", "draft_grade", "roster_z", "lineup_pts",
                 "starters_vbd", "depth_credit", "lineup_missing", "gaps")

    def __init__(self, team, label):
        self.team = team
        self.label = label
        self.picks = 0
        self.total_vbd = 0.0
        self.total_adp_delta = 0.0
        self.value = 0.0           # draft-skill value: VBD + 0.25 * ADP delta
        self.grade = "C"           # PRIMARY: roster grade (draft skill when
                                   # partial - no honest roster read exists)
        self.draft_grade = "C"     # SECONDARY: pick-skill curve, always set
        self.roster_z = None       # None = partial draft, no roster curve
        self.lineup_pts = None     # None = not projected (partial draft)
        self.starters_vbd = None   # starters-only VBD (complete drafts)
        self.depth_credit = None   # capped bench credit (complete drafts)
        self.lineup_missing = []
        self.gaps = []


def letter_for(z: float) -> str:
    for cut, letter in GRADE_STEPS:
        if z >= cut:
            return letter
    return "F"


def curve(values: List[float]) -> List[float]:
    """z-scores against this league's own distribution; flat field = all 0."""
    mean = sum(values) / len(values)
    sd = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    if sd < 1e-9:
        return [0.0] * len(values)
    return [(v - mean) / sd for v in values]


def bench_depth_credit(repl: Dict[str, float], roster: List[Player],
                       starters: List[Player]) -> float:
    """Small depth credit: best BENCH player per position, points above
    replacement, capped at DEPTH_CAP per position.

    Only the best backup counts - the 2nd bench RB is insurance for the
    insurance - and the cap stops depth from outvoting the lineup: a 5th
    startable RB adds little in a shallow league because he never starts.
    """
    started = set(id(p) for p in starters)
    bench = [p for p in roster if id(p) not in started]
    total = 0.0
    for pos in set(p.pos for p in bench):
        if pos not in repl:
            continue
        best = max(float(p.proj_points or 0.0) - repl[pos]
                   for p in bench if p.pos == pos)
        total += max(0.0, min(best, DEPTH_CAP))
    return total


def _anchor_to_lineup(letter: str, lineup_letter: str) -> str:
    """Clamp the composite letter to within one step of the pure
    lineup-points curve - lineup points are what wins matchups, so the
    other inputs may nudge a grade, never flip it."""
    li, ai = LETTERS.index(letter), LETTERS.index(lineup_letter)
    return LETTERS[min(max(li, ai - 1), ai + 1)]


def team_grades(state: DraftState, grades: List[PickGrade]) -> List[TeamGrade]:
    out = dict((t, TeamGrade(t, state.team_label(t)))
               for t in range(1, state.teams + 1))
    for g in grades:
        tg = out[g.team]
        tg.picks += 1
        tg.total_vbd += g.player_vbd
        tg.total_adp_delta += g.adp_delta
    complete = state.is_complete()
    repl = replacement_levels(state)
    for tg in out.values():
        tg.value = tg.total_vbd + 0.25 * tg.total_adp_delta
        tg.gaps = positional_gaps(state, tg.team)
        if complete:
            roster = state.roster(tg.team)
            rows, pts, missing = best_lineup(state.league, roster)
            tg.lineup_pts = pts
            tg.lineup_missing = missing
            starters = [p for _, p in rows if p is not None]
            tg.starters_vbd = sum(vbd(p, repl) for p in starters)
            tg.depth_credit = bench_depth_credit(repl, roster, starters)

    teams = [out[t] for t in range(1, state.teams + 1)]

    # Draft skill: the pick-by-pick market curve. Always computed; it is the
    # PRIMARY grade only mid-draft, when no honest roster read exists.
    for tg, z in zip(teams, curve([t.value for t in teams])):
        tg.draft_grade = letter_for(z)
        if not complete:
            tg.grade = tg.draft_grade

    if complete:
        z_pts = curve([t.lineup_pts for t in teams])
        z_vbd = curve([t.starters_vbd for t in teams])
        z_dep = curve([t.depth_credit for t in teams])
        wa, wb, wc = ROSTER_WEIGHTS
        z_comp = curve([wa * a + wb * b + wc * c
                        for a, b, c in zip(z_pts, z_vbd, z_dep)])
        for tg, zc, zl in zip(teams, z_comp, z_pts):
            tg.roster_z = zc
            tg.grade = _anchor_to_lineup(letter_for(zc), letter_for(zl))
    return teams


# --- fallen players ---------------------------------------------------------
def best_fallen(state: DraftState, limit: int = 8) -> List[Tuple[Player, float]]:
    """Available players furthest past their ADP right now.

    In a completed draft this is 'went undrafted despite ADP N'; mid-draft it
    is the live discount rack.
    """
    frontier = min(state.current_pick(), state.total_picks() + 1)
    out = []
    for p in state.available():
        adp = effective_adp(p)
        fall = frontier - adp
        if fall >= 3:
            out.append((p, fall))
    out.sort(key=lambda t: (-t[1], effective_adp(t[0])))
    return out[:limit]


# --- report -----------------------------------------------------------------
def grade_report(state: DraftState, save_path: str = "", color: bool = True,
                 width: int = 74) -> str:
    c = Ansi(color)
    line, thin = "=" * width, "-" * width
    out = [c.cyan(line)]

    made = len(state.picks)
    total = state.total_picks()
    complete = state.is_complete()
    out.append(c.bold(" DRAFT GRADE   %s   %d teams, %d rounds%s"
                      % (state.league.name, state.teams, state.league.rounds,
                         ("   [%s]" % os.path.basename(save_path))
                         if save_path else "")))
    if not complete:
        full_rounds = made // state.teams
        rem = made % state.teams
        where = ("rounds 1-%d done, round %d in progress"
                 % (full_rounds, full_rounds + 1) if full_rounds and rem
                 else "round %d in progress" % (full_rounds + 1) if rem
                 else "rounds 1-%d done" % full_rounds)
        out.append(c.yellow(
            " PARTIAL DRAFT: %d of %d picks made (%s)." % (made, total, where)))
        out.append(c.yellow(
            " Grading only what's on the board; lineup projections are "
            "skipped, not faked -"))
        out.append(c.yellow(
            " a lineup that is mostly empty slots would rank teams by "
            "draft-slot luck."))
        per_team = [sum(1 for p in state.picks.values() if p.team == t)
                    for t in range(1, state.teams + 1)]
        if len(set(per_team)) > 1:
            out.append(c.dim(
                " (mid-round: teams differ by a pick - the extra pick's "
                "value counts for its team)"))

    grades = pick_grades(state)
    unmatched = made - len(grades)
    if unmatched:
        out.append(c.dim(" %d pick(s) had no matched player and were skipped."
                         % unmatched))

    # Steals and reaches.
    steals = [g for g in grades if g.label == "STEAL"]
    reaches = [g for g in grades if g.label == "REACH"]
    steals.sort(key=lambda g: -g.adp_delta)
    reaches.sort(key=lambda g: g.adp_delta)
    out.append(thin)
    out.append(c.bold(" STEALS AND REACHES  (DRAFT SKILL, not roster quality; "
                      "vs ADP)"))
    out.append(c.dim("   vbd-vs-slot = value vs the best player then "
                     "available; feeds no roster grade"))
    if not steals and not reaches:
        out.append("   none worth calling out - the room drafted to market")
    for g in steals:
        out.append(c.green(
            "   STEAL  %s  %-26s %-12s ADP %.0f (+%d)  vbd-vs-slot %+.0f"
            % (fmt_pick(g.overall, state.teams), g.player.short_label(),
               state.team_label(g.team)[:12], effective_adp(g.player),
               int(round(g.adp_delta)), g.vbd_delta)))
    for g in reaches:
        out.append(c.red(
            "   REACH  %s  %-26s %-12s ADP %.0f (%d)  vbd-vs-slot %+.0f"
            % (fmt_pick(g.overall, state.teams), g.player.short_label(),
               state.team_label(g.team)[:12], effective_adp(g.player),
               int(round(g.adp_delta)), g.vbd_delta)))

    # Team table.
    tgrades = team_grades(state, grades)
    out.append(thin)
    if complete:
        out.append(c.bold(" TEAM GRADES  (ROSTER strength, curved: A >= +1.0 "
                          "sigma, B +0.35, C -0.35, D -1.0)"))
        out.append(c.dim("   roster grade = best legal lineup (the number "
                         "that wins matchups)"))
        out.append(c.dim("   + starters-only VBD + capped bench depth. "
                         "DRAFT SKILL is the separate"))
        out.append(c.dim("   pick-value curve - 'drafted well' and 'roster "
                         "strength' can differ."))
        header = "   %-5s %-20s %-12s %-7s %-6s %s" % (
            "GRADE", "TEAM", "PROJ LINEUP", "ST.VBD", "DEPTH", "DRAFT SKILL")
        out.append(c.dim(header))
        ordered = sorted(tgrades, key=lambda t: (-t.roster_z, -t.lineup_pts))
        for tg in ordered:
            tail = "%s (value %.0f)" % (tg.draft_grade, tg.value)
            if tg.lineup_missing:
                tail += "  (open: %s)" % ", ".join(tg.lineup_missing)
            row = "   %-5s %-20s %-12s %-7s %-6s %s" % (
                tg.grade, tg.label[:20], "%.0f pts" % tg.lineup_pts,
                "%+.0f" % tg.starters_vbd, "%+.0f" % tg.depth_credit, tail)
            if tg.team == state.my_slot:
                out.append(c.green(">>" + row[2:]))
            else:
                out.append(row)
    else:
        out.append(c.bold(" TEAM GRADES  (curved to this league: A >= +1.0 "
                          "sigma, B +0.35, C -0.35, D -1.0)"))
        out.append(c.yellow("   partial draft: grades below are DRAFT SKILL "
                            "only - roster strength is"))
        out.append(c.yellow("   graded when the draft completes."))
        header = "   %-5s %-22s %-5s %-8s %-8s %s" % (
            "GRADE", "TEAM", "PICKS", "VBD", "VALUE",
            "GAPS (starting demand unfilled)")
        out.append(c.dim(header))
        for tg in sorted(tgrades, key=lambda t: -t.value):
            tail = ", ".join(tg.gaps) if tg.gaps else "-"
            row = "   %-5s %-22s %-5d %-8.0f %-8.0f %s" % (
                tg.grade, tg.label[:22], tg.picks, tg.total_vbd, tg.value,
                tail)
            if tg.team == state.my_slot:
                out.append(c.green(">>" + row[2:]))
            else:
                out.append(row)

    # Best fallen players.
    fallen = best_fallen(state)
    out.append(thin)
    out.append(c.bold(" BEST FALLEN PLAYERS  (still available past their "
                      "ADP%s)" % ("" if complete else " right now")))
    if not fallen:
        out.append("   nobody notable has slipped - the board is tracking ADP")
    for p, fall in fallen:
        out.append("   %-26s ADP %5.1f  fell %3d picks  proj %s"
                   % (p.short_label(), effective_adp(p), int(round(fall)),
                      ("%.0f" % p.proj_points) if p.proj_points else "-"))

    # My team's gap list - the trade-target feed.
    if state.my_slot:
        out.append(thin)
        out.append(c.bold(" MY GAPS  (%s) - feeds trade targets"
                          % state.team_label(state.my_slot)))
        roster = state.my_roster()
        out.append("   roster: " + (", ".join("%s(%s)" % (p.surname(), p.pos)
                                              for p in roster) or "(empty)"))
        gaps = positional_gaps(state, state.my_slot)
        if gaps:
            out.append(c.yellow("   need:   " + ", ".join(gaps)))
        else:
            out.append(c.green("   need:   none - every starting slot is "
                               "covered"))
        surplus = surplus_positions(state, state.my_slot)
        if surplus:
            out.append("   ammo:   " + ", ".join(surplus)
                       + "  (depth beyond any starting use)")
        if not complete:
            out.append(c.dim("   (partial draft: gaps reflect rounds drafted "
                             "so far, not a finished roster)"))

    out.append(c.cyan(line))
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.grader",
        description="Grade a completed or in-progress draft from a save JSON.")
    ap.add_argument("save", nargs="?", default=None,
                    help="save JSON (default: latest save for --league)")
    ap.add_argument("--league", default=None,
                    help="league id (default: the save's own league_id)")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    save_path = args.save
    if save_path is None:
        save_path = save_state.latest_save(args.league or "yahoo-main")
        if save_path is None:
            print("no save found in saves/ for league %r"
                  % (args.league or "yahoo-main"))
            return 1
    if not os.path.exists(save_path):
        alt = os.path.join(HERE, save_path)
        if os.path.exists(alt):
            save_path = alt
        else:
            print("save not found: %s" % save_path)
            return 1

    state, _ = load_from_save(save_path, args.league)
    color = (not args.no_color) and sys.stdout.isatty()
    print(grade_report(state, save_path=save_path, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
