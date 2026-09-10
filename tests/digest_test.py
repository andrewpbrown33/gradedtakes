#!/usr/bin/env python3
"""Acceptance test: Tuesday digest (engine/digest.py).

FIXTURE RULE - read before editing this file:

    Acceptance tests assert INVARIANTS AND BEHAVIOR against controlled
    fixtures. They must NEVER depend on the contents of the user's live
    roster (data/rosters/), source registry (data/sources.yaml), or league
    (leagues/) files. Those files change every time the product is actually
    used - a name is added to a roster, a source is enabled - and a suite
    that asserts today's contents fails for the wrong reason: it reports a
    regression when nothing regressed. The render below runs against a
    whole throwaway project root (leagues/, data/rankings.csv,
    data/rosters/, data/sources.yaml, data/creator_calls/) built in a
    tempdir, reached through build_digest(roster_dir=...) plus the
    module-constant redirects that tests/mock_draft.py::test_persistence
    uses for save_state.SAVE_DIR.

Pure checks first - current-week derivation from injected schedule rows,
the honest-degradation guard, the roster-coverage banner, and the injury
section's positive-only wording. Then TWO full renders from fixture
rosters: a PARTIAL one (3 of 16) that must carry the PARTIAL ROSTER
banner, and a COMPLETE one (16 of 16) that must NOT - so neither state
can regress into the other. Both must build without crashing, carry all
five section cards, and be self-contained HTML on the v3 design system
(engine/ui.py): the shared shell present, at most ONE inline script (the
theme toggle - never a src=), no <link>, no src=, and no http(s) URL other
than the inert SVG namespace, the local Model Settings link and - should
the design system ever import rather than embed its fonts - a web-font
@import. No forbidden colour (the old green/red chip and
alert hexes) may appear anywhere in the page. A pure render of the YOUR
MODEL section against fixture avatars proves the source columns are faces
(compact nameplates) and the votes are the system's verdict chips.
Files are written only inside tempfile.mkdtemp() dirs (try/finally
cleanup) and any pre-existing production digest at the real project root
is byte-checked untouched; the %owned baseline snapshot the waivers
section ADVANCES is redirected into the fixture root too, so running this
suite never moves the live one (waivers.OWNED_SNAP).

    .venv/bin/python tests/digest_test.py
"""

import io
import contextlib
import os
import re
import shutil
import sys
import tempfile
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import assets, digest, ui, weekly                # noqa: E402
from engine.exposure import LeagueRoster                     # noqa: E402
from engine.models import Player                             # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- 1. current week from injected schedule rows ----------------------------

def _row(week, gameday, season=None, game_type="REG"):
    return {"season": str(season if season is not None else weekly.SEASON),
            "game_type": game_type, "week": str(week), "gameday": gameday}


def test_current_week():
    print("\n[1] current_week - pure schedule-row derivation")
    rows = [
        _row(1, "2026-09-04"), _row(1, "2026-09-08"),      # wk1 ends Mon 9/8
        _row(2, "2026-09-13"), _row(2, "2026-09-15"),      # wk2 ends 9/15
        _row(3, "2026-09-20"),
        _row(1, "2026-12-25", season=2025),                # wrong season
        _row(19, "2027-01-10", game_type="POST"),          # playoffs ignored
        {"season": str(weekly.SEASON), "game_type": "REG",
         "week": "junk", "gameday": "not-a-date"},         # malformed row
    ]
    check(digest.current_week(rows, today=date(2026, 9, 1)) == 1,
          "before kickoff -> week 1")
    check(digest.current_week(rows, today=date(2026, 9, 8)) == 1,
          "week 1 Monday night still counts as week 1")
    check(digest.current_week(rows, today=date(2026, 9, 9)) == 2,
          "Tuesday after week 1 -> week 2 (digest day semantics)")
    check(digest.current_week(rows, today=date(2026, 9, 21)) is None,
          "past the last filed week -> None (never guesses)")
    check(digest.current_week([], today=date(2026, 9, 1)) is None,
          "no usable rows -> None, caller must ask for --week")


