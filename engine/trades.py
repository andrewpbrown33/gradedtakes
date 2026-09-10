"""Trade analyzer: FantasyCalc market values blended with our ROS projections.

    python -m engine.trades --league yahoo-main
    python -m engine.trades --league yahoo-main --offer "give: X, Y | get: Z"

Two value systems, always shown side by side:

  * MARKET - FantasyCalc's free redraft trade values (crowd-sourced from
    real trades; https://api.fantasycalc.com). Fetched with the ppr and
    numQbs parameters derived from THIS league's scoring/roster config,
    cached 24h in data/cache/ with stale-fallback (same pattern as adp.py).
  * PROJ - our own ROS view: VBD (projected points over the last
    league-wide starter, engine.recommend.replacement_levels) quantile-
    mapped onto the FantasyCalc value scale so the two numbers are directly
    comparable. The mapping is monotonic: our #7-by-VBD player gets the
    market's #7 value. It changes no ordering of ours, it only converts
    "points over replacement" into "market points".

When the two systems disagree hard on a player (>= 1.6x apart AND >= 800
value points), the row says so - that gap IS the trade thesis (buy guys the
market undervalues vs our projections, sell the reverse).

Judgment calls, documented once here:

  * FantasyCalc's redraft pool has no K/DEF. Both are treated as fungible
    streamers: a nominal floor value (the smallest market value seen) on the
    market side, and their real VBD on the projection side. A trade should
    never be won or lost on a kicker.
  * Verdict margins: each system's margin is (get - give) / max(give, get),
    the blended margin is their mean. |blend| < 8% is CLOSE - inside the
    noise of both systems. ACCEPT/DECLINE outside that band. When the two
    systems point in opposite directions and both are outside the band, the
    verdict is forced to CLOSE and says the systems disagree - averaging a
    strong buy and a strong sell into a confident verdict would be lying.
  * Starter impact divides the season-total lineup delta by 17 (games per
    team) for a pts/week read, using grader.best_lineup before/after.
  * ROSTER TRUTH: data/rosters/<league>.yaml, which is PARTIAL BY DESIGN
    (positive-only: a listed player is held; an unlisted player is unknown,
    not absent). Every output carries the coverage banner. Players you
    offer to give are assumed held even if not yet captured in the file -
    you would know your own roster - and the report says so.
  * RIVAL-AWARE MODE. When engine/leagueview.py can hand over the other
    teams' rosters (load_league_rosters(league_id)), no-offer mode stops at
    shapes and names TARGETS: each rival's startable surplus/hole read
    crossed with ours, then a concrete 1-for-1 with both value systems and
    the starter impact in pts/wk for BOTH sides. When leagueview is absent,
    empty, or throws, the section degrades to the literal line "rival
    rosters unknown - constructs only" and the CONSTRUCTS stay - it never
    invents a rival, a roster, or an offer.
  * Startable surplus/hole (positional_net): a body counts as startable when
    its projection clears the league-wide replacement level at its position
    (recommend.replacement_levels - the same bar VBD measures from). Demand
    is the hard starting slots plus the flex slots that roster's own
    startable bodies would fill. "+2 startable RB, -1 WR" therefore means
    two RBs beyond any starting use and one starting slot they can only fill
    with a below-replacement body. K/DEF are excluded: nobody trades for a
    kicker (see the FantasyCalc note above).
  * A proposal lopsided in OUR favor is labeled, not hidden. Past
    LOPSIDED_BAND of blended margin - or when their starting lineup loses
    LOPSIDED_PTS/wk while ours gains - the row says "they likely decline",
    and ranking discounts it (ACCEPT_DISCOUNT), because a proposal nobody
    accepts is worth a fraction of its paper gain.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .exposure import Exposure, MATCH_THRESHOLD
from .grader import best_lineup, positional_gaps, surplus_positions
from .ingest import Matcher
from .models import (DraftState, LeagueConfig, Player, load_players,
                     norm_name, norm_pos)
from .recommend import Ansi, replacement_levels, vbd

try:                       # built in parallel; every use is guarded
    from . import leagueview as _leagueview
except Exception:          # noqa: BLE001 - absence is a supported state
    _leagueview = None

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
ROSTER_DIR = os.path.join(HERE, "data", "rosters")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

FC_URL = ("https://api.fantasycalc.com/values/current"
          "?isDynasty=false&numQbs=%d&ppr=%s")

GAMES_PER_TEAM = 17           # season length for the pts/week conversion
CLOSE_BAND = 0.08             # |blended margin| under this is CLOSE
DISAGREE_RATIO = 1.6          # market-vs-proj per-player disagreement gates
DISAGREE_MIN_DIFF = 800.0
MARKET_POSITIONS = ("QB", "RB", "WR", "TE")   # FC redraft covers only these

# Rival-aware constants - see the module docstring for the reasoning.
RIVALS_UNKNOWN = "rival rosters unknown - constructs only"
LOPSIDED_BAND = 0.20      # blended margin past which they read the same
                          # market we do and say no
LOPSIDED_PTS = 1.0        # pts/wk their starting lineup must LOSE (while
                          # ours gains) for the same honest flag
OVERPAY_DISCOUNT = 0.75   # ranking weight when WE are the side overpaying
TARGET_CHIPS = 3          # spare bodies considered per position, best first
TARGETS_PER_TEAM = 2
TARGETS_LIMIT = 6

# Acceptance proxy. Ranking is our gain TIMES these odds, because a proposal
# the other manager never accepts is worth close to nothing however good it
# looks on our side. The ladder is a judgment call, stated out loud rather
# than hidden in a weight: the only trade that reliably gets accepted is the
# one where the other lineup also gains and the value is inside the noise
# band both systems already call CLOSE.
ACCEPT_MUTUAL = 1.00      # their starters gain AND |blend| <= CLOSE_BAND
ACCEPT_THEY_GAIN = 0.60   # their starters gain, but they give up value
ACCEPT_FAIR = 0.40        # fair value, their starters flat or worse
ACCEPT_TILTED = 0.25      # value tilts our way, their starters flat or worse
ACCEPT_LOPSIDED = 0.15    # flagged lopsided - they likely decline


# --- league -> FantasyCalc query params -------------------------------------
def ppr_param(league: LeagueConfig) -> str:
    """FantasyCalc ppr parameter from THIS league's reception scoring."""
    if league.ppr >= 1:
        return "1"
    if league.ppr > 0:
        return "0.5"
    return "0"


def num_qbs_param(league: LeagueConfig) -> int:
    """2 (superflex market) when any flex slot can hold a QB, else 1."""
    for elig in league.flex_spots():
        if "QB" in elig:
            return 2
    return 1


