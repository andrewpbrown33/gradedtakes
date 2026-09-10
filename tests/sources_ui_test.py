#!/usr/bin/env python3
"""Acceptance test: creator-source control panel (engine/sources_ui.py).

Pure checks first - the type auto-guesser (youtube.com -> youtube,
.xml/feed -> rss, an x.com/twitter.com HOST -> paste NEVER a fetchable
type while hosts merely ENDING in "x.com" like netflix.com stay urls -
host-boundary, not substring, else url), the
kebab slugger, the validate-everything-first update merger, the add-source
validator, and the guard_write write-surface fence. Then a LIVE server
spun in-process on an ephemeral 127.0.0.1 port with the registry AND the
paste-store cache dir redirected into a tempfile.mkdtemp() (try/finally
restore - the same isolation discipline mock_draft.py applies to
save_state.SAVE_DIR): GET must render every seeded source, a POSTed
weight/toggle change must land in the tempdir yaml, add-source must
append, paste must hit the redirected store, and EVERY invalid POST must
bounce with the registry file byte-identical. Production data/sources.yaml
is existence+byte-checked untouched throughout.

Then the LEAGUES tab: guard_scoped_write's allowlist (exactly
leagues/*.yaml, data/rosters/*.yaml, data/espn_secrets.json,
data/rankings-*.csv, data/cache/ - everything else PermissionError),
the ESPN-field validator, the pure renderers (three platform cards,
escaped league names, password-type secret fields with no value
attribute), and a second LIVE server whose data_root AND connections
module are both swapped for tempdir fakes: sleeper lookup/import wired
through the fake, import reporting exactly the files created, a rogue
reported path answered 403, /espn/save writing 0600 atomically with the
secret value NEVER appearing in any response or later page render, and
every malformed POST bouncing with the secrets file byte-identical.
Production espn_secrets.json / leagues/ / data/rosters/ are
byte-and-listing-checked untouched throughout.

The v3 skin (engine/ui.py) is asserted on a pure render of the Inputs
tab against fixture avatars: the shared shell, both tabs, one nameplate
with a face per creator (the-favorites, sharp-or-square), a weight slider
paired with a number box per source, the live sum, and no forbidden
colour (the old green/red hexes) anywhere. The add-source flow's
best-effort avatar fetch is swapped for a recording fake in the live
server test so no add ever reaches the network, and a fake that raises
proves an avatar failure never fails the add.

    .venv/bin/python tests/sources_ui_test.py
"""

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import sources as sources_mod                    # noqa: E402
from engine import sources_ui as ui                          # noqa: E402
from engine import assets                                    # noqa: E402

# v2's mint/coral chips and the panel's own old green/red/blue - none may
# survive anywhere in an emitted page (v3 has no green and no red).
FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171", "#0369a1")

# The smallest byte string that reads as a JPEG to the cache (ui.py never
# decodes it - it base64s whatever is on disk).
_TINY_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 12 + b"\xff\xd9"


class _FixtureAvatars(object):
    """Point engine/assets' avatar cache (what ui.py embeds) at a tempdir
    holding <id>.jpg for each id, forgetting its per-process memo on the
    way in and out - the real data/cache/avatars/ can neither help nor
    hurt."""

    def __init__(self, ids):
        self.ids = list(ids)
        self.dir = None
        self.saved = None

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="srcui-avatars-")
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


class _RecordingAvatar(object):
    """Stand-in for sources_ui._avatar_after_add: records the entries it
    was handed, answers a canned note, and raises on demand."""

    def __init__(self):
        self.calls = []
        self.boom = False

    def __call__(self, entry):
        self.calls.append(dict(entry))
        if self.boom:
            raise RuntimeError("avatar host unreachable (fixture)")
        return None, "fixture: no face fetched"

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- 1. type auto-guess ------------------------------------------------------

def test_guess_type():
    print("\n[1] guess_type - URL/handle auto-detection")
    check(ui.guess_type("https://www.youtube.com/@somechannel") == "youtube",
          "youtube.com channel URL -> youtube")
    check(ui.guess_type("https://youtu.be/abc123") == "youtube",
          "youtu.be short link -> youtube")
    check(ui.guess_type("https://example.com/blog/feed.xml") == "rss",
          ".xml -> rss")
    check(ui.guess_type("https://example.com/feed") == "rss",
          "'feed' in URL -> rss")
    check(ui.guess_type("https://example.com/rss/all.rss") == "rss",
          ".rss -> rss")
    check(ui.guess_type("https://example.com/articles/today") == "url",
          "plain page -> url")
    check(ui.guess_type("") == "url", "empty handle -> url (safe default)")
    check(ui.guess_type("https://x.com/someone") == "paste",
          "x.com -> paste (NO X scraping - ToS)")
    check(ui.guess_type("https://twitter.com/someone/status/1") == "paste",
          "twitter.com -> paste (NO X scraping - ToS)")
    check(ui.guess_type("x.com/someone") == "paste",
          "scheme-less x.com handle -> paste")
    check(ui.guess_type("https://x.com") == "paste",
          "bare x.com host, no path -> paste")
    check(ui.guess_type("https://mobile.twitter.com/someone") == "paste",
          "dot-prefixed subdomain of twitter.com -> paste")
    # host-BOUNDARY, not substring: hosts merely ENDING in x.com stay urls
    check(ui.guess_type("https://netflix.com/title/81234567") == "url",
          "netflix.com is NOT x.com - stays a fetchable url")
    check(ui.guess_type("https://www.netflix.com/browse") == "url",
          "www.netflix.com -> url (no ToS overblock)")
    check(ui.guess_type("https://stockx.com/sneakers") == "url",
          "stockx.com -> url (no ToS overblock)")
    check(ui.guess_type("https://example.com/why-x.com-matters") == "url",
          "x.com in the PATH only -> url (host is example.com)")


