#!/usr/bin/env python3
"""THE PUBLISH PIPELINE — one private copy of War Room per person.

    .venv/bin/python publish.py [--dry-run] [--person NAME] [--week N]
    .venv/bin/python publish.py check-heartbeat
    .venv/bin/python publish.py new-token
    .venv/bin/python publish.py list

WHAT THIS IS
------------
The owner's family and co-workers are in THEIR OWN leagues. This renders each
person's leagues, assembles them into `public/<token>/`, and publishes that
directory — and nothing else — to a private path only they can reach.

The failure that ruins this is not a crash. It is publishing the wrong
person's pages, or the owner's own strategy pages, to the wrong path. So the
pipeline is built to REFUSE rather than to guess:

  THE ALLOWLIST      Every person has an explicit, computed list of the files
                     that may exist in their directory: their leagues' pages
                     at this week, an index, a heartbeat, and (when
                     engine/pwa.py is present) the declared PWA files. Anything
                     else found in the staging tree is a refusal.

  THE PRE-FLIGHT     Before one byte moves into public/, every staged file is
                     read and asserted: it is on the allowlist; it names no
                     league this person does not own; it carries no other
                     person's league NAME either; it contains no other
                     person's token; it links to no localhost panel; and it
                     carries a publish stamp whose week is the week we asked
                     for.

  TWO-PHASE COMMIT   Every person is staged and asserted first. Only if ALL
                     of them pass does anything get committed. One bad file
                     anywhere means nothing is published, anywhere, and the
                     exit code is non-zero.

  FAIL CLOSED        Every ambiguity resolves to "refuse". A renderer that
                     writes an unexpected file, a league id too short to match
                     safely, a duplicate token, a weak token, a missing
                     stamp — all stop the run. Nothing is ever published on
                     the strength of "it probably didn't leak".

THE HEARTBEAT IS A CONTENT HEARTBEAT
------------------------------------
This system degrades honestly and exits 0, so "the cron job ran fine" proves
nothing at all: a publish that quietly re-published week 1 pages in week 7 is
green by every exit code and useless to the reader. So `check-heartbeat`
re-reads the PUBLISHED HTML on disk and asserts the week stamped inside it
matches the week it should be, then exits non-zero if it does not. That exit
code is what an alert hangs off.

PUBLIC RENDER MODE
------------------
`engine/ui.py`'s NAV_PAGES carries `http://127.0.0.1:8787/` (the owner's local
Model Settings panel) into every page, and the league switcher lists every
league in `leagues/` — including leagues the reader does not own. Neither
renderer takes a flag for this and this module does not own those files, so
the mechanism here is DOCUMENTED, NARROW, ASSERTED POST-PROCESSING:

  1. Any anchor whose href points at a loopback address is removed whole.
  2. Any `<a class="wr-lg" ...>` league-switcher entry that points at, or is
     named after, a league this person does not own is removed whole.
  3. The result is then ASSERTED: no "127.0.0.1", no "localhost", no foreign
     league id, no foreign league name. The substitution is best-effort; the
     assertion is the guarantee. If the assertion fails, nothing publishes.

Stdlib + PyYAML only. Reads leagues/ and users.yaml; writes public/ and
publish-heartbeat.json and nothing else.
"""

import argparse
import datetime as _dt
import glob
import hashlib
import html as _html
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter, OrderedDict

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_USERS = os.path.join(HERE, "users.yaml")
DEFAULT_PUBLIC = os.path.join(HERE, "public")
DEFAULT_HEARTBEAT = os.path.join(HERE, "publish-heartbeat.json")
LEAGUE_DIR = os.path.join(HERE, "leagues")
# READ ONLY, and read for one reason: engine/exposure.py labels cross-league
# holdings with the `name:` in THIS file, not the one in leagues/. They are
# routinely different ("Kid's Table" vs "Kid's Table (Yahoo)"), and the shorter
# one is what lands in a rendered page. A pipeline that only knew the leagues/
# name would let the other one straight through.
ROSTER_DIR = os.path.join(HERE, "data", "rosters")

VENV_PY = os.path.join(HERE, ".venv", "bin", "python")
PYTHON = VENV_PY if os.path.exists(VENV_PY) else sys.executable

SCHEMA = "warroom.publish.heartbeat/2"

# How old a publish may be before check-heartbeat calls it stale. A daily
# schedule plus a couple of hours of slack.
DEFAULT_MAX_AGE_HOURS = 26.0


class Refusal(Exception):
    """A safety assertion said no. Nothing is published; the exit is 2."""


class ConfigError(Exception):
    """users.yaml or leagues/ cannot be trusted. Nothing is published."""


# --- the pages, and the seam each renderer already offers ---------------------
#
# Every renderer takes --league / --week / --out and prints the written path as
# its last stdout line. This table is the ONLY place that knowledge lives.

class PageSpec(object):
    __slots__ = ("kind", "module", "template", "scope", "label")

    def __init__(self, kind, module, template, scope, label):
        self.kind = kind            # stamp + manifest name
        self.module = module        # python -m <module>
        self.template = template    # filename, {league}/{week} substituted
        self.scope = scope          # "league" (one per league) or "person"
        self.label = label          # what the index calls it

    def filename(self, league, week):
        return self.template.format(league=league, week=int(week))


PAGES = (
    PageSpec("home", "engine.home", "home.html", "person", "Home"),
    PageSpec("lineup", "engine.lineup_page",
             "lineup-{league}-week{week}.html", "league", "Lineup"),
    PageSpec("board", "engine.board",
             "board-{league}-week{week}.html", "league", "Board"),
    PageSpec("digest", "engine.digest",
             "digest-{league}-week{week}.html", "league", "Ledger"),
    PageSpec("trades", "engine.tradedesk",
             "tradedesk-{league}-week{week}.html", "league", "Trade Desk"),
    PageSpec("sources", "engine.sources_page", "sources.html", "person",
             "Sources"),
)

INDEX_NAME = "index.html"
HEARTBEAT_NAME = "heartbeat.json"

# Files engine/pwa.py is permitted to add to a person's directory. Anything it
# writes outside this set is a refusal — a module built in parallel does not
# get to widen this pipeline's allowlist by surprise.
PWA_ALLOWED = re.compile(
    r"^(manifest\.(webmanifest|json)"
    r"|sw\.js|service-worker\.js|serviceworker\.js"
    r"|install\.html|offline\.html"
    r"|favicon\.ico|favicon\.png|favicon\.svg"
    r"|apple-touch-icon(-\d+x\d+)?\.png"
    r"|icon[-_]?\d*(x\d+)?\.(png|svg)"
    r"|icons/[A-Za-z0-9._-]+\.(png|svg|ico|json))$")

PWA_ENTRY_POINTS = ("publish_into", "write_into", "install_into", "emit_into",
                    "write_all", "write_pwa", "write_files", "write", "emit")

TEXT_EXT = (".html", ".htm", ".json", ".webmanifest", ".js", ".css", ".txt",
            ".md", ".svg", ".xml")

# --- what must never appear in a published file ------------------------------
#
# "localhost" appears zero times in every page the renderers emit today, so it
# is forbidden outright rather than only in hrefs. If a future page wants the
# word in prose, the refusal will say so loudly and this list is where it is
# reconsidered — deliberately, not accidentally.
# NOTE ON ":8787" rather than "8787": every page embeds hundreds of kilobytes
# of base64 fonts and avatars, and a bare four-digit run occurs there by pure
# chance often enough to refuse a good publish. A colon never appears inside a
# base64 payload, so ":8787" matches the port and nothing else.
FORBIDDEN = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]", ":8787")

LOOPBACK_ANCHOR = re.compile(
    r'<a\b[^>]*href="(?:https?:)?//(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])'
    r'(?::\d+)?[^"]*"[^>]*>.*?</a>',
    re.I | re.S)
LEAGUE_ANCHOR = re.compile(r'<a\b[^>]*class="wr-lg"[^>]*>.*?</a>', re.I | re.S)
HREF_ATTR = re.compile(r'href="([^"]*)"', re.I)
# The only two href shapes ui.shell() gives a switcher entry. Parsed exactly —
# an href that does not match one of these has its anchor dropped, because an
# href nobody can read is an href nobody can vouch for.
SWITCH_HREF = re.compile(
    r'^(?:home\.html\#league-(?P<a>.+)'
    r'|(?:board|digest|tradedesk|lineup)-(?P<b>.+)-week\d+\.html)$')

STAMP_RE = re.compile(
    r'<!--\s*warroom:publish v1'
    r' week="(?P<week>\d+)"'
    r' page="(?P<page>[^"]*)"'
    r' leagues="(?P<leagues>[^"]*)"'
    r' generated="(?P<generated>[^"]*)"'
    r' person="(?P<person>[^"]*)"\s*-->')


# =============================================================================
# small helpers
# =============================================================================

def esc(text):
    """Escape for element bodies and attributes (engine/ui.esc's rule)."""
    return _html.escape("" if text is None else str(text), quote=True)


def now_utc():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text):
    """Parse our own stamp format. Returns None rather than raising."""
    try:
        return _dt.datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def fingerprint(token):
    """A stable, non-reversing label for a token. NEVER the token itself —
    this goes into heartbeat files, logs and the pages themselves."""
    return hashlib.sha256(("warroom-publish/" + str(token)).encode(
        "utf-8")).hexdigest()[:12]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def slug(text):
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "person"


def is_text(name):
    return os.path.splitext(name)[1].lower() in TEXT_EXT


