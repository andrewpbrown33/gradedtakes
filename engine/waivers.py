"""Waiver engine: rank the wire, name a drop, suggest a FAAB band - or, in
a priority-waivers league, a burn-priority verdict instead.

    python -m engine.waivers --league yahoo-main --week N

Candidate pool = every rankings-pool player NOT known to be on my roster
(data/rosters/<league>.yaml via exposure's loader), minus other teams'
players when ESPN cookies exist (guarded, optional - RUNBOOK A3). Yahoo has
no roster API wired yet, so without cookies the pool is honest but wide:
players on rivals' rosters WILL appear; the banner says so every run.

Each candidate is scored transparently - every component is printed with the
number it contributed and the evidence behind it:

  (a) ROS  - rest-of-season points (weekly.ros_projection) over my current
      worst starter that the candidate could displace (grader.best_lineup
      fills my lineup; the min-ROS starter in an eligible slot is the bar).
      When my roster file is partial and no starter is known at a position,
      the bar falls back to a replacement-level ROS (the Nth-best ROS in the
      pool, N = this league's starter demand via hard counts + flex
      allocation) and the basis line says so.
  (b) xFP  - regression signal from nflverse expected fantasy points: the
      average (expected - actual) over the last XFP_WEEKS filed weeks.
      Positive = production trailed opportunity = buy candidate. Before the
      current season files any weeks, last season's data is used and every
      line carries a '2025 signal' label.
  (c) TREND - Sleeper trending-adds count over the last 24h (live endpoint,
      cached 1h), log-scaled so 100k adds cannot drown the points math.
  (d) OWNED - %owned momentum, ONLY when ESPN cookies exist: the delta vs
      the previous cookie-run snapshot. No cookies (or first run) = component
      absent with a note, never a fake zero baseline.

JUDGMENT CALLS, documented here rather than sprinkled around:

  * Component weights: score = ros_gain + 4.0*xfp_gap (capped +/-20)
    + min(15, 3*log10(1+adds)) + 0.5*owned_delta (capped +/-5). ROS is the
    anchor (real points over a real bar); xFP at 4x says "a month of this
    regression gap"; the trend cap keeps hype from ever outvoting more than
    ~two starts' worth of points.
  * Scarcity: 1.5x when <=3 candidates at the position clear my bar, 1.25x
    when <=6, else 1.0x. Thin positions justify paying up.
  * FAAB bands (% of budget) come from score x scarcity: <=0 -> pass,
    <3 -> 1-3%, <8 -> 4-8%, <15 -> 9-15%, <25 -> 16-25%, <40 -> 26-40%,
    else 41-60%. These are bands, not bids - league bid history calibration
    needs cookies (RUNBOOK).
  * PRIORITY leagues (waiver_mode: priority in leagues/<id>.yaml) replace
    FAAB bands with burn-priority guidance. A claim's opportunity cost is
    the score gap to the next-best SAME-POSITION candidate lower on the
    board - the player you could still take from free agency after letting
    the claim pass. "worth burning priority? YES" needs that gap >=
    PRIORITY_GAP (5.0 score points, roughly a weekly start's worth of
    edge); anything thinner is not worth surrendering queue position for.
    The report also restates the structural cost every run: priority
    resets weekly by inverse standings, and from draft slot 1 in The
    Original 8 you START the season 8th of 8 in the queue.
  * Drop candidate = the known roster player with the lowest ROS after
    starters are protected (bench first; a starter only when every known
    player starts). With a partial roster file this is drawn from the known
    players ONLY - positive-only semantics, the banner repeats it.

COMPETITION AWARENESS (rival rosters, when engine/leagueview.py can supply
them through engine.trades.load_rival_view - the same adapter the trade
analyzer uses, never a second copy):

  * A rival is counted as competition for a candidate when the candidate
    would ACTUALLY change their team: he cracks their best legal starting
    lineup (his ROS beats their worst pos-eligible starter, the identical
    displacement bar starter_baselines applies to us), or their roster is
    structurally short startable bodies at the position
    (engine.trades.positional_net < 0). Wanting a player and bidding on him
    are not the same thing, so the count is a read on likely bidders, never
    a claim about what anyone will do.
  * Bid pressure: the FAAB band is re-banded on score x scarcity x
    (1 + COMP_STEP per competing rival, capped at COMP_CAP). Competition
    does not make a player better - it makes him more expensive.
  * Priority leagues: priority_guidance()'s gap assumes the next-best
    same-position candidate survives to free agency. When FALLBACK_CONTESTED
    or more rivals need that position, the assumption fails and the honest
    cost of passing is the WHOLE score, not the gap - which can flip a
    burn verdict to YES. The line always names why.
  * Rival rosters also thin the candidate pool: a player on a rival roster
    is not a free agent. Without leagueview that exclusion cannot be made,
    and the banner keeps saying so.
  * Drop candidates carry a warning when the player being cut is a likely
    rival target - dropping him hands a rival the upgrade for free.
  * With no rival data every one of these degrades to a single honest line
    ("rival rosters unknown ..."), never to a silent zero.

Nothing is written outside data/cache/: the %owned momentum snapshot
(espn-owned-snapshot.json) is a data/cache feed snapshot like every other
fetch, and no saves/, rosters, or logs are ever touched.

That snapshot is a BASELINE, not a cache entry, so advancing it is opt-in:
owned_momentum(advance=True) is the deliberate refresh gesture this report
and the digest use, and every read-only caller (the board) leaves the
baseline where it found it. See owned_momentum for why.
"""

import argparse
import math
import os
import sys
from typing import Callable, Dict, List, Optional, Tuple

