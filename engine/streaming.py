"""DEF/K streaming: rank available defenses and kickers over a horizon.

    python -m engine.streaming --league yahoo-main --week N [--horizon 3]

For each of the next H weeks the board scores every DEF and K that is not
KNOWN to be on my roster, from three transparent drivers (Subvertadown-spec:
every number that moves a rank is printed next to it):

  * weekly projection  - engine/weekly.fetch_weekly_projections (ESPN kona
    per-week split, Sleeper fill).
  * matchup adjustment - Vegas implied totals from fetch_game_lines. A LOW
    opposing implied total is a GOOD defense matchup (fewer expected points
    to give back, more bad-offense turnovers); a HIGH own implied total is a
    good kicker matchup (more drives that end in kicks). Lines are optional
    garnish: a missing line means adj 0.0 and a "no line" note, never an
    error.
  * schedule           - a team absent from the week's schedule is on bye
    and drops off that week's board entirely.

MULTI-WEEK PATHS: the horizon planner shows the best single pickup held
across all H weeks vs the optimal week-by-week chain, where every pickup
beyond the first costs MOVE_COST points (churn tax: a roster spot, a waiver
claim, FAAB attention). The chain is a tiny dynamic program, not greedy -
holding one defense two weeks beats flipping weekly whenever the flip's
edge is smaller than the move tax. Ties prefer fewer moves, so a huge move
cost degenerates the chain into the hold, by construction. The greedy
per-week chain is printed too so the tax's effect is visible.

AVAILABILITY IS POSITIVE-ONLY (exposure.py semantics): data/rosters/
<league>.yaml lists players KNOWN to be on my roster - partial by design -
and other teams' rosters are unknown until host APIs land (ESPN reads need
cookies, RUNBOOK A3; guarded here, never fatal). "Available" therefore
means "not known to be taken", and every run carries a banner saying so.

HUMILITY LEDGER: each run appends its own top DEF and K picks for the
target week to data/streaming_log.jsonl. Once real weeks complete and
actuals land (the weekly layer exposes them later), a backfill can fill
"actual"/"baseline_actual" per entry and the summary prints our hit-rate vs
the 'just keep the highest-owned defense' baseline. For now the ledger
records; without ownership data the baseline is logged as unknown - never
guessed.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import yaml

try:
    from engine import weekly
    from engine.models import LeagueConfig
    from engine.projections import name_key
    from engine.exposure import DEFAULT_DIR as ROSTER_DIR
except ImportError:  # run directly as `python engine/streaming.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import weekly
    from engine.models import LeagueConfig
    from engine.projections import name_key
    from engine.exposure import DEFAULT_DIR as ROSTER_DIR

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(HERE, "data", "streaming_log.jsonl")

STREAM_POS = ("DEF", "K")
AVG_IMPLIED = 22.5          # league-average implied team total (half of ~45)
DEF_PTS_PER_POINT = 0.35    # DEF fantasy pts per point of opposing implied
K_PTS_PER_POINT = 0.15      # K fantasy pts per point of own implied
MOVE_COST = 1.0             # churn tax per pickup beyond the first


# --- weekly board -----------------------------------------------------------

def build_board(week: int, scoring: str = "ppr",
                proj: Optional[Dict] = None, sched: Optional[Dict] = None,
                lines: Optional[Dict] = None, force: bool = False,
                quiet: bool = True) -> Dict[str, List[Dict]]:
    """{"DEF": [cand...], "K": [cand...]} sorted best-first for one week.

    Pure when proj/sched/lines are injected (tests); otherwise fetches via
    engine/weekly. Candidate: {key, name, pos, team, opp, home, proj,
    implied, adj, score, note}. implied is the driver total (opponent's for
    DEF, own for K) or None when no line is filed -> adj 0.0, note
    "no line". Teams on bye (absent from the schedule) are dropped.
    """
    if proj is None:
        proj = weekly.fetch_weekly_projections(week, scoring, force=force,
                                               quiet=quiet)
    if sched is None:
        sched = weekly.fetch_schedule(week, force=force)
    if lines is None:
        lines = weekly.fetch_game_lines(week, force=force, quiet=quiet)

    board = {"DEF": [], "K": []}
    for key, rec in proj.items():
        pos = rec.get("pos")
        if pos not in STREAM_POS:
            continue
        team = rec.get("team", "")
        game = sched.get(team)
        if not team or game is None:      # unknown team or on bye
            continue
        opp = game["opponent"]
        if pos == "DEF":
            implied = (lines.get(opp) or {}).get("implied_total")
            per_pt, sign = DEF_PTS_PER_POINT, -1.0
            name = "%s D/ST" % team
        else:
            implied = (lines.get(team) or {}).get("implied_total")
            per_pt, sign = K_PTS_PER_POINT, 1.0
            name = key.title()
        if implied is None:
            adj, note = 0.0, "no line"
        else:
            adj = round(sign * (implied - AVG_IMPLIED) * per_pt, 2)
            note = ""
        board[pos].append({
            "key": key, "name": name, "pos": pos, "team": team,
            "opp": opp, "home": bool(game["home"]),
            "proj": round(float(rec["proj"]), 2), "implied": implied,
            "adj": adj, "score": round(float(rec["proj"]) + adj, 2),
            "note": note})
    for pos in board:
        board[pos].sort(key=lambda c: (-c["score"], c["key"]))
    return board


def filter_available(board: Dict[str, List[Dict]], roster_keys: Set[str],
                     whitelist: Optional[Set[str]] = None
                     ) -> Dict[str, List[Dict]]:
    """Drop candidates KNOWN to be on my roster; optional host whitelist.

    POSITIVE-ONLY: roster_keys holds players known-rostered from a partial
    file - a candidate that survives this filter may still be taken (by me
    or anyone else). DEF names differ across hosts ('Seahawks D/ST' vs
    'Seattle Seahawks'), so a defense is also excluded when its nickname
    token appears in any roster name. whitelist, when a host read worked,
    keeps only keys the host says are free agents.
    """
    roster_tokens = set()
    for k in roster_keys:
        roster_tokens.update(k.split())
    out = {}
    for pos, cands in board.items():
        kept = []
        for c in cands:
            if c["key"] in roster_keys:
                continue
            if pos == "DEF":
                nick = c["key"].split()[0] if c["key"] else ""
                if nick and nick in roster_tokens:
                    continue
            if whitelist is not None and c["key"] not in whitelist:
                continue
            kept.append(c)
        out[pos] = kept
    return out


# --- my roster / host reads (guarded) ---------------------------------------

def _roster_keys(league_id: str, dirpath: Optional[str] = None
                 ) -> Tuple[Set[str], Optional[Tuple[str, int, int]]]:
    """(known-roster name_keys, (display, known, size)) from the roster file.

    Same file exposure.py reads (data/rosters/<league>.yaml) - THE roster
    source of truth until host APIs land. Missing file -> (set(), None):
    no information, and the caller's banner must say so.
    """
    path = os.path.join(dirpath or ROSTER_DIR, "%s.yaml" % league_id)
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
    except (IOError, OSError, yaml.YAMLError):
        return set(), None
    if not isinstance(data, dict) or not isinstance(data.get("players"), list):
        return set(), None
    keys = set()
    for raw in data["players"]:
        nm = str(raw.get("name", "")) if isinstance(raw, dict) else str(raw or "")
        k = name_key(nm)
        if k:
            keys.add(k)
    display = str(data.get("name") or league_id)
    try:
        size = int(data.get("size") or 0) or len(data["players"])
    except (TypeError, ValueError):
        size = len(data["players"])
    return keys, (display, len(keys), size)


def _espn_free_agent_keys(league, quiet: bool = False) -> Optional[Set[str]]:
    """Host free-agent whitelist for other-team filtering, or None.

    Only meaningful for ESPN leagues, and engine/espn.py's cookie reads are
    untested live with no cookies on file - so every failure degrades to
    None ("no host info") with a RUNBOOK A3 pointer, never an exception.
    """
    if getattr(league, "platform", "") != "espn":
        return None
    try:
        from engine import espn as espn_mod
        lg = espn_mod.connect()
        keys = set()
        for pos in ("D/ST", "K"):
            for p in espn_mod.free_agents(lg, size=120, position=pos):
                nm = getattr(p, "name", "") or ""
                if nm:
                    keys.add(name_key(nm))
        return keys or None
    except Exception as exc:
        if not quiet:
            print("  streaming: other-team filtering skipped - needs cookies "
                  "(RUNBOOK A3): %s" % exc)
        return None


def _baseline_defense(league) -> Tuple[Optional[str], str]:
    """(name_key of the highest-owned defense, note) for the humility ledger.

    'Just keep the highest-owned defense' needs ownership data no source
    provides yet (Yahoo API not wired; ESPN percent_owned needs cookies,
    RUNBOOK A3). Positive-only honesty: record unknown, never guess.
    """
    platform = getattr(league, "platform", "") or "unknown"
    if platform != "espn":
        return None, ("baseline unknown - %s ownership API not wired"
                      % platform)
    try:
        from engine import espn as espn_mod
        po = getattr(espn_mod, "percent_owned", None)
        if po is None:
            return None, ("baseline unknown - engine.espn has no "
                          "percent_owned yet (RUNBOOK A3)")
        lg = espn_mod.connect()
        rows = po(lg, position="D/ST")
        if not rows:
            return None, "baseline unknown - empty ownership read"
        top = max(rows, key=lambda r: r.get("percent_owned", 0.0))
        return name_key(top.get("name", "")), "highest-owned defense"
    except Exception as exc:
        return None, ("baseline unknown - ESPN read failed, needs cookies "
                      "(RUNBOOK A3): %s" % exc)


# --- multi-week planning (pure) ---------------------------------------------
# week_maps: [(week, {key: candidate})] for ONE position across the horizon.
# A key absent from a week's map (bye / no projection) scores 0.0 that week.

def best_hold(week_maps: List[Tuple[int, Dict[str, Dict]]]) -> Optional[Dict]:
    """Best single pickup held across the whole horizon (one move total)."""
    totals = {}
    for _, m in week_maps:
        for k, c in m.items():
            totals[k] = totals.get(k, 0.0) + c["score"]
    if not totals:
        return None
    key = sorted(totals, key=lambda k: (-totals[k], k))[0]
    per_week = [(w, m.get(key)) for w, m in week_maps]
    return {"key": key, "total": round(totals[key], 2), "per_week": per_week,
            "weeks_covered": sum(1 for _, c in per_week if c is not None)}


def _score(m: Dict[str, Dict], k: str) -> float:
    c = m.get(k)
    return c["score"] if c else 0.0


def _count_moves(path: List[Tuple[int, Optional[str], float]]) -> int:
    moves, held = 0, None
    for _, k, _ in path:
        if k is not None and k != held:
            moves += 1
            held = k
    return moves


def _chain_summary(path, move_cost: float) -> Dict:
    gross = round(sum(s for _, _, s in path), 2)
    moves = _count_moves(path)
    return {"path": path, "gross": gross, "moves": moves,
            "net": round(gross - move_cost * max(0, moves - 1), 2)}


def greedy_chain(week_maps, move_cost: float = MOVE_COST) -> Optional[Dict]:
    """Take each week's top candidate, then pay the move tax. The naive
    chain the DP in best_chain() is judged against."""
    if not any(m for _, m in week_maps):
        return None
    path = []
    for w, m in week_maps:
        if not m:
            path.append((w, None, 0.0))
            continue
        k = sorted(m, key=lambda k: (-m[k]["score"], k))[0]
        path.append((w, k, m[k]["score"]))
    return _chain_summary(path, move_cost)


def _better(a: Tuple, b: Optional[Tuple]) -> bool:
    """DP state order: higher net, then FEWER moves, then stable key order.

    Strict - so 'stay' wins ties against 'switch', and with a big enough
    move cost the optimal chain collapses into the hold, by construction.
    """
    if b is None:
        return True
    if abs(a[0] - b[0]) > 1e-9:
        return a[0] > b[0]
    if a[1] != b[1]:
        return a[1] < b[1]
    return a[2] < b[2]


def best_chain(week_maps, move_cost: float = MOVE_COST) -> Optional[Dict]:
    """Optimal week-by-week path when every pickup beyond the first costs
    move_cost points. Tiny DP over (week, held player); holding through a
    bye week scores 0.0 but costs no move."""
    keys = sorted(set(k for _, m in week_maps for k in m))
    if not keys:
        return None
    w0, m0 = week_maps[0]
    states = dict((k, (_score(m0, k), 1, [k])) for k in keys)
    for _, m in week_maps[1:]:
        best_prev = None
        for k in keys:
            if _better(states[k], best_prev):
                best_prev = states[k]
        nxt = {}
        for k in keys:
            s = _score(m, k)
            stay = (states[k][0] + s, states[k][1], states[k][2] + [k])
            switch = (best_prev[0] - move_cost + s, best_prev[1] + 1,
                      best_prev[2] + [k])
            nxt[k] = switch if _better(switch, stay) else stay
        states = nxt
    final = None
    for k in keys:
        if _better(states[k], final):
            final = states[k]
    path = [(w, k, _score(m, k))
            for (w, m), k in zip(week_maps, final[2])]
    return _chain_summary(path, move_cost)


def plan_position(week_maps, move_cost: float = MOVE_COST) -> Optional[Dict]:
    """Hold vs optimal chain vs greedy chain; recommend chain only when its
    net (after move tax) strictly beats the hold's total."""
    hold = best_hold(week_maps)
    if hold is None:
        return None
    chain = best_chain(week_maps, move_cost)
    greedy = greedy_chain(week_maps, move_cost)
    rec = "chain" if chain["net"] > hold["total"] + 1e-9 else "hold"
    return {"hold": hold, "chain": chain, "greedy": greedy,
            "recommendation": rec}