# --- 2. slugify --------------------------------------------------------------

def test_slugify():
    print("\n[2] slugify - kebab ids")
    check(ui.slugify("Late Round QB!") == "late-round-qb", "punctuation drops")
    check(ui.slugify("  The  FF  Hub  ") == "the-ff-hub", "spaces collapse")
    check(ui.slugify("---") == "", "no alnum -> empty (caller rejects)")


# --- 3. apply_updates - validate everything before touching anything ---------

def _seed():
    return [dict(s) for s in sources_mod.DEFAULT_SOURCES]


def test_apply_updates():
    print("\n[3] apply_updates - all-or-nothing merge")
    rows = _seed()
    merged, err = ui.apply_updates(
        rows, [{"id": "engine", "enabled": False, "weight": 10},
               {"id": "chen-tiers", "enabled": True, "weight": 55}])
    check(err is None, "valid batch accepted")
    got = {s["id"]: s for s in merged}
    check(got["engine"]["enabled"] is False and got["engine"]["weight"] == 10,
          "engine toggled off, weight 10")
    check(got["chen-tiers"]["weight"] == 55, "chen-tiers weight 55")
    check(got["espn-proj"]["weight"] == 25, "untouched row keeps its weight")
    check(rows[0]["enabled"] is True, "input rows not mutated (merge copies)")

    for bad, label in [
        ([{"id": "ghost", "enabled": True, "weight": 5}], "unknown id"),
        ([{"id": "engine", "enabled": "yes", "weight": 5}], "string enabled"),
        ([{"id": "engine", "enabled": True, "weight": 101}], "weight > 100"),
        ([{"id": "engine", "enabled": True, "weight": -1}], "weight < 0"),
        ([{"id": "engine", "enabled": True, "weight": 7.5}],
         "fractional weight"),
        ([{"id": "engine", "enabled": True, "weight": True}], "bool weight"),
        ([{"id": "engine", "enabled": True, "weight": 5},
          {"id": "engine", "enabled": False, "weight": 5}], "duplicate id"),
        ([], "empty list"),
        ("nope", "non-list"),
    ]:
        merged, err = ui.apply_updates(_seed(), bad)
        check(merged is None and err, "%s rejected (%s)" % (label, err))


# --- 4. new_source_entry -----------------------------------------------------

def test_new_source_entry():
    print("\n[4] new_source_entry - add-source validation")
    rows = _seed()
    entry, err = ui.new_source_entry(rows, "My Feed",
                                     "https://example.com/feed.xml")
    check(err is None and entry["id"] == "my-feed", "id slugged from name")
    check(entry["type"] == "rss", "type auto-guessed rss from .xml")
    check(entry["enabled"] is True
          and entry["weight"] == ui.DEFAULT_WEIGHT, "starts enabled at %d"
          % ui.DEFAULT_WEIGHT)

    _, err = ui.new_source_entry(rows, "", "https://a.com")
    check(err, "empty name rejected")
    _, err = ui.new_source_entry(rows, "X", "")
    check(err, "empty handle rejected")
    _, err = ui.new_source_entry(rows, "Sneaky", "https://a.com", "feed")
    check(err and "built-in" in err, "'feed' type refused (built-ins only)")
    _, err = ui.new_source_entry(rows, "Engine", "https://a.com")
    check(err and "exists" in err, "duplicate id refused")
    _, err = ui.new_source_entry(rows, "Harmon", "https://x.com/someone",
                                 "url")
    check(err and "paste-only" in err,
          "X handle as fetchable type refused (ToS)")
    entry, err = ui.new_source_entry(rows, "Harmon", "https://x.com/someone",
                                     "paste")
    check(err is None and entry["type"] == "paste",
          "X handle allowed as explicit paste source")
    entry, err = ui.new_source_entry(rows, "Netflix Tudum",
                                     "https://netflix.com/tudum/article")
    check(err is None and entry["type"] == "url",
          "netflix.com accepted as a url source (host-boundary, not "
          "substring - no forced paste)")
    entry, err = ui.new_source_entry(rows, "StockX Blog",
                                     "https://stockx.com/news", "url")
    check(err is None and entry["type"] == "url",
          "stockx.com accepted with explicit type url")


# --- 5. guard_write ----------------------------------------------------------

def test_guard_write():
    print("\n[5] guard_write - the write surface, fenced in code")
    tmp = tempfile.mkdtemp(prefix="srcui-guard-")
    try:
        reg = os.path.join(tmp, "sources.yaml")
        roots = [reg, os.path.join(tmp, "cache")]
        check(ui.guard_write(reg, roots) == reg, "registry path allowed")
        check(ui.guard_write(os.path.join(tmp, "cache", "src-x.json"),
                             roots), "path under cache root allowed")
        for outside in [os.path.join(tmp, "rosters", "yahoo-main.yaml"),
                        os.path.join(tmp, "sources.yaml.evil"),
                        "/etc/passwd"]:
            try:
                ui.guard_write(outside, roots)
                check(False, "outside path refused: %s" % outside)
            except PermissionError:
                check(True, "outside path refused: %s" % outside)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 6. live server on an ephemeral port, tempdir-redirected -----------------

