"""League-size normalization: read outside advice at THIS league's depth.

    python -m engine.leaguesize --league espn-1

Nearly all public fantasy advice is written for 10- or 12-team leagues. The
user's ESPN league ("The Original 8") has EIGHT teams, and that changes the
meaning of almost every waiver-wire and start/sit take:

  * replacement level is far higher. 8 teams x 2 flex still only starts 26
    WR league-wide, so the "WR3 upside" the podcast is excited about is a
    player who, here, is somebody's fourth bench receiver;
  * "deep-league add" and "sleeper" advice is often about players who are
    ALREADY ROSTERED at 12 teams and, at 8, are simply worse than what is
    already sitting on a bench - the wire here is deeper than the wire
    there, so the bar to be worth a claim is higher, not lower;
  * conversely a "reach" in a 12-team context can be exactly right at 8,
    because the shallow pool means the next-best body is much better.

This module never DROPS a voice. A source that talks about a player who is
irrelevant at this league size is DOWNGRADED - its confidence drops one
tier and its vote carries a reduced weight - and it is TAGGED so the strip
shows the user why that source was discounted. Silently dropping a call
would hide a disagreement; silently keeping it at full weight would let
12-team advice steer an 8-team lineup. Downgrade-with-a-reason is the only
honest option, and it is reversible by eye.

WHAT THIS MODULE COMPUTES

  replacement_context(league)   per position: the positional rank of the
                                LAST league-wide starter (derived from
                                engine.recommend.replacement_levels - the
                                same baseline the draft engine, keeper
                                math, and trade values already use, never
                                a second opinion), plus a rostered-depth
                                estimate (teams x roster_spots split into
                                starters and bench).

  relevance(player, league)     CORE / STARTABLE / FRINGE / IRRELEVANT for
                                THAT league size, from the player's
                                positional rank against that context.
                                UNKNOWN when the player carries no
                                projection in this league's own pool -
                                absence of data is not evidence of
                                irrelevance (the codebase's honest-
                                degradation rule), so UNKNOWN never
                                downgrades anything.

  adjust_call(call, league)     an IRRELEVANT-player call comes back with
                                confidence knocked down one tier, a
                                weight_factor < 1, and the tag fields the
                                strip renders. Every other call comes back
                                untouched.

EVERY THRESHOLD IS A JUDGMENT CALL. They are named constants below, each
with the reasoning that picked it, so a disagreement is a one-line edit
rather than an archaeology project.
"""

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

try:
    from engine.models import POSITIONS, LeagueConfig, DraftState, load_players
    from engine.recommend import replacement_levels
except ImportError:  # run directly as `python engine/leaguesize.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.models import POSITIONS, LeagueConfig, DraftState, load_players
    from engine.recommend import replacement_levels

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- classes ---------------------------------------------------------------

CORE = "CORE"
STARTABLE = "STARTABLE"
FRINGE = "FRINGE"
IRRELEVANT = "IRRELEVANT"
UNKNOWN = "UNKNOWN"

CLASSES = (CORE, STARTABLE, FRINGE, IRRELEVANT)


# --- judgment calls ---------------------------------------------------------
#
# CORE_FRACTION - what share of the league-wide starter pool at a position
# is "you never think about benching him". Set at 0.50: the top HALF of the
# starters at a position. In espn-1 that is RB1-11 of 22 and WR1-13 of 26 -
# i.e. roughly every team's genuine RB1/WR1. Anything tighter (0.33) would
# call a solid RB2 "fringe"; anything looser (0.75) would make CORE mean
# nothing. CORE exists for one purpose: to guarantee that no amount of
# league-size math can ever discount a call about a real starter.
CORE_FRACTION = 0.50

# FRINGE_BENCH_ROUNDS - how many bench bodies PER TEAM at a position are
# plausible weekly starters, and therefore still worth hearing advice about.
# This is the line that actually does the work: past it, a start/sit or
# add call is about a player who will not enter this league's lineups.
#
# 1.0 for RB/WR: every team carries at least one RB/WR handcuff or flex
# dart that a bye or an injury promotes on any given Sunday, so one full
# round of bench depth per team stays live.
# 0.5 for QB/TE in a 1-QB league: about half of teams carry a backup at
# these positions at all, and the ones who do rarely start them.
# K/DEF: see STREAMED_POSITIONS - the concept does not apply.
#
# Scaling by `teams` is the whole point: the fringe band widens with the
# league, so the SAME player is a live streamer at 12 teams and noise at 8.
FRINGE_BENCH_ROUNDS = {"RB": 1.0, "WR": 1.0, "QB": 0.5, "TE": 0.5}

