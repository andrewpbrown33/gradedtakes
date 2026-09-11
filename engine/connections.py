"""One place to connect all three platforms, FOR A PERSON WHO IS NOT YOU.

Two layers live here.

THE PLATFORM LAYER (original) - Sleeper is the star: its API is public and
read-only (no auth, no keys), so a username is enough to resolve leagues,
import one into leagues/ + data/rosters/, and run the per-league data rebuild
from docs/PER_LEAGUE.md (ADP seed -> projections fill -> Chen tiers). ESPN and
Yahoo import through their own modules (engine/espn_public.py,
engine/yahoo_cli.py), which this module calls through documented seams.

THE PERSON LAYER (docs/ONBOARD.md) - the owner runs this on his Mac and
publishes a private copy per person, so onboarding is something you do TO
SOMEONE ELSE'S account, not to your own. A person is a name, an email, and
one or more leagues across platforms; data/people.yaml is the ledger of who
is being onboarded and what is connected. It is NOT the publish list -
publish.py reads users.yaml and this module never writes that file (see
users_yaml_block(), which prints the block for you to paste).

    add_person(name, email)             -> the record
    list_people()                       -> every record
    add_league_for(person, platform, **) -> connect ONE league, record it
    coverage(person)                    -> connected / missing / stale
    status(person=None)                 -> the platform board PLUS a
                                           per-person board under "people"

THE CREDENTIAL RULE, WHICH IS NOT NEGOTIABLE: we never take custody of
another person's platform password or session cookie - not here, not on a
server, not "just for testing". A pasted cookie is not consent, it is
credential sharing, and it breaks the sharer's own terms with the platform.
So each platform gets a route that a FRIEND can safely walk:

    Sleeper  their username. Public read-only API. Nothing else exists.
    Yahoo    OAuth consent: you send a link, they approve in Yahoo, they
             read back a short code. That IS consent, and it is fine.
    ESPN     either they flip their league to publicly viewable and give
             you the league id, or they paste their roster in. ESPN's
             espn_s2/SWID cookies are whole-account Disney session
             credentials - asking a friend for those is off the table, and
             the ESPN card in the panel says so out loud.

ADVISE-ONLY holds throughout: read-only scopes everywhere, nothing is ever
written back to a host platform.

Everything network-touching is cached under data/cache/ with the
fresh-cache -> network -> stale-cache -> honest-error discipline from
engine/adp.py. Nothing here writes outside leagues/, data/rosters/,
data/cache/, data/people.yaml, and the league's own rankings CSV. Secret
VALUES are never printed, logged, recorded in the ledger, or returned -
status lines only ever say whether a file exists.

Sleeper waiver_type enum (settings.waiver_type), verified 2026-09-02 against
live public leagues (docs.sleeper.com does not document the numbers):
    0 = rolling waivers      -> priority   (68/68 sampled claims had no bid)
    1 = reverse standings    -> priority
    2 = FAAB blind bidding   -> faab       (27/27 sampled claims carried
                                            settings.waiver_bid)

CLI (./connect.sh):  python -m engine.connections [status|people]
"""

import datetime
import glob
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from typing import Dict, List, Optional

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# Paths as module-level names so tests can redirect them into a tempdir
# (tests/mock_draft.py SAVE_DIR discipline).
LEAGUES_DIR = os.path.join(HERE, "leagues")
ROSTERS_DIR = os.path.join(HERE, "data", "rosters")
DATA_DIR = os.path.join(HERE, "data")
CACHE_DIR = os.path.join(HERE, "data", "cache")
ESPN_SECRETS = os.path.join(HERE, "data", "espn_secrets.json")
YAHOO_SECRETS = os.path.join(HERE, "data", "yahoo_secrets.json")
YAHOO_TOKEN = os.path.join(HERE, "data", "yahoo_token.json")
ESPN_CHECK_FLAG = os.path.join(HERE, "data", "cache", "espn-connect-ok.json")

# The onboarding ledger (ours) and the publish list (publish.py's - read
# here, NEVER written here).
PEOPLE_FILE = os.path.join(HERE, "data", "people.yaml")
USERS_FILE = os.path.join(HERE, "users.yaml")

SLEEPER_API = "https://api.sleeper.app/v1"
SEASON = 2026

PLATFORMS = ("sleeper", "espn", "yahoo")
PLATFORM_LABELS = {"sleeper": "Sleeper", "espn": "ESPN", "yahoo": "Yahoo"}

# A league whose files have not been rewritten in this long is reported
# stale: rosters move every week, and a page built from a three-day-old
# roster is wrong in a way no exit code will tell you about.
STALE_AFTER_HOURS = 72.0

# publish.py's LEAGUE_ID_RE, mirrored so coverage() can say - BEFORE the
# owner pastes anything into users.yaml - whether an imported league id is
# one publish.py will accept.
LEAGUE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

# A person's key becomes a file name in more than one place - notably
# engine/yahoo.py's per-person token, whose PERSON_RE caps the label at 40
# characters. Catching that when the person is ADDED beats discovering it
# three steps later, halfway through a Yahoo handshake.
KEY_MAX = 40

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Sleeper roster_positions -> the tokens engine/models.FLEX_ELIGIBLE knows.
# SUPER_FLEX maps to SUPERFLEX (QB/WR/RB/TE eligible), which the engine
# treats correctly; the import printout still names it out loud so a
# superflex room is never mistaken for a 1-QB one. Unknown positions
# (IDP slots etc.) pass through unchanged - honest, visible, unmangled.
SLEEPER_SPOT_MAP = {
    "FLEX": "W/R/T",
    "SUPER_FLEX": "SUPERFLEX",
    "WRRB_FLEX": "W/R",
    "REC_FLEX": "W/T",
}


class SleeperError(RuntimeError):
    pass


class PersonError(RuntimeError):
    """A person-layer refusal, phrased for the owner to read and act on."""


# Test seams: set to a module-like object to bypass the lazy import of the
# platform modules two other agents own. None -> import for real; an
# ImportError is a rendered state, never a traceback.
#
# The contracts, as those modules actually ship them:
#   engine/espn_public.py
#       read_public_league(league_id, season=) -> facts dict, or raises
#           EspnPublicError (.kind PRIVATE / NOT_FOUND / BAD_REQUEST /
#           FEED_DOWN) whose str() already carries the remediation.
#       import_public_league(league_id, season=) -> summary
#       import_from_paste(text, league_meta) -> summary
#           league_meta REQUIRES league_id: it names the files, so the same
#           league updates in place next time.
#   engine/yahoo.py  (engine/yahoo_cli.py is the ./yahoo.sh front end for
#   the same functions - authorize / finish / leagues / import --person)
#       authorize_url(person) -> (url, state)
#       exchange_code(person, code) -> token object
#       list_leagues(person) -> [{league_key, name, teams, season, ...}]
#       import_league(person, league) -> summary
ESPN_PUBLIC = None
YAHOO_CLI = None


# --- HTTP + cache (engine/adp.py pattern) -----------------------------------

def _http_get_json(url: str):
    """One network GET. Isolated so tests can replace it with fixtures."""
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def _get_json(url: str, cache_file: str, max_age_hours: float = 1.0,
              force: bool = False):
    """Fresh cache -> network -> stale cache -> honest error.

    Sleeper league/roster data moves faster than ADP, hence the short
    default window. A payload of None (Sleeper's 'no such thing' answer)
    is returned as-is and never cached.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_file)

    if not force and os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            with open(path, "r") as fh:
                return json.load(fh)

    try:
        payload = _http_get_json(url)
        if payload is not None:
            with open(path, "w") as fh:
                json.dump(payload, fh)
        return payload
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            print("  sleeper fetch failed (%s) - using cached %s"
                  % (type(exc).__name__, cache_file))
            with open(path, "r") as fh:
                return json.load(fh)
        raise SleeperError("Could not reach Sleeper (%s) and no cache exists "
                           "for %s" % (exc, cache_file))


def _atomic_write(path: str, text: str) -> None:
    """Write via temp file + rename (engine/sources_ui.py discipline)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


# --- Sleeper: resolve / list / import ---------------------------------------

def resolve_user(username: str) -> Dict:
    """Sleeper username -> {user_id, username, display_name}.

    Raises SleeperError for an unknown username (Sleeper answers null).
    """
    username = (username or "").strip().lstrip("@")
    if not username:
        raise SleeperError("Empty Sleeper username.")
    data = _get_json("%s/user/%s" % (SLEEPER_API, username),
                     "sleeper-user-%s.json" % username.lower())
    if not data or not data.get("user_id"):
        raise SleeperError(
            "Sleeper has no user named %r. The username is the @handle in "
            "the Sleeper app (Settings -> Username), not the display name."
            % username)
    return {"user_id": str(data["user_id"]),
            "username": data.get("username") or username,
            "display_name": data.get("display_name") or username}