# --- 2. honest-degradation guard --------------------------------------------

def test_guard():
    print("\n[2] _guard - a dead section degrades visibly, never vanishes")
    ok = digest._guard("T", lambda: "<section>fine</section>")
    check(ok == "<section>fine</section>", "healthy builder passes through")

    def boom():
        raise RuntimeError("feed down: nflverse 503")
    card = digest._guard("Waiver shortlist", boom)
    check("SECTION DEGRADED" in card, "failure renders a DEGRADED card")
    check("feed down: nflverse 503" in card,
          "the exception's own message is shown")
    check("Waiver shortlist" in card, "the section keeps its title")

    def conf():
        raise SystemExit("no league yaml")
    raised = False
    try:
        digest._guard("T", conf)
    except SystemExit:
        raised = True
    check(raised, "SystemExit (config error) propagates to the CLI")


# --- 3. roster-coverage banner ----------------------------------------------

def _roster(known, size=16):
    r = LeagueRoster("fx-digest", "Fixture Roster", size)
    r.keys = set("k%d" % i for i in range(known))
    return r


def test_banner():
    print("\n[3] coverage banner - partial-roster honesty")
    b = digest.coverage_banner("fx-digest", None)
    check("NO ROSTER FILE" in b and "fx-digest" in b,
          "missing roster file -> NO ROSTER FILE banner")
    b = digest.coverage_banner("fx-digest", _roster(3))
    check("PARTIAL ROSTER" in b and "3/16" in b,
          "partial roster -> PARTIAL ROSTER banner with known/size")
    check("positive-only" in b, "banner names the positive-only semantics")
    check(digest.coverage_banner("fx-digest", _roster(16)) == "",
          "full roster -> no banner")
    check(digest.coverage_banner("fx-digest", _roster(17, size=16)) == "",
          "known >= size is complete, not a negative-coverage banner")


# --- 4. injury section (pure) -----------------------------------------------

def test_injuries():
    print("\n[4] injury flags - positive-only wording")
    ja = Player(1, "Jamarr Chase", "WR", "CIN")
    bt = Player(2, "Brian Thomas", "WR", "JAX")
    card = digest.render_injuries([ja, bt], {ja.nkey: "Questionable"}, 3, 16)
    check("QUESTIONABLE" in card and "Jamarr Chase" in card,
          "filed status is flagged with the player")
    check("no report filed" in card and "3/16" in card,
          "missing report is 'no report filed', never 'healthy'")
    card = digest.render_injuries([ja], None, 3, 16)
    check("feed unavailable" in card,
          "dead injury feed says so instead of implying health")


# --- 5. full renders from fixture rosters (partial and complete) ------------

FIVE_SECTIONS = (
    "Waiver shortlist - FAAB bands",
    "verdicts and alerts",
    "YOUR MODEL - source agreement matrix",
    "DEF / K streaming plan",
    "Trade constructs",
    "Injury flags - my roster",
)

LEAGUE_ID = "fx-digest"

# A league of our own: 10 starters + 6 bench, full PPR, FAAB waivers.
FIXTURE_LEAGUE_DATA = {
    "id": LEAGUE_ID, "name": "Fixture Digest League", "teams": 10,
    "my_slot": 1, "waiver_mode": "faab",
    "roster_spots": ["QB", "WR", "WR", "RB", "RB", "TE", "W/R/T", "W/R/T",
                     "K", "DEF"] + ["BN"] * 6,
    "rounds": 16,
    "rankings_csv": "data/rankings.csv",
    "scoring": {"reception": 1, "passing_td": 4, "rushing_td": 6,
                "receiving_td": 6, "interception": -1, "fumble_lost": -2,
                "passing_yards_per_point": 25, "rushing_yards_per_point": 10,
                "receiving_yards_per_point": 10},
}

