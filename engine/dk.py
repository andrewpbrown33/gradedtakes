"""DEF/K weekly call: HOLD what I have, or STREAM the best one on the wire?

    python -m engine.dk --league espn-1 --week 1

THE QUESTION. A defense or a kicker is not a start/sit decision against my
own bench - I roster one of each. The decision every week is: does the
DEF/K I hold beat the best one I could actually pick up, given who each
one plays this week? So the Board/Home rows for DST and K stop carrying a
generic "START 83%" and carry this instead:

    HOLD LAC                          (mine is as good as anything free)
    STREAM NE D/ST +1.6 over LAC      (a free one clearly beats mine)
    TOSS-UP ...                       (inside the band, or unverified)
    NO READ                           (the board could not be built)

SCORES ARE STREAMING'S, NOT A SECOND MODEL. Every score here is
engine/streaming.build_board's weekly score for that week: the merged
weekly projection (ESPN kona per-week split, Sleeper fill) plus the Vegas
implied-total adjustment streaming already applies - a DEF gains
DEF_PTS_PER_POINT for every point the OPPONENT's implied total sits below
the league-average total (a low-scoring opponent is the whole matchup
argument for a defense: fewer points given back, more bad-offense
turnovers), a K gains K_PTS_PER_POINT per point his OWN team's implied
total sits above it (more drives that end in kicks). Lines are optional
garnish; a game with no line adjusts 0.0 and says "no line". Nothing is
re-weighted here, and this module never appends to the streaming humility
ledger (build_board does not log; only the streaming CLI does).

OPPONENT CONTEXT, per position, printed next to every candidate:
  * DST  the opponent OFFENSE: its Vegas implied total and the resulting
         adjustment. That is the read streaming uses and the one that
         moves the score; no points-scored table is invented on top of it.
  * K    the opponent DEFENSE from engine/matchups.py's points-allowed
         table (sum of PA/game to QB/RB/WR/TE, ranked - softer = more
         drives that stall in range), which is a 2025-basis prior today
         and says so; plus the VENUE from the nflverse schedule's `roof`
         column ("dome" / "outdoors", with the stadium) - and "venue not
         filed" when nflverse left it blank, which it does for a few games.
         Neither moves the score; both are context on the line.

AVAILABILITY IS THE POINT. A candidate is offered only when it is
genuinely available: not on my roster, not on another ESPN team
(waivers.espn_taken_keys - applied ONLY to the ESPN league, a platform
guard this module re-checks itself so a Yahoo league never sees an ESPN
fact), and not on a rival roster (trades.load_rival_view). Then
waivers.claim_gate decides whether a claim can be honest at all: when
rival rosters are UNKNOWN (yahoo-main today) the call still computes, the
best candidate is still named, but the verdict is downgraded from STREAM
to TOSS-UP and the reason carries the literal text
"candidates unverified - rival rosters unknown". A player who may already
be rostered is never recommended as a claim.

THRESHOLDS - judgment calls, stated so they can be argued with:
  * delta = best available score - held score, on streaming's weekly
    scale (fantasy points).
  * STREAM  when delta >= STREAM_MARGIN (DST 2.0, K 1.5). Two points is
    roughly a third of a DEF's weekly sigma (lineup.DEFAULT_SIGMA 6.5) -
    anything thinner is projection noise dressed as a decision - and a
    kicker's tighter distribution (sigma 4.8) earns a tighter band.
    Additionally the candidate must survive the league's waiver mode:
    FAAB leagues need a band above "pass" (waivers.faab_band on the delta,
    which any positive delta clears); priority leagues stream too, but
    the cost line says whether the edge is worth BURNING priority
    (delta >= waivers.PRIORITY_GAP) or whether to wait for him to clear
    to free agency - a streamer rarely justifies the queue.
  * TOSS-UP when TOSS_MIN <= delta < STREAM_MARGIN (DST 0.75, K 0.5): a
    real but thin edge; either call is defensible and the cost decides.
  * HOLD    otherwise (delta below TOSS_MIN, including negative).
  * A held DEF/K on BYE or without a projection scores 0.0 - the delta is
    then the whole candidate score, which is the right answer: a bye-week
    defense needs replacing whatever the wire looks like.
  * CONFIDENCE (the pct the consensus and Home rows show) is
    P(held outscores best) under lineup.p_first_beats with lineup's own
    DEF/K sigma - the same normal-approximation every lineup verdict
    uses. It is deliberately humble: a +2.0 DEF edge is ~41/59, not
    17/83, because one-week DEF scoring is that swingy.
  * FAAB cost: a one-week stream's delta is put straight onto the waiver
    score scale (1 pt = 1 pt) and banded with waivers.faab_band, so +2.0
    reads "1-3%" of budget and +5 reads "4-8%". Streamers are cheap by
    design; a band, never a bid.

READ-ONLY. This module writes nothing: no streaming-ledger append (the
board is built, never logged), no %owned momentum baseline (owned_momentum
is never called), no source ledger. Feed caches under data/cache/ refill
on their normal windows through the modules that own them.

API (stable - engine/lineup, consensus, home, board and lineup_page import
it):

    weekly_call(league, week, my_roster_players, players, matcher,
                force=False, *, board=None, rival=None, taken=None,
                secrets_path=None, venues=None, pa_table=None)
        -> {"DST": Call, "K": Call}
    Call: {pos, held, held_key, held_short, held_score, held_proj,
           held_opp, held_opp_note, best, best_key, best_short,
           best_score, best_proj, best_opp, best_opp_note, delta,
           verdict ("HOLD"|"STREAM"|"TOSS-UP"|"NO READ"), reason, text,
           cost, confidence (P best beats held, 0-100), held_pct
           (P held beats best), unverified (bool), gate_reason,
           candidates [<= CAND_LIMIT dicts: name, key, team, opp, home,
           proj, adj, score, opp_note], basis, coverage_note,
           excluded {mine, espn, rival}, mode}
    verdict_text(call)      "HOLD LAC" / "STREAM NE D/ST +1.6 over LAC"
    consensus_vote(call)    "start" | "sit" | "flex" | None
    consensus_verdict(call) ("START"|"SIT"|"EVEN", start-ward pct) | None
    lineup_verdict(call, slot)  a lineup.build verdict dict for the slot
    inbox_item_text(call)   (text, detail) for the Home inbox
    board_line(call)        the one-line "held vs best available"

The keyword seams (board, rival, taken, venues, pa_table) exist so tests
drive the call from synthetic fixtures with no network; production leaves
them None and the module reads through the owning modules.
"""

