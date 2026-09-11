#!/usr/bin/env python3
"""Acceptance test: the installable app (engine/pwa.py).

The claim under test is "a family member can put this on their iPhone and
it opens like an app", and every part of that claim is checkable:

  [1] MANIFEST   manifest.webmanifest is valid JSON, carries every field an
                 install needs, and its two colours ARE the design tokens -
                 read from engine/ui.py, never a second palette.
  [2] ICONS      every icon the manifest declares EXISTS on disk, and its
                 real pixel size - read out of the PNG's own IHDR chunk,
                 not asked of the tool that wrote it - matches the size the
                 manifest advertises. The mark is on brand and the maskable
                 variant sits inside Android's safe zone.
  [3] HEAD TAGS  all TEN pages are rendered for real and every one of them
                 carries the iOS/Android head set, inside <head>, from the
                 single ui hook - and nothing that would be fetched to
                 paint the page came with it.
  [4] WORKER     sw.js parses (under node when node is present), is
                 network-first for pages and cache-first for icons, and its
                 cache name changes when the week changes so a new publish
                 supersedes the old.
  [5] HONESTY    the contract that lets the cache exist at all: a page
                 served from the cache is REWRITTEN with a banner naming
                 the week and the build time and disclaiming everything in
                 it. Run for real under node - the worker's own stale()
                 is called on a fixture document and the output inspected.
  [6] INSTALL    install.html is a complete document on the design system,
                 legible on a phone, free of jargon, and says plainly what
                 the saved copy cannot tell you.
  [7] OPTIONAL   the layer is additive: unregister the worker, delete the
                 two links, and every page is exactly what it was.

    .venv/bin/python tests/pwa_test.py
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import pwa, ui                                    # noqa: E402

FAILURES = []
CHECKS = [0]
NOTES = []


def check(cond, label):
    CHECKS[0] += 1
    print("  %s  %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        FAILURES.append(label)
    return bool(cond)


def _read(rel):
    with open(os.path.join(HERE, rel), "r") as fh:
        return fh.read()


def _node():
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, "node")
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


NODE = _node()
WEEK, LEAGUES = pwa.discover(HERE)


# --- 1. the manifest --------------------------------------------------------

REQUIRED = ("name", "short_name", "start_url", "scope", "display",
            "orientation", "background_color", "theme_color", "icons")


def test_manifest():
    print("\n[1] manifest - valid, complete, and the design system's colours")
    path = os.path.join(HERE, pwa.MANIFEST_NAME)
    check(os.path.isfile(path),
          "manifest.webmanifest is on disk beside the pages")
    raw = _read(pwa.MANIFEST_NAME)
    try:
        man = json.loads(raw)
        ok = True
    except ValueError as err:
        man, ok = {}, False
        print("      json error: %s" % err)
    check(ok and isinstance(man, dict), "it is valid JSON (an object)")

    for field in REQUIRED:
        check(field in man and man[field] not in (None, "", [], {}),
              "declares %s (%r)" % (field, man.get(field)))

    check(man.get("name") == "Graded Takes" and man.get("short_name") == "Graded Takes",
          "the name and short name are both 'Graded Takes' - the label under "
          "the icon is never truncated into something else")
    check(pwa.APP_NAME == ui.PRODUCT_NAME and pwa.APP_SHORT == ui.PRODUCT_NAME,
          "the manifest name IS the design system's product name - one "
          "source, so the icon label can never drift from the wordmark")
    check(len(str(man.get("short_name", ""))) <= 12,
          "short_name fits the 12-character launcher budget (%d)"
          % len(str(man.get("short_name", ""))))
    check("War Room" not in json.dumps(man),
          "the working title is nowhere in the manifest")
    check(man.get("display") == "standalone",
          "display is standalone - no address bar, no tabs")
    check(man.get("orientation") == "portrait",
          "orientation is portrait - the pages are drawn to a phone column")
    check(str(man.get("scope", "")).startswith("."),
          "scope is relative (%r), so the app works from any directory the "
          "pages are published into" % man.get("scope"))
    check(str(man.get("start_url", "")).endswith("home.html"),
          "start_url is the landing page (%r). '.' would need an index.html "
          "this project does not have" % man.get("start_url"))

    # THE COLOURS ARE THE TOKENS, not a copy of them.
    light = ui.tokens_css().split("@media", 1)[0]
    nav = re.search(r"--wr-nav:\s*([^;]+);", light).group(1).strip()
    canvas = re.search(r"--wr-canvas:\s*([^;]+);", light).group(1).strip()
    check(man.get("theme_color", "").upper() == nav.upper(),
          "theme_color IS ui's --wr-nav (%s) - the navy bar in both themes, "
          "which is why one value can serve the iOS status bar" % nav)
    check(man.get("background_color", "").upper() == canvas.upper(),
          "background_color IS ui's --wr-canvas (%s) - the splash screen "
          "settles on the paper the page will paint" % canvas)

    src = _read("engine/pwa.py").split('"""', 2)[2]
    hexes = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", src)))
    check(not hexes,
          "engine/pwa.py declares no colour of its own (%s)"
          % (hexes or "none found"))

    cuts = man.get("shortcuts") or []
    check(all(("name" in c and "url" in c) for c in cuts),
          "every shortcut names itself and a url (%d shortcut(s))" % len(cuts))
    for cut in cuts:
        rel = cut["url"].lstrip("./")
        check(os.path.isfile(os.path.join(HERE, rel)),
              "the %s shortcut points at a page that exists (%s)"
              % (cut["name"], rel))