def list_leagues(user_id: str, season: int = SEASON) -> List[Dict]:
    """All NFL leagues for a user id in a season, as compact dicts.

    Each entry: league_id, name, teams (total_rosters), season, waiver_mode,
    waiver_budget, reception, roster_positions, raw (the full league object).
    Empty list = the account has no leagues that season (honest, not an error).
    """
    data = _get_json("%s/user/%s/leagues/nfl/%d" % (SLEEPER_API, user_id, season),
                     "sleeper-leagues-%s-%d.json" % (user_id, season))
    out = []
    for lg in data or []:
        settings = lg.get("settings") or {}
        scoring = lg.get("scoring_settings") or {}
        out.append({
            "league_id": str(lg.get("league_id")),
            "name": lg.get("name") or "Sleeper league",
            "teams": int(lg.get("total_rosters") or 0),
            "season": str(lg.get("season") or season),
            "waiver_mode": waiver_mode_from(settings.get("waiver_type")),
            "waiver_budget": settings.get("waiver_budget"),
            "reception": float(scoring.get("rec") or 0.0),
            "roster_positions": list(lg.get("roster_positions") or []),
            "raw": lg,
        })
    return out


def sleeper_lookup(username: str) -> Dict:
    """One-shot resolve + list for the Model Settings panel.

    engine/sources_ui.py prefers this over the two-step when present
    (its module docstring documents the contract). Raises SleeperError
    with the honest message on an unknown username; the panel shows it
    inline.
    """
    user = resolve_user(username)
    return {"username": user["username"],
            "user_id": user["user_id"],
            "display_name": user["display_name"],
            "leagues": list_leagues(user["user_id"], SEASON)}


def waiver_mode_from(waiver_type) -> str:
    """Sleeper settings.waiver_type -> the engine's waiver_mode token.

    2 = FAAB blind bidding -> 'faab'; 0 (rolling) and 1 (reverse standings)
    are both priority queues -> 'priority'. Verified live 2026-09-02: every
    completed waiver claim in sampled waiver_type=2 leagues carried
    settings.waiver_bid; none did in waiver_type=0 leagues.
    """
    try:
        return "faab" if int(waiver_type) == 2 else "priority"
    except (TypeError, ValueError):
        return "priority"


def map_roster_spots(roster_positions: List[str]) -> List[str]:
    """Sleeper roster_positions -> the engine's roster_spots tokens."""
    return [SLEEPER_SPOT_MAP.get((p or "").strip().upper(),
                                 (p or "").strip().upper())
            for p in roster_positions if (p or "").strip()]


def _sleeper_scoring(scoring_settings: Dict) -> Dict:
    """Map the handful of Sleeper scoring keys the engine understands.

    Only 'reception' drives engine math (LeagueConfig.ppr / scoring_label);
    the rest are carried for the human reading the yaml. Yards-per-point is
    derived from Sleeper's points-per-yard when it divides cleanly.
    """
    out = {"reception": float(scoring_settings.get("rec") or 0.0)}
    for src, dest in (("pass_td", "passing_td"), ("rush_td", "rushing_td"),
                      ("rec_td", "receiving_td"), ("pass_int", "interception"),
                      ("fum_lost", "fumble_lost")):
        val = scoring_settings.get(src)
        if val is not None:
            out[dest] = float(val)
    for src, dest in (("pass_yd", "passing_yards_per_point"),
                      ("rush_yd", "rushing_yards_per_point"),
                      ("rec_yd", "receiving_yards_per_point")):
        per_yd = scoring_settings.get(src)
        if per_yd:
            out[dest] = round(1.0 / float(per_yd), 2)
    return out


def player_name_map() -> Dict[str, str]:
    """Sleeper player id -> display name, from the cached players dump.

    Reuses engine/projections' fetch of data/cache/sleeper-players.json
    (12h window, ~5MB - the same dump the injury feed reads). Defenses are
    keyed by team abbreviation in the dump and named '<City> <Mascot>
    Defense' here so the exposure matcher can find them in rankings CSVs
    ('Seattle Seahawks Defense' ~ 'Seattle Defense', and the LA teams stay
    unambiguous).
    """
    from engine import projections
    try:
        dump = projections._fetch_json(
            projections.SLEEPER_PLAYERS_URL, "sleeper-players.json",
            {"User-Agent": UA, "Accept": "application/json"},
            max_age_hours=12.0, quiet=True)
    except RuntimeError as exc:
        raise SleeperError(
            "The Sleeper players dump (data/cache/sleeper-players.json) is "
            "missing and could not be fetched: %s" % exc)
    names = {}
    for pid, pl in dump.items():
        if not isinstance(pl, dict):
            continue
        first = (pl.get("first_name") or "").strip()
        last = (pl.get("last_name") or "").strip()
        full = ("%s %s" % (first, last)).strip()
        if not full:
            continue
        if (pl.get("position") or "").upper() in ("DEF", "DST"):
            full = "%s Defense" % full
        names[str(pid)] = full
    return names


def _find_my_roster(rosters: List[Dict], user_id: str) -> Optional[Dict]:
    user_id = str(user_id)
    for r in rosters or []:
        if str(r.get("owner_id")) == user_id:
            return r
        if user_id in [str(c) for c in (r.get("co_owners") or [])]:
            return r
    return None


def rebuild_rankings(csv_path: str, reception: float, teams: int,
                     year: int = SEASON) -> Dict:
    """The per-league data rebuild from docs/PER_LEAGUE.md, steps 1-3.

    ADP seed (overwrites the file) -> projections fill -> Chen tiers (no
    Chen feed exists for standard scoring - the seeded ADP-gap tiers stand,
    and the summary says so). Network-heavy; tests stub this function.
    Returns {seeded, filled, tiered, scoring} row counts.
    """
    from engine import adp, projections, tiers
    label = "ppr" if reception >= 1 else ("half" if reception > 0 else "std")
    ffc = {"ppr": "ppr", "half": "half-ppr", "std": "standard"}[label]
    seeded = adp.seed_rankings_csv(csv_path, scoring=ffc, teams=teams,
                                   year=year)
    filled = projections.apply_to_csv(csv_path, scoring=label)
    tiered = None
    if label != "std":
        tiered = tiers.apply_to_csv(csv_path, scoring=label)
    return {"seeded": seeded, "filled": filled, "tiered": tiered,
            "scoring": label}


def import_league(league_id: str, user_id: str, rebuild: bool = True) -> Dict:
    """Import one Sleeper league: league yaml + roster yaml + rankings CSV.

    Writes leagues/sleeper-<id>.yaml and data/rosters/sleeper-<id>.yaml,
    then runs the per-league rankings rebuild into
    data/rankings-sleeper-<id>.csv (skippable for tests via rebuild=False,
    stubbed via monkeypatching rebuild_rankings). Returns a summary dict of
    everything created. Raises SleeperError with an honest message when the
    league does not exist, the user owns no roster in it, or the players
    dump is unavailable.
    """
    league_id = str(league_id).strip()
    lg = _get_json("%s/league/%s" % (SLEEPER_API, league_id),
                   "sleeper-league-%s.json" % league_id)
    if not lg or not lg.get("league_id"):
        raise SleeperError("Sleeper league %s does not exist." % league_id)

    rosters = _get_json("%s/league/%s/rosters" % (SLEEPER_API, league_id),
                        "sleeper-rosters-%s.json" % league_id)
    mine = _find_my_roster(rosters or [], user_id)
    if mine is None:
        raise SleeperError(
            "No roster in league %r is owned by user id %s - is this one of "
            "your leagues?" % (lg.get("name"), user_id))

    names = player_name_map()   # raises honestly if the dump is unavailable
    player_ids = [str(p) for p in (mine.get("players") or [])]
    players, unresolved = [], []
    for pid in player_ids:
        if pid in names:
            players.append(names[pid])
        else:
            unresolved.append(pid)

    settings = lg.get("settings") or {}
    scoring_settings = lg.get("scoring_settings") or {}
    config_id = "sleeper-%s" % league_id
    teams = int(lg.get("total_rosters") or 0)
    roster_spots = map_roster_spots(lg.get("roster_positions") or [])
    waiver_mode = waiver_mode_from(settings.get("waiver_type"))
    rankings_rel = "data/rankings-%s.csv" % config_id

    league_doc = {
        "id": config_id,
        "name": "%s (Sleeper)" % (lg.get("name") or league_id),
        "platform": "sleeper",
        "teams": teams,
        # Draft slot is unknowable pre-draft (roster_id is not the slot);
        # null on purpose - set it from the draft room.
        "my_slot": None,
        "waiver_mode": waiver_mode,
        "roster_spots": roster_spots,
        "rounds": len(roster_spots),
        "rankings_csv": rankings_rel,
        "strategy_file": "strategies/%s.yaml" % config_id,
        "scoring": _sleeper_scoring(scoring_settings),
        "sleeper_league_id": league_id,
        "sleeper_season": str(lg.get("season") or SEASON),
    }
    if waiver_mode == "faab" and settings.get("waiver_budget") is not None:
        league_doc["waiver_budget"] = settings.get("waiver_budget")

    league_path = os.path.join(LEAGUES_DIR, "%s.yaml" % config_id)
    header = ("# Imported from Sleeper league %s (%s) by engine/connections.py.\n"
              "# my_slot is unknown until the draft order is set - fill it in\n"
              "# from the draft room before drafting.\n"
              % (league_id, lg.get("name") or "?"))
    _atomic_write(league_path, header + yaml.safe_dump(
        league_doc, default_flow_style=False, sort_keys=False))

    roster_doc = {
        "league": config_id,
        "name": lg.get("name") or config_id,
        "size": len(player_ids),
        "players": players,
    }
    roster_path = os.path.join(ROSTERS_DIR, "%s.yaml" % config_id)
    _atomic_write(roster_path, yaml.safe_dump(
        roster_doc, default_flow_style=False, sort_keys=False))

    summary = {
        "league_file": league_path,
        "roster_file": roster_path,
        "rankings_csv": os.path.join(HERE, rankings_rel),
        "config_id": config_id,
        "name": league_doc["name"],
        "teams": teams,
        "waiver_mode": waiver_mode,
        "reception": league_doc["scoring"]["reception"],
        "roster_spots": roster_spots,
        "superflex": "SUPERFLEX" in roster_spots,
        "my_roster_size": len(player_ids),
        "unresolved_player_ids": unresolved,
        "rebuild": None,
    }
    if rebuild:
        summary["rebuild"] = rebuild_rankings(
            summary["rankings_csv"], league_doc["scoring"]["reception"], teams)
    return summary


