"""Keeper calculator: keep a player, or throw him back and keep the pick.

The trade being priced: keeping a player burns the draft pick in his cost
round. So his keeper value is not his raw VBD - it is his VBD minus the VBD
of the player you would otherwise have taken with that forfeited pick:

    margin = VBD(keeper) - VBD(expected best available at the forfeited slot)

"Expected best available" is the highest-projected player whose ADP is at or
after the forfeited pick's overall number - i.e. the market does not expect
him to be gone yet. Projection is measured as VBD, the same scale the margin
is priced in (see expected_best). The expectation is ADP-based and
deliberately ignores which players OTHER managers will keep (nobody knows
that yet), which the output says out loud.

    python -m engine.keeper "Puka Nacua" --cost-round 5
    python -m engine.keeper --list                # batch: data/keepers.yaml

data/keepers.yaml format:

    players:
      - name: Puka Nacua
        cost_round: 5
"""

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

import yaml

from .ingest import Matcher
from .models import (DraftState, LeagueConfig, Player, fmt_pick, load_players,
                     missing_rankings_message)
from .recommend import LATE_ONLY, effective_adp, replacement_levels, vbd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_KEEPERS = os.path.join(HERE, "data", "keepers.yaml")

# |margin| under this many season points is a coin flip, not a conviction.
MARGINAL_BAND = 10.0

CAVEATS = [
    "league keeper rules unconfirmed (RUNBOOK B2) - verify the round cost",
    "and keeper count with the commissioner before trusting these verdicts.",
    "Expected-best is ADP-based and ignores other managers' keepers.",
]


def forfeited_overall(cost_round: int, slot: int, teams: int) -> int:
    """Overall pick number my slot forfeits by keeping at this round (snake)."""
    if cost_round % 2 == 1:
        return (cost_round - 1) * teams + slot
    return (cost_round - 1) * teams + (teams - slot + 1)


def resolve_slot(league: LeagueConfig,
                 override: Optional[int] = None) -> Tuple[int, bool]:
    """(slot, assumed). Mid-slot is assumed - and flagged - when unset."""
    if override:
        return override, False
    if league.my_slot:
        return league.my_slot, False
    return (league.teams + 1) // 2, True


def expected_best(state: DraftState, overall: int, repl: Dict[str, float],
                  exclude_key: Optional[str] = None,
                  skip_pos: Tuple[str, ...] = ()) -> Optional[Player]:
    """Highest-projected available player whose ADP is >= this overall pick.

    "Highest-projected" is measured as VBD - the same scale the margin is
    priced in - not raw points. Raw points would crown a QB the expected best
    at every early pick (QBs top the raw projection board) even though his
    value over a replacement QB is modest, and every keep margin would
    inflate. VBD selection makes the comparison the pick you would actually
    make at that slot.

    skip_pos mirrors the recommendation engine's LATE_ONLY rule: before the
    endgame rounds a real pick would never be spent on K/DEF, so a kicker
    must not stand in as the alternative to keeping a skill player.
    """
    best, best_v = None, None
    for p in state.available():
        if p.key == exclude_key or not p.proj_points or p.pos in skip_pos:
            continue
        if effective_adp(p) < overall:
            continue
        v = vbd(p, repl)
        if best is None or v > best_v:
            best, best_v = p, v
    return best


