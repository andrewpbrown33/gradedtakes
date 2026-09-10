#!/usr/bin/env python3
"""Acceptance test: the multi-person Yahoo connector (engine/yahoo.py).

Everything here runs OFFLINE. urllib.request.urlopen is replaced wholesale
with a router, so the REAL code path is exercised end to end - the Basic auth
header is actually built and decoded back, the form body is actually urlencoded
and parsed back, HTTPError bodies are actually mapped to typed errors - while
any URL the router does not know raises, which is the proof that no packet
leaves the machine. Every path constant (LEAGUES_DIR, ROSTERS_DIR, TOKENS_DIR,
SECRETS_FILE) is redirected into a tempdir in try/finally, per the
tests/mock_draft.py SAVE_DIR discipline, and the network-heavy rankings
rebuild is stubbed with a recorder.

Payload shapes mirror live Yahoo responses: the settings block (stat_ids,
roster_positions with position+count, uses_faab), the users/games/leagues
collection with its "0"/"1"/count string keys, and the roster's
[[metadata dicts], {selected_position}] positional array.

Covers
  1. authorize URL shape + the read-only scope, and the refusal to ask for
     fspt-w even when data/yahoo_secrets.json asks for it
  2. code -> token exchange, including the Basic app auth Yahoo requires
  3. automatic refresh when the 1-hour access token is at/past expiry
  4. token file mode 0600, private-from-creation, in a 0700 directory
  5. typed failures: denied consent, expired/used code, revoked token,
     throttling, missing app credential
  6. Yahoo settings/roster -> leagues/yahoo-<id>.yaml + data/rosters/... that
     load through LeagueConfig with real scoring and roster spots
  7. no secret - app secret, access token, refresh token, or auth code - ever
     appears in a printed line, an exception message, or a written artifact
  8. the 24-hour retention stamp, and that purge never touches an unstamped
     hand-written league yaml

    .venv/bin/python tests/yahoo_test.py
"""

import base64
import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import yaml                                                    # noqa: E402

from engine import yahoo, yahoo_cli                            # noqa: E402
from engine.models import LeagueConfig                         # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- the secrets that must never surface ------------------------------------

CLIENT_ID = "dj0yJmk9FIXTURECLIENTID0000000000000000--"
CLIENT_SECRET = "fixtureclientsecret0123456789abcdef0123456789abcd"
AUTH_CODE = "fixtureauthcode7788"
ACCESS_1 = "fixtureaccesstokenONEaaaaaaaaaaaaaaaaaaaa"
ACCESS_2 = "fixtureaccesstokenTWObbbbbbbbbbbbbbbbbbbb"
REFRESH_1 = "fixturerefreshtokenONEcccccccccccccccccccc"
REFRESH_2 = "fixturerefreshtokenTWOdddddddddddddddddddd"

ALL_SECRETS = [CLIENT_SECRET, AUTH_CODE, ACCESS_1, ACCESS_2,
               REFRESH_1, REFRESH_2]

LEAGUE_KEY = "461.l.428472"
LEAGUE_ID = "428472"
TEAM_KEY = "461.l.428472.t.5"


# --- fixtures (shapes mirror live Yahoo payloads) ---------------------------

def _stat(sid, value):
    return {"stat": {"stat_id": sid, "value": str(value)}}


def _cat(sid, name, ptype="O"):
    return {"stat": {"stat_id": sid, "name": name, "display_name": name,
                     "position_type": ptype}}


def _spot(position, count, ptype="O"):
    return {"roster_position": {"position": position, "position_type": ptype,
                                "count": count}}


SETTINGS_PAYLOAD = {
    "fantasy_content": {
        "league": [
            {"league_key": LEAGUE_KEY, "league_id": LEAGUE_ID,
             "name": "Kid's Table", "num_teams": 10, "season": "2026",
             "scoring_type": "head", "current_week": "1",
             "url": "https://football.fantasysports.yahoo.com/f1/428472"},
            {"settings": [{
                "draft_type": "live",
                "scoring_type": "head",
                "uses_faab": "1",
                "waiver_type": "FS",
                "uses_fractional_points": "1",
                "uses_negative_points": "1",
                "roster_positions": [
                    _spot("QB", 1), _spot("WR", 2), _spot("RB", 2),
                    _spot("TE", 1), _spot("W/R/T", 2),
                    _spot("K", 1, "K"), _spot("DEF", 1, "DT"),
                    _spot("BN", 6), _spot("IR", 2),
                ],
                "stat_categories": {"stats": [
                    _cat(4, "Passing Yards"), _cat(5, "Passing Touchdowns"),
                    _cat(6, "Interceptions"), _cat(9, "Rushing Yards"),
                    _cat(10, "Rushing Touchdowns"), _cat(11, "Receptions"),
                    _cat(12, "Receiving Yards"),
                    _cat(13, "Receiving Touchdowns"),
                    _cat(15, "Return Touchdowns"),
                    _cat(16, "2-Point Conversions"),
                    _cat(18, "Fumbles Lost"),
                    _cat(57, "Offensive Fumble Return TD"),
                    _cat(19, "Field Goals 0-19 Yards", "K"),
                    _cat(22, "Field Goals 40-49 Yards", "K"),
                    _cat(23, "Field Goals 50+ Yards", "K"),
                    _cat(29, "Point After Attempt Made", "K"),
                    _cat(32, "Sack", "DT"), _cat(33, "Interception", "DT"),
                    _cat(35, "Touchdown", "DT"),
                    _cat(50, "Points Allowed 0 points", "DT"),
                    _cat(56, "Points Allowed 35+ points", "DT"),
                    _cat(78, "Targets"),
                    _cat(1001, "Fixture Bonus Stat"),
                ]},
                "stat_modifiers": {"stats": [
                    _stat(4, "0.04"), _stat(5, "4"), _stat(6, "-1"),
                    _stat(9, "0.1"), _stat(10, "6"), _stat(11, "1"),
                    _stat(12, "0.1"), _stat(13, "6"), _stat(15, "6"),
                    _stat(16, "2"), _stat(18, "-2"), _stat(57, "6"),
                    _stat(19, "3"), _stat(22, "4"), _stat(23, "5"),
                    _stat(29, "1"),
                    _stat(32, "1"), _stat(33, "2"), _stat(35, "6"),
                    _stat(50, "10"), _stat(56, "-4"),
                    _stat(78, "0"),          # ignored counting stat
                    _stat(1001, "3.5"),      # unknown -> scoring.unmapped
                ]},
            }]},
        ]
    }
}