# --- status ------------------------------------------------------------------

def _sleeper_status() -> Dict:
    files = sorted(glob.glob(os.path.join(LEAGUES_DIR, "sleeper-*.yaml")))
    names = []
    for path in files:
        try:
            with open(path) as fh:
                doc = yaml.safe_load(fh) or {}
            names.append(str(doc.get("name") or
                             os.path.splitext(os.path.basename(path))[0]))
        except Exception:
            names.append(os.path.splitext(os.path.basename(path))[0])
    if names:
        return {"connected": True, "leagues": names,
                "detail": "%d league%s imported: %s"
                          % (len(names), "" if len(names) == 1 else "s",
                             ", ".join(names))}
    return {"connected": False, "leagues": [],
            "detail": "no leagues imported yet - only a Sleeper username "
                      "is needed (no password, no keys)"}


def _espn_status() -> Dict:
    if not os.path.exists(ESPN_SECRETS):
        return {"connected": False,
                "detail": "no data/espn_secrets.json - see SETUP_ESPN.md "
                          "(two minutes, done once)"}
    try:
        with open(ESPN_SECRETS) as fh:
            s = json.load(fh)
        missing = [k for k in ("league_id", "espn_s2", "swid")
                   if not s.get(k)]
    except Exception as exc:
        return {"connected": False,
                "detail": "data/espn_secrets.json is unreadable (%s)"
                          % type(exc).__name__}
    if missing:
        return {"connected": False,
                "detail": "data/espn_secrets.json is missing: %s"
                          % ", ".join(missing)}
    detail = "cookies on file for league %s" % s.get("league_id")
    try:
        if os.path.exists(ESPN_CHECK_FLAG):
            with open(ESPN_CHECK_FLAG) as fh:
                flag = json.load(fh)
            if flag.get("checked"):
                detail += " (last verified %s)" % flag["checked"]
        else:
            detail += " (unverified - run ./connect.sh or ./espn.sh check)"
    except Exception:
        pass
    return {"connected": True, "detail": detail}


def _yahoo_status() -> Dict:
    if not os.path.exists(YAHOO_SECRETS):
        return {"connected": False, "stage": "unregistered",
                "detail": "no data/yahoo_secrets.json - register the app "
                          "per SETUP_YAHOO.md. The form is five minutes; "
                          "Fantasy API access is then reviewed by Yahoo by "
                          "hand and is NOT instant, so start it now"}
    try:
        with open(YAHOO_SECRETS) as fh:
            s = json.load(fh)
        missing = [k for k in ("consumer_key", "consumer_secret")
                   if not s.get(k)]
    except Exception as exc:
        return {"connected": False, "stage": "unregistered",
                "detail": "data/yahoo_secrets.json is unreadable (%s)"
                          % type(exc).__name__}
    if missing:
        return {"connected": False, "stage": "unregistered",
                "detail": "data/yahoo_secrets.json is missing: %s"
                          % ", ".join(missing)}
    has_token = False
    try:
        if os.path.exists(YAHOO_TOKEN):
            with open(YAHOO_TOKEN) as fh:
                tok = json.load(fh)
            has_token = bool(tok.get("access_token"))
    except Exception:
        has_token = False
    if has_token:
        return {"connected": True, "stage": "handshaken",
                "detail": "app registered + OAuth token on disk"}
    return {"connected": False, "stage": "registered",
            "detail": "app registered; OAuth handshake not done yet - "
                      "./yahoo.sh check will open the browser prompt once"}


def status(person=None) -> Dict:
    """The connection board. Read-only; never raises.

    Keys "sleeper" / "espn" / "yahoo" are the OWNER's own plumbing, exactly
    as before. Key "people" is the per-person board this product actually
    runs on - it carries {connected, detail} like a platform entry (so a
    caller that walks every entry keeps working) plus "people": a list of
    coverage summaries, one per person, narrowed to `person` when given.
    """
    out = {}
    for platform, fn in (("sleeper", _sleeper_status),
                         ("espn", _espn_status),
                         ("yahoo", _yahoo_status)):
        try:
            out[platform] = fn()
        except Exception as exc:   # status must never take the caller down
            out[platform] = {"connected": False,
                             "detail": "status check failed (%s)"
                                       % type(exc).__name__}
    out["people"] = _people_board(person)
    return out


# =============================================================================
# THE PERSON LAYER
# =============================================================================
# A person is a name, an email, and leagues across platforms. The ledger is
# data/people.yaml; the publish list is users.yaml and belongs to publish.py.
# NOTHING here writes users.yaml - users_yaml_block() prints the block and
# the owner pastes it, so publish.py's format stays publish.py's business.
#
# The ledger NEVER holds a credential. Not a password, not a cookie, not an
# OAuth token, not a publish token. It holds who, where, and when.


def person_key(name) -> str:
    """A person's stable id: their name reduced to a directory-safe slug.

    Deliberately identical to publish.slug() (publish.py line ~250) so the
    two systems agree on who is who; tests/connections_test.py asserts the
    agreement against the real function.
    """
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "person"


def _today() -> str:
    return datetime.date.today().isoformat()


def _email_problem(email: str) -> Optional[str]:
    """publish.py's email rule, checked here so the owner hears it now.

    Cloudflare Access keys on the address (docs/DEPLOY.md), so a person
    without a usable one cannot be published to at all.
    """
    email = (email or "").strip()
    if not email:
        return ("an email is required - Cloudflare Access keys on it, so a "
                "person without one cannot be given a private page")
    if ("@" not in email or email.startswith("@") or email.endswith("@")
            or " " in email):
        return "%r does not look like an email address" % email
    return None


def load_people() -> List[Dict]:
    """Every person in the ledger, oldest first. Missing file -> [].

    Tolerant on purpose: a hand-edited ledger with a junk row loses that
    row and keeps the rest, because refusing to list anybody because of one
    bad line would strand the owner mid-onboarding.
    """
    if not os.path.exists(PEOPLE_FILE):
        return []
    try:
        with open(PEOPLE_FILE) as fh:
            doc = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        return []
    raw = doc.get("people") if isinstance(doc, dict) else None
    out = []
    for entry in (raw or []):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        leagues = []
        for lg in (entry.get("leagues") or []):
            if not isinstance(lg, dict):
                continue
            lid = str(lg.get("league_id") or "").strip()
            platform = str(lg.get("platform") or "").strip().lower()
            if not lid or platform not in PLATFORMS:
                continue
            leagues.append({
                "platform": platform,
                "league_id": lid,
                "name": str(lg.get("name") or lid),
                "how": str(lg.get("how") or ""),
                "handle": str(lg.get("handle") or ""),
                "added": str(lg.get("added") or ""),
            })
        skipped = [str(p).strip().lower() for p in (entry.get("skip") or [])]
        out.append({
            "key": person_key(name),
            "name": name,
            "email": str(entry.get("email") or "").strip(),
            "added": str(entry.get("added") or ""),
            "note": str(entry.get("note") or ""),
            "leagues": leagues,
            "skip": [p for p in skipped if p in PLATFORMS],
        })
    return out


