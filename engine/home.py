#!/usr/bin/env python3
"""THE LANDING PAGE, v3: the strongest single surface in the product.

    python -m engine.home                # current week, every configured league
    python -m engine.home --week 3
    python -m engine.home --skip-waivers # fast render: the wire is not read
    ./home.sh                            # wrapper - opens the page

Writes home.html to the project root (atomic tmp+replace, the same discipline
as engine/board.py and engine/strip.py) and prints the absolute path as its
LAST stdout line so home.sh can open it.

WHAT IS ON IT
-------------
  1. the shell (engine/ui.shell) and ONE line: today, the week, the first
     lock - "first lock Thu 8:20 PM ET · 2 of your starters play then" -
     computed from the nflverse schedule engine/weekly.py already fetches.
  2. THE INBOX, as a SIDEBAR. On a screen 1000px and wider it is a sticky
     right rail (~320px) beside the roster content; below that it stacks
     at the top as compact rows, the first three visible and the rest
     behind a native <details> "show N more". Every item is ONE line -
     glyph · player · a short verb button (44px tall, 88px wide) with the
     host deep link - grouped under three small headers with counts:
         Do now      before the first lock: a starter is out, on bye, a
                     filed zero, an empty slot
         Before lock start/sit splits, questionable tags, avoid matchups,
                     missing projections
         This week   waiver claims, DEF/K streams, roster housekeeping
     The preferences layer (engine/prefs.py) may stamp data-inbox="top" on
     <html> to force the stacked form at any width, and data-quiet="1" to
     hush the context lines; both are honoured in CSS here and stored
     nowhere here.
  3. THE WEEK STRIP: the game windows in kickoff order, how many of your
     starters play in each (per league), the first-lock window under the
     gold rule.
  4. one card per league (id="league-<id>", the shell's switcher targets it):
     name, platform, record or "record not tracked", coverage, the projected
     starting-lineup total, and the league's Board / Ledger / Trade Desk.
  5. the roster rows inside each card, in the THREE-COLUMN anatomy that fits
     a phone without a sideways scroll:
         identity   pos pill · name · status pill (Q / OUT / BYE) · the news
                    dot for a creator's own words · dissent / hot / locked
                    marks · a 13px context line: ESPN roster % and start %
                    when the public feed has him, a trending-adds pill when
                    the wire is moving on him
         middle     the opponent chip toned by the matchup grade · kickoff ·
                    the score cell (projection; the actual once a scoring
                    feed files one - none is connected, and the cell says
                    so rather than inventing a number)
         verdict    the room's chip and the matchup meter
     A row whose game has kicked off is muted and carries the lock mark.
     Every row expands into the PLAYER CARD: every signal in words, and -
     when you play more than one league - CROSS-LEAGUE OWNERSHIP: one line
     per league (rostered? starting or bench? the room's verdict there?)
     with Claim / Trade / Drop as host deep links for THAT league, and the
     correlated-risk note when he is on more than one of your rosters.
  6. the exposure ribbon: players you hold on more than one roster, with
     the correlated-risk note - rendered only when there is overlap.
  7. the source pulse: every enabled voice as a nameplate with its weight
     and current form, linking to sources.html.
  8. a jump box that filters the roster rows by name. Vanilla JS, a dozen
     lines; hidden without JS, and the page is complete without it.
  9. the legend is a "?" popover at the inbox head and at every roster
     head, not a block at the bottom; every glyph carries a title.

THE HONESTY CONTRACT, restated for this page
--------------------------------------------
  IT NEVER MANUFACTURES URGENCY. An inbox item appears because a specific,
  checkable fact is true - a starter with no game, a filed status, a
  quarter of the room's weight on the other side of a call, a free agent
  who clears your worst starter's bar. When none is true it says nothing
  needs you, in those words, and how many starters that claim rests on.

  IT NEVER CLAIMS A CLEAN BILL IT DID NOT EARN. A feed that is down is a
  caveat beside the all-clear AND a degraded banner in place; a check that
  did not run is named, never skipped into silence.

  IT NEVER INVENTS A TIME. nflverse files `gametime` blank for games not
  yet scheduled, and weekly._kickoff_iso() then stamps 00:00. No NFL game
  kicks off at midnight ET, so a midnight stamp is read as "day known, time
  not filed": the page shows the day only and says so (time_known()).

  IT NEVER INVENTS A SCORE. No live scoring feed is connected. Once a game
  has started the score cell shows the projection and a dash for the
  actual, titled with that fact.

  IT NEVER FAKES A RECORD. No standings feed is connected (see
  board.record_line); the card says "record not tracked" unless the league
  yaml carries one by hand.

  IT NEVER GUESSES A HOST. Deep links need `host: {league_id, team_id}` in
  the league yaml (models.LeagueConfig.host). Without it the item still
  renders, without a link, and a quiet note names the key that adds one.

  IT NEVER CALLS A PLAYER A FREE AGENT. The cross-league card knows YOUR
  rosters. A player not on your roster in a league is "not rostered by
  you"; whether a rival holds him is the host's page to answer, which is
  where the Claim verb goes.

READ-ONLY. The only thing this module writes is the one HTML file it is
asked to write. The waiver read passes waivers.owned_momentum(advance=False),
so data/cache/espn-owned-snapshot.json is read and left exactly where it
was; nothing here records a ledger vote or advances a baseline.
tests/home_test.py hashes that snapshot around a double render to hold the
line.

COMPOSITION, NOT REIMPLEMENTATION. Every fact on the page is computed by the
module that owns it; this file arranges them and picks the mark.

  starters vs bench ............ engine/lineup     (load_roster, build)
  weekly projections, schedule . engine/weekly     (fetch_weekly_projections,
                                                    fetch_schedule)
  injury statuses .............. engine/projections(fetch_injury_status)
  ESPN roster % / start % ...... engine/projections(the public ESPN payload
                                                    fetch_espn already caches)
  trending adds ................ engine/waivers    (fetch_trending_adds)
  the room's lean + the split .. engine/consensus  (build_consensus)
  what counts as a split ....... engine/board      (divergence_level,
                                                    split_weight)
  matchup grade ................ engine/matchups   (pa_table, matchups_for_roster)
  the waiver shortlist ......... engine/waivers    (the board's read-only path)
  DEF/K hold-or-stream ......... engine/dk         (weekly_call - the DST/K
                                                    rows' verdict, and ONE
                                                    inbox item on a STREAM)
  rival rosters ................ engine/trades     (load_rival_view)
  which voices are running hot . engine/performance(source_scoreboard)
  cross-roster exposure ........ engine/exposure   (Exposure.load)
  roster coverage per league ... engine/leagueview (coverage_rows)
  the record line .............. engine/board      (record_line)
  every colour, glyph, chip .... engine/ui         (v3: tokens only)

THE UI BRIDGE. engine/ui.py is gaining a v4 vocabulary - status_pill,
news_dot, trend_arrow, opp_chip, score_cell, legend_popover, sheet +
sheets_script, segmented, row3 and the .wr-t1..t4 type scale. Each is
reached through getattr() with a LOCAL fallback built from the same tokens
(see the "ui bridge" section), so this page renders whether or not a
component has landed, and ui_components() reports which it found.

NO SECOND DESIGN SYSTEM. This module emits not one hex value and not one
<svg> path of its own; its stylesheet is layout only and every colour in it
is a var(--wr-*) token. The few components ui.py lacks - the inbox verb
button, the week-strip window, the fallbacks above - are built HERE, from
the tokens, and say so in the stylesheet.

PURE CORE, IMPURE EDGE. gather_league(), fetch_ownership() and
load_exposure() fetch; everything from signal_icons() down is a pure
function of the dicts it is handed. tests/home_test.py drives that half
with fixtures - no network, and no read of the user's rosters or registry
beyond the league yamls it opens read-only.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

try:
    from engine import board as board_mod
    from engine import consensus as consensus_mod
    from engine import dk as dk_mod
    from engine import leagueview, lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import performance as performance_mod
    from engine import trades as trades_mod
    from engine import ui, waivers as waivers_mod, weekly
    from engine.exposure import Exposure
    from engine.ingest import Matcher
    from engine.models import (LeagueConfig, load_players,
                               missing_rankings_message, repo_path)
    from engine.projections import fetch_injury_status
except ImportError:  # run directly as `python engine/home.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import board as board_mod
    from engine import consensus as consensus_mod
    from engine import dk as dk_mod
    from engine import leagueview, lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import performance as performance_mod
    from engine import trades as trades_mod
    from engine import ui, waivers as waivers_mod, weekly
    from engine.exposure import Exposure
    from engine.ingest import Matcher
    from engine.models import (LeagueConfig, load_players,
                               missing_rankings_message, repo_path)
    from engine.projections import fetch_injury_status

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(HERE, "home.html")
LEAGUE_DIR = os.path.join(HERE, "leagues")
ET_ZONE = "America/New_York"    # nflverse gametime is Eastern wall-clock

# Inbox policy -----------------------------------------------------------------
#
# ATTENTION_MAX is a DISPLAY cap, never a filter: criticals sort first, and
# everything past the cap is still on the page inside a disclosure, so the
# inbox can never quietly swallow a problem.
ATTENTION_MAX = 12

# When the inbox is STACKED (a phone, or data-inbox="top") only this many
# rows show before the "show N more" disclosure. The sidebar shows them all.
STACK_VISIBLE = 3

# A split earns the inbox when a quarter of the room's WEIGHT sits on the
# losing side (board.split_weight is 0-50, where 50 is a dead halving).
# Below that it still shows its glyph on the row - the reader can see it -
# but it does not claim to be something that needs them this week.
SPLIT_ATTENTION = 25

# Waiver claims that may reach the inbox per league. The wire is long; the
# inbox is for the one or two adds that clear your own starters' bar.
CLAIMS_MAX = 2

# The sidebar breaks in at this width; below it the inbox stacks on top.
SIDEBAR_MIN_PX = 1000

# Injury statuses, borrowed from the module that owns the classification so
# "Out" can never mean one thing here and another in the lineup report.
RED_STATUSES = lineup_mod.RED_STATUSES
WARN_STATUSES = lineup_mod.WARN_STATUSES

OPEN_SLOT = "(open slot)"

# models.scoring_label() returns the FETCHER token ("ppr"), which is the right
# thing to pass a feed and the wrong thing to print at a human. Display only.
SCORING_LABEL = {"ppr": "full PPR", "half": "half PPR", "std": "standard"}
PLATFORM_LABEL = {"espn": "ESPN", "yahoo": "Yahoo"}

# Where a decision is actually made, per host. `team` is the lineup page;
# `players` is the add/waiver page. `trade` and `drop` are the team page
# too - both hosts start a trade or a drop from your own roster, and no
# deeper URL is known for either, so none is invented. Ids come from
# LeagueConfig.host and are URL-quoted at link time; nothing else is ever
# substituted in.
HOST_URLS = {
    "espn": {
        "team": ("https://fantasy.espn.com/football/team?leagueId={league_id}"
                 "&teamId={team_id}&seasonId={season}"),
        "players": "https://fantasy.espn.com/football/players/add?leagueId={league_id}",
        "trade": ("https://fantasy.espn.com/football/team?leagueId={league_id}"
                  "&teamId={team_id}&seasonId={season}"),
        "drop": ("https://fantasy.espn.com/football/team?leagueId={league_id}"
                 "&teamId={team_id}&seasonId={season}"),
    },
    "yahoo": {
        "team": "https://football.fantasysports.yahoo.com/f1/{league_id}/{team_id}",
        "players": "https://football.fantasysports.yahoo.com/f1/{league_id}/players",
        "trade": "https://football.fantasysports.yahoo.com/f1/{league_id}/{team_id}",
        "drop": "https://football.fantasysports.yahoo.com/f1/{league_id}/{team_id}",
    },
}

# inbox kind -> (the verb the user performs, the host page it happens on,
#                the SHORT verb on the 88px button)
VERBS = {
    "open": ("Fill the slot", "team", "Fill"),
    "bye": ("Swap him out", "team", "Swap"),
    "out": ("Replace him", "team", "Replace"),
    "injury": ("Check his status", "team", "Check"),
    "zero": ("Replace him", "team", "Replace"),
    "noproj": ("Verify him", "team", "Verify"),
    "avoid": ("Rethink the slot", "team", "Rethink"),
    "split": ("Set your lineup", "team", "Set lineup"),
    "unresolved": ("Open your roster", "team", "Open"),
    "claim": ("Claim him", "players", "Claim"),
}

# The cross-league card's verbs: what you can do with a player in a league
# where you hold him, and where you do not.
XL_VERBS_HELD = (("Trade", "trade"), ("Drop", "drop"))
XL_VERBS_FREE = (("Claim", "players"),)

# inbox kind -> urgency shelf. The three shelves, in order.
URGENCY = (
    ("now", "Do now", "before the first lock: a starter is out or on bye, "
                      "a slot is empty, a filed zero"),
    ("lock", "Before lock", "start/sit splits, questionable tags, matchups "
                            "to rethink, projections to verify"),
    ("week", "This week", "waiver claims, DEF/K streams, roster housekeeping"),
)
URGENCY_OF = {
    "open": "now", "bye": "now", "out": "now", "zero": "now",
    "injury": "lock", "noproj": "lock", "avoid": "lock", "split": "lock",
    "claim": "week", "unresolved": "week",
}

# Injury status -> the code on the status pill. Anything else is the feed's
# word, trimmed to pill length.
STATUS_CODE = {
    "questionable": "Q", "doubtful": "D", "out": "OUT", "ir": "IR",
    "injured reserve": "IR", "pup": "PUP", "suspended": "SUSP",
    "suspension": "SUSP", "probable": "P", "nfi": "NFI",
}

# The legend. Only glyphs this page can actually emit appear here - a key
# that documents a symbol the page never prints teaches the reader to look
# for something that is not there. The status pill, the news dot, the
# verdict chips and the matchup meter carry their own words and are keyed
# beside these in legend_items().
LEGEND = (
    ("dissent", "the voices point both ways"),
    ("injury", "an injury status is filed"),
    ("bye", "no game this week"),
    ("locked", "his game has started - this is final"),
    ("hot_streak", "a source on a hot run backs this"),
    ("news", "read this — a creator's own words, or a gap in what the page "
             "could see"),
    ("matchup_avoid", "a starter walking into a matchup to avoid"),
    ("waiver_add", "a free agent worth a claim"),
    ("sit", "a filed projection of zero - the feed expects him not to play"),
)

# The v4 vocabulary this page reaches for in engine/ui (see the ui bridge).
UI_NAMES = ("status_pill", "news_dot", "trend_arrow", "opp_chip",
            "score_cell", "legend_popover", "sheet", "sheets_script",
            "segmented", "row3")


# --- small pure helpers -----------------------------------------------------

def fmt_pts(value) -> str:
    """A projection as one number, or an em dash for none filed.

    None and 0.0 are different facts and stay different: 0.0 is a filed
    projection of zero (hurt, inactive, benched by his own coach) and reads
    as a number; None is silence from the feed and reads as a dash.
    """
    if value is None:
        return "—"
    try:
        return "%.1f" % float(value)
    except (TypeError, ValueError):
        return "—"


def fmt_count(n) -> str:
    """1234 -> '1.2k', 87 -> '87'."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    if n >= 1000:
        return "%.1fk" % (n / 1000.0)
    return "%d" % n


def opponent_label(team: str, game: Optional[Dict],
                   schedule_known: bool = True) -> str:
    """'vs PHI' / '@ DET' / 'BYE' / '' - never a guess.

    schedule_known=False means the feed is down, so absence from the map
    proves nothing and the label stays empty rather than saying BYE.
    """
    if not team:
        return ""
    if not schedule_known:
        return ""
    if not game:
        return "BYE"
    return "%s %s" % ("vs" if game.get("home") else "@",
                      game.get("opponent") or "?")


def _parse_iso(iso) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def _wall(iso) -> Optional[datetime]:
    """Naive ET wall-clock, for ordering and equality.

    Every kickoff on this page comes from the one nflverse feed and carries
    the same zone, so stripping it compares safely - and keeps a naive
    fixture and an aware feed from raising on `<` in the same sort.
    """
    dt = _parse_iso(iso)
    return dt.replace(tzinfo=None) if dt is not None else None


def time_known(iso) -> bool:
    """Did the feed file a clock time, or only a day?

    nflverse leaves `gametime` blank for games not yet scheduled, and
    weekly._kickoff_iso() then stamps 00:00 to keep the ISO parseable. No
    NFL game kicks off at midnight ET, so a midnight stamp is read as "day
    known, time not filed" - the page then shows the day and says so. It
    never invents a clock.
    """
    dt = _parse_iso(iso)
    return dt is not None and not (dt.hour == 0 and dt.minute == 0)


def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return "%d:%02d %s ET" % (hour, dt.minute, "AM" if dt.hour < 12 else "PM")


def day_label(iso) -> str:
    """'Sun 9/13', or '' for nothing filed."""
    dt = _parse_iso(iso)
    return "%s %d/%d" % (dt.strftime("%a"), dt.month, dt.day) if dt else ""


def lock_label(iso) -> str:
    """'Thu 8:20 PM ET' - or 'Thu 9/10 (time not filed)', never a made-up
    clock (see time_known)."""
    dt = _parse_iso(iso)
    if dt is None:
        return ""
    if not time_known(iso):
        return "%s (time not filed)" % day_label(iso)
    return "%s %s" % (dt.strftime("%a"), _clock(dt))


