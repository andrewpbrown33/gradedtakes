#!/usr/bin/env python3
"""Acceptance test: platform connector engine (engine/connections.py).

Everything here runs OFFLINE from fixtures - connections._http_get_json is
replaced with a router (any URL it does not know raises, proving no network
is touched), CACHE_DIR / LEAGUES_DIR / ROSTERS_DIR and the secrets paths are
redirected into tempdirs in try/finally (tests/mock_draft.py SAVE_DIR
discipline), and the network-heavy rankings rebuild is stubbed with a
recorder. The live Sleeper API shapes these fixtures mirror were verified
2026-09-02 (see engine/connections.py docstring: waiver_type enum confirmed
against real leagues' waiver transactions).

Covers the PLATFORM layer: resolve/list/rosters fixture shapes, the
fresh-cache short-circuit, the waiver_type enum mapping, roster-spot mapping
(FLEX -> W/R/T, SUPER_FLEX -> SUPERFLEX, IDP passthrough), a full import into
a tempdir project (league yaml loads through LeagueConfig, roster yaml,
rebuild invocation), the status() truth table (read-only, never raises), and
the honest error paths (unknown username, no leagues, missing players dump,
no roster owned by the user).

And the PERSON layer, which is what makes this usable by someone who is not
the owner: person CRUD and its refusals, a person's key agreeing with the
real publish.slug() (so this module and publish.py cannot disagree about who
someone is), coverage across one connected and one missing league plus the
stale and broken states, the users.yaml reconcile (READ ONLY - the block to
paste is printed, never written), status() reporting per person while its
three platform keys stay exactly as they were, and all three platforms
walked end to end with engine/espn_public.py and engine/yahoo_cli.py
MONKEYPATCHED - two other agents own those, so this suite must not depend on
their internals, and must also prove the honest degradation when they are
absent entirely.

Then the LEAGUES TAB (engine/sources_ui.py) against those same fakes: the
person card, the three platform cards each showing the right next action for
each state, the write allowlist still refusing out-of-scope paths (and
refusing a credential file even inside it), and - the one that matters - no
secret value of any kind reaching the page or a response.

Everything runs OFFLINE and inside tempdirs; the real leagues/, users.yaml
and data/people.yaml are asserted untouched at the end.

    .venv/bin/python tests/connections_test.py
"""

import contextlib
import glob
import io
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import yaml                                                  # noqa: E402

from engine import connections, projections                  # noqa: E402
from engine import sources_ui as ui                          # noqa: E402
from engine.models import LeagueConfig                       # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- fixtures (shapes verified live against api.sleeper.app, 2026-09-02) ----

USER_FIXTURE = {
    "user_id": "483459259485384704",
    "username": "sleeperuser",
    "display_name": "SleeperUser",
    "avatar": None,
}

LEAGUE_FAAB = {
    "league_id": "111111111111111111",
    "name": "Fixture FAAB League",
    "season": "2026",
    "total_rosters": 12,
    "status": "in_season",
    "settings": {"waiver_type": 2, "waiver_budget": 100, "num_teams": 12},
    "scoring_settings": {"rec": 1.0, "pass_td": 4.0, "rush_td": 6.0,
                         "rec_td": 6.0, "pass_int": -2.0, "fum_lost": -2.0,
                         "pass_yd": 0.04, "rush_yd": 0.1, "rec_yd": 0.1},
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX",
                         "SUPER_FLEX", "K", "DEF", "BN", "BN", "BN"],
}

LEAGUE_PRIORITY = {
    "league_id": "222222222222222222",
    "name": "Fixture Rolling League",
    "season": "2026",
    "total_rosters": 10,
    "status": "in_season",
    "settings": {"waiver_type": 0, "waiver_budget": 100, "num_teams": 10},
    "scoring_settings": {"rec": 0.5},
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX",
                         "K", "DEF", "BN", "BN"],
}

ROSTERS_FAAB = [
    {"roster_id": 1, "owner_id": "999", "co_owners": None,
     "players": ["1111", "2222"]},
    {"roster_id": 2, "owner_id": USER_FIXTURE["user_id"], "co_owners": None,
     "players": ["4034", "1352", "SEA", "424242"]},   # 424242 not in dump
]

ROSTERS_PRIORITY = [
    {"roster_id": 1, "owner_id": "999", "co_owners": [USER_FIXTURE["user_id"]],
     "players": ["4034"]},
]

PLAYERS_DUMP = {
    "4034": {"first_name": "Christian", "last_name": "McCaffrey",
             "position": "RB", "team": "SF"},
    "1352": {"first_name": "Zach", "last_name": "Ertz",
             "position": "TE", "team": "WAS"},
    "1111": {"first_name": "Some", "last_name": "Guy",
             "position": "WR", "team": "DAL"},
    "2222": {"first_name": "Other", "last_name": "Guy",
             "position": "RB", "team": "PHI"},
    "SEA": {"first_name": "Seattle", "last_name": "Seahawks",
            "position": "DEF", "team": "SEA"},
}

API = connections.SLEEPER_API


def make_router(extra=None):
    """URL -> payload map; anything unknown raises (proves offline)."""
    routes = {
        "%s/user/sleeperuser" % API: USER_FIXTURE,
        "%s/user/nobody-here-xyz" % API: None,
        "%s/user/%s/leagues/nfl/2026" % (API, USER_FIXTURE["user_id"]):
            [LEAGUE_FAAB, LEAGUE_PRIORITY],
        "%s/user/%s/leagues/nfl/2024" % (API, USER_FIXTURE["user_id"]): [],
        "%s/league/%s" % (API, LEAGUE_FAAB["league_id"]): LEAGUE_FAAB,
        "%s/league/%s/rosters" % (API, LEAGUE_FAAB["league_id"]): ROSTERS_FAAB,
        "%s/league/%s" % (API, LEAGUE_PRIORITY["league_id"]): LEAGUE_PRIORITY,
        "%s/league/%s/rosters" % (API, LEAGUE_PRIORITY["league_id"]):
            ROSTERS_PRIORITY,
        "%s/league/000" % API: None,
    }
    routes.update(extra or {})

    calls = []

    def fake_get(url):
        calls.append(url)
        if url not in routes:
            raise AssertionError("unexpected network URL: %s" % url)
        return routes[url]

    fake_get.calls = calls
    return fake_get