def save_people(people: List[Dict]) -> str:
    """Write the ledger atomically. Returns the path written.

    The header is the file's own documentation - the owner will open this
    in an editor eventually, and it must say what it is and what it must
    never hold.
    """
    doc = {"version": 1, "people": [
        {"name": p["name"], "email": p.get("email", ""),
         "added": p.get("added") or _today(),
         "note": p.get("note", ""),
         "skip": list(p.get("skip") or []),
         "leagues": [dict(lg) for lg in (p.get("leagues") or [])]}
        for p in people]}
    header = (
        "# WAR ROOM - THE ONBOARDING LEDGER\n"
        "#\n"
        "# Who is being onboarded, and which of their leagues are connected.\n"
        "# Written by engine/connections.py (the Leagues tab writes it too).\n"
        "#\n"
        "# THIS IS NOT THE PUBLISH LIST. publish.py reads users.yaml; a\n"
        "# person only gets pages once they have an entry THERE, with a\n"
        "# token. `python -m engine.connections people` prints the block to\n"
        "# paste, and names anyone who is connected but not yet published.\n"
        "#\n"
        "# THIS FILE MUST NEVER HOLD A CREDENTIAL - no password, no ESPN\n"
        "# cookie, no Yahoo token, no publish token. Who, where, and when,\n"
        "# and nothing else. If you find a secret in here, something is\n"
        "# broken: delete it and say so.\n")
    _atomic_write(PEOPLE_FILE, header + yaml.safe_dump(
        doc, default_flow_style=False, sort_keys=False, allow_unicode=True))
    return PEOPLE_FILE


def get_person(who) -> Optional[Dict]:
    """One person by key, name (case-insensitive) or email - or None."""
    if isinstance(who, dict):
        who = who.get("key") or who.get("name") or ""
    needle = str(who or "").strip().lower()
    if not needle:
        return None
    people = load_people()
    for p in people:
        if p["key"] == needle:
            return p
    for p in people:
        if p["name"].strip().lower() == needle:
            return p
        if p["email"] and p["email"].strip().lower() == needle:
            return p
    key = person_key(needle)
    for p in people:
        if p["key"] == key:
            return p
    return None


def require_person(who) -> Dict:
    """get_person, or PersonError naming who is actually on file."""
    p = get_person(who)
    if p is not None:
        return p
    known = ", ".join(x["name"] for x in load_people()) or "nobody yet"
    raise PersonError("No person named %r is being onboarded (on file: %s). "
                      "Add them first." % (who, known))


def list_people() -> List[Dict]:
    """Every person in the ledger. Alias of load_people, named for callers."""
    return load_people()


def add_person(name: str, email: str, note: str = "") -> Dict:
    """Put a person in the ledger. Idempotent on the key; returns the record.

    Refuses an unusable email (Cloudflare Access keys on it) and a second
    person on the same email or the same directory-safe key, because
    publish.py refuses both and hearing it here is cheaper than hearing it
    on publish night.
    """
    name = str(name or "").strip()
    if not name:
        raise PersonError("A person needs a name - it is what --person and "
                          "their directory are keyed on.")
    problem = _email_problem(email)
    if problem:
        raise PersonError("Cannot add %s: %s" % (name, problem))
    email = email.strip()
    key = person_key(name)
    if len(key) > KEY_MAX:
        raise PersonError(
            "%r reduces to a %d-character key, and a person's key becomes a "
            "file name (Yahoo's per-person token caps it at %d). Use a "
            "shorter name - a first name and an initial is plenty."
            % (name, len(key), KEY_MAX))
    people = load_people()
    for p in people:
        if p["key"] != key and p["email"].strip().lower() == email.lower():
            raise PersonError(
                "%s already uses %s. Two people on one email cannot both be "
                "published - publish.py refuses it." % (p["name"], email))
    for p in people:
        if p["key"] == key:
            p["name"], p["email"] = name, email
            if note:
                p["note"] = note
            save_people(people)
            return dict(p)
    record = {"key": key, "name": name, "email": email, "added": _today(),
              "note": note, "leagues": [], "skip": []}
    people.append(record)
    save_people(people)
    return dict(record)


def forget_person(who) -> Dict:
    """Drop a person from the LEDGER ONLY.

    Their imported league files stay exactly where they are (other people
    may share the league, and deleting someone's data on a typo is not a
    thing this should do). Removing their published pages is publish.py's
    --prune, and the return value says so.
    """
    p = require_person(who)
    people = [x for x in load_people() if x["key"] != p["key"]]
    save_people(people)
    return {"person": p["name"], "key": p["key"],
            "removed_leagues": [lg["league_id"] for lg in p["leagues"]],
            "note": ("league files were NOT deleted. To stop publishing to "
                     "them, remove their entry from users.yaml and run "
                     "./publish.sh --prune.")}


def skip_platform(who, platform: str, on: bool = True) -> Dict:
    """Mark a platform as one this person does not play on (or unmark it).

    The difference between "we have not done Yahoo yet" and "they have no
    Yahoo league" is the difference between a to-do and a finished
    onboarding, so the ledger records it rather than nagging forever.
    """
    platform = str(platform or "").strip().lower()
    if platform not in PLATFORMS:
        raise PersonError("Unknown platform %r - one of: %s"
                          % (platform, ", ".join(PLATFORMS)))
    p = require_person(who)
    people = load_people()
    for row in people:
        if row["key"] != p["key"]:
            continue
        skip = [s for s in row["skip"] if s != platform]
        if on:
            if any(lg["platform"] == platform for lg in row["leagues"]):
                raise PersonError(
                    "%s already has a %s league connected - forget that "
                    "league first if it was a mistake."
                    % (row["name"], PLATFORM_LABELS[platform]))
            skip.append(platform)
        row["skip"] = skip
        save_people(people)
        return dict(row)
    raise PersonError("%s vanished from the ledger mid-write." % p["name"])


def record_league_for(who, platform: str, league_id: str, name: str = "",
                      how: str = "", handle: str = "") -> Dict:
    """Record an ALREADY-IMPORTED league against a person (ledger only).

    Separate from add_league_for on purpose: this is the bookkeeping half,
    so a league imported by hand or by another tool can still be attached
    to the person who plays in it. It writes no league files and touches no
    network.
    """
    platform = str(platform or "").strip().lower()
    if platform not in PLATFORMS:
        raise PersonError("Unknown platform %r - one of: %s"
                          % (platform, ", ".join(PLATFORMS)))
    league_id = str(league_id or "").strip()
    if not league_id:
        raise PersonError("A league needs an id.")
    p = require_person(who)
    people = load_people()
    for row in people:
        if row["key"] != p["key"]:
            continue
        row["skip"] = [s for s in row["skip"] if s != platform]
        for lg in row["leagues"]:
            if lg["league_id"] == league_id:
                lg.update({"platform": platform, "name": name or lg["name"],
                           "how": how or lg["how"],
                           "handle": handle or lg["handle"]})
                save_people(people)
                return dict(lg)
        entry = {"platform": platform, "league_id": league_id,
                 "name": name or league_id, "how": how, "handle": handle,
                 "added": _today()}
        row["leagues"].append(entry)
        save_people(people)
        return dict(entry)
    raise PersonError("%s vanished from the ledger mid-write." % p["name"])


def forget_league_for(who, league_id: str) -> Dict:
    """Drop one league from a person's LEDGER ROW. Files are left alone."""
    p = require_person(who)
    league_id = str(league_id or "").strip()
    people = load_people()
    for row in people:
        if row["key"] != p["key"]:
            continue
        keep = [lg for lg in row["leagues"] if lg["league_id"] != league_id]
        if len(keep) == len(row["leagues"]):
            raise PersonError("%s has no league %r on file."
                              % (row["name"], league_id))
        row["leagues"] = keep
        save_people(people)
        return {"person": row["name"], "forgot": league_id,
                "note": "the league files were not deleted"}
    raise PersonError("%s vanished from the ledger mid-write." % p["name"])


# --- the other agents' modules, called through documented seams --------------
# engine/espn_public.py and engine/yahoo_cli.py are owned elsewhere and land
# separately. Absence is a rendered state with an honest next step, never a
# traceback, and the adapters tolerate a person= keyword the callee may not
# take yet - the CLI contract is `--person`, so we offer it and fall back.