import argparse
import os
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

try:
    from engine import lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import streaming, trades, waivers, weekly
    from engine.models import LeagueConfig, load_players
    from engine.projections import name_key, norm_team
except ImportError:  # run directly as `python engine/dk.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import streaming, trades, waivers, weekly
    from engine.models import LeagueConfig, load_players
    from engine.projections import name_key, norm_team

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SLOTS = ("DST", "K")
POS_OF = {"DST": "DEF", "K": "K"}       # call slot -> streaming/pool position
SLOT_OF = {"DEF": "DST", "K": "K"}      # pool position -> call slot

# Judgment calls - see the module docstring.
STREAM_MARGIN = {"DST": 2.0, "K": 1.5}
TOSS_MIN = {"DST": 0.75, "K": 0.5}
CAND_LIMIT = 5
UNVERIFIED = "candidates unverified - rival rosters unknown"
VERDICTS = ("HOLD", "STREAM", "TOSS-UP", "NO READ")

BASIS = ("engine/streaming weekly board: merged weekly projection (ESPN "
         "kona per-week split, Sleeper fill) + Vegas implied-total "
         "adjustment (DEF %.2f pts per point the OPPONENT's implied total "
         "sits below %.1f; K %.2f per point the OWN total sits above it); "
         "lines are nflverse games.csv opening-ish numbers, refreshed "
         "nightly - a game with no line adjusts 0.0"
         % (streaming.DEF_PTS_PER_POINT, streaming.AVG_IMPLIED,
            streaming.K_PTS_PER_POINT))


