"""Recommendation engine: value, need, tiers, survival odds, runs, pivots.

Everything here is deliberately explainable - each recommendation carries the
reasons that produced it, because the user has 30 seconds to trust or override.
"""

import math
from typing import Dict, List, Optional, Tuple

from .models import POSITIONS, Player, _applied_order

# Positions the engine will not recommend before the endgame rounds.
LATE_ONLY = ("K", "DEF")


# --- probability helpers ---------------------------------------------------
def _p_still_there(pick_no: float, adp: float, scale: float) -> float:
    """P(a player is still on the board at `pick_no`).

    Logistic rather than normal: ADP standard deviations are measured across
    many drafts, and any single draft has far fatter tails than a normal curve
    allows. A normal model reports 0% for anyone more than three ADP-sigmas
    away, which makes the whole column useless exactly when it matters.
    """
    if scale <= 0:
        scale = 1.0
    z = (pick_no - adp) / scale
    if z > 40:
        return 0.0
    if z < -40:
        return 1.0
    return 1.0 / (1.0 + math.exp(z))


def effective_adp(p: Player) -> float:
    return float(p.adp) if p.adp else float(p.rank)


def effective_sd(p: Player) -> float:
    if p.adp_stdev and p.adp_stdev > 0:
        return float(p.adp_stdev)
    return max(3.0, 0.15 * effective_adp(p))


def effective_scale(p: Player) -> float:
    """Spread used for survival. Floored so early picks are not falsely certain."""
    return max(2.5, effective_sd(p)) * 1.15


def survival_odds(state, player: Player, horizon: Optional[int] = None,
                  intel=None) -> float:
    """Rough P(player is still available at my next pick).

    Conditions on him being available right now, then nudges by how many of the
    teams picking in between actually need that position.
    """
    if horizon is None:
        horizon = state.next_my_pick()
        if horizon is not None and horizon == state.current_pick():
            horizon = state.my_pick_after_this()
    if horizon is None:
        return 0.0

    now = state.current_pick()
    if horizon <= now:
        return 1.0

    # Rivals picking between now and my next pick. My own on-clock pick is
    # not a threat to me: at a back-to-back snake turn (say picks 10 and 11)
    # nobody else picks in between, so survival is a certainty.
    between = [state.team_at(n) for n in range(now, horizon)
               if state.team_at(n) != state.my_slot]
    if not between:
        return 1.0

    adp, scale = effective_adp(player), effective_scale(player)
    p_now = _p_still_there(now - 0.5, adp, scale)
    p_then = _p_still_there(horizon - 0.5, adp, scale)
    if p_now <= 1e-6:
        base = 0.02 if horizon - now > 6 else 0.15
    else:
        base = max(0.0, min(1.0, p_then / p_now))

    # Roster-need adjustment across the teams picking between now and then.
    # Applied as an exponent rather than a multiplier on the hazard: scaling the
    # hazard can push it past 1.0 and crush every number to zero, which is what
    # made this column unreadable. A power keeps it smooth and inside (0, 1).
    if between:
        teams_between = set(between)
        needy = 0.0
        for t in teams_between:
            want = 1.0 if team_needs_pos(state, t, player.pos) else 0.0
            if intel is not None:
                # A known manager tendency beats a generic roster-need guess.
                want = max(want, intel.manager_appetite(t, player))
            needy += want
        need_frac = needy / float(len(teams_between))
        base = base ** (0.85 + 0.5 * need_frac)
    return max(0.0, min(1.0, base))


# --- roster need -----------------------------------------------------------
def team_needs_pos(state, team: int, pos: str) -> bool:
    """Does this team still have an unfilled starting slot that pos can fill?"""
    counts = state.pos_counts(team)
    hard = state.league.hard_starter_counts()
    if counts.get(pos, 0) < hard.get(pos, 0):
        return True
    # Flex: any leftover flex slot this position is eligible for.
    for elig in state.league.flex_spots():
        if pos not in elig:
            continue
        used = 0
        for p2 in elig:
            used += max(0, counts.get(p2, 0) - hard.get(p2, 0))
        if used < len(state.league.flex_spots()):
            return True
    return False


