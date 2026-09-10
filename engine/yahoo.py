"""Yahoo Fantasy connection: ONE registered app, MANY people, read-only.

The old shape of this file assumed one person on one Mac: each user registered
their own Yahoo app and a single data/yahoo_token.json held their tokens. That
is why a friend could not connect. OAuth 2.0 does not work that way and never
did - the app is the *developer's*, the token is the *user's*.

So: the owner registers ONE app (SETUP_YAHOO.md, field by field). Each person
who wants their leagues read grants that app read access through Yahoo's own
consent screen (docs/CONNECT_YAHOO.md). One data/yahoo_secrets.json holds the
app credential; one data/yahoo_tokens/<person>.json holds that person's tokens.

WHAT WE NEVER TAKE
    No password. No session cookie. Nothing but a short-lived authorization
    code the person reads off Yahoo's own screen after consenting, which is
    worthless to anyone who does not hold the app secret. Revocable by the
    person at any time from their Yahoo account (docs/CONNECT_YAHOO.md says
    exactly where).

ADVISE ONLY
    The registered permission is Fantasy Sports -> Read (scope token fspt-r).
    There is no add, drop, claim, or trade call in this module and no POST to
    fantasysports.yahooapis.com at all. A bug here cannot cost anyone a player.

ENDPOINTS AND FACTS (verified against Yahoo docs 2026-09-09)
    authorize  https://api.login.yahoo.com/oauth2/request_auth
    token      https://api.login.yahoo.com/oauth2/get_token
    api        https://fantasysports.yahooapis.com/fantasy/v2
    "The access token has a 1-hour lifetime."  - developer.yahoo.com/oauth2/
    guide/flows_authcode/ ; the refresh token "has a long lifetime" and
    survives a password change.
    "If the user should not be redirected to your server, you should specify
    the callback as `oob` (out of band)."  - same page. That is the whole
    reason this works with no server: Yahoo shows the person a code instead
    of calling back to a host we do not have.

THE 24-HOUR RETENTION RULE - READ THIS BEFORE ADDING A LEDGER
    Yahoo APIs Terms of Use s2.1: "You may not retain or use, and must
    immediately remove from any Application and any data repository in your
    possession or under your control any Yahoo user data obtained through the
    Yahoo APIs that is not explicitly identified as being storable
    indefinitely in the API Documents within 24 hours after the time at which
    you obtained the data".
    Every artifact this module writes therefore carries yahoo_fetched_at and
    yahoo_retention_expires_at, and purge_expired() deletes the ones past
    their clock. Derived output of our own (a grade, a projection, an accuracy
    score) is ours and may persist; a copy of somebody's Yahoo roster is not.

Rate limits: Yahoo publishes no number. Terms of Use preamble: "Yahoo's APIs
may be subject to rate limits at Yahoo's absolute and sole discretion." The
Fantasy portal adds that excessive short-burst usage may be "temporarily
throttle[d] or limit[ed]". We map 429/999 to YahooRateLimited and back off.

CLI: engine/yahoo_cli.py  (./yahoo.sh authorize|finish|leagues|import|check)
"""

import base64
import datetime
import glob
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# Module-level paths so tests can redirect every write into a tempdir
# (tests/mock_draft.py SAVE_DIR discipline). Nothing here writes outside them.
DATA_DIR = os.path.join(HERE, "data")
LEAGUES_DIR = os.path.join(HERE, "leagues")
ROSTERS_DIR = os.path.join(HERE, "data", "rosters")
SECRETS_FILE = os.path.join(HERE, "data", "yahoo_secrets.json")
TOKENS_DIR = os.path.join(HERE, "data", "yahoo_tokens")

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# Fantasy Sports read-only scope. fspt-w is read/WRITE and this project must
# never ask for it - asserted in tests/yahoo_test.py.
SCOPE_READ = "fspt-r"
SCOPE_WRITE = "fspt-w"          # named only so the test can prove we avoid it

OOB = "oob"
SEASON = 2026
GAME_CODE = "nfl"

# Refresh this many seconds BEFORE Yahoo's 1-hour expiry, so a long import
# cannot have a token die halfway through it.
EXPIRY_SKEW_SECONDS = 300
RETENTION_HOURS = 24.0

UA = "WarRoom/1.0 (+read-only fantasy advisor; stdlib urllib)"

PERSON_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# A leading label a person types around the code they were asked to send back:
# "code: k7m2xq9", "Code - k7m2xq9", "my code = k7m2xq9". Anchored, matched
# once, and only when a separator follows, so it can never eat a bare code
# (Yahoo's codes are unpunctuated alphanumerics) or a redirect URL.
_CODE_LABEL = re.compile(r"^(?:my\s+|the\s+)?code\b\s*[:=\-–—]?\s*",
                         re.IGNORECASE)


# --- secret hygiene ---------------------------------------------------------
# Every secret value this process touches is registered here the moment it is
# read or received, and redact() scrubs it out of anything on its way to a
# terminal, a log, an exception message, or a rendered page. YahooError runs
# every message through it, so a token cannot reach a traceback even when it
# came back inside an upstream HTTP error body.

_SENSITIVE = set()


def remember_secret(value) -> None:
    """Register a value that must never be printed. Idempotent, cheap.

    The 6-character floor is deliberate: Yahoo's oob authorization codes run
    about 7-8 characters, so a stricter floor would leave a live code
    printable, while a looser one starts redacting ordinary short words out
    of league names and mangling honest output.
    """
    if isinstance(value, str) and len(value.strip()) >= 6:
        _SENSITIVE.add(value.strip())


def redact(text) -> str:
    """Return text with every registered secret replaced by <redacted>."""
    out = "" if text is None else str(text)
    for secret in sorted(_SENSITIVE, key=len, reverse=True):
        if secret and secret in out:
            out = out.replace(secret, "<redacted>")
    return out


def log(message: str) -> None:
    """The ONE print path in the Yahoo connector. Always redacted."""
    print(redact(message))


# --- typed errors -----------------------------------------------------------

class YahooError(RuntimeError):
    """Base. Scrubs every argument so no subclass can leak a token."""

    def __init__(self, *args):
        super(YahooError, self).__init__(*[redact(a) for a in args])


class YahooSetupError(YahooError):
    """The owner's app credential is missing or malformed."""