TEAMS_PAYLOAD = {
    "fantasy_content": {
        "league": [
            {"league_key": LEAGUE_KEY, "league_id": LEAGUE_ID,
             "name": "Kid's Table", "num_teams": 10},
            {"teams": {
                "0": {"team": [[{"team_key": "461.l.428472.t.1"},
                                {"team_id": "1"},
                                {"name": "Brock Hard"},
                                {"is_owned_by_current_login": 0},
                                []]]},
                "1": {"team": [[{"team_key": TEAM_KEY},
                                {"team_id": "5"},
                                {"name": "Kid's Table Champs"},
                                {"is_owned_by_current_login": 1},
                                [],
                                {"faab_balance": "100"},
                                {"waiver_priority": 7}]]},
                "count": 2}},
        ]
    }
}


def _player(pid, full, display, eligible, selected, abbr):
    return {"player": [
        [{"player_key": "461.p.%s" % pid},
         {"player_id": str(pid)},
         {"name": {"full": full, "first": full.split()[0],
                   "last": full.split()[-1], "ascii_first": full.split()[0],
                   "ascii_last": full.split()[-1]}},
         {"editorial_team_key": "nfl.t.1"},
         {"editorial_team_abbr": abbr},
         {"display_position": display},
         {"primary_position": display},
         {"eligible_positions": [{"position": p} for p in eligible]},
         []],
        {"selected_position": [{"coverage_type": "week", "week": "1"},
                               {"position": selected},
                               {"is_flex": 0}]},
    ]}


ROSTER_PAYLOAD = {
    "fantasy_content": {
        "team": [
            [{"team_key": TEAM_KEY}, {"team_id": "5"},
             {"name": "Kid's Table Champs"},
             {"is_owned_by_current_login": 1}, []],
            {"roster": {
                "coverage_type": "week", "week": "1", "is_editable": 1,
                "0": {"players": {
                    "0": _player(1, "Dak Prescott", "QB", ["QB"], "QB", "DAL"),
                    "1": _player(2, "Jahmyr Gibbs", "RB",
                                 ["RB", "W/R/T"], "RB", "DET"),
                    "2": _player(3, "Breece Hall", "RB",
                                 ["RB", "W/R/T"], "W/R/T", "NYJ"),
                    "3": _player(4, "Drake London", "WR",
                                 ["WR", "W/R/T"], "WR", "ATL"),
                    "4": _player(5, "Sam LaPorta", "TE",
                                 ["TE", "W/R/T"], "TE", "DET"),
                    "5": _player(6, "Evan McPherson", "K", ["K"], "K", "CIN"),
                    "6": _player(7, "Baltimore", "DEF", ["DEF"], "DEF", "BAL"),
                    "7": _player(8, "Rico Dowdle", "RB",
                                 ["RB", "W/R/T"], "BN", "CAR"),
                    "count": 8}},
            }},
        ]
    }
}

LEAGUES_PAYLOAD = {
    "fantasy_content": {
        "users": {
            "0": {"user": [
                {"guid": "FIXTUREGUID0000000000000000"},
                {"games": {
                    "0": {"game": [
                        {"game_key": "461", "game_id": "461",
                         "name": "Football", "code": "nfl", "season": "2026"},
                        {"leagues": {
                            "0": {"league": [{
                                "league_key": LEAGUE_KEY,
                                "league_id": LEAGUE_ID,
                                "name": "Kid's Table",
                                "num_teams": 10,
                                "season": "2026",
                                "scoring_type": "head",
                                "draft_status": "postdraft",
                                "url": "https://football.fantasysports."
                                       "yahoo.com/f1/428472"}]},
                            "count": 1}},
                    ]},
                    "count": 1}},
            ]},
            "count": 1}
    }
}


# --- the fake network -------------------------------------------------------

class FakeResponse(object):
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status, payload):
    body = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError(
        "https://api.login.yahoo.com/oauth2/get_token", status,
        "fixture", {}, io.BytesIO(body))


