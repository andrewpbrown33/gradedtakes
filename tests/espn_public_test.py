#!/usr/bin/env python3
"""Acceptance test: friend-safe ESPN reader (engine/espn_public.py).

Everything here runs OFFLINE from fixtures. urllib.request.urlopen is
replaced with a router in try/finally, so:
  * any URL the router does not know raises - proving no real network call
    escapes, and
  * every Request object the module built is captured, which is how the
    "never sends a credential" promise is checked rather than asserted.

CACHE_DIR / LEAGUES_DIR / ROSTERS_DIR / HERE are redirected into tempdirs
(tests/mock_draft.py SAVE_DIR discipline) and the network-heavy rankings
rebuild is stubbed with a recorder, so nothing here can touch leagues/,
data/rosters/ or data/cache/.

The fixture shapes mirror what lm-api-reads.fantasy.espn.com actually
returned on 2026-09-09 for public ffl leagues 39 / 164 / 200 / 308 / 349 /
375 (see the engine/espn_public.py docstring for the ids, statuses and
statIds those readings established).

Covers: the public read and its facts, the 401 -> PRIVATE typed failure
carrying the exact remediation text, 404 -> NOT_FOUND, 400 -> BAD_REQUEST,
5xx -> FEED_DOWN with the stale-cache fallback, the fresh-cache
short-circuit, scoring + roster-spot mapping off a realistic mSettings
payload (superflex, IDP passthrough, an ABSENT statId 53 reading as 0.0
PPR), a full public import whose league yaml loads through LeagueConfig,
the overwrite guard over a hand-written league, a paste import producing a
loadable LeagueConfig plus an honest paste-fed coverage note, the
no-credential guarantees (source grep AND captured request headers), and
one LIVE read that is skipped with a reason when offline.

    .venv/bin/python tests/espn_public_test.py
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import yaml                                                   # noqa: E402

from engine import espn_public as ep                          # noqa: E402
from engine.models import LeagueConfig                        # noqa: E402

FAILURES = []
SKIPS = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def skip(label, why):
    print("  SKIP  %s (%s)" % (label, why))
    SKIPS.append("%s: %s" % (label, why))


# --- fixtures (shapes verified live 2026-09-09) ------------------------------

PLAYER_POOL = [
    (3117251, "Bijan Robinson", 2, 1),      # id, name, defaultPositionId, team
    (4362628, "Chase Brown", 2, 5),
    (4432773, "Malik Nabers", 3, 19),
    (4426354, "Emeka Egbuka", 3, 27),
    (4262921, "Garrett Wilson", 3, 20),
    (3915511, "Joe Burrow", 1, 4),
    (3121422, "Dallas Goedert", 4, 21),
    (-16021, "Eagles D/ST", 16, 21),
    (4697745, "Tyler Loop", 5, 33),
    (4429795, "Jonathon Brooks", 2, 29),
    (4035004, "Michael Pittman Jr.", 3, 11),
    (3045147, "Tony Pollard", 2, 10),
]

BENCH_SLOT, IR_SLOT = 20, 21


def _entry(pid, name, pos_id, pro_team, lineup_slot):
    """One mRoster entry, shaped exactly like ESPN's."""
    return {
        "acquisitionType": "DRAFT",
        "injuryStatus": "ACTIVE",
        "lineupSlotId": lineup_slot,
        "playerId": pid,
        "status": "NORMAL",
        "playerPoolEntry": {
            "id": pid,
            "onTeamId": 1,
            "player": {
                "active": True,
                "defaultPositionId": pos_id,
                "eligibleSlots": [pos_id, 20, 21],
                "firstName": name.split(" ")[0],
                "fullName": name,
                "id": pid,
                "injured": False,
                "lastName": " ".join(name.split(" ")[1:]),
                "proTeamId": pro_team,
            },
        },
    }


def _team(tid, name, abbrev, players, starters=5):
    entries = []
    for i, (pid, pname, pos_id, pro_team) in enumerate(players):
        slot = {1: 0, 2: 2, 3: 4, 4: 6, 5: 17, 16: 16}.get(pos_id, BENCH_SLOT)
        if i >= starters:
            slot = BENCH_SLOT
        entries.append(_entry(pid, pname, pos_id, pro_team, slot))
    return {
        "abbrev": abbrev,
        "id": tid,
        "location": None,
        "logo": "",
        "name": name,
        "nickname": None,
        "owners": ["{00000000-0000-0000-0000-%012d}" % tid],
        "primaryOwner": "{00000000-0000-0000-0000-%012d}" % tid,
        "playoffSeed": tid,
        "points": 0.0,
        "record": {},
        "roster": {"appliedStatTotal": 0.0, "entries": entries,
                   "tradeReservedEntries": 0},
        "transactionCounter": {},
        "waiverRank": tid,
    }


TEAM_NAMES = [
    (1, "Fixture Bench Mob", "BNCH"), (2, "Fixture Regulators", "REGS"),
    (3, "Fixture Gridiron Gang", "GRID"), (4, "Fixture Ballers", "BALL"),
    (5, "Fixture Blitz Brigade", "BLTZ"), (6, "Fixture Sack Exchange", "SACK"),
    (7, "Fixture Hail Marys", "HAIL"), (8, "Fixture Red Zone", "RDZN"),
    (9, "Fixture Two Minute Drill", "2MIN"), (10, "Fixture End Arounds", "ENDA"),
]