# Registry fixture: the built-in feed voices only. The digest never sees the
# user's data/sources.yaml, so enabling a creator there cannot move this test.
FIXTURE_REGISTRY = """sources:
- id: engine
  name: War Room Engine
  type: feed
  handle: engine
  enabled: true
  weight: 40
- id: espn-proj
  name: ESPN Projections
  type: feed
  handle: espn-proj
  enabled: true
  weight: 20
- id: sleeper-proj
  name: Sleeper Projections
  type: feed
  handle: sleeper-proj
  enabled: true
  weight: 15
- id: chen-tiers
  name: Boris Chen Tiers
  type: feed
  handle: chen-tiers
  enabled: true
  weight: 10
"""


def _write_roster(dirpath, league_id, display, size, names):
    path = os.path.join(dirpath, "%s.yaml" % league_id)
    with open(path, "w") as fh:
        fh.write("league: %s\n" % league_id)
        fh.write("name: \"%s\"\n" % display)
        fh.write("size: %d\n" % size)
        fh.write("players:\n")
        for n in names:
            fh.write("  - %s\n" % n)
    return path


def _roster_names():
    """16 real pool names covering every starting slot, plus a 3-name subset.

    WHICH players these are is never asserted - only the counts. Real names
    are used so the weekly feeds and the fuzzy matcher can resolve them;
    they come from the shipped rankings pool, not from any roster file.
    """
    from engine.models import load_players
    csv_path = os.path.join(HERE, "data", "rankings.csv")
    if not os.path.exists(csv_path):
        return None, None
    by = {}
    for p in load_players(csv_path):
        by.setdefault(p.pos, []).append(p.name)
    need = [("QB", 2), ("RB", 5), ("WR", 5), ("TE", 2), ("K", 1), ("DEF", 1)]
    if any(len(by.get(pos, [])) < n for pos, n in need):
        return None, None
    full = []
    for pos, n in need:
        full.extend(by[pos][:n])
    return full, [by["QB"][0], by["RB"][0], by["WR"][0]]


def _fixture_root(full_names, partial_names):
    """A throwaway project root the digest can be pointed at wholesale."""
    import yaml
    root = tempfile.mkdtemp(prefix="digest-root-")
    os.makedirs(os.path.join(root, "leagues"))
    os.makedirs(os.path.join(root, "data", "rosters"))
    os.makedirs(os.path.join(root, "data", "rosters-full"))
    os.makedirs(os.path.join(root, "data", "creator_calls"))
    os.makedirs(os.path.join(root, "data", "cache"))
    shutil.copy(os.path.join(HERE, "data", "rankings.csv"),
                os.path.join(root, "data", "rankings.csv"))
    with open(os.path.join(root, "leagues", "%s.yaml" % LEAGUE_ID), "w") as fh:
        yaml.safe_dump(FIXTURE_LEAGUE_DATA, fh, default_flow_style=False,
                       sort_keys=False)
    with open(os.path.join(root, "data", "sources.yaml"), "w") as fh:
        fh.write(FIXTURE_REGISTRY)
    with open(os.path.join(root, "data", "creator_calls", "week-1.yaml"),
              "w") as fh:
        fh.write("week: 1\ncalls: []\n")
    _write_roster(os.path.join(root, "data", "rosters"), LEAGUE_ID,
                  "Fixture Roster", 16, partial_names)
    _write_roster(os.path.join(root, "data", "rosters-full"), LEAGUE_ID,
                  "Fixture Roster", 16, full_names)
    return root


