"""Read a FRIEND'S ESPN league without ever touching their credentials.

engine/espn.py connects as the OWNER, with the owner's own browser session
cookies. Those are whole-account Disney session credentials, not
fantasy-scoped; asking a friend for theirs would be credential sharing,
would break ESPN's terms for the person sharing them, and is refused here on
purpose. This module never reads the owner's ESPN secrets file, never sets a
Cookie header, and never sends a credential of any kind. The only place this
file names those cookies at all is PRIVATE_REMEDIATION, where it tells the
friend we will not take them - tests/espn_public_test.py asserts exactly
that, by counting.

There are exactly two supported ways for a friend's ESPN league to reach the
war room, and the second one is not an apology:

  1. PUBLIC READ. The league manager turns on "Make League Viewable to
     Public". ESPN's own read host then answers an anonymous GET with the
     whole league: settings, scoring, every team's roster. Nothing is
     impersonated - we are just a member of the public reading a page the
     manager published.

  2. PASTE. The league stays private, the friend copies their roster page
     and sends the text. Same files land on disk; the league is marked
     paste-fed so every screen says out loud that it will not refresh on
     its own.

EMPIRICAL FACTS behind this module (measured 2026-09-09 against
lm-api-reads.fantasy.espn.com, seasons/2026/segments/0/leagues/<id>, no
cookies, no auth of any kind):

  * PUBLIC league        -> 200 with the full payload. Confirmed on ffl
    league ids 39, 68, 109, 164, 184, 200, 203, 207, 209, 264, 308, 349,
    375. Every 200 carried settings.isPublic == true; no 200 was ever seen
    with isPublic false, so 200 and "viewable to public" are the same fact.
  * PRIVATE league       -> 401 {"messages":["You are not authorized to view
    this League."], ... "type":"AUTH_..."} on EVERY view (mTeam, mRoster,
    mSettings, mNav, mStatus, kona_player_info all tested). Nothing leaks.
  * NONEXISTENT league   -> 404 {"messages":["Not Found"], ...
    "type":"GENERAL_NOT_FOUND"}.
  * Non-numeric/oversize league id -> 400 "Invalid parameter for 'leagueId'".
  * Non-numeric season   -> 400 "Invalid parameter for 'seasonId'".
    Season with no such league-year -> 404.
  * PAST SEASONS of a public league are readable at seasons/<year>/... and
    visibility is PER SEASON, not per league: id 39 answered 200 for
    2019-2026 and 401 for 2018. The /leagueHistory/<id> endpoint answered
    404 for the leagues tested - use seasons/<year> instead.
  * EVERY view works unauthenticated on a public league: mTeam, mRoster,
    mSettings, mMatchup, mMatchupScore, mDraftDetail, mStandings, mBoxscore,
    mLiveScoring, mPendingTransactions, mStatus, mTransactions2, mNav,
    mPositionalRatings, kona_player_info, players_wl. One request carrying
    view=mSettings&view=mTeam&view=mRoster returns everything this module
    needs, so that is the one call made.

  Lineup slot ids were not taken on faith either - they were derived from
  the data by tallying which defaultPositionId values appear in each slot's
  eligibleSlots across leagues 39/164/200/264/308/349/375 (see SLOT_TOKENS).
  Scoring statIds likewise: 53 appears with 1.0 / 0.75 / 0.5 in PPR,
  half-PPR and 0.75-PPR leagues and is ABSENT in the standard league (349),
  which is why an absent 53 reads as 0.0 reception rather than "unknown".

What making a league viewable costs the friend, stated honestly: anyone who
has the league id can then read team names, rosters, scores and transactions
without logging in. It does not let anyone join, does not expose the
message board or owner email addresses, and the manager can switch it back
off at any time. If that trade is not wanted, use the paste path.

CLI:
    python -m engine.espn_public --league <id> [--season 2026]
                                 [--team <id|name>] [--paste-file f]
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Module-level paths so tests can redirect every write into a tempdir
# (tests/mock_draft.py SAVE_DIR discipline).
LEAGUES_DIR = os.path.join(HERE, "leagues")
ROSTERS_DIR = os.path.join(HERE, "data", "rosters")
DATA_DIR = os.path.join(HERE, "data")
CACHE_DIR = os.path.join(HERE, "data", "cache")

# ESPN's read-only host. The write host (fantasy.espn.com) is never used:
# this module is advise-only and cannot change anything on ESPN.
READ_HOST = "https://lm-api-reads.fantasy.espn.com"
API = READ_HOST + "/apis/v3/games/ffl/seasons/%s/segments/0/leagues/%s"

# The one request this module makes. Verified 2026-09-09: these three views
# in a single GET return settings + teams + full rosters for a public league.
VIEWS = ("mSettings", "mTeam", "mRoster")

DEFAULT_SEASON = 2026

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# The COMPLETE header set. Nothing is added anywhere else in this module.
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

# Headers this module refuses to send, ever. _http_get_json asserts it.
FORBIDDEN_HEADERS = ("cookie", "authorization", "x-espn-swid", "espn-s2",
                     "x-fantasy-source", "set-cookie")

# --- typed failures ----------------------------------------------------------

PRIVATE = "PRIVATE"
NOT_FOUND = "NOT_FOUND"
FEED_DOWN = "FEED_DOWN"
BAD_REQUEST = "BAD_REQUEST"
CONFLICT = "CONFLICT"
NO_BOARD = "NO_BOARD"
NO_TEAM = "NO_TEAM"

# The exact words a friend needs when their league is private. Kept as one
# constant so the CLI, the library and the test all say the same thing.
PRIVATE_REMEDIATION = (
    "ESPN league %(id)s is private for %(season)s, so nothing outside the "
    "league can read it - and that is the correct behaviour, not a bug.\n"
    "Two ways in. NEITHER of them involves sending anyone an ESPN password "
    "or the espn_s2 / SWID browser cookies: this war room does not accept "
    "those and will not store them.\n"
    "  1. MAKE IT VIEWABLE (league manager only, web only - the phone "
    "app cannot change this, about 20 seconds):\n"
    "     fantasy.espn.com -> your league -> League -> Settings -> Basic "
    "Settings -> Edit Basic Settings -> set 'Make League Viewable to "
    "Public' to Yes -> Save Changes. Then run this import again.\n"
    "     Cost: anyone who knows the league id can then read team names, "
    "rosters, scores and box scores without logging in. It does NOT let "
    "anyone join, and ESPN never shows non-members the list of team "
    "managers or the league message boards. The manager can switch it "
    "back off whenever they like.\n"
    "  2. PASTE INSTEAD (anyone, no settings change):\n"
    "     open your team's roster page on ESPN, select the roster, copy it, "
    "save it to a text file, then run:\n"
    "       python -m engine.espn_public --league %(id)s --paste-file "
    "roster.txt --teams <how many teams> --reception <points per catch>\n"
    "     Cost: a pasted league does not refresh on its own. Re-paste after "
    "every add, drop or trade.\n"
)


class EspnPublicError(RuntimeError):
    """A failure with a machine-readable kind and human remediation.

    kind is one of PRIVATE / NOT_FOUND / FEED_DOWN / BAD_REQUEST (read
    failures), or CONFLICT / NO_BOARD / NO_TEAM (import failures). str()
    is the message followed by the remediation, so a caller that only
    prints the exception still tells the user what to do next.
    """

    def __init__(self, kind: str, message: str, remediation: str = "",
                 league_id: str = "", season: Optional[int] = None,
                 status: Optional[int] = None):
        self.kind = kind
        self.message = message
        self.remediation = remediation
        self.league_id = str(league_id or "")
        self.season = season
        self.status = status
        full = message if not remediation else "%s\n%s" % (message, remediation)
        super(EspnPublicError, self).__init__(full)


# --- ESPN vocabulary, derived from the data (see module docstring) ------------

# lineupSlotId -> a roster-spot token. The flex tokens are deliberately
# spelled the way engine/connections.SLEEPER_SPOT_MAP spells them so the
# final normalisation happens in connections.map_roster_spots and the flex
# vocabulary lives in exactly one place.
#
# Proof, from eligibleSlots tallies across 7 public leagues (1381 roster
# entries): slot 3 accepts WR+RB; slot 5 accepts WR+TE; slot 7 accepts
# QB+RB+WR+TE; slot 23 accepts RB+WR+TE; slot 16 accepts only D/ST; slot 17
# only K; slot 18 only P; slot 19 only HC; slots 8-15 only defensive
# positions; slots 20/21 accept everything (bench / IR).
SLOT_TOKENS = {
    0: "QB", 1: "TQB", 2: "RB", 3: "WRRB_FLEX", 4: "WR", 5: "REC_FLEX",
    6: "TE", 7: "SUPER_FLEX", 8: "DT", 9: "DE", 10: "LB", 11: "DL",
    12: "CB", 13: "S", 14: "DB", 15: "DP", 16: "DEF", 17: "K", 18: "P",
    19: "HC", 20: "BN", 21: "IR", 23: "FLEX", 24: "ER", 25: "ROOKIE",
}

# The order ESPN itself lists a lineup in, so roster_spots reads like the
# league page rather than like a dict iteration order.
SLOT_ORDER = (0, 1, 2, 3, 4, 5, 6, 23, 7, 8, 9, 10, 11, 12, 13, 14, 15,
              17, 16, 18, 19, 20, 21, 24, 25)

# Slots that are real starting positions in this engine's vocabulary.
# Anything else (IDP, P, HC, ROOKIE, ER) is carried through unchanged and
# named out loud on import - honest, visible, unmangled, exactly the way
# engine/connections.py carries Sleeper's IDP slots.
KNOWN_SPOTS = {"QB", "RB", "WR", "TE", "K", "DEF", "BN", "IR",
               "W/R", "W/T", "W/R/T", "SUPERFLEX"}

# defaultPositionId -> position. Derived the same way (which ids turn up in
# which slots): 1 QB, 2 RB, 3 WR, 4 TE, 5 K, 7 P, 9 DT, 10 DE, 11 LB,
# 12 CB, 13 S, 14 HC, 16 D/ST.
POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 7: "P",
                9: "DT", 10: "DE", 11: "LB", 12: "CB", 13: "S", 14: "HC",
                16: "DEF"}

# scoringItems statId -> the key engine/connections._sleeper_scoring uses,
# so an ESPN league yaml and a Sleeper league yaml carry the same names.
# Confirmed across leagues 164/200/308/349/375: 3=pass yds (0.04),
# 4=pass TD (4/5/6), 20=INT thrown (-1/-2), 24=rush yds (0.1),
# 25=rush TD (6), 42=rec yds (0.1), 43=rec TD (6), 53=reception
# (1.0/0.75/0.5, ABSENT in a standard league), 72=fumble lost (-1/-2).
SCORING_FLAT = {4: "passing_td", 25: "rushing_td", 43: "receiving_td",
                20: "interception", 72: "fumble_lost"}
SCORING_PER_YARD = {3: "passing_yards_per_point",
                    24: "rushing_yards_per_point",
                    42: "receiving_yards_per_point"}
RECEPTION_STAT_ID = 53

_DST_SUFFIX = re.compile(r"\s*(?:D/ST|DST|D-ST)\s*$", re.I)


# --- HTTP + cache (engine/adp.py discipline) ---------------------------------

def _http_get_json(url: str, timeout: float = 25.0):
    """The ONE network call in this module. Never carries a credential.

    Builds the Request from HEADERS only and asserts that no forbidden
    header survived, so a future edit that tries to bolt a cookie on here
    fails loudly instead of quietly shipping someone's session to ESPN.
    Isolated so tests can replace it wholesale with fixtures.
    """
    headers = dict(HEADERS)
    bad = sorted(k for k in headers if k.lower() in FORBIDDEN_HEADERS)
    if bad:
        raise EspnPublicError(
            BAD_REQUEST,
            "engine/espn_public.py must never send %s. This module reads "
            "public leagues only." % ", ".join(bad))
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _error_for_status(status: int, body: str, league_id: str,
                      season: int) -> EspnPublicError:
    """Map ESPN's HTTP status onto a typed failure. Verified 2026-09-09."""
    ctx = {"id": league_id, "season": season}
    if status == 401 or status == 403:
        return EspnPublicError(
            PRIVATE,
            "ESPN answered 401 for league %s (%s): \"You are not authorized "
            "to view this League.\"" % (league_id, season),
            PRIVATE_REMEDIATION % ctx, league_id, season, status)
    if status == 404:
        return EspnPublicError(
            NOT_FOUND,
            "ESPN has no league %s in the %s season (404 Not Found)."
            % (league_id, season),
            "Check the id in the league's own URL - it is the leagueId= "
            "number on fantasy.espn.com. A league that exists but has no "
            "%s season also answers 404, so try the season it was last "
            "played in: --season <year>." % season,
            league_id, season, status)
    if status == 400:
        return EspnPublicError(
            BAD_REQUEST,
            "ESPN rejected the request for league %s / season %s as "
            "malformed (400): %s" % (league_id, season, body[:160]),
            "The league id must be the plain number from the league URL "
            "and the season a four-digit year.",
            league_id, season, status)
    return EspnPublicError(
        FEED_DOWN,
        "ESPN's read host answered HTTP %s for league %s (%s)."
        % (status, league_id, season),
        "That is ESPN having a bad minute, not a permissions problem. "
        "Try again in a few minutes; the last good copy in data/cache/ is "
        "used meanwhile when there is one.",
        league_id, season, status)