try:
    from engine import nflverse
    from engine import weekly
    from engine.exposure import Exposure, DEFAULT_DIR as ROSTER_DIR
    from engine.grader import best_lineup
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player, POSITIONS,
                               load_players, missing_rankings_message,
                               repo_path)
    from engine.projections import (SLEEPER_PLAYERS_URL, UA, _def_index,
                                    _fetch_json, name_key)
    from engine.recommend import Ansi, flex_allocation
    # Rival rosters come through the trade analyzer's leagueview adapter -
    # one loader, one degradation story, no second copy of the same guard.
    from engine.trades import (RIVALS_UNKNOWN, load_rival_view,
                               positional_net, replacement_from_pool)
except ImportError:  # run directly as `python engine/waivers.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import nflverse
    from engine import weekly
    from engine.exposure import Exposure, DEFAULT_DIR as ROSTER_DIR
    from engine.grader import best_lineup
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player, POSITIONS,
                               load_players, missing_rankings_message,
                               repo_path)
    from engine.projections import (SLEEPER_PLAYERS_URL, UA, _def_index,
                                    _fetch_json, name_key)
    from engine.recommend import Ansi, flex_allocation
    # Rival rosters come through the trade analyzer's leagueview adapter -
    # one loader, one degradation story, no second copy of the same guard.
    from engine.trades import (RIVALS_UNKNOWN, load_rival_view,
                               positional_net, replacement_from_pool)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = weekly.SEASON

TRENDING_URL = ("https://api.sleeper.app/v1/players/nfl/trending/add"
                "?lookback_hours=%d&limit=%d")
OWNED_SNAP = os.path.join(HERE, "data", "cache", "espn-owned-snapshot.json")

# Judgment-call constants - see the module docstring for the reasoning.
XFP_WEEKS = 4          # regression window: last N filed weeks
XFP_WEIGHT = 4.0       # points per (xfp-actual)/week - "a month of this gap"
XFP_CAP = 20.0
TREND_SCALE = 3.0      # points = TREND_SCALE * log10(1 + adds)
TREND_CAP = 15.0
OWNED_WEIGHT = 0.5     # points per %owned momentum point
OWNED_CAP = 5.0
FAAB_BANDS = [(0.0, "pass"), (3.0, "1-3%"), (8.0, "4-8%"), (15.0, "9-15%"),
              (25.0, "16-25%"), (40.0, "26-40%"), (None, "41-60%")]
PRIORITY_GAP = 5.0     # score pts a claim must clear its FA fallback by
                       # before burning inverse-standings priority says YES
COMP_STEP = 0.12       # bid-pressure multiplier added per competing rival
COMP_CAP = 1.6         # ...capped here; a wire scramble is not a blank cheque
FALLBACK_CONTESTED = 2  # rivals needing the position before a priority
                        # fallback stops counting as "survives to free agency"

# The waiver-shaped half of engine.trades.RIVALS_UNKNOWN ("rival rosters
# unknown"), with the tail this report can actually stand behind. Derived
# from that constant so the two modules can never drift apart.
NO_COMPETITION = ("%s - no competition read on any candidate below; bid and "
                  "burn guidance is position scarcity only"
                  % RIVALS_UNKNOWN.split(" - ")[0])


# --- roster (exposure loader semantics, honest about partial files) ---------
def load_my_roster(league_id: str, matcher: Matcher,
                   dirpath: Optional[str] = None):
    """(LeagueRoster-or-None, banner). Reuses exposure's file loader.

    None means NO roster file (or an invalid one) - grade the pool anyway,
    but the banner must ride on every output: without exclusions, players
    already on MY roster can appear as candidates.
    """
    dirpath = dirpath or ROSTER_DIR
    path = os.path.join(dirpath, "%s.yaml" % league_id)
    if not os.path.exists(path):
        return None, ("NO roster file for %s (expected data/rosters/%s.yaml) "
                      "- grading the full pool; players already on MY roster "
                      "may appear as candidates" % (league_id, league_id))
    roster = Exposure._load_file(path, matcher)
    if roster is None:
        return None, ("roster file for %s did not parse as a roster yaml - "
                      "grading the full pool; players already on MY roster "
                      "may appear as candidates" % league_id)
    banner = ""
    if len(roster.keys) < roster.size:
        banner = ("%s roster known %d/%d - unknown holdings may appear as "
                  "candidates, and the drop pick is drawn from the %d known "
                  "players only (positive-only semantics)"
                  % (roster.name, len(roster.keys), roster.size,
                     len(roster.keys)))
    if not roster.auto_refresh:
        # A paste-fed roster is COMPLETE, so the count above never fires for
        # it - and a stale roster grades the wire against players who may
        # already be gone. Say so on the same line, always.
        stale = ("%s is PASTE-FED - it does not refresh on its own, so this "
                 "wire was graded against whatever the roster looked like at "
                 "the last paste" % roster.name)
        banner = "%s. %s" % (banner, stale) if banner else stale
    return roster, banner


# --- ROS map ----------------------------------------------------------------
def build_ros_map(players: List[Player], week: int, scoring: str,
                  force: bool = False) -> Dict[str, float]:
    """{player.key: rest-of-season points}. One kona download serves all.

    DEF rows route through the team index (rankings say 'Seattle Defense',
    ESPN says 'Seahawks D/ST' - names never match, teams always do).
    A 0.0 here means "no ROS data filed", surfaced as such downstream.
    """
    records = weekly._espn_weekly_records(scoring, force=force, quiet=True)
    defs = _def_index(records)
    out = {}
    for p in players:
        if p.pos == "DEF":
            rec = defs.get(p.team)
            key = name_key(rec["name"]) if rec else p.nkey
        else:
            key = p.nkey
        out[p.key] = weekly.ros_projection(key, week, scoring, records=records)
    return out