def _get(port, path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path),
                                timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def _post(port, path, obj, raw=None):
    data = raw if raw is not None else json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path), data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_server():
    print("\n[6] live server - ephemeral port, tempdir registry")
    prod_registry = os.path.join(HERE, "data", "sources.yaml")
    prod_existed = os.path.exists(prod_registry)
    prod_bytes = _read_bytes(prod_registry) if prod_existed else None

    tmp = tempfile.mkdtemp(prefix="srcui-live-")
    reg = os.path.join(tmp, "sources.yaml")
    real_cache = sources_mod.CACHE_DIR
    sources_mod.CACHE_DIR = os.path.join(tmp, "cache")
    # hermetic: never let GET / touch a real engine.connections module,
    # and never let POST /add reach for a creator's avatar over the network
    ui.CONNECTIONS = _StatusOnlyConnections()
    real_avatar = ui._avatar_after_add
    fake_avatar = _RecordingAvatar()
    ui._avatar_after_add = fake_avatar
    srv = ui.make_server(0, reg)
    thread = threading.Thread(target=srv.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        host, port = srv.server_address[0], srv.server_address[1]
        check(host == "127.0.0.1", "bound to 127.0.0.1 only (got %s)" % host)

        # GET / renders the seeded registry ---------------------------------
        code, page = _get(port, "/")
        check(code == 200, "GET / -> 200")
        check(os.path.exists(reg),
              "missing registry seeded into the TEMPDIR on first load")
        for s in sources_mod.DEFAULT_SOURCES:
            check(("data-id=\"%s\"" % s["id"]) in page
                  and s["name"] in page,
                  "row rendered: %s" % s["id"])
        check("Model Settings" in page, "page titled Model Settings")
        check("your inputs, your weights, your formula" in page,
              "branding subtitle present")
        check("<script src" not in page and "<link" not in page,
              "self-contained: no external scripts or stylesheets")
        check('class="wr-nav"' in page and 'aria-current="page"' in page,
              "the shared v3 shell heads the live page")
        n = len(sources_mod.DEFAULT_SOURCES)
        check(page.count('type="range"') == n
              and page.count('type="number"') == n,
              "live page: one slider + one number box per source")
        check(page.count('class="wr-np ') == n,
              "live page: one nameplate per source")
        for hx in FORBIDDEN_HEX:
            check(hx.lower() not in page.lower(),
                  "live page: forbidden colour absent: %s" % hx)

        code, body = _get(port, "/state")
        st = json.loads(body)
        check([s["id"] for s in st["sources"]] ==
              [s["id"] for s in sources_mod.DEFAULT_SOURCES],
              "GET /state lists the four built-in feeds in order")

        # POST /save - weight + toggle land in the tempdir yaml -------------
        code, res = _post(port, "/save", {"sources": [
            {"id": "engine", "enabled": False, "weight": 12},
            {"id": "espn-proj", "enabled": True, "weight": 80}]})
        check(code == 200 and res["ok"], "POST /save -> ok")
        check(res["enabled_weight"] == 80 + 20 + 15,
              "saved-state confirmation reports enabled weight (%s)"
              % res.get("enabled_weight"))
        rows = {s["id"]: s for s in sources_mod.load_sources(reg)}
        check(rows["engine"]["enabled"] is False
              and rows["engine"]["weight"] == 12,
              "engine toggle+weight persisted to yaml")
        check(rows["espn-proj"]["weight"] == 80, "espn-proj weight persisted")
        check(rows["chen-tiers"]["weight"] == 15, "untouched row persisted")

        # invalid POSTs bounce with the file byte-identical ------------------
        before = _read_bytes(reg)
        for label, path, payload, raw in [
            ("unknown id", "/save",
             {"sources": [{"id": "ghost", "enabled": True, "weight": 5}]},
             None),
            ("weight 150", "/save",
             {"sources": [{"id": "engine", "enabled": True, "weight": 150}]},
             None),
            ("garbage body", "/save", None, b"{not json"),
            ("empty body", "/save", None, b""),
            ("dup add", "/add",
             {"name": "Engine", "handle": "https://a.com"}, None),
            ("feed add", "/add",
             {"name": "Sneak", "handle": "x", "type": "feed"}, None),
            ("unknown paste source", "/paste",
             {"source": "ghost", "text": "hi"}, None),
            ("empty paste", "/paste",
             {"source": "engine", "text": "   "}, None),
            ("unknown fetch id", "/fetch", {"id": "ghost"}, None),
            ("bad endpoint", "/nope", {"x": 1}, None),
        ]:
            code, res = _post(port, path, payload, raw=raw)
            check(code in (400, 404) and not res.get("ok"),
                  "invalid POST rejected: %s (%d %s)"
                  % (label, code, res.get("error", "")[:60]))
        check(_read_bytes(reg) == before,
              "registry yaml byte-identical after every invalid POST")

        # POST /add appends through the helpers ------------------------------
        code, res = _post(port, "/add", {
            "name": "My Feed", "handle": "https://example.com/feed.xml",
            "type": ""})
        check(code == 200 and res["ok"]
              and res["added"]["type"] == "rss",
              "POST /add -> ok, type auto-guessed rss")
        rows = sources_mod.load_sources(reg)
        check(any(s["id"] == "my-feed" and s["enabled"]
                  and s["weight"] == ui.DEFAULT_WEIGHT for s in rows),
              "added source persisted enabled at default weight")
        check(len(rows) == len(sources_mod.DEFAULT_SOURCES) + 1,
              "no other row lost on add")
        check([c["id"] for c in fake_avatar.calls] == ["my-feed"],
              "add-source asked for the new voice's face (best effort)")
        check(res.get("avatar") is None
              and res.get("avatar_note") == "fixture: no face fetched",
              "the add response carries the avatar outcome honestly")

        # an avatar failure never fails the add ----------------------------
        fake_avatar.boom = True
        code, res = _post(port, "/add", {
            "name": "Boom Feed", "handle": "https://example.com/boom.xml"})
        fake_avatar.boom = False
        check(code == 200 and res["ok"] and res["added"]["id"] == "boom-feed",
              "add still succeeds when the avatar fetch raises")
        check("unreachable" in (res.get("avatar_note") or ""),
              "...and says why the face is missing")
        check(any(s["id"] == "boom-feed"
                  for s in sources_mod.load_sources(reg)),
              "the registry write stood - the avatar step came after it")

        # POST /paste hits the redirected store ------------------------------
        code, res = _post(port, "/paste", {
            "source": "my-feed", "text": "Start Puka Nacua this week.",
            "url": "https://x.com/whoever/status/1"})
        check(code == 200 and res["ok"] and res["chars"] == 27,
              "POST /paste -> stored (%s chars)" % res.get("chars"))
        store = os.path.join(sources_mod.CACHE_DIR, "src-my-feed.json")
        check(os.path.exists(store), "paste landed in the TEMPDIR store")
        if os.path.exists(store):
            with open(store) as fh:
                items = json.load(fh)["items"]
            check(items[0]["text"] == "Start Puka Nacua this week."
                  and items[0]["url"].startswith("https://x.com/"),
                  "paste text + attribution url stored verbatim")

        # POST /fetch - built-in feed answers honestly, no network ----------
        code, res = _post(port, "/fetch", {"id": "engine"})
        check(code == 200 and res["ok"] and res["items"] == 0
              and "built-in" in res.get("note", ""),
              "fetch on a built-in feed: 0 items + honest note")

        # nothing leaked outside the tempdir ---------------------------------
        check(os.path.exists(prod_registry) == prod_existed,
              "production data/sources.yaml existence unchanged")
        if prod_existed:
            check(_read_bytes(prod_registry) == prod_bytes,
                  "production data/sources.yaml byte-identical")
        check(sorted(os.listdir(tmp)) == ["cache", "sources.yaml"],
              "tempdir holds exactly the registry + paste store")
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
        sources_mod.CACHE_DIR = real_cache
        ui.CONNECTIONS = None
        ui._avatar_after_add = real_avatar
        shutil.rmtree(tmp, ignore_errors=True)


# --- 6b. the Inputs tab on v3 - faces, sliders, sum, no forbidden colour ----

def _creator_rows():
    return _seed() + [
        {"id": "the-favorites", "name": "The Favorites / Action Network",
         "type": "youtube", "handle": "https://www.youtube.com/@Example",
         "enabled": True, "weight": 17, "notes": ""},
        {"id": "sharp-or-square", "name": "Sharp or Square",
         "type": "rss", "handle": "https://example.com/podcast.rss",
         "enabled": False, "weight": 17, "notes": ""},
    ]


def test_render_inputs():
    print("\n[6b] render - the Inputs tab on the v3 system")
    rows = _creator_rows()
    with _FixtureAvatars(["the-favorites", "sharp-or-square"]):
        page = ui.render_page(rows, "/tmp/reg.yaml", status=None,
                              nav_leagues=[("fx-1", "Fixture League")],
                              week=3)
    low = page.lower()
    check(page.startswith("<!doctype html>"), "full document")
    check('class="wr-nav"' in page, "the shared shell (navy header) heads the page")
    check('aria-current="page"' in page and "Model Settings" in page,
          "the shell marks Model Settings as the current page")
    check("WK 3" in page and "Fixture League" in page,
          "the shell carries the week badge and the league switcher it was given")
    check('<main class="wr-page">' in page, "the body is the wr-page frame")
    check('id="tab-model"' in page and 'id="tab-leagues"' in page
          and 'role="tablist"' in page,
          "both tabs render (Inputs / Leagues) as a tablist")
    check("<section class=\"wr-card\">" in page
          and page.index('class="wr-card"') < page.index('id="tab-model"'),
          "the tabs sit inside a wr-card")
    check('id="pane-model"' in page and 'id="pane-leagues" role="tabpanel" hidden'
          in page, "Inputs pane first and shown, Leagues pane hidden")
    check("wr-av-pic-the-favorites" in page
          and "wr-av-pic-sharp-or-square" in page,
          "nameplates wear the cached avatars for the-favorites and "
          "sharp-or-square")
    check("wr-av-creator" in page and "wr-av-feed" in page,
          "creators get the gold ring, built-in feeds the hairline ring")
    check("width:36px;height:36px" in page, "avatars are drawn at 36px")
    check(page.count('class="wr-np ') == len(rows),
          "one nameplate per source (%d)" % len(rows))
    check(page.count('type="range"') == len(rows)
          and 'min="0" max="100"' in page,
          "one 0-100 weight slider per source")
    check(page.count('type="number"') == len(rows),
          "each slider is paired with a number box")
    check(page.count('class="mp-switch"') == len(rows)
          and page.count('class="en"') == len(rows),
          "one enable switch per source, still the .en the script posts")
    check('id="tot" class="wr-num"' in page,
          "the live enabled-weight sum is a wr-num")
    check("weights normalize" in page, "a quiet note says weights normalize")
    check('class="src off"' in page,
          "a disabled source row is dimmed via .off, not coloured")
    check("wr-np-sub" in page and "example.com/podcast.rss" in page,
          "a creator's handle rides under its name")
    check('class="chip' not in page and "tabbtn" not in page,
          "no v1 chip or tab classes survive")
    check("card-sleeper" in page and "card-espn" in page
          and "card-yahoo" in page and "status unavailable" in page,
          "the Leagues tab still renders its cards (status=None -> neutral)")
    # (--good/--bad survive as ui.py's var() ALIASES onto tokens; the
    # panel's own --bg/--accent declarations are what must be gone)
    check("--wr-canvas:" in page and "--bg:" not in page
          and "--accent:" not in page,
          "the panel's old private palette is gone - wr- tokens only")
    check(re.search(r"#[0-9a-fA-F]{3,8}\b", ui._PANEL_CSS) is None,
          "the panel layer itself names no hex colour")
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low, "forbidden colour absent: %s" % hx)
    check("<link" not in low and "<script src" not in low,
          "self-contained: no external stylesheet or fetched script")
    check("prefers-color-scheme" in page and '[data-theme="dark"]' in page,
          "light and dark via tokens, explicit dark honoured")


