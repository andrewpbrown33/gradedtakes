"""Fetch season/weekly projections and market data from ESPN and Sleeper.

ESPN's kona_player_info view (unauthenticated) is the primary source; Sleeper's
public projections API is the fallback and cross-check. Both are cached on disk
under data/cache/ with graceful offline fallback, same pattern as engine/adp.py.
Runs on the standard library only.

ESPN scoring formats (leaguedefaults id): 1 = standard, 3 = PPR. Ids 2 and 4
return 404 for 2026 - there is no working half-PPR default, so half-PPR season
totals are derived as the average of the PPR and standard fetches (exact, since
the two differ only by 1.0 vs 0.0 points per reception over identical
underlying stat projections).
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

try:
    from engine.models import norm_name
except ImportError:  # run directly as `python engine/projections.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.models import norm_name

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SEASON = 2026

ESPN_URL = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/%d"
            "/segments/0/leaguedefaults/%d?view=kona_player_info")
ESPN_FILTER = {"players": {"limit": 600,
                           "sortPercOwned": {"sortAsc": False, "sortPriority": 1}}}
# leaguedefaults id -> scoring label. 2 and 4 are 404 as of Aug 2026 (verified).
ESPN_FORMATS = {1: "std", 3: "ppr"}

SLEEPER_URL = ("https://api.sleeper.app/projections/nfl/%d?season_type=regular"
               "&position[]=QB&position[]=RB&position[]=WR&position[]=TE"
               "&position[]=K&position[]=DEF")
SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"

ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
ESPN_PRO_TEAMS = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
    22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS",
    29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}
# Variant team abbreviations seen across sources, mapped to rankings.csv's set.
TEAM_ALIASES = {"WSH": "WAS", "JAC": "JAX", "OAK": "LV", "SD": "LAC",
                "STL": "LAR", "LA": "LAR"}


def norm_team(team: str) -> str:
    t = (team or "").strip().upper()
    return TEAM_ALIASES.get(t, t)


def name_key(name: str) -> str:
    """Alias for models.norm_name, the one shared normalizer.

    norm_name folds accents itself now ('Piñeiro' == 'Pineiro'), so every
    module keys names identically; this alias survives for its call sites.
    """
    return norm_name(name)


def _fetch_json(url: str, cache_file: str, headers: Dict[str, str],
                force: bool = False, max_age_hours: float = 6.0,
                quiet: bool = False):
    """Shared fetch: fresh cache -> network -> stale cache -> error."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_file)

    if not force and os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            with open(path, "r") as fh:
                return json.load(fh)

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
        if not payload:
            raise ValueError("empty payload")
        with open(path, "w") as fh:
            json.dump(payload, fh)
        return payload
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            if not quiet:
                print("  projections fetch failed (%s) - using cached %s"
                      % (type(exc).__name__, cache_file))
            with open(path, "r") as fh:
                return json.load(fh)
        raise RuntimeError("Could not fetch %s and no cache exists: %s"
                           % (cache_file, exc))


# --- ESPN -------------------------------------------------------------------

def fetch_espn(format_id: int = 3, force: bool = False,
               quiet: bool = False) -> Dict[str, Dict]:
    """ESPN kona projections for one scoring format, keyed by normalized name.

    Each record: name, pos, team, proj {scoring: season points}, weekly
    {week: points, 1-18}, actual_2025, adp {espn: pick}, pct_owned, source.
    """
    if format_id not in ESPN_FORMATS:
        raise ValueError("ESPN leaguedefaults id must be one of %s (2/4 are 404)"
                         % sorted(ESPN_FORMATS))
    scoring = ESPN_FORMATS[format_id]
    payload = _fetch_json(
        ESPN_URL % (SEASON, format_id),
        "espn-kona-%s-%d.json" % (scoring, SEASON),
        {"User-Agent": UA, "Accept": "application/json",
         "X-Fantasy-Filter": json.dumps(ESPN_FILTER)},
        force=force, quiet=quiet)

    out = {}
    for entry in payload.get("players", []):
        pl = entry.get("player") or {}
        name = pl.get("fullName", "")
        pos = ESPN_POS.get(pl.get("defaultPositionId"))
        if not name or not pos:
            continue

        proj = None
        actual_2025 = None
        weekly = {}
        for st in pl.get("stats", []):
            src, split = st.get("statSourceId"), st.get("statSplitTypeId")
            season, period = st.get("seasonId"), st.get("scoringPeriodId")
            total = st.get("appliedTotal")
            if season == SEASON and src == 1:
                if period == 0 and split == 0:
                    proj = total
                elif split == 1 and period and 1 <= period <= 18:
                    weekly[period] = round(total or 0.0, 2)
            elif season == SEASON - 1 and src == 0 and period == 0 and split == 0:
                actual_2025 = total

        own = pl.get("ownership") or {}
        rec = {
            "name": name,
            "pos": pos,
            "team": norm_team(ESPN_PRO_TEAMS.get(pl.get("proTeamId"), "")),
            "proj": {scoring: proj},
            "weekly": weekly,
            "actual_2025": actual_2025,
            "adp": {"espn": own.get("averageDraftPosition")},
            "pct_owned": own.get("percentOwned"),
            "source": "espn",
        }
        key = name_key(name)
        old = out.get(key)
        if old is None or (proj or 0) > (old["proj"].get(scoring) or 0):
            out[key] = rec

    if not quiet:
        print("  ESPN: %d players (%s, season %d)" % (len(out), scoring, SEASON))
    return out


