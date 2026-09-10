"""Fetch nflverse community data: ECR ranks, expected fantasy points, games played.

Three datasets, all public CSV assets on GitHub - no auth, stdlib urllib only:

* ECR - DynastyProcess republishes FantasyPros Expert Consensus Rankings to
  dynastyprocess/data as files/db_fpecr_latest.csv (the file behind
  nflreadr::load_ff_rankings("latest")). We keep the redraft-overall page,
  which is the current preseason/weekly redraft consensus.
* Expected fantasy points - the ffverse/ffopportunity release tagged
  "latest-data", asset ep_weekly_<season>.csv (nflreadr::load_ff_opportunity).
* Games played - the nflverse/nflverse-data release tagged "stats_player",
  asset stats_player_reg_<season>.csv. The regular-season aggregate carries a
  per-player `games` column, so we can skip the ~8MB weekly files entirely.
* Per-week player stats - the SAME "stats_player" release, asset
  stats_player_week_<season>.csv (~8.6MB for 2025; asset list read live from
  the GitHub releases API 2026-09-05, not guessed). This is the only nflverse
  file that carries `opponent_team` alongside per-week raw box-score columns,
  which is what points-allowed-to-position needs: to score a defense in an
  ARBITRARY league's scoring you must have the raw stats, not the pre-baked
  `fantasy_points`/`fantasy_points_ppr` columns (those are standard and full
  PPR only, and would silently misprice a half-PPR or 6-pt-passing league).
  engine/matchups.py is its consumer.

Asset-naming notes vs. the nflverse docs' shorthand: "ff_rankings" is not a
nflverse-data release - it ships as a raw file in the dynastyprocess/data
repo - and "ff_opportunity" ships from the ffverse/ffopportunity repo's own
releases, not from nflverse-data. "player_stats" was superseded by the
"stats_player" release tag (same repo, new schema with a `games` column).

Downloads are MB-scale, so each lands in data/cache with a 24h freshness
window and the same stale-cache-offline fallback engine/adp.py uses.
All name keys go through models.norm_name so they line up with Player.nkey.
norm_name folds accents to ASCII (the Piñeiro bug: nflverse spells names
plain, rankings may carry the accent), so both sides land on one key.
"""

import csv
import os
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .models import norm_name

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ECR_URL = ("https://github.com/dynastyprocess/data/raw/master/files/"
           "db_fpecr_latest.csv")
XFP_URL = ("https://github.com/ffverse/ffopportunity/releases/download/"
           "latest-data/ep_weekly_%d.csv")
GAMES_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
             "stats_player/stats_player_reg_%d.csv")
WEEK_STATS_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
                  "stats_player/stats_player_week_%d.csv")