def _espn_public():
    if ESPN_PUBLIC is not None:
        return ESPN_PUBLIC
    try:
        from engine import espn_public as mod   # noqa: PLC0415 - lazy
        return mod
    except Exception:   # noqa: BLE001 - absence is a state
        return None


def _yahoo_cli():
    """The Yahoo module. engine/yahoo.py holds the functions; yahoo_cli is
    the ./yahoo.sh front end for exactly the same four verbs."""
    if YAHOO_CLI is not None:
        return YAHOO_CLI
    try:
        from engine import yahoo as mod         # noqa: PLC0415 - lazy
        return mod
    except Exception:   # noqa: BLE001 - absence is a state
        return None


def _need(mod, module_name: str, what: str):
    if mod is None:
        raise PersonError(
            "engine/%s.py is not installed yet, so %s cannot run from here. "
            "Everything else on this page still works." % (module_name, what))
    return mod


def _call(mod, names, *args, **kwargs):
    """Call the first callable of `names` on `mod`, honestly if absent.

    The name list is the tolerance: those modules are owned elsewhere and a
    renamed function should be a clear sentence here, not an AttributeError
    somewhere downstream.
    """
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            return fn(*args, **kwargs)
    raise PersonError(
        "engine/%s.py offers none of %s - the platform module and this one "
        "disagree about the contract; nothing was changed."
        % (getattr(mod, "__name__", "?").split(".")[-1], ", ".join(names)))


# Every file an import may legitimately report having created. A path under
# any other key is not blessed and not shown - the panel re-guards these
# against its own allowlist anyway (engine/sources_ui.guard_scoped_write).
CREATED_KEYS = ("league_file", "league_yaml", "roster_file", "rankings_csv",
                "store_file")


def _summary_row(summary, platform: str, fallback_id: str,
                 fallback_name: str = "") -> Dict:
    """An import summary (any of the three modules') -> a ledger row.

    engine/connections.import_league's shape is the model, and both other
    modules deliberately mirror it: config_id, name, and the created paths
    at the top level.
    """
    summary = summary if isinstance(summary, dict) else {}
    lid = str(summary.get("config_id") or summary.get("league_id")
              or fallback_id or "").strip()
    name = str(summary.get("name") or fallback_name or lid)
    created = [str(summary[k]) for k in CREATED_KEYS if summary.get(k)]
    return {"league_id": lid, "name": name, "created": created,
            "summary": summary}


def add_league_for(who, platform: str, **kw) -> Dict:
    """Connect ONE league for ONE person on ONE platform, then record it.

    The whole point of the module: the three platforms have three different
    shapes, and this is where that difference stops mattering to the caller.

        sleeper: username=<their @handle>, league_id=<from list_leagues>
                 Public read-only API. No auth, no keys, nothing to send.
        yahoo:   league_key=<from yahoo_leagues(person)>
                 Only after the person approved the consent link and you ran
                 yahoo_finish(person, code) with what they read back.
        espn:    league_id=<their league id>   (publicly-readable league)
              or paste=<the roster text they sent you>, league_id optional
                 We never ask a friend for their ESPN cookies.

    Returns {"person", "platform", "league_id", "name", "created", "summary"}.
    Raises PersonError with an actionable sentence on anything missing.
    """
    platform = str(platform or "").strip().lower()
    p = require_person(who)
    if platform == "sleeper":
        row = _add_sleeper_league(p, **kw)
    elif platform == "yahoo":
        row = _add_yahoo_league(p, **kw)
    elif platform == "espn":
        row = _add_espn_league(p, **kw)
    else:
        raise PersonError("Unknown platform %r - one of: %s"
                          % (platform, ", ".join(PLATFORMS)))
    record_league_for(p["key"], platform, row["league_id"], row["name"],
                      how=row.get("how", ""), handle=row.get("handle", ""))
    return {"person": p["name"], "key": p["key"], "platform": platform,
            "league_id": row["league_id"], "name": row["name"],
            "how": row.get("how", ""), "created": row["created"],
            "summary": row["summary"]}


def _add_sleeper_league(p: Dict, username: str = "", league_id: str = "",
                        user_id: str = "", rebuild: bool = True) -> Dict:
    league_id = str(league_id or "").strip()
    if not league_id:
        raise PersonError(
            "Which Sleeper league? Look %s up by username first "
            "(sleeper_lookup) and pass one of the league ids it lists."
            % p["name"])
    username = str(username or "").strip().lstrip("@")
    if not user_id:
        if not username:
            raise PersonError(
                "Sleeper needs %s's username - the @handle in their app "
                "under Settings -> Username. That is the whole ask: no "
                "password, no cookie." % p["name"])
        user_id = resolve_user(username)["user_id"]
    summary = import_league(league_id, user_id, rebuild=rebuild)
    row = _summary_row(summary, "sleeper", "sleeper-%s" % league_id)
    row["how"] = "sleeper username"
    row["handle"] = username
    return row


def _add_yahoo_league(p: Dict, league_key: str = "", league_id: str = "",
                      **kw) -> Dict:
    key = str(league_key or league_id or "").strip()
    if not key:
        raise PersonError(
            "Which Yahoo league? Run yahoo_leagues(%r) after %s has approved "
            "the consent link, and pass one of the league keys it lists."
            % (p["key"], p["name"]))
    mod = _need(_yahoo_cli(), "yahoo", "a Yahoo import")
    # person first, exactly as engine/yahoo.import_league declares it: one
    # app, many people, each with their own token file.
    summary = _call(mod, ("import_league", "import_for_person"),
                    p["key"], key, **kw)
    row = _summary_row(summary, "yahoo", "yahoo-%s" % key.split(".")[-1])
    row["how"] = "yahoo oauth consent"
    return row


# What espn_public's two importers actually accept past the arguments this
# function fills in itself. Anything else is a caller mistake, and almost
# always the same one: a league fact (teams, reception, waiver_mode,
# roster_spots) passed as a top-level keyword instead of inside meta=.
_ESPN_PASSTHROUGH = {"rebuild", "overwrite", "quiet"}
_ESPN_PUBLIC_ONLY = {"force"}
# The keys import_from_paste reads out of league_meta - named back to the
# caller so the sentence says where the value goes, not just that it is wrong.
_ESPN_META_KEYS = ("season", "name", "teams", "reception", "waiver_mode",
                   "waiver_budget", "roster_spots", "my_team")


def _check_espn_kwargs(kw: Dict, is_paste: bool, p: Dict) -> None:
    """Refuse unknown keywords in a sentence, not a TypeError.

    add_league_for(..., platform="espn", **kw) forwards whatever it is
    given straight through. Without this, `teases=12` or the far likelier
    `teams=12` reached import_from_paste as an unexpected keyword and the
    panel showed a bare TypeError - a Python noun, at the moment someone
    is trying to connect a friend's league, saying nothing about the meta
    dict that is where league facts actually belong.
    """
    allowed = set(_ESPN_PASSTHROUGH)
    if not is_paste:
        allowed |= _ESPN_PUBLIC_ONLY
    unknown = sorted(k for k in kw if k not in allowed)
    if not unknown:
        return
    misplaced = [k for k in unknown if k in _ESPN_META_KEYS]
    if misplaced:
        one = len(misplaced) == 1
        raise PersonError(
            "%s %s, not %s - %s inside meta={...}, the dict describing "
            "%s's league. For example: add_league_for(%r, 'espn', "
            "league_id='...', paste=text, meta={%s}). Nothing was changed."
            % (", ".join(misplaced),
               "is a league fact" if one else "are league facts",
               "a connection option" if one else "connection options",
               "it goes" if one else "they go",
               p["name"], p.get("name") or p.get("key"),
               ", ".join("%r: ..." % k for k in misplaced)))
    raise PersonError(
        "An ESPN import does not take %s. It takes league_id=, paste=, "
        "team=, season=, and meta={...} for the league's own facts "
        "(%s). Nothing was changed."
        % (", ".join("%s=" % k for k in unknown),
           ", ".join(_ESPN_META_KEYS)))


