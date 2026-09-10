"""Positional matchup engine: how a defense treats a whole position group.

    python -m engine.matchups --league espn-1 --week 1

THE QUESTION. Not "is this defense good" but "is this defense bleeding to
MY guy's position". A unit can be top-5 overall and still the softest TE
draw on the board; fantasy is scored by position, so the matchup read has
to be by position too.

POINTS ALLOWED PER GAME, PER POSITION (PA/pos). For every NFL defense we
sum the fantasy points every QB / RB / WR / TE scored AGAINST it and divide
by its games. The inputs are nflverse's per-week player box scores
(engine/nflverse.fetch_weekly_stats - the stats_player release's
stats_player_week_<season>.csv, the only nflverse asset carrying
`opponent_team` next to raw per-week stat columns).

RAW STATS, NOT BAKED POINTS. That file ships `fantasy_points` and
`fantasy_points_ppr` columns, and we deliberately ignore both: they are
standard and full-PPR ONLY, with a 4-point passing TD and -2 interception
baked in. Scoring here comes from LeagueConfig.scoring, so a 6-point-passing
-TD or half-PPR or -1-INT league gets ITS OWN defensive ranks. score_row()
was validated against the file's own PPR column across all 6,037 QB/RB/WR/TE
rows of 2025 under espn-1's scoring (which happens to match nflverse's
formula): 0 mismatches over 0.02 points.
  One documented judgment call inside score_row: fumbles use the OFFENSIVE
  triad (sack + rushing + receiving fumbles lost) rather than the file's
  `fumbles_lost_total`, which also counts fumbles lost on kick and punt
  returns. That is the mainstream platform convention and it is what makes
  the validation above land exactly; a returner who coughs one up on a
  kickoff is not a knock on the defense his OFFENSE faced.

GRADES. Defenses are ranked per position, rank 1 = most points allowed =
the softest draw. Rank becomes a percentile (100 = softest, 0 = stingiest)
and the percentile becomes a grade. Both cuts below are JUDGMENT CALLS,
stated so they can be argued with:

  SMASH    pctl >= 87.5   softest eighth   (top 4 of 32)
  GOOD     pctl >= 62.5                    (next 8)
  NEUTRAL  pctl >  37.5   the middle       (8)
  TOUGH    pctl >  12.5                    (8)
  AVOID    otherwise      stingiest eighth (bottom 4 of 32)

THE MAGNITUDE GATE. Rank alone lies when the league is tight: somebody is
always 1st of 32 even in a season where all 32 defenses sit within a point
of each other, and calling that a SMASH would be manufacturing an edge.
So the two EXTREME grades additionally require the defense to be at least
EDGE_Z (0.5) standard deviations off the league mean for that position.
A defense that ranks top-4 but is not separated from the pack degrades to
GOOD, not SMASH; same on the AVOID side. Every graded cell carries its `z`
so the caller can see the separation it was graded on.

THIN BASIS. A defense with fewer than MIN_GAMES games cannot earn SMASH or
AVOID at all - the rate is too noisy to bet on. Those cells carry
thin=True and say so in their evidence string.

THE 2026 CAVEAT, SAID OUT LOUD. It is September 2026 and week 1 has not
been played: there is NO current-season defensive data, so every grade you
see today is computed from the 2025 season, against defenses that have
since changed coordinators, corners and safeties. That is not a footnote,
it is the headline, so:
  * every table carries `basis` ("2025 season, 17 games") and `caveat`;
  * every matchup dict carries `basis` and `prior_only`;
  * every evidence string names the season it came from, and when the
    grade is prior-season-only it says the rosters and schemes have
    changed since.
A 2025-derived grade must never be printed as if it were a fact about 2026.

BLENDING, ONCE 2026 WEEKS EXIST. When the current season has games,
current and prior rates are blended per defense at the RATE level:

    w_current = weeks_played / (weeks_played + PRIOR_HALFLIFE)   (halflife 4)
    w_prior   = 1 - w_current

  weeks played:   0      2      4      6      8     12     17
  current-season: 0%    33%    50%    60%    67%    75%    81%

Documented judgment call: PRIOR_HALFLIFE=4 means the young current season
overtakes the prior one at four weeks, which is roughly where per-game
defensive rates stop being one-game noise, and the prior season never quite
vanishes (19% at week 17) because a 17-game sample still carries signal
about personnel that did not turn over. A defense present in only one of
the two seasons uses that one at full weight and says so.

AS A WEIGHTED SOURCE. The engine ships as a built-in `feed` source with id
"matchup", DISABLED by default with a weight SUGGESTION of 12 (see
SOURCE_DEFAULT). It is disabled on purpose: adding an enabled source would
silently re-normalize every weight already in data/sources.yaml, changing
consensus verdicts the user never asked to change. register() adds the row
disabled; the user opts in from the sources panel.

  VOTE RULE (judgment calls, stated): START on SMASH, SIT on AVOID,
  ABSTAIN on GOOD / NEUTRAL / TOUGH. The neutral middle is deliberately
  wide - three of five grades, 24 of 32 defenses - because a matchup that
  is merely "fine" should not be allowed to outvote a projection. A source
  that speaks on every row is a source that adds noise to every row.
  Votes are further gated to STARTABLE players (startable_keys): a dream
  matchup for the WR6 on a 16-man bench is not a start call, and telling
  someone to sit a player they were never starting is not advice.

WIRING NOTE (honest degradation). engine/consensus.build_consensus maps
feed handles to voice builders by name ("engine", "espn-proj",
"sleeper-proj", "chen-tiers"); "matchup" is not in that list yet, so an
enabled matchup source would appear in the sources list and cast NO votes -
a silent abstention on every row. Two ways out, both supported here:
  * preferred, one line in consensus.py's feed loop, calling feed_votes();
  * available today without touching that file, augment_consensus(), which
    appends the matchup vote to a built consensus result and re-weighs each
    row through consensus's OWN pure helpers (weigh / agreement /
    verdict_of). consensus_gap() reports the silent-abstention state so a
    page can warn instead of quietly showing a source that never speaks.
"""