class Router(object):
    """Replaces urllib.request.urlopen. Unknown URLs raise - proof of offline."""

    def __init__(self):
        self.calls = []            # (method, url, form-or-None)
        self.bearers = []
        self.token_script = []     # queued outcomes for /get_token
        self.api_script = {}       # path fragment -> queued outcomes
        self.access_now = ACCESS_1

    def queue_token(self, outcome):
        self.token_script.append(outcome)

    def queue_api(self, fragment, outcome):
        self.api_script.setdefault(fragment, []).append(outcome)

    def __call__(self, req, timeout=None):
        url = req.full_url
        if url.startswith(yahoo.TOKEN_URL):
            return self._token(req, url)
        if url.startswith(yahoo.API_BASE):
            return self._api(req, url)
        raise AssertionError("test tried to reach the network: %s" % url)

    def _token(self, req, url):
        form = dict(urllib.parse.parse_qsl(req.data.decode("utf-8")))
        self.calls.append(("POST", url, form))
        auth = req.get_header("Authorization") or ""
        if not auth.startswith("Basic "):
            raise AssertionError("token call had no Basic app auth")
        decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        if decoded != "%s:%s" % (CLIENT_ID, CLIENT_SECRET):
            raise AssertionError("Basic auth did not carry the app credential")
        if self.token_script:
            outcome = self.token_script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(outcome)
        grant = form.get("grant_type")
        if grant == "authorization_code":
            return FakeResponse({"access_token": ACCESS_1,
                                 "refresh_token": REFRESH_1,
                                 "expires_in": 3600, "token_type": "bearer",
                                 "xoauth_yahoo_guid": "FIXTUREGUID"})
        if grant == "refresh_token":
            self.access_now = ACCESS_2
            return FakeResponse({"access_token": ACCESS_2,
                                 "refresh_token": REFRESH_2,
                                 "expires_in": 3600, "token_type": "bearer"})
        raise AssertionError("unexpected grant_type %r" % grant)

    def _api(self, req, url):
        self.calls.append((req.get_method(), url, None))
        bearer = (req.get_header("Authorization") or "")
        if not bearer.startswith("Bearer "):
            raise AssertionError("api call had no Bearer token")
        self.bearers.append(bearer.split(" ", 1)[1])
        if req.get_method() != "GET":
            raise AssertionError("this connector must never write: %s"
                                 % req.get_method())
        for fragment, queue in self.api_script.items():
            if fragment in url and queue:
                outcome = queue.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return FakeResponse(outcome)
        if "users;use_login=1" in url:
            return FakeResponse(LEAGUES_PAYLOAD)
        if "/settings" in url:
            return FakeResponse(SETTINGS_PAYLOAD)
        if "/teams" in url:
            return FakeResponse(TEAMS_PAYLOAD)
        if "/roster" in url:
            return FakeResponse(ROSTER_PAYLOAD)
        raise AssertionError("router has no fixture for %s" % url)


# --- sandbox ----------------------------------------------------------------

class Sandbox(object):
    """Redirect every yahoo path into a tempdir; restore in __exit__."""

    def __init__(self, with_secrets=True, scope=yahoo.SCOPE_READ,
                 redirect_uri=yahoo.OOB):
        self.with_secrets = with_secrets
        self.scope = scope
        self.redirect_uri = redirect_uri

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="yahoo-test-")
        self.saved = {k: getattr(yahoo, k) for k in
                      ("DATA_DIR", "LEAGUES_DIR", "ROSTERS_DIR",
                       "SECRETS_FILE", "TOKENS_DIR", "HERE")}
        self.saved_rebuild = yahoo.rebuild_rankings
        self.saved_urlopen = urllib.request.urlopen
        yahoo.HERE = self.root
        yahoo.DATA_DIR = os.path.join(self.root, "data")
        yahoo.LEAGUES_DIR = os.path.join(self.root, "leagues")
        yahoo.ROSTERS_DIR = os.path.join(self.root, "data", "rosters")
        yahoo.SECRETS_FILE = os.path.join(self.root, "data",
                                          "yahoo_secrets.json")
        yahoo.TOKENS_DIR = os.path.join(self.root, "data", "yahoo_tokens")
        for path in (yahoo.DATA_DIR, yahoo.LEAGUES_DIR, yahoo.ROSTERS_DIR):
            os.makedirs(path, exist_ok=True)
        if self.with_secrets:
            doc = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                   "redirect_uri": self.redirect_uri}
            if self.scope is not None:
                doc["scope"] = self.scope
            with open(yahoo.SECRETS_FILE, "w") as fh:
                json.dump(doc, fh)
            os.chmod(yahoo.SECRETS_FILE, 0o600)

        self.rebuilds = []

        def fake_rebuild(csv_path, reception, teams, year=yahoo.SEASON):
            self.rebuilds.append((csv_path, reception, teams, year))
            return {"seeded": 200, "filled": 180, "tiered": 150,
                    "scoring": "ppr" if reception >= 1 else "std"}

        yahoo.rebuild_rankings = fake_rebuild
        self.router = Router()
        urllib.request.urlopen = self.router
        return self

    def __exit__(self, *exc):
        urllib.request.urlopen = self.saved_urlopen
        yahoo.rebuild_rankings = self.saved_rebuild
        for key, value in self.saved.items():
            setattr(yahoo, key, value)
        shutil.rmtree(self.root, ignore_errors=True)
        return False

    def connect(self, person="sam"):
        """Take a person all the way through consent, offline."""
        yahoo.authorize_url(person)
        return yahoo.exchange_code(person, AUTH_CODE)


@contextlib.contextmanager
def captured():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


# --- 1. authorization URL ---------------------------------------------------