class _Redirect(object):
    """Point every module that resolves project paths at the fixture root.

    build_digest takes roster_dir explicitly, but the league yaml, the
    rankings CSV, the source registry, the creator-call dir and the ledger
    are all resolved off module constants - and digest.main() takes no
    roster_dir at all. Redirecting them here (restored in __exit__) is the
    same discipline mock_draft applies to save_state.SAVE_DIR.
    """

    ATTRS = ("digest.HERE", "consensus.HERE", "consensus.LEDGER_PATH",
             "sources.SOURCES_PATH", "calls.CALLS_DIR", "lineup.ROSTER_DIR",
             "waivers.ROSTER_DIR", "streaming.ROSTER_DIR",
             # The digest is the run that ADVANCES the %owned momentum
             # baseline (waivers.owned_momentum(advance=True)). Left at its
             # default this suite would roll the user's live snapshot
             # forward on every run - board_test points the same constant
             # into its tempdir for the read path; the write path needs it
             # even more.
             "waivers.OWNED_SNAP")

    def __init__(self, root, roster_dir):
        from engine import (calls, consensus, lineup, sources, streaming,
                            waivers)
        self.mods = {"digest": digest, "consensus": consensus,
                     "sources": sources, "calls": calls, "lineup": lineup,
                     "waivers": waivers, "streaming": streaming}
        self.values = {
            "digest.HERE": root,
            "consensus.HERE": root,
            "consensus.LEDGER_PATH": os.path.join(root, "data",
                                                  "source_ledger.jsonl"),
            "sources.SOURCES_PATH": os.path.join(root, "data", "sources.yaml"),
            "calls.CALLS_DIR": os.path.join(root, "data", "creator_calls"),
            "lineup.ROSTER_DIR": roster_dir,
            "waivers.ROSTER_DIR": roster_dir,
            "streaming.ROSTER_DIR": roster_dir,
            "waivers.OWNED_SNAP": os.path.join(root, "data", "cache",
                                               "espn-owned-snapshot.json"),
        }
        self.saved = {}

    def __enter__(self):
        for dotted in self.ATTRS:
            mod, attr = dotted.split(".")
            self.saved[dotted] = getattr(self.mods[mod], attr)
            setattr(self.mods[mod], attr, self.values[dotted])
        return self

    def __exit__(self, *exc):
        for dotted, old in self.saved.items():
            mod, attr = dotted.split(".")
            setattr(self.mods[mod], attr, old)
        return False


# The URL-shaped strings a v3 page may legitimately carry: the xmlns
# declaration on every inline <svg> (a string constant no user agent
# resolves), the shell's link to the local Model Settings panel, and a
# web-font @import should the system ever import rather than embed its
# fonts (today engine/assets embeds them). Everything else stays banned.
_SVG_NS = "http://www.w3.org/2000/svg"
_ALLOWED_URLS = (_SVG_NS, "https://fonts.googleapis.com/",
                 "http://127.0.0.1:8787/")

# v2's mint/coral chips and the digest's own old green/red - none of them
# may survive anywhere in an emitted page (v3 has no green and no red).
FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171", "#0369a1")