import argparse
import math
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from engine import nflverse, weekly
    from engine.models import LeagueConfig, Player, norm_pos
    from engine.projections import name_key, norm_team
except ImportError:  # run directly as `python engine/matchups.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import nflverse, weekly
    from engine.models import LeagueConfig, Player, norm_pos
    from engine.projections import name_key, norm_team

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Positions that get a PA/pos read. K and DEF are excluded on purpose: no
# defense "allows points to kickers" in any sense a lineup decision can use,
# and DEF-vs-DEF is an offense question, not a matchup-group question.
PA_POSITIONS = ("QB", "RB", "WR", "TE")

CURRENT_SEASON = weekly.SEASON      # 2026
PRIOR_SEASON = CURRENT_SEASON - 1   # 2025 - the last completed season

# Grade bands, softest first. See the module docstring: judgment calls.
GRADE_BANDS = ((87.5, "SMASH"), (62.5, "GOOD"), (37.5, "NEUTRAL"),
               (12.5, "TOUGH"), (float("-inf"), "AVOID"))
GRADES = ("SMASH", "GOOD", "NEUTRAL", "TOUGH", "AVOID")
GRADE_ORDER = dict((g, i) for i, g in enumerate(GRADES))

EDGE_Z = 0.5        # SD off the league mean an extreme grade must clear
MIN_GAMES = 4       # fewer games than this = thin basis, no extreme grade
PRIOR_HALFLIFE = 4.0

# What the extreme grades soften to when the magnitude gate or the thin-basis
# rule blocks them. Never softer than one step - the rank IS real.
_SOFTEN = {"SMASH": "GOOD", "AVOID": "TOUGH"}

# The built-in source row. DISABLED, with a weight SUGGESTION - opting in is
# the user's call, and an enabled row would silently re-normalize every other
# weight in the registry.
SOURCE_ID = "matchup"
SOURCE_DEFAULT = {
    "id": SOURCE_ID,
    "name": "Positional Matchup (PA/pos)",
    "type": "feed",
    "handle": SOURCE_ID,
    "enabled": False,
    "weight": 12,
    "notes": ("Built-in: points allowed per game to QB/RB/WR/TE, in THIS "
              "league's scoring. Votes start on SMASH and sit on AVOID for "
              "startable players only, and abstains in the neutral middle. "
              "Disabled by default - enabling it re-normalizes every other "
              "weight, so that is your call, not the engine's. Pre-week-1 "
              "2026 its grades come from the 2025 season."),
}

# Grade -> vote. Everything absent from this map is an abstention.
VOTE_ON = {"SMASH": "start", "AVOID": "sit"}


# --- scoring ---------------------------------------------------------------

def _f(val) -> float:
    """Float or 0.0 - nflverse CSVs use 'NA' and '' for a missing stat."""
    s = (str(val) if val is not None else "").strip()
    if not s or s.upper() == "NA":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def score_row(row: Dict, scoring: Dict) -> float:
    """Fantasy points for one nflverse weekly stat row, in a league's scoring.

    `scoring` is LeagueConfig.scoring - the raw yaml mapping. Keys absent
    from a league's file fall back to the near-universal defaults spelled
    out below (a league that scores 6-point passing TDs writes it down;
    one that omits `two_point_conversion` is not a league where a two-point
    conversion is worth nothing).

    Fumbles: the offensive triad only - see the module docstring.
    """
    s = scoring or {}

    def val(key, default):
        v = s.get(key)
        return default if v is None else float(v)

    def per(key, default):
        v = s.get(key)
        v = default if v is None else float(v)
        return v if v else default   # a 0 divisor is a typo, not a rule

    pts = 0.0
    pts += _f(row.get("passing_yards")) / per("passing_yards_per_point", 25.0)
    pts += _f(row.get("passing_tds")) * val("passing_td", 4.0)
    pts += _f(row.get("passing_interceptions")) * val("interception", -2.0)
    pts += _f(row.get("rushing_yards")) / per("rushing_yards_per_point", 10.0)
    pts += _f(row.get("rushing_tds")) * val("rushing_td", 6.0)
    pts += _f(row.get("receptions")) * val("reception", 0.0)
    pts += _f(row.get("receiving_yards")) / per("receiving_yards_per_point", 10.0)
    pts += _f(row.get("receiving_tds")) * val("receiving_td", 6.0)
    fumbles = (_f(row.get("sack_fumbles_lost"))
               + _f(row.get("rushing_fumbles_lost"))
               + _f(row.get("receiving_fumbles_lost")))
    pts += fumbles * val("fumble_lost", -2.0)
    two_pt = (_f(row.get("passing_2pt_conversions"))
              + _f(row.get("rushing_2pt_conversions"))
              + _f(row.get("receiving_2pt_conversions")))
    pts += two_pt * val("two_point_conversion", 2.0)
    pts += _f(row.get("special_teams_tds")) * val("return_td", 6.0)
    return pts