# BENCH_SHARE - how the league's bench slots distribute across positions,
# used only for the rostered-depth ESTIMATE (and therefore only for the
# wording of the explanation, never for the downgrade decision itself).
# Managers hoard runners and receivers, carry a backup QB/TE occasionally,
# and essentially never roster a second K or DEF.
#
# The shares are renormalized over the positions a league actually starts
# (a no-kicker league's 0.02 goes to the others, not into a void) and then
# apportioned by largest remainder, so the bench slots handed out total
# EXACTLY teams x bench_spots. That makes the reconciliation exact rather
# than approximate: sum(rostered_depth) == teams x (starting + bench)
# slots, which is teams x roster_spots for a league with no IR slot.
BENCH_SHARE = {"RB": 0.38, "WR": 0.38, "QB": 0.10, "TE": 0.10,
               "K": 0.02, "DEF": 0.02}

# STREAMED_POSITIONS - K and DEF are NEVER downgraded for league size, at
# any depth. There are 32 of each in the NFL and a league starts at most a
# dozen, so the free-agent pool is enormous in every format; shallower
# leagues make DEF/K advice MORE actionable, not less. Capping them at
# FRINGE prevents the obviously wrong "DEF12 is irrelevant in an 8-team
# league" (in an 8-team league DEF12 is on waivers and startable today).
STREAMED_POSITIONS = frozenset(("K", "DEF"))

# DOWNGRADE_WEIGHT - the multiplier applied to an IRRELEVANT-player call's
# vote weight. 0.40 is deliberately a discount and not a mute: the source
# may know something our positional ranks do not (a starter went down an
# hour ago), so the voice must still be able to move a genuinely close row.
# At 0.4 a lone creator can no longer outvote the engine on a player this
# league would never start, which is exactly the failure being fixed.
DOWNGRADE_WEIGHT = 0.40

# One confidence tier, not two, and never below 'low'. The call is still a
# real observation about a real player - the claim that survives is "this
# person said it", which is worth less here, not worthless.
CONF_DOWNGRADE = {"high": "med", "med": "low", "low": "low"}

# The tag itself. Kept as one constant because the strip renders it, the
# tests assert on it, and the digest notes repeat it - it must be one
# string in one place.
SIZED_TAG = "advice sized for deeper leagues"

# Enough downgrade lines to show the pattern without drowning the digest's
# note list; the summary line above them always carries the true count.
MAX_SIZE_NOTES = 6


# --- replacement context ----------------------------------------------------

class ReplacementContext(object):
    """Per-position depth of ONE league. Pure data; build via
    replacement_context()."""

    __slots__ = ("league_id", "teams", "bench_spots", "starter_rank",
                 "repl_points", "rostered_depth", "fringe_rank", "pos_rank",
                 "pool_size")

    def __init__(self, league_id, teams, bench_spots, starter_rank,
                 repl_points, rostered_depth, fringe_rank, pos_rank,
                 pool_size):
        self.league_id = league_id
        self.teams = teams
        self.bench_spots = bench_spots        # bench slots PER TEAM
        self.starter_rank = starter_rank      # pos -> rank of last starter
        self.repl_points = repl_points        # pos -> that starter's proj
        self.rostered_depth = rostered_depth  # pos -> est. rostered leaguewide
        self.fringe_rank = fringe_rank        # pos -> last rank worth hearing
        self.pos_rank = pos_rank              # player_key -> positional rank
        self.pool_size = pool_size            # pos -> projected players ranked

    def rank_of(self, player_or_key) -> Optional[int]:
        """Positional rank of a Player or a 'normname|POS' key; None when
        this league's pool carries no projection for him."""
        key = getattr(player_or_key, "key", player_or_key)
        return self.pos_rank.get(key)

    def describe(self, pos: str) -> str:
        """One line of depth for a position, for notes and the CLI."""
        pos = (pos or "").upper()
        if pos not in self.starter_rank:
            return "%s: no starting demand in this league" % (pos or "?")
        head = ("%s: %d start league-wide, ~%d rostered"
                % (pos, self.starter_rank[pos], self.rostered_depth[pos]))
        if pos in STREAMED_POSITIONS:
            # Saying "advice past DEF8 is sized for deeper leagues" would be
            # a claim this module deliberately does not make.
            return head + ", streamed from a 32-deep pool - never downgraded"
        return (head + ", %s past %s%d"
                % (SIZED_TAG, pos, self.fringe_rank[pos]))

    def summary(self) -> Dict:
        """Plain dict for the digest / JSON consumers."""
        return {"league": self.league_id, "teams": self.teams,
                "bench_spots": self.bench_spots,
                "starter_rank": dict(self.starter_rank),
                "rostered_depth": dict(self.rostered_depth),
                "fringe_rank": dict(self.fringe_rank),
                # How deep our own board actually goes - a rank near this is
                # a rank the pool can barely support, worth seeing next to
                # the league's demand.
                "ranked_pool": dict(self.pool_size),
                "replacement_points": dict(
                    (k, round(v, 1)) for k, v in self.repl_points.items())}