# --- fetch + cache (adp.py pattern: freshness window, stale fallback) -------
def cache_path(ppr: str, num_qbs: int) -> str:
    return os.path.join(CACHE_DIR,
                        "fantasycalc-%dqb-ppr%s.json" % (num_qbs, ppr))


def fetch_fantasycalc(ppr: str = "1", num_qbs: int = 1,
                      max_age_hours: float = 24.0,
                      quiet: bool = False) -> List[Dict]:
    """Return raw FantasyCalc rows. Disk cache; falls back to stale offline."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(ppr, num_qbs)

    if os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            with open(path, "r") as fh:
                return json.load(fh)

    url = FC_URL % (num_qbs, ppr)
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            rows = json.load(resp)
        if not isinstance(rows, list) or not rows:
            raise ValueError("FantasyCalc returned no players")
        with open(path, "w") as fh:
            json.dump(rows, fh)
        if not quiet:
            print("  market: %d players from FantasyCalc (ppr=%s, %dQB)"
                  % (len(rows), ppr, num_qbs))
        return rows
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            if not quiet:
                print("  FantasyCalc fetch failed (%s) - using cached copy"
                      % type(exc).__name__)
            with open(path, "r") as fh:
                return json.load(fh)
        raise RuntimeError(
            "Could not fetch FantasyCalc values and no cache exists: %s" % exc)


def parse_rows(rows: List[Dict]) -> List[Dict]:
    """Flatten raw FantasyCalc rows to {name, pos, value, overall_rank}."""
    out = []
    for r in rows:
        p = r.get("player") or {}
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "pos": norm_pos(str(p.get("position") or "")),
            "value": float(r.get("value") or 0.0),
            "overall_rank": int(r.get("overallRank") or 0),
        })
    return out


def market_values(players: List[Player], parsed: List[Dict],
                  matcher: Optional[Matcher] = None) -> Dict[str, float]:
    """Map parsed FantasyCalc rows onto our player pool: {player_key: value}.

    Exact normalized name|pos match first; leftovers go through the fuzzy
    Matcher with a position hint. Rows that match nothing are dropped -
    they are players outside our rankings pool (we cannot trade for what
    the pool cannot name).
    """
    matcher = matcher or Matcher(players)
    by_key = dict((p.key, p) for p in players)
    out = {}
    for row in parsed:
        key = "%s|%s" % (norm_name(row["name"]), row["pos"])
        if key in by_key:
            out[key] = row["value"]
            continue
        m = matcher.match(row["name"], pos_hint=row["pos"])
        if m is not None and m.score >= MATCH_THRESHOLD \
                and m.player.pos == row["pos"]:
            # keep the higher value if two rows collapse to one player
            if row["value"] > out.get(m.player.key, -1.0):
                out[m.player.key] = row["value"]
    return out


# --- our projection view, on the market's scale -----------------------------
def proj_scale_values(league: LeagueConfig, players: List[Player],
                      market: Dict[str, float]) -> Dict[str, float]:
    """Quantile-map our VBD ordering onto the FantasyCalc value scale.

    Pool = QB/RB/WR/TE with projections (the positions the market covers).
    Sorted by VBD desc, player i receives the market value at the same
    quantile of the market's own (sorted desc) value list. K/DEF get the
    market's floor value - fungible streamers, see module docstring.
    """
    state = DraftState(league, players)
    repl = replacement_levels(state)

    vals = sorted(market.values(), reverse=True)
    out = {}
    if not vals:
        return out
    floor = vals[-1]

    pool = [p for p in players
            if p.pos in MARKET_POSITIONS and p.proj_points]
    pool.sort(key=lambda p: -vbd(p, repl))
    n = len(pool)
    m = len(vals)
    for i, p in enumerate(pool):
        j = int(round(i * (m - 1) / float(n - 1))) if n > 1 else 0
        out[p.key] = vals[j]
    for p in players:
        if p.pos not in MARKET_POSITIONS:
            out[p.key] = floor
    return out


def disagreement(market_v: Optional[float], proj_v: Optional[float]) -> str:
    """'' | 'MARKET>>PROJ' | 'PROJ>>MARKET' for one player's two values."""
    if not market_v or not proj_v:
        return ""
    hi, lo = max(market_v, proj_v), min(market_v, proj_v)
    if hi - lo < DISAGREE_MIN_DIFF or lo <= 0 or hi / lo < DISAGREE_RATIO:
        return ""
    return "MARKET>>PROJ" if market_v > proj_v else "PROJ>>MARKET"


# --- roster loading (data/rosters is THE truth until host APIs land) --------
def load_my_roster(league: LeagueConfig, matcher: Matcher,
                   players: List[Player],
                   dirpath: Optional[str] = None
                   ) -> Tuple[List[Player], int, int, List[str]]:
    """(known_players, known_count, expected_size, unresolved_names).

    Reads data/rosters/<league-id>.yaml through exposure's parser. PARTIAL
    BY DESIGN and positive-only: known players ARE held; anyone else is
    unknown, never 'not rostered'.
    """
    path = os.path.join(dirpath or ROSTER_DIR, "%s.yaml" % league.id)
    if not os.path.exists(path):
        return [], 0, 0, []
    roster = Exposure._load_file(path, matcher)
    if roster is None:
        return [], 0, 0, []
    by_key = dict((p.key, p) for p in players)
    known = sorted((by_key[k] for k in roster.keys if k in by_key),
                   key=lambda p: p.rank)
    return known, len(known), roster.size, list(roster.unresolved)


class _RosterState(object):
    """Duck-typed stand-in for DraftState so grader's gap/surplus logic
    (positional_gaps, surplus_positions) runs on a plain roster list."""

    def __init__(self, league: LeagueConfig, roster: List[Player]):
        self.league = league
        self._roster = list(roster)

    def pos_counts(self, team: int = 0) -> Dict[str, int]:
        counts = {}
        for p in self._roster:
            counts[p.pos] = counts.get(p.pos, 0) + 1
        return counts