# --- humility ledger --------------------------------------------------------

def log_top_pick(entry: Dict, path: Optional[str] = None) -> str:
    """Append one pick record to the jsonl ledger; returns the path used.

    Tests MUST redirect streaming.LOG_PATH to a tempdir (same discipline as
    save_state.SAVE_DIR) - the production ledger is an append-only record
    of what we recommended before outcomes were known.
    """
    path = path or LOG_PATH
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return path


def read_ledger(path: Optional[str] = None) -> List[Dict]:
    """All parseable ledger entries; a corrupt line is skipped, not fatal."""
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def ledger_summary(entries: List[Dict]) -> str:
    """Hit-rate vs the highest-owned-defense baseline, once actuals exist.

    An entry is scoreable when a backfill has filled both "actual" (our
    pick's real points) and "baseline_actual". Until then the ledger just
    records - saying "no scored weeks yet" is the honest summary.
    """
    scored = [e for e in entries
              if e.get("actual") is not None
              and e.get("baseline_actual") is not None]
    if not scored:
        return ("humility ledger: %d pick(s) logged; no scored weeks yet - "
                "hit-rate vs the keep-the-highest-owned-defense baseline "
                "starts once real-week actuals land." % len(entries))
    hits = sum(1 for e in scored
               if float(e["actual"]) >= float(e["baseline_actual"]))
    return ("humility ledger: our pick met or beat the highest-owned "
            "baseline in %d/%d scored week(s) (%.0f%%); %d unscored."
            % (hits, len(scored), 100.0 * hits / len(scored),
               len(entries) - len(scored)))


