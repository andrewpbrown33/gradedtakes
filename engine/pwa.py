#!/usr/bin/env python3
"""The installable-app layer: manifest, icons, service worker, install page.

WHY THIS MODULE EXISTS
----------------------
The ten pages are already the whole product on a phone. What they are not
is an ICON. A family member who has to remember a filename, find it in a
browser's history and squint past the address bar is a family member who
opens it twice and then stops. This module turns the same static pages
into something iOS and Android will put on a home screen and open
full-screen, WITHOUT changing a single thing about how the pages are
built, and without adding one byte the page's rendering depends on.

    .venv/bin/python -m engine.pwa            # icons, manifest, sw.js, install.html
    .venv/bin/python -m engine.pwa --week 3   # cache a specific week

FIVE PIECES, AND WHAT EACH ONE ACTUALLY BUYS
--------------------------------------------
  manifest.webmanifest  name, icons, standalone display, portrait, the two
                        brand colours. Android/Chrome reads all of it; iOS
                        16.4+ reads most of it.
  icons/                PNGs rasterised from design/icon.svg by `sips`
                        (macOS, no install), plus the SVG itself.
  head tags             the <meta>/<link> set every page needs, injected
                        through ONE hook - ui.style_tag() - so no renderer
                        was edited to get them.
  sw.js                 the offline copy. Network-first for pages so a
                        connected phone is never shown yesterday's read;
                        cache-first for the icons and the manifest, which
                        never change within a version.
  install.html          what to tap, written for someone who has never
                        heard the phrase "progressive web app".

THE HONESTY LINE - THE ONLY REASON THE SERVICE WORKER IS ALLOWED
-----------------------------------------------------------------
A cache that serves a week-old page as though it were live is the single
worst thing this product could do. A verdict is a claim about right now:
"START him" was true on Sunday at 11am and can be false at 11:40. So the
service worker NEVER silently serves a stale page. Every cached page it
hands back is rewritten on the way out with a banner that says it is a
saved copy, which week it is, when it was built, and that nothing in it
has been re-checked. That is the same contract every degraded section on
every page already holds itself to - it says what it does not know and
asserts nothing - and it is why the fallback path in `service_worker()`
is not allowed to return a cached response untouched.

WHAT THIS DOES NOT DO TO THE PAGES
----------------------------------
The pages stay self-contained. The head tags add two <link>s -
`rel="manifest"` and `rel="apple-touch-icon"` - and NOTHING the render
depends on: strip both and every page still paints identically, offline,
from its own bytes. There is deliberately no `rel="icon"`, because a
favicon IS fetched to paint a tab, and that would be a real break in the
contract for a 16px decoration. See `head_tags()`.

PURITY
------
Colours are READ FROM ui, never restated. `theme_color()` and
`background_color()` parse ui.tokens_css() rather than copying a hex, so
a palette edit reaches the home screen icon and the iOS status bar the
same day it reaches the pages, and tests/pwa_test.py asserts the SVG's
two hexes still equal those tokens.
"""

import json
import os
import re
import struct
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

from engine import ui

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_SVG = os.path.join(HERE, "design", "icon.svg")

# The product name, from the design system so the label under the home
# screen icon can never drift from the wordmark in the bar. "Graded
# Takes" is 12 characters - inside the short_name budget every launcher
# shows untruncated.
APP_NAME = ui.PRODUCT_NAME
APP_SHORT = ui.PRODUCT_NAME
APP_DESC = ("Your fantasy teams, read by one model: lineup verdicts, the "
            "waiver board, the trade desk and the week's ledger.")

# The manifest's entry point. The brief asked for ".", which is what you
# write when the directory has an index.html; this one does not - the
# landing page is home.html - so "." would install an icon that opens a
# directory listing. `scope` stays "./" so every page is inside the app.
START_URL = "./home.html"
SCOPE = "./"

ICON_DIR = "icons"
MANIFEST_NAME = "manifest.webmanifest"
SW_NAME = "sw.js"
INSTALL_NAME = "install.html"

# The four rasters, plus the vector. 180 is the apple-touch-icon iOS wants;
# 192 and 512 are the two Android/Chrome requires; the maskable 512 is the
# same mark shrunk into Android's safe zone so an adaptive-icon mask cannot
# clip the diamond's points.
ICON_SPECS: Tuple[Tuple[str, int, str], ...] = (
    ("apple-touch-icon-180.png", 180, "any"),
    ("icon-192.png", 192, "any"),
    ("icon-512.png", 512, "any"),
    ("icon-maskable-512.png", 512, "maskable"),
)

# Android's maskable safe zone is the centred circle of 80% diameter. The
# mark's diagonal is 60% of the canvas, so scaling it to 0.68 leaves it
# inside a 41%-diameter circle - clear of every mask shape Android applies.
MASKABLE_SCALE = 0.68