# The friend's team (id 4) gets the whole pool; the rest get a slice, which
# is enough to exercise the store write without a 200-line fixture.
FIXTURE_TEAMS = []
for _tid, _name, _abbrev in TEAM_NAMES:
    _players = PLAYER_POOL if _tid == 4 else PLAYER_POOL[:4]
    FIXTURE_TEAMS.append(_team(_tid, _name, _abbrev, _players))

# scoringItems as ESPN really spells them. statId 53 == 1.0 makes this a
# full-PPR league; 3/24/42 are points PER YARD (0.04 == 1 point / 25 yards).
PPR_SCORING_ITEMS = [
    {"isReverseItem": False, "points": 0.04, "statId": 3},
    {"isReverseItem": False, "points": 4.0, "statId": 4},
    {"isReverseItem": False, "points": 2.0, "statId": 19},
    {"isReverseItem": False, "points": -2.0, "statId": 20},
    {"isReverseItem": False, "points": 0.1, "statId": 24},
    {"isReverseItem": False, "points": 6.0, "statId": 25},
    {"isReverseItem": False, "points": 0.1, "statId": 42},
    {"isReverseItem": False, "points": 6.0, "statId": 43},
    {"isReverseItem": False, "points": 1.0, "statId": 53},
    {"isReverseItem": False, "points": -2.0, "statId": 72},
    {"isReverseItem": False, "points": 1.0, "statId": 86},
]

PUBLIC_LEAGUE_ID = "424242"

PUBLIC_PAYLOAD = {
    "draftDetail": {"drafted": True, "inProgress": False},
    "gameId": 1,
    "id": int(PUBLIC_LEAGUE_ID),
    "scoringPeriodId": 1,
    "seasonId": 2026,
    "segmentId": 0,
    "status": {"isActive": True, "currentMatchupPeriod": 1},
    "settings": {
        "name": "Fixture Public League",
        "size": 10,
        "isPublic": True,
        "restrictionType": "NONE",
        "acquisitionSettings": {
            "acquisitionBudget": 100, "acquisitionLimit": -1,
            "acquisitionType": "WAIVERS_TRADITIONAL",
            "isUsingAcquisitionBudget": True, "minimumBid": 0,
            "waiverHours": 24, "waiverProcessDays": ["WEDNESDAY"],
        },
        "draftSettings": {
            "type": "SNAKE", "date": 1788030000000, "keeperCount": 0,
            # Team 4 drafts 1st, so its my_slot must come out as 1.
            "pickOrder": [4, 9, 5, 2, 10, 6, 1, 7, 8, 3],
        },
        "rosterSettings": {
            "isBenchUnlimited": False,
            "lineupSlotCounts": {
                "0": 1, "1": 0, "2": 2, "3": 0, "4": 2, "5": 0, "6": 1,
                "7": 0, "8": 0, "9": 0, "10": 0, "11": 0, "12": 0, "13": 0,
                "14": 0, "15": 0, "16": 1, "17": 1, "18": 0, "19": 0,
                "20": 6, "21": 1, "22": 0, "23": 1, "24": 0,
            },
        },
        "scoringSettings": {
            "scoringType": "H2H_POINTS", "playerRankType": "PPR",
            "scoringItems": PPR_SCORING_ITEMS,
        },
    },
    "teams": FIXTURE_TEAMS,
    "members": [{"displayName": "fixture%d" % t[0], "firstName": "Fix",
                 "id": "{00000000-0000-0000-0000-%012d}" % t[0],
                 "lastName": "Ture"} for t in TEAM_NAMES],
}

# A second, deliberately awkward settings block: SUPERFLEX + IDP + head
# coach + NO statId 53 at all. Public league 349 really does omit 53 (it is
# a standard-scoring league) and 39 really does carry OP/IDP/HC slots.
ODD_SETTINGS = {
    "name": "Fixture Superflex IDP",
    "size": 12,
    "isPublic": True,
    "acquisitionSettings": {"acquisitionType": "WAIVERS_TRADITIONAL",
                            "acquisitionBudget": 100,
                            "isUsingAcquisitionBudget": False},
    "draftSettings": {"type": "SNAKE", "pickOrder": []},
    "rosterSettings": {"lineupSlotCounts": {
        "0": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 2, "10": 1,
        "11": 1, "14": 1, "15": 1, "16": 1, "17": 1, "18": 1, "19": 1,
        "20": 6, "21": 4, "23": 1,
    }},
    "scoringSettings": {
        "scoringType": "H2H_POINTS", "playerRankType": "SUPERFLEX",
        "scoringItems": [
            {"points": 4.0, "statId": 4},
            {"points": -1.0, "statId": 20},
            {"points": 6.0, "statId": 25},
            {"points": 6.0, "statId": 43},
            {"points": -1.0, "statId": 72},
        ],
    },
}

ERROR_401 = json.dumps({
    "messages": ["You are not authorized to view this League."],
    "details": [{"message": "You are not authorized to view this League.",
                 "shortMessage": "You are not authorized to view this League.",
                 "resolution": None, "type": "AUTH_LEAGUE_NOT_VISIBLE",
                 "metaData": None}]}).encode()
ERROR_404 = json.dumps({
    "messages": ["Not Found"],
    "details": [{"message": "Not Found", "shortMessage": "Not Found",
                 "resolution": None, "type": "GENERAL_NOT_FOUND",
                 "metaData": None}]}).encode()