# --- rival rosters (engine/leagueview.py when it can answer, else nothing) --
class RivalTeam(object):
    """One team's roster as OUR player pool sees it, plus its shape read."""

    __slots__ = ("slot", "name", "players", "unresolved", "is_me", "net",
                 "surplus", "holes")

    def __init__(self, slot, name=""):
        self.slot = str(slot)
        self.name = str(name or "").strip() or ("Team %s" % slot)
        self.players = []       # Player objects from OUR rankings pool
        self.unresolved = []    # roster names the pool could not name
        self.is_me = False
        self.net = {}           # {pos: startable bodies minus starting demand}
        self.surplus = []       # [(pos, n)] n>0, richest first
        self.holes = []         # [(pos, n)] n>0 = short by n, biggest first

    def shape_label(self) -> str:
        """'+2 startable RB, -1 WR' - the line the proposal argues from."""
        bits = ["+%d startable %s" % (n, pos) for pos, n in self.surplus]
        bits += ["-%d %s" % (n, pos) for pos, n in self.holes]
        if not bits:
            return "no startable surplus or hole"
        return ", ".join(bits)

    def __repr__(self):
        return "<RivalTeam %s %s %dp>" % (self.slot, self.name,
                                          len(self.players))


class RivalView(object):
    """Rival rosters, or an honest account of why there are none.

    `available` is False whenever no OTHER team's roster could be read -
    engine/leagueview.py missing, a loader error, an empty league, or a
    league where only my own roster is known (Kid's Table today). Callers
    must gate every named-target rendering on it and print `reason`, which
    always carries the literal RIVALS_UNKNOWN line in that case.
    """

    __slots__ = ("teams", "me", "reason", "coverage", "unresolved")

    def __init__(self):
        self.teams = []         # [RivalTeam] excluding mine
        self.me = None          # RivalTeam for my own team, when identified
        self.reason = RIVALS_UNKNOWN
        self.coverage = None    # whatever leagueview reported alongside
        self.unresolved = []    # (team name, [names]) that missed our pool

    @property
    def available(self) -> bool:
        return bool(self.teams)

    def rostered_keys(self) -> set:
        """Player keys held by RIVALS - not free agents, whatever else."""
        out = set()
        for t in self.teams:
            for p in t.players:
                out.add(p.key)
        return out

    def coverage_note(self) -> str:
        if self.coverage is None:
            return ""
        if isinstance(self.coverage, str):
            return self.coverage
        if isinstance(self.coverage, dict):
            bits = ["%s=%s" % (k, self.coverage[k])
                    for k in sorted(self.coverage)]
            return ", ".join(bits)
        return str(self.coverage)


def _default_rival_loader(league_id: str,
                          league: Optional[LeagueConfig] = None,
                          matcher: Optional[Matcher] = None):
    """Rosters out of engine/leagueview.py, or raise so callers degrade.

    Two entry points, in order: load_league_rosters(league_id) if that
    module ever exposes it, otherwise load_league_view(league, matcher) -
    the LeagueView object it actually ships - flattened into the same
    {slot: {name, players, mine}} shape with its coverage line attached.
    Nothing here interprets a roster; it only reshapes one.
    """
    if _leagueview is None:
        raise ImportError("engine/leagueview.py not present")
    fn = getattr(_leagueview, "load_league_rosters", None)
    if fn is not None:
        return fn(league_id)
    fn = getattr(_leagueview, "load_league_view", None)
    if fn is None:
        raise ImportError("engine.leagueview exposes neither "
                          "load_league_rosters() nor load_league_view()")
    if league is None:
        raise ValueError("load_league_view needs the LeagueConfig")
    lv = fn(league, matcher)
    teams = {}
    for t in getattr(lv, "teams", None) or []:
        teams[str(getattr(t, "slot", len(teams)))] = {
            "name": getattr(t, "name", ""),
            "players": list(getattr(t, "players", None) or []),
            "mine": bool(getattr(t, "mine", False)),
        }
    coverage = lv.coverage_text() if hasattr(lv, "coverage_text") else None
    return teams, coverage


def _looks_like_team_map(obj) -> bool:
    if not isinstance(obj, dict) or not obj:
        return False
    for val in obj.values():
        if isinstance(val, dict) and ("players" in val or "roster" in val):
            return True
        if isinstance(val, (list, tuple)):
            return True
        return False
    return False


def _normalize_rosters(raw) -> Tuple[Optional[Dict], object]:
    """(teams_map, coverage) out of whatever shape leagueview hands back.

    Accepts the documented {slot: {name, players}} directly, that mapping
    paired with coverage info as a 2-tuple, and a wrapper dict carrying the
    mapping under teams/rosters/by_slot alongside a coverage key. Anything
    else returns (None, coverage) and the caller degrades honestly.
    """
    coverage = None
    teams = raw
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        teams, coverage = raw[0], raw[1]
    if isinstance(teams, dict) and not _looks_like_team_map(teams):
        for key in ("teams", "rosters", "by_slot"):
            inner = teams.get(key)
            if isinstance(inner, dict):
                if coverage is None:
                    coverage = teams.get("coverage")
                teams = inner
                break
    if not isinstance(teams, dict) or not teams:
        return None, coverage
    return teams, coverage


def _slot_order(slot):
    """Numeric team slots sort as numbers ('10' after '9'), the rest last."""
    try:
        return (0, int(str(slot)), "")
    except (TypeError, ValueError):
        return (1, 0, str(slot))


def _entry_name_pos(raw) -> Tuple[str, str]:
    """A roster entry -> (name, position hint). Strings and dicts both work."""
    if isinstance(raw, dict):
        name = raw.get("player") or raw.get("name") or raw.get("full_name")
        pos = raw.get("pos") or raw.get("position") or ""
        return str(name or "").strip(), norm_pos(str(pos))
    return str(raw or "").strip(), ""


def _resolve_team(entries, matcher: Matcher, by_key: Dict[str, Player],
                  team: RivalTeam) -> None:
    """Fill team.players from raw roster entries; misses go to unresolved."""
    seen = set()
    for raw in entries or []:
        if hasattr(raw, "key") and hasattr(raw, "pos"):      # Player already
            player = by_key.get(getattr(raw, "key"), raw)
            if player.key not in seen:
                seen.add(player.key)
                team.players.append(player)
            continue
        name, pos = _entry_name_pos(raw)
        if not name:
            continue
        key = "%s|%s" % (norm_name(name), pos)
        hit = by_key.get(key) if pos else None
        if hit is None:
            m = matcher.match(name, pos_hint=pos or None)
            hit = (m.player if m is not None and m.score >= MATCH_THRESHOLD
                   else None)
        if hit is None:
            team.unresolved.append(name)
            continue
        if hit.key not in seen:
            seen.add(hit.key)
            team.players.append(hit)