# --- colours: read from the design system, never restated -------------------

def _token(name: str) -> str:
    """One design token's LIGHT value, parsed out of ui.tokens_css().

    Parsed rather than imported so this module cannot drift into being a
    second palette: if ui renames or re-values a token, this raises at
    build time instead of shipping last season's navy to a home screen.
    """
    light = ui.tokens_css().split("@media", 1)[0]
    hit = re.search(r"--wr-%s:\s*([^;]+);" % re.escape(name), light)
    if not hit:
        raise RuntimeError("engine/ui.py has no --wr-%s token" % name)
    return hit.group(1).strip()


def theme_color() -> str:
    """The navy bar. It is navy in BOTH themes (see ui._LIGHT/_DARK), which
    is exactly why it can be a single theme-color: the iOS status bar and
    the Android task-switcher chrome never have to repaint."""
    return _token("nav")


def background_color() -> str:
    """The paper. This is what the OS paints for the splash screen in the
    half-second before the page's own CSS exists, so it has to be the
    canvas the page will settle on, not white."""
    return _token("canvas")


def accent_color() -> str:
    return _token("rule")


# --- the mark ---------------------------------------------------------------

def icon_svg() -> str:
    with open(ICON_SVG, "r") as fh:
        return fh.read()


def svg_hexes(svg: Optional[str] = None) -> List[str]:
    """Every colour literal in the mark, upper-cased."""
    src = icon_svg() if svg is None else svg
    body = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return [h.upper() for h in re.findall(r"#[0-9a-fA-F]{6}\b", body)]


def check_brand(svg: Optional[str] = None) -> None:
    """The mark is the brand or the build stops.

    design/icon.svg is an art file and carries literal hexes; this is what
    keeps them honest. Only two colours are allowed and they are the two
    tokens the nav bar is made of.
    """
    want = {theme_color().upper(), accent_color().upper()}
    got = set(svg_hexes(svg))
    if got != want:
        raise RuntimeError(
            "design/icon.svg is off-brand: uses %s, the tokens are %s"
            % (sorted(got), sorted(want)))


def maskable_svg() -> str:
    """The Android adaptive variant, derived from the one authored SVG.

    The navy ground stays full-bleed (a maskable icon must have no
    transparency to the edge) and only <g id="mark"> is scaled about the
    centre, so there is still exactly one drawing to maintain.
    """
    src = icon_svg()
    if '<g id="mark">' not in src:
        raise RuntimeError('design/icon.svg must wrap its art in <g id="mark">')
    wrap = ('<g id="mark" transform="translate(256,256) scale(%s) '
            'translate(-256,-256)">' % MASKABLE_SCALE)
    return src.replace('<g id="mark">', wrap, 1)


# --- rasterising ------------------------------------------------------------

def png_size(path: str) -> Tuple[int, int]:
    """A PNG's REAL pixel dimensions, read out of its IHDR chunk.

    Deliberately not `sips -g pixelWidth`: the point of the check is to
    read the file rather than to ask the same tool that wrote it.
    """
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("%s is not a PNG" % path)
    return struct.unpack(">II", head[16:24])


def rasteriser() -> Optional[str]:
    """The tool we will actually use, or None.

    `sips` ships with macOS and reads SVG directly, so there is nothing to
    install. `qlmanage` is the documented fallback (Quick Look renders the
    SVG through the same WebKit the phone will use) and it is checked
    second because it can only write one size per call and names its
    output after the input.
    """
    for tool in ("sips", "qlmanage"):
        path = _which(tool)
        if path:
            return tool
    return None


def _which(name: str) -> Optional[str]:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


FALLBACK_COMMAND = (
    "qlmanage -t -s 512 -o icons design/icon.svg && "
    "sips -s format png -Z 512 icons/icon.svg.png --out icons/icon-512.png")


def write_icons(root: str = HERE) -> Tuple[Optional[str], List[str], List[str]]:
    """Rasterise the mark. Returns (tool, written paths, notes).

    Every PNG is measured from its own bytes afterwards; a size that came
    out wrong is deleted rather than shipped, because a manifest that
    declares 512x512 and points at a 128px file is a manifest that fails
    installability with no visible symptom.
    """
    check_brand()
    outdir = os.path.join(root, ICON_DIR)
    _mkdir(outdir)
    written, notes = [], []

    svg_path = os.path.join(outdir, "icon.svg")
    _write(svg_path, icon_svg())
    written.append(svg_path)
    mask_src = os.path.join(outdir, ".icon-maskable.svg")
    _write(mask_src, maskable_svg())

    tool = rasteriser()
    if not tool:
        notes.append(
            "no rasteriser found - the SVG shipped, the PNGs did not. "
            "One command fixes it: %s" % FALLBACK_COMMAND)
        _rm(mask_src)
        return None, written, notes

    for name, size, purpose in ICON_SPECS:
        src = mask_src if purpose == "maskable" else svg_path
        dst = os.path.join(outdir, name)
        ok = _raster(tool, src, dst, size)
        if not ok:
            notes.append("%s: %s could not rasterise it" % (name, tool))
            continue
        try:
            w, h = png_size(dst)
        except (OSError, ValueError) as err:
            notes.append("%s: not a readable PNG (%s)" % (name, err))
            _rm(dst)
            continue
        if (w, h) != (size, size):
            notes.append("%s: came out %dx%d, wanted %dx%d - dropped"
                         % (name, w, h, size, size))
            _rm(dst)
            continue
        written.append(dst)

    _rm(mask_src)
    return tool, written, notes