# --- pure core: points allowed to position ---------------------------------

def points_allowed(rows: Iterable[Dict], scoring: Dict,
                   positions: Sequence[str] = PA_POSITIONS
                   ) -> Tuple[Dict[Tuple[str, str], float], Dict[str, Set[str]]]:
    """PURE. Weekly stat rows -> (totals, games).

    totals: {(pos, defense): fantasy points that position scored against it}
    games:  {defense: set of game_ids it played}

    Games are counted from EVERY row facing that defense, not just the
    graded positions, so a defense that shut a position out completely
    still divides by its real game count instead of vanishing.
    """
    totals: Dict[Tuple[str, str], float] = {}
    games: Dict[str, Set[str]] = {}
    wanted = set(positions)
    for row in rows:
        opp = norm_team(row.get("opponent_team") or "")
        if not opp:
            continue
        gid = str(row.get("game_id") or "")
        if gid:
            games.setdefault(opp, set()).add(gid)
        pos = norm_pos(row.get("position") or "")
        if pos not in wanted:
            continue
        k = (pos, opp)
        totals[k] = totals.get(k, 0.0) + score_row(row, scoring)
    # A defense that appears only in totals (rows with no game_id) still
    # deserves a denominator; never divide by zero silently.
    for pos, opp in totals:
        games.setdefault(opp, set())
    return totals, games


def rates(totals: Dict[Tuple[str, str], float], games: Dict[str, Set[str]],
          positions: Sequence[str] = PA_POSITIONS
          ) -> Dict[str, Dict[str, Dict]]:
    """PURE. Totals+games -> {pos: {defense: {"pa_per_game", "games"}}}.

    A defense with zero counted games is dropped rather than shown at an
    infinite rate.
    """
    out: Dict[str, Dict[str, Dict]] = dict((p, {}) for p in positions)
    for pos in positions:
        for defense, gset in games.items():
            n = len(gset)
            if n <= 0:
                continue
            pts = totals.get((pos, defense), 0.0)
            # pa_exact is what ranking and z-scores use; pa_per_game is the
            # display value. Ranking on the ROUNDED rate manufactured ties
            # (2025 QB: NO and SEA both 14.0 to two decimals, but not equal),
            # and a tie shares a rank, which put holes in the 1..32 ladder.
            out[pos][defense] = {"defense": defense, "pos": pos,
                                 "pa_exact": pts / n,
                                 "pa_per_game": round(pts / n, 2),
                                 "points": round(pts, 2), "games": n}
    return out


def _mean_sd(values: Sequence[float]) -> Tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def grade_for(pctl: float, z: float, thin: bool = False) -> str:
    """PURE. Percentile + separation -> one of GRADES.

    The magnitude gate and the thin-basis rule can only SOFTEN an extreme
    grade by one step (SMASH->GOOD, AVOID->TOUGH); they never flip a
    direction. See the module docstring for why both exist.
    """
    grade = "AVOID"
    for floor, name in GRADE_BANDS:
        if pctl >= floor:
            grade = name
            break
    if grade in _SOFTEN and (thin or abs(z) < EDGE_Z):
        return _SOFTEN[grade]
    return grade


def rank_defenses(pos_rates: Dict[str, Dict]) -> Dict[str, Dict]:
    """PURE. {defense: {"pa_per_game", "games"}} -> graded cells.

    Rank 1 = most points allowed = softest matchup. Ties share the better
    (lower) rank, the standard competition ranking, so two identical
    defenses cannot be graded differently for being alphabetically unlucky.
    Percentile is 100*(n-rank)/(n-1): softest = 100, stingiest = 0.
    """
    cells = list(pos_rates.values())
    n = len(cells)
    if n == 0:
        return {}

    def exact(c):
        v = c.get("pa_exact")
        return float(c["pa_per_game"] if v is None else v)

    values = [exact(c) for c in cells]
    mean, sd = _mean_sd(values)
    ordered = sorted(cells, key=lambda c: (-exact(c), c["defense"]))

    out = {}
    rank = 0
    prev = None
    for i, cell in enumerate(ordered):
        if prev is None or exact(cell) != prev:
            rank = i + 1
            prev = exact(cell)
        pctl = 100.0 * (n - rank) / (n - 1) if n > 1 else 50.0
        z = (exact(cell) - mean) / sd if sd > 0 else 0.0
        thin = cell["games"] < MIN_GAMES
        row = dict(cell)
        row.update({"rank": rank, "of": n, "pctl": round(pctl, 1),
                    "z": round(z, 2), "thin": thin,
                    "grade": grade_for(pctl, z, thin),
                    "league_mean": round(mean, 2), "league_sd": round(sd, 2)})
        out[cell["defense"]] = row
    return out


# --- basis + blending ------------------------------------------------------

