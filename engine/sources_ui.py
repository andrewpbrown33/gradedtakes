"""Local control panel: creator sources (data/sources.yaml) + league
connections (Sleeper / ESPN / Yahoo), one page, two tabs.

    ./sources.sh                     -> port 8787 (falls back), opens browser
    python -m engine.sources_ui [--port N] [--registry PATH] [--no-browser]

One self-contained page (inline HTML/CSS/tiny-JS on the shared design
system, engine/ui.py v3: ui.css() tokens + components, ui.shell() for the
navy header, ui.nameplate() faces for every input, and a thin mp- layer of
panel classes written against var(--wr-*) tokens only) served by a stdlib
http.server bound to 127.0.0.1 ONLY. No frameworks, nothing fetched (the
system embeds its fonts and faces). The shell's nav links point at the
sibling static pages (home.html, board-<league>-week<N>.html ...), which
GET serves READ-ONLY from the project root when they exist - a page not
generated yet answers 404 with the command that makes it.

THE INPUTS TAB (Model Settings proper): one row per source - a nameplate
(avatar 36px, name, live weight, the handle), the type as a monochrome
tag, an enable switch, and the weight as a slider PAIRED with a number box
(the script keeps the two in step; both feed the same /save payload), the
live share, and fetch-now. The enabled-weight sum is live and a note says
weights normalize. Adding a source also fetches its face best-effort
(engine/sources.fetch_avatar) - an avatar failure never fails the add.

THE LEAGUES TAB (onboarding SOMEONE WHO IS NOT THE OWNER)
  The owner runs this on his Mac and publishes a private copy per
  person, so this tab is about a FRIEND's leagues, not his own. Pick or
  add a person at the top; every card below acts on that selection.
  Each person's state and their ONE next action are rendered
  SERVER-SIDE per person (engine.connections.people_status() -> one
  coverage dict each) into .mp-person blocks, and the script only
  chooses which block is visible - so what the page says is what
  coverage() actually computed.
    person card  name + email -> POST /person/add -> data/people.yaml
                 (the ledger; publish.py's users.yaml is NEVER written
                 from here - the card prints the command that emits the
                 block to paste).
    sleeper      their username -> lookup -> Import files the league
                 under the selected person.
    espn         TWO person-safe routes of equal standing: a league id
                 (POST /espn/check reports honestly whether ESPN will
                 show it logged-out; /espn/import) or their pasted
                 roster (/espn/paste). The cookie box below them is
                 labelled as the OWNER'S OWN account only.
    yahoo        POST /yahoo/link mints the consent link to send;
                 /yahoo/code exchanges the short code they read back
                 (single-use, never stored or echoed) and lists their
                 leagues; /yahoo/import files one.
  THE CREDENTIAL RULE: this panel never accepts another person's
  password or session cookie. ESPN cookies are whole-account Disney
  session credentials and the ESPN card says so in as many words. OAuth
  consent is a different thing and is fine.

  * three platform cards driven by engine.connections.status() -
    green "connected" chip + the league names (or the detail line), or
    a neutral chip and the ONE next step. The contract this panel codes
    against (engine/connections.py owns the implementation):
        status() -> {"sleeper"|"espn"|"yahoo": {"connected": bool,
            "detail": str, "leagues": [names] (sleeper),
            "stage": str (yahoo: unregistered/registered/handshaken)}}
        resolve_user(username) -> {"user_id", "username", ...}
            (raises SleeperError on an unknown username - shown inline)
        list_leagues(user_id) -> [{"league_id", "name", "teams",
            "season", ...}]
        import_league(league_id, user_id) -> summary with
            league_file / roster_file / rankings_csv paths + name
    The normalizers below also tolerate the earlier draft shapes
    (next_step for detail, a sleeper_lookup() one-shot, a
    {"created": {...}} wrapper). Missing module / a raising status()
    degrades to neutral cards with an honest next step - the sources
    tab keeps working regardless.
  * SLEEPER: username -> POST /sleeper/lookup -> that user's leagues,
    each with an Import button -> POST /sleeper/import runs
    connections.import_league and reports exactly what was created.
  * ESPN: league_id + espn_s2 + swid -> POST /espn/save writes
    data/espn_secrets.json (0600, atomic), then a live check reports
    "saved, connected as <league>" or the error. Existing secret
    values are NEVER rendered back into the page, echoed into a
    response, or logged - the fields are always empty, the response
    carries only the league name / error.
  * YAHOO: staged guidance (register app -> data/yahoo_secrets.json ->
    ./yahoo.sh check, which must run in a terminal because the OAuth
    handshake opens a browser - the panel says so honestly); the
    current stage comes from status().
  * LEAGUE ROSTERS: coverage per league ("3 of 10 rosters known", and
    which layer each roster came from) plus a paste box for the leagues
    no API can read - Yahoo today. Preview PARSES ONLY: it shows every
    team, every matched player, every unmatched line and the coverage
    the save would produce, and writes nothing. Save re-parses the same
    text SERVER-SIDE (a client can post text, never rows) and writes
    data/league-<id>.json through engine/leagueview.py. The league id is
    checked against leagues/*.yaml before it reaches any path.
    engine/leagueview.py owns the parsing, merging and the write.

WHAT THE SOURCES TAB DOES
  * source rows: enable checkbox, 0-100 weight slider with a LIVE
    consensus-share readout (share = weight / sum of enabled weights -
    the same normalization consensus applies), multi-select + bulk
    enable/disable.
  * Save POSTs the rows; the server validates EVERYTHING first and only
    then writes data/sources.yaml atomically through engine/sources.py
    helpers (never hand-rolled YAML), answering with a saved-state
    confirmation the page shows.
  * add-source form: name + URL/handle, type auto-guessed from the URL
    (youtube.com -> youtube, .xml/feed -> rss, else url) and overridable.
  * paste box: pick a source, paste its content, stored via
    engine.sources.add_paste for later call extraction.
  * fetch-now per source: runs the fetcher and shows the item count -
    or the error, verbatim and inline. A failed source never vanishes.

WRITE DISCIPLINE (enforced in code): the sources tab performs no
filesystem writes itself - every mutation is delegated to
engine/sources.py helpers, whose write surface is exactly
data/sources.yaml + data/cache/ + the creator-calls paste store.
guard_write() re-checks any path this module ever hands them and raises
on anything outside that surface, so a bug here cannot grow a new write
path silently. GET requests write nothing (one exception:
engine.sources.load_sources seeds a MISSING registry file with the
built-in feeds - a write to the registry path itself).

The leagues tab adds a second, separately fenced allowlist
(guard_scoped_write): exactly leagues/*.yaml, data/rosters/*.yaml,
data/league-*.json, data/people.yaml, data/espn_secrets.json,
data/rankings-*.csv, and anything under data/cache/ - everything else
refused with PermissionError. The panel's only direct write is the ESPN
secrets file (plus its momentary atomic sibling <dest>.tmp, covered by
the grant on its destination); Sleeper/ESPN/Yahoo imports are written by
engine.connections and the modules it calls, the ledger by
engine.connections, and league-roster pastes by engine.leagueview. Every
path any of them reports is re-checked against this same allowlist
before the panel blesses the result - a rogue path turns the response
into a loud 403, and a path that merely LOOKS like a credential file
(secret/token in its name) is refused even inside the allowlist, because
an import has no business creating one. data/yahoo_secrets.json and any
per-person yahoo token file are deliberately NOT writable from here.

NO TWITTER/X SCRAPING - ANYWHERE. X's ToS forbid automated scraping and
logged-out access is actively hostile to it, so this panel offers no way
to add an X account as a fetchable source; X content enters ONLY through
the paste box, attributed to whichever source the user picks. The type
auto-guesser deliberately maps x.com/twitter.com HOSTS to 'paste' - a
host-boundary check (exact host or dot-prefixed subdomain, is_x_host),
never a substring scan: netflix.com/stockx.com merely end in "x.com" and
stay ordinary fetchable urls.

SINGLE-THREADED on purpose: one user, localhost, HTTP/1.0 close-per-
request - no locking, no concurrency to reason about. Ctrl-C shuts the
server down cleanly.
"""

import argparse
import html as _html
import json
import os
import re
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

try:
    from engine import sources as sources_mod
    from engine import ui as wr
except ImportError:  # run directly as `python engine/sources_ui.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import sources as sources_mod
    from engine import ui as wr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BIND = "127.0.0.1"          # localhost only - never 0.0.0.0
PORTS = (8787, 8788, 8789, 0)   # 0 = ask the OS for any free port

VALID_TYPES = ("youtube", "rss", "url", "paste", "feed")
ADDABLE_TYPES = ("youtube", "rss", "url", "paste")   # 'feed' = built-ins only
DEFAULT_WEIGHT = 25

PLATFORMS = ("sleeper", "espn", "yahoo")
PLATFORM_LABELS = {"sleeper": "Sleeper", "espn": "ESPN", "yahoo": "Yahoo"}

# Test seam: set to a module-like object to bypass the lazy import of
# engine.connections (tests plug a fake in; None -> import for real).
CONNECTIONS = None

YAHOO_STAGES = (
    ("register_app", "Register a read-only app at "
     "developer.yahoo.com/apps/create (SETUP_YAHOO.md step 1: Installed "
     "Application, redirect URI 'oob', Fantasy Sports - Read)."),
    ("secrets", "Put the Client ID + Secret into data/yahoo_secrets.json "
     "(SETUP_YAHOO.md step 3 has the exact two-key shape)."),
    ("handshake", "Run ./yahoo.sh check in a terminal - the OAuth "
     "handshake opens a browser window for Yahoo's consent screen, so "
     "this one step cannot happen from this panel."),
    ("connected", "Connected - nothing left to do."),
)

# engine/connections.py stage tokens -> the panel's stage keys above.
YAHOO_STAGE_ALIASES = {"unregistered": "register_app",
                       "registered": "handshake",
                       "handshaken": "connected"}


# --- pure helpers (unit-tested directly) ------------------------------------

X_HOSTS = ("x.com", "twitter.com")