def _assert_self_contained(html, label):
    check(html.startswith("<!doctype html>"), "%s: page is a full document"
          % label)
    for title in FIVE_SECTIONS:
        check(title in html, "%s: section present: %s" % (label, title))
    low = html.lower()
    # Derived, the way every other page suite derives it, rather than a
    # hardcoded 1: the shell's theme toggle plus whatever the design system
    # itself ships in <head> (engine/pwa.py's service-worker registration
    # arrives that way). A digest that grows a script of its own still
    # fails.
    _sys_scripts = (ui.shell("digest", "espn-1", 1).lower().count("<script")
                    + ui.head_tags().lower().count("<script")
                    # ...and the pre-paint preferences script. Every other
                    # page gets it inside ui.style_tag(); the digest builds
                    # its own <style> and so calls ui.prefs_boot() by name.
                    # Without it the ledger was the one page that ignored a
                    # stored theme and flashed white before correcting.
                    + ui.prefs_boot().lower().count("<script"))
    check(low.count("<script") <= _sys_scripts,
          "%s: no script beyond the design system's own (got %d, system %d)"
          % (label, low.count("<script"), _sys_scripts))
    check("<script src" not in low,
          "%s: the script is inline, never fetched" % label)
    # ORDER IS THE POINT: the preferences script must run BEFORE the page
    # paints, or a reader in Night or Broadcast sees a white flash first.
    _head_end = low.find("</head>")
    _first = low.find("<script")
    check(_head_end > 0 and 0 <= _first < _head_end,
          "%s: the pre-paint preferences script is inside <head> (script at "
          "%d, </head> at %d)" % (label, _first, _head_end))
    # engine/pwa.py adds two link relations through ui.head_tags() so the
    # page installs on a phone; neither is fetched to paint it. A
    # stylesheet, a favicon or a preload still fails - see board_test.
    _links = re.findall(r"<link\b[^>]*>", low)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in _links),
          "%s: the only <link>s are the app manifest and the touch icon, "
          "neither fetched at open (%s)" % (label, _links or "none"))
    check(" src=" not in low,
          "%s: no embedded resources (faces are data URIs in CSS)" % label)
    scrubbed = html
    for u in _ALLOWED_URLS:
        scrubbed = scrubbed.replace(u, "")
    check(not re.search(r"https?://", scrubbed),
          "%s: no external URL beyond the SVG namespace, the web-font "
          "import and the local Model Settings link" % label)
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low,
              "%s: forbidden colour absent: %s" % (label, hx))
    check('class="wr-nav"' in html,
          "%s: the shared shell (navy header) is present" % label)
    check('aria-current="page"' in html and "Ledger" in html,
          "%s: the shell marks the Ledger as the current page" % label)
    check('<main class="wr-page">' in html,
          "%s: the body is the system's wr-page frame" % label)
    # (--good/--bad survive as ui.py's var() ALIASES onto tokens; the
    # digest's own --bg/--accent declarations are what must be gone)
    check("--wr-canvas:" in html and "--bg:" not in html
          and "--accent:" not in html,
          "%s: the digest's old private palette is gone - wr- tokens only"
          % label)
    check(re.search(r"#[0-9a-fA-F]{3,8}\b", digest._DIGEST_CSS) is None,
          "%s: the digest layer itself names no hex colour" % label)
    check('[data-theme="dark"]' in html,
          "%s: an explicit dark theme is honoured too, not only the OS one"
          % label)
    check('class="wr-np ' in html,
          "%s: sources are nameplates, not column labels" % label)
    check('class="chip' not in html and 'class="red"' not in html,
          "%s: no v1 chip or red-alert classes survive" % label)