def cache_path(league_id: str, season: int) -> str:
    return os.path.join(CACHE_DIR, "espn-public-%s-%s.json"
                        % (season, league_id))


# Keys ESPN sends that identify the PEOPLE in the league rather than the
# league. `members` is a list of real human beings - displayName, firstName,
# lastName - and every team carries `primaryOwner`/`owners`, the persistent
# account GUIDs behind them.
_PERSONAL_LEAGUE_KEYS = ("members",)
_PERSONAL_TEAM_KEYS = ("primaryOwner", "owners")


def scrub_personal(payload: Dict) -> Dict:
    """Drop the league members' names and account ids. In place, returns it.

    Nothing in this module reads any of these keys: a team is resolved by
    id, name or abbrev (find_team), and the rosters, settings and draft
    all come from elsewhere in the document. They are pure retention -
    eleven real people's first and last names sitting in data/cache/
    indefinitely, because max_age_hours governs REUSE, never deletion.

    So they never reach the disk. The outputs already dropped them; this
    makes the sentence true of the cache too, which is the copy that
    actually persists. Called on the fetched document before it is
    written AND before it is returned, so a cache hit and a fresh read
    hand back the same shape.
    """
    if not isinstance(payload, dict):
        return payload
    for key in _PERSONAL_LEAGUE_KEYS:
        payload.pop(key, None)
    for team in (payload.get("teams") or []):
        if isinstance(team, dict):
            for key in _PERSONAL_TEAM_KEYS:
                team.pop(key, None)
    return payload