# --- Sleeper ----------------------------------------------------------------

def fetch_sleeper(force: bool = False, quiet: bool = False) -> Dict[str, Dict]:
    """Sleeper season projections, keyed by normalized name (same shape as ESPN).

    proj carries all three scorings; adp carries Sleeper's per-format ADPs.
    Sleeper defenses are named like 'Seattle Seahawks' - match those by team.
    """
    payload = _fetch_json(
        SLEEPER_URL % SEASON, "sleeper-proj-%d.json" % SEASON,
        {"User-Agent": UA, "Accept": "application/json"},
        force=force, quiet=quiet)

    out = {}
    for entry in payload:
        pl = entry.get("player") or {}
        stats = entry.get("stats") or {}
        pos = (pl.get("position") or "").upper()
        pos = {"DST": "DEF"}.get(pos, pos)
        name = ("%s %s" % (pl.get("first_name", ""), pl.get("last_name", ""))).strip()
        proj = {"ppr": stats.get("pts_ppr"), "half": stats.get("pts_half_ppr"),
                "std": stats.get("pts_std")}
        if not name or not pos or all(v is None for v in proj.values()):
            continue
        rec = {
            "name": name,
            "pos": pos,
            "team": norm_team(entry.get("team") or pl.get("team") or ""),
            "proj": proj,
            "weekly": {},
            "actual_2025": None,
            "adp": {"ppr": stats.get("adp_ppr"), "half": stats.get("adp_half_ppr"),
                    "std": stats.get("adp_std"), "2qb": stats.get("adp_2qb")},
            "pct_owned": None,
            "source": "sleeper",
        }
        key = name_key(name)
        old = out.get(key)
        if old is None or (proj.get("ppr") or 0) > (old["proj"].get("ppr") or 0):
            out[key] = rec

    if not quiet:
        print("  Sleeper: %d players (season %d)" % (len(out), SEASON))
    return out


# --- injuries ---------------------------------------------------------------

# Sleeper injury_status -> the compact badge the war room renders. Statuses
# outside this map fall back to their first four letters, uppercased.
INJURY_BADGES = {"questionable": "Q", "doubtful": "D", "out": "O", "ir": "IR",
                 "pup": "PUP", "sus": "SUS", "cov": "COV", "dnr": "IR",
                 "holdout": "HOLD"}


def injury_badge(status: str) -> str:
    """Compact badge for a Sleeper injury_status ('' for no status)."""
    s = (status or "").strip().lower()
    if not s:
        return ""
    return INJURY_BADGES.get(s, s[:4].upper())


def fetch_injury_status(force: bool = False, quiet: bool = False) -> Dict[str, str]:
    """Sleeper injury reports: {normalized_name: injury_status}.

    Built from Sleeper's full players dump (the only public per-player injury
    feed) - ~5MB, so it lives in the 12h cache window rather than the usual 6.
    POSITIVE-ONLY: a name present here has a filed report (Questionable, Out,
    IR, Holdout, ...); a name absent has no report, which is NOT the same as
    'healthy' - the dump simply carries a null status for most players.
    Duplicate names keep the more fantasy-relevant player (lower search_rank),
    so a retired journeyman's stale IR tag cannot shadow an active starter.
    """
    payload = _fetch_json(
        SLEEPER_PLAYERS_URL, "sleeper-players.json",
        {"User-Agent": UA, "Accept": "application/json"},
        force=force, max_age_hours=12.0, quiet=quiet)

    out, best_rank = {}, {}
    for pl in payload.values():
        if not isinstance(pl, dict):
            continue
        name = ("%s %s" % (pl.get("first_name") or "",
                           pl.get("last_name") or "")).strip()
        status = (pl.get("injury_status") or "").strip()
        if not name:
            continue
        key = name_key(name)
        rank = pl.get("search_rank") or 9999999
        if key in best_rank and rank >= best_rank[key]:
            continue
        best_rank[key] = rank
        if status:
            out[key] = status
        else:
            # The more relevant same-name player is healthy - drop any badge
            # a less relevant namesake left behind.
            out.pop(key, None)

    if not quiet:
        print("  Sleeper injuries: %d players with a filed status" % len(out))
    return out