def kickoff_label(iso) -> str:
    """'Sun 9/13 1:00 PM ET' for a row's card; '' when the feed filed no
    kickoff; the day alone when it filed no time."""
    dt = _parse_iso(iso)
    if dt is None:
        return ""
    if not time_known(iso):
        return "%s (time not filed)" % day_label(iso)
    return "%s %s" % (day_label(iso), _clock(dt))


def short_kick(iso) -> str:
    """'Sun 1:00 PM' for the row's middle column - the zone and the date
    ride in the title. A day with no filed time is the day alone."""
    dt = _parse_iso(iso)
    if dt is None:
        return ""
    if not time_known(iso):
        return day_label(iso)
    hour = dt.hour % 12 or 12
    return "%s %d:%02d %s" % (dt.strftime("%a"), hour, dt.minute,
                              "AM" if dt.hour < 12 else "PM")


def is_locked(iso: str, now: Optional[datetime] = None) -> bool:
    """Has this game kicked off?

    Returns False - not True - whenever the answer cannot be established:
    no kickoff filed, an unparseable stamp, or a naive/aware mismatch that
    would make the comparison meaningless. A wrongly-locked row tells the
    reader a decision is already made when it is not, which is the more
    expensive of the two mistakes.
    """
    if not iso:
        return False
    dt = _parse_iso(iso)
    if dt is None:
        return False
    if now is None:
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    if (dt.tzinfo is None) != (now.tzinfo is None):
        return False
    if not time_known(iso):
        # Only the day is filed (see time_known). During that day the game
        # may or may not have started - unknown is NOT locked. Once the day
        # is over it has certainly kicked off.
        local_now = now.astimezone(dt.tzinfo) if dt.tzinfo else now
        return local_now.date() > dt.date()
    return now >= dt


def row_locked(row: Dict, now: Optional[datetime] = None) -> bool:
    """The row's lock state at RENDER time: the gathered flag, or the
    kickoff against the injected clock. A fixture with a Thursday kickoff
    rendered on Sunday is locked, exactly as the real page would be."""
    if row.get("open"):
        return False
    if row.get("locked"):
        return True
    return is_locked(row.get("kickoff_iso") or "", now) if now else False


def today_label(now: datetime) -> str:
    """'Sat Sep 5' - assembled by hand, so no platform-specific strftime flag."""
    return "%s %s %d" % (now.strftime("%a"), now.strftime("%b"), now.day)


def _now() -> datetime:
    """Aware Eastern time when the zone database is there, else local naive
    (is_locked then refuses to compare an aware kickoff against it)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(ET_ZONE))
    except Exception:  # noqa: BLE001 - a missing tz database degrades, not dies
        return datetime.now()


def anchor_id(league_id: str, index: int) -> str:
    slug = "".join(c if (c.isalnum() or c == "-") else "-"
                   for c in str(league_id))
    return "p-%s-%d" % (slug, index)


def short_labels(snapshots: Sequence[Dict]) -> Dict[str, str]:
    """{league name: short label} for the strip and the lock line.

    The platform name when every league is on a different one - 'ESPN 3 ·
    Yahoo 2' reads at a glance - otherwise the league name, trimmed.
    """
    live = [s for s in snapshots if s.get("error") is None]
    plats = [PLATFORM_LABEL.get(str(s.get("platform") or "").lower())
             for s in live]
    use_platform = all(plats) and len(set(plats)) == len(plats)
    out = {}
    for s, plat in zip(live, plats):
        name = s.get("name") or s.get("id") or "?"
        out[name] = plat if use_platform else ui.trim(name, 14)
    return out


def status_code(status) -> str:
    """'Questionable' -> 'Q', 'Out' -> 'OUT'; an unknown word is trimmed to
    pill length, never dropped."""
    s = str(status or "").strip()
    if not s:
        return ""
    return STATUS_CODE.get(s.lower()) or ui.trim(s.upper(), 5)


# --- game windows (pure) ----------------------------------------------------

_DAYPARTS = ((12.0, "morning"), (15.5, "early"), (19.0, "late"), (None, "night"))


def game_window(iso) -> Optional[Dict]:
    """Which strip column a kickoff belongs to, from its ET weekday + clock.

    The canonical five (Thu night · Sun early · Sun late · Sun night · Mon
    night) fall out of one rule; an off-pattern game - a Wednesday opener,
    Black Friday, a Saturday slate, a 9:30 London kick - gets its own
    honestly-labelled column rather than being forced into the nearest one
    or dropped. A kickoff with no filed time is a column of its own, and
    says so.
    """
    dt = _parse_iso(iso)
    if dt is None:
        return None
    day = dt.strftime("%a")
    if not time_known(iso):
        return {"key": "%s-tbd" % day.lower(),
                "label": "%s (time not filed)" % day, "iso": iso}
    if dt.weekday() in (5, 6):          # Sat, Sun: the multi-slate days
        h = dt.hour + dt.minute / 60.0
        part = next(p for lim, p in _DAYPARTS if lim is None or h < lim)
    else:
        part = "night" if dt.hour >= 17 else "day"
    return {"key": "%s-%s" % (day.lower(), part),
            "label": "%s %s" % (day, part), "iso": iso}


def week_kickoffs(snapshots: Sequence[Dict]) -> List[str]:
    """One kickoff per GAME, from the first league that carries a schedule.

    Every league in the same week sees the same schedule, so the lists are
    identical when both are present and one stands in when the other
    league's feed was down; unioning them would double-count games.
    """
    for s in snapshots:
        if s.get("error") is None and s.get("kickoffs"):
            return list(s["kickoffs"])
    return []


def week_windows(snapshots: Sequence[Dict]) -> Dict:
    """The strip's data: every window in the week's schedule, in kickoff
    order, with how many of your starters play in each, per league.

    Windows come from the SCHEDULE, not from your starters, so a slate none
    of your players are in still shows - with a zero, which is information.
    """
    kicks = week_kickoffs(snapshots)
    if not kicks:
        return {"known": False, "windows": [], "first_iso": "",
                "first_key": "", "byes": 0}
    windows: Dict[str, Dict] = {}
    for iso in kicks:
        w = game_window(iso)
        if not w:
            continue
        win = windows.setdefault(w["key"], {
            "key": w["key"], "label": w["label"], "first_iso": iso,
            "games": 0, "per_league": {}, "starters": 0})
        win["games"] += 1
        if _wall(iso) < _wall(win["first_iso"]):
            win["first_iso"] = iso
    byes = 0
    for s in snapshots:
        if s.get("error") is not None:
            continue
        name = s.get("name") or s.get("id") or "?"
        for row in s.get("starters") or []:
            if row.get("open"):
                continue
            w = game_window(row.get("kickoff_iso") or "")
            if w is None:
                if row.get("bye") is True:
                    byes += 1
                continue
            win = windows.get(w["key"])
            if win is None:
                continue        # not in the schedule union: never a new column
            win["starters"] += 1
            win["per_league"][name] = win["per_league"].get(name, 0) + 1
    ordered = sorted(windows.values(), key=lambda w: _wall(w["first_iso"]))
    first_iso = min(kicks, key=_wall)
    fw = game_window(first_iso)
    return {"known": True, "windows": ordered, "first_iso": first_iso,
            "first_key": fw["key"] if fw else "", "byes": byes}


def lock_line(snapshots: Sequence[Dict], now: datetime) -> str:
    """The header's one fact: when the first game locks and who of yours is
    in it - or, once it has passed, the next lock. Never a guessed clock."""
    live = [s for s in snapshots if s.get("error") is None]
    kicks = week_kickoffs(snapshots)
    if not kicks:
        if not live:
            return "first lock unknown — no league could be read"
        return "first lock unknown — the schedule feed filed no kickoff"
    order = sorted(set(kicks), key=_wall)
    labels = short_labels(snapshots)

    def playing_at(iso):
        target = _wall(iso)
        per = []
        for s in live:
            n = sum(1 for r in s.get("starters") or []
                    if not r.get("open")
                    and _wall(r.get("kickoff_iso") or "") == target)
            per.append((labels.get(s.get("name") or s.get("id") or "?", "?"), n))
        return sum(n for _, n in per), per

    def phrase(iso):
        n, per = playing_at(iso)
        if n == 0:
            who = "none of your starters play then"
        elif n == 1:
            who = "1 of your starters plays then"
        else:
            who = "%d of your starters play then" % n
        if n and len(per) > 1:
            who += " (%s)" % " · ".join("%s %d" % (lab, k) for lab, k in per)
        return who

    first = order[0]
    if not is_locked(first, now):
        return "first lock %s · %s" % (lock_label(first), phrase(first))
    nxt = next((iso for iso in order if not is_locked(iso, now)), None)
    if nxt is None:
        return ("every game this week has kicked off — first lock was %s; "
                "your lineups are final" % lock_label(first))
    return ("first lock passed (%s) · next lock %s · %s"
            % (lock_label(first), lock_label(nxt), phrase(nxt)))


# --- host deep links (pure) -------------------------------------------------

def host_link(snap: Dict, target: str = "team") -> str:
    """The host page for this league, or '' when it cannot be built.

    Needs a platform with a recipe AND the ids from the league yaml's
    `host:` key. A team-shaped link (team, trade, drop) additionally needs
    the team id - a link to the league's front door dressed up as "your
    team" would be a lie.
    """
    urls = HOST_URLS.get(str(snap.get("platform") or "").strip().lower())
    if not urls or target not in urls:
        return ""
    host = snap.get("host") or {}
    lid = str(host.get("league_id") or "").strip()
    tid = str(host.get("team_id") or "").strip()
    if not lid or (target in ("team", "trade", "drop") and not tid):
        return ""
    return urls[target].format(league_id=quote(lid, safe=""),
                               team_id=quote(tid, safe=""),
                               season=weekly.SEASON)


def host_note(snap: Dict) -> str:
    """Why an item carries no link - the quiet note beside the verb."""
    platform = str(snap.get("platform") or "").strip().lower()
    if platform not in HOST_URLS:
        return ("no link — no deep-link recipe for the %s platform"
                % (platform or "unnamed"))
    return ("no link — add host: {league_id, team_id} to leagues/%s.yaml"
            % (snap.get("id") or "?"))


def verb_for(kind: str, snap: Dict) -> Dict:
    """{'verb', 'short_verb', 'href', 'host_note'} for one inbox kind on one
    league. `verb` is the full phrase naming the platform (the button's
    title); `short_verb` is the word on the button."""
    verb, target, short = VERBS[kind]
    href = host_link(snap, target)
    plat = PLATFORM_LABEL.get(str(snap.get("platform") or "").strip().lower())
    label = "%s on %s" % (verb, plat) if (href and plat) else verb
    return {"verb": label, "short_verb": short, "href": href,
            "host_note": "" if href else host_note(snap)}


def xl_verb(label: str, target: str, snap: Dict) -> Dict:
    """A cross-league verb - Claim / Trade / Drop - on one league."""
    href = host_link(snap, target)
    plat = PLATFORM_LABEL.get(str(snap.get("platform") or "").strip().lower())
    return {"verb": ("%s on %s" % (label, plat)) if (href and plat) else label,
            "short_verb": label, "href": href,
            "host_note": "" if href else host_note(snap)}


# --- the ui bridge ------------------------------------------------------------
# engine/ui.py's v4 components are reached by NAME. Each wrapper below tries
# the component and falls back to a local form built from the same tokens,
# wrapped in a page class the tests can find either way. A component that
# raises is treated as absent - a half-landed helper must not take the page
# down.

def _ui(name: str):
    fn = getattr(ui, name, None)
    return fn if callable(fn) else None


def _try(name: str, *args):
    fn = _ui(name)
    if fn is None:
        return None
    try:
        out = fn(*args)
    except Exception:  # noqa: BLE001 - absent and broken read the same here
        return None
    return out if isinstance(out, str) and out.strip() else None


_UI_CSS: Dict[str, str] = {}


def _ui_css() -> str:
    if "css" not in _UI_CSS:
        _UI_CSS["css"] = ui.css()
    return _UI_CSS["css"]


def ui_has_type_scale() -> bool:
    return ".wr-t1" in _ui_css()


def ui_components() -> Dict[str, bool]:
    """Which v4 components engine/ui carries right now - reported by the
    build, so a render says what it composed and what it fell back on."""
    out = dict((n, _ui(n) is not None) for n in UI_NAMES)
    out["type_scale"] = ui_has_type_scale()
    return out


def status_pill_html(status: str, note: str, tone: str = "") -> str:
    """Q / D / OUT / BYE beside the name. `status` is the feed's word (or
    'BYE'). ui.status_pill speaks its own code set and raises on a word it
    does not badge, so the word goes through ui.normalize_status first;
    the fallback is the design system's flag badge with the page's code."""
    norm = _ui("normalize_status")
    code = None
    if norm is not None:
        try:
            code = norm(status)
        except Exception:  # noqa: BLE001
            code = None
    inner = _try("status_pill", code, note) if code else None
    if inner is None:
        local = "BYE" if str(status).strip().upper() == "BYE" else status_code(status)
        ico = "bye" if local == "BYE" else "injury"
        inner = ('<span class="wr-badge wr-badge-%s" title="%s">%s'
                 '<span class="wr-badge-l">%s</span></span>'
                 % (ico, ui.esc("%s: %s" % (note, status)
                                if local != "BYE" else note),
                    ui.icon(ico, 20), ui.esc(local)))
    return '<span class="home-st%s">%s</span>' % (
        (" home-st-" + tone) if tone else "", inner)


def news_dot_html(title: str) -> str:
    """The unread mark: a creator's own words are filed on this player.
    Fallback: an 8px gold dot drawn in CSS from the rule token."""
    inner = _try("news_dot", True, title)
    if inner is None:
        inner = ('<span class="home-dot" role="img" aria-label="%s" '
                 'title="%s"></span>' % (ui.esc(title), ui.esc(title)))
    return '<span class="home-dot-w">%s</span>' % inner


def trend_html(adds: int, title: str) -> str:
    """The wire is moving on him. Fallback: a stat pill with the add count -
    a word and a number, never an invented arrow glyph."""
    inner = _try("trend_arrow", "up", adds, title)
    if inner is None:
        inner = ui.stat_pill("adds", fmt_count(adds), tone="lean", title=title)
    return '<span class="home-trend">%s</span>' % inner


_GRADE_TONE = {"SMASH": "hi", "GOOD": "hi", "NEUTRAL": "mid",
               "TOUGH": "lo", "AVOID": "lo"}


def opp_chip_html(row: Dict) -> str:
    """'vs PHI' toned by the matchup grade. Fallback: a bordered chip whose
    left rule takes the meter's own tone tokens."""
    opp, home = opp_of(row)
    label = row_opp_label(row)
    if not label:
        return ""
    m = row.get("matchup") or {}
    grade = str(m.get("pa_grade") or "").upper()
    inner = _try("opp_chip", opp, grade or None, home, meter_title(row))
    if inner is None:
        tone = _GRADE_TONE.get(grade, "none")
        inner = ('<span class="home-oppc home-oppc-%s" title="%s">%s</span>'
                 % (tone, ui.esc(meter_title(row)), ui.esc(label)))
    return '<span class="home-oppw">%s</span>' % inner


def score_html(snap: Dict, row: Dict, locked: bool) -> str:
    """Projection, and the actual once one is filed. No scoring feed is
    connected, so a started game shows a dash for the actual and says so."""
    proj = row.get("proj")
    actual = row.get("actual")
    scoring = SCORING_LABEL.get(snap.get("scoring") or "", snap.get("scoring") or "")
    bits = ["projection %s" % fmt_pts(proj)]
    if scoring:
        bits.append("%s scoring" % scoring)
    if row.get("proj_source"):
        bits.append("from %s" % row["proj_source"])
    if actual is not None:
        bits.append("actual %s" % fmt_pts(actual))
    elif locked:
        bits.append("game started — no live scoring feed is connected, so "
                    "no actual is filed")
    title = " · ".join(bits)
    # No breakdown_html on purpose: with one, ui.score_cell becomes a
    # <details>, and a <details> inside the row's own summary is two
    # expanders fighting for one tap. The breakdown lives in the card.
    inner = _try("score_cell", proj, actual, None, title)
    if inner is None:
        a_html = ""
        if actual is not None:
            a_html = '<span class="home-score-a">%s</span>' % ui.esc(fmt_pts(actual))
        elif locked:
            a_html = '<span class="home-score-a home-score-na">—</span>'
        inner = ('<span class="home-score wr-num" title="%s">'
                 '<span class="home-score-p">%s</span>%s</span>'
                 % (ui.esc(title), ui.esc(fmt_pts(proj)), a_html))
    return '<span class="home-scorew">%s</span>' % inner


TREND_LEGEND = (
    ("trend_up", "the wire is adding him - the 24h add count is in the title"),
)


def legend_items() -> List[Tuple[str, str]]:
    """(icon name, meaning) - every GLYPH the page can print, in the shape
    ui.legend() and ui.legend_popover() take. The trend arrow's icon is
    listed only when the design system carries it (the fallback trend
    mark is a stat pill, which says its own word). The status pill, the
    news dot, the verdict chip and the meter carry their own words and
    titles and need no key."""
    have = set(ui.icon_names())
    items = [(n, m) for n, m in LEGEND if n in have]
    items.extend((n, m) for n, m in TREND_LEGEND if n in have)
    return items