def blend_weights(weeks_played: int,
                  prior_halflife: float = PRIOR_HALFLIFE) -> Tuple[float, float]:
    """PURE. (current_weight, prior_weight) for `weeks_played` of the season.

    w_current = weeks / (weeks + halflife). Zero weeks played puts ALL the
    weight on the prior season - which is exactly the September 2026 state
    and the reason the caveat exists. See the module docstring's table.
    """
    w = max(0, int(weeks_played or 0))
    if w <= 0:
        return 0.0, 1.0
    hl = float(prior_halflife) if prior_halflife and prior_halflife > 0 \
        else PRIOR_HALFLIFE
    cur = w / (w + hl)
    return round(cur, 4), round(1.0 - cur, 4)


def _basis_label(parts: List[Dict]) -> str:
    """'2025 season, 17 games' / '2026 wk1-5 (56%) + 2025 season (44%)'."""
    if not parts:
        return "no data"
    if len(parts) == 1:
        p = parts[0]
        if p.get("complete"):
            return "%d season, %d games" % (p["season"], p["games"])
        return "%d wk1-%d, %d games" % (p["season"], p["weeks"], p["games"])
    bits = []
    for p in sorted(parts, key=lambda q: -q["season"]):
        span = ("%d season" % p["season"] if p.get("complete")
                else "%d wk1-%d" % (p["season"], p["weeks"]))
        bits.append("%s (%d%%)" % (span, round(100 * p["weight"])))
    return " + ".join(bits)


def season_part(rows: List[Dict], season: int, scoring: Dict,
                positions: Sequence[str] = PA_POSITIONS) -> Dict:
    """PURE. One season's rows -> its rates plus the facts about its basis."""
    totals, games = points_allowed(rows, scoring, positions)
    weeks = set()
    for r in rows:
        try:
            weeks.add(int(str(r.get("week") or "").strip() or 0))
        except ValueError:
            continue
    weeks.discard(0)
    per_def = rates(totals, games, positions)
    max_games = max([len(g) for g in games.values()] or [0])
    return {"season": season, "weeks": max(weeks) if weeks else 0,
            "n_weeks": len(weeks), "games": max_games,
            "complete": len(weeks) >= 18, "rates": per_def,
            "weight": 1.0}


def build_table(parts: List[Dict], scoring_label: str = "",
                positions: Sequence[str] = PA_POSITIONS) -> Dict:
    """PURE. Weighted season parts -> the graded PA/pos table.

    Blending happens at the RATE level, per defense per position, using each
    part's `weight`. A defense missing from a part contributes nothing and
    its present parts are re-normalized, so a team that did not exist in the
    prior file is graded on what we actually have rather than being halved
    toward zero. Games are summed across the parts that carried the defense.
    """
    parts = [p for p in parts if p.get("weight", 0) > 0]
    total_w = sum(p["weight"] for p in parts) or 1.0
    for p in parts:
        p["weight"] = round(p["weight"] / total_w, 4)

    by_pos = {}
    for pos in positions:
        merged: Dict[str, Dict] = {}
        for part in parts:
            for defense, cell in (part["rates"].get(pos) or {}).items():
                acc = merged.setdefault(defense, {"defense": defense,
                                                  "pos": pos, "num": 0.0,
                                                  "wsum": 0.0, "games": 0,
                                                  "points": 0.0})
                rate = cell.get("pa_exact")
                rate = cell["pa_per_game"] if rate is None else rate
                acc["num"] += part["weight"] * float(rate)
                acc["wsum"] += part["weight"]
                acc["games"] += cell["games"]
                acc["points"] += cell.get("points") or 0.0
        pos_rates = {}
        for defense, acc in merged.items():
            if acc["wsum"] <= 0:
                continue
            blended = acc["num"] / acc["wsum"]
            pos_rates[defense] = {
                "defense": defense, "pos": pos, "pa_exact": blended,
                "pa_per_game": round(blended, 2), "games": acc["games"],
                "points": round(acc["points"], 2)}
        graded = rank_defenses(pos_rates)
        vals = [c["pa_exact"] for c in pos_rates.values()]
        mean, sd = _mean_sd(vals)
        by_pos[pos] = {
            "defenses": graded,
            "ranked": [c["defense"] for c in
                       sorted(graded.values(), key=lambda c: c["rank"])],
            "mean": round(mean, 2), "sd": round(sd, 2), "n": len(graded)}

    seasons = sorted(set(p["season"] for p in parts), reverse=True)
    prior_only = bool(parts) and all(p["season"] < CURRENT_SEASON
                                     for p in parts)
    basis = _basis_label(parts)
    caveat = ""
    if prior_only:
        caveat = ("Basis is %s - NOT %d. Rosters, coordinators and schemes "
                  "have changed since; treat these as priors, not facts "
                  "about this season." % (basis, CURRENT_SEASON))
    elif len(parts) > 1:
        caveat = ("Blended basis (%s): the %d sample is still young, so "
                  "prior-season form is carrying part of every grade."
                  % (basis, CURRENT_SEASON))
    return {"basis": basis, "basis_parts": parts, "caveat": caveat,
            "prior_only": prior_only, "seasons": seasons,
            "scoring": scoring_label, "positions": list(positions),
            "by_pos": by_pos}


# --- fetch + assemble ------------------------------------------------------