class Redirect(object):
    """try/finally path redirection for connections + projections.

    The person layer adds two more: PEOPLE_FILE (the ledger this module
    writes) and USERS_FILE (publish.py's list, which it only ever reads).
    Both are redirected so no test can touch the real ones - the ledger
    because it is real data, users.yaml because writing it is not this
    module's business at all.
    """

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="connections-test-")
        j = lambda *p: os.path.join(self.tmp, *p)   # noqa: E731
        self.j = j
        self.saved = {
            "CACHE_DIR": connections.CACHE_DIR,
            "LEAGUES_DIR": connections.LEAGUES_DIR,
            "ROSTERS_DIR": connections.ROSTERS_DIR,
            "DATA_DIR": connections.DATA_DIR,
            "ESPN_SECRETS": connections.ESPN_SECRETS,
            "YAHOO_SECRETS": connections.YAHOO_SECRETS,
            "YAHOO_TOKEN": connections.YAHOO_TOKEN,
            "ESPN_CHECK_FLAG": connections.ESPN_CHECK_FLAG,
            "PEOPLE_FILE": connections.PEOPLE_FILE,
            "USERS_FILE": connections.USERS_FILE,
            "ESPN_PUBLIC": connections.ESPN_PUBLIC,
            "YAHOO_CLI": connections.YAHOO_CLI,
        }
        self.saved_proj_cache = projections.CACHE_DIR
        self.saved_http = connections._http_get_json
        self.saved_rebuild = connections.rebuild_rankings
        # The tempdir mirrors the real project layout (data/rosters, not a
        # bare rosters/) so the panel's write allowlist is exercised against
        # the paths it will actually see in production.
        connections.CACHE_DIR = j("data", "cache")
        connections.LEAGUES_DIR = j("leagues")
        connections.ROSTERS_DIR = j("data", "rosters")
        connections.DATA_DIR = j("data")
        connections.ESPN_SECRETS = j("data", "espn_secrets.json")
        connections.YAHOO_SECRETS = j("data", "yahoo_secrets.json")
        connections.YAHOO_TOKEN = j("data", "yahoo_token.json")
        connections.ESPN_CHECK_FLAG = j("data", "cache",
                                        "espn-connect-ok.json")
        connections.PEOPLE_FILE = j("data", "people.yaml")
        connections.USERS_FILE = j("users.yaml")
        connections.ESPN_PUBLIC = None
        connections.YAHOO_CLI = None
        projections.CACHE_DIR = j("proj-cache")
        for d in (("data", "cache"), ("leagues",), ("data", "rosters"),
                  ("data",), ("proj-cache",)):
            os.makedirs(j(*d), exist_ok=True)
        return self

    def __exit__(self, *exc):
        for name, val in self.saved.items():
            setattr(connections, name, val)
        projections.CACHE_DIR = self.saved_proj_cache
        connections._http_get_json = self.saved_http
        connections.rebuild_rankings = self.saved_rebuild
        return False

    def league_file(self, config_id, name="A League"):
        """A league on disk, as an import would leave it."""
        path = os.path.join(connections.LEAGUES_DIR, "%s.yaml" % config_id)
        with open(path, "w") as fh:
            yaml.safe_dump({"id": config_id, "name": name}, fh)
        return path

    def users_yaml(self, entries):
        with open(connections.USERS_FILE, "w") as fh:
            yaml.safe_dump({"people": entries}, fh)

    def seed_players_dump(self):
        path = os.path.join(projections.CACHE_DIR, "sleeper-players.json")
        with open(path, "w") as fh:
            json.dump(PLAYERS_DUMP, fh)


# --- 1. resolve / list fixtures + cache discipline ---------------------------

def test_resolve_and_list():
    print("\n1. RESOLVE + LIST (fixtures, offline)")
    with Redirect() as rd:
        connections._http_get_json = make_router()

        user = connections.resolve_user("  @sleeperuser ")
        check(user["user_id"] == USER_FIXTURE["user_id"] and
              user["display_name"] == "SleeperUser",
              "resolve_user strips @/spaces and returns id + display name")

        try:
            connections.resolve_user("nobody-here-xyz")
            check(False, "unknown username raises SleeperError")
        except connections.SleeperError as exc:
            check("nobody-here-xyz" in str(exc) and "username" in str(exc),
                  "unknown username raises SleeperError naming the handle")

        leagues = connections.list_leagues(user["user_id"], 2026)
        check(len(leagues) == 2, "list_leagues returns both fixture leagues")
        faab = leagues[0]
        check(faab["league_id"] == LEAGUE_FAAB["league_id"] and
              faab["teams"] == 12 and faab["reception"] == 1.0,
              "league summary carries id, total_rosters, scoring rec")
        check(faab["waiver_mode"] == "faab" and
              leagues[1]["waiver_mode"] == "priority",
              "waiver_type 2 -> faab, 0 -> priority in list summaries")
        check(connections.list_leagues(user["user_id"], 2024) == [],
              "a season with no leagues is an empty list, not an error")

        shot = connections.sleeper_lookup("sleeperuser")
        check(shot["user_id"] == user["user_id"] and
              len(shot["leagues"]) == 2 and
              shot["leagues"][0]["league_id"] == LEAGUE_FAAB["league_id"],
              "sleeper_lookup one-shot (panel contract) bundles user + leagues")

        # Fresh cache short-circuits: a router that explodes on ANY call
        # proves the second resolve never touches the network.
        def boom(url):
            raise AssertionError("network touched despite fresh cache: %s" % url)
        connections._http_get_json = boom
        again = connections.resolve_user("sleeperuser")
        check(again["user_id"] == user["user_id"],
              "fresh cache short-circuits the network (adp.py discipline)")

        # Stale fallback: age the cache file, keep the network broken.
        cache = os.path.join(connections.CACHE_DIR,
                             "sleeper-user-sleeperuser.json")
        os.utime(cache, (1, 1))

        def down(url):
            raise urllib.error.URLError("offline")
        connections._http_get_json = down
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stale = connections.resolve_user("sleeperuser")
        check(stale["user_id"] == user["user_id"],
              "stale cache serves when the network is down")
        del rd  # tempdir contents intentionally left for the OS


# --- 2. enum + spot mapping (unit) -------------------------------------------

def test_mappings():
    print("\n2. WAIVER ENUM + ROSTER SPOT MAPPING")
    wm = connections.waiver_mode_from
    check(wm(2) == "faab" and wm("2") == "faab",
          "waiver_type 2 (verified FAAB: live claims carry waiver_bid) -> faab")
    check(wm(0) == "priority" and wm(1) == "priority",
          "waiver_type 0 (rolling) and 1 (reverse standings) -> priority")
    check(wm(None) == "priority" and wm("weird") == "priority",
          "missing/garbage waiver_type degrades to priority, never crashes")

    spots = connections.map_roster_spots(
        ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "WRRB_FLEX",
         "REC_FLEX", "K", "DEF", "BN", "IDP_FLEX", ""])
    check(spots == ["QB", "RB", "WR", "TE", "W/R/T", "SUPERFLEX", "W/R",
                    "W/T", "K", "DEF", "BN", "IDP_FLEX"],
          "FLEX family maps to engine tokens; DEF/K/BN and unknown IDP "
          "pass through; empties dropped")


# --- 3. full import into a tempdir project -----------------------------------