def legend_pop_html() -> str:
    """The '?' at a section head. Fallback: a native <details> popover
    around ui.legend()."""
    items = legend_items()
    inner = _try("legend_popover", items)
    if inner is None:
        inner = ('<details class="wr-pop home-legend-pop">'
                 '<summary class="wr-pop-s" title="what the marks mean">'
                 '<span class="home-legend-q" aria-label="what the marks mean">'
                 '?</span></summary><div class="wr-pop-d">%s'
                 '<p class="wr-note">Hovering a mark names it; on a phone, '
                 'open any row — its card repeats every signal in words.</p>'
                 '</div></details>' % ui.legend(items))
    return '<span class="home-legend-w">%s</span>' % inner


def sheets_script_html() -> str:
    """ui.sheets_script() once per page, when the sheet has landed."""
    return _try("sheets_script") or ""


# --- the signal strip (pure) ------------------------------------------------

def contradicts_slot(row: Dict) -> bool:
    """Does the room's lean disagree with where this player is sitting?

    A starter the voices want benched, or a bench player they want started.
    This is the only kind of disagreement that implies an ACTION, so it is
    the one the row's flag and the inbox are both keyed to.
    """
    if row.get("open"):
        return False
    starting = row.get("group") == "STARTING"
    lean = row.get("lean")
    return (lean == "SIT" and starting) or (lean == "START" and not starting)


def signal_icons(row: Dict) -> List[Tuple[str, str, str]]:
    """(icon_name, title, tone) - the STATUS marks beside a name, in a
    FIXED order: dissent · injury · bye · news · hot backer · locked.

    The lean and the matchup are not here any more: the verdict chip and
    the matchup meter say them in their own columns. Fixed order is the
    whole trick - a reader scanning twenty rows compares like with like. A
    signal that is not true emits nothing at all; a greyed "no" glyph in
    every slot would be twenty times the ink for zero information.

    This is the full vocabulary. render_signals() draws the injury, bye and
    news entries as the status pill and the news dot instead of glyphs.
    """
    out: List[Tuple[str, str, str]] = []

    if int(row.get("level") or 0) >= board_mod.LVL_SPLIT:
        if int(row.get("level") or 0) >= board_mod.LVL_TOP:
            note = row.get("top_note") or "the top-weighted source dissents"
        else:
            note = ("the voices point both ways (%s) - %d%% of the weight is "
                    "on the losing side"
                    % (str(row.get("agreement") or "split").lower(),
                       int(row.get("split_weight") or 0)))
        out.append(("dissent", note, "warn"))

    status = (row.get("status") or "").strip()
    if status:
        red = status.lower() in RED_STATUSES
        out.append(("injury", "injury status filed: %s" % status,
                    "alarm" if red else "warn"))

    if row.get("bye") is True:
        out.append(("bye", "no game this week - he cannot score",
                    "alarm" if row.get("group") == "STARTING" else ""))

    quotes = row.get("quotes") or []
    if quotes:
        who = ", ".join(q[0] for q in quotes[:3])
        out.append(("news", "a creator filed a call in his own words: %s"
                    % who, "warn"))

    hot = row.get("hot_backers") or []
    if hot:
        out.append(("hot_streak",
                    "backed by a source on a hot run: %s" % ", ".join(hot),
                    "good"))

    if row.get("locked"):
        out.append(("locked", "his game has started - this is final", ""))

    return out


def row_tone(row: Dict) -> str:
    """The flag on a row - reserved for the two states worth a mark.

    'bad'   a STARTER carries a hard problem: no game, an out-class status,
            a filed zero, or an empty slot. Something is broken right now.
    'split' the room's lean CONTRADICTS where the player is sitting - a
            starter the voices want benched, a bench player they want
            started. That is the only disagreement that implies an action.

    Everything else is unmarked on purpose. A page where most rows carry
    the rule has taught its reader that the rule means nothing.
    """
    starting = row.get("group") == "STARTING"
    if starting:
        if row.get("open"):
            return "bad"
        if row.get("bye") is True:
            return "bad"
        if (row.get("status") or "").strip().lower() in RED_STATUSES:
            return "bad"
        if row.get("proj") == 0.0:
            return "bad"
    return "split" if contradicts_slot(row) else ""


def verdict_title(row: Dict) -> str:
    """What the verdict chip claims, in words, for its title."""
    lean = row.get("lean")
    if not lean:
        return ("no voice filed an opinion on him this week - silence, not "
                "agreement")
    bits = ["the room leans %s" % str(lean).lower()]
    if row.get("pct") is not None:
        bits.append("%d%% start-ward" % int(row["pct"]))
    voices = row.get("voices") or []
    if voices:
        bits.append("%d voice%s" % (len(voices), "" if len(voices) == 1 else "s"))
    if contradicts_slot(row):
        bits.append("he is %s" % ("in your lineup"
                                  if row.get("group") == "STARTING"
                                  else "on your bench"))
    return " · ".join(bits)


def chip_key(lean) -> Optional[str]:
    """The consensus verdict word -> ui.verdict_chip's key. Unknown stays
    unknown, and the chip then renders as 'no opinion filed'."""
    if lean is None:
        return None
    return {"START": "start", "SIT": "sit", "EVEN": "even"}.get(
        str(lean).strip().upper(), str(lean))


def opp_of(row: Dict) -> Tuple[str, Optional[bool]]:
    """(opponent, home?) from the row - the gathered keys first, else parsed
    out of the 'ATL vs XXX' meta a fixture carries. Unknown is ('', None)."""
    opp = row.get("opponent")
    if opp:
        return str(opp), row.get("home")
    bits = str(row.get("meta") or "").split()
    if len(bits) >= 3 and bits[-2] in ("vs", "@"):
        return bits[-1], bits[-2] == "vs"
    return "", None


def row_opp_label(row: Dict) -> str:
    """'vs PHI' / '@ DET' / 'BYE' / '' for the opponent chip."""
    if row.get("open"):
        return ""
    if row.get("bye") is True:
        return "BYE"
    opp, home = opp_of(row)
    if not opp:
        return ""
    return "%s %s" % ("vs" if home else "@", opp)


# --- the inbox (pure) -------------------------------------------------------

def short_matchup(m: Optional[Dict]) -> str:
    """The matchup read in one line, for the inbox and the meter's title.

    matchups.evidence_for writes the full sentence - rank, percentile, z,
    basis and caveat - which belongs in the row's card. This restates the
    same numbers from the same dict, and never drops the basis, because a
    grade built on last season that does not say so is the misleading half
    of the sentence.
    """
    m = m or {}
    if m.get("pa_per_game") is None or not m.get("pa_rank"):
        return m.get("reason") or ""
    # matchups ranks 1 = most points allowed, so the stingy end is the tail.
    tough = int(m["pa_of"]) - int(m["pa_rank"]) + 1
    return ("%s allowed %.1f pts/game to %s — %s-stingiest of %d, on %s."
            % (m.get("opponent") or "?", float(m["pa_per_game"]),
               m.get("pos") or "?", matchups_mod._ordinal(tough),
               int(m["pa_of"]), m.get("basis") or "an unnamed basis"))


def meter_title(row: Dict) -> str:
    m = row.get("matchup") or {}
    grade = m.get("pa_grade")
    if grade:
        return "matchup: %s vs %s — %s" % (grade, m.get("opponent") or "?",
                                          short_matchup(m))
    if m.get("reason"):
        return "matchup: not graded — %s" % m["reason"]
    return "matchup: not graded"


def _item(severity: str, ico: str, kind: str, snap: Dict, row: Dict,
          text: str, detail: str = "", subject: str = "", short: str = "",
          now: Optional[datetime] = None) -> Dict:
    item = {"severity": severity, "icon": ico, "kind": kind,
            "urgency": URGENCY_OF.get(kind, "week"),
            "league": snap.get("name") or "", "league_id": snap.get("id") or "",
            "text": text, "detail": detail, "anchor": row.get("anchor") or "",
            "subject": subject or row.get("name") or "", "short": short,
            "locked": row_locked(row, now) if row else False}
    item.update(verb_for(kind, snap))
    return item


def attention_items(snapshots: Sequence[Dict],
                    now: Optional[datetime] = None
                    ) -> Tuple[List[Dict], List[str]]:
    """(items, caveats) across every league.

    An item is a fact that is TRUE and that the user can act on before
    kickoff; each carries the verb and the host link to act on it, its
    urgency shelf, and whether its player's game has already started. A
    caveat is a check that could not run - the two are kept apart so a
    clean page can say "nothing needs you" without that sentence quietly
    absorbing "...as far as I could see, which was not far".
    """
    items: List[Dict] = []
    caveats: List[str] = []

    for snap in snapshots:
        if snap.get("error") is not None:
            caveats.append("%s could not be read at all (%s) - nothing about "
                           "that team was checked"
                           % (snap.get("name") or snap.get("id"),
                              snap.get("error_text") or "unknown error"))
            continue
        for why in snap.get("unchecked") or []:
            caveats.append("%s: %s" % (snap.get("name") or snap.get("id"), why))

        for row in snap.get("starters") or []:
            who = row.get("name") or "this slot"
            slot = row.get("slot") or row.get("pos") or ""

            if row.get("open"):
                items.append(_item(
                    "bad", "news", "open", snap, row,
                    "The %s slot is empty." % slot,
                    "No known player on the roster fits it - that is missing "
                    "roster data, not a benched player.",
                    subject="%s slot" % slot, short="empty", now=now))
                continue

            if row.get("bye") is True:
                items.append(_item(
                    "bad", "bye", "bye", snap, row,
                    "%s is on BYE and is in your starting lineup." % who,
                    "He has no week-%s game. Replace him before lock."
                    % snap.get("week"), short="on BYE, starting", now=now))

            status = (row.get("status") or "").strip()
            if status and status.lower() in RED_STATUSES:
                items.append(_item(
                    "bad", "injury", "out", snap, row,
                    "%s is %s and is starting." % (who, status.upper()),
                    "Replace him before lock.",
                    short="%s, starting" % status.upper(), now=now))
            elif status:
                items.append(_item(
                    "warn", "injury", "injury", snap, row,
                    "%s is %s." % (who, status),
                    "Check his status before kickoff.", short=status, now=now))

            if row.get("proj") == 0.0:
                # `sit` and not a "cold" glyph: a filed 0.0 is not a slump,
                # it is the feed saying he will not play.
                items.append(_item(
                    "bad", "sit", "zero", snap, row,
                    "%s projects 0.0 this week." % who,
                    "A filed zero means the feed expects him not to play.",
                    short="projects 0.0", now=now))
            elif row.get("proj") is None:
                items.append(_item(
                    "warn", "news", "noproj", snap, row,
                    "%s has no projection filed." % who,
                    "No feed filed a number for him - verify he is active.",
                    short="no projection filed", now=now))

            grade = (row.get("matchup") or {}).get("pa_grade")
            if grade == "AVOID":
                m = row.get("matchup") or {}
                items.append(_item(
                    "warn", "matchup_avoid", "avoid", snap, row,
                    "%s starts into an AVOID matchup vs %s."
                    % (who, m.get("opponent") or "?"),
                    short_matchup(m),
                    short="AVOID vs %s" % (m.get("opponent") or "?"), now=now))

        # DEF/K: a STREAM verdict is ONE item - the claim, with the host's
        # waiver page as its verb - and it stands in for BOTH the generic
        # wire claim on that position and the "room leans sit" split on
        # the held player's row, which would be the same fact twice. A
        # computed call of ANY verdict owns its position in the inbox: a
        # HOLD next to a rest-of-season "burn priority for a defense" item
        # would be the page arguing with itself, and the weekly,
        # opponent-aware call is the one the owner asked for.
        stream_pos = set()
        dk_pos = set()
        dk = snap.get("dk") or {}
        for slot in dk_mod.SLOTS:
            call = dk.get(slot) or {}
            if call.get("verdict") in ("HOLD", "STREAM", "TOSS-UP"):
                dk_pos.add(dk_mod.POS_OF[slot])
            if call.get("verdict") != "STREAM":
                if call.get("unverified") and call.get("best") and \
                        float(call.get("delta") or 0.0) >= \
                        dk_mod.STREAM_MARGIN.get(slot, 0.0):
                    caveats.append(
                        "%s: %s would beat %s by %+.1f this week, but %s - "
                        "no claim is surfaced"
                        % (snap.get("name") or snap.get("id"),
                           dk_mod._best_label(call),
                           call.get("held_short") or call.get("held")
                           or "your %s" % slot,
                           float(call.get("delta") or 0.0),
                           dk_mod.UNVERIFIED))
                continue
            pos = dk_mod.POS_OF[slot]
            stream_pos.add(pos)
            held_row = next((r for r in (snap.get("starters") or [])
                             if r.get("pos") == pos and not r.get("open")),
                            {})
            text, detail = dk_mod.inbox_item_text(call)
            items.append(_item(
                "warn", "waiver_add", "claim", snap, held_row, text, detail,
                subject=dk_mod._best_label(call),
                short="stream over %s %+.1f"
                      % (call.get("held_short") or call.get("held") or
                         "your %s" % slot, float(call.get("delta") or 0.0)),
                now=now))

        for row in (list(snap.get("starters") or [])
                    + list(snap.get("bench") or [])):
            if row.get("open"):
                continue
            if row.get("pos") in stream_pos:
                continue        # the stream item above IS this row's item
            level = int(row.get("level") or 0)
            if level < board_mod.LVL_SPLIT:
                continue
            starting = row.get("group") == "STARTING"
            contradicts = contradicts_slot(row)
            heavy = int(row.get("split_weight") or 0) >= SPLIT_ATTENTION
            if level < board_mod.LVL_TOP and not (contradicts or heavy):
                continue
            if contradicts:
                text = ("%s is %s but the room leans %s."
                        % (row.get("name"),
                           "in your lineup" if starting else "on your bench",
                           (row.get("lean") or "").lower()))
                short = ("room leans %s, he is %s"
                         % ((row.get("lean") or "").lower(),
                            "starting" if starting else "benched"))
            else:
                text = ("%s is a genuine start/sit split."
                        % row.get("name"))
                short = "genuine start/sit split"
            detail = row.get("top_note") or (
                "%d%% of the enabled weight is on the losing side of this "
                "call." % int(row.get("split_weight") or 0))
            items.append(_item("warn", "dissent", "split", snap, row, text,
                               detail, short=short, now=now))

        wire = snap.get("waivers") or {}
        # The same gate as _waiver_claims, held in the pure layer too: a
        # claim list built without rival rosters is not a list of free
        # agents, and never reaches the inbox.
        claims = wire.get("claims") if wire.get("rivals_known", True) else []
        for claim in claims or []:
            if claim.get("pos") in dk_pos:
                continue        # the DEF/K call owns this position's item
            where = ", ".join(x for x in (claim.get("pos"), claim.get("team"))
                              if x)
            band = claim.get("band") or "clears your starter's bar"
            items.append(_item(
                "warn", "waiver_add", "claim", snap, {},
                "%s%s is worth a claim — %s."
                % (claim.get("name") or "?", (" (%s)" % where) if where else "",
                   band),
                claim.get("detail") or "",
                subject=claim.get("name") or "?",
                short=" · ".join(x for x in (where, band) if x), now=now))

        for name in snap.get("unresolved") or []:
            items.append(_item(
                "warn", "news", "unresolved", snap, {},
                "“%s” on your roster matched no player." % name,
                "No voice - ours included - could vote on him, so he is "
                "absent from every read on this page.",
                subject=name, short="matched no player", now=now))

    items.sort(key=item_sort_key)
    return items, caveats


_URGENCY_ORDER = dict((k, i) for i, (k, _l, _n) in enumerate(URGENCY))
_SEVERITY_ORDER = {"bad": 0, "warn": 1}


def item_sort_key(item: Dict):
    """Shelf first (Do now · Before lock · This week), a started game to the
    bottom of its shelf, criticals above warnings, then by league."""
    return (_URGENCY_ORDER.get(item.get("urgency"), 9),
            1 if item.get("locked") else 0,
            _SEVERITY_ORDER.get(item.get("severity"), 2),
            item.get("league") or "")