def load_rival_view(league: LeagueConfig, matcher: Matcher,
                    players: List[Player], my_keys: Optional[set] = None,
                    loader: Optional[object] = None) -> RivalView:
    """Other teams' rosters through engine/leagueview.py, or an empty view.

    `loader` is injectable (tests pass a synthetic league; production uses
    leagueview.load_league_rosters). EVERY failure path - module absent,
    bad shape, an exception from the loader - returns an unavailable view
    whose .reason starts with the literal RIVALS_UNKNOWN line. My own team
    is identified by roster overlap first (the roster file is the ground
    truth for who I am) and by league.my_slot second, and is kept out of
    .teams so it can never be proposed a trade with itself.
    """
    view = RivalView()
    if loader is None:
        def loader(lid, _lg=league, _m=matcher):
            return _default_rival_loader(lid, _lg, _m)
    try:
        raw = loader(league.id)
    except Exception as exc:      # noqa: BLE001 - absence is expected today
        view.reason = "%s (%s: %s)" % (
            RIVALS_UNKNOWN, type(exc).__name__,
            str(exc).splitlines()[0][:70] if str(exc) else "no detail")
        return view

    teams_map, coverage = _normalize_rosters(raw)
    view.coverage = coverage
    if teams_map is None:
        view.reason = ("%s (engine/leagueview.py returned no usable "
                       "{slot: {name, players}} mapping)" % RIVALS_UNKNOWN)
        return view

    by_key = dict((p.key, p) for p in players)
    my_keys = set(my_keys or ())
    built, flagged = [], None
    for slot in sorted(teams_map, key=_slot_order):
        entry = teams_map[slot]
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("team") or ""
            roster = entry.get("players", entry.get("roster"))
        else:
            name, roster = "", entry
        team = RivalTeam(slot, name)
        _resolve_team(roster, matcher, by_key, team)
        built.append(team)
        if isinstance(entry, dict) and entry.get("mine") and flagged is None:
            flagged = team

    # Which one is me: the loader's own flag, then best overlap with my
    # known roster, then my_slot. Being wrong here would propose a trade
    # with myself, so the cheapest reliable signal wins.
    mine = flagged
    if mine is None and my_keys:
        scored = [(len(set(p.key for p in t.players) & my_keys), t)
                  for t in built]
        scored.sort(key=lambda st: -st[0])
        if scored and scored[0][0] >= 3 and \
                scored[0][0] >= 0.5 * len(my_keys):
            mine = scored[0][1]
    if mine is None and league.my_slot:
        mine = next((t for t in built if t.slot == str(league.my_slot)), None)
    if mine is not None:
        mine.is_me = True
    view.me = mine
    view.teams = [t for t in built if t is not mine and t.players]
    view.unresolved = [(t.name, list(t.unresolved)) for t in built
                       if t.unresolved]

    if not view.teams:
        view.reason = ("%s (engine/leagueview.py knows %d team%s, none of "
                       "them a rival with players)"
                       % (RIVALS_UNKNOWN, len(built),
                          "" if len(built) == 1 else "s"))
        return view
    view.reason = ("rival rosters known: %d of %d teams via "
                   "engine/leagueview.py%s"
                   % (len(view.teams) + (1 if mine is not None else 0),
                      league.teams,
                      "; me: %s" % mine.name if mine is not None else
                      "; my own team not identified in the feed"))
    return view


# --- positional shape: startable bodies vs starting demand ------------------
def replacement_from_pool(league: LeagueConfig,
                          players: List[Player]) -> Dict[str, float]:
    """League-wide replacement level per position (recommend's own bar)."""
    return replacement_levels(DraftState(league, players))


def positional_net(league: LeagueConfig, roster: List[Player],
                   repl: Dict[str, float]) -> Dict[str, int]:
    """{pos: startable bodies beyond starting demand}; negative = a hole.

    Startable = projects above the league-wide replacement level at the
    position. Hard slots are charged first, then each flex slot is charged
    to the eligible position with the most spare startable bodies (ties to
    the better projection) - the same most-restrictive-first, best-first
    ordering grader.best_lineup uses, so the arithmetic matches the lineup
    a rival would actually field. Only QB/RB/WR/TE: K/DEF are streamers.
    """
    hard = league.hard_starter_counts()
    boards, net, cursor = {}, {}, {}
    for pos in MARKET_POSITIONS:
        board = sorted((p for p in roster if p.pos == pos
                        and float(p.proj_points or 0.0) > repl.get(pos, 0.0)),
                       key=lambda p: -float(p.proj_points or 0.0))
        boards[pos] = board
        net[pos] = len(board) - hard.get(pos, 0)
        cursor[pos] = hard.get(pos, 0)

    def _spare_proj(pos):
        board, i = boards[pos], cursor[pos]
        return float(board[i].proj_points or 0.0) if i < len(board) else -1.0

    for elig in sorted(league.flex_spots(), key=len):
        pool = [pos for pos in elig if pos in net]
        if not pool:
            continue
        best = max(pool, key=lambda pos: (net[pos], _spare_proj(pos)))
        net[best] -= 1
        cursor[best] += 1
    return net


def shape_from_net(net: Dict[str, int]) -> Tuple[List[Tuple[str, int]],
                                                 List[Tuple[str, int]]]:
    """(surplus, holes) as [(pos, count)] lists, biggest first."""
    surplus = sorted([(p, n) for p, n in net.items() if n > 0],
                     key=lambda t: (-t[1], t[0]))
    holes = sorted([(p, -n) for p, n in net.items() if n < 0],
                   key=lambda t: (-t[1], t[0]))
    return surplus, holes


def shape_team(league: LeagueConfig, team: RivalTeam,
               repl: Dict[str, float]) -> RivalTeam:
    team.net = positional_net(league, team.players, repl)
    team.surplus, team.holes = shape_from_net(team.net)
    return team


# --- named targets: their shape crossed with ours ---------------------------
class TradeTarget(object):
    """One concrete 1-for-1 proposal to one named rival team."""

    __slots__ = ("team", "give", "get", "give_market", "get_market",
                 "give_proj", "get_proj", "market_pct", "proj_pct",
                 "blended_pct", "my_delta_wk", "their_delta_wk", "lopsided",
                 "overpay", "lopsided_note", "rationale", "score",
                 "accept_odds", "accept_label", "systems_disagree")

    def headline(self) -> str:
        return "offer %s for %s" % (self.give.surname(), self.get.surname())

    def summary(self) -> str:
        """The one-line form: shape, then the offer it argues for."""
        return "%s is %s; %s" % (self.team.name, self.team.shape_label(),
                                 self.headline())

    def value_label(self) -> str:
        return ("market %s -> %s (%+.0f%%) | proj %s -> %s (%+.0f%%)"
                % (_fmt_val(self.give_market).strip(),
                   _fmt_val(self.get_market).strip(), 100 * self.market_pct,
                   _fmt_val(self.give_proj).strip(),
                   _fmt_val(self.get_proj).strip(), 100 * self.proj_pct))

    def starters_label(self) -> str:
        return ("starters: me %+.1f pts/wk, %s %+.1f pts/wk"
                % (self.my_delta_wk, self.team.name, self.their_delta_wk))