# --- rendering --------------------------------------------------------------

def _fmt_opp(c: Dict) -> str:
    return ("vs %s" if c["home"] else "@ %s") % c["opp"]


def _fmt_driver(c: Dict) -> str:
    label = "opp imp" if c["pos"] == "DEF" else "own imp"
    if c["implied"] is None:
        return "%s   --  adj  0.00 (no line)" % label
    return "%s %4.1f  adj %+5.2f" % (label, c["implied"], c["adj"])


def _print_week_table(week: int, pos: str, cands: List[Dict],
                      top: int) -> None:
    print("\n  WEEK %d %s - top %d available (proj + matchup adj)"
          % (week, pos, min(top, len(cands))))
    if not cands:
        print("    (no candidates - projections or schedule missing)")
        return
    for i, c in enumerate(cands[:top], 1):
        print("   %2d. %-22s %-7s proj %5.2f  %s  -> %5.2f"
              % (i, c["name"], _fmt_opp(c), c["proj"], _fmt_driver(c),
                 c["score"]))


def _print_plan(pos: str, plan: Optional[Dict], names: Dict[str, str],
                weeks: List[int], move_cost: float) -> None:
    print("\n  MULTI-WEEK PLAN - %s, weeks %d-%d (move tax %.1f pt per "
          "pickup beyond the first)" % (pos, weeks[0], weeks[-1], move_cost))
    if plan is None:
        print("    (no candidates across the horizon)")
        return
    hold = plan["hold"]
    parts = []
    for w, c in hold["per_week"]:
        parts.append("wk%d %.2f (%s)" % (w, c["score"], _fmt_opp(c))
                     if c else "wk%d bye/none (0.0)" % w)
    print("    HOLD  %-18s %6.2f pts, 1 move" %
          (names.get(hold["key"], hold["key"]), hold["total"]))
    print("          %s" % " | ".join(parts))
    chain = plan["chain"]
    print("    CHAIN %6.2f gross - %.1f move tax (%d move(s)) = %.2f net"
          % (chain["gross"], move_cost * max(0, chain["moves"] - 1),
             chain["moves"], chain["net"]))
    print("          %s" % " | ".join(
        "wk%d %s %.2f" % (w, names.get(k, k or "(none)"), s)
        for w, k, s in chain["path"]))
    greedy = plan["greedy"]
    if greedy and greedy["path"] != chain["path"]:
        print("          (greedy per-week chain: %.2f gross, %d moves -> "
              "%.2f net - the tax is why it loses)"
              % (greedy["gross"], greedy["moves"], greedy["net"]))
    if plan["recommendation"] == "chain":
        print("    VERDICT: chain, nets %+.2f over the hold"
              % (chain["net"] - hold["total"]))
    else:
        print("    VERDICT: hold %s - chaining does not clear the move tax"
              % names.get(hold["key"], hold["key"]))


