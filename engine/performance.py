"""Source performance + hot streaks: which voices have actually been right.

    python -m engine.performance --league espn-1 [--backfill]

THE HONESTY PROBLEM THIS MODULE EXISTS TO SOLVE
===============================================
It is Sep 2026. Week 1 has not kicked off, data/source_ledger.jsonl is
empty, and NOT ONE source in data/sources.yaml has a graded in-season call.
A performance page that renders anything other than "no data" for a creator
today would be inventing a track record.

But that verdict is not uniform, and pretending it is would be its own kind
of dishonesty. The registry holds two different species of voice:

  CREATOR sources (the-favorites, sharp-or-square - anything whose registry
  `type` is not "feed", plus the hand-curated house-research desk) speak in
  video and prose. We never recorded what they said in 2025. Their history
  genuinely starts at zero and fills one week at a time. They are NEVER
  backfilled: backfill_feed() refuses them by name and returns the reason.
  Guessing what a YouTuber would have said about Week 6 2025 is fabrication,
  full stop.

  ALGORITHMIC FEEDS (engine, espn-proj, sleeper-proj) publish a NUMBER for
  every player every week, and both ESPN and Sleeper still serve their 2025
  weekly projection archives (verified live, Sep 2026). A projection implies
  a start/sit - start iff the number clears the positional replacement line -
  so their 2025 calls are reconstructible, and nflverse ships what actually
  happened. Those are backfilled and every reconstructed row is stamped
  provenance="backfill-2025" so it can never be mistaken for something the
  source said into the live ledger before kickoff.

  chen-tiers is an algorithmic feed with NO archive: borischen.co publishes
  one current snapshot per position (text_RB-PPR.txt), overwritten weekly,
  with no history. It is refused for a different reason than the creators
  are, and the reason is printed.

CAVEATS ON THE BACKFILL, STATED UP FRONT RATHER THAN BURIED
-----------------------------------------------------------
1. ARCHIVE, NOT SNAPSHOT. ESPN's and Sleeper's 2025 weekly projections are
   read TODAY. They are almost certainly the numbers those feeds filed at
   the time, but nothing proves they were never revised after kickoff. A
   backfilled row is a reconstruction of a past call, not a contemporaneous
   recording. That is exactly why it carries its own provenance tag and is
   written to its own file instead of into the humility ledger.
2. THE ENGINE ROW IS NOT A LINEUP REPLAY. Live, the `engine` voice votes by
   running best_lineup over YOUR roster. There were no 2025 rosters, so the
   backfilled engine row grades its projection blend (ESPN primary, Sleeper
   filling gaps - weekly._merge_weekly, the same merge it uses live) by the
   replacement rule, like every other feed. Same yardstick for all three,
   different from the live engine vote. Labelled, not hidden.
3. SYMMETRIC UNSCORABLES. A player with no row in the actuals file that week
   (bye, inactive, never took a snap) is UNSCORABLE for both directions.
   Scoring the sit side as a hit would hand every feed a pile of free
   bye-week wins; scoring the start side as a zero would punish it for
   injury news the projection already priced. Neither side is graded, the
   count rides along in the scoreboard as `unscorable_n`, and nothing is
   silently deleted.
4. K AND DEF ARE UNGRADED. The actuals feed (ffopportunity) is offense-only.
   Kicker and defense calls are dropped with a counted reason.
5. THE GRADED UNIVERSE IS THE ROSTERABLE POOL. Grading every projected
   player would be a fraud dressed as rigour: ~90% of the league is
   correctly benched, so every source would score ~90% and look like a
   genius. We grade only the decision-relevant pool - the top
   ROSTERABLE_MULT x starter-demand players at each position on that
   source's OWN board - where both a start and a sit are live possibilities.
   Each row's start/sit split is reported so the remaining asymmetry stays
   visible.

THE GRADING RULE (one rule, documented here)
============================================
A START call is a HIT when the player's actual points that week are >= the
positional replacement level. A SIT call is a HIT when they are below it.
Replacement is engine/recommend.replacement_levels: the Nth-best score at
that position, N = this league's hard starters x teams PLUS the flex slots
that position actually wins in the pool (recommend.flex_allocation). The
same function draws both lines this module uses:

  * the PROJECTED line, off the source's own weekly board - what its numbers
    imply it was saying;
  * the ACTUAL line, off that week's realized league-wide scores - the bar
    the week itself set.

An 8-team league's line is far higher than a 12-team league's, so grades are
per-league by construction; a source is never graded against a replacement
level from a league it was not advising.

NOTE ON A DELIBERATE DIVERGENCE: consensus.score_entries grades the live
ledger with its own replacement helper, which splits flex slots EVENLY among
eligible positions. This module uses recommend.replacement_levels, which
reads flex demand off the pool. They agree on hard starters and differ only
in flex allocation. Said out loud here rather than papered over; the flex-
allocation version is the better line, and swapping consensus over is a
change to a module this one does not own.

MARGIN: every graded row records `margin` (actual - replacement, signed
against the line) and `edge` (the same number signed FOR the call, so
positive is right whichever way the call went) plus a `band`: narrow
(< 2 pts), clear (>= 2), loud (>= 5). A source that is barely right on
everything and loudly wrong on the calls that mattered reads very
differently from one that is quietly wrong and loudly right, and a bare hit
rate hides exactly that.

STREAK STATES (a judgment call, and labelled as one)
====================================================
There is no arithmetic that proves a source is "hot" - hot is a bet that
recent form carries information. This is where the line is drawn, and the
numbers are constants at the top of this file so an argument with them is an
argument with a number, not with the code:

  NO-DATA          zero graded calls on this basis.
  LOW-CONFIDENCE   fewer than MIN_GRADED_CALLS (30) graded calls or fewer
                   than MIN_GRADED_WEEKS (3) weeks. NEVER hot, never cold -
                   a 2-for-2 source is not a genius, it is two data points,
                   and this floor exists so it can never be crowned.
  HOT              at least STREAK_MIN (2) consecutive recent weeks above
                   the source's OWN season baseline, AND its last-ROLLING_N
                   (4) week pooled rate is at least HOT_BAND (5 points)
                   above that baseline, AND the rolling window itself
                   carries MIN_ROLLING_CALLS (12) calls.
  COLD             the mirror image.
  STEADY           graded, past the floor, not on a run either way.

Weeks with fewer than MIN_WEEK_CALLS (5) graded calls are "thin": they are
kept in the series (with thin=True) and shown in charts, but they cannot
start, extend or break a streak. A source is compared to ITSELF, not to the
field - hot means "better than this source usually is", which is the only
comparison that survives sources grading different player pools.

STATE IS ALWAYS A CLAIM ABOUT NOW. A HOT badge computed off 2025 backfill
would be a lie about this week's form, so `state` is derived from LIVE rows
only. With the ledger empty, every source's `state` today is NO-DATA - the
feeds included - and the 2025 read is carried separately as
`backfill_state`, explicitly scoped to "as of the end of 2025". The flat
hit_rate / sample_n / per_position / sparkline_values mirror whichever basis
`provenance` names; `bases` holds each basis broken out and never averaged.

FILES: backfilled rows go to data/performance_history.jsonl (HISTORY_PATH),
NOT into data/source_ledger.jsonl. The ledger is the record of what was said
before kickoff and reconstruction does not belong in it. Live rows are read
back out of the ledger through consensus.read_ledger and tagged "live".
Tests must redirect performance.HISTORY_PATH to a tempdir (same rule as
consensus.LEDGER_PATH and streaming.LOG_PATH).
"""