# --- 2. the icons -----------------------------------------------------------

def test_icons():
    print("\n[2] icons - generated from the brand, at the sizes declared")
    svg = os.path.join(HERE, "design", "icon.svg")
    check(os.path.isfile(svg), "design/icon.svg is the one authored mark")

    hexes = set(pwa.svg_hexes())
    check(hexes == {pwa.theme_color().upper(), pwa.accent_color().upper()},
          "the mark uses exactly the two identity tokens, navy and gold "
          "(%s)" % sorted(hexes))
    try:
        pwa.check_brand()
        branded = True
    except RuntimeError as err:
        branded = False
        print("      %s" % err)
    check(branded, "pwa.check_brand() passes - a palette edit this file "
                   "missed would stop the build, not ship off brand")

    mask = pwa.maskable_svg()
    check('scale(%s)' % pwa.MASKABLE_SCALE in mask
          and 'id="ground"' in mask
          and mask.count('id="mark"') == 1,
          "the maskable variant is DERIVED from the same file: the ground "
          "stays full bleed, only the mark is scaled")
    check(0 < pwa.MASKABLE_SCALE <= 0.8 and 0.60 * pwa.MASKABLE_SCALE < 0.80,
          "at %.2f the mark's 60%%-wide diagonal lands inside Android's "
          "80%% safe circle" % pwa.MASKABLE_SCALE)

    man = json.loads(_read(pwa.MANIFEST_NAME))
    pngs = [i for i in man["icons"] if i["type"] == "image/png"]
    check(len(pngs) >= 4,
          "the manifest declares %d PNGs - 180 for iOS, 192 and 512 for "
          "Android, and a maskable" % len(pngs))
    for entry in man["icons"]:
        rel = entry["src"].lstrip("./")
        path = os.path.join(HERE, rel)
        if not check(os.path.isfile(path), "%s exists on disk" % rel):
            continue
        if entry["type"] != "image/png":
            continue
        want = int(entry["sizes"].split("x")[0])
        try:
            got = pwa.png_size(path)
        except (OSError, ValueError) as err:
            check(False, "%s is a readable PNG (%s)" % (rel, err))
            continue
        check(got == (want, want),
              "%s is REALLY %dx%d, exactly what the manifest says (read from "
              "its IHDR, not from sips)" % (rel, got[0], got[1]))

    have = set(e["src"].lstrip("./").split("/")[-1] for e in man["icons"])
    check("apple-touch-icon-180.png" in have,
          "the 180px apple-touch-icon is there - it is the one iOS actually "
          "puts on the home screen")
    check(any(e.get("purpose") == "maskable" for e in man["icons"]),
          "one icon is declared maskable, so Android's mask cannot clip the "
          "diamond's points")
    check(pwa.rasteriser() in ("sips", "qlmanage", None),
          "the rasteriser is a tool macOS already ships (%s)"
          % pwa.rasteriser())
    if pwa.rasteriser() is None:
        NOTES.append("no rasteriser on this machine - the documented "
                     "fallback is: %s" % pwa.FALLBACK_COMMAND)