def need_assessment(state, pos: str) -> Tuple[float, str]:
    """Score and label how badly MY roster needs this position right now."""
    if not state.my_slot:
        return 0.0, ""
    counts = state.pos_counts(state.my_slot)
    hard = state.league.hard_starter_counts()
    have, need = counts.get(pos, 0), hard.get(pos, 0)
    rounds_left = state.league.rounds - state.current_round() + 1

    if pos in LATE_ONLY:
        if have >= max(1, need):
            return -60.0, "already have %s" % pos
        if rounds_left <= 2:
            return 22.0, "%s must be filled" % pos
        return -55.0, "%s can wait" % pos

    if have < need:
        return 15.0, "fills %s%d" % (pos, have + 1)

    # Flex-eligible surplus still starts.
    flex_elig = [e for e in state.league.flex_spots() if pos in e]
    if flex_elig:
        surplus = 0
        for elig in flex_elig[:1]:
            for p2 in elig:
                surplus += max(0, counts.get(p2, 0) - hard.get(p2, 0))
        if surplus < len(flex_elig):
            return 8.0, "fills FLEX"

    if pos == "QB" and have >= 1:
        return -28.0, "QB filled"
    if pos == "TE" and have >= 1:
        return -14.0, "TE filled"
    depth_over = have - need
    return max(-18.0, -4.0 * depth_over), "%s depth" % pos


# --- tiers -----------------------------------------------------------------
def tier_remaining(state, player: Player) -> int:
    return sum(1 for p in state.available(player.pos) if p.tier == player.tier)


def next_tier_gap(state, pos: str, tier: int) -> Optional[float]:
    """Approx picks until the next tier at this position becomes the best one."""
    later = [p for p in state.available(pos) if p.tier > tier]
    if not later:
        return None
    best_next = min(later, key=lambda p: effective_adp(p))
    return effective_adp(best_next) - state.current_pick()


def tier_alerts(state) -> List[str]:
    """Cliff warnings, filtered to the ones that actually cost something.

    A thin tier is only news if it will be gone before my next pick. Without
    that filter every singleton tier fires on pick 1 and the alerts become
    wallpaper.
    """
    out = []
    for pos in ("RB", "WR", "TE", "QB"):
        avail = state.available(pos)
        if not avail:
            continue
        best = min(avail, key=lambda p: p.rank)
        left = sum(1 for p in avail if p.tier == best.tier)
        if left > 3:
            continue
        if state.my_slot and survival_odds(state, best) >= 0.60:
            continue
        gap = next_tier_gap(state, pos, best.tier)
        gap_txt = ("next %s tier ~%d picks out" % (pos, max(0, int(round(gap))))
                   if gap is not None else "no tier left after this")
        word = "LAST" if left == 1 else "%d left" % left
        out.append("%s: %s in Tier %d (%s) - %s"
                   % (pos, word, best.tier,
                      ", ".join(p.name for p in avail if p.tier == best.tier)[:52],
                      gap_txt))
    return out


def run_warning(state, window: int = 5, threshold: int = 3) -> Optional[str]:
    recent = state.recent_picks(window)
    if len(recent) < threshold:
        return None
    counts = {}
    for pk in recent:
        # Placeholder picks ('__skipped__') hold a board slot but name no
        # player - they count toward the window, not toward any position.
        pl = state.by_key.get(pk.player_key)
        if pl is None:
            continue
        counts[pl.pos] = counts.get(pl.pos, 0) + 1
    hot = [(c, p) for p, c in counts.items() if c >= threshold]
    if not hot:
        return None
    hot.sort(reverse=True)
    count, pos = hot[0]
    return "%s RUN: %d of the last %d picks were %s" % (pos, count, len(recent), pos)


# --- scoring ---------------------------------------------------------------
class Rec(object):
    def __init__(self, player: Player, score: float, survival: float,
                 reasons: List[str]):
        self.player = player
        self.score = score
        self.survival = survival
        self.reasons = reasons

    def reason_text(self, limit: int = 3) -> str:
        return "; ".join(self.reasons[:limit])


def pct(x: float) -> str:
    """Survival as a readable percent - never a flat, misleading 0."""
    if x >= 0.995:
        return ">99%"
    if x < 0.01:
        return "<1%"
    return "%d%%" % round(x * 100)


def blended_rank(player: Player) -> float:
    """Our rank, mildly pulled toward the FantasyPros consensus when present.

    Both numbers live on the same overall-rank scale (the ECR feed is the
    redraft-OVERALL page, not positional, so no positional->overall mapping is
    needed). The 0.7/0.3 split is a judgment call: our board stays the anchor -
    it carries the intel and the league's scoring - while 500-odd experts get
    enough weight to sand off a single-source outlier. No ECR, no change.
    """
    if player.ecr is None:
        return float(player.rank)
    return 0.7 * float(player.rank) + 0.3 * float(player.ecr)


def consensus_edge(player: Player) -> Optional[float]:
    """How many overall ranks higher (+) or lower (-) we sit vs consensus.

    Positive means our blended view likes him MORE than the expert consensus
    (his ECR number is worse than where we slot him). None without ECR.
    """
    if player.ecr is None:
        return None
    return float(player.ecr) - blended_rank(player)


def value_score(player: Player) -> float:
    """Steep-early value curve off the (consensus-blended) custom rank."""
    return 100.0 - 22.0 * math.log(max(1.0, blended_rank(player)))