# --- 7. guard_scoped_write + espn validator + normalizers --------------------

def test_league_guards():
    print("\n[7] guard_scoped_write - the leagues allowlist, fenced in code")
    tmp = tempfile.mkdtemp(prefix="srcui-scope-")
    try:
        for rel in ["leagues/sleeper-123.yaml", "data/rosters/espn-1.yaml",
                    "data/espn_secrets.json", "data/rankings-espn.csv",
                    "data/cache/sleeper-players.json",
                    "data/cache/sub/deep.json"]:
            p = os.path.join(tmp, *rel.split("/"))
            check(ui.guard_scoped_write(p, tmp) == p, "allowed: %s" % rel)
        for rel in ["data/rankings.csv",          # shared default: NOT ours
                    "data/rankings-.csv",         # empty stem
                    "leagues/deep/x.yaml",        # no subdirs
                    "leagues/.yaml",              # empty stem
                    "leagues/x.yml",              # wrong extension
                    "data/rosters/x.json",        # wrong extension
                    "data/rosters/a/b.yaml",      # no subdirs
                    "data/espn_secrets.json.evil",
                    "data/yahoo_secrets.json",    # guidance-only card
                    "data/sources.yaml",          # sources tab's surface
                    "warroom.py",
                    "leagues/../warroom.py"]:     # traversal
            p = os.path.join(tmp, *rel.split("/"))
            try:
                ui.guard_scoped_write(p, tmp)
                check(False, "refused: %s" % rel)
            except PermissionError:
                check(True, "refused: %s" % rel)
        try:
            ui.guard_scoped_write("/etc/passwd", tmp)
            check(False, "refused: /etc/passwd")
        except PermissionError:
            check(True, "refused: /etc/passwd")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n[7b] validate_espn_secrets + normalizers")
    s, err = ui.validate_espn_secrets(
        {"league_id": " 123456 ", "espn_s2": "A" * 40, "swid": "ABC-DEF"})
    check(err is None and s["league_id"] == 123456,
          "league_id trimmed + int-ed")
    check(s["swid"] == "{ABC-DEF}", "missing SWID braces added")
    s, _ = ui.validate_espn_secrets(
        {"league_id": "9", "espn_s2": "A" * 40, "swid": "{X-1}"})
    check(s["swid"] == "{X-1}", "already-braced SWID untouched")
    for body, label in [
        ({"league_id": "abc", "espn_s2": "A" * 40, "swid": "{X}"},
         "non-numeric league_id"),
        ({"league_id": "", "espn_s2": "A" * 40, "swid": "{X}"},
         "empty league_id"),
        ({"league_id": "1", "espn_s2": "short", "swid": "{X}"},
         "too-short espn_s2"),
        ({"league_id": "1", "espn_s2": "", "swid": "{X}"}, "empty espn_s2"),
        ({"league_id": "1", "espn_s2": "A" * 40, "swid": ""}, "empty swid"),
        ({"league_id": "1", "espn_s2": "A" * 40, "swid": "{}"},
         "braces-only swid"),
    ]:
        s, err = ui.validate_espn_secrets(body)
        check(s is None and err, "%s rejected (%s)" % (label, err))

    lgs = ui.normalize_leagues({"leagues": [
        {"league_id": "1", "name": "A", "teams": 12, "season": "2026"},
        {"id": "2", "name": "B", "total_rosters": 10}, "junk"]})
    check(len(lgs) == 2 and lgs[1]["league_id"] == "2"
          and lgs[1]["teams"] == 10,
          "normalize_leagues: id/total_rosters aliases, junk dropped")
    made = ui.normalize_created({"created": {"league_yaml": "a.yaml",
                                             "roster_file": ""}})
    check(made == [{"label": "league_yaml", "path": "a.yaml"}],
          "normalize_created: dict shape, empty paths dropped")
    check(ui.normalize_created({"created": ["p1", "p2"]})[1]["path"] == "p2",
          "normalize_created: list shape")
    check(ui.normalize_created("junk") == [], "normalize_created: junk -> []")