def _add_espn_league(p: Dict, league_id: str = "", paste: str = "",
                     team=None, season: Optional[int] = None,
                     meta: Optional[Dict] = None, **kw) -> Dict:
    mod = _need(_espn_public(), "espn_public", "an ESPN import")
    league_id = str(league_id or "").strip()
    text = paste if isinstance(paste, str) else ""
    _check_espn_kwargs(kw, bool(text.strip()), p)
    if text.strip():
        if not league_id:
            raise PersonError(
                "A pasted ESPN roster still needs %s's league id - the "
                "number after leagueId= in their league URL. It names the "
                "files, so the same league updates in place next time "
                "instead of piling up copies." % p["name"])
        league_meta = dict(meta or {})
        league_meta.setdefault("league_id", league_id)
        if season:
            league_meta.setdefault("season", season)
        if team not in (None, ""):
            league_meta.setdefault("my_team", team)
        summary = _call(mod, ("import_from_paste",), text, league_meta, **kw)
        row = _summary_row(summary, "espn", "espn-%s" % league_id)
        row["how"] = "espn roster paste"
        return row
    if not league_id:
        raise PersonError(
            "ESPN needs either %s's league id (from their league URL, with "
            "the league set to viewable by anyone) or the roster text they "
            "pasted you. We do not ask anyone for their ESPN cookies."
            % p["name"])
    # Which team is theirs is never guessed - espn_public raises NO_TEAM
    # listing every team, and that list is what the panel shows.
    summary = _call(mod, ("import_public_league",), league_id,
                    season=season or SEASON, my_team_id=team, **kw)
    row = _summary_row(summary, "espn", "espn-%s" % league_id)
    row["how"] = "espn public league"
    return row


def espn_public_check(league_id: str, season: Optional[int] = None) -> Dict:
    """Is this ESPN league publicly readable? An honest yes or no.

    {"readable", "league_id", "name", "teams", "kind", "detail", "roster"}
    - on a no, `detail` is what to ask the friend to change, not a status
    code; on a yes, `roster` lists the teams so the owner can ask which
    one is theirs. Nothing here ever guesses that.
    """
    league_id = str(league_id or "").strip()
    if not league_id.isdigit():
        return {"readable": False, "league_id": league_id, "name": "",
                "teams": None,
                "detail": "that is not an ESPN league id - it is the number "
                          "after leagueId= in their league's URL"}
    mod = _espn_public()
    if mod is None:
        return {"readable": False, "league_id": league_id, "name": "",
                "teams": None,
                "detail": "engine/espn_public.py is not installed yet, so a "
                          "public read cannot be tried from here - the paste "
                          "route below works regardless"}
    try:
        res = _call(mod, ("read_public_league",), league_id,
                    season=season or SEASON)
    except Exception as exc:   # noqa: BLE001 - the reason IS the product
        # espn_public raises EspnPublicError, whose str() is already the
        # message plus what to do about it - pass it through unmangled and
        # keep .kind for anyone who wants to branch on it.
        return {"readable": False, "league_id": league_id, "name": "",
                "teams": None, "kind": str(getattr(exc, "kind", "") or ""),
                "roster": [],
                "detail": "%s" % (exc if str(exc) else type(exc).__name__)}
    res = res if isinstance(res, dict) else {}
    readable = bool(res.get("readable", res.get("ok", bool(res.get("name")))))
    detail = str(res.get("detail") or res.get("reason") or res.get("error")
                 or "")
    if not detail:
        detail = ("readable - nothing else to ask for" if readable else
                  "ESPN would not show that league to a logged-out reader. "
                  "Ask them to open League Settings and set visibility to "
                  "viewable by anyone, or to paste their roster instead.")
    roster = [{"team_id": str(r.get("team_id") or ""),
               "name": str(r.get("name") or "?")}
              for r in (res.get("rosters") or []) if isinstance(r, dict)]
    return {"readable": readable, "league_id": league_id,
            "name": str(res.get("name") or ""),
            "teams": res.get("teams") or res.get("size"),
            "kind": str(res.get("kind") or ""), "roster": roster,
            "detail": detail}


def yahoo_consent_link(who) -> Dict:
    """The link to SEND the person, and what to ask them to send back.

    The one credential-safe Yahoo route: they approve in Yahoo's own UI and
    read back a short code. We never see their password, and the read-only
    scope means the app cannot change their league even if it wanted to.
    """
    p = require_person(who)
    mod = _need(_yahoo_cli(), "yahoo", "a Yahoo consent link")
    # engine/yahoo.authorize_url(person) -> (url, state). The state is
    # Yahoo's CSRF pairing and belongs to that module's pending file; it
    # is deliberately not returned, printed or recorded here.
    res = _call(mod, ("authorize_url", "authorize", "consent_link"),
                p["key"])
    if isinstance(res, tuple):
        res = {"url": res[0] if res else ""}
    res = res if isinstance(res, dict) else {"url": str(res or "")}
    url = str(res.get("url") or res.get("consent_url") or "")
    if not url:
        raise PersonError(
            "engine/yahoo_cli.py returned no consent URL, so there is "
            "nothing to send %s. Nothing was changed." % p["name"])
    return {"person": p["name"], "key": p["key"], "url": url,
            "expires": str(res.get("expires") or ""),
            "ask": ("Open this link, sign in as yourself, press Agree, and "
                    "send me the short code Yahoo shows you. It is read-only "
                    "- I can see the league, I cannot change your team.")}


def yahoo_finish(who, code: str) -> Dict:
    """Exchange the code the person read back. Returns their leagues.

    The code is used and dropped: it is never written to the ledger, never
    logged, and never returned. Whatever token comes out of it belongs to
    engine/yahoo_cli.py's own storage, not to this module.
    """
    p = require_person(who)
    code = str(code or "").strip()
    if not code:
        raise PersonError("Paste the short code %s read back from Yahoo."
                          % p["name"])
    mod = _need(_yahoo_cli(), "yahoo", "the Yahoo handshake")
    _call(mod, ("exchange_code", "finish", "finish_authorize"),
          p["key"], code)
    return {"person": p["name"], "key": p["key"], "connected": True,
            "leagues": yahoo_leagues(p["key"])}


def yahoo_leagues(who) -> List[Dict]:
    """That person's Yahoo leagues, as {league_key, name, teams, season}."""
    p = require_person(who)
    mod = _need(_yahoo_cli(), "yahoo", "a Yahoo league list")
    res = _call(mod, ("list_leagues", "leagues"), p["key"])
    if isinstance(res, dict):
        res = res.get("leagues") or []
    out = []
    for lg in (res or []):
        if not isinstance(lg, dict):
            out.append({"league_key": str(lg), "name": str(lg),
                        "teams": None, "season": ""})
            continue
        out.append({
            "league_key": str(lg.get("league_key") or lg.get("league_id")
                              or lg.get("key") or ""),
            "name": str(lg.get("name") or "Yahoo league"),
            "teams": lg.get("teams") or lg.get("num_teams"),
            "season": str(lg.get("season") or ""),
        })
    return out


# --- coverage ----------------------------------------------------------------

def league_files(league_id: str) -> Dict:
    """Where one league's files are and when they were last written.

    {"league", "roster", "rankings", "exists", "refreshed", "age_hours"} -
    refreshed is the NEWEST mtime across the files that exist, because that
    is the moment the person's pages stopped being made-up.
    """
    lid = str(league_id or "").strip()
    paths = {
        "league": os.path.join(LEAGUES_DIR, "%s.yaml" % lid),
        "roster": os.path.join(ROSTERS_DIR, "%s.yaml" % lid),
        "rankings": os.path.join(DATA_DIR, "rankings-%s.csv" % lid),
    }
    times = []
    present = {}
    for label, path in paths.items():
        there = os.path.exists(path)
        present[label] = there
        if there:
            try:
                times.append(os.path.getmtime(path))
            except OSError:
                pass
    newest = max(times) if times else None
    return {
        "paths": paths, "present": present,
        "exists": present["league"],
        "refreshed": (datetime.datetime.fromtimestamp(newest)
                      .strftime("%Y-%m-%d %H:%M") if newest else ""),
        "age_hours": ((time.time() - newest) / 3600.0
                      if newest is not None else None),
    }


def _age_phrase(age_hours: Optional[float]) -> str:
    if age_hours is None:
        return "never"
    if age_hours < 1:
        return "just now"
    if age_hours < 24:
        return "%d hour%s ago" % (int(age_hours),
                                  "" if int(age_hours) == 1 else "s")
    days = int(age_hours // 24)
    return "%d day%s ago" % (days, "" if days == 1 else "s")


def _users_entries() -> List[Dict]:
    """users.yaml as {name, email, leagues, has_token} - READ ONLY.

    Never raises (the shipped template is deliberately unpublishable, and
    that must not break a status board) and NEVER carries the token value:
    only whether one is set. publish.py owns this file; we look.
    """
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE) as fh:
            doc = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        return []
    out = []
    for entry in ((doc.get("people") if isinstance(doc, dict) else None) or []):
        if not isinstance(entry, dict):
            continue
        token = entry.get("token")
        out.append({
            "name": str(entry.get("name") or "").strip(),
            "email": str(entry.get("email") or "").strip(),
            "leagues": [str(x).strip() for x in (entry.get("leagues") or [])],
            "has_token": bool(isinstance(token, str) and token.strip()),
        })
    return out