def _chips(roster: List[Player], pos: str, league: LeagueConfig,
           limit: int = TARGET_CHIPS) -> List[Player]:
    """The tradeable bodies at a surplus position: best spare first.

    Hard starters at the position are never offered; what is left is sorted
    best-projection-first so the chip that fetches a starter is considered
    before the one that fetches nothing.
    """
    board = sorted((p for p in roster if p.pos == pos),
                   key=lambda p: -float(p.proj_points or 0.0))
    keep = league.hard_starter_counts().get(pos, 0)
    return board[keep:keep + limit]


def _lineup_delta_wk(league: LeagueConfig, roster: List[Player],
                     out_player: Player, in_player: Player) -> float:
    """pts/wk this roster's best legal lineup gains by swapping out for in."""
    _, before, _ = best_lineup(league, roster)
    after = [p for p in roster if p.key != out_player.key] + [in_player]
    _, after_pts, _ = best_lineup(league, after)
    return (after_pts - before) / float(GAMES_PER_TEAM)


def rival_targets(league: LeagueConfig, players: List[Player],
                  my_roster: List[Player], view: RivalView,
                  market: Dict[str, float], projv: Dict[str, float],
                  repl: Optional[Dict[str, float]] = None,
                  per_team: int = TARGETS_PER_TEAM,
                  limit: int = TARGETS_LIMIT) -> List[TradeTarget]:
    """Ranked concrete proposals, one rival at a time. [] when unavailable.

    We BUY at the positions where their startable net beats ours - the ones
    they can spare and we are short of - and PAY from our own spare bodies
    at any other position. In the textbook mirror (they are RB-rich and
    WR-poor, we are the reverse) that is exactly the obvious swap; on real
    near-balanced rosters it still finds the one-notch version. Hard
    starters are never offered (_chips), both value systems and both
    starting lineups are measured on the real rosters, and nothing survives
    that does not upgrade OUR starting lineup.
    """
    if view is None or not view.available or not my_roster:
        return []
    repl = repl if repl is not None else replacement_from_pool(league, players)
    my_net = positional_net(league, my_roster, repl)

    out = []
    for team in view.teams:
        shape_team(league, team, repl)
        # Cross the two shapes: we BUY where their startable net beats ours
        # (they can spare what we are short of) and PAY from our own spare
        # bodies - every position where we hold more than the hard starting
        # slots demand. A chip that turns out to cost us starting points is
        # rejected below on the measured lineup delta, not by guesswork.
        edge = dict((pos, my_net.get(pos, 0) - team.net.get(pos, 0))
                    for pos in MARKET_POSITIONS)
        get_pos = sorted((p for p in MARKET_POSITIONS if edge[p] < 0),
                         key=lambda p: (edge[p], p))[:2]
        gives, gets = [], []
        for pos in MARKET_POSITIONS:
            if pos in get_pos:
                continue          # never pay from what we are buying
            gives += _chips(my_roster, pos, league)
        for pos in get_pos:
            gets += _chips(team.players, pos, league)
        if not gives or not gets:
            continue

        picks = []
        for give in gives:
            for get in gets:
                t = _build_target(league, players, my_roster, team, give, get,
                                  market, projv)
                if t is not None:
                    picks.append(t)
        # Best first; on a tie the MORE BALANCED offer wins - that is the one
        # you would actually send. One proposal per target player, so the
        # list reads as several ideas rather than one idea five ways.
        picks.sort(key=lambda t: (-t.score, t.blended_pct, t.get.rank))
        seen, kept = set(), []
        for t in picks:
            if t.get.key in seen:
                continue
            seen.add(t.get.key)
            kept.append(t)
            if len(kept) >= max(0, per_team):
                break
        out += kept

    out.sort(key=lambda t: (-t.score, t.blended_pct, t.get.rank))
    return out[:max(0, limit)]


def _build_target(league, players, my_roster, team, give, get, market, projv
                  ) -> Optional[TradeTarget]:
    rep = evaluate_offer(league, players, [give], [get], market, projv,
                         my_roster, len(my_roster))
    if rep.lineup_delta_wk <= 0:
        return None                     # never propose our own downgrade
    t = TradeTarget()
    t.team, t.give, t.get = team, give, get
    t.give_market, t.get_market = rep.give_market, rep.get_market
    t.give_proj, t.get_proj = rep.give_proj, rep.get_proj
    t.market_pct, t.proj_pct = rep.market_pct, rep.proj_pct
    t.blended_pct = rep.blended_pct
    t.my_delta_wk = rep.lineup_delta_wk
    t.their_delta_wk = _lineup_delta_wk(league, team.players, get, give)
    t.systems_disagree = rep.systems_disagree

    t.lopsided = (t.blended_pct >= LOPSIDED_BAND
                  or (t.their_delta_wk <= -LOPSIDED_PTS and t.my_delta_wk > 0))
    t.overpay = (not t.lopsided) and t.blended_pct <= -LOPSIDED_BAND
    t.accept_odds, t.accept_label = acceptance(t.blended_pct,
                                               t.their_delta_wk, t.lopsided)
    if t.lopsided and t.their_delta_wk > 0:
        # Value says we are fleecing them; their own starting lineup says
        # otherwise. Both halves get printed - that disagreement is the
        # whole reason the offer is worth sending.
        t.lopsided_note = (
            "LOPSIDED our way on value (blend %+.0f%%) - but their starters "
            "gain %+.1f pts/wk, so it is worth asking"
            % (100 * t.blended_pct, t.their_delta_wk))
    elif t.lopsided:
        t.lopsided_note = (
            "LOPSIDED our way (blend %+.0f%%, their starters %+.1f pts/wk) - "
            "they likely decline" % (100 * t.blended_pct, t.their_delta_wk))
    elif t.overpay:
        t.lopsided_note = (
            "we overpay on value (blend %+.0f%%) - the lineup gain is real, "
            "so is the price" % (100 * t.blended_pct))
    else:
        t.lopsided_note = t.accept_label

    t.rationale = ("they can spare a %s we are short of; we pay from %s "
                   "depth" % (get.pos, give.pos))
    t.score = t.my_delta_wk * t.accept_odds
    if t.overpay:
        t.score *= OVERPAY_DISCOUNT
    return t