# --- 8. leagues section renders - three cards, no secrets, escaped names -----

def _fake_status():
    # sleeper: real shape (leagues list); espn: detail-only connected;
    # yahoo: connections.py's stage token + a draft-shape next_step -
    # together the cards must digest every documented alias.
    return {
        "sleeper": {"connected": True,
                    "leagues": ["Longo <Memorial> League (Sleeper)"],
                    "detail": "1 league imported"},
        "espn": {"connected": True,
                 "detail": "cookies on file for league 1234567"},
        "yahoo": {"connected": False, "stage": "registered",
                  "next_step": "finish the OAuth handshake in a terminal"},
    }


def _norm_status():
    """_fake_status() exactly as GET / receives it - normalized by
    connection_status() through a temporarily plugged fake module."""
    ui.CONNECTIONS = _StatusOnlyConnections()
    try:
        return ui.connection_status()
    finally:
        ui.CONNECTIONS = None


def test_render_leagues():
    print("\n[8] render - leagues tab, three platform cards")
    page = ui.render_page(_seed(), "/tmp/reg.yaml", status=_norm_status())
    for cid in ("card-sleeper", "card-espn", "card-yahoo"):
        check(("id=\"%s\"" % cid) in page, "card present: %s" % cid)
    check("id=\"tab-leagues\"" in page and "id=\"tab-model\"" in page,
          "two-tab bar rendered (single-file panel kept)")
    check("id=\"pane-leagues\"" in page and "id=\"pane-model\"" in page,
          "both panes in the one page")
    check("Longo &lt;Memorial&gt; League (Sleeper)" in page,
          "connected league name listed, HTML-escaped")
    check("cookies on file for league 1234567" in page,
          "connected-without-league-list card shows the detail line")
    check("next step: finish the OAuth handshake in a terminal" in page,
          "not-connected card shows the ONE next step")
    check("Find my leagues" in page, "sleeper lookup button")
    check("DevTools" in page and "Application" in page and "Cookies" in page
          and "espn.com" in page, "30-second ESPN cookie instructions inline")
    check(page.count("type=\"password\"") == 2,
          "both ESPN secret fields are password inputs")
    for fid in ("espn-s2", "espn-swid"):
        i = page.index("id=\"%s\"" % fid)
        tag = page[page.rindex("<input", 0, i):page.index(">", i)]
        check("value=" not in tag,
              "secret field never carries a value attribute: %s" % fid)
    check("./yahoo.sh check" in page and "terminal" in page,
          "yahoo handshake honestly requires a terminal run")
    check("you are here" in page, "yahoo current stage highlighted")
    check(page.count("&#10003;") == 2,
          "the two stages before 'registered'->handshake marked done")
    check("developer.yahoo.com" in page and "yahoo_secrets.json" in page,
          "yahoo staged guidance rendered")
    check("<script src" not in page and "<link" not in page,
          "still self-contained (no external assets)")

    page = ui.render_page(_seed(), "/tmp/reg.yaml", status=None)
    check("status unavailable" in page and "card-yahoo" in page,
          "status=None degrades to neutral cards, page still renders")