ERROR_400 = json.dumps({
    "messages": ["Invalid parameter for 'leagueId'."],
    "cause": "For input string: \"999999999999\""}).encode()


# --- the fake network --------------------------------------------------------

class FakeResponse(object):
    def __init__(self, body):
        self._buf = io.BytesIO(body)
        self.status = 200

    def read(self, *a):
        return self._buf.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Router(object):
    """Answers only the URLs it was told about; anything else is a failure."""

    def __init__(self, routes):
        self.routes = routes            # league id (str) -> (status, bytes)
        self.requests = []              # every urllib Request built

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for league_id, (status, body) in self.routes.items():
            if "/leagues/%s?" % league_id in url or url.endswith(
                    "/leagues/%s" % league_id):
                if status == 200:
                    return FakeResponse(body)
                raise urllib.error.HTTPError(
                    url, status, "fixture", {}, io.BytesIO(body))
        raise AssertionError("unrouted network call escaped the test: %s" % url)


@contextlib.contextmanager
def routed(routes):
    router = Router(routes)
    real = urllib.request.urlopen
    urllib.request.urlopen = router
    try:
        yield router
    finally:
        urllib.request.urlopen = real


@contextlib.contextmanager
def sandbox():
    """Every path engine/espn_public.py writes to, moved into a tempdir."""
    tmp = tempfile.mkdtemp(prefix="espn-public-test-")
    saved = (ep.HERE, ep.LEAGUES_DIR, ep.ROSTERS_DIR, ep.DATA_DIR,
             ep.CACHE_DIR)
    ep.HERE = tmp
    ep.LEAGUES_DIR = os.path.join(tmp, "leagues")
    ep.ROSTERS_DIR = os.path.join(tmp, "data", "rosters")
    ep.DATA_DIR = os.path.join(tmp, "data")
    ep.CACHE_DIR = os.path.join(tmp, "data", "cache")
    for path in (ep.LEAGUES_DIR, ep.ROSTERS_DIR, ep.CACHE_DIR):
        os.makedirs(path)
    try:
        yield tmp
    finally:
        (ep.HERE, ep.LEAGUES_DIR, ep.ROSTERS_DIR, ep.DATA_DIR,
         ep.CACHE_DIR) = saved
        shutil.rmtree(tmp, ignore_errors=True)


RANKINGS_HEADER = ("rank,name,pos,team,bye,tier,adp,adp_stdev,proj_points,"
                   "notes,flags\n")
RANKINGS_ROWS = [
    "Bijan Robinson,RB,ATL,5", "Chase Brown,RB,CIN,10",
    "Malik Nabers,WR,NYG,14", "Emeka Egbuka,WR,TB,9",
    "Garrett Wilson,WR,NYJ,9", "Joe Burrow,QB,CIN,10",
    "Dallas Goedert,TE,PHI,9", "Philadelphia Defense,DEF,PHI,9",
    "Tyler Loop,K,BAL,7", "Jonathon Brooks,RB,CAR,14",
    "Michael Pittman Jr.,WR,IND,11", "Tony Pollard,RB,TEN,10",
    "Saquon Barkley,RB,PHI,9", "Ja'Marr Chase,WR,CIN,10",
]


def write_rankings(path):
    """A small board so the paste matcher has a real pool to match against."""
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w") as fh:
        fh.write(RANKINGS_HEADER)
        for i, row in enumerate(RANKINGS_ROWS, start=1):
            name, pos, team, bye = row.split(",")
            fh.write("%d,%s,%s,%s,%s,1,%d,1.0,120.0,,\n"
                     % (i, name, pos, team, bye, i))
    return path


class RebuildRecorder(object):
    """Stands in for connections.rebuild_rankings - writes the board, no net."""

    def __init__(self):
        self.calls = []

    def __call__(self, csv_path, reception, teams, year=2026):
        self.calls.append({"csv_path": csv_path, "reception": reception,
                           "teams": teams, "year": year})
        write_rankings(csv_path)
        return {"seeded": len(RANKINGS_ROWS), "filled": len(RANKINGS_ROWS),
                "tiered": None,
                "scoring": ("ppr" if reception >= 1
                            else ("half" if reception > 0 else "std"))}


@contextlib.contextmanager
def stubbed_rebuild():
    from engine import connections
    real = connections.rebuild_rankings
    rec = RebuildRecorder()
    connections.rebuild_rankings = rec
    try:
        yield rec
    finally:
        connections.rebuild_rankings = real


def routes_ok():
    return {PUBLIC_LEAGUE_ID: (200, json.dumps(PUBLIC_PAYLOAD).encode())}


# --- 1. reading a public league ----------------------------------------------

