"""Durability flag: how much of the recent past a player was actually on the field.

This is a TRANSPARENT AVAILABILITY FLAG, explicitly NOT injury prediction.
It answers one backward-looking question from nflverse games-played data:
"across the last few seasons, how many games did this player suit up for?"
It cannot see torn labrums that healed clean, suspensions vs. surgeries,
healthy scratches, depth-chart burial, or late-season rest - Rashee Rice's
2025 games lost to suspension count exactly like games lost to his 2024 knee.
That is deliberate: for draft purposes an absent player scores zero either
way, and the detail string puts the raw numbers on screen so the user judges
the WHY themselves.

Semantics mirror engine/exposure.py: POSITIVE-ONLY. A flag means we have
seasons of games data and this is what it says. A missing entry means NO
INFORMATION (2026 rookies, name misses across sources) - never "durable" and
never "fragile". Callers must not render anything for absent players.

The classic rookie bug, handled here: a player absent from a season's data
was (as far as we know) not in the league that season, so that season is NO
INFO and drops out of the math - a 2025 rookie is judged on 2025 alone, not
punished for 2023-24 "zeros" he never could have played. BUT a season absent
AFTER the player's first appearance in the window is a real lost season and
counts as 0 games played - that is the guy who blew out a knee in August and
vanished from the stat file, precisely who this flag exists to surface.
"""

from typing import Dict, Iterable, Optional, Tuple

from .nflverse import games_played

# The lookback window. Three seasons is enough to see a pattern without
# punishing anyone for ancient history.
SEASONS = (2023, 2024, 2025)

# NFL regular season length for every season in the window above.
SEASON_GAMES = 17

# Recency weights by position in the window: oldest season 1.0, each newer
# season +0.25 (so 2023/24/25 weigh 1.0/1.25/1.5). Judgment call: last
# season should matter more than two ago - a healthy 2025 partially redeems
# a lost 2024 (McCaffrey) - but not so much that one good year erases a
# pattern. Linear steps keep the math explainable at the draft table.
WEIGHT_STEP = 0.25

# Flag thresholds on the weighted availability fraction. Judgment calls:
#   GREEN  >= 0.90  missed roughly a game and a half per season or less -
#                   the "pencil him in" tier (Henry, Bijan, ASB).
#   RED    <  0.72  missing ~5+ games a season on a weighted basis - a lost
#                   season inside the window lands here (Rice, Godwin).
#   YELLOW between  real missed time, not a pattern of lost years (Tua,
#                   CeeDee Lamb, and McCaffrey-after-a-clean-2025).
GREEN_MIN = 0.90
RED_BELOW = 0.72

_GAMES_CACHE = {}  # seasons tuple -> games_played() result, per session


def _clamp(games) -> int:
    """Games as an int pinned to [0, SEASON_GAMES] - data glitches stay sane."""
    try:
        g = int(games)
    except (TypeError, ValueError):
        return 0
    return max(0, min(SEASON_GAMES, g))


def _counted_seasons(seasons_map: Dict[int, int],
                     seasons: Iterable[int]) -> list:
    """Seasons that count for this player: first appearance through the end.

    Seasons before the player's first row are no-info (not in the league) and
    drop out; seasons after it with no row count as played-zero lost years.
    Empty when the player has no data in the window at all.
    """
    present = [s for s in seasons if s in seasons_map]
    if not present:
        return []
    first = min(present)
    return [s for s in sorted(seasons) if s >= first]


def availability(seasons_map: Dict[int, int],
                 seasons: Iterable[int] = SEASONS) -> Optional[float]:
    """Weighted fraction of possible games played, or None for no data.

    seasons_map is one player's {season: games} from nflverse.games_played.
    Weights are positional within the full window (newest season heaviest)
    so a rookie's lone season is judged at full weight, same scale as a vet.
    """
    ordered = sorted(seasons)
    counted = _counted_seasons(seasons_map, ordered)
    if not counted:
        return None
    played = 0.0
    possible = 0.0
    for s in counted:
        w = 1.0 + WEIGHT_STEP * ordered.index(s)
        played += w * _clamp(seasons_map.get(s, 0))
        possible += w * SEASON_GAMES
    return played / possible if possible else None


def _detail(seasons_map: Dict[int, int], seasons: Iterable[int]) -> str:
    """Raw unweighted evidence string, e.g. '31/51 gms 23-25' or '17/17 gms 25'.

    Always the plain counts, never the weighted score - the user should see
    the actual games behind the flag, not our arithmetic.
    """
    counted = _counted_seasons(seasons_map, sorted(seasons))
    played = sum(_clamp(seasons_map.get(s, 0)) for s in counted)
    possible = SEASON_GAMES * len(counted)
    if len(counted) == 1:
        span = "%02d" % (counted[0] % 100)
    else:
        span = "%02d-%02d" % (counted[0] % 100, counted[-1] % 100)
    return "%d/%d gms %s" % (played, possible, span)


def _flag(avail: float) -> str:
    if avail >= GREEN_MIN:
        return "GREEN"
    if avail < RED_BELOW:
        return "RED"
    return "YELLOW"


def _games(seasons: Tuple[int, ...]) -> Dict[str, Dict[int, int]]:
    key = tuple(seasons)
    if key not in _GAMES_CACHE:
        _GAMES_CACHE[key] = games_played(key)
    return _GAMES_CACHE[key]


def score(name_key: str,
          games: Optional[Dict[str, Dict[int, int]]] = None,
          seasons: Tuple[int, ...] = SEASONS
          ) -> Optional[Tuple[str, str]]:
    """(flag, detail) for one normalized name key, or None for no data.

    name_key is a models.norm_name key (Player.nkey). Pass `games` to score
    against a synthetic dict (tests); by default the real nflverse data is
    fetched once and cached for the session. None means UNKNOWN - fewer than
    one season of data in the window - and must never be rendered as either
    durable or fragile.
    """
    if games is None:
        games = _games(seasons)
    seasons_map = games.get(name_key)
    if not seasons_map:
        return None
    avail = availability(seasons_map, seasons)
    if avail is None:
        return None
    return _flag(avail), _detail(seasons_map, seasons)


def load(matcher,
         games: Optional[Dict[str, Dict[int, int]]] = None,
         seasons: Tuple[int, ...] = SEASONS) -> Dict[str, Tuple[str, str]]:
    """{player_key: (flag, detail)} for every pool player with enough data.

    Keys are Player.key ("name|POS") so draft-side callers can join on the
    same key exposure flags use. Players with no games data in the window -
    2026 rookies above all - are simply ABSENT, not flagged: absence means
    no information (see module docstring). Network/cache errors from the
    underlying fetch propagate; callers that render mid-draft should wrap
    this like recommend.injury_badges() wraps its fetch.
    """
    if games is None:
        games = _games(seasons)
    out = {}
    for p in matcher.players:
        got = score(p.nkey, games=games, seasons=seasons)
        if got is not None:
            out[p.key] = got
    return out