def host_of(handle: str) -> str:
    """Bare hostname of a URL-ish handle ('' when there is none).

    Tolerates a missing scheme ('x.com/user'), userinfo, ports, and
    path/query/fragment tails. An @handle has no host and returns ''.
    """
    h = (handle or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    for sep in ("/", "?", "#"):
        h = h.split(sep, 1)[0]
    h = h.rsplit("@", 1)[-1]
    return h.split(":", 1)[0]


def is_x_host(handle: str) -> bool:
    """True only when the handle's HOST is x.com/twitter.com or a subdomain.

    Host-boundary check, not a substring scan: netflix.com and stockx.com
    merely END in 'x.com' and must stay fetchable - only the exact hosts
    (or a dot-prefixed subdomain like mobile.twitter.com) hit the ToS wall.
    """
    host = host_of(handle)
    return any(host == d or host.endswith("." + d) for d in X_HOSTS)


def guess_type(handle: str) -> str:
    """Auto-guess a source type from its URL/handle.

    youtube.com/youtu.be -> youtube; .xml/.rss/'feed'/'/rss' -> rss;
    an x.com/twitter.com HOST (exact or subdomain - see is_x_host) ->
    paste (NO X scraping - ToS, see module docstring); everything else
    -> url.
    """
    h = (handle or "").strip().lower()
    if "youtube.com" in h or "youtu.be" in h:
        return "youtube"
    if is_x_host(h):
        return "paste"
    if (h.endswith(".xml") or h.endswith(".rss") or "feed" in h
            or "/rss" in h):
        return "rss"
    return "url"


def slugify(name: str) -> str:
    """kebab-slug id from a display name ('Late Round QB!' -> 'late-round-qb')."""
    out, prev_dash = [], True
    for ch in (name or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def apply_updates(existing: List[Dict], updates) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """Merge enable/weight updates into a COPY of the registry rows.

    Validates everything before touching anything: unknown id, non-bool
    enabled, or a weight outside 0-100 rejects the whole batch (None, err)
    so a bad POST never half-applies. Fields other than enabled/weight are
    read-only from the panel - notes, handles, ids stay as filed.
    """
    if not isinstance(updates, list) or not updates:
        return None, "sources must be a non-empty list"
    by_id = {s.get("id"): dict(s) for s in existing}
    if len(by_id) != len(existing):
        return None, "registry has duplicate ids - fix data/sources.yaml first"
    seen = set()
    for u in updates:
        if not isinstance(u, dict):
            return None, "each update must be an object"
        sid = u.get("id")
        if sid not in by_id:
            return None, "unknown source id: %r" % (sid,)
        if sid in seen:
            return None, "duplicate update for id: %r" % (sid,)
        seen.add(sid)
        if not isinstance(u.get("enabled"), bool):
            return None, "%s: enabled must be true/false" % sid
        w = u.get("weight")
        if isinstance(w, bool) or not isinstance(w, (int, float)) or w != int(w):
            return None, "%s: weight must be an integer" % sid
        w = int(w)
        if not 0 <= w <= 100:
            return None, "%s: weight %d outside 0-100" % (sid, w)
    merged = []
    for s in existing:
        row = dict(s)
        for u in updates:
            if u["id"] == row.get("id"):
                row["enabled"] = u["enabled"]
                row["weight"] = int(u["weight"])
        merged.append(row)
    return merged, None


def new_source_entry(existing: List[Dict], name: str, handle: str,
                     type_: str = "") -> Tuple[Optional[Dict], Optional[str]]:
    """Validate + build a registry entry for the add-source form.

    Empty type_ means auto-guess from the handle. 'feed' is refused - the
    built-in engine feeds are seeded by engine/sources.py, not added here.
    """
    name = (name or "").strip()
    handle = (handle or "").strip()
    if not name:
        return None, "name is required"
    if not handle:
        return None, "URL/handle is required"
    type_ = (type_ or "").strip().lower() or guess_type(handle)
    if type_ == "feed":
        return None, "'feed' sources are the built-ins - not addable here"
    if type_ not in ADDABLE_TYPES:
        return None, "type must be one of %s" % (", ".join(ADDABLE_TYPES))
    if guess_type(handle) == "paste" and type_ != "paste":
        return None, ("X/Twitter is paste-only (no scraping - ToS; see "
                      "engine/sources_ui.py docstring). Re-add with type "
                      "'paste' and use the paste box.")
    sid = slugify(name)
    if not sid:
        return None, "name must contain at least one letter or digit"
    if any(s.get("id") == sid for s in existing):
        return None, "a source with id '%s' already exists" % sid
    return {"id": sid, "name": name, "type": type_, "handle": handle,
            "enabled": True, "weight": DEFAULT_WEIGHT, "notes": ""}, None


def guard_write(path: str, roots: List[str]) -> str:
    """Assert `path` sits inside the server's declared write surface.

    Called before ANY path is handed to a writing helper. Raises
    PermissionError otherwise - the write-discipline contract, in code.
    """
    real = os.path.realpath(os.path.abspath(path))
    for root in roots:
        r = os.path.realpath(os.path.abspath(root))
        if real == r or real.startswith(r.rstrip(os.sep) + os.sep):
            return path
    raise PermissionError("write outside the panel's surface refused: %s "
                          "(allowed: %s)" % (path, ", ".join(roots)))


LEAGUE_SCOPE = ("leagues/*.yaml, data/rosters/*.yaml, data/league-*.json, "
                "data/people.yaml, data/espn_secrets.json, "
                "data/rankings-*.csv, data/cache/")


def guard_scoped_write(path: str, data_root: str) -> str:
    """The leagues tab's write allowlist, fenced in code.

    Under `data_root` exactly these are writable - everything else
    raises PermissionError:
        leagues/<name>.yaml            (single segment, non-empty stem)
        data/rosters/<name>.yaml       (single segment, non-empty stem)
        data/league-<name>.json        (the League rosters card's store)
        data/people.yaml               (the onboarding ledger)
        data/espn_secrets.json
        data/rankings-<name>.csv       (non-empty stem after 'rankings-')
        data/cache/**                  (anything below it)
    NOTE data/rankings.csv (no dash) is NOT in scope - the shared
    default csv is owned elsewhere - and neither is
    data/yahoo_secrets.json or any data/yahoo_token*.json: the Yahoo
    card never writes a credential file from this seat, so a module
    that REPORTS having written one gets a 403 rather than a blessing.
    """
    real = os.path.realpath(os.path.abspath(path))
    root = os.path.realpath(os.path.abspath(data_root))
    rel = os.path.relpath(real, root)
    parts = rel.split(os.sep)
    ok = False
    if ".." not in parts:
        if (len(parts) == 2 and parts[0] == "leagues"
                and parts[1].endswith(".yaml")
                and len(parts[1]) > len(".yaml")):
            ok = True
        elif (len(parts) == 3 and parts[0] == "data"
                and parts[1] == "rosters" and parts[2].endswith(".yaml")
                and len(parts[2]) > len(".yaml")):
            ok = True
        elif parts == ["data", "espn_secrets.json"]:
            ok = True
        elif parts == ["data", "people.yaml"]:
            ok = True
        elif (len(parts) == 2 and parts[0] == "data"
                and parts[1].startswith("league-")
                and parts[1].endswith(".json")
                and len(parts[1]) > len("league-.json")):
            ok = True
        elif (len(parts) == 2 and parts[0] == "data"
                and parts[1].startswith("rankings-")
                and parts[1].endswith(".csv")
                and len(parts[1]) > len("rankings-.csv")):
            ok = True
        elif len(parts) > 2 and parts[0] == "data" and parts[1] == "cache":
            ok = True
    if not ok:
        raise PermissionError(
            "write outside the leagues surface refused: %s "
            "(allowed under %s: %s)" % (path, data_root, LEAGUE_SCOPE))
    return path


def _rel_to(path: str, root: str) -> str:
    """Path relative to root for display; unchanged when outside it."""
    real = os.path.realpath(os.path.abspath(path))
    rootr = os.path.realpath(os.path.abspath(root))
    rel = os.path.relpath(real, rootr)
    return path if rel.startswith("..") else rel


def validate_espn_secrets(body: Dict) -> Tuple[Optional[Dict], Optional[str]]:
    """Validate the ESPN card's three fields into a secrets dict.

    league_id must be the numeric id from the league URL; espn_s2 is a
    long cookie value; SWID gets its curly braces added when missing
    (the cookie always carries them - engine/espn.py insists).
    """
    lid = str(body.get("league_id") or "").strip()
    s2 = str(body.get("espn_s2") or "").strip()
    swid = str(body.get("swid") or "").strip()
    if not lid.isdigit():
        return None, ("league_id must be the number from your league URL "
                      "(...leagueId=NNNNNN...)")
    if not s2:
        return None, "espn_s2 is required - copy the whole cookie value"
    if len(s2) < 20:
        return None, ("espn_s2 looks too short to be the cookie - copy the "
                      "full value (hundreds of characters)")
    if not swid.strip("{}"):
        return None, "swid is required - copy the SWID cookie value"
    if not swid.startswith("{"):
        swid = "{" + swid
    if not swid.endswith("}"):
        swid = swid + "}"
    return {"league_id": int(lid), "espn_s2": s2, "swid": swid}, None


def normalize_leagues(result) -> List[Dict]:
    """Sleeper lookup result -> uniform league rows for the page.

    Tolerates a bare list or a {"leagues": [...]} dict, and either
    league_id/name/teams/season keys or Sleeper's own id/total_rosters.
    """
    leagues = result.get("leagues", []) if isinstance(result, dict) else result
    out = []
    for lg in (leagues or []):
        if not isinstance(lg, dict):
            continue
        out.append({
            "league_id": str(lg.get("league_id") or lg.get("id") or ""),
            "name": str(lg.get("name") or "unnamed league"),
            "teams": lg.get("teams") or lg.get("total_rosters") or "",
            "season": str(lg.get("season") or ""),
        })
    return out


def normalize_created(result) -> List[Dict]:
    """import_league result -> [{"label", "path"}] of what was created.

    engine/connections.py returns the paths at the top of its summary
    (league_file / roster_file / rankings_csv); a {"created": {...}} or
    {"created": [...]} wrapper is tolerated too. Junk reports nothing.
    """
    if not isinstance(result, dict):
        return []
    created = result.get("created")
    if isinstance(created, dict):
        return [{"label": str(k), "path": str(v)}
                for k, v in created.items() if v]
    if isinstance(created, list):
        return [{"label": "created", "path": str(p)} for p in created if p]
    return [{"label": k, "path": str(result[k])}
            for k in ("league_file", "league_yaml", "roster_file",
                      "rankings_csv")
            if result.get(k)]


# --- engine/sources.py bindings ---------------------------------------------
# The registry module owns ALL yaml/paste/fetch I/O; the panel only calls it.

def _registry_path(override: Optional[str]) -> str:
    return override or sources_mod.SOURCES_PATH


def _load_registry(path: str) -> List[Dict]:
    # NB: load_sources seeds a MISSING registry with the built-in feeds
    # (one write, to the registry path itself - inside the write surface).
    return sources_mod.load_sources(path)


def _save_registry(rows: List[Dict], path: str, roots: List[str]) -> None:
    guard_write(path, roots)
    sources_mod.save_sources(rows, path)


def _add_paste(source_id: str, text: str, url: str = "") -> Dict:
    # Paste store = data/cache/src-<id>.json (engine/sources.py owns it).
    return sources_mod.add_paste(source_id, text, url=url)


def _fetch_source(source: Dict) -> List[Dict]:
    # fetch NOW means fetch: max_age_hours=0 skips the freshness window;
    # a failure still falls back to the stale cache with items marked
    # stale=True (engine/sources.py), which the panel reports honestly.
    return sources_mod.fetch_source(source, max_age_hours=0.0, quiet=True)


def _avatar_after_add(entry: Dict) -> Tuple[Optional[str], str]:
    """Best-effort face for a just-added source: (path or None, reason).

    engine/sources.fetch_avatar_detail does the work (its write surface is
    data/cache/avatars/, inside the panel's). Module-level on purpose:
    tests plug a fake in so no add ever reaches the network. engine/assets
    memoizes avatar lookups per id for the life of a process, so a fresh
    picture must not stay shadowed by a remembered miss.
    """
    path, note = sources_mod.fetch_avatar_detail(entry)
    if path:
        try:
            from engine import assets as assets_mod  # noqa: PLC0415 - lazy
            mem = getattr(assets_mod, "_AVATAR_MEM", None)
        except Exception:  # noqa: BLE001 - a memo, never a failed add
            mem = None
        if isinstance(mem, dict):
            mem.pop(str(entry.get("id") or ""), None)
    return path, note


# --- the shell's context: week badge + league switcher ----------------------

def week_hint() -> Optional[int]:
    """The current NFL week from the CACHED nflverse schedule, for the
    shell's WK badge. Read from disk only - a GET of this panel never
    reaches for the network; with no cache on disk the badge falls back to
    the shell's default."""
    path = os.path.join(sources_mod.CACHE_DIR, "nflverse-schedule.csv")
    if not os.path.isfile(path):
        return None
    try:
        import csv  # noqa: PLC0415 - lazy
        from engine.digest import current_week  # noqa: PLC0415 - heavy
        with open(path, "r", newline="") as fh:
            return current_week(list(csv.DictReader(fh)))
    except Exception:  # noqa: BLE001 - a badge, never a broken page
        return None


def shell_leagues(data_root: str) -> List[Tuple[str, str]]:
    """[(id, name)] for the shell's league switcher - every readable
    leagues/*.yaml under data_root, or [] when none can be listed."""
    mod = _leagueview()
    if mod is None:
        return []
    try:
        return [(str(c.id), str(c.name)) for c in mod.list_configs(data_root)]
    except Exception:  # noqa: BLE001 - a switcher, never a broken page
        return []


# The sibling static pages the shell links to - one bare basename each,
# no directories, no query, so nothing but a generated page can be read.
_STATIC_PAGE_RE = re.compile(
    r"^(?:home|sources)\.html$"
    r"|^(?:board|digest|tradedesk)-[A-Za-z0-9_-]+-week\d{1,2}\.html$")


# --- engine/connections.py bindings ------------------------------------------
# connections owns platform I/O and league-file creation; the panel only
# calls it (contract in the module docstring) and re-guards reported paths.

def _connections():
    """The connections module - the CONNECTIONS test seam, else a lazy
    import of engine.connections, else None (panel degrades honestly)."""
    if CONNECTIONS is not None:
        return CONNECTIONS
    try:
        from engine import connections as mod  # noqa: PLC0415 - lazy
        return mod
    except Exception:  # noqa: BLE001 - absence is a rendered state
        return None


def connection_status() -> Dict[str, Dict]:
    """status() normalized to one dict per platform - NEVER raises.

    Every entry carries connected/leagues/next_step/detail/stage
    whatever the module returned ("detail" doubles as next_step when
    the module gives no explicit one); league entries may be names or
    {id,name} dicts; yahoo stage tokens are mapped onto YAHOO_STAGES.
    """
    mod = _connections()
    if mod is None:
        return {p: {"connected": False, "leagues": [], "stage": "",
                    "detail": "",
                    "next_step": "engine/connections.py is not available "
                                 "yet - the platform bridge ships "
                                 "separately; everything else here works."}
                for p in PLATFORMS}
    try:
        st = mod.status()
        if not isinstance(st, dict):
            raise TypeError("status() returned %s" % type(st).__name__)
    except Exception as exc:  # noqa: BLE001 - shown on the cards, honest
        return {p: {"connected": False, "leagues": [], "stage": "",
                    "detail": "",
                    "next_step": "status check failed: %s: %s"
                                 % (type(exc).__name__, exc)}
                for p in PLATFORMS}
    out = {}
    for p in PLATFORMS:
        e = st.get(p)
        e = e if isinstance(e, dict) else {}
        names = []
        for lg in (e.get("leagues") or []):
            if isinstance(lg, dict):
                names.append(str(lg.get("name") or lg.get("id") or "?"))
            else:
                names.append(str(lg))
        detail = str(e.get("detail") or "")
        stage = str(e.get("stage") or "").strip().lower()
        connected = bool(e.get("connected"))
        if connected and p == "yahoo" and not stage:
            stage = "connected"
        out[p] = {"connected": connected, "leagues": names,
                  "detail": detail,
                  "next_step": str(e.get("next_step") or "") or detail,
                  "stage": YAHOO_STAGE_ALIASES.get(stage, stage)}
    return out


def people_rows() -> List[Dict]:
    """coverage() per person for the Leagues tab - NEVER raises.

    [] means "nobody onboarded yet OR the person layer is unavailable",
    which the person card renders as an honest empty state: the panel's
    job is to keep working while a bridge module is missing.
    """
    mod = _connections()
    if mod is None or not hasattr(mod, "people_status"):
        return []
    try:
        rows = mod.people_status()
    except Exception:  # noqa: BLE001 - a card, never a broken page
        return []
    return [r for r in (rows or []) if isinstance(r, dict)]


def person_platform(row: Dict, platform: str) -> Dict:
    """One person's state on one platform, normalized for a card.

    Tolerates a coverage dict from any vintage: a missing platforms map
    degrades to 'missing' with the module's own next_step, never a
    KeyError on a page GET.
    """
    plats = row.get("platforms") if isinstance(row, dict) else None
    entry = (plats or {}).get(platform)
    entry = entry if isinstance(entry, dict) else {}
    state = str(entry.get("state") or ("ok" if entry.get("connected")
                                       else "missing"))
    return {"state": state,
            "connected": bool(entry.get("connected")),
            "detail": str(entry.get("detail") or ""),
            "next_step": str(entry.get("next_step") or "")}


def _sleeper_lookup(mod, username: str) -> Dict:
    """Username -> {username, user_id, leagues} via the real two-step
    API (resolve_user + list_leagues), or a one-shot sleeper_lookup()
    when the module offers one. Raises with an honest message."""
    if hasattr(mod, "sleeper_lookup"):
        result = mod.sleeper_lookup(username)
        return result if isinstance(result, dict) else {"leagues": result}
    user = mod.resolve_user(username)
    return {"username": str(user.get("username") or username),
            "user_id": str(user.get("user_id") or ""),
            "leagues": mod.list_leagues(user["user_id"])}


# --- engine/leagueview.py bindings -------------------------------------------
# leagueview owns the paste parser, the three-layer merge and the ONE
# write (data/league-<id>.json); the panel validates, guards the path and
# renders. Its absence degrades the card, never the page.

def _leagueview():
    try:
        from engine import leagueview as mod  # noqa: PLC0415 - lazy
        return mod
    except Exception:  # noqa: BLE001 - absence is a rendered state
        return None


def league_rows(data_root: str) -> Optional[List[Dict]]:
    """Coverage rows for the League rosters card, or None when unavailable.

    None is a rendered state ("coverage unavailable"), never a traceback -
    one unreadable league yaml must not blank the whole panel.
    """
    mod = _leagueview()
    if mod is None:
        return None
    try:
        return mod.coverage_rows(data_root)
    except Exception:  # noqa: BLE001 - shown as an honest empty card
        return None


def league_config(mod, data_root: str, league_id: str):
    """The LeagueConfig for an id THAT EXISTS in leagues/ - or None.

    The id reaches a file path (data/league-<id>.json), so it is never
    taken on trust: only an id the config listing itself produced is
    accepted, which forecloses traversal before guard_scoped_write is
    even asked.
    """
    for cfg in mod.list_configs(data_root):
        if cfg.id == league_id:
            return cfg
    return None


def espn_live_check() -> str:
    """Live ESPN check AFTER a save: connect with the just-written
    cookies and return the league name (raises with the honest error
    otherwise). Module-level on purpose - tests monkeypatch it."""
    from engine import espn as espn_mod  # noqa: PLC0415 - lazy, heavy
    lg = espn_mod.connect()
    return str(espn_mod.league_facts(lg).get("name") or "ESPN league")


# --- page -------------------------------------------------------------------

def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


# The panel's layer over the design system (engine/ui.py v3). Tokens only -
# every colour is a var(--wr-*) - and no green or red anywhere: a state is
# carried by WEIGHT (gold fill / ghost / dashed chips, a gold switch) and
# attention by a gold RULE beside ink text. Prefixed mp- so nothing here
# collides with the system's wr- vocabulary; the handful of bare class
# names (.note, .who, .why, .formrow ...) are the ones the inline JS writes
# and are kept for that reason.
_PANEL_CSS = """
  .mp-mast { margin: 0 0 16px; }
  .mp-tabbar { display: flex; gap: 4px; margin: -4px 0 14px;
               border-bottom: 1px solid var(--wr-hairline); }
  .mp-tab { font: inherit; font-size: 13px; font-weight: 700;
            letter-spacing: 0.04em; color: var(--wr-muted);
            background: transparent; border: 0; padding: 8px 12px;
            border-bottom: 3px solid transparent; cursor: pointer; }
  .mp-tab:hover { color: var(--wr-text); }
  .mp-tab.active { color: var(--wr-text); border-bottom-color: var(--wr-rule); }
  .mp-sec { padding: 14px 0 4px; border-top: 1px solid var(--wr-hairline); }
  .mp-sec:first-child { border-top: 0; padding-top: 0; }
  .note { color: var(--wr-muted); font-size: 12px; margin: 4px 0; }
  .note.warn, .note.bad { color: var(--wr-text); padding-left: 9px;
                          box-shadow: inset 3px 0 0 var(--wr-rule); }
  .note.bad { font-weight: 600; }
  .note.good { color: var(--wr-text); }
  .note code, code.mini, .mp-foot code {
    font-family: "Spline Sans Mono", ui-monospace, SFMono-Regular, Menlo,
                 monospace; font-size: 11.5px;
  }
  code.mini { background: var(--wr-raised); border: 1px solid var(--wr-hairline);
              border-radius: 4px; padding: 0 4px; }
  .who { font-weight: 700; }
  .who .meta { color: var(--wr-muted); font-weight: 400; font-size: 12px; }
  .why { color: var(--wr-muted); font-size: 12px; margin-top: 1px;
         overflow-wrap: anywhere; }
  .mp-table { font-size: 13.5px; }
  .mp-table td.num, .mp-table th.num { text-align: right; }
  .mp-inputs td { vertical-align: middle; }
  .mp-inputs .wr-np-n { max-width: 30ch; }
  .mp-inputs .wr-np-sub { max-width: 34ch; overflow: hidden;
                          text-overflow: ellipsis; white-space: nowrap; }
  tr.src.off .wr-np, tr.src.off .mp-tag { opacity: 0.45; }
  .mp-tag { display: inline-block; padding: 1px 6px; border-radius: 4px;
            background: var(--wr-raised); border: 1px solid var(--wr-hairline-2);
            color: var(--wr-muted); font-size: 11px; font-weight: 700;
            letter-spacing: 0.08em; text-transform: uppercase; }
  .mp-chip { display: inline-flex; align-items: center; border-radius: 5px;
             padding: 2px 8px; border: 1px solid transparent; font-size: 11.5px;
             font-weight: 700; letter-spacing: 0.4px; white-space: nowrap;
             color: var(--wr-text); }
  .mp-chip-fill  { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                   border-color: var(--wr-chip-start); }
  .mp-chip-ghost { color: var(--wr-muted); border-color: var(--wr-chip-sit); }
  .mp-chip-dash  { color: var(--wr-chip-lean);
                   border: 1px dashed var(--wr-chip-lean); }
  /* the enable toggle: a switch that fills gold when the input is on */
  .mp-switch { display: inline-flex; align-items: center; gap: 7px;
               cursor: pointer; font-size: 12px; color: var(--wr-muted);
               position: relative; }
  .mp-switch input { position: absolute; opacity: 0; width: 1px; height: 1px; }
  .mp-switch-t { width: 34px; height: 20px; border-radius: 999px; flex: none;
                 background: var(--wr-hairline-2); position: relative;
                 transition: background 120ms ease; }
  .mp-switch-t::after { content: ""; position: absolute; top: 3px; left: 3px;
                        width: 14px; height: 14px; border-radius: 50%;
                        background: var(--wr-panel);
                        transition: transform 120ms ease; }
  .mp-switch input:checked + .mp-switch-t { background: var(--wr-rule); }
  .mp-switch input:checked + .mp-switch-t::after { transform: translateX(14px); }
  .mp-switch input:focus-visible + .mp-switch-t { outline: 2px solid var(--wr-rule);
                                                  outline-offset: 2px; }
  /* weight: slider and number are ONE control, kept in step by the script */
  .mp-wcell { white-space: nowrap; }
  input[type=range].w { width: 120px; vertical-align: middle;
                        accent-color: var(--wr-rule); }
  input[type=number].wn { width: 4.4em; text-align: right; }
  .mp-sum { display: flex; flex-wrap: wrap; align-items: baseline;
            gap: 6px 14px; margin: 10px 0 2px; font-size: 12.5px;
            color: var(--wr-muted); }
  .mp-sum .wr-num { font-size: 16px; font-weight: 600; color: var(--wr-text); }
  .wr-page button { font: inherit; font-size: 12.5px; font-weight: 600;
                    color: var(--wr-text); background: var(--wr-raised);
                    border: 1px solid var(--wr-hairline-2); border-radius: 6px;
                    padding: 5px 11px; cursor: pointer; }
  .wr-page button:hover { border-color: var(--wr-gold); color: var(--wr-gold); }
  .wr-page button:disabled { opacity: 0.5; cursor: default; }
  .wr-page button.primary { background: var(--wr-chip-start);
                            border-color: var(--wr-chip-start);
                            color: var(--wr-chip-ink); font-size: 13.5px;
                            padding: 7px 16px; }
  .wr-page button.primary:hover { color: var(--wr-chip-ink); }
  .wr-page button:focus-visible, .wr-page input:focus-visible,
  .wr-page select:focus-visible, .wr-page textarea:focus-visible,
  .mp-tab:focus-visible {
    outline: 2px solid var(--wr-rule); outline-offset: 2px;
  }
  input[type=text], input[type=number], input[type=password], select, textarea {
    font: inherit; font-size: 13px; color: var(--wr-text);
    background: var(--wr-panel); border: 1px solid var(--wr-hairline-2);
    border-radius: 6px; padding: 5px 8px;
  }
  textarea { width: 100%; box-sizing: border-box; min-height: 110px;
             font-family: "Spline Sans Mono", ui-monospace, SFMono-Regular,
                          Menlo, monospace; font-size: 12px; }
  .formrow { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
             margin: 8px 0; }
  .formrow label { font-size: 12px; color: var(--wr-muted); }
  .bulkbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
             margin: 10px 0 2px; font-size: 12.5px; color: var(--wr-muted); }
  .savebar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
             margin-top: 12px; border-top: 1px solid var(--wr-hairline);
             padding-top: 10px; }
  .fres { font-size: 12px; margin-top: 2px; }
  .mp-foot { margin-top: 22px; color: var(--wr-muted); font-size: 12px;
             border-top: 1px solid var(--wr-hairline); padding-top: 10px; }
  [hidden] { display: none !important; }
  .lhead { display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
           margin: 2px 0 6px; }
  ul.leaguelist { margin: 4px 0 2px; padding-left: 18px; font-size: 13px; }
  ol.steps { margin: 6px 0 4px; padding-left: 20px; font-size: 12.5px; }
  ul.steps { margin: 6px 0 4px; padding-left: 20px; font-size: 12.5px; }
  ol.steps li, ul.steps li { margin: 3px 0; }
  ol.steps li.here { font-weight: 700; }
  ol.steps li.done { color: var(--wr-dim); }
  /* the selected person's state, per card - one block visible at a time */
  .mp-person { margin: 2px 0 8px; padding: 8px 10px;
               border: 1px solid var(--wr-hairline); border-radius: 6px; }
  .mp-person .lhead { margin: 0 0 4px; }
  .mp-person p:last-child { margin-bottom: 0; }
  hr.mp-rule { border: 0; border-top: 1px solid var(--wr-hairline);
               margin: 14px 0 10px; }
  #ya-url { font-family: var(--wr-mono, monospace); font-size: 11.5px; }
"""


def _style_tag() -> str:
    """The system's stylesheet (tokens, components, v3 layer, one rule per
    cached avatar) plus the panel layer - one <style>, nothing linked."""
    return "<style>%s%s</style>" % (wr.css(), _PANEL_CSS)


_JS = """
'use strict';
function rows(){return Array.prototype.slice.call(
  document.querySelectorAll('tr.src'));}
function num(el){var v=parseInt(el.value,10);return isNaN(v)?0:v;}
function clamp(v){return Math.max(0,Math.min(100,v));}
function recalc(){
  var tot=0;
  rows().forEach(function(r){
    if(r.querySelector('.en').checked) tot+=num(r.querySelector('.w'));});
  rows().forEach(function(r){
    var w=num(r.querySelector('.w')), on=r.querySelector('.en').checked;
    var np=r.querySelector('.wr-np-w'); if(np) np.textContent='wt '+w;
    r.querySelector('.share').textContent=
      (on&&tot>0)?(100*w/tot).toFixed(1)+'%':'\\u2014';
    r.classList.toggle('off',!on);});
  document.getElementById('tot').textContent=tot;
}
/* slider and number box are one control: whichever moved drives the other */
function syncFromRange(r){
  r.querySelector('.wn').value=num(r.querySelector('.w'));
}
function syncFromNumber(r,final){
  var n=r.querySelector('.wn'), raw=parseInt(n.value,10), v=clamp(num(n));
  if(final||raw>100||raw<0) n.value=v;
  r.querySelector('.w').value=v;
}
function markDirty(){
  var s=document.getElementById('savestate');
  s.textContent='unsaved changes'; s.className='note warn';
}
function post(url,body,cb){
  fetch(url,{method:'POST',
             headers:{'Content-Type':'application/json'},
             body:JSON.stringify(body)})
    .then(function(r){return r.json();}).then(cb)
    .catch(function(e){cb({ok:false,error:String(e)});});
}
function save(){
  var payload={sources:rows().map(function(r){return{
    id:r.getAttribute('data-id'),
    enabled:r.querySelector('.en').checked,
    weight:num(r.querySelector('.w'))};})};
  var s=document.getElementById('savestate');
  s.textContent='saving\\u2026'; s.className='note';
  post('/save',payload,function(res){
    if(res.ok){
      s.textContent='saved '+res.sources+' sources at '+res.at+
        ' \\u00b7 enabled weight '+res.enabled_weight+' \\u00b7 '+res.registry;
      s.className='note good';
    }else{
      s.textContent='NOT saved \\u2014 '+res.error;
      s.className='note bad';
    }});
}
function bulk(on){
  rows().forEach(function(r){
    if(r.querySelector('.sel').checked) r.querySelector('.en').checked=on;});
  recalc(); markDirty();
}
function selAll(box){
  rows().forEach(function(r){r.querySelector('.sel').checked=box.checked;});
}
function fetchNow(btn){
  var r=btn.closest('tr'), out=r.querySelector('.fres');
  out.textContent='fetching\\u2026'; out.className='fres note';
  btn.disabled=true;
  post('/fetch',{id:r.getAttribute('data-id')},function(res){
    btn.disabled=false;
    if(res.ok){
      out.textContent=res.items+' item(s)'+(res.note?' \\u00b7 '+res.note:'');
      out.className='fres note good';
    }else{
      out.textContent='FAILED \\u2014 '+res.error;
      out.className='fres note bad';
    }});
}
function hostOf(h){
  /* mirror of engine/sources_ui.py host_of() - keep in sync */
  h=(h||'').toLowerCase().replace(/^\\s+|\\s+$/g,'');
  var i=h.indexOf('://'); if(i>=0)h=h.slice(i+3);
  h=h.split('/')[0].split('?')[0].split('#')[0];
  var a=h.split('@'); h=a[a.length-1];
  return h.split(':')[0];
}
function isXHost(h){
  /* host-boundary check, not a substring scan: netflix.com/stockx.com
     merely END in "x.com" and stay fetchable (mirror of is_x_host) */
  var host=hostOf(h);
  return ['x.com','twitter.com'].some(function(d){
    return host===d||host.slice(-(d.length+1))==='.'+d;});
}
function guessType(h){
  h=(h||'').toLowerCase();
  if(h.indexOf('youtube.com')>=0||h.indexOf('youtu.be')>=0)return 'youtube';
  if(isXHost(h))return 'paste';
  if(/\\.xml($|[?#])/.test(h)||/\\.rss($|[?#])/.test(h)||
     h.indexOf('feed')>=0||h.indexOf('/rss')>=0)return 'rss';
  return 'url';
}
function updateGuess(){
  var h=document.getElementById('add-handle').value;
  var g=document.getElementById('add-guess');
  g.textContent=h?('auto-guess: '+guessType(h)):'';
}
function addSource(){
  var sel=document.getElementById('add-type');
  var out=document.getElementById('add-res');
  out.textContent='adding\\u2026 (fetching a face for it too, best effort)';
  out.className='note';
  post('/add',{name:document.getElementById('add-name').value,
               handle:document.getElementById('add-handle').value,
               type:sel.value==='auto'?'':sel.value},
    function(res){
      if(res.ok){location.reload();}
      else{out.textContent='NOT added \\u2014 '+res.error;
           out.className='note bad';}});
}
function storePaste(){
  var out=document.getElementById('paste-res');
  out.textContent='storing\\u2026'; out.className='note';
  post('/paste',{source:document.getElementById('paste-src').value,
                 text:document.getElementById('paste-text').value,
                 url:document.getElementById('paste-url').value},
    function(res){
      if(res.ok){
        out.textContent='stored '+res.chars+' chars for '+res.source+
          ' as \\u201c'+res.title+'\\u201d';
        out.className='note good';
        document.getElementById('paste-text').value='';
        document.getElementById('paste-url').value='';
      }else{
        out.textContent='NOT stored \\u2014 '+res.error;
        out.className='note bad';
      }});
}
function showTab(name){
  ['model','leagues'].forEach(function(t){
    var pane=document.getElementById('pane-'+t);
    var btn=document.getElementById('tab-'+t);
    if(pane) pane.hidden=(t!==name);
    if(btn){
      btn.className='mp-tab'+(t===name?' active':'');
      btn.setAttribute('aria-selected',t===name?'true':'false');
    }
  });
}
function slLookup(){
  var u=document.getElementById('sl-user').value
        .replace(/^\\s+|\\s+$/g,'');
  var out=document.getElementById('sl-res');
  var list=document.getElementById('sl-leagues');
  while(list.firstChild) list.removeChild(list.firstChild);
  if(!u){out.textContent='enter your Sleeper username first';
         out.className='note bad';return;}
  out.textContent='looking up '+u+'\\u2026'; out.className='note';
  post('/sleeper/lookup',{username:u},function(res){
    if(!res.ok){out.textContent=res.error;out.className='note bad';return;}
    if(!res.leagues.length){
      out.textContent='no leagues this season for '+res.username;
      out.className='note warn';return;}
    out.textContent=res.leagues.length+' league(s) for '+res.username+
      ' \\u2014 import the ones you play in:';
    out.className='note good';
    res.leagues.forEach(function(lg){
      /* DOM-built (textContent), never innerHTML - league names are
         remote data */
      var row=document.createElement('div'); row.className='formrow';
      var b=document.createElement('button'); b.textContent='Import';
      b.addEventListener('click',function(){
        slImport(b,res.user_id,lg.league_id);});
      var label=document.createElement('span');
      label.textContent=lg.name+' \\u00b7 '+(lg.teams||'?')+' teams'+
        (lg.season?(' \\u00b7 '+lg.season):'');
      var msg=document.createElement('span'); msg.className='note';
      row.appendChild(b); row.appendChild(label); row.appendChild(msg);
      list.appendChild(row);
    });
  });
}
function slImport(btn,userId,leagueId){
  var msg=btn.parentNode.querySelector('.note');
  btn.disabled=true;
  msg.textContent='importing\\u2026'; msg.className='note';
  post('/sleeper/import',{user_id:userId,league_id:leagueId,
                          person:whoIsSelected()},function(res){
    if(res.ok){
      msg.textContent='imported '+res.league+' \\u2014 created: '+
        (createdList(res)||'nothing new')+
        (res.person?(' \\u00b7 filed under '+res.person):'')+
        ' \\u00b7 reload to refresh the cards';
      msg.className='note good';
    }else{
      btn.disabled=false;
      msg.textContent='NOT imported \\u2014 '+res.error;
      msg.className='note bad';
    }});
}
/* --- the person layer: every card below acts on this one selection ----- */
function whoIsSelected(){
  var sel=document.getElementById('pp-person');
  return sel?sel.value:'';
}
function pickPerson(){
  var key=whoIsSelected();
  var blocks=document.querySelectorAll('.mp-person[data-person]');
  for(var i=0;i<blocks.length;i++){
    blocks[i].hidden=(blocks[i].getAttribute('data-person')!==key);
  }
}
function needPerson(out){
  var key=whoIsSelected();
  if(!key){
    out.textContent='add the person you are onboarding first \\u2014 '+
      'these boxes act on whoever is selected up top';
    out.className='note bad';
    return '';
  }
  return key;
}
function createdList(res){
  return (res.created||[]).map(function(c){return c.path;}).join(', ');
}
function addPerson(){
  var out=document.getElementById('pp-res');
  var name=document.getElementById('pp-name').value;
  var email=document.getElementById('pp-email').value;
  out.textContent='adding\\u2026'; out.className='note';
  post('/person/add',{name:name,email:email},function(res){
    if(res.ok){
      out.textContent='added '+res.person+' \\u00b7 '+res.detail+
        ' \\u00b7 reload to select them';
      out.className='note good';
      document.getElementById('pp-name').value='';
      document.getElementById('pp-email').value='';
    }else{
      out.textContent='NOT added \\u2014 '+res.error;
      out.className='note bad';
    }});
}
function espnCheck(){
  var out=document.getElementById('espn-pub-res');
  var box=document.getElementById('espn-pub-teams');
  var lid=document.getElementById('espn-pub-lid').value;
  while(box.firstChild) box.removeChild(box.firstChild);
  out.textContent='asking ESPN\\u2026'; out.className='note';
  post('/espn/check',{league_id:lid},function(res){
    if(!res.ok){out.textContent=res.error;out.className='note bad';return;}
    if(res.readable){
      out.textContent='readable without logging in'+
        (res.name?(' \\u2014 '+res.name):'')+
        ' \\u00b7 now say which team is theirs';
      out.className='note good';
      (res.roster||[]).forEach(function(t){
        /* DOM-built (textContent) - team names are remote data */
        var p=document.createElement('p'); p.className='why';
        p.textContent='team '+t.team_id+'  \\u00b7  '+t.name;
        box.appendChild(p);
      });
    }else{
      out.textContent='NOT readable \\u2014 '+res.detail;
      out.className='note warn';
    }});
}
function espnImport(){
  var out=document.getElementById('espn-pub-res');
  var key=needPerson(out); if(!key) return;
  out.textContent='importing\\u2026'; out.className='note';
  post('/espn/import',{person:key,
       league_id:document.getElementById('espn-pub-lid').value,
       team:document.getElementById('espn-pub-team').value},
    function(res){
      if(res.ok){
        out.textContent='imported '+res.league+' for '+res.person+
          ' \\u2014 created: '+(createdList(res)||'nothing new')+
          ' \\u00b7 reload to refresh';
        out.className='note good';
      }else{
        out.textContent='NOT imported \\u2014 '+res.error;
        out.className='note bad';
      }});
}
function espnPaste(){
  var out=document.getElementById('espn-paste-res');
  var key=needPerson(out); if(!key) return;
  var text=document.getElementById('espn-paste-text').value;
  if(!text.replace(/^\\s+|\\s+$/g,'')){
    out.textContent='paste their roster first'; out.className='note bad';
    return;
  }
  out.textContent='reading the paste\\u2026'; out.className='note';
  post('/espn/paste',{person:key,text:text,
       league_id:document.getElementById('espn-paste-lid').value,
       team:document.getElementById('espn-paste-team').value},
    function(res){
      if(res.ok){
        out.textContent='imported '+res.league+' for '+res.person+
          ' \\u2014 created: '+(createdList(res)||'nothing new')+
          ' \\u00b7 reload to refresh';
        out.className='note good';
      }else{
        out.textContent='NOT imported \\u2014 '+res.error;
        out.className='note bad';
      }});
}
function yaLink(){
  var out=document.getElementById('ya-link-res');
  var key=needPerson(out); if(!key) return;
  out.textContent='building the consent link\\u2026'; out.className='note';
  post('/yahoo/link',{person:key},function(res){
    if(!res.ok){out.textContent=res.error;out.className='note bad';return;}
    document.getElementById('ya-url').value=res.url;
    out.textContent='send this to '+res.person+', then paste back the code '+
      'they read to you. What to say: '+res.ask;
    out.className='note good';
  });
}
function yaFinish(){
  var out=document.getElementById('ya-res');
  var key=needPerson(out); if(!key) return;
  var list=document.getElementById('ya-leagues');
  while(list.firstChild) list.removeChild(list.firstChild);
  out.textContent='exchanging the code\\u2026'; out.className='note';
  post('/yahoo/code',{person:key,
       code:document.getElementById('ya-code').value},function(res){
    /* the code is single-use: clear it whatever happened */
    document.getElementById('ya-code').value='';
    if(!res.ok){out.textContent=res.error;out.className='note bad';return;}
    if(!(res.leagues||[]).length){
      out.textContent='connected, but Yahoo lists no NFL leagues for '+
        res.person+' this season';
      out.className='note warn';return;}
    out.textContent='connected \\u2014 '+res.leagues.length+
      ' league(s) for '+res.person+'; import the ones they play in:';
    out.className='note good';
    res.leagues.forEach(function(lg){
      /* DOM-built (textContent), never innerHTML - names are remote data */
      var row=document.createElement('div'); row.className='formrow';
      var b=document.createElement('button'); b.textContent='Import';
      b.addEventListener('click',function(){yaImport(b,key,lg.league_key);});
      var label=document.createElement('span');
      label.textContent=lg.name+(lg.teams?(' \\u00b7 '+lg.teams+' teams'):'')+
        (lg.season?(' \\u00b7 '+lg.season):'');
      var msg=document.createElement('span'); msg.className='note';
      row.appendChild(b); row.appendChild(label); row.appendChild(msg);
      list.appendChild(row);
    });
  });
}
function yaImport(btn,key,leagueKey){
  var msg=btn.parentNode.querySelector('.note');
  btn.disabled=true;
  msg.textContent='importing\\u2026'; msg.className='note';
  post('/yahoo/import',{person:key,league_key:leagueKey},function(res){
    if(res.ok){
      msg.textContent='imported '+res.league+' \\u2014 created: '+
        (createdList(res)||'nothing new')+' \\u00b7 reload to refresh';
      msg.className='note good';
    }else{
      btn.disabled=false;
      msg.textContent='NOT imported \\u2014 '+res.error;
      msg.className='note bad';
    }});
}
function espnSave(){
  var out=document.getElementById('espn-res');
  out.textContent='saving, then testing the connection\\u2026';
  out.className='note';
  post('/espn/save',{
    league_id:document.getElementById('espn-lid').value,
    espn_s2:document.getElementById('espn-s2').value,
    swid:document.getElementById('espn-swid').value},
    function(res){
      if(res.ok&&res.connected){
        out.textContent='saved, connected as '+res.league+
          ' \\u00b7 reload to refresh the cards';
        out.className='note good';
        document.getElementById('espn-s2').value='';
        document.getElementById('espn-swid').value='';
      }else if(res.ok){
        out.textContent='saved, but the live check failed \\u2014 '+
          res.error;
        out.className='note warn';
      }else{
        out.textContent='NOT saved \\u2014 '+res.error;
        out.className='note bad';
      }});
}
function lrEl(id){return document.getElementById(id);}
function lrLine(cls,text){
  /* DOM-built (textContent), never innerHTML - team and player names
     are pasted data */
  var p=document.createElement('p'); p.className=cls; p.textContent=text;
  return p;
}
function lrRender(res){
  var box=lrEl('lr-preview');
  while(box.firstChild) box.removeChild(box.firstChild);
  box.appendChild(lrLine('note','coverage '+res.before+
    ' \\u2192 '+res.after+' if saved'));
  (res.teams||[]).forEach(function(t){
    box.appendChild(lrLine('note good',t.team+' \\u2192 slot '+t.slot+
      ' \\u00b7 '+t.count+' player(s)'+(t.note?' \\u00b7 '+t.note:'')));
    box.appendChild(lrLine('why',t.players.join(', ')));
  });
  (res.refused||[]).forEach(function(r){
    box.appendChild(lrLine('note bad','REFUSED '+r.team+' \\u2014 '+r.why));});
  if((res.unmatched||[]).length){
    box.appendChild(lrLine('note warn',
      res.unmatched.length+' line(s) NOT matched - nothing was invented '+
      'for them; fix the spelling and paste again:'));
    res.unmatched.forEach(function(u){
      box.appendChild(lrLine('why',(u.team||'(no team)')+'  |  '+u.line));});
  }
  (res.contested||[]).forEach(function(c){
    box.appendChild(lrLine('note warn',c));});
  (res.warnings||[]).forEach(function(w){
    box.appendChild(lrLine('note warn',w));});
  if(res.skipped)
    box.appendChild(lrLine('note',res.skipped+
      ' page-furniture line(s) skipped'));
}
function lrPost(url,cb){
  var out=lrEl('lr-res');
  var text=lrEl('lr-text').value;
  if(!text.replace(/^\\s+|\\s+$/g,'')){
    out.textContent='paste some rosters first'; out.className='note bad';
    return;
  }
  out.textContent='parsing\\u2026'; out.className='note';
  post(url,{league:lrEl('lr-league').value,text:text},function(res){
    if(!res.ok){
      out.textContent='NOT saved \\u2014 '+res.error;
      out.className='note bad';
      lrEl('lr-save').disabled=true;
      return;
    }
    lrRender(res); cb(res,out);
  });
}
function previewLeague(){
  lrPost('/league/preview',function(res,out){
    out.textContent='parsed '+res.matched+' player(s) across '+
      res.teams.length+' team(s) \\u2014 nothing written yet';
    out.className='note good';
    lrEl('lr-save').disabled=(res.teams.length===0);
  });
}
function saveLeague(){
  lrPost('/league/save',function(res,out){
    out.textContent='saved '+res.written+' roster(s) to '+res.path+
      ' \\u00b7 coverage now '+res.after+' \\u00b7 reload to refresh the table';
    out.className='note good';
    lrEl('lr-save').disabled=true;
  });
}
document.addEventListener('DOMContentLoaded',function(){
  rows().forEach(function(r){
    r.querySelector('.w').addEventListener('input',
      function(){syncFromRange(r);recalc();markDirty();});
    r.querySelector('.wn').addEventListener('input',
      function(){syncFromNumber(r,false);recalc();markDirty();});
    r.querySelector('.wn').addEventListener('change',
      function(){syncFromNumber(r,true);recalc();});
    r.querySelector('.en').addEventListener('change',
      function(){recalc();markDirty();});
  });
  document.getElementById('add-handle')
    .addEventListener('input',updateGuess);
  if(document.getElementById('pp-person')) pickPerson();
  recalc();
});
"""


_CHIP_TONE = {"fill": "mp-chip mp-chip-fill", "ghost": "mp-chip mp-chip-ghost",
              "dash": "mp-chip mp-chip-dash"}


def _chip(tone: str, text) -> str:
    """A state by WEIGHT: fill (it is so), ghost (it is not), dash (partway)."""
    return '<span class="%s">%s</span>' % (_CHIP_TONE[tone], _esc(text))


def _type_tag(type_: str) -> str:
    """The source type as a monochrome typographic tag - the palette's one
    accent is spent on states, not on a rainbow of kinds."""
    return '<span class="mp-tag">%s</span>' % _esc(type_ or "?")


def _status_chip(entry: Dict) -> str:
    if entry.get("connected"):
        return _chip("fill", "connected")
    return _chip("ghost", "not connected")


def _card_head(platform: str, entry: Dict) -> str:
    """Shared card lead: status chip, then league names OR the ONE next step."""
    bits = ['<div class="lhead">%s</div>' % _status_chip(entry)]
    if entry.get("connected"):
        if entry.get("leagues"):
            bits.append('<ul class="leaguelist">%s</ul>' % "".join(
                "<li>%s</li>" % _esc(n) for n in entry["leagues"]))
        elif entry.get("detail"):
            bits.append('<p class="note good">%s</p>' % _esc(entry["detail"]))
    else:
        bits.append('<p class="note warn">next step: %s</p>'
                    % _esc(entry.get("next_step") or "unknown"))
    return "".join(bits)


def _sec(sec_id: str, title: str, body_html: str,
         count_note: Optional[str] = None) -> str:
    """One section inside the tab card: the system's gold-rule header
    over trusted body HTML."""
    attrs = (' id="%s"' % _esc(sec_id)) if sec_id else ""
    return ('<section class="mp-sec"%s>%s%s</section>'
            % (attrs, wr.section_header(title, count_note=count_note),
               body_html))


_PERSON_CHIP = {"ok": ("fill", "connected"), "stale": ("dash", "stale"),
                "missing": ("ghost", "not connected"),
                "broken": ("ghost", "files missing"),
                "not used": ("ghost", "not used")}


def _person_blocks(people: Optional[List[Dict]], platform: str) -> str:
    """One state block per person for a platform card; the selected
    person's is the visible one.

    The state AND the next action are rendered server-side, per person,
    so what the owner reads is what coverage() actually computed - the
    script only chooses which block is on screen.
    """
    people = [p for p in (people or []) if isinstance(p, dict)]
    if not people:
        return ('<div class="mp-person">'
                '<p class="note warn">no one to onboard yet &mdash; add the '
                "person above first. These boxes always act on whoever is "
                "selected there.</p></div>")
    out = []
    for i, row in enumerate(people):
        st = person_platform(row, platform)
        tone, label = _PERSON_CHIP.get(st["state"], ("ghost", st["state"]))
        bits = ['<div class="lhead">%s <b>%s</b></div>'
                % (_chip(tone, label), _esc(row.get("person") or "?"))]
        if st["detail"]:
            bits.append('<p class="note%s">%s</p>'
                        % (" good" if st["connected"] else "",
                           _esc(st["detail"])))
        if st["next_step"]:
            bits.append('<p class="note warn">next: %s</p>'
                        % _esc(st["next_step"]))
        out.append('<div class="mp-person" data-person="%s"%s>%s</div>'
                   % (_esc(row.get("key") or ""), "" if i == 0 else " hidden",
                      "".join(bits)))
    return "".join(out)


def render_person_card(people: Optional[List[Dict]]) -> str:
    """Who are we onboarding? The picker, the add form, and the state.

    Everything below this card acts on the person selected here - the
    panel is no longer about the owner's own account, because the owner
    is not the one who needs onboarding.
    """
    people = [p for p in (people or []) if isinstance(p, dict)]
    if people:
        options = "".join(
            '<option value="%s">%s%s</option>'
            % (_esc(p.get("key") or ""), _esc(p.get("person") or "?"),
               (" (%s)" % _esc(p["email"])) if p.get("email") else "")
            for p in people)
        picker = ('<div class="formrow"><label>onboarding '
                  '<select id="pp-person" onchange="pickPerson()">%s'
                  "</select></label>"
                  '<span id="pp-detail" class="note"></span></div>' % options)
        states = []
        for i, p in enumerate(people):
            published = bool(p.get("in_users_yaml"))
            # The publish state gets its own line with the commands in it,
            # so the same sentence is not also repeated in the to-do list.
            steps = [s for s in (p.get("next_steps") or [])
                     if s and not (not published and "users.yaml" in s)]
            items = "".join("<li>%s</li>" % _esc(s) for s in steps)
            pub = ('<p class="note good">in users.yaml &mdash; '
                   "publish.sh will build their pages.</p>" if published else
                   '<p class="note warn">not in users.yaml, so nothing is '
                   "published to them yet. "
                   "<code class=\"mini\">python -m engine.connections block "
                   "%s</code> prints the entry to paste; "
                   "<code class=\"mini\">publish.py new-token</code> makes "
                   "its token.</p>" % _esc(p.get("key") or ""))
            states.append(
                '<div class="mp-person" data-person="%s"%s>'
                '<p class="note">%s &middot; %s</p>%s%s</div>'
                % (_esc(p.get("key") or ""), "" if i == 0 else " hidden",
                   _esc(p.get("email") or "no email"),
                   _esc(p.get("detail") or ""), pub,
                   ('<ul class="steps">%s</ul>' % items) if items else
                   '<p class="note good">nothing outstanding.</p>'))
        body = picker + "".join(states)
    else:
        body = ('<p class="note warn">nobody is being onboarded yet. Add the '
                "friend you are setting up - their name and the email "
                "Cloudflare Access will check at the door.</p>")
    return _sec("card-person", "Who you are onboarding", (
        "%s"
        '<div class="formrow">'
        '<label>name <input type="text" id="pp-name" size="18" '
        'placeholder="Their Name" autocomplete="off"></label>'
        '<label>email <input type="email" id="pp-email" size="24" '
        'placeholder="them@example.com" autocomplete="off"></label>'
        '<button onclick="addPerson()">Add person</button></div>'
        '<p id="pp-res" class="note"></p>'
        '<p class="note">recorded in <code class="mini">data/people.yaml'
        "</code> - who, where and when, never a credential. This is not "
        "the publish list: <code class=\"mini\">users.yaml</code> is, and "
        "nothing here writes it.</p>" % body))


def render_sleeper_card(entry: Dict,
                        people: Optional[List[Dict]] = None) -> str:
    return _sec("card-sleeper", "Sleeper", (
        "%s%s"
        '<p class="note">the easy one: no password, no cookies, nothing to '
        "install. Sleeper's read-only API takes a username - THEIRS, the "
        "@handle in their app under Settings &rarr; Username.</p>"
        '<div class="formrow">'
        '<label>username <input type="text" id="sl-user" size="20" '
        'placeholder="their_sleeper_name" autocomplete="off"></label>'
        '<button onclick="slLookup()">Find my leagues</button></div>'
        '<p id="sl-res" class="note"></p>'
        '<div id="sl-leagues"></div>'
        '<p class="note">Import creates that league\'s config '
        '(<code class="mini">leagues/&lt;id&gt;.yaml</code>), roster file '
        "and rankings csv, and files the league under the selected person "
        "- it lists exactly what it wrote.</p>"
        % (_card_head("sleeper", entry), _person_blocks(people, "sleeper"))))


def render_espn_card(entry: Dict,
                     people: Optional[List[Dict]] = None) -> str:
    # SECURITY: the two secret fields are always rendered EMPTY
    # (type=password, no value attribute, autocomplete off) - existing
    # cookie values are never read back into the page. They are also for
    # the OWNER'S OWN account only; the person-safe routes are above them.
    return _sec("card-espn", "ESPN", (
        "%s%s"
        '<p class="note bad">Never ask someone else for their ESPN '
        "cookies. espn_s2 and SWID are whole-account Disney session "
        "credentials, not fantasy-scoped - handing them over signs the "
        "other person up for more than a roster read, and breaks their own "
        "terms with ESPN. Two routes below work without them.</p>"
        '<p class="note"><b>Route 1 &mdash; their league id.</b> Ask them '
        "to open League Settings and set visibility so anyone can view the "
        "league, then send you the number after "
        '<code class="mini">leagueId=</code> in their league URL. This '
        "checks honestly whether ESPN will show it to a logged-out "
        "reader.</p>"
        '<div class="formrow">'
        '<label>league id <input type="text" id="espn-pub-lid" size="12" '
        'placeholder="1234567" autocomplete="off"></label>'
        '<label>their team <input type="text" id="espn-pub-team" size="16" '
        'placeholder="team id or name" autocomplete="off"></label>'
        '<button onclick="espnCheck()">Check if readable</button>'
        '<button onclick="espnImport()">Import for this person</button>'
        "</div>"
        '<p id="espn-pub-res" class="note"></p>'
        '<div id="espn-pub-teams"></div>'
        '<p class="note">Check first: it lists every team in the league so '
        "you can ask which one is theirs. Nothing guesses that.</p>"
        '<p class="note"><b>Route 2 &mdash; they paste their roster.</b> '
        "Equal standing, not a fallback: a private league stays private and "
        "their team still gets read. Ask them to copy their roster page and "
        "send it to you; paste it here. The league id is still needed - it "
        "names the files, so the same league updates in place instead of "
        "piling up copies.</p>"
        '<div class="formrow">'
        '<label>their league id <input type="text" id="espn-paste-lid" '
        'size="12" placeholder="1234567" autocomplete="off"></label>'
        '<label>their team <input type="text" id="espn-paste-team" '
        'size="16" placeholder="team name" autocomplete="off"></label>'
        '<button onclick="espnPaste()">Import from paste</button></div>'
        '<textarea id="espn-paste-text" placeholder="paste their roster '
        'page - team name line, then player lines"></textarea>'
        '<p id="espn-paste-res" class="note"></p>'
        '<hr class="mp-rule">'
        '<p class="note"><b>Your own ESPN league only.</b> The cookie copy '
        "below is for the account sitting at this Mac. It is how YOU connect "
        "YOUR league, and it is the thing that does not scale to anyone "
        "else.</p>"
        '<p class="note">30-second cookie copy (done once; they expire '
        "when you log out of ESPN): <b>1)</b> log in at fantasy.espn.com "
        "and open your league &mdash; the number after "
        '<code class="mini">leagueId=</code> in the URL is your '
        "league_id. <b>2)</b> open DevTools (F12, or Cmd-Opt-I on a Mac) "
        "&rarr; <b>Application</b> tab &rarr; <b>Cookies</b> &rarr; "
        "the espn.com entry. <b>3)</b> copy the values of "
        '<code class="mini">espn_s2</code> (very long) and '
        '<code class="mini">SWID</code> (keep the curly braces; added '
        "for you if you miss them).</p>"
        '<div class="formrow">'
        '<label>league_id <input type="text" id="espn-lid" size="12" '
        'placeholder="1234567" autocomplete="off"></label>'
        '<label>espn_s2 <input type="password" id="espn-s2" size="26" '
        'placeholder="paste cookie value" autocomplete="off"></label>'
        '<label>SWID <input type="password" id="espn-swid" size="20" '
        'placeholder="{...}" autocomplete="off"></label>'
        '<button onclick="espnSave()">Save &amp; test</button></div>'
        '<p id="espn-res" class="note"></p>'
        '<p class="note">saved to <code class="mini">'
        "data/espn_secrets.json</code> (file mode 0600, written "
        "atomically). Saved values are never shown here again - on "
        "success you only see the league name the live check found.</p>"
        % (_card_head("espn", entry), _person_blocks(people, "espn"))))


def render_yahoo_card(entry: Dict,
                      people: Optional[List[Dict]] = None) -> str:
    stage = (entry.get("stage") or "").strip().lower()
    keys = [k for k, _ in YAHOO_STAGES]
    here = keys.index(stage) if stage in keys else -1
    items = []
    for i, (key, text) in enumerate(YAHOO_STAGES):
        cls, mark = "", ""
        if here >= 0 and i < here:
            cls, mark = ' class="done"', " &#10003;"
        elif i == here:
            cls = ' class="here"'
            mark = (" " + _chip("dash", "you are here")
                    if key != "connected" else "")
        items.append("<li%s>%s%s</li>" % (cls, _esc(text), mark))
    return _sec("card-yahoo", "Yahoo", (
        "%s%s"
        '<p class="note"><b>Consent, not credentials.</b> Generate a link, '
        "send it to them, and they approve inside Yahoo's own screen. They "
        "read back a short code; that code is used once and never stored. "
        "The scope is read-only - the app can see their league and cannot "
        "touch their team. Never ask for their Yahoo password.</p>"
        '<div class="formrow">'
        '<button onclick="yaLink()">Generate consent link</button>'
        '<input type="text" id="ya-url" size="46" readonly '
        'placeholder="the link to send them appears here" '
        'aria-label="consent link to send"></div>'
        '<p id="ya-link-res" class="note"></p>'
        '<div class="formrow">'
        '<label>code they read back <input type="text" id="ya-code" '
        'size="18" placeholder="short code" autocomplete="off"></label>'
        '<button onclick="yaFinish()">Finish &amp; list their leagues'
        "</button></div>"
        '<p id="ya-res" class="note"></p>'
        '<div id="ya-leagues"></div>'
        '<hr class="mp-rule">'
        '<p class="note"><b>Your own Yahoo league.</b> Yours still runs '
        "through the one-time handshake in a terminal (a browser window "
        "opens for Yahoo's consent screen - honestly, this panel cannot "
        "click that for you). The stages:</p>"
        '<ol class="steps">%s</ol>'
        % (_card_head("yahoo", entry), _person_blocks(people, "yahoo"),
           "".join(items))))


def _coverage_chip(row: Dict) -> str:
    return _chip("fill" if row.get("complete") else "dash", row.get("text"))


def render_league_rosters_card(leagues: Optional[List[Dict]]) -> str:
    """Coverage per league + the paste box for leagues no API can read.

    Pure: `leagues` is engine.leagueview.coverage_rows() output (None =
    the module or the listing was unavailable, rendered as an honest
    empty state rather than a broken card).
    """
    if leagues is None:
        body = ('<p class="note bad">roster coverage unavailable - '
                "engine/leagueview.py could not be read. The rest of this "
                "page is unaffected.</p>")
        select, controls = "", ""
    elif not leagues:
        body = ('<p class="note warn">no leagues configured yet - import '
                "one above, or drop a config into "
                '<code class="mini">leagues/</code>.</p>')
        select, controls = "", ""
    else:
        rows = []
        for lg in leagues:
            layers = ", ".join(
                "%s%s (%d)" % (_esc(t.get("name") or "?"),
                               " &#9733;" if t.get("mine") else "",
                               int(t.get("count") or 0))
                for t in (lg.get("teams") or [])) or "nothing known yet"
            sources = sorted(set(str(t.get("source_label") or "")
                                 for t in (lg.get("teams") or []) if t.get("count")))
            rows.append(
                '<tr><td><span class="who">%s <span class="meta">%s'
                '</span></span><div class="why">%s</div></td>'
                '<td>%s</td><td class="why">%s</td></tr>'
                % (_esc(lg.get("name")), _esc(lg.get("id")), layers,
                   _coverage_chip(lg),
                   _esc(", ".join(sources)) or "&mdash;"))
        body = ('<div class="wr-scroll"><table class="wr-table mp-table">'
                "<thead><tr><th>league</th><th>rosters known</th><th>from</th>"
                "</tr></thead><tbody>%s</tbody></table></div>" % "".join(rows))
        select = "".join('<option value="%s">%s (%s)</option>'
                         % (_esc(lg.get("id")), _esc(lg.get("name")),
                            _esc(lg.get("text")))
                         for lg in leagues)
        controls = (
            '<div class="formrow">'
            '<label>league <select id="lr-league">%s</select></label>'
            '<button onclick="previewLeague()">Preview paste</button>'
            '<button class="primary" id="lr-save" '
            'onclick="saveLeague()" disabled>Save to store</button></div>'
            '<textarea id="lr-text" placeholder="paste one team\'s roster '
            "or the whole league-rosters page - team name lines followed by "
            "player lines; slot labels, byes, injury tags and kickoff times "
            'are fine"></textarea>'
            '<p id="lr-res" class="note"></p>'
            '<div id="lr-preview"></div>' % select)
    return _sec("card-league-rosters", "League rosters", (
        '<p class="note">who holds what, for trade targets and waiver '
        "competition. ESPN's draft capture fills The Original 8 by itself; "
        "Yahoo is not API-readable, so the other rosters only exist here if "
        "you paste them. Precedence per team: draft capture &gt; pasted "
        "store &gt; your own roster file.</p>%s%s"
        '<p class="note">Preview parses and shows every team, every '
        "matched player and every line it could NOT match &mdash; it writes "
        "nothing. Nothing is ever invented: an unmatched line is reported "
        "for you to fix, never guessed onto a roster. Save writes "
        '<code class="mini">data/league-&lt;id&gt;.json</code>.</p>'
        % (body, controls)))


def render_leagues_section(status: Optional[Dict[str, Dict]],
                           leagues: Optional[List[Dict]] = None,
                           people: Optional[List[Dict]] = None) -> str:
    """The Leagues tab: pick a person, then one card per platform.

    `people` is engine.connections.people_status() output - one coverage
    dict per person. [] or None renders the honest empty state and every
    card still explains its route, so the panel teaches the flow before
    anybody is on file.
    """
    status = status or {}
    empty = {"connected": False, "leagues": [], "stage": "",
             "next_step": "status unavailable"}
    return "\n".join([
        render_person_card(people),
        render_sleeper_card(status.get("sleeper") or dict(empty), people),
        render_espn_card(status.get("espn") or dict(empty), people),
        render_yahoo_card(status.get("yahoo") or dict(empty), people),
        render_league_rosters_card(leagues),
    ])


def render_input_row(s: Dict) -> str:
    """One model input: nameplate (face, name, live weight, handle), type
    tag, the enable switch, the weight slider paired with its number box,
    the live share, and fetch-now. The script keeps slider and number in
    step and rewrites the nameplate's weight as either moves."""
    sid = str(s.get("id", ""))
    name = str(s.get("name") or sid)
    handle = str(s.get("handle", ""))
    # built-in feeds carry handle == id - repeating it is noise
    sub = wr.trim(handle, 60) if handle and handle != sid else None
    fetchable = s.get("type") in ("youtube", "rss", "url", "feed")
    fetch_cell = (
        '<button onclick="fetchNow(this)">fetch now</button>'
        '<div class="fres note"></div>' if fetchable else
        '<span class="note">paste-only</span>')
    try:
        w = int(s.get("weight") or 0)
    except (TypeError, ValueError):
        w = 0
    w = max(0, min(100, w))
    on = bool(s.get("enabled"))
    return (
        '<tr class="src%s" data-id="%s">'
        '<td><input type="checkbox" class="sel" aria-label="select %s"></td>'
        "<td>%s</td>"
        "<td>%s</td>"
        '<td><label class="mp-switch"><input type="checkbox" class="en"%s '
        'aria-label="%s enabled"><span class="mp-switch-t" aria-hidden="true">'
        "</span><span>on</span></label></td>"
        '<td class="mp-wcell"><input type="range" class="w" min="0" max="100" '
        'step="1" value="%d" aria-label="weight for %s"> '
        '<input type="number" class="wn wr-num" min="0" max="100" step="1" '
        'value="%d" aria-label="weight for %s, as a number"></td>'
        '<td class="num share wr-num">&mdash;</td>'
        "<td>%s</td></tr>"
        % ("" if on else " off", _esc(sid), _esc(name),
           wr.nameplate(s, weight=w, size=36, sub=sub),
           _type_tag(str(s.get("type", ""))),
           " checked" if on else "", _esc(name),
           w, _esc(name), w, _esc(name), fetch_cell))


def render_page(rows: List[Dict], registry_path: str,
                status: Optional[Dict[str, Dict]] = None,
                leagues: Optional[List[Dict]] = None,
                nav_leagues=(), week: Optional[int] = None,
                people: Optional[List[Dict]] = None) -> str:
    """The whole panel as one self-contained HTML string (pure).

    `nav_leagues` = [(id, name)] for the shell's league switcher and `week`
    for its WK badge; both optional - the panel is league-agnostic.
    """
    enabled = [s for s in rows if s.get("enabled")]
    table = (
        '<div class="wr-scroll"><table class="wr-table mp-table mp-inputs">'
        '<thead><tr><th><input type="checkbox" onchange="selAll(this)" '
        'aria-label="select every input"></th>'
        "<th>input</th><th>type</th><th>on</th>"
        '<th>weight (0-100)</th><th class="num">share</th>'
        "<th>fetch</th></tr></thead><tbody>%s</tbody></table></div>"
        % "".join(render_input_row(s) for s in rows))

    registry_card = _sec("card-inputs", "Source registry", (
        '<p class="note">share = weight / sum of ENABLED weights &mdash; '
        "the exact normalization consensus applies. Weights are relative, "
        "not percentages.</p>%s"
        '<div class="mp-sum">enabled weight <b id="tot" class="wr-num">0</b>'
        '<span class="note">weights normalize &mdash; the total can be any '
        "number; only each input's share of it reaches the verdict.</span>"
        "</div>"
        '<div class="bulkbar">with selected: '
        '<button onclick="bulk(true)">enable</button>'
        '<button onclick="bulk(false)">disable</button></div>'
        '<div class="savebar"><button class="primary" '
        'onclick="save()">Save registry</button>'
        '<span id="savestate" class="note">saved state on disk shown; '
        "nothing is written until you press Save.</span></div>"
        '<p class="note">faces: <code>python -m engine.sources --avatars'
        "</code> fetches a picture for every enabled youtube/rss input "
        "(a new source gets one on add, best effort); anything without one "
        "wears its monogram.</p>"
        % table), count_note="%d sources, %d enabled" % (len(rows),
                                                         len(enabled)))

    add_card = _sec("card-add", "Add source", (
        '<div class="formrow">'
        '<label>name <input type="text" id="add-name" size="22" '
        'placeholder="Display Name"></label>'
        '<label>URL / handle <input type="text" id="add-handle" '
        'size="34" placeholder="https://…"></label>'
        '<label>type <select id="add-type">'
        '<option value="auto">auto</option>'
        "<option>youtube</option><option>rss</option>"
        "<option>url</option><option>paste</option></select></label>"
        '<button onclick="addSource()">Add</button>'
        '<span id="add-guess" class="note"></span></div>'
        '<p id="add-res" class="note"></p>'
        '<p class="note">new sources start enabled at weight %d. '
        "X/Twitter is paste-only (their ToS forbid scraping) &mdash; "
        "an x.com handle auto-guesses to 'paste'.</p>"
        % DEFAULT_WEIGHT))

    opts = "".join('<option value="%s">%s (%s)</option>'
                   % (_esc(s.get("id", "")), _esc(s.get("name", "")),
                      _esc(s.get("id", ""))) for s in rows)
    paste_card = _sec("card-paste", "Paste creator content", (
        '<div class="formrow"><label>source <select id="paste-src">%s'
        "</select></label>"
        '<label>where it came from <input type="text" id="paste-url" '
        'size="28" placeholder="URL (optional)"></label>'
        '<button onclick="storePaste()">Store paste</button></div>'
        '<textarea id="paste-text" placeholder="paste a transcript, '
        'article, tweet text, rankings blob …"></textarea>'
        '<p id="paste-res" class="note"></p>'
        '<p class="note">stored raw in the creator-calls paste store; '
        "call extraction is crude on purpose, so every auto-extracted call "
        "later carries a confidence + quote. This is also the ONLY door "
        "for X/Twitter content.</p>"
        % opts))

    footer = (
        '<footer class="mp-foot">write surface &mdash; inputs tab: '
        "<code>data/sources.yaml</code> &middot; <code>data/cache/</code> "
        "&middot; the creator-calls paste store (guard_write); leagues "
        "tab: <code>%s</code> (guard_scoped_write) &mdash; nothing else, "
        "enforced in engine/sources_ui.py. Server: 127.0.0.1 only, "
        "Ctrl-C to stop.<br>"
        "registry: <code>%s</code></footer>"
        % (_esc(LEAGUE_SCOPE), _esc(registry_path)))

    tabbar = (
        '<div class="mp-tabbar" role="tablist" aria-label="panel">'
        '<button id="tab-model" class="mp-tab active" role="tab" '
        'aria-selected="true" aria-controls="pane-model" '
        'onclick="showTab(\'model\')">Inputs</button>'
        '<button id="tab-leagues" class="mp-tab" role="tab" '
        'aria-selected="false" aria-controls="pane-leagues" '
        'onclick="showTab(\'leagues\')">Leagues</button></div>')
    model_pane = ('<div id="pane-model" role="tabpanel">\n%s\n%s\n%s\n</div>'
                  % (registry_card, add_card, paste_card))
    leagues_pane = ('<div id="pane-leagues" role="tabpanel" hidden>\n%s\n</div>'
                    % render_leagues_section(status, leagues, people))

    shell = wr.shell("model", None, week, list(nav_leagues or ()))
    masthead = (
        '<header class="mp-mast"><p class="wr-kicker">Model Settings</p>'
        '<h1 class="wr-h1 wr-display">Your model</h1>'
        '<p class="wr-lede">your inputs, your weights, your formula '
        "&middot; %d inputs &middot; %d enabled</p></header>"
        % (len(rows), len(enabled)))

    return (
        '<!doctype html>\n<html lang="en"><head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        "<title>Model Settings</title>\n"
        "%s\n</head><body>\n"
        '%s\n<main class="wr-page">\n%s\n'
        '<section class="wr-card">\n%s\n%s\n%s\n</section>\n%s\n</main>\n'
        "<script>%s</script>\n</body></html>\n"
        % (_style_tag(), shell, masthead, tabbar, model_pane, leagues_pane,
           footer, _JS))


# --- server -----------------------------------------------------------------

class SourcesServer(HTTPServer):
    """HTTPServer carrying the panel config (registry path, write roots)."""

    def __init__(self, addr, handler, registry_path: str,
                 data_root: Optional[str] = None):
        HTTPServer.__init__(self, addr, handler)
        self.registry_path = registry_path
        # Project root the LEAGUES tab writes under (guard_scoped_write
        # fences it to LEAGUE_SCOPE) - tests point it at a tempdir.
        self.data_root = data_root or HERE
        # The sources-tab write surface. The registry file itself, the
        # shared feed caches, and the creator-calls paste store
        # (redirected in tests along with the registry via
        # engine.sources module paths).
        self.write_roots = [
            registry_path,
            sources_mod.CACHE_DIR,      # feed caches + the paste store
            os.path.join(HERE, "data", "creator_calls"),
        ]


class Handler(BaseHTTPRequestHandler):
    server_version = "WarRoomSources/1.0"

    # -- plumbing ------------------------------------------------------------

    def log_message(self, fmt, *args):  # quiet: tests and normal use
        if os.environ.get("SOURCES_UI_DEBUG"):
            BaseHTTPRequestHandler.log_message(self, fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "bad Content-Length"
        if n <= 0 or n > 2 * 1024 * 1024:
            return None, "body required (max 2MB)"
        try:
            obj = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return None, "invalid JSON: %s" % exc
        if not isinstance(obj, dict):
            return None, "JSON object required"
        return obj, None

    def _registry(self) -> List[Dict]:
        return _load_registry(self.server.registry_path)

    # -- routes --------------------------------------------------------------

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = render_page(self._registry(), self.server.registry_path,
                               status=connection_status(),
                               leagues=league_rows(self.server.data_root),
                               nav_leagues=shell_leagues(self.server.data_root),
                               week=week_hint(), people=people_rows())
            self._send(200, page.encode("utf-8"),
                       "text/html; charset=utf-8")
        elif self.path == "/state":
            self._json({"ok": True, "sources": self._registry(),
                        "registry": self.server.registry_path})
        elif _STATIC_PAGE_RE.match(self.path.lstrip("/")):
            self._serve_page(self.path.lstrip("/"))
        else:
            self._send(404, b"not found", "text/plain")

    def _serve_page(self, name: str) -> None:
        """A sibling static page (the shell's nav targets), READ-ONLY from
        the project root. Not generated yet -> 404 naming the command that
        makes it, never a bare miss."""
        path = os.path.join(self.server.data_root, name)
        if not os.path.isfile(path):
            self._send(404, ("%s is not generated yet - ./home.sh, "
                             "./board.sh <league> <week> or ./season.sh "
                             "<league> <week> writes it" % name)
                       .encode("utf-8"), "text/plain; charset=utf-8")
            return
        with open(path, "rb") as fh:
            body = fh.read()
        self._send(200, body, "text/html; charset=utf-8")

    def do_POST(self):
        route = {"/save": self._post_save, "/add": self._post_add,
                 "/paste": self._post_paste, "/fetch": self._post_fetch,
                 "/person/add": self._post_person_add,
                 "/sleeper/lookup": self._post_sleeper_lookup,
                 "/sleeper/import": self._post_sleeper_import,
                 "/espn/save": self._post_espn_save,
                 "/espn/check": self._post_espn_check,
                 "/espn/import": self._post_espn_import,
                 "/espn/paste": self._post_espn_paste,
                 "/yahoo/link": self._post_yahoo_link,
                 "/yahoo/code": self._post_yahoo_code,
                 "/yahoo/import": self._post_yahoo_import,
                 "/league/preview": self._post_league_preview,
                 "/league/save": self._post_league_save,
                 }.get(self.path)
        if route is None:
            self._json({"ok": False, "error": "no such endpoint"}, 404)
            return
        body, err = self._read_json()
        if err:
            self._json({"ok": False, "error": err}, 400)
            return
        try:
            route(body)
        except PermissionError as exc:      # guard_write tripped
            self._json({"ok": False, "error": str(exc)}, 403)
        except Exception as exc:  # noqa: BLE001 - shown verbatim, honest
            self._json({"ok": False,
                        "error": "%s: %s" % (type(exc).__name__, exc)}, 500)

    # -- POST handlers (validate FIRST, write through helpers only) ----------

    def _post_save(self, body: Dict) -> None:
        merged, err = apply_updates(self._registry(), body.get("sources"))
        if err:
            self._json({"ok": False, "error": err}, 400)
            return
        _save_registry(merged, self.server.registry_path,
                       self.server.write_roots)
        self._json({
            "ok": True, "sources": len(merged),
            "enabled": sum(1 for s in merged if s.get("enabled")),
            "enabled_weight": sum(int(s.get("weight", 0)) for s in merged
                                  if s.get("enabled")),
            "registry": self.server.registry_path,
            "at": datetime.now().strftime("%H:%M:%S"),
        })

    def _post_add(self, body: Dict) -> None:
        existing = self._registry()
        entry, err = new_source_entry(existing, body.get("name", ""),
                                      body.get("handle", ""),
                                      body.get("type", ""))
        if err:
            self._json({"ok": False, "error": err}, 400)
            return
        _save_registry(existing + [entry], self.server.registry_path,
                       self.server.write_roots)
        # A face for the new voice, best effort: the add is already on
        # disk, and no avatar failure - network, parse, size - undoes it.
        try:
            avatar, avatar_note = _avatar_after_add(entry)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            avatar, avatar_note = None, "avatar fetch failed: %s: %s" % (
                type(exc).__name__, exc)
        self._json({"ok": True, "added": entry,
                    "sources": len(existing) + 1,
                    "avatar": _rel_to(avatar, HERE) if avatar else None,
                    "avatar_note": avatar_note})

    def _post_paste(self, body: Dict) -> None:
        sid = body.get("source")
        text = (body.get("text") or "").strip()
        url = (body.get("url") or "").strip()
        if not any(s.get("id") == sid for s in self._registry()):
            self._json({"ok": False, "error": "unknown source id: %r" % sid},
                       400)
            return
        if not text:
            self._json({"ok": False, "error": "paste text is empty"}, 400)
            return
        item = _add_paste(sid, text, url)
        self._json({"ok": True, "source": sid, "chars": len(text),
                    "title": item.get("title", ""),
                    "published": item.get("published", "")})

    def _post_fetch(self, body: Dict) -> None:
        sid = body.get("id")
        src = next((s for s in self._registry() if s.get("id") == sid), None)
        if src is None:
            self._json({"ok": False, "error": "unknown source id: %r" % sid},
                       400)
            return
        if src.get("type") == "paste":
            self._json({"ok": False,
                        "error": "paste-only source - nothing to fetch "
                                 "(X/Twitter scraping is off the table: "
                                 "ToS)"}, 400)
            return
        if src.get("type") == "feed":
            self._json({"ok": True, "items": 0,
                        "note": "built-in feed - consensus reads it "
                                "directly, nothing fetched here"})
            return
        try:
            items = _fetch_source(src)
        except Exception as exc:  # noqa: BLE001 - the row shows the error
            self._json({"ok": False,
                        "error": "%s: %s" % (type(exc).__name__, exc)})
            return
        stale = sum(1 for it in items if isinstance(it, dict)
                    and it.get("stale"))
        note = ("STALE cache - live fetch failed" if stale else "")
        self._json({"ok": True, "items": len(items), "note": note})

    # -- leagues-tab handlers (connections contract: module docstring) -------

    def _conn_or_none(self):
        mod = _connections()
        if mod is None:
            self._json({"ok": False,
                        "error": "engine/connections.py is not available "
                                 "yet - the platform bridge ships "
                                 "separately"}, 501)
        return mod

    def _post_sleeper_lookup(self, body: Dict) -> None:
        username = str(body.get("username") or "").strip()
        if (not username or len(username) > 64
                or any(ch.isspace() for ch in username)):
            self._json({"ok": False,
                        "error": "enter a Sleeper username (no spaces)"},
                       400)
            return
        mod = self._conn_or_none()
        if mod is None:
            return
        try:
            result = _sleeper_lookup(mod, username)
        except Exception as exc:  # noqa: BLE001 - unknown user etc, inline
            self._json({"ok": False, "error": str(exc) or
                        "lookup failed for '%s'" % username}, 400)
            return
        self._json({"ok": True,
                    "username": str(result.get("username") or username),
                    "user_id": str(result.get("user_id") or ""),
                    "leagues": normalize_leagues(result)})

    # -- the person layer ----------------------------------------------------

    def _person_arg(self, body: Dict, required: bool = True):
        """The selected person's key, validated, or None after answering.

        Keys are the directory-safe slug connections.person_key() makes, so
        anything outside a-z 0-9 . _ - is refused before it reaches a
        lookup - a page can only ever name a person, never a path.
        """
        key = str(body.get("person") or "").strip().lower()
        if not key:
            if not required:
                return ""
            self._json({"ok": False,
                        "error": "pick the person you are onboarding first "
                                 "- everything on this card acts on them"},
                       400)
            return None
        if len(key) > 64 or not all(ch.isalnum() or ch in "-._"
                                    for ch in key):
            self._json({"ok": False,
                        "error": "that is not a person key"}, 400)
            return None
        return key

    def _bless_created(self, result) -> List[Dict]:
        """Re-guard every path a platform module reports having created.

        The leagues write surface, enforced at THIS seat too: a rogue path
        raises PermissionError -> do_POST answers 403, loudly. A reported
        credential file is refused outright even though the ESPN card may
        legitimately write one from its own handler - an IMPORT has no
        business creating secrets, and a module claiming it did is a bug
        worth stopping on.
        """
        created = normalize_created(result)
        for c in created:
            base = os.path.basename(c["path"]).lower()
            if "secret" in base or "token" in base:
                raise PermissionError(
                    "an import reported writing a credential file (%s); "
                    "refusing to bless it" % c["path"])
            guard_scoped_write(c["path"], self.server.data_root)
            c["path"] = _rel_to(c["path"], self.server.data_root)
        return created

    def _person_import_reply(self, result, fallback: str = "") -> None:
        """The shared answer for every per-person import."""
        created = self._bless_created(result)
        result = result if isinstance(result, dict) else {}
        self._json({"ok": True,
                    "person": str(result.get("person") or ""),
                    "league": str(result.get("name")
                                  or result.get("league") or fallback),
                    "league_id": str(result.get("league_id")
                                     or result.get("config_id") or ""),
                    "created": created})

    def _post_person_add(self, body: Dict) -> None:
        mod = self._conn_or_none()
        if mod is None:
            return
        if not hasattr(mod, "add_person"):
            self._json({"ok": False,
                        "error": "this build of engine/connections.py has no "
                                 "person layer"}, 501)
            return
        name = str(body.get("name") or "").strip()
        email = str(body.get("email") or "").strip()
        if not name or len(name) > 80:
            self._json({"ok": False,
                        "error": "a person needs a name (80 chars or less)"},
                       400)
            return
        try:
            person = mod.add_person(name, email)
        except Exception as exc:  # noqa: BLE001 - shown inline, honest
            self._json({"ok": False, "error": str(exc) or
                        "could not add %s" % name}, 400)
            return
        detail = ""
        try:
            detail = str(mod.coverage(person["key"]).get("next_step") or "")
        except Exception:  # noqa: BLE001 - a hint, never the answer
            detail = ""
        self._json({"ok": True, "person": str(person.get("name") or name),
                    "key": str(person.get("key") or ""),
                    "detail": detail})

    def _post_sleeper_import(self, body: Dict) -> None:
        league_id = str(body.get("league_id") or "").strip()
        user_id = str(body.get("user_id") or "").strip()
        for label, val in (("league_id", league_id), ("user_id", user_id)):
            if (not val
                    or not all(ch.isalnum() or ch in "-_" for ch in val)):
                self._json({"ok": False,
                            "error": "%s must be alphanumeric (dashes/"
                                     "underscores allowed) - use the "
                                     "lookup above first" % label}, 400)
                return
        mod = self._conn_or_none()
        if mod is None:
            return
        # With a person selected the import is filed under them; without
        # one it is the owner's own league, exactly as before.
        person = self._person_arg(body, required=False)
        if person is None:
            return
        if person and hasattr(mod, "add_league_for"):
            try:
                result = mod.add_league_for(person, "sleeper",
                                            league_id=league_id,
                                            user_id=user_id)
            except PermissionError:
                raise
            except Exception as exc:  # noqa: BLE001 - inline and honest
                self._json({"ok": False, "error": str(exc) or
                            "import failed"}, 400)
                return
            self._person_import_reply(result, league_id)
            return
        result = mod.import_league(league_id, user_id)
        created = self._bless_created(result)
        name, local_id = "", ""
        if isinstance(result, dict):
            name = str(result.get("name") or result.get("league") or "")
            local_id = str(result.get("config_id")
                           or result.get("league_id") or "")
        self._json({"ok": True, "league": name or league_id,
                    "league_id": local_id, "created": created,
                    "person": ""})

    # -- ESPN, the two person-safe routes (never a friend's cookies) ---------

    def _post_espn_check(self, body: Dict) -> None:
        league_id = str(body.get("league_id") or "").strip()
        if not league_id.isdigit() or len(league_id) > 24:
            self._json({"ok": False,
                        "error": "an ESPN league id is the number after "
                                 "leagueId= in their league URL"}, 400)
            return
        mod = self._conn_or_none()
        if mod is None:
            return
        try:
            res = mod.espn_public_check(league_id)
        except Exception as exc:  # noqa: BLE001 - the reason IS the answer
            self._json({"ok": False, "error": "%s: %s"
                        % (type(exc).__name__, exc)}, 400)
            return
        res = res if isinstance(res, dict) else {}
        self._json({"ok": True, "readable": bool(res.get("readable")),
                    "league_id": league_id,
                    "name": str(res.get("name") or ""),
                    "teams": res.get("teams"),
                    "kind": str(res.get("kind") or ""),
                    "roster": [{"team_id": str(t.get("team_id") or ""),
                                "name": str(t.get("name") or "?")}
                               for t in (res.get("roster") or [])
                               if isinstance(t, dict)],
                    "detail": str(res.get("detail") or "")})

    def _post_espn_import(self, body: Dict) -> None:
        person = self._person_arg(body)
        if person is None:
            return
        league_id = str(body.get("league_id") or "").strip()
        if not league_id.isdigit() or len(league_id) > 24:
            self._json({"ok": False,
                        "error": "an ESPN league id is the number after "
                                 "leagueId= in their league URL"}, 400)
            return
        self._person_add_league(person, "espn", league_id,
                                league_id=league_id,
                                team=self._team_arg(body))

    @staticmethod
    def _team_arg(body: Dict):
        """Which team is theirs - an id or a name, never guessed.

        Empty means "not said", which the ESPN module answers by listing
        every team rather than picking one.
        """
        team = str(body.get("team") or "").strip()
        return team[:80] or None

    def _post_espn_paste(self, body: Dict) -> None:
        person = self._person_arg(body)
        if person is None:
            return
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            self._json({"ok": False,
                        "error": "paste the roster they sent you first"}, 400)
            return
        league_id = str(body.get("league_id") or "").strip()
        if not league_id.isdigit() or len(league_id) > 24:
            self._json({"ok": False,
                        "error": "a pasted roster still needs their league "
                                 "id (the number after leagueId= in their "
                                 "league URL) - it names the files, so the "
                                 "same league updates in place next time"},
                       400)
            return
        self._person_add_league(person, "espn", league_id,
                                paste=text, league_id=league_id,
                                team=self._team_arg(body))

    # -- Yahoo, by consent: a link out, a short code back --------------------

    def _post_yahoo_link(self, body: Dict) -> None:
        person = self._person_arg(body)
        if person is None:
            return
        mod = self._conn_or_none()
        if mod is None:
            return
        try:
            res = mod.yahoo_consent_link(person)
        except Exception as exc:  # noqa: BLE001 - inline and honest
            self._json({"ok": False, "error": str(exc) or
                        "no consent link"}, 400)
            return
        res = res if isinstance(res, dict) else {}
        url = str(res.get("url") or "")
        # A consent URL carries the app's PUBLIC client id and nothing
        # else. If a secret ever rides along, this page is not showing it.
        low = url.lower()
        if "client_secret" in low or "consumer_secret" in low:
            self._json({"ok": False,
                        "error": "that consent link carries a secret - "
                                 "refusing to display it. engine/yahoo_cli.py "
                                 "should send only the client id."}, 500)
            return
        self._json({"ok": True, "url": url,
                    "person": str(res.get("person") or ""),
                    "ask": str(res.get("ask") or "")})

    def _post_yahoo_code(self, body: Dict) -> None:
        person = self._person_arg(body)
        if person is None:
            return
        code = str(body.get("code") or "").strip()
        if not code or len(code) > 128:
            self._json({"ok": False,
                        "error": "paste the short code they read back from "
                                 "Yahoo"}, 400)
            return
        mod = self._conn_or_none()
        if mod is None:
            return
        try:
            res = mod.yahoo_finish(person, code)
        except Exception as exc:  # noqa: BLE001 - inline and honest
            self._json({"ok": False, "error": str(exc) or
                        "the handshake failed"}, 400)
            return
        res = res if isinstance(res, dict) else {}
        # The code is single-use and never echoed, stored or logged.
        self._json({"ok": True, "person": str(res.get("person") or ""),
                    "leagues": [
                        {"league_key": str(lg.get("league_key") or ""),
                         "name": str(lg.get("name") or "Yahoo league"),
                         "teams": lg.get("teams"),
                         "season": str(lg.get("season") or "")}
                        for lg in (res.get("leagues") or [])
                        if isinstance(lg, dict)]})

    def _post_yahoo_import(self, body: Dict) -> None:
        person = self._person_arg(body)
        if person is None:
            return
        key = str(body.get("league_key") or "").strip()
        if (not key or len(key) > 64
                or not all(ch.isalnum() or ch in "-._" for ch in key)):
            self._json({"ok": False,
                        "error": "pick one of the leagues listed above"}, 400)
            return
        self._person_add_league(person, "yahoo", key, league_key=key)

    def _person_add_league(self, person: str, platform: str,
                           fallback: str, **kw) -> None:
        """add_league_for through the panel: connect, record, re-guard."""
        mod = self._conn_or_none()
        if mod is None:
            return
        if not hasattr(mod, "add_league_for"):
            self._json({"ok": False,
                        "error": "this build of engine/connections.py has no "
                                 "person layer"}, 501)
            return
        try:
            result = mod.add_league_for(person, platform, **kw)
        except PermissionError:
            raise
        except Exception as exc:  # noqa: BLE001 - inline and honest
            self._json({"ok": False, "error": str(exc) or
                        "%s import failed" % platform}, 400)
            return
        self._person_import_reply(result, fallback)

    # -- League rosters card (engine/leagueview.py owns parse+merge+write) ---

    def _league_plan(self, body: Dict):
        """(module, config, parsed, plan, view) for a POSTed paste, or None
        after answering with the reason.

        Both endpoints run THIS - save re-parses the text server-side
        rather than trusting rows from the page, so what Save writes is
        exactly what Preview showed, and a client can never post roster
        rows of its own invention.
        """
        mod = _leagueview()
        if mod is None:
            self._json({"ok": False,
                        "error": "engine/leagueview.py is not available"},
                       501)
            return None
        league_id = str(body.get("league") or "").strip()
        cfg = league_config(mod, self.server.data_root, league_id)
        if cfg is None:
            self._json({"ok": False,
                        "error": "unknown league id: %r - pick one of the "
                                 "leagues listed above" % league_id}, 400)
            return None
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            self._json({"ok": False, "error": "paste some rosters first"},
                       400)
            return None
        matcher = mod.matcher_for(cfg, self.server.data_root)
        if matcher is None:
            self._json({"ok": False,
                        "error": "%s has no rankings board at %s - a paste "
                                 "cannot be matched against the player pool "
                                 "without one"
                                 % (cfg.name, cfg.rankings_csv)}, 400)
            return None
        view = mod.load_league_view(cfg, matcher, self.server.data_root)
        parsed = mod.parse_league_paste(text, matcher, cfg)
        plan = mod.apply_paste(parsed, cfg,
                               mod.load_store(cfg.id, self.server.data_root),
                               view)
        return mod, cfg, parsed, plan, view

    @staticmethod
    def _league_payload(mod, cfg, parsed, plan, view) -> Dict:
        known, expected = mod.coverage_after(plan, cfg, view)
        return {
            "ok": True, "league": cfg.id,
            "before": view.coverage_text(),
            "after": "%d of %d rosters known" % (known, expected),
            "matched": parsed.matched,
            "teams": plan.rows(),
            "refused": [{"team": t, "why": w} for t, w in plan.refused],
            "unmatched": [{"team": t, "line": ln} for t, ln in parsed.unmatched],
            "skipped": len(parsed.skipped),
            "warnings": list(parsed.warnings),
            "contested": ["%s is also on %s in the %s" % c
                          for c in plan.contested]
                         + ["%s moved off %s" % (p, src)
                            for p, src, _dst in plan.moved],
        }

    def _post_league_preview(self, body: Dict) -> None:
        got = self._league_plan(body)
        if got is None:
            return
        mod, cfg, parsed, plan, view = got
        payload = self._league_payload(mod, cfg, parsed, plan, view)
        payload["saved"] = False
        self._json(payload)

    def _post_league_save(self, body: Dict) -> None:
        got = self._league_plan(body)
        if got is None:
            return
        mod, cfg, parsed, plan, view = got
        if not plan.assignments:
            self._json({"ok": False,
                        "error": "nothing to save - no team in that paste "
                                 "produced a single matched player"}, 400)
            return
        dest = mod.store_path(cfg.id, self.server.data_root)
        # The leagues write surface, enforced at this seat too: a store
        # path outside it raises PermissionError -> do_POST answers 403.
        guard_scoped_write(dest, self.server.data_root)
        written = mod.save_store(plan.store, cfg.id, self.server.data_root)
        payload = self._league_payload(mod, cfg, parsed, plan, view)
        payload["saved"] = True
        payload["written"] = plan.teams_written()
        payload["path"] = _rel_to(written, self.server.data_root)
        self._json(payload)

    def _post_espn_save(self, body: Dict) -> None:
        secrets, err = validate_espn_secrets(body)
        if err:
            self._json({"ok": False, "error": err}, 400)
            return
        dest = os.path.join(self.server.data_root, "data",
                            "espn_secrets.json")
        guard_scoped_write(dest, self.server.data_root)
        if not os.path.isdir(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        # Atomic + private: 0600 from the very first byte (os.open mode
        # on the .tmp sibling), then renamed over the destination.
        tmp = dest + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(secrets, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        os.chmod(dest, 0o600)
        # Live check AFTER the save. The response NEVER carries the
        # secret values - only the league name, or the error.
        try:
            name = espn_live_check()
        except Exception as exc:  # noqa: BLE001 - shown verbatim, honest
            self._json({"ok": True, "saved": True, "connected": False,
                        "error": str(exc)})
            return
        self._json({"ok": True, "saved": True, "connected": True,
                    "league": name})


def make_server(port: int = 0, registry_path: Optional[str] = None,
                data_root: Optional[str] = None) -> SourcesServer:
    """Bind a panel server on 127.0.0.1 (never any other interface)."""
    return SourcesServer((BIND, port), Handler,
                         _registry_path(registry_path), data_root)


def pick_server(registry_path: Optional[str] = None,
                port: Optional[int] = None,
                data_root: Optional[str] = None) -> SourcesServer:
    """Try 8787, then neighbors, then any free port (an explicit --port
    is honored or fails - no silent surprise address)."""
    for p in ([port] if port else list(PORTS)):
        try:
            return make_server(p, registry_path, data_root)
        except OSError:
            if port is not None:
                raise
    raise OSError("no free port found")


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.sources_ui",
        description="Local control panel for data/sources.yaml "
                    "(localhost-only http.server).")
    ap.add_argument("--port", type=int, default=None,
                    help="exact port (default: 8787, falling back to a "
                         "free one)")
    ap.add_argument("--registry", default=None,
                    help="registry yaml path (default: data/sources.yaml)")
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open the page in a browser")
    args = ap.parse_args(argv)

    srv = pick_server(args.registry, args.port)
    url = "http://%s:%d/" % (BIND, srv.server_address[1])
    print("Model Settings panel: %s  (registry: %s)"
          % (url, srv.registry_path))
    print("Ctrl-C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