# --- context reads (each guarded, each optional) ----------------------------

def venue_notes(week: int, rows: Optional[List[Dict]] = None,
                force: bool = False) -> Dict[str, str]:
    """{team: 'dome (SoFi Stadium)' | 'outdoors (Lumen Field)' | 'venue not
    filed'} for every team playing that week, from the nflverse schedule's
    roof/stadium columns. A blank roof is reported as not filed, never
    guessed from the stadium name."""
    if rows is None:
        rows = weekly._schedule_rows(force=force)
    out: Dict[str, str] = {}
    for r in weekly._week_games(rows, weekly.SEASON, int(week)):
        roof = str(r.get("roof") or "").strip().lower()
        stadium = str(r.get("stadium") or "").strip()
        if roof:
            note = roof + (" (%s)" % stadium if stadium else "")
        else:
            note = "venue not filed"
        for side in ("home_team", "away_team"):
            team = norm_team(r.get(side, ""))
            if team:
                out[team] = note
    return out


def defense_reads(table: Optional[Dict]) -> Dict[str, Dict]:
    """{defense: {'pa': pts/game allowed to QB+RB+WR+TE, 'rank', 'of'}}
    from engine/matchups.py's PA table (rank 1 = most allowed = softest).
    An empty dict when the table is absent or carries no positions."""
    if not table:
        return {}
    totals: Dict[str, float] = {}
    for pos, block in (table.get("by_pos") or {}).items():
        for team, cell in (block.get("defenses") or {}).items():
            try:
                totals[team] = totals.get(team, 0.0) + float(cell["pa_per_game"])
            except (KeyError, TypeError, ValueError):
                continue
    if not totals:
        return {}
    order = sorted(totals, key=lambda t: (-totals[t], t))
    return dict((t, {"pa": round(totals[t], 1), "rank": i + 1,
                     "of": len(order)}) for i, t in enumerate(order))


def _fmt_opp(c: Dict) -> str:
    return ("vs %s" if c.get("home") else "@ %s") % (c.get("opp") or "?")


def opp_note(cand: Dict, slot: str, venues: Optional[Dict[str, str]] = None,
             dreads: Optional[Dict[str, Dict]] = None,
             basis: str = "") -> str:
    """The one-line opponent read for a candidate, per the docstring."""
    bits = [_fmt_opp(cand)]
    imp = cand.get("implied")
    if slot == "DST":
        if imp is None:
            bits.append("%s implied: no line filed, adj 0.00"
                        % (cand.get("opp") or "opp"))
        else:
            bits.append("%s offense implied %.1f (low = good for a DEF), "
                        "adj %+.2f" % (cand.get("opp") or "opp", imp,
                                       cand.get("adj") or 0.0))
        return " · ".join(bits)
    # K: own implied total drives the score; the opponent defense and the
    # venue are context.
    if imp is None:
        bits.append("%s implied: no line filed, adj 0.00"
                    % (cand.get("team") or "own"))
    else:
        bits.append("%s offense implied %.1f, adj %+.2f"
                    % (cand.get("team") or "own", imp,
                       cand.get("adj") or 0.0))
    d = (dreads or {}).get(cand.get("opp") or "")
    if d:
        bits.append("%s DEF allowed %.1f pts/g to QB/RB/WR/TE (%d%s-most "
                    "of %d%s)" % (cand.get("opp"), d["pa"], d["rank"],
                                  _suffix(d["rank"]), d["of"],
                                  (", " + basis) if basis else ""))
    else:
        bits.append("no opponent-defense read")
    venue = (venues or {}).get(cand.get("team") or "")
    bits.append(venue if venue else "venue unknown")
    return " · ".join(bits)