def test_public_read():
    print("\n1. PUBLIC LEAGUE READS UNAUTHENTICATED")
    with sandbox(), routed(routes_ok()) as router:
        read = ep.read_public_league(PUBLIC_LEAGUE_ID, 2026)

    check(len(router.requests) == 1,
          "exactly one HTTP request for a whole league")
    url = router.requests[0].full_url
    check(url.startswith("https://lm-api-reads.fantasy.espn.com/apis/v3/"
                         "games/ffl/seasons/2026/segments/0/leagues/%s?"
                         % PUBLIC_LEAGUE_ID),
          "hits ESPN's read host at seasons/2026/segments/0/leagues/<id>")
    for view in ("mSettings", "mTeam", "mRoster"):
        check("view=%s" % view in url, "asks for view=%s" % view)

    check(read["name"] == "Fixture Public League", "league name read")
    check(read["is_public"] is True, "settings.isPublic carried through")
    check(read["teams"] == 10, "team count from settings.size")
    check(read["reception"] == 1.0, "statId 53 -> 1.0 reception (full PPR)")
    check(read["waiver_mode"] == "faab",
          "isUsingAcquisitionBudget true -> faab")
    check(read["waiver_budget"] == 100, "FAAB budget carried")
    check(read["drafted"] is True, "draftDetail.drafted carried")
    check(len(read["rosters"]) == 10, "all ten teams' rosters returned")

    mine = [r for r in read["rosters"] if r["team_id"] == 4][0]
    check(mine["name"] == "Fixture Ballers", "team name off mTeam")
    check(len(mine["players"]) == len(PLAYER_POOL),
          "every roster entry read (%d players)" % len(PLAYER_POOL))
    check("Bijan Robinson" in mine["players"], "a real player name came back")
    check("Eagles Defense" in mine["players"],
          "'Eagles D/ST' rewritten to 'Eagles Defense' for the matcher")
    check("Eagles D/ST" not in mine["players"],
          "the D/ST spelling the pool cannot match is not carried")
    check(mine["slot"] == 1,
          "draftSettings.pickOrder gives team 4 the real draft slot 1")
    check(len(mine["bench"]) == len(PLAYER_POOL) - 5,
          "lineupSlotId 20/21 split starters from bench")

    names = set(read.get("rosters")[0].keys())
    check("owner" not in names and "members" not in read,
          "no owner display names or member emails are returned")


# --- 2. typed failures --------------------------------------------------------