def _users_entry_for(person: Dict) -> Optional[Dict]:
    """This person's users.yaml entry, matched on email then name."""
    email = (person.get("email") or "").strip().lower()
    key = person["key"]
    for e in _users_entries():
        if email and e["email"].strip().lower() == email:
            return e
    for e in _users_entries():
        if person_key(e["name"]) == key:
            return e
    return None


def users_yaml_block(who) -> str:
    """The users.yaml block for this person, ready to paste. NOT written.

    publish.py owns users.yaml's format, so this module proposes and the
    owner disposes. The token line is a PLACEHOLDER naming the command that
    generates a real one - we neither invent a token nor print one into a
    page: a token is a secret URL, and this module does not handle secrets.
    """
    p = require_person(who)
    lids = [lg["league_id"] for lg in p["leagues"]]
    if not lids:
        return ("# %s has no connected league yet, and publish.py refuses a\n"
                "# person with an empty `leagues:` list. Connect one first.\n"
                % p["name"])
    lines = ["  - name: %s" % p["name"],
             "    email: %s" % (p["email"] or "REQUIRED-see-docs/DEPLOY.md"),
             "    # generate with: .venv/bin/python publish.py new-token",
             "    token: PASTE-A-FRESHLY-GENERATED-TOKEN-HERE",
             "    leagues:"]
    lines += ["      - %s" % lid for lid in lids]
    return "\n".join(lines) + "\n"


def coverage(who) -> Dict:
    """What is connected for this person, what is missing, what is stale.

    Everything a human needs to answer "is this person done?", each item
    carrying its own next step in a sentence the owner can act on or paste
    into a message. Never raises except on an unknown person.
    """
    p = require_person(who)
    connected, stale, broken = [], [], []
    for lg in p["leagues"]:
        files = league_files(lg["league_id"])
        row = {"platform": lg["platform"], "league_id": lg["league_id"],
               "name": lg["name"], "how": lg["how"], "added": lg["added"],
               "refreshed": files["refreshed"],
               "age_hours": files["age_hours"],
               "age": _age_phrase(files["age_hours"]),
               "publishable_id": bool(LEAGUE_ID_RE.match(lg["league_id"]))}
        if not files["exists"]:
            row["state"] = "broken"
            row["next_step"] = (
                "%s is on %s's list but leagues/%s.yaml is gone - re-import "
                "it, or forget_league_for(%r, %r)."
                % (lg["name"], p["name"], lg["league_id"], p["key"],
                   lg["league_id"]))
            broken.append(row)
        elif (files["age_hours"] is not None
                and files["age_hours"] > STALE_AFTER_HOURS):
            row["state"] = "stale"
            row["next_step"] = (
                "%s last refreshed %s - re-import it before you publish, or "
                "%s reads a stale roster."
                % (lg["name"], row["age"], p["name"]))
            stale.append(row)
            connected.append(row)
        else:
            row["state"] = "ok"
            row["next_step"] = ""
            connected.append(row)

    platforms, missing = {}, []
    for platform in PLATFORMS:
        mine = [r for r in connected if r["platform"] == platform]
        gone = [r for r in broken if r["platform"] == platform]
        if platform in p["skip"]:
            platforms[platform] = {
                "state": "not used", "connected": False, "leagues": [],
                "detail": "%s does not play on %s" % (p["name"],
                                                      PLATFORM_LABELS[platform]),
                "next_step": ""}
            continue
        if mine:
            worst = "stale" if any(r["state"] == "stale" for r in mine) else "ok"
            platforms[platform] = {
                "state": worst, "connected": True,
                "leagues": [r["league_id"] for r in mine],
                "detail": "%d league%s: %s" % (
                    len(mine), "" if len(mine) == 1 else "s",
                    ", ".join(r["name"] for r in mine)),
                "next_step": next((r["next_step"] for r in mine
                                   if r["next_step"]), "")}
            continue
        step = _first_step(platform, p["name"])
        platforms[platform] = {
            "state": "broken" if gone else "missing", "connected": False,
            "leagues": [],
            "detail": (gone[0]["next_step"] if gone else
                       "no %s league yet" % PLATFORM_LABELS[platform]),
            "next_step": gone[0]["next_step"] if gone else step}
        missing.append({"platform": platform, "next_step": step,
                        "detail": "no %s league connected for %s"
                                  % (PLATFORM_LABELS[platform], p["name"])})

    entry = _users_entry_for(p)
    unpublishable = [r["league_id"] for r in connected
                     if not r["publishable_id"]]
    steps = []
    for r in broken:
        steps.append(r["next_step"])
    for r in stale:
        steps.append(r["next_step"])
    for m in missing:
        steps.append(m["next_step"])
    if connected and entry is None:
        steps.append(
            "%s has %d league%s connected but no entry in users.yaml, so "
            "publish.py will not build their pages. Paste the block from "
            "users_yaml_block(%r) into users.yaml, generate a token with "
            "`.venv/bin/python publish.py new-token`, then ./publish.sh "
            "--person %r."
            % (p["name"], len(connected), "" if len(connected) == 1 else "s",
               p["key"], p["name"]))
    elif entry is not None:
        extra = [r["league_id"] for r in connected
                 if r["league_id"] not in entry["leagues"]]
        if extra:
            steps.append(
                "%s's users.yaml entry does not list %s - add %s there or "
                "their pages will not include %s."
                % (p["name"], ", ".join(extra),
                   "them" if len(extra) > 1 else "it",
                   "those leagues" if len(extra) > 1 else "that league"))
        if not entry["has_token"]:
            steps.append(
                "%s's users.yaml entry has no token - generate one with "
                "`.venv/bin/python publish.py new-token`; publish.py refuses "
                "the whole run without it." % p["name"])
    if unpublishable:
        steps.append(
            "league id %s cannot be published - publish.py requires "
            "lowercase a-z 0-9 . _ - and at least 3 characters."
            % ", ".join(unpublishable))
    if not p["leagues"]:
        steps.insert(0, "%s has no league connected yet - start with "
                        "whichever platform they actually play on. Each ask "
                        "below is one message." % p["name"])

    ready = bool(connected) and not broken and not unpublishable
    if not connected:
        detail = "nothing connected yet"
    else:
        bits = ["%d league%s connected" % (len(connected),
                                           "" if len(connected) == 1 else "s")]
        if stale:
            bits.append("%d stale" % len(stale))
        if broken:
            bits.append("%d missing its files" % len(broken))
        if entry is None:
            bits.append("not in users.yaml yet")
        detail = ", ".join(bits)
    return {
        "person": p["name"], "key": p["key"], "email": p["email"],
        "added": p["added"], "note": p["note"],
        "connected": connected, "missing": missing, "stale": stale,
        "broken": broken, "platforms": platforms, "skip": list(p["skip"]),
        "in_users_yaml": entry is not None,
        "published_leagues": list(entry["leagues"]) if entry else [],
        "has_publish_token": bool(entry and entry["has_token"]),
        "ready_to_publish": ready and entry is not None
                            and bool(entry["has_token"]),
        "detail": detail,
        "next_steps": steps,
        "next_step": steps[0] if steps else
                     "nothing outstanding - %s is fully connected." % p["name"],
    }


def _first_step(platform: str, name: str) -> str:
    """The ONE thing to ask this person for, on this platform, in a sentence
    the owner can paste into a message. docs/ONBOARD.md is the long form."""
    if platform == "sleeper":
        return ("Ask %s for their Sleeper username - the @handle under "
                "Settings -> Username in the app. That is the entire ask: "
                "no password, no cookie, nothing to install." % name)
    if platform == "yahoo":
        return ("Generate %s's Yahoo consent link, send it, and paste back "
                "the short code they read to you. They approve inside "
                "Yahoo; read-only, so nothing can change their team." % name)
    return ("Ask %s for their ESPN league id (the number after leagueId= in "
            "their league URL) and to set the league to viewable by anyone "
            "in League Settings. If they would rather not, ask them to copy "
            "their roster page and paste it to you instead - never ask them "
            "for their ESPN cookies." % name)


def people_status(person=None) -> List[Dict]:
    """coverage() for everyone (or one person), safe for a status board.

    Never raises: an unreadable ledger is an empty list and one unhappy
    person is one unhappy row.
    """
    try:
        people = load_people()
    except Exception:   # noqa: BLE001 - a board, never a traceback
        return []
    if person is not None:
        want = get_person(person)
        people = [want] if want else []
    out = []
    for p in people:
        try:
            out.append(coverage(p["key"]))
        except Exception as exc:   # noqa: BLE001 - one bad row, not the board
            out.append({"person": p.get("name", "?"),
                        "key": p.get("key", "?"),
                        "email": p.get("email", ""),
                        "connected": [], "missing": [], "stale": [],
                        "broken": [], "platforms": {}, "skip": [],
                        "in_users_yaml": False, "ready_to_publish": False,
                        "detail": "coverage failed (%s)" % type(exc).__name__,
                        "next_steps": [], "next_step": "coverage failed"})
    return out