def _positional_order(players) -> Tuple[Dict[str, int], Dict[str, int]]:
    """(player_key -> positional rank, pos -> ranked count) by projection.

    Ranked over the SAME set replacement_levels ranks - players carrying a
    projection - so a rank and the replacement baseline it is compared
    against can never come from two differently-sized lists. A player with
    no projection gets no rank at all and classifies UNKNOWN.
    """
    by_pos: Dict[str, List] = {}
    for p in players:
        if p.proj_points:
            by_pos.setdefault(p.pos, []).append(p)
    ranks, sizes = {}, {}
    for pos, group in by_pos.items():
        # Ties broken by the pool's own overall rank so the order is stable.
        group.sort(key=lambda x: (-float(x.proj_points), x.rank))
        sizes[pos] = len(group)
        for i, p in enumerate(group, start=1):
            ranks[p.key] = i
    return ranks, sizes


def _apportion(total: int, shares: Dict[str, float]) -> Dict[str, int]:
    """Split `total` whole slots by `shares`, summing to exactly `total`.

    Largest-remainder (Hamilton) apportionment over shares renormalized to
    the keys given. Naive per-position rounding loses or invents slots -
    72 bench slots split 0.38/0.38/0.10/0.10/0.02/0.02 rounds to 70 - which
    would quietly break the "teams x roster_spots" reconciliation that
    makes rostered_depth checkable at all.
    """
    keys = [k for k in shares if shares[k] > 0]
    denom = sum(shares[k] for k in keys)
    if total <= 0 or not keys or denom <= 0:
        return dict((k, 0) for k in shares)
    exact = dict((k, total * shares[k] / denom) for k in keys)
    out = dict((k, int(exact[k])) for k in keys)
    left = total - sum(out.values())
    # Ties broken by descending share then name, so the result is stable.
    for k in sorted(keys, key=lambda x: (-(exact[x] - int(exact[x])),
                                         -shares[x], x))[:left]:
        out[k] += 1
    for k in shares:
        out.setdefault(k, 0)
    return out


def replacement_context(league: LeagueConfig, players=None,
                        state=None) -> ReplacementContext:
    """This league's positional depth: last-starter rank + rostered depth.

    The starter baseline is NOT recomputed here. engine.recommend.
    replacement_levels() already answers "what does the last league-wide
    starter at this position project for", accounting for this league's
    hard starters, its team count, and the flex slots each position
    actually wins in this pool. We call it and read the RANK off the same
    projection board: the number of players at a position projecting at or
    above that baseline IS the rank of the last starter. Two players tied
    exactly on the baseline both count, which widens the starter band by
    one - the honest direction, since a tie is not a demotion.

    When the pool carries no projections at all (replacement_levels returns
    {} by design) each position falls back to its structural demand, hard
    starters x teams. Flex slots cannot be allocated without projections, so
    they are left out rather than guessed - which makes the starter band
    NARROWER and would make the downgrade MORE aggressive, exactly the wrong
    direction to fail in. Nothing is downgraded in that state anyway, and by
    construction rather than by a special case: positional ranks come off
    the same projection board, so a projection-less pool yields no ranks,
    every player classifies UNKNOWN, and relevance() never returns
    IRRELEVANT. The fallback numbers stay useful for reporting; they simply
    cannot be used to discount anybody.
    """
    if players is None:
        csv_path = league.rankings_csv
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(HERE, csv_path)
        players = load_players(csv_path)
    if state is None:
        state = DraftState(league, players)

    repl = replacement_levels(state)
    pos_rank, pool_size = _positional_order(players)

    hard = league.hard_starter_counts()
    starter_rank, fringe_rank, rostered_depth = {}, {}, {}
    bench_per_team = league.bench_spots()
    bench_total = league.teams * bench_per_team

    for pos in POSITIONS:
        if pos in repl:
            floor = repl[pos]
            n = sum(1 for p in players
                    if p.pos == pos and p.proj_points
                    and float(p.proj_points) >= floor)
        else:
            n = int(hard.get(pos, 0)) * league.teams
        if n <= 0:
            continue
        starter_rank[pos] = n
        fringe_rank[pos] = n + int(round(league.teams
                                         * FRINGE_BENCH_ROUNDS.get(pos, 0.0)))

    # Bench depth is an estimate of the LEAGUE, not of our CSV, so it is not
    # capped by pool_size - it answers "would anyone here roster him", which
    # stays true past the end of our rankings file.
    bench_alloc = _apportion(bench_total,
                             dict((pos, BENCH_SHARE.get(pos, 0.0))
                                  for pos in starter_rank))
    for pos, n in starter_rank.items():
        rostered_depth[pos] = n + bench_alloc.get(pos, 0)

    return ReplacementContext(
        league_id=league.id, teams=league.teams, bench_spots=bench_per_team,
        starter_rank=starter_rank, repl_points=dict(repl),
        rostered_depth=rostered_depth, fringe_rank=fringe_rank,
        pos_rank=pos_rank, pool_size=pool_size)