def _f(val) -> Optional[float]:
    """Float or None - nflverse CSVs use 'NA' and '' for missing values."""
    s = (str(val) if val is not None else "").strip()
    if not s or s.upper() == "NA":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_csv(url: str, cache_name: str, must_have: str,
               max_age_hours: float = 24.0, force: bool = False) -> List[Dict]:
    """Download a CSV to data/cache and return its rows as dicts.

    Fresh cache is served as-is; a failed download falls back to a stale
    cache; no cache and no network is a hard error. `must_have` is a header
    column that proves we got the real dataset and not an error page.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_name)

    def read_rows():
        with open(path, "r", newline="") as fh:
            return list(csv.DictReader(fh))

    if os.path.exists(path) and not force:
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            return read_rows()

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        header = body.split("\n", 1)[0]
        if must_have not in header:
            raise ValueError("unexpected header for %s: %.120s" % (cache_name, header))
        # Write via a temp file so a mid-download failure can't corrupt the cache.
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as fh:
            fh.write(body)
        os.replace(tmp, path)
        return read_rows()
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            return read_rows()
        raise RuntimeError("Could not fetch %s and no cache exists: %s" % (url, exc))


def fetch_ecr(force: bool = False) -> Dict[str, Dict[str, float]]:
    """Return {normalized_name: {"ecr": rank, "sd": stdev}} for redraft.

    Uses the redraft-overall page (QB/RB/WR/TE plus K and DST), the current
    FantasyPros consensus for this preseason/week. On the rare duplicate
    name the better (lower) ECR wins. Missing sd comes back as 0.0.
    """
    rows = _fetch_csv(ECR_URL, "nflverse-ecr.csv", "page_type", force=force)
    out = {}
    for r in rows:
        if r.get("page_type") != "redraft-overall":
            continue
        ecr = _f(r.get("ecr"))
        if ecr is None:
            continue
        key = norm_name(r.get("player", ""))
        if not key:
            continue
        if key not in out or ecr < out[key]["ecr"]:
            out[key] = {"ecr": ecr, "sd": _f(r.get("sd")) or 0.0}
    return out


def fetch_xfp(season: int, force: bool = False) -> Dict[str, List[Dict]]:
    """Return {normalized_name: [{"week": int, "xfp": float, "actual": float}]}.

    Expected vs. actual fantasy points per week from ffopportunity. Weeks
    are sorted ascending; a name shared by two players merges their weeks
    (the file is offense-only, so real collisions are rare).
    """
    rows = _fetch_csv(XFP_URL % season, "nflverse-xfp-%d.csv" % season,
                      "total_fantasy_points_exp", force=force)
    out = {}
    for r in rows:
        key = norm_name(r.get("full_name", ""))
        week = _f(r.get("week"))
        xfp = _f(r.get("total_fantasy_points_exp"))
        if not key or week is None or xfp is None:
            continue
        out.setdefault(key, []).append({
            "week": int(week),
            "xfp": xfp,
            "actual": _f(r.get("total_fantasy_points")) or 0.0,
        })
    for weeks in out.values():
        weeks.sort(key=lambda w: w["week"])
    return out


def games_played(seasons: Tuple[int, ...] = (2023, 2024, 2025)
                 ) -> Dict[str, Dict[int, int]]:
    """Return {normalized_name: {season: games}} for a durability read.

    Regular-season games only. A season a player has no row for is simply
    absent - rookies and missed years look the same, so let the caller
    decide what absence means. Duplicate names keep the larger count.
    """
    out = {}
    for season in seasons:
        rows = _fetch_csv(GAMES_URL % season, "nflverse-games-%d.csv" % season,
                          "player_display_name")
        for r in rows:
            key = norm_name(r.get("player_display_name", ""))
            games = _f(r.get("games"))
            if not key or games is None:
                continue
            seasons_map = out.setdefault(key, {})
            seasons_map[season] = max(seasons_map.get(season, 0), int(games))
    return out


def fetch_weekly_stats(season: int, season_type: str = "REG",
                       force: bool = False,
                       max_age_hours: float = 168.0) -> List[Dict]:
    """Raw per-week player box scores for one season: a list of row dicts.

    The stats_player release's weekly asset. Rows are returned verbatim
    (strings, nflverse's own column names) so the caller owns the scoring -
    engine/matchups.py applies THIS league's LeagueConfig.scoring to the raw
    columns rather than trusting the file's baked fantasy_points columns.
    Every row carries `week`, `team`, `opponent_team`, `position` and
    `game_id`, which is what a points-allowed-to-position table is built on.

    season_type filters the `season_type` column ("REG", "POST", or "" for
    everything). Default REG: playoff football is a different population
    (better teams, different rest) and mixing it into a per-game rate would
    quietly flatter defenses that made January.

    The default freshness window is a WEEK, not the 24h the other fetchers
    use: a completed season's file never changes, and the in-season file is
    only rewritten after each week's games. Pass max_age_hours=24 (or
    force=True) when pulling the live season mid-week.
    """
    rows = _fetch_csv(WEEK_STATS_URL % season, "nflverse-weekstats-%d.csv"
                      % season, "opponent_team", max_age_hours=max_age_hours,
                      force=force)
    want = (season_type or "").strip().upper()
    if not want:
        return rows
    return [r for r in rows
            if (r.get("season_type") or "").strip().upper() == want]


def apply_ecr_to_csv(csv_path: str) -> int:
    """Write 'ecr' and 'ecr_sd' columns into a rankings CSV. Returns matches.

    Matches rows to fetch_ecr() by normalized name. Existing ecr/ecr_sd
    columns are refreshed in place; otherwise both are appended, which the
    tolerant loader in models.load_players simply ignores. Unmatched rows
    (retirees, deep sleepers, DEF naming differences) get blank cells.
    """
    ecr = fetch_ecr()

    with open(csv_path, "r", newline="") as fh:
        rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("Rankings CSV %s is empty" % csv_path)

    header = [c.strip().lower() for c in rows[0]]
    try:
        name_idx = header.index("name")
    except ValueError:
        raise ValueError("Rankings CSV %s has no 'name' column" % csv_path)
    for col in ("ecr", "ecr_sd"):
        if col not in header:
            header.append(col)
            rows[0].append(col)
    ecr_idx, sd_idx = header.index("ecr"), header.index("ecr_sd")

    matched = 0
    for row in rows[1:]:
        while len(row) < len(header):
            row.append("")
        hit = ecr.get(norm_name(row[name_idx])) if name_idx < len(row) else None
        if hit:
            row[ecr_idx] = "%g" % hit["ecr"]
            row[sd_idx] = "%g" % hit["sd"]
            matched += 1
        else:
            row[ecr_idx], row[sd_idx] = "", ""

    with open(csv_path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    return matched