def acceptance(blended_pct: float, their_delta_wk: float,
               lopsided: bool) -> Tuple[float, str]:
    """(odds, one-line read) that the other manager says yes. See constants.

    A lopsided offer whose STARTING LINEUP effect is positive for them is
    not the same as a fleecing: it is the classic "he has depth he cannot
    start" trade, and it gets the middling odds, not the floor.
    """
    if lopsided and their_delta_wk <= 0:
        return ACCEPT_LOPSIDED, "they likely decline"
    fair = abs(blended_pct) <= CLOSE_BAND
    if their_delta_wk > 0 and fair:
        return ACCEPT_MUTUAL, ("both starting lineups gain and the value is "
                               "inside the noise band - the sellable one")
    if their_delta_wk > 0:
        return ACCEPT_THEY_GAIN, ("their starters gain, but they give up "
                                  "value - a real conversation")
    if fair:
        return ACCEPT_FAIR, ("fair value, but their starters do not gain - "
                             "they need to like the player")
    return ACCEPT_TILTED, ("value tilts our way and their starters stay "
                           "flat - a long shot")


# --- offer parsing ----------------------------------------------------------
def parse_offer(text: str) -> Tuple[List[str], List[str]]:
    """'give: X, Y | get: Z' -> (['X','Y'], ['Z']). Order-insensitive."""
    give, get = None, None
    for part in (text or "").split("|"):
        part = part.strip()
        low = part.lower()
        if low.startswith("give"):
            give = part.split(":", 1)[1] if ":" in part else ""
        elif low.startswith("get"):
            get = part.split(":", 1)[1] if ":" in part else ""
    if give is None or get is None:
        raise ValueError(
            'offer must look like: --offer "give: Player A, Player B | '
            'get: Player C"')
    give_names = [n.strip() for n in give.split(",") if n.strip()]
    get_names = [n.strip() for n in get.split(",") if n.strip()]
    if not give_names or not get_names:
        raise ValueError("both sides of the offer need at least one player")
    return give_names, get_names


def resolve_names(names: List[str], matcher: Matcher
                  ) -> Tuple[List[Player], List[str]]:
    """(matched players, names that missed the pool)."""
    hits, misses = [], []
    for n in names:
        m = matcher.match(n)
        if m is None or m.score < MATCH_THRESHOLD:
            misses.append(n)
        else:
            hits.append(m.player)
    return hits, misses


# --- offer evaluation -------------------------------------------------------
class OfferSideRow(object):
    __slots__ = ("player", "market", "proj", "note")

    def __init__(self, player, market, proj, note):
        self.player = player
        self.market = market    # FantasyCalc value, None = market has no price
        self.proj = proj        # our VBD quantile-mapped to the same scale
        self.note = note        # "" | MARKET>>PROJ | PROJ>>MARKET


class OfferReport(object):
    __slots__ = ("give", "get", "give_market", "get_market", "give_proj",
                 "get_proj", "market_pct", "proj_pct", "blended_pct",
                 "verdict", "systems_disagree", "lineup_delta_wk",
                 "lineup_known", "lineup_size", "give_unknown")

    def margin_label(self) -> str:
        return ("market %+.0f%% / proj %+.0f%% (blend %+.0f%%)"
                % (100 * self.market_pct, 100 * self.proj_pct,
                   100 * self.blended_pct))


def _side_rows(side: List[Player], market: Dict[str, float],
               projv: Dict[str, float]) -> Tuple[List[OfferSideRow], float, float]:
    floor = min(market.values()) if market else 0.0
    rows, mkt_total, proj_total = [], 0.0, 0.0
    for p in side:
        mv = market.get(p.key)
        pv = projv.get(p.key)
        rows.append(OfferSideRow(p, mv, pv, disagreement(mv, pv)))
        mkt_total += mv if mv is not None else floor
        proj_total += pv if pv is not None else floor
    return rows, mkt_total, proj_total


def evaluate_offer(league: LeagueConfig, players: List[Player],
                   give: List[Player], get: List[Player],
                   market: Dict[str, float], projv: Dict[str, float],
                   my_roster: List[Player], roster_size: int) -> OfferReport:
    """Score one offer under both value systems + lineup impact.

    Baseline roster for lineup impact = known holdings UNION the give side
    (you would know what you are offering away, even if the roster file has
    not captured it yet); after = baseline - give + get.
    """
    rep = OfferReport()
    rep.give, gm, gp = _side_rows(give, market, projv)
    rep.get, tm, tp = _side_rows(get, market, projv)
    rep.give_market, rep.get_market = gm, tm
    rep.give_proj, rep.get_proj = gp, tp

    rep.market_pct = (tm - gm) / max(gm, tm, 1.0)
    rep.proj_pct = (tp - gp) / max(gp, tp, 1.0)
    rep.blended_pct = (rep.market_pct + rep.proj_pct) / 2.0

    rep.systems_disagree = (
        rep.market_pct * rep.proj_pct < 0
        and abs(rep.market_pct) >= CLOSE_BAND
        and abs(rep.proj_pct) >= CLOSE_BAND)
    if rep.systems_disagree:
        rep.verdict = "CLOSE"
    elif rep.blended_pct >= CLOSE_BAND:
        rep.verdict = "ACCEPT"
    elif rep.blended_pct <= -CLOSE_BAND:
        rep.verdict = "DECLINE"
    else:
        rep.verdict = "CLOSE"

    # Lineup impact over KNOWN holdings (plus the give side, assumed held).
    known_keys = set(p.key for p in my_roster)
    rep.give_unknown = [p for p in give if p.key not in known_keys]
    give_keys = set(p.key for p in give)
    baseline = list(my_roster) + [p for p in rep.give_unknown]
    after = [p for p in baseline if p.key not in give_keys] + list(get)
    _, before_pts, _ = best_lineup(league, baseline)
    _, after_pts, _ = best_lineup(league, after)
    rep.lineup_delta_wk = (after_pts - before_pts) / float(GAMES_PER_TEAM)
    rep.lineup_known = len(baseline)
    rep.lineup_size = roster_size
    return rep