# --- starter baselines (reuses grader.best_lineup - never duplicated) -------
def _slot_covers(slot: str, pos: str) -> bool:
    return slot == pos or pos in FLEX_ELIGIBLE.get(slot, ())


def starter_baselines(league: LeagueConfig, roster_players: List[Player],
                      ros_map: Dict[str, float], pool_players: List[Player]
                      ) -> Dict[str, Dict]:
    """{pos: {"value": ROS bar, "basis": how it was set}}.

    Every pos-eligible starting slot filled by a KNOWN roster player -> the
    bar is my worst such starter's ROS (the player a pickup would displace).
    Any pos-eligible slot still open -> the bar falls to replacement-level
    ROS (the Nth-best ROS in the pool, N = hard starters * teams + this
    league's flex allocation): with a partial roster file an "open" slot is
    probably filled by an uncaptured player, so displacing a known flex
    body would overstate the gain. The basis string keeps whichever bar was
    used visible on every output line.
    """
    rows, _, _ = best_lineup(league, roster_players)
    hard = league.hard_starter_counts()
    flex = flex_allocation(league, pool_players)
    boards = {}
    for p in pool_players:
        boards.setdefault(p.pos, []).append(ros_map.get(p.key, 0.0))
    for board in boards.values():
        board.sort(reverse=True)

    def replacement(pos):
        n = int(round(hard.get(pos, 0) * league.teams + flex.get(pos, 0.0)))
        board = boards.get(pos, [])
        return board[min(n, len(board)) - 1] if n > 0 and board else 0.0

    out = {}
    for pos in POSITIONS:
        eligible = [(slot, p) for slot, p in rows if _slot_covers(slot, pos)]
        starters = [p for _, p in eligible if p is not None]
        open_slots = any(p is None for _, p in eligible)
        if starters and not open_slots:
            worst = min(starters, key=lambda p: ros_map.get(p.key, 0.0))
            val = ros_map.get(worst.key, 0.0)
            out[pos] = {"value": val,
                        "basis": "my worst %s-eligible starter: %s (ROS %.0f)"
                                 % (pos, worst.name, val)}
        else:
            val = replacement(pos)
            why = ("open %s-eligible slot" % pos if starters or eligible
                   else "no %s slot in lineup" % pos)
            out[pos] = {"value": val,
                        "basis": "replacement level ROS %.0f (%s - unknown "
                                 "players likely fill it)" % (val, why)}
    return out


# --- component math (pure - tests inject synthetics) ------------------------
def xfp_gap(weeks_data: List[Dict], latest_n: int = XFP_WEEKS
            ) -> Optional[float]:
    """Average (expected - actual) over the last `latest_n` filed weeks.

    Positive = points trailed opportunity (buy signal). None = no filed
    weeks, which is "no signal", never zero-signal.
    """
    if not weeks_data:
        return None
    tail = weeks_data[-latest_n:]
    return sum(w["xfp"] - w["actual"] for w in tail) / float(len(tail))


def xfp_points(gap: Optional[float]) -> float:
    if gap is None:
        return 0.0
    return max(-XFP_CAP, min(XFP_CAP, XFP_WEIGHT * gap))


def trend_points(adds: int) -> float:
    if not adds or adds <= 0:
        return 0.0
    return min(TREND_CAP, TREND_SCALE * math.log10(1.0 + adds))


def owned_points(delta: Optional[float]) -> float:
    if delta is None:
        return 0.0
    return max(-OWNED_CAP, min(OWNED_CAP, OWNED_WEIGHT * delta))


def scarcity_factor(n_clearing_bar: int) -> float:
    if n_clearing_bar <= 3:
        return 1.5
    if n_clearing_bar <= 6:
        return 1.25
    return 1.0


def faab_band(scaled_score: float) -> str:
    for cut, label in FAAB_BANDS:
        if cut is None or scaled_score <= cut:
            return label
    return FAAB_BANDS[-1][1]


# --- candidate scoring ------------------------------------------------------
class Candidate(object):
    __slots__ = ("player", "ros", "ros_gain", "ros_basis", "xfp_pts",
                 "xfp_detail", "trend_pts", "trend_detail", "owned_pts",
                 "owned_detail", "score", "scarcity", "faab", "burn",
                 "burn_detail", "rivals", "rival_names", "comp_detail",
                 "comp_factor")

    def __init__(self, player):
        self.player = player
        self.ros = 0.0
        self.ros_gain = 0.0
        self.ros_basis = ""
        self.xfp_pts = 0.0
        self.xfp_detail = ""
        self.trend_pts = 0.0
        self.trend_detail = ""
        self.owned_pts = 0.0
        self.owned_detail = ""
        self.score = 0.0
        self.scarcity = 1.0
        self.faab = "pass"
        self.burn = "NO"        # priority mode: worth burning priority?
        self.burn_detail = ""   # the opportunity-cost evidence behind it
        self.rivals = 0         # rival teams this pickup would actually help
        self.rival_names = []   # ...named, so the count can be argued with
        self.comp_detail = ""   # "" = no rival data, never a silent zero
        self.comp_factor = 1.0  # bid-pressure multiplier applied to the band