def _suffix(n: int) -> str:
    n = int(n)
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# --- key bridging -----------------------------------------------------------
# Pool / rival / ESPN keys are Player.key ("la chargers defense|DEF",
# "cameron dicker|K"); streaming's board keys are name_key of the feed's
# own name ("chargers dst", "cameron dicker"). A defense is bridged by its
# NFL team, a kicker by his normalized name.

def _bridge(keys: Sequence[str], players: Sequence) -> Tuple[Set[str], Set[str]]:
    """(DEF teams, K name keys) for a set of Player.keys drawn from a pool."""
    by_key = dict((p.key, p) for p in players)
    teams: Set[str] = set()
    nkeys: Set[str] = set()
    for k in keys:
        p = by_key.get(k)
        if p is None:
            nk, _, pos = str(k).partition("|")
            if pos == "K" and nk:
                nkeys.add(nk)
            continue
        if p.pos == "DEF" and p.team:
            teams.add(norm_team(p.team))
        elif p.pos == "K":
            nkeys.add(p.nkey)
    return teams, nkeys


def _is_player(cand: Dict, slot: str, player) -> bool:
    if slot == "DST":
        return bool(player.team) and norm_team(cand.get("team", "")) == \
            norm_team(player.team)
    return cand.get("key") == player.nkey


def _short(player_or_cand, slot: str) -> str:
    """'LAC' for a defense, the surname for a kicker; from a Player or a
    board candidate alike."""
    if hasattr(player_or_cand, "surname"):
        return player_or_cand.surname()
    c = player_or_cand
    if slot == "DST":
        return c.get("team") or c.get("name") or "?"
    parts = str(c.get("name") or "").split()
    return parts[-1] if parts else "?"


def _cand_view(c: Dict, note: str) -> Dict:
    return {"name": c["name"], "key": c["key"], "team": c["team"],
            "opp": c["opp"], "home": bool(c.get("home")),
            "proj": c["proj"], "adj": c["adj"], "score": c["score"],
            "opp_note": note}


# --- the decision (pure) ----------------------------------------------------

def confidence(held_score: Optional[float], best_score: Optional[float],
               slot: str, sigmas: Optional[Dict[str, float]] = None) -> int:
    """P(best beats held) in percent, lineup's normal approximation."""
    sig = (sigmas or lineup_mod.DEFAULT_SIGMA).get(POS_OF[slot], 6.0)
    a = float(best_score or 0.0)
    b = float(held_score or 0.0)
    return int(round(100.0 * lineup_mod.p_first_beats(a, b, sig, sig)))


def cost_line(league, delta: float) -> Tuple[bool, str]:
    """(survives the waiver mode, the cost line). See the docstring."""
    mode = str(getattr(league, "waiver_mode", "faab") or "faab").lower()
    if mode == "priority":
        burn = delta >= waivers.PRIORITY_GAP
        try:
            queue = waivers.priority_position_note(league)
        except Exception:  # noqa: BLE001 - a note is never worth the call
            queue = "queue position unknown"
        return True, ("costs a waiver claim - priority league: %s (edge %+.1f "
                      "vs the %.1f-pt burn bar); %s"
                      % ("worth burning priority" if burn
                         else "NOT worth burning priority - wait for him to "
                              "clear to free agency", delta,
                         waivers.PRIORITY_GAP, queue))
    band = waivers.faab_band(max(0.0, delta))
    return band != "pass", "costs a waiver claim - FAAB band %s" % band