def group_items(items: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """{shelf key: items on it}, every shelf present even when empty."""
    out: Dict[str, List[Dict]] = dict((k, []) for k, _l, _n in URGENCY)
    for it in items:
        out.setdefault(it.get("urgency") or "week", []).append(it)
    return out


# --- cross-league ownership (pure) -----------------------------------------

def _live_rows(snap: Dict) -> List[Dict]:
    return [r for r in (list(snap.get("starters") or [])
                        + list(snap.get("bench") or []))
            if not r.get("open")]


def cross_league(key: str, snapshots: Sequence[Dict],
                 exposure: Optional[Dict] = None) -> List[Dict]:
    """One entry per league the user plays, for a player key - empty when
    the user plays only one league, when there is nothing to cross.

    rostered: True  he is on YOUR roster there (the snapshot's own rows,
                    or engine/exposure's key set for that league)
              False he is not on your roster there - which is NOT "free
                    agent": a rival may hold him, and the host page says
              None  unknown: the league could not be read, or no roster
                    file exists for it
    """
    if not key or len(snapshots) < 2:
        return []
    rosters = dict((lid, keys) for lid, _n, keys in
                   ((exposure or {}).get("rosters") or []))
    out: List[Dict] = []
    for s in snapshots:
        lid = s.get("id") or ""
        e = {"id": lid, "name": s.get("name") or lid, "rostered": None,
             "group": None, "slot": "", "lean": None, "pct": None,
             "anchor": "", "locked": False, "note": "", "verbs": []}
        if s.get("error") is not None:
            e["note"] = "league could not be read"
            out.append(e)
            continue
        rows = _live_rows(s)
        row = next((r for r in rows if r.get("key") == key), None)
        if row is not None:
            e.update({"rostered": True, "group": row.get("group"),
                      "slot": row.get("slot") or row.get("pos") or "",
                      "lean": row.get("lean"), "pct": row.get("pct"),
                      "anchor": row.get("anchor") or "",
                      "locked": bool(row.get("locked"))})
        elif rows:
            e["rostered"] = False
        elif lid in rosters:
            e["rostered"] = key in rosters[lid]
        else:
            e["note"] = "no roster file for this league"
        if e["rostered"] is True:
            e["verbs"] = [xl_verb(v, t, s) for v, t in XL_VERBS_HELD]
        elif e["rostered"] is False:
            e["verbs"] = [xl_verb(v, t, s) for v, t in XL_VERBS_FREE]
        out.append(e)
    return out


# --- rendering (pure) -------------------------------------------------------

def render_signals(row: Dict) -> str:
    """The marks beside a name that are still GLYPHS: dissent, hot backer,
    locked. Injury and bye are the status pill; news is the dot."""
    strip = [(n, t, tone) for n, t, tone in signal_icons(row)
             if n not in ("injury", "bye", "news")]
    if not strip:
        return ""
    cells = "".join(
        '<span class="home-sig-i%s">%s</span>'
        % ((" home-sig-" + tone) if tone else "",
           ui.icon(name, 20, title=title))
        for name, title, tone in strip)
    return '<span class="home-sig">%s</span>' % cells


def render_status(row: Dict) -> str:
    """The status pill(s): the injury code, and BYE."""
    out = []
    status = (row.get("status") or "").strip()
    if status:
        red = status.lower() in RED_STATUSES
        out.append(status_pill_html(status, "injury status filed",
                                    "alarm" if red else "warn"))
    if row.get("bye") is True:
        out.append(status_pill_html(
            "BYE", "no game this week - he cannot score",
            "alarm" if row.get("group") == "STARTING" else ""))
    return "".join(out)


def is_unanimous(row: Dict) -> bool:
    """Nothing on this row asks for a look: no flag, no split, no status,
    a game to play. The preferences layer hides such rows under quiet
    mode (data-unanimous="1"); a row with any signal is never hidden."""
    if row.get("open") or row.get("bye") is True:
        return False
    if (row.get("status") or "").strip():
        return False
    if int(row.get("level") or 0) >= board_mod.LVL_SPLIT:
        return False
    if row_tone(row) or row.get("quotes") or row.get("hot_backers"):
        return False
    return row.get("lean") is not None


def render_context(row: Dict) -> str:
    """The 13px context line under the name: ESPN roster % and start % when
    the public feed has him, the slot when it differs from the position,
    and the trending-adds pill. Nothing is printed for a rate the feed did
    not file - the card says why."""
    bits = []
    own, start = row.get("own_pct"), row.get("start_pct")
    if own is not None:
        bits.append("rostered %d%%" % int(round(float(own))))
    if start is not None:
        bits.append("started %d%%" % int(round(float(start))))
    slot, pos = row.get("slot") or "", row.get("pos") or ""
    if row.get("group") == "STARTING" and slot and slot != pos:
        bits.append("%s slot" % slot)
    text = ""
    if bits:
        text = ('<span class="home-ctx-t" title="%s">%s</span>'
                % ("ESPN public roster and start rates, all ESPN leagues"
                   if (own is not None or start is not None) else "",
                   ui.esc(" · ".join(bits))))
    trend = ""
    adds = row.get("trend_adds")
    if adds:
        try:
            n = int(adds)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            trend = trend_html(n, "trending: %d adds on Sleeper in the last "
                                  "24 hours" % n)
    if not text and not trend:
        return ""
    return '<span class="home-ctx wr-t3">%s%s</span>' % (text, trend)


def page_links_pure(league_id: str, week) -> Dict[str, Dict]:
    """Board / Ledger / Trade Desk hrefs from ui.NAV_PAGES' own templates,
    existence unknown (None) - the fixture-side twin of page_links()."""
    out = {}
    for key, label, tpl in ui.NAV_PAGES:
        if key in ("board", "digest", "trades"):
            out[key] = {"label": label,
                        "href": tpl.format(league=league_id, week=int(week)),
                        "exists": None}
    return out


def _pages(snap: Dict) -> Dict[str, Dict]:
    pages = snap.get("pages")
    if pages:
        return pages
    pages = page_links_pure(snap.get("id") or "", snap.get("week") or 1)
    if snap.get("board_href"):
        pages["board"] = {"label": "Board", "href": snap["board_href"],
                          "exists": snap.get("board_exists")}
    return pages


def render_verb(v: Dict, extra_cls: str = "") -> str:
    """The 44x88 verb button. With a link it opens the host in a new tab;
    without one it is a ghost carrying the note, never a fabricated URL."""
    cls = ("home-act " + extra_cls).strip()
    if v.get("href"):
        return ('<a class="%s" href="%s" target="_blank" rel="noopener noreferrer" '
                'title="%s">%s</a>'
                % (cls, ui.esc(v["href"]), ui.esc(v.get("verb") or ""),
                   ui.esc(v.get("short_verb") or v.get("verb") or "Open")))
    return ('<span class="%s home-act-none" title="%s">%s'
            '<span class="home-act-nl wr-t4">no link</span></span>'
            % (cls, ui.esc(v.get("host_note") or "no link"),
               ui.esc(v.get("short_verb") or v.get("verb") or "Act")))


def render_cross_league(entries: Sequence[Dict], name: str) -> str:
    """The player card's cross-league block: one line per league."""
    if not entries:
        return ""
    lines = []
    for e in entries:
        if e["rostered"] is True:
            state = {"STARTING": "starting", "BENCH": "bench"}.get(
                e.get("group") or "", "held")
            where = " · ".join(x for x in (state, e.get("slot") or "") if x)
            if e.get("locked"):
                where += " · locked"
            chip = ui.verdict_chip(chip_key(e.get("lean")), e.get("pct"),
                                   size="sm",
                                   title="the room's verdict on him in %s"
                                         % e["name"])
        elif e["rostered"] is False:
            where, chip = "not rostered by you", ""
        else:
            where = "unknown — %s" % (e.get("note") or "not read")
            chip = ""
        acts = "".join(render_verb(v, "home-act-sm") for v in e.get("verbs") or [])
        lg = ui.esc(e["name"])
        if e.get("anchor"):
            lg = '<a class="home-xl-go" href="#%s">%s</a>' % (ui.esc(e["anchor"]), lg)
        lines.append('<div class="home-xl-r"><span class="home-xl-lg">%s</span>'
                     '<span class="home-xl-s wr-t3">%s</span>%s'
                     '<span class="home-xl-a">%s</span></div>'
                     % (lg, ui.esc(where), chip, acts))
    held = sum(1 for e in entries if e["rostered"] is True)
    note = ""
    if held >= 2:
        note = ('<p class="wr-note home-xl-risk">Correlated risk — %s is on %d '
                'of your rosters: one injury, one bad Sunday, lands on every '
                'one of them at once.</p>' % (ui.esc(name), held))
    return ('<div class="home-xl"><p><b>Across your leagues</b> — %s</p>%s%s'
            '</div>' % (ui.esc(name), "".join(lines), note))


def render_detail(snap: Dict, row: Dict, snapshots: Sequence[Dict] = (),
                  exposure: Optional[Dict] = None,
                  now: Optional[datetime] = None) -> str:
    """The words behind the marks - the player card.

    Every signal on the row is restated here as a sentence. That is not
    duplication - it is the only form of the strip that works on a phone,
    where nothing hovers, and the only form a screen reader reads in
    context. Then the cross-league block, when there is more than one
    league to cross.
    """
    parts: List[str] = []

    voices = row.get("voices") or []
    if row.get("lean"):
        tally = " · ".join("%s %s" % (ui.esc(n), ui.esc(v))
                           for n, v, _q in voices) or "no voice filed"
        pct = row.get("pct")
        parts.append(
            "<p><b>The room</b> — leans %s%s. %s</p>"
            % (ui.esc(row["lean"]),
               (" at %d%% start-ward" % int(pct)) if pct is not None else "",
               tally))
    else:
        parts.append("<p><b>The room</b> — no voice filed an opinion on him "
                     "this week. That is silence, not agreement.</p>")

    if int(row.get("level") or 0) >= board_mod.LVL_SPLIT:
        parts.append("<p><b>Disagreement</b> — %s.</p>"
                     % ui.esc(row.get("top_note")
                              or ("%s; %d%% of the weight is on the losing "
                                  "side"
                                  % (str(row.get("agreement") or "split")
                                     .lower(),
                                     int(row.get("split_weight") or 0)))))

    for who, verdict, quote in voices:
        if quote:
            parts.append('<p><b>%s</b> — %s: “%s”</p>'
                         % (ui.esc(who), ui.esc(verdict),
                            ui.esc(ui.trim(quote, 220))))

    parts.append("<p><b>Projection</b> — %s (%s scoring)%s.</p>"
                 % (ui.esc(fmt_pts(row.get("proj"))),
                    ui.esc(SCORING_LABEL.get(snap.get("scoring") or "",
                                             snap.get("scoring") or "")),
                    (" from %s" % ui.esc(row["proj_source"]))
                    if row.get("proj_source") else ""))
    if row.get("actual") is not None:
        parts.append("<p><b>Actual</b> — %s so far.</p>"
                     % ui.esc(fmt_pts(row["actual"])))

    m = row.get("matchup") or {}
    if m.get("evidence"):
        parts.append("<p><b>Matchup</b> — %s</p>" % ui.esc(m["evidence"]))
    elif m.get("reason"):
        parts.append("<p><b>Matchup</b> — %s.</p>" % ui.esc(m["reason"]))

    slot_key = dk_mod.SLOT_OF.get(row.get("pos") or "")
    call = (snap.get("dk") or {}).get(slot_key) if slot_key else None
    if call and row.get("group") == "STARTING":
        parts.append("<p><b>Hold or stream</b> — %s</p>"
                     % ui.esc(dk_mod.board_line(call)))

    status = (row.get("status") or "").strip()
    if status:
        parts.append("<p><b>Injury</b> — %s is filed against him. An absent "
                     "status is not a clean bill of health; it means no "
                     "report was filed.</p>" % ui.esc(status))

    own, start = row.get("own_pct"), row.get("start_pct")
    if own is not None or start is not None:
        parts.append("<p><b>Ownership</b> — rostered in %s of ESPN leagues, "
                     "started in %s (ESPN's public rates, every ESPN league, "
                     "not this one).</p>"
                     % ("%d%%" % int(round(float(own))) if own is not None
                        else "an unfiled share",
                        "%d%%" % int(round(float(start))) if start is not None
                        else "an unfiled share"))
    elif row.get("own_known"):
        parts.append("<p><b>Ownership</b> — ESPN filed no roster or start "
                     "rate for him (outside its public top 600).</p>")
    else:
        parts.append("<p><b>Ownership</b> — roster and start rates were not "
                     "read this render.</p>")
    adds = row.get("trend_adds")
    if adds:
        parts.append("<p><b>Trending</b> — %s adds on Sleeper in the last 24 "
                     "hours; the wire is moving on him.</p>"
                     % ui.esc(fmt_count(adds)))

    locked = row_locked(row, now)
    kick = kickoff_label(row.get("kickoff_iso") or "") or row.get("kickoff") or ""
    if row.get("bye") is True:
        parts.append("<p><b>Bye</b> — %s has no game in week %s.</p>"
                     % (ui.esc(row.get("team") or "his team"),
                        ui.esc(snap.get("week"))))
    elif kick:
        parts.append("<p><b>Kickoff</b> — %s%s</p>"
                     % (ui.esc(kick),
                        " (already started — this is final)."
                        if locked else "."))

    parts.append(render_cross_league(
        cross_league(row.get("key") or "", snapshots, exposure),
        row.get("name") or ""))

    board = _pages(snap).get("board") or {}
    if board.get("href"):
        note = ("" if board.get("exists") is not False else
                " — not generated yet: run <code>./board.sh %s %s</code>"
                % (ui.esc(snap.get("id")), ui.esc(snap.get("week"))))
        parts.append('<p><a class="home-link" href="%s">Full breakdown on '
                     'the board</a>%s</p>' % (ui.esc(board["href"]), note))
    return "".join(parts)


def render_row(snap: Dict, row: Dict, now: Optional[datetime] = None,
               snapshots: Sequence[Dict] = (),
               exposure: Optional[Dict] = None) -> str:
    """One roster line in the three-column anatomy: identity | middle |
    verdict, the whole line the tap target (44px floor, see _PAGE_CSS),
    opening the player card. A started game mutes the row."""
    open_ = bool(row.get("open"))
    name = row.get("name") or OPEN_SLOT
    tone = row_tone(row)
    locked = row_locked(row, now)
    cls = "home-r" + ((" home-r-flag home-r-%s" % tone) if tone else "") \
        + (" home-r-locked" if locked else "")
    anchor = row.get("anchor") or ""
    slot = row.get("slot") or ""
    pos = row.get("pos") or ""
    lrow = dict(row, locked=locked) if locked != bool(row.get("locked")) else row

    pos_cell = ui.pos_badge(pos, title=("%s slot" % slot) if slot else None)

    if open_:
        identity = ('%s<span class="home-name home-name-open wr-t2">%s</span>'
                    '<span class="home-ctx wr-t3"><span class="home-ctx-t">'
                    'nobody on the roster fits the %s slot</span></span>'
                    % (pos_cell, ui.esc(OPEN_SLOT), ui.esc(slot or pos)))
        line = ('<span class="home-r3"><span class="home-r3-id">%s</span>'
                '<span class="home-r3-mid"></span>'
                '<span class="home-r3-ver"></span></span>' % identity)
        return ('<div class="%s"%s data-player="">%s</div>'
                % (cls, (' id="%s"' % ui.esc(anchor)) if anchor else "", line))

    dot = ""
    if row.get("quotes"):
        who = ", ".join(q[0] for q in row["quotes"][:3])
        dot = news_dot_html("a creator filed a call in his own words: %s" % who)
    extras = (render_status(lrow) + dot + render_signals(lrow)
              + render_context(row))
    identity = _try("row3_identity", name, pos, None, extras)
    if identity is None:
        identity = ('%s<span class="home-name wr-t2">%s</span>%s'
                    % (pos_cell, ui.esc(name), extras))

    if row.get("bye") is True:
        middle = ('<span class="home-kick wr-t4" title="no game this week">'
                  'no game</span>%s' % score_html(snap, row, locked))
    else:
        kick = short_kick(row.get("kickoff_iso") or "")
        kick_title = kickoff_label(row.get("kickoff_iso") or "") \
            or row.get("kickoff") or ""
        if kick and not time_known(row.get("kickoff_iso") or ""):
            kick_title = "%s — time not filed by the schedule feed" % kick_title
        middle = ('%s%s%s'
                  % (opp_chip_html(row),
                     ('<span class="home-kick wr-t4" title="%s">%s</span>'
                      % (ui.esc(kick_title), ui.esc(kick))) if kick else "",
                     score_html(snap, row, locked)))

    verdict = (ui.verdict_chip(chip_key(row.get("lean")), row.get("pct"),
                               size="sm", title=verdict_title(row))
               + ui.matchup_meter((row.get("matchup") or {}).get("pa_grade"),
                                  label=False, title=meter_title(row),
                                  size="sm"))

    expanded = render_detail(snap, row, snapshots=snapshots,
                             exposure=exposure, now=now)
    # Composition, by what has landed: the three-column line is ui.row3
    # (else a local grid); the card behind it is ui.sheet (else row3's own
    # expander, else ui.popover). Never two expanders on one tap.
    line = _try("row3", identity, middle, verdict, None)
    if line is None:
        line = ('<span class="home-r3"><span class="home-r3-id">%s</span>'
                '<span class="home-r3-mid">%s</span>'
                '<span class="home-r3-ver">%s</span></span>'
                % (identity, middle, verdict))
    inner = _try("sheet", (anchor or "row") + "-card", name, expanded, line)
    if inner is None:
        inner = _try("row3", identity, middle, verdict, expanded)
    if inner is None:
        inner = ui.popover(line, expanded, cls="home-pop")

    return ('<div class="%s"%s data-player="%s"%s>%s</div>'
            % (cls, (' id="%s"' % ui.esc(anchor)) if anchor else "",
               ui.esc(str(name).lower()),
               ' data-unanimous="1"' if is_unanimous(row) else "", inner))


def quiet_note_html(hidden: int, what: str = "rows") -> str:
    """The one visible line quiet mode owes the reader, from engine/prefs.

    Optional layer: with prefs absent nothing is hidden either, so an empty
    string is correct rather than a silent omission."""
    if not hidden:
        return ""
    try:
        from engine import prefs as _prefs
        return _prefs.quiet_note(hidden, what)
    except Exception:  # noqa: BLE001 - the preferences layer is optional
        return ""


def render_roster(snap: Dict, now: Optional[datetime] = None,
                  snapshots: Sequence[Dict] = (),
                  exposure: Optional[Dict] = None) -> str:
    """Starters then bench, as three-column rows under a head that carries
    the '?' legend."""
    groups = [(label, snap.get(key) or [])
              for label, key in (("Starting", "starters"), ("Bench", "bench"))]
    if not any(rows for _, rows in groups):
        return ""
    body: List[str] = []
    quiet_n = 0
    for label, rows in groups:
        if not rows:
            continue
        body.append('<div class="home-grp">%s <span class="wr-num">%d</span>'
                    '</div>' % (ui.esc(label), len(rows)))
        for r in rows:
            if is_unanimous(r):
                quiet_n += 1
            body.append(render_row(snap, r, now=now, snapshots=snapshots,
                                   exposure=exposure))
    head = ('<div class="home-roster-h"><span class="wr-sec-h">Roster</span>'
            '<span class="home-roster-n wr-t3">%d starting · %d bench</span>%s'
            '</div>' % (len(groups[0][1]), len(groups[1][1]), legend_pop_html()))
    # QUIET MODE owes the reader a line. Rows marked data-unanimous="1" are
    # folded away by engine/prefs' stylesheet; without this count a quiet
    # roster would read as a SHORTER roster, which is a lie about what the
    # room said. The note itself is hidden until quiet mode is on (CSS).
    return ('%s%s<div class="home-roster" role="list">%s</div>'
            % (head, quiet_note_html(quiet_n, "roster rows"), "".join(body)))


def render_item(it: Dict, hidden: bool = False) -> str:
    """One inbox row, ONE line: glyph · league tag + subject + a few words ·
    the verb button. The fact links to its roster row on this page; the
    verb opens the host in a new tab, since the host is where the decision
    is made and this page is where it was found. A started game mutes the
    row and turns the verb into a lock."""
    full = "%s — %s" % (it["text"], ui.trim(it.get("detail") or "", 170)) \
        if it.get("detail") else it["text"]
    ico = "locked" if it.get("locked") else it["icon"]
    inner = ('%s<span class="home-att-l">'
             '<span class="home-att-lg wr-t4">%s</span>'
             '<span class="home-att-s wr-t2">%s</span>'
             '<span class="home-att-w wr-t3">%s</span></span>'
             % (ui.icon(ico, 20, title="%s — %s" % (it["severity"], it["text"])),
                ui.esc(it["league"]), ui.esc(it.get("subject") or it["text"]),
                ui.esc(it.get("short") or "")))
    if it.get("anchor"):
        fact = ('<a class="home-att-go" href="#%s" title="%s">%s</a>'
                % (ui.esc(it["anchor"]), ui.esc(full), inner))
    else:
        fact = '<div class="home-att-go" title="%s">%s</div>' % (ui.esc(full), inner)
    if it.get("locked"):
        act = ('<span class="home-act home-act-locked" title="his game has '
               'started - this is final">Locked</span>')
    else:
        act = render_verb(it)
    cls = "home-att-item home-att-%s home-att-u-%s" % (
        ui.esc(it["severity"]), ui.esc(it.get("urgency") or "week"))
    if it.get("locked"):
        cls += " home-att-locked"
    if hidden:
        cls += " home-inb-x"
    return '<li class="%s">%s%s</li>' % (cls, fact, act)


def render_attention(items: Sequence[Dict], caveats: Sequence[str],
                     checked: Dict) -> str:
    """The inbox card: three urgency shelves with counts, or an honest
    all-clear. On a phone the first STACK_VISIBLE rows show and the rest
    sit behind 'show N more'; the sidebar shows every row (CSS)."""
    n = len(items)
    head = ('<header class="wr-sec home-inb-head"><h2 class="wr-sec-h">'
            'Needs you <span class="wr-sec-n">%s</span></h2>%s</header>'
            % (ui.esc(("%d item%s" % (n, "" if n == 1 else "s")) if items
                      else "across every league"),
               legend_pop_html()))

    body: List[str] = []
    if items:
        shown = list(items[:ATTENTION_MAX])
        rest = list(items[len(shown):])
        by = group_items(items)
        shown_by = group_items(shown)
        seen = 0
        shelves = []
        for key, label, note in URGENCY:
            total = len(by.get(key) or [])
            rows = shown_by.get(key) or []
            lis = []
            for it in rows:
                lis.append(render_item(it, hidden=seen >= STACK_VISIBLE))
                seen += 1
            if lis:
                content = '<ul class="home-att">%s</ul>' % "".join(lis)
            elif total:
                content = ('<p class="home-inb-empty wr-t3">%d below, in the '
                           'disclosure</p>' % total)
            else:
                content = '<p class="home-inb-empty wr-t3">nothing</p>'
            shelves.append(
                '<section class="home-inb-g home-inb-g-%s">'
                '<h3 class="home-inb-h wr-t4" title="%s">%s'
                '<span class="home-inb-n wr-num">%d</span></h3>%s</section>'
                % (key, ui.esc(note), ui.esc(label), total, content))
        more = ""
        if len(shown) > STACK_VISIBLE:
            k = len(shown) - STACK_VISIBLE
            more = ('<details class="wr-pop home-inb-more"><summary class="wr-pop-s">'
                    '<span class="home-inb-more-o">show %d more</span>'
                    '<span class="home-inb-more-c">show fewer</span></summary>'
                    '<div class="wr-pop-d"></div></details>' % k)
        body.append('<div class="home-inb">%s%s</div>' % ("".join(shelves), more))
        if rest:
            body.append(ui.popover(
                '<span class="home-att-more">%d more warning%s not listed '
                'above — show them</span>'
                % (len(rest), "" if len(rest) == 1 else "s"),
                '<ul class="home-att">%s</ul>'
                % "".join(render_item(it) for it in rest),
                cls="home-att-over"))
    elif not checked.get("leagues"):
        # An empty list of problems has two unrelated causes - every team was
        # checked and every team is fine, or NOTHING was checked - and the
        # all-clear must never be printed when it means the second.
        body.append(ui.banner(
            "Nothing could be checked — no league was readable, so this page "
            "is not telling you your teams are fine. It is telling you it "
            "could not look.", tone="bad", ico="news"))
    else:
        body.append(ui.banner(
            "Nothing needs you — %d starter%s checked across %d league%s."
            % (checked.get("starters", 0),
               "" if checked.get("starters") == 1 else "s",
               checked.get("leagues", 0),
               "" if checked.get("leagues") == 1 else "s"),
            tone="good", ico="consensus"))

    if caveats:
        body.append(ui.banner(
            "Some checks did not run, so this is not a clean bill of health: "
            + "; ".join(caveats) + ".", tone="warn"))
    return ('<section class="wr-card home-attention" id="home-inbox">%s%s'
            '</section>' % (head, "".join(body)))


def render_header(week, snapshots: Sequence[Dict], now: datetime) -> str:
    return ('<header class="home-head"><p class="wr-kicker">Your teams</p>'
            '<h1 class="wr-h1 wr-display">Week %s</h1>'
            '<p class="home-line wr-t3"><span>%s</span><span>week %s</span>'
            '<span class="home-lock">%s</span></p></header>'
            % (ui.esc(week), ui.esc(today_label(now)), ui.esc(week),
               ui.esc(lock_line(snapshots, now))))


def render_strip(snapshots: Sequence[Dict], now: datetime) -> str:
    """The game windows as a horizontal strip; the first-lock window under
    the gold rule. Degrades to a stated absence when no kickoff was filed."""
    ww = week_windows(snapshots)
    head = ui.section_header("The week", "game windows, first lock marked"
                             if ww["known"] else None)
    if not ww["known"]:
        body = ui.banner("Game windows unknown — the schedule feed filed no "
                         "kickoff, so nothing here is derived and no window "
                         "is assumed.", tone="warn")
        return '<section class="wr-card home-week">%s%s</section>' % (head, body)

    labels = short_labels(snapshots)
    many = len([s for s in snapshots if s.get("error") is None]) > 1
    cells = []
    for w in ww["windows"]:
        first = w["key"] == ww["first_key"]
        past = is_locked(w["first_iso"], now)
        per = ""
        if many and w["per_league"]:
            per = ('<div class="home-win-per">%s</div>'
                   % " · ".join("%s %d" % (ui.esc(labels.get(n, n)), k)
                                for n, k in sorted(w["per_league"].items())))
        when = lock_label(w["first_iso"])
        cells.append(
            '<div class="home-win%s%s">'
            '<div class="home-win-l">%s%s</div>'
            '<div class="home-win-t">%s · %d game%s%s</div>'
            '<div class="home-win-n"><b class="wr-num">%d</b>'
            '<span>of your starters</span></div>%s</div>'
            % (" home-win-first" if first else "",
               " home-win-past" if past else "",
               ui.esc(w["label"]),
               ' <span class="home-win-k">first lock</span>' if first else "",
               ui.esc(when), w["games"], "" if w["games"] == 1 else "s",
               " · kicked off" if past else "",
               w["starters"], per))
    notes = []
    if ww["byes"]:
        notes.append("%d of your starters ha%s no game this week (bye) and "
                     "%s in no window above." %
                     (ww["byes"], "s" if ww["byes"] == 1 else "ve",
                      "is" if ww["byes"] == 1 else "are"))
    if any("tbd" in w["key"] for w in ww["windows"]):
        notes.append("A window marked 'time not filed' has a day but no "
                     "clock in the schedule feed; the page shows the day "
                     "and invents nothing.")
    return ('<section class="wr-card home-week">%s'
            '<div class="home-strip">%s</div>%s</section>'
            % (head, "".join(cells),
               "".join('<p class="wr-note">%s</p>' % ui.esc(n) for n in notes)))


def lineup_total(snap: Dict) -> Tuple[Optional[float], int, int]:
    """(sum of starters' projections, starters with a number, starters).

    None means no starter had a projection at all. A partial sum is still
    reported - beside the count it rests on, never as the whole lineup."""
    starters = [r for r in snap.get("starters") or [] if not r.get("open")]
    vals = []
    for r in starters:
        v = r.get("proj")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(float(v))
    return (sum(vals) if vals else None), len(vals), len(starters)


def render_league(snap: Dict, now: Optional[datetime] = None,
                  snapshots: Sequence[Dict] = (),
                  exposure: Optional[Dict] = None) -> str:
    """One league card: head, record, coverage, projected total, page links,
    the roster. id="league-<id>" so the shell's switcher lands here."""
    lid = snap.get("id") or ""
    if snap.get("error") is not None:
        return ('<section class="wr-card home-league" id="league-%s">%s%s'
                '</section>'
                % (ui.esc(lid), ui.section_header(snap.get("name") or lid),
                   ui.degraded_banner("this whole league section",
                                      snap["error"])))

    platform = str(snap.get("platform") or "").strip().lower()
    bits = [PLATFORM_LABEL.get(platform) or (platform or "platform unknown")]
    if snap.get("teams"):
        bits.append("%d teams" % snap["teams"])
    scoring = SCORING_LABEL.get(snap.get("scoring") or "",
                                snap.get("scoring") or "")
    if scoring:
        bits.append(scoring)
    bits.append("week %s" % snap.get("week"))
    rec = str(snap.get("record") or "").strip()
    if not rec or rec.lower().startswith("not tracked"):
        rec_html = ('<span class="home-rec" title="%s">record not tracked</span>'
                    % ui.esc(rec or "no standings feed connected"))
    else:
        rec_html = '<span class="home-rec">record <b class="wr-num">%s</b></span>' \
            % ui.esc(rec)

    total, n_proj, n_start = lineup_total(snap)
    if total is None:
        total_html = '<span class="wr-num">—</span>'
        total_sub = ("no starter has a projection filed" if n_start
                     else "no starters known")
    else:
        total_html = '<span class="wr-num">%.1f</span>' % total
        total_sub = "projected starting lineup"
        if n_proj != n_start:
            total_sub += " · %d of %d starters projected" % (n_proj, n_start)

    links = []
    for key in ("board", "digest", "trades"):
        pg = _pages(snap).get(key)
        if not pg:
            continue
        tail = ""
        if pg.get("exists") is False:
            tail = ' title="not generated yet"'
        links.append('<a href="%s"%s>%s%s</a>'
                     % (ui.esc(pg["href"]), tail, ui.esc(pg["label"]),
                        ' <span class="home-lg-miss">(not built yet)</span>'
                        if pg.get("exists") is False else ""))
    team_href = host_link(snap, "team")
    if team_href:
        links.append('<a href="%s" target="_blank" rel="noopener noreferrer">Your team on '
                     '%s</a>' % (ui.esc(team_href),
                                 ui.esc(PLATFORM_LABEL.get(platform, "the host"))))
    else:
        links.append('<span class="home-lg-nohost">%s</span>'
                     % ui.esc(host_note(snap)))

    notes = list(snap.get("notes") or [])
    wv = snap.get("waivers")
    if isinstance(wv, dict):
        n = len(wv.get("claims") or []) if wv.get("rivals_known", True) else 0
        if not wv.get("rivals_known", True):
            notes.append("Waiver wire read, but the other teams' rosters are "
                         "unknown for this league, so no claim is surfaced — "
                         "without them the wire cannot tell a free agent from "
                         "a rostered star (%d names in the pool)."
                         % int(wv.get("pool") or 0))
        elif n:
            notes.append("Waiver wire: %d free agent%s worth a claim — in the "
                         "inbox." % (n, "" if n == 1 else "s"))
        else:
            notes.append("Waiver wire read: no free agent clears your "
                         "starters' bar this week (%d in the pool)."
                         % int(wv.get("pool") or 0))

    head = (
        '<header class="home-lg-head"><div class="home-lg-id">'
        '<h2 class="wr-display home-lg-name">%s</h2>'
        '<p class="home-lg-meta wr-t3">%s · %s</p></div>'
        '<div class="home-lg-proj">%s<span>%s</span></div></header>'
        '<nav class="home-lg-links" aria-label="%s pages">%s</nav>%s'
        % (ui.esc(snap.get("name") or lid), " · ".join(ui.esc(b) for b in bits),
           rec_html, total_html, ui.esc(total_sub),
           ui.esc(snap.get("name") or lid), "".join(links),
           "".join('<p class="wr-note">%s</p>' % ui.esc(n) for n in notes)))

    degraded = "".join(ui.degraded_banner(title, err)
                       for title, err in (snap.get("degraded") or []))
    unresolved = ""
    if snap.get("unresolved"):
        unresolved = ('<p class="wr-note">%d roster name(s) matched no known '
                      'player and are listed nowhere above, not dropped '
                      'silently: %s</p>'
                      % (len(snap["unresolved"]),
                         ui.esc(", ".join(snap["unresolved"]))))
    return ('<section class="wr-card home-league" id="league-%s">%s%s%s%s'
            '</section>'
            % (ui.esc(lid), head, degraded,
               render_roster(snap, now=now, snapshots=snapshots,
                             exposure=exposure), unresolved))


def exposure_overlap(exposure: Optional[Dict],
                     snapshots: Sequence[Dict]) -> List[Dict]:
    """Players on MORE THAN ONE of your rosters, from engine/exposure's
    per-league key sets, named from the snapshot rows that carry them.

    Positive-only, like the module it reads: a player absent from a partial
    roster file is unknown, not single-held, and the coverage banner rides
    with the ribbon for that reason.
    """
    rosters = (exposure or {}).get("rosters") or []
    if len(rosters) < 2:
        return []
    holders: Dict[str, List[Tuple[str, str]]] = {}
    for lid, lname, keys in rosters:
        for key in keys:
            holders.setdefault(key, []).append((lid, lname))
    rows_by: Dict[Tuple[str, str], Dict] = {}
    for snap in snapshots:
        for row in (list(snap.get("starters") or [])
                    + list(snap.get("bench") or [])):
            if row.get("key"):
                rows_by[(snap.get("id") or "", row["key"])] = row
    out = []
    for key, held in holders.items():
        if len(set(lid for lid, _ in held)) < 2:
            continue
        rows = [rows_by.get((lid, key)) for lid, _ in held]
        row = next((r for r in rows if r), None)
        nkey, _, pos = key.partition("|")
        entry = {
            "key": key,
            "name": (row or {}).get("name") or nkey.title(),
            "pos": (row or {}).get("pos") or pos,
            "team": (row or {}).get("team") or "",
            "leagues": [{"id": lid, "name": lname,
                         "group": (r or {}).get("group")}
                        for (lid, lname), r in zip(held, rows)],
        }
        out.append(entry)
    out.sort(key=lambda e: (str(e["pos"]), str(e["name"]).lower()))
    return out


def render_exposure(overlap: Sequence[Dict], banner: str = "") -> str:
    """The ribbon - one line - only when there is overlap."""
    if not overlap:
        return ""
    parts = []
    for e in overlap:
        where = []
        for lg in e["leagues"]:
            state = {"STARTING": "starts", "BENCH": "benched"}.get(
                lg.get("group") or "", "held")
            where.append("%s in %s" % (state, ui.esc(lg.get("name") or lg.get("id"))))
        parts.append('<span class="home-expo-p"><b>%s</b> %s <span class="home-expo-w">%s</span></span>'
                     % (ui.esc(e["name"]), ui.pos_badge(e["pos"]),
                        "; ".join(where)))
    n = len(overlap)
    note = ("Correlated risk: one injury, one bad Sunday, lands on every "
            "team at once — %d player%s doubled across your rosters."
            % (n, "" if n == 1 else "s"))
    return ('<section class="wr-card home-expo">%s'
            '<p class="home-expo-line">%s</p><p class="wr-note">%s</p>%s'
            '</section>'
            % (ui.section_header("Exposure", "%d shared" % n),
               " · ".join(parts), ui.esc(note),
               ('<p class="wr-note">%s</p>' % ui.esc(banner)) if banner else ""))


def source_pulse(snapshots: Sequence[Dict]) -> Dict:
    """Every enabled source once, heaviest first, with its CURRENT-form
    state per league (performance.source_scoreboard's `state`)."""
    live = [s for s in snapshots if s.get("error") is None]
    read = any(s.get("scoreboard") is not None for s in live)
    by: Dict[str, Dict] = {}
    for s in live:
        lname = s.get("name") or s.get("id") or "?"
        for r in s.get("scoreboard") or []:
            sid = r.get("source") or r.get("name") or "?"
            e = by.setdefault(sid, {"id": sid, "name": r.get("name") or sid,
                                    "type": r.get("type") or "",
                                    "weight": r.get("weight"),
                                    "states": {}, "reasons": {}})
            e["states"][lname] = r.get("state") or "NO-DATA"
            e["reasons"][lname] = r.get("state_reason") or ""
    rows = sorted(by.values(),
                  key=lambda e: (-float(e["weight"] or 0),
                                 str(e["name"]).lower()))
    for e in rows:
        states = set(e["states"].values())
        e["state"] = states.pop() if len(states) == 1 else "MIXED"
    return {"read": read, "rows": rows}


def render_pulse(pulse: Dict) -> str:
    rows = pulse.get("rows") or []
    head = ui.section_header("Source pulse",
                             ("%d enabled" % len(rows)) if rows else None)
    body: List[str] = []
    if not pulse.get("read"):
        body.append(ui.banner("Source form was not read — no voice's current "
                              "form is known, and none is assumed steady.",
                              tone="warn"))
    elif not rows:
        body.append(ui.banner("No enabled source — the room is empty "
                              "(data/sources.yaml).", tone="warn"))
    else:
        plates = "".join(
            ui.nameplate({"id": e["id"], "name": e["name"], "type": e["type"]},
                         weight=e["weight"], state=e["state"], size=38,
                         compact=True, href="sources.html")
            for e in rows)
        body.append('<div class="home-pulse-row">%s</div>' % plates)
        if all(e["state"] == "NO-DATA" for e in rows):
            body.append('<p class="wr-note">No voice has a current-form read '
                        'yet — the ledger is empty until a week is played. '
                        'That is a fact about the record, not about the '
                        'sources.</p>')
        mixed = [e for e in rows if e["state"] == "MIXED"]
        if mixed:
            body.append('<p class="wr-note">Form differs by league: %s.</p>'
                        % ui.esc("; ".join(
                            "%s — %s" % (e["name"], ", ".join(
                                "%s %s" % (lg, st)
                                for lg, st in sorted(e["states"].items())))
                            for e in mixed)))
    body.append('<p class="home-more"><a class="home-link" href="sources.html">'
                'Every source — weight, record and form</a></p>')
    return '<section class="wr-card home-pulse">%s%s</section>' % (
        head, "".join(body))


def render_jump() -> str:
    """The filter box. `hidden` until the script below removes it, so a
    reader without JS never sees an input that does nothing."""
    return ('<div class="home-jump" id="home-jump" hidden>'
            '<label class="home-jump-l" for="home-jump-q">Jump to a player'
            '</label>'
            '<input class="home-jump-q" id="home-jump-q" type="search" '
            'autocomplete="off" spellcheck="false" '
            'placeholder="type a name — filters every roster below">'
            '<span class="home-jump-n wr-num" id="home-jump-n" '
            'aria-live="polite"></span></div>')


# Vanilla, a dozen lines, no framework: reveal the box, then hide any roster
# row whose data-player does not contain the query. Nothing else on the
# page depends on it.
_JUMP_JS = """(function(){
var box=document.getElementById("home-jump"),q=document.getElementById("home-jump-q"),n=document.getElementById("home-jump-n");
if(!box||!q||!n)return;
box.hidden=false;
var rows=[].slice.call(document.querySelectorAll(".home-r[data-player]"));
q.addEventListener("input",function(){
  var s=q.value.trim().toLowerCase(),hit=0;
  rows.forEach(function(el){var on=!s||el.getAttribute("data-player").indexOf(s)>=0;el.hidden=!on;if(on)hit++;});
  n.textContent=s?(hit+" of "+rows.length):"";
});
})();"""


_PAGE_CSS = """
  /* ------------------------------------------------------------------ *
   * LAYOUT ONLY. Every colour below is a var(--wr-*) token from
   * engine/ui.py; this file declares no palette and draws no artwork.
   * Components ui.py lacks are built here from its tokens: the inbox verb
   * (.home-act - a gold GHOST button, never a fill: fill is the START
   * verdict's), the week-strip window (.home-win - the first lock carries
   * the gold rule, the identity's mark for attention), and the fallbacks
   * for the v4 vocabulary (.home-st, .home-dot, .home-oppc, .home-score,
   * .home-legend-pop) used only until engine/ui carries them.
   * Type scale 17 / 15 / 13 / 11 - nothing here is set below 11px.
   * Widths are relative or max-* so a 390px phone never scrolls sideways.
   * ------------------------------------------------------------------ */
  .home-head { margin: 0 0 16px; }
  .home-line {
    display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 6px 0 0;
    color: var(--wr-muted); font-size: 13px;
  }
  .home-lock { color: var(--wr-text); font-weight: 600;
               box-shadow: inset 0 -2px 0 var(--wr-rule); }

  /* the frame: one column; from 1000px the inbox is a sticky side rail
     beside the roster content unless the preferences layer stamps
     data-inbox="top" on <html> ---------------------------------------- */
  .home-grid { display: block; }
  .home-side { margin: 0 0 14px; min-width: 0; }
  .home-main { min-width: 0; }
  @media (min-width: 1000px) {
    :root:not([data-inbox="top"]) .home-grid {
      display: grid; grid-template-columns: minmax(0, 1fr) 320px;
      gap: 0 18px; align-items: start;
    }
    :root:not([data-inbox="top"]) .home-main { grid-column: 1; grid-row: 1; }
    :root:not([data-inbox="top"]) .home-side {
      grid-column: 2; grid-row: 1; margin: 0;
      position: sticky; top: 66px; max-height: calc(100vh - 80px);
      overflow-y: auto;
    }
    :root:not([data-inbox="top"]) .home-inb-x { display: flex; }
    :root:not([data-inbox="top"]) .home-inb-more { display: none; }
  }

  /* the inbox: three shelves, one line per item ------------------------ */
  .home-inb-head { display: flex; align-items: center; gap: 8px; }
  .home-inb-head .wr-sec-h { flex: 1 1 auto; }
  .home-inb-h {
    display: flex; align-items: center; gap: 6px; margin: 10px 0 2px;
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    font-weight: 700; color: var(--wr-muted);
  }
  .home-inb-g-now .home-inb-h { color: var(--wr-gold); }
  .home-inb-n {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px;
    background: var(--wr-raised); border: 1px solid var(--wr-hairline-2);
    color: var(--wr-text); font-size: 11px; letter-spacing: 0;
  }
  .home-inb-g-now .home-inb-n { background: var(--wr-chip-start);
                                border-color: var(--wr-chip-start);
                                color: var(--wr-chip-ink); }
  .home-inb-empty { margin: 2px 0 0; color: var(--wr-dim); font-size: 13px; }
  .home-att { list-style: none; margin: 0; padding: 0; }
  .home-att-item {
    display: flex; align-items: center; gap: 8px;
    padding: 2px 0; border-bottom: 1px solid var(--wr-hairline);
  }
  .home-att-item:last-child { border-bottom: none; }
  /* stacked: rows past the first three hide behind the disclosure; a
     browser without :has() shows them all - more ink, nothing hidden */
  .home-inb-x { display: none; }
  .home-inb:has(.home-inb-more[open]) .home-inb-x { display: flex; }
  @supports not selector(:has(*)) {
    .home-inb-x { display: flex; }
    .home-inb-more { display: none; }
  }
  .home-inb-more { border-top: none; }
  .home-inb-more > .wr-pop-d { display: none; }
  .home-inb-more > .wr-pop-s { min-height: 44px; color: var(--wr-muted);
                               font-size: 13px; }
  .home-inb-more-c, .home-inb-more[open] .home-inb-more-o { display: none; }
  .home-inb-more[open] .home-inb-more-c { display: inline; }
  .home-att-go {
    display: flex; align-items: center; gap: 8px; flex: 1 1 auto;
    min-width: 0; min-height: 44px; padding: 4px 2px 4px 8px;
    color: var(--wr-text); text-decoration: none;
    box-shadow: inset 3px 0 0 var(--wr-rule);
  }
  .home-att-warn .home-att-go { box-shadow: inset 2px 0 0 var(--wr-gold); }
  .home-att-bad .wr-icon { color: var(--wr-text); }
  .home-att-warn .wr-icon { color: var(--wr-gold); }
  .home-att-l { display: flex; flex-direction: column; min-width: 0;
                line-height: 1.25; }
  .home-att-lg {
    font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--wr-dim);
  }
  .home-att-s { font-size: 15px; font-weight: 700; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
  .home-att-w { font-size: 13px; color: var(--wr-muted); white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
  a.home-att-go:hover, a.home-att-go:focus-visible { background: var(--wr-raised); }
  .home-act {
    display: inline-flex; align-items: center; justify-content: center;
    flex-direction: column; min-height: 44px; min-width: 88px;
    padding: 0 12px; flex: none;
    border: 1px solid var(--wr-gold); border-radius: 6px;
    color: var(--wr-gold); font-weight: 700; font-size: 13px;
    letter-spacing: 0.02em; text-decoration: none; white-space: nowrap;
    line-height: 1.2;
  }
  .home-act:hover, .home-act:focus-visible { background: var(--wr-wash-hot); }
  .home-act-locked, .home-act-none { border-color: var(--wr-hairline-2);
                                     color: var(--wr-dim); }
  .home-act-none { border-style: dashed; }
  .home-act-nl { font-size: 11px; font-weight: 400; letter-spacing: 0; }
  .home-att-locked { opacity: 0.55; }
  .home-att-more { color: var(--wr-muted); font-size: 13px; }
  .home-att-over { margin-top: 6px; }
  :root[data-quiet="1"] .home-inb-g-week { opacity: 0.75; }

  /* the week strip ----------------------------------------------------- */
  .home-strip {
    display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 8px;
    scroll-snap-type: x proximity; -webkit-overflow-scrolling: touch;
  }
  .home-win {
    flex: 1 0 8.5rem; min-width: 8.5rem; scroll-snap-align: start;
    border: 1px solid var(--wr-hairline); border-radius: 8px;
    padding: 9px 11px; background: var(--wr-raised);
  }
  .home-win-first { border-color: var(--wr-rule);
                    box-shadow: inset 0 3px 0 var(--wr-rule); }
  .home-win-past { opacity: 0.6; }
  .home-win-l {
    font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
    font-weight: 700; color: var(--wr-muted);
  }
  .home-win-first .home-win-l { color: var(--wr-gold); }
  .home-win-k { font-weight: 600; letter-spacing: 0.04em; text-transform: none; }
  .home-win-t { color: var(--wr-dim); font-size: 11px; margin-top: 2px;
                white-space: nowrap; }
  .home-win-n { display: flex; align-items: baseline; gap: 6px; margin-top: 6px; }
  .home-win-n b { font-size: 20px; font-weight: 600; line-height: 1; }
  .home-win-n span { color: var(--wr-dim); font-size: 11px; }
  .home-win-per { color: var(--wr-muted); font-size: 11px; margin-top: 4px; }

  /* league cards ------------------------------------------------------- */
  /* anchor clearance is the shell's (ui.py: html { scroll-padding-top }),
     so every #id on every page clears the same bar by the same amount. */
  .home-lg-head {
    display: flex; flex-wrap: wrap; align-items: flex-start;
    justify-content: space-between; gap: 8px 18px;
  }
  .home-lg-id { min-width: 0; flex: 1 1 16rem; }
  .home-lg-name { margin: 0; font-size: 20px; line-height: 1.2;
                  overflow-wrap: anywhere; }
  .home-lg-meta { margin: 3px 0 0; color: var(--wr-muted); font-size: 13px; }
  .home-rec b { color: var(--wr-text); }
  .home-lg-proj { text-align: right; flex: none; }
  .home-lg-proj .wr-num { display: block; font-size: 26px; font-weight: 600;
                          line-height: 1; }
  .home-lg-proj span:last-child {
    display: block; margin-top: 3px; font-size: 11px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--wr-dim);
  }
  .home-lg-links { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 0; }
  .home-lg-links a {
    display: inline-flex; align-items: center; min-height: 44px;
    padding: 0 12px; border: 1px solid var(--wr-hairline-2);
    border-radius: 6px; color: var(--wr-text); text-decoration: none;
    font-weight: 600; font-size: 13px;
  }
  .home-lg-links a:hover, .home-lg-links a:focus-visible {
    border-color: var(--wr-gold);
  }
  .home-lg-miss { color: var(--wr-dim); font-weight: 400; margin-left: 4px; }
  .home-lg-nohost { display: inline-flex; align-items: center; min-height: 44px;
                    color: var(--wr-dim); font-size: 11px; }

  /* roster rows: identity | middle | verdict --------------------------- */
  /* 44px is the floor for a finger, and the row is the tap target. */
  .home-roster-h { display: flex; align-items: center; gap: 8px; margin: 12px 0 0; }
  .home-roster-h .wr-sec-h { margin: 0; }
  .home-roster-n { color: var(--wr-dim); flex: 1 1 auto; }
  .home-roster { margin-top: 2px; }
  .home-grp {
    padding: 12px 2px 4px; font-size: 11px; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700; color: var(--wr-dim);
    border-bottom: 1px solid var(--wr-hairline-2);
  }
  .home-grp .wr-num { color: var(--wr-hairline-2); margin-left: 4px; }
  .home-r { border-bottom: 1px solid var(--wr-hairline); min-height: 44px;
            display: flex; align-items: center; }
  .home-r > * { flex: 1 1 auto; min-width: 0; }
  .home-r:last-child { border-bottom: none; }
  .home-r-flag { box-shadow: inset 3px 0 0 var(--wr-rule); }
  .home-r-locked .home-r3 { opacity: 0.55; }
  .home-r .wr-pop { border-top: none; }
  .home-r .wr-pop > .wr-pop-s { padding: 4px 2px; min-height: 44px; }
  .home-r .wr-pop-d { margin-left: 1px; }
  /* ui.row3's identity is a no-wrap flex line; the 13px context line
     must drop UNDER the name, so the identity wraps inside this page */
  .home-r .wr-r3-id { flex-wrap: wrap; row-gap: 2px; }
  .home-r .wr-r3-id > .home-ctx { flex: 1 1 100%; }
  .home-r3 {
    display: grid; grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 2px 10px; align-items: center; min-width: 0; padding: 3px 4px;
  }
  .home-r3-id { display: flex; flex-wrap: wrap; align-items: center;
                gap: 3px 7px; min-width: 0; }
  .home-name { font-weight: 700; font-size: 15px; overflow-wrap: anywhere; }
  .home-name-open { color: var(--wr-dim); font-style: italic; }
  .home-ctx { flex: 1 1 100%; display: flex; flex-wrap: wrap;
              align-items: center; gap: 2px 8px; color: var(--wr-muted);
              font-size: 13px; }
  .home-r3-mid { display: flex; flex-direction: column; align-items: flex-end;
                 gap: 2px; white-space: nowrap; }
  .home-kick { color: var(--wr-dim); font-size: 11px; }
  .home-r3-ver { display: flex; flex-direction: column; align-items: flex-end;
                 gap: 3px; white-space: nowrap; }
  .home-sig { display: inline-flex; align-items: center; gap: 5px;
              vertical-align: middle; }
  .home-sig-i { display: inline-flex; color: var(--wr-dim); }
  .home-sig-good  { color: var(--wr-mint); }
  .home-sig-warn  { color: var(--wr-gold); }
  .home-sig-alarm { color: var(--wr-text); }
  :root[data-quiet="1"] .home-ctx-t, :root[data-quiet="1"] .home-trend {
    display: none;
  }

  /* fallbacks for the v4 vocabulary (see the ui bridge) ---------------- */
  .home-st { display: inline-flex; }
  .home-st-alarm .wr-badge { color: var(--wr-text); border-color: var(--wr-text); }
  .home-dot-w { display: inline-flex; align-items: center; }
  .home-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
              background: var(--wr-rule);
              box-shadow: 0 0 0 2px var(--wr-panel), 0 0 0 3px var(--wr-gold); }
  .home-trend { display: inline-flex; }
  .home-oppw { display: inline-flex; }
  .home-oppc {
    display: inline-flex; align-items: center; padding: 1px 7px 1px 9px;
    border-radius: 5px; border: 1px solid var(--wr-hairline-2);
    font-size: 13px; font-weight: 600; color: var(--wr-text);
    box-shadow: inset 3px 0 0 var(--wr-meter-lo);
  }
  .home-oppc-hi  { box-shadow: inset 3px 0 0 var(--wr-meter-hi); }
  .home-oppc-mid { box-shadow: inset 3px 0 0 var(--wr-meter-mid); }
  .home-oppc-lo  { box-shadow: inset 3px 0 0 var(--wr-meter-lo); }
  .home-oppc-none { box-shadow: none; color: var(--wr-muted); }
  .home-scorew { display: inline-flex; }
  .home-score { display: inline-flex; align-items: baseline; gap: 6px;
                font-size: 15px; font-weight: 600; }
  .home-score-a { color: var(--wr-gold); }
  .home-score-na { color: var(--wr-dim); font-weight: 400; }
  .home-legend-w { display: inline-flex; flex: none; }
  .home-legend-pop { border-top: none; position: relative; }
  .home-legend-pop > .wr-pop-s { padding: 0; min-height: 44px; min-width: 44px;
                                 justify-content: center; }
  .home-legend-pop > .wr-pop-s .wr-pop-chev { display: none; }
  .home-legend-q {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 50%;
    border: 1px solid var(--wr-hairline-2); color: var(--wr-muted);
    font-weight: 700; font-size: 13px;
  }
  .home-legend-pop[open] .home-legend-q { border-color: var(--wr-gold);
                                          color: var(--wr-gold); }
  .home-legend-pop > .wr-pop-d {
    position: absolute; right: 0; top: 100%; z-index: 20;
    width: 22rem; max-width: 80vw; margin: 0; padding: 10px 12px;
    background: var(--wr-panel); border: 1px solid var(--wr-hairline-2);
    border-left: 1px solid var(--wr-hairline-2); border-radius: 8px;
    box-shadow: 0 6px 18px var(--wr-shadow);
  }
  .home-legend-pop .wr-legend { gap: 8px 14px; }

  /* the player card's cross-league block ------------------------------- */
  .home-xl { margin: 8px 0 0; }
  .home-xl-r { display: flex; flex-wrap: wrap; align-items: center;
               gap: 4px 10px; padding: 4px 0;
               border-top: 1px solid var(--wr-hairline); }
  .home-xl-lg { font-weight: 700; color: var(--wr-text); font-size: 13px;
                min-width: 8rem; }
  .home-xl-go { color: var(--wr-text); text-decoration: none;
                border-bottom: 1px solid var(--wr-hairline-2); }
  .home-xl-s { color: var(--wr-muted); }
  .home-xl-a { display: flex; gap: 6px; margin-left: auto; }
  .home-act-sm { min-height: 44px; }

  /* exposure + pulse ---------------------------------------------------- */
  .home-expo-line { margin: 6px 0 0; font-size: 13px; line-height: 1.7; }
  .home-expo-p { white-space: nowrap; }
  .home-expo-w { color: var(--wr-muted); font-size: 13px; }
  .home-pulse-row { display: flex; flex-wrap: wrap; gap: 14px 22px;
                    margin: 10px 0 4px; }

  /* jump box ------------------------------------------------------------ */
  .home-jump { display: flex; flex-wrap: wrap; align-items: center;
               gap: 8px 12px; margin: 14px 0; }
  .home-jump-l { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
                 font-weight: 700; color: var(--wr-gold); }
  .home-jump-q {
    flex: 1 1 12rem; min-height: 44px; padding: 0 12px; font: inherit;
    border: 1px solid var(--wr-hairline-2); border-radius: 8px;
    background: var(--wr-panel); color: var(--wr-text);
  }
  .home-jump-q:focus { outline: 2px solid var(--wr-rule); outline-offset: 1px; }
  .home-jump-n { color: var(--wr-dim); font-size: 13px; }

  /* footer ---------------------------------------------------------------- */
  .home-more { margin: 12px 0 0; }
  .home-link {
    display: inline-flex; align-items: center; min-height: 44px; gap: 6px;
    color: var(--wr-gold); font-weight: 700; text-decoration: none;
    border-bottom: 1px solid var(--wr-gold);
  }
  .home-link:focus-visible, a.home-att-go:focus-visible,
  .home-act:focus-visible {
    outline: 2px solid var(--wr-rule); outline-offset: 2px;
  }
  footer.home-foot {
    color: var(--wr-muted); font-size: 11px; line-height: 1.6;
    margin: 18px 2px 0;
  }
  footer.home-foot code, .wr-note code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
  }

  /* the phone: three columns stay, paddings tighten, and nothing
     acquires a fixed width */
  @media (max-width: 700px) {
    .home-r3 { gap: 2px 6px; padding: 3px 2px; }
    /* ui.row3 lays its middle and verdict columns out side by side; at
       375px that squeezes the name to nothing, so inside this page both
       stack vertically and the identity keeps the width - three columns,
       still, each one narrow */
    .home-r .wr-r3-mid, .home-r .wr-r3-v {
      flex-direction: column; align-items: flex-end; gap: 2px;
    }
    .home-r .wr-r3-mid > *, .home-r .wr-r3-v > * { flex: none; }
    /* the chip keeps its word and loses its glyph and percentage on a
       phone - the card still says both - so three columns fit 375px */
    .home-roster .wr-chip .wr-icon, .home-roster .wr-chip-pct { display: none; }
    .home-roster .wr-chip { padding: 2px 6px; }
    .home-sig { flex-wrap: wrap; gap: 3px; }
    .home-lg-proj { text-align: left; }
    .home-lg-name { font-size: 18px; }
    .home-expo-p { white-space: normal; }
    .wr-card { padding: 12px 10px; }
    .home-xl-lg { min-width: 0; flex: 1 1 100%; }
  }
  @media (max-width: 30rem) {
    .home-head .wr-h1 { font-size: 22px; }
    .home-win { flex-basis: 7.5rem; min-width: 7.5rem; }
  }
"""

# Page-local twins of the type scale, emitted ONLY while engine/ui lacks
# .wr-t1..t4 (ui_has_type_scale()). Same four sizes, so the markup does
# not change when the real ones land.
_TYPE_SCALE_CSS = """
  .wr-t1 { font-size: 17px; }
  .wr-t2 { font-size: 15px; }
  .wr-t3 { font-size: 13px; }
  .wr-t4 { font-size: 11px; }
"""


def local_css() -> str:
    """This page's own stylesheet: the layout, plus the type-scale twins
    while engine/ui does not carry them."""
    return _PAGE_CSS + ("" if ui_has_type_scale() else _TYPE_SCALE_CSS)


def page_css() -> str:
    """The whole stylesheet: the shared design system, then page layout."""
    return _ui_css() + local_css()


def render_page(snapshots: Sequence[Dict], week, stamp: str = "",
                notes: Sequence[str] = (), now: Optional[datetime] = None,
                exposure: Optional[Dict] = None) -> str:
    """The complete landing page as one self-contained string."""
    snaps = list(snapshots)
    now = now or _now()
    items, caveats = attention_items(snaps, now=now)
    checked = {
        "leagues": sum(1 for s in snaps if s.get("error") is None),
        "starters": sum(len([r for r in (s.get("starters") or [])
                             if not r.get("open")])
                        for s in snaps if s.get("error") is None),
    }
    nav_leagues = [(s.get("id") or "", s.get("name") or s.get("id") or "")
                   for s in snaps]

    inbox = render_attention(items, caveats, checked)
    main_parts = [render_strip(snaps, now), render_jump()]
    main_parts.extend(render_league(s, now=now, snapshots=snaps,
                                    exposure=exposure) for s in snaps)
    if not snaps:
        main_parts.append('<section class="wr-card">%s%s</section>'
                          % (ui.section_header("No leagues configured"),
                             ui.banner("There is no league yaml in leagues/ — "
                                       "nothing to show, and nothing is being "
                                       "assumed.", tone="warn")))
    main_parts.append(render_exposure(exposure_overlap(exposure, snaps),
                                      (exposure or {}).get("banner") or ""))
    main_parts.append(render_pulse(source_pulse(snaps)))

    grid = ('<div class="home-grid">'
            '<aside class="home-side" aria-label="needs you">%s</aside>'
            '<div class="home-main">%s</div></div>'
            % (inbox, "\n".join(p for p in main_parts if p)))

    note_html = "".join('<p class="wr-note">%s</p>' % ui.esc(n)
                        for n in notes if n)
    footer = (
        '<footer class="home-foot">%s%s'
        'Every number here is computed by the module that owns it — lineup, '
        'consensus, matchups, waivers, performance, exposure, leagueview — '
        'and this page only arranges them and picks the mark. It is '
        'read-only: it records no ledger vote and advances no baseline (the '
        '%%owned snapshot is read with advance=False), so opening it twice '
        'changes nothing.<br>regenerate: <code>./home.sh</code> · the full '
        'breakdown: <code>./board.sh &lt;league&gt; %s</code> · '
        'weights: <code>./sources.sh</code></footer>'
        % (note_html, ('<p class="wr-note">%s</p>' % ui.esc(stamp)) if stamp
           else "", ui.esc(week)))

    scripts = "<script>%s</script>" % _JUMP_JS
    sheets = sheets_script_html()
    if sheets:
        scripts += ("\n" + sheets) if sheets.lstrip().startswith("<script") \
            else "\n<script>%s</script>" % sheets

    title = "%s — your teams, week %s" % (ui.PRODUCT_NAME, week)
    return ("<!doctype html>\n<html lang=\"en\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">\n"
            "<title>%s</title>\n%s\n<style>%s</style>\n</head><body>\n"
            "%s\n<main class=\"wr-page\">\n%s\n%s\n%s\n</main>\n"
            "%s\n</body></html>\n"
            % (ui.esc(title), ui.style_tag(), local_css(),
               ui.shell("home", week=week, leagues=nav_leagues),
               render_header(week, snaps, now), grid, footer, scripts))


# --- gathering (impure) -----------------------------------------------------

def league_ids(league_dir: Optional[str] = None) -> List[str]:
    """Every configured league, in a stable order."""
    paths = glob.glob(os.path.join(league_dir or LEAGUE_DIR, "*.yaml"))
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in paths)