def score_pool(candidates: List[Player], ros_map: Dict[str, float],
               baselines: Dict[str, Dict], xfp_map: Dict[str, List[Dict]],
               trending: Dict[str, int],
               owned_delta: Optional[Dict[str, float]] = None,
               xfp_label: str = "") -> List[Candidate]:
    """Pure scoring core: every input is injectable, output is sorted.

    candidates: Player objects NOT known to be mine. ros_map: {player.key:
    ROS}. baselines: starter_baselines() shape. xfp_map: {nkey: nflverse
    fetch_xfp weeks}. trending: {nkey: 24h add count}. owned_delta: {nkey:
    %owned momentum} or None when the component is unavailable.
    """
    out = []
    for p in candidates:
        c = Candidate(p)
        c.ros = ros_map.get(p.key, 0.0)
        base = baselines.get(p.pos, {"value": 0.0, "basis": "no baseline"})
        c.ros_gain = c.ros - base["value"]
        c.ros_basis = base["basis"]
        if c.ros == 0.0:
            c.ros_basis += " [no ROS data for %s]" % p.name

        gap = xfp_gap(xfp_map.get(p.nkey) or [])
        c.xfp_pts = xfp_points(gap)
        if gap is None:
            c.xfp_detail = "no xFP data"
        else:
            n = min(XFP_WEEKS, len(xfp_map.get(p.nkey) or []))
            c.xfp_detail = ("avg %+.1f xfp-actual/wk over last %d wk%s%s"
                            % (gap, n, "s" if n != 1 else "",
                               " (%s)" % xfp_label if xfp_label else ""))

        adds = int(trending.get(p.nkey, 0))
        c.trend_pts = trend_points(adds)
        c.trend_detail = ("%s Sleeper adds (24h)" % format(adds, ",d")
                          if adds else "not trending")

        if owned_delta is not None and p.nkey in owned_delta:
            delta = owned_delta[p.nkey]
            c.owned_pts = owned_points(delta)
            c.owned_detail = "%%owned %+.1f pts since last snapshot" % delta
        else:
            c.owned_detail = ""

        c.score = c.ros_gain + c.xfp_pts + c.trend_pts + c.owned_pts
        out.append(c)

    clearing = {}
    for c in out:
        if c.ros_gain > 0:
            clearing[c.player.pos] = clearing.get(c.player.pos, 0) + 1
    for c in out:
        c.scarcity = scarcity_factor(clearing.get(c.player.pos, 0))
        c.faab = faab_band(c.score * c.scarcity) if c.score > 0 else "pass"

    out.sort(key=lambda c: (-c.score, c.player.rank))
    return out


# --- waiver competition: who else needs this position (pure) ----------------
class Competition(object):
    """How many rivals a candidate would actually help, and which ones."""

    __slots__ = ("count", "teams", "structural", "upgrade")

    def __init__(self):
        self.count = 0
        self.teams = []         # display names, board order
        self.structural = []    # teams short startable bodies at the position
        self.upgrade = []       # teams whose worst starter he would displace

    def detail(self, pos: str) -> str:
        if not self.count:
            return "no rival roster shows a need at %s" % pos
        who = ", ".join(self.teams[:4])
        if len(self.teams) > 4:
            who += ", +%d more" % (len(self.teams) - 4)
        kind = []
        if self.structural:
            kind.append("%d structurally short" % len(self.structural))
        if self.upgrade:
            kind.append("%d would start him" % len(self.upgrade))
        return "%d rival%s %s %s (%s): %s" % (
            self.count, "" if self.count == 1 else "s",
            "needs" if self.count == 1 else "need", pos,
            "; ".join(kind), who)


def waiver_competition(league: LeagueConfig, view, candidates: List[Player],
                       ros_map: Dict[str, float], pool_players: List[Player],
                       repl: Optional[Dict[str, float]] = None
                       ) -> Dict[str, Competition]:
    """{player.key: Competition} over the rivals in `view`. {} when unknown.

    Two tests per rival, both drawn from logic that already exists rather
    than a new heuristic: STRUCTURAL - engine.trades.positional_net says
    they are short startable bodies at the position; UPGRADE - the
    candidate's ROS beats their worst pos-eligible starter, i.e. the same
    displacement bar starter_baselines() computes for us, run over their
    roster. An empty dict means NO RIVAL DATA and must be rendered as such.
    """
    if view is None or not getattr(view, "available", False):
        return {}
    repl = (repl if repl is not None
            else replacement_from_pool(league, pool_players))
    reads = []
    for team in view.teams:
        net = positional_net(league, team.players, repl)
        bars = starter_baselines(league, team.players, ros_map, pool_players)
        reads.append((team, net, bars))

    out = {}
    for p in candidates:
        comp = Competition()
        for team, net, bars in reads:
            short = net.get(p.pos, 0) < 0
            bar = bars.get(p.pos, {"value": 0.0})["value"]
            starts = ros_map.get(p.key, 0.0) > bar
            if not (short or starts):
                continue
            comp.teams.append(team.name)
            if short:
                comp.structural.append(team.name)
            if starts:
                comp.upgrade.append(team.name)
        comp.count = len(comp.teams)
        out[p.key] = comp
    return out


def competition_factor(rivals: int) -> float:
    """Bid-pressure multiplier: more bidders, higher price, same player."""
    return min(COMP_CAP, 1.0 + COMP_STEP * max(0, rivals))


def apply_competition(ranked: List[Candidate],
                      comp: Dict[str, Competition]) -> None:
    """Annotate scored candidates with the rival read and re-band FAAB.

    A no-op on the scoring itself: competition never changes what a player
    is worth to us (the score), only what he is likely to cost. With an
    empty comp map every candidate keeps comp_detail "" and the report
    prints the rivals-unknown line once instead of a fake zero per row.
    """
    if not comp:
        return
    for c in ranked:
        read = comp.get(c.player.key)
        if read is None:
            continue
        c.rivals = read.count
        c.rival_names = list(read.teams)
        c.comp_detail = read.detail(c.player.pos)
        c.comp_factor = competition_factor(read.count)
        if c.score > 0:
            c.faab = faab_band(c.score * c.scarcity * c.comp_factor)