def test_authorize_url():
    print("\n1. AUTHORIZATION URL AND SCOPE")
    with Sandbox() as box:
        url, state = yahoo.authorize_url("sam")
        parsed = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(parsed.query))
        check(url.startswith(yahoo.AUTH_URL),
              "consent URL points at api.login.yahoo.com/oauth2/request_auth")
        check(q.get("client_id") == CLIENT_ID,
              "carries the OWNER's one client_id (no per-friend app)")
        check(q.get("response_type") == "code",
              "response_type=code (authorization code grant)")
        check(q.get("redirect_uri") == "oob",
              "redirect_uri=oob - Yahoo shows the code, no callback host")
        check(q.get("scope") == yahoo.SCOPE_READ,
              "scope is the Fantasy READ scope fspt-r")
        check(yahoo.SCOPE_WRITE not in url,
              "the read/write scope fspt-w never appears in the URL")
        check(len(state) >= 16 and q.get("state") == state,
              "a random state is issued and echoed into the URL")

        pending = yahoo.pending_path("sam")
        mode = stat.S_IMODE(os.stat(pending).st_mode)
        check(mode == 0o600, "pending state file is mode 0600")

        url2, state2 = yahoo.authorize_url("sam")
        check(state2 != state, "each authorize issues a fresh state")

        # two different people, one app
        url3, _ = yahoo.authorize_url("alex")
        q3 = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url3).query))
        check(q3.get("client_id") == q.get("client_id"),
              "a second person gets the SAME app - one app, many people")
        check(os.path.exists(yahoo.pending_path("alex")),
              "each person gets their own pending file")

    with Sandbox(scope="") as box:
        url, _ = yahoo.authorize_url("sam")
        check("scope=" not in url,
              "scope can be omitted (app registration pins Read) when the "
              "owner sets scope to empty")

    with Sandbox(scope=yahoo.SCOPE_WRITE) as box:
        try:
            yahoo.authorize_url("sam")
            check(False, "asking for fspt-w is refused")
        except yahoo.YahooSetupError as exc:
            check("advise-only" in str(exc),
                  "asking for fspt-w is refused as advise-only violation")

    with Sandbox(with_secrets=False) as box:
        try:
            yahoo.load_app()
            check(False, "missing app credential raises YahooSetupError")
        except yahoo.YahooSetupError as exc:
            check("SETUP_YAHOO.md" in str(exc),
                  "missing app credential points at SETUP_YAHOO.md")


# --- 2. code exchange -------------------------------------------------------

def test_exchange():
    print("\n2. AUTHORIZATION CODE -> TOKEN")
    with Sandbox() as box:
        yahoo.authorize_url("sam")
        token = yahoo.exchange_code("sam", AUTH_CODE)
        method, url, form = box.router.calls[-1]
        check(method == "POST" and url.startswith(yahoo.TOKEN_URL),
              "exchange POSTs to api.login.yahoo.com/oauth2/get_token")
        check(form.get("grant_type") == "authorization_code",
              "grant_type=authorization_code")
        check(form.get("code") == AUTH_CODE, "the person's code is sent")
        check(form.get("redirect_uri") == "oob",
              "redirect_uri matches the one the consent URL used")
        check(token.access_token == ACCESS_1 and
              token.refresh_token == REFRESH_1,
              "access and refresh tokens are captured")
        check(3000 < token.seconds_left() <= 3600,
              "expiry set from Yahoo's 1-hour expires_in")
        check(not os.path.exists(yahoo.pending_path("sam")),
              "the pending state file is consumed and deleted")

        stored = json.load(open(yahoo.token_path("sam")))
        check(stored["refresh_token"] == REFRESH_1,
              "the refresh token is persisted for next time")
        check(stored["scope"] == yahoo.SCOPE_READ,
              "the stored token records the read-only scope")

        # a full redirect URL works just as well as a bare code
        yahoo.authorize_url("alex")
        pend = json.load(open(yahoo.pending_path("alex")))
        redirect = ("https://localhost:8080/?code=%s&state=%s"
                    % (AUTH_CODE, pend["state"]))
        token2 = yahoo.exchange_code("alex", redirect)
        check(token2.access_token == ACCESS_1,
              "a pasted redirect URL is accepted - the code is parsed out")

        check(sorted(p["person"] for p in yahoo.connected_people())
              == ["alex", "sam"],
              "two people are connected against the one app")


# --- 3. refresh -------------------------------------------------------------

def test_refresh():
    print("\n3. REFRESH ON EXPIRY")
    with Sandbox() as box:
        box.connect("sam")

        # age the token past Yahoo's 1-hour life
        stored = json.load(open(yahoo.token_path("sam")))
        stored["expires_at"] = time.time() - 60
        yahoo._write_private(yahoo.token_path("sam"), json.dumps(stored))

        before = len(box.router.calls)
        leagues = yahoo.list_leagues("sam")
        forms = [f for (m, u, f) in box.router.calls[before:] if f]
        check(any(f.get("grant_type") == "refresh_token" for f in forms),
              "an expired access token triggers grant_type=refresh_token")
        check(any(f.get("refresh_token") == REFRESH_1 for f in forms),
              "the stored refresh token is what is presented")
        check(box.router.bearers[-1] == ACCESS_2,
              "the API call then uses the NEW access token")
        check(len(leagues) == 1 and leagues[0]["league_id"] == LEAGUE_ID,
              "the read succeeds after the silent refresh")

        rotated = json.load(open(yahoo.token_path("sam")))
        check(rotated["refresh_token"] == REFRESH_2,
              "a rotated refresh token replaces the old one on disk")

        # a token still inside its window is NOT refreshed
        before = len(box.router.calls)
        yahoo.list_leagues("sam")
        forms = [f for (m, u, f) in box.router.calls[before:] if f]
        check(not forms, "a live token is reused, not refreshed every call")

        # Yahoo may keep the same refresh token; we must not lose it
        box.router.queue_token({"access_token": ACCESS_1, "expires_in": 3600,
                                "token_type": "bearer"})
        token = yahoo.refresh_token("sam")
        check(token.refresh_token == REFRESH_2,
              "a refresh response with no refresh_token keeps the stored one")

        # 401 mid-flight: one forced refresh, then retry
        box.router.queue_api("/settings", http_error(
            401, {"error": {"description": "token expired"}}))
        meta, settings = yahoo.league_settings("sam", LEAGUE_KEY)
        check(meta.get("league_key") == LEAGUE_KEY,
              "a mid-flight 401 is retried once after a forced refresh")