def _as_context(league, ctx=None) -> ReplacementContext:
    """Accept a ReplacementContext in either argument slot.

    relevance(player, league) and relevance(player, ctx) both read
    naturally at a call site; building a context reloads and re-ranks the
    whole pool, so anything looping over calls should build one and pass
    it in.
    """
    if ctx is not None:
        return ctx
    if isinstance(league, ReplacementContext):
        return league
    return replacement_context(league)


# --- classification ---------------------------------------------------------

def relevance(player, league, ctx: Optional[ReplacementContext] = None) -> str:
    """CORE / STARTABLE / FRINGE / IRRELEVANT for THIS league's size.

    `player` is a Player, or a 'normname|POS' player_key. `league` is a
    LeagueConfig or an already-built ReplacementContext.

    The bands, all measured in POSITIONAL RANK against the context:
      CORE        <= CORE_FRACTION x last-starter rank - a genuine starter
                  somewhere in this league; never downgraded, ever.
      STARTABLE   <= last-starter rank - inside the league-wide starter
                  pool, so some manager legitimately starts him weekly.
      FRINGE      <= fringe rank (starters + FRINGE_BENCH_ROUNDS bench
                  bodies per team) - a bench/streaming body whose week
                  could still matter here.
      IRRELEVANT  past that - at THIS depth no lineup decision in the
                  league involves him, so advice about him was written
                  for a deeper league.
      UNKNOWN     no projection for him in this league's pool. Returned,
                  never guessed, and never downgraded.
    """
    ctx = _as_context(league, ctx)
    key = getattr(player, "key", player)
    pos = getattr(player, "pos", None)
    if pos is None and isinstance(key, str) and "|" in key:
        pos = key.rpartition("|")[2]
    pos = (pos or "").upper()

    rank = ctx.rank_of(key)
    starters = ctx.starter_rank.get(pos)
    if rank is None or not starters:
        # No rank, or a position this league does not start (a DEF call in a
        # league without a DEF slot): unclassifiable, so unjudged.
        return UNKNOWN

    if rank <= max(1, int(round(CORE_FRACTION * starters))):
        return CORE
    if rank <= starters:
        return STARTABLE
    if pos in STREAMED_POSITIONS:
        # Streamed positions bottom out at FRINGE by construction: the
        # waiver pool is 32 deep in every format, so depth never makes a
        # K/DEF call irrelevant.
        return FRINGE
    if rank <= ctx.fringe_rank.get(pos, starters):
        return FRINGE
    return IRRELEVANT


# --- call adjustment --------------------------------------------------------

def _article(n: int) -> str:
    """'an 8-team league', 'a 12-team league' - spoken, not spelled."""
    return "an" if n in (8, 11, 18) or 80 <= n <= 89 else "a"


def size_note(pos: str, rank: int, ctx: ReplacementContext) -> str:
    """The full sentence explaining a downgrade, for notes and the digest."""
    starters = ctx.starter_rank.get(pos, 0)
    depth = ctx.rostered_depth.get(pos, 0)
    where = ("already rostered here" if rank <= depth
             else "not rostered in a league this shallow")
    return ("%s%d in %s %d-team league: %d start league-wide, ~%d rostered "
            "(%s) - %s" % (pos, rank, _article(ctx.teams), ctx.teams,
                           starters, depth, where, SIZED_TAG))