def test_render():
    print("\n[5] full render - PARTIAL and COMPLETE fixture rosters")
    full_names, partial_names = _roster_names()
    if not full_names:
        check(False, "data/rankings.csv missing or too thin to build a "
                     "fixture roster")
        return

    # The production digests at the REAL project root must not move: with
    # digest.HERE redirected, any write that lands there is a bug.
    root_digest = os.path.join(HERE, "digest-yahoo-main-week1.html")
    before = (open(root_digest, "rb").read()
              if os.path.exists(root_digest) else None)

    root = _fixture_root(full_names, partial_names)
    partial_dir = os.path.join(root, "data", "rosters")
    full_dir = os.path.join(root, "data", "rosters-full")
    try:
        from engine import consensus
        # --- partial: 3 of 16 --------------------------------------------
        with _Redirect(root, partial_dir):
            html = digest.build_digest(LEAGUE_ID, 1)
            _assert_self_contained(html, "partial")
            check("PARTIAL ROSTER" in html,
                  "coverage banner rides on top when the roster is 3/16")
            check("3/16" in html, "banner names the exact coverage 3/16")
            check("prefers-color-scheme" in html,
                  "dark palette via CSS tokens")
            check("data refreshed" in html and "season.sh" in html,
                  "refresh-timestamp footer with the regenerate command")
            check("./sources.sh" in html,
                  "YOUR MODEL section carries the model-settings footer")
            check("Fixture Digest League" in html,
                  "the render used the fixture league, not the user's")
            from engine import waivers as waivers_mod
            check(waivers_mod.OWNED_SNAP.startswith(root),
                  "the %owned baseline the waivers section advances is "
                  "redirected into the fixture root - the suite never "
                  "moves the live snapshot")
            check('href="digest-%s-week1.html"' % LEAGUE_ID in html,
                  "the shell's league switcher links the fixture league's "
                  "own ledger, not the user's leagues")

            # write_digest: explicit path, then the default naming contract
            # (inside the fixture root, never the real one).
            out = os.path.join(root, "digest.html")
            path = digest.write_digest(LEAGUE_ID, 1, out_path=out)
            check(path == out and os.path.exists(out),
                  "write_digest writes the requested path and returns it")
            check(not os.path.exists(out + ".tmp"),
                  "atomic write leaves no .tmp behind")
            default_path = digest.write_digest(LEAGUE_ID, 1)
            check(default_path == os.path.join(
                      root, "digest-%s-week1.html" % LEAGUE_ID)
                  and os.path.exists(default_path),
                  "default out path is digest-<league>-week<N>.html in the "
                  "project root (got %s)" % default_path)

            out2 = os.path.join(root, "cli.html")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = digest.main(["--league", LEAGUE_ID, "--week", "1",
                                  "--out", out2])
            lines = buf.getvalue().strip().splitlines()
            check(rc == 0, "CLI exits 0")
            check(lines and lines[-1] == out2,
                  "CLI prints the written path as its LAST stdout line "
                  "(season.sh contract)")
            cli_html = open(out2).read()
            check("PARTIAL ROSTER" in cli_html,
                  "CLI render (no roster_dir argument) also banners the "
                  "partial fixture roster")

            check(os.path.exists(consensus.LEDGER_PATH),
                  "YOUR MODEL recorded votes into the redirected ledger")
            recorded = consensus.read_ledger()
            check(recorded and all(e.get("league") == LEAGUE_ID
                                   for e in recorded),
                  "recorded ledger rows carry the fixture league id")

        # --- complete: 16 of 16 ------------------------------------------
        with _Redirect(root, full_dir):
            html_full = digest.build_digest(LEAGUE_ID, 1,
                                            roster_dir=full_dir)
            _assert_self_contained(html_full, "complete")
            check("PARTIAL ROSTER" not in html_full,
                  "a complete roster raises NO coverage banner")
            check("NO ROSTER FILE" not in html_full,
                  "and certainly no missing-file banner")

        # --- no roster file at all ----------------------------------------
        empty_dir = os.path.join(root, "data", "rosters-none")
        os.makedirs(empty_dir)
        with _Redirect(root, empty_dir):
            html_none = digest.build_digest(LEAGUE_ID, 1, roster_dir=empty_dir)
            check("NO ROSTER FILE" in html_none,
                  "no roster file -> the loud NO ROSTER FILE banner")
            check("PARTIAL ROSTER" not in html_none,
                  "missing is reported as missing, not as partial coverage")

        after = (open(root_digest, "rb").read()
                 if os.path.exists(root_digest) else None)
        check(after == before,
              "the real project root's digest is byte-identical (every "
              "write landed in the fixture root)")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 6. YOUR MODEL section - faces and verdict chips (pure) -----------------

# The smallest byte string that reads as a JPEG: SOI, a filler, EOI. The
# pages never decode it - ui.py base64s whatever is on disk - so the
# fixture only has to LOOK like a picture to the cache.
_TINY_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 12 + b"\xff\xd9"


class _FixtureAvatars(object):
    """Point engine/assets' avatar cache (what ui.py embeds) at a tempdir
    holding <id>.jpg for each id, forgetting its per-process memo on the
    way in AND out - the real data/cache/avatars/ can neither help nor
    hurt."""

    def __init__(self, ids):
        self.ids = list(ids)
        self.dir = None
        self.saved = None

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="digest-avatars-")
        for sid in self.ids:
            with open(os.path.join(self.dir, "%s.jpg" % sid), "wb") as fh:
                fh.write(_TINY_JPEG)
        self.saved = assets.AVATAR_DIR
        assets.AVATAR_DIR = self.dir
        assets._AVATAR_MEM.clear()
        return self

    def __exit__(self, *exc):
        assets.AVATAR_DIR = self.saved
        assets._AVATAR_MEM.clear()
        shutil.rmtree(self.dir, ignore_errors=True)
        return False