# --- 4. token file permissions ---------------------------------------------

def test_token_file_mode():
    print("\n4. TOKEN FILE PRIVACY")
    with Sandbox() as box:
        box.connect("sam")
        path = yahoo.token_path("sam")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        check(mode == 0o600, "data/yahoo_tokens/sam.json is mode 0600")
        dir_mode = stat.S_IMODE(os.stat(yahoo.TOKENS_DIR).st_mode)
        check(dir_mode == 0o700, "data/yahoo_tokens/ is mode 0700")
        guard = os.path.join(yahoo.TOKENS_DIR, ".gitignore")
        check(os.path.exists(guard) and
              open(guard).read().strip().endswith("*"),
              "the tokens directory writes its own .gitignore so other "
              "people's tokens cannot be committed by accident")

        # rewriting must not widen the mode, and must leave no stray temp file
        box.connect("sam")
        mode = stat.S_IMODE(os.stat(path).st_mode)
        check(mode == 0o600, "a re-authorize rewrites the file still at 0600")
        strays = [f for f in os.listdir(yahoo.TOKENS_DIR) if ".tmp" in f]
        check(not strays, "the atomic write leaves no .tmp file behind")

        check(ACCESS_1 not in repr(box.connect("sam")) and
              REFRESH_1 not in repr(yahoo.load_token("sam")),
              "Token.__repr__ shows facts, never token values")

        removed = yahoo.forget_person("sam")
        check(removed and not os.path.exists(path),
              "forget deletes the local token file")

        for bad in ("../../etc/passwd", "sam/../alex", "", "a" * 60):
            try:
                yahoo.token_path(bad)
                check(False, "person name %r is rejected" % bad)
                break
            except yahoo.YahooError:
                pass
        else:
            check(True, "person names that could escape the tokens dir are "
                        "rejected (path traversal, empty, over-long)")


# --- 5. typed failures ------------------------------------------------------

def test_typed_failures():
    print("\n5. TYPED FAILURES")
    with Sandbox() as box:
        yahoo.authorize_url("sam")

        # denied consent
        try:
            yahoo.exchange_code(
                "sam", "https://localhost:8080/?error=access_denied&"
                       "error_description=User+denied+access")
            check(False, "denied consent raises YahooConsentDenied")
        except yahoo.YahooConsentDenied as exc:
            check("declined" in str(exc) and "nothing was stored" in str(exc),
                  "denied consent -> YahooConsentDenied, says nothing was kept")

        # expired / already-used code
        box.router.queue_token(http_error(400, {
            "error": "invalid_grant",
            "error_description": "Invalid authorization code"}))
        try:
            yahoo.exchange_code("sam", AUTH_CODE)
            check(False, "an expired code raises YahooCodeError")
        except yahoo.YahooCodeError as exc:
            check("single-use" in str(exc),
                  "expired/used code -> YahooCodeError with the real reason")

        # revoked refresh token
        box.connect("sam")
        box.router.queue_token(http_error(400, {
            "error": "invalid_grant",
            "error_description": "token revoked"}))
        try:
            yahoo.refresh_token("sam")
            check(False, "a revoked token raises YahooTokenRevoked")
        except yahoo.YahooTokenRevoked as exc:
            check("revoked this app" in str(exc),
                  "revoked token -> YahooTokenRevoked, names the cause")

        # a second 401 after a forced refresh is also 'revoked'
        box.connect("sam")
        box.router.queue_api("/settings",
                             http_error(401, {"error": "unauthorized"}))
        box.router.queue_api("/settings",
                             http_error(401, {"error": "unauthorized"}))
        try:
            yahoo.league_settings("sam", LEAGUE_KEY)
            check(False, "two 401s in a row raise YahooTokenRevoked")
        except yahoo.YahooTokenRevoked:
            check(True, "a 401 that survives a fresh token -> "
                        "YahooTokenRevoked")

        # throttling
        box.connect("sam")
        box.router.queue_api("/settings", http_error(999, {"error": "rate"}))
        try:
            yahoo.league_settings("sam", LEAGUE_KEY)
            check(False, "throttling raises YahooRateLimited")
        except yahoo.YahooRateLimited as exc:
            check("throttling" in str(exc),
                  "HTTP 999 -> YahooRateLimited (Yahoo's own throttle code)")

        # bad app credential
        box.connect("sam")
        box.router.queue_token(http_error(401, {"error": "invalid_client"}))
        try:
            yahoo.refresh_token("sam")
            check(False, "a bad app credential raises YahooSetupError")
        except yahoo.YahooSetupError as exc:
            check("SETUP_YAHOO.md" in str(exc),
                  "invalid_client -> YahooSetupError pointing at setup")

        # nobody connected
        try:
            yahoo.load_token("nobody")
            check(False, "an unconnected person raises YahooNotConnected")
        except yahoo.YahooNotConnected as exc:
            check("authorize" in str(exc),
                  "unconnected person -> YahooNotConnected with the next step")


# --- 6. mapping into engine artifacts --------------------------------------