def page_links(league_id: str, week: int) -> Dict[str, Dict]:
    """Board / Ledger / Trade Desk for this league, with whether each file
    exists on disk right now (a missing sibling is linked and marked, never
    hidden - it is one command away)."""
    out = page_links_pure(league_id, week)
    for pg in out.values():
        pg["exists"] = os.path.exists(os.path.join(HERE, pg["href"]))
    return out


def fetch_ownership(force: bool = False) -> Dict[str, Dict[str, Optional[float]]]:
    """{nkey: {'own': % rostered, 'start': % started}} from ESPN's PUBLIC
    projections payload - the same cached file engine/projections.fetch_espn
    reads (data/cache/espn-kona-ppr-<season>.json, 6h), so no second request
    is made for it and nothing here needs cookies. The rates are ESPN-wide,
    not this league's; the page labels them so. Read-only.

    fetch_espn() keeps percentOwned and drops percentStarted, which is why
    the raw payload is read here rather than its output.
    """
    from engine import projections as proj_mod
    fmt = 3                                  # ppr: the one file every render has
    payload = proj_mod._fetch_json(
        proj_mod.ESPN_URL % (proj_mod.SEASON, fmt),
        "espn-kona-%s-%d.json" % (proj_mod.ESPN_FORMATS[fmt], proj_mod.SEASON),
        {"User-Agent": proj_mod.UA, "Accept": "application/json",
         "X-Fantasy-Filter": json.dumps(proj_mod.ESPN_FILTER)},
        force=force, quiet=True)
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for entry in (payload or {}).get("players", []):
        pl = entry.get("player") or {}
        name = pl.get("fullName") or ""
        own = pl.get("ownership") or {}
        if not name or not own:
            continue
        rec = {}
        for src, dst in (("percentOwned", "own"), ("percentStarted", "start")):
            v = own.get(src)
            try:
                rec[dst] = float(v) if v is not None else None
            except (TypeError, ValueError):
                rec[dst] = None
        if rec.get("own") is None and rec.get("start") is None:
            continue
        out[proj_mod.name_key(name)] = rec
    return out