def _raster(tool: str, src: str, dst: str, size: int) -> bool:
    if tool == "sips":
        cmd = ["sips", "-s", "format", "png",
               "--resampleHeightWidth", str(size), str(size),
               src, "--out", dst]
    else:                                   # qlmanage: one size, fixed name
        cmd = ["qlmanage", "-t", "-s", str(size), "-o",
               os.path.dirname(dst), src]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return False
    if tool == "qlmanage":
        made = os.path.join(os.path.dirname(dst),
                            os.path.basename(src) + ".png")
        if os.path.isfile(made):
            os.replace(made, dst)
    return os.path.isfile(dst)


# --- the manifest -----------------------------------------------------------

def icon_entries(root: str = HERE, only_existing: bool = True) -> List[Dict]:
    out: List[Dict] = []
    svg = os.path.join(root, ICON_DIR, "icon.svg")
    if not only_existing or os.path.isfile(svg):
        out.append({"src": "./%s/icon.svg" % ICON_DIR, "sizes": "any",
                    "type": "image/svg+xml", "purpose": "any"})
    for name, size, purpose in ICON_SPECS:
        path = os.path.join(root, ICON_DIR, name)
        if only_existing and not os.path.isfile(path):
            continue
        out.append({"src": "./%s/%s" % (ICON_DIR, name),
                    "sizes": "%dx%d" % (size, size),
                    "type": "image/png", "purpose": purpose})
    return out


def manifest(week: int = 1, league: str = "", root: str = HERE,
             only_existing: bool = True) -> Dict:
    """The web app manifest, as a dict."""
    data: Dict = {
        "name": APP_NAME,
        "short_name": APP_SHORT,
        "description": APP_DESC,
        "id": SCOPE,
        "start_url": START_URL,
        "scope": SCOPE,
        "display": "standalone",
        "orientation": "portrait",
        "background_color": background_color(),
        "theme_color": theme_color(),
        "lang": "en",
        "dir": "ltr",
        "categories": ["sports"],
        "icons": icon_entries(root, only_existing=only_existing),
    }
    cuts = shortcuts(week, league, root, only_existing=only_existing)
    if cuts:
        data["shortcuts"] = cuts
    return data


def shortcuts(week: int, league: str, root: str = HERE,
              only_existing: bool = True) -> List[Dict]:
    """Long-press the icon and go straight to the two pages people open.

    Cheap, and only offered for pages that are actually on disk - a
    shortcut to a file that was never rendered is a 404 with the app's own
    name on it.
    """
    if not league:
        return []
    icons = [i for i in icon_entries(root, only_existing=only_existing)
             if i.get("sizes") == "192x192"]
    out = []
    for label, stem, desc in (
            ("Lineup", "lineup", "Who to start this week"),
            ("Board", "board", "Every player, every source")):
        rel = "%s-%s-week%d.html" % (stem, league, week)
        if only_existing and not os.path.isfile(os.path.join(root, rel)):
            continue
        cut = {"name": label, "short_name": label,
               "description": desc, "url": "./%s" % rel}
        if icons:
            cut["icons"] = icons
        out.append(cut)
    return out


def manifest_json(week: int = 1, league: str = "", root: str = HERE,
                  only_existing: bool = True) -> str:
    return json.dumps(manifest(week, league, root, only_existing),
                      indent=2, sort_keys=False) + "\n"


# --- the head tags (the ONE hook) -------------------------------------------

# The two link relations the pages carry, and the whole list: anything else
# would be fetched to paint the page and would break the self-contained
# contract. tests/pwa_test.py and the six page suites assert this set.
LINK_RELS = ("manifest", "apple-touch-icon")