def _banner(league, coverage, whitelist) -> str:
    lines = ["  AVAILABILITY IS BEST-EFFORT (positive-only roster data):"]
    if coverage is None:
        lines.append("    * no roster file for this league (data/rosters/) "
                     "- NOTHING is excluded; every candidate may be taken.")
    else:
        display, known, size = coverage
        lines.append("    * %s roster known %d/%d - a candidate NOT "
                     "excluded may still be rostered (by me or anyone else)."
                     % (display, known, size))
    if whitelist is None:
        platform = getattr(league, "platform", "") or "unknown"
        if platform == "espn":
            lines.append("    * other-team rosters unknown - ESPN reads "
                         "need cookies (RUNBOOK A3).")
        else:
            lines.append("    * other-team rosters unknown - %s API not "
                         "wired; no flag does NOT mean free agent."
                         % platform)
    else:
        lines.append("    * host free-agent list applied (%d keys)."
                     % len(whitelist))
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.streaming",
        description="Rank available DEF/K streamers over the next few weeks.")
    ap.add_argument("--league", default="yahoo-main", help="league id")
    ap.add_argument("--week", type=int, required=True, help="first week (1-18)")
    ap.add_argument("--horizon", type=int, default=3,
                    help="weeks to plan (default 3)")
    ap.add_argument("--scoring", default=None,
                    help="ppr/half/std (default: the league's own)")
    ap.add_argument("--top", type=int, default=8,
                    help="rows per weekly table (default 8)")
    ap.add_argument("--move-cost", type=float, default=MOVE_COST,
                    help="points charged per pickup beyond the first")
    ap.add_argument("--no-log", action="store_true",
                    help="skip the humility-ledger append")
    ap.add_argument("--force", action="store_true", help="refetch all feeds")
    args = ap.parse_args(argv)

    league_path = os.path.join(HERE, "leagues", "%s.yaml" % args.league)
    if not os.path.exists(league_path):
        print("no league config: %s" % league_path)
        return 1
    league = LeagueConfig.load(league_path)
    scoring = args.scoring or league.scoring_label()

    first = max(1, min(args.week, weekly.FINAL_WEEK))
    last = min(first + max(1, args.horizon) - 1, weekly.FINAL_WEEK)
    weeks = list(range(first, last + 1))

    roster_keys, coverage = _roster_keys(league.id)
    whitelist = _espn_free_agent_keys(league)

    print("STREAMING - %s, weeks %d-%d, %s scoring"
          % (league.name, first, last, scoring))
    print(_banner(league, coverage, whitelist))

    week_boards = []       # [(week, filtered board)]
    for w in weeks:
        try:
            board = build_board(w, scoring, force=args.force, quiet=True)
        except RuntimeError as exc:
            print("\n  WEEK %d: feeds unavailable (%s) - skipped" % (w, exc))
            week_boards.append((w, {"DEF": [], "K": []}))
            continue
        board = filter_available(board, roster_keys, whitelist)
        week_boards.append((w, board))
        for pos in STREAM_POS:
            _print_week_table(w, pos, board[pos], args.top)

    names = {}
    for _, board in week_boards:
        for pos in STREAM_POS:
            for c in board[pos]:
                names.setdefault(c["key"], c["name"])

    plans = {}
    for pos in STREAM_POS:
        week_maps = [(w, dict((c["key"], c) for c in board[pos]))
                     for w, board in week_boards]
        plans[pos] = plan_position(week_maps, args.move_cost)
        _print_plan(pos, plans[pos], names, weeks, args.move_cost)

    if not args.no_log:
        base_key, base_note = _baseline_defense(league)
        first_board = week_boards[0][1]
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        for pos in STREAM_POS:
            cands = first_board[pos]
            if not cands:
                continue
            top = cands[0]
            log_top_pick({
                "ts": stamp, "season": weekly.SEASON, "week": first,
                "league": league.id, "scoring": scoring, "pos": pos,
                "pick_key": top["key"], "pick_name": top["name"],
                "team": top["team"], "opp": top["opp"],
                "proj": top["proj"], "adj": top["adj"],
                "score": top["score"],
                "baseline_key": base_key, "baseline_note": base_note,
                "actual": None, "baseline_actual": None})
        print("\n  logged week-%d top DEF/K picks to %s"
              % (first, os.path.relpath(LOG_PATH, HERE)))
    print("  " + ledger_summary(read_ledger()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