def pa_table(league: LeagueConfig,
             current_season: int = CURRENT_SEASON,
             prior_season: int = PRIOR_SEASON,
             positions: Sequence[str] = PA_POSITIONS,
             force: bool = False,
             rows_by_season: Optional[Dict[int, List[Dict]]] = None,
             quiet: bool = True) -> Dict:
    """The graded PA/pos table for THIS league's scoring.

    Fetches the current season first; when it has no games yet (September
    2026) the table is prior-season-only and says so loudly. `rows_by_season`
    injects fixtures and skips the network entirely.
    """
    scoring = league.scoring or {}
    label = league.scoring_label()
    parts: List[Dict] = []
    notes: List[str] = []

    def _rows(season: int, max_age: float) -> Optional[List[Dict]]:
        if rows_by_season is not None:
            return rows_by_season.get(season)
        try:
            return nflverse.fetch_weekly_stats(season, force=force,
                                               max_age_hours=max_age)
        except (RuntimeError, ValueError) as exc:
            notes.append("%d weekly stats unavailable (%s)" % (season, exc))
            return None

    cur_rows = _rows(current_season, 24.0)     # live season: refresh daily
    cur_part = None
    if cur_rows:
        cur_part = season_part(cur_rows, current_season, scoring, positions)
        if cur_part["n_weeks"] <= 0:
            cur_part = None
    if cur_part is None:
        notes.append("%d has no completed games on file - grades rest "
                     "entirely on %d" % (current_season, prior_season))

    weeks_played = cur_part["n_weeks"] if cur_part else 0
    w_cur, w_prior = blend_weights(weeks_played)

    prior_rows = _rows(prior_season, 168.0)    # completed season: weekly
    prior_part = None
    if prior_rows:
        prior_part = season_part(prior_rows, prior_season, scoring, positions)

    if cur_part is not None and w_cur > 0:
        cur_part["weight"] = w_cur
        parts.append(cur_part)
    if prior_part is not None and w_prior > 0:
        prior_part["weight"] = w_prior
        parts.append(prior_part)
    if not parts and cur_part is not None:
        cur_part["weight"] = 1.0
        parts.append(cur_part)

    table = build_table(parts, scoring_label=label, positions=positions)
    table["league"] = league.id
    table["notes"] = notes
    table["blend"] = {"weeks_played": weeks_played, "current": w_cur,
                      "prior": w_prior, "halflife": PRIOR_HALFLIFE}
    if not quiet:
        print("  matchups: %s (%s scoring); %s"
              % (table["basis"], label, table["caveat"] or "current-season basis"))
    return table


# --- player level ----------------------------------------------------------

def cell_for(pos: str, defense: str, table: Dict) -> Optional[Dict]:
    """The graded cell for one (position, defense), or None if ungraded."""
    pos = norm_pos(pos or "")
    block = (table.get("by_pos") or {}).get(pos)
    if not block:
        return None
    return (block.get("defenses") or {}).get(norm_team(defense or ""))


def _ordinal(n: int) -> str:
    n = int(n)
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


def evidence_for(cell: Dict, table: Dict, pos: str, scoring_label: str = "",
                 player: str = "") -> str:
    """One sentence a page can print verbatim, basis and all.

    Never states a prior-season grade as current-season fact: when the
    table is prior-only the sentence says the season it came from AND that
    rosters/schemes have changed.
    """
    label = (scoring_label or table.get("scoring") or "").upper()
    unit = "%s pts/game" % label if label else "pts/game"
    head = "%s allowed %.1f %s to %s" % (cell["defense"], cell["pa_per_game"],
                                         unit, pos)
    detail = "%s-most of %d, %s pctl, %+.1f SD" % (
        _ordinal(cell["rank"]), cell["of"],
        _ordinal(int(round(cell["pctl"]))), cell["z"])
    tail = "basis: %s" % table.get("basis", "unknown")
    if table.get("prior_only"):
        tail += "; %d rosters and schemes have changed since" % CURRENT_SEASON
    if cell.get("thin"):
        tail += ("; thin sample (%d games) - extreme grades withheld"
                 % cell["games"])
    return "%s (%s) - %s." % (head, detail, tail)