# --- priority-mode guidance (pure - waiver_mode: priority leagues) ----------
def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def priority_guidance(ranked: List[Candidate]) -> None:
    """Annotate a score_pool() result in place with burn-priority verdicts.

    The fallback for each candidate is the next-best SAME-POSITION candidate
    lower on the board - the similar player you could still take from free
    agency after letting the claim pass through waivers. burn = "YES" only
    when the score gap to that fallback is >= PRIORITY_GAP (module docstring
    has the reasoning); with no same-position fallback at all the whole
    score is the gap (passing leaves nothing similar behind). Rivals may of
    course claim the fallback too - the gap is the honest expected cost,
    not a guarantee.
    """
    for i, c in enumerate(ranked):
        if c.score <= 0:
            c.burn = "NO"
            c.burn_detail = ("score <= 0 - not a claim at any queue cost")
            continue
        fallback = None
        for other in ranked[i + 1:]:
            if other.player.pos == c.player.pos:
                fallback = other
                break
        if fallback is None:
            gap = c.score
            c.burn_detail = ("no other %s candidate scores - nothing "
                            "similar survives to free agency"
                            % c.player.pos)
        else:
            gap = c.score - fallback.score
            c.burn_detail = ("gap %+.1f vs next-best %s who'd survive to "
                             "FA: %s (score %.1f)"
                             % (gap, c.player.pos, fallback.player.name,
                                fallback.score))
        c.burn = "YES" if gap >= PRIORITY_GAP else "NO"


def priority_competition(ranked: List[Candidate],
                         comp: Dict[str, Competition]) -> None:
    """Re-read burn verdicts once rival demand for the FALLBACK is known.

    priority_guidance() prices a claim against the next-best same-position
    candidate ON THE ASSUMPTION that he survives to free agency. When
    FALLBACK_CONTESTED or more rivals need that position, that assumption is
    the weak link, not the arithmetic: the fallback is probably claimed, so
    the honest cost of passing is the whole score. Verdicts only ever move
    NO -> YES here, and the line says exactly which rivals moved it.
    """
    if not comp:
        return
    for i, c in enumerate(ranked):
        if c.score <= 0 or c.burn == "YES":
            continue
        fallback = next((o for o in ranked[i + 1:]
                         if o.player.pos == c.player.pos), None)
        if fallback is None:
            continue
        read = comp.get(fallback.player.key)
        if read is None or read.count < FALLBACK_CONTESTED:
            continue
        if c.score < PRIORITY_GAP:
            c.burn_detail += ("; %d rivals need %s too, so the fallback may "
                              "not survive - still under the %.0f-pt bar"
                              % (read.count, c.player.pos, PRIORITY_GAP))
            continue
        c.burn = "YES"
        c.burn_detail += ("; but %d rivals need %s (%s), so %s likely does "
                          "NOT survive to FA - passing costs the full %.1f"
                          % (read.count, c.player.pos,
                             ", ".join(read.teams[:3]),
                             fallback.player.name, c.score))


def drop_rival_note(victim: Optional[Player],
                    comp: Dict[str, Competition]) -> str:
    """Warning when the player we would cut is a likely rival target."""
    if victim is None or not comp:
        return ""
    read = comp.get(victim.key)
    if read is None or not read.count:
        return ""
    who = ", ".join(read.teams[:3])
    return ("heads up: %d rival%s %s %s (%s) - dropping %s hands them the "
            "upgrade for nothing"
            % (read.count, "" if read.count == 1 else "s",
               "needs" if read.count == 1 else "need", victim.pos, who,
               victim.surname()))


def priority_position_note(league: LeagueConfig) -> str:
    """One-line structural reminder for a priority-waivers league."""
    base = ("priority resets weekly by inverse standings - a burned claim "
            "sends you to the back of the queue until the next reset")
    if league.my_slot:
        start = league.teams + 1 - league.my_slot
        return ("from draft slot %d you start the season %s of %d; %s"
                % (league.my_slot, _ordinal(start), league.teams, base))
    return base


# --- drop candidate ---------------------------------------------------------
def drop_candidate(league: LeagueConfig, roster_players: List[Player],
                   ros_map: Dict[str, float]
                   ) -> Tuple[Optional[Player], str]:
    """Worst known roster player, starter-adjusted: bench before starters."""
    if not roster_players:
        return None, "no known roster players - cannot suggest a drop"
    rows, _, _ = best_lineup(league, roster_players)
    starter_ids = set(id(p) for _, p in rows if p is not None)
    bench = [p for p in roster_players if id(p) not in starter_ids]
    pool = bench or roster_players
    victim = min(pool, key=lambda p: ros_map.get(p.key, 0.0))
    note = ("bench" if bench else
            "every known player fills a starting slot - dropping the worst "
            "starter")
    return victim, note


# --- live feeds -------------------------------------------------------------
def fetch_trending_adds(lookback_hours: int = 24, limit: int = 300,
                        force: bool = False, quiet: bool = True
                        ) -> Dict[str, int]:
    """{nkey: 24h add count} from Sleeper's trending endpoint (1h cache).

    Ids resolve through the Sleeper players dump (12h cache, same file the
    injury fetch uses). Duplicate names keep the larger count.
    """
    headers = {"User-Agent": UA, "Accept": "application/json"}
    payload = _fetch_json(TRENDING_URL % (lookback_hours, limit),
                          "sleeper-trending-add.json", headers,
                          force=force, max_age_hours=1.0, quiet=quiet)
    players = _fetch_json(SLEEPER_PLAYERS_URL, "sleeper-players.json",
                          headers, max_age_hours=12.0, quiet=quiet)
    out = {}
    for row in payload or []:
        pl = players.get(str(row.get("player_id"))) or {}
        name = ("%s %s" % (pl.get("first_name") or "",
                           pl.get("last_name") or "")).strip()
        count = int(row.get("count") or 0)
        if not name or count <= 0:
            continue
        key = name_key(name)
        out[key] = max(out.get(key, 0), count)
    return out