def decide(slot: str, held_score: Optional[float],
           best_score: Optional[float], gate_ok: bool,
           survives: bool, held_name: Optional[str] = None,
           best_name: Optional[str] = None) -> Tuple[str, float, str]:
    """(verdict, delta, reason) from the two scores and the gates."""
    if best_score is None:
        if held_score is None:
            return "NO READ", 0.0, ("no %s scored this week - board empty "
                                    "and nothing held" % slot)
        return "HOLD", 0.0, ("no available %s on the board beats a blank - "
                             "nothing to stream" % slot)
    delta = round(float(best_score) - float(held_score or 0.0), 2)
    margin, toss = STREAM_MARGIN[slot], TOSS_MIN[slot]
    if held_score is None:
        reason = ("no %s on the roster plays this week - %s is the best "
                  "available" % (slot, best_name or "the top candidate"))
        verdict = "STREAM"
    elif delta >= margin:
        verdict = "STREAM"
        reason = ("%s beats %s by %+.1f, past the %.1f-pt stream margin"
                  % (best_name or "best", held_name or "held", delta, margin))
    elif delta >= toss:
        verdict = "TOSS-UP"
        reason = ("%s edges %s by only %+.1f - inside the %.1f-%.1f band, "
                  "either call is defensible"
                  % (best_name or "best", held_name or "held", delta, toss,
                     margin))
    else:
        verdict = "HOLD"
        reason = ("nothing available beats %s by more than %.1f (best: %s "
                  "%+.1f)" % (held_name or "held", toss, best_name or "-",
                              delta))
    if verdict == "STREAM" and not survives:
        verdict = "TOSS-UP"
        reason += "; the claim does not clear the waiver-mode bar"
    if verdict == "STREAM" and not gate_ok:
        verdict = "TOSS-UP"
        reason += "; " + UNVERIFIED
    return verdict, delta, reason


# --- the call ---------------------------------------------------------------

def _empty_call(slot: str, reason: str, coverage: str = "") -> Dict:
    return {"pos": slot, "held": None, "held_key": None, "held_short": None,
            "held_score": None, "held_proj": None, "held_opp": None,
            "held_opp_note": "", "best": None, "best_key": None,
            "best_short": None, "best_score": None, "best_proj": None,
            "best_opp": None, "best_opp_note": "", "delta": 0.0,
            "verdict": "NO READ", "reason": reason, "text": "NO READ",
            "cost": "", "confidence": 50, "held_pct": 50,
            "unverified": False, "gate_reason": "", "candidates": [],
            "basis": BASIS, "coverage_note": coverage,
            "excluded": {"mine": 0, "espn": 0, "rival": 0}, "mode": ""}