def test_typed_failures():
    print("\n2. TYPED FAILURES (401 / 404 / 400 / 5xx)")
    with sandbox(), routed({"1": (401, ERROR_401)}):
        try:
            ep.read_public_league("1", 2026)
            check(False, "a private league raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.PRIVATE, "401 -> kind PRIVATE")
            check(exc.status == 401, "the HTTP status is on the error")
            rem = exc.remediation
            check("Make League Viewable to Public" in rem,
                  "remediation names the exact ESPN setting")
            check("League -> Settings -> Basic Settings" in rem
                  and "Edit Basic Settings" in rem,
                  "remediation gives ESPN's own documented click path")
            check("web only" in rem,
                  "remediation warns the phone app cannot change it")
            check("espn_s2" in rem and "SWID" in rem
                  and "does not accept" in rem,
                  "remediation refuses cookies out loud")
            check("--paste-file" in rem,
                  "remediation offers the paste path with the real command")
            check("switch it back off" in rem,
                  "remediation says the setting is reversible")
            check("anyone who knows the league id" in rem,
                  "remediation states the honest cost of going public")
            check("1" == exc.league_id, "the error knows which league")
            check("You are not authorized" in exc.message,
                  "ESPN's own words are quoted, not paraphrased away")
            check("Make League Viewable to Public" in str(exc),
                  "str(exc) carries the remediation for a bare printer")

    with sandbox(), routed({"2": (404, ERROR_404)}):
        try:
            ep.read_public_league("2", 2026)
            check(False, "a missing league raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.NOT_FOUND, "404 -> kind NOT_FOUND")
            check("--season" in exc.remediation,
                  "NOT_FOUND suggests trying another season")

    with sandbox(), routed({"999999999999": (400, ERROR_400)}):
        try:
            ep.read_public_league("999999999999", 2026)
            check(False, "a malformed id raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.BAD_REQUEST, "400 -> kind BAD_REQUEST")

    with sandbox(), routed({"7": (503, b"upstream boom")}):
        try:
            ep.read_public_league("7", 2026)
            check(False, "a 5xx with no cache raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.FEED_DOWN, "503 -> kind FEED_DOWN")
            check("permissions" in exc.remediation,
                  "FEED_DOWN says it is not a permissions problem")

    # PRIVATE and NOT_FOUND must never be served from a stale cache: a
    # league that just went private has to say so.
    with sandbox():
        path = ep.cache_path(PUBLIC_LEAGUE_ID, 2026)
        with open(path, "w") as fh:
            json.dump(PUBLIC_PAYLOAD, fh)
        os.utime(path, (time.time() - 86400, time.time() - 86400))
        with routed({PUBLIC_LEAGUE_ID: (401, ERROR_401)}):
            try:
                ep.read_public_league(PUBLIC_LEAGUE_ID, 2026)
                check(False, "a league that went private raises")
            except ep.EspnPublicError as exc:
                check(exc.kind == ep.PRIVATE,
                      "a now-private league reports PRIVATE, never replays "
                      "the stale cache")

    # FEED_DOWN, by contrast, does fall back - and says so.
    with sandbox():
        path = ep.cache_path(PUBLIC_LEAGUE_ID, 2026)
        with open(path, "w") as fh:
            json.dump(PUBLIC_PAYLOAD, fh)
        os.utime(path, (time.time() - 86400, time.time() - 86400))
        with routed({PUBLIC_LEAGUE_ID: (503, b"boom")}):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                read = ep.read_public_league(PUBLIC_LEAGUE_ID, 2026,
                                             quiet=False)
            check(read["from_cache"] is True,
                  "a 5xx falls back to the stale cache")
            check("cached copy" in buf.getvalue(),
                  "the stale-cache fallback says so out loud")


def test_cache():
    print("\n3. CACHE (engine/adp.py discipline)")
    with sandbox():
        with routed(routes_ok()) as router:
            ep.read_public_league(PUBLIC_LEAGUE_ID, 2026)
            check(len(router.requests) == 1, "first read hits the network")
            ep.read_public_league(PUBLIC_LEAGUE_ID, 2026)
            check(len(router.requests) == 1,
                  "a second read inside the window is served from disk")
            ep.read_public_league(PUBLIC_LEAGUE_ID, 2026, force=True)
            check(len(router.requests) == 2, "--force refetches")
        check(os.path.exists(ep.cache_path(PUBLIC_LEAGUE_ID, 2026)),
              "the cache file lands in data/cache/")


# --- 4. settings mapping ------------------------------------------------------

def test_mapping():
    print("\n4. SCORING AND ROSTER-SPOT MAPPING")
    spots = ep.roster_spots_from_slots(
        PUBLIC_PAYLOAD["settings"]["rosterSettings"]["lineupSlotCounts"])
    check(spots == ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "K", "DEF"]
          + ["BN"] * 6 + ["IR"],
          "a normal ESPN lineup maps to the engine's roster_spots, in "
          "ESPN's own order")

    odd = ep.roster_spots_from_slots(
        ODD_SETTINGS["rosterSettings"]["lineupSlotCounts"])
    check(odd.count("SUPERFLEX") == 2,
          "lineupSlotId 7 (OP) maps to SUPERFLEX, twice")
    check(odd.count("W/R") == 1 and odd.count("W/T") == 1
          and odd.count("W/R/T") == 1,
          "slots 3 / 5 / 23 map to W/R, W/T and W/R/T")
    for token in ("LB", "DL", "DB", "DP", "P", "HC"):
        check(token in odd, "IDP/oddball slot %s is carried through "
                            "unchanged, not dropped" % token)
    check(odd.count("BN") == 6 and odd.count("IR") == 4,
          "bench and IR counts survive")

    ppr = ep.scoring_from_items(PPR_SCORING_ITEMS)
    check(ppr["reception"] == 1.0, "statId 53 -> reception")
    check(ppr["passing_td"] == 4.0 and ppr["rushing_td"] == 6.0
          and ppr["receiving_td"] == 6.0,
          "statIds 4 / 25 / 43 -> passing, rushing, receiving TD")
    check(ppr["interception"] == -2.0 and ppr["fumble_lost"] == -2.0,
          "statIds 20 / 72 -> interception and fumble lost")
    check(ppr["passing_yards_per_point"] == 25.0
          and ppr["rushing_yards_per_point"] == 10.0
          and ppr["receiving_yards_per_point"] == 10.0,
          "points-per-yard inverted into yards-per-point")

    std = ep.scoring_from_items(ODD_SETTINGS["scoringSettings"]["scoringItems"])
    check(std["reception"] == 0.0,
          "an ABSENT statId 53 reads as 0.0 PPR (public league 349's real "
          "shape), never as unknown")
    check("passing_yards_per_point" not in std,
          "a scoring category ESPN did not send is not invented")

    check(ep.waiver_mode_from_settings(
        {"acquisitionType": "WAIVERS_TRADITIONAL",
         "isUsingAcquisitionBudget": True}) == "faab",
        "isUsingAcquisitionBudget decides FAAB, not acquisitionType "
        "(public league 164 is TRADITIONAL *with* a budget)")
    check(ep.waiver_mode_from_settings(
        {"acquisitionType": "WAIVERS_CONTINUOUS",
         "isUsingAcquisitionBudget": False}) == "priority",
        "no budget -> priority")
    check(ep.waiver_mode_from_settings({}) == "priority",
          "an empty acquisitionSettings falls back to priority, not a crash")

    check(ep.player_name({"fullName": "Seahawks D/ST",
                          "defaultPositionId": 16}) == "Seahawks Defense",
          "D/ST names are rewritten once, for the matcher")
    check(ep.player_name({"fullName": "Ka'imi Fairbairn",
                          "defaultPositionId": 5}) == "Ka'imi Fairbairn",
          "everyone else keeps ESPN's own spelling")
    check(ep.player_name({"firstName": "Bijan", "lastName": "Robinson",
                          "defaultPositionId": 2}) == "Bijan Robinson",
          "a missing fullName falls back to first + last")


# --- 5. the full public import ------------------------------------------------

def test_public_import():
    print("\n5. PUBLIC IMPORT WRITES THE SAME FILES AS connections")
    with sandbox() as tmp, routed(routes_ok()), stubbed_rebuild() as rebuild:
        summary = ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, 4)

        league_path = os.path.join(tmp, "leagues", "espn-424242.yaml")
        roster_path = os.path.join(tmp, "data", "rosters", "espn-424242.yaml")
        check(summary["league_file"] == league_path,
              "wrote leagues/espn-<id>.yaml")
        check(summary["roster_file"] == roster_path,
              "wrote data/rosters/espn-<id>.yaml")
        check(os.path.exists(league_path) and os.path.exists(roster_path),
              "both files are really on disk")

        cfg = LeagueConfig.load(league_path)
        check(cfg.id == "espn-424242", "league yaml loads through LeagueConfig")
        check(cfg.platform == "espn", "platform is espn")
        check(cfg.teams == 10, "team count survives the round trip")
        check(cfg.ppr == 1.0 and cfg.scoring_label() == "ppr",
              "LeagueConfig reads full PPR out of the imported scoring")
        check(cfg.waiver_mode == "faab", "waiver mode survives")
        check(cfg.rounds == len(cfg.roster_spots) == 16,
              "rounds match the roster spots (1 QB, 2 RB, 2 WR, TE, FLEX, "
              "K, D/ST, 6 bench, IR)")
        check(cfg.my_slot == 1, "my_slot is the real draft slot from pickOrder")
        check(cfg.host == {"league_id": "424242", "team_id": "4"},
              "host deep-link keys point at the friend's own team")
        starters = cfg.starter_counts()
        check(round(starters["RB"], 2) == round(2 + 1 / 3.0, 2),
              "starter demand computes (2 RB + a third of the flex)")

        with open(roster_path) as fh:
            roster = yaml.safe_load(fh)
        check(roster["league"] == "espn-424242", "roster yaml names the league")
        check(roster["size"] == len(PLAYER_POOL) == len(roster["players"]),
              "roster yaml holds the friend's whole team")
        check("Bijan Robinson" in roster["players"], "with real names in it")
        check(roster["source"] == "espn-public-api",
              "roster yaml records where it came from")

        with open(league_path) as fh:
            doc = yaml.safe_load(fh)
        cov = doc.get("coverage") or {}
        check(cov.get("source") == "espn-public-api"
              and cov.get("auto_refresh") is True,
              "coverage note says this league auto-refreshes")
        check("No cookie, password or token" in cov.get("note", ""),
              "coverage note states no credential was used")
        check(doc.get("team_names") and len(doc["team_names"]) == 10,
              "every team name is recorded for the league view")

        check(len(rebuild.calls) == 1, "the rankings rebuild ran once")
        call = rebuild.calls[0]
        check(call["reception"] == 1.0 and call["teams"] == 10,
              "rebuild got THIS league's format (1.0 PPR, 10 teams)")
        check(call["csv_path"].endswith("data/rankings-espn-424242.csv"),
              "into this league's own rankings CSV")

        store = summary.get("store_file")
        check(store and os.path.exists(store),
              "every team's roster landed in the league-wide store")
        with open(store) as fh:
            store_doc = json.load(fh)
        check(len(store_doc["teams"]) == 10, "all ten teams in the store")
        check(store_doc["teams"]["1"]["name"] == "Fixture Ballers",
              "the store is keyed by real draft slot (team 4 drafts 1st)")
        row = [r for r in store_doc["teams"]["1"]["players"]
               if r["player"] == "Bijan Robinson"][0]
        check(row["pos"] == "RB" and row["nfl"] == "ATL",
              "store rows resolved against the rebuilt board")

        check(summary["superflex"] is False, "not a superflex league")
        check(summary["paste_fed"] is False, "not paste-fed")
        check(summary["drafted"] is True,
              "the summary carries whether the league has drafted, so an "
              "empty roster can be explained rather than look like a bug")

    # no --team means no guessing
    with sandbox(), routed(routes_ok()):
        try:
            ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, None)
            check(False, "an import with no team raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.NO_TEAM,
                  "no --team -> NO_TEAM rather than a guess")
            check("--team 4" in exc.remediation
                  and "Fixture Ballers" in exc.remediation,
                  "the error lists every team with the flag to pick it")

    with sandbox(), routed(routes_ok()), stubbed_rebuild():
        summary = ep.import_public_league(PUBLIC_LEAGUE_ID, 2026,
                                          "Fixture Ballers")
        check(summary["my_team_id"] == 4, "a team NAME resolves too")

    with sandbox(), routed(routes_ok()):
        try:
            ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, "Nobody's Team")
            check(False, "an unknown team raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.NO_TEAM, "an unknown team -> NO_TEAM")

    # a failed import leaves nothing behind
    with sandbox() as tmp, routed({PUBLIC_LEAGUE_ID: (401, ERROR_401)}):
        with contextlib.suppress(ep.EspnPublicError):
            ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, 4)
        check(os.listdir(os.path.join(tmp, "leagues")) == [],
              "a private league writes no half-league into leagues/")