# `black-translucent` and nothing else. The three choices are `default` (a
# light strip with dark text), `black` (an opaque black strip) and
# `black-translucent` (no strip at all - the page runs under the clock).
# The header is ui's nav token, the same navy in both themes, so `default`
# would hang a white band over it and `black` a pure-black one that reads
# as a seam against the navy. `black-translucent` lets the navy bar BE the
# status bar; ui gets `padding-top: env(safe-area-inset-top)` on .wr-nav from
# safe_area_css() so the clock never lands on the league name.
STATUS_BAR_STYLE = "black-translucent"

# Guarded on every axis: no serviceWorker on a file:// page (which is how
# ./home.sh opens these), none in older Safari, and a failed registration
# is swallowed. The page has never depended on this script and does not
# start to now - unregister the worker and everything still works.
_REGISTER_JS = (
    "(function(){try{if('serviceWorker' in navigator&&"
    "location.protocol.slice(0,4)==='http'){"
    "addEventListener('load',function(){navigator.serviceWorker"
    ".register('%s',{scope:'%s'})['catch'](function(){});});}}"
    "catch(e){}})();" % (SW_NAME, SCOPE)
)


def head_tags() -> str:
    """Everything the phone needs, and nothing the page needs.

    Emitted once per page from ui.style_tag(), which every renderer
    already calls, so not one of the six renderers was edited to get an
    installable app.

    The viewport line is deliberately a SECOND viewport meta. Each
    renderer writes its own `width=device-width, initial-scale=1` before
    calling ui.style_tag(); this one repeats those two values and adds
    `viewport-fit=cover`, so it is correct whether the browser treats a
    later viewport meta as a merge or as a replacement. Editing the
    renderers' line instead would have meant touching all six.
    """
    return "\n".join((
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1, viewport-fit=cover">',
        '<meta name="theme-color" content="%s">' % theme_color(),
        '<meta name="apple-mobile-web-app-capable" content="yes">',
        '<meta name="mobile-web-app-capable" content="yes">',
        '<meta name="apple-mobile-web-app-status-bar-style" content="%s">'
        % STATUS_BAR_STYLE,
        '<meta name="apple-mobile-web-app-title" content="%s">' % APP_NAME,
        '<meta name="application-name" content="%s">' % APP_NAME,
        '<link rel="manifest" href="%s">' % MANIFEST_NAME,
        '<link rel="apple-touch-icon" href="%s/apple-touch-icon-180.png">'
        % ICON_DIR,
        "<script>%s</script>" % _REGISTER_JS,
    )) + "\n"


def safe_area_css() -> str:
    """The inset padding an installed window needs, appended to ui.css().

    env() resolves to 0 in every browser tab and on every desktop, so this
    layer costs a page that is not installed exactly nothing.
    """
    return """
  /* --- installed app: the safe areas (engine/pwa.py) ------------------- */
  /* With apple-mobile-web-app-status-bar-style=black-translucent the page
     runs UNDER the status bar. What should fill that strip is the navy
     bar, not the top of the league name, so the bar grows by the inset
     instead of the content sliding beneath the clock. */
  .wr-nav { padding-top: env(safe-area-inset-top, 0px); }
  :root { --wr-nav-h: calc(72px + env(safe-area-inset-top, 0px)); }
  @media (max-width: 700px) {
    /* .wr-tabs already pads itself past the home indicator; the body has
       to clear the bar AND that padding or the last row of every page
       hides behind it. */
    body { padding-bottom: calc(60px + env(safe-area-inset-bottom, 0px)); }
    /* landscape on a notched phone: keep the page off the sensor housing
       without ever narrowing the 18px gutter the layout is drawn to. */
    .wr-page { padding-left: max(18px, env(safe-area-inset-left, 0px));
               padding-right: max(18px, env(safe-area-inset-right, 0px)); }
  }
"""


# --- the service worker -----------------------------------------------------

CACHE_PREFIX = "warroom-"
CACHE_EPOCH = "v1"


def cache_name(week: int, stamp: str) -> str:
    """Versioned per publish AND per week.

    The week is in the name on purpose: a Tuesday publish for week 4 must
    not be able to serve week 3's verdicts out of an old bucket, and the
    activate handler drops every `warroom-` cache that is not this one.
    """
    return "%s%s-wk%d-%s" % (CACHE_PREFIX, CACHE_EPOCH, int(week),
                             re.sub(r"[^0-9A-Za-z]+", "", str(stamp)))


def shell_assets(week: int, leagues: Sequence[str],
                 root: str = HERE, only_existing: bool = True) -> List[str]:
    """What gets cached: the last rendered week, plus the app furniture."""
    out = ["./home.html", "./sources.html", "./%s" % INSTALL_NAME,
           "./%s" % MANIFEST_NAME]
    for lg in leagues:
        for stem in ("lineup", "board", "digest", "tradedesk"):
            out.append("./%s-%s-week%d.html" % (stem, lg, int(week)))
    for entry in icon_entries(root, only_existing=only_existing):
        out.append(entry["src"])
    keep = []
    for rel in out:
        if only_existing and not os.path.isfile(
                os.path.join(root, rel[2:] if rel.startswith("./") else rel)):
            continue
        if rel not in keep:
            keep.append(rel)
    return keep