def adjust_call(call: Dict, league, ctx: Optional[ReplacementContext] = None) -> Dict:
    """One creator call, normalized for league size. Never mutates the input.

    A call about an IRRELEVANT player comes back as a COPY carrying:
      confidence      knocked down exactly one tier (never below 'low')
      weight_factor   DOWNGRADE_WEIGHT - consensus multiplies the vote's
                      source weight by this, so the discount is real and
                      not merely cosmetic
      relevance       'IRRELEVANT'
      size_rank       'WR37' - the compact reason the strip prints
      sized_for       SIZED_TAG - the stable tag
      size_note       the full sentence (see size_note())

    Anything else - CORE, STARTABLE, FRINGE, UNKNOWN, a malformed call, a
    context with no starter demand at that position - comes back as the
    SAME object, untouched. Downgrading is the exception that has to earn
    itself; leaving a voice alone is the default.
    """
    if not isinstance(call, dict):
        return call
    ctx = _as_context(league, ctx)
    if not ctx.starter_rank:
        return call     # projection-less pool: no basis to judge, so don't
    key = call.get("player_key") or ""
    if not isinstance(key, str) or "|" not in key:
        return call
    if relevance(key, ctx) != IRRELEVANT:
        return call

    pos = key.rpartition("|")[2].upper()
    rank = ctx.rank_of(key)
    out = dict(call)
    out["relevance"] = IRRELEVANT
    out["confidence"] = CONF_DOWNGRADE.get(
        str(call.get("confidence") or "").strip().lower(), "low")
    # Compose rather than overwrite: a call downgraded twice (a caller that
    # re-adjusts an already-adjusted list) must not compound the discount,
    # so the factor is set, not multiplied.
    out["weight_factor"] = DOWNGRADE_WEIGHT
    out["size_rank"] = "%s%d" % (pos, rank)
    out["sized_for"] = SIZED_TAG
    out["size_note"] = size_note(pos, rank, ctx)
    return out


def adjust_calls(calls: List[Dict], league,
                 ctx: Optional[ReplacementContext] = None
                 ) -> Tuple[List[Dict], List[str]]:
    """adjust_call over a week's calls. Returns (calls, notes).

    The notes are the honest-degradation trail: the digest and the CLI
    print them so a discount is never invisible. One summary line plus one
    line per downgraded call, capped so a pathological week cannot bury
    the rest of the notes.
    """
    ctx = _as_context(league, ctx)
    out, downgraded = [], []
    for c in calls or []:
        adj = adjust_call(c, ctx)
        out.append(adj)
        if adj is not c:
            downgraded.append(adj)
    notes: List[str] = []
    if downgraded:
        notes.append("%d creator call(s) downgraded for league size "
                     "(%d teams): %s"
                     % (len(downgraded), ctx.teams, SIZED_TAG))
        for adj in downgraded[:MAX_SIZE_NOTES]:
            notes.append("  %s - %s: %s"
                         % (adj.get("source") or "?",
                            adj.get("player") or adj.get("player_key"),
                            adj.get("size_note")))
        if len(downgraded) > MAX_SIZE_NOTES:
            notes.append("  ... and %d more (see data/creator_calls/)"
                         % (len(downgraded) - MAX_SIZE_NOTES))
    return out, notes


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="League-size normalization: this league's real depth.")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--compare", default="",
                    help="second league id to show side by side")
    args = ap.parse_args(argv)

    def ctx_for(lid):
        lg = LeagueConfig.load(os.path.join(HERE, "leagues", "%s.yaml" % lid))
        return lg, replacement_context(lg)

    lg, ctx = ctx_for(args.league)
    other = ctx_for(args.compare)[1] if args.compare else None

    print("=" * 72)
    print("LEAGUE SIZE CONTEXT  %s (%s, %d teams, %d bench)"
          % (lg.name, lg.id, ctx.teams, ctx.bench_spots))
    print("=" * 72)
    head = "  %-5s %9s %9s %9s" % ("pos", "starters", "fringe", "rostered")
    if other:
        head += " |%9s %9s %9s" % ("starters", "fringe", "rostered")
    print(head)
    def cell(c, pos):
        # 'exempt' rather than a number for K/DEF: printing the fringe rank
        # there would read as a downgrade line that this module never draws.
        fringe = ("exempt" if pos in STREAMED_POSITIONS
                  else str(c.fringe_rank[pos]))
        return "%9d %9s %9d" % (c.starter_rank[pos], fringe,
                                c.rostered_depth[pos])

    for pos in POSITIONS:
        if pos not in ctx.starter_rank:
            continue
        line = "  %-5s %s" % (pos, cell(ctx, pos))
        if other and pos in other.starter_rank:
            line += " |%s" % cell(other, pos)
        print(line)
    print("")
    print("  advice about a player past the 'fringe' rank at his position is")
    print("  %s - downgraded, tagged, never dropped." % SIZED_TAG)
    print("  K/DEF are exempt: a 32-deep waiver pool in every format.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