def _adp_round(adp: float, teams: int) -> int:
    return max(1, int((adp - 1) // teams) + 1)


class Verdict(object):
    __slots__ = ("player", "cost_round", "overall", "comparison", "margin",
                 "keep", "marginal", "reasons")

    def __init__(self, player: Player, cost_round: int, overall: int,
                 comparison: Optional[Player], margin: float,
                 reasons: List[str]):
        self.player = player
        self.cost_round = cost_round
        self.overall = overall
        self.comparison = comparison
        self.margin = margin
        self.keep = margin > 0
        self.marginal = abs(margin) < MARGINAL_BAND
        self.reasons = reasons

    def tag(self) -> str:
        return "KEEP" if self.keep else "THROW BACK"


def evaluate(state: DraftState, player: Player, cost_round: int, slot: int,
             repl: Optional[Dict[str, float]] = None) -> Verdict:
    """Price keeping `player` at `cost_round` from `slot`. Raises loudly when
    the math cannot be done (no projections) rather than guessing."""
    league = state.league
    if not 1 <= cost_round <= league.rounds:
        raise ValueError("cost round %d is outside this league's 1-%d"
                         % (cost_round, league.rounds))
    repl = replacement_levels(state) if repl is None else repl
    if not repl:
        raise ValueError("no projections in the player pool - VBD is "
                         "undefined; fill proj_points first "
                         "(engine/projections.py)")
    if not player.proj_points:
        raise ValueError("%s carries no projection - cannot compute his VBD"
                         % player.name)

    overall = forfeited_overall(cost_round, slot, league.teams)
    keeper_vbd = vbd(player, repl)
    # K/DEF cannot be the alternative before the endgame rounds (LATE_ONLY),
    # matching when the recommendation engine would actually draft them.
    skip = LATE_ONLY if cost_round <= league.rounds - 2 else ()
    comparison = expected_best(state, overall, repl, exclude_key=player.key,
                               skip_pos=skip)

    adp = effective_adp(player)
    reasons = ["keeping him burns my round-%d pick (overall %d, pick %s)"
               % (cost_round, overall, fmt_pick(overall, league.teams)),
               "%s: %.1f proj, %+.1f VBD, ADP %.1f (~round %d)"
               % (player.name, float(player.proj_points), keeper_vbd, adp,
                  _adp_round(adp, league.teams))]

    if comparison is None:
        margin = keeper_vbd
        reasons.append("no projected player carries an ADP at/after pick %d "
                       "- that pick prices as replacement level" % overall)
    else:
        margin = keeper_vbd - vbd(comparison, repl)
        reasons.append("expected best there instead: %s (%.1f proj, %+.1f "
                       "VBD, ADP %.1f)"
                       % (comparison.short_label(),
                          float(comparison.proj_points),
                          vbd(comparison, repl), effective_adp(comparison)))

    surplus = cost_round - _adp_round(adp, league.teams)
    if surplus >= 2:
        reasons.append("market price ~round %d vs cost round %d = %d rounds "
                       "of surplus" % (_adp_round(adp, league.teams),
                                       cost_round, surplus))
    if adp >= overall:
        reasons.append("his own ADP (%.1f) says he would likely still be "
                       "there at pick %d - keeping gains little" % (adp,
                                                                    overall))
    v = Verdict(player, cost_round, overall, comparison, margin, reasons)
    if v.marginal:
        v.reasons.append("margin under %.0f pts - call it a coin flip"
                         % MARGINAL_BAND)
    return v


# --- keeper sheet (--list) --------------------------------------------------
def load_keepers(path: str) -> List[Dict]:
    """Read data/keepers.yaml. Bad entries fail loudly - a silently skipped
    keeper is a wrong verdict sheet."""
    with open(path, "r") as fh:
        data = yaml.safe_load(fh) or {}
    rows = data.get("players") or []
    if not isinstance(rows, list):
        raise ValueError("%s: 'players' must be a list" % path)
    out, bad = [], []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not row.get("name") \
                or not str(row.get("cost_round", "")).strip():
            bad.append("entry %d: %r" % (i, row))
            continue
        try:
            cost = int(row["cost_round"])
        except (TypeError, ValueError):
            bad.append("entry %d (%s): cost_round %r is not an integer"
                       % (i, row.get("name"), row.get("cost_round")))
            continue
        out.append({"name": str(row["name"]), "cost_round": cost})
    if bad:
        raise ValueError("%s has malformed entries (need name + cost_round):\n"
                         "  %s" % (path, "\n  ".join(bad)))
    return out


# --- rendering --------------------------------------------------------------
def verdict_lines(v: Verdict) -> List[str]:
    lines = ["%-10s  %s  cost: round %d  margin %+.1f pts"
             % (v.tag(), v.player.short_label(), v.cost_round, v.margin)]
    for r in v.reasons:
        lines.append("    - %s" % r)
    return lines


def _caveat_lines() -> List[str]:
    return ["CAVEAT: %s" % CAVEATS[0]] + ["        %s" % c for c in CAVEATS[1:]]


def build_state(league_arg: str):
    """(state, matcher) for a league id (leagues/<id>.yaml) or a yaml path."""
    if league_arg.endswith((".yaml", ".yml")) or os.sep in league_arg:
        league_path = league_arg if os.path.isabs(league_arg) \
            else os.path.join(HERE, league_arg)
    else:
        league_path = os.path.join(HERE, "leagues", "%s.yaml" % league_arg)
    if not os.path.exists(league_path):
        raise ValueError("league file not found: %s" % league_path)
    league = LeagueConfig.load(league_path)
    csv_path = league.rankings_csv if os.path.isabs(league.rankings_csv) \
        else os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        raise ValueError(missing_rankings_message(league, csv_path))
    players = load_players(csv_path)
    state = DraftState(league, players)
    return state, Matcher(players)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.keeper",
        description="keep-vs-throwback calculator (VBD vs the forfeited pick)")
    ap.add_argument("player", nargs="?", default=None,
                    help="player to evaluate (fuzzy-matched)")
    ap.add_argument("--cost-round", type=int, dest="cost_round", default=None,
                    help="round the keeper costs (the pick you forfeit)")
    ap.add_argument("--league", default="yahoo-main",
                    help="league id under leagues/ (or a yaml path)")
    ap.add_argument("--list", dest="list_mode", action="store_true",
                    help="batch verdicts from the keepers file")
    ap.add_argument("--keepers", default=DEFAULT_KEEPERS,
                    help="keepers yaml for --list (default data/keepers.yaml)")
    ap.add_argument("--slot", type=int, default=None,
                    help="override my_slot (1-based draft position)")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))

    if not args.list_mode and (not args.player or not args.cost_round):
        ap.error("need \"<player>\" --cost-round N (or --list)")

    try:
        state, matcher = build_state(args.league)
    except ValueError as exc:
        print("ERROR: %s" % exc)
        return 1
    league = state.league
    slot, assumed = resolve_slot(league, args.slot)

    print("KEEPER CALL  %s  (%d-team, slot %d)" % (league.name, league.teams,
                                                   slot))
    if assumed:
        print("NOTE: my_slot is not set for league %s - ASSUMING mid-slot %d."
              % (league.id, slot))
        print("      Set my_slot in %s (or pass --slot) for real numbers."
              % (league.path or "the league yaml"))
    print()

    if args.list_mode:
        try:
            rows = load_keepers(args.keepers)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print("ERROR: %s" % exc)
            return 1
        if not rows:
            print("no keepers listed in %s - add entries like:" % args.keepers)
            print("  players:")
            print("    - name: Puka Nacua")
            print("      cost_round: 5")
            return 1
        jobs = rows
    else:
        jobs = [{"name": args.player, "cost_round": args.cost_round}]

    repl = replacement_levels(state)
    failures = 0
    for job in jobs:
        m = matcher.match(job["name"])
        if m is None:
            print("ERROR: no player in the pool matches %r" % job["name"])
            failures += 1
            continue
        try:
            v = evaluate(state, m.player, job["cost_round"], slot, repl=repl)
        except ValueError as exc:
            print("ERROR: %s" % exc)
            failures += 1
            continue
        for line in verdict_lines(v):
            print(line)
        print()

    for line in _caveat_lines():
        print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