# --- projections (VBD) ------------------------------------------------------
def _proj_boards(players) -> Dict[str, List[float]]:
    """Per-position projections, best first - the raw material for baselines."""
    boards = dict((pos, []) for pos in POSITIONS)
    for p in players:
        if p.proj_points:
            boards.setdefault(p.pos, []).append(float(p.proj_points))
    for board in boards.values():
        board.sort(reverse=True)
    return boards


def flex_allocation(league, players) -> Dict[str, float]:
    """League-wide flex slots absorbed per position, Dodds-style.

    Each flex slot goes to whichever eligible position offers the best
    remaining projection AFTER that position's hard starters are spoken for -
    i.e. flex demand is read off this pool's own projections, never a
    hardcoded split. Pure function of (league config, player pool).

    Groups fill most-restrictive first (a W/R slot before a W/R/T slot) over
    shared per-position cursors, so overlapping eligibilities cannot double
    count the same player. A group with no projected candidates falls back to
    the old fixed logic: an even split among its eligible positions.
    """
    teams = league.teams
    hard = league.hard_starter_counts()
    groups = {}   # eligibility tuple -> league-wide slot count
    for elig in league.flex_spots():
        key = tuple(elig)
        groups[key] = groups.get(key, 0) + teams
    if not groups:
        return {}

    boards = _proj_boards(players)
    cursor = {}   # position -> next flex candidate index past the hard starters
    for pos in boards:
        cursor[pos] = 0
        boards[pos] = boards[pos][hard.get(pos, 0) * teams:]

    alloc = dict((pos, 0.0) for pos in POSITIONS)
    for elig, slots in sorted(groups.items(), key=lambda kv: len(kv[0])):
        if not any(cursor[pos] < len(boards.get(pos, [])) for pos in elig):
            for pos in elig:
                alloc[pos] = alloc.get(pos, 0.0) + slots / float(len(elig))
            continue
        for _ in range(slots):
            best_pos, best_val = None, None
            for pos in elig:
                i = cursor.get(pos, 0)
                board = boards.get(pos, [])
                if i < len(board) and (best_val is None or board[i] > best_val):
                    best_pos, best_val = pos, board[i]
            if best_pos is None:
                break   # projected pool exhausted mid-group
            alloc[best_pos] += 1.0
            cursor[best_pos] += 1
    return alloc


def replacement_levels(state) -> Dict[str, float]:
    """Projection of the last league-wide starter at each position.

    Demand per position = this league's hard starters times teams, plus the
    flex slots the position actually wins in this pool (flex_allocation) -
    so a full-PPR league's WR-heavy flex raises the WR baseline while a
    12-team half-PPR league lands somewhere else entirely, by construction.
    The Nth-best projection at each position is the baseline a pick has to
    beat. Empty when the pool carries no projections, so every VBD term stays
    exactly zero and the engine behaves as if the column did not exist.
    """
    league = state.league
    hard = league.hard_starter_counts()
    flex = flex_allocation(league, state.players)
    boards = _proj_boards(state.players)
    out = {}
    for pos in boards:
        n = int(round(hard.get(pos, 0) * league.teams + flex.get(pos, 0.0)))
        if n <= 0 or not boards[pos]:
            continue
        out[pos] = boards[pos][min(n, len(boards[pos])) - 1]
    return out


def vbd(player: Player, repl: Dict[str, float]) -> float:
    """Value over the replacement-level starter; 0 when proj data is absent."""
    if not player.proj_points or player.pos not in repl:
        return 0.0
    return float(player.proj_points) - repl[player.pos]