def test_overwrite_guard():
    print("\n6. NEVER CLOBBERS A HAND-WRITTEN LEAGUE")
    with sandbox() as tmp, routed(routes_ok()), stubbed_rebuild():
        path = os.path.join(tmp, "leagues", "espn-424242.yaml")
        with open(path, "w") as fh:
            yaml.safe_dump({"id": "espn-424242", "name": "Andrew's own",
                            "platform": "espn", "teams": 8}, fh)
        try:
            ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, 4)
            check(False, "importing over a hand-written league raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.CONFLICT, "-> kind CONFLICT")
            check("--overwrite" in exc.remediation,
                  "and says how to proceed on purpose")
        with open(path) as fh:
            check(yaml.safe_load(fh)["name"] == "Andrew's own",
                  "the hand-written file is untouched")

        ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, 4, overwrite=True)
        with open(path) as fh:
            check("Fixture Public League" in (yaml.safe_load(fh)["name"]),
                  "--overwrite replaces it deliberately")

        # a re-import of our own file needs no flag
        ep.import_public_league(PUBLIC_LEAGUE_ID, 2026, 4)
        check(True, "re-importing a league this tool wrote just updates it")


# --- 7. the paste path --------------------------------------------------------

ESPN_ROSTER_PASTE = """
STARTERS
QB   Joe Burrow Cin QB   BYE 10   18.4
RB   Bijan Robinson Atl RB   @NO   21.2
RB   Chase Brown Cin RB   vs PIT   14.9
WR   Malik Nabers NYG WR   @DAL   16.1
WR   Garrett Wilson NYJ WR   vs BUF   13.7
TE   Dallas Goedert Phi TE   @KC   9.2
FLEX Emeka Egbuka TB WR   vs ATL   11.8
D/ST Eagles D/ST Phi D/ST   @KC   7.0
K    Tyler Loop Bal K   vs CLE   8.1
BENCH
Jonathon Brooks Car RB   O
Michael Pittman Jr. Ind WR
Tony Pollard Ten RB
"""