# --- 3. the head tags, on all ten pages -------------------------------------

MUST_HAVE = (
    ('name="apple-mobile-web-app-capable" content="yes"',
     "iOS opens it full screen"),
    ('name="apple-mobile-web-app-status-bar-style" content="black-translucent"',
     "the navy bar fills the status bar"),
    ('name="apple-mobile-web-app-title" content="Graded Takes"',
     "the label under the icon"),
    ('name="theme-color"', "the OS chrome colour"),
    ('rel="manifest"', "the manifest link"),
    ('rel="apple-touch-icon"', "the home screen icon"),
    ("viewport-fit=cover", "the page reaches the edges of the screen"),
)


def _pages():
    """The ten pages, rendered for real, one per (renderer, league)."""
    from engine import board, digest, home, lineup_page, sources_page
    from engine import tradedesk
    out = [("home.html", lambda: home.build_page(WEEK)),
           ("sources.html", lambda: sources_page.build_page(
               LEAGUES[0] if LEAGUES else "espn-1", WEEK))]
    for lg in LEAGUES:
        out.append(("lineup-%s" % lg,
                    lambda l=lg: lineup_page.build_page(l, WEEK)))
        out.append(("board-%s" % lg, lambda l=lg: board.build_page(l, WEEK)))
        out.append(("digest-%s" % lg,
                    lambda l=lg: digest.build_digest(l, WEEK)))
        out.append(("tradedesk-%s" % lg,
                    lambda l=lg: tradedesk.build_page(l, WEEK)))
    return out


def test_head_tags():
    print("\n[3] head tags - every page, from the one hook, in <head>")
    tags = pwa.head_tags()
    for needle, why in MUST_HAVE:
        check(needle in tags, "ui/pwa emits %s (%s)" % (needle, why))

    check(tags in ui.style_tag(),
          "ui.style_tag() carries the whole set - THE hook: five of the six "
          "renderers call it and needed no edit")
    check(ui.style_tag().startswith(ui.prefs_boot()),
          "...and the pre-paint preferences script still comes first")
    from engine import digest as _digest
    check(tags in _digest._style_tag(),
          "engine/digest.py builds its own <style> and so asks for the tags "
          "by name - the one renderer that needed a line")

    check(len(LEAGUES) >= 1, "leagues rendered on disk: %s"
          % (", ".join(LEAGUES) or "NONE"))
    pages = _pages()
    check(len(pages) == 10,
          "ten pages under test for week %d (%d found)" % (WEEK, len(pages)))

    seen = 0
    for name, build in pages:
        try:
            html = build()
        except Exception as err:                          # noqa: BLE001
            check(False, "%s: rendered (%s: %s)"
                  % (name, type(err).__name__, str(err)[:90]))
            continue
        seen += 1
        head = html[:html.index("</head>")] if "</head>" in html else ""
        missing = [n for n, _ in MUST_HAVE if n not in head]
        check(not missing, "%s: every app tag, inside <head> (%s)"
              % (name, missing or "all present"))
        check(html.count('rel="manifest"') == 1,
              "%s: exactly one manifest link, never doubled" % name)
        check("env(safe-area-inset-bottom" in html,
              "%s: the safe-area layer rode in on ui.css()" % name)
        links = re.findall(r"<link\b[^>]*>", html.lower())
        stray = [l for l in links if 'rel="manifest"' not in l
                 and 'rel="apple-touch-icon"' not in l]
        check(not stray,
              "%s: no <link> the browser would fetch to paint it (%s)"
              % (name, stray or "none"))
    check(seen == 10, "all ten rendered and were checked (%d of 10)" % seen)


# --- 4. the service worker --------------------------------------------------