def _voices(cons_row: Optional[Dict]) -> List[Tuple[str, str, str]]:
    if not cons_row:
        return []
    return [(v.get("name") or v.get("source") or "?", v.get("verdict") or "",
             v.get("quote") or "")
            for v in (cons_row.get("votes") or [])]


def _hot_source_ids(scoreboard: Optional[Dict]) -> Dict[str, str]:
    """{source_id: display name} for sources on a HOT CURRENT-form run.

    `state` is deliberately the live-basis state (see performance.py): a
    source with a strong 2025 reconstruction and no live call is NO-DATA, so
    in September this map is empty and the hot glyph never fires. That is the
    correct answer, not a missing feature.
    """
    if not scoreboard:
        return {}
    return dict((r.get("source"), r.get("name") or r.get("source"))
                for r in (scoreboard.get("rows") or [])
                if r.get("state") == "HOT")


def kickoffs_of(schedule: Optional[Dict]) -> List[str]:
    """One kickoff ISO per GAME (the home side's entry), for the strip."""
    if not schedule:
        return []
    out = []
    for team, game in sorted(schedule.items()):
        if game.get("home") and game.get("kickoff_iso"):
            out.append(game["kickoff_iso"])
    return out


def _row_from_player(player, group: str, slot: str, snap_meta: Dict,
                     cmap: Dict, meta: Dict, schedule: Optional[Dict],
                     injuries: Optional[Dict], mmap: Dict,
                     hot: Dict[str, str], now: Optional[datetime],
                     ownership: Optional[Dict] = None,
                     trending: Optional[Dict] = None) -> Dict:
    key = player.key
    cons_row = cmap.get(key)
    pmeta = meta.get(key) or {}
    schedule_known = schedule is not None
    game = (schedule or {}).get(player.team) if player.team else None
    bye = None
    if schedule_known and player.team:
        bye = game is None
    status = ""
    if injuries is not None:
        status = (injuries.get(player.nkey) or "").strip()

    quotes = [(n, q) for n, _v, q in _voices(cons_row) if q]
    backers = []
    if cons_row and hot:
        want = cons_row.get("verdict")
        for v in cons_row.get("votes") or []:
            sid = v.get("source")
            if sid in hot and str(v.get("verdict") or "").upper() == want:
                backers.append(hot[sid])

    own = (ownership or {}).get(player.nkey) or {}
    kickoff_iso = (game or {}).get("kickoff_iso") or ""
    return {
        "name": player.name, "pos": player.pos, "team": player.team,
        "key": key, "slot": slot, "group": group, "open": False,
        "meta": " ".join(x for x in (player.team,
                                     opponent_label(player.team, game,
                                                    schedule_known)) if x),
        "opponent": (game or {}).get("opponent") or "",
        "home": (game or {}).get("home") if game else None,
        "proj": pmeta.get("weekly"),
        "proj_source": pmeta.get("source") or "",
        "actual": None,                 # no live scoring feed is connected
        "status": status,
        "bye": bye,
        "lean": cons_row.get("verdict") if cons_row else None,
        "pct": cons_row.get("pct") if cons_row else None,
        "agreement": cons_row.get("agreement") if cons_row else "",
        "top_note": cons_row.get("top_note") if cons_row else "",
        "level": board_mod.divergence_level(cons_row),
        "split_weight": board_mod.split_weight(cons_row),
        "voices": _voices(cons_row),
        "quotes": quotes,
        "hot_backers": backers,
        "matchup": mmap.get(key),
        "kickoff_iso": kickoff_iso,
        "kickoff": kickoff_label(kickoff_iso),
        "locked": is_locked(kickoff_iso, now),
        "own_pct": own.get("own"),
        "start_pct": own.get("start"),
        "own_known": ownership is not None,
        "trend_adds": (trending or {}).get(player.nkey),
    }