# --- 9. live leagues server - fake connections + tempdir data_root -----------

class _StatusOnlyConnections(object):
    """Minimal fake so GET / never imports a real engine.connections."""

    def status(self):
        return _fake_status()


class _FakeConnections(object):
    """engine/connections.py's real contract (resolve_user +
    list_leagues + import_league(league_id, user_id) returning a
    summary with top-level paths), tempdir-backed."""

    def __init__(self, root):
        self.root = root
        self.rogue = False

    def status(self):
        return _fake_status()

    def resolve_user(self, username):
        if username == "ghost":
            raise LookupError("Sleeper has no user named 'ghost' - the "
                              "username is the @handle in the app")
        return {"user_id": "u777", "username": username,
                "display_name": username.title()}

    def list_leagues(self, user_id):
        assert user_id == "u777", "panel must pass the resolved user_id"
        return [
            {"league_id": "9990001", "name": "Dynasty Bros", "teams": 12,
             "season": "2026"},
            {"id": "9990002", "name": "Work League", "total_rosters": 10},
        ]

    def import_league(self, league_id, user_id):
        assert user_id == "u777", "panel must import with the user_id"
        if self.rogue:
            evil = os.path.join(self.root, "warroom.py")
            with open(evil, "w") as fh:
                fh.write("# rogue write the panel must refuse to bless\n")
            return {"name": "Evil", "config_id": "evil",
                    "league_file": evil}
        lid = "sleeper-%s" % league_id
        summary = {
            "league_file": os.path.join(self.root, "leagues",
                                        lid + ".yaml"),
            "roster_file": os.path.join(self.root, "data", "rosters",
                                        lid + ".yaml"),
            "rankings_csv": os.path.join(self.root, "data",
                                         "rankings-" + lid + ".csv"),
        }
        for p in summary.values():
            if not os.path.isdir(os.path.dirname(p)):
                os.makedirs(os.path.dirname(p))
            with open(p, "w") as fh:
                fh.write("stub\n")
        summary.update({"config_id": lid, "name": "Dynasty Bros (Sleeper)",
                        "teams": 12, "my_roster_size": 15,
                        "unresolved_player_ids": [], "rebuild": None})
        return summary