def weekly_call(league, week: int, my_roster_players: Sequence,
                players: Sequence, matcher, force: bool = False, *,
                board: Optional[Dict[str, List[Dict]]] = None,
                rival=None, taken: Optional[Set[str]] = None,
                secrets_path: Optional[str] = None,
                venues: Optional[Dict[str, str]] = None,
                pa_table: Optional[Dict] = None,
                sigmas: Optional[Dict[str, float]] = None
                ) -> Dict[str, Dict]:
    """{"DST": Call, "K": Call} for one league and week. See the module
    docstring for every field and every judgment call.

    my_roster_players: my Player objects (the pool's, or lineup.build's -
    both carry .key/.pos/.team/.nkey). players: the rankings pool (rival
    and ESPN keys are resolved against it). matcher: engine.ingest.Matcher
    over that pool. Keyword seams inject fixtures; None reads live.
    """
    week = int(week)
    slot_calls: Dict[str, Dict] = {}
    scoring = league.scoring_label()
    my_keys = set(p.key for p in my_roster_players)

    # 1. streaming's weekly board (never logged from here).
    if board is None:
        try:
            board = streaming.build_board(week, scoring, force=force,
                                          quiet=True)
        except Exception as exc:  # noqa: BLE001 - NO READ, said out loud
            why = "streaming board unavailable (%s: %s)" % (
                type(exc).__name__, str(exc).splitlines()[0][:120]
                if str(exc) else "no detail")
            for slot in SLOTS:
                slot_calls[slot] = _empty_call(slot, why)
            return slot_calls

    # 2. availability: mine, ESPN-rostered (ESPN league only), rival-rostered.
    if taken is None:
        plat = str(getattr(league, "platform", "") or "").strip().lower()
        if plat == "espn":
            taken, taken_note = waivers.espn_taken_keys(
                matcher, secrets_path=secrets_path, league=league)
        else:
            taken = set()
            skip = waivers.platform_blocks_espn_data(league)
            taken_note = ("ESPN taken-players filter %s"
                          % (skip or "not applied - platform '%s' is not "
                                     "ESPN" % (plat or "unset")))
    else:
        taken = set(taken)
        taken_note = "taken keys supplied (%d)" % len(taken)
    if rival is None:
        rival = trades.load_rival_view(league, matcher, players,
                                       my_keys=my_keys)
    rival_keys = rival.rostered_keys() if getattr(rival, "available",
                                                  False) else set()
    gate_ok, gate_reason = waivers.claim_gate(rival)
    coverage = "; ".join(x for x in (
        taken_note,
        getattr(rival, "reason", "") or "",
        "" if gate_ok else UNVERIFIED) if x)

    my_def_teams, my_k = _bridge(my_keys, players)
    # lineup.build's Players may not be in the pool by key; read them direct.
    for p in my_roster_players:
        if p.pos == "DEF" and p.team:
            my_def_teams.add(norm_team(p.team))
        elif p.pos == "K":
            my_k.add(p.nkey)
    taken_def, taken_k = _bridge(taken, players)
    rival_def, rival_k = _bridge(rival_keys, players)

    # 3. context (each optional; absence is stated on the line).
    if venues is None:
        try:
            venues = venue_notes(week, force=force)
        except Exception:  # noqa: BLE001 - "venue unknown" on the line
            venues = {}
    if pa_table is None:
        try:
            pa_table = matchups_mod.pa_table(league, force=force)
        except Exception:  # noqa: BLE001 - "no opponent-defense read"
            pa_table = None
    dreads = defense_reads(pa_table)
    d_basis = (pa_table or {}).get("basis", "") if pa_table else ""

    mode = str(getattr(league, "waiver_mode", "faab") or "faab").lower()

    for slot in SLOTS:
        pos = POS_OF[slot]
        cands = list(board.get(pos) or [])
        mine_team, mine_k = my_def_teams, my_k
        excl = {"mine": 0, "espn": 0, "rival": 0}
        avail: List[Dict] = []
        held_c: Optional[Dict] = None
        for c in cands:
            if slot == "DST":
                team = norm_team(c.get("team", ""))
                is_mine = team in mine_team
                is_espn = team in taken_def
                is_rival = team in rival_def
            else:
                is_mine = c["key"] in mine_k
                is_espn = c["key"] in taken_k
                is_rival = c["key"] in rival_k
            if is_mine:
                excl["mine"] += 1
                if held_c is None or c["score"] > held_c["score"]:
                    held_c = c
                continue
            # Counted independently - a defense on a rival's roster that
            # the ESPN read also sees is both facts, not one.
            if is_espn:
                excl["espn"] += 1
            if is_rival:
                excl["rival"] += 1
            if is_espn or is_rival:
                continue
            avail.append(c)

        # The held player: the roster's DEF/K, whether or not the board
        # scored him this week (bye / no projection -> 0.0, said so).
        held_players = [p for p in my_roster_players if p.pos == pos]
        held_p = None
        if held_c is not None:
            held_p = next((p for p in held_players
                           if _is_player(held_c, slot, p)), None)
        if held_p is None and held_players:
            held_p = held_players[0]
        held_name = held_p.name if held_p is not None else (
            held_c["name"] if held_c else None)
        held_key = held_p.key if held_p is not None else None
        held_short = (_short(held_p, slot) if held_p is not None
                      else (_short(held_c, slot) if held_c else None))
        if held_c is not None:
            held_score = held_c["score"]
            held_proj = held_c["proj"]
            held_opp = held_c["opp"]
            held_note = opp_note(held_c, slot, venues, dreads, d_basis)
        elif held_p is not None:
            held_score, held_proj, held_opp = 0.0, None, None
            held_note = ("%s has no game or no projection this week - "
                         "scores 0.0" % held_name)
        else:
            held_score = held_proj = held_opp = None
            held_note = "no %s on the roster" % pos

        best = avail[0] if avail else None
        survives, cost = (cost_line(league, (best["score"] -
                                             float(held_score or 0.0)))
                          if best else (False, ""))
        verdict, delta, reason = decide(
            slot, held_score, best["score"] if best else None, gate_ok,
            survives, held_short, _short(best, slot) + (
                " D/ST" if slot == "DST" else "") if best else None)
        if held_c is None and held_p is not None and best is not None:
            # A held DEF/K with no game or no projection scored 0.0 above;
            # say that first, because it is the whole reason.
            reason = "%s; %s" % (held_note, reason)
        conf = confidence(held_score, best["score"] if best else None, slot,
                          sigmas) if best else 50
        call = {
            "pos": slot, "held": held_name, "held_key": held_key,
            "held_short": held_short, "held_score": held_score,
            "held_proj": held_proj, "held_opp": held_opp,
            "held_opp_note": held_note,
            "best": best["name"] if best else None,
            "best_key": best["key"] if best else None,
            "best_short": _short(best, slot) if best else None,
            "best_score": best["score"] if best else None,
            "best_proj": best["proj"] if best else None,
            "best_opp": best["opp"] if best else None,
            "best_opp_note": (opp_note(best, slot, venues, dreads, d_basis)
                              if best else ""),
            "delta": delta, "verdict": verdict, "reason": reason,
            "cost": cost if best else "", "confidence": conf,
            "held_pct": 100 - conf, "unverified": not gate_ok,
            "gate_reason": "" if gate_ok else gate_reason,
            "candidates": [_cand_view(c, opp_note(c, slot, venues, dreads,
                                                  d_basis))
                           for c in avail[:CAND_LIMIT]],
            "basis": BASIS, "coverage_note": coverage, "excluded": excl,
            "mode": mode,
        }
        call["text"] = verdict_text(call)
        slot_calls[slot] = call
    return slot_calls