import argparse
import datetime
import json
import math
import os
import sys
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from engine import consensus, recommend, weekly
    from engine import sources as sources_mod
    from engine.models import POSITIONS, LeagueConfig, Player, norm_pos
    from engine.projections import name_key
except ImportError:  # run directly as `python engine/performance.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import consensus, recommend, weekly
    from engine import sources as sources_mod
    from engine.models import POSITIONS, LeagueConfig, Player, norm_pos
    from engine.projections import name_key

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_PATH = os.path.join(HERE, "data", "performance_history.jsonl")
CACHE_DIR = os.path.join(HERE, "data", "cache")

SEASON_BACKFILL = 2025
FINAL_WEEK = 18

PROV_LIVE = "live"
PROV_BACKFILL = "backfill-%d" % SEASON_BACKFILL

# The actuals feed is offense-only, so these are the only gradeable slots.
GRADED_POSITIONS = ("QB", "RB", "WR", "TE")

# Decision-relevant depth: this many times the league's starter demand at a
# position is the pool where a start/sit is a real question (see caveat 5).
ROSTERABLE_MULT = 2.0

# Margin bands - "barely right" vs "loud right", in fantasy points.
CLEAR_PTS = 2.0
LOUD_PTS = 5.0

# --- the streak judgment call, as numbers you can argue with ---------------
MIN_GRADED_CALLS = 30     # below this: LOW-CONFIDENCE, never HOT/COLD
MIN_GRADED_WEEKS = 3      # ...and this many distinct graded weeks
MIN_WEEK_CALLS = 5        # a week thinner than this cannot move a streak
ROLLING_N = 4             # "recent form" window, in non-thin weeks
MIN_ROLLING_CALLS = 12    # ...which must itself carry this many calls
HOT_BAND = 0.05           # rolling rate must clear own baseline by 5 pts
STREAK_MIN = 2            # consecutive weeks needed to call it a run

STATES = ("HOT", "COLD", "STEADY", "LOW-CONFIDENCE", "NO-DATA")

# --- backfill decay -------------------------------------------------------
# The 2025 reconstruction is the only evidence that exists before week 1, and
# it is worthless once this season has spoken for itself. So it does not sit
# beside the live record forever - it PHASES OUT on a fixed schedule, by
# completed weeks of the current season:
#
#   0 weeks (pre-season) -> 1.00   the archive is all we have
#   1 week               -> 0.60   one live week, still thin
#   2 weeks              -> 0.30   live record taking over
#   3+ weeks             -> 0.00   this season only; the archive is retired
#
# Judgment call, per the owner's spec. The shape matters more than the exact
# numbers: a fast decay, fully retired by the end of week 3, because roster
# and scheme turnover makes a 2025 read stale quickly and because three live
# weeks is where the live sample starts to mean something on its own.
BACKFILL_DECAY = {0: 1.00, 1: 0.60, 2: 0.30}
BACKFILL_RETIRED_AFTER = 3


def backfill_weight(weeks_played: int) -> float:
    """Share of the headline number the 2025 archive still carries."""
    try:
        w = int(weeks_played)
    except (TypeError, ValueError):
        w = 0
    if w < 0:
        w = 0
    return BACKFILL_DECAY.get(w, 0.0)


def blend_label(w_back: float) -> str:
    """What the headline number is actually made of - never hide the mix."""
    if w_back >= 0.999:
        return "%d archive" % SEASON_BACKFILL
    if w_back <= 0.0:
        return "this season"
    if w_back >= 0.5:
        return "%d-weighted" % SEASON_BACKFILL
    return "mostly %d" % weekly.SEASON


def blend_bases(bases: Dict, weeks_played: int) -> Dict:
    """Decay-weighted headline across the two bases.

    `bases` itself stays pure - the two records are still reported unmixed,
    because a reader must always be able to see each on its own. This adds
    the blended headline the pages show, plus the label that says what went
    into it and the weights that produced it.
    """
    live = bases.get(PROV_LIVE)
    back = bases.get(PROV_BACKFILL)
    w_back = backfill_weight(weeks_played)
    if back is None:
        w_back = 0.0
    if live is None:
        w_back = 1.0 if back is not None else 0.0
    w_live = 1.0 - w_back

    def rate(basis):
        return None if basis is None else basis.get("hit_rate")

    lr, br = rate(live), rate(back)
    if lr is None and br is None:
        blended = None
    elif lr is None:
        blended = br
    elif br is None or w_back <= 0.0:
        blended = lr
    else:
        blended = (w_back * br) + (w_live * lr)

    retired = weeks_played >= BACKFILL_RETIRED_AFTER
    if retired and back is not None:
        note = ("%d archive retired - %d completed weeks of %d now carry the "
                "number on their own." % (SEASON_BACKFILL, weeks_played,
                                          weekly.SEASON))
    elif back is not None and w_back > 0.0:
        note = ("%.0f%% %d archive / %.0f%% %d live, decaying to zero after "
                "week %d." % (100 * w_back, SEASON_BACKFILL, 100 * w_live,
                              weekly.SEASON, BACKFILL_RETIRED_AFTER))
    else:
        note = "no %d archive in this number." % SEASON_BACKFILL

    return {
        "hit_rate": blended,
        "label": blend_label(w_back),
        "weight_backfill": w_back,
        "weight_live": w_live,
        "weeks_played": weeks_played,
        "retired": retired,
        "note": note,
    }


def weeks_completed(week: Optional[int] = None) -> int:
    """Completed weeks of the current season (week 1 in progress -> 0)."""
    if week is None:
        try:
            week = weekly.current_week()
        except Exception:
            week = None
    if not week:
        return 0
    return max(0, int(week) - 1)


# Feeds whose 2025 weekly projections are still served. Anything not listed
# is refused with its own reason - silence is not an archive.
ARCHIVED_FEEDS = ("espn-proj", "sleeper-proj", "engine")

NO_ARCHIVE_REASON = {
    "chen-tiers":
        "borischen.co publishes one current snapshot per position "
        "(text_<POS>-<FMT>.txt), overwritten each week with no history - "
        "there is no 2025 tier file to reconstruct a call from",
    "house-research":
        "hand-curated desk verdicts (data/player_intel.yaml), written by a "
        "person in Aug 2026 - nothing was filed for 2025",
}

CREATOR_REASON = ("no history - starts accumulating week 1. Nothing this "
                  "source said in 2025 was ever recorded, and inventing it "
                  "would be fabrication, not a backfill")

_HISTORY_CACHE_AGE_H = 24.0 * 365.0   # a finished season never changes


# --- source classification --------------------------------------------------

def is_creator(source: Dict) -> bool:
    """True for a voice that speaks in prose/video rather than numbers.

    Registry `type` other than "feed" is a creator by construction. The one
    feed-typed exception is house-research: it points at the engine handle
    but its content is hand-written verdicts, so it has no archive either -
    it is classified by NO_ARCHIVE_REASON rather than here.
    """
    return (source.get("type") or "").strip().lower() != "feed"


def backfill_capability(source: Dict) -> Tuple[bool, str]:
    """(can_backfill, reason). The reason is printed either way.

    Three distinct answers, never collapsed into one shrug:
      creator          -> never, on principle (CREATOR_REASON);
      feed, no archive -> not possible, and which archive is missing;
      feed, archived   -> yes, and where the numbers come from.
    """
    sid = source.get("id")
    if is_creator(source):
        return False, CREATOR_REASON
    if sid in NO_ARCHIVE_REASON:
        return False, NO_ARCHIVE_REASON[sid]
    if sid in ARCHIVED_FEEDS:
        return True, ("%s still serves its %d weekly projection archive; "
                      "calls are reconstructed by the replacement rule"
                      % (sid, SEASON_BACKFILL))
    return False, ("unknown feed %r - no historical projection archive is "
                   "wired up for it" % (sid,))


