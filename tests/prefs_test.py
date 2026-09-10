#!/usr/bin/env python3
"""Acceptance test: reader preferences (engine/prefs.py).

engine/prefs.py is PURE PRESENTATION like ui.py - it reads no files and
writes nothing - so this suite needs no fixture root. It asserts:

  [1] BOOT       the pre-paint script is one inline <script> wrapped in
                 try/catch, applies every stored preference as a data
                 attribute on <html>, survives bad JSON, an array, an
                 unknown theme and a blocked store, and falls back to the
                 legacy "wr-theme" key. Run for real under node when node
                 is on the PATH (a DOM shim of a dozen lines), statically
                 otherwise.
  [2] CONTROL    the gear opens a native <details> with every group -
                 theme, density, type size, home inbox, quiet - as real
                 radios/checkbox inside labels, plus a reset; the markup is
                 balanced, script-free, and every target is 44px.
  [3] THEME      the signature theme declares EVERY token in ui.TOKEN_NAMES
                 (asserted programmatically), carries no green and no red
                 by hue, meets WCAG AA on every text/surface pair the
                 module promises, and keeps the identity tokens (navy bar,
                 gold fill, chip ink) exactly as ui.py has them.
  [4] NIGHT      the retune stays warm, above 7:1 on every dark surface,
                 and touches no identity token.
  [5] RULES      density and type variables, the quiet-mode rule and its
                 notice hook, no literal colour outside the theme blocks.
  [6] WIRING     ui.css() carries the layer, ui.style_tag() emits the boot
                 script BEFORE <style>, the shell renders the control after
                 the theme toggle and adds no second script.

    .venv/bin/python tests/prefs_test.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import prefs, ui                                 # noqa: E402

FAILURES = []
CHECKS = [0]


def check(cond, label):
    CHECKS[0] += 1
    print("  %s  %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        FAILURES.append(label)
    return bool(cond)


# --- independent colour maths (NOT prefs.py's - the point is to agree) -----

def _rgb(hexstr):
    h = hexstr.strip().lstrip("#")[:6]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(hexstr):
    def lin(c):
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hexstr)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _traffic_light(hexstr):
    """ui_test's hue bands, restated: saturated green 75-170, red <=12/>=345."""
    r, g, b = (c / 255.0 for c in _rgb(hexstr))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return False
    den = 1 - abs(mx + mn - 1)
    sat = d / den if den else 0.0
    if sat < 0.25:
        return False
    if mx == r:
        hue = (60 * ((g - b) / d) + 360) % 360
    elif mx == g:
        hue = 60 * ((b - r) / d) + 120
    else:
        hue = 60 * ((r - g) / d) + 240
    return 75 <= hue <= 170 or hue <= 12 or hue >= 345


def _block(css, selector, start=0):
    i = css.find(selector, start)
    if i < 0:
        return None, -1
    j = css.find("{", i)
    depth, k = 1, j + 1
    while k < len(css) and depth:
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
        k += 1
    return css[j + 1:k - 1], k


def _props(block):
    return dict(re.findall(r"(--[A-Za-z0-9-]+)\s*:\s*([^;]+);", block or ""))


def _rgb_to_hex(value):
    """'rgb(26 23 20)' / 'rgb(0 0 0 / 50%)' -> '#1A1714' / '#00000080'."""
    m = re.match(r"rgb\((\d+)\s+(\d+)\s+(\d+)(?:\s*/\s*(\d+)%)?\)", value.strip())
    if not m:
        return None
    r, g, b = (int(m.group(i)) for i in (1, 2, 3))
    out = "#%02X%02X%02X" % (r, g, b)
    if m.group(4) is not None:
        out += "%02X" % int(round(int(m.group(4)) / 100.0 * 255))
    return out


# --- a balance-checking HTML parser (stdlib) --------------------------------

_VOID = {"input", "br", "img", "hr", "meta", "link", "path", "circle", "rect"}