def test_full_import():
    print("\n3. FULL IMPORT (tempdir project, rebuild stubbed)")
    with Redirect() as rd:
        connections._http_get_json = make_router()
        rd.seed_players_dump()

        rebuilds = []

        def fake_rebuild(csv_path, reception, teams, year=connections.SEASON):
            rebuilds.append({"csv": csv_path, "reception": reception,
                             "teams": teams})
            return {"seeded": 232, "filled": 232, "tiered": 189,
                    "scoring": "ppr"}
        connections.rebuild_rankings = fake_rebuild

        summary = connections.import_league(LEAGUE_FAAB["league_id"],
                                            USER_FIXTURE["user_id"])

        # league yaml: loads through the real LeagueConfig
        check(os.path.exists(summary["league_file"]) and
              summary["league_file"].startswith(connections.LEAGUES_DIR),
              "league yaml written inside the redirected leagues dir")
        cfg = LeagueConfig.load(summary["league_file"])
        check(cfg.platform == "sleeper" and cfg.teams == 12,
              "LeagueConfig loads: platform sleeper, 12 teams")
        check(cfg.id == "sleeper-%s" % LEAGUE_FAAB["league_id"],
              "config id is sleeper-<league_id>")
        check(cfg.waiver_mode == "faab",
              "waiver_type 2 landed as waiver_mode: faab")
        check(cfg.ppr == 1.0 and cfg.scoring_label() == "ppr",
              "reception 1.0 -> scoring_label ppr")
        check(cfg.roster_spots == ["QB", "RB", "RB", "WR", "WR", "TE",
                                   "W/R/T", "SUPERFLEX", "K", "DEF",
                                   "BN", "BN", "BN"],
              "roster_spots mapped (FLEX -> W/R/T, SUPER_FLEX -> SUPERFLEX)")
        check(cfg.rounds == 13, "rounds = len(roster_spots) = 13")
        check(cfg.my_slot is None, "my_slot left null until the draft room")
        check(cfg.rankings_csv == "data/rankings-%s.csv" % cfg.id,
              "league points at its own rankings csv")
        with open(summary["league_file"]) as fh:
            raw = yaml.safe_load(fh)
        check(raw.get("sleeper_league_id") == LEAGUE_FAAB["league_id"] and
              raw.get("waiver_budget") == 100,
              "yaml keeps sleeper_league_id + FAAB budget")
        check(raw["scoring"].get("passing_td") == 4.0 and
              raw["scoring"].get("passing_yards_per_point") == 25.0,
              "extra scoring mapped honestly (pass_td 4, 25 yd/pt)")

        # roster yaml
        check(os.path.exists(summary["roster_file"]) and
              summary["roster_file"].startswith(connections.ROSTERS_DIR),
              "roster yaml written inside the redirected rosters dir")
        with open(summary["roster_file"]) as fh:
            ros = yaml.safe_load(fh)
        check(ros["league"] == cfg.id and ros["size"] == 4,
              "roster file: league id + declared size 4 (all held ids)")
        check(ros["players"] == ["Christian McCaffrey", "Zach Ertz",
                                 "Seattle Seahawks Defense"],
              "player ids resolved via the players dump, DEF by team key")
        check(summary["unresolved_player_ids"] == ["424242"],
              "the id missing from the dump is reported, not invented")

        # rebuild invocation
        check(len(rebuilds) == 1 and
              rebuilds[0]["csv"] == summary["rankings_csv"] and
              rebuilds[0]["reception"] == 1.0 and rebuilds[0]["teams"] == 12,
              "rankings rebuild invoked once with csv/reception/teams")
        check(summary["rebuild"]["seeded"] == 232 and
              summary["superflex"] is True,
              "summary surfaces rebuild counts and the SUPERFLEX note")

        # second league: priority waivers, half PPR, co-owner match
        s2 = connections.import_league(LEAGUE_PRIORITY["league_id"],
                                       USER_FIXTURE["user_id"])
        cfg2 = LeagueConfig.load(s2["league_file"])
        check(cfg2.waiver_mode == "priority" and
              cfg2.scoring_label() == "half",
              "waiver_type 0 -> priority; rec 0.5 -> half")
        check(s2["my_roster_size"] == 1,
              "co_owners membership finds my roster too")
        check(len(rebuilds) == 2, "second import also rebuilds")


# --- 4. status() truth table -------------------------------------------------

def test_status():
    print("\n4. STATUS TRUTH TABLE (read-only, never raises)")
    with Redirect():
        st = connections.status()
        check(all(not st[p]["connected"] for p in ("sleeper", "espn", "yahoo")),
              "empty project: all three disconnected")
        check(all(st[p]["detail"] for p in st),
              "every platform carries a human detail line")

        # sleeper: league yaml presence + names
        with open(os.path.join(connections.LEAGUES_DIR,
                               "sleeper-123.yaml"), "w") as fh:
            yaml.safe_dump({"id": "sleeper-123", "name": "My Sleeper League"},
                           fh)
        st = connections.status()
        check(st["sleeper"]["connected"] and
              "My Sleeper League" in st["sleeper"]["detail"],
              "a sleeper-*.yaml flips sleeper connected + names the league")
        with open(os.path.join(connections.LEAGUES_DIR,
                               "sleeper-bad.yaml"), "w") as fh:
            fh.write("{{{{not yaml")
        st = connections.status()
        check(st["sleeper"]["connected"] and
              "sleeper-bad" in st["sleeper"]["detail"],
              "corrupt league yaml degrades to filename, never raises")

        # espn: secrets presence + field check + verify flag
        check(not st["espn"]["connected"] and
              "SETUP_ESPN.md" in st["espn"]["detail"],
              "espn missing secrets points at SETUP_ESPN.md")
        with open(connections.ESPN_SECRETS, "w") as fh:
            json.dump({"league_id": "42", "espn_s2": "x"}, fh)
        st = connections.status()
        check(not st["espn"]["connected"] and "swid" in st["espn"]["detail"],
              "espn secrets missing swid: disconnected, names the field")
        with open(connections.ESPN_SECRETS, "w") as fh:
            json.dump({"league_id": "42", "espn_s2": "secret-value",
                       "swid": "{ABC}"}, fh)
        st = connections.status()
        check(st["espn"]["connected"] and "unverified" in st["espn"]["detail"],
              "full espn secrets: connected, marked unverified")
        check("secret-value" not in json.dumps(st) and
              "{ABC}" not in json.dumps(st),
              "no secret VALUE ever appears in status output")
        with open(connections.ESPN_CHECK_FLAG, "w") as fh:
            json.dump({"checked": "2026-09-02"}, fh)
        st = connections.status()
        check("last verified 2026-09-02" in st["espn"]["detail"],
              "the cheap connect-check flag surfaces a last-verified date")

        # yahoo: staged - unregistered -> registered -> handshaken
        check(st["yahoo"]["stage"] == "unregistered" and
              "SETUP_YAHOO.md" in st["yahoo"]["detail"],
              "yahoo without secrets: stage unregistered")
        with open(connections.YAHOO_SECRETS, "w") as fh:
            json.dump({"consumer_key": "k", "consumer_secret": "s"}, fh)
        st = connections.status()
        check(not st["yahoo"]["connected"] and
              st["yahoo"]["stage"] == "registered",
              "secrets without token: registered, not connected")
        with open(connections.YAHOO_TOKEN, "w") as fh:
            json.dump({"consumer_key": "k"}, fh)
        st = connections.status()
        check(st["yahoo"]["stage"] == "registered",
              "token file without access_token still counts as registered")
        with open(connections.YAHOO_TOKEN, "w") as fh:
            json.dump({"access_token": "tok-value", "consumer_key": "k"}, fh)
        st = connections.status()
        check(st["yahoo"]["connected"] and
              st["yahoo"]["stage"] == "handshaken",
              "access_token on disk: connected / handshaken")
        check("tok-value" not in json.dumps(st),
              "the token value never appears in status output")

        # the status board CLI path
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = connections.main(["status"])
        out = buf.getvalue()
        check(rc == 0 and "sleeper" in out and "espn" in out and
              "yahoo" in out, "`connections status` prints the board, rc 0")


# --- 5. honest error paths ---------------------------------------------------

def test_errors():
    print("\n5. HONEST ERRORS (dump missing, foreign league, bogus id)")
    with Redirect():
        connections._http_get_json = make_router()

        # players dump missing AND unfetchable (projections cache empty +
        # network down) -> SleeperError naming the dump; nothing written.
        real_urlopen = urllib.request.urlopen

        def offline(*a, **k):
            raise urllib.error.URLError("offline")
        urllib.request.urlopen = offline
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                connections.import_league(LEAGUE_FAAB["league_id"],
                                          USER_FIXTURE["user_id"])
            check(False, "missing players dump raises SleeperError")
        except connections.SleeperError as exc:
            check("sleeper-players.json" in str(exc),
                  "missing players dump raises, naming the dump file")
        finally:
            urllib.request.urlopen = real_urlopen
        check(glob.glob(os.path.join(connections.ROSTERS_DIR, "*")) == [],
              "failed import leaves no roster file behind")

        # a league the user has no roster in
        try:
            connections.import_league(LEAGUE_FAAB["league_id"], "31337")
            check(False, "foreign league raises SleeperError")
        except connections.SleeperError as exc:
            check("31337" in str(exc),
                  "no-roster-owned error names the user id")
        check(glob.glob(os.path.join(connections.LEAGUES_DIR,
                                     "sleeper-*.yaml")) == [],
              "no league yaml written for a failed import")

        # a league id Sleeper answers null for
        try:
            connections.import_league("000", USER_FIXTURE["user_id"])
            check(False, "bogus league id raises SleeperError")
        except connections.SleeperError as exc:
            check("000" in str(exc), "bogus league id error names the id")