def service_worker(week: int = 1, leagues: Sequence[str] = (),
                   stamp: str = "", stamp_human: str = "",
                   root: str = HERE, only_existing: bool = True) -> str:
    """The offline copy, and the banner that keeps it honest.

    STRATEGY, and why each half is the way round it is:

      PAGES are network-first. A phone with a bar of signal must never be
      handed Sunday-morning's verdicts because they were quicker to reach.
      Only when the network actually fails does the cache answer - and
      then never untouched: `stale()` rewrites the document with a banner
      naming the week and the build time before it leaves the worker.

      ICONS AND THE MANIFEST are cache-first. They cannot go out of date
      inside a cache version, and they are what makes the app open
      instantly instead of flashing white.

    Everything else falls through to the network untouched, so nothing
    this worker does can make a page show something the page did not say.
    """
    assets = shell_assets(week, leagues, root, only_existing=only_existing)
    return _SW_TEMPLATE % {
        "cache": _js_str(cache_name(week, stamp)),
        "prefix": _js_str(CACHE_PREFIX),
        "week": int(week),
        "stamp": _js_str(stamp_human or stamp or "an earlier publish"),
        "assets": ",\n  ".join(_js_str(a) for a in assets),
        "start": _js_str(START_URL),
        # The last-resort document below is the ONE place a colour has to be
        # spelled out - it is served when there is no cached page and so no
        # stylesheet to inherit tokens from. They are still the tokens.
        "paper": background_color(),
        "ink": _token("text"),
    }


def _js_str(value) -> str:
    return json.dumps(str(value))


_SW_TEMPLATE = """'use strict';
/* Graded Takes service worker - engine/pwa.py wrote this file; edit that.

   The whole contract in one line: this worker may make the app OPEN
   offline, and it may never make the app LIE. Anything it serves from the
   cache is rewritten with a banner that says so before it is handed over. */

var CACHE  = %(cache)s;
var PREFIX = %(prefix)s;
var WEEK   = %(week)d;
var BUILT  = %(stamp)s;
var START  = %(start)s;
var SHELL  = [
  %(assets)s
];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) {
      return c.add(new Request(u, {cache: 'reload'}))['catch'](function () {});
    }));
  }).then(function () { return self.skipWaiting(); }));
});

/* A new publish supersedes the old one outright: every warroom- cache that
   is not this exact version goes, so a stale week cannot survive a
   deploy. */
self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.map(function (k) {
      if (k !== CACHE && k.lastIndexOf(PREFIX, 0) === 0) {
        return caches['delete'](k);
      }
      return null;
    }));
  }).then(function () { return self.clients.claim(); }));
});

function isPage(req) {
  if (req.mode === 'navigate') { return true; }
  var a = req.headers.get('accept') || '';
  return a.indexOf('text/html') > -1;
}

/* THE BANNER. Not decoration - the reason the cache is allowed to exist.
   It names the week, names the build time, and refuses to imply anything
   in the page has been re-checked. Colours are the page's own tokens, so
   it lands in whichever theme the reader chose. */
function banner() {
  return '<div class="wr-offline" role="status" aria-live="polite">'
    + '<b>Offline &mdash; showing week ' + WEEK + ' as of ' + BUILT + '.</b> '
    + 'This is the saved copy your phone already had. Injuries, kickoffs, '
    + 'scores and every verdict below were true when it was built and have '
    + 'not been checked since. Reconnect and reload for the current read.'
    + '</div>'
    + '<style>.wr-offline{margin:0 0 16px;padding:12px 14px;'
    + 'border-left:3px solid var(--wr-rule);background:var(--wr-wash-hot);'
    + 'color:var(--wr-text);font-size:var(--wr-t3);line-height:1.45;'
    + 'border-radius:0 6px 6px 0;}'
    + '.wr-offline b{display:block;margin-bottom:2px;}</style>';
}

/* Rewrite on the way out. The banner goes just inside <main> so it sits
   under the sticky bar and inside the page's own gutters; <body> is the
   fallback for any document that ever stops using <main>. */
function stale(res) {
  return res.text().then(function (body) {
    var mark = banner();
    var out = body.replace(/<main\\b[^>]*>/, function (m) { return m + mark; });
    if (out === body) {
      out = body.replace(/<body\\b[^>]*>/, function (m) { return m + mark; });
    }
    if (out === body) { out = mark + body; }
    var h = new Headers();
    h.set('Content-Type', 'text/html; charset=utf-8');
    h.set('X-WarRoom-Offline', '1');
    return new Response(out, {status: 200, statusText: 'offline copy',
                              headers: h});
  });
}

function nothingSaved() {
  return new Response(
    '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
    + '<meta name="viewport" content="width=device-width,initial-scale=1">'
    + '<title>Graded Takes &mdash; offline</title>'
    + '<body style="margin:0;padding:28px;background:%(paper)s;'
    + 'color:%(ink)s;'
    + 'font:15px/1.5 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">'
    + '<h1 style="font-size:26px;margin:0 0 10px">Offline</h1>'
    + '<p>Graded Takes has no saved copy of this page yet, so it has nothing to '
    + 'show you and will not guess. Reconnect and open it once; after that '
    + 'it opens without a signal.</p>',
    {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8'}});
}

function keep(req, res) {
  if (res && res.ok && res.type !== 'opaque') {
    var copy = res.clone();
    caches.open(CACHE).then(function (c) {
      c.put(req, copy)['catch'](function () {});
    })['catch'](function () {});
  }
  return res;
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') { return; }
  var url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) { return; }

  if (isPage(req)) {                       /* network-first, honest fallback */
    e.respondWith(
      fetch(req).then(function (res) { return keep(req, res); })
        ['catch'](function () {
          return caches.match(req, {ignoreSearch: true}).then(function (hit) {
            if (hit) { return stale(hit); }
            return caches.match(START).then(function (home) {
              return home ? stale(home) : nothingSaved();
            });
          });
        })
    );
    return;
  }

  /* icons and the manifest: cache-first - they cannot go stale inside a
     cache version, and they are what makes the app open without a flash */
  e.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) { return hit; }
      return fetch(req).then(function (res) { return keep(req, res); });
    })['catch'](function () { return fetch(req); })
  );
});
"""