def test_import_mapping():
    print("\n6. YAHOO PAYLOAD -> ENGINE ARTIFACTS")
    with Sandbox() as box:
        box.connect("sam")
        summary = yahoo.import_league("sam", LEAGUE_ID)

        league_path = os.path.join(yahoo.LEAGUES_DIR,
                                   "yahoo-%s.yaml" % LEAGUE_ID)
        roster_path = os.path.join(yahoo.ROSTERS_DIR,
                                   "yahoo-%s.yaml" % LEAGUE_ID)
        check(os.path.exists(league_path), "leagues/yahoo-<id>.yaml written")
        check(os.path.exists(roster_path),
              "data/rosters/yahoo-<id>.yaml written")

        cfg = LeagueConfig.load(league_path)
        check(cfg.id == "yahoo-%s" % LEAGUE_ID and cfg.platform == "yahoo",
              "the league yaml loads through LeagueConfig")
        check(cfg.teams == 10, "team count comes from num_teams")
        check(cfg.waiver_mode == "faab",
              "uses_faab='1' maps to waiver_mode: faab")
        check(cfg.ppr == 1.0 and cfg.scoring_label() == "ppr",
              "stat_id 11 value 1 -> reception 1.0 -> PPR")
        check(cfg.scoring.get("passing_yards_per_point") == 25.0,
              "Yahoo's 0.04 points-per-yard inverts to 25 yards-per-point")
        check(cfg.scoring.get("rushing_yards_per_point") == 10.0 and
              cfg.scoring.get("receiving_yards_per_point") == 10.0,
              "rushing and receiving yardage invert the same way")
        check(cfg.scoring.get("passing_td") == 4.0 and
              cfg.scoring.get("interception") == -1.0 and
              cfg.scoring.get("fumble_lost") == -2.0,
              "flat point stats carry through with their signs")
        check(cfg.scoring.get("kicker", {}).get("fg_50_plus") == 5.0,
              "kicker stat ids land in scoring.kicker")
        check(cfg.scoring.get("defense", {}).get("points_allowed_35_plus")
              == -4.0,
              "defense stat ids land in scoring.defense")
        check("1001 (Fixture Bonus Stat)" in (cfg.scoring.get("unmapped") or {}),
              "an unknown scoring rule is kept under scoring.unmapped, "
              "never silently dropped")
        check("78 (Targets)" not in str(cfg.scoring.get("unmapped") or {}),
              "zero-value counting stats are not reported as unmapped noise")

        spots = cfg.roster_spots
        check(spots.count("W/R/T") == 2 and spots.count("BN") == 6 and
              spots.count("IR") == 2,
              "roster_positions expand by count (2 flex, 6 bench, 2 IR)")
        check(len(spots) == 18 and cfg.rounds == 16,
              "18 roster spots but 16 rounds - Yahoo's 2 IR slots are never "
              "drafted and must not invent phantom rounds")
        starters = cfg.hard_starter_counts()
        check(starters["QB"] == 1 and starters["RB"] == 2 and
              starters["WR"] == 2 and starters["TE"] == 1 and
              starters["K"] == 1 and starters["DEF"] == 1,
              "hard starter counts survive the mapping")
        check(len(cfg.flex_spots()) == 2,
              "W/R/T is a flex the engine already understands")
        check(cfg.host == {"league_id": LEAGUE_ID, "team_id": "5"},
              "host deep-link ids come from the person's own team key")
        check("Kid's Table Champs" in cfg.team_names,
              "team names are carried for the draft board")

        roster = yaml.safe_load(open(roster_path))
        check(roster["league"] == "yahoo-%s" % LEAGUE_ID and
              roster["size"] == 8, "roster yaml matches the Sleeper shape")
        check("Baltimore Defense" in roster["players"],
              "Yahoo's 'Baltimore' becomes 'Baltimore Defense' so the "
              "rankings CSV can match it")
        check("Dak Prescott" in roster["players"] and
              "Rico Dowdle" in roster["players"],
              "starters and bench are both in the roster")

        check(box.rebuilds and box.rebuilds[0][1] == 1.0 and
              box.rebuilds[0][2] == 10,
              "the rankings rebuild runs with THIS league's PPR and size")
        check(box.rebuilds[0][0].endswith(
            "data/rankings-yahoo-%s.csv" % LEAGUE_ID),
            "the rebuild targets this league's own rankings CSV")

        check(summary["league_key"] == LEAGUE_KEY and
              summary["team_key"] == TEAM_KEY,
              "a bare league id resolves to the full Yahoo league_key")
        check(not summary["superflex"], "a 1-QB league is not flagged "
                                        "superflex")

        # the connector never writes to Yahoo
        methods = set(m for (m, u, f) in box.router.calls
                      if u.startswith(yahoo.API_BASE))
        check(methods == {"GET"},
              "every Fantasy API call is a GET - advise-only holds")

        # someone else's league
        try:
            yahoo.import_league("sam", "999999", rebuild=False)
            check(False, "an unknown league id is refused")
        except yahoo.YahooError as exc:
            check("999999" in str(exc),
                  "an unknown league id is refused, naming the id")


def test_no_team_of_mine():
    print("\n7. LEAGUE THE PERSON DOES NOT PLAY IN")
    with Sandbox() as box:
        box.connect("sam")
        orphan = json.loads(json.dumps(TEAMS_PAYLOAD))
        orphan["fantasy_content"]["league"][1]["teams"]["1"]["team"][0][3] = \
            {"is_owned_by_current_login": 0}
        box.router.queue_api("/teams", orphan)
        try:
            yahoo.import_league("sam", LEAGUE_KEY, rebuild=False)
            check(False, "a league with no team of theirs is refused")
        except yahoo.YahooAPIError as exc:
            check("different Yahoo login" in str(exc),
                  "no owned team -> honest error naming the likely cause")
        check(not os.path.exists(os.path.join(
            yahoo.LEAGUES_DIR, "yahoo-%s.yaml" % LEAGUE_ID)),
            "nothing is written for a failed import")