def _waiver_claims(league: LeagueConfig, week: int, players, matcher,
                   roster_keys, force: bool = False) -> Dict:
    """The board's read-only wire, reduced to "is anyone worth a claim".

    Same calls in the same order as engine/board.py's wire section, with the
    ONE rule that matters more than the rest: owned_momentum(advance=False).
    The %owned baseline (data/cache/espn-owned-snapshot.json) is read and
    left where it was - rendering the landing page is not the gesture that
    moves the week on (the digest and `python -m engine.waivers` are).

    "Worth a claim" is the wire's own verdict, not a new one: a positive
    score AND (priority league) burn == YES, or (FAAB league) a band above
    "pass". At most CLAIMS_MAX per league reach the inbox.
    """
    roster_keys = set(roster_keys)
    scoring = league.scoring_label()
    roster_players = [p for p in players if p.key in roster_keys]
    rival = trades_mod.load_rival_view(league, matcher, players,
                                       my_keys=roster_keys)
    rival_keys = rival.rostered_keys() if rival.available else set()
    notes: List[str] = []
    taken = set()
    if str(league.platform or "").lower() == "espn":
        # Other ESPN teams' rosters are an ESPN fact; applying them to a
        # Yahoo league would thin the wrong pool.
        taken, taken_note = waivers_mod.espn_taken_keys(matcher)
        notes.append(taken_note)
    owned, owned_note = waivers_mod.owned_momentum(advance=False)  # READ-ONLY
    notes.append(owned_note)
    ros_map = waivers_mod.build_ros_map(players, week, scoring, force=force)
    baselines = waivers_mod.starter_baselines(league, roster_players, ros_map,
                                              players)
    xfp_map, xfp_label = waivers_mod.fetch_xfp_signal(force=force)
    trending = waivers_mod.fetch_trending_adds(force=force)
    pool = [p for p in players if p.key not in roster_keys
            and p.key not in taken and p.key not in rival_keys]
    ranked = waivers_mod.score_pool(pool, ros_map, baselines, xfp_map,
                                    trending, owned_delta=owned,
                                    xfp_label=xfp_label)
    comp = waivers_mod.waiver_competition(league, rival, pool + roster_players,
                                          ros_map, players)
    waivers_mod.apply_competition(ranked, comp)
    mode = getattr(league, "waiver_mode", "faab")
    if mode == "priority":
        waivers_mod.priority_guidance(ranked)
        waivers_mod.priority_competition(ranked, comp)

    # WITHOUT rival rosters the pool is "everyone not known to be mine",
    # which in a league whose other teams are unknown means the wire's top
    # names are the league's best players. Nominating Puka Nacua as a claim
    # would be manufactured urgency, so no claim is surfaced - the card says
    # why, and the pool size is still reported.
    claims = []
    for cand in (ranked if rival.available else []):
        if cand.score <= 0:
            continue
        if mode == "priority":
            if cand.burn != "YES":
                continue
            band, why = "worth burning waiver priority", cand.burn_detail
        else:
            if cand.faab == "pass":
                continue
            band, why = "FAAB %s" % cand.faab, ""
        p = cand.player
        detail = "score %.1f: ROS %+.1f vs %s" % (cand.score, cand.ros_gain,
                                                 cand.ros_basis)
        if cand.trend_pts and cand.trend_detail:
            detail += " · %s" % cand.trend_detail
        if why:
            detail += " · %s" % why
        claims.append({"name": p.name, "pos": p.pos, "team": p.team,
                       "score": round(cand.score, 1), "band": band,
                       "detail": detail})
        if len(claims) >= CLAIMS_MAX:
            break
    if not rival.available:
        notes.append(waivers_mod.NO_COMPETITION)
    return {"claims": claims, "notes": [n for n in notes if n],
            "pool": len(pool), "ranked": len(ranked), "mode": mode,
            "rivals_known": bool(rival.available)}