def fetch_xfp_signal(force: bool = False,
                     xfp_by_season: Optional[Dict[int, Dict[str, List[Dict]]]]
                     = None) -> Tuple[Dict[str, List[Dict]], str]:
    """(xfp_map, label). Current season when it has filed weeks; otherwise
    last season with the honest '2025 signal' label the task demands.

    `xfp_by_season` ({season: fetch_xfp-shaped map}) is a TEST SEAM: it
    injects fixtures and skips nflverse entirely, so the calendar rule above
    can be asserted on both sides of week 1 without depending on what the
    live file holds today. A season absent from the dict reads as
    "unavailable", exactly like a failed fetch. Default None: the live
    fetch, unchanged.
    """
    def _season(season: int) -> Dict[str, List[Dict]]:
        if xfp_by_season is not None:
            got = xfp_by_season.get(season)
            if got is None:
                raise RuntimeError("no %d xFP fixture injected" % season)
            return got
        return nflverse.fetch_xfp(season, force=force)

    try:
        cur = _season(SEASON)
        if cur:
            return cur, ""
    except RuntimeError:
        pass
    return _season(SEASON - 1), "2025 signal"


# --- ESPN cookie-gated extras (guarded, optional - RUNBOOK A3) --------------
MIN_BASELINE_AGE_H = 20.0   # a refresh younger than this keeps the baseline
NO_CLAIMS_REASON = ("rival rosters unknown - the pool is everyone not known "
                    "to be mine, so a 'claim' here could be a rostered star. "
                    "No claim is surfaced (bands read n/a). Paste the league "
                    "rosters in Model Settings -> Leagues to unlock the wire.")


def _platform_of(league) -> str:
    return str(getattr(league, "platform", "") or "").strip().lower()


def platform_blocks_espn_data(league) -> Optional[str]:
    """ESPN rosters and ESPN %owned are facts about ONE ESPN league. Applied
    to a Yahoo pool they thin the wrong wire and rank rostered stars as
    claims (Bo Nix, 89% owned on ESPN, was once the #1 Yahoo FAAB target).
    Returns the reason to skip, or None when the league IS the ESPN one."""
    if league is None:
        return None
    plat = _platform_of(league)
    # Block only a platform we KNOW is not ESPN. An unset/unknown platform
    # (synthetic leagues, old configs) keeps the legacy behaviour.
    if plat in ("yahoo", "sleeper", "cbs", "nfl", "fleaflicker", "mfl",
                "underdog", "fantrax"):
        return ("not applied - this is a %s league; ESPN rosters and "
                "ownership are ESPN facts" % plat)
    return None


def claim_gate(view) -> Tuple[bool, str]:
    """(claims_allowed, reason). Without rival rosters no claim is honest."""
    if view is not None and getattr(view, "available", False):
        return True, ""
    return False, NO_CLAIMS_REASON


def suppress_claims(ranked, reason: str) -> int:
    """Turn every band into an honest n/a. The candidates stay listed (the
    pool read is still useful) but nothing reads as a recommendation."""
    n = 0
    for cand in ranked or ():
        for attr, val in (("faab", "n/a"), ("burn", "N/A"),
                          ("burn_detail", reason), ("suppressed", reason)):
            try:
                setattr(cand, attr, val)
            except Exception:  # noqa: BLE001 - frozen candidate shapes
                pass
        n += 1
    return n


def espn_taken_keys(matcher: Matcher, secrets_path: Optional[str] = None,
                    league=None) -> Tuple[set, str]:
    """Player keys on OTHER teams' ESPN rosters, when cookies exist.

    Pass the league: for anything but the ESPN league the filter is NOT
    applied and the note says so. Every failure path returns an empty set
    plus a note pointing at RUNBOOK A3, never an exception.
    """
    skip = platform_blocks_espn_data(league)
    if skip:
        return set(), "ESPN taken-players filter %s" % skip
    try:
        from engine import espn as espn_mod
    except Exception as exc:
        return set(), ("ESPN taken-players filter unavailable (%s) - needs "
                       "cookies (RUNBOOK A3)" % exc)
    path = secrets_path or espn_mod.SECRETS
    if not os.path.exists(path):
        return set(), ("ESPN taken-players filter skipped - needs cookies "
                       "(RUNBOOK A3)")
    try:
        lg = espn_mod.connect()
        taken = set()
        for team in (getattr(lg, "teams", None) or []):
            for pl in (getattr(team, "roster", None) or []):
                m = matcher.match(getattr(pl, "name", "") or "")
                if m is not None and m.score >= 70:
                    taken.add(m.player.key)
        return taken, ("ESPN taken-players filter active: %d rostered players "
                       "excluded" % len(taken))
    except Exception as exc:
        return set(), ("ESPN taken-players filter failed (%s) - needs cookies "
                       "(RUNBOOK A3)" % exc)