class _Walk(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack, self.errors, self.elements = [], [], []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append("unexpected </%s> (open: %s)" % (tag, self.stack))
        else:
            self.stack.pop()


def walk(markup):
    w = _Walk()
    w.feed(markup)
    w.close()
    if w.stack:
        w.errors.append("unclosed: %s" % w.stack)
    return w


# --- 1. boot ----------------------------------------------------------------

_NODE_SHIM = r"""
var attrs = {};
var listeners = {};
var store = %(store)s;              // null -> localStorage throws
var root = {
  setAttribute: function (k, v) { attrs[k] = String(v); },
  removeAttribute: function (k) { delete attrs[k]; },
  getAttribute: function (k) { return k in attrs ? attrs[k] : null; },
  hasAttribute: function (k) { return k in attrs; }
};
global.window = global;
global.document = {
  documentElement: root,
  addEventListener: function (n, f) { (listeners[n] = listeners[n] || []).push(f); },
  querySelectorAll: function () { return []; }
};
Object.defineProperty(global, "localStorage", { get: function () {
  if (store === null) throw new Error("blocked");
  return {
    getItem: function (k) { return k in store ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; }
  };
}});
var observers = [];
global.MutationObserver = function (cb) { observers.push(cb); this.observe = function () {}; };
%(boot)s
// a fake form: the reader picks Compact + Larger + Top + Quiet + Broadcast
function fakeForm(values) {
  var f = { inputs: [] };
  f.closest = function (sel) { return sel.indexOf("form") >= 0 ? f : null; };
  f.querySelectorAll = function () { return f.inputs; };
  f.querySelector = function () { return f; };
  f.values = values;
  return f;
}
global.FormData = function (f) { this.get = function (k) { return f.values[k] == null ? null : f.values[k]; }; };
var out = { boot: JSON.parse(JSON.stringify(attrs)), listeners: Object.keys(listeners).sort() };
if (listeners.change) {
  var f = fakeForm({ theme: "broadcast", density: "compact", type: "large", inbox: "top", quiet: "1" });
  listeners.change.forEach(function (h) { h({ target: f }); });
  out.afterChange = JSON.parse(JSON.stringify(attrs));
  if (store !== null) {
    out.stored = JSON.parse(store["wr-prefs"] || "null");
    out.legacy = store["wr-theme"] || null;
  }
  var btn = { closest: function (sel) { return sel.indexOf("reset") >= 0 ? btn : f; } };
  listeners.click.forEach(function (h) { h({ target: btn }); });
  out.afterReset = JSON.parse(JSON.stringify(attrs));
  if (store !== null) out.storeAfterReset = Object.keys(store);
  // the legacy toggle flips data-theme itself; the observer must fold it in
  attrs["data-theme"] = "dark";
  observers.forEach(function (cb) { cb([]); });
  if (store !== null) {
    out.afterObserver = { prefs: JSON.parse(store["wr-prefs"] || "null"), legacy: store["wr-theme"] || null };
  }
}
console.log(JSON.stringify(out));
"""


def _run_boot(store):
    """Execute the boot script under node with `store` as localStorage
    (None = the store throws). Returns the parsed result or None."""
    node = shutil.which("node")
    if not node:
        return None
    src = _NODE_SHIM % {"store": "null" if store is None else json.dumps(store),
                        "boot": prefs.boot_js()}
    p = subprocess.run([node, "-"], input=src.encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if p.returncode != 0:
        print("    node: %s" % p.stderr.decode("utf-8", "replace").strip()[:300])
        return {"error": p.stderr.decode("utf-8", "replace")}
    return json.loads(p.stdout.decode("utf-8").strip().splitlines()[-1])


def test_boot():
    print("\n[1] boot - stored preferences land on <html> before paint")
    tag = prefs.boot_script()
    js = prefs.boot_js()
    check(tag.startswith("<script>") and tag.endswith("</script>")
          and tag.count("<script") == 1,
          "one inline <script>, no src, no type - it runs where it stands")
    check(js.lstrip().startswith("(function(){try{") and js.rstrip().endswith("}catch(e){}})();"),
          "the whole script is one IIFE inside try/catch - a blocked store "
          "or bad JSON leaves the page following the OS")
    check("JSON.parse" in js and "catch" in js.split("JSON.parse", 1)[1][:80],
          "JSON.parse is guarded by its own catch")
    check('"%s"' % prefs.STORAGE_KEY in js and '"%s"' % prefs.LEGACY_THEME_KEY in js,
          "reads %s and falls back to the legacy %s key"
          % (prefs.STORAGE_KEY, prefs.LEGACY_THEME_KEY))
    for attr in prefs.DATA_ATTRS:
        check('"%s"' % attr in js, "sets %s" % attr)
    check("localStorage" in js and "document.documentElement" in js,
          "applies to document.documentElement synchronously - no DOMContentLoaded")
    check("DOMContentLoaded" not in js and "load" not in js.replace("load()", "").replace("function load", ""),
          "nothing waits for an event before the first apply")
    check('"data-theme"' in js and "MutationObserver" in js,
          "a MutationObserver folds the legacy toggle's data-theme flip back "
          "into the preference, so the two never disagree")
    check("</" not in js and "<!--" not in js,
          "the script body contains no '</' or '<!--' that could close or "
          "comment out its own tag")

    if not shutil.which("node"):
        print("  SKIP  node not on PATH - behavioural checks not run "
              "(static checks above still hold)")
        return

    r = _run_boot({"wr-prefs": json.dumps({"theme": "broadcast", "density": "compact",
                                           "type": "large", "inbox": "top",
                                           "quiet": True})})
    b = (r or {}).get("boot") or {}
    check(b.get("data-theme") == "broadcast" and b.get("data-density") == "compact"
          and b.get("data-type") == "large" and b.get("data-inbox") == "top"
          and b.get("data-quiet") == "1",
          "a full stored preference lands as all five attributes (%s)" % b)

    r = _run_boot({"wr-prefs": json.dumps({"theme": "light", "density": "comfortable",
                                           "type": "default", "inbox": "side",
                                           "quiet": False})})
    b = (r or {}).get("boot") or {}
    check(b.get("data-theme") == "light" and "data-density" not in b
          and "data-type" not in b and b.get("data-inbox") == "side"
          and "data-quiet" not in b,
          "the defaults leave density/type/quiet ABSENT and inbox=side (%s)" % b)

    r = _run_boot({"wr-prefs": "{oops"})
    b = (r or {}).get("boot") or {}
    check(r is not None and "error" not in r and "data-theme" not in b
          and b.get("data-inbox") == "side",
          "bad JSON survives: no theme forced, the page follows the OS (%s)" % b)
    for bad in ("[1,2]", "null", "42", '"dark"'):
        r = _run_boot({"wr-prefs": bad})
        b = (r or {}).get("boot") or {}
        check(r is not None and "error" not in r and "data-theme" not in b,
              "a stored %s survives as an empty preference" % bad)

    r = _run_boot({"wr-prefs": json.dumps({"theme": "neon"}), "wr-theme": "dark"})
    b = (r or {}).get("boot") or {}
    check(b.get("data-theme") == "dark",
          "an unknown theme is dropped and the legacy wr-theme key is honoured")
    r = _run_boot({"wr-theme": "light"})
    b = (r or {}).get("boot") or {}
    check(b.get("data-theme") == "light",
          "no preference at all + legacy wr-theme=light -> data-theme=light")
    r = _run_boot({"wr-theme": "broadcast"})
    check(((r or {}).get("boot") or {}).get("data-theme") == "broadcast",
          "a legacy key carrying the signature theme is honoured too")
    r = _run_boot(None) or {}
    check("error" not in r and r.get("boot", {}).get("data-inbox") == "side",
          "a blocked localStorage throws inside its guard, never on the page")
    check(set(r.get("listeners") or []) >= {"change", "click", "toggle", "keydown"},
          "...and the control's handlers are still registered (%s)"
          % r.get("listeners"))
    a = r.get("afterChange") or {}
    check(a.get("data-theme") == "broadcast" and a.get("data-quiet") == "1",
          "...so with storage blocked a change still applies for the session - "
          "only persistence is lost (%s)" % a)

    # the control's handlers, driven through the same script
    r = _run_boot({}) or {}
    a = r.get("afterChange") or {}
    check(a.get("data-theme") == "broadcast" and a.get("data-density") == "compact"
          and a.get("data-type") == "large" and a.get("data-inbox") == "top"
          and a.get("data-quiet") == "1",
          "a change in the form re-applies every attribute at once (%s)" % a)
    st = r.get("stored") or {}
    check(st.get("theme") == "broadcast" and st.get("density") == "compact"
          and st.get("type") == "large" and st.get("inbox") == "top"
          and st.get("quiet") is True,
          "...and stores the JSON under wr-prefs (%s)" % st)
    check(r.get("legacy") == "broadcast",
          "...and writes the same theme to wr-theme, so the legacy toggle "
          "script and this layer agree on load")
    z = r.get("afterReset") or {}
    check("data-theme" not in z and "data-density" not in z and "data-type" not in z
          and "data-quiet" not in z and z.get("data-inbox") == "side",
          "Reset clears every attribute back to the OS defaults (%s)" % z)
    check(r.get("storeAfterReset") == [],
          "...and removes both keys from the store")
    ob = r.get("afterObserver") or {}
    check((ob.get("prefs") or {}).get("theme") == "dark" and ob.get("legacy") == "dark",
          "when the legacy toggle flips data-theme, the observer writes the "
          "theme to BOTH wr-prefs and wr-theme (%s)" % ob)


# --- 2. control -------------------------------------------------------------

def test_control():
    print("\n[2] control - a gear, a native <details>, real form controls")
    m = prefs.control()
    w = walk(m)
    check(not w.errors, "the control's markup is balanced (%s)" % (w.errors or "ok"))
    check("<script" not in m.lower(), "the control is markup only - its handlers "
                                      "ride in the boot script")
    check(m.startswith("<details") and 'data-wr-prefs' in m.split(">", 1)[0],
          "a native <details> carrying the data-wr-prefs hook")
    tags = [(t, a) for t, a in w.elements]
    summ = [a for t, a in tags if t == "summary"]
    check(len(summ) == 1 and summ[0].get("aria-label") == "Preferences"
          and "wr-prefs-s" in summ[0].get("class", ""),
          "one <summary>, labelled Preferences, with the 44px class")
    check("<svg" in m.split("</summary>")[0] and 'aria-hidden="true"' in m.split("</summary>")[0],
          "the gear is an inline svg, decorative beside the label")
    forms = [a for t, a in tags if t == "form"]
    check(len(forms) == 1 and "data-wr-prefs-form" in forms[0],
          "one <form> carrying the data-wr-prefs-form hook")
    check(">Preferences<" in m, "the popover is titled Preferences")

    inputs = [a for t, a in tags if t == "input"]
    by_name = {}
    for a in inputs:
        by_name.setdefault(a.get("name"), []).append(a)
    want = {
        "theme": ("radio", [v for v, _, _ in prefs.THEMES]),
        "density": ("radio", [v for v, _, _ in prefs.DENSITIES]),
        "type": ("radio", [v for v, _, _ in prefs.TYPE_SIZES]),
        "inbox": ("radio", [v for v, _, _ in prefs.INBOX_LAYOUTS]),
        "quiet": ("checkbox", ["1"]),
    }
    for name, (kind, values) in want.items():
        got = by_name.get(name, [])
        check([a.get("value") for a in got] == values
              and all(a.get("type") == kind for a in got),
              "group %r: %s %s %s" % (name, len(values), kind, values))
    check(set(by_name) == set(want), "no other inputs (%s)" % sorted(by_name))
    check([v for v, _, _ in prefs.THEMES] == ["light", "dark", prefs.SIGNATURE_THEME],
          "THEME offers Daylight, Night and the signature theme, in that order")
    for label in ("Daylight", "Night", "Broadcast", "Comfortable", "Compact",
                  "Default", "Larger", "Sidebar", "Top", "Hide unanimous rows"):
        check(">%s<" % label in m, "option %r is labelled in words" % label)
    for legend in ("Theme", "Density", "Type size", "Home inbox", "Quiet mode"):
        check("<legend>%s</legend>" % legend in m, "fieldset %r has a legend" % legend)

    # every input is INSIDE a label with the 44px class
    labels = re.findall(r'<label class="wr-prefs-o">\s*<input[^>]*>', m)
    check(len(labels) == len(inputs) == 10,
          "all %d inputs sit inside a .wr-prefs-o label (%d labels)"
          % (len(inputs), len(labels)))
    reset = [a for t, a in tags if t == "button"]
    check(len(reset) == 1 and reset[0].get("type") == "button"
          and "data-wr-prefs-reset" in reset[0] and ">Reset" in m,
          "a Reset button, type=button so it cannot submit anything")
    check("<a " not in m and "href" not in m,
          "the control navigates nowhere - it is a form, not a menu")

    css = prefs.css()
    opt, _ = _block(css, ".wr-prefs-o {")
    check(opt is not None and re.search(r"min-height:\s*44px", opt or ""),
          "each option label is at least 44px tall")
    gear, _ = _block(css, ".wr-prefs > .wr-prefs-s {")
    check(gear is not None and re.search(r"width:\s*44px", gear or "")
          and re.search(r"height:\s*44px", gear or ""),
          "the gear target is 44 x 44")
    rst, _ = _block(css, ".wr-prefs-r {")
    check(rst is not None and re.search(r"min-height:\s*44px", rst or ""),
          "the Reset button is 44px tall")
    check("accent-color: var(--wr-rule)" in css,
          "the radios and checkbox take the identity gold as their accent")
    check("@media (max-width: 700px)" in css and "position: fixed" in css,
          "on a phone the popover becomes a fixed sheet that cannot overflow")
    pop, _ = _block(css, ".wr-prefs-p {")
    check(pop is not None and "var(--wr-panel)" in pop and "var(--wr-text)" in pop
          and "var(--wr-shadow)" in pop,
          "the popover is painted in tokens: panel, text, shadow")


# --- 3. the signature theme ---------------------------------------------------

def test_signature():
    print("\n[3] theme - %s declares every token, no green, no red, AA"
          % prefs.SIGNATURE_THEME)
    css = prefs.css()
    sel = ':root[data-theme="%s"]' % prefs.SIGNATURE_THEME
    blk, _ = _block(css, sel + " {")
    check(blk is not None, "a %s token block exists" % sel)
    p = _props(blk)
    want = set(ui.TOKEN_PREFIX + n for n in ui.TOKEN_NAMES)
    check(set(p) == want,
          "the block declares EVERY token in ui.TOKEN_NAMES and nothing else "
          "(missing: %s / extra: %s)"
          % (sorted(want - set(p)) or "none", sorted(set(p) - want) or "none"))
    src = prefs.theme_tokens(prefs.SIGNATURE_THEME)
    check(set(src) == set(ui.TOKEN_NAMES),
          "prefs.theme_tokens() carries the same complete set (audited at import)")
    back = {}
    bad_rgb = []
    for k, v in p.items():
        h = _rgb_to_hex(v)
        if h is None:
            bad_rgb.append("%s=%s" % (k, v))
        else:
            back[k[len(ui.TOKEN_PREFIX):]] = h
    check(not bad_rgb, "every emitted value is an rgb() colour (%s)" % (bad_rgb or "ok"))
    diff = [k for k in src if back.get(k, "").upper() != src[k].upper()]
    check(not diff, "the emitted rgb() values round-trip to the hex dict exactly "
                    "(%s)" % (diff or "all"))

    offenders = ["%s=%s" % (k, v) for k, v in sorted(src.items()) if _traffic_light(v)]
    check(not offenders, "no token is a green or a red by hue (%s)"
          % (offenders or "clean"))
    check(prefs.audit(src) == [], "prefs.audit() agrees the theme is clean: %s"
          % (prefs.audit(src) or "clean"))

    for fg, bg, floor in prefs.CONTRAST_PAIRS:
        ratio = _contrast(src[fg], src[bg])
        check(ratio >= floor, "%s on %s = %.2f:1 (needs %.1f)" % (fg, bg, ratio, floor))
    check(_contrast(src["text"], src["canvas"]) >= 12,
          "cream on charcoal is a reading contrast, not a bare pass (%.1f:1)"
          % _contrast(src["text"], src["canvas"]))
    check(set(prefs.CONTRAST_PAIRS) >= {("text", "canvas", 4.5), ("text", "panel", 4.5),
                                        ("gold", "canvas", 3.0), ("gold", "panel", 3.0)},
          "the promised pairs include text/canvas, text/panel at 4.5 and gold at 3")

    light = _props(_block(ui.tokens_css(), ":root {")[0])
    for tok in ("nav", "rule", "chip-start", "chip-ink"):
        check(src[tok].upper() == light[ui.TOKEN_PREFIX + tok].strip().upper(),
              "%s is identical to the identity - the navy bar and the gold fill "
              "are learned once" % tok)
    check(src["canvas"].upper() != light["--wr-canvas"].strip().upper()
          and src["canvas"].upper() != "#0D1730",
          "the ground is neither the paper nor the navy night")
    r, g, b = _rgb(src["canvas"])
    check(r >= g >= b, "the charcoal is WARM (r >= g >= b), not a blue-black")
    r, g, b = _rgb(src["text"])
    check(r >= g >= b, "the ink is a cream (r >= g >= b), not a blue-white")

    # the block sits AFTER ui.py's dark blocks in the shared sheet so that,
    # at equal specificity, it wins under a dark OS as well
    full = ui.css()
    i_layer = full.index(prefs.css())
    i_dark = full.rfind(':root[data-theme="dark"]', 0, i_layer)   # ui.py's own
    i_sig = full.find(sel)
    check(0 <= i_dark < i_sig,
          "the signature block is emitted after ui.py's dark blocks in ui.css()")
    check(("%s body { background-image: url(" % sel) in full and "#" not in full[i_sig:],
          "the grain is a background-image on body under the theme, and no '#' "
          "follows the theme block in the sheet")
    check("feTurbulence" in full and "0.04 0" in full,
          "the grain is monochrome turbulence at 4%% alpha - texture, not tint")


# --- 4. night ----------------------------------------------------------------

def test_night():
    print("\n[4] night - retuned for the hour-long session")
    tune = prefs.night_tune()
    dark = _props(_block(ui.tokens_css(), ':root[data-theme="dark"]')[0])
    dark = dict((k[len(ui.TOKEN_PREFIX):], v.strip()) for k, v in dark.items())
    check(set(tune) <= set(ui.TOKEN_NAMES) and "text" in tune,
          "the tune names real tokens and includes the text tone")
    for tok in ("nav", "nav-text", "rule", "chip-start", "chip-ink", "canvas", "panel"):
        check(tok not in tune, "the tune leaves %s alone - identity and surfaces "
                               "are ui.py's" % tok)
    for k, v in tune.items():
        check(not _traffic_light(v), "night %s=%s is not a green or a red" % (k, v))
    for surf in ("canvas", "panel", "raised"):
        ratio = _contrast(tune["text"], dark[surf])
        check(ratio >= 7.0, "night text on %s = %.2f:1 (>= 7)" % (surf, ratio))
    old = _contrast(dark["text"], dark["canvas"])
    new = _contrast(tune["text"], dark["canvas"])
    check(new < old, "peak contrast eased: %.1f:1 -> %.1f:1" % (old, new))
    r, g, b = _rgb(tune["text"])
    r0, g0, b0 = _rgb(dark["text"])
    check((r - b) > (r0 - b0), "the text is WARMER than ui.py's cool white")
    if "muted" in tune:
        ratio = _contrast(tune["muted"], dark["panel"])
        check(ratio >= 4.5, "night muted on panel = %.2f:1 (>= 4.5)" % ratio)

    css = prefs.css()
    media, m_end = _block(css, "@media (prefers-color-scheme: dark)")
    guard = ':root:not([data-theme="light"]):not([data-theme="%s"])' % prefs.SIGNATURE_THEME
    sysblk, _ = _block(media or "", guard)
    expblk, _ = _block(css, ':root[data-theme="dark"]')
    check(sysblk is not None, "the tune is applied under prefers-dark, guarded so "
                              "an explicit light OR the signature theme is left alone")
    check(expblk is not None, "and under the explicit data-theme=dark")
    ps, pe = _props(sysblk), _props(expblk)
    check(ps == pe and set(ps) == set(ui.TOKEN_PREFIX + k for k in tune),
          "both dark states restate exactly the tuned tokens, identically")
    back = dict((k[len(ui.TOKEN_PREFIX):], _rgb_to_hex(v)) for k, v in pe.items())
    check(all(back[k].upper() == tune[k].upper() for k in tune),
          "the emitted values round-trip to the tune")


# --- 5. rules ------------------------------------------------------------------

def test_rules():
    print("\n[5] rules - density, type, quiet, and no colour outside the themes")
    css = prefs.css()
    dflt, _ = _block(css, ":where(:root) {")
    check(dflt is not None, "defaults are declared at ZERO specificity "
                            "(:where(:root)) so ui.py's own :root values win")
    pd = _props(dflt)
    for var, val in prefs.DENSITY_VARS["comfortable"].items():
        check(pd.get(var, "").strip() == val, "%s defaults to %s" % (var, val))
    cmp_, _ = _block(css, 'html[data-density="compact"]')
    pc = _props(cmp_)
    for var, val in prefs.DENSITY_VARS["compact"].items():
        check(pc.get(var, "").strip() == val, "compact sets %s to %s" % (var, val))
    check(float(pd["--wr-row-h"].rstrip("px")) >= 44,
          "the comfortable row is a 44px target - never crowded")
    check(float(pc["--wr-row-h"].rstrip("px")) >= 32,
          "the compact row is still 32px or more - denser, not tiny")
    row, _ = _block(css, ".wr-row {")
    check(row is not None and "var(--wr-row-h)" in row and "var(--wr-pad)" in row,
          ".wr-row keys its min-height and padding on the variables")
    check(re.search(r"\.wr-table td \{[^}]*var\(--wr-pad\)", css),
          "table cells follow the density too")

    # type scale: every step, default and large, large ~1.1x
    for sec_sel in (":where(:root) {",):
        pass
    p_all = {}
    pos = 0
    while True:
        blk, pos = _block(css, ":where(:root) {", pos)
        if blk is None:
            break
        p_all.update(_props(blk))
    large, _ = _block(css, 'html[data-type="large"]')
    pl = _props(large)
    for var in prefs.TYPE_SCALE_NAMES:
        d = p_all.get(var, "").strip()
        lg = pl.get(var, "").strip()
        check(d.endswith("px") and lg.endswith("px"), "%s is declared in both steps" % var)
        if d.endswith("px") and lg.endswith("px"):
            ratio = float(lg[:-2]) / float(d[:-2])
            check(1.08 <= ratio <= 1.12, "%s large is ~1.1x default (%.3f)" % (var, ratio))
    check(float(p_all["--wr-t4"].rstrip("px")) >= 11,
          "the floor step is 11px or more, in both sizes")
    check("body { font-size: var(--wr-t2); }" in css and ".wr-h1 { font-size: var(--wr-t0); }" in css,
          "body and the h1 read their size from the scale, so Larger reaches "
          "every page")
    for cls in ("wr-t1", "wr-t2", "wr-t3", "wr-t4"):
        check(".%s { font-size: var(--%s); }" % (cls, cls) in css,
              ".%s utility class exists" % cls)
    sizes = re.findall(r"font-size:\s*([^;]+);", css)
    literal = [s for s in sizes if "var(--wr-t" not in s]
    check(not literal, "every font-size in the layer is a scale token (%s)"
          % (literal or "all tokens"))

    check('html[data-quiet="1"] [data-unanimous="1"] { display: none !important; }' in css,
          "the quiet rule hides exactly [data-unanimous=\"1\"] under data-quiet")
    note, _ = _block(css, ".wr-quiet-note {")
    check(note is not None and re.search(r"display:\s*none", note),
          ".wr-quiet-note is hidden by default")
    check(re.search(r'html\[data-quiet="1"\] \.wr-quiet-note \{\s*display:\s*flex', css),
          "...and shown when quiet mode is on")
    check("data-unanimous" not in prefs.control() and "data-unanimous" not in prefs.boot_js(),
          "nothing in this layer SETS data-unanimous - only a page may, on a "
          "row with no decision (the honesty contract)")
    doc = prefs.__doc__ or ""
    check("never hide a decision" in doc and "data-unanimous" in doc,
          "the contract is written down in the module docstring")

    # no colour outside the theme blocks
    stripped = css
    pos = 0
    for sel in (':root[data-theme="%s"] {' % prefs.SIGNATURE_THEME,
                ':root:not([data-theme="light"]):not([data-theme="%s"])' % prefs.SIGNATURE_THEME,
                ':root[data-theme="dark"]'):
        blk, _ = _block(stripped, sel)
        if blk:
            stripped = stripped.replace(blk, "")
    check("#" not in stripped and "rgb(" not in stripped and "hsl(" not in stripped,
          "no literal colour of any notation outside the theme blocks")
    values = " ".join(re.findall(r":\s*([^;{}]+)[;}]", stripped))
    values = re.sub(r"var\(--[A-Za-z0-9-]+\)", " ", values)
    names = re.findall(r"\b(white|black|red|green|blue|gray|grey|yellow|orange|navy|gold)\b",
                       values)
    check(not names, "no named colour either (%s)" % (sorted(set(names)) or "none"))
    check("<script" not in css and "</style" not in css,
          "the stylesheet carries no script and cannot close its own tag")


# --- 6. wiring -----------------------------------------------------------------

def test_wiring():
    print("\n[6] wiring - the three hooks in ui.py are live")
    full = ui.css()
    check(prefs.css() in full and full.endswith(prefs.css()),
          "ui.css() ends with prefs.css() - the layer is last, so it wins ties")
    tag = ui.style_tag()
    check(tag.startswith(prefs.boot_script()) and tag.index("<style>") > 0,
          "ui.style_tag() emits the boot script BEFORE <style> - pre-paint")
    shell = ui.shell("home", leagues=[("l1", "League One")])
    check(prefs.control() in shell, "the shell renders the control")
    check(shell.index('data-wr-theme') < shell.index('data-wr-prefs'),
          "...next to and after the theme toggle")
    check(shell.count("<script") == 1,
          "the control adds no script of its own to the shell (count=%d)"
          % shell.count("<script"))

    n = prefs.quiet_note(3)
    w = walk(n)
    check(not w.errors and 'class="wr-quiet-note"' in n and ">3<" in n
          and "Quiet mode" in n and "Preferences" in n,
          "quiet_note(3) is one balanced line naming the count and the way back")
    check(prefs.quiet_note(0) == "" and prefs.quiet_note("x") == "",
          "quiet_note renders nothing for zero or nonsense - no empty box")
    hostile = "<b>rows</b>&\"'"
    h = prefs.quiet_note(2, hostile)
    check("<b>rows</b>" not in h and "&lt;b&gt;" in h,
          "the `what` word is escaped")

    src = open(os.path.join(HERE, "engine", "prefs.py"), "r").read()
    for bad in ("open(", "os.remove", "shutil.", "urllib", "requests",
                "subprocess", "pandas", "yaml"):
        check(bad not in src, "engine/prefs.py contains no %r - presentation only" % bad)
    check(re.search(r"^from engine import ui$", src, re.M) and "import typing" not in src.replace("from typing", ""),
          "prefs imports ui and the standard library only")


def main():
    print("PREFERENCES ACCEPTANCE TEST")
    test_boot()
    test_control()
    test_signature()
    test_night()
    test_rules()
    test_wiring()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d of %d FAILURE(S):" % (len(FAILURES), CHECKS[0])))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