def gather_league(league_id: str, week: int, force: bool = False,
                  roster_dir: Optional[str] = None,
                  calls_dir: Optional[str] = None,
                  registry_path: Optional[str] = None,
                  data_root: Optional[str] = None,
                  now: Optional[datetime] = None,
                  read_waivers: bool = True) -> Dict:
    """One league's snapshot. Every feed is guarded on its own.

    A dead feed becomes a `degraded` entry (rendered in place, carrying the
    real exception) and an `unchecked` line (which reaches the inbox's
    caveats). Neither is ever allowed to silently narrow what the page
    claims to have checked. Context feeds - ownership rates, trending adds
    - are guarded too, but a dead one is a card note, not a caveat: they
    inform a decision, they do not check one.
    """
    week = int(week)
    snap: Dict = {"id": league_id, "week": week, "error": None,
                  "error_text": "", "degraded": [], "unchecked": [],
                  "notes": [], "starters": [], "bench": [], "unresolved": [],
                  "platform": "", "host": None, "kickoffs": [],
                  "scoreboard": None, "waivers": None, "dk": None,
                  "pages": page_links(league_id, week),
                  "board_href": "board-%s-week%d.html" % (league_id, week),
                  "board_exists": None}
    try:
        path = os.path.join(LEAGUE_DIR, "%s.yaml" % league_id)
        if not os.path.exists(path):
            raise IOError("no league yaml: %s" % repo_path(path))
        league = LeagueConfig.load(path)
        csv_path = os.path.join(HERE, league.rankings_csv)
        if not os.path.exists(csv_path):
            raise IOError(missing_rankings_message(league, csv_path))
        players = load_players(csv_path)
        matcher = Matcher(players)
    except Exception as exc:  # noqa: BLE001 - the card carries the error
        snap["error"] = exc
        snap["error_text"] = "%s: %s" % (type(exc).__name__,
                                         ui.trim(str(exc), 160))
        snap["name"] = league_id
        return snap

    snap["name"] = league.name
    snap["teams"] = league.teams
    snap["scoring"] = league.scoring_label()
    snap["platform"] = str(league.platform or "").strip().lower()
    snap["host"] = getattr(league, "host", None)
    snap["record"] = board_mod.record_line(league)
    snap["board_exists"] = snap["pages"]["board"]["exists"]
    snap["_matcher"] = matcher

    roster = lineup_mod.load_roster(league_id, dirpath=roster_dir)
    stale = lineup_mod.stale_note(roster)
    if stale:
        snap["notes"].append(stale)
    names = roster["players"] if roster else []
    if not names:
        snap["notes"].append(
            "no roster file (data/rosters/%s.yaml) — there is nothing to show "
            "for this team, which is a missing file, not an empty roster."
            % league_id)

    def _guard(title, fn, unchecked_note, default=None, soft=False):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - honest degradation
            if soft:
                snap["notes"].append("%s not read (%s: %s) — %s"
                                     % (title, type(exc).__name__,
                                        ui.trim(str(exc), 120), unchecked_note))
            else:
                snap["degraded"].append((title, exc))
                snap["unchecked"].append(unchecked_note)
            return default

    proj = _guard("weekly projections",
                  lambda: weekly.fetch_weekly_projections(
                      week, scoring=snap["scoring"], force=force, quiet=True),
                  "the weekly projection feed is down, so no projection, "
                  "lineup or lean was read", {})
    schedule = _guard("the NFL schedule",
                      lambda: weekly.fetch_schedule(week, force=force),
                      "the schedule feed is down, so BYE weeks, kickoffs and "
                      "locks were NOT checked", None)
    snap["kickoffs"] = kickoffs_of(schedule)
    injuries = _guard("the injury report",
                      lambda: fetch_injury_status(force=force, quiet=True),
                      "the injury feed is down, so no status was checked and "
                      "no player is assumed healthy", None)

    build = _guard("the best legal lineup",
                   lambda: lineup_mod.build(league, names, week, proj or {},
                                            schedule=schedule,
                                            injuries=injuries,
                                            matcher=matcher),
                   "the lineup could not be built, so starters and bench are "
                   "unknown", None)
    if build is None:
        return snap

    starters = [p for _, p in build["rows"] if p is not None]
    bench = list(build["bench"] or [])
    # DEF/K hold-or-stream (engine/dk): computed ONCE here, handed to the
    # consensus so the DST/K rows carry it, and kept on the snap for the
    # inbox. Read-only - dk never logs the streaming ledger and never
    # touches the %owned baseline.
    dk = None
    if any(p.pos in ("DEF", "K") for p in starters + bench):
        dk = _guard("the DEF/K stream call",
                    lambda: dk_mod.weekly_call(league, week,
                                               starters + bench, players,
                                               matcher, force=force),
                    "the DEF/K wire read failed, so no hold-or-stream call "
                    "was made on your defense or kicker", None)
    snap["dk"] = dk

    cons = _guard("the room (every enabled source)",
                  lambda: consensus_mod.build_consensus(
                      league_id, week, roster_dir=roster_dir,
                      calls_dir=calls_dir, registry_path=registry_path,
                      force=force, dk_calls=dk if dk else False),
                  "the consensus could not be built, so no source lean was "
                  "read", None)
    cmap = consensus_mod.consensus_map(cons) if cons else {}
    if cons:
        snap["notes"].extend(cons.get("notes") or [])
        snap["sources"] = [{"id": s.get("id"), "name": s.get("name"),
                            "weight": s.get("weight")}
                           for s in (cons.get("sources") or [])]

    mmap: Dict[str, Dict] = {}
    table = _guard("the matchup table",
                   lambda: matchups_mod.pa_table(league, force=force),
                   "the points-allowed table is unavailable, so no matchup "
                   "was graded", None)
    if table is not None and schedule is not None:
        rows = _guard("matchup grades",
                      lambda: matchups_mod.matchups_for_roster(
                          starters + bench, week, league, table=table,
                          schedule=schedule),
                      "matchup grades could not be computed", [])
        mmap = dict((m["player_key"], m) for m in (rows or []))
        if table.get("caveat"):
            snap["notes"].append(table["caveat"])
    elif table is not None:
        snap["unchecked"].append("matchup grades need the schedule, which is "
                                 "down, so none were checked")

    scoreboard = _guard("source form",
                        lambda: performance_mod.source_scoreboard(
                            league, registry_path=registry_path),
                        "no source-form read was available", None)
    hot = _hot_source_ids(scoreboard)
    if scoreboard is not None:
        snap["scoreboard"] = [
            {"source": r.get("source"), "name": r.get("name"),
             "type": r.get("type") or "", "weight": r.get("weight"),
             "state": r.get("state"), "state_reason": r.get("state_reason")}
            for r in (scoreboard.get("rows") or [])]
        if not hot:
            snap["notes"].append(
                "No voice has a current-form read yet, so the hot-source "
                "icon appears nowhere below — that is a fact about the record "
                "(the ledger is empty until a week is played), not about the "
                "sources.")

    # Context, not checks: ESPN's public roster/start rates and the wire's
    # trending adds. A dead feed is a note on the card and an honest blank on
    # the row - never a caveat against the all-clear, which they do not earn.
    ownership = _guard("ESPN roster/start rates",
                       lambda: fetch_ownership(force=force),
                       "no row carries a roster % or start % this render",
                       None, soft=True)
    trending = _guard("trending adds",
                      lambda: waivers_mod.fetch_trending_adds(force=force),
                      "no row carries a trend mark this render",
                      None, soft=True)

    idx = [0]

    def _mk(player, group, slot):
        idx[0] += 1
        row = _row_from_player(player, group, slot, snap, cmap,
                               build.get("meta") or {}, schedule, injuries,
                               mmap, hot, now, ownership=ownership,
                               trending=trending)
        row["anchor"] = anchor_id(league_id, idx[0])
        return row

    for slot, p in build["rows"]:
        if p is None:
            idx[0] += 1
            snap["starters"].append({
                "name": OPEN_SLOT, "pos": "", "team": "", "key": "",
                "slot": slot, "group": "STARTING", "open": True,
                "meta": "", "opponent": "", "home": None, "proj": None,
                "proj_source": "", "actual": None, "status": "",
                "bye": None, "lean": None, "pct": None, "agreement": "",
                "top_note": "", "level": 0, "split_weight": 0, "voices": [],
                "quotes": [], "hot_backers": [], "matchup": None,
                "kickoff_iso": "", "kickoff": "", "locked": False,
                "own_pct": None, "start_pct": None,
                "own_known": ownership is not None, "trend_adds": None,
                "anchor": anchor_id(league_id, idx[0])})
            continue
        snap["starters"].append(_mk(p, "STARTING", slot))
    for p in bench:
        snap["bench"].append(_mk(p, "BENCH", ""))

    snap["unresolved"] = list(build.get("unresolved") or [])

    if read_waivers:
        roster_keys = [p.key for p in starters + bench]
        snap["waivers"] = _guard(
            "the waiver wire",
            lambda: _waiver_claims(league, week, players, matcher,
                                   roster_keys, force=force),
            "the waiver wire could not be read, so no claim was checked",
            None)
    else:
        snap["unchecked"].append("the waiver wire was skipped "
                                 "(--skip-waivers), so no claim was checked")

    cov = None
    try:
        for row in leagueview.coverage_rows(data_root=data_root):
            if row.get("id") == league_id:
                cov = row
                break
    except Exception as exc:  # noqa: BLE001 - coverage is a note, not a page
        snap["notes"].append("league roster coverage unreadable (%s) — the "
                             "count below is unknown, not complete."
                             % ui.trim(str(exc), 120))
    if cov is not None:
        snap["coverage"] = cov
        line = "Coverage: %s" % cov.get("text")
        if not cov.get("complete"):
            line += (" — a player on none of them is UNKNOWN, not a free "
                     "agent")
        resolved = len(snap["starters"]) + len(snap["bench"]) \
            - sum(1 for r in snap["starters"] if r.get("open"))
        line += ("; my %d-man roster, %d resolved"
                 % (roster["size"] if roster else 0, resolved))
        snap["notes"].insert(0, line)
    return snap


def load_exposure(matcher, roster_dir: Optional[str] = None) -> Dict:
    """engine/exposure over every roster file, reduced to what the ribbon
    and the cross-league card need: per-league key sets and the
    partial-coverage banner."""
    try:
        exp = Exposure.load(matcher, dirpath=roster_dir)
    except Exception as exc:  # noqa: BLE001 - a ribbon is never worth a page
        return {"available": False, "rosters": [], "banner": "",
                "note": "exposure unreadable (%s)" % ui.trim(str(exc), 120)}
    return {"available": exp.available,
            "rosters": [(r.league_id, r.name, set(r.keys)) for r in exp.leagues],
            "banner": exp.banner_text(), "note": ""}


def gather(week: int, leagues: Optional[Sequence[str]] = None,
           force: bool = False, **kwargs) -> Tuple[List[Dict], Dict]:
    """(snapshots, exposure) for every configured league."""
    ids = list(leagues) if leagues else league_ids()
    snaps = [gather_league(lid, week, force=force, **kwargs) for lid in ids]
    matcher = next((s.get("_matcher") for s in snaps
                    if s.get("_matcher") is not None), None)
    if matcher is not None:
        exposure = load_exposure(matcher, roster_dir=kwargs.get("roster_dir"))
    else:
        exposure = {"available": False, "rosters": [], "banner": "",
                    "note": "no league could be read, so no roster was compared"}
    for s in snaps:
        s.pop("_matcher", None)
    return snaps, exposure


# --- assembly + write -------------------------------------------------------

def build_page(week: int, leagues: Optional[Sequence[str]] = None,
               force: bool = False, snapshots: Optional[Sequence[Dict]] = None,
               stamp: Optional[str] = None, now: Optional[datetime] = None,
               exposure: Optional[Dict] = None, **kwargs) -> str:
    """The whole landing page. `snapshots` skips every fetch (tests)."""
    week = int(week)
    if snapshots is None:
        snaps, found = gather(week, leagues=leagues, force=force, **kwargs)
        if exposure is None:
            exposure = found
    else:
        snaps = list(snapshots)
    now = now or _now()
    if stamp is None:
        stamp = now.strftime("%a %Y-%m-%d %I:%M %p %Z").strip()
    stamp = "generated %s · %d league%s" % (stamp, len(snaps),
                                            "" if len(snaps) == 1 else "s")
    return render_page(snaps, week, stamp=stamp, now=now, exposure=exposure)


def write_home(week: int, out_path: Optional[str] = None, **kwargs) -> str:
    """Build and atomically write the landing page; returns the path."""
    html = build_page(week, **kwargs)
    out = out_path or DEFAULT_PATH
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(html)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)
    return out


def render_failure(exc: BaseException, week: Optional[int] = None) -> str:
    """One legible line for a failure that killed the whole render."""
    return ("could not build the landing page%s: %s: %s\n"
            "  a league card degrades on its own, so this failed before any "
            "card existed — check leagues/*.yaml, data/rankings*.csv and "
            "data/sources.yaml."
            % ((" for week %s" % week) if week else "",
               type(exc).__name__, ui.trim(str(exc), 240)))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.home",
        description="THE LANDING PAGE: every league, every roster, the week's "
                    "game windows, and the handful of things that need you "
                    "before lock — each with a link to where you fix it. One "
                    "self-contained HTML page; prints the output path as its "
                    "last line.")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--league", action="append", default=None,
                    help="limit to this league id (repeatable; default: "
                         "every yaml in leagues/)")
    ap.add_argument("--out", default=None,
                    help="output path (default: home.html in the project "
                         "root)")
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when caches are fresh")
    ap.add_argument("--skip-waivers", action="store_true",
                    help="do not read the waiver wire (faster; the inbox then "
                         "says no claim was checked)")
    ap.add_argument("--roster-dir", default=None,
                    help="read rosters from this directory instead of "
                         "data/rosters/ (read-only). This page's exposure "
                         "ribbon reads EVERY roster file it can see, so "
                         "publish.py hands each person a copy holding only "
                         "the leagues they own")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
        from engine.digest import current_week
        try:
            week = current_week()
        except RuntimeError as exc:
            print("cannot derive the current week (schedule feed down: %s) — "
                  "pass --week explicitly" % exc)
            return 1
        if week is None:
            print("no remaining %d regular-season week found in the schedule "
                  "— pass --week explicitly" % weekly.SEASON)
            return 1
        print("week %d (current, from the nflverse schedule)" % week)
    try:
        week = weekly._check_week(week)
    except ValueError as exc:
        print(exc)
        return 1

    try:
        path = write_home(week, out_path=args.out, leagues=args.league,
                          force=args.force, roster_dir=args.roster_dir,
                          read_waivers=not args.skip_waivers)
    except KeyboardInterrupt:
        raise
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, str):
            print(ui.trim(code, 240))
            return 1
        return int(code or 0)
    except BaseException as exc:  # noqa: BLE001 - the diagnosis replaces it
        print(render_failure(exc, week))
        return 1
    present = ui_components()
    print("ui components: %s" % ", ".join(
        "%s %s" % (k, "present" if v else "fallback")
        for k, v in sorted(present.items())))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