def owned_momentum(secrets_path: Optional[str] = None,
                   advance: bool = False,
                   snapshot_path: Optional[str] = None,
                   league=None,
                   min_age_h: float = MIN_BASELINE_AGE_H
                   ) -> Tuple[Optional[Dict[str, float]], str]:
    """{nkey: %owned delta since the stored baseline snapshot}, or None.

    Momentum is a difference between TWO authenticated reads, so it owns a
    baseline on disk (OWNED_SNAP). Moving that baseline forward is a WRITE,
    and a write must be asked for:

      advance=False (the default, and what every READ path passes - the
        board renders a page and changes nothing) measures against the
        stored baseline and leaves the file exactly as it found it. Two
        renders in a row therefore report the SAME deltas.
      advance=True is the deliberate refresh gesture - the digest and the
        waiver report, the runs whose job is to move the week on. It reads
        the baseline, reports against it, then rolls it forward.

    Without that split, rendering twice compared the wire against a
    seconds-old baseline and every delta collapsed to ~0 while the note
    still said "momentum active" - a real signal silently zeroed by the
    act of looking at it.

    With no baseline on file yet, the component is absent (None) and says
    so; a read path additionally says which run stores one. Never a fake
    zero, and never a delta measured against a snapshot this same call
    just wrote.
    """
    snap = snapshot_path or OWNED_SNAP
    skip = platform_blocks_espn_data(league)
    if skip:
        # No read of ESPN ownership for a non-ESPN league - and, just as
        # important, no WRITE: a Yahoo digest must never roll the ESPN
        # baseline.
        return None, "%%owned momentum %s" % skip
    try:
        from engine import espn as espn_mod
    except Exception as exc:
        return None, ("%%owned momentum unavailable (%s) - needs cookies "
                      "(RUNBOOK A3)" % exc)
    path = secrets_path or espn_mod.SECRETS
    if not os.path.exists(path):
        return None, "%owned momentum skipped - needs cookies (RUNBOOK A3)"
    try:
        import json
        import time
        lg = espn_mod.connect()
        now = {}
        for pl in espn_mod.free_agents(lg, size=300):
            pct = getattr(pl, "percent_owned", None)
            name = getattr(pl, "name", "") or ""
            if name and pct is not None:
                now[name_key(name)] = float(pct)
        prev = None
        if os.path.exists(snap):
            with open(snap, "r") as fh:
                prev = json.load(fh)
        kept = ""
        if advance:
            # Same-day guard: a refresh run twice in a morning must not
            # measure the second run against a baseline the first one wrote
            # minutes earlier (every delta would read ~0). The baseline
            # advances only once it is older than min_age_h; pass 0 to
            # force it.
            fresh = False
            try:
                age_h = (time.time() - float((prev or {}).get("ts") or 0)) / 3600.0
                fresh = bool(prev and prev.get("owned")) and 0 <= age_h < float(min_age_h)
            except (TypeError, ValueError):
                fresh = False
            if fresh:
                kept = (", baseline kept - %.1fh old, advances after %dh"
                        % (age_h, int(min_age_h)))
            else:
                tmp = snap + ".tmp"
                with open(tmp, "w") as fh:
                    json.dump({"ts": time.time(), "owned": now}, fh)
                os.replace(tmp, snap)
        if not prev or not prev.get("owned"):
            if advance:
                return None, ("%owned baseline snapshot stored - momentum "
                              "available from the next cookie run")
            return None, ("%owned momentum unavailable - no baseline "
                          "snapshot on file yet; this is a read-only render "
                          "and does not store one. Run the digest or "
                          "python -m engine.waivers to store the baseline")
        deltas = dict((k, v - prev["owned"][k]) for k, v in now.items()
                      if k in prev["owned"])
        age = ""
        try:
            hours = (time.time() - float(prev.get("ts") or 0)) / 3600.0
            if 0 <= hours < 24 * 60:
                age = ", baseline %.1fh old" % hours
        except (TypeError, ValueError):
            age = ""
        return deltas, ("%%owned momentum active (%d players%s%s)"
                        % (len(deltas), age, kept))
    except Exception as exc:
        return None, ("%%owned momentum failed (%s) - needs cookies "
                      "(RUNBOOK A3)" % exc)