# --- the install page -------------------------------------------------------

_INSTALL_CSS = """
  .ins-lede { color: var(--wr-muted); font-size: var(--wr-t2);
              max-width: 62ch; margin: 6px 0 0; }
  .ins-cards { display: grid; gap: 16px; grid-template-columns: 1fr 1fr;
               margin-top: 18px; }
  .ins-steps { margin: 10px 0 0; padding: 0; list-style: none;
               counter-reset: ins; }
  /* BLOCK, never flex. A flex <li> turns every <b> and every key cap into
     a flex item and shreds the sentence into columns - which is exactly
     what it did at 375px the first time this page was measured. */
  .ins-steps li { position: relative; display: block;
                  padding: 12px 0 12px 42px; min-height: 44px;
                  border-top: 1px solid var(--wr-hairline);
                  font-size: var(--wr-t2); line-height: 1.5; }
  .ins-steps li:first-child { border-top: 0; }
  .ins-steps li::before { counter-increment: ins; content: counter(ins);
                          position: absolute; left: 0; top: 12px;
                          width: 28px; height: 28px; border-radius: 50%;
                          background: var(--wr-rule); color: var(--wr-chip-ink);
                          font-size: var(--wr-t3); font-weight: 700;
                          line-height: 28px; text-align: center; }
  .ins-steps b { font-weight: 700; }
  .ins-k { display: inline-block; padding: 2px 7px; border-radius: 5px;
           border: 1px solid var(--wr-hairline-2); background: var(--wr-raised);
           font-size: var(--wr-t3); font-weight: 600; white-space: nowrap; }
  .ins-two { display: grid; gap: 0 22px; grid-template-columns: 1fr 1fr;
             margin-top: 4px; }
  .ins-list { margin: 8px 0 0; padding: 0; list-style: none; }
  .ins-list li { padding: 9px 0 9px 26px; position: relative;
                 border-top: 1px solid var(--wr-hairline);
                 font-size: var(--wr-t2); line-height: 1.45; }
  .ins-list li:first-child { border-top: 0; }
  .ins-list li::before { position: absolute; left: 4px; top: 9px;
                         color: var(--wr-rule); font-weight: 700;
                         content: "\\2014"; }
  .ins-no li::before { color: var(--wr-hairline-2); }
  .ins-note { margin-top: 16px; padding: 12px 14px;
              border-left: 3px solid var(--wr-rule);
              background: var(--wr-wash-hot); color: var(--wr-text);
              font-size: var(--wr-t3); line-height: 1.5;
              border-radius: 0 6px 6px 0; }
  .ins-foot { margin-top: 26px; color: var(--wr-muted);
              font-size: var(--wr-t4); line-height: 1.6; }
  .ins-foot code { font-size: var(--wr-t4); }
  .ins-next { margin-top: 16px; }
  .ins-sub { margin: 12px 0 0; font-size: var(--wr-t3); font-weight: 700;
             letter-spacing: 0.04em; text-transform: uppercase;
             color: var(--wr-muted); }
  @media (max-width: 700px) {
    .ins-cards, .ins-two { grid-template-columns: 1fr; gap: 14px; }
  }
"""