def matchup_for(player, week: int, league: LeagueConfig,
                table: Optional[Dict] = None,
                schedule: Optional[Dict] = None,
                force: bool = False) -> Dict:
    """{opponent, pa_rank, pa_grade, basis, evidence, ...} for one player.

    `player` is a models.Player (or anything with .name/.pos/.team). The
    OPPONENT comes from engine/weekly.fetch_schedule(week) - i.e. the real
    current-season schedule - while the GRADE comes from the PA table,
    which today is 2025. That split is the whole caveat: a true 2026 fact
    (who they play) joined to a 2025 prior (how that defense held up).

    Never raises for a normal absence. A bye, a position without a PA read
    (K, DEF), an unknown NFL team or an ungraded defense all come back with
    pa_grade=None and a `reason` that says which - silence, not a guess.
    """
    if table is None:
        table = pa_table(league, force=force)
    if schedule is None:
        schedule = weekly.fetch_schedule(week, force=force)

    pos = norm_pos(getattr(player, "pos", "") or "")
    team = norm_team(getattr(player, "team", "") or "")
    name = getattr(player, "name", "") or ""
    key = getattr(player, "key", None) or ("%s|%s" % (name_key(name), pos))

    out = {"player": name, "player_key": key, "pos": pos, "team": team,
           "week": int(week), "opponent": None, "home": None,
           "pa_per_game": None, "pa_rank": None, "pa_of": None,
           "pa_pctl": None, "pa_z": None, "pa_grade": None,
           "vote": None, "thin": None,
           "basis": table.get("basis", ""), "caveat": table.get("caveat", ""),
           "prior_only": bool(table.get("prior_only")),
           "evidence": "", "reason": ""}

    # Resolve the opponent BEFORE any bail-out. A kicker still has a real
    # week-1 opponent; reporting opponent=None for him would read as a bye
    # on every page that prints the field, which is a lie about the schedule
    # rather than an honest "no grade for this position".
    if not team:
        out["reason"] = "no NFL team on file for %s" % (name or "this player")
        out["evidence"] = out["reason"]
        return out

    game = (schedule or {}).get(team)
    if not game:
        out["reason"] = "%s is on bye in week %d" % (team, int(week))
        out["evidence"] = out["reason"]
        return out
    out["opponent"] = game.get("opponent")
    out["home"] = game.get("home")

    if pos not in (table.get("positions") or PA_POSITIONS):
        out["reason"] = ("no points-allowed read for %s - defenses are not "
                         "graded against this position" % (pos or "?"))
        out["evidence"] = out["reason"]
        return out

    cell = cell_for(pos, out["opponent"], table)
    if cell is None:
        out["reason"] = ("no %s points-allowed data for %s"
                         % (pos, out["opponent"]))
        out["evidence"] = out["reason"]
        return out

    out.update({"pa_per_game": cell["pa_per_game"], "pa_rank": cell["rank"],
                "pa_of": cell["of"], "pa_pctl": cell["pctl"],
                "pa_z": cell["z"], "pa_grade": cell["grade"],
                "thin": cell["thin"],
                "vote": VOTE_ON.get(cell["grade"])})
    out["evidence"] = evidence_for(cell, table, pos,
                                   table.get("scoring", ""), name)
    return out


def matchups_for_roster(players: Sequence, week: int, league: LeagueConfig,
                        table: Optional[Dict] = None,
                        schedule: Optional[Dict] = None,
                        force: bool = False) -> List[Dict]:
    """matchup_for over a roster, one table and one schedule fetch."""
    if table is None:
        table = pa_table(league, force=force)
    if schedule is None:
        schedule = weekly.fetch_schedule(week, force=force)
    return [matchup_for(p, week, league, table=table, schedule=schedule)
            for p in players]


# --- highlighting ----------------------------------------------------------

def _sort_key(m: Dict) -> Tuple:
    return (GRADE_ORDER.get(m.get("pa_grade") or "NEUTRAL", 2),
            -(m.get("pa_pctl") or 0.0))


def roster_extremes(matchups: Sequence[Dict], n: int = 1) -> Dict:
    """Best/worst graded matchups on one roster, softest and stingiest first.

    Only graded rows compete; byes, K/DEF and ungraded defenses are counted
    in `skipped` rather than silently dropped.
    """
    graded = [m for m in matchups if m.get("pa_grade")]
    ordered = sorted(graded, key=_sort_key)
    n = max(1, int(n))
    return {"best": ordered[:n],
            "worst": list(reversed(ordered[-n:])) if ordered else [],
            "graded": len(graded), "skipped": len(matchups) - len(graded)}


def leaguewide_extremes(table: Dict, week: int,
                        schedule: Optional[Dict] = None, n: int = 5,
                        positions: Sequence[str] = PA_POSITIONS,
                        force: bool = False) -> Dict:
    """Top/bottom N (offense, position) matchups in the whole NFL this week.

    One entry per team-position pair actually playing in `week`: "any RB
    facing NYJ this week draws the softest RB matchup on the board". This
    is what a page needs to say "the single best positional matchup on your
    roster is also the best one in football".
    """
    if schedule is None:
        schedule = weekly.fetch_schedule(week, force=force)
    entries = []
    for team, game in (schedule or {}).items():
        opp = game.get("opponent")
        for pos in positions:
            cell = cell_for(pos, opp, table)
            if cell is None:
                continue
            entries.append({
                "offense": team, "opponent": opp, "pos": pos,
                "week": int(week), "home": game.get("home"),
                "pa_per_game": cell["pa_per_game"], "pa_rank": cell["rank"],
                "pa_of": cell["of"], "pa_pctl": cell["pctl"],
                "pa_z": cell["z"], "pa_grade": cell["grade"],
                "thin": cell["thin"], "vote": VOTE_ON.get(cell["grade"]),
                "basis": table.get("basis", ""),
                "prior_only": bool(table.get("prior_only")),
                "evidence": evidence_for(cell, table, pos,
                                         table.get("scoring", ""))})
    ordered = sorted(entries, key=_sort_key)
    n = max(1, int(n))
    return {"best": ordered[:n],
            "worst": list(reversed(ordered[-n:])) if ordered else [],
            "count": len(ordered), "basis": table.get("basis", ""),
            "caveat": table.get("caveat", "")}


# --- as a weighted source --------------------------------------------------

def source_default() -> Dict:
    """A fresh copy of the registry row - disabled, with a weight suggestion."""
    return dict(SOURCE_DEFAULT)


def register(path: Optional[str] = None, sources_mod=None) -> Dict:
    """Add the matchup source to the registry if absent. Returns the row.

    ALWAYS added disabled. An existing row is returned untouched - never
    re-enabled, never re-weighted: once the user has an opinion about this
    source, the engine does not get to overwrite it.
    """
    if sources_mod is None:
        from engine import sources as sources_mod
    registry = sources_mod.load_sources(path)
    for s in registry:
        if s.get("id") == SOURCE_ID:
            return s
    row = source_default()
    registry.append(row)
    sources_mod.save_sources(registry, path)
    return row