def _people_board(person=None) -> Dict:
    """The "people" entry of status(): platform-shaped, plus the roster.

    Shaped like a platform entry (connected + detail) on purpose, so a
    caller that walks every entry of status() keeps working.
    """
    try:
        rows = people_status(person)
    except Exception as exc:   # noqa: BLE001 - never takes the board down
        return {"connected": False, "people": [],
                "detail": "people board failed (%s)" % type(exc).__name__}
    if not rows:
        return {"connected": False, "people": [],
                "detail": "no people onboarded yet - add one in the Leagues "
                          "tab, or connections.add_person(name, email)"}
    ready = [r for r in rows if r.get("ready_to_publish")]
    waiting = [r for r in rows if not r.get("ready_to_publish")]
    detail = "%d person%s onboarded, %d ready to publish" % (
        len(rows), "" if len(rows) == 1 else "s", len(ready))
    if waiting:
        detail += " - waiting on %s" % ", ".join(r["person"] for r in waiting)
    return {"connected": bool(ready), "people": rows, "detail": detail}


# --- interactive wizard ------------------------------------------------------

def _print_status_board() -> None:
    st = status()
    print("\n  PLATFORM CONNECTIONS (yours)")
    for platform in PLATFORMS:
        s = st[platform]
        mark = "[ok]" if s["connected"] else "[--]"
        print("   %s %-8s %s" % (mark, platform, s["detail"]))
    print("\n  PEOPLE  %s" % st["people"]["detail"])


def _print_people_board(person=None) -> None:
    """The per-person board: who is connected where, and the ONE next step."""
    rows = people_status(person)
    if not rows:
        print("\n  Nobody is being onboarded yet.")
        print("  Add someone:  python -c \"from engine.connections import "
              "add_person; add_person('Their Name', 'their@email')\"")
        print("  The script for onboarding one friend: docs/ONBOARD.md")
        return
    for r in rows:
        print("\n  %s  <%s>" % (r["person"], r["email"] or "no email"))
        print("   %s" % r["detail"])
        for platform in PLATFORMS:
            pl = (r.get("platforms") or {}).get(platform) or {}
            state = pl.get("state", "missing")
            mark = {"ok": "[ok]", "stale": "[~~]", "not used": "[--]"}.get(
                state, "[  ]")
            print("   %s %-8s %s" % (mark, platform, pl.get("detail") or ""))
        for step in r.get("next_steps") or []:
            print("    -> %s" % step)
        if not r.get("next_steps"):
            print("    -> nothing outstanding.")


def _sleeper_wizard() -> int:
    try:
        username = input("\n  Sleeper username (the @handle): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    try:
        user = resolve_user(username)
    except SleeperError as exc:
        print("  %s" % exc)
        return 1
    print("  Found %s (user id %s)" % (user["display_name"], user["user_id"]))

    try:
        leagues = list_leagues(user["user_id"], SEASON)
    except SleeperError as exc:
        print("  %s" % exc)
        return 1
    if not leagues:
        print("  No NFL leagues for this account in %d. If your league is "
              "from an older season,\n  import it with: python -c \"from "
              "engine.connections import *; "
              "import_league('<league_id>', '%s')\""
              % (SEASON, user["user_id"]))
        return 1

    print("\n  Leagues for %s (%d):" % (user["display_name"], SEASON))
    for i, lg in enumerate(leagues, start=1):
        rec = lg["reception"]
        fmt = "PPR" if rec >= 1 else ("half PPR" if rec > 0 else "standard")
        print("   %d. %-32s %2d teams, %s, waivers: %s"
              % (i, lg["name"], lg["teams"], fmt, lg["waiver_mode"]))
    try:
        pick = input("  Import which league? [1-%d, blank to cancel]: "
                     % len(leagues)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    if not pick:
        print("  Cancelled - nothing written.")
        return 0
    try:
        idx = int(pick)
        if not 1 <= idx <= len(leagues):
            raise ValueError
    except ValueError:
        print("  Not a number between 1 and %d - nothing written." % len(leagues))
        return 1

    chosen = leagues[idx - 1]
    print("\n  Importing %r (league %s)..." % (chosen["name"],
                                               chosen["league_id"]))
    try:
        summary = import_league(chosen["league_id"], user["user_id"])
    except SleeperError as exc:
        print("  %s" % exc)
        return 1
    _print_import_summary(summary)
    return 0


def _print_import_summary(summary: Dict) -> None:
    print("\n  CREATED")
    print("   league  : %s" % summary["league_file"])
    print("   roster  : %s  (%d players)"
          % (summary["roster_file"], summary["my_roster_size"]))
    print("   rankings: %s" % summary["rankings_csv"])
    rb = summary.get("rebuild")
    if rb:
        line = ("   rebuild : %d seeded, %d projections filled (%s)"
                % (rb["seeded"], rb["filled"], rb["scoring"]))
        if rb["tiered"] is not None:
            line += ", %d Chen tier rows" % rb["tiered"]
        else:
            line += " (no Chen feed for standard scoring - ADP-gap tiers stand)"
        print(line)
    print("   settings: %d teams, reception=%s, waivers=%s, %d roster spots"
          % (summary["teams"], summary["reception"], summary["waiver_mode"],
             len(summary["roster_spots"])))
    if summary["superflex"]:
        print("   NOTE    : this is a SUPERFLEX league (QB-eligible flex) - "
              "rankings seeded from 1-QB ADP will undervalue QBs")
    if summary["unresolved_player_ids"]:
        print("   NOTE    : %d roster player id(s) not in the Sleeper dump: %s"
              % (len(summary["unresolved_player_ids"]),
                 ", ".join(summary["unresolved_player_ids"])))
    print("   NEXT    : set my_slot in %s once the draft order is known"
          % summary["league_file"])


def _espn_wizard() -> int:
    if not os.path.exists(ESPN_SECRETS):
        print("\n  ESPN needs two cookies copied from your browser (about two")
        print("  minutes, done once). Follow: %s"
              % os.path.join(HERE, "SETUP_ESPN.md"))
        print("  Then re-run ./connect.sh to verify.")
        return 1
    print("\n  Secrets found - running the read-only connection check...")
    try:
        from engine import espn_cli
        rc = espn_cli.check()
    except Exception as exc:
        print("  ESPN check crashed: %s: %s" % (type(exc).__name__, exc))
        return 1
    if rc == 0:
        try:
            import datetime
            _atomic_write(ESPN_CHECK_FLAG, json.dumps(
                {"checked": datetime.date.today().isoformat()}))
        except OSError:
            pass
    return rc


def _yahoo_wizard() -> int:
    st = _yahoo_status()
    print("\n  Yahoo: %s" % st["detail"])
    if st["stage"] == "unregistered":
        print("  Follow: %s" % os.path.join(HERE, "SETUP_YAHOO.md"))
        return 1
    if st["stage"] == "registered":
        print("  Run ./yahoo.sh check when ready - it opens the browser "
              "authorization once.")
        return 1
    print("  Token on disk - running the read-only connection check...")
    try:
        from engine import yahoo
        lg, team = yahoo.connect()
        facts = yahoo.league_facts(lg)
        print("  Connected: %s (week %s)" % (facts.get("name"),
                                             facts.get("week")))
        return 0
    except Exception as exc:
        print("  Yahoo check failed: %s: %s" % (type(exc).__name__, exc))
        print("  See SETUP_YAHOO.md - 'What can go wrong'.")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("status", "--status"):
        _print_status_board()
        return 0
    if args and args[0] in ("people", "--people"):
        _print_people_board(args[1] if len(args) > 1 else None)
        return 0
    if args and args[0] == "block":
        if len(args) < 2:
            print("usage: python -m engine.connections block <person>")
            return 2
        try:
            print(users_yaml_block(args[1]), end="")
        except PersonError as exc:
            print("  %s" % exc)
            return 1
        return 0

    print("Graded Takes platform connections - one place for all three.")
    _print_status_board()
    print("\n  1. Sleeper  (username only - no password, no keys)")
    print("  2. ESPN     (browser cookies - YOUR OWN account only)")
    print("  3. Yahoo    (OAuth app)")
    print("\n  Onboarding someone else? `python -m engine.connections people`")
    print("  and docs/ONBOARD.md - never ask a friend for a cookie.")
    print("  q. quit")
    try:
        choice = input("\n  Connect which? [1/2/3/q]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if choice in ("1", "sleeper"):
        return _sleeper_wizard()
    if choice in ("2", "espn"):
        return _espn_wizard()
    if choice in ("3", "yahoo"):
        return _yahoo_wizard()
    return 0


if __name__ == "__main__":
    sys.exit(main())