def load_league(league) -> LeagueConfig:
    """Accept a LeagueConfig or a league id; never write to leagues/."""
    if isinstance(league, LeagueConfig):
        return league
    return LeagueConfig.load(os.path.join(HERE, "leagues", "%s.yaml" % league))


# --- the replacement rule (recommend.replacement_levels, twice) -------------

class _PoolState(object):
    """The two attributes recommend.replacement_levels reads: league, players.

    A shim, not a DraftState: replacement_levels is a pure function of the
    league's slot layout and a pool of players carrying proj_points, so the
    same function draws a line off projections and off realized scores.
    """

    __slots__ = ("league", "players")

    def __init__(self, league: LeagueConfig, players: List[Player]):
        self.league = league
        self.players = players


def _pool(rows: Sequence[Dict]) -> List[Player]:
    """[{name, pos, points}] -> Players carrying points as proj_points."""
    out = []
    for i, r in enumerate(rows):
        pos = norm_pos(r.get("pos") or "")
        if pos not in POSITIONS:
            continue
        pts = r.get("points")
        if pts is None:
            continue
        out.append(Player(rank=i + 1, name=r.get("name") or "",
                          pos=pos, team=r.get("team") or "",
                          proj_points=float(pts)))
    return out


def replacement_line(league: LeagueConfig,
                     rows: Sequence[Dict]) -> Dict[str, float]:
    """{pos: replacement points} for a pool of [{name, pos, points}].

    Straight delegation to recommend.replacement_levels - the Nth-best score
    at each position, N = hard starters x teams + the flex slots that
    position wins in THIS pool. Feed it projections and it is the line the
    projections imply; feed it a week's realized scores and it is the line
    the week actually set.
    """
    return recommend.replacement_levels(_PoolState(league, _pool(rows)))


def starter_demand(league: LeagueConfig,
                   rows: Sequence[Dict]) -> Dict[str, int]:
    """The N behind replacement_line, per position - same primitives.

    Computed from recommend.flex_allocation on the same pool, so the depth
    used to pick the graded universe cannot drift away from the line used to
    grade it.
    """
    players = _pool(rows)
    hard = league.hard_starter_counts()
    flex = recommend.flex_allocation(league, players)
    out = {}
    for pos in POSITIONS:
        n = int(round(hard.get(pos, 0) * league.teams + flex.get(pos, 0.0)))
        if n > 0:
            out[pos] = n
    return out


def rosterable_depth(demand: Dict[str, int],
                     mult: float = ROSTERABLE_MULT) -> Dict[str, int]:
    """How deep a position stays decision-relevant (see caveat 5)."""
    return dict((pos, int(math.ceil(n * mult))) for pos, n in demand.items())


# --- grading ----------------------------------------------------------------

def _norm_call(verdict) -> Optional[str]:
    """Ledger/consensus verdicts -> the two gradeable directions.

    'flex' is a start-side call (consensus.VERDICT_VALUE puts it above
    zero); 'rank' is graded only through its start/sit conversion upstream,
    exactly as consensus.score_entries rules, so it lands unscorable here.
    """
    v = (verdict or "").strip().lower()
    if v in ("start", "flex"):
        return "start"
    if v == "sit":
        return "sit"
    return None


def band_of(edge: float) -> str:
    """narrow / clear / loud - how much the call actually said."""
    a = abs(edge)
    if a >= LOUD_PTS:
        return "loud"
    if a >= CLEAR_PTS:
        return "clear"
    return "narrow"


def score(call: Dict, actual: Optional[float]) -> Dict:
    """Grade ONE call against ONE actual. Returns a graded COPY.

    `call` carries at least "call" (start|sit|flex) and "replacement" (that
    week's positional line from replacement_line). `actual` is the player's
    realized points, or None when the actuals feed filed no row for him.

    THE RULE: a start call hits when actual >= replacement; a sit call hits
    when actual < replacement. Ties go to the start call, matching
    consensus.score_entries so the live ledger and this history agree on the
    boundary.

    Also records:
      margin  actual - replacement, signed against the LINE (a start and a
              sit on the same player-week share a margin);
      edge    the same gap signed FOR the call, so positive is right either
              way - the number a "barely right vs loud right" read needs;
      band    narrow / clear / loud, off |edge|.

    Never raises and never guesses: anything ungradeable comes back with
    hit=None and an `unscorable` reason string.
    """
    out = dict(call)
    out.pop("unscorable", None)
    direction = _norm_call(call.get("call") or call.get("verdict"))
    out["call"] = direction or (call.get("call") or call.get("verdict"))
    out["actual"] = None
    out["margin"] = None
    out["edge"] = None
    out["band"] = None
    out["hit"] = None

    if direction is None:
        out["unscorable"] = ("verdict %r is not a start/sit call"
                             % (call.get("call") or call.get("verdict"),))
        return out
    repl = call.get("replacement")
    if repl is None:
        out["unscorable"] = "no positional replacement line for this week"
        return out
    if actual is None:
        out["unscorable"] = ("no actual filed (bye/inactive/no snap - the "
                             "actuals feed files only players who played)")
        return out

    margin = round(float(actual) - float(repl), 2)
    edge = margin if direction == "start" else -margin
    out["actual"] = round(float(actual), 2)
    out["replacement"] = round(float(repl), 2)
    out["margin"] = margin
    out["edge"] = round(edge, 2)
    out["band"] = band_of(edge)
    out["hit"] = bool(margin >= 0) if direction == "start" else bool(margin < 0)
    return out


def grade_calls(calls: Sequence[Dict],
                actuals: Dict[str, float]) -> List[Dict]:
    """score() over a week's calls; {nkey: actual points} supplies the truth."""
    return [score(c, actuals.get(c.get("player_key") or c.get("nkey")))
            for c in calls]


# --- the 2025 actuals -------------------------------------------------------

def season_actuals(season: int = SEASON_BACKFILL,
                   force: bool = False) -> Dict[int, Dict[str, Dict]]:
    """{week: {nkey: {"actual": pts, "pos": POS}}} for a whole season.

    Points come from nflverse.fetch_xfp(season) - the ffopportunity weekly
    file, the SAME feed consensus.week_actuals grades the live ledger
    against, so a backfilled week and a live week are measured with one
    yardstick. Its fantasy points are FULL PPR (verified against the raw
    columns: receptions score 1.0), which is what both of Andrew's leagues
    play. Positions come from the same cached CSV's `position` column.
    """
    from engine import nflverse
    weeks: Dict[int, Dict[str, Dict]] = {}
    pos_map = _season_positions(season, force=force)
    for nkey, rows in nflverse.fetch_xfp(season, force=force).items():
        pos = pos_map.get(nkey)
        if pos not in GRADED_POSITIONS:
            continue
        for row in rows:
            weeks.setdefault(int(row["week"]), {})[nkey] = {
                "actual": float(row["actual"]), "pos": pos}
    return weeks