def _steps(rows: Sequence[str]) -> str:
    return '<ol class="ins-steps">%s</ol>' % "".join(
        "<li>%s</li>" % r for r in rows)


def install_page(week: int = 1, league: str = "", stamp_human: str = "",
                 host_page: str = "home.html") -> str:
    """install.html - written for the person, not the platform.

    No jargon: the words "progressive web app", "manifest" and "service
    worker" do not appear. What appears is what to tap, in the order the
    phone shows it, and an honest paragraph about what the saved copy can
    and cannot tell you.
    """
    esc = ui.esc
    shell = ui.shell("install", league=league or None, week=week,
                     leagues=(), title="Install %s" % APP_NAME)

    ios = _steps((
        'Open the %s link you were sent (it ends in <b>%s</b>) in '
        '<b>Safari</b>. Safari is the sure route on an iPhone; some other '
        'browsers can do this now, but not all of them.' % (esc(APP_NAME), esc(host_page)),
        'Tap the <span class="ins-k">Share</span> button: the square with an '
        'arrow coming out of the top. It is at the bottom of the screen, or '
        'top-right on an iPad.',
        'Scroll the grey list down until you see '
        '<span class="ins-k">Add to Home Screen</span>, and tap it.',
        'The name will already say <b>%s</b>. Tap '
        '<span class="ins-k">Add</span>, top-right.' % esc(APP_NAME),
        'Close Safari. The gold diamond is on your home screen. Tap it and '
        'it opens full screen — no address bar, no tabs.',
    ))

    android = _steps((
        'Open the %s link you were sent (it ends in <b>%s</b>) in '
        '<b>Chrome</b>.' % (esc(APP_NAME), esc(host_page)),
        'Tap the <span class="ins-k">⋮</span> menu, top-right.',
        'Tap <span class="ins-k">Add to Home screen</span> (older phones say '
        '<span class="ins-k">Install app</span>), then confirm.',
        'Tap the gold diamond on your home screen. Press and hold it and you '
        'also get <b>Lineup</b> and <b>Board</b> as shortcuts.',
    ))

    yes = ("Every page you had already opened, exactly as it looked when it "
           "was built — lineup, board, ledger, trade desk, sources.",
           "The whole page, not a summary: the sheets open, the switches "
           "switch, the numbers are all there.",
           "A banner across the top of anything saved, saying which week it "
           "is and when it was built.")
    no = ("Anything you had never opened on that phone. It will say so "
          "rather than guess.",
          "Live scores, a new injury, a waiver that cleared this morning. "
          "Nothing updates without a signal.",
          "Setting a lineup. That still happens on ESPN or Yahoo — the "
          "buttons that jump you there need a signal too.",
          "Saving anything at all, if you opened these pages as a file "
          "rather than a web address. A phone can only keep a copy of a "
          "page it fetched over the internet. The icon and the full-screen "
          "window still work either way.")

    built = (' <b>This copy was built %s.</b>' % esc(stamp_human)
             if stamp_human else "")

    body = (
        '<header class="ins-head"><p class="wr-kicker">Install</p>'
        '<h1 class="wr-h1 wr-display">Put %s on your phone</h1>'
        '<p class="ins-lede">Two minutes, no App Store, no account, nothing '
        'to pay. You end up with a gold diamond on your home screen that '
        'opens straight into your week.</p></header>'

        '<div class="ins-cards">'
        '<section class="wr-card">%s%s</section>'
        '<section class="wr-card">%s%s</section>'
        '</div>'

        '<section class="wr-card ins-next">%s'
        '<div class="ins-two">'
        '<div><p class="ins-sub">It still works</p>'
        '<ul class="ins-list">%s</ul></div>'
        '<div><p class="ins-sub">It cannot</p>'
        '<ul class="ins-list ins-no">%s</ul></div>'
        '</div>'
        '<p class="ins-note">%s will never show you a saved page as if '
        'it were live. If your phone is offline, every page opens with a '
        'banner naming the week and the moment it was built, and saying that '
        'nothing in it has been re-checked. A verdict that was right on '
        'Sunday morning can be wrong by kickoff, and the app is not allowed '
        'to hide that from you.%s</p>'
        '</section>'

        '<section class="wr-card ins-next">%s'
        '<ul class="ins-list">'
        '<li>The icon does not need updating. It always opens the newest '
        'page that has been published.</li>'
        '<li>A new week is a new set of pages. Open the app once while you '
        'have a signal and it saves the new week for you.</li>'
        '<li>To remove it: press and hold the diamond, then delete it like '
        'any other app. Nothing is left behind.</li>'
        '</ul></section>'

        '<p class="ins-foot">Rebuild this page and the icons with '
        '<code>.venv/bin/python -m engine.pwa</code>. The mark is one file, '
        '<code>design/icon.svg</code> — the same gold diamond that sits '
        'in the bar at the top of every page.</p>'
        % (esc(APP_NAME), ui.section_header("On an iPhone or iPad",
                             "Safari · about two minutes"), ios,
           ui.section_header("On an Android phone", "Chrome"), android,
           ui.section_header("With no signal",
                             "what the saved copy can and cannot tell you"),
           "".join("<li>%s</li>" % y for y in yes),
           "".join("<li>%s</li>" % n for n in no),
           esc(APP_NAME), built,
           ui.section_header("Afterwards")))

    return ('<!doctype html>\n<html lang="en"><head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n'
            '<title>Install %s</title>\n%s\n<style>%s</style>\n'
            '</head><body>\n%s\n<main class="wr-page">\n%s\n</main>\n'
            '</body></html>\n'
            % (esc(APP_NAME), ui.style_tag(), _INSTALL_CSS, shell, body))


