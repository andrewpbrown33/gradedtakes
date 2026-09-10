"""Weekly data layer: per-week projections, schedule/byes, and game lines.

Three fetchers every in-season module leans on, plus a rest-of-season sum:

* fetch_weekly_projections(week) - ESPN kona is primary. The same
  unauthenticated kona_player_info payload the season fetch caches carries a
  full per-week projection split (statSourceId 1, statSplitTypeId 1, one
  entry per scoringPeriodId), so one cached download serves every week AND
  rest-of-season sums. Verified live for 2026 week 1: 523 of ESPN's top 600
  carry a week-1 number, including 32 D/ST and 42 K. Sleeper's weekly
  endpoint (/projections/nfl/<season>/<week>) is the per-player fallback.
* fetch_schedule(week) - the nflverse schedules release asset
  (nflverse-data/releases/download/schedules/games.csv, the file behind
  nflreadr::load_schedules; discovered live Aug 2026 - "schedules.csv" is a
  404, games.csv is the real asset name). Powers bye detection (a team
  absent from the week's map is on bye) and lock times.
* fetch_game_lines(week) - OPTIONAL GARNISH. ESPN's site.api.espn.com
  scoreboard returns 403 without auth as of Aug 2026 (probed live; the
  code still tries it first in case that changes), so implied totals are
  derived from the Vegas columns nflverse ships inside games.csv
  (total_line/spread_line - opening-ish lines, refreshed nightly, NOT live
  closing lines). Coverage thins out for future weeks (week 1: 16/16 games,
  week 10: 1/14), so callers MUST treat a missing team as "no line", never
  as an error. Returns {} when no source has lines.

Caching follows engine/adp.py: data/cache/, freshness window, stale-cache
fallback offline. All names go through projections.name_key (models.norm_name)
so keys join cleanly with every other module.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional

try:
    from engine.models import norm_pos
    from engine.nflverse import _fetch_csv
    from engine.projections import (UA, _fetch_json, fetch_espn, name_key,
                                    norm_team)
except ImportError:  # run directly as `python engine/weekly.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.models import norm_pos
    from engine.nflverse import _fetch_csv
    from engine.projections import (UA, _fetch_json, fetch_espn, name_key,
                                    norm_team)

SEASON = 2026
FINAL_WEEK = 18
FANTASY_POS = ("QB", "RB", "WR", "TE", "K", "DEF")

SCHEDULE_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
                "schedules/games.csv")
SLEEPER_WEEKLY_URL = ("https://api.sleeper.app/projections/nfl/%d/%d"
                      "?season_type=regular&position[]=QB&position[]=RB"
                      "&position[]=WR&position[]=TE&position[]=K&position[]=DEF")
ESPN_SCOREBOARD_URL = ("https://site.api.espn.com/apis/site/v2/sports/football"
                       "/nfl/scoreboard?seasontype=2&week=%d&dates=%d")

_SLEEPER_PTS = {"ppr": "pts_ppr", "half": "pts_half_ppr", "std": "pts_std"}


def _norm_scoring(scoring: str) -> str:
    s = {"standard": "std", "half_ppr": "half", "halfppr": "half"}.get(
        (scoring or "").lower(), (scoring or "").lower())
    if s not in ("ppr", "half", "std"):
        raise ValueError("scoring must be ppr, half, or std (got %r)" % scoring)
    return s


def _check_week(week: int) -> int:
    week = int(week)
    if not 1 <= week <= FINAL_WEEK:
        raise ValueError("week must be 1-%d (got %r)" % (FINAL_WEEK, week))
    return week


# --- weekly projections -----------------------------------------------------

def _espn_weekly_records(scoring: str, force: bool = False,
                         quiet: bool = False) -> Dict[str, Dict]:
    """fetch_espn records with rec["weekly"] in the requested scoring.

    half-PPR has no working ESPN leaguedefault (ids 2/4 are 404), so each
    half week is the average of the PPR and standard weeks - exact, since
    the two differ only by points per reception on identical projections.
    """
    if scoring == "half":
        ppr = fetch_espn(3, force=force, quiet=quiet)
        std = fetch_espn(1, force=force, quiet=quiet)
        for key, rec in ppr.items():
            sweekly = (std.get(key) or {}).get("weekly", {})
            rec["weekly"] = dict(
                (w, round((p + sweekly[w]) / 2.0, 2) if w in sweekly else p)
                for w, p in rec["weekly"].items())
        return ppr
    return fetch_espn(3 if scoring == "ppr" else 1, force=force, quiet=quiet)


def _weekly_from_espn(records: Dict[str, Dict], week: int) -> Dict[str, Dict]:
    """Pure transform: fetch_espn-shaped records -> this week's projections."""
    out = {}
    for key, rec in records.items():
        pts = (rec.get("weekly") or {}).get(week)
        if pts is None:
            continue
        out[key] = {"proj": float(pts), "pos": rec["pos"],
                    "team": rec.get("team", ""), "source": "espn"}
    return out