def test_paste_import():
    print("\n7. PASTE IMPORT (a private league, first class)")
    with sandbox() as tmp, stubbed_rebuild() as rebuild:
        summary = ep.import_from_paste(
            ESPN_ROSTER_PASTE,
            {"league_id": "284298483", "season": 2026,
             "name": "The Original 8", "teams": 8, "reception": 1.0,
             "waiver_mode": "priority",
             "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T",
                              "K", "DEF", "BN", "BN", "BN", "BN", "BN",
                              "BN", "BN"]})

        league_path = os.path.join(tmp, "leagues", "espn-284298483.yaml")
        roster_path = os.path.join(tmp, "data", "rosters",
                                   "espn-284298483.yaml")
        check(os.path.exists(league_path), "paste wrote the league yaml")
        check(os.path.exists(roster_path), "paste wrote the roster yaml")

        cfg = LeagueConfig.load(league_path)
        check(cfg.id == "espn-284298483",
              "a pasted league loads through LeagueConfig")
        check(cfg.teams == 8 and cfg.ppr == 1.0 and cfg.waiver_mode
              == "priority",
              "the format the friend told us survives the round trip")
        check(cfg.rounds == len(cfg.roster_spots),
              "roster spots and rounds agree")

        with open(league_path) as fh:
            doc = yaml.safe_load(fh)
        cov = doc["coverage"]
        check(cov["source"] == "paste", "coverage note says source: paste")
        check(cov["auto_refresh"] is False,
              "coverage note says it will NOT auto-refresh")
        check("Re-paste" in cov["note"] and "private" in cov["note"],
              "coverage note tells the human what that costs them")
        check("cookies or password" in cov["note"],
              "coverage note repeats that we never ask for credentials")
        check("assumed" not in cov,
              "nothing was assumed when the friend supplied the format")

        with open(roster_path) as fh:
            roster = yaml.safe_load(fh)
        check(roster["source"] == "paste"
              and roster["auto_refresh"] is False,
              "the roster yaml is marked paste-fed too")
        check("Bijan Robinson" in roster["players"],
              "a starter came through the paste")
        check("Tony Pollard" in roster["players"],
              "a bench player came through too")
        check("Philadelphia Defense" in roster["players"],
              "'Eagles D/ST' matched the pool's 'Philadelphia Defense'")
        check(len(roster["players"]) == 12,
              "all twelve pasted players landed, none invented")
        check(summary["my_roster_size"] == 12, "summary agrees")
        check(summary["paste_fed"] is True, "summary says paste-fed")
        check(rebuild.calls and rebuild.calls[0]["reception"] == 1.0,
              "the paste import rebuilt the board for THIS format")

    # defaults are recorded as assumptions, never passed off as readings
    with sandbox() as tmp, stubbed_rebuild():
        summary = ep.import_from_paste(
            ESPN_ROSTER_PASTE, {"league_id": "555"})
        with open(summary["league_file"]) as fh:
            cov = yaml.safe_load(fh)["coverage"]
        check(sorted(cov.get("assumed") or []) ==
              ["reception", "roster_spots", "teams", "waiver_mode"],
              "every unstated league fact is listed as assumed")
        check("NOT read from ESPN" in cov.get("assumed_note", ""),
              "and labelled as a default rather than a reading")

    # two teams in one paste: pick one or be told to
    with sandbox(), stubbed_rebuild():
        two = ESPN_ROSTER_PASTE + "\n\nThe Other Guys\nSaquon Barkley Phi RB\nJa'Marr Chase Cin WR\n"
        try:
            ep.import_from_paste(two, {"league_id": "556"})
            check(False, "an ambiguous paste raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.NO_TEAM,
                  "a multi-team paste with no --team -> NO_TEAM")
            check("The Other Guys" in exc.remediation,
                  "and lists the teams it found")

    with sandbox() as tmp, stubbed_rebuild():
        two = ESPN_ROSTER_PASTE + "\n\nThe Other Guys\nSaquon Barkley Phi RB\nJa'Marr Chase Cin WR\n"
        summary = ep.import_from_paste(two, {"league_id": "556",
                                             "my_team": "The Other Guys"})
        check(summary["my_team_name"] == "The Other Guys",
              "naming the team picks it")
        check(summary["store_file"] and os.path.exists(summary["store_file"]),
              "a multi-team paste also fills the league-wide store")

    with sandbox(), stubbed_rebuild():
        try:
            ep.import_from_paste("", {"league_id": "557"})
            check(False, "an empty paste raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.NO_BOARD,
                  "an empty paste fails honestly instead of writing nothing "
                  "shaped like a league")

    with sandbox():
        try:
            ep.import_from_paste(ESPN_ROSTER_PASTE, {})
            check(False, "a paste with no league id raises")
        except ep.EspnPublicError as exc:
            check(exc.kind == ep.BAD_REQUEST,
                  "a paste still needs the league id")