def startable_keys(league: LeagueConfig, players: Sequence[Player],
                   cushion: int = 1) -> Set[str]:
    """Player keys the matchup source is allowed to vote on.

    The best legal lineup (engine/grader.best_lineup - not reimplemented
    here) PLUS `cushion` next-best bench players at each starting-eligible
    position. The cushion is the point: a SMASH grade earns its keep exactly
    at the starter/bench boundary, where the projection gap is small enough
    for a matchup to be the tiebreaker. Players with no projection cannot
    make a lineup and are excluded.
    """
    from engine.grader import best_lineup
    pool = [p for p in players if p is not None]
    if not pool:
        return set()
    rows, _, _ = best_lineup(league, pool)
    keys = set(p.key for _, p in rows if p is not None)

    eligible = set()
    for pos, count in league.starter_counts().items():
        if count > 0:
            eligible.add(pos)
    cushion = max(0, int(cushion))
    if cushion:
        for pos in eligible:
            bench = sorted((p for p in pool
                            if p.pos == pos and p.key not in keys),
                           key=lambda p: -(float(p.proj_points or 0.0)))
            for p in bench[:cushion]:
                keys.add(p.key)
    return keys


def feed_votes(universe: Dict[str, Dict], week: int, league: LeagueConfig,
               table: Optional[Dict] = None,
               schedule: Optional[Dict] = None,
               startable: Optional[Iterable[str]] = None,
               players_by_key: Optional[Dict[str, Player]] = None,
               force: bool = False) -> Dict[str, str]:
    """{player_key: "start"|"sit"} - engine/consensus's feed_votes shape.

    START on SMASH, SIT on AVOID, ABSTAIN everywhere else (see the module
    docstring for why the neutral middle is three grades wide). `startable`
    narrows the electorate to players who might actually be started; None
    means every key in the universe is eligible, which is what a
    roster-sized universe already is.

    The team a player plays for comes from `players_by_key` when given
    (models.Player carries .team); a universe entry may also carry "team".
    A player whose team we cannot resolve abstains rather than guessing.
    """
    if table is None:
        table = pa_table(league, force=force)
    if schedule is None:
        schedule = weekly.fetch_schedule(week, force=force)
    allowed = set(startable) if startable is not None else None

    out: Dict[str, str] = {}
    for key, info in (universe or {}).items():
        if allowed is not None and key not in allowed:
            continue
        player = (players_by_key or {}).get(key)
        if player is None:
            name = (info or {}).get("name") or key.partition("|")[0]
            pos = (info or {}).get("pos") or key.partition("|")[2]
            team = (info or {}).get("team") or ""
            player = Player(rank=0, name=name, pos=pos, team=team)
        m = matchup_for(player, week, league, table=table, schedule=schedule)
        if m.get("vote"):
            out[key] = m["vote"]
    return out


def consensus_gap(cons: Dict, votes: Optional[Dict[str, str]] = None) -> str:
    """'' when all is well, else a sentence naming the silent-abstention bug.

    The matchup source is enabled in the registry but engine/consensus's
    feed loop does not know its handle yet, so it would appear as a voice
    that never speaks. Pages should print this rather than showing a source
    with no votes and no explanation.
    """
    sources = (cons or {}).get("sources") or []
    row = next((s for s in sources if s.get("id") == SOURCE_ID), None)
    if row is None:
        return ""
    seen = any(v.get("source") == SOURCE_ID
               for r in (cons.get("rows") or []) for v in (r.get("votes") or []))
    if seen:
        return ""
    n = len(votes or {})
    return ("source %r is enabled (weight %s) but cast no votes: "
            "engine/consensus.build_consensus does not map its handle yet. "
            "%s Call matchups.augment_consensus(cons, votes) to fold them in."
            % (SOURCE_ID, row.get("weight"),
               "It has %d vote(s) to cast this week." % n if n
               else "It has no votes to cast this week anyway."))