def _weekly_from_sleeper(payload: List[Dict], scoring: str) -> Dict[str, Dict]:
    """Pure transform: Sleeper weekly payload -> {name_key: projection}.

    Sleeper defenses are named by city ('Seattle Seahawks'), so their keys
    never collide with ESPN's 'Seahawks D/ST' - dedupe happens by team in
    the merge, not here. Duplicate names keep the larger projection.
    """
    field = _SLEEPER_PTS[scoring]
    out = {}
    for entry in payload:
        pl = entry.get("player") or {}
        pos = norm_pos(pl.get("position") or "")
        name = ("%s %s" % (pl.get("first_name", ""),
                           pl.get("last_name", ""))).strip()
        pts = (entry.get("stats") or {}).get(field)
        if not name or pos not in FANTASY_POS or pts is None:
            continue
        rec = {"proj": float(pts), "pos": pos,
               "team": norm_team(entry.get("team") or pl.get("team") or ""),
               "source": "sleeper"}
        key = name_key(name)
        old = out.get(key)
        if old is None or rec["proj"] > old["proj"]:
            out[key] = rec
    return out


def _merge_weekly(espn: Dict[str, Dict],
                  sleeper: Dict[str, Dict]) -> Dict[str, Dict]:
    """ESPN primary; Sleeper fills missing players. One DEF per team:
    a Sleeper city-named defense is dropped when ESPN already carries that
    team's D/ST under its own key."""
    out = dict(espn)
    espn_def_teams = set(r["team"] for r in espn.values()
                         if r["pos"] == "DEF" and r["team"])
    for key, rec in sleeper.items():
        if key in out:
            continue
        if rec["pos"] == "DEF" and rec["team"] in espn_def_teams:
            continue
        out[key] = rec
    return out


def fetch_weekly_projections(week: int, scoring: str = "ppr",
                             force: bool = False,
                             quiet: bool = False) -> Dict[str, Dict]:
    """Per-week projections: {name_key: {"proj": pts, "pos": pos, ...}}.

    ESPN kona weekly split is primary; Sleeper's weekly endpoint fills
    players ESPN skips. Extra keys "team" and "source" ride along for DEF
    matching and provenance. A 0.0 proj is a real projection (injured/role
    change), distinct from absence (no projection filed).
    """
    week = _check_week(week)
    scoring = _norm_scoring(scoring)

    try:
        espn = _weekly_from_espn(
            _espn_weekly_records(scoring, force=force, quiet=quiet), week)
    except RuntimeError as exc:
        if not quiet:
            print("  weekly: ESPN unavailable (%s) - Sleeper only" % exc)
        espn = {}

    try:
        payload = _fetch_json(
            SLEEPER_WEEKLY_URL % (SEASON, week),
            "sleeper-proj-wk%d-%d.json" % (week, SEASON),
            {"User-Agent": UA, "Accept": "application/json"},
            force=force, quiet=quiet)
        sleeper = _weekly_from_sleeper(payload, scoring)
    except RuntimeError as exc:
        if not quiet:
            print("  weekly: Sleeper unavailable (%s) - ESPN only" % exc)
        sleeper = {}

    out = _merge_weekly(espn, sleeper)
    if not quiet:
        n_def = sum(1 for r in out.values() if r["pos"] == "DEF")
        n_k = sum(1 for r in out.values() if r["pos"] == "K")
        print("  weekly: %d players projected for week %d (%s) - %d DEF, %d K"
              % (len(out), week, scoring, n_def, n_k))
    return out