# --- 8. secrets never surface ----------------------------------------------

def test_secrets_never_surface():
    print("\n8. NO SECRET IN ANY OUTPUT")
    with Sandbox() as box:
        box.connect("sam")
        with captured() as buf:
            yahoo_cli.main(["status"])
            yahoo_cli.main(["authorize", "--person", "sam"])
            yahoo_cli.main(["leagues", "--person", "sam"])
            yahoo_cli.main(["check", "--person", "sam"])
            yahoo_cli.main(["import", "--person", "sam",
                            "--league", LEAGUE_ID])
            yahoo_cli.main(["purge"])
            yahoo_cli.main(["forget", "--person", "sam"])
        printed = buf.getvalue()
        leaked = [s for s in ALL_SECRETS if s in printed]
        check(not leaked,
              "no app secret, token, or auth code in %d lines of CLI output"
              % len(printed.splitlines()))
        check("dj0yJmk9" in printed,
              "the client_id IS printed - it is the public half of the consent "
              "link and has to be")

        # every artifact on disk
        rendered = []
        for directory in (yahoo.LEAGUES_DIR, yahoo.ROSTERS_DIR):
            for name in os.listdir(directory):
                path = os.path.join(directory, name)
                if os.path.isfile(path):
                    rendered.append(open(path).read())
        blob = "\n".join(rendered)
        check(blob and not [s for s in ALL_SECRETS if s in blob],
              "no secret in any league/roster artifact that publish.py "
              "would render into a page")

    with Sandbox() as box:
        box.connect("sam")
        # an upstream error body that echoes the token back at us
        box.router.queue_api("/settings", http_error(500, {
            "error": {"description":
                      "upstream failure for token %s" % ACCESS_1}}))
        try:
            yahoo.league_settings("sam", LEAGUE_KEY)
            check(False, "the echoed-token error raises")
        except yahoo.YahooError as exc:
            check(ACCESS_1 not in str(exc) and "<redacted>" in str(exc),
                  "a token echoed back inside a Yahoo error body is redacted "
                  "out of the exception message")

        with captured() as buf:
            yahoo.log("debug: bearer=%s refresh=%s secret=%s"
                      % (ACCESS_1, REFRESH_1, CLIENT_SECRET))
        line = buf.getvalue()
        check(not [s for s in ALL_SECRETS if s in line] and
              line.count("<redacted>") == 3,
              "a log line that tries to print three secrets prints none")

        try:
            raise yahoo.YahooError("boom while using %s" % REFRESH_1)
        except yahoo.YahooError as exc:
            check(REFRESH_1 not in str(exc) and REFRESH_1 not in repr(exc),
                  "YahooError scrubs its own message and repr")


# --- 9. the 24-hour retention rule -----------------------------------------

def test_retention():
    print("\n9. 24-HOUR RETENTION (Yahoo APIs ToU s2.1)")
    with Sandbox() as box:
        box.connect("sam")
        yahoo.import_league("sam", LEAGUE_ID, rebuild=False)
        league_path = os.path.join(yahoo.LEAGUES_DIR,
                                   "yahoo-%s.yaml" % LEAGUE_ID)
        roster_path = os.path.join(yahoo.ROSTERS_DIR,
                                   "yahoo-%s.yaml" % LEAGUE_ID)
        doc = yaml.safe_load(open(league_path))
        check(doc.get("yahoo_fetched_at") and
              doc.get("yahoo_retention_expires_at"),
              "the league artifact is stamped with fetch time and expiry")
        span = (yahoo._parse_iso(doc["yahoo_retention_expires_at"]) -
                yahoo._parse_iso(doc["yahoo_fetched_at"]))
        check(abs(span - 24 * 3600) < 2,
              "the expiry is exactly 24 hours after the fetch")
        check("Terms of Use" in open(league_path).read(),
              "the file itself says why it expires")
        check(yaml.safe_load(open(roster_path)).get(
            "yahoo_retention_expires_at"),
            "the roster artifact is stamped too")

        check(not yahoo.expired_artifacts(),
              "a fresh import is not expired")
        check(yahoo.require_fresh(league_path) == league_path,
              "require_fresh passes a fresh artifact straight through")
        try:
            yahoo.require_fresh(league_path, now=time.time() + 25 * 3600)
            check(False, "require_fresh refuses a stale artifact")
        except yahoo.YahooRetentionError as exc:
            check("s2.1" in str(exc),
                  "require_fresh refuses a stale artifact, citing the clause "
                  "- a stamped file served anyway is the same violation")
        future = time.time() + 25 * 3600
        stale = yahoo.expired_artifacts(now=future)
        check(sorted(stale) == sorted([league_path, roster_path]),
              "25 hours later both artifacts are expired")

        # a hand-written league yaml has no stamp and must survive
        handwritten = os.path.join(yahoo.LEAGUES_DIR, "yahoo-main.yaml")
        with open(handwritten, "w") as fh:
            fh.write("id: yahoo-main\nname: Kid's Table\nplatform: yahoo\n")
        check(handwritten not in yahoo.expired_artifacts(now=future),
              "an unstamped hand-written yahoo-main.yaml is never a purge "
              "candidate")

        removed = yahoo.purge_expired(now=future)
        check(sorted(removed) == sorted([league_path, roster_path]),
              "purge removes exactly the expired Yahoo artifacts")
        check(os.path.exists(handwritten),
              "purge left the hand-written league config alone")
        check(not os.path.exists(league_path),
              "the expired artifact is gone from disk")

    # An import must SWEEP, not just stamp. A rule enforced only when the
    # owner remembers to type `purge` is a rule that will be broken by the
    # first busy Sunday, so the common path has to clean up after itself.
    with Sandbox() as box:
        box.connect("sam")

        # a different league, fetched 30 hours ago and never purged
        old = os.path.join(yahoo.LEAGUES_DIR, "yahoo-999999.yaml")
        old_roster = os.path.join(yahoo.ROSTERS_DIR, "yahoo-999999.yaml")
        past = time.time() - 30 * 3600
        stamp = yahoo.retention_stamps(fetched_at=past)
        for path in (old, old_roster):
            with open(path, "w") as fh:
                fh.write(yaml.safe_dump(dict({"id": "yahoo-999999"}, **stamp)))

        summary = yahoo.import_league("sam", LEAGUE_ID, rebuild=False)

        check(not os.path.exists(old) and not os.path.exists(old_roster),
              "importing one league sweeps ANOTHER league's expired artifacts")
        check(sorted(summary.get("purged") or []) == sorted([old, old_roster]),
              "the import reports exactly what it purged, so the owner is "
              "told rather than silently losing a file")

        fresh = os.path.join(yahoo.LEAGUES_DIR, "yahoo-%s.yaml" % LEAGUE_ID)
        check(os.path.exists(fresh),
              "the league being imported survives its own sweep")
        check(fresh not in (summary.get("purged") or []),
              "and is never listed as purged")