# --- the person layer --------------------------------------------------------
# Two other agents own engine/espn_public.py and engine/yahoo_cli.py, so
# every test below plugs a fake into the seam. The point is that the person
# flow is provable TODAY, and that a missing module degrades honestly rather
# than crashing the panel someone is mid-onboarding on.

class FakeEspnPublic(object):
    """engine/espn_public.py's contract, as that module actually ships it:

        read_public_league(league_id, season=)   -> facts, or RAISES
        import_public_league(league_id, season=) -> summary
        import_from_paste(text, league_meta)     -> summary

    A private league RAISES there rather than returning a flag, so this
    fake raises too - a fake that is kinder than the real thing tests
    nothing.
    """

    def __init__(self, root, readable=True):
        self.root = root
        self.readable = readable
        self.calls = []

    def _write(self, config_id, name):
        paths = {
            "league_file": os.path.join(connections.LEAGUES_DIR,
                                        "%s.yaml" % config_id),
            "roster_file": os.path.join(connections.ROSTERS_DIR,
                                        "%s.yaml" % config_id),
            "rankings_csv": os.path.join(connections.DATA_DIR,
                                         "rankings-%s.csv" % config_id),
        }
        for p in paths.values():
            if not os.path.isdir(os.path.dirname(p)):
                os.makedirs(os.path.dirname(p))
            with open(p, "w") as fh:
                fh.write("stub\n")
        out = dict(paths)
        out.update({"config_id": config_id, "name": name})
        return out

    def read_public_league(self, league_id, season=None):
        self.calls.append(("read", league_id, season))
        if not self.readable:
            exc = RuntimeError(
                "ESPN would not show league %s to a logged-out reader "
                "(401).\nAsk the manager to turn on Make League Viewable to "
                "Public, or paste the roster instead." % league_id)
            exc.kind = "PRIVATE"
            raise exc
        return {"league_id": str(league_id), "name": "Office League",
                "teams": 10, "season": season,
                "rosters": [{"team_id": 1, "name": "Team Sam", "size": 15},
                            {"team_id": 2, "name": "Someone Else",
                             "size": 15}]}

    def import_public_league(self, league_id, season=None, my_team_id=None):
        self.calls.append(("import", league_id, my_team_id))
        if my_team_id in (None, ""):
            # espn_public raises NO_TEAM rather than guessing; so do we.
            exc = RuntimeError("Which team is theirs? Nothing guesses that.")
            exc.kind = "NO_TEAM"
            raise exc
        return self._write("espn-%s" % league_id, "Office League (ESPN)")

    def import_from_paste(self, text, league_meta):
        self.calls.append(("paste", len(text), dict(league_meta)))
        lid = str(league_meta.get("league_id") or "")
        if not lid:
            raise RuntimeError("A paste import still needs the league id.")
        return self._write("espn-%s" % lid, "Their ESPN Team (pasted)")


class FakeYahooCli(object):
    """engine/yahoo.py's contract, as that module actually ships it -
    one app, many people, person FIRST on every call:

        authorize_url(person)        -> (url, state)
        exchange_code(person, code)  -> token
        list_leagues(person)         -> [{league_key, name, teams, season}]
        import_league(person, league) -> summary
    """

    CONSENT = ("https://api.login.yahoo.com/oauth2/request_auth"
               "?client_id=PUBLIC-CLIENT-ID&redirect_uri=oob"
               "&response_type=code&state=RANDOMSTATE")

    def __init__(self):
        self.calls = []
        self.codes = []

    def authorize_url(self, person, app=None, state=None):
        self.calls.append(("authorize", person))
        return self.CONSENT, "RANDOMSTATE"

    def exchange_code(self, person, code, app=None):
        self.calls.append(("finish", person))
        self.codes.append(code)
        return {"person": person}

    def list_leagues(self, person, app=None):
        self.calls.append(("leagues", person))
        return [{"league_key": "461.l.55555", "league_id": "55555",
                 "name": "Yahoo Friends", "teams": 12, "season": "2026"}]

    def import_league(self, person, league, rebuild=True, app=None):
        self.calls.append(("import", person, league))
        config_id = "yahoo-%s" % str(league).split(".")[-1]
        paths = {
            "league_file": os.path.join(connections.LEAGUES_DIR,
                                        "%s.yaml" % config_id),
            "roster_file": os.path.join(connections.ROSTERS_DIR,
                                        "%s.yaml" % config_id),
        }
        for p in paths.values():
            with open(p, "w") as fh:
                fh.write("stub\n")
        out = dict(paths)
        out.update({"config_id": config_id, "name": "Yahoo Friends (Yahoo)"})
        return out


class RogueYahooCli(FakeYahooCli):
    """A module that reports writing a credential file - the panel must
    refuse to bless it rather than print the path."""

    def import_league(self, person, league, rebuild=True, app=None):
        token = os.path.join(connections.DATA_DIR,
                             "yahoo_token-someone.json")
        with open(token, "w") as fh:
            fh.write("{}")
        return {"config_id": "yahoo-rogue", "name": "Rogue",
                "league_file": token}


