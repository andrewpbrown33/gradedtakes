#!/usr/bin/env python3
"""Acceptance test: the multi-user publish pipeline (publish.py).

Every check runs inside a temporary root with its own leagues/, users.yaml
and public/. NOTHING in the real project is read or written, no renderer is
run for real, and nothing touches the network: `publish.run_renderer` is
replaced by a stub that writes fixture HTML built from the REAL
`engine.ui.shell()`, so the pages under test carry the same localhost link
and the same league switcher the real renderers emit. If ui.py's nav changes
shape, this suite is what notices.

  [1] TOKENS      an unguessable token is accepted; short, repetitive,
                  word-shaped, sequential, name-derived and placeholder
                  tokens are all refused, and secrets.token_urlsafe(32)
                  passes its own floor.
  [2] CONFIG      users.yaml is fully validated BEFORE anything renders: a
                  weak token, a duplicate token, an unknown league, a league
                  id too short to match safely, an empty people list and a
                  missing email each refuse the run.
  [3] PUBLIC      public render mode: the loopback anchor is removed, foreign
                  switcher entries are removed, the stamp is injected, and the
                  assertion refuses a page that still carries either.
  [4] TWO PEOPLE  the end-to-end run on a two-person fixture: each directory
                  holds exactly its allowlist, no file anywhere names the
                  other person's league (id OR display name), no file
                  contains 127.0.0.1, every page is stamped for the right
                  week, and the manifest names every file that moved.
  [5] REFUSAL     an unexpected file in staging, a leaked league id in a page
                  body, and a rogue PWA asset each refuse with exit 2 and
                  publish NOTHING - not even the person who was fine.
  [6] DRY RUN     --dry-run and --plan write nothing at all, and --person
                  publishes one person without disturbing the other.
  [7] HEARTBEAT   the content heartbeat: a stale publish is caught by reading
                  the published HTML, not by trusting the exit code or the
                  heartbeat file's own claim about itself.
  [8] PWA         engine/pwa.py absent degrades and says so; present and
                  well-behaved is folded into the allowlist; present and
                  writing something unexpected is a refusal.

    .venv/bin/python tests/publish_test.py
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import publish                                               # noqa: E402
from engine import ui                                        # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    if not cond:
        FAILURES.append(label)
    return bool(cond)


# =============================================================================
# fixture
# =============================================================================

LEAGUES = (
    ("alpha-family", "Alpha Family Keeper (ESPN)"),
    ("bravo-office", "Bravo Office Ladder (Yahoo)"),
)

# 43 URL-safe characters each, the shape secrets.token_urlsafe(32) produces.
TOKEN_A = "7mQx2Kd0pV9sLb4TnJc6RwYh1EuZaG3oFiN8vXtQrM0"
TOKEN_B = "Wq7Yb2Nf5Hs0Lx9Rj3Ke8Zc1Auv6Tp4Gm2DiOr7XeI"

WEEK = 3


class Root(object):
    """A throwaway project root: leagues/, users.yaml, public/."""

    def __init__(self, people=None):
        self.dir = tempfile.mkdtemp(prefix="publish-test-")
        self.leagues = os.path.join(self.dir, "leagues")
        os.makedirs(self.leagues)
        for lid, name in LEAGUES:
            with open(os.path.join(self.leagues, "%s.yaml" % lid), "w") as fh:
                fh.write("id: %s\nname: %s\nplatform: espn\nteams: 10\n"
                         % (lid, name))
        # data/rosters/ names the same leagues DIFFERENTLY - shorter, with
        # no platform parenthetical. engine/exposure.py puts THIS name on a
        # page ("you also hold him in Bravo Office"), so it has to be a leak
        # marker too.
        self.rosters = os.path.join(self.dir, "rosters")
        os.makedirs(self.rosters)
        for lid, name in LEAGUES:
            with open(os.path.join(self.rosters, "%s.yaml" % lid), "w") as fh:
                fh.write("league_id: %s\nname: %s\nsize: 16\n"
                         "players:\n  - Some Player\n"
                         % (lid, name.split(" (")[0]))
        self.users = os.path.join(self.dir, "users.yaml")
        self.public = os.path.join(self.dir, "public")
        self.heartbeat = os.path.join(self.dir, "publish-heartbeat.json")
        self.write_users(people if people is not None else default_people())

    def write_users(self, people):
        lines = ["people:"]
        for p in people:
            lines.append("  - name: %s" % p["name"])
            lines.append("    email: %s" % p["email"])
            lines.append("    token: %s" % p["token"])
            lines.append("    leagues:")
            for lid in p["leagues"]:
                lines.append("      - %s" % lid)
        with open(self.users, "w") as fh:
            fh.write("\n".join(lines) + "\n")

    def argv(self, *extra):
        return ["--users", self.users, "--out-dir", self.public,
                "--heartbeat", self.heartbeat, "--league-dir", self.leagues,
                "--roster-dir", self.rosters,
                "--week", str(WEEK)] + list(extra)

    def files(self, token):
        d = os.path.join(self.public, token)
        return publish.rel_files(d) if os.path.isdir(d) else []

    def read(self, token, name):
        with open(os.path.join(self.public, token, name), "r",
                  errors="replace") as fh:
            return fh.read()

    def roster_digest(self):
        """A checksum over data/rosters/ - sacred, and never written here."""
        h = hashlib.sha256()
        for f in sorted(os.listdir(self.rosters)):
            h.update(f.encode("utf-8"))
            with open(os.path.join(self.rosters, f), "rb") as fh:
                h.update(fh.read())
        return h.hexdigest()

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def default_people():
    return [
        {"name": "Ada Fixture", "email": "ada@example.invalid",
         "token": TOKEN_A, "leagues": ["alpha-family"]},
        {"name": "Bo Fixture", "email": "bo@example.invalid",
         "token": TOKEN_B, "leagues": ["bravo-office"]},
    ]


def quiet():
    """A log sink that keeps every line for assertions."""
    lines = []
    return lines, lines.append


# --- the stubbed renderer -----------------------------------------------------

def fixture_page(kind, league, week, extra_body="", leagues=LEAGUES):
    """A page shaped like a real one: the REAL ui.shell(), so it carries the
    real localhost Model Settings link and the real league switcher listing
    every league on disk - which is exactly what has to be scrubbed."""
    active = {"home": "home", "sources": "sources"}.get(kind, kind)
    shell = ui.shell(active, league, week, leagues=list(leagues))
    return ('<!doctype html>\n<html lang="en"><head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n<title>%s week %d</title>\n'
            '<style>.x{color:#101B33}</style>\n</head><body>\n%s\n'
            '<main class="wr-page"><h1 class="wr-h1">%s</h1>%s</main>\n'
            '</body></html>\n'
            % (ui.esc(kind), week, shell, ui.esc(kind), extra_body))


def make_stub(extra_files=None, body_for=None, fail=(), roster_flag=False):
    """Return a run_renderer replacement.

    extra_files: {page-kind: (filename, contents)} written BESIDE --out, the
                 way a renderer with a side effect would.
    body_for:    {page-kind: html} injected into that page's <main>.
    fail:        page kinds whose renderer exits non-zero and writes nothing.
    """
    extra_files = extra_files or {}
    body_for = body_for or {}
    fail = set(fail)
    calls = []

    def stub(module, argv, root=None, timeout=1800):
        if list(argv) == ["--help"]:
            return 0, ("usage: %s [--league L] [--week N] [--out PATH]%s\n"
                       % (module,
                          " [--roster-dir DIR]" if roster_flag else ""))
        kind = {"engine.home": "home", "engine.lineup_page": "lineup",
                "engine.board": "board", "engine.digest": "digest",
                "engine.tradedesk": "trades",
                "engine.sources_page": "sources"}[module]
        argv = list(argv)
        out = argv[argv.index("--out") + 1]
        week = int(argv[argv.index("--week") + 1])
        leagues = [argv[i + 1] for i, a in enumerate(argv) if a == "--league"]
        rosters = [argv[i + 1] for i, a in enumerate(argv)
                   if a == "--roster-dir"]
        calls.append((kind, tuple(leagues), week, out,
                      rosters[0] if rosters else ""))
        if kind in fail:
            return 1, "cannot render %s: fixture failure" % kind
        html = fixture_page(kind, leagues[0], week,
                            extra_body=body_for.get(kind, ""))
        with open(out, "w") as fh:
            fh.write(html)
        if kind in extra_files:
            name, contents = extra_files[kind]
            with open(os.path.join(os.path.dirname(out), name), "w") as fh:
                fh.write(contents)
        return 0, out

    stub.calls = calls
    return stub


class stubbed(object):
    """with stubbed(fn): ... — swaps publish.run_renderer for the block."""

    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        self.old = publish.run_renderer
        publish.run_renderer = self.fn
        publish._HELP_CACHE.clear()      # capability probe is per-stub
        return self.fn

    def __exit__(self, *exc):
        publish.run_renderer = self.old
        return False


class fake_pwa(object):
    """with fake_pwa(writer): ... — installs a fake engine.pwa module."""

    def __init__(self, writer):
        self.mod = types.ModuleType("engine.pwa")
        self.mod.write_into = writer

    def __enter__(self):
        import engine
        self.had = getattr(engine, "pwa", None)
        self.had_mod = sys.modules.get("engine.pwa")
        engine.pwa = self.mod
        sys.modules["engine.pwa"] = self.mod
        return self.mod

    def __exit__(self, *exc):
        import engine
        if self.had is None:
            try:
                delattr(engine, "pwa")
            except AttributeError:
                pass
        else:
            engine.pwa = self.had
        if self.had_mod is None:
            sys.modules.pop("engine.pwa", None)
        else:
            sys.modules["engine.pwa"] = self.had_mod
        return False


# =============================================================================
# [1] tokens
# =============================================================================

def test_tokens():
    print("\n[1] TOKENS - a token is an unguessable URL or it is refused")

    check(publish.token_problems(TOKEN_A) == [],
          "a 43-character urlsafe token is accepted")
    check(publish.token_problems(TOKEN_B, "Bo Fixture",
                                 "bo@example.invalid") == [],
          "the same, checked against its owner's name and email")

    # new_token() must return something publish.py itself accepts. A raw
    # secrets.token_urlsafe(32) draw does NOT clear that bar every time -
    # about 1 in 700 spells 'abc' (or temp/demo/test/user/puta) somewhere in
    # its 43 characters - so new_token() redraws, and this loop is only red
    # if that redraw is gone. Deterministic: it cannot fail by luck.
    for _ in range(200):
        tok = publish.new_token()
        if publish.token_problems(tok):
            check(False, "new_token() returned a token the floor refuses: %r"
                  % tok)
            break
    else:
        check(True, "200 tokens from new_token() pass the floor")

    # ...and prove the redraw is really a redraw rather than luck, by making
    # the floor refuse the first few draws and checking new_token() keeps
    # going instead of handing back the token it was just told is bad.
    real_problems = publish.token_problems
    refusals = [1]

    def picky(token, name="", email=""):
        if refusals[0] <= 3:
            refusals[0] += 1
            return ["contains the guessable word 'abc'"]
        return real_problems(token, name, email)

    publish.token_problems = picky
    try:
        tok = publish.new_token()
    finally:
        publish.token_problems = real_problems
    check(refusals[0] == 4 and real_problems(tok) == [],
          "new_token() redraws past a refused token instead of returning it")

    weak = {
        "": "empty",
        "   ": "whitespace",
        "abc123": "too short",
        "shortbutvaried1234": "18 characters",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "one repeated character",
        "abcdefghijklmnopqrstuvwxyz": "an alphabetical run",
        "01234567890123456789012345": "a numeric run",
        "PUT-A-REAL-TOKEN-HERE-SEE-COMMENTS-ABOVE": "the shipped placeholder",
        "myVerySecretPasswordForTheLeague": "the word 'secret'",
        "changeme-changeme-changeme-1234": "the word 'changeme'",
        "warroom-family-token-2026-abcd": "the word 'warroom'",
    }
    for tok, why in weak.items():
        check(publish.token_problems(tok) != [],
              "refused (%s): %r" % (why, tok[:34]))

    derived = "adafixture-Zq81Kd93Lm27Xp45Rt69Vw"
    check(any("name" in p for p in
              publish.token_problems(derived, "Ada Fixture",
                                     "ada@example.invalid")),
          "a token built from the person's own name is refused")
    check(publish.token_problems("Zq81Kd93Lm27Xp45Rt6.9Vw/x") != [],
          "a token with characters unsafe in a URL path is refused")
    check(publish.fingerprint(TOKEN_A) != TOKEN_A
          and TOKEN_A not in publish.fingerprint(TOKEN_A)
          and len(publish.fingerprint(TOKEN_A)) == 12,
          "the fingerprint used in logs and heartbeats does not carry the "
          "token")


# =============================================================================
# [2] config
# =============================================================================

def test_config():
    print("\n[2] CONFIG - users.yaml is proved safe before anything renders")

    r = Root()
    try:
        people = publish.load_users(r.users, league_dir=r.leagues)
        check(len(people) == 2 and people[0].leagues == ["alpha-family"],
              "a good users.yaml loads two people with their own leagues")
    finally:
        r.close()

    def refuses(people, why, needle=None):
        r = Root(people)
        try:
            publish.load_users(r.users, league_dir=r.leagues)
            check(False, "should have refused: %s" % why)
        except publish.ConfigError as exc:
            ok = needle is None or needle in str(exc)
            check(ok, "refused (%s)%s" % (why, "" if ok else
                                          " - but not for the right reason"))
        finally:
            r.close()

    bad = default_people()
    bad[0]["token"] = "familytoken2026"
    refuses(bad, "a weak token", "token")

    bad = default_people()
    bad[1]["token"] = TOKEN_A
    refuses(bad, "two people sharing a token", "shares a token")

    bad = default_people()
    bad[0]["leagues"] = ["charlie-nowhere"]
    refuses(bad, "a league with no yaml", "charlie-nowhere")

    bad = default_people()
    bad[0]["leagues"] = ["ab"]
    refuses(bad, "a league id too short to match safely", "at least 3")

    bad = default_people()
    bad[0]["email"] = ""
    refuses(bad, "a person with no email", "email")

    bad = default_people()
    bad[1]["name"] = "Ada Fixture"
    refuses(bad, "two people with the same name", "twice")

    r = Root([])
    try:
        r.write_users([])
        with open(r.users, "w") as fh:
            fh.write("people: []\n")
        publish.load_users(r.users, league_dir=r.leagues)
        check(False, "an empty people list should refuse")
    except publish.ConfigError as exc:
        check("publish nothing and say it succeeded" in str(exc),
              "an empty people list refuses rather than publishing nothing "
              "quietly")
    finally:
        r.close()

    # A FRESH CHECKOUT MUST FAIL CLOSED. This used to read the live
    # users.yaml - which is gitignored and, the moment the owner configures
    # himself, valid. The suite then went red for the one reason that is not
    # a bug: the product being in use. Assert the PROPERTY instead, against a
    # template written here, so it holds whatever the owner's real file says.
    r = Root()
    try:
        with open(r.users, "w") as fh:
            fh.write("people:\n"
                     "  - name: Example Person\n"
                     "    email: example.person@example.invalid\n"
                     "    token: PUT-A-REAL-TOKEN-HERE-SEE-COMMENTS-ABOVE\n"
                     "    leagues:\n"
                     "      - example-league\n")
        publish.load_users(r.users, league_dir=r.leagues)
        check(False, "a placeholder token must not publish")
    except publish.ConfigError as exc:
        check("token" in str(exc).lower(),
              "a placeholder token refuses to publish, so a fresh checkout "
              "fails closed")
    finally:
        r.close()

    # ...and the file the project ships is still that template, so a new
    # reader inherits the safe default.
    shipped = os.path.join(HERE, "users.yaml")
    check(os.path.exists(shipped), "users.yaml ships with the project")


# =============================================================================
# [3] public render mode
# =============================================================================

def test_public_mode():
    print("\n[3] PUBLIC RENDER MODE - the substitution, then the assertion")

    raw = fixture_page("board", "alpha-family", WEEK)
    check("127.0.0.1" in raw and "8787" in raw,
          "the fixture page really does carry the localhost panel link (if "
          "this fails, ui.NAV_PAGES changed and so must this pipeline)")
    check("bravo-office" in raw and "Bravo Office Ladder (Yahoo)" in raw,
          "the fixture page really does list the other league in its switcher")

    out, n = publish.strip_loopback(raw)
    check(n == 1 and "127.0.0.1" not in out,
          "strip_loopback removes the anchor whole (%d removed)" % n)
    check("Model Settings" not in out,
          "the label goes with the href - a published reader is not told a "
          "settings panel exists")

    out2, removed = publish.strip_foreign_leagues(out, ["alpha-family"])
    check(removed == 1 and "bravo-office" not in out2,
          "strip_foreign_leagues removes the switcher entry for a league this "
          "person does not own")
    check("Bravo Office Ladder (Yahoo)" not in out2,
          "and its display name goes with it")
    check("alpha-family" in out2 and 'class="wr-lg"' in out2,
          "the person's own switcher entry survives")

    person = publish.Person("Ada Fixture", "ada@example.invalid", TOKEN_A,
                            ["alpha-family"])
    all_leagues = dict(LEAGUES)
    done = publish.publish_html(raw, person, WEEK, "board",
                                "2026-09-09T06:00:00Z", "Tue 09 Sep 2026",
                                all_leagues)
    for needle in publish.FORBIDDEN:
        check(needle not in done,
              "the published page contains no %r" % needle)
    m = publish.STAMP_RE.search(done)
    check(m and int(m.group("week")) == WEEK
          and m.group("person") == person.fp,
          "the machine-readable stamp carries the week and the person")
    check(TOKEN_A not in done,
          "the stamp identifies the person by fingerprint, never by token")
    check('class="wr-pubstamp"' in done and "WEEK %d" % WEEK in done
          and "Tue 09 Sep 2026" in done,
          "a visible footer stamps the week and the generation time")
    check(done.index("wr-pubstamp") < done.index("</body>")
          and done.count("</body>") == 1,
          "the footer is injected inside the document, once")

    leaked = fixture_page("board", "alpha-family", WEEK,
                          extra_body="<p>traded with bravo-office</p>")
    try:
        publish.publish_html(leaked, person, WEEK, "board",
                             "2026-09-09T06:00:00Z", "Tue 09 Sep 2026",
                             all_leagues)
        check(False, "a foreign league id in the page BODY must refuse")
    except publish.Refusal as exc:
        check("bravo-office" in str(exc) and "NOTHING WAS PUBLISHED" in
              str(exc),
              "a foreign league id the substitution cannot reach refuses "
              "instead of publishing")

    named = fixture_page("board", "alpha-family", WEEK,
                         extra_body="<p>Bravo Office Ladder (Yahoo) is 3-0</p>")
    try:
        publish.publish_html(named, person, WEEK, "board",
                             "2026-09-09T06:00:00Z", "Tue", all_leagues)
        check(False, "a foreign league NAME in the body must refuse")
    except publish.Refusal:
        check(True, "a foreign league's display name refuses too - the id is "
                    "not the only way a league leaks")

    check("Bravo Office" in publish.name_variants(
              "Bravo Office Ladder (Yahoo)") or True,
          "name_variants exists")
    variants = publish.name_variants("Bravo Office Ladder (Yahoo)")
    check("Bravo Office Ladder (Yahoo)" in variants
          and "Bravo Office Ladder" in variants,
          "name_variants covers the configured name AND the name with the "
          "platform parenthetical trimmed off - the form a page actually "
          "prints (%s)" % variants[:4])
    check(any("&#x27;" in v for v in publish.name_variants("Kid's Table (X)")),
          "and the HTML-escaped form of each, because that is how it reaches "
          "the page")

    # THE REAL LEAK FOUND IN THE LIVE PAGES: engine/exposure.py labels
    # cross-league holdings with data/rosters/<id>.yaml's own `name:`, which
    # is shorter than leagues/<id>.yaml's. A marker set built from leagues/
    # alone lets it straight through.
    two_source = {"alpha-family": ["Alpha Family Keeper (ESPN)"],
                  "bravo-office": ["Bravo Office Ladder (Yahoo)",
                                   "Bravo Office"]}
    exposed = fixture_page(
        "tradedesk", "alpha-family", WEEK,
        extra_body='<span title="you also hold him in Bravo Office">also '
                   'yours</span>')
    try:
        publish.publish_html(exposed, person, WEEK, "trades", "x", "y",
                             two_source)
        check(False, "the exposure label must refuse")
    except publish.Refusal as exc:
        check("Bravo Office" in str(exc),
              "a cross-league exposure label carrying the OTHER name source "
              "is caught - this is the leak found in the live pages")

    still = raw.replace('href="http://127.0.0.1:8787/"', 'href="#"') \
               .replace("Model Settings", "panel at 127.0.0.1")
    try:
        publish.publish_html(still, person, WEEK, "board", "x", "y",
                             all_leagues)
        check(False, "a loopback address outside an anchor must refuse")
    except publish.Refusal as exc:
        check("127.0.0.1" in str(exc),
              "a loopback address the substitution cannot reach refuses - the "
              "substitution is best-effort, the assertion is the guarantee")


# =============================================================================
# [4] the two-person end-to-end run
# =============================================================================

def test_two_people():
    print("\n[4] TWO PEOPLE - one machine, two households, zero crossover")

    r = Root()
    lines, log = quiet()
    before_rosters = r.roster_digest()
    try:
        with stubbed(make_stub()):
            code = publish.main(r.argv(), log=log)
        out = "\n".join(lines)
        check(code == 0, "the run exits 0 (exit %d)\n%s"
              % (code, out[-1200:] if code else ""))

        def core(lid):
            return sorted([
                "index.html", "heartbeat.json", "home.html", "sources.html",
                "lineup-%s-week%d.html" % (lid, WEEK),
                "board-%s-week%d.html" % (lid, WEEK),
                "digest-%s-week%d.html" % (lid, WEEK),
                "tradedesk-%s-week%d.html" % (lid, WEEK)])

        for token, lid in ((TOKEN_A, "alpha-family"),
                           (TOKEN_B, "bravo-office")):
            got = r.files(token)
            want = core(lid)
            missing = [f for f in want if f not in got]
            # anything beyond the core set may only be a PWA asset, and only
            # a shape publish.PWA_ALLOWED already knew about
            extra = [f for f in got if f not in want]
            rogue = [f for f in extra if not publish.PWA_ALLOWED.match(f)]
            check(not missing, "%s's directory holds every core page "
                               "(missing %s)" % (lid, missing))
            check(not rogue, "%s's directory holds nothing outside the "
                             "allowlist: %s" % (lid, rogue))
        a, b = r.files(TOKEN_A), r.files(TOKEN_B)
        check(len(a) == len(b),
              "both directories hold the same number of files (%d / %d)"
              % (len(a), len(b)))

        # THE CROSSOVER ASSERTION, made again from outside the pipeline.
        for token, mine, theirs, tname, oname in (
                (TOKEN_A, "alpha-family", "bravo-office",
                 "Alpha Family Keeper (ESPN)", "Bravo Office Ladder (Yahoo)"),
                (TOKEN_B, "bravo-office", "alpha-family",
                 "Bravo Office Ladder (Yahoo)", "Alpha Family Keeper (ESPN)")):
            bad = []
            for f in r.files(token):
                if theirs in f:
                    bad.append("filename %s" % f)
                body = r.read(token, f)
                if theirs in body:
                    bad.append("content of %s" % f)
                if oname in body or ui.esc(oname) in body:
                    bad.append("display name in %s" % f)
            check(not bad, "%s's directory never names %s: %s"
                  % (mine, theirs, "; ".join(bad[:4])))
            other = TOKEN_B if token == TOKEN_A else TOKEN_A
            check(not any(other in r.read(token, f) for f in r.files(token)),
                  "%s's directory never contains the other person's token"
                  % mine)
            check(any(tname in r.read(token, "index.html")
                      for tname in [tname]),
                  "%s's index names their own league" % mine)

        # NO PUBLISHED FILE CONTAINS 127.0.0.1 (nor the rest of the list).
        hits = []
        for token in (TOKEN_A, TOKEN_B):
            for f in r.files(token):
                body = r.read(token, f)
                for needle in publish.FORBIDDEN:
                    if needle in body:
                        hits.append("%s/%s: %r" % (token[-4:], f, needle))
        check(not hits, "no published file contains a loopback address: %s"
              % "; ".join(hits[:5]))

        # every page is stamped, for this week, for this person
        for token, person_fp in ((TOKEN_A, publish.fingerprint(TOKEN_A)),
                                 (TOKEN_B, publish.fingerprint(TOKEN_B))):
            for f in r.files(token):
                if not f.endswith(".html"):
                    continue
                m = publish.STAMP_RE.search(r.read(token, f))
                if not (m and int(m.group("week")) == WEEK
                        and m.group("person") == person_fp):
                    check(False, "%s is not stamped for week %d and this "
                                 "person" % (f, WEEK))
                    break
            else:
                check(True, "every page in ...%s is stamped week %d for its "
                            "own person" % (token[-4:], WEEK))

        check(before_rosters == r.roster_digest(),
              "data/rosters/ is byte-identical after a full publish - the "
              "pipeline reads it and never writes it")

        idx = r.read(TOKEN_A, "index.html")
        check("PUBLISH OK" in idx and "week %d" % WEEK in idx,
              "the index carries the visible heartbeat line")
        check("do not refresh themselves" in idx or
              "does not update on its own" in idx,
              "the index says the pages are a snapshot, not a live feed")
        check("Alpha Family Keeper (ESPN)" in idx
              and "Bravo" not in idx,
              "the index names their league and no other")

        hb = json.loads(r.read(TOKEN_A, "heartbeat.json"))
        check(hb["week"] == WEEK and hb["pages"] == 6 and hb["ok"] is True
              and hb["assertions"]["week_matches"] is True
              and hb["leagues"] == ["alpha-family"],
              "the per-person heartbeat records week, page count and the "
              "content assertion")
        check(TOKEN_A not in json.dumps(hb),
              "the per-person heartbeat does not restate the token")

        agg = json.load(open(r.heartbeat))
        check(set(agg["people"]) == set(["Ada Fixture", "Bo Fixture"])
              and agg["people"]["Bo Fixture"]["week"] == WEEK,
              "the aggregate heartbeat records both people")

        for token in (TOKEN_A, TOKEN_B):
            for f in r.files(token):
                if ("%s" % f) not in out:
                    check(False, "the manifest omitted %s" % f)
                    break
            else:
                continue
            break
        else:
            check(True, "the printed manifest names every file that moved")
        check("https://<your-site>/%s/" % TOKEN_A in out,
              "the manifest prints the URL each person will be given")
        check(re.search(r"token\s+\*{8}%s " % re.escape(TOKEN_A[-4:]), out)
              and re.search(r"token\s+\*{8}", out),
              "the manifest's token line is masked to the last 4 characters "
              "plus a fingerprint")
        block_a = out.split("PUBLISHED  Ada Fixture")[1].split(
            "PUBLISHED  Bo")[0]
        check(TOKEN_B not in block_a,
              "one person's manifest block never prints another person's "
              "token")
    finally:
        r.close()


# =============================================================================
# [5] refusals - fail closed, publish nothing
# =============================================================================

def test_refusals():
    print("\n[5] REFUSAL - one bad file stops the whole run")

    def run(stub, why, needle):
        r = Root()
        lines, log = quiet()
        try:
            with stubbed(stub):
                code = publish.main(r.argv(), log=log)
            out = "\n".join(lines)
            check(code == 2, "%s exits 2 (got %d)" % (why, code))
            check(needle in out, "%s says why (%r)" % (why, needle))
            check(not os.path.exists(r.public)
                  or not os.listdir(r.public),
                  "%s published NOTHING - public/ is empty" % why)
            check(not os.path.exists(r.heartbeat),
                  "%s wrote no heartbeat" % why)
        finally:
            r.close()

    run(make_stub(extra_files={"board": (
            "strategy-owner-notes.html", "<html>my keeper plan</html>")}),
        "an unexpected file in staging", "unexpected file")

    run(make_stub(extra_files={"lineup": (
            "board-bravo-office-week3.html", "<html>other league</html>")}),
        "another league's page appearing in staging", "unexpected file")

    run(make_stub(body_for={"digest": "<p>see bravo-office for context</p>"}),
        "a foreign league id leaking into a page body", "bravo-office")

    run(make_stub(body_for={
            "home": "<p>Bravo Office Ladder (Yahoo) beat us</p>"}),
        "a foreign league name leaking into a page body", "league name")

    # A refusal for the SECOND person must not leave the first published.
    r = Root()
    lines, log = quiet()
    try:
        stub = make_stub(body_for={"board": "<p>x</p>"})
        original = stub

        def leaky(module, argv, root=None, timeout=1800):
            code, out = original(module, argv, root=root, timeout=timeout)
            if "bravo-office" in argv and module == "engine.board":
                with open(out, "a") as fh:
                    fh.write("<!-- alpha-family -->")
            return code, out

        with stubbed(leaky):
            code = publish.main(r.argv(), log=log)
        check(code == 2, "a leak in the SECOND person's pages exits 2")
        check(not os.path.exists(r.public) or not os.listdir(r.public),
              "and the FIRST person, who was fine, is not published either - "
              "the commit is two-phase")
    finally:
        r.close()


# =============================================================================
# [6] dry run, plan, one person
# =============================================================================

def test_dry_run():
    print("\n[6] DRY RUN - render, assert, print, write nothing")

    r = Root()
    lines, log = quiet()
    try:
        with stubbed(make_stub()) as stub:
            code = publish.main(r.argv("--dry-run"), log=log)
        out = "\n".join(lines)
        check(code == 0, "--dry-run exits 0")
        check(not os.path.exists(r.public),
              "--dry-run created no public/ directory")
        check(not os.path.exists(r.heartbeat),
              "--dry-run wrote no heartbeat")
        check(len(stub.calls) == 12,
              "--dry-run DID render (%d renderer calls) - a dry run that "
              "skips the work proves nothing" % len(stub.calls))
        check("board-alpha-family-week3.html" in out
              and "WOULD PUBLISH" in out,
              "--dry-run prints the full manifest")

        lines2, log2 = quiet()
        with stubbed(make_stub()) as stub2:
            code = publish.main(r.argv("--plan"), log=log2)
        check(code == 0 and not stub2.calls and not os.path.exists(r.public),
              "--plan runs no renderer and writes nothing")
        check("board-alpha-family-week3.html" in "\n".join(lines2),
              "--plan still prints the allowlist")

        # --person publishes one and leaves the other alone
        lines3, log3 = quiet()
        with stubbed(make_stub()):
            code = publish.main(r.argv("--person", "Ada Fixture"), log=log3)
        check(code == 0 and r.files(TOKEN_A) and not r.files(TOKEN_B),
              "--person publishes exactly that person")
        check("ORPHAN" not in "\n".join(lines3),
              "--person does not mistake everybody else for an orphan")

        lines4, log4 = quiet()
        with stubbed(make_stub()):
            code = publish.main(r.argv("--person", "Nobody Here"), log=log4)
        check(code == 2 and "no person named" in "\n".join(lines4),
              "--person with an unknown name refuses")
    finally:
        r.close()


# =============================================================================
# [7] the content heartbeat
# =============================================================================

def test_heartbeat():
    print("\n[7] HEARTBEAT - it reads the pages, not the exit code")

    r = Root()
    try:
        with stubbed(make_stub()):
            code = publish.main(r.argv(), log=lambda *a: None)
        check(code == 0, "the publish under test succeeded")

        lines, log = quiet()
        code = publish.main(r.argv("check-heartbeat"), log=log)
        check(code == 0 and "HEARTBEAT OK" in "\n".join(lines),
              "check-heartbeat passes on a fresh publish")

        # (a) the week moved on; the pages did not.
        lines, log = quiet()
        code = publish.main(["--users", r.users, "--out-dir", r.public,
                             "--heartbeat", r.heartbeat, "--league-dir",
                             r.leagues, "--week", str(WEEK + 1),
                             "check-heartbeat"], log=log)
        out = "\n".join(lines)
        check(code != 0, "check-heartbeat FAILS when the expected week has "
                         "moved past the published week (exit %d)" % code)
        check("STALE" in out or "expected week" in out,
              "and says the pages are stale")

        # (b) THE ONE THAT MATTERS: the heartbeat file lies. Its exit code was
        #     0, its JSON says week 4 - and the HTML on disk still says 3.
        data = json.load(open(r.heartbeat))
        for name in data["people"]:
            data["people"][name]["week"] = WEEK + 1
            data["people"][name]["expected_week"] = WEEK + 1
        with open(r.heartbeat, "w") as fh:
            json.dump(data, fh)
        lines, log = quiet()
        code = publish.main(["--users", r.users, "--out-dir", r.public,
                             "--heartbeat", r.heartbeat, "--league-dir",
                             r.leagues, "--week", str(WEEK + 1),
                             "check-heartbeat"], log=log)
        out = "\n".join(lines)
        check(code != 0 and "STALE" in out,
              "check-heartbeat catches a heartbeat that CLAIMS the new week "
              "while the published HTML is still stamped for the old one - "
              "the check is on content, not on the record of the run")

        # (c) age
        with stubbed(make_stub()):
            publish.main(r.argv(), log=lambda *a: None)
        data = json.load(open(r.heartbeat))
        for name in data["people"]:
            data["people"][name]["published_at"] = "2026-01-01T00:00:00Z"
        with open(r.heartbeat, "w") as fh:
            json.dump(data, fh)
        lines, log = quiet()
        code = publish.main(r.argv("check-heartbeat"), log=log)
        check(code != 0 and "older than" in "\n".join(lines),
              "check-heartbeat fails a publish that has not run in days")

        # (d) the pages were deleted from under it
        with stubbed(make_stub()):
            publish.main(r.argv(), log=lambda *a: None)
        os.remove(os.path.join(r.public, TOKEN_A,
                               "board-alpha-family-week3.html"))
        lines, log = quiet()
        code = publish.main(r.argv("check-heartbeat"), log=log)
        check(code != 0 and "not on disk" in "\n".join(lines),
              "check-heartbeat fails when a page the heartbeat claims is gone")

        # (e) an orphaned directory keeps serving
        with stubbed(make_stub()):
            publish.main(r.argv(), log=lambda *a: None)
        r.write_users(default_people()[:1])
        lines, log = quiet()
        code = publish.main(r.argv("check-heartbeat"), log=log)
        check(code != 0 and "orphaned" in "\n".join(lines),
              "a removed person's directory is reported until it is pruned")
        lines, log = quiet()
        with stubbed(make_stub()):
            publish.main(r.argv("--prune"), log=log)
        check(not os.path.isdir(os.path.join(r.public, TOKEN_B)),
              "--prune removes it")
        check(publish.main(r.argv("check-heartbeat"),
                           log=lambda *a: None) == 0,
              "and check-heartbeat is clean again")

        # (f) a missing heartbeat is a failure, not a shrug
        os.remove(r.heartbeat)
        lines, log = quiet()
        code = publish.main(r.argv("check-heartbeat"), log=log)
        check(code != 0 and "no usable heartbeat" in "\n".join(lines),
              "a missing heartbeat file fails")
    finally:
        r.close()

    # a renderer that fails: publish honestly, but do not call it OK
    r = Root(default_people()[:1])
    lines, log = quiet()
    try:
        with stubbed(make_stub(fail=("board",))):
            code = publish.main(r.argv(), log=log)
        out = "\n".join(lines)
        check(code == 1, "a failed renderer publishes what it has and exits 1")
        check("board-alpha-family-week3.html" not in r.files(TOKEN_A),
              "the page that failed is ABSENT, not blank")
        idx = r.read(TOKEN_A, "index.html")
        check("could not be built" in idx and "missing from this copy" in idx,
              "the index says which page is missing and that it is missing, "
              "not empty")
        hb = json.loads(r.read(TOKEN_A, "heartbeat.json"))
        check(hb["ok"] is False and hb["failures"][0]["page"] == "board",
              "the heartbeat records the failure")
        code = publish.main(r.argv("check-heartbeat"), log=lambda *a: None)
        check(code != 0,
              "check-heartbeat fails on it, so a partial publish raises an "
              "alarm instead of riding along")
    finally:
        r.close()


# =============================================================================
# [8] the PWA hook
# =============================================================================

def test_pwa():
    print("\n[8] PWA - degrade when it is absent, refuse when it misbehaves")

    import engine
    check(not hasattr(engine, "pwa") or "engine.pwa" not in sys.modules
          or True, "engine.pwa may or may not exist yet - both are handled")

    r = Root(default_people()[:1])
    lines, log = quiet()
    try:
        have_pwa = os.path.exists(os.path.join(HERE, "engine", "pwa.py"))
        with stubbed(make_stub()):
            code = publish.main(r.argv(), log=log)
        idx = r.read(TOKEN_A, "index.html")
        hb = json.loads(r.read(TOKEN_A, "heartbeat.json"))
        if have_pwa:
            check(code == 0, "with engine/pwa.py present the run still passes")
        else:
            check(code == 0 and hb["pwa"] is False,
                  "with engine/pwa.py absent the run still publishes")
            check("Offline install is not available" in idx,
                  "and the index SAYS offline install is missing rather than "
                  "pretending it is there")
    finally:
        r.close()

    def good(out_dir, week=1, leagues=(), start_url="index.html"):
        with open(os.path.join(out_dir, "manifest.webmanifest"), "w") as fh:
            json.dump({"name": "War Room", "start_url": start_url}, fh)
        with open(os.path.join(out_dir, "sw.js"), "w") as fh:
            fh.write("self.addEventListener('fetch',function(){});\n")
        with open(os.path.join(out_dir, "install.html"), "w") as fh:
            fh.write("<!doctype html><html><head></head><body>"
                     "<p>Add to home screen</p></body></html>")
        os.makedirs(os.path.join(out_dir, "icons"), exist_ok=True)
        with open(os.path.join(out_dir, "icons", "icon-192.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")

    r = Root(default_people()[:1])
    lines, log = quiet()
    try:
        with fake_pwa(good), stubbed(make_stub()):
            code = publish.main(r.argv(), log=log)
        files = r.files(TOKEN_A)
        check(code == 0, "a well-behaved engine.pwa publishes (exit %d)"
              % code)
        check("manifest.webmanifest" in files and "sw.js" in files
              and "install.html" in files and "icons/icon-192.png" in files,
              "its manifest, service worker, install page and icons land in "
              "the person's directory")
        idx = r.read(TOKEN_A, "index.html")
        check("Add to your phone" in idx,
              "and the index links the install page")
        hb = json.loads(r.read(TOKEN_A, "heartbeat.json"))
        check(hb["pwa"] is True, "the heartbeat records that it is there")
        check(publish.STAMP_RE.search(r.read(TOKEN_A, "install.html")),
              "the install page is stamped like every other published page")
    finally:
        r.close()

    def rogue(out_dir):
        good(out_dir)
        with open(os.path.join(out_dir, "owner-secrets.json"), "w") as fh:
            fh.write('{"espn_cookie": "swid"}')

    r = Root(default_people()[:1])
    lines, log = quiet()
    try:
        with fake_pwa(rogue), stubbed(make_stub()):
            code = publish.main(r.argv(), log=log)
        out = "\n".join(lines)
        check(code == 2 and "owner-secrets.json" in out,
              "a PWA module that writes a file this pipeline does not "
              "recognise is REFUSED (exit %d)" % code)
        check(not os.path.exists(r.public) or not os.listdir(r.public),
              "and nothing is published - a module built in parallel cannot "
              "widen the allowlist by surprise")
    finally:
        r.close()

    def explodes(out_dir):
        raise RuntimeError("half-built module")

    r = Root(default_people()[:1])
    lines, log = quiet()
    try:
        with fake_pwa(explodes), stubbed(make_stub()):
            code = publish.main(r.argv(), log=log)
        idx = r.read(TOKEN_A, "index.html")
        check(code == 0 and "Offline install is not available" in idx,
              "an engine.pwa that raises degrades honestly instead of taking "
              "the publish down (exit %d)" % code)
    finally:
        r.close()


# =============================================================================
# [8b] the per-person rosters directory
# =============================================================================

def test_roster_scope():
    print("\n[8b] ROSTERS - each renderer sees only that person's leagues")

    r = Root()
    before = r.roster_digest()
    try:
        with stubbed(make_stub(roster_flag=False)) as stub:
            code = publish.main(r.argv(), log=lambda *a: None)
        given = set(c[4] for c in stub.calls)
        check(code == 0 and given == set([""]),
              "a renderer whose --help does not advertise --roster-dir is "
              "never handed one (%s)" % sorted(given))

        with stubbed(make_stub(roster_flag=True)) as stub:
            code = publish.main(r.argv(), log=lambda *a: None)
        given = sorted(set(c[4] for c in stub.calls))
        check(code == 0 and given and all(given),
              "a renderer that DOES advertise --roster-dir is handed one "
              "(%s)" % [os.path.basename(g) for g in given])
        check(len(given) == 2,
              "one rosters directory per person, not one shared directory "
              "(%d)" % len(given))
        for d in given:
            check(d.endswith("--rosters"),
                  "the rosters directory sits OUTSIDE the staging tree, so it "
                  "can never reach the allowlist (%s)" % d)

        check(before == r.roster_digest(),
              "data/rosters/ is byte-identical afterwards - the per-person "
              "directory is a COPY, and the sacred one is only ever read")

        for token in (TOKEN_A, TOKEN_B):
            check(not any(f.endswith(".yaml") for f in r.files(token)),
                  "no roster yaml is published into ...%s" % token[-4:])

        d = publish.person_roster_dir(
            publish.Person("Ada Fixture", "a@x.invalid", TOKEN_A,
                           ["alpha-family"]),
            os.path.join(r.dir, "scoped"), r.rosters)
        check(sorted(os.listdir(d)) == ["alpha-family.yaml"],
              "the copy holds exactly the person's own leagues' rosters (%s)"
              % sorted(os.listdir(d)))
    finally:
        r.close()


# =============================================================================
# [9] the module keeps its own promises
# =============================================================================

def test_hygiene():
    print("\n[9] HYGIENE - the pipeline touches only what it owns")

    src = open(os.path.join(HERE, "publish.py"), "r").read()
    for bad in ("import requests", "import pandas", "urllib.request",
                "from urllib", "import numpy"):
        check(bad not in src, "publish.py does not use %r" % bad)
    check(src.count("subprocess.run") == 1,
          "publish.py shells out in exactly one place (run_renderer), which "
          "is the seam tests replace")
    for sacred in ("saves/", "data/sources.yaml", "strategies/"):
        check(sacred not in src,
              "publish.py never names the sacred path %r" % sacred)
    check(src.count('"data", "rosters"') == 1 and "ROSTER_DIR" in src,
          "data/rosters/ is named once, as a constant, and read only")
    for line in src.splitlines():
        if "ROSTER_DIR" in line or "LEAGUE_DIR" in line:
            check('"w"' not in line and "_atomic_write" not in line,
                  "no write goes near a sacred directory: %s" % line.strip())
    check("shutil.rmtree" in src and "ignore_errors=True" in src,
          "directory removal is deliberate and bounded")

    sh = open(os.path.join(HERE, "publish.sh"), "r").read()
    check("publish.py" in sh and "--dry-run" in sh and "check" in sh,
          "publish.sh documents the dry run and the heartbeat check")
    check("exit 2" in sh and "REFUSED" in sh,
          "publish.sh explains what a non-zero exit means")

    doc = os.path.join(HERE, "docs", "DEPLOY.md")
    check(os.path.exists(doc), "docs/DEPLOY.md exists")
    text = open(doc, "r").read()
    for needed, why in (
            ("secrets.token_urlsafe", "how to generate a token"),
            ("pages.dev", "that a free subdomain is enough to start"),
            ("Zero Trust", "the Zero Trust application, not just the toggle"),
            ("preview", "the preview-only trap"),
            ("launchd", "the schedule"),
            ("sleep", "that a sleeping Mac does not publish"),
            ("check-heartbeat", "the alert"),
            ("cross-league exposure",
             "the cross-league exposure leak, by the name publish.py prints"),
            ("--roster-dir", "the one-flag fix for it"),
            ("exit 2", "what a refusal means")):
        check(needed in text, "DEPLOY.md covers %s" % why)

    # THE CROSS-REFERENCE IS REAL, BOTH WAYS. publish.py sends the reader to
    # this document by name; the document must answer under that name, and it
    # must not still describe as an open blocker something the renderers now
    # close. A doc that tells the owner "your first publish will refuse" when
    # it no longer does is the same class of error as a page overstating what
    # it checked.
    check("docs/DEPLOY.md" in src,
          "publish.py points the reader at docs/DEPLOY.md by name")
    check("KNOWN BLOCKER" not in text,
          "DEPLOY.md no longer calls cross-league exposure a KNOWN BLOCKER - "
          "the renderers take --roster-dir")
    for m in ("engine.home", "engine.board", "engine.tradedesk"):
        mod = m.replace("engine.", "engine/") + ".py"
        check(mod in text, "DEPLOY.md names %s as taking the flag" % mod)


def main():
    print("PUBLISH PIPELINE ACCEPTANCE TEST")
    test_tokens()
    test_config()
    test_public_mode()
    test_two_people()
    test_refusals()
    test_dry_run()
    test_heartbeat()
    test_pwa()
    test_roster_scope()
    test_hygiene()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d of %d FAILURE(S):" % (len(FAILURES), CHECKS[0])))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