def _room_fixture():
    sources = [
        {"id": "engine", "name": "War Room Engine", "type": "feed",
         "weight": 40},
        {"id": "the-favorites", "name": "The Favorites", "type": "youtube",
         "weight": 17},
        {"id": "sharp-or-square", "name": "Sharp or Square", "type": "rss",
         "weight": 17},
    ]
    row = {"player": "Puka Nacua", "player_key": "puka|WR", "pos": "WR",
           "verdict": "START", "pct": 71, "score": 0.4,
           "agreement": "LONE-DISSENT", "dissenter": "Sharp or Square",
           "top_disagrees": True, "vs_engine": False,
           "top_note": "top-weighted War Room Engine says start - disagrees "
                       "with your model's verdict",
           "votes": [
               {"source": "engine", "verdict": "start", "weight": 40},
               {"source": "the-favorites", "verdict": "flex", "weight": 17,
                "confidence": "high", "quote": "he's a <flex> \"play\"",
                "detail": "rank WR12"},
               {"source": "sharp-or-square", "verdict": "sit", "weight": 17,
                "confidence": "low", "quote": ""},
           ]}
    return {"sources": sources, "rows": [row], "close_keys": ["puka|WR"],
            "creator_enabled": True, "calls_count": 0}


def test_room():
    print("\n[6] YOUR MODEL - sources are faces, votes are verdict chips")
    with _FixtureAvatars(["the-favorites", "sharp-or-square"]):
        html = digest.render_room(_room_fixture(), 1, {"weeks": [1]},
                                  ["fixture note"])
        style = digest._style_tag()
    check("wr-av-pic-the-favorites" in html
          and "wr-av-pic-sharp-or-square" in html,
          "creator columns wear their cached avatars")
    check('.wr-av-pic-the-favorites { background-image: url("data:image/'
          'jpeg;base64,' in style,
          "the page style embeds the face once as a data URI")
    check("wr-av-mono" in html and ">WR<" in html,
          "a feed with no picture gets its monogram (War Room Engine -> WR), "
          "never a broken image")
    check(html.count('class="wr-np wr-np-c"') == 3,
          "each source column head is a COMPACT nameplate")
    check(html.count('class="wr-np wr-np-f"') == 3,
          "the inputs line carries the full nameplates (name + weight)")
    check(">wt 40<" in html and ">wt 17<" in html,
          "nameplates carry the registry weight")
    check("wr-chip-start" in html and "wr-chip-sit" in html
          and "wr-chip-lean" in html,
          "votes are the system's chips: START fill, SIT ghost, FLEX dashed")
    check("Your model says" in html and "71%" in html,
          "the weighted verdict is phrased as the user's model, with pct")
    check("rank WR12" in html and "high" in html,
          "rank detail and confidence ride under the chip")
    check("he&#x27;s a &lt;flex&gt; &quot;play&quot;" in html
          and "<flex>" not in html,
          "the quote rides in a title attribute, escaped")
    check('class="dg-hot"' in html,
          "a row where the top voice dissents is highlighted (gold rule)")
    check("DEGRADED - no creator calls ingested" in html
          and 'class="wr-note dg-attn"' in html,
          "creator enabled + empty calls file -> the DEGRADED note, on the "
          "gold attention rule")
    check("scoreboard appears once" in html,
          "one scored week is called noise, not a track record")
    check("./sources.sh" in html, "model-settings footer present")
    check('class="chip' not in html,
          "no v1 chip classes (good/bad/warn) survive in the room")
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in (html + style).lower(),
              "forbidden colour absent from the room + style: %s" % hx)


def main():
    print("DIGEST ACCEPTANCE TEST")
    test_current_week()
    test_guard()
    test_banner()
    test_injuries()
    test_render()
    test_room()
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