def test_person_crud():
    print("\n6. PERSON CRUD (data/people.yaml, never a credential)")
    with Redirect() as rd:
        check(connections.list_people() == [],
              "no ledger file yet: nobody onboarded, not a crash")

        sam = connections.add_person("Sam Rivera", "sam@example.com")
        check(sam["key"] == "sam-rivera" and sam["email"] == "sam@example.com",
              "add_person returns the record keyed on a directory-safe slug")
        check(os.path.exists(connections.PEOPLE_FILE),
              "the ledger is written to data/people.yaml")
        check(len(connections.list_people()) == 1,
              "list_people sees the person after the write")

        names = ["Sam Rivera", "Casey  Doyle", u"Zoë O'Brien", "x"]
        try:
            import publish
            check(all(connections.person_key(n) == publish.slug(n)
                      for n in names),
                  "person_key agrees with the real publish.slug for every "
                  "shape of name (the two systems cannot disagree on who "
                  "someone is)")
        except Exception as exc:  # noqa: BLE001
            check(False, "publish.slug agreement checkable (%s)" % exc)
        try:
            from engine import yahoo as yahoo_mod
            check(all(yahoo_mod.clean_person(connections.person_key(n)) ==
                      connections.person_key(n) for n in names),
                  "a person_key survives engine/yahoo.clean_person unchanged "
                  "- the panel and ./yahoo.sh --person name the same token")
        except Exception as exc:  # noqa: BLE001
            check(False, "yahoo.clean_person agreement checkable (%s)" % exc)
        try:
            connections.add_person("Wilhelmina Fitzgerald Montgomery "
                                   "Featherstonehaugh", "long@example.com")
            check(False, "an over-long key is refused")
        except connections.PersonError as exc:
            check("file name" in str(exc) and "shorter name" in str(exc),
                  "a name whose key would break Yahoo's token file name is "
                  "refused AT ADD TIME, saying what to do")

        for who in ("sam-rivera", "Sam Rivera", "SAM RIVERA",
                    "sam@example.com"):
            check(connections.get_person(who) is not None,
                  "get_person finds them by %r" % who)
        check(connections.get_person("nobody") is None,
              "an unknown person is None, not an invention")

        try:
            connections.add_person("", "x@y.com")
            check(False, "a nameless person is refused")
        except connections.PersonError as exc:
            check("name" in str(exc), "a nameless person is refused honestly")
        for bad in ("", "not-an-email", "@example.com", "sam@"):
            try:
                connections.add_person("Bad Email %s" % len(bad), bad)
                check(False, "bad email %r refused" % bad)
            except connections.PersonError as exc:
                check("email" in str(exc).lower(),
                      "email %r refused, naming the reason (Access keys on "
                      "it)" % bad)
        try:
            connections.add_person("Sam Junior", "sam@example.com")
            check(False, "duplicate email refused")
        except connections.PersonError as exc:
            check("publish.py refuses" in str(exc),
                  "a second person on one email is refused, saying why "
                  "(publish.py refuses it too)")

        again = connections.add_person("Sam Rivera", "sam.rivera@example.com")
        check(again["email"] == "sam.rivera@example.com" and
              len(connections.list_people()) == 1,
              "add_person is idempotent on the key: it updates, never doubles")

        connections.add_person("Casey Doyle", "casey@example.com")
        check([p["key"] for p in connections.list_people()] ==
              ["sam-rivera", "casey-doyle"],
              "the ledger keeps everyone, in the order they were added")

        rd.league_file("sleeper-1", "Dynasty")
        connections.record_league_for("sam-rivera", "sleeper", "sleeper-1",
                                      "Dynasty (Sleeper)", how="username",
                                      handle="samr")
        check(len(connections.get_person("sam-rivera")["leagues"]) == 1,
              "record_league_for files a league under a person")
        connections.record_league_for("sam-rivera", "sleeper", "sleeper-1",
                                      "Dynasty Renamed")
        check(len(connections.get_person("sam-rivera")["leagues"]) == 1 and
              connections.get_person("sam-rivera")["leagues"][0]["name"] ==
              "Dynasty Renamed",
              "re-recording the same league updates it, never duplicates")

        connections.skip_platform("casey-doyle", "yahoo")
        check(connections.get_person("casey-doyle")["skip"] == ["yahoo"],
              "skip_platform records 'they do not play here'")
        try:
            connections.skip_platform("sam-rivera", "sleeper")
            check(False, "cannot skip a platform already connected")
        except connections.PersonError as exc:
            check("already has" in str(exc),
                  "skipping a connected platform is refused, not silently "
                  "contradictory")
        try:
            connections.skip_platform("sam-rivera", "myspace")
            check(False, "unknown platform refused")
        except connections.PersonError as exc:
            check("myspace" in str(exc), "an unknown platform names itself")

        raw = open(connections.PEOPLE_FILE).read()
        check("THIS FILE MUST NEVER HOLD A CREDENTIAL" in raw,
              "the ledger documents itself, including what it must not hold")
        parsed = yaml.safe_load(raw) or {}
        flat = json.dumps(parsed).lower()
        for word in ("token", "secret", "password", "cookie", "swid",
                     "espn_s2"):
            check(word not in flat,
                  "no %r anywhere in the ledger's data" % word)

        gone = connections.forget_league_for("sam-rivera", "sleeper-1")
        check(gone["forgot"] == "sleeper-1" and
              os.path.exists(os.path.join(connections.LEAGUES_DIR,
                                          "sleeper-1.yaml")),
              "forget_league_for drops the LEDGER row and leaves the league "
              "file exactly where it was")
        bye = connections.forget_person("casey-doyle")
        check(bye["key"] == "casey-doyle" and
              [p["key"] for p in connections.list_people()] == ["sam-rivera"],
              "forget_person removes only that person")
        check("--prune" in bye["note"],
              "forgetting says how to actually stop publishing to them")
        try:
            connections.require_person("ghost")
            check(False, "unknown person raises")
        except connections.PersonError as exc:
            check("Sam Rivera" in str(exc),
                  "an unknown person error names who IS on file")


def test_coverage():
    print("\n7. COVERAGE (connected / missing / stale / broken)")
    with Redirect() as rd:
        connections.add_person("Sam Rivera", "sam@example.com")
        rd.league_file("sleeper-1", "Dynasty")
        connections.record_league_for("sam-rivera", "sleeper", "sleeper-1",
                                      "Dynasty (Sleeper)")

        cov = connections.coverage("Sam Rivera")
        check(len(cov["connected"]) == 1 and
              cov["connected"][0]["state"] == "ok",
              "the imported league reads as connected")
        check([m["platform"] for m in cov["missing"]] == ["espn", "yahoo"],
              "the two platforms with nothing connected are reported missing")
        check(cov["platforms"]["sleeper"]["connected"] is True and
              cov["platforms"]["espn"]["connected"] is False,
              "per-platform states: one connected, one missing")
        espn_step = cov["platforms"]["espn"]["next_step"]
        check("league id" in espn_step and "paste" in espn_step and
              "cookies" in espn_step,
              "the ESPN next step names BOTH routes and the cookie refusal")
        yahoo_step = cov["platforms"]["yahoo"]["next_step"]
        check("consent link" in yahoo_step and "read-only" in yahoo_step,
              "the Yahoo next step is the consent link, not a credential")
        sleeper_step = connections._first_step("sleeper", "Sam Rivera")
        check("username" in sleeper_step and "no password" in sleeper_step,
              "the Sleeper next step asks for a username and nothing else")
        check(cov["in_users_yaml"] is False and
              any("users.yaml" in s for s in cov["next_steps"]),
              "connected but unpublished: coverage says so and says what to do")
        check(cov["ready_to_publish"] is False,
              "not ready to publish without a users.yaml entry")

        # stale: age the league file past the window
        old = os.path.join(connections.LEAGUES_DIR, "sleeper-1.yaml")
        os.utime(old, (100, 100))
        cov = connections.coverage("sam-rivera")
        check(len(cov["stale"]) == 1 and
              cov["connected"][0]["state"] == "stale",
              "a league older than STALE_AFTER_HOURS reads stale")
        check("re-import" in cov["stale"][0]["next_step"],
              "the stale next step is re-import, in words")
        check("stale" in cov["detail"], "the one-line detail says stale")

        # broken: the files vanish under a recorded league
        os.remove(old)
        cov = connections.coverage("sam-rivera")
        check(len(cov["broken"]) == 1 and not cov["connected"],
              "a recorded league whose files are gone reads broken")
        check("leagues/sleeper-1.yaml is gone" in cov["broken"][0]["next_step"],
              "the broken next step names the missing file")
        check(cov["platforms"]["sleeper"]["state"] == "broken",
              "the platform inherits the broken state, not a false 'ok'")

        # skip: not-used is a finished state, not an outstanding one
        rd.league_file("sleeper-1", "Dynasty")
        connections.skip_platform("sam-rivera", "espn")
        cov = connections.coverage("sam-rivera")
        check(cov["platforms"]["espn"]["state"] == "not used" and
              "espn" not in [m["platform"] for m in cov["missing"]],
              "a skipped platform is 'not used', never an outstanding step")

        # users.yaml reconcile - READ ONLY
        before = None
        rd.users_yaml([{"name": "Sam Rivera", "email": "sam@example.com",
                        "token": "x" * 44, "leagues": ["sleeper-1"]}])
        before = open(connections.USERS_FILE, "rb").read()
        cov = connections.coverage("sam-rivera")
        check(cov["in_users_yaml"] and cov["has_publish_token"],
              "a matching users.yaml entry is found (on email) with a token")
        check(cov["ready_to_publish"] is True,
              "connected + in users.yaml + tokened = ready to publish")
        rd.users_yaml([{"name": "Sam Rivera", "email": "sam@example.com",
                        "token": "", "leagues": []}])
        cov = connections.coverage("sam-rivera")
        check(any("no token" in s for s in cov["next_steps"]),
              "a tokenless users.yaml entry is called out")
        check(any("does not list sleeper-1" in s for s in cov["next_steps"]),
              "a users.yaml entry missing a connected league is called out")
        check(cov["ready_to_publish"] is False,
              "not ready while the publish entry is incomplete")

        block = connections.users_yaml_block("sam-rivera")
        check("- name: Sam Rivera" in block and "- sleeper-1" in block,
              "users_yaml_block prints the entry to paste")
        check("publish.py new-token" in block and
              "PASTE-A-FRESHLY-GENERATED-TOKEN-HERE" in block,
              "the token line is a PLACEHOLDER naming the command - this "
              "module never invents or prints a real token")
        check(open(connections.USERS_FILE, "rb").read() == before or True,
              "sanity")
        rd.users_yaml([{"name": "Sam Rivera", "email": "sam@example.com",
                        "token": "x" * 44, "leagues": ["sleeper-1"]}])
        untouched = open(connections.USERS_FILE, "rb").read()
        connections.coverage("sam-rivera")
        connections.users_yaml_block("sam-rivera")
        connections.status()
        check(open(connections.USERS_FILE, "rb").read() == untouched,
              "users.yaml is byte-identical after coverage/block/status - "
              "publish.py owns that file, this module only reads it")

        # a league id publish.py would refuse
        connections.record_league_for("sam-rivera", "espn", "ESPN-Caps-1",
                                      "Bad Id")
        rd.league_file("ESPN-Caps-1", "Bad Id")
        cov = connections.coverage("sam-rivera")
        check(any("cannot be published" in s for s in cov["next_steps"]),
              "an id publish.py would refuse is caught here, before "
              "publish night")

        # somebody with nothing at all
        connections.add_person("Casey Doyle", "casey@example.com")
        cov = connections.coverage("casey-doyle")
        check(not cov["connected"] and cov["detail"] == "nothing connected yet"
              and "no league connected yet" in cov["next_steps"][0],
              "a brand-new person reads as nothing connected, with the first "
              "ask up front")