# --- no-offer mode: constructs, not fabricated offers -----------------------
def suggest_constructs(league: LeagueConfig, roster: List[Player],
                       known: int, size: int) -> List[str]:
    """2-3 trade CONSTRUCTS from grader's gap/surplus read of MY roster.

    Constructs name shapes ('shop a WR3 for an RB2'), never rivals - rival
    rosters are unknown without host cookies. Positive-only roster data:
    with partial coverage the constructs say what they are standing on.
    """
    shim = _RosterState(league, roster)
    gaps = positional_gaps(shim, 0)
    surplus = surplus_positions(shim, 0)
    out = []

    gap_positions = [g.split()[0] for g in gaps]
    for s in surplus[:2]:
        pos, count = s.split()[0], s.split()[1]
        targets = [g for g in gap_positions if g not in ("K", "DEF", pos)]
        depth = sum(1 for p in roster if p.pos == pos)
        want = ("a %s2-quality starter" % targets[0] if targets
                else "an upgrade at any starting spot")
        out.append(
            "you are %s startable %s beyond any starting use: shop your "
            "%s%d for %s" % (count, pos, pos, depth, want))
        if len(targets) > 1:
            out.append(
                "package two %s depth pieces to consolidate: 2-for-1 up at "
                "%s - depth you cannot start is only worth what it brings "
                "back" % (pos, targets[1]))

    if not surplus:
        counts = shim.pos_counts()
        deepest = max(counts, key=lambda k: counts[k]) if counts else None
        skill_gaps = [g for g in gap_positions if g not in ("K", "DEF")]
        if deepest and skill_gaps:
            out.append(
                "no surplus among KNOWN players (%d/%d captured) - your "
                "known depth skews %s; if the full roster holds more, shop "
                "the %s you would bench for a %s starter"
                % (known, size, deepest, deepest, skill_gaps[0]))
        if len(skill_gaps) > 1:
            out.append(
                "you show open starting demand at %s: target a rival deep "
                "there and lead with your best bench piece"
                % ", ".join(skill_gaps[:3]))
    return out[:3]


def rival_note(league: LeagueConfig,
               view: Optional[RivalView] = None) -> str:
    """One line on whether rivals can be named at all, and by what.

    Order of truth: an already-built RivalView, then engine/leagueview.py,
    then the guarded (cookie-auth, UNTESTED-live) ESPN read. Every failure
    degrades to a message carrying the literal RIVALS_UNKNOWN line - never a
    crash, and never silence that could read as "no rivals need anything".
    """
    if view is not None:
        return view.reason
    seen = None
    try:
        teams_map, _ = _normalize_rosters(
            _default_rival_loader(league.id, league))
        filled = [s for s, t in (teams_map or {}).items()
                  if isinstance(t, dict) and (t.get("players")
                                              or t.get("roster"))]
        if len(filled) > 1:
            return ("rival rosters available: %d of %d teams via "
                    "engine/leagueview.py" % (len(filled), league.teams))
        if teams_map is not None:
            seen = ("%s (engine/leagueview.py knows %d of %d rosters)"
                    % (RIVALS_UNKNOWN, len(filled), league.teams))
    except Exception:      # noqa: BLE001 - leagueview optional by design
        pass
    if seen:
        return seen
    if league.platform != "espn":
        return ("%s (%s host API not wired, engine/leagueview.py silent)"
                % (RIVALS_UNKNOWN, league.platform or "this"))
    try:
        from . import espn as espn_mod
        lg = espn_mod.connect()
        taken = getattr(espn_mod, "taken_players", None)
        if taken is None:
            return ("rival naming not wired yet (espn.taken_players "
                    "missing) - constructs stay generic")
        names = [str(t) for t in taken(lg)[:5]]
        return "rival-held candidates: " + ", ".join(names)
    except Exception as exc:  # noqa: BLE001 - cookie/env failures expected
        return ("rival naming needs cookies (RUNBOOK A3): %s"
                % (str(exc).splitlines()[0][:70] or type(exc).__name__))


# --- report -----------------------------------------------------------------
def _coverage_banner(c: Ansi, known: int, size: int,
                     unresolved: List[str]) -> List[str]:
    out = []
    if size and known < size:
        out.append(c.yellow(
            " PARTIAL ROSTER: %d of %d players known (data/rosters is "
            "positive-only:" % (known, size)))
        out.append(c.yellow(
            " a player not listed may still be on the roster - absence is "
            "not evidence)."))
    if unresolved:
        out.append(c.dim(" unresolved roster names (no pool match): %s"
                         % ", ".join(unresolved)))
    return out


def _fmt_val(v: Optional[float]) -> str:
    return "%6.0f" % v if v is not None else "     -"


def _offer_side_lines(c: Ansi, title: str, rows: List[OfferSideRow]) -> List[str]:
    out = [c.bold("   %s" % title)]
    for r in rows:
        note = ""
        if r.note:
            note = "  << %s" % r.note
        if r.player.pos not in MARKET_POSITIONS:
            note += "  (no market price: FC skips K/DEF - streamer value)"
        out.append("     %-26s market %s   proj %s   szn %s%s"
                   % (r.player.short_label(), _fmt_val(r.market),
                      _fmt_val(r.proj),
                      ("%.0f" % r.player.proj_points)
                      if r.player.proj_points else "-",
                      note))
    return out


def offer_report_text(league: LeagueConfig, rep: OfferReport,
                      known: int, size: int, unresolved: List[str],
                      color: bool = True, width: int = 74) -> str:
    c = Ansi(color)
    line, thin = "=" * width, "-" * width
    out = [c.cyan(line),
           c.bold(" TRADE ANALYZER   %s   market=FantasyCalc  proj=our ROS "
                  "view" % league.name)]
    out += _coverage_banner(c, known, size, unresolved)
    out.append(thin)
    out += _offer_side_lines(c, "YOU GIVE", rep.give)
    out.append("     %-26s market %s   proj %s"
               % ("TOTAL", _fmt_val(rep.give_market), _fmt_val(rep.give_proj)))
    out += _offer_side_lines(c, "YOU GET", rep.get)
    out.append("     %-26s market %s   proj %s"
               % ("TOTAL", _fmt_val(rep.get_market), _fmt_val(rep.get_proj)))
    out.append(thin)

    verdict_line = " VERDICT: %s   margin: %s" % (rep.verdict,
                                                  rep.margin_label())
    paint = (c.green if rep.verdict == "ACCEPT"
             else c.red if rep.verdict == "DECLINE" else c.yellow)
    out.append(paint(c.bold(verdict_line)))
    if rep.systems_disagree:
        out.append(c.yellow(
            " MARKET AND PROJECTIONS DISAGREE HARD on this offer - one "
            "system says take it,"))
        out.append(c.yellow(
            " the other says run. That split IS the information; verdict "
            "held at CLOSE."))
    out.append(" starter impact: %s your actual lineup by ~%.1f pts/wk"
               % ("upgrades" if rep.lineup_delta_wk >= 0 else "downgrades",
                  abs(rep.lineup_delta_wk)))
    if rep.lineup_size and rep.lineup_known < rep.lineup_size:
        out.append(c.dim(
            "   (lineup impact computed over %d KNOWN players of a %d-man "
            "roster - directional only)" % (rep.lineup_known,
                                            rep.lineup_size)))
    if rep.give_unknown:
        out.append(c.dim(
            "   (give side not in the captured roster file - assumed held: "
            "%s)" % ", ".join(p.surname() for p in rep.give_unknown)))
    out.append(c.cyan(line))
    return "\n".join(out)