def _season_positions(season: int, force: bool = False) -> Dict[str, str]:
    """{nkey: position} from the same cached ffopportunity file."""
    from engine import nflverse
    rows = nflverse._fetch_csv(nflverse.XFP_URL % season,
                               "nflverse-xfp-%d.csv" % season,
                               "total_fantasy_points_exp",
                               max_age_hours=_HISTORY_CACHE_AGE_H, force=force)
    out = {}
    for r in rows:
        key = name_key(r.get("full_name", ""))
        pos = norm_pos(r.get("position") or "")
        if key and pos:
            out[key] = pos
    return out


def actual_rows(week_map: Dict[str, Dict]) -> List[Dict]:
    """{nkey: {actual,pos}} -> the [{name,pos,points}] pool shape."""
    return [{"name": nkey, "pos": rec["pos"], "points": rec["actual"]}
            for nkey, rec in week_map.items()]


# --- the feeds' own 2025 archives -------------------------------------------

def _reduced_path(source_id: str, season: int, week: int, scoring: str) -> str:
    return os.path.join(CACHE_DIR, "perf-%s-%s-%d-wk%d.json"
                        % (source_id, scoring, season, week))


def _read_reduced(path: str) -> Optional[Dict[str, Dict]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fh:
            doc = json.load(fh)
    except (ValueError, OSError):
        return None
    return doc if isinstance(doc, dict) else None


def _write_reduced(path: str, data: Dict[str, Dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def _espn_season_records(season: int, scoring: str,
                         force: bool = False) -> Dict[str, Dict]:
    """ESPN kona weekly projections for a PAST season, keyed by name.

    projections.fetch_espn hardcodes its SEASON, so the season-parameterized
    read lives here - but it reuses that module's URL, fantasy filter,
    position and pro-team maps and its fetch/cache helper, so there is still
    exactly one definition of each. A finished season is immutable, hence
    the year-long freshness window.

    Half-PPR has no working ESPN leaguedefault (ids 2/4 are 404), so a half
    week is the mean of the PPR and standard weeks - exact, since they
    differ only by points per reception on identical projections. Same trick
    weekly._espn_weekly_records uses for the live season.
    """
    from engine import projections as proj_mod
    if scoring == "half":
        ppr = _espn_season_records(season, "ppr", force=force)
        std = _espn_season_records(season, "std", force=force)
        for key, rec in ppr.items():
            sw = (std.get(key) or {}).get("weekly", {})
            rec["weekly"] = dict(
                (w, round((p + sw[w]) / 2.0, 2) if w in sw else p)
                for w, p in rec["weekly"].items())
        return ppr

    format_id = 3 if scoring == "ppr" else 1
    payload = proj_mod._fetch_json(
        proj_mod.ESPN_URL % (season, format_id),
        "espn-kona-%s-%d.json" % (proj_mod.ESPN_FORMATS[format_id], season),
        {"User-Agent": proj_mod.UA, "Accept": "application/json",
         "X-Fantasy-Filter": json.dumps(proj_mod.ESPN_FILTER)},
        force=force, max_age_hours=_HISTORY_CACHE_AGE_H, quiet=True)

    out: Dict[str, Dict] = {}
    for entry in payload.get("players", []):
        pl = entry.get("player") or {}
        name = pl.get("fullName", "")
        pos = proj_mod.ESPN_POS.get(pl.get("defaultPositionId"))
        if not name or not pos:
            continue
        wk = {}
        for st in pl.get("stats", []):
            period = st.get("scoringPeriodId")
            if (st.get("seasonId") == season and st.get("statSourceId") == 1
                    and st.get("statSplitTypeId") == 1
                    and period and 1 <= period <= FINAL_WEEK):
                wk[int(period)] = round(st.get("appliedTotal") or 0.0, 2)
        rec = {"name": name, "pos": pos, "weekly": wk,
               "team": proj_mod.norm_team(
                   proj_mod.ESPN_PRO_TEAMS.get(pl.get("proTeamId"), ""))}
        key = name_key(name)
        old = out.get(key)
        if old is None or len(wk) > len(old["weekly"]):
            out[key] = rec
    return out


def _sleeper_archive_week(season: int, week: int, scoring: str,
                          force: bool = False) -> Dict[str, Dict]:
    """Sleeper's weekly projections for a past season+week, reduced on write.

    Sleeper's raw weekly payload is ~2.3 MB; eighteen of them is 40 MB of
    cache for numbers that will never change again. We keep only the reduced
    {name_key: {proj,pos,team}} map (weekly._weekly_from_sleeper does the
    reduction - same transform the live path uses), which is ~100 KB.
    Network failure with a cache present serves the cache; no cache and no
    network raises, same contract as every other fetcher here.
    """
    path = _reduced_path("sleeper-proj", season, week, scoring)
    if not force:
        cached = _read_reduced(path)
        if cached is not None:
            return cached
    url = weekly.SLEEPER_WEEKLY_URL % (season, week)
    req = urllib.request.Request(
        url, headers={"User-Agent": weekly.UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, ValueError, OSError) as exc:
        cached = _read_reduced(path)
        if cached is not None:
            return cached
        raise RuntimeError("Could not fetch %s and no cache exists: %s"
                           % (url, exc))
    reduced = weekly._weekly_from_sleeper(payload, scoring)
    # _weekly_from_sleeper keys by normalized name and drops the spelling;
    # graded rows are read by humans, so the display name rides along.
    for entry in payload:
        pl = entry.get("player") or {}
        nm = ("%s %s" % (pl.get("first_name", ""),
                         pl.get("last_name", ""))).strip()
        rec = reduced.get(name_key(nm))
        if nm and rec is not None and not rec.get("name"):
            rec["name"] = nm
    _write_reduced(path, reduced)
    return reduced


def _espn_archive_week(season: int, week: int, scoring: str,
                       force: bool = False) -> Dict[str, Dict]:
    """ESPN's week-N projections for a past season, in weekly-map shape."""
    records = _espn_season_records(season, scoring, force=force)
    out = weekly._weekly_from_espn(records, week)
    for key, rec in out.items():
        nm = (records.get(key) or {}).get("name")
        if nm:
            rec["name"] = nm
    return out


def feed_projections(source_id: str, season: int, week: int,
                     scoring: str = "ppr",
                     force: bool = False) -> Dict[str, Dict]:
    """{name_key: {"proj","pos","team",...}} - one feed's archived week.

    engine = ESPN primary, Sleeper filling the gaps, through
    weekly._merge_weekly: the exact blend the live engine voice scores its
    lineup on, so its backfilled calls come off the same numbers.
    """
    scoring = weekly._norm_scoring(scoring)
    if source_id == "espn-proj":
        return _espn_archive_week(season, week, scoring, force=force)
    if source_id == "sleeper-proj":
        return _sleeper_archive_week(season, week, scoring, force=force)
    if source_id == "engine":
        try:
            espn = _espn_archive_week(season, week, scoring, force=force)
        except RuntimeError:
            espn = {}
        try:
            sleeper = _sleeper_archive_week(season, week, scoring, force=force)
        except RuntimeError:
            sleeper = {}
        if not espn and not sleeper:
            raise RuntimeError("neither archive reachable for %d week %d"
                               % (season, week))
        return weekly._merge_weekly(espn, sleeper)
    raise ValueError("no archive wired up for feed %r" % (source_id,))


# --- reconstructing a feed's implied calls ----------------------------------

def implied_calls(source_id: str, league: LeagueConfig,
                  proj_map: Dict[str, Dict], week: int,
                  season: int = SEASON_BACKFILL,
                  provenance: str = PROV_BACKFILL) -> Tuple[List[Dict], Dict]:
    """A feed's weekly projections -> the start/sit calls they imply.

    (calls, note). Start iff the projection clears that position's PROJECTED
    replacement line - the line this source's own board draws under this
    league's slot layout. The graded universe is the rosterable pool: the
    top rosterable_depth() players per position on that same board, where a
    sit is a genuine decision rather than a formality. Positions outside
    GRADED_POSITIONS are dropped and counted, never graded.
    """
    rows = [{"name": k, "pos": r.get("pos"), "team": r.get("team"),
             "points": r.get("proj")}
            for k, r in proj_map.items()]
    demand = starter_demand(league, rows)
    depth = rosterable_depth(demand)
    line = replacement_line(league, rows)

    by_pos: Dict[str, List[Tuple[float, str, Dict]]] = {}
    dropped_pos = 0
    for key, rec in proj_map.items():
        pos = norm_pos(rec.get("pos") or "")
        if pos not in GRADED_POSITIONS:
            dropped_pos += 1
            continue
        if rec.get("proj") is None:
            continue
        by_pos.setdefault(pos, []).append((float(rec["proj"]), key, rec))

    calls: List[Dict] = []
    for pos, entries in by_pos.items():
        repl = line.get(pos)
        n = depth.get(pos)
        if repl is None or not n:
            continue
        entries.sort(key=lambda e: (-e[0], e[1]))
        for proj, key, rec in entries[:n]:
            calls.append({
                "source": source_id, "season": int(season), "week": int(week),
                "player": rec.get("name") or key, "player_key": key,
                "pos": pos, "team": rec.get("team") or "",
                "call": "start" if proj >= repl else "sit",
                "proj": round(float(proj), 2),
                "proj_replacement": round(float(repl), 2),
                "provenance": provenance,
            })
    note = {"week": int(week), "universe": len(calls),
            "projected": len(proj_map), "dropped_positions": dropped_pos,
            "depth": depth, "proj_replacement": dict(
                (p, round(v, 2)) for p, v in line.items()
                if p in GRADED_POSITIONS)}
    return calls, note


# --- backfill ---------------------------------------------------------------

def backfill_feed(source_id: str, league="espn-1",
                  season: int = SEASON_BACKFILL,
                  weeks: Optional[Sequence[int]] = None,
                  scoring: Optional[str] = None,
                  registry_path: Optional[str] = None,
                  projections_fn: Optional[Callable] = None,
                  actuals: Optional[Dict[int, Dict[str, Dict]]] = None,
                  write: bool = True, path: Optional[str] = None,
                  force: bool = False) -> Dict:
    """Reconstruct + grade one source's past season. Creators are REFUSED.

    Returns {source, name, backfilled, reason, provenance, rows, weeks,
    graded, unscorable, notes}. `backfilled` False with a reason is a
    first-class, honest outcome - a creator source and a feed with no
    archive both land there, with DIFFERENT reasons, and neither produces a
    single fabricated row.

    Grading is league-relative (replacement levels are), so `league` (a
    LeagueConfig or an id) is part of the signature rather than an
    assumption. `projections_fn(source_id, season, week)` and `actuals`
    exist so tests can drive the whole path offline; unset, they are the
    real archives.
    """
    league = load_league(league)
    registry = sources_mod.load_sources(registry_path)
    source = next((s for s in registry if s.get("id") == source_id), None)
    if source is None:
        return {"source": source_id, "name": source_id, "backfilled": False,
                "reason": "not in the source registry (data/sources.yaml)",
                "provenance": PROV_BACKFILL, "rows": [], "weeks": [],
                "graded": 0, "unscorable": 0, "notes": []}

    name = source.get("name") or source_id
    can, reason = backfill_capability(source)
    if not can:
        return {"source": source_id, "name": name, "backfilled": False,
                "reason": reason, "provenance": PROV_BACKFILL, "rows": [],
                "weeks": [], "graded": 0, "unscorable": 0, "notes": []}

    scoring = scoring or league.scoring_label()
    weeks = list(weeks) if weeks else list(range(1, FINAL_WEEK + 1))
    getter = projections_fn or (
        lambda sid, ssn, wk: feed_projections(sid, ssn, wk, scoring=scoring,
                                              force=force))
    if actuals is None:
        actuals = season_actuals(season, force=force)

    rows: List[Dict] = []
    notes: List[str] = []
    done_weeks: List[int] = []
    for week in weeks:
        week_actual = actuals.get(int(week))
        if not week_actual:
            notes.append("week %d: no actuals filed - skipped, not graded"
                         % week)
            continue
        try:
            proj_map = getter(source_id, season, int(week))
        except (RuntimeError, ValueError) as exc:
            notes.append("week %d: archive unavailable (%s) - skipped, not "
                         "guessed" % (week, exc))
            continue
        if not proj_map:
            notes.append("week %d: archive returned no projections - skipped"
                         % week)
            continue
        calls, note = implied_calls(source_id, league, proj_map, week,
                                    season=season)
        line = replacement_line(league, actual_rows(week_actual))
        pts = dict((k, v["actual"]) for k, v in week_actual.items())
        for call in calls:
            call["replacement"] = line.get(call["pos"])
            call["league"] = league.id
        graded = grade_calls(calls, pts)
        rows.extend(graded)
        done_weeks.append(int(week))
        note["graded"] = sum(1 for g in graded if g.get("hit") is not None)
        note["unscorable"] = sum(1 for g in graded if g.get("hit") is None)
        notes.append("week %d: %d calls, %d graded, %d unscorable "
                     "(no actual filed)"
                     % (week, note["universe"], note["graded"],
                        note["unscorable"]))

    if write and rows:
        append_history(rows, path=path)

    return {"source": source_id, "name": name, "backfilled": True,
            "reason": reason, "provenance": PROV_BACKFILL, "rows": rows,
            "weeks": done_weeks,
            "graded": sum(1 for r in rows if r.get("hit") is not None),
            "unscorable": sum(1 for r in rows if r.get("hit") is None),
            "notes": notes}


def backfill_all(league="espn-1", season: int = SEASON_BACKFILL,
                 weeks: Optional[Sequence[int]] = None,
                 registry_path: Optional[str] = None,
                 path: Optional[str] = None,
                 force: bool = False, quiet: bool = False) -> List[Dict]:
    """backfill_feed over every ENABLED source; refusals come back too."""
    league = load_league(league)
    registry = sources_mod.load_sources(registry_path)
    out = []
    for source in registry:
        if not source.get("enabled"):
            continue
        res = backfill_feed(source.get("id"), league=league, season=season,
                            weeks=weeks, registry_path=registry_path,
                            path=path, force=force)
        if not quiet:
            if res["backfilled"]:
                print("  %-16s backfilled %d row(s) over %d week(s)"
                      % (res["source"], len(res["rows"]), len(res["weeks"])))
            else:
                print("  %-16s NOT backfilled: %s"
                      % (res["source"], res["reason"]))
        out.append(res)
    return out


# --- history i/o ------------------------------------------------------------

def read_history(path: Optional[str] = None) -> List[Dict]:
    """Graded backfill rows; a corrupt line is skipped, not fatal."""
    path = path or HISTORY_PATH
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


def append_history(rows: Sequence[Dict], path: Optional[str] = None) -> int:
    """Append graded rows, replacing any earlier pass over the same
    (league, source, season, week) - a re-run corrects itself instead of
    stacking duplicate copies of the same reconstruction. Atomic rewrite.

    This is deliberately NOT the ledger's append-only humility rule: the
    ledger records what a voice said before kickoff and must never be
    rewritten, while this file is a reconstruction that a better archive
    read should be free to replace.
    """
    path = path or HISTORY_PATH
    rows = [dict(r) for r in rows]
    touched = set((r.get("league"), r.get("source"), r.get("season"),
                   r.get("week")) for r in rows)
    kept = [r for r in read_history(path)
            if (r.get("league"), r.get("source"), r.get("season"),
                r.get("week")) not in touched]
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for rec in kept + rows:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    os.replace(tmp, path)
    return len(rows)


def live_rows(league: LeagueConfig,
              ledger_path: Optional[str] = None) -> List[Dict]:
    """This league's SCORED ledger rows, normalized into graded-row shape.

    consensus rows carry hit/actual/replacement but no margin or provenance;
    the gap is filled here (never re-graded - the ledger's hit stands) so
    live and backfilled weeks can be summarized by the same code.
    """
    out = []
    for e in consensus.read_ledger(ledger_path):
        if e.get("league") not in (league.id, None):
            continue
        if e.get("hit") is None:
            continue
        direction = _norm_call(e.get("verdict"))
        actual, repl = e.get("actual"), e.get("replacement")
        margin = edge = band = None
        if actual is not None and repl is not None:
            margin = round(float(actual) - float(repl), 2)
            edge = round(margin if direction == "start" else -margin, 2)
            band = band_of(edge)
        out.append({"source": e.get("source"), "league": league.id,
                    "season": weekly.SEASON, "week": e.get("week"),
                    "player": e.get("player"),
                    "player_key": e.get("player_key"), "pos": e.get("pos"),
                    "call": direction or e.get("verdict"),
                    "actual": actual, "replacement": repl, "margin": margin,
                    "edge": edge, "band": band, "hit": bool(e["hit"]),
                    "provenance": PROV_LIVE})
    return out


# --- streaks ----------------------------------------------------------------

def _rate(hits: int, n: int) -> Optional[float]:
    return round(hits / float(n), 4) if n else None


def weekly_rates(rows: Sequence[Dict],
                 min_week_calls: int = MIN_WEEK_CALLS) -> List[Dict]:
    """Per-week [{week, n, hits, rate, avg_edge, thin}], ascending.

    Only GRADED rows count. `thin` marks a week too small to be evidence -
    it stays in the series (a chart should show it) but cannot move a
    streak.
    """
    per: Dict[int, Dict] = {}
    for r in rows:
        if r.get("hit") is None:
            continue
        wk = r.get("week")
        if not isinstance(wk, int):
            continue
        d = per.setdefault(wk, {"week": wk, "n": 0, "hits": 0, "edge": 0.0,
                                "edge_n": 0})
        d["n"] += 1
        d["hits"] += 1 if r["hit"] else 0
        if r.get("edge") is not None:
            d["edge"] += float(r["edge"])
            d["edge_n"] += 1
    out = []
    for wk in sorted(per):
        d = per[wk]
        edge_n = d.pop("edge_n")
        d["avg_edge"] = round(d.pop("edge") / edge_n, 2) if edge_n else None
        d["rate"] = _rate(d["hits"], d["n"])
        d["thin"] = d["n"] < min_week_calls
        out.append(d)
    return out


def current_streak(weeks: Sequence[Dict],
                   baseline: float) -> Tuple[int, int]:
    """(length, direction) of the run ending at the latest non-thin week.

    Direction +1 above the source's own baseline, -1 below, 0 for no run. A
    week exactly ON the baseline is not a run week and ends the count: a
    streak is a claim about deviation, and zero deviation is not one.
    """
    solid = [w for w in weeks if not w["thin"] and w["rate"] is not None]
    length, direction = 0, 0
    for w in reversed(solid):
        d = 1 if w["rate"] > baseline else (-1 if w["rate"] < baseline else 0)
        if d == 0 or (direction and d != direction):
            break
        direction = d
        length += 1
    return length, direction


def rolling_window(weeks: Sequence[Dict],
                   n: int = ROLLING_N) -> Tuple[Optional[float], int, int]:
    """(pooled rate, calls, weeks) over the last n non-thin weeks.

    POOLED, not the mean of weekly rates: a 6-call week and a 60-call week
    are not equal evidence, and averaging rates would pretend they were.
    """
    solid = [w for w in weeks if not w["thin"]][-n:]
    calls = sum(w["n"] for w in solid)
    hits = sum(w["hits"] for w in solid)
    return _rate(hits, calls), calls, len(solid)


def classify(sample_n: int, weeks_n: int, baseline: Optional[float],
             rolling: Optional[float], rolling_calls: int,
             streak: int, direction: int) -> Tuple[str, str]:
    """(state, reason). The rule lives in the module docstring; this is it
    in code, and the reason string is written to be shown to the user."""
    if not sample_n:
        return "NO-DATA", "no graded calls on this basis"
    if sample_n < MIN_GRADED_CALLS or weeks_n < MIN_GRADED_WEEKS:
        return "LOW-CONFIDENCE", (
            "%d graded call%s across %d week%s carrying at least %d calls - "
            "under the %d-call / %d-week floor, so no hot or cold claim is "
            "made"
            % (sample_n, "" if sample_n == 1 else "s", weeks_n,
               "" if weeks_n == 1 else "s", MIN_WEEK_CALLS,
               MIN_GRADED_CALLS, MIN_GRADED_WEEKS))
    if baseline is None:
        return "STEADY", "graded, but no baseline computable"
    if rolling is None or rolling_calls < MIN_ROLLING_CALLS:
        return "STEADY", (
            "last %d week(s) carry only %d call(s) - under the %d needed to "
            "read recent form" % (ROLLING_N, rolling_calls,
                                  MIN_ROLLING_CALLS))
    if streak >= STREAK_MIN and direction > 0 and rolling >= baseline + HOT_BAND:
        return "HOT", (
            "%d straight weeks above its own %.0f%% baseline; last %d weeks "
            "%.0f%% over %d calls"
            % (streak, 100 * baseline, ROLLING_N, 100 * rolling,
               rolling_calls))
    if streak >= STREAK_MIN and direction < 0 and rolling <= baseline - HOT_BAND:
        return "COLD", (
            "%d straight weeks below its own %.0f%% baseline; last %d weeks "
            "%.0f%% over %d calls"
            % (streak, 100 * baseline, ROLLING_N, 100 * rolling,
               rolling_calls))
    return "STEADY", (
        "%.0f%% baseline, last %d weeks %.0f%%, streak %d - inside the "
        "%d-point band" % (100 * baseline, ROLLING_N, 100 * rolling, streak,
                           int(round(100 * HOT_BAND))))


def per_position(rows: Sequence[Dict]) -> Dict[str, Dict]:
    """{POS: {n, hits, rate, avg_edge}} - does this source read RBs better
    than WRs? Only graded rows count; a position it never called is absent
    rather than 0%."""
    per: Dict[str, Dict] = {}
    for r in rows:
        if r.get("hit") is None:
            continue
        pos = r.get("pos")
        if not pos:
            continue
        d = per.setdefault(pos, {"n": 0, "hits": 0, "edge": 0.0, "edge_n": 0})
        d["n"] += 1
        d["hits"] += 1 if r["hit"] else 0
        if r.get("edge") is not None:
            d["edge"] += float(r["edge"])
            d["edge_n"] += 1
    out = {}
    for pos, d in per.items():
        edge_n = d.pop("edge_n")
        out[pos] = {"n": d["n"], "hits": d["hits"],
                    "rate": _rate(d["hits"], d["n"]),
                    "avg_edge": round(d.pop("edge") / edge_n, 2)
                                if edge_n else None}
    return out


def _direction_split(rows: Sequence[Dict], direction: str) -> Dict:
    sub = [r for r in rows
           if r.get("hit") is not None and r.get("call") == direction]
    hits = sum(1 for r in sub if r["hit"])
    return {"n": len(sub), "hits": hits, "rate": _rate(hits, len(sub))}


def summarize(rows: Sequence[Dict]) -> Dict:
    """Everything a scoreboard needs about ONE source on ONE basis.

    Never mixes bases: callers hand it live rows or backfill rows, never a
    pile of both, because a reconstructed 2025 rate and three live weeks are
    different kinds of evidence and pooling them would launder one into the
    other.
    """
    graded = [r for r in rows if r.get("hit") is not None]
    unscorable = [r for r in rows if r.get("hit") is None]
    weeks = weekly_rates(rows)
    solid = [w for w in weeks if not w["thin"]]
    sample_n = len(graded)
    hits = sum(1 for r in graded if r["hit"])
    baseline = _rate(hits, sample_n)
    rolling, rolling_calls, rolling_weeks = rolling_window(weeks)
    streak, direction = current_streak(weeks, baseline) if baseline is not None \
        else (0, 0)
    state, reason = classify(sample_n, len(solid), baseline, rolling,
                             rolling_calls, streak, direction)
    edges = [float(r["edge"]) for r in graded if r.get("edge") is not None]
    return {
        "hit_rate": baseline,
        "sample_n": sample_n,
        "hits": hits,
        "weeks_n": len(weeks),
        "solid_weeks_n": len(solid),
        "unscorable_n": len(unscorable),
        "state": state,
        "state_reason": reason,
        "streak": streak,
        "streak_dir": direction,
        "rolling_rate": rolling,
        "rolling_calls": rolling_calls,
        "rolling_weeks": rolling_weeks,
        "baseline": baseline,
        "sparkline_values": [round(100.0 * w["rate"], 1) for w in solid],
        "sparkline_weeks": [w["week"] for w in solid],
        "series": weeks,
        "per_position": per_position(rows),
        "start_split": _direction_split(rows, "start"),
        "sit_split": _direction_split(rows, "sit"),
        "avg_edge": round(sum(edges) / len(edges), 2) if edges else None,
        "loud_hits": sum(1 for r in graded
                         if r["hit"] and r.get("band") == "loud"),
        "loud_misses": sum(1 for r in graded
                           if not r["hit"] and r.get("band") == "loud"),
    }


# --- the API the pages call -------------------------------------------------

EMPTY_BASIS = {"hit_rate": None, "sample_n": 0, "hits": 0, "weeks_n": 0,
               "solid_weeks_n": 0, "unscorable_n": 0, "state": "NO-DATA",
               "streak": 0, "streak_dir": 0, "rolling_rate": None,
               "rolling_calls": 0, "rolling_weeks": 0, "baseline": None,
               "sparkline_values": [], "sparkline_weeks": [], "series": [],
               "per_position": {}, "avg_edge": None}


def source_scoreboard(league, registry_path: Optional[str] = None,
                      path: Optional[str] = None,
                      ledger_path: Optional[str] = None,
                      season: int = SEASON_BACKFILL) -> Dict:
    """Per-source performance for a league, for the board and digest pages.

    One row per ENABLED source, heaviest weight first, INCLUDING sources
    with nothing to show - a creator at NO-DATA is the most important row on
    the page in September, and dropping it would quietly imply the feeds are
    all there is.

    Row shape (the keys the pages consume):
      name, source, weight, state, hit_rate, sample_n, streak,
      sparkline_values, per_position, provenance
    plus state_reason, backfill_state, backfill_reason, rolling_rate,
    start_split / sit_split, unscorable_n, avg_edge, and `bases` holding
    each basis broken out.

    TWO RULES ABOUT WHAT THOSE MEAN, because they are the whole point:
      * `state` is a claim about CURRENT form, so it is computed from LIVE
        rows only. A source with a rich 2025 backfill and no live calls is
        NO-DATA today, and its reason says so. The 2025 form read is carried
        as `backfill_state`, scoped to "as of the end of 2025".
      * every other flat number mirrors the basis `provenance` names - live
        when live rows exist, else the backfill. The two are never averaged
        into one figure.
    """
    league = load_league(league)
    registry = sources_mod.load_sources(registry_path)
    hist = [r for r in read_history(path)
            if r.get("league") in (league.id, None)
            and int(r.get("season") or 0) == int(season)]
    live = live_rows(league, ledger_path=ledger_path)

    weeks_done = weeks_completed()

    hist_by: Dict[str, List[Dict]] = {}
    live_by: Dict[str, List[Dict]] = {}
    for r in hist:
        hist_by.setdefault(r.get("source"), []).append(r)
    for r in live:
        live_by.setdefault(r.get("source"), []).append(r)

    rows = []
    for source in sorted((s for s in registry if s.get("enabled")),
                         key=lambda s: (-consensus._w(s), str(s.get("id")))):
        sid = source.get("id")
        can, reason = backfill_capability(source)
        bases = {}
        if live_by.get(sid):
            bases[PROV_LIVE] = summarize(live_by[sid])
        if hist_by.get(sid):
            bases[PROV_BACKFILL] = summarize(hist_by[sid])

        headline_key = PROV_LIVE if PROV_LIVE in bases else (
            PROV_BACKFILL if PROV_BACKFILL in bases else None)
        head = bases.get(headline_key, EMPTY_BASIS)
        back = bases.get(PROV_BACKFILL)

        if PROV_LIVE in bases:
            state = bases[PROV_LIVE]["state"]
            state_reason = bases[PROV_LIVE]["state_reason"]
        elif back:
            state = "NO-DATA"
            state_reason = (
                "no live call graded yet - week 1 of %d has not been played. "
                "The %s record below is a reconstruction of %d and says "
                "nothing about this week's form."
                % (weekly.SEASON, PROV_BACKFILL, season))
        else:
            state = "NO-DATA"
            state_reason = reason if not can else (
                "no graded calls yet on any basis")

        rows.append({
            "source": sid,
            "name": source.get("name") or sid,
            "type": (source.get("type") or "").strip().lower(),
            "weight": consensus._w(source),
            "is_creator": is_creator(source),
            "backfillable": can,
            "backfill_reason": reason,
            "provenance": headline_key or "none",
            "state": state,
            "state_reason": state_reason,
            "backfill_state": back["state"] if back else None,
            "backfill_state_reason": back["state_reason"] if back else None,
            "hit_rate": head["hit_rate"],
            "sample_n": head["sample_n"],
            "weeks_n": head["weeks_n"],
            "unscorable_n": head["unscorable_n"],
            "streak": head["streak"],
            "streak_dir": head["streak_dir"],
            "rolling_rate": head["rolling_rate"],
            "sparkline_values": head["sparkline_values"],
            "sparkline_weeks": head["sparkline_weeks"],
            "per_position": head["per_position"],
            "start_split": head.get("start_split") or {},
            "sit_split": head.get("sit_split") or {},
            "avg_edge": head["avg_edge"],
            "bases": bases,
            # Decay-weighted headline: the archive fades out by week 3.
            "blend": blend_bases(bases, weeks_done),
        })

    notes = []
    if not live:
        notes.append("data/source_ledger.jsonl holds no graded call for %s - "
                     "week 1 of %d has not been played, so every CURRENT-form "
                     "state is NO-DATA by fact, not by failure."
                     % (league.id, weekly.SEASON))
    if not hist:
        notes.append("no %s rows yet - run with --backfill to reconstruct "
                     "the algorithmic feeds." % PROV_BACKFILL)
    creators = [r["name"] for r in rows if r["is_creator"]]
    if creators:
        notes.append("never backfilled (nothing was ever recorded): %s."
                     % ", ".join(creators))
    refused = [r["name"] for r in rows
               if not r["is_creator"] and not r["backfillable"]]
    if refused:
        notes.append("feeds with no published archive: %s." % ", ".join(refused))

    return {"league": league.id, "league_name": league.name,
            "season": season, "generated": datetime.date.today().isoformat(),
            "min_graded_calls": MIN_GRADED_CALLS,
            "min_graded_weeks": MIN_GRADED_WEEKS,
            "rows": rows, "notes": notes}


def history_series(source: str, league="espn-1",
                   basis: Optional[str] = None,
                   path: Optional[str] = None,
                   ledger_path: Optional[str] = None,
                   season: int = SEASON_BACKFILL) -> Dict:
    """One source's week-by-week series, for charting.

    {source, league, basis, baseline, weeks:[{week,n,hits,rate,avg_edge,
    thin}], values, labels, per_position, state, state_reason}. `basis`
    picks "live" or "backfill-<season>"; unset takes live when live rows
    exist. Thin weeks are RETURNED with thin=True rather than dropped - a
    chart that hides its own small samples is the thing this module exists
    to avoid - and `values` carries only the non-thin points a sparkline
    should draw.
    """
    league = load_league(league)
    live = [r for r in live_rows(league, ledger_path=ledger_path)
            if r.get("source") == source]
    hist = [r for r in read_history(path)
            if r.get("source") == source
            and r.get("league") in (league.id, None)
            and int(r.get("season") or 0) == int(season)]
    if basis is None:
        basis = PROV_LIVE if live else PROV_BACKFILL
    rows = live if basis == PROV_LIVE else hist
    summary = summarize(rows) if rows else dict(EMPTY_BASIS,
                                                state_reason="no rows on "
                                                "basis %r" % basis)
    return {"source": source, "league": league.id, "basis": basis,
            "season": season if basis != PROV_LIVE else weekly.SEASON,
            "baseline": summary["hit_rate"],
            "weeks": summary["series"],
            "values": summary["sparkline_values"],
            "labels": summary["sparkline_weeks"],
            "per_position": summary["per_position"],
            "state": summary["state"],
            "state_reason": summary.get("state_reason", "")}


# --- CLI --------------------------------------------------------------------

_STATE_MARK = {"HOT": "HOT ", "COLD": "COLD", "STEADY": "----",
               "LOW-CONFIDENCE": "LOW?", "NO-DATA": "  - "}


def _pct(v: Optional[float]) -> str:
    return "  -  " if v is None else "%4.1f%%" % (100.0 * v)


def _spark(values: Sequence[float]) -> str:
    """A blocks-free sparkline: hit-rate deciles as digits, oldest first."""
    if not values:
        return ""
    return "".join(str(min(9, max(0, int(round(v / 10.0))))) for v in values)


def format_scoreboard(sb: Dict) -> str:
    """The terminal scoreboard. Every number says which basis it is from."""
    out = []
    out.append("SOURCE PERFORMANCE - %s (%s)  generated %s"
               % (sb["league_name"], sb["league"], sb["generated"]))
    out.append("  grading: start hits when actual >= positional replacement "
               "(recommend.replacement_levels);")
    out.append("           sit hits when it does not. Floor for any hot/cold "
               "claim: %d graded calls over %d weeks."
               % (sb["min_graded_calls"], sb["min_graded_weeks"]))
    out.append("")
    out.append("  %-28s %3s %-5s %6s %7s %4s %-18s %s"
               % ("SOURCE", "WT", "STATE", "HIT", "CALLS", "WKS",
                  "SPARK (wk1->)", "BASIS"))
    out.append("  " + "-" * 92)
    for r in sb["rows"]:
        out.append("  %-28.28s %3d %-5s %6s %7s %4s %-18.18s %s"
                   % (r["name"], int(r["weight"]),
                      _STATE_MARK.get(r["state"], r["state"]),
                      _pct(r["hit_rate"]), r["sample_n"] or "-",
                      r["weeks_n"] or "-", _spark(r["sparkline_values"]),
                      r["provenance"]))
        out.append("      %s" % r["state_reason"])
        if r["backfill_state"]:
            out.append("      2025 form (season over): %s - %s"
                       % (r["backfill_state"], r["backfill_state_reason"]))
        if r["per_position"]:
            bits = ", ".join(
                "%s %s (%d)" % (pos, _pct(d["rate"]).strip(), d["n"])
                for pos, d in sorted(r["per_position"].items(),
                                     key=lambda kv: -(kv[1]["rate"] or 0)))
            out.append("      by position: %s" % bits)
        if r["sample_n"]:
            out.append("      start %s of %d | sit %s of %d | avg edge %s pts "
                       "| %d unscorable (no actual filed)"
                       % (r["start_split"].get("hits", 0),
                          r["start_split"].get("n", 0),
                          r["sit_split"].get("hits", 0),
                          r["sit_split"].get("n", 0),
                          "-" if r["avg_edge"] is None else "%+.2f"
                          % r["avg_edge"], r["unscorable_n"]))
        if (not r["backfillable"] and not r["sample_n"]
                and r["backfill_reason"] != r["state_reason"]):
            out.append("      no backfill: %s" % r["backfill_reason"])
    out.append("")
    for n in sb["notes"]:
        out.append("  NOTE: %s" % n)
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.performance",
        description="How each source's calls have actually graded, and who "
                    "is on a run. Creator sources are never backfilled.")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--backfill", action="store_true",
                    help="reconstruct + grade the algorithmic feeds against "
                         "the %d season before printing" % SEASON_BACKFILL)
    ap.add_argument("--season", type=int, default=SEASON_BACKFILL)
    ap.add_argument("--source", help="backfill only this source id")
    ap.add_argument("--weeks", help="weeks to backfill, e.g. 1-18 or 1,2,5")
    ap.add_argument("--force", action="store_true",
                    help="refetch archives, ignoring caches")
    ap.add_argument("--json", action="store_true",
                    help="emit the scoreboard as JSON")
    args = ap.parse_args(argv)

    league = load_league(args.league)
    weeks = _parse_weeks(args.weeks)

    if args.backfill:
        print("BACKFILL - %s, season %d%s"
              % (league.id, args.season,
                 "" if not weeks else " weeks %s" % args.weeks))
        if args.source:
            res = backfill_feed(args.source, league=league, season=args.season,
                                weeks=weeks, force=args.force)
            if res["backfilled"]:
                print("  %-16s backfilled %d row(s) over %d week(s)"
                      % (res["source"], len(res["rows"]), len(res["weeks"])))
            else:
                print("  %-16s NOT backfilled: %s"
                      % (res["source"], res["reason"]))
            for n in res["notes"]:
                print("    %s" % n)
        else:
            backfill_all(league=league, season=args.season, weeks=weeks,
                         force=args.force)
        print("")

    sb = source_scoreboard(league, season=args.season)
    if args.json:
        print(json.dumps(sb, indent=2, sort_keys=True, default=str))
    else:
        print(format_scoreboard(sb))
    return 0


def _parse_weeks(spec: Optional[str]) -> Optional[List[int]]:
    if not spec:
        return None
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return sorted(set(w for w in out if 1 <= w <= FINAL_WEEK)) or None


if __name__ == "__main__":
    sys.exit(main())