def _positional_ranks(players) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Per-position order by projection and by market (ADP), keyed by player.

    Both orders are computed over the same set - players that carry a
    projection - so the two ranks disagree only when the sources actually
    disagree, not because the lists are different sizes.
    """
    by_pos = {}
    for p in players:
        if p.proj_points:
            by_pos.setdefault(p.pos, []).append(p)
    proj_rank, adp_rank = {}, {}
    for group in by_pos.values():
        for i, p in enumerate(sorted(group, key=lambda x: -float(x.proj_points)),
                              start=1):
            proj_rank[p.key] = i
        for i, p in enumerate(sorted(group, key=effective_adp), start=1):
            adp_rank[p.key] = i
    return proj_rank, adp_rank


def recommend(state, tree=None, top_n: int = 5, intel=None) -> List[Rec]:
    plan = tree.plan_now(state) if tree else None
    dnd = tree.dnd_keys if tree else {}
    current = state.current_pick()
    rnd = state.current_round()
    recs = []

    never = intel.never_draft if intel else {}
    pool = [p for p in state.available()
            if p.key not in dnd and p.key not in never]
    # Only score a sensible window of the board.
    pool = sorted(pool, key=lambda p: p.rank)[:60]

    repl = replacement_levels(state)
    proj_rank, adp_rank = _positional_ranks(state.available())

    for p in pool:
        reasons = []
        score = value_score(p)

        adp = effective_adp(p)
        if adp - current >= 8:
            reasons.append("value: ADP %.0f at pick %d" % (adp, current))
            score += min(12.0, (adp - current) * 0.5)
        elif current - adp >= 12:
            score -= min(8.0, (current - adp) * 0.2)

        # VBD blends in at modest weight - rank/ADP stay the anchor, and with
        # no projections loaded the term is exactly zero (current behavior).
        v = vbd(p, repl)
        if v:
            score += max(-20.0, min(20.0, 0.15 * v))

        # Badge when our blended view and the expert consensus disagree by a
        # dozen-plus overall ranks. Informational only - the blend already
        # moved value_score - but a big split is exactly the pick to re-check.
        edge = consensus_edge(p)
        if edge is not None and abs(edge) >= 12:
            reasons.append("vs consensus %+d" % int(round(edge)))

        # Badge when the projection-implied positional order disagrees with
        # the market by a lot. Informational only; VBD already moved the score.
        ppos, mpos = proj_rank.get(p.key), adp_rank.get(p.key)
        if ppos is not None and mpos is not None:
            if mpos - ppos >= 8:
                reasons.append("PROJ VALUE: %s%d by proj, %s%d by market"
                               % (p.pos, ppos, p.pos, mpos))
            elif ppos - mpos >= 8:
                reasons.append("proj fade: %s%d by proj, %s%d by market"
                               % (p.pos, ppos, p.pos, mpos))

        need_pts, need_txt = need_assessment(state, p.pos)
        score += need_pts
        if need_txt and need_pts > 0:
            reasons.append(need_txt)

        left = tier_remaining(state, p)
        urgency = max(-5.0, min(13.0, 13.0 - 3.5 * (left - 1)))
        score += urgency
        if left == 1:
            reasons.append("LAST in %s Tier %d" % (p.pos, p.tier))
        elif left <= 3:
            reasons.append("%d left in %s Tier %d" % (left, p.pos, p.tier))

        surv = survival_odds(state, p, intel=intel)
        score -= 14.0 * surv
        if surv >= 0.75:
            reasons.append("likely back at my next pick (%s)" % pct(surv))
        elif surv <= 0.25:
            reasons.append("won't last (%s)" % pct(surv))

        if plan:
            if p.key in plan.target_keys:
                score += 26.0 if plan.reach_ok else 16.0
                reasons.insert(0, "R%d TARGET%s" % (state.current_round(),
                                                    " (reach OK)" if plan.reach_ok else ""))
            elif plan.prefer and p.pos in plan.prefer:
                score += 12.0
                reasons.append("plan prefers %s" % p.pos)
            elif plan.avoid and p.pos in plan.avoid:
                score -= 18.0
                reasons.append("plan says avoid %s" % p.pos)

        # Research intel. An explicit thesis is the whole view of a player, so
        # it replaces the automatic keyword penalty rather than stacking on it.
        hit = intel.for_player(p.key) if intel else None
        if hit:
            pts, note = hit
            score += pts
            if note:
                # The thesis is the most useful thing on the line - keep it
                # near the front so it survives the reason-text truncation.
                reasons.insert(0 if abs(pts) >= 8 else 1, note)
            sched_pts, sched_txt = intel.playoff_adjust(p, rnd)
            if sched_pts:
                score += sched_pts
                reasons.append(sched_txt)
        else:
            flags = (p.flags or "").lower() + " " + (p.notes or "").lower()
            for bad, pts in (("injur", -7), ("holdout", -7), ("suspen", -9),
                             ("questionable", -3)):
                if bad in flags:
                    score += pts
                    reasons.append("flag: %s" % (p.flags or p.notes))
                    break
            if intel:
                sched_pts, sched_txt = intel.playoff_adjust(p, rnd)
                if sched_pts:
                    score += sched_pts
                    reasons.append(sched_txt)

        recs.append(Rec(p, score, surv, reasons))

    recs.sort(key=lambda r: -r.score)
    return recs[:top_n]


def wait_costs(state, recs, horizon: Optional[int] = None, intel=None,
               per_pos_cap: int = 12) -> List[Tuple[str, float]]:
    """Expected points lost by waiting, per position among the recommendations.

    For each recommended position: candidate projection minus the
    survival-weighted projection of the best player still available at my next
    pick. The weighting walks the position's board in projection order -
    P(this one is the best left) = his survival times everyone better being
    gone - capped at the top per_pos_cap players for speed; whatever mass is
    left past the cap is scored at the cap's floor. Empty when projections or
    a next pick are absent, so callers can skip the line silently.
    """
    if horizon is None:
        horizon = state.next_my_pick()
        if horizon is not None and horizon == state.current_pick():
            horizon = state.my_pick_after_this()
    if horizon is None or horizon <= state.current_pick():
        return []

    out = []
    seen = set()
    for r in recs:
        cand = r.player
        if cand.pos in seen:
            continue
        seen.add(cand.pos)
        if not cand.proj_points:
            continue
        board = sorted((p for p in state.available(cand.pos) if p.proj_points),
                       key=lambda p: -float(p.proj_points))[:per_pos_cap]
        if not board:
            continue
        expected, none_left = 0.0, 1.0
        for p in board:
            s = survival_odds(state, p, horizon=horizon, intel=intel)
            expected += none_left * s * float(p.proj_points)
            none_left *= (1.0 - s)
        expected += none_left * float(board[-1].proj_points)
        out.append((cand.pos, max(0.0, float(cand.proj_points) - expected)))
    return out


# --- injury badges ----------------------------------------------------------
_INJURY_BADGES = None
_DURABILITY_FLAGS = None


def injury_badges() -> Dict[str, str]:
    """Compact injury badges keyed by Player.nkey, cached for the session.

    POSITIVE-ONLY, like exposure flags: a badge means Sleeper has a filed
    report (Q/D/O/IR/HOLD/...); no badge means no report, which must never be
    read as 'healthy'. Offline with no cache the map is simply empty - the
    war room renders nothing rather than failing a draft over a nicety.
    """
    global _INJURY_BADGES
    if _INJURY_BADGES is None:
        try:
            from .projections import fetch_injury_status, injury_badge
            _INJURY_BADGES = dict((k, injury_badge(v)) for k, v in
                                  fetch_injury_status(quiet=True).items())
        except Exception:
            _INJURY_BADGES = {}
    return _INJURY_BADGES


def durability_flags() -> Dict[str, Tuple[str, str]]:
    """(flag, detail) durability tuples keyed by Player.nkey, session-cached.

    Lazily memoized exactly like injury_badges(), and POSITIVE-ONLY the same
    way: an entry means we hold seasons of nflverse games data and this is
    what it says; an absent name (2026 rookies, cross-source misses) means NO
    INFORMATION - never "durable". Offline with no cache the map is simply
    empty, so a network hiccup can never break a draft over a nicety.
    """
    global _DURABILITY_FLAGS
    if _DURABILITY_FLAGS is None:
        try:
            from .durability import SEASONS, score
            from .nflverse import games_played
            games = games_played(SEASONS)
            flags = {}
            for k in games:
                got = score(k, games=games, seasons=SEASONS)
                if got is not None:
                    flags[k] = got
            _DURABILITY_FLAGS = flags
        except Exception:
            _DURABILITY_FLAGS = {}
    return _DURABILITY_FLAGS


def warm_caches() -> None:
    """Pre-fetch every network-backed cache the draft loop can touch.

    One guarded call for CLI startup: the Sleeper players dump behind injury
    badges is ~16MB and the nflverse games files are MB-scale, so warming
    them before the first pick means no fetch ever lands while someone is on
    the clock. Each leg swallows its own failures - warming is a nicety and
    must never keep a war room from starting.
    """
    injury_badges()        # Sleeper players dump (12h cache window)
    durability_flags()     # nflverse games-played CSVs (24h cache window)
    try:                   # season projections (6h cache window)
        from .projections import fetch_espn, fetch_sleeper
        fetch_espn(3, quiet=True)
        fetch_sleeper(quiet=True)
    except Exception:
        pass


def _risk_badge(nkey: str, inj: Dict[str, str],
                dur: Dict[str, Tuple[str, str]]) -> str:
    """Combined '[INJ|DUR]' badge text: injury badge first, then a RED or
    YELLOW durability flag. GREEN never renders - the badge column is for
    risk, and painting most of the board green would bury the news."""
    b = inj.get(nkey, "")
    d = dur.get(nkey)
    if d and d[0] in ("RED", "YELLOW"):
        b = ("%s|%s" % (b, d[0])) if b else d[0]
    return b


def _badged(label: str, badge: str, width: int = 0) -> str:
    """Append ' [BADGE]' to a label, trimming the label to keep a column."""
    if not badge:
        return label[:width] if width else label
    if width:
        return "%s [%s]" % (label[:width - len(badge) - 3], badge)
    return "%s [%s]" % (label, badge)


# --- rendering -------------------------------------------------------------
class Ansi(object):
    def __init__(self, enabled: bool = True):
        self.on = enabled

    def _w(self, code, s):
        return "\033[%sm%s\033[0m" % (code, s) if self.on else s

    def bold(self, s):
        return self._w("1", s)

    def red(self, s):
        return self._w("1;31", s)

    def yellow(self, s):
        return self._w("1;33", s)

    def green(self, s):
        return self._w("1;32", s)

    def cyan(self, s):
        return self._w("1;36", s)

    def dim(self, s):
        return self._w("2", s)


def on_clock_block(state, tree=None, alerts=None, width: int = 74,
                   color: bool = True, intel=None, matcher=None,
                   exposure=None) -> str:
    """The five-part answer, answer-first, readable in about five seconds."""
    from .models import fmt_pick

    c = Ansi(color)
    alerts = alerts or []
    out = []
    line = "=" * width
    thin = "-" * width

    current = state.current_pick()
    rnd = state.current_round()
    recs = recommend(state, tree, top_n=5, intel=intel)

    out.append(c.cyan(line))
    header = " ON THE CLOCK   pick %d  (%s)   round %d" % (
        current, fmt_pick(current, state.teams), rnd)
    out.append(c.bold(header))

    # Cross-league exposure: flag-only and positive-only (see engine/exposure).
    # Rendered OUTSIDE reason_text()'s truncation: a player with 3+ organic
    # reasons must still show the flag - this block is where it gets acted on.
    expo_notes = {}
    if exposure is not None and exposure.available:
        banner = exposure.banner_text()
        if banner:
            out.append(c.yellow("   ! " + banner))
        for r in recs:
            held = exposure.flag(r.player.key)
            if held:
                expo_notes[r.player.key] = "also yours in %s" % ", ".join(held)

    if not recs:
        out.append("  No players available to recommend.")
        out.append(c.cyan(line))
        return "\n".join(out)

    # 1. The pick. Injury and durability badges are positive-only: no badge =
    # no filed report / no games data, which is never a claim of health.
    inj = injury_badges()
    dur = durability_flags()
    top = recs[0]
    out.append(c.green("  PICK >>  %s"
                       % _badged(top.player.label(),
                                 _risk_badge(top.player.nkey, inj, dur))))
    # Durability detail rides the reason line OUTSIDE reason_text()'s
    # truncation (same rule as exposure): a top pick with 3+ organic reasons
    # must still show the raw games evidence behind a RED/YELLOW flag.
    reason_line = top.reason_text()
    d = dur.get(top.player.nkey)
    if d and d[0] in ("RED", "YELLOW"):
        note = "durability %s: %s" % (d[0], d[1])
        reason_line = ("%s; %s" % (reason_line, note)) if reason_line else note
    out.append("           %s" % reason_line)
    if top.player.key in expo_notes:
        out.append(c.yellow("           ! " + expo_notes[top.player.key]))

    # 2. Alternates.
    if len(recs) > 1:
        out.append(thin)
        out.append(c.bold("  ALTERNATES"))
        for i, r in enumerate(recs[1:], start=2):
            note = expo_notes.get(r.player.key)
            out.append("   %d. %-28s %5s back  %s%s"
                       % (i, _badged(r.player.short_label(),
                                     _risk_badge(r.player.nkey, inj, dur), 28),
                          pct(r.survival),
                          r.reason_text(2),
                          c.yellow("  [" + note + "]") if note else ""))

    # 3. Survival odds.
    nxt = state.next_my_pick()
    horizon = state.my_pick_after_this() if (nxt == current) else nxt
    out.append(thin)
    if horizon:
        away = horizon - current
        out.append(c.bold("  SURVIVAL to my next pick %s (%d picks away)"
                          % (fmt_pick(horizon, state.teams), away)))
        cells = ["%s %s" % (r.player.surname()[:12], pct(r.survival)) for r in recs]
        out.append("   " + " | ".join(cells))
        # VONA: what waiting until that pick is expected to cost, by position.
        costs = wait_costs(state, recs, horizon=horizon, intel=intel)
        if costs:
            out.append("   WAIT COST  " + " | ".join(
                "%s ~%d pts" % (pos, int(round(cost))) for pos, cost in costs))
    else:
        out.append(c.bold("  SURVIVAL: this is my last pick"))

    # 4. Tier alerts + 5. run warning.
    talerts = tier_alerts(state)
    if talerts:
        out.append(thin)
        out.append(c.bold("  TIERS"))
        for t in talerts:
            out.append(c.yellow("   ! " + t))

    run = run_warning(state)
    if run:
        out.append(c.red("   ! " + run))

    # Strategy state.
    out.append(thin)
    if tree and tree.branches:
        branch = tree.active(state)
        bname = ("%s (%s)" % (branch.id, branch.name)) if branch else "none"
        status = tree.script_status(state)
        status_txt = c.green(status) if status.startswith("ON") else c.yellow(status)
        out.append(c.bold("  STRATEGY  branch %s   %s" % (bname, status_txt)))
        plan = tree.plan_now(state)
        if plan:
            out.append("   R%d plan: %s" % (rnd, plan.describe()))
            if plan.notes:
                out.append(c.dim("   note: %s" % plan.notes))
        else:
            out.append(c.dim("   no plan line for round %d - best available" % rnd))
        # A branch is a fork, not a fact. If another one still qualifies, say so
        # rather than letting a tie-break silently decide the draft.
        if matcher is not None:
            rivals = tree.rival_branches(state, matcher)
            if rivals:
                alts = ", ".join("%s (%s) - `pivot %s`"
                                 % (b, tree.branches[b].name, b) for b in rivals)
                out.append(c.yellow("   ! also live right now: " + alts))
    else:
        out.append(c.bold("  STRATEGY  (no contingency tree loaded)"))

    for a in alerts:
        prefix = "   >> PIVOT: " if a.level == "pivot" else "   ! "
        text = a.text + (("  ->  `pivot %s`" % a.goto) if a.goto else "")
        out.append(c.red(prefix + text) if a.level == "pivot"
                   else c.yellow(prefix + text))

    out.append(c.cyan(line))
    return "\n".join(out)


def _my_last_pick_overall(state) -> int:
    """Applied-order marker of my most recent pick (0 if I have none).

    Compares by application order (Pick.seq, stamped by PickBoard), NOT by
    overall number: a keeper parked at overall 100 before the draft starts
    would otherwise make every early pick look 'recent' forever - and my own
    parked keeper would silence the board shift entirely.
    """
    mine = [_applied_order(p) for p in state.picks.values()
            if p.team == state.my_slot]
    return max(mine) if mine else 0


def board_shift(state) -> Tuple[Dict[str, int], List[Player]]:
    """What has come off the board since my last pick: counts + notable names."""
    since = _my_last_pick_overall(state)
    gone = [state.by_key[p.player_key] for p in state.picks.values()
            if _applied_order(p) > since and p.player_key in state.by_key]
    counts = {}
    for pl in gone:
        counts[pl.pos] = counts.get(pl.pos, 0) + 1
    notable = sorted([p for p in gone if p.rank <= 40], key=lambda p: p.rank)
    return counts, notable


def strategy_brief(state, tree=None, intel=None, color: bool = True,
                   width: int = 74, exposure=None) -> str:
    """Between-picks digest: what shifted, targets alive/lost, decisions ahead."""
    from .models import fmt_pick, round_and_pick

    c = Ansi(color)
    out = []
    thin = "-" * width
    out.append(c.cyan("=" * width))

    branch = tree.active(state) if tree else None
    header = "  STRATEGY BRIEF   round %d" % state.current_round()
    if branch:
        header += "   branch %s (%s)" % (branch.id, branch.name)
    out.append(c.bold(header))
    if tree and tree.branches:
        status = tree.script_status(state)
        out.append("   " + (c.green(status) if status.startswith("ON")
                            else c.yellow(status)))

    # My roster in one line.
    roster = state.my_roster()
    if roster:
        out.append("   my roster: " + ", ".join(
            "%s(%s)" % (p.surname(), p.pos) for p in roster))

    # What shifted since my last pick.
    since = _my_last_pick_overall(state)
    counts, notable = board_shift(state)
    if counts:
        parts = ["%s x%d" % (pos, n) for pos, n in
                 sorted(counts.items(), key=lambda kv: -kv[1])]
        label = "since my last pick" if since else "so far"
        out.append(thin)
        out.append(c.bold("  BOARD SHIFT (%s): %s" % (label, ", ".join(parts))))
        if notable:
            out.append("   gone: " + ", ".join(p.surname() for p in notable[:9]))

    # Targets: lost since last pick, and still alive with survival odds.
    if branch and state.my_slot:
        lost, alive = [], []
        seen = set()
        horizon_rounds = set()
        nxt = state.next_my_pick()
        for k in range(3):
            if nxt is None:
                break
            horizon_rounds.add(round_and_pick(nxt, state.teams)[0])
            nxt = state.next_my_pick(after=nxt)
        for pr in branch.plan:
            if not any(r in horizon_rounds for r in pr.rounds):
                continue
            for key in pr.target_keys:
                if key in seen or key not in state.by_key:
                    continue
                seen.add(key)
                pl = state.by_key[key]
                pk = state.drafted.get(key)
                if pk is not None:
                    if _applied_order(pk) > since and pk.team != state.my_slot:
                        lost.append(pl)
                else:
                    alive.append((pl, survival_odds(state, pl)))
        out.append(thin)
        if lost:
            out.append(c.red("  TARGETS LOST: " +
                             ", ".join(p.surname() for p in lost[:8])))
        if alive:
            # Most endangered first - those are the ones the next pick is about.
            alive.sort(key=lambda t: t[1])
            out.append(c.bold("  TARGETS ALIVE (next ~3 rounds, most at-risk first)"))
            cells = ["%s(%s) %s" % (p.surname(), p.pos, pct(s))
                     for p, s in alive[:8]]
            out.append("   " + " | ".join(cells[:4]))
            if len(cells) > 4:
                out.append("   " + " | ".join(cells[4:8]))

        # The plan for my next few picks.
        out.append(thin)
        out.append(c.bold("  MY NEXT PICKS"))
        nxt = state.next_my_pick()
        for _ in range(3):
            if nxt is None:
                break
            rnd = round_and_pick(nxt, state.teams)[0]
            pr = branch.plan_for(rnd)
            out.append("   %s (%d away): %s"
                       % (fmt_pick(nxt, state.teams), nxt - state.current_pick(),
                          pr.describe() if pr else "best available"))
            nxt = state.next_my_pick(after=nxt)

    # Cross-league exposure among my picks and my upcoming targets. Flags are
    # positive-only: an unflagged player is unknown, never "clean", so the
    # section renders hits (with the coverage caveat) or nothing at all.
    if exposure is not None and exposure.available:
        rows, seen = [], set()
        for pl, leagues in exposure.overlap(state):
            seen.add(pl.key)
            rows.append("%s(%s) drafted - also yours in %s"
                        % (pl.surname(), pl.pos, ", ".join(leagues)))
        if branch:
            for pr in branch.plan:
                for key in pr.target_keys:
                    if key in seen or key not in state.by_key \
                            or state.is_drafted(key):
                        continue
                    held = exposure.flag(key)
                    if held:
                        seen.add(key)
                        pl = state.by_key[key]
                        rows.append("%s(%s) target - also yours in %s"
                                    % (pl.surname(), pl.pos, ", ".join(held)))
        if rows:
            out.append(thin)
            out.append(c.bold("  EXPOSURE"))
            for row in rows[:6]:
                out.append("   " + row)
            banner = exposure.banner_text()
            if banner:
                out.append(c.dim("   " + banner))

    # Key decisions, derived from the tree's own watch rules.
    decisions = []
    if tree:
        for w in tree.watch:
            cond = w.get("when", {}) or {}
            if cond.get("type") == "players_gone":
                names = list(cond.get("names", []) or [])
                gone = 0
                left = []
                for nm in names:
                    hit = [p for p in state.players
                           if p.name.lower() == str(nm).lower()]
                    pl = hit[0] if hit else None
                    if pl and state.is_drafted(pl.key):
                        gone += 1
                    elif pl:
                        left.append(pl)
                if len(left) == 1:
                    s = survival_odds(state, left[0])
                    decisions.append("last one standing: %s (%s to my next pick)"
                                     % (left[0].surname(), pct(s)))
    counts_mine = state.pos_counts(state.my_slot) if state.my_slot else {}
    rnd = state.current_round()
    if counts_mine.get("QB", 0) == 0 and rnd >= 5:
        decisions.append("no QB yet - the value pocket is open (round 5-6, then after pick 100)")
    if counts_mine.get("TE", 0) == 0 and rnd >= 6:
        decisions.append("no TE yet - decide: mid tier now or punt to streamers")
    rounds_left = state.league.rounds - rnd + 1
    if rounds_left <= 3 and (counts_mine.get("K", 0) == 0
                             or counts_mine.get("DEF", 0) == 0):
        decisions.append("K/DEF still open - they are the last two rounds' job")
    if decisions:
        out.append(thin)
        out.append(c.bold("  DECISIONS"))
        for d in decisions[:4]:
            out.append(c.yellow("   > " + d))

    out.append(c.cyan("=" * width))
    return "\n".join(out)


def board_text(state, pos: Optional[str] = None, limit: int = 15,
               color: bool = True) -> str:
    c = Ansi(color)
    avail = sorted(state.available(pos), key=lambda p: p.rank)[:limit]
    if not avail:
        return "Nothing available."
    lines = [c.bold("  %-4s %-24s %-5s %-4s %-5s %-6s %s"
                    % ("#", "PLAYER", "POS", "TM", "TIER", "ADP", "BYE"))]
    # Injury and durability badges are positive-only: an unbadged row has no
    # filed report / no games data, which is not the same claim as 'healthy'.
    inj = injury_badges()
    dur = durability_flags()
    last_tier = None
    for p in avail:
        if pos and last_tier is not None and p.tier != last_tier:
            lines.append(c.dim("  " + "-" * 52))
        last_tier = p.tier
        lines.append("  %-4d %-24s %-5s %-4s T%-4d %-6s %s"
                     % (p.rank, _badged(p.name, _risk_badge(p.nkey, inj, dur), 24),
                        p.pos, p.team, p.tier,
                        ("%.1f" % p.adp) if p.adp else "-", p.bye or "-"))
    return "\n".join(lines)