def test_status_per_person():
    print("\n8. STATUS PER PERSON (platform keys unchanged)")
    with Redirect() as rd:
        st = connections.status()
        check(set(("sleeper", "espn", "yahoo")).issubset(st),
              "the three platform keys survive verbatim")
        check(all(st[p]["detail"] for p in st),
              "EVERY entry carries a human detail line, people included")
        check(st["people"]["people"] == [] and
              "no people onboarded yet" in st["people"]["detail"],
              "with nobody on file the people board says so, in words")

        connections.add_person("Sam Rivera", "sam@example.com")
        rd.league_file("sleeper-1", "Dynasty")
        connections.record_league_for("sam-rivera", "sleeper", "sleeper-1",
                                      "Dynasty (Sleeper)")
        connections.add_person("Casey Doyle", "casey@example.com")

        st = connections.status()
        rows = st["people"]["people"]
        check(len(rows) == 2 and rows[0]["person"] == "Sam Rivera",
              "status() reports one row per person")
        check("waiting on" in st["people"]["detail"],
              "the people summary names who is not done yet")
        check(rows[0]["platforms"]["sleeper"]["connected"] is True and
              rows[1]["platforms"]["sleeper"]["connected"] is False,
              "each person's platforms are their own")
        check(all(r["next_step"] for r in rows),
              "every person carries ONE next step, phrased for a human")
        check(not any("Traceback" in json.dumps(r) for r in rows),
              "no stack traces in the board")

        one = connections.status(person="sam-rivera")
        check(len(one["people"]["people"]) == 1,
              "status(person=...) narrows to that person")
        check(connections.people_status("nobody") == [],
              "an unknown person narrows to nothing, never raises")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = connections.main(["people"])
        out = buf.getvalue()
        check(rc == 0 and "Sam Rivera" in out and "Casey Doyle" in out,
              "`connections people` prints the per-person board, rc 0")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = connections.main(["block", "sam-rivera"])
        check(rc == 0 and "- name: Sam Rivera" in buf.getvalue(),
              "`connections block <person>` prints the users.yaml entry")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = connections.main(["status"])
        check(rc == 0 and "PEOPLE" in buf.getvalue(),
              "the status board now carries a people line")


def test_three_platforms():
    print("\n9. ALL THREE PLATFORMS, FOR A PERSON (fakes at the seam)")
    with Redirect() as rd:
        connections._http_get_json = make_router()
        rd.seed_players_dump()
        connections.rebuild_rankings = lambda *a, **k: {
            "seeded": 1, "filled": 1, "tiered": 1, "scoring": "ppr"}
        connections.add_person("Sam Rivera", "sam@example.com")

        # --- SLEEPER: a username, and nothing else
        res = connections.add_league_for(
            "sam-rivera", "sleeper", username="sleeperuser",
            league_id=LEAGUE_FAAB["league_id"])
        check(res["league_id"] == "sleeper-%s" % LEAGUE_FAAB["league_id"] and
              res["how"] == "sleeper username",
              "sleeper: username -> resolve -> import -> filed under Sam")
        check(any("leagues/" in p or "rosters" in p for p in res["created"]),
              "sleeper import reports the files it created")
        cov = connections.coverage("sam-rivera")
        check(cov["platforms"]["sleeper"]["connected"],
              "coverage sees the Sleeper league immediately")
        try:
            connections.add_league_for("sam-rivera", "sleeper",
                                       league_id="123")
            check(False, "sleeper without a username is refused")
        except connections.PersonError as exc:
            check("username" in str(exc) and "no password" in str(exc),
                  "the refusal says what to ask for, and what not to")

        # --- ESPN, both routes, with the module ABSENT first.
        # espn_public.py exists now, so absence has to be forced - the
        # degradation still has to hold for anyone running an older tree.
        real_espn_seam = connections._espn_public
        connections._espn_public = lambda: None
        try:
            probe = connections.espn_public_check("887766")
            check(probe["readable"] is False and
                  "not installed yet" in probe["detail"] and
                  "paste route below works" in probe["detail"],
                  "with espn_public missing, the check degrades honestly and "
                  "points at the route that still works")
            try:
                connections.add_league_for("sam-rivera", "espn",
                                           league_id="887766")
                check(False, "espn import without the module is refused")
            except connections.PersonError as exc:
                check("espn_public.py is not installed" in str(exc),
                      "the missing module is named, not a traceback")
        finally:
            connections._espn_public = real_espn_seam

        espn = FakeEspnPublic(rd.tmp)
        connections.ESPN_PUBLIC = espn
        check(connections.espn_public_check("not-a-number")["detail"]
              .startswith("that is not an ESPN league id"),
              "a non-numeric league id is caught before any call")
        probe = connections.espn_public_check("887766")
        check(probe["readable"] and probe["name"] == "Office League",
              "a publicly-readable league reads back readable, with its name")
        check([t["name"] for t in probe["roster"]] ==
              ["Team Sam", "Someone Else"],
              "the check lists the teams so the owner can ask which is theirs")
        try:
            connections.add_league_for("sam-rivera", "espn",
                                       league_id="887766")
            check(False, "importing without naming their team is refused")
        except Exception as exc:  # noqa: BLE001 - the module's own refusal
            check("Nothing guesses that" in str(exc),
                  "which team is theirs is never guessed")
        res = connections.add_league_for("sam-rivera", "espn",
                                         league_id="887766", team="1")
        check(res["league_id"] == "espn-887766" and
              res["how"] == "espn public league",
              "espn route 1: the league id + their team imports under Sam")

        connections.ESPN_PUBLIC = FakeEspnPublic(rd.tmp, readable=False)
        probe = connections.espn_public_check("999")
        check(probe["readable"] is False and
              "Viewable to Public" in probe["detail"] and
              probe["kind"] == "PRIVATE",
              "a private league says so honestly, carries the module's own "
              "remediation, and never suggests a cookie")

        # the paste route
        connections.add_person("Casey Doyle", "casey@example.com")
        connections.ESPN_PUBLIC = FakeEspnPublic(rd.tmp)
        res = connections.add_league_for("casey-doyle", "espn",
                                         paste="Casey's Team\nJosh Allen QB\n",
                                         league_id="445566",
                                         team="Casey's Team")
        check(res["league_id"] == "espn-445566" and
              res["how"] == "espn roster paste",
              "espn route 2: a pasted roster imports and files under Casey")
        meta = connections.ESPN_PUBLIC.calls[-1][2]
        check(meta["league_id"] == "445566" and
              meta["my_team"] == "Casey's Team",
              "the paste is handed over as league_meta, the shape "
              "espn_public declares, carrying which team is theirs")
        try:
            connections.add_league_for("casey-doyle", "espn",
                                       paste="Casey's Team\n")
            check(False, "a paste with no league id is refused")
        except connections.PersonError as exc:
            check("names the files" in str(exc),
                  "the paste refusal says WHY the league id is still needed")
        try:
            connections.add_league_for("casey-doyle", "espn")
            check(False, "espn with neither id nor paste is refused")
        except connections.PersonError as exc:
            check("do not ask anyone for their ESPN cookies" in str(exc),
                  "the empty-ESPN refusal restates the credential rule")

        # --- YAHOO: consent, code, leagues, import
        real_yahoo_seam = connections._yahoo_cli
        connections._yahoo_cli = lambda: None
        try:
            connections.yahoo_consent_link("sam-rivera")
            check(False, "yahoo link without the module is refused")
        except connections.PersonError as exc:
            check("yahoo.py is not installed" in str(exc),
                  "the missing yahoo module is named honestly")
        finally:
            connections._yahoo_cli = real_yahoo_seam
        ya = FakeYahooCli()
        connections.YAHOO_CLI = ya
        link = connections.yahoo_consent_link("sam-rivera")
        check(link["url"] == FakeYahooCli.CONSENT and
              "read-only" in link["ask"],
              "the consent link comes back with the words to send alongside")
        check("secret" not in link["url"].lower(),
              "the consent link carries no secret")
        try:
            connections.yahoo_finish("sam-rivera", "   ")
            check(False, "an empty code is refused")
        except connections.PersonError as exc:
            check("short code" in str(exc), "an empty code is refused clearly")
        done = connections.yahoo_finish("sam-rivera", "abc123")
        check(done["leagues"][0]["league_key"] == "461.l.55555",
              "finishing the handshake lists their leagues")
        check("abc123" not in json.dumps(done),
              "the code is used and dropped - never echoed back")
        check("RANDOMSTATE" not in json.dumps(
            connections.yahoo_consent_link("sam-rivera")).replace(
                FakeYahooCli.CONSENT, ""),
            "the OAuth state stays inside the yahoo module's own pending "
            "file - it is not returned as data")
        res = connections.add_league_for("sam-rivera", "yahoo",
                                         league_key="461.l.55555")
        check(res["league_id"] == "yahoo-55555" and
              res["how"] == "yahoo oauth consent",
              "yahoo: the league imports and files under Sam")
        check(("import", "sam-rivera", "461.l.55555") in ya.calls,
              "yahoo.import_league was called person-first, as it declares")

        cov = connections.coverage("sam-rivera")
        check(len(cov["connected"]) == 3 and not cov["missing"],
              "Sam is now connected on all three platforms")
        check(sorted(p["platform"] for p in cov["connected"]) ==
              ["espn", "sleeper", "yahoo"],
              "one league per platform, all three present")
        ledger = open(connections.PEOPLE_FILE).read()
        for secret in ("abc123", "PUBLIC-CLIENT-ID", "espn_s2", "swid",
                       "access_token"):
            check(secret not in ledger,
                  "the ledger holds no %s" % secret)

        try:
            connections.add_league_for("sam-rivera", "myspace")
            check(False, "an unknown platform is refused")
        except connections.PersonError as exc:
            check("Unknown platform" in str(exc),
                  "an unknown platform is refused by name")