def targets_report_lines(c: Ansi, league: LeagueConfig,
                         view: Optional[RivalView],
                         targets: Optional[List[TradeTarget]],
                         my_shape: str = "") -> List[str]:
    """The NAMED TARGETS block, or the honest one-liner in its place."""
    out = [c.bold(" NAMED TARGETS  (rival rosters crossed with ours)")]
    if view is None or not view.available:
        reason = view.reason if view is not None else RIVALS_UNKNOWN
        out.append(c.yellow("   %s" % reason))
        out.append(c.dim("   no rival is named, no offer is invented - the "
                         "CONSTRUCTS below are what the data supports"))
        return out
    out.append(c.dim("   %s" % view.reason))
    if my_shape:
        out.append("   us: %s" % my_shape)
    if not targets:
        out.append("   no 1-for-1 that trades into both sides' holes AND "
                   "upgrades our starting lineup")
        return out
    for i, t in enumerate(targets, start=1):
        out.append(c.green("   %d. %s" % (i, t.summary())))
        out.append("        %s" % t.value_label())
        out.append("        %s" % t.starters_label())
        if t.lopsided or t.overpay:
            out.append(c.yellow("        %s" % t.lopsided_note))
        elif t.lopsided_note:
            out.append(c.dim("        %s" % t.lopsided_note))
        if t.systems_disagree:
            out.append(c.yellow("        market and our projections disagree "
                                "hard on this one - that split IS the thesis"))
    return out


def no_offer_report_text(league: LeagueConfig, roster: List[Player],
                         known: int, size: int, unresolved: List[str],
                         market: Dict[str, float], projv: Dict[str, float],
                         color: bool = True, width: int = 74,
                         view: Optional[RivalView] = None,
                         targets: Optional[List[TradeTarget]] = None,
                         repl: Optional[Dict[str, float]] = None) -> str:
    c = Ansi(color)
    line, thin = "=" * width, "-" * width
    out = [c.cyan(line),
           c.bold(" TRADE ANALYZER   %s   (no offer given - roster read + "
                  "constructs)" % league.name)]
    out += _coverage_banner(c, known, size, unresolved)
    out.append(thin)
    out.append(c.bold(" KNOWN HOLDINGS  (market=FantasyCalc, proj=our ROS "
                      "view on the same scale)"))
    if not roster:
        out.append("   no roster file captured for this league yet "
                   "(data/rosters/%s.yaml)" % league.id)
    for p in roster:
        mv, pv = market.get(p.key), projv.get(p.key)
        note = disagreement(mv, pv)
        out.append("   %-26s market %s   proj %s%s"
                   % (p.short_label(), _fmt_val(mv), _fmt_val(pv),
                      ("   << " + note) if note else ""))

    shim = _RosterState(league, roster)
    gaps = positional_gaps(shim, 0)
    surplus = surplus_positions(shim, 0)
    out.append(thin)
    out.append(c.bold(" GAPS AND AMMO  (grader logic over KNOWN players "
                      "only)"))
    out.append(c.yellow("   need: " + (", ".join(gaps) if gaps else
                                       "none - every starting slot covered")))
    out.append("   ammo: " + (", ".join(surplus) if surplus else
                              "none among known players"))

    out.append(thin)
    my_shape = ""
    if roster and repl:
        s_sur, s_hole = shape_from_net(positional_net(league, roster, repl))
        bits = ["+%d startable %s" % (n, p) for p, n in s_sur]
        bits += ["-%d %s" % (n, p) for p, n in s_hole]
        my_shape = ", ".join(bits) if bits else "no startable surplus or hole"
    out += targets_report_lines(c, league, view, targets, my_shape)

    out.append(thin)
    out.append(c.bold(" TRADE CONSTRUCTS  (shapes to shop, not offers to "
                      "named rivals)"))
    constructs = suggest_constructs(league, roster, known, size)
    if not constructs:
        out.append("   too little roster known to shape a trade - capture "
                   "more names in data/rosters/%s.yaml" % league.id)
    for s in constructs:
        out.append("   * %s" % s)
    out.append(c.dim("   " + rival_note(league, view)))
    out.append(c.cyan(line))
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.trades",
        description="Trade analyzer: FantasyCalc market values blended with "
                    "our ROS projections.")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--offer", default=None,
                    help='"give: Player A, Player B | get: Player C"')
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    league_path = os.path.join(HERE, "leagues", "%s.yaml" % args.league)
    if not os.path.exists(league_path):
        print("no league yaml at %s" % league_path)
        return 1
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        print("rankings csv missing: %s" % csv_path)
        return 1
    players = load_players(csv_path)
    matcher = Matcher(players)

    ppr = ppr_param(league)
    nqb = num_qbs_param(league)
    try:
        raw = fetch_fantasycalc(ppr, nqb)
    except RuntimeError as exc:
        print(str(exc))
        return 1
    market = market_values(players, parse_rows(raw), matcher)
    projv = proj_scale_values(league, players, market)

    roster, known, size, unresolved = load_my_roster(league, matcher, players)
    color = (not args.no_color) and sys.stdout.isatty()

    if not args.offer:
        repl = replacement_from_pool(league, players)
        view = load_rival_view(league, matcher, players,
                               my_keys=set(p.key for p in roster))
        # leagueview may know MY roster more completely than the capture
        # file does; union it in (positive-only - a name in either is held).
        if view.me is not None:
            have = set(p.key for p in roster)
            extra = [p for p in view.me.players if p.key not in have]
            if extra:
                roster = sorted(roster + extra, key=lambda p: p.rank)
                known = len(roster)
        targets = rival_targets(league, players, roster, view, market, projv,
                                repl=repl)
        print(no_offer_report_text(league, roster, known, size, unresolved,
                                   market, projv, color=color, view=view,
                                   targets=targets, repl=repl))
        return 0

    try:
        give_names, get_names = parse_offer(args.offer)
    except ValueError as exc:
        print(str(exc))
        return 1
    give, miss_g = resolve_names(give_names, matcher)
    get, miss_t = resolve_names(get_names, matcher)
    if miss_g or miss_t:
        for n in miss_g + miss_t:
            print("no player in the pool matches %r" % n)
        return 1
    rep = evaluate_offer(league, players, give, get, market, projv,
                         roster, size)
    print(offer_report_text(league, rep, known, size, unresolved,
                            color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