# --- renderings other modules import (pure) ---------------------------------

def _best_label(call: Dict) -> str:
    if call.get("pos") == "DST":
        return "%s D/ST" % (call.get("best_short") or call.get("best") or "?")
    return call.get("best") or "?"


def verdict_text(call: Dict) -> str:
    """'HOLD LAC' / 'STREAM NE D/ST +1.6 over LAC' / 'TOSS-UP ... (why)'."""
    v = call.get("verdict") or "NO READ"
    held = call.get("held_short") or call.get("held") or "nobody"
    if v == "NO READ":
        return "NO READ"
    if v == "HOLD":
        return "HOLD %s" % held
    line = "%s %s %+.1f over %s" % (v, _best_label(call),
                                    float(call.get("delta") or 0.0), held)
    if v == "TOSS-UP" and call.get("unverified"):
        line += " (%s)" % UNVERIFIED
    return line


def consensus_vote(call: Dict) -> Optional[str]:
    """The engine's vote on the HELD player: start (HOLD), sit (STREAM),
    flex-lean (TOSS-UP); None when there is no read."""
    return {"HOLD": "start", "STREAM": "sit", "TOSS-UP": "flex"}.get(
        call.get("verdict") or "")


def consensus_verdict(call: Dict) -> Optional[Tuple[str, int]]:
    """(row verdict, start-ward pct) for the held player's consensus row.
    pct is P(held beats best) - see CONFIDENCE in the docstring."""
    v = call.get("verdict")
    if v == "HOLD":
        return "START", max(50, int(call.get("held_pct") or 50))
    if v == "STREAM":
        return "SIT", min(50, int(call.get("held_pct") or 50))
    if v == "TOSS-UP":
        return "EVEN", 50
    return None