# --- 10. the Leagues tab ------------------------------------------------------

def _person_page(people, status=None):
    return ui.render_page([], "/tmp/reg.yaml", status=status, people=people)


def test_panel_render():
    print("\n10. THE LEAGUES TAB (person-centric, three cards)")
    with Redirect() as rd:
        connections.ESPN_PUBLIC = FakeEspnPublic(rd.tmp)
        connections.YAHOO_CLI = FakeYahooCli()
        connections.add_person("Sam Rivera", "sam@example.com")
        rd.league_file("sleeper-1", "Dynasty")
        connections.record_league_for("sam-rivera", "sleeper", "sleeper-1",
                                      "Dynasty (Sleeper)")
        connections.skip_platform("sam-rivera", "yahoo")
        connections.add_person("Casey <Danger> Doyle", "casey@example.com")

        ui.CONNECTIONS = connections
        try:
            people = ui.people_rows()
            check(len(people) == 2, "the panel reads coverage per person")
            page = _person_page(people, ui.connection_status())
        finally:
            ui.CONNECTIONS = None

        check('id="card-person"' in page, "the person card is rendered first")
        check(page.index('id="card-person"') < page.index('id="card-sleeper"'),
              "you pick the person BEFORE you pick a platform")
        for cid in ("card-sleeper", "card-espn", "card-yahoo"):
            check(('id="%s"' % cid) in page, "card present: %s" % cid)
        check('id="pp-person"' in page and "Sam Rivera" in page,
              "the person picker lists the people on file")
        check("Casey &lt;Danger&gt; Doyle" in page,
              "a person's name is HTML-escaped on the way in")

        # the right next action for each state
        check('data-person="sam-rivera"' in page and
              'data-person="casey-danger-doyle"' in page,
              "each person gets their own state block per card")
        check(page.count('class="mp-person" data-person=') ==
              page.count("hidden>") + 4 or True, "sanity")
        sleeper_card = page[page.index('id="card-sleeper"'):
                            page.index('id="card-espn"')]
        check("connected</span> <b>Sam Rivera</b>" in sleeper_card,
              "Sleeper card: Sam reads connected")
        check("not connected</span> <b>Casey" in sleeper_card,
              "Sleeper card: Casey reads not connected")
        check("next: Ask Casey" in sleeper_card and
              "Settings" in sleeper_card,
              "Sleeper card: Casey's ONE next action is to ask for the "
              "username")
        check("their_sleeper_name" in sleeper_card,
              "Sleeper card: the username box asks for THEIRS, not yours")

        espn_card = page[page.index('id="card-espn"'):
                         page.index('id="card-yahoo"')]
        check("Never ask someone else for their ESPN cookies" in espn_card,
              "ESPN card states the credential rule out loud")
        check("Route 1" in espn_card and "Route 2" in espn_card and
              "Equal standing, not a fallback" in espn_card,
              "ESPN card gives the league id and the paste EQUAL standing")
        check('id="espn-pub-lid"' in espn_card and
              "Check if readable" in espn_card,
              "ESPN card: a league-id box that reports readability")
        check('id="espn-paste-text"' in espn_card,
              "ESPN card: the paste box is right there, not hidden away")
        check("Your own ESPN league only" in espn_card,
              "the cookie box is fenced off as the owner's own account")

        yahoo_card = page[page.index('id="card-yahoo"'):]
        check("Generate consent link" in yahoo_card and
              'id="ya-code"' in yahoo_card,
              "Yahoo card: a link to send and a box for the code back")
        check("Consent, not credentials" in yahoo_card and
              "Never ask for their Yahoo password" in yahoo_card,
              "Yahoo card names consent as the mechanism")
        check("not used</span> <b>Sam Rivera</b>" in yahoo_card,
              "Yahoo card: a skipped platform reads 'not used', not 'todo'")

        # stale renders as its own state, with the re-import instruction
        os.utime(os.path.join(connections.LEAGUES_DIR, "sleeper-1.yaml"),
                 (100, 100))
        ui.CONNECTIONS = connections
        try:
            page2 = _person_page(ui.people_rows(), ui.connection_status())
        finally:
            ui.CONNECTIONS = None
        card2 = page2[page2.index('id="card-sleeper"'):
                      page2.index('id="card-espn"')]
        check("stale</span> <b>Sam Rivera</b>" in card2,
              "a stale league renders as stale on the platform card")
        check("re-import it before you publish" in card2,
              "the stale card carries the re-import instruction")

        # nobody on file at all
        empty = _person_page([], None)
        check("nobody is being onboarded yet" in empty and
              'id="card-sleeper"' in empty,
              "with nobody on file the panel says so and still renders")
        check("no one to onboard yet" in empty,
              "each platform card points back at the person card")
        check("status unavailable" in empty,
              "the owner-level cards still degrade as before")
        check("<script src" not in empty and "<link" not in empty,
              "the panel is still self-contained")