def augment_consensus(cons: Dict, votes: Dict[str, str],
                      source: Optional[Dict] = None,
                      engine_id: str = "engine") -> Dict:
    """Fold matchup votes into a built consensus result and re-weigh.

    Returns a NEW result dict; `cons` is not mutated. Each affected row gets
    the matchup vote appended and its score / pct / verdict / agreement
    recomputed through engine/consensus's OWN pure helpers, so the weighing
    rule stays defined in exactly one place.

    The top-weighted bookkeeping below deliberately MIRRORS build_rows
    rather than calling it: build_rows takes raw creator calls, which a
    built result no longer carries (quotes and rank details would be lost
    round-tripping them back out of the votes). If consensus.py ever maps
    the "matchup" handle itself, delete this function and use that path -
    it is the better one.
    """
    from engine import consensus as cons_mod

    src = dict(source or source_default())
    src.setdefault("enabled", True)
    try:
        weight = max(0.0, float(src.get("weight") or 0))
    except (TypeError, ValueError):
        weight = 0.0

    out = dict(cons or {})
    sources = list(out.get("sources") or [])
    if not any(s.get("id") == SOURCE_ID for s in sources):
        sources.append(src)
    sources = sorted(sources, key=lambda s: -cons_mod._w(s))
    out["sources"] = sources
    top_id = sources[0].get("id") if sources else None

    new_rows = []
    added = 0
    for row in out.get("rows") or []:
        row = dict(row)
        row["votes"] = [dict(v) for v in (row.get("votes") or [])]
        verdict = votes.get(row.get("player_key"))
        if verdict in cons_mod.VERDICT_VALUE and not any(
                v["source"] == SOURCE_ID for v in row["votes"]):
            row["votes"].append({"source": SOURCE_ID,
                                 "name": src.get("name") or SOURCE_ID,
                                 "weight": weight, "verdict": verdict})
            added += 1
        row["votes"].sort(key=lambda v: -float(v.get("weight") or 0))

        score, pct = cons_mod.weigh(row["votes"])
        agree, dissenter = cons_mod.agreement(row["votes"], score)
        wsign = cons_mod._sign(score)
        ev = next((v for v in row["votes"] if v["source"] == engine_id), None)
        esign = cons_mod._sign(cons_mod.VERDICT_VALUE[ev["verdict"]]) if ev else 0
        top_vote = next((v for v in row["votes"] if v["source"] == top_id), None)
        reasons = []
        top_disagrees = False
        if top_vote is not None:
            tsign = cons_mod._sign(cons_mod.VERDICT_VALUE[top_vote["verdict"]])
            if wsign != 0 and tsign != wsign:
                top_disagrees = True
                reasons.append("the weighted verdict")
            if ev is not None and top_vote["source"] != engine_id \
                    and esign != 0 and tsign != esign:
                top_disagrees = True
                reasons.append("the engine")
        row.update({
            "score": round(score, 3), "pct": pct,
            "verdict": cons_mod.verdict_of(score),
            "agreement": agree, "dissenter": dissenter,
            "engine": ev["verdict"] if ev else None,
            "vs_engine": bool(ev) and esign != 0 and wsign != 0
            and esign != wsign,
            "top_source": top_id,
            "top_vote": top_vote["verdict"] if top_vote else None,
            "top_disagrees": top_disagrees,
            "top_note": ("top-weighted %s says %s - disagrees with %s"
                         % (top_vote.get("name") or top_id,
                            top_vote["verdict"], " and ".join(reasons)))
            if top_disagrees else "",
        })
        new_rows.append(row)
    out["rows"] = new_rows
    out["notes"] = list(out.get("notes") or []) + [
        "matchup source folded in: %d row(s) got a %s vote (start on SMASH, "
        "sit on AVOID, abstain otherwise)" % (added, SOURCE_ID)]
    return out


# --- leaderboard / CLI -----------------------------------------------------

def leaderboard(table: Dict, pos: str, top: int = 0) -> List[Dict]:
    """Graded cells for one position, softest first. top=0 means all."""
    block = (table.get("by_pos") or {}).get(norm_pos(pos or ""))
    if not block:
        return []
    cells = sorted((block.get("defenses") or {}).values(),
                   key=lambda c: c["rank"])
    return cells[:top] if top else cells


def format_leaderboard(table: Dict, pos: str, top: int = 0) -> str:
    lines = ["%s - points allowed per game (%s scoring). Basis: %s"
             % (pos, (table.get("scoring") or "?").upper(),
                table.get("basis", "?"))]
    for c in leaderboard(table, pos, top):
        lines.append("  %2d. %-4s %6.2f  %-7s  pctl %5.1f  z %+5.2f%s"
                     % (c["rank"], c["defense"], c["pa_per_game"], c["grade"],
                        c["pctl"], c["z"], "  THIN" if c["thin"] else ""))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Positional matchup engine")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--top", type=int, default=0,
                    help="limit each positional leaderboard (0 = all 32)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "%s.yaml" % args.league))
    table = pa_table(league, force=args.force, quiet=False)
    print()
    if table.get("caveat"):
        print("CAVEAT: %s\n" % table["caveat"])
    for pos in table.get("positions") or PA_POSITIONS:
        print(format_leaderboard(table, pos, args.top))
        print()

    from engine import lineup as lineup_mod
    roster = lineup_mod.load_roster(league.id)
    if not roster:
        return 0
    from engine.ingest import Matcher
    from engine.models import load_players
    pool = load_players(os.path.join(HERE, league.rankings_csv))
    matcher = Matcher(pool)
    merged = weekly.fetch_weekly_projections(args.week,
                                             scoring=league.scoring_label(),
                                             quiet=True)
    b = lineup_mod.build(league, roster["players"], args.week, merged,
                         matcher=matcher)
    starters = [p for _, p in b["rows"] if p is not None]
    ms = matchups_for_roster(starters, args.week, league, table=table)
    print("WEEK %d STARTERS - %s" % (args.week, league.name))
    for m in ms:
        print("  %-22s %-3s vs %-4s %-8s %s"
              % (m["player"], m["pos"], m["opponent"] or "BYE",
                 m["pa_grade"] or "-", m["evidence"]))
    ex = roster_extremes(ms)
    if ex["best"]:
        print("\n  BEST : %s (%s)" % (ex["best"][0]["player"],
                                      ex["best"][0]["evidence"]))
    if ex["worst"]:
        print("  WORST: %s (%s)" % (ex["worst"][0]["player"],
                                    ex["worst"][0]["evidence"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