def test_leagues_server():
    print("\n[9] live leagues server - fake connections, tempdir data_root")
    prod_secrets = os.path.join(HERE, "data", "espn_secrets.json")
    prod_sec_existed = os.path.exists(prod_secrets)
    prod_sec_bytes = _read_bytes(prod_secrets) if prod_sec_existed else None
    prod_leagues = sorted(os.listdir(os.path.join(HERE, "leagues")))
    prod_rosters = sorted(os.listdir(os.path.join(HERE, "data", "rosters")))

    tmp = tempfile.mkdtemp(prefix="srcui-leagues-")
    reg = os.path.join(tmp, "sources.yaml")
    real_cache = sources_mod.CACHE_DIR
    sources_mod.CACHE_DIR = os.path.join(tmp, "data", "cache")
    fake = _FakeConnections(tmp)
    ui.CONNECTIONS = fake
    real_check = ui.espn_live_check
    srv = ui.make_server(0, reg, data_root=tmp)
    thread = threading.Thread(target=srv.serve_forever)
    thread.daemon = True
    thread.start()
    secret = "S2SECRETXYZZY" + "A" * 40   # never in any response or page
    try:
        port = srv.server_address[1]

        # status cards render from the fake's status() --------------------
        code, page = _get(port, "/")
        check(code == 200 and "card-sleeper" in page
              and "card-espn" in page and "card-yahoo" in page,
              "GET / renders all three platform cards")

        # the shell's nav targets: sibling pages served READ-ONLY --------
        with open(os.path.join(tmp, "home.html"), "w") as fh:
            fh.write("<!doctype html><title>fixture home</title>")
        code, body = _get(port, "/home.html")
        check(code == 200 and "fixture home" in body,
              "GET /home.html serves the generated page from the data root")
        for bad in ("/warroom.py", "/leagues/x.yaml", "/home.html?x=1",
                    "/board-espn-1-week1.html.tmp", "/data/sources.yaml"):
            try:
                code, _ = _get(port, bad)
            except urllib.error.HTTPError as e:
                code = e.code
            check(code == 404, "GET %s -> 404 (only bare page names)" % bad)
        try:
            _get(port, "/digest-espn-1-week9.html")
            check(False, "an ungenerated page -> 404 naming the command")
        except urllib.error.HTTPError as e:
            check(e.code == 404
                  and "not generated yet" in e.read().decode("utf-8"),
                  "an ungenerated page -> 404 naming the command")
        check("Longo &lt;Memorial&gt; League" in page,
              "espn card lists its league (escaped)")

        # sleeper lookup --------------------------------------------------
        code, res = _post(port, "/sleeper/lookup", {"username": "andrew"})
        check(code == 200 and res["ok"] and len(res["leagues"]) == 2,
              "lookup -> that user's leagues")
        check(res["user_id"] == "u777",
              "lookup response carries the resolved user_id for import")
        check(res["leagues"][0]["league_id"] == "9990001"
              and res["leagues"][1]["teams"] == 10,
              "league rows normalized (id + total_rosters aliases)")
        code, res = _post(port, "/sleeper/lookup", {"username": "ghost"})
        check(code == 400 and not res["ok"] and "ghost" in res["error"],
              "unknown username -> inline 400 with the honest message")

        # sleeper import - reports exactly what was created ---------------
        code, res = _post(port, "/sleeper/import",
                          {"user_id": "u777", "league_id": "9990001"})
        check(code == 200 and res["ok"]
              and res["league"] == "Dynasty Bros (Sleeper)",
              "import -> ok with the league name")
        got = sorted(c["path"] for c in res["created"])
        check(got == ["data/rankings-sleeper-9990001.csv",
                      "data/rosters/sleeper-9990001.yaml",
                      "leagues/sleeper-9990001.yaml"],
              "created files reported exactly, root-relative (%s)" % got)
        for rel in got:
            check(os.path.exists(os.path.join(tmp, *rel.split("/"))),
                  "created file exists: %s" % rel)

        # a rogue reported path is refused at this seat -------------------
        fake.rogue = True
        code, res = _post(port, "/sleeper/import",
                          {"user_id": "u777", "league_id": "666"})
        fake.rogue = False
        check(code == 403 and not res["ok"] and "refused" in res["error"],
              "import reporting a path outside the allowlist -> 403")

        # espn save - 0600, atomic, live-checked, never echoed ------------
        ui.espn_live_check = lambda: "The Testers League"
        code, res = _post(port, "/espn/save", {
            "league_id": "123456", "espn_s2": secret, "swid": "ABC-DEF"})
        check(code == 200 and res["ok"] and res["connected"]
              and res["league"] == "The Testers League",
              "espn save -> saved, connected as <league name>")
        check(secret not in json.dumps(res),
              "espn_s2 value NOT echoed in the save response")
        dest = os.path.join(tmp, "data", "espn_secrets.json")
        check(os.path.exists(dest), "espn_secrets.json written")
        mode = os.stat(dest).st_mode & 0o777
        check(mode == 0o600, "secrets file mode 0600 (got %o)" % mode)
        check(not os.path.exists(dest + ".tmp"),
              "atomic sibling cleaned up")
        with open(dest) as fh:
            saved = json.load(fh)
        check(saved == {"league_id": 123456, "espn_s2": secret,
                        "swid": "{ABC-DEF}"},
              "file holds int league_id + braced SWID")
        code, page = _get(port, "/")
        check(secret not in page and "ABC-DEF" not in page,
              "page NEVER contains the saved secret values")
        check("value=\"123456\"" not in page,
              "league_id not prefilled back either")

        # espn save with a failing live check: saved, error shown ---------
        ui.espn_live_check = _raise_espn
        code, res = _post(port, "/espn/save", {
            "league_id": "654321", "espn_s2": secret, "swid": "{Z-9}"})
        check(code == 200 and res["ok"] and res["saved"]
              and not res["connected"] and "cookies rejected" in res["error"],
              "failed live check -> saved:true, connected:false, the error")
        with open(dest) as fh:
            check(json.load(fh)["league_id"] == 654321,
                  "file still updated on a failed live check")

        # malformed POSTs bounce with the secrets file byte-identical -----
        before = _read_bytes(dest)
        before_tree = sorted(os.listdir(os.path.join(tmp, "leagues")))
        for label, path, payload, raw in [
            ("empty username", "/sleeper/lookup", {"username": "  "}, None),
            ("spaced username", "/sleeper/lookup", {"username": "a b"},
             None),
            ("missing league_id", "/sleeper/import", {"user_id": "u777"},
             None),
            ("missing user_id", "/sleeper/import",
             {"league_id": "9990001"}, None),
            ("traversal league_id", "/sleeper/import",
             {"user_id": "u777", "league_id": "../evil"}, None),
            ("non-numeric espn league_id", "/espn/save",
             {"league_id": "abc", "espn_s2": "A" * 40, "swid": "{X}"},
             None),
            ("short espn_s2", "/espn/save",
             {"league_id": "1", "espn_s2": "tiny", "swid": "{X}"}, None),
            ("missing swid", "/espn/save",
             {"league_id": "1", "espn_s2": "A" * 40}, None),
            ("garbage espn body", "/espn/save", None, b"{not json"),
            ("empty espn body", "/espn/save", None, b""),
        ]:
            code, res = _post(port, path, payload, raw=raw)
            check(code == 400 and not res.get("ok"),
                  "invalid POST rejected: %s (%d %s)"
                  % (label, code, res.get("error", "")[:50]))
        check(_read_bytes(dest) == before,
              "espn_secrets.json byte-identical after every invalid POST")
        check(sorted(os.listdir(os.path.join(tmp, "leagues")))
              == before_tree, "leagues/ unchanged by invalid POSTs")

        # nothing leaked outside the tempdir ------------------------------
        check(os.path.exists(prod_secrets) == prod_sec_existed,
              "production espn_secrets.json existence unchanged")
        if prod_sec_existed:
            check(_read_bytes(prod_secrets) == prod_sec_bytes,
                  "production espn_secrets.json byte-identical")
        check(sorted(os.listdir(os.path.join(HERE, "leagues")))
              == prod_leagues, "production leagues/ listing unchanged")
        check(sorted(os.listdir(os.path.join(HERE, "data", "rosters")))
              == prod_rosters, "production data/rosters/ unchanged")
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
        sources_mod.CACHE_DIR = real_cache
        ui.CONNECTIONS = None
        ui.espn_live_check = real_check
        shutil.rmtree(tmp, ignore_errors=True)