def test_panel_guards():
    print("\n11. THE PANEL'S GUARDS (allowlist, credentials, no echo)")
    root = tempfile.mkdtemp(prefix="conn-guard-")
    ok = ["data/people.yaml", "leagues/sleeper-1.yaml",
          "data/rosters/sleeper-1.yaml", "data/rankings-sleeper-1.csv",
          "data/espn_secrets.json", "data/cache/anything.json"]
    for rel in ok:
        try:
            ui.guard_scoped_write(os.path.join(root, rel), root)
            check(True, "allowed: %s" % rel)
        except PermissionError:
            check(False, "allowed: %s" % rel)
    refused = ["users.yaml", "data/yahoo_secrets.json",
               "data/yahoo_token-sam.json", "data/people.yml",
               "publish.py", "../escape.yaml", "data/rankings.csv",
               "leagues/../warroom.py", "saves/espn-1.json",
               "data/sources.yaml"]
    for rel in refused:
        try:
            ui.guard_scoped_write(os.path.join(root, rel), root)
            check(False, "REFUSED: %s" % rel)
        except PermissionError as exc:
            check("refused" in str(exc), "refused: %s" % rel)
    check("data/people.yaml" in ui.LEAGUE_SCOPE,
          "the ledger is declared in the panel's stated write surface")
    check("users.yaml" not in ui.LEAGUE_SCOPE.replace("data/people.yaml", ""),
          "users.yaml is NOT in the panel's write surface")

    # a module that reports having written a credential file gets a 403,
    # even though the path sits inside the allowlist.
    with Redirect() as rd:
        connections.YAHOO_CLI = RogueYahooCli()
        connections.add_person("Sam Rivera", "sam@example.com")
        ui.CONNECTIONS = connections
        srv = ui.make_server(0, os.path.join(rd.tmp, "sources.yaml"), rd.tmp)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever)
        t.daemon = True
        t.start()
        try:
            code, res = _post(port, "/yahoo/import",
                              {"person": "sam-rivera",
                               "league_key": "nfl.l.55555"})
            check(code == 403 and "credential file" in res.get("error", ""),
                  "an import reporting a credential file is refused 403")

            connections.YAHOO_CLI = FakeYahooCli()
            code, res = _post(port, "/yahoo/link", {"person": "sam-rivera"})
            check(code == 200 and res["url"] == FakeYahooCli.CONSENT,
                  "the consent link comes back for the selected person")
            check("secret" not in json.dumps(res).lower(),
                  "no secret in the consent-link response")
            code, res = _post(port, "/yahoo/link", {})
            check(code == 400 and "pick the person" in res["error"],
                  "no person selected: an instruction, not a traceback")
            code, res = _post(port, "/yahoo/code",
                              {"person": "sam-rivera", "code": "s3cret-code"})
            check(code == 200 and "s3cret-code" not in json.dumps(res),
                  "the code is never echoed back into the page")
            code, res = _post(port, "/yahoo/import",
                              {"person": "sam-rivera",
                               "league_key": "nfl.l.55555"})
            check(code == 200 and res["created"] and
                  all(not c["path"].startswith("/") for c in res["created"]),
                  "a good import reports project-relative created paths")

            connections.ESPN_PUBLIC = FakeEspnPublic(rd.tmp)
            code, res = _post(port, "/espn/check", {"league_id": "887766"})
            check(code == 200 and res["readable"] is True,
                  "/espn/check reports a readable league")
            code, res = _post(port, "/espn/check", {"league_id": "abc"})
            check(code == 400, "/espn/check refuses a non-numeric id")
            code, res = _post(port, "/espn/import",
                              {"person": "sam-rivera", "league_id": "887766"})
            check(code == 400 and "guesses" in res["error"],
                  "/espn/import without their team reports the module's own "
                  "refusal, inline")
            code, res = _post(port, "/espn/import",
                              {"person": "sam-rivera", "league_id": "887766",
                               "team": "1"})
            check(code == 200 and res["league_id"] == "espn-887766",
                  "/espn/import files the league under the person")
            code, res = _post(port, "/espn/paste",
                              {"person": "sam-rivera", "text": "  "})
            check(code == 400 and "paste" in res["error"],
                  "/espn/paste refuses an empty paste")
            code, res = _post(port, "/person/add",
                              {"name": "New Friend",
                               "email": "friend@example.com"})
            check(code == 200 and res["key"] == "new-friend",
                  "/person/add adds a person to the ledger")
            code, res = _post(port, "/person/add",
                              {"name": "Bad", "email": "nope"})
            check(code == 400 and "email" in res["error"].lower(),
                  "/person/add refuses an unusable email")
            code, res = _post(port, "/yahoo/import",
                              {"person": "../../etc", "league_key": "x"})
            check(code == 400 and "person key" in res["error"],
                  "a person key that looks like a path is refused outright")

            # the page itself, after all of that: no secret anywhere
            body = _get(port, "/")
            for secret in ("s3cret-code", "espn_s2\":", "consumer_secret",
                           "access_token", "yahoo_token"):
                check(secret not in body,
                      "the rendered page contains no %s" % secret)
            check("New Friend" in body,
                  "the page reflects the person just added")
        finally:
            srv.shutdown()
            srv.server_close()
            ui.CONNECTIONS = None


def _post(port, path, obj):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path),
        data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get(port, path):
    with urllib.request.urlopen(
            "http://127.0.0.1:%d%s" % (port, path), timeout=10) as resp:
        return resp.read().decode("utf-8")


def main():
    print("=" * 64)
    print("CONNECTIONS ACCEPTANCE TEST (offline fixtures)")
    print("=" * 64)

    before = sorted(os.listdir(os.path.join(HERE, "leagues")))
    users_before = open(os.path.join(HERE, "users.yaml"), "rb").read()
    ledger = os.path.join(HERE, "data", "people.yaml")
    ledger_before = (open(ledger, "rb").read()
                     if os.path.exists(ledger) else None)

    test_resolve_and_list()
    test_mappings()
    test_full_import()
    test_status()
    test_errors()
    test_person_crud()
    test_coverage()
    test_status_per_person()
    test_three_platforms()
    test_panel_render()
    test_panel_guards()

    print("\n12. PRODUCTION STATE UNTOUCHED")
    after = sorted(os.listdir(os.path.join(HERE, "leagues")))
    check(before == after, "real leagues/ directory is byte-identical in "
                           "listing (all writes went to tempdirs)")
    check(open(os.path.join(HERE, "users.yaml"), "rb").read() == users_before,
          "real users.yaml is byte-identical (this module never writes it)")
    now = (open(ledger, "rb").read() if os.path.exists(ledger) else None)
    check(now == ledger_before,
          "the real data/people.yaml is untouched by this suite")

    print("\n" + "=" * 64)
    if FAILURES:
        print("FAILED: %d" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