# --- schedule ---------------------------------------------------------------

def _kickoff_iso(gameday: str, gametime: str) -> str:
    """ISO kickoff from nflverse gameday (YYYY-MM-DD) + gametime (ET HH:MM).

    Carries the real Eastern offset when zoneinfo has tz data; otherwise
    falls back to a naive ISO string that is still ET wall-clock time.
    """
    day = (gameday or "").strip()
    hhmm = (gametime or "").strip() or "00:00"
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        dt = datetime.strptime("%s %s" % (day, hhmm), "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=ZoneInfo("America/New_York")).isoformat()
    except Exception:
        return "%sT%s:00" % (day, hhmm)


def _schedule_rows(force: bool = False) -> List[Dict]:
    """All rows of the nflverse schedules asset (12h cache - lines move)."""
    return _fetch_csv(SCHEDULE_URL, "nflverse-schedule.csv", "game_id",
                      max_age_hours=12.0, force=force)


def _week_games(rows: List[Dict], season: int, week: int) -> List[Dict]:
    return [r for r in rows
            if r.get("season") == str(season) and r.get("week") == str(week)
            and r.get("game_type") == "REG"]


def _schedule_from_rows(rows: List[Dict], season: int,
                        week: int) -> Dict[str, Dict]:
    """Pure transform: games.csv rows -> {team: opponent/home/kickoff}.

    Team abbreviations are normalized (nflverse's 'LA' -> 'LAR') so they
    match rankings.csv and the projection fetchers. A team absent from the
    result is on bye that week.
    """
    out = {}
    for r in _week_games(rows, season, week):
        home = norm_team(r.get("home_team", ""))
        away = norm_team(r.get("away_team", ""))
        if not home or not away:
            continue
        iso = _kickoff_iso(r.get("gameday", ""), r.get("gametime", ""))
        out[home] = {"opponent": away, "home": True, "kickoff_iso": iso}
        out[away] = {"opponent": home, "home": False, "kickoff_iso": iso}
    return out


def fetch_schedule(week: int, force: bool = False) -> Dict[str, Dict]:
    """{team_abbr: {"opponent": abbr, "home": bool, "kickoff_iso": str}}.

    Bye detection: a team missing from the map has no game that week.
    kickoff_iso powers lock-time logic (waivers, lineup deadlines).
    """
    week = _check_week(week)
    return _schedule_from_rows(_schedule_rows(force=force), SEASON, week)


def byes(week: int, force: bool = False) -> List[str]:
    """Teams on bye for the week - the complement of fetch_schedule."""
    playing = set(fetch_schedule(week, force=force))
    rows = _schedule_rows(force=force)
    all_teams = set()
    for r in rows:
        if r.get("season") == str(SEASON) and r.get("game_type") == "REG":
            all_teams.add(norm_team(r.get("home_team", "")))
            all_teams.add(norm_team(r.get("away_team", "")))
    all_teams.discard("")
    return sorted(all_teams - playing)


# --- game lines (optional garnish) ------------------------------------------

def _f(val) -> Optional[float]:
    s = (str(val) if val is not None else "").strip()
    if not s or s.upper() == "NA":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _lines_from_rows(rows: List[Dict], season: int,
                     week: int) -> Dict[str, Dict]:
    """Pure transform: nflverse total_line/spread_line -> implied totals.

    nflverse convention: spread_line is the HOME team's expected winning
    margin (positive = home favored). implied_home = total/2 + spread/2.
    Games without a filed line are simply skipped.
    """
    out = {}
    for r in _week_games(rows, season, week):
        total = _f(r.get("total_line"))
        spread = _f(r.get("spread_line"))
        if total is None or spread is None:
            continue
        home = norm_team(r.get("home_team", ""))
        away = norm_team(r.get("away_team", ""))
        if not home or not away:
            continue
        out[home] = {"implied_total": round(total / 2.0 + spread / 2.0, 2),
                     "game_total": total}
        out[away] = {"implied_total": round(total / 2.0 - spread / 2.0, 2),
                     "game_total": total}
    return out


def _lines_from_espn_scoreboard(payload: Dict) -> Dict[str, Dict]:
    """Pure transform: ESPN scoreboard events -> implied totals.

    ESPN convention: odds[0].spread is the HOME team's line (negative =
    home favored by that much), overUnder is the game total, so
    implied_home = ou/2 - spread/2.
    """
    out = {}
    for ev in payload.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        odds = comp.get("odds") or []
        if not odds:
            continue
        ou = _f(odds[0].get("overUnder"))
        spread = _f(odds[0].get("spread"))
        if ou is None or spread is None:
            continue
        home = away = ""
        for c in comp.get("competitors", []):
            abbr = norm_team((c.get("team") or {}).get("abbreviation", ""))
            if c.get("homeAway") == "home":
                home = abbr
            elif c.get("homeAway") == "away":
                away = abbr
        if not home or not away:
            continue
        out[home] = {"implied_total": round(ou / 2.0 - spread / 2.0, 2),
                     "game_total": ou}
        out[away] = {"implied_total": round(ou / 2.0 + spread / 2.0, 2),
                     "game_total": ou}
    return out


def fetch_game_lines(week: int, force: bool = False,
                     quiet: bool = True) -> Dict[str, Dict]:
    """{team_abbr: {"implied_total": float, "game_total": float}}.

    OPTIONAL GARNISH - callers must degrade gracefully when a team (or the
    whole week) is missing. ESPN's scoreboard odds are tried first but
    return 403 without auth as of Aug 2026 (probed live); the working
    source is the Vegas columns inside the nflverse schedule file, which
    are nightly-refreshed opening-ish lines, not live closers, and thin
    out for far-future weeks. Returns {} when no source has lines.
    """
    week = _check_week(week)

    # ESPN scoreboard: currently 403 unauthenticated; kept in case it opens
    # back up, but never allowed to break the caller.
    try:
        req = urllib.request.Request(
            ESPN_SCOREBOARD_URL % (week, SEASON),
            headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.load(resp)
        lines = _lines_from_espn_scoreboard(payload)
        if lines:
            return lines
    except Exception:
        pass

    try:
        lines = _lines_from_rows(_schedule_rows(force=force), SEASON, week)
    except RuntimeError as exc:
        if not quiet:
            print("  lines: unavailable (%s) - proceeding without" % exc)
        return {}
    if not quiet and not lines:
        print("  lines: none filed for week %d yet" % week)
    return lines


# --- rest of season ---------------------------------------------------------

def ros_projection(key: str, from_week: int, scoring: str = "ppr",
                   records: Optional[Dict[str, Dict]] = None,
                   force: bool = False) -> float:
    """Sum of remaining weekly projections for one name_key, weeks
    from_week..18. Bye weeks contribute zero naturally (ESPN files either
    no entry or 0.0 for the bye). Unknown keys sum to 0.0 - callers should
    treat that as "no data", not "worthless player".

    `records` accepts a prefetched _espn_weekly_records() dict so callers
    scoring a whole roster fetch once, and tests can inject fixtures.
    """
    if records is None:
        records = _espn_weekly_records(_norm_scoring(scoring), force=force,
                                       quiet=True)
    rec = records.get(key)
    if not rec:
        return 0.0
    weekly = rec.get("weekly") or {}
    total = 0.0
    for w, pts in weekly.items():
        if pts is not None and from_week <= int(w) <= FINAL_WEEK:
            total += pts
    return round(total, 2)


if __name__ == "__main__":
    wk = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    proj = fetch_weekly_projections(wk, quiet=False)
    sched = fetch_schedule(wk)
    lines = fetch_game_lines(wk)
    print("  schedule: %d teams playing week %d; byes: %s"
          % (len(sched), wk, ", ".join(byes(wk)) or "none"))
    print("  lines: implied totals for %d teams" % len(lines))