# --- CSV fill ---------------------------------------------------------------

def _espn_for_scoring(scoring: str, force: bool = False,
                      quiet: bool = False) -> Dict[str, Dict]:
    """ESPN records with proj[scoring] populated; half = avg of ppr and std."""
    if scoring == "half":
        ppr = fetch_espn(3, force=force, quiet=quiet)
        std = fetch_espn(1, force=force, quiet=quiet)
        for key, rec in ppr.items():
            p = rec["proj"].get("ppr")
            s = std.get(key, {}).get("proj", {}).get("std")
            rec["proj"]["half"] = (p + s) / 2.0 if p is not None and s is not None else p
        return ppr
    return fetch_espn(3 if scoring == "ppr" else 1, force=force, quiet=quiet)


def _def_index(records: Dict[str, Dict]) -> Dict[str, Dict]:
    """Team abbrev -> record, for defenses (source names never match CSVs)."""
    return dict((r["team"], r) for r in records.values()
                if r["pos"] == "DEF" and r["team"])


def _lookup(row_name: str, row_pos: str, row_team: str, scoring: str,
            records: Dict[str, Dict], defs: Dict[str, Dict]) -> Optional[float]:
    """Season points for a CSV row from one source, or None."""
    if row_pos == "DEF":
        rec = defs.get(norm_team(row_team))
    else:
        rec = records.get(name_key(row_name))
        if rec is not None and rec["pos"] != row_pos:
            rec = None
    return rec["proj"].get(scoring) if rec else None


def apply_to_csv(csv_path: str, scoring: str = "ppr", force: bool = False) -> int:
    """Fill the proj_points column of a rankings CSV in place.

    ESPN is primary, Sleeper the per-player fallback. Returns the number of
    rows filled; prints how many found no match in either source.
    """
    scoring = {"standard": "std", "half_ppr": "half", "halfppr": "half"}.get(
        scoring.lower(), scoring.lower())
    if scoring not in ("ppr", "half", "std"):
        raise ValueError("scoring must be ppr, half, or std (got %r)" % scoring)

    espn = _espn_for_scoring(scoring, force=force)
    try:
        sleeper = fetch_sleeper(force=force)
    except RuntimeError as exc:
        print("  Sleeper unavailable (%s) - ESPN only" % exc)
        sleeper = {}
    espn_defs, sleeper_defs = _def_index(espn), _def_index(sleeper)

    with open(csv_path, "r", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise ValueError("Rankings CSV %s is empty" % csv_path)

    header = [c.strip().lower() for c in rows[0]]
    try:
        i_name, i_pos = header.index("name"), header.index("pos")
        i_proj = header.index("proj_points")
    except ValueError:
        raise ValueError("CSV needs name, pos, and proj_points columns. Found: %s"
                         % ", ".join(header))
    i_team = header.index("team") if "team" in header else None

    filled, unmatched = 0, []
    for row in rows[1:]:
        if len(row) <= max(i_name, i_pos, i_proj):
            continue
        name, pos = row[i_name].strip(), row[i_pos].strip().upper()
        team = row[i_team].strip() if i_team is not None else ""
        if not name:
            continue
        # ESPN primary; a matched name with an empty projection still falls
        # through to Sleeper (ESPN carries unprojected players in its top 600).
        pts = _lookup(name, pos, team, scoring, espn, espn_defs)
        if pts is None:
            pts = _lookup(name, pos, team, scoring, sleeper, sleeper_defs)
        if pts is None:
            unmatched.append("%s (%s)" % (name, pos))
            continue
        row[i_proj] = "%.1f" % pts
        filled += 1

    with open(csv_path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)

    print("  projections: filled %d/%d rows (%s); %d unmatched"
          % (filled, len(rows) - 1, scoring, len(unmatched)))
    if unmatched:
        print("  unmatched: %s" % ", ".join(unmatched[:12])
              + (" ..." if len(unmatched) > 12 else ""))
    return filled


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "rankings.csv")
    fmt = sys.argv[2] if len(sys.argv) > 2 else "ppr"
    apply_to_csv(target, scoring=fmt)