# --- 8. the promise: no credential ever leaves this module -------------------

def test_no_credentials():
    print("\n8. NO COOKIE, EVER")
    with open(os.path.join(HERE, "engine", "espn_public.py")) as fh:
        src = fh.read()

    for needle in ("espn_secrets", "load_secrets", "HTTPCookieProcessor",
                   "http.cookiejar", "CookieJar", "build_opener",
                   "add_header", "engine.espn ", "from engine import espn\n",
                   "lm-api-writes", "https://fantasy.espn.com",
                   "urlencode", "urlopen(url"):
        check(needle not in src,
              "the module never mentions %r" % needle)

    check(src.count("\"Cookie\"") == 0 and src.count("'Cookie'") == 0,
          "no Cookie header is ever named in code")
    check(src.count("espn_s2") == ep.PRIVATE_REMEDIATION.count("espn_s2"),
          "espn_s2 appears ONLY inside the remediation text that refuses it")
    check(src.count("SWID") == ep.PRIVATE_REMEDIATION.count("SWID"),
          "SWID likewise")
    check(set(ep.HEADERS) == {"User-Agent", "Accept"},
          "the complete header set is User-Agent + Accept")

    with sandbox(), routed(routes_ok()) as router:
        ep.read_public_league(PUBLIC_LEAGUE_ID, 2026)
        ep.read_public_league(PUBLIC_LEAGUE_ID, 2026, force=True)
        check(len(router.requests) == 2, "two requests were captured")
        for req in router.requests:
            headers = dict((k.lower(), v) for k, v in req.header_items())
            check(all(bad not in headers for bad in ep.FORBIDDEN_HEADERS),
                  "the request carries none of %s"
                  % ", ".join(ep.FORBIDDEN_HEADERS))
            check(req.get_header("Cookie") is None,
                  "Request.get_header('Cookie') is None")
            check(sorted(headers) == ["accept", "user-agent"],
                  "the request carries exactly two headers")
            check(req.data is None and req.get_method() == "GET",
                  "it is a GET with no body - advise-only, never a write")
            check(req.full_url.startswith(ep.READ_HOST + "/"),
                  "and it only ever talks to ESPN's read host")

    check(ep.API.startswith(ep.READ_HOST),
          "the only URL template points at the read host")
    check(src.count("https://") == 1,
          "exactly ONE https:// URL exists in the whole module, and it is "
          "the read host")


# --- 9. one live read, skipped with a reason when offline ---------------------

LIVE_IDS = ["349", "308", "164", "200", "39"]


def test_live():
    print("\n9. LIVE READ (skipped with a reason when offline)")
    if os.environ.get("WARROOM_NO_NETWORK"):
        skip("live public read", "WARROOM_NO_NETWORK is set")
        return
    with sandbox():
        reasons = []
        for league_id in LIVE_IDS:
            try:
                read = ep.read_public_league(league_id, 2026, force=True,
                                             quiet=True)
            except ep.EspnPublicError as exc:
                reasons.append("%s: %s" % (league_id, exc.kind))
                if exc.kind in (ep.FEED_DOWN,):
                    break        # the network is down; stop hammering ESPN
                continue
            check(read["is_public"] is True,
                  "live league %s answers 200 and says isPublic"
                  % league_id)
            check(read["teams"] >= 4 and len(read["rosters"]) >= 4,
                  "live league %s returned %d teams' rosters"
                  % (league_id, len(read["rosters"])))
            check(bool(read["roster_spots"]),
                  "live league %s produced engine roster_spots: %s"
                  % (league_id, ", ".join(read["roster_spots"][:6]) + " ..."))
            check(any(r["players"] for r in read["rosters"]),
                  "live league %s returned real rosters unauthenticated"
                  % league_id)
            return
        skip("live public read",
             "no known public league was readable (%s) - offline, or those "
             "leagues changed" % "; ".join(reasons) or "no response")


def main():
    print("=" * 68)
    print("ESPN PUBLIC-READ ACCEPTANCE TEST (offline fixtures + 1 live)")
    print("=" * 68)

    before_leagues = sorted(os.listdir(os.path.join(HERE, "leagues")))
    before_rosters = sorted(os.listdir(os.path.join(HERE, "data", "rosters")))

    test_public_read()
    test_typed_failures()
    test_cache()
    test_mapping()
    test_public_import()
    test_overwrite_guard()
    test_paste_import()
    test_no_credentials()
    test_live()

    print("\n10. PRODUCTION STATE UNTOUCHED")
    check(before_leagues == sorted(os.listdir(os.path.join(HERE, "leagues"))),
          "real leagues/ listing is unchanged (every write went to a tempdir)")
    check(before_rosters == sorted(os.listdir(os.path.join(
        HERE, "data", "rosters"))),
        "real data/rosters/ listing is unchanged")
    check(ep.LEAGUES_DIR == os.path.join(HERE, "leagues"),
          "module paths were restored after the sandboxes")

    print("\n" + "=" * 68)
    if SKIPS:
        print("SKIPPED: %d" % len(SKIPS))
        for s in SKIPS:
            print("  - %s" % s)
    if FAILURES:
        print("FAILED: %d" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