class YahooNotConnected(YahooError):
    """This person has no token yet - they have not consented."""


class YahooConsentDenied(YahooError):
    """The person said No on Yahoo's consent screen (error=access_denied)."""


class YahooCodeError(YahooError):
    """The authorization code was wrong, already used, or expired."""


class YahooTokenRevoked(YahooError):
    """The refresh token no longer works - revoked at Yahoo, or expired."""


class YahooRateLimited(YahooError):
    """Yahoo is throttling us (HTTP 429 or Yahoo's 999)."""


class YahooAPIError(YahooError):
    """Any other non-2xx from Yahoo."""


class YahooRetentionError(YahooError):
    """An artifact is past the 24-hour retention clock and must be refetched."""


# --- app credential ---------------------------------------------------------

class AppCredential(object):
    """The OWNER's one registered app. Shared by every person; never printed."""

    __slots__ = ("client_id", "client_secret", "redirect_uri", "scope")

    def __init__(self, client_id, client_secret, redirect_uri=OOB,
                 scope=SCOPE_READ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri or OOB
        self.scope = scope if scope is not None else SCOPE_READ

    def __repr__(self):
        return "<YahooApp redirect=%s scope=%s>" % (self.redirect_uri,
                                                    self.scope or "(app default)")

    __str__ = __repr__

    def basic_auth(self) -> str:
        raw = ("%s:%s" % (self.client_id, self.client_secret)).encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")


def load_app() -> AppCredential:
    """Read data/yahoo_secrets.json - the owner's app, not anyone's password.

    Accepts the OAuth 2.0 names (client_id / client_secret) and the older
    consumer_key / consumer_secret spelling Yahoo still shows on the app page.
    """
    if not os.path.exists(SECRETS_FILE):
        raise YahooSetupError(
            "No %s yet. That file holds the OWNER's one registered Yahoo app "
            "- friends never create one. Follow SETUP_YAHOO.md."
            % _rel(SECRETS_FILE))
    try:
        with open(SECRETS_FILE) as fh:
            raw = json.load(fh)
    except (ValueError, OSError) as exc:
        raise YahooSetupError("%s is unreadable (%s)."
                              % (_rel(SECRETS_FILE), type(exc).__name__))
    if not isinstance(raw, dict):
        raise YahooSetupError("%s must contain a JSON object."
                              % _rel(SECRETS_FILE))

    client_id = raw.get("client_id") or raw.get("consumer_key")
    client_secret = raw.get("client_secret") or raw.get("consumer_secret")
    missing = [n for n, v in (("client_id", client_id),
                              ("client_secret", client_secret)) if not v]
    if missing:
        raise YahooSetupError(
            "%s is missing: %s (SETUP_YAHOO.md step 4 says where Yahoo shows "
            "them)." % (_rel(SECRETS_FILE), ", ".join(missing)))

    remember_secret(client_secret)
    # scope: present-and-empty means "omit it, the app registration already
    # pins Read". See SETUP_YAHOO.md 'If Yahoo rejects the scope'.
    scope = raw.get("scope", SCOPE_READ)
    if scope == SCOPE_WRITE:
        raise YahooSetupError(
            "data/yahoo_secrets.json asks for the read/WRITE scope (%s). This "
            "tool is advise-only and refuses to request write access. Use %s "
            "or remove the key." % (SCOPE_WRITE, SCOPE_READ))
    return AppCredential(str(client_id), str(client_secret),
                         str(raw.get("redirect_uri") or OOB), scope)


def _rel(path: str) -> str:
    try:
        return os.path.relpath(path, HERE)
    except ValueError:
        return path


# --- token storage ----------------------------------------------------------

class Token(object):
    """One person's Yahoo tokens. repr/str deliberately show no values."""

    __slots__ = ("person", "access_token", "refresh_token", "token_type",
                 "expires_at", "obtained_at", "scope", "guid")

    def __init__(self, person, access_token, refresh_token, expires_at,
                 token_type="bearer", obtained_at=None, scope=SCOPE_READ,
                 guid=""):
        self.person = person
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = float(expires_at or 0)
        self.token_type = token_type or "bearer"
        self.obtained_at = float(obtained_at or time.time())
        self.scope = scope or SCOPE_READ
        self.guid = guid or ""
        remember_secret(access_token)
        remember_secret(refresh_token)

    def __repr__(self):
        return ("<YahooToken person=%s scope=%s expires_in=%ds>"
                % (self.person, self.scope, int(self.seconds_left())))

    __str__ = __repr__

    def seconds_left(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def is_expired(self, skew: float = EXPIRY_SKEW_SECONDS) -> bool:
        return time.time() >= (self.expires_at - skew)

    def to_json(self) -> Dict:
        return {"person": self.person,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": self.token_type,
                "expires_at": self.expires_at,
                "obtained_at": self.obtained_at,
                "scope": self.scope,
                "guid": self.guid}


def clean_person(person: str) -> str:
    """A person label is a filename, so it is validated, not trusted."""
    name = (person or "").strip().lower().replace(" ", "-")
    if not PERSON_RE.match(name):
        raise YahooError(
            "Person name %r is not usable as a file name. Use letters, "
            "digits, dashes or underscores (e.g. 'sam' or 'sam-b')." % person)
    return name


def token_path(person: str) -> str:
    return os.path.join(TOKENS_DIR, "%s.json" % clean_person(person))


def pending_path(person: str) -> str:
    return os.path.join(TOKENS_DIR, "%s.pending.json" % clean_person(person))


# Git ignores a directory from a .gitignore placed inside it. The repo root
# .gitignore lists data/yahoo_secrets.json but predates this directory, and
# these are OTHER PEOPLE's tokens - the one file in the project that must
# never be committed by accident. So the directory ships its own ignore rule
# the moment it is created, and does not depend on anyone remembering.
_TOKENS_GITIGNORE = (
    "# Other people's Yahoo OAuth tokens. Never commit, never publish.\n"
    "# Written by engine/yahoo.py when this directory is created.\n"
    "*\n")


def _ensure_tokens_dir(directory: str) -> None:
    os.makedirs(directory, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    guard = os.path.join(directory, ".gitignore")
    if not os.path.exists(guard):
        try:
            with open(guard, "w") as fh:
                fh.write(_TOKENS_GITIGNORE)
        except OSError:
            pass


def _write_private(path: str, text: str) -> None:
    """Atomic write at mode 0600: temp file created private, then renamed.

    The temp file is opened with O_CREAT|O_EXCL and 0600 from the start, so
    the token never exists on disk at a wider mode even for an instant.
    """
    _ensure_tokens_dir(os.path.dirname(path))
    tmp = "%s.%d.tmp" % (path, os.getpid())
    if os.path.exists(tmp):
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def save_token(token: Token) -> str:
    path = token_path(token.person)
    _write_private(path, json.dumps(token.to_json(), indent=2, sort_keys=True))
    return path


def load_token(person: str) -> Token:
    path = token_path(person)
    if not os.path.exists(path):
        raise YahooNotConnected(
            "%s has not connected Yahoo yet. Send them the link from "
            "`./yahoo.sh authorize --person %s` (see docs/CONNECT_YAHOO.md)."
            % (clean_person(person), clean_person(person)))
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except (ValueError, OSError) as exc:
        raise YahooError("Token file for %s is unreadable (%s). Delete it and "
                         "re-run authorize." % (clean_person(person),
                                                type(exc).__name__))
    for key in ("access_token", "refresh_token"):
        if not raw.get(key):
            raise YahooNotConnected(
                "Token file for %s is missing %s - re-run authorize."
                % (clean_person(person), key))
    return Token(person=clean_person(person),
                 access_token=raw["access_token"],
                 refresh_token=raw["refresh_token"],
                 expires_at=raw.get("expires_at") or 0,
                 token_type=raw.get("token_type") or "bearer",
                 obtained_at=raw.get("obtained_at"),
                 scope=raw.get("scope") or SCOPE_READ,
                 guid=raw.get("guid") or "")


def forget_person(person: str) -> List[str]:
    """Delete this person's local tokens. Does NOT revoke at Yahoo."""
    removed = []
    for path in (token_path(person), pending_path(person)):
        if os.path.exists(path):
            os.unlink(path)
            removed.append(path)
    return removed


def connected_people() -> List[Dict]:
    """Who has a token on disk. Values are never included - only facts."""
    out = []
    for path in sorted(glob.glob(os.path.join(TOKENS_DIR, "*.json"))):
        if path.endswith(".pending.json"):
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        entry = {"person": name, "mode": None, "scope": None,
                 "expires_in": None, "readable": False}
        try:
            entry["mode"] = oct(os.stat(path).st_mode & 0o777)
            with open(path) as fh:
                raw = json.load(fh)
            entry["scope"] = raw.get("scope") or SCOPE_READ
            entry["expires_in"] = int(max(
                0.0, float(raw.get("expires_at") or 0) - time.time()))
            entry["readable"] = bool(raw.get("refresh_token"))
        except Exception:
            pass
        out.append(entry)
    return out


# --- OAuth 2.0 --------------------------------------------------------------

def authorize_url(person: str, app: Optional[AppCredential] = None,
                  state: Optional[str] = None) -> Tuple[str, str]:
    """Build the consent URL for one person. Returns (url, state).

    Parameters are exactly the ones Yahoo documents for the authorization code
    flow: client_id, redirect_uri, response_type=code, plus optional state and
    language. `scope` is sent when configured; Yahoo pins Fantasy Read at app
    registration, so omitting it is still read-only (SETUP_YAHOO.md says so).
    """
    app = app or load_app()
    state = state or secrets.token_urlsafe(16)
    params = [("client_id", app.client_id),
              ("redirect_uri", app.redirect_uri),
              ("response_type", "code"),
              ("state", state),
              ("language", "en-us")]
    if app.scope:
        params.insert(3, ("scope", app.scope))
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    _save_pending(person, state, app.redirect_uri)
    return url, state


def _save_pending(person: str, state: str, redirect_uri: str) -> None:
    _write_private(pending_path(person), json.dumps(
        {"person": clean_person(person), "state": state,
         "redirect_uri": redirect_uri, "created_at": time.time()}, indent=2))


def _read_pending(person: str) -> Dict:
    path = pending_path(person)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh) or {}
    except (ValueError, OSError):
        return {}


def parse_code(text: str, expect_state: Optional[str] = None) -> str:
    """Accept what the person actually sends back, in any of its three shapes.

    1. the bare code Yahoo prints on the oob screen
    2. the whole redirect URL, when the app is registered with a real callback
       (nothing is listening on it - the code is simply in the address bar)
    3. a redirect URL carrying error=access_denied, i.e. they said No

    Raising YahooConsentDenied for (3) is the point: 'nothing happened' and
    'they declined' are different answers and the owner should see which.

    A helpful person labels what they send - "code: k7m2xq9", "Code - k7m2xq9"
    - and the label is not part of the code. Stripping it here costs nothing
    and saves a round trip: unstripped it travels all the way to Yahoo and
    comes back as a failed exchange, which reads like the friend did
    something wrong when they did exactly what was asked.
    """
    raw = (text or "").strip().strip("'\"")
    # The label is stripped ONLY from something that is not already a URL or
    # a query string. `code=k7m2xq9&state=...` is a redirect's query, where
    # "code=" is the parameter name and must survive to be parsed below;
    # `code: k7m2xq9` is a person labelling their paste. Deciding the shape
    # first keeps the two apart.
    if not (raw.lower().startswith("http") or "?" in raw or "&" in raw):
        raw = _CODE_LABEL.sub("", raw, count=1).strip().strip("'\"")
    if not raw:
        raise YahooCodeError("No code given. Ask them to re-open the consent "
                             "link and copy the code Yahoo shows.")
    if "?" in raw or "&" in raw or raw.lower().startswith("http"):
        query = raw.split("?", 1)[1] if "?" in raw else raw
        fields = urllib.parse.parse_qs(query, keep_blank_values=True)
        err = (fields.get("error") or [""])[0]
        if err:
            desc = (fields.get("error_description") or [""])[0]
            if err == "access_denied":
                raise YahooConsentDenied(
                    "They declined on Yahoo's consent screen (access_denied). "
                    "Nothing was shared and nothing was stored. They can "
                    "re-open the same link if they change their mind.%s"
                    % (" Yahoo said: %s" % desc if desc else ""))
            raise YahooCodeError("Yahoo returned error=%s%s"
                                 % (err, ": %s" % desc if desc else ""))
        got_state = (fields.get("state") or [""])[0]
        if expect_state and got_state and got_state != expect_state:
            raise YahooCodeError(
                "The state in that link does not match the one we issued for "
                "this person. Re-run authorize and use the fresh link.")
        code = (fields.get("code") or [""])[0]
        if not code:
            raise YahooCodeError("That URL has no code= in it. Copy the whole "
                                 "address bar, or just the code Yahoo shows.")
        raw = code
    remember_secret(raw)
    return raw


def _token_request(app: AppCredential, form: Dict[str, str]) -> Dict:
    """POST to Yahoo's token endpoint with HTTP Basic app auth."""
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Authorization", app.basic_auth())
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _token_http_error(exc, form.get("grant_type", ""))
    except urllib.error.URLError as exc:
        raise YahooAPIError("Could not reach Yahoo's token endpoint (%s). "
                            "Check the network and try again." % exc.reason)
    except ValueError:
        raise YahooAPIError("Yahoo's token endpoint returned something that "
                            "is not JSON.")
    if not payload.get("access_token"):
        raise YahooAPIError("Yahoo's token response had no access_token "
                            "(keys: %s)." % ", ".join(sorted(payload)))
    return payload


def _error_fields(exc: urllib.error.HTTPError) -> Tuple[str, str]:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    code, desc = "", ""
    try:
        doc = json.loads(body)
        if isinstance(doc, dict):
            err = doc.get("error")
            if isinstance(err, dict):
                code = str(err.get("code") or err.get("error") or "")
                desc = str(err.get("description") or err.get("detail") or "")
            else:
                code = str(err or "")
            desc = desc or str(doc.get("error_description") or "")
    except ValueError:
        desc = body[:300]
    return code, redact(desc)


def _token_http_error(exc: urllib.error.HTTPError, grant_type: str) -> YahooError:
    code, desc = _error_fields(exc)
    status = getattr(exc, "code", 0)
    if status in (429, 999):
        return YahooRateLimited("Yahoo is throttling this app (HTTP %s). Wait "
                                "a few minutes and retry." % status)
    if code in ("invalid_client", "unauthorized_client") or status == 401:
        return YahooSetupError(
            "Yahoo rejected the app credential (%s). The client_id/"
            "client_secret in data/yahoo_secrets.json do not match a live "
            "app. Re-check SETUP_YAHOO.md step 4.%s"
            % (code or status, " Yahoo said: %s" % desc if desc else ""))
    if code == "invalid_grant":
        if grant_type == "refresh_token":
            return YahooTokenRevoked(
                "Yahoo rejected the refresh token (invalid_grant). Either "
                "they revoked this app in their Yahoo account, or the token "
                "aged out. Send them a fresh authorize link.%s"
                % (" Yahoo said: %s" % desc if desc else ""))
        return YahooCodeError(
            "Yahoo rejected the authorization code (invalid_grant). Codes are "
            "single-use and expire in minutes - send a fresh authorize link "
            "and have them paste the new code promptly.%s"
            % (" Yahoo said: %s" % desc if desc else ""))
    if code == "invalid_request" and grant_type == "authorization_code":
        return YahooCodeError(
            "Yahoo called the code exchange malformed (invalid_request). The "
            "usual cause is a redirect_uri that does not match the one "
            "registered on the app.%s"
            % (" Yahoo said: %s" % desc if desc else ""))
    return YahooAPIError("Yahoo token endpoint returned HTTP %s%s%s"
                         % (status, " (%s)" % code if code else "",
                            ": %s" % desc if desc else ""))


def _token_from_payload(person: str, payload: Dict,
                        previous: Optional[Token] = None) -> Token:
    expires_in = float(payload.get("expires_in") or 3600)
    refresh = payload.get("refresh_token") or (previous.refresh_token
                                               if previous else "")
    if not refresh:
        raise YahooAPIError("Yahoo returned no refresh_token and we hold none "
                            "for this person - re-run authorize.")
    return Token(person=clean_person(person),
                 access_token=payload["access_token"],
                 refresh_token=refresh,
                 expires_at=time.time() + expires_in,
                 token_type=payload.get("token_type") or "bearer",
                 obtained_at=time.time(),
                 scope=(payload.get("scope")
                        or (previous.scope if previous else SCOPE_READ)),
                 guid=payload.get("xoauth_yahoo_guid")
                 or (previous.guid if previous else ""))


def exchange_code(person: str, code: str,
                  app: Optional[AppCredential] = None) -> Token:
    """Trade the person's one-time authorization code for their tokens."""
    app = app or load_app()
    pending = _read_pending(person)
    code = parse_code(code, expect_state=pending.get("state"))
    redirect_uri = pending.get("redirect_uri") or app.redirect_uri
    payload = _token_request(app, {"grant_type": "authorization_code",
                                   "redirect_uri": redirect_uri,
                                   "code": code})
    token = _token_from_payload(person, payload)
    save_token(token)
    path = pending_path(person)
    if os.path.exists(path):
        os.unlink(path)
    return token


def refresh_token(person: str, app: Optional[AppCredential] = None) -> Token:
    """Swap the refresh token for a new 1-hour access token."""
    app = app or load_app()
    current = load_token(person)
    payload = _token_request(app, {"grant_type": "refresh_token",
                                   "redirect_uri": app.redirect_uri,
                                   "refresh_token": current.refresh_token})
    token = _token_from_payload(person, payload, previous=current)
    save_token(token)
    return token


def valid_token(person: str, app: Optional[AppCredential] = None) -> Token:
    """The person's access token, refreshed first if it is at/near expiry."""
    token = load_token(person)
    if token.is_expired():
        token = refresh_token(person, app=app)
    return token


# --- read-only API ----------------------------------------------------------

def _http_get_json(url: str, bearer: str) -> Dict:
    """One authenticated GET. Isolated so tests replace it with fixtures."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer %s" % bearer)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(person: str, path: str, app: Optional[AppCredential] = None,
            _retried: bool = False) -> Dict:
    """GET a Fantasy resource as this person. Read-only by construction."""
    app = app or load_app()
    token = valid_token(person, app=app)
    sep = "&" if "?" in path else "?"
    url = "%s/%s%sformat=json" % (API_BASE, path.lstrip("/"), sep)
    try:
        return _http_get_json(url, token.access_token)
    except urllib.error.HTTPError as exc:
        status = getattr(exc, "code", 0)
        code, desc = _error_fields(exc)
        if status == 401 and not _retried:
            # 1-hour token died mid-flight, or Yahoo aged it early. One retry
            # after a forced refresh; a second 401 means the grant is gone.
            refresh_token(person, app=app)
            return api_get(person, path, app=app, _retried=True)
        if status == 401:
            raise YahooTokenRevoked(
                "Yahoo still says unauthorized after a fresh token. They have "
                "most likely revoked this app in their Yahoo account. Send a "
                "new authorize link.%s" % (" Yahoo said: %s" % desc if desc
                                           else ""))
        if status in (429, 999):
            raise YahooRateLimited("Yahoo is throttling this app (HTTP %s) on "
                                   "%s. Wait and retry." % (status, path))
        if status == 403:
            raise YahooAPIError(
                "Yahoo refused this read (HTTP 403) on %s. If this app was "
                "only just registered, Fantasy API access also has to be "
                "approved - SETUP_YAHOO.md step 2.%s"
                % (path, " Yahoo said: %s" % desc if desc else ""))
        raise YahooAPIError("Yahoo returned HTTP %s on %s%s"
                            % (status, path, ": %s" % desc if desc else ""))
    except urllib.error.URLError as exc:
        raise YahooAPIError("Could not reach Yahoo (%s) for %s."
                            % (exc.reason, path))
    except ValueError:
        raise YahooAPIError("Yahoo returned non-JSON for %s." % path)


# --- Yahoo's JSON is a nested muddle; these three helpers tame it -----------
# Yahoo mixes objects and positional arrays and numbers collections with
# string keys ("0", "1", ..., "count"). Rather than index by position - which
# breaks the first time Yahoo inserts a field - we search by key.

def _merge_dicts(seq) -> Dict:
    """Merge the dicts in a Yahoo positional array; skip [] padding entries."""
    out = {}
    if isinstance(seq, dict):
        return dict(seq)
    for item in seq or []:
        if isinstance(item, dict):
            out.update(item)
    return out


def _numbered(container, key: str) -> List:
    """{"0": {key: X}, "1": {key: Y}, "count": 2} -> [X, Y]."""
    out = []
    if not isinstance(container, dict):
        return out
    for k in sorted((k for k in container if str(k).isdigit()), key=int):
        item = container[k]
        if isinstance(item, dict) and key in item:
            out.append(item[key])
    return out


def _find_key(node, key: str) -> List:
    """Every value stored under `key` anywhere in the tree, outermost first."""
    found, queue = [], [node]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == key:
                    found.append(v)
                elif isinstance(v, (dict, list)):
                    queue.append(v)
        elif isinstance(cur, list):
            for v in cur:
                if isinstance(v, (dict, list)):
                    queue.append(v)
    return found


# --- league / roster reads --------------------------------------------------

def list_leagues(person: str, app: Optional[AppCredential] = None) -> List[Dict]:
    """This person's current-season NFL leagues.

    game_keys=nfl resolves to the season Yahoo currently considers live, which
    is what we want; archived seasons need an explicit numeric game key.
    """
    payload = api_get(person, "users;use_login=1/games;game_keys=%s/leagues"
                      % GAME_CODE, app=app)
    out = []
    for leagues in _find_key(payload, "leagues"):
        for entry in _numbered(leagues, "league"):
            meta = _merge_dicts(entry)
            if not meta.get("league_key"):
                continue
            out.append({
                "league_key": str(meta["league_key"]),
                "league_id": str(meta.get("league_id")
                                 or str(meta["league_key"]).split(".")[-1]),
                "name": meta.get("name") or "Yahoo league",
                "teams": int(meta.get("num_teams") or 0),
                "season": str(meta.get("season") or SEASON),
                "scoring_type": meta.get("scoring_type") or "",
                "url": meta.get("url") or "",
                "draft_status": meta.get("draft_status") or "",
            })
    # Yahoo can list the same league under more than one game entry.
    seen, unique = set(), []
    for lg in out:
        if lg["league_key"] in seen:
            continue
        seen.add(lg["league_key"])
        unique.append(lg)
    return unique


def league_settings(person: str, league_key: str,
                    app: Optional[AppCredential] = None) -> Tuple[Dict, Dict]:
    """(league metadata, settings) for one league_key like '461.l.1000'."""
    payload = api_get(person, "league/%s/settings" % league_key, app=app)
    league = (payload.get("fantasy_content") or {}).get("league")
    parts = league if isinstance(league, list) else [league]
    meta, settings = {}, {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "settings" in part:
            inner = part["settings"]
            if isinstance(inner, list) and inner:
                settings = _merge_dicts(inner)
            elif isinstance(inner, dict):
                settings = inner
        else:
            meta.update(part)
    if not meta.get("league_key"):
        raise YahooAPIError(
            "Yahoo returned no league for %s. Either that id is wrong or this "
            "person is not in that league." % league_key)
    return meta, settings


def league_teams(person: str, league_key: str,
                 app: Optional[AppCredential] = None) -> List[Dict]:
    """Every team in the league, flattened, with is_owned_by_current_login."""
    payload = api_get(person, "league/%s/teams" % league_key, app=app)
    teams = []
    for coll in _find_key(payload, "teams"):
        for entry in _numbered(coll, "team"):
            inner = entry[0] if (isinstance(entry, list) and entry
                                 and isinstance(entry[0], list)) else entry
            meta = _merge_dicts(inner)
            if meta.get("team_key"):
                teams.append(meta)
    return teams


def my_team_key(person: str, league_key: str,
                app: Optional[AppCredential] = None,
                teams: Optional[List[Dict]] = None) -> str:
    teams = teams if teams is not None else league_teams(person, league_key,
                                                         app=app)
    for team in teams:
        if str(team.get("is_owned_by_current_login") or "0") in ("1", "true"):
            return str(team["team_key"])
    raise YahooAPIError(
        "None of the %d teams in %s is owned by the Yahoo account that "
        "authorized as %s. Did they consent with a different Yahoo login?"
        % (len(teams), league_key, clean_person(person)))


def team_roster(person: str, team_key: str, week: Optional[int] = None,
                app: Optional[AppCredential] = None) -> List[Dict]:
    """One team's roster as plain dicts. Read-only; no lineup call exists."""
    path = "team/%s/roster" % team_key
    if week:
        path = "team/%s/roster;week=%d" % (team_key, int(week))
    payload = api_get(person, path, app=app)
    out = []
    for coll in _find_key(payload, "players"):
        for entry in _numbered(coll, "player"):
            player = _player_from(entry)
            if player:
                out.append(player)
        if out:
            break
    return out


def _player_from(entry) -> Optional[Dict]:
    if not isinstance(entry, list) or not entry:
        return None
    meta = _merge_dicts(entry[0] if isinstance(entry[0], list) else entry)
    name = (meta.get("name") or {}).get("full") if isinstance(
        meta.get("name"), dict) else None
    if not name:
        return None
    display = (meta.get("display_position") or "").upper()
    selected = ""
    for part in entry:
        if isinstance(part, dict) and "selected_position" in part:
            selected = _merge_dicts(part["selected_position"]).get(
                "position") or ""
    eligible = [e.get("position") for e in (meta.get("eligible_positions") or [])
                if isinstance(e, dict) and e.get("position")]
    return {"name": display_name(name, display),
            "yahoo_name": name,
            "position": display,
            "selected_position": selected,
            "eligible_positions": eligible,
            "team": _team_abbr(meta),
            "status": meta.get("status") or ""}


def display_name(full_name: str, position: str) -> str:
    """Yahoo names a defense by its city ('Baltimore'); rankings say 'Defense'.

    data/rosters/*.yaml already spells them 'Baltimore Defense', and
    engine/models.norm_name folds the rest, so this one rule is what lets a
    Yahoo roster match a rankings CSV at all.
    """
    name = (full_name or "").strip()
    if (position or "").upper() in ("DEF", "DST", "D/ST") and name:
        if not name.lower().endswith("defense"):
            return "%s Defense" % name
    return name


def _team_abbr(meta: Dict) -> str:
    abbr = meta.get("editorial_team_abbr")
    if abbr:
        return str(abbr).upper()
    key = str(meta.get("editorial_team_key") or "")
    return key.split(".")[-1].upper() if key else ""


# --- Yahoo settings -> engine artifacts -------------------------------------
# stat_ids confirmed against a live NFL league settings payload's own
# stat_categories block (ids 4/5/6/9/10/11/12/13/15/16/18/57 offence,
# 19-23/29 kicker, 31-37/49-56/82 defence).

STAT_POINTS = {
    5: "passing_td", 6: "interception",
    10: "rushing_td", 11: "reception", 13: "receiving_td",
    15: "return_td", 16: "two_point_conversion", 18: "fumble_lost",
    57: "offensive_fumble_return_td",
}
STAT_PER_YARD = {4: "passing_yards_per_point",
                 9: "rushing_yards_per_point",
                 12: "receiving_yards_per_point"}
STAT_KICKER = {19: "fg_0_19", 20: "fg_20_29", 21: "fg_30_39",
               22: "fg_40_49", 23: "fg_50_plus", 29: "pat_made"}
STAT_DEFENSE = {32: "sack", 33: "interception", 34: "fumble_recovery",
                35: "touchdown", 36: "safety", 37: "block_kick",
                49: "return_td", 50: "points_allowed_0",
                51: "points_allowed_1_6", 52: "points_allowed_7_13",
                53: "points_allowed_14_20", 54: "points_allowed_21_27",
                55: "points_allowed_28_34", 56: "points_allowed_35_plus",
                82: "extra_point_returned"}
# Counting stats with no fantasy value on their own; scored 0 in most leagues
# and never mapped into engine scoring. Listed so they are not reported as
# "unmapped" noise.
STAT_IGNORED = {8, 31, 78}


def _stat_names(settings: Dict) -> Dict[int, str]:
    names = {}
    for entry in ((settings.get("stat_categories") or {}).get("stats") or []):
        stat = entry.get("stat") if isinstance(entry, dict) else None
        if isinstance(stat, dict) and stat.get("stat_id") is not None:
            names[int(stat["stat_id"])] = str(stat.get("name")
                                              or stat.get("display_name") or "")
    return names


def map_scoring(settings: Dict) -> Dict:
    """Yahoo stat_modifiers -> the scoring block leagues/*.yaml already uses.

    Yahoo gives points-per-yard (0.04); the engine's yaml carries
    yards-per-point (25), so those three invert. Anything Yahoo scores that
    we have no name for is kept verbatim under 'unmapped' rather than dropped
    - a silently ignored scoring rule is how advice goes quietly wrong.
    """
    names = _stat_names(settings)
    out = {}
    kicker, defense, unmapped = {}, {}, {}
    mods = (settings.get("stat_modifiers") or {}).get("stats") or []
    for entry in mods:
        stat = entry.get("stat") if isinstance(entry, dict) else None
        if not isinstance(stat, dict) or stat.get("stat_id") is None:
            continue
        try:
            sid = int(stat["stat_id"])
            value = float(stat.get("value"))
        except (TypeError, ValueError):
            continue
        if sid in STAT_PER_YARD:
            # A zero here means the league scores no points for that yardage.
            # Writing 'passing_yards_per_point: 0' would read as "one point
            # per zero yards", the exact opposite, so the key is omitted.
            if value:
                out[STAT_PER_YARD[sid]] = round(1.0 / value, 2)
        elif sid in STAT_POINTS:
            out[STAT_POINTS[sid]] = value
        elif sid in STAT_KICKER:
            kicker[STAT_KICKER[sid]] = value
        elif sid in STAT_DEFENSE:
            defense[STAT_DEFENSE[sid]] = value
        elif sid in STAT_IGNORED:
            continue
        else:
            unmapped["%d (%s)" % (sid, names.get(sid, "?"))] = value
    out.setdefault("reception", 0.0)
    if kicker:
        out["kicker"] = kicker
    if defense:
        out["defense"] = defense
    if unmapped:
        out["unmapped"] = unmapped
    return out


def map_roster_spots(settings: Dict) -> List[str]:
    """roster_positions (position + count) -> the engine's flat spot list.

    Yahoo already speaks the engine's flex tokens (W/R/T, W/R, Q/W/R/T), so
    the mapping is an expansion, not a translation. Unknown tokens (IDP slots)
    pass through unchanged - honest, visible, unmangled.
    """
    spots = []
    for entry in (settings.get("roster_positions") or []):
        pos = entry.get("roster_position") if isinstance(entry, dict) else None
        if not isinstance(pos, dict):
            continue
        token = str(pos.get("position") or "").strip().upper()
        if not token:
            continue
        try:
            count = int(pos.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        spots.extend([token] * max(0, count))
    return spots


def waiver_mode_from(settings: Dict) -> str:
    """Yahoo uses_faab='1' -> 'faab'; anything else is a priority queue."""
    return "faab" if str(settings.get("uses_faab") or "0") in ("1", "true") \
        else "priority"


# --- retention (Yahoo APIs Terms of Use s2.1) -------------------------------

def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.datetime.utcfromtimestamp(ts).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def retention_stamps(fetched_at: Optional[float] = None) -> Dict[str, str]:
    """The two keys every Yahoo-derived artifact carries."""
    fetched_at = fetched_at if fetched_at is not None else _now()
    return {"yahoo_fetched_at": _iso(fetched_at),
            "yahoo_retention_expires_at": _iso(
                fetched_at + RETENTION_HOURS * 3600.0)}


def _parse_iso(text: str) -> Optional[float]:
    try:
        dt = datetime.datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None
    epoch = datetime.datetime(1970, 1, 1)
    return (dt - epoch).total_seconds()


def artifact_expiry(path: str) -> Optional[float]:
    """The expiry epoch stamped in a yaml artifact, or None if unstamped."""
    try:
        with open(path) as fh:
            doc = yaml.safe_load(fh) or {}
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    return _parse_iso(doc.get("yahoo_retention_expires_at"))


def is_expired(path: str, now: Optional[float] = None) -> bool:
    expiry = artifact_expiry(path)
    return expiry is not None and (now if now is not None else _now()) >= expiry


def require_fresh(path: str, now: Optional[float] = None) -> str:
    """Refuse to read a Yahoo artifact that is past its 24-hour clock.

    The enforcement half of the retention promise, for any renderer that
    reads leagues/yahoo-*.yaml. Stamping a file and then serving it anyway
    would be the same violation with better paperwork.
    """
    if is_expired(path, now=now):
        raise YahooRetentionError(
            "%s is past the 24-hour Yahoo retention window (Yahoo APIs Terms "
            "of Use s2.1) and must not be read. Re-run ./yahoo.sh import to "
            "refresh it, or ./yahoo.sh purge to drop it." % _rel(path))
    return path


def expired_artifacts(now: Optional[float] = None) -> List[str]:
    """Yahoo artifacts we wrote that are past the 24-hour clock.

    ONLY files carrying our own yahoo_retention_expires_at stamp are ever
    considered - a hand-written league yaml (leagues/yahoo-main.yaml) has no
    stamp and is therefore never a candidate, twice over: it also fails the
    yahoo-<digits> name check.
    """
    out = []
    for directory, pattern in ((LEAGUES_DIR, "yahoo-*.yaml"),
                               (ROSTERS_DIR, "yahoo-*.yaml")):
        for path in sorted(glob.glob(os.path.join(directory, pattern))):
            stem = os.path.splitext(os.path.basename(path))[0]
            if not re.match(r"^yahoo-\d+$", stem):
                continue           # not one of ours (e.g. yahoo-main)
            if is_expired(path, now=now):
                out.append(path)
    return out


def purge_expired(now: Optional[float] = None) -> List[str]:
    """Delete expired Yahoo artifacts. Returns what was removed.

    The league's rankings CSV is NOT touched and must not be: it is seeded
    from public ADP and filled with our own projections, so it is our data,
    not Yahoo user data, and s2.1 does not reach it. Deleting it would also
    cost a network rebuild for nothing.
    """
    removed = []
    for path in expired_artifacts(now=now):
        try:
            os.unlink(path)
            removed.append(path)
        except OSError:
            pass
    return removed


# --- import: the same artifacts connections.import_league writes -------------

def rebuild_rankings(csv_path: str, reception: float, teams: int,
                     year: int = SEASON) -> Dict:
    """Delegate to the shared per-league rebuild. Stubbed by tests.

    Kept as a module-level name (rather than an inline import) precisely so
    tests can replace yahoo.rebuild_rankings and stay offline, exactly the way
    tests/connections_test.py replaces connections.rebuild_rankings.
    """
    from engine import connections
    return connections.rebuild_rankings(csv_path, reception, teams, year=year)


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def import_league(person: str, league: str, rebuild: bool = True,
                  app: Optional[AppCredential] = None) -> Dict:
    """Import one Yahoo league for one person.

    Writes leagues/yahoo-<league_id>.yaml, data/rosters/yahoo-<league_id>.yaml
    and (unless rebuild=False) data/rankings-yahoo-<league_id>.csv - the same
    three artifacts connections.import_league produces for Sleeper, so every
    downstream page treats a Yahoo league exactly like a Sleeper one.

    `league` accepts either a full league_key ('461.l.1000') or the bare
    league id ('1000'), which is what people read off their league URL.

    RETENTION: s2.1 says expired Yahoo user data must be removed, not merely
    marked. Leaving that to the owner remembering `./yahoo.sh purge` makes the
    rule decorative, so any import sweeps every *other* league's expired
    artifacts first and reports what it dropped in summary['purged']. The
    league being imported is exempt from the sweep because it is about to be
    overwritten with a fresh copy in the same breath.
    """
    app = app or load_app()
    league_key = resolve_league_key(person, league, app=app)
    meta, settings = league_settings(person, league_key, app=app)
    teams_raw = league_teams(person, league_key, app=app)
    team_key = my_team_key(person, league_key, app=app, teams=teams_raw)
    roster = team_roster(person, team_key, app=app)

    league_id = str(meta.get("league_id") or league_key.split(".")[-1])
    config_id = "yahoo-%s" % league_id
    # s2.1 sweep. Skip this league's own pair: they are overwritten below, so
    # deleting them here would only risk leaving a hole if the write failed.
    mine = {os.path.join(LEAGUES_DIR, "%s.yaml" % config_id),
            os.path.join(ROSTERS_DIR, "%s.yaml" % config_id)}
    purged = [p for p in expired_artifacts() if p not in mine]
    for path in purged:
        try:
            os.unlink(path)
        except OSError:
            purged = [p for p in purged if p != path]
    roster_spots = map_roster_spots(settings)
    scoring = map_scoring(settings)
    waiver_mode = waiver_mode_from(settings)
    teams_count = int(meta.get("num_teams") or len(teams_raw) or 0)
    rankings_rel = "data/rankings-%s.csv" % config_id
    stamps = retention_stamps()

    league_doc = {
        "id": config_id,
        "name": "%s (Yahoo)" % (meta.get("name") or league_id),
        "platform": "yahoo",
        "teams": teams_count,
        # Draft slot is not in the settings payload; null on purpose.
        "my_slot": None,
        "waiver_mode": waiver_mode,
        "roster_spots": roster_spots,
        # Rounds = the spots you actually draft into. Yahoo hands out IR slots
        # that no draft ever fills, so counting them (which is what a naive
        # len(roster_spots) does) would invent phantom rounds and stretch
        # every survival-odds curve. Bench spots ARE drafted, so they count.
        "rounds": len([s for s in roster_spots if s != "IR"]),
        "rankings_csv": rankings_rel,
        "strategy_file": "strategies/%s.yaml" % config_id,
        "scoring": scoring,
        "team_names": [str(t.get("name") or "") for t in teams_raw
                       if t.get("name")],
        "yahoo_league_key": league_key,
        "yahoo_team_key": team_key,
        "yahoo_season": str(meta.get("season") or SEASON),
        "host": {"league_id": league_id,
                 "team_id": team_key.split(".")[-1]},
    }
    league_doc.update(stamps)
    if waiver_mode == "faab":
        # Yahoo carries the FAAB balance on the TEAM, not the league settings,
        # so it is read off this person's own team row when present.
        mine = [t for t in teams_raw if str(t.get("team_key")) == team_key]
        budget = mine[0].get("faab_balance") if mine else None
        if budget is not None:
            league_doc["waiver_budget"] = budget

    header = (
        "# Imported from Yahoo league %s (%s) by engine/yahoo.py for person\n"
        "# %r. my_slot is unknown until the draft order is set.\n"
        "#\n"
        "# RETENTION: Yahoo APIs Terms of Use s2.1 caps retention of Yahoo\n"
        "# user data at 24 hours. This file expires %s; ./yahoo.sh purge\n"
        "# deletes it, ./yahoo.sh import rewrites it fresh.\n"
        % (league_key, meta.get("name") or "?", clean_person(person),
           stamps["yahoo_retention_expires_at"]))
    league_path = os.path.join(LEAGUES_DIR, "%s.yaml" % config_id)
    _atomic_write(league_path, header + yaml.safe_dump(
        league_doc, default_flow_style=False, sort_keys=False))

    roster_doc = {"league": config_id,
                  "name": meta.get("name") or config_id,
                  "size": len(roster),
                  "players": [p["name"] for p in roster]}
    roster_doc.update(stamps)
    roster_path = os.path.join(ROSTERS_DIR, "%s.yaml" % config_id)
    _atomic_write(roster_path, yaml.safe_dump(
        roster_doc, default_flow_style=False, sort_keys=False))

    summary = {
        "person": clean_person(person),
        "league_file": league_path,
        "roster_file": roster_path,
        "rankings_csv": os.path.join(HERE, rankings_rel),
        "config_id": config_id,
        "league_key": league_key,
        "team_key": team_key,
        "name": league_doc["name"],
        "teams": teams_count,
        "waiver_mode": waiver_mode,
        "reception": float(scoring.get("reception") or 0.0),
        "roster_spots": roster_spots,
        "superflex": any(s in ("Q/W/R/T", "SUPERFLEX") for s in roster_spots),
        "my_roster_size": len(roster),
        "unmapped_scoring": sorted(scoring.get("unmapped") or {}),
        "expires_at": stamps["yahoo_retention_expires_at"],
        "purged": sorted(purged),
        "rebuild": None,
    }
    if rebuild:
        summary["rebuild"] = rebuild_rankings(
            summary["rankings_csv"], summary["reception"], teams_count)
    return summary


def resolve_league_key(person: str, league: str,
                       app: Optional[AppCredential] = None) -> str:
    """Accept '461.l.1000' as-is; turn a bare '1000' into the person's key."""
    text = str(league or "").strip()
    if not text:
        raise YahooError("No league given.")
    if ".l." in text:
        return text
    for lg in list_leagues(person, app=app):
        if lg["league_id"] == text:
            return lg["league_key"]
    raise YahooError(
        "No league with id %s among the leagues %s can see. Run "
        "`./yahoo.sh leagues --person %s` to list them."
        % (text, clean_person(person), clean_person(person)))


# --- status (read-only, never raises, never prints a value) -----------------

def connect(season: Optional[int] = None):
    """Compatibility shim for the old single-user entry point.

    engine/connections.py (which this task must not edit) still calls
    yahoo.connect() from its wizard. Rather than let that surface as a bare
    AttributeError, it gets the honest sentence: the single-user handshake is
    gone because it could not serve a second person, and here is what replaced
    it. Raising - not half-working - is the point.
    """
    raise YahooSetupError(
        "yahoo.connect() was the one-person handshake and no longer exists. "
        "Yahoo is now one app serving many people: "
        "./yahoo.sh authorize --person <name>, then finish/leagues/import. "
        "See docs/CONNECT_YAHOO.md.")


def status() -> Dict:
    """Connection facts for the wizard. Values never appear - only whether."""
    out = {"app_registered": False, "detail": "", "people": [],
           "expired_artifacts": []}
    try:
        app = load_app()
        out["app_registered"] = True
        out["redirect_uri"] = app.redirect_uri
        out["scope"] = app.scope or "(pinned at app registration)"
    except YahooError as exc:
        out["detail"] = str(exc)
        return out
    try:
        out["people"] = connected_people()
    except Exception:
        out["people"] = []
    try:
        out["expired_artifacts"] = expired_artifacts()
    except Exception:
        out["expired_artifacts"] = []
    if out["people"]:
        out["detail"] = ("app registered; %d person/people connected"
                         % len(out["people"]))
    else:
        out["detail"] = ("app registered; nobody has consented yet - "
                         "./yahoo.sh authorize --person <name>")
    return out