def rel_files(root):
    """Every regular file under root, as sorted forward-slash relative paths.
    A symlink is reported with its own name so the caller can refuse it."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def human_size(n):
    if n < 1024:
        return "%dB" % n
    if n < 1024 * 1024:
        return "%.0fK" % (n / 1024.0)
    return "%.1fM" % (n / (1024.0 * 1024.0))


# =============================================================================
# tokens
# =============================================================================

TOKEN_MIN_LEN = 24
TOKEN_MIN_DISTINCT = 12
TOKEN_MIN_ENTROPY = 3.0
TOKEN_CHARSET = re.compile(r"^[A-Za-z0-9_-]+$")

# Words that make a token a guess rather than a secret. Substring match,
# case-insensitive, after stripping separators.
WEAK_WORDS = (
    "token", "secret", "password", "passwd", "changeme", "change", "replace",
    "example", "sample", "test", "demo", "temp", "default", "placeholder",
    "warroom", "fantasy", "football", "league", "private", "public", "admin",
    "user", "guest", "family", "qwerty", "letmein", "iloveyou", "monkey",
    "dragon", "master", "welcome", "abc", "123456", "000000", "111111",
    "seecomments", "puta", "putarealtoken",
)


def _entropy(text):
    """Shannon entropy in bits per character."""
    n = len(text)
    if n <= 1:
        return 0.0
    counts = Counter(text)
    return -sum((c / float(n)) * math.log(c / float(n), 2)
                for c in counts.values())


def _sequential(text):
    """True for runs like abcdefgh / 12345678 / hgfedcba."""
    if len(text) < 8:
        return False
    up = 0
    down = 0
    for a, b in zip(text, text[1:]):
        d = ord(b) - ord(a)
        up = up + 1 if d == 1 else 0
        down = down + 1 if d == -1 else 0
        if up >= 7 or down >= 7:
            return True
    return False


def token_problems(token, name="", email=""):
    """Every reason this token is not unguessable. Empty list = acceptable.

    A token is a URL path that stands in for a password until Cloudflare
    Access checks the email, so "looks random" is the whole bar. These rules
    are a floor, not a substitute for `secrets.token_urlsafe(32)`.
    """
    problems = []
    if not isinstance(token, str) or not token.strip():
        return ["missing — generate one with: %s" % NEW_TOKEN_CMD]
    tok = token.strip()
    if tok != token:
        problems.append("has leading or trailing whitespace")
    if len(tok) < TOKEN_MIN_LEN:
        problems.append("is %d characters; at least %d are required"
                        % (len(tok), TOKEN_MIN_LEN))
    if not TOKEN_CHARSET.match(tok):
        bad = sorted(set(c for c in tok if not re.match(r"[A-Za-z0-9_-]", c)))
        problems.append("contains characters that are unsafe in a URL path: %s"
                        % " ".join(repr(c) for c in bad[:8]))
    distinct = len(set(tok))
    if distinct < TOKEN_MIN_DISTINCT:
        problems.append("uses only %d distinct characters; at least %d are "
                        "required" % (distinct, TOKEN_MIN_DISTINCT))
    ent = _entropy(tok)
    if ent < TOKEN_MIN_ENTROPY:
        problems.append("has %.2f bits of entropy per character; at least "
                        "%.1f are required" % (ent, TOKEN_MIN_ENTROPY))
    if _sequential(tok):
        problems.append("contains a long alphabetical or numeric run")
    flat = re.sub(r"[^a-z0-9]", "", tok.lower())
    for word in WEAK_WORDS:
        if word in flat:
            problems.append("contains the guessable word %r" % word)
            break
    for label, source in (("name", name), ("email", email)):
        part = re.sub(r"[^a-z0-9]", "", str(source or "").split("@")[0].lower())
        if len(part) >= 4 and part in flat:
            problems.append("is derived from this person's %s" % label)
    return problems


NEW_TOKEN_CMD = ('.venv/bin/python -c "import secrets; '
                 'print(secrets.token_urlsafe(32))"')


def new_token():
    """A fresh token that is guaranteed to pass this module's own floor.

    secrets.token_urlsafe(32) is unguessable, but roughly one draw in 700
    happens to spell a WEAK_WORDS substring somewhere inside its 43 random
    characters - 'abc' mostly, also 'temp', 'demo', 'test', 'user', 'puta' -
    and token_problems() then refuses it. Left unfiltered that makes
    `publish.py new-token` print a token publish.py itself rejects, and makes
    any assertion that a fresh draw passes the floor fail at that same rate.

    Redrawing costs nothing and leaks nothing: the floor is a property of the
    string, not of the generator, so rejecting and redrawing just leaves the
    draw uniform over the tokens that pass. Every draw is a full-entropy
    token; none is patched up or reused.
    """
    import secrets
    while True:
        tok = secrets.token_urlsafe(32)
        if not token_problems(tok):
            return tok


# =============================================================================
# configuration
# =============================================================================

LEAGUE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

# A league display name shorter than this is not used as a leak marker: a
# 3-letter name would match inside ordinary prose and refuse every run. The
# id is always a marker; the name is the extra belt.
NAME_MARKER_MIN = 5


class Person(object):
    __slots__ = ("name", "email", "token", "leagues", "index")

    def __init__(self, name, email, token, leagues, index=0):
        self.name = name
        self.email = email
        self.token = token
        self.leagues = list(leagues)
        self.index = index

    @property
    def fp(self):
        return fingerprint(self.token)

    @property
    def slug(self):
        return slug(self.name)


def known_leagues(league_dir=None):
    """{league id: display name} for every yaml in leagues/."""
    out = OrderedDict()
    for path in sorted(glob.glob(os.path.join(league_dir or LEAGUE_DIR,
                                              "*.yaml"))):
        lid = os.path.splitext(os.path.basename(path))[0]
        name = lid
        try:
            with open(path, "r") as fh:
                data = yaml.safe_load(fh) or {}
            if isinstance(data, dict):
                lid = str(data.get("id") or lid)
                name = str(data.get("name") or lid)
        except Exception:
            # An unparseable league yaml is not this pipeline's to fix, but
            # its id still has to count as a foreign marker.
            pass
        out[lid] = name
    return out


def roster_labels(roster_dir=None):
    """{league id: display name} from data/rosters/*.yaml. READ ONLY.

    This directory is sacred and is never written here. It is read because it
    is a SECOND, independent source of league display names - the one
    engine/exposure.py puts on a page when it says "you also hold him in X".
    """
    out = OrderedDict()
    for path in sorted(glob.glob(os.path.join(roster_dir or ROSTER_DIR,
                                              "*.yaml"))):
        lid = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        lid = str(data.get("league_id") or data.get("id") or lid)
        name = str(data.get("name") or "").strip()
        if name:
            out[lid] = name
    return out


def name_variants(name):
    """Every written form of one league name that could reach a page.

    Renderers print the configured name, and they print it with the platform
    parenthetical trimmed. Both forms, and both HTML-escaped, are markers.
    """
    name = str(name or "").strip()
    if not name:
        return []
    forms = set([name])
    trimmed = re.sub(r"\s*\([^()]*\)\s*$", "", name).strip()
    if trimmed:
        forms.add(trimmed)
    stripped = re.sub(r"\s*\([^()]*\)", " ", name)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped:
        forms.add(stripped)
    out = []
    for form in sorted(forms, key=lambda f: (-len(f), f)):
        if len(form) < NAME_MARKER_MIN:
            continue
        for written in (form, esc(form)):
            if written not in out:
                out.append(written)
    return out


def _names_of(all_leagues, lid):
    """Accept either {id: name} or {id: [name, ...]}."""
    value = all_leagues.get(lid)
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if value else [str(lid)]


def display_name(all_leagues, lid):
    names = _names_of(all_leagues, lid)
    return names[0] if names else str(lid)


def load_users(path=None, league_dir=None):
    """Parse and FULLY validate users.yaml. Raises ConfigError on anything
    that would make a publish unsafe — this runs before any rendering."""
    path = path or DEFAULT_USERS
    if not os.path.exists(path):
        raise ConfigError(
            "%s does not exist. Copy the template shipped with the project, "
            "add one entry per person, and generate each token with:\n    %s"
            % (path, NEW_TOKEN_CMD))
    with open(path, "r") as fh:
        try:
            data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ConfigError("%s is not valid YAML: %s" % (path, exc))
    if not isinstance(data, dict) or "people" not in data:
        raise ConfigError("%s has no top-level `people:` key." % path)
    raw = data.get("people")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ConfigError("%s: `people:` must be a list." % path)
    if not raw:
        raise ConfigError(
            "%s lists no people, so this run would publish nothing and say it "
            "succeeded. Add at least one person, or do not run publish."
            % path)

    leagues_on_disk = known_leagues(league_dir)
    people = []
    problems = []
    seen_tokens = {}
    seen_names = {}
    seen_emails = {}
    for i, entry in enumerate(raw):
        where = "%s: people[%d]" % (path, i)
        if not isinstance(entry, dict):
            problems.append("%s is not a mapping" % where)
            continue
        name = str(entry.get("name") or "").strip()
        email = str(entry.get("email") or "").strip()
        token = entry.get("token")
        token = token.strip() if isinstance(token, str) else token
        lgs = entry.get("leagues") or []
        if not name:
            problems.append("%s has no `name`" % where)
            continue
        where = "%s (%s)" % (where, name)
        if not email or "@" not in email or email.startswith("@") \
                or email.endswith("@"):
            problems.append("%s has no usable `email` — Cloudflare Access "
                            "keys on it, so it is required" % where)
        if not isinstance(lgs, list) or not lgs:
            problems.append("%s lists no `leagues`" % where)
            lgs = []
        lgs = [str(x).strip() for x in lgs]
        for lid in lgs:
            if not LEAGUE_ID_RE.match(lid):
                problems.append(
                    "%s: league id %r must be lowercase, at least 3 "
                    "characters, and only a-z 0-9 . _ - . Short or exotic ids "
                    "cannot be matched safely against page content, so they "
                    "are refused rather than trusted." % (where, lid))
            elif lid not in leagues_on_disk:
                problems.append("%s: no leagues/%s.yaml — add that league "
                                "config first" % (where, lid))
        if len(set(lgs)) != len(lgs):
            problems.append("%s lists the same league twice" % where)
        for problem in token_problems(token, name, email):
            problems.append("%s: token %s" % (where, problem))
        if isinstance(token, str) and token:
            if token in seen_tokens:
                problems.append("%s shares a token with %s — two people would "
                                "read the same directory"
                                % (where, seen_tokens[token]))
            seen_tokens[token] = name
        key = name.strip().lower()
        if key in seen_names:
            problems.append("%s: the name %r appears twice; --person could "
                            "not tell them apart" % (where, name))
        seen_names[key] = name
        if email:
            ekey = email.lower()
            if ekey in seen_emails:
                problems.append("%s: the email %s appears twice" % (where,
                                                                    email))
            seen_emails[ekey] = email
        if slug(name) in [p.slug for p in people]:
            problems.append("%s: the name %r collides with another person "
                            "once reduced to a directory-safe form (%s)"
                            % (where, name, slug(name)))
        people.append(Person(name, email, token, lgs, i))

    if problems:
        raise ConfigError(
            "users.yaml is not safe to publish from. Nothing was rendered and "
            "nothing was published.\n\n  - %s\n\nGenerate a token with:\n    "
            "%s" % ("\n  - ".join(problems), NEW_TOKEN_CMD))
    return people


def universe(people, league_dir=None, roster_dir=None):
    """{league id: [every name this league is known by]}.

    Merged from leagues/*.yaml AND data/rosters/*.yaml, because those two
    files disagree about what a league is called and BOTH names reach a
    rendered page. This union is what "foreign" is measured against.
    """
    out = OrderedDict()
    for lid, name in known_leagues(league_dir).items():
        out[lid] = [name]
    for lid, name in roster_labels(roster_dir).items():
        names = out.setdefault(lid, [])
        if name not in names:
            names.append(name)
    for p in people:
        for lid in p.leagues:
            out.setdefault(lid, [lid])
    return out


def foreign_markers(owned, all_leagues):
    """The strings that must NOT appear in this person's files.

    Returns [(kind, marker, league_id)] — ids always, display names when they
    are long enough to match meaningfully, in both raw and HTML-escaped form
    (the renderers escape "Kid's Table" to "Kid&#x27;s Table").
    """
    owned = set(owned)
    out = []
    seen = set()
    for lid in all_leagues:
        if lid in owned:
            continue
        if lid not in seen:
            seen.add(lid)
            out.append(("league id", lid, lid))
        for name in _names_of(all_leagues, lid):
            if name == lid:
                continue
            for variant in name_variants(name):
                if variant in seen:
                    continue
                seen.add(variant)
                out.append(("league name", variant, lid))
    return out


# =============================================================================
# rendering (the seam tests replace)
# =============================================================================

def run_renderer(module, argv, root=None, timeout=1800):
    """Invoke one renderer through its existing CLI. Returns (code, output).

    A subprocess, not an import: a renderer that raises, calls sys.exit, or
    leaves global state behind cannot take the pipeline down with it, and
    `--out` is the seam every renderer already documents. TESTS REPLACE THIS
    FUNCTION — nothing else in this module shells out.
    """
    cmd = [PYTHON, "-m", module] + list(argv)
    try:
        proc = subprocess.run(cmd, cwd=root or HERE, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ds: %s" % (timeout, " ".join(cmd))
    except OSError as exc:
        return 127, "cannot run %s: %s" % (" ".join(cmd), exc)
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace")


_HELP_CACHE = {}


def renderer_supports(module, flag, root=None):
    """Does this renderer's CLI accept `flag`? Asked once, by --help.

    engine/exposure.py reads EVERY file in data/rosters/ and prints the other
    leagues' names onto the page. The renderers already take a `roster_dir`
    internally; the day any of them exposes it as `--roster-dir`, this starts
    handing each person a directory containing only their own leagues' rosters
    and the cross-tenant leak stops at the source instead of at the refusal.
    Until then this returns False and the pre-flight does its job.
    """
    key = (module, flag)
    if key not in _HELP_CACHE:
        code, out = run_renderer(module, ["--help"], root=root, timeout=120)
        _HELP_CACHE[key] = (code == 0 and flag in (out or ""))
    return _HELP_CACHE[key]


def person_roster_dir(person, dest, roster_dir=None):
    """A copy of data/rosters/ holding ONLY this person's leagues.

    A COPY. data/rosters/ is sacred: it is globbed and read, never written,
    never moved, never emptied. Returns the new directory, or "" when there is
    nothing to copy.
    """
    src = roster_dir or ROSTER_DIR
    if not os.path.isdir(src):
        return ""
    owned = set(person.leagues)
    keep = [(lid, path) for lid, path in
            ((os.path.splitext(os.path.basename(f))[0], f)
             for f in sorted(glob.glob(os.path.join(src, "*.yaml"))))
            if lid in owned]
    if not os.path.isdir(dest):
        os.makedirs(dest)
    for lid, path in keep:
        shutil.copyfile(path, os.path.join(dest, os.path.basename(path)))
    return dest


def renderer_argv(spec, person, week, out_path, league=None):
    """The exact CLI for one page. `engine.home` takes --league repeatably and
    limits the page to those leagues; every other renderer takes one."""
    argv = []
    if spec.scope == "league":
        argv += ["--league", league]
    elif spec.module == "engine.home":
        for lid in person.leagues:
            argv += ["--league", lid]
    else:
        argv += ["--league", person.leagues[0]]
    argv += ["--week", str(int(week)), "--out", out_path]
    return argv


def render_person(person, week, stage, root=None, timeout=1800, log=print,
                  roster_dir=""):
    """Render this person's pages into `stage`. Returns (rendered, failures).

    A renderer that fails does NOT abort: the honesty contract says a degraded
    section says what it does not know. The page is simply absent, the index
    says which and why, and the heartbeat records ok=false — which makes
    check-heartbeat exit non-zero, so the failure raises an alarm instead of
    riding along silently.
    """
    rendered = []
    failures = []
    for spec in PAGES:
        targets = person.leagues if spec.scope == "league" else [None]
        for lid in targets:
            fname = spec.filename(lid or person.leagues[0], week)
            out_path = os.path.join(stage, fname)
            argv = renderer_argv(spec, person, week, out_path, league=lid)
            if roster_dir and renderer_supports(spec.module, "--roster-dir",
                                                root=root):
                argv += ["--roster-dir", roster_dir]
            log("    %-11s %s" % (spec.kind, fname))
            code, output = run_renderer(spec.module, argv, root=root,
                                        timeout=timeout)
            if code != 0 or not os.path.exists(out_path):
                tail = " / ".join(
                    [ln.strip() for ln in (output or "").splitlines()
                     if ln.strip()][-2:]) or "no output"
                failures.append({
                    "page": spec.kind, "league": lid or "", "file": fname,
                    "exit": int(code), "why": tail[:240]})
                log("      NOT RENDERED (exit %d): %s" % (code, tail[:160]))
                if os.path.exists(out_path):
                    os.remove(out_path)
                continue
            rendered.append({"page": spec.kind, "league": lid or "",
                             "file": fname, "label": spec.label})
    return rendered, failures


# =============================================================================
# public render mode: the documented, asserted substitution
# =============================================================================

def strip_loopback(html):
    """Remove every anchor pointing at the owner's local settings panel.

    ui.NAV_PAGES renders `http://127.0.0.1:8787/` into the nav of every page.
    A published reader cannot reach it, and the link advertises that a panel
    exists. The anchor is removed whole — href, title and label together.
    Returns (html, count).
    """
    return LOOPBACK_ANCHOR.subn("", html)


def strip_foreign_leagues(html, owned):
    """Remove league-switcher entries for leagues this person does not own.

    Every renderer globs leagues/*.yaml for the switcher, so a person in one
    league still gets an anchor to every OTHER league's board, carrying that
    league's display name. Each `<a class="wr-lg">` is kept only when its href
    names a league this person owns. Returns (html, removed_count).
    """
    owned = set(owned)
    removed = [0]

    def keep(match):
        chunk = match.group(0)
        href = HREF_ATTR.search(chunk)
        m = SWITCH_HREF.match(href.group(1)) if href else None
        lid = (m.group("a") or m.group("b")) if m else None
        if lid is not None and lid in owned:
            return chunk
        removed[0] += 1
        return ""

    return LEAGUE_ANCHOR.sub(keep, html), removed[0]


def stamp_comment(week, page, leagues, generated, person_fp):
    return ('<!-- warroom:publish v1 week="%d" page="%s" leagues="%s" '
            'generated="%s" person="%s" -->'
            % (int(week), esc(page), esc(",".join(leagues)), esc(generated),
               esc(person_fp)))


STAMP_CSS = (
    "<style>"
    ".wr-pubstamp{display:flex;flex-wrap:wrap;justify-content:center;"
    "align-items:center;gap:4px 8px;margin:28px 0 0;"
    "padding:14px 16px calc(14px + env(safe-area-inset-bottom,0px));"
    "border-top:2px solid var(--wr-rule,#F2B722);"
    "background:var(--wr-raised,#F8F7F3);color:var(--wr-muted,#5B6478);"
    "font-size:var(--wr-t4,11px);line-height:1.55;letter-spacing:.3px;"
    "text-align:center;overflow-wrap:anywhere;max-width:100%;"
    "box-sizing:border-box}"
    ".wr-pubstamp b{color:var(--wr-text,#101B33);font-weight:700;"
    "letter-spacing:.9px}"
    ".wr-pubstamp i{font-style:normal;color:var(--wr-hairline-2,#CFCABB)}"
    "@media (max-width:700px){.wr-pubstamp{margin-bottom:96px}}"
    "</style>")


def stamp_footer(week, generated_human, person_name):
    return ('<footer class="wr-pubstamp">'
            '<b>WEEK %d</b><i>&#183;</i>'
            '<span>published %s</span><i>&#183;</i>'
            '<span>private copy for %s &#8212; this page does not update on '
            'its own</span></footer>'
            % (int(week), esc(generated_human), esc(person_name)))


def publish_html(html, person, week, page, generated, generated_human,
                 all_leagues, path_label=""):
    """Turn one rendered page into a publishable page, then PROVE it.

    Order matters: substitute first, assert second. The assertion is what the
    guarantee rests on — if a renderer starts emitting a foreign league id
    somewhere the substitution does not reach, this raises and the whole run
    publishes nothing.
    """
    out, loopback = strip_loopback(html)
    out, switchers = strip_foreign_leagues(out, person.leagues)

    stamp = stamp_comment(week, page, person.leagues, generated, person.fp)
    footer = stamp_footer(week, generated_human, person.name)
    if "</head>" in out:
        out = out.replace("</head>", STAMP_CSS + "\n</head>", 1)
    else:
        out = STAMP_CSS + "\n" + out
    if "</body>" in out:
        out = out.replace("</body>", stamp + "\n" + footer + "\n</body>", 1)
    else:
        out = out + "\n" + stamp + "\n" + footer + "\n"

    where = path_label or page
    for needle in FORBIDDEN:
        if needle in out:
            raise Refusal(
                "%s for %s still contains %r after public render mode. The "
                "substitution removed %d loopback anchor(s); something else on "
                "the page carries it. Nothing was published — find it with:\n"
                "    grep -o '.\\{80\\}%s.\\{80\\}' <the rendered page>"
                % (where, person.name, needle, loopback, needle))
    for kind, marker, lid in foreign_markers(person.leagues, all_leagues):
        if marker in out:
            raise Refusal(
                "%s for %s contains the %s %r, which belongs to league %r — a "
                "league this person does not own. This is exactly the leak "
                "this pipeline exists to stop. %d switcher entr(y/ies) were "
                "removed and it survived, so it is in the page body, not the "
                "nav. NOTHING WAS PUBLISHED."
                % (where, person.name, kind, marker, lid, switchers))
    if not STAMP_RE.search(out):
        raise Refusal("%s for %s did not take a publish stamp — refusing to "
                      "publish a page whose week cannot be checked later."
                      % (where, person.name))
    return out


# =============================================================================
# the per-person index
# =============================================================================

def _ui():
    try:
        from engine import ui
        return ui
    except Exception:
        return None


def index_html(person, week, rendered, failures, pwa, generated,
               generated_human, all_leagues, heartbeat):
    """The person's front door: what is here, what is not, and when it ran."""
    ui = _ui()
    lgs = [(lid, display_name(all_leagues, lid)) for lid in person.leagues]

    by_page = {}
    for r in rendered:
        by_page.setdefault(r["league"], []).append(r)

    cards = []
    home = [r for r in rendered if r["page"] == "home"]
    src = [r for r in rendered if r["page"] == "sources"]

    def link(href, label, note):
        return ('<a class="pub-link" href="%s"><span class="pub-link-l">%s'
                '</span><span class="pub-link-n">%s</span></a>'
                % (esc(href), esc(label), esc(note)))

    top = []
    if home:
        top.append(link(home[0]["file"], "Home",
                        "every league you have, and what needs you this week"))
    if pwa.get("install"):
        top.append(link(pwa["install"], "Add to your phone",
                        "put War Room on your home screen"))
    if src:
        top.append(link(src[0]["file"], "Sources",
                        "the per-source record behind every call"))
    if top:
        cards.append('<section class="pub-card"><h2 class="pub-h">Start here'
                     '</h2><div class="pub-links">%s</div></section>'
                     % "".join(top))

    for lid, lname in lgs:
        rows = [r for r in by_page.get(lid, [])]
        if not rows:
            continue
        links = "".join(link(r["file"], r["label"], _blurb(r["page"]))
                        for r in rows)
        cards.append('<section class="pub-card"><h2 class="pub-h">%s</h2>'
                     '<div class="pub-links">%s</div></section>'
                     % (esc(lname), links))

    # THE HONESTY BLOCK. Nothing here asserts what it does not know.
    notes = []
    if failures:
        lines = "".join(
            "<li>%s%s &#8212; not rendered (%s)</li>"
            % (esc(f["page"]), (" for %s" % esc(display_name(all_leagues,
                                                              f["league"])))
               if f["league"] else "", esc(f["why"][:160] or "no reason given"))
            for f in failures)
        notes.append(
            '<div class="pub-warn"><h2 class="pub-h">%d page%s could not be '
            'built</h2><p class="pub-p">They are missing from this copy, not '
            'blank. Nothing on the pages below was computed from them.</p>'
            '<ul class="pub-ul">%s</ul></div>'
            % (len(failures), "" if len(failures) == 1 else "s", lines))
    if not pwa.get("ok"):
        notes.append('<p class="pub-p">%s</p>' % esc(pwa.get("note") or ""))
    notes.append(
        '<p class="pub-p">These pages are a snapshot taken at the time '
        'stamped below. They do not refresh themselves, and they do not know '
        'anything that happened after that moment &#8212; check the kickoff '
        'times on the page against the clock before you trust a lineup.</p>')
    if len(lgs) > 1 and src:
        notes.append(
            '<p class="pub-p">Sources is rendered on one league basis '
            '(%s). The per-source record it shows is that league\'s; it does '
            'not claim to cover %s.</p>'
            % (esc(display_name(all_leagues, person.leagues[0])),
               esc(_and_list([n for _, n in lgs[1:]]))))
    notes.append(
        '<p class="pub-p">This copy covers %s and nothing else. Other '
        'leagues in this War Room are not rendered here and are not reachable '
        'from this address.</p>'
        % esc(_and_list([n for _, n in lgs])))

    # THE VISIBLE HEARTBEAT LINE — the same facts as heartbeat.json, in words.
    ok = heartbeat["ok"]
    hb = ('<div class="pub-hb"><span class="pub-hb-k">%s</span>'
          '<span class="pub-hb-v">published %s &#183; week %d &#183; %d page%s'
          ' &#183; rendered week matches the week requested: %s</span></div>'
          % ("PUBLISH OK" if ok else "PUBLISH INCOMPLETE",
             esc(generated_human), int(week), len(rendered),
             "" if len(rendered) == 1 else "s",
             "yes" if heartbeat["assertions"]["week_matches"] else "NO"))

    style = ui.style_tag() if ui else ""
    shell = ""
    if ui:
        try:
            shell = ui.shell("home", None, week, leagues=lgs, title="War Room")
        except Exception:
            shell = ""
    body = (
        '%s\n<main class="wr-page pub-page">\n'
        '<h1 class="pub-t wr-display">%s</h1>\n'
        '<p class="pub-lede">Your War Room for week %d. Everything below was '
        'built for your league%s on this machine and published to an address '
        'only you have &#8212; keep it to yourself.</p>\n'
        '%s\n%s\n<section class="pub-card pub-notes"><h2 class="pub-h">What '
        'this is, and what it is not</h2>%s</section>\n</main>\n'
        % (shell, esc(person.name), int(week),
           "" if len(lgs) == 1 else "s", hb, "".join(cards), "".join(notes)))
    return ("<!doctype html>\n<html lang=\"en\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">\n"
            "<title>%s &#8212; War Room, week %d</title>\n%s\n<style>%s</style>"
            "\n</head><body>\n%s</body></html>\n"
            % (esc(person.name), int(week), style, INDEX_CSS, body))


def _blurb(kind):
    return {
        "lineup": "every starting slot, and who should be in it",
        "board": "your roster against every source in the room",
        "digest": "the week ahead: waivers, streams, trades",
        "trades": "who needs what, and what they would give up",
    }.get(kind, "")


def _and_list(items):
    items = [str(i) for i in items]
    if not items:
        return "no leagues"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# Mobile is the acceptance bar: one column at 375px, 44px targets, nothing
# below 11px, no horizontal overflow. Names wrap here on purpose — these are
# league names in headings, not player names in rows.
INDEX_CSS = """
.pub-page { max-width: 720px; margin: 0 auto; padding: 18px 14px 40px;
            box-sizing: border-box; overflow-x: hidden; }
.pub-t { font-size: var(--wr-t0, 26px); margin: 6px 0 2px; letter-spacing: .2px;
         color: var(--wr-text, #101B33); }
.pub-lede { font-size: var(--wr-t2, 15px); color: var(--wr-muted, #5B6478);
            margin: 0 0 16px; line-height: 1.5; max-width: 58ch; }
.pub-hb { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px;
          border-left: 3px solid var(--wr-rule, #F2B722);
          background: var(--wr-raised, #F8F7F3); padding: 10px 12px;
          margin: 0 0 18px; border-radius: 2px; }
.pub-hb-k { font-size: var(--wr-t4, 11px); font-weight: 700; letter-spacing: 1px;
            color: var(--wr-text, #101B33); }
.pub-hb-v { font-size: var(--wr-t3, 13px); color: var(--wr-muted, #5B6478); }
.pub-card { border: 1px solid var(--wr-hairline, #E4E1D8);
            background: var(--wr-panel, #fff); border-radius: 3px;
            padding: 12px 12px 6px; margin: 0 0 14px; }
.pub-h { font-size: var(--wr-t4, 11px); font-weight: 700; letter-spacing: 1.2px;
         overflow-wrap: anywhere;
         text-transform: uppercase; color: var(--wr-muted, #5B6478);
         margin: 0 0 8px; }
.pub-links { display: grid; grid-template-columns: 1fr; gap: 2px; }
.pub-link { display: flex; flex-direction: column; justify-content: center;
            gap: 1px; min-height: 52px; padding: 8px 6px; text-decoration: none;
            border-bottom: 1px solid var(--wr-hairline, #E4E1D8); }
.pub-links .pub-link:last-child { border-bottom: 0; }
.pub-link-l { font-size: var(--wr-t1, 17px); font-weight: 700;
              color: var(--wr-text, #101B33); overflow-wrap: anywhere; }
.pub-link-n { font-size: var(--wr-t3, 13px); color: var(--wr-muted, #5B6478); }
.pub-warn { border-left: 3px solid var(--wr-rule, #F2B722);
            background: var(--wr-wash-hot, #FFF3D1); padding: 10px 12px;
            margin: 0 0 12px; }
.pub-p { font-size: var(--wr-t3, 13px); color: var(--wr-muted, #5B6478);
         line-height: 1.55; margin: 0 0 8px; max-width: 62ch; }
.pub-ul { margin: 6px 0 0 18px; padding: 0; font-size: var(--wr-t3, 13px);
          color: var(--wr-text, #101B33); line-height: 1.6; }
.pub-notes { background: transparent; border-style: dashed; }
@media (min-width: 620px) { .pub-links { grid-template-columns: 1fr 1fr; }
  .pub-links .pub-link { border-bottom: 1px solid var(--wr-hairline, #E4E1D8); } }
"""


# =============================================================================
# the PWA hook (engine/pwa.py is built in parallel — degrade, never guess)
# =============================================================================

def add_pwa(stage, person, week, log=print):
    """Ask engine/pwa.py to add its manifest, icons, service worker and
    install page to this person's directory.

    That module is owned by another track and may not exist yet. Absent, this
    returns a note that the index prints and the heartbeat records — the copy
    is published without offline install, and says so. Present, whatever it
    writes must match PWA_ALLOWED or the run refuses: a parallel module does
    not get to widen this pipeline's allowlist by surprise.
    """
    before = set(rel_files(stage))
    try:
        from engine import pwa                                 # noqa: F401
    except Exception as exc:
        note = ("Offline install is not available in this copy: engine/pwa.py "
                "is not present (%s: %s). Everything else published normally."
                % (type(exc).__name__, str(exc)[:120]))
        log("    pwa         absent — %s" % type(exc).__name__)
        return {"ok": False, "files": [], "install": "", "note": note}

    available = {
        "out_dir": stage, "outdir": stage, "out": stage, "dest": stage,
        "destination": stage, "directory": stage, "dir": stage, "path": stage,
        "root": stage, "target": stage, "target_dir": stage, "into": stage,
        "week": int(week), "league": person.leagues[0],
        "leagues": list(person.leagues), "league_id": person.leagues[0],
        "league_ids": list(person.leagues), "name": person.name,
        "title": "War Room", "person": person.name,
        "start_url": INDEX_NAME, "scope": "./",
    }
    called = None
    last_error = None
    for fn_name in PWA_ENTRY_POINTS:
        fn = getattr(pwa, fn_name, None)
        if not callable(fn):
            continue
        try:
            args, kwargs = _bind(fn, available, stage)
        except TypeError as exc:
            last_error = "%s: %s" % (fn_name, exc)
            continue
        try:
            fn(*args, **kwargs)
            called = fn_name
            break
        except Exception as exc:                              # noqa: BLE001
            last_error = "%s raised %s: %s" % (fn_name, type(exc).__name__,
                                               str(exc)[:160])
            continue
    if called is None:
        note = ("Offline install is not available in this copy: engine/pwa.py "
                "is present but exposes none of the entry points this "
                "pipeline knows how to call (%s)%s. Everything else published "
                "normally."
                % (", ".join(PWA_ENTRY_POINTS),
                   " — last error: %s" % last_error if last_error else ""))
        log("    pwa         present but not callable — %s"
            % (last_error or "no known entry point"))
        return {"ok": False, "files": [], "install": "", "note": note}

    added = sorted(set(rel_files(stage)) - before)
    bad = [f for f in added if not PWA_ALLOWED.match(f)]
    if bad:
        raise Refusal(
            "engine/pwa.%s() wrote %d file(s) this pipeline does not "
            "recognise into %s's directory: %s. The allowlist is closed on "
            "purpose — an unrecognised file is one nobody has checked for "
            "another person's data. NOTHING WAS PUBLISHED. Either the file "
            "belongs in publish.PWA_ALLOWED, or it does not belong in a "
            "published directory."
            % (called, len(bad), person.name, ", ".join(bad[:10])))
    install = "install.html" if "install.html" in added else ""
    log("    pwa         engine.pwa.%s() added %d file(s)" % (called,
                                                              len(added)))
    return {"ok": True, "files": added, "install": install,
            "note": "Offline install added by engine.pwa.%s()." % called,
            "entry": called}


def _bind(fn, available, stage):
    """Build the call for one candidate entry point from what it accepts.

    Only parameters the function actually declares are passed; a required
    positional whose name we do not recognise gets the staging directory,
    which is the one argument every plausible signature starts with.
    """
    sig = inspect.signature(fn)
    args = []
    kwargs = {}
    for i, param in enumerate(sig.parameters.values()):
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        required = param.default is inspect.Parameter.empty
        if param.name in available:
            value = available[param.name]
        elif required and i == 0:
            value = stage          # every plausible signature starts here
        elif required:
            raise TypeError("required parameter %r is not one this pipeline "
                            "knows how to fill" % param.name)
        else:
            continue
        if param.kind == param.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[param.name] = value
    return args, kwargs


# =============================================================================
# the allowlist and the pre-flight assertion
# =============================================================================

def allowlist(person, week, pwa_files=()):
    """EXACTLY the files that may exist in this person's directory.

    Computed from the person's own leagues and the requested week — never
    discovered from disk. Anything found in staging that is not in here stops
    the run.
    """
    allowed = OrderedDict()
    allowed[INDEX_NAME] = "the person's index"
    allowed[HEARTBEAT_NAME] = "the machine-checkable heartbeat"
    for spec in PAGES:
        if spec.scope == "league":
            for lid in person.leagues:
                allowed[spec.filename(lid, week)] = "%s (%s)" % (spec.kind, lid)
        else:
            allowed[spec.filename(person.leagues[0], week)] = spec.kind
    for f in pwa_files:
        allowed[f] = "pwa asset"
    return allowed


def assert_stage(stage, person, week, allowed, all_leagues, people, log=print):
    """THE PRE-FLIGHT. Every check that must pass before anything is copied.

    Raises Refusal on the first failure. The caller publishes nothing —
    not for this person and, because commit is two-phase, not for anyone.
    """
    found = rel_files(stage)

    # [1] nothing unexpected, and nothing that is not a plain file.
    unexpected = [f for f in found if f not in allowed]
    if unexpected:
        raise Refusal(
            "%d unexpected file(s) in %s's staging directory: %s. The "
            "allowlist for this person and week is:\n    %s\nA file nobody "
            "listed is a file nobody has checked for another person's data. "
            "NOTHING WAS PUBLISHED."
            % (len(unexpected), person.name, ", ".join(unexpected[:12]),
               "\n    ".join(sorted(allowed))))
    for f in found:
        full = os.path.join(stage, f)
        if os.path.islink(full):
            raise Refusal("%s in %s's staging directory is a symlink. A "
                          "symlink can point anywhere on this Mac, including "
                          "at another league's pages. NOTHING WAS PUBLISHED."
                          % (f, person.name))
        if not os.path.isfile(full):
            raise Refusal("%s in %s's staging directory is not a regular "
                          "file. NOTHING WAS PUBLISHED." % (f, person.name))

    # [2] the filename itself may not name a foreign league.
    markers = foreign_markers(person.leagues, all_leagues)
    for f in found:
        for kind, marker, lid in markers:
            if kind == "league id" and marker in f:
                raise Refusal(
                    "the filename %s in %s's directory names league %r, which "
                    "they do not own. NOTHING WAS PUBLISHED."
                    % (f, person.name, lid))

    # [3] content: no foreign league, no loopback, no other person's token.
    others = [p for p in people if p.token != person.token]
    for f in found:
        full = os.path.join(stage, f)
        if not is_text(f):
            continue
        with open(full, "r", errors="replace") as fh:
            body = fh.read()
        for needle in FORBIDDEN:
            if needle in body:
                raise Refusal(
                    "%s in %s's directory contains %r — a published page must "
                    "never link to the owner's local machine. NOTHING WAS "
                    "PUBLISHED." % (f, person.name, needle))
        for kind, marker, lid in markers:
            if marker in body:
                raise Refusal(
                    "%s in %s's directory contains the %s %r, belonging to "
                    "league %r, which they do not own. This is the leak this "
                    "pipeline exists to stop. NOTHING WAS PUBLISHED."
                    % (f, person.name, kind, marker, lid))
        for other in others:
            if other.token in body:
                raise Refusal(
                    "%s in %s's directory contains %s's private token. That "
                    "token is the whole of %s's privacy. NOTHING WAS "
                    "PUBLISHED." % (f, person.name, other.name, other.name))

    # [4] every published HTML page carries a stamp for THIS week.
    for f in found:
        if not f.endswith(".html"):
            continue
        with open(os.path.join(stage, f), "r", errors="replace") as fh:
            body = fh.read()
        m = STAMP_RE.search(body)
        if not m:
            raise Refusal(
                "%s in %s's directory has no publish stamp, so nothing later "
                "could tell whether it is this week's page or a stale one. "
                "NOTHING WAS PUBLISHED." % (f, person.name))
        if int(m.group("week")) != int(week):
            raise Refusal(
                "%s in %s's directory is stamped week %s but this run is "
                "publishing week %d. NOTHING WAS PUBLISHED."
                % (f, person.name, m.group("week"), int(week)))
        if m.group("person") != person.fp:
            raise Refusal(
                "%s in %s's directory is stamped for a different person (%s). "
                "NOTHING WAS PUBLISHED."
                % (f, person.name, m.group("person")))

    # [5] the index must exist. A directory with no front door is a silent
    #     half-publish, which is the thing this pipeline refuses to be.
    if INDEX_NAME not in found:
        raise Refusal("%s's staging directory has no %s. NOTHING WAS "
                      "PUBLISHED." % (person.name, INDEX_NAME))
    log("    assertions  %d file(s) checked against %d allowlist entr(y/ies), "
        "%d foreign marker(s)" % (len(found), len(allowed), len(markers)))
    return found


# =============================================================================
# staging, committing, manifest
# =============================================================================

def stage_person(person, week, stage, all_leagues, root=None, timeout=1800,
                 log=print, roster_dir=None):
    """Render, post-process, index, stamp, heartbeat — into `stage` only."""
    generated_dt = now_utc()
    generated = iso(generated_dt)
    generated_human = generated_dt.strftime("%a %d %b %Y %H:%M UTC")

    log("  %s <%s> — %s, week %d"
        % (person.name, person.email, _and_list(person.leagues), week))
    # A per-person rosters directory, held OUTSIDE the staging tree so it can
    # never reach the allowlist. Only renderers that advertise --roster-dir
    # are given it; the rest are policed by the pre-flight instead.
    mine = person_roster_dir(person, stage + "--rosters", roster_dir)
    rendered, failures = render_person(person, week, stage, root=root,
                                       timeout=timeout, log=log,
                                       roster_dir=mine)

    # public render mode, applied to every rendered page in place
    for r in rendered:
        full = os.path.join(stage, r["file"])
        with open(full, "r", errors="replace") as fh:
            html = fh.read()
        out = publish_html(html, person, week, r["page"], generated,
                           generated_human, all_leagues, path_label=r["file"])
        _atomic_write(full, out)

    pwa = add_pwa(stage, person, week, log=log)

    # Anything engine/pwa.py wrote as HTML is a published page like any other:
    # install.html carries the same ui.shell(), so it carries the same
    # localhost link, and it must carry the same stamp. Public render mode is
    # applied to it on exactly the same terms.
    for f in (pwa.get("files") or []):
        if not f.endswith(".html"):
            continue
        full = os.path.join(stage, f)
        with open(full, "r", errors="replace") as fh:
            html = fh.read()
        _atomic_write(full, publish_html(
            html, person, week, "pwa:" + os.path.splitext(f)[0], generated,
            generated_human, all_leagues, path_label=f))

    # THE CONTENT ASSERTION, MEASURED — not asserted from a variable we set
    # ourselves a moment ago. Re-read what is actually on disk and read the
    # week out of each page's own stamp.
    stamped = set()
    unstamped = []
    for r in rendered:
        with open(os.path.join(stage, r["file"]), "r", errors="replace") as fh:
            m = STAMP_RE.search(fh.read())
        if m:
            stamped.add(int(m.group("week")))
        else:
            unstamped.append(r["file"])
    week_matches = (not unstamped) and (stamped == set([int(week)])
                                        if stamped else False)

    heartbeat = {
        "schema": SCHEMA,
        "person": person.name,
        "person_fingerprint": person.fp,
        "leagues": list(person.leagues),
        "week": int(week),
        "expected_week": int(week),
        "published_at": generated,
        "pages": len(rendered),
        "page_files": [r["file"] for r in rendered],
        "failures": failures,
        "pwa": bool(pwa.get("ok")),
        "stamped_weeks": sorted(stamped),
        "assertions": {
            # every one of these is measured, never assumed: the first three
            # are proved by publish_html() raising if they are false, the
            # last two by re-reading the staged files above.
            "no_loopback": True,
            "no_foreign_league": True,
            "every_page_stamped": not unstamped,
            "week_matches": bool(week_matches),
            "all_pages_rendered": not failures,
        },
        "ok": bool(week_matches) and not failures and not unstamped,
    }

    idx = index_html(person, week, rendered, failures, pwa, generated,
                     generated_human, all_leagues, heartbeat)
    idx = publish_html(idx, person, week, "index", generated, generated_human,
                       all_leagues, path_label=INDEX_NAME)
    _atomic_write(os.path.join(stage, INDEX_NAME), idx)
    _atomic_write(os.path.join(stage, HEARTBEAT_NAME),
                  json.dumps(heartbeat, indent=2, sort_keys=True) + "\n")

    allowed = allowlist(person, week, pwa.get("files") or [])
    return {"person": person, "week": int(week), "stage": stage,
            "rendered": rendered, "failures": failures, "pwa": pwa,
            "heartbeat": heartbeat, "allowed": allowed,
            "generated": generated}


def _atomic_write(path, text):
    d = os.path.dirname(path) or "."
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def commit(stage, dest):
    """Replace dest with stage as nearly atomically as a directory allows."""
    parent = os.path.dirname(dest) or "."
    if not os.path.isdir(parent):
        os.makedirs(parent)
    incoming = dest + ".incoming-%d" % os.getpid()
    outgoing = dest + ".outgoing-%d" % os.getpid()
    for junk in (incoming, outgoing):
        if os.path.exists(junk):
            shutil.rmtree(junk)
    shutil.copytree(stage, incoming)
    had = os.path.exists(dest)
    if had:
        os.replace(dest, outgoing)
    try:
        os.replace(incoming, dest)
    except OSError:
        if had:
            os.replace(outgoing, dest)
        shutil.rmtree(incoming, ignore_errors=True)
        raise
    if had:
        shutil.rmtree(outgoing, ignore_errors=True)
    return dest


def manifest_lines(staged, public_dir, committed):
    """EXACTLY WHAT WENT WHERE. Printed on every run, dry or wet."""
    lines = []
    verb = "WOULD PUBLISH" if not committed else "PUBLISHED"
    for s in staged:
        p = s["person"]
        dest = os.path.join(public_dir, p.token)
        lines.append("")
        lines.append("%s  %s <%s>" % (verb, p.name, p.email))
        lines.append("  leagues     %s" % ", ".join(p.leagues))
        lines.append("  week        %d" % s["week"])
        lines.append("  directory   %s/" % dest)
        lines.append("  url         https://<your-site>/%s/" % p.token)
        lines.append("  token       %s (fingerprint %s)"
                     % ("*" * 8 + p.token[-4:], p.fp))
        for f in rel_files(s["stage"]):
            full = os.path.join(s["stage"], f)
            lines.append("    %-42s %8s  %s"
                         % (f, human_size(os.path.getsize(full)),
                            sha256_file(full)[:12]))
        if s["failures"]:
            for fl in s["failures"]:
                lines.append("    MISSING: %s%s (%s)"
                             % (fl["page"],
                                " / " + fl["league"] if fl["league"] else "",
                                fl["why"][:90]))
        if not s["pwa"].get("ok"):
            lines.append("    NOTE: no PWA assets — %s"
                         % (s["pwa"].get("note") or "")[:140])
    return lines


def orphans(public_dir, people):
    """Directories under public/ that belong to nobody in users.yaml.

    A rotated or deleted person's token keeps serving pages until it is
    removed. Reported on every publish and treated as an error by
    check-heartbeat, so it cannot sit there quietly.
    """
    if not os.path.isdir(public_dir):
        return []
    live = set(p.token for p in people)
    return sorted(d for d in os.listdir(public_dir)
                  if os.path.isdir(os.path.join(public_dir, d))
                  and d not in live and not d.startswith(".")
                  and ".incoming-" not in d and ".outgoing-" not in d)


# =============================================================================
# heartbeat file (aggregate, outside public/)
# =============================================================================

def read_heartbeat(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_heartbeat(path, staged, public_dir, keep_only=None):
    """MERGE, never replace: `--person` publishes one person and must not
    erase everyone else's record, or check-heartbeat would go quiet about the
    people it just stopped watching."""
    data = read_heartbeat(path)
    people = data.get("people")
    if not isinstance(people, dict):
        people = {}
    if keep_only is not None:
        # a full run also forgets people who have left users.yaml, so
        # check-heartbeat is never watching a person who no longer exists
        people = dict((k, v) for k, v in people.items() if k in keep_only)
    for s in staged:
        entry = dict(s["heartbeat"])
        entry["directory"] = os.path.join(public_dir, s["person"].token)
        entry["token_fingerprint"] = s["person"].fp
        people[s["person"].name] = entry
    out = {"schema": SCHEMA, "written_at": iso(now_utc()),
           "public_dir": public_dir, "people": people}
    _atomic_write(path, json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


# =============================================================================
# check-heartbeat — the content check, not the exit-code check
# =============================================================================

def check_heartbeat(users_path=DEFAULT_USERS, heartbeat_path=DEFAULT_HEARTBEAT,
                    public_dir=DEFAULT_PUBLIC, expected_week=None,
                    max_age_hours=DEFAULT_MAX_AGE_HOURS, league_dir=None,
                    roster_dir=None, now=None, log=print):
    """Return (exit_code, problems). Non-zero when a publish is stale.

    This deliberately does NOT trust the heartbeat file. It re-reads the HTML
    actually sitting in public/ and asserts the week stamped inside it. A run
    that crashed after writing the heartbeat, a directory restored from a
    backup, a cron job that has been rendering week 1 since September — all
    of those are green by exit code and caught here.
    """
    now = now or now_utc()
    problems = []
    notes = []

    try:
        people = load_users(users_path, league_dir=league_dir)
    except ConfigError as exc:
        return 2, ["users.yaml cannot be read, so nothing can be checked "
                   "against it: %s" % str(exc).splitlines()[0]]
    all_leagues = universe(people, league_dir, roster_dir)

    data = read_heartbeat(heartbeat_path)
    if not data or not isinstance(data.get("people"), dict):
        return 1, ["no usable heartbeat at %s — publish has never completed, "
                   "or the file was removed" % heartbeat_path]
    recorded = data["people"]

    if expected_week is None:
        expected_week, why = _current_week()
        if expected_week is None:
            notes.append("the current NFL week could not be derived (%s), so "
                         "each person is checked against the week their own "
                         "heartbeat asked for" % why)

    for person in people:
        entry = recorded.get(person.name)
        label = "%s" % person.name
        if not isinstance(entry, dict):
            problems.append("%s: in users.yaml but never published" % label)
            continue
        want = expected_week if expected_week is not None \
            else entry.get("expected_week")

        when = parse_iso(entry.get("published_at"))
        if when is None:
            problems.append("%s: heartbeat has no readable timestamp" % label)
        else:
            age = (now - when).total_seconds() / 3600.0
            if age > max_age_hours:
                problems.append(
                    "%s: last published %.1f hours ago (%s), older than the "
                    "%.0f-hour limit" % (label, age, entry["published_at"],
                                         max_age_hours))
        if not entry.get("ok"):
            fails = entry.get("failures") or []
            problems.append("%s: last publish reported itself incomplete (%d "
                            "page(s) missing: %s)"
                            % (label, len(fails),
                               ", ".join(str(f.get("page")) for f in fails[:6])
                               or "reason not recorded"))
        if want is not None and int(entry.get("week", -1)) != int(want):
            problems.append("%s: heartbeat says week %s, expected week %s"
                            % (label, entry.get("week"), want))

        # --- the content check ------------------------------------------
        d = os.path.join(public_dir, person.token)
        if not os.path.isdir(d):
            problems.append("%s: nothing published at %s" % (label, d))
            continue
        files = rel_files(d)
        if INDEX_NAME not in files:
            problems.append("%s: %s has no %s" % (label, d, INDEX_NAME))
        pages = [f for f in files if f.endswith(".html")]
        if not pages:
            problems.append("%s: %s contains no pages" % (label, d))
        markers = foreign_markers(person.leagues, all_leagues)
        stamped_weeks = set()
        for f in pages:
            with open(os.path.join(d, f), "r", errors="replace") as fh:
                body = fh.read()
            m = STAMP_RE.search(body)
            if not m:
                problems.append("%s: %s carries no publish stamp" % (label, f))
                continue
            stamped_weeks.add(int(m.group("week")))
            for needle in FORBIDDEN:
                if needle in body:
                    problems.append("%s: published file %s contains %r"
                                    % (label, f, needle))
                    break
            for kind, marker, lid in markers:
                if marker in body:
                    problems.append(
                        "%s: published file %s contains the %s %r from league "
                        "%r, which they do not own" % (label, f, kind, marker,
                                                       lid))
                    break
        if len(stamped_weeks) > 1:
            problems.append("%s: published pages are stamped for more than one "
                            "week (%s) — a partial publish left old pages "
                            "behind" % (label,
                                        ", ".join(str(w) for w in
                                                  sorted(stamped_weeks))))
        if want is not None and stamped_weeks and \
                stamped_weeks != set([int(want)]):
            problems.append(
                "%s: THE PAGES ON DISK ARE STALE — they are stamped week %s "
                "but should be week %s. The publish ran and exited 0; the "
                "content did not move." % (label,
                                           ", ".join(str(w) for w in
                                                     sorted(stamped_weeks)),
                                           want))
        recorded_pages = entry.get("page_files") or []
        missing = [f for f in recorded_pages if f not in files]
        if missing:
            problems.append("%s: the heartbeat claims %d page(s) that are not "
                            "on disk: %s" % (label, len(missing),
                                             ", ".join(missing[:6])))

    for d in orphans(public_dir, people):
        problems.append("orphaned directory %s/%s is still serving pages but "
                        "belongs to nobody in users.yaml — run "
                        "./publish.sh --prune"
                        % (public_dir, d))

    for note in notes:
        log("note: %s" % note)
    return (1 if problems else 0), problems


def _current_week():
    """The current NFL week from the schedule, or (None, why)."""
    try:
        sys.path.insert(0, HERE)
        from engine.digest import current_week
        week = current_week()
        if week is None:
            return None, "the schedule has no remaining regular-season week"
        return int(week), ""
    except Exception as exc:                                  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:120])


# =============================================================================
# commands
# =============================================================================

def cmd_publish(args, log=print):
    # EVERYONE is what safety is measured against — every foreign league, every
    # other person's token, every directory that has an owner. TARGETS is what
    # this run renders. `--person` narrows the second and never the first: a
    # single-person publish that forgot the other people would report their
    # live directories as orphans and would not check their tokens.
    try:
        everyone = load_users(args.users, league_dir=args.league_dir)
    except ConfigError as exc:
        log(str(exc))
        return 2

    targets = everyone
    if args.person:
        want = args.person.strip().lower()
        targets = [p for p in everyone if p.name.strip().lower() == want]
        if not targets:
            log("no person named %r in %s. Known: %s"
                % (args.person, args.users,
                   ", ".join(p.name for p in everyone)))
            return 2

    week = args.week
    if week is None:
        week, why = _current_week()
        if week is None:
            log("cannot derive the current NFL week (%s) — pass --week "
                "explicitly. Nothing was published." % why)
            return 2
        log("week %d (current, from the nflverse schedule)" % week)

    all_leagues = universe(everyone, args.league_dir, args.roster_dir)
    public_dir = args.out_dir
    _warn_shared_exposure(everyone, targets, args.roster_dir, log,
                          root=args.root)

    if args.plan:
        log("PLAN ONLY — no renderer was run and nothing was written.")
        for p in targets:
            log("")
            log("  %s <%s> -> %s/%s/" % (p.name, p.email, public_dir, p.token))
            for f, why in allowlist(p, week).items():
                log("    %-42s %s" % (f, why))
        _report_orphans(public_dir, everyone, log)
        return 0

    tmp_root = tempfile.mkdtemp(prefix="warroom-publish-")
    staged = []
    try:
        log("STAGING %d person/people into %s" % (len(targets), tmp_root))
        for p in targets:
            stage = os.path.join(tmp_root, p.slug)
            os.makedirs(stage)
            staged.append(stage_person(p, week, stage, all_leagues,
                                       root=args.root, timeout=args.timeout,
                                       log=log, roster_dir=args.roster_dir))

        log("")
        log("PRE-FLIGHT")
        for s in staged:
            log("  %s" % s["person"].name)
            assert_stage(s["stage"], s["person"], s["week"], s["allowed"],
                         all_leagues, everyone, log=log)
        _assert_no_crossover(staged, log=log)

        log("")
        log("MANIFEST")
        for line in manifest_lines(staged, public_dir,
                                   committed=not args.dry_run):
            log(line)

        if args.dry_run:
            log("")
            log("DRY RUN — nothing was written. %d person/people, %d file(s) "
                "would be published."
                % (len(staged), sum(len(rel_files(s["stage"]))
                                    for s in staged)))
            _report_orphans(public_dir, everyone, log)
            return 0

        for s in staged:
            commit(s["stage"], os.path.join(public_dir, s["person"].token))
        write_heartbeat(args.heartbeat, staged, public_dir,
                        keep_only=None if args.person
                        else set(p.name for p in everyone))
        log("")
        log("PUBLISHED %d person/people to %s" % (len(staged), public_dir))
        log("heartbeat %s" % args.heartbeat)

        incomplete = [s for s in staged if not s["heartbeat"]["ok"]]
        code = 0
        if incomplete:
            log("")
            log("INCOMPLETE: %s published with missing page(s). The pages that "
                "did render are live and honest; the missing ones are absent, "
                "not blank. check-heartbeat will report this as not-ok until "
                "a clean run replaces it."
                % ", ".join(s["person"].name for s in incomplete))
            code = 1
        _report_orphans(public_dir, everyone, log, prune=args.prune)
        return code
    except Refusal as exc:
        log("")
        log("REFUSED — nothing was published, for anyone.")
        log("")
        log(str(exc))
        return 2
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _assert_no_crossover(staged, log=print):
    """Belt and braces across the whole run: no person's staged tree may
    contain any other person's token or league ids. assert_stage already
    proves this per person; this proves it again over the finished set, so a
    bug in the per-person marker computation cannot pass silently."""
    for a in staged:
        for b in staged:
            if a is b:
                continue
            bad = [lid for lid in b["person"].leagues
                   if lid not in a["person"].leagues]
            for f in rel_files(a["stage"]):
                if not is_text(f):
                    continue
                with open(os.path.join(a["stage"], f), "r",
                          errors="replace") as fh:
                    body = fh.read()
                for lid in bad:
                    if lid in body or lid in f:
                        raise Refusal(
                            "cross-person check: %s's file %s contains %s's "
                            "league %r. NOTHING WAS PUBLISHED."
                            % (a["person"].name, f, b["person"].name, lid))
                if b["person"].token in body:
                    raise Refusal(
                        "cross-person check: %s's file %s contains %s's "
                        "private token. NOTHING WAS PUBLISHED."
                        % (a["person"].name, f, b["person"].name))
    if len(staged) > 1:
        log("  cross-person: %d directories checked against each other"
            % len(staged))


def _warn_shared_exposure(everyone, targets, roster_dir, log, root=None):
    """Say, BEFORE ten minutes of rendering, that this run is going to refuse.

    engine/exposure.py reads every file in data/rosters/ and labels players
    with the leagues that also hold them - by name, on the page. In a
    single-owner War Room that is a feature. In a multi-tenant publish it is a
    cross-tenant leak: a page built for one person will name another person's
    league (or the owner's own), and the pre-flight will refuse the run.

    THIS WARNING MUST NOT CRY WOLF. It predicts a refusal, so it is only
    honest while the leak can actually reach the page. render_person confines
    each person to a rosters directory holding only their own leagues, but
    only for renderers whose CLI advertises --roster-dir; the ones that do are
    confined at the source and cannot leak. So the prediction is asked of the
    renderers themselves, and when every one of them is confined there is
    nothing to warn about and this says nothing at all.

    Nothing is silenced here. This only turns a late refusal into an early,
    legible one - and stays quiet when there is no longer a refusal coming.
    """
    labels = roster_labels(roster_dir)
    if not labels:
        return
    claimed = set()
    for p in everyone:
        claimed.update(p.leagues)
    for p in targets:
        strangers = [(lid, name) for lid, name in labels.items()
                     if lid not in p.leagues]
        if not strangers:
            continue
        leaky = [s.module for s in PAGES
                 if not renderer_supports(s.module, "--roster-dir", root=root)]
        if not leaky:
            # Every renderer takes the confined directory. The strangers are
            # still on disk, but no page this run builds can read them.
            return
        log("")
        log("NOTE - %d renderer(s) are not confined to %s's own rosters."
            % (len(leaky), p.name))
        log("  data/rosters/ holds %d roster(s) for league(s) %s does not own:"
            % (len(strangers), p.name))
        for lid, name in strangers:
            who = ("another person in users.yaml" if lid in claimed
                   else "the owner, or somebody not in users.yaml")
            log("    %-24s named %-28r (%s)" % (lid, name, who))
        log("  This pipeline hands each renderer a rosters directory holding "
            "only that person's leagues, but only to renderers whose CLI "
            "advertises --roster-dir. These %d do not, and so still read the "
            "whole directory: %s" % (len(leaky), ", ".join(leaky)))
        log("  THIS IS NOT A PREDICTION THAT THE RUN WILL REFUSE. Whether it "
            "does depends on whether one of them actually prints a foreign "
            "league name - engine/exposure.py is the reader that does, and "
            "the renderer carrying it is confined. If any of the above does "
            "name a stranger, the pre-flight will catch it and nothing will "
            "be published for anyone. See docs/DEPLOY.md, \"cross-league "
            "exposure\".")
        break


def _report_orphans(public_dir, people, log, prune=False):
    orph = orphans(public_dir, people)
    if not orph:
        return
    log("")
    log("ORPHANS — %d directory/ies under %s belong to nobody in users.yaml:"
        % (len(orph), public_dir))
    for d in orph:
        log("  %s/%s/" % (public_dir, d))
    if prune:
        for d in orph:
            shutil.rmtree(os.path.join(public_dir, d), ignore_errors=True)
            log("  pruned %s" % d)
    else:
        log("They are still serving pages. Remove them with "
            "./publish.sh --prune once you are sure nobody needs them.")


def cmd_check(args, log=print):
    code, problems = check_heartbeat(
        users_path=args.users, heartbeat_path=args.heartbeat,
        public_dir=args.out_dir, expected_week=args.week,
        max_age_hours=args.max_age_hours, league_dir=args.league_dir,
        roster_dir=args.roster_dir, log=log)
    if code == 0:
        log("PUBLISH HEARTBEAT OK — every person's published pages are "
            "present, fresh and stamped for the expected week.")
        return 0
    log("PUBLISH HEARTBEAT FAILED — %d problem(s):" % len(problems))
    for p in problems:
        log("  - %s" % p)
    log("")
    log("Re-publish with ./publish.sh, then run this again.")
    return code


def cmd_list(args, log=print):
    try:
        people = load_users(args.users, league_dir=args.league_dir)
    except ConfigError as exc:
        log(str(exc))
        return 2
    log("%-24s %-32s %-14s %s" % ("PERSON", "EMAIL", "TOKEN", "LEAGUES"))
    for p in people:
        log("%-24s %-32s %-14s %s"
            % (p.name[:24], p.email[:32], "…" + p.token[-4:] + " " + p.fp[:6],
               ", ".join(p.leagues)))
    log("")
    log("Tokens are shown only as their last 4 characters and a fingerprint. "
        "The full token is the private URL — read it from users.yaml.")
    return 0


def cmd_new_token(args, log=print):
    tok = new_token()
    problems = token_problems(tok)
    if problems:                      # cannot happen; proves the floor holds
        log("generated token failed its own validation: %s"
            % "; ".join(problems))
        return 2
    log(tok)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="publish.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Publish one private copy of War Room per person in "
                    "users.yaml.",
        epilog="COMMANDS\n"
               "  (none)           render, assert and publish everyone\n"
               "  check-heartbeat  fail (non-zero) if any publish is stale\n"
               "  list             who is configured, without their tokens\n"
               "  new-token        print one unguessable token\n")
    ap.add_argument("command", nargs="?", default="publish",
                    choices=["publish", "check-heartbeat", "list",
                             "new-token"])
    ap.add_argument("--person", default=None,
                    help="publish only this person (their `name` in "
                         "users.yaml)")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--dry-run", action="store_true",
                    help="render and assert everything, print the manifest, "
                         "write nothing")
    ap.add_argument("--plan", action="store_true",
                    help="print the allowlist for each person without running "
                         "a renderer (implies --dry-run)")
    ap.add_argument("--prune", action="store_true",
                    help="delete published directories that belong to nobody "
                         "in users.yaml")
    ap.add_argument("--users", default=DEFAULT_USERS)
    ap.add_argument("--out-dir", default=DEFAULT_PUBLIC,
                    help="where the per-person directories go (default: "
                         "public/)")
    # Default DEFERRED, not bound here: an explicit --heartbeat wins, but
    # otherwise the file belongs under --root. Binding it to the real repo
    # at import time meant a sandboxed test publish (--root /tmp/...)
    # silently overwrote the OWNER'S live publish-heartbeat.json, which is
    # the file check-heartbeat reads to decide whether the real publish is
    # stale. See resolve_heartbeat().
    ap.add_argument("--heartbeat", default=None,
                    help="where the aggregate heartbeat goes (default: "
                         "publish-heartbeat.json under --root, or the "
                         "project root)")
    ap.add_argument("--league-dir", default=None,
                    help="override leagues/ (tests only)")
    ap.add_argument("--roster-dir", default=None,
                    help="override data/rosters/ (tests only; read-only)")
    ap.add_argument("--root", default=None,
                    help="project root the renderers run in (tests only)")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds one renderer may take (default 1800)")
    ap.add_argument("--max-age-hours", type=float,
                    default=DEFAULT_MAX_AGE_HOURS,
                    help="check-heartbeat: how old a publish may be "
                         "(default %.0f)" % DEFAULT_MAX_AGE_HOURS)
    return ap


def resolve_heartbeat(args):
    """Where the aggregate heartbeat goes, given --heartbeat and --root.

    An explicit --heartbeat is obeyed exactly. Otherwise the file lands
    beside the tree the renderers actually ran in: a test that redirects
    everything else into a sandbox with --root must not reach back into
    the owner's checkout and overwrite the one file check-heartbeat
    trusts to say whether the REAL publish is stale.
    """
    if args.heartbeat:
        return args.heartbeat
    root = getattr(args, "root", None)
    return os.path.join(os.path.abspath(root) if root else HERE,
                        os.path.basename(DEFAULT_HEARTBEAT))


def main(argv=None, log=print):
    args = build_parser().parse_args(argv)
    args.heartbeat = resolve_heartbeat(args)
    if args.plan:
        args.dry_run = True
    if args.command == "check-heartbeat":
        return cmd_check(args, log=log)
    if args.command == "list":
        return cmd_list(args, log=log)
    if args.command == "new-token":
        return cmd_new_token(args, log=log)
    return cmd_publish(args, log=log)


if __name__ == "__main__":
    sys.exit(main())