def _raise_espn():
    raise RuntimeError("ESPN cookies rejected (private league / 401)")


# --- 10. integration: the real engine.connections, if it has landed ----------

def test_connections_integration():
    print("\n[10] engine.connections integration (skips until it lands)")
    try:
        from engine import connections as conn_mod  # noqa: PLC0415
    except ImportError:
        print("  SKIP  engine/connections.py not on disk yet - the panel "
              "degrades to neutral cards (covered in [8])")
        return
    st = ui.connection_status()   # normalizes the REAL status(), never raises
    check(sorted(st) == ["espn", "sleeper", "yahoo"],
          "real status() normalizes to the three platform cards")
    for p, e in st.items():
        check(isinstance(e["connected"], bool)
              and isinstance(e["leagues"], list)
              and isinstance(e["next_step"], str),
              "normalized %s entry carries connected/leagues/next_step" % p)
    check(callable(getattr(conn_mod, "import_league", None)),
          "connections.import_league is callable (documented contract)")
    lookup_ok = (callable(getattr(conn_mod, "sleeper_lookup", None))
                 or (callable(getattr(conn_mod, "resolve_user", None))
                     and callable(getattr(conn_mod, "list_leagues", None))))
    check(lookup_ok, "a sleeper lookup path exists (sleeper_lookup, or "
                     "resolve_user + list_leagues)")


# --- main --------------------------------------------------------------------

def main():
    print("=" * 74)
    print("SOURCES CONTROL PANEL TEST (engine/sources_ui.py)")
    print("=" * 74)
    test_guess_type()
    test_slugify()
    test_apply_updates()
    test_new_source_entry()
    test_guard_write()
    test_server()
    test_render_inputs()
    test_league_guards()
    test_render_leagues()
    test_leagues_server()
    test_connections_integration()

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