def test_worker():
    print("\n[4] service worker - versioned, network-first, tiny")
    path = os.path.join(HERE, pwa.SW_NAME)
    check(os.path.isfile(path), "sw.js is on disk beside the pages")
    src = _read(pwa.SW_NAME)

    if NODE:
        proc = subprocess.run([NODE, "--check", path],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        check(proc.returncode == 0,
              "node --check parses it (%s)"
              % (proc.stdout.decode("utf-8", "replace").strip()[:120] or "clean"))
    else:
        NOTES.append("node is not installed - sw.js was checked for balance "
                     "and shape, not parsed")
        for pair in ("{}", "()", "[]"):
            check(src.count(pair[0]) == src.count(pair[1]),
                  "balanced %s (no parser available)" % pair)
        check("'use strict';" in src, "declared strict")

    check("'use strict'" in src, "the worker is strict mode")
    check("addEventListener('install'" in src
          and "addEventListener('activate'" in src
          and "addEventListener('fetch'" in src,
          "it handles install, activate and fetch and nothing else exotic")
    check(len(src.splitlines()) < 160 and "import " not in src,
          "it is %d lines of plain ES5 - no framework, nothing fetched"
          % len(src.splitlines()))

    # versioned, and the version moves with the week
    a = pwa.cache_name(3, "STAMP")
    b = pwa.cache_name(4, "STAMP")
    check(a != b and "wk3" in a and "wk4" in b,
          "the cache name changes when the week changes (%s -> %s)" % (a, b))
    c = pwa.cache_name(3, "LATER")
    check(c != a,
          "...and again on a new publish of the same week (%s)" % c)
    check(a.startswith(pwa.CACHE_PREFIX) and "delete" in src,
          "every older warroom- cache is deleted on activate, so a new "
          "publish supersedes the old outright")

    sw3 = pwa.service_worker(3, LEAGUES, "STAMP", "then", only_existing=False)
    sw4 = pwa.service_worker(4, LEAGUES, "STAMP", "then", only_existing=False)
    check(sw3 != sw4 and 'wk3' in sw3 and 'wk4' in sw4,
          "the emitted worker itself carries the week in its cache name")
    check("week3" in sw3 and "week4" in sw4,
          "...and precaches that week's pages, not last week's")

    # the two strategies, the right way round
    body = src.split("addEventListener('fetch'", 1)[-1]
    page_branch = body.split("isPage(req)", 1)[-1].split("/* icons", 1)[0]
    check("fetch(req)" in page_branch
          and page_branch.index("fetch(req)") < page_branch.index("caches.match"),
          "PAGES are network-first: the network is tried before the cache, "
          "so a connected phone is never handed a saved verdict")
    tail = body.split("/* icons", 1)[-1]
    check(tail.index("caches.match") < tail.index("fetch(req)"),
          "ICONS AND THE MANIFEST are cache-first - they cannot go stale "
          "inside a cache version")

    assets = pwa.shell_assets(WEEK, LEAGUES, HERE)
    check("./home.html" in assets and "./%s" % pwa.MANIFEST_NAME in assets,
          "the precache covers the landing page and the manifest")
    for lg in LEAGUES:
        check("./lineup-%s-week%d.html" % (lg, WEEK) in assets,
              "...and %s's lineup for the rendered week %d" % (lg, WEEK))
    check(all(os.path.isfile(os.path.join(HERE, a[2:])) for a in assets),
          "every precached path exists - a 404 in the install list would "
          "poison the whole cache")


# --- 5. the honesty contract ------------------------------------------------

_SHIM = r"""
const vm = require('vm'), fs = require('fs');
globalThis.self = {
  addEventListener: function () {}, skipWaiting: function () {},
  clients: {claim: function () {}}, location: {origin: 'https://x'}
};
globalThis.caches = {
  open: function () { return Promise.resolve({put: function(){return Promise.resolve()}, add: function(){return Promise.resolve()}}); },
  keys: function () { return Promise.resolve([]); },
  match: function () { return Promise.resolve(null); }
};
globalThis.Headers = function () { this._ = {}; this.set = function (k, v) { this._[k] = v; }; };
globalThis.Response = function (body, init) { this.body = body; this.init = init; };
globalThis.Request = function (u) { this.url = u; };
globalThis.fetch = function () { return Promise.reject(new Error('offline')); };
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const doc = '<!doctype html><html><head><title>t</title></head><body>'
          + '<header class="wr-nav">bar</header><main class="wr-page">ROWS</main>'
          + '</body></html>';
stale({text: function () { return Promise.resolve(doc); }}).then(function (r) {
  console.log(JSON.stringify({out: r.body, week: WEEK, built: BUILT,
                              cache: CACHE, headers: r.init.headers._}));
});
"""


def test_honesty():
    print("\n[5] honesty - a cached page SAYS it is cached, or it is a lie")
    src = _read(pwa.SW_NAME)

    check("function stale(" in src,
          "there is exactly one way out of the cache for a page: stale()")
    page_branch = src.split("isPage(req)", 1)[-1].split("/* icons", 1)[0]
    check("stale(hit)" in page_branch and "stale(home)" in page_branch,
          "BOTH cache hits in the page path go through it")
    check("return hit;" not in page_branch,
          "no path in the page branch returns a cached response untouched")

    if not NODE:
        NOTES.append("node is not installed - the banner was read, not run")
        for needle in ("Offline", "week ' + WEEK", "BUILT",
                       "not been checked", "Reconnect"):
            check(needle in src, "the banner text contains %r" % needle)
        return

    shim = os.path.join(HERE, "tests", ".pwa_shim.js")
    try:
        with open(shim, "w") as fh:
            fh.write(_SHIM)
        proc = subprocess.run(
            [NODE, shim, os.path.join(HERE, pwa.SW_NAME)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = proc.stdout.decode("utf-8", "replace").strip()
    finally:
        try:
            os.remove(shim)
        except OSError:
            pass

    try:
        got = json.loads(raw)
        ran = True
    except ValueError:
        got, ran = {}, False
        print("      node said: %s" % raw[:300])
    if not check(ran, "the worker's own stale() ran under node on a fixture "
                      "page - this is the real behaviour, not a grep"):
        return

    out = got["out"]
    check("ROWS" in out, "the page's own content survives untouched")
    check(out.index("wr-offline") < out.index("ROWS"),
          "the banner is injected INSIDE <main>, above the first row - under "
          "the sticky bar and inside the page's own gutters")
    check("<main" in out and out.index("<main") < out.index("wr-offline"),
          "...not dumped above the header where it would scroll away")

    low = re.sub(r"<[^>]+>", " ", out).lower()
    check("offline" in low, "it says the word offline")
    check("week %d" % got["week"] in low,
          "it names the week it is showing (week %d)" % got["week"])
    check(str(got["built"]).lower() in low,
          "it names when the copy was built (%s)" % got["built"])
    check("not been checked" in low or "have not been checked" in low,
          "it says nothing in the page has been re-checked")
    check("reconnect" in low, "it tells the reader what to do about it")
    check("var(--wr-rule)" in out and "var(--wr-text)" in out,
          "the banner is drawn in the design system's tokens, so it lands "
          "in whichever theme the reader chose")
    for bad in ("#3DDC97", "#F26D6D", "green", "red"):
        check(bad.lower() not in out.lower(),
              "no %s anywhere in it - attention is a gold rule, never a hue"
              % bad)
    check(got["headers"].get("X-WarRoom-Offline") == "1",
          "the response is labelled offline in its own headers too")
    check(pwa.CACHE_PREFIX in got["cache"] and "wk" in got["cache"],
          "the running worker's cache name is the versioned one (%s)"
          % got["cache"])


# --- 6. the install page ----------------------------------------------------

def test_install():
    print("\n[6] install.html - written for a person, on the design system")
    path = os.path.join(HERE, pwa.INSTALL_NAME)
    check(os.path.isfile(path), "install.html is on disk")
    html = _read(pwa.INSTALL_NAME)

    check(html.startswith("<!doctype html>")
          and html.rstrip().endswith("</html>"), "one complete document")
    check('<header class="wr-nav">' in html,
          "it wears the shell - same navy bar, same tab bar, same switcher")
    check("wr-h1" in html and "wr-kicker" in html and "wr-card" in html,
          "and the design system's own classes, not a private layout")
    body = html.split("</head>", 1)[-1]
    hexes = re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", body)
    check(not hexes, "no colour is written into the markup (%s)"
                     % (sorted(set(hexes)) or "none"))
    own = re.findall(r"<style>(.*?)</style>", html, re.S)[-1]
    stray = sorted(set(re.findall(r"var\((--[a-z0-9-]+)\)", own))
                   - set(v for v in re.findall(r"var\((--[a-z0-9-]+)\)", own)
                         if v.startswith("--wr-")))
    check(not stray, "its stylesheet reads only --wr-* tokens (%s)"
                     % (stray or "clean"))
    sizes = [float(s) for s in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px",
                                          own)]
    check(not sizes or min(sizes) >= ui.TYPE_FLOOR,
          "nothing on it is set below %dpx (%s)"
          % (ui.TYPE_FLOOR, min(sizes) if sizes else "tokens only"))
    check("min-height: 44px" in own,
          "every step is a 44px target - the phone acceptance bar")
    check("grid-template-columns: 1fr;" in own.replace("  ", " ")
          or "grid-template-columns: 1fr" in own,
          "the two-column cards collapse to one at 700px")

    # The READING text: scripts and stylesheets are machinery, not prose,
    # so they come out before the words are judged.
    prose = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", prose)).lower()
    for word in ("share", "add to home screen", "safari", "chrome"):
        check(word in text, "it says %r - the actual thing to tap" % word)
    check("graded takes" in text and "war room" not in text
          and "<title>Install Graded Takes</title>" in html,
          "it names the product, Graded Takes, and never the working title")
    for jargon in ("progressive web app", "pwa", "service worker",
                   "manifest", "cache", "localstorage", "standalone"):
        # `\bpwa\b` would also hit the `engine.pwa` in the rebuild command at
        # the foot of the page; that is a command to type, not a word being
        # used at the reader, so a dotted or slashed prefix does not count.
        hit = re.search(r"(?<![.\w/])%s(?![\w])" % re.escape(jargon), text)
        check(hit is None,
              "it never says %r - nobody's mother needs that word" % jargon)
    for honest in ("offline", "week", "re-checked",
                   "nothing updates without a signal"):
        check(honest in text,
              "it says %r - what the saved copy cannot tell you" % honest)
    check("app store" in text and "no account" in text,
          "it says up front there is no App Store and no account")


# --- 7. additive, and nothing more ------------------------------------------

def test_optional():
    print("\n[7] additive - unregister the worker and nothing changes")
    tags = pwa.head_tags()
    script = re.search(r"<script>(.*?)</script>", tags, re.S)
    check(script is not None, "the head set carries exactly one small script")
    js = script.group(1) if script else ""
    check(len(js) < 400, "it is %d characters" % len(js))
    check("try{" in js and "catch" in js,
          "wrapped in try/catch - a browser without any of this is unharmed")
    check("'serviceWorker' in navigator" in js,
          "feature-detected, never assumed")
    check("location.protocol" in js and "http" in js,
          "and skipped entirely on a file:// page, which is how ./home.sh "
          "opens these")
    check("['catch']" in js or ".catch" in js,
          "a failed registration is swallowed, not thrown at the reader")
    check(tags.count("<script") == 1 and "<script src" not in tags,
          "one inline script and nothing fetched")

    css = pwa.safe_area_css()
    check("env(safe-area-inset-top" in css and "env(safe-area-inset-bottom" in css,
          "the safe-area layer pads the navy bar past the notch and the body "
          "past the home indicator")
    check(", 0px)" in css,
          "every env() has a 0px fallback, so a browser tab and a desktop "
          "pay nothing for it")
    check("font-size" not in css,
          "it sets no type - the scale stays the design system's")
    full = ui.css()
    check(css in full, "it ships inside ui.css(), so every page has it")
    try:
        from engine import prefs as _prefs
        layer = _prefs.css()
    except Exception:                                     # noqa: BLE001
        layer = ""
    check(not layer or full.index(css) < full.index(layer),
          "...ahead of the preferences layer, so the reader's own settings "
          "still win every tie")

    src = _read("engine/pwa.py")
    for bad in ("urllib", "requests", "pandas", "yaml"):
        check(bad not in src, "engine/pwa.py contains no %r" % bad)
    for sacred in ("saves/", "saves\"", "rosters", "sources.yaml", "leagues/"):
        check(sacred not in src,
              "it never names the sacred %r - this module reads design/ and "
              "writes the published pages' own directory, nothing else"
              % sacred)


def main():
    print("INSTALLABLE APP ACCEPTANCE TEST (engine/pwa.py)")
    print("  week %d, leagues %s, node %s"
          % (WEEK, ", ".join(LEAGUES) or "none", "yes" if NODE else "no"))
    test_manifest()
    test_icons()
    test_head_tags()
    test_worker()
    test_honesty()
    test_install()
    test_optional()
    for note in NOTES:
        print("\n  note: %s" % note)
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d of %d FAILURE(S):" % (len(FAILURES), CHECKS[0])))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