def lineup_verdict(call: Dict, slot: str) -> Optional[Dict]:
    """A verdict row for lineup.build's list, in its own shape."""
    if not call or call.get("verdict") == "NO READ":
        return None
    text = verdict_text(call)
    tail = [call.get("reason") or ""]
    if call.get("best_opp_note"):
        tail.append("%s: %s" % (_best_label(call), call["best_opp_note"]))
    if call.get("held_opp_note") and call.get("held"):
        tail.append("%s: %s" % (call.get("held_short") or call["held"],
                                call["held_opp_note"]))
    if call.get("cost"):
        tail.append(call["cost"])
    return {"slot": slot, "a": call.get("held") or "(no %s)" % slot,
            "b": call.get("best") or "-", "a_key": call.get("held_key"),
            "b_key": None, "pct": int(call.get("held_pct") or 50),
            "text": "%s - %s" % (text, " · ".join(t for t in tail if t)),
            "dk": call}


def inbox_item_text(call: Dict) -> Tuple[str, str]:
    """(text, detail) for ONE Home inbox item on a STREAM verdict."""
    text = ("Stream %s over %s this week (%+.1f)."
            % (_best_label(call), call.get("held_short") or call.get("held")
               or "your %s" % call.get("pos"), float(call.get("delta") or 0)))
    detail = " · ".join(x for x in (
        "%s: %s" % (_best_label(call), call.get("best_opp_note") or ""),
        call.get("cost") or "") if x)
    return text, detail


def board_line(call: Dict) -> str:
    """The one line under a DST/K row: held vs best available, with why."""
    if not call or call.get("verdict") == "NO READ":
        return "no DEF/K read this week - %s" % (call.get("reason")
                                                 if call else "no call")
    held = call.get("held_short") or call.get("held") or "nobody"
    hs = call.get("held_score")
    bits = [verdict_text(call),
            "held %s %s (%s)" % (held, ("%.1f" % hs) if hs is not None
                                 else "-", call.get("held_opp_note") or "")]
    if call.get("best"):
        bits.append("best available %s %.1f (%s)"
                    % (_best_label(call), float(call["best_score"]),
                       call.get("best_opp_note") or ""))
    if call.get("cost"):
        bits.append(call["cost"])
    if call.get("unverified"):
        bits.append(UNVERIFIED)
    return " · ".join(bits)


# --- CLI (read-only) --------------------------------------------------------

def _print_call(call: Dict) -> None:
    print("\n  %s: %s" % (call["pos"], call["text"]))
    print("     reason: %s" % call["reason"])
    print("     held:   %s  score %s  %s"
          % (call["held"] or "-",
             ("%.2f" % call["held_score"]) if call["held_score"] is not None
             else "-", call["held_opp_note"]))
    if call["best"]:
        print("     best:   %s  score %.2f  %s"
              % (call["best"], call["best_score"], call["best_opp_note"]))
        print("     P(best beats held) %d%%  ·  %s"
              % (call["confidence"], call["cost"]))
    print("     available (top %d): %s"
          % (CAND_LIMIT, ", ".join("%s %.2f %s" % (c["name"], c["score"],
                                                    _fmt_opp(c))
                                   for c in call["candidates"]) or "none"))
    ex = call["excluded"]
    print("     excluded: mine %d · ESPN-rostered %d · rival-rostered %d"
          % (ex["mine"], ex["espn"], ex["rival"]))
    print("     coverage: %s" % (call["coverage_note"] or "-"))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.dk",
        description="HOLD or STREAM: my DEF/K vs the best genuinely "
                    "available one this week. Read-only.")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--force", action="store_true", help="refetch feeds")
    args = ap.parse_args(argv)
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % args.league)
    if not os.path.exists(league_path):
        print("no league yaml at leagues/%s.yaml" % args.league)
        return 1
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, league.rankings_csv)
    players = load_players(csv_path)
    from engine.ingest import Matcher
    matcher = Matcher(players)
    roster, banner = waivers.load_my_roster(args.league, matcher)
    mine = ([p for p in players if p.key in roster.keys]
            if roster is not None else [])
    print("DEF/K CALL - %s, week %d" % (league.name, args.week))
    if banner:
        print("  " + banner)
    calls = weekly_call(league, args.week, mine, players, matcher,
                        force=args.force)
    for slot in SLOTS:
        _print_call(calls[slot])
    print("\n  basis: %s" % BASIS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