# --- 10. CLI surface --------------------------------------------------------

def test_cli():
    print("\n10. CLI")
    with Sandbox(with_secrets=False) as box:
        with captured() as buf:
            rc = yahoo_cli.main(["status"])
        check(rc == 1 and "SETUP_YAHOO.md" in buf.getvalue(),
              "status with no app registered points at SETUP_YAHOO.md")

    with Sandbox() as box:
        with captured() as buf:
            rc = yahoo_cli.main(["status"])
        out = buf.getvalue()
        check(rc == 0 and "nobody has consented yet" in out,
              "status with an app but no people says so")

        with captured() as buf:
            rc = yahoo_cli.main(["authorize", "--person", "sam"])
        out = buf.getvalue()
        check(rc == 0 and yahoo.AUTH_URL in out,
              "authorize prints the consent link to send")
        check("no password, no cookie" in out.lower(),
              "authorize tells the owner what the friend will and will not do")

        pend = json.load(open(yahoo.pending_path("sam")))
        with captured() as buf:
            rc = yahoo_cli.main(["finish", "--person", "sam",
                                 "--code", AUTH_CODE])
        out = buf.getvalue()
        check(rc == 0 and "is connected" in out, "finish exchanges the code")
        check("revoke" in out and "Apps connected to your account" in out,
              "finish says where they can revoke it")

        with captured() as buf:
            rc = yahoo_cli.main(["leagues"])
        check(rc == 0 and LEAGUE_ID in buf.getvalue(),
              "leagues works without --person when exactly one is connected")

        with captured() as buf:
            rc = yahoo_cli.main(["check", "--person", "sam"])
        out = buf.getvalue()
        check(rc == 0 and "refresh    : ok" in out,
              "check proves the token refreshes")
        check("0o600" in out, "check reports the token file mode")

        with captured() as buf:
            rc = yahoo_cli.main(["import", "--person", "sam",
                                 "--league", LEAGUE_ID])
        out = buf.getvalue()
        check(rc == 0 and "CREATED" in out and "EXPIRES" in out,
              "import reports what it wrote and when it expires")
        check("scoring.unmapped" in out,
              "import says out loud that a scoring rule was unmapped")

        with captured() as buf:
            rc = yahoo_cli.main(["finish", "--person", "sam"])
        check(rc == 2, "finish without --code exits 2 rather than guessing")

        with captured() as buf:
            rc = yahoo_cli.main(["import", "--person", "sam"])
        check(rc == 2, "import without --league exits 2")

        yahoo.forget_person("sam")
        with captured() as buf:
            rc = yahoo_cli.main(["leagues"])
        check(rc == 1 and "--person" in buf.getvalue(),
              "with nobody connected the CLI asks who, and exits 1")

        box.router.queue_api("/settings", http_error(429, {"error": "slow"}))
        box.connect("sam")
        with captured() as buf:
            rc = yahoo_cli.main(["import", "--person", "sam",
                                 "--league", LEAGUE_KEY])
        check(rc == 1 and "YahooRateLimited" in buf.getvalue(),
              "a typed failure reaches the CLI as its own name, exit 1")


def main():
    print("=" * 64)
    print("YAHOO CONNECTOR ACCEPTANCE TEST (offline fixtures)")
    print("=" * 64)

    before_leagues = sorted(os.listdir(os.path.join(HERE, "leagues")))
    before_rosters = sorted(os.listdir(os.path.join(HERE, "data", "rosters")))

    test_authorize_url()
    test_exchange()
    test_refresh()
    test_token_file_mode()
    test_typed_failures()
    test_import_mapping()
    test_no_team_of_mine()
    test_secrets_never_surface()
    test_retention()
    test_cli()

    print("\n11. PRODUCTION STATE UNTOUCHED")
    check(sorted(os.listdir(os.path.join(HERE, "leagues"))) == before_leagues,
          "the real leagues/ listing is unchanged (all writes went to "
          "tempdirs)")
    check(sorted(os.listdir(os.path.join(HERE, "data", "rosters")))
          == before_rosters, "the real data/rosters/ listing is unchanged")
    check(not os.path.exists(os.path.join(HERE, "data", "yahoo_tokens")),
          "no token directory was created in the real project")

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