def _get_league_json(league_id: str, season: int, max_age_hours: float = 1.0,
                     force: bool = False, quiet: bool = True) -> Dict:
    """Fresh cache -> network -> stale cache -> honest typed error.

    401 and 404 are NOT served from a stale cache: a league that has just
    been made private again, or deleted, must say so rather than quietly
    replaying yesterday's copy. Only a transport failure or a 5xx falls
    back, and it says out loud that it did.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(league_id, season)

    if not force and os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            try:
                with open(path, "r") as fh:
                    doc = json.load(fh)
                scrub_personal(doc)   # also cleans a file an older build left
                doc["_from_cache"] = True
                return doc
            except (ValueError, OSError):
                pass    # a corrupt cache is not a reason to fail - refetch

    url = API % (season, league_id) + "?" + "&".join(
        "view=%s" % v for v in VIEWS)
    try:
        payload = _http_get_json(url)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:                                     # noqa: BLE001
            body = ""
        err = _error_for_status(exc.code, body, league_id, season)
        if err.kind == FEED_DOWN and os.path.exists(path):
            if not quiet:
                print("  ESPN %s - using the cached copy of league %s"
                      % (exc.code, league_id))
            with open(path, "r") as fh:
                doc = json.load(fh)
            scrub_personal(doc)
            doc["_from_cache"] = True
            return doc
        raise err
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            if not quiet:
                print("  ESPN fetch failed (%s) - using the cached copy of "
                      "league %s" % (type(exc).__name__, league_id))
            with open(path, "r") as fh:
                doc = json.load(fh)
            scrub_personal(doc)
            doc["_from_cache"] = True
            return doc
        raise EspnPublicError(
            FEED_DOWN,
            "Could not reach ESPN (%s: %s) and nothing for league %s is "
            "cached." % (type(exc).__name__, exc, league_id),
            "Check the network and try again.", league_id, season)

    if not isinstance(payload, dict):
        raise EspnPublicError(
            FEED_DOWN,
            "ESPN returned something that is not a league document for %s."
            % league_id, "", league_id, season)
    scrub_personal(payload)
    with open(path, "w") as fh:
        json.dump(payload, fh)
    payload["_from_cache"] = False
    return payload


def _atomic_write(path: str, text: str) -> None:
    """Temp file + rename, the discipline every writer here uses."""
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


# --- reading a public league --------------------------------------------------

def roster_spots_from_slots(lineup_slot_counts: Dict) -> List[str]:
    """ESPN lineupSlotCounts -> the engine's roster_spots list.

    Slots are emitted in ESPN's own lineup order. The flex tokens go out
    through connections.map_roster_spots so W/R/T, W/R, W/T and SUPERFLEX
    are spelled by the same function that spells them for Sleeper.
    """
    from engine import connections
    counts = {}
    for key, val in (lineup_slot_counts or {}).items():
        try:
            counts[int(key)] = int(val or 0)
        except (TypeError, ValueError):
            continue        # a key ESPN never sends; ignored, not guessed at
    tokens = []
    for slot in SLOT_ORDER:
        tokens.extend([SLOT_TOKENS.get(slot, "SLOT%d" % slot)]
                      * max(0, counts.get(slot, 0)))
    # Any slot id ESPN invents that SLOT_ORDER does not know is still
    # carried, at the end, named for what it is - never dropped.
    for slot in sorted(k for k in counts if k not in SLOT_ORDER):
        tokens.extend([SLOT_TOKENS.get(slot, "SLOT%d" % slot)]
                      * max(0, counts[slot]))
    return connections.map_roster_spots(tokens)


def scoring_from_items(scoring_items: List[Dict]) -> Dict:
    """ESPN scoringItems -> the scoring dict a league yaml carries.

    An ABSENT statId 53 means zero points per reception, not unknown:
    league 349 (a standard league) simply has no 53 item at all, while
    PPR / half-PPR / 0.75-PPR leagues carry 1.0 / 0.5 / 0.75.
    """
    points = {}
    for item in scoring_items or []:
        if not isinstance(item, dict):
            continue
        try:
            stat = int(item.get("statId"))
        except (TypeError, ValueError):
            continue
        val = item.get("points")
        if val is None:
            continue
        points[stat] = float(val)

    out = {"reception": float(points.get(RECEPTION_STAT_ID, 0.0))}
    for stat, key in sorted(SCORING_FLAT.items()):
        if stat in points:
            out[key] = points[stat]
    for stat, key in sorted(SCORING_PER_YARD.items()):
        per_yd = points.get(stat)
        if per_yd:
            out[key] = round(1.0 / per_yd, 2)
    return out


def waiver_mode_from_settings(acquisition_settings: Dict) -> str:
    """ESPN acquisitionSettings -> 'faab' or 'priority'.

    isUsingAcquisitionBudget is the determinant, NOT acquisitionType:
    league 164 is WAIVERS_TRADITIONAL with the budget on, league 200 is
    WAIVERS_CONTINUOUS with the budget on, leagues 39/308/349/375 are
    WAIVERS_TRADITIONAL with it off. Verified 2026-09-09.
    """
    return ("faab" if (acquisition_settings or {}).get(
        "isUsingAcquisitionBudget") else "priority")


def _team_name(team: Dict) -> str:
    """Team display name across ESPN's two shapes.

    2026 payloads carry a single `name`; older seasons split it into
    `location` + `nickname`.
    """
    name = (team.get("name") or "").strip()
    if name:
        return name
    parts = [(team.get("location") or "").strip(),
             (team.get("nickname") or "").strip()]
    joined = " ".join(p for p in parts if p).strip()
    return joined or ("Team %s" % team.get("id"))


def player_name(player: Dict) -> str:
    """ESPN player -> the name the rankings pool uses.

    Only one rewrite happens: 'Eagles D/ST' becomes 'Eagles Defense',
    which engine/ingest.Matcher resolves to 'Philadelphia Defense' through
    its NFL_TEAMS mascot aliases. Everything else is ESPN's own spelling,
    untouched.
    """
    name = (player.get("fullName") or "").strip()
    if not name:
        name = ("%s %s" % (player.get("firstName") or "",
                           player.get("lastName") or "")).strip()
    try:
        pos = POSITION_IDS.get(int(player.get("defaultPositionId")))
    except (TypeError, ValueError):
        pos = None
    if pos == "DEF" or _DST_SUFFIX.search(name):
        base = _DST_SUFFIX.sub("", name).strip()
        if base:
            return "%s Defense" % base
    return name


def _draft_slots(settings: Dict, team_ids: List[int]) -> Dict[int, int]:
    """ESPN team id -> real draft slot, from draftSettings.pickOrder.

    pickOrder is the first round's team order, so a team's slot is its
    index there. When ESPN gives no pickOrder (or a partial one) the
    remaining teams fall back to their id order and the caller says so.
    """
    order = [t for t in ((settings or {}).get("draftSettings") or {}).get(
        "pickOrder") or [] if isinstance(t, int)]
    slots = {}
    for i, tid in enumerate(order, start=1):
        slots.setdefault(tid, i)
    nxt = len(slots) + 1
    for tid in team_ids:
        if tid not in slots:
            slots[tid] = nxt
            nxt += 1
    return slots


def read_public_league(league_id, season: int = DEFAULT_SEASON,
                       max_age_hours: float = 1.0, force: bool = False,
                       quiet: bool = True) -> Dict:
    """League facts + every team's roster, from ESPN's public read host.

    Raises EspnPublicError with .kind == PRIVATE (401 - the league is not
    viewable), NOT_FOUND (404 - no such league or no such season for it),
    BAD_REQUEST (400 - malformed id/season) or FEED_DOWN (transport or
    5xx, after trying the disk cache).

    Deliberately does NOT return owner display names or member emails:
    those belong to people who did not ask to be in this database. Team
    names, which the league publishes anyway, are enough to pick a team.
    """
    league_id = str(league_id).strip()
    if not league_id:
        raise EspnPublicError(BAD_REQUEST, "Empty ESPN league id.",
                              "Pass the number from the league's URL.")
    season = int(season)
    doc = _get_league_json(league_id, season, max_age_hours=max_age_hours,
                           force=force, quiet=quiet)

    settings = doc.get("settings") or {}
    roster_settings = settings.get("rosterSettings") or {}
    scoring_settings = settings.get("scoringSettings") or {}
    slot_counts = roster_settings.get("lineupSlotCounts") or {}
    roster_spots = roster_spots_from_slots(slot_counts)
    scoring = scoring_from_items(scoring_settings.get("scoringItems") or [])
    acquisition = settings.get("acquisitionSettings") or {}
    waiver_mode = waiver_mode_from_settings(acquisition)

    raw_teams = [t for t in (doc.get("teams") or []) if isinstance(t, dict)]
    team_ids = []
    for t in raw_teams:
        try:
            team_ids.append(int(t.get("id")))
        except (TypeError, ValueError):
            continue
    slots = _draft_slots(settings, team_ids)
    has_pick_order = bool(((settings.get("draftSettings") or {})
                           .get("pickOrder")))

    rosters = []
    for team in raw_teams:
        try:
            tid = int(team.get("id"))
        except (TypeError, ValueError):
            continue
        entries = ((team.get("roster") or {}).get("entries") or [])
        players, starters, bench = [], [], []
        for entry in entries:
            player = ((entry.get("playerPoolEntry") or {}).get("player")
                      or {})
            name = player_name(player)
            if not name:
                continue
            players.append(name)
            try:
                lineup = int(entry.get("lineupSlotId"))
            except (TypeError, ValueError):
                lineup = None
            if lineup in (20, 21):
                bench.append(name)
            else:
                starters.append(name)
        rosters.append({
            "team_id": tid,
            "slot": slots.get(tid),
            "name": _team_name(team),
            "abbrev": (team.get("abbrev") or "").strip(),
            "players": players,
            "starters": starters,
            "bench": bench,
            "size": len(players),
        })
    rosters.sort(key=lambda r: r["team_id"])

    unmapped = sorted({s for s in roster_spots if s not in KNOWN_SPOTS})
    size = settings.get("size")
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = len(rosters)

    return {
        "league_id": league_id,
        "season": int(doc.get("seasonId") or season),
        "name": (settings.get("name") or "ESPN league %s" % league_id),
        "is_public": bool(settings.get("isPublic")),
        "teams": size or len(rosters),
        "scoring_type": scoring_settings.get("scoringType"),
        "player_rank_type": scoring_settings.get("playerRankType"),
        "scoring": scoring,
        "reception": scoring["reception"],
        "roster_spots": roster_spots,
        "lineup_slot_counts": dict(slot_counts),
        "unmapped_spots": unmapped,
        "waiver_mode": waiver_mode,
        "waiver_budget": (acquisition.get("acquisitionBudget")
                          if waiver_mode == "faab" else None),
        "acquisition_type": acquisition.get("acquisitionType"),
        "draft_type": ((settings.get("draftSettings") or {}).get("type")),
        "has_pick_order": has_pick_order,
        "drafted": bool((doc.get("draftDetail") or {}).get("drafted")),
        "rosters": rosters,
        "scoring_period": doc.get("scoringPeriodId"),
        "from_cache": bool(doc.get("_from_cache")),
        "fetched_at": _now(),
    }


def _now() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def find_team(read: Dict, wanted) -> Dict:
    """Pick one team out of a read_public_league result.

    `wanted` is an ESPN team id or a team name (case/punctuation
    insensitive). Raises EspnPublicError(NO_TEAM) listing every team when
    it cannot be resolved - never guesses which team is the friend's.
    """
    rosters = read.get("rosters") or []
    listing = "\n".join(
        "    --team %-4s %s%s (%d players)"
        % (r["team_id"], r["name"], " [%s]" % r["abbrev"] if r["abbrev"] else "",
           r["size"]) for r in rosters)
    if wanted is None or str(wanted).strip() == "":
        raise EspnPublicError(
            NO_TEAM,
            "Which team in %r is yours? Nothing here guesses that."
            % read.get("name"),
            "Re-run with the team's id:\n%s" % listing,
            read.get("league_id"), read.get("season"))
    text = str(wanted).strip()
    for r in rosters:
        if text == str(r["team_id"]):
            return r
    norm = _norm(text)
    for r in rosters:
        if norm and (_norm(r["name"]) == norm or _norm(r["abbrev"]) == norm):
            return r
    for r in rosters:
        if norm and norm in _norm(r["name"]):
            return r
    raise EspnPublicError(
        NO_TEAM,
        "No team in %r matches %r." % (read.get("name"), text),
        "Pick one of:\n%s" % listing,
        read.get("league_id"), read.get("season"))


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


# --- writing the same files engine/connections.import_league writes -----------

def config_id_for(league_id) -> str:
    return "espn-%s" % str(league_id).strip()


def _guard_overwrite(path: str, config_id: str, overwrite: bool) -> None:
    """Never clobber a league yaml this module did not write.

    leagues/espn-1.yaml is the OWNER's hand-tuned league. A friend whose
    ESPN league id happened to be 1 must not silently overwrite it.
    """
    if overwrite or not os.path.exists(path):
        return
    try:
        with open(path, "r") as fh:
            existing = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        existing = {}
    if (existing.get("source") or "").startswith("espn-public"):
        return
    raise EspnPublicError(
        CONFLICT,
        "%s already exists and was not written by engine/espn_public.py."
        % path,
        "Refusing to overwrite a hand-written league. Move it aside, or "
        "re-run with --overwrite if you really mean to replace it.",
        config_id)


def _league_doc(config_id: str, name: str, teams: int, roster_spots: List[str],
                scoring: Dict, waiver_mode: str, league_id: str, season: int,
                source: str, coverage: Dict, my_slot=None,
                my_team_id=None, team_names=None,
                waiver_budget=None) -> Dict:
    doc = {
        "id": config_id,
        "name": "%s (ESPN)" % name,
        "platform": "espn",
        "teams": int(teams),
        "my_slot": my_slot,
        "waiver_mode": waiver_mode,
        "roster_spots": list(roster_spots),
        "rounds": len(roster_spots),
        "rankings_csv": "data/rankings-%s.csv" % config_id,
        "strategy_file": "strategies/%s.yaml" % config_id,
        "scoring": dict(scoring),
        "espn_league_id": str(league_id),
        "espn_season": int(season),
        "source": source,
        "coverage": dict(coverage),
    }
    if waiver_mode == "faab" and waiver_budget is not None:
        doc["waiver_budget"] = waiver_budget
    if team_names:
        doc["team_names"] = list(team_names)
    if my_team_id is not None:
        doc["host"] = {"league_id": _int_or_text(league_id),
                       "team_id": _int_or_text(my_team_id)}
    return doc


def _int_or_text(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return str(val)


def _write_league_and_roster(league_doc: Dict, header: str, roster_doc: Dict,
                             config_id: str, overwrite: bool) -> Dict:
    league_path = os.path.join(LEAGUES_DIR, "%s.yaml" % config_id)
    _guard_overwrite(league_path, config_id, overwrite)
    _atomic_write(league_path, header + yaml.safe_dump(
        league_doc, default_flow_style=False, sort_keys=False))
    roster_path = os.path.join(ROSTERS_DIR, "%s.yaml" % config_id)
    _atomic_write(roster_path, yaml.safe_dump(
        roster_doc, default_flow_style=False, sort_keys=False))
    return {"league_file": league_path, "roster_file": roster_path}


def _maybe_rebuild(summary: Dict, rebuild: bool, reception: float,
                   teams: int, season: int) -> None:
    from engine import connections
    summary["rebuild"] = None
    if rebuild:
        summary["rebuild"] = connections.rebuild_rankings(
            summary["rankings_csv"], reception, teams, season)


def import_public_league(league_id, season: int = DEFAULT_SEASON,
                         my_team_id=None, rebuild: bool = True,
                         overwrite: bool = False, force: bool = False,
                         quiet: bool = True) -> Dict:
    """Import one PUBLIC ESPN league, mirroring connections.import_league.

    Writes leagues/espn-<id>.yaml (real scoring, roster spots, team count
    and waiver mode straight out of mSettings), data/rosters/espn-<id>.yaml
    for the friend's own team, and data/league-espn-<id>.json holding every
    team's roster, then rebuilds data/rankings-espn-<id>.csv for that exact
    format. Returns a summary dict of everything created.

    Nothing is written until the read succeeded AND the friend's team was
    identified, so a failed import leaves no half-league behind.
    """
    read = read_public_league(league_id, season, force=force, quiet=quiet)
    mine = find_team(read, my_team_id)

    config_id = config_id_for(read["league_id"])
    coverage = {
        "source": "espn-public-api",
        "auto_refresh": True,
        "fetched_at": read["fetched_at"],
        "teams_known": len(read["rosters"]),
        "teams_expected": read["teams"],
        "note": ("Read anonymously from ESPN's public read host because "
                 "this league is set viewable to the public. No cookie, "
                 "password or token was used or stored. If the manager "
                 "turns visibility back off, refreshes will fail with a "
                 "401 and say so."),
    }
    if not read["has_pick_order"]:
        coverage["slot_note"] = ("ESPN published no draft pick order, so "
                                 "slots here are team-id order, not draft "
                                 "order.")

    league_doc = _league_doc(
        config_id, read["name"], read["teams"], read["roster_spots"],
        read["scoring"], read["waiver_mode"], read["league_id"],
        read["season"], "espn-public-api", coverage,
        my_slot=mine.get("slot"), my_team_id=mine["team_id"],
        team_names=[r["name"] for r in read["rosters"]],
        waiver_budget=read["waiver_budget"])

    header = (
        "# Imported from PUBLIC ESPN league %s (%s), season %s, by\n"
        "# engine/espn_public.py on %s. Read with no credentials of any\n"
        "# kind - see docs/CONNECT_ESPN.md.\n"
        % (read["league_id"], read["name"], read["season"],
           read["fetched_at"]))

    roster_doc = {
        "league": config_id,
        "name": mine["name"],
        "size": len(mine["players"]),
        "source": "espn-public-api",
        "espn_team_id": mine["team_id"],
        "fetched_at": read["fetched_at"],
        "players": list(mine["players"]),
    }

    summary = _write_league_and_roster(league_doc, header, roster_doc,
                                       config_id, overwrite)
    summary.update({
        "config_id": config_id,
        "name": league_doc["name"],
        "espn_league_id": read["league_id"],
        "season": read["season"],
        "teams": read["teams"],
        "waiver_mode": read["waiver_mode"],
        "reception": read["reception"],
        "roster_spots": read["roster_spots"],
        "unmapped_spots": read["unmapped_spots"],
        "superflex": "SUPERFLEX" in read["roster_spots"],
        "my_team_id": mine["team_id"],
        "my_team_name": mine["name"],
        "my_slot": mine.get("slot"),
        "my_roster_size": len(mine["players"]),
        "teams_captured": len(read["rosters"]),
        "from_cache": read["from_cache"],
        "drafted": read["drafted"],
        "paste_fed": False,
        "rankings_csv": os.path.join(HERE, league_doc["rankings_csv"]),
        "coverage": coverage,
    })
    # The board is rebuilt BEFORE the league-wide store so the store's
    # rows can resolve against a pool that actually exists.
    _maybe_rebuild(summary, rebuild, read["reception"], read["teams"],
                   read["season"])
    summary["store_file"] = _write_store(config_id, read, league_doc)
    return summary


def _write_store(config_id: str, read: Dict, league_doc: Dict) -> Optional[str]:
    """Every team's roster into engine/leagueview's own store file.

    Slots are real draft slots when ESPN published a pick order (see
    _draft_slots); the coverage note says so when they are not. Names are
    resolved through this league's rankings pool when one exists so the
    rows carry pos/team/bye like every other store row - unresolved names
    are still carried, never invented.
    """
    from engine import leagueview
    from engine.models import LeagueConfig
    cfg = LeagueConfig(dict(league_doc), path="")
    matcher = leagueview.matcher_for(cfg, HERE)
    doc = leagueview.empty_store(cfg, read["season"])
    for team in read["rosters"]:
        rows = []
        for name in team["players"]:
            match = matcher.match(name) if matcher is not None else None
            if match is not None and match.score >= leagueview.MATCH_MIN:
                rows.append(leagueview._row(match.player))
            else:
                rows.append(leagueview._raw_row(name))
        doc["teams"][str(team["slot"])] = {"name": team["name"],
                                           "players": rows}
    doc["source"] = "espn-public-api"
    doc["espn_league_id"] = read["league_id"]
    return leagueview.save_store(doc, config_id, HERE)


# --- the paste path -----------------------------------------------------------

# What a paste import assumes when the friend does not tell us. Every
# assumed key is listed in the league yaml's coverage.assumed so nobody
# mistakes a default for a reading. ESPN's own default new-league lineup.
DEFAULT_PASTE_META = {
    "teams": 10,
    "reception": 0.0,
    "waiver_mode": "priority",
    "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "K",
                     "DEF", "BN", "BN", "BN", "BN", "BN", "BN", "BN"],
}


def import_from_paste(text: str, league_meta: Dict, rebuild: bool = True,
                      overwrite: bool = False, quiet: bool = True) -> Dict:
    """Import a PRIVATE ESPN league from pasted roster text.

    Produces exactly the files import_public_league produces - league
    yaml, own roster yaml, rankings CSV, and the league-wide store when
    the paste covered more than one team - plus a coverage note recording
    that this league is paste-fed and will NOT auto-refresh.

    league_meta carries what the API would otherwise have told us:
        league_id  (required)      season, name, teams, reception,
        waiver_mode, waiver_budget, roster_spots, my_team ("name" or a
        1-based index into the pasted teams).
    Anything missing falls back to DEFAULT_PASTE_META and is named in
    coverage.assumed - a default is never passed off as a reading.

    Parsing is engine/leagueview.parse_league_paste, so nothing is
    invented: every player row is a >= MATCH_MIN match against this
    league's rankings pool and every other line is reported.
    """
    from engine import leagueview
    from engine.models import LeagueConfig

    meta = dict(league_meta or {})
    league_id = str(meta.get("league_id") or "").strip()
    if not league_id:
        raise EspnPublicError(
            BAD_REQUEST, "A paste import still needs the ESPN league id.",
            "It is the leagueId= number in the league's own URL. It names "
            "the files, so the same league updates in place next time.")
    season = int(meta.get("season") or DEFAULT_SEASON)
    config_id = config_id_for(league_id)

    assumed = []
    resolved = {}
    for key, default in sorted(DEFAULT_PASTE_META.items()):
        val = meta.get(key)
        if val is None or val == "":
            resolved[key] = default
            assumed.append(key)
        else:
            resolved[key] = val
    teams = int(resolved["teams"])
    reception = float(resolved["reception"])
    roster_spots = list(resolved["roster_spots"])
    waiver_mode = str(resolved["waiver_mode"]).strip().lower()
    name = str(meta.get("name") or "ESPN league %s" % league_id)

    scoring = {"reception": reception}
    coverage = {
        "source": "paste",
        "auto_refresh": False,
        "pasted_at": _now(),
        "note": ("PASTE-FED. This ESPN league is private, so nothing here "
                 "refreshes on its own: every number is as old as the last "
                 "paste. Re-paste the roster page after every add, drop or "
                 "trade. To switch to automatic refreshes the league "
                 "manager would have to set 'Make League Viewable to "
                 "Public' to Yes - we will never ask for anyone's ESPN "
                 "cookies or password."),
    }
    if assumed:
        coverage["assumed"] = sorted(assumed)
        coverage["assumed_note"] = (
            "These league facts were NOT read from ESPN - they are "
            "defaults. Correct them in this file if the league differs.")

    league_doc = _league_doc(
        config_id, name, teams, roster_spots, scoring, waiver_mode,
        league_id, season, "paste", coverage,
        waiver_budget=meta.get("waiver_budget"))
    cfg = LeagueConfig(dict(league_doc), path="")

    rankings_csv = os.path.join(HERE, league_doc["rankings_csv"])
    rebuild_summary = None
    if rebuild or not os.path.exists(rankings_csv):
        from engine import connections
        rebuild_summary = connections.rebuild_rankings(
            rankings_csv, reception, teams, season)

    matcher = leagueview.matcher_for(cfg, HERE)
    if matcher is None:
        raise EspnPublicError(
            NO_BOARD,
            "No rankings board at %s, so a paste cannot be matched against "
            "anything." % league_doc["rankings_csv"],
            "Run the import again without --no-rebuild (it seeds the board "
            "from ADP), or drop a rankings CSV at that path first. Guessing "
            "at names is not on the table.",
            league_id, season)

    parsed = leagueview.parse_league_paste(text or "", matcher, cfg)
    if not parsed.teams:
        raise EspnPublicError(
            NO_BOARD,
            "That paste produced no teams: %s" % parsed.summary(),
            "Copy the roster area of your ESPN team page - the player names "
            "themselves, not a screenshot. One player per line is ideal; "
            "the slot labels, byes and stat columns around them are fine "
            "and get skipped.",
            league_id, season)

    mine = _pick_pasted_team(parsed, meta.get("my_team"))
    roster_doc = {
        "league": config_id,
        "name": mine.name,
        "size": len(mine.players),
        "source": "paste",
        "auto_refresh": False,
        "pasted_at": coverage["pasted_at"],
        "note": coverage["note"],
        "players": [str(r.get("player")) for r in mine.players],
    }
    header = (
        "# PASTE-FED ESPN league %s, season %s, written by\n"
        "# engine/espn_public.py on %s. This league is private on ESPN, so\n"
        "# it does NOT refresh on its own - re-paste after every roster\n"
        "# move. See docs/CONNECT_ESPN.md.\n"
        % (league_id, season, coverage["pasted_at"]))

    summary = _write_league_and_roster(league_doc, header, roster_doc,
                                       config_id, overwrite)
    store_file = None
    if len(parsed.teams) > 1:
        plan = leagueview.apply_paste(parsed, cfg, None, None, season)
        plan.store["source"] = "paste"
        plan.store["espn_league_id"] = league_id
        store_file = leagueview.save_store(plan.store, config_id, HERE)

    summary.update({
        "store_file": store_file,
        "config_id": config_id,
        "name": league_doc["name"],
        "espn_league_id": league_id,
        "season": season,
        "teams": teams,
        "waiver_mode": waiver_mode,
        "reception": reception,
        "roster_spots": roster_spots,
        "unmapped_spots": sorted({s for s in roster_spots
                                  if s not in KNOWN_SPOTS}),
        "superflex": "SUPERFLEX" in roster_spots,
        "my_team_name": mine.name,
        "my_team_id": None,
        "my_slot": None,
        "my_roster_size": len(mine.players),
        "teams_captured": len(parsed.teams),
        "paste_fed": True,
        "assumed": sorted(assumed),
        "paste_summary": parsed.summary(),
        "unmatched": list(parsed.unmatched),
        "rankings_csv": rankings_csv,
        "coverage": coverage,
        "rebuild": rebuild_summary,
        "from_cache": False,
    })
    return summary


def _pick_pasted_team(parsed, wanted):
    """Which pasted team is the friend's own.

    One team in the paste means one answer. More than one needs a name or
    a 1-based index; without it we list them and stop rather than pick.
    """
    teams = parsed.teams
    if wanted is None or str(wanted).strip() == "":
        if len(teams) == 1:
            return teams[0]
        listing = "\n".join("    --team %d  %s (%d players)"
                            % (i, t.name, len(t))
                            for i, t in enumerate(teams, start=1))
        raise EspnPublicError(
            NO_TEAM,
            "That paste holds %d teams; which one is yours?" % len(teams),
            "Re-run naming it:\n%s" % listing)
    text = str(wanted).strip()
    if text.isdigit():
        idx = int(text)
        if 1 <= idx <= len(teams):
            return teams[idx - 1]
    norm = _norm(text)
    for team in teams:
        if _norm(team.name) == norm:
            return team
    for team in teams:
        if norm and norm in _norm(team.name):
            return team
    listing = "\n".join("    --team %d  %s" % (i, t.name)
                        for i, t in enumerate(teams, start=1))
    raise EspnPublicError(
        NO_TEAM, "No pasted team matches %r." % text,
        "Pick one of:\n%s" % listing)


# --- CLI ----------------------------------------------------------------------

def _print_summary(summary: Dict) -> None:
    print("")
    print("  league   %s" % summary["name"])
    print("  format   %d teams, %s (%s per catch), %s waivers"
          % (summary["teams"],
             _scoring_label(summary["reception"]),
             summary["reception"],
             summary["waiver_mode"]))
    print("  lineup   %s" % ", ".join(summary["roster_spots"]))
    if summary.get("superflex"):
        print("           SUPERFLEX league - a QB can start in the flex.")
    if summary.get("unmapped_spots"):
        print("           carried through unchanged (this engine has no "
              "model for them): %s" % ", ".join(summary["unmapped_spots"]))
    print("  my team  %s (%d players)"
          % (summary.get("my_team_name"), summary["my_roster_size"]))
    if not summary["my_roster_size"]:
        print("           EMPTY - ESPN says this league has %s drafted, so "
              "there is nothing on this roster yet."
              % ("not " if summary.get("drafted") is False else ""))
    print("")
    print("  wrote    %s" % summary["league_file"])
    print("           %s" % summary["roster_file"])
    if summary.get("store_file"):
        print("           %s  (%d team(s))"
              % (summary["store_file"], summary.get("teams_captured", 0)))
    if summary.get("rebuild"):
        rb = summary["rebuild"]
        print("           %s  (%s rows, %s scoring)"
              % (summary["rankings_csv"], rb.get("seeded"), rb.get("scoring")))
    else:
        print("           %s  (rankings rebuild skipped)"
              % summary["rankings_csv"])
    if summary.get("paste_fed"):
        print("")
        print("  PASTE-FED: %s" % summary.get("paste_summary", ""))
        if summary.get("assumed"):
            print("  ASSUMED (not read from ESPN): %s"
                  % ", ".join(summary["assumed"]))
            print("  Fix any of those in %s if the league differs."
                  % summary["league_file"])
        if summary.get("unmatched"):
            print("  %d line(s) did not resolve to a player and were NOT "
                  "guessed at:" % len(summary["unmatched"]))
            for team, line in summary["unmatched"][:10]:
                print("    %s: %s" % (team or "?", line))
        print("  This league does not refresh on its own - re-paste after "
              "every roster move.")
    else:
        print("")
        print("  Read with no credentials. Re-run any time to refresh.")


def _scoring_label(reception: float) -> str:
    if reception >= 1:
        return "full PPR"
    if reception > 0:
        return "%g PPR" % reception
    return "standard (no PPR)"


def _print_teams(read: Dict) -> None:
    print("%s - ESPN league %s, %s season"
          % (read["name"], read["league_id"], read["season"]))
    print("  %d teams, %s, %s waivers, lineup: %s"
          % (read["teams"], _scoring_label(read["reception"]),
             read["waiver_mode"], ", ".join(read["roster_spots"])))
    print("")
    print("  Which team is yours? Re-run with --team <id>:")
    for r in read["rosters"]:
        print("    --team %-4s %-32s %2d players"
              % (r["team_id"], r["name"][:32], r["size"]))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.espn_public",
        description="Import a friend's ESPN league without their cookies: "
                    "read it from ESPN when the league is viewable to the "
                    "public, or from pasted roster text when it is not.")
    parser.add_argument("--league", required=True,
                        help="ESPN league id (the leagueId= number in the "
                             "league URL)")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--team", default=None,
                        help="which team is yours: an ESPN team id or team "
                             "name (a 1-based index with --paste-file). "
                             "Omit to list them.")
    parser.add_argument("--paste-file", default=None,
                        help="text file of a copied ESPN roster page - the "
                             "path for a private league")
    parser.add_argument("--name", default=None,
                        help="league name, paste imports only")
    parser.add_argument("--teams", type=int, default=None,
                        help="how many teams, paste imports only")
    parser.add_argument("--reception", type=float, default=None,
                        help="points per catch (0, 0.5, 1), paste only")
    parser.add_argument("--waiver", default=None, choices=["faab", "priority"],
                        help="waiver style, paste imports only")
    parser.add_argument("--no-rebuild", action="store_true",
                        help="skip the rankings CSV rebuild")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace a league yaml this tool did not write")
    parser.add_argument("--force", action="store_true",
                        help="ignore the disk cache and refetch")
    args = parser.parse_args(argv)

    try:
        if args.paste_file:
            with open(args.paste_file, "r") as fh:
                text = fh.read()
            meta = {"league_id": args.league, "season": args.season,
                    "name": args.name, "teams": args.teams,
                    "reception": args.reception, "waiver_mode": args.waiver,
                    "my_team": args.team}
            summary = import_from_paste(text, meta,
                                        rebuild=not args.no_rebuild,
                                        overwrite=args.overwrite, quiet=False)
        elif args.team is None:
            read = read_public_league(args.league, args.season,
                                      force=args.force, quiet=False)
            _print_teams(read)
            return 0
        else:
            summary = import_public_league(
                args.league, args.season, args.team,
                rebuild=not args.no_rebuild, overwrite=args.overwrite,
                force=args.force, quiet=False)
    except EspnPublicError as exc:
        print("")
        print("  %s: %s" % (exc.kind, exc.message))
        if exc.remediation:
            print("")
            for line in exc.remediation.splitlines():
                print("  %s" % line)
        return 1
    except (IOError, OSError) as exc:
        print("  Could not read %s: %s" % (args.paste_file, exc))
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