# --- report -----------------------------------------------------------------
def build_report(league_id: str, week: int, top_n: int = 12,
                 color: bool = False, force: bool = False,
                 roster_dir: Optional[str] = None,
                 secrets_path: Optional[str] = None,
                 rival_loader: Optional[object] = None,
                 xfp_by_season: Optional[Dict[int, Dict[str, List[Dict]]]]
                 = None) -> str:
    """The waiver report as text. `xfp_by_season` is fetch_xfp_signal's
    test seam, passed straight through (default None: the live fetch)."""
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        raise SystemExit(missing_rankings_message(league, csv_path))
    players = load_players(csv_path)
    matcher = Matcher(players)
    scoring = league.scoring_label()

    roster, roster_banner = load_my_roster(league_id, matcher,
                                           dirpath=roster_dir)
    my_keys = set(roster.keys) if roster is not None else set()
    roster_players = [p for p in players if p.key in my_keys]

    taken, taken_note = espn_taken_keys(matcher, secrets_path=secrets_path,
                                        league=league)
    # The waiver report IS the refresh: it rolls the %owned baseline forward
    # so the NEXT run measures against this week's wire. Read-only callers
    # (the board) pass no advance and leave the baseline alone.
    owned, owned_note = owned_momentum(secrets_path=secrets_path,
                                       advance=True, league=league)

    ros_map = build_ros_map(players, week, scoring, force=force)
    baselines = starter_baselines(league, roster_players, ros_map, players)
    xfp_map, xfp_label = fetch_xfp_signal(force=force,
                                          xfp_by_season=xfp_by_season)
    trending = fetch_trending_adds(force=force)

    view = load_rival_view(league, matcher, players, my_keys=my_keys,
                           loader=rival_loader)
    rival_keys = view.rostered_keys() if view.available else set()

    pool = [p for p in players if p.key not in my_keys
            and p.key not in taken and p.key not in rival_keys]
    ranked = score_pool(pool, ros_map, baselines, xfp_map, trending,
                        owned_delta=owned, xfp_label=xfp_label)
    claims_ok, claims_reason = claim_gate(view)
    if not claims_ok:
        suppress_claims(ranked, claims_reason)
    # Competition is read over the pool AND my own roster: the drop pick
    # needs the same read to warn when a cut feeds a rival.
    comp = waiver_competition(league, view, pool + roster_players, ros_map,
                              players)
    apply_competition(ranked, comp)
    mode = getattr(league, "waiver_mode", "faab")
    if mode == "priority":
        priority_guidance(ranked)
        priority_competition(ranked, comp)

    c = Ansi(color)
    width = 76
    line, thin = "=" * width, "-" * width
    out = [c.cyan(line)]
    out.append(c.bold(" WAIVER WIRE   %s   week %d   scoring %s"
                      % (league.name, week, scoring)))
    if roster_banner:
        out.append(c.yellow(" BANNER: %s" % roster_banner))
    if view.available:
        out.append(c.dim(" pool: %d ranked players, %d rival-rostered names "
                         "excluded" % (len(pool), len(rival_keys))))
        out.append(c.dim(" %s" % view.reason))
    else:
        out.append(c.dim(" pool: %d ranked players not known-mine; other "
                         "teams' rosters unknown without" % len(pool)))
        out.append(c.dim("       host APIs - real waiver wires are thinner "
                         "than this list"))
        out.append(c.yellow(" %s" % NO_COMPETITION))
        out.append(c.dim("   %s" % view.reason))
    out.append(c.dim(" %s" % taken_note))
    out.append(c.dim(" %s" % owned_note))
    if xfp_label:
        out.append(c.dim(" xFP regression uses %s data - 2026 weeks not yet "
                         "filed" % xfp_label))
    out.append(thin)
    out.append(c.bold(" SHORTLIST  (score = ROS-over-starter + xFP-regression "
                      "+ trending%s)" % (" + %owned" if owned else "")))
    if mode == "priority":
        out.append(c.dim("  priority league - claims spend queue position, "
                         "not budget; weights and the"))
        out.append(c.dim("  burn-priority gap (%.0f pts) are judgment calls, "
                         "documented in engine/waivers.py" % PRIORITY_GAP))
        out.append(c.yellow("  MY QUEUE: %s" % priority_position_note(league)))
    else:
        out.append(c.dim("  weights and FAAB bands are judgment calls, "
                         "documented in engine/waivers.py;"))
        out.append(c.dim("  league bid history calibration needs cookies "
                         "(RUNBOOK)"))
        if comp:
            out.append(c.dim("  bands include bid pressure from rivals who "
                             "need the position (%.2f per rival, capped "
                             "%.2fx)" % (1.0 + COMP_STEP, COMP_CAP)))
    for i, cand in enumerate(ranked[:top_n], start=1):
        p = cand.player
        if mode == "priority":
            head = ("  %2d. %-28s score %6.1f   worth burning priority? %s"
                    % (i, p.short_label(), cand.score, cand.burn))
        else:
            head = ("  %2d. %-28s score %6.1f   FAAB %s"
                    % (i, p.short_label(), cand.score, cand.faab))
        out.append(c.green(head) if cand.score > 0 else head)
        out.append("       ros   %+7.1f  vs %s" % (cand.ros_gain,
                                                   cand.ros_basis))
        out.append("       xfp   %+7.1f  %s" % (cand.xfp_pts, cand.xfp_detail))
        out.append("       trend %+7.1f  %s" % (cand.trend_pts,
                                                cand.trend_detail))
        if cand.owned_detail:
            out.append("       owned %+7.1f  %s" % (cand.owned_pts,
                                                    cand.owned_detail))
        if cand.comp_detail:
            line_c = "       rival   %s" % cand.comp_detail
            out.append(c.yellow(line_c) if cand.rivals else c.dim(line_c))
            if mode != "priority" and cand.comp_factor > 1.0 \
                    and cand.score > 0:
                out.append(c.dim("       band already includes %.2fx bid "
                                 "pressure from that competition"
                                 % cand.comp_factor))
        if mode == "priority":
            out.append("       prio  %s" % cand.burn_detail)
            if cand.scarcity > 1.0 and cand.burn == "NO":
                out.append(c.dim("       thin %s pool (%.2fx scarcity) - a "
                                 "rival may claim the fallback first"
                                 % (p.pos, cand.scarcity)))
        elif cand.scarcity > 1.0:
            out.append(c.dim("       faab band uses %.2fx scarcity (few %s "
                             "candidates clear my bar)"
                             % (cand.scarcity, p.pos)))

    out.append(thin)
    out.append(c.bold(" DROP CANDIDATE  (worst known ROS, starters protected)"))
    victim, note = drop_candidate(league, roster_players, ros_map)
    if victim is None:
        out.append(c.yellow("   %s" % note))
    else:
        out.append("   %-28s ROS %.0f  (%s)"
                   % (victim.short_label(),
                      ros_map.get(victim.key, 0.0), note))
        if roster is not None and len(roster.keys) < roster.size:
            out.append(c.dim("   (drawn from the %d/%d known players only - "
                             "the real worst drop may be an uncaptured name)"
                             % (len(roster.keys), roster.size)))
        drop_warn = drop_rival_note(victim, comp)
        if drop_warn:
            out.append(c.yellow("   %s" % drop_warn))
        elif not comp:
            out.append(c.dim("   (no rival read on this drop - %s)"
                             % RIVALS_UNKNOWN.split(" - ")[0]))
    if roster is not None and roster.unresolved:
        out.append(c.dim("   unresolved roster names: %s"
                         % ", ".join(roster.unresolved)))
    out.append(c.cyan(line))
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.waivers",
        description="Rank the waiver wire with transparent per-component "
                    "scoring, a drop candidate, and FAAB bands (or "
                    "burn-priority guidance when the league yaml says "
                    "waiver_mode: priority).")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--week", type=int, required=True,
                    help="NFL week the pickup is FOR (ROS sums start here)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when the cache is fresh")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    week = weekly._check_week(args.week)
    color = (not args.no_color) and sys.stdout.isatty()
    print(build_report(args.league, week, top_n=args.top, color=color,
                       force=args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