# --- discovery + writing ----------------------------------------------------

_PAGE_RE = re.compile(r"^(lineup|board|digest|tradedesk)-(.+)-week(\d+)\.html$")


def discover(root: str = HERE) -> Tuple[int, List[str]]:
    """The last rendered week and the leagues rendered for it, from disk.

    Reading the filenames beats asking the calendar: what the worker should
    cache is what has actually been published, not what week it is.
    """
    weeks: Dict[int, set] = {}
    try:
        names = os.listdir(root)
    except OSError:
        return 1, []
    for name in names:
        hit = _PAGE_RE.match(name)
        if hit:
            weeks.setdefault(int(hit.group(3)), set()).add(hit.group(2))
    if not weeks:
        return 1, []
    week = max(weeks)
    return week, sorted(weeks[week])


def _mkdir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path)


def _write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _stamp(root: str = HERE, pages: Sequence[str] = ()) -> Tuple[str, str]:
    """When the CACHED PAGES were built - not when this module last ran.

    The offline banner says "showing week N as of <this>", and the only
    honest answer is the moment the numbers in those pages were true.
    Stamping it with pwa.py's own run time would date a week-old board to
    this afternoon every time the icons were regenerated. Falls back to
    now only when there is no page to read a time from.
    """
    import time
    newest = 0.0
    for rel in pages:
        path = os.path.join(root, rel[2:] if rel.startswith("./") else rel)
        if path.endswith(".html") and os.path.isfile(path):
            newest = max(newest, os.path.getmtime(path))
    when = time.localtime(newest) if newest else time.localtime()
    return (time.strftime("%Y%m%dT%H%M%S", when),
            time.strftime("%a %-d %b, %-I:%M %p", when))


def write_all(root: str = HERE, week: Optional[int] = None,
              leagues: Optional[Sequence[str]] = None) -> Dict:
    """Write icons, manifest, sw.js and install.html. Returns a report."""
    found_week, found_leagues = discover(root)
    week = int(week) if week else found_week
    lgs = list(leagues) if leagues else found_leagues
    # install.html is the one page in the list this module writes itself, so
    # it is excluded: the stamp has to come from the RENDERED pages.
    cached = shell_assets(week, lgs, root)
    stamp, human = _stamp(root, [a for a in cached
                                 if not a.endswith(INSTALL_NAME)])

    tool, icons, notes = write_icons(root)

    man = os.path.join(root, MANIFEST_NAME)
    _write(man, manifest_json(week, lgs[0] if lgs else "", root))

    sw = os.path.join(root, SW_NAME)
    _write(sw, service_worker(week, lgs, stamp, human, root))

    ins = os.path.join(root, INSTALL_NAME)
    _write(ins, install_page(week, lgs[0] if lgs else "", human))

    return {"week": week, "leagues": lgs, "rasteriser": tool,
            "icons": icons, "notes": notes, "stamp": human,
            "files": [man, sw, ins] + icons,
            "cached": shell_assets(week, lgs, root)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    week = None
    if "--week" in args:
        i = args.index("--week")
        if i + 1 < len(args):
            week = int(args[i + 1])
    rep = write_all(week=week)
    print("%s - installable app" % APP_NAME)
    print("  week cached : %d  (%s)" % (rep["week"],
                                        ", ".join(rep["leagues"]) or "no leagues"))
    print("  rasteriser  : %s" % (rep["rasteriser"] or "NONE"))
    print("  icons       : %d" % len(rep["icons"]))
    print("  pages cached: %d" % len(rep["cached"]))
    for note in rep["notes"]:
        print("  note        : %s" % note)
    for path in rep["files"]:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
