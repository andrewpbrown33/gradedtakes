#!/usr/bin/env python3
"""Acceptance test: the shared design system (engine/ui.py).

engine/ui.py is PURE PRESENTATION - it reads no files, fetches nothing and
writes nothing, so this suite needs no fixture root and cannot touch the
user's rosters, saves, leagues or source registry. It asserts the four
contracts that let three different pages share one vocabulary:

  [1] ICONS      every icon is a single-root, well-formed SVG on the 24-grid
                 that strokes in currentColor and carries the right a11y
                 attributes - role="img" + <title> when titled, aria-hidden
                 when decorative. No child may hardcode a colour, or the
                 icon stops inheriting the semantic colour of its chip.
  [2] TOKENS     every token is declared in ALL THREE theme states, and no
                 colour exists ONLY inside a media query or a [data-theme]
                 block. Every hex in the whole stylesheet lives in a token
                 block; component rules reference var(--wr-*) and nothing
                 else.
  [3] ESCAPING   a hostile string through every text-taking component comes
                 out inert - and the surrounding markup stays well-formed,
                 which is the check that catches an attribute break that a
                 substring search would miss.
  [4] SPARKLINE  empty, one-point and flat series all render without a
                 division by zero. All three arrive in real use during a
                 week 1 with an empty ledger, which is exactly today.

  [5] LEGIBILITY no two icons share a silhouette, and every icon carries a
                 written note saying what distinguishes it at 20px.
  [8] TYPE SCALE every font-size the module emits is a scale token or a
                 scale number, and nothing is ever set under 11px.
  [9] V4         the League-Legend components (status pill, news dot,
                 trend arrow, opp chip, score cell, legend popover, sheet,
                 segmented control, three-column row, title switcher)
                 render valid markup, escape hostile text, carry their
                 a11y attributes, and every glyph carries a hover title.
  [10] BRAND     the wordmark is the product name, GRADED TAKES - the
                 working title "War Room" never reaches a reader.
  [11] APP MODE  <html data-app="ios"> hides the shell's header and tab
                 bar (and only those), releases the padding they reserved,
                 keeps every token block and the hue rule intact, and the
                 page's scripts leave the app's data-theme alone.

    .venv/bin/python tests/ui_test.py
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import ui                                        # noqa: E402

FAILURES = []
CHECKS = [0]

SVG_NS = "{http://www.w3.org/2000/svg}"

# One string carrying every way markup breaks: tag injection, an attribute
# break with a double quote, a single quote, a bare ampersand, and a
# premature close of the element the value sits inside.
HOSTILE = "<script>alert(\"xss\")</script> & 'q' </span> --> é"


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def parse_one(markup, label):
    """Parse a fragment and return its single root element.

    ElementTree raises on a second root, on an unquoted attribute and on a
    bare `&` - so a clean parse is simultaneously the single-root check and
    the well-formedness check.
    """
    try:
        return ET.fromstring(markup)
    except ET.ParseError as exc:
        check(False, "%s parses as well-formed XML (%s)" % (label, exc))
        return None


# --- 1. icons ---------------------------------------------------------------

# The concepts the board, the digest and the roster page all have to speak.
REQUIRED_ICONS = {
    # the original vocabulary
    "start", "sit", "toss_up", "hot_streak", "cold_streak", "injury", "bye",
    "matchup_smash", "matchup_avoid", "waiver_add", "drop", "trade",
    "dissent", "consensus", "locked", "news", "expand",
    # v4: the League-Legend row and the chrome around it
    "trend_up", "trend_down", "info", "settings", "sheet_handle", "wall",
    "calendar", "clock", "search", "close",
}


def test_icons():
    print("\n[1] icons - single-root SVG, currentColor, a11y attributes")

    check(set(ui.icon_names()) == REQUIRED_ICONS,
          "the set is exactly the %d concepts the pages need (missing: %s / "
          "extra: %s)"
          % (len(REQUIRED_ICONS),
             sorted(REQUIRED_ICONS - set(ui.icon_names())) or "none",
             sorted(set(ui.icon_names()) - REQUIRED_ICONS) or "none"))

    bad_root, bad_stroke, bad_fill, bad_box, bad_size = [], [], [], [], []
    hardcoded, empty_body, out_of_grid = [], [], []

    for name in ui.icon_names():
        for size in ui.ICON_SIZES:
            markup = ui.icon(name, size)
            root = parse_one(markup, "icon %r @%d" % (name, size))
            if root is None:
                bad_root.append(name)
                continue
            if root.tag != SVG_NS + "svg":
                bad_root.append(name)
            if root.get("stroke") != "currentColor":
                bad_stroke.append(name)
            if root.get("fill") != "none":
                bad_fill.append(name)
            if root.get("viewBox") != "0 0 24 24":
                bad_box.append(name)
            if (root.get("width") != str(size)
                    or root.get("height") != str(size)):
                bad_size.append("%s@%d" % (name, size))
            kids = list(root)
            if not kids:
                empty_body.append(name)
            for el in root.iter():
                if el is root:
                    continue
                for attr in ("fill", "stroke", "color"):
                    val = (el.get(attr) or "").strip()
                    if val and val not in ("none", "currentColor"):
                        hardcoded.append("%s/%s=%s" % (name, attr, val))
            # loose grid sanity: catch a 220 typed for a 22
            for num in re.findall(r"-?\d+(?:\.\d+)?",
                                  " ".join((el.get("d") or "")
                                           for el in root.iter())):
                if not -24.0 <= float(num) <= 30.0:
                    out_of_grid.append("%s:%s" % (name, num))

    check(not bad_root, "every icon is one well-formed <svg> root (%s)"
          % (sorted(set(bad_root)) or "all clean"))
    check(not bad_stroke, "every icon strokes in currentColor (%s)"
          % (sorted(set(bad_stroke)) or "all clean"))
    check(not bad_fill, "every icon root sets fill=\"none\" - stroke-based, "
          "not filled (%s)" % (sorted(set(bad_fill)) or "all clean"))
    check(not hardcoded,
          "no child hardcodes a colour, so an icon inside a mint chip comes "
          "out mint (%s)" % (sorted(set(hardcoded)) or "all clean"))
    check(not bad_box, "every icon is drawn on the same 0 0 24 24 grid (%s)"
          % (sorted(set(bad_box)) or "all clean"))
    check(not bad_size, "width/height match the requested size (%s)"
          % (sorted(set(bad_size)) or "all clean"))
    check(not empty_body, "no icon renders an empty <svg> (%s)"
          % (sorted(set(empty_body)) or "all clean"))
    check(not out_of_grid, "no path number escapes the grid (%s)"
          % (sorted(set(out_of_grid))[:4] or "all clean"))

    # --- a11y: titled vs decorative ---------------------------------------
    titled = ui.icon("hot_streak", 20, title="on a hot streak")
    root = parse_one(titled, "titled icon")
    check(root is not None and root.get("role") == "img",
          "a titled icon is role=\"img\"")
    check(root is not None
          and [e.tag for e in root].count(SVG_NS + "title") == 1
          and (root.find(SVG_NS + "title").text == "on a hot streak"),
          "a titled icon carries exactly one <title> with the given text")
    check(root is not None and root.get("aria-hidden") is None,
          "a titled icon is NOT aria-hidden - it is a labelled image")

    plain = ui.icon("hot_streak", 20)
    root = parse_one(plain, "decorative icon")
    check(root is not None and root.get("aria-hidden") == "true",
          "an untitled icon is aria-hidden - decoration beside text that "
          "already says it")
    check(root is not None and root.get("focusable") == "false",
          "an untitled icon is focusable=\"false\" (legacy IE/Edge tab trap)")
    check(root is not None and root.find(SVG_NS + "title") is None,
          "an untitled icon carries no <title>")
    check(root is not None and root.get("role") is None,
          "an untitled icon claims no role")

    # --- optical weight ----------------------------------------------------
    w20 = float(parse_one(ui.icon("start", 20), "s20").get("stroke-width"))
    w24 = float(parse_one(ui.icon("start", 24), "s24").get("stroke-width"))
    check(w20 > w24,
          "the 20px render carries a heavier grid stroke than the 24px one, "
          "so optical weight stays constant (%.2f vs %.2f)" % (w20, w24))
    check(abs(w20 * 20 / 24.0 - w24 * 24 / 24.0) < 0.02,
          "both sizes land on the same device-pixel stroke")

    # --- error behaviour ---------------------------------------------------
    try:
        ui.icon("no_such_icon")
        raised = False
    except KeyError:
        raised = True
    check(raised, "an unknown icon name raises instead of rendering a blank")

    try:
        ui.icon("start", 400)
        raised = False
    except ValueError:
        raised = True
    check(raised, "an absurd size raises instead of rendering mush")

    # --- position badges are typographic, not pictograms -------------------
    for pos in ui.POSITIONS:
        markup = ui.pos_badge(pos)
        root = parse_one(markup, "pos_badge(%r)" % pos)
        check(root is not None and "<svg" not in markup
              and (root.text or "") == pos,
              "%s renders as a typographic chip, no pictogram" % pos)
    check(ui.normalize_pos("D/ST") == "DST" and ui.normalize_pos("def")
          == "DST", "DEF and D/ST both normalise onto the DST chip")


def test_distinct():
    print("\n[5] legibility - no two icons share a silhouette")
    bodies, notes = {}, {}
    dupe_body, dupe_note, no_note = [], [], []
    for name in ui.icon_names():
        body = re.sub(r"\s+", " ", ui._ICONS[name][0]).strip()
        note = " ".join(ui.ICON_NOTES[name].split()).lower()
        if body in bodies:
            dupe_body.append("%s == %s" % (name, bodies[body]))
        bodies[body] = name
        if note in notes:
            dupe_note.append("%s == %s" % (name, notes[note]))
        notes[note] = name
        if len(note) < 30:
            no_note.append(name)
    check(not dupe_body, "no two icons draw the same geometry (%s)"
          % (dupe_body or "all distinct"))
    check(not dupe_note, "no two icons describe the same silhouette (%s)"
          % (dupe_note or "all distinct"))
    check(not no_note,
          "every icon carries a written note of what makes it readable at "
          "20px (%s)" % (no_note or "all documented"))

    # The set's near-miss pairs, checked as a standing guard: each was
    # deliberately built out of a DIFFERENT primitive so it cannot collapse
    # into its neighbour at 20px. Element-type mix is the cheap proxy.
    def shapes(name):
        root = parse_one(ui.icon(name, 20), name)
        return tuple(sorted(e.tag.replace(SVG_NS, "") for e in root))

    for a, b in (("waiver_add", "toss_up"), ("consensus", "dissent"),
                 ("matchup_avoid", "drop"), ("matchup_avoid", "locked"),
                 ("hot_streak", "bye"), ("start", "expand"),
                 ("injury", "matchup_smash"), ("sit", "trade"),
                 ("sit", "toss_up"), ("news", "hot_streak"),
                 ("dissent", "trade"), ("start", "toss_up"),
                 ("waiver_add", "consensus"), ("news", "locked"),
                 # v4 near-misses
                 ("waiver_add", "drop"), ("waiver_add", "injury"),
                 ("info", "clock"), ("search", "info"), ("settings", "consensus"),
                 ("wall", "matchup_avoid"), ("wall", "calendar"),
                 ("calendar", "locked"), ("trend_up", "trend_down"),
                 ("trend_up", "dissent"), ("close", "cold_streak"),
                 ("news", "trend_up"), ("sheet_handle", "drop"),
                 ("sheet_handle", "sit")):
        check(shapes(a) != shapes(b) or ui._ICONS[a][0] != ui._ICONS[b][0],
              "%s and %s are built from different forms" % (a, b))

    # A RING IS TOLD BY ITS INTERIOR. The ring family (one circle) is
    # allowed to grow, but no two members may share the strokes that sit
    # with the ring, because at 20px the ring is the same shape every time
    # and the interior is the whole message. Two-ring forms stay unique.
    ring_counts, interiors, dupe_interior = {}, {}, []
    for name in ui.icon_names():
        root = parse_one(ui.icon(name, 20), name)
        rings = [e for e in root if e.tag in (SVG_NS + "circle",
                                              SVG_NS + "ellipse")]
        if not rings:
            continue
        ring_counts.setdefault(len(rings), []).append(name)
        rest = tuple(sorted(re.sub(r"\s+", " ", (e.get("d") or "")).strip()
                            for e in root if e not in rings))
        if rest in interiors:
            dupe_interior.append("%s == %s" % (name, interiors[rest]))
        interiors[rest] = name
    check(not dupe_interior,
          "no two ring glyphs share an interior - the ring family is told "
          "apart by what sits inside (%s)" % (dupe_interior or "all distinct"))
    check(len(ring_counts.get(2, [])) <= 2
          and "consensus" in ring_counts.get(2, []),
          "consensus is the interlocked two-ring form; the only other "
          "two-circle glyph is the concentric gear hub (%s)"
          % {k: v for k, v in ring_counts.items()})
    check(all(len(ui._ICONS[n][0]) for n in ring_counts.get(1, []))
          and all(interiors[k] for k in interiors if k),
          "every single-ring glyph carries strokes beside its ring - a bare "
          "ring would be the one shape with no message")


# --- 2. tokens --------------------------------------------------------------

def _block(css, selector, start=0):
    """Return the text inside the braces that follow `selector`.

    The brace is searched from the START of the match, not from its end:
    some selectors here are written WITH their opening brace (":root {") to
    tell them apart from their longer neighbours (":root:not(...)"), and
    scanning from the end of such a selector walks straight past its own
    brace into the next block.
    """
    i = css.find(selector, start)
    if i < 0:
        return None, -1
    j = css.find("{", i)
    if j < 0:
        return None, -1
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


def test_tokens():
    print("\n[2] tokens - declared in all three theme states")
    css = ui.css()

    light, _ = _block(css, ":root {")
    media, media_end = _block(css, "@media (prefers-color-scheme: dark)")
    sysdark, _ = _block(media or "", ':root:not([data-theme="light"])')
    explicit, _ = _block(css, ':root[data-theme="dark"]')

    check(light is not None, "a bare :root block exists (the light theme)")
    check(media is not None, "a prefers-color-scheme: dark media query exists")
    check(sysdark is not None,
          "system dark is guarded by :root:not([data-theme=\"light\"]) so an "
          "explicit light choice wins over the OS")
    check(explicit is not None,
          "an explicit :root[data-theme=\"dark\"] block exists so the toggle "
          "wins in both directions")

    want = set(ui.TOKEN_PREFIX + n for n in ui.TOKEN_NAMES)
    p_light = _props(light)
    p_sys = _props(sysdark)
    p_exp = _props(explicit)

    have_light = set(k for k in p_light if k.startswith(ui.TOKEN_PREFIX))
    check(have_light == want,
          "bare :root declares every token (missing: %s)"
          % (sorted(want - have_light) or "none"))
    check(set(p_sys) == want,
          "the system-dark block declares every token (missing: %s)"
          % (sorted(want - set(p_sys)) or "none"))
    check(set(p_exp) == want,
          "the explicit-dark block declares every token (missing: %s)"
          % (sorted(want - set(p_exp)) or "none"))

    # THE headline invariant: nothing may exist only in a dark block.
    only_dark = (set(p_sys) | set(p_exp)) - have_light
    check(not only_dark,
          "no colour is defined ONLY inside a media/[data-theme] block - "
          "every one has a bare :root definition (%s)"
          % (sorted(only_dark) or "none"))
    check(p_sys == p_exp,
          "the two dark blocks are value-for-value identical, so the OS "
          "theme and the explicit toggle can never disagree")

    # Aliases carry no colour of their own; they point at tokens, which is
    # why they follow the theme without being restated three times.
    aliases = dict((k, v) for k, v in p_light.items()
                   if not k.startswith(ui.TOKEN_PREFIX))
    check(aliases, "compatibility aliases for existing board/digest markup "
                   "are declared")
    check(all(v.strip().startswith("var(" + ui.TOKEN_PREFIX)
              for v in aliases.values()),
          "every alias is a var() reference, never a second copy of a hex")

    # Every hex in the WHOLE stylesheet must live in a token block.
    stripped = css
    for blk in (light, sysdark, explicit):
        if blk:
            stripped = stripped.replace(blk, "")
    strays = re.findall(r"#[0-9A-Fa-f]{3,8}\b", stripped)
    check(not strays,
          "no hex colour appears outside a token block - component rules "
          "reference var(--wr-*) and nothing else (%s)"
          % (sorted(set(strays)) or "none"))

    # Named colours are scanned on the VALUE side only, with var() refs
    # removed: "white-space: nowrap" is a property name and "var(--wr-gold)"
    # is a token reference - neither is a literal colour.
    values = " ".join(re.findall(r":\s*([^;{}]+)[;}]", stripped))
    values = re.sub(r"var\(--[A-Za-z0-9-]+\)", " ", values)
    names = re.findall(
        r"\b(white|black|red|green|blue|gray|grey|yellow|orange|navy|gold)\b",
        values)
    check(not names,
          "no named CSS colour sneaks past the tokens either (%s)"
          % (sorted(set(names)) or "none"))
    check("currentColor" in ui.icon("start", 20) and "#" not in values,
          "component values carry no literal colour at all - only tokens "
          "and currentColor")

    check(re.search(r"body\s*\{[^}]*background:\s*var\(--wr-canvas\)", css),
          "body sets an explicit token background, so the page never "
          "borrows the host's theme through a transparent body")
    check("color-scheme: light dark" in css,
          "color-scheme is declared so form controls and scrollbars follow")

    # v3: the identity is LIGHT paper + navy ink + one gold accent; dark is
    # the same identity inverted. The verdict FILL is learned once.
    for tok in ("chip-start", "chip-ink", "rule", "nav", "nav-text"):
        key = ui.TOKEN_PREFIX + tok
        check(p_light[key].strip() == p_sys[key].strip(),
              "%s is identical light and dark - the gold fill, the navy "
              "bar and the identity gold are learned once" % tok)
    for tok in ("chip-sit", "chip-lean"):
        key = ui.TOKEN_PREFIX + tok
        check(p_light[key].strip() != p_sys[key].strip(),
              "%s follows the theme - a ghost border and a dashed outline "
              "must sit on their own canvas" % tok)

    check(p_light[ui.TOKEN_PREFIX + "canvas"].strip().upper() == "#F4F2EC"
          and p_light[ui.TOKEN_PREFIX + "panel"].strip().upper() == "#FFFFFF",
          "light canvas is the warm paper and panels are white")
    check(p_sys[ui.TOKEN_PREFIX + "canvas"].strip().upper() == "#0D1730",
          "dark canvas is the deep navy")
    check(p_light[ui.TOKEN_PREFIX + "text"].strip().upper() == "#101B33",
          "light mode keeps the identity by making the navy the INK")
    check(p_light[ui.TOKEN_PREFIX + "rule"].strip().upper() == "#F2B722"
          and p_sys[ui.TOKEN_PREFIX + "chip-start"].strip().upper() == "#F2B722",
          "the accent is the one gold, and START is a gold fill")

    # THE RULE THAT DEFINES v3: no green and no red anywhere in the system.
    # Verdicts are weight (fill / ghost / dash), attention is a gold rule.
    def _hue_sat(hexstr):
        h = hexstr.strip().lstrip("#")
        if len(h) == 8:
            h = h[:6]
        if len(h) != 6:
            return None
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        d = mx - mn
        if d == 0:
            return (0.0, 0.0)
        sat = d / (1 - abs(mx + mn - 1)) if (1 - abs(mx + mn - 1)) else 0.0
        if mx == r:
            hue = (60 * ((g - b) / d) + 360) % 360
        elif mx == g:
            hue = 60 * ((b - r) / d) + 120
        else:
            hue = 60 * ((r - g) / d) + 240
        return (hue, sat)

    offenders = []
    for palette_name, pal in (("light", p_light), ("dark", p_sys)):
        for key, val in pal.items():
            hs = _hue_sat(val)
            if not hs:
                continue
            hue, sat = hs
            if sat < 0.25:
                continue
            if 75 <= hue <= 170 or hue <= 12 or hue >= 345:
                offenders.append("%s:%s=%s" % (palette_name, key, val.strip()))
    check(not offenders,
          "no token is a green or a red in either theme - verdicts are "
          "encoded by weight, never by traffic-light hue (%s)"
          % (offenders or "clean"))


# --- 3. escaping ------------------------------------------------------------

def test_escaping():
    print("\n[3] escaping - a hostile string stays inert everywhere")

    # Components that pass the caller's text THROUGH to the page. These must
    # render the whole string, escaped byte for byte.
    echoing = [
        ("esc", ui.esc(HOSTILE)),
        ("icon title", ui.icon("start", 20, title=HOSTILE)),
        ("verdict_chip title", ui.verdict_chip("start", 62, title=HOSTILE)),
        ("stat_pill", ui.stat_pill(HOSTILE, HOSTILE, title=HOSTILE)),
        ("flag_badge note", ui.flag_badge("injury", note=HOSTILE)),
        ("sparkline title", ui.sparkline([1, 2, 3], title=HOSTILE)),
        ("section_header", ui.section_header(HOSTILE, HOSTILE, [HOSTILE])),
        ("banner", ui.banner(HOSTILE)),
        ("degraded_banner", ui.degraded_banner(HOSTILE,
                                               ValueError(HOSTILE))),
        ("degraded_banner str", ui.degraded_banner(HOSTILE, HOSTILE)),
        ("legend", ui.legend([("consensus", HOSTILE)])),
        ("player_row name", ui.player_row(HOSTILE, pos="WR", team=HOSTILE,
                                          note=HOSTILE)),
        # v4
        ("status_pill note", ui.status_pill("Q", note=HOSTILE)),
        ("news_dot title", ui.news_dot(True, title=HOSTILE)),
        ("trend_arrow title", ui.trend_arrow("up", 12, title=HOSTILE)),
        ("opp_chip title", ui.opp_chip("KC", "good", title=HOSTILE)),
        ("score_cell title", ui.score_cell(1.0, title=HOSTILE)),
        ("score_cell details title", ui.score_cell(1.0, 2.0, "<i>b</i>",
                                                   title=HOSTILE)),
        ("legend_popover label", ui.legend_popover([("start", HOSTILE)],
                                                   label=HOSTILE)),
        ("sheet title", ui.sheet("s1", HOSTILE, "<p>b</p>")),
        ("segmented", ui.segmented(HOSTILE, [("a", HOSTILE, "#a"),
                                             ("b", HOSTILE)], "a")),
        ("row3_identity", ui.row3_identity(HOSTILE, "WR", HOSTILE)),
        ("shell title", re.search(
            r'<details class="wr-lgsw">.*?</details>',
            ui.shell("home", leagues=[("l1", HOSTILE)], title=HOSTILE)
        ).group(0)),
    ]
    # Components with a CLOSED vocabulary. An unrecognised value is not
    # echoed at all - which is a stronger guarantee than escaping, and the
    # right one: the page must not repeat a string a feed made up.
    closed = [
        ("verdict_chip verdict", ui.verdict_chip(HOSTILE)),
        ("streak_badge", ui.streak_badge(HOSTILE)),
        ("matchup_badge", ui.matchup_badge(HOSTILE)),
        ("trend_arrow direction", ui.trend_arrow(HOSTILE, HOSTILE)),
        ("opp_chip grade", ui.opp_chip("KC", HOSTILE)),
    ]
    # A chip that renders an unknown code, but cut to chip length first.
    trunc = [("pos_badge", ui.pos_badge(HOSTILE)),
             ("opp_chip opponent", ui.opp_chip(HOSTILE, "neutral"))]

    for label, markup in echoing + closed + trunc:
        check("<script" not in markup,
              "%s: the injected tag is not emitted raw" % label)
        check('alert("xss")' not in markup,
              "%s: the attribute-breaking quote does not survive" % label)
        # A clean parse proves no attribute or element boundary was broken -
        # the failure a substring search misses.
        parse_one("<div>%s</div>" % markup, "%s output" % label)

    for label, markup in echoing:
        check(ui.esc(HOSTILE) in markup,
              "%s: the whole string is echoed, escaped byte for byte" % label)

    for label, markup in closed:
        check("script" not in markup.lower() and "xss" not in markup.lower(),
              "%s: an unrecognised value is dropped, not echoed - a closed "
              "vocabulary never repeats what a feed invented" % label)

    for label, markup in trunc:
        check("&lt;" in markup and "<" not in markup.replace("<span", "")
              .replace("</span", ""),
              "%s: an unknown code is escaped before it is printed" % label)
        root = ET.fromstring(markup)
        code = root.find(".//*[@class='wr-opp-c']")
        text = (code.text if code is not None else root.text) or ""
        check(len(text) <= 6,
              "%s: and cut to chip length - a feed does not get to set the "
              "column width" % label)

    # A quote inside an attribute is the case a substring search misses.
    chip = ui.verdict_chip("sit", 91, title='he "sits" & that is that')
    root = parse_one("<div>%s</div>" % chip, "quoted title")
    span = root.find("span") if root is not None else None
    check(span is not None and span.get("title") == 'he "sits" & that is that',
          "an attribute round-trips through escaping byte for byte")

    # A real creator quote with the punctuation feeds actually carry.
    quote = ui.stat_pill("QUOTE", "O'Dell & \"the guy\" <3 <b>bold</b>")
    parse_one("<div>%s</div>" % quote, "creator quote")
    check("<b>" not in quote, "a quote's markup is neutralised, not rendered")

    # Full-page composition still parses.
    page = ("<div>%s%s%s%s</div>"
            % (ui.section_header("Divergence", "3 rows", ["one", "two"]),
               ui.player_row("Ja'Marr Chase", "WR", "CIN",
                             note="top-weighted dissent",
                             badges=[ui.streak_badge("hot"),
                                     ui.matchup_badge("smash")],
                             trailing_html=ui.verdict_chip("start", 78),
                             locked=True),
               ui.popover("<b>%s</b>" % ui.esc(HOSTILE),
                          "<p>%s</p>" % ui.esc(HOSTILE)),
               ui.legend()))
    parse_one(page, "composed page fragment")
    check("<script>" not in page, "the composed fragment carries no raw tag")
    check(ui.esc(HOSTILE) in page,
          "popover's trusted-HTML slots render what the caller escaped")


# --- 4. sparkline -----------------------------------------------------------

def _spark_points(markup, cls):
    root = parse_one(markup, "sparkline")
    if root is None:
        return []
    out = []
    for el in root.iter():
        if cls in (el.get("class") or ""):
            nums = [float(n) for n in
                    re.findall(r"-?\d+(?:\.\d+)?", el.get("d") or "")]
            out.append(list(zip(nums[0::2], nums[1::2])))
    return out


def test_sparkline():
    print("\n[4] sparkline - degenerate series, no division by zero")

    for label, series in (("None", None), ("empty list", []),
                          ("all junk", ["x", None, "", {}]),
                          ("all non-finite", [float("nan"),
                                              float("inf")])):
        markup = ui.sparkline(series)
        parse_one(markup, "sparkline(%s)" % label)
        check("wr-spark-empty" in markup,
              "%s renders the EMPTY baseline, not a flat line at zero - an "
              "empty series is drawn as empty" % label)
        check("wr-spark-line" not in markup,
              "%s draws no trend line it cannot support" % label)

    one = ui.sparkline([14.6])
    parse_one(one, "one-point sparkline")
    check("wr-spark-dot" in one and "wr-spark-line" not in one,
          "one point is a single dot - there is no trend in one week, and "
          "none is drawn")

    flat = ui.sparkline([12.0, 12.0, 12.0, 12.0])
    parse_one(flat, "flat sparkline")
    pts = _spark_points(flat, "wr-spark-line")
    ys = sorted(set(round(y, 3) for y in [p[1] for p in (pts[0] if pts
                                                         else [])]))
    check(len(pts) == 1 and len(pts[0]) == 4,
          "a flat series still plots all four of its points")
    check(len(ys) == 1,
          "a flat series lands every point on one horizontal line (%s)" % ys)

    zeros = ui.sparkline([0, 0])
    parse_one(zeros, "all-zero sparkline")
    check("nan" not in zeros.lower() and "inf" not in zeros.lower(),
          "an all-zero series produces no NaN or inf in the path data")

    # Every degenerate shape, in one sweep - none may raise.
    raised = None
    for series in ([], [0], [0, 0], [5, 5, 5], [-3, -3], [1e-12, 1e-12],
                   [0.0, 0.0, 0.0, 0.0], ["a"], [None], [True, False],
                   [float("nan")], [1, float("nan"), 1], [2, 3],
                   list(range(60))):
        for w, h in ((8, 8), (72, 20), (400, 60)):
            try:
                out = ui.sparkline(series, w, h)
            except ZeroDivisionError as exc:
                raised = "ZeroDivisionError on %r @%dx%d: %s" % (
                    series, w, h, exc)
            except Exception as exc:                 # noqa: BLE001
                raised = "%s on %r @%dx%d: %s" % (
                    type(exc).__name__, series, w, h, exc)
            else:
                if "nan" in out.lower() or "inf" in out.lower():
                    raised = "non-finite path data from %r" % (series,)
    check(raised is None,
          "no series or size divides by zero or emits non-finite data (%s)"
          % (raised or "swept clean"))

    # A real series is monotone-mapped: the max sits highest on the page.
    rising = ui.sparkline([2.0, 9.0, 21.0], 60, 20)
    pts = _spark_points(rising, "wr-spark-line")[0]
    check(pts[0][1] > pts[1][1] > pts[2][1],
          "a rising series rises on screen (SVG y grows downward)")
    check(all(0 <= x <= 60 and 0 <= y <= 20 for x, y in pts),
          "every plotted point stays inside the viewBox")

    titled = ui.sparkline([1, 2], title="weeks 1-2")
    root = parse_one(titled, "titled sparkline")
    check(root is not None and root.get("role") == "img"
          and root.find(SVG_NS + "title") is not None,
          "a titled sparkline is a labelled image")
    check(parse_one(ui.sparkline([1, 2]), "plain spark").get("aria-hidden")
          == "true", "an untitled sparkline is decoration")


# --- components -------------------------------------------------------------

def test_components():
    print("\n[6] components - the shared vocabulary")

    for verdict, want in (("start", "START"), ("SIT", "SIT"),
                          ("flex", "FLEX"), ("toss-up", "TOSS-UP")):
        chip = ui.verdict_chip(verdict, 70)
        check(want in chip and "<svg" in chip,
              "verdict %r renders as %s with its icon" % (verdict, want))
    unfiled = ui.verdict_chip(None)
    check("wr-chip-unfiled" in unfiled and "<svg" not in unfiled,
          "no verdict filed renders a hollow chip with NO icon - the page "
          "never invents an opinion a source did not give")

    check("120%" not in ui.verdict_chip("start", 480)
          and "100%" in ui.verdict_chip("start", 480),
          "a percentage is clamped into 0-100")
    check("%" not in ui.verdict_chip("start", "junk"),
          "an unparseable percentage is dropped, not printed as junk")

    check("STEADY" in ui.streak_badge("flat")
          and "<svg" not in ui.streak_badge("flat"),
          "a player with no trend gets the muted STEADY badge and no icon - "
          "there is no signal, so no glyph claims one")
    check("wr-icon-hot-streak" in ui.streak_badge("hot")
          and "wr-icon-cold-streak" in ui.streak_badge("cold"),
          "hot and cold carry the flame and the snowflake")
    check("wr-icon-matchup-smash" in ui.matchup_badge("smash")
          and "wr-icon-matchup-avoid" in ui.matchup_badge("tough"),
          "smash and avoid carry the hammer and the wall")
    check("NEUTRAL" in ui.matchup_badge(None), "an ungraded matchup is "
          "NEUTRAL, not guessed")

    pop = ui.popover("<b>summary</b>", "<p>detail</p>")
    root = parse_one(pop, "popover")
    check(root is not None and root.tag == "details",
          "popover is a native <details> - no JS framework, and the "
          "keyboard, focus and find-in-page behaviour come free")
    check(root is not None and root.find("summary") is not None,
          "with a real <summary> for the toggle")
    check("<script" not in ui.css() and "<script" not in pop,
          "the design system ships no script at all")
    check("open" in ui.popover("s", "d", open_=True)
          and " open" not in ui.popover("s", "d"),
          "open_ controls the initial disclosure state")

    deg = ui.degraded_banner("Divergence", RuntimeError("feed 503"))
    check("SECTION DEGRADED" in deg and "RuntimeError" in deg
          and "feed 503" in deg,
          "a degraded section says so in place and carries its own error - "
          "the honesty contract, not a silently dropped card")
    check("--force" in deg, "and tells the reader how to retry")

    row = ui.player_row("Bijan Robinson", "RB", "ATL", locked=True)
    parse_one(row, "player row")
    check("wr-icon-locked" in row and "LOCKED" in row,
          "a locked row carries the padlock - his game has started")
    check("Bijan Robinson" in row and ">RB<" in row,
          "the row prints the name and the position chip")

    check("<svg" in ui.legend() and all(
        n.replace("_", "-") in ui.legend() for n in ui.icon_names()),
        "the legend can render the whole set, so no page ships a glyph the "
        "reader has no key for")

    for tone in ("neutral", "good", "bad", "lean"):
        parse_one(ui.stat_pill("XFP", "14.2", tone), "pill %s" % tone)
    for bad_call, label in (
            (lambda: ui.stat_pill("A", "B", "chartreuse"), "pill tone"),
            (lambda: ui.verdict_chip("start", 1, size="huge"), "chip size"),
            (lambda: ui.banner("x", tone="mauve"), "banner tone"),
            (lambda: ui.flag_badge("vibes"), "flag kind")):
        try:
            bad_call()
            ok = False
        except (ValueError, KeyError):
            ok = True
        check(ok, "an off-system %s raises instead of rendering unstyled"
              % label)

    check(ui.trim("a" * 500, 40).endswith("…") and
          len(ui.trim("a" * 500, 40)) == 40,
          "trim cuts to the limit and shows that it cut")


def test_purity():
    print("\n[7] purity - the design system reads and writes nothing")
    src = open(os.path.join(HERE, "engine", "ui.py"), "r").read()
    for bad in ("open(", "os.remove", "shutil.", "urllib", "requests",
                "subprocess", "pandas"):
        check(bad not in src,
              "engine/ui.py contains no %r - it is presentation only, so it "
              "can never touch the user's data" % bad)
    check("import html" in src and "from typing import" in src,
          "and imports nothing outside the standard library")


# --- 8. type scale ----------------------------------------------------------

def _font_sizes(css):
    """Every font-size value in a stylesheet, with its line for the report."""
    return re.findall(r"font-size\s*:\s*([^;}]+)", css)


def test_type_scale():
    print("\n[8] type scale - one scale, nothing under 11px")
    css = ui.component_css()
    full = ui.css()

    check(ui.TYPE_SCALE == {"t0": 26, "t1": 17, "t2": 15, "t3": 13, "t4": 11},
          "the scale is 17/15/13/11 with one display size (26) - the audit's "
          "phone floors")
    check(ui.TYPE_FLOOR == 11 and min(ui.TYPE_SCALE.values()) == 11
          and min(ui.TYPE_SCALE_DESKTOP.values()) >= 11,
          "the floor is 11px on every viewport - desktop may drop t3 one "
          "pixel but never below the floor")
    for k, v in ui.TYPE_SCALE.items():
        check("--wr-%s: %dpx;" % (k, v) in css,
              "--wr-%s is declared as %dpx" % (k, v))
    check(re.search(r"@media not all and \(max-width: 700px\)\s*\{\s*:root"
                    r"\s*\{\s*--wr-t3: 12px;", css),
          "from 701px t3 steps down to 12px (documented desktop exception), "
          "written as the negated phone query")
    check(not [m.group(0) for m in re.finditer(
              r"(?<![-\w])(min-)?width:\s*(\d+(?:\.\d+)?)px", css)
              if float(m.group(2)) > 390],
          "no fixed width over 390px anywhere in the owned sheet - the "
          "phone-first audit every page runs")
    for k in ui.TYPE_SCALE:
        check(".wr-%s {" % k in css, ".wr-%s utility class exists" % k)

    allowed_px = set(ui.TYPE_SCALE.values()) | set(
        ui.TYPE_SCALE_DESKTOP.values())
    tokens = set("var(--wr-%s)" % k for k in ui.TYPE_SCALE)
    off_scale, under_floor = [], []
    for raw in _font_sizes(css):
        v = raw.strip()
        if v in tokens or v == "inherit":
            continue
        m = re.match(r"^(\d+(?:\.\d+)?)px$", v)
        if not m:
            off_scale.append(v)
            continue
        px = float(m.group(1))
        if px < ui.TYPE_FLOOR:
            under_floor.append(v)
        if px not in allowed_px:
            off_scale.append(v)
    check(not under_floor,
          "no font-size in the emitted CSS is under 11px (%s)"
          % (under_floor or "clean"))
    check(not off_scale,
          "every font-size is a scale token or a scale number - no ad-hoc "
          "sizes (%s)" % (sorted(set(off_scale)) or "clean"))
    check(len(_font_sizes(css)) >= 30,
          "the audit actually saw the component sheet (%d declarations)"
          % len(_font_sizes(css)))
    check(re.search(r"body\s*\{[^}]*font-size:\s*var\(--wr-t2\)", css),
          "body text is t2 (15px)")
    check(re.search(r"\.wr-h1\s*\{[^}]*font-size:\s*var\(--wr-t0\)", css),
          ".wr-h1 is the one rule that spends the display size")
    check(ui.type_css() in full,
          "the type scale ships inside ui.css() after the colour tokens")
    check(full.index(":root {") < full.index("--wr-t1"),
          "the colour token block still comes first, so the three-state "
          "theme audit reads the right :root")

    # Inline monogram sizes obey the floor at avatar sizes.
    for size in (24, 28, 36):
        fs = int(re.search(r"font-size:(\d+)px", ui.avatar("x", "Ab Cd",
                                                            size)).group(1))
        check(fs >= ui.TYPE_FLOOR,
              "a %dpx monogram avatar sets its letters at >= 11px (%d)"
              % (size, fs))


# --- 9. v4 components -------------------------------------------------------

def _glyphs_titled(markup, label):
    """Every <svg> in `markup` is either a labelled image (role=img with a
    <title>) or decorative inside an element that carries a title."""
    root = parse_one("<div>%s</div>" % markup, label)
    if root is None:
        return
    parents = {c: p for p in root.iter() for c in p}
    naked = 0
    for el in root.iter(SVG_NS + "svg"):
        if el.get("role") == "img" and el.find(SVG_NS + "title") is not None:
            continue
        node, ok = el, False
        while node in parents:
            node = parents[node]
            if node.get("title") or node.get("aria-label"):
                ok = True
                break
        if not ok:
            naked += 1
    check(naked == 0, "%s: every glyph carries a hover title, itself or "
          "through its chip (%d naked)" % (label, naked))


def test_v4():
    print("\n[9] v4 - the League-Legend row and its chrome")

    # --- status pill ------------------------------------------------------
    weights = {}
    for code in ui.STATUS_CODES:
        pill = ui.status_pill(code)
        root = parse_one(pill, "status_pill(%s)" % code)
        check(root is not None and root.tag == "abbr" and root.text == code
              and root.get("title"),
              "%s is an <abbr> whose text is the code and whose title is "
              "the long word" % code)
        weights[code] = re.search(r"wr-st-(rule|fill|ghost)", pill).group(1)
    check(weights["Q"] == "rule" and weights["D"] == "rule",
          "Q and D are ink on paper with the gold rule - he may still play")
    check(weights["O"] == "fill" and weights["IR"] == "fill"
          and weights["SUSP"] == "fill",
          "O, IR and SUSP are the ink fill - weight, not hue, says he will "
          "not")
    check(weights["BYE"] == "ghost" and weights["LOCK"] == "ghost",
          "BYE and LOCK are ghosts - the calendar's and the clock's status")
    check(ui.normalize_status("Questionable") == "Q"
          and ui.normalize_status("injured reserve") == "IR"
          and ui.normalize_status("PUP") is None
          and ui.normalize_status(None) is None,
          "normalize_status maps a feed's words and refuses to guess PUP")
    check("Questionable - out of practice" in
          ui.status_pill("questionable", "out of practice"),
          "the title carries the note after the long word")
    try:
        ui.status_pill("VIBES")
        raised = False
    except KeyError:
        raised = True
    check(raised, "an unknown status code raises - a closed vocabulary")
    check(len(re.search(r">([A-Z]+)</abbr>", ui.status_pill("SUSP"))
              .group(1)) <= 4,
          "no pill is longer than four letters")

    # --- news dot ---------------------------------------------------------
    for unread in (True, False):
        dot = ui.news_dot(unread)
        root = parse_one(dot, "news_dot(%s)" % unread)
        check(root is not None and root.get("role") == "img"
              and root.get("aria-label") and root.get("title"),
              "news_dot(unread=%s) is a labelled image with a title"
              % unread)
    check("wr-dot-unread" in ui.news_dot(True)
          and "wr-dot-read" in ui.news_dot(False),
          "the dot is filled while unread and hollow once read")
    check("width: 8px; height: 8px" in ui.css() and
          ".wr-dot-read { background: transparent; }" in ui.css(),
          "the dot is 8px and the read state is hollow, by CSS")

    # --- trending arrows --------------------------------------------------
    up = ui.trend_arrow("up", 3100)
    check("wr-icon-trend-up" in up and "wr-trend-strong" in up
          and "3,100 adds" in up,
          "a strong up-trend carries the up arrow, the strong class and "
          "the add count in its title")
    check("wr-trend-strong" not in ui.trend_arrow("up", 40),
          "a mild up-trend is ink, not gold")
    check("wr-icon-trend-down" in ui.trend_arrow("down")
          and "wr-trend-strong" not in ui.trend_arrow("down", 99999),
          "down never goes gold - the accent is for a reason to act")
    check(ui.trend_arrow(None) == "" and ui.trend_arrow("flat") == "",
          "no trend renders nothing - no glyph claims a signal that is "
          "not there")
    check(".wr-trend-up.wr-trend-strong { color: var(--wr-gold); }"
          in ui.css(), "the strong up-arrow is gold by token")
    _glyphs_titled(up, "trend_arrow")

    # --- opponent chip ----------------------------------------------------
    want = {"smash": "wr-opp-smash", "good": "wr-opp-good",
            "neutral": "wr-opp-neutral", "tough": "wr-opp-tough",
            "avoid": "wr-opp-avoid"}
    for grade, klass in want.items():
        chip = ui.opp_chip("KC", grade)
        check(klass in chip and ">KC<" in chip,
              "opp_chip graded %s carries %s and the code" % (grade, klass))
        _glyphs_titled(chip, "opp_chip(%s)" % grade)
    check("wr-icon-wall" in ui.opp_chip("KC", "avoid")
          and "wr-icon-wall" not in ui.opp_chip("KC", "tough"),
          "only AVOID carries the wall glyph")
    check(">vs<" in ui.opp_chip("KC", "good", home=True)
          and ">@<" in ui.opp_chip("KC", "good", home=False)
          and "wr-opp-p" not in ui.opp_chip("KC", "good", home=None),
          "home is 'vs', away is '@', None is bare")
    check("wr-opp-none" in ui.opp_chip("KC", None)
          and "not graded" in ui.opp_chip("KC", None),
          "an ungraded matchup is the dotted chip, never a guess")
    css = ui.css()
    check(re.search(r"\.wr-opp-smash \{[^}]*background: var\(--wr-chip-start\)",
                    css)
          and re.search(r"\.wr-opp-avoid \{[^}]*background: var\(--wr-text\)",
                        css)
          and re.search(r"\.wr-opp-good\s+\{[^}]*solid var\(--wr-rule\)", css)
          and re.search(r"\.wr-opp-tough \{[^}]*solid var\(--wr-text\)", css),
          "the grade is weight: gold fill / gold outline / hairline / ink "
          "outline / ink fill - no hue")

    # --- projected vs actual ----------------------------------------------
    proj = ui.score_cell(14.26)
    check("wr-score-proj" in proj and ">14.3<" in proj
          and "wr-num" in proj and "wr-score-a" not in proj,
          "before kickoff the cell shows the projection alone, tabular")
    live = ui.score_cell(14.2, 21.7)
    check("wr-score-live" in live and ">21.7<" in live
          and "proj 14.2" in live,
          "with an actual the cell shows the actual bold and the "
          "projection muted beneath")
    check("wr-score-none" in ui.score_cell(None)
          and ">—<" in ui.score_cell("junk"),
          "no projection is an honest dash, not a zero")
    det = ui.score_cell(14.2, 21.7, breakdown_html="<p>breakdown</p>")
    root = parse_one(det, "score_cell details")
    check(root is not None and root.tag == "details"
          and root.find("summary") is not None
          and "breakdown" in det and "tap for the breakdown" in det,
          "with a breakdown the number is a <details> summary - tap it, "
          "no JS")
    check("<details" not in live,
          "without a breakdown there is nothing to open, so no <details>")
    check(re.search(r"\.wr-score-a \{[^}]*var\(--wr-t1\)", css)
          and re.search(r"\.wr-num, \.wr-chip-pct[^{]*\{[^}]*tabular-nums",
                        css),
          "the actual is t1 and every number is tabular")

    # --- legend popover ---------------------------------------------------
    pop = ui.legend_popover([("start", "play him"),
                             (ui.raw(ui.status_pill("Q")), "questionable")])
    root = parse_one(pop, "legend_popover")
    check(root is not None and root.tag == "details"
          and root.find("summary") is not None
          and root.find("summary").get("aria-label"),
          "the legend is a <details> behind a labelled '?' control")
    check("wr-icon-start" in pop and 'class="wr-st' in pop,
          "the key lists icons and this module's own chips alike")
    check(re.search(r"\.wr-lgd > \.wr-lgd-b \{[^}]*width: 44px; height: 44px",
                    css),
          "the '?' has a 44px hit area")
    _glyphs_titled(pop, "legend_popover")
    try:
        ui.legend([(HOSTILE, "x")])
        raised = False
    except KeyError:
        raised = True
    check(raised, "a legend glyph that is a plain string and not an icon "
                  "name raises - a feed string starting with '<' is never "
                  "mistaken for markup")
    check(ui.status_pill("Q") in ui.legend([(ui.raw(ui.status_pill("Q")),
                                             "questionable")]),
          "only markup marked with raw() is emitted as a glyph")

    # --- bottom sheet -----------------------------------------------------
    sh = ui.sheet("p 12/x", "Ja'Marr Chase", "<p>the breakdown</p>")
    root = parse_one(sh, "sheet")
    dlg = root.find("dialog") if root is not None else None
    fb = root.find("details") if root is not None else None
    check(dlg is not None and dlg.get("id") == "p-12-x"
          and dlg.get("aria-labelledby") == "p-12-x-t",
          "the sheet is a <dialog> with a sanitised id, labelled by its "
          "title")
    check(fb is not None and fb.find("summary") is not None
          and fb.find("summary").get("data-sheet") == "p-12-x",
          "a <details> fallback sits beside it, its summary the trigger")
    check(list(root).index(fb) + 1 == list(root).index(dlg),
          "the dialog is the details' next sibling, which is what the "
          "no-JS CSS rule keys on")
    check(".wr-sheet-fb[open] + .wr-sheet:not([open]) {" in css
          and "display: block; position: static" in css,
          "without JS, opening the details shows the sheet in flow")
    check(dlg.find(".//button[@data-sheet-close]") is not None
          and dlg.find(".//button").get("aria-label") == "close",
          "the sheet has a labelled close button")
    check("wr-icon-sheet-handle" in sh and "wr-icon-close" in sh,
          "drag-handle and close glyphs are present")
    check("the breakdown" in sh and "Ja&#x27;Marr" in sh,
          "the body is carried and the title is escaped")
    check(re.search(r"\.wr-sheet\[open\] \{[^}]*position: fixed[^}]*bottom: 0"
                    r"[^}]*max-height: 60vh[^}]*border-radius: 16px 16px 0 0",
                    css),
          "with JS it is a bottom sheet: fixed, ~half height, rounded top")
    check(re.search(r"@media not all and \(max-width: 700px\) \{[^@]*"
                    r"\.wr-sheet\[open\] \{[^}]*translate\(-50%, -50%\)", css),
          "from 701px it centres as a modal")
    js = ui.sheets_script()
    check(js.startswith("<script>") and "[data-sheet]" in js
          and "showModal" in js and "[data-sheet-close]" in js
          and "preventDefault" in js,
          "sheets_script opens by [data-sheet], closes by "
          "[data-sheet-close], and stops the details toggle when it runs")
    check("<script" not in ui.css() and "<script" not in sh,
          "the sheet itself ships no script - pages include "
          "sheets_script() once")
    _glyphs_titled(sh, "sheet")

    # --- segmented control ------------------------------------------------
    seg = ui.segmented("view", [("s", "Starters", "#s"), ("b", "Bench", "#b"),
                                ("a", "All", "#a")], "b")
    root = parse_one(seg, "segmented")
    tabs = root.findall("a") if root is not None else []
    check(root is not None and root.get("role") == "tablist"
          and root.get("aria-label") == "view" and len(tabs) == 3,
          "segmented is a role=tablist of anchors")
    check([t.get("aria-selected") for t in tabs] == ["false", "true", "false"]
          and all(t.get("role") == "tab" for t in tabs),
          "exactly the active segment is aria-selected")
    btn = ui.segmented("v", [("a", "A"), ("b", "B")], "a")
    check('<button type="button" class="wr-seg-a" role="tab"' in btn
          and 'data-seg="a"' in btn,
          "without hrefs the segments are buttons carrying data-seg")
    for n in (1, 5):
        try:
            ui.segmented("v", [("k%d" % i, "L") for i in range(n)], "k0")
            raised = False
        except ValueError:
            raised = True
        check(raised, "%d segments raise - the control is 2-4 wide" % n)
    check(re.search(r"\.wr-seg \{[^}]*grid-auto-columns: 1fr[^}]*height: 44px",
                    css)
          and re.search(r'\.wr-seg-a\[aria-selected="true"\] \{[^}]*'
                        r"var\(--wr-rule\)", css),
          "equal segments, 44px tall, gold underline on the active one")

    # --- three-column row -------------------------------------------------
    ident = ui.row3_identity("Ja'Marr Chase", "WR", "CIN",
                             ui.status_pill("Q") + ui.news_dot())
    mid = ui.opp_chip("KC", "smash") + ui.score_cell(16.4)
    row = ui.row3(ident, mid, ui.verdict_chip("start", 78))
    root = parse_one(row, "row3")
    cols = [c.get("class") for c in root] if root is not None else []
    check(cols == ["wr-r3-id", "wr-r3-mid", "wr-r3-v"],
          "row3 is exactly three columns: identity | opponent+projection | "
          "verdict")
    check("wr-r3-name" in row and "Ja&#x27;Marr Chase" in row
          and ">WR<" in row and ">CIN<" in row,
          "the identity column prints chip, name and team")
    x = ui.row3(ident, mid, ui.verdict_chip("start", 78), "<p>why</p>")
    root = parse_one(x, "row3 expanded")
    check(root is not None and root.tag == "details"
          and root.find("summary") is not None
          and "wr-icon-expand" in x and "why" in x,
          "with expanded_html the row is a <details> whose summary is the "
          "row")
    check(re.search(r"\.wr-r3 \{[^}]*grid-template-columns: minmax\(0, 1fr\) "
                    r"auto auto[^}]*min-height: 48px", css)
          and re.search(r"\.wr-r3-name \{[^}]*text-overflow: ellipsis", css)
          and re.search(r"\.wr-r3-mid \{[^}]*white-space: nowrap", css),
          "48px rows; names ellipsize; the middle column never wraps")
    _glyphs_titled(row, "row3")

    # --- glyph titles across the older components -------------------------
    check('title="START - the call is to play him"' in ui.verdict_chip("start")
          and 'title="no verdict filed"' in ui.verdict_chip(None),
          "verdict chips carry a hover explanation even when the page gives "
          "none")
    check('title="an injury status is filed"' in ui.flag_badge("injury")
          and 'title="no game this week"' in ui.flag_badge("bye"),
          "flag badges carry a default note")
    for label, markup in (("verdict_chip", ui.verdict_chip("sit", 40)),
                          ("streak_badge", ui.streak_badge("hot")),
                          ("matchup_badge", ui.matchup_badge("avoid")),
                          ("flag_badge", ui.flag_badge("locked")),
                          ("legend", ui.legend()),
                          ("matchup_meter", ui.matchup_meter("smash"))):
        _glyphs_titled(markup, label)

    # --- the shell: title switcher + five phone tabs ----------------------
    leagues = [("l1", "Main League"), ("l2", "Dynasty")]
    nav = ui.shell("board", "l2", 3, leagues)
    frag = re.search(r'<details class="wr-lgsw">.*?</details>', nav).group(0)
    root = parse_one(frag, "title switcher")
    check(root is not None and root.find("summary") is not None
          and ">Dynasty<" in frag.split("</summary>")[0],
          "the switcher is a <details> whose summary is the current "
          "league's name")
    check('class="wr-lgs-cur wr-display"' in frag and "wr-icon-expand" in frag,
          "the title is set in the display face with a chevron")
    lst = root.find("nav") if root is not None else None
    check(lst is not None and lst.get("class") == "wr-lgs"
          and lst.get("aria-label") == "league",
          "the league list keeps the .wr-lgs nav pages already style")
    check('<a class="wr-lg" href="board-l2-week3.html" aria-current="true">'
          in frag and '<a class="wr-lg" href="board-l1-week3.html">' in frag,
          "the .wr-lg items keep their exact markup and current marking")
    check('title="switch league"' in frag,
          "the switcher summary carries a hover title")
    home = ui.shell("home", leagues=leagues)
    check(">All leagues<" in home and 'aria-current="true"' not in
          re.search(r'<details class="wr-lgsw">.*?</details>', home).group(0),
          "a page with no league of its own is titled 'All leagues' and "
          "marks no league current")
    check(">Waivers<" in ui.shell("home", leagues=leagues, title="Waivers"),
          "a page may pass its own title")
    check("wr-lgs-static" in ui.shell("sources", title="Sources")
          and ">Sources<" in ui.shell("sources", title="Sources"),
          "with no leagues at all a passed title still renders, static")
    check(nav.count('class="wr-tab"') == 5,
          "the phone bar still carries five tabs")
    check(nav.count("<script") == 1,
          "the shell still ships exactly one script (the theme toggle) - "
          "the switcher is <details>, not JS")
    check(re.search(r"\.wr-lgsw > \.wr-lgs \{[^}]*position: absolute[^}]*"
                    r"flex-direction: column", css),
          "the other leagues drop down beneath the title")


# --- 10. brand --------------------------------------------------------------

def test_brand():
    print("\n[10] brand - the wordmark is the product name")
    nav = ui.shell("board", "l1", 2, [("l1", "Main League")])
    check(ui.PRODUCT_NAME == "Graded Takes" and ui.WORDMARK == "GRADED TAKES",
          "the product is Graded Takes; the wordmark is set in caps")
    mark = re.search(r'<a class="wr-mark"[^>]*>.*?</a>', nav)
    check(mark is not None and
          '<span class="wr-mark-t wr-display">GRADED TAKES</span>' in mark.group(0),
          "the shell's wordmark text reads GRADED TAKES")
    check(mark is not None and 'aria-label="Graded Takes - home"' in mark.group(0)
          and 'class="wr-mark-sq"' in mark.group(0),
          "the mark link is labelled with the product name and keeps the "
          "gold diamond")
    check("WAR ROOM" not in nav and "War Room" not in nav,
          "the working title appears nowhere in the shell")
    css = ui.css()
    check("War Room" not in css and "WAR ROOM" not in css,
          "...nor anywhere in the stylesheet")
    for extra in (ui.shell("home", leagues=[("l1", "L")]),
                  ui.shell("sources", title="Sources"),
                  ui.shell("install", title="Install %s" % ui.PRODUCT_NAME)):
        check("War Room" not in extra and "WAR ROOM" not in extra,
              "every shell variant is free of the working title")


# --- 11. app mode -----------------------------------------------------------

def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _rule(css, selector):
    """The declaration block(s) for one exact selector list, joined."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _strip_comments(css)):
        sels = [x.strip() for x in m.group(1).strip().split(",")]
        if selector in sels:
            out.append(m.group(2))
    return " ".join(out)


def test_app_mode():
    print("\n[11] app mode - data-app=\"ios\" hides the shell chrome, nothing else")
    css = ui.css()
    block = ui.APP_MODE_CSS
    check(block in ui.component_css() and block in css,
          "APP_MODE_CSS is part of the owned component sheet and of css(), "
          "so every page inherits it without a renderer changing")
    check(ui.APP_ATTR == "data-app" and ui.APP_VALUES == ("ios",),
          "the contract is one attribute, data-app, and one value, ios")
    check('html[data-app="ios"]' in block
          and re.search(r'html\[data-app="ios"\]\s+\.wr-nav\s*,', block)
          and re.search(r'html\[data-app="ios"\]\s+\.wr-tabs\s*\{\s*display:\s*none;?\s*\}',
                        block),
          "html[data-app=\"ios\"] .wr-nav and .wr-tabs are display:none")
    hidden = _rule(block, 'html[data-app="ios"] .wr-nav-sub')
    check("display: none" in hidden,
          "the subtitle strip - the bar's own second row - hides with the bar")
    # every selector in the block is anchored on the attribute, and none of
    # them reaches a card, table, sheet, popover or note
    sels = [x.strip() for m in re.finditer(r"([^{}]+)\{", _strip_comments(block))
            for x in m.group(1).split(",") if x.strip()]
    check(sels and all(x.startswith('html[data-app="ios"]') for x in sels),
          "every app-mode selector is anchored on html[data-app=\"ios\"] "
          "(%s)" % [x for x in sels if not x.startswith('html[data-app="ios"]')])
    touched = [x for x in sels for c in
               ("wr-card", "wr-table", "wr-sheet", "wr-pop", "wr-quiet",
                "wr-page", "wr-lgsw", "wr-legend") if c in x]
    check(not touched,
          "app mode touches no card, table, sheet, popover, page frame or "
          "quiet note (%s)" % (touched or "clean"))
    root = _rule(block, 'html[data-app="ios"]')
    check("--wr-nav-h: 0px" in root and "scroll-padding-top: 0" in root,
          "with no pinned bar --wr-nav-h and the scroll padding go to 0, so "
          "an in-page anchor lands at the very top")
    body = _rule(block, 'html[data-app="ios"] body')
    check("padding-bottom: env(safe-area-inset-bottom, 0px)" in body
          and "60px" not in body,
          "the 60px the fixed tab bar reserved is released; only the "
          "device's own bottom inset remains")
    # specificity: the pwa layer's phone rule re-reserves the 60px; the
    # app-mode rule must outrank it whatever the order of the layers
    check(re.search(r"body \{ padding-bottom: calc\(60px", css)
          and css.index('html[data-app="ios"] body') > 0,
          "the pwa safe-area layer still reserves the bar for browsers; the "
          "app-mode rule outranks it by specificity (html[attr] body)")
    check("#" not in block,
          "app mode adds no colour - the token blocks, and so the hue rule, "
          "are untouched")
    # the shell's markup is still emitted in full: one file, three homes
    nav = ui.shell("lineup", "l1", 1, [("l1", "L")], subtitle="week 1")
    check('class="wr-nav"' in nav and 'class="wr-tabs"' in nav
          and 'class="wr-nav-sub"' in nav and "data-app" not in nav.split("<script")[0],
          "the header, subtitle and tabs are still emitted, and the shell "
          "never sets data-app itself - only the native app does")
    # the theme toggle's script steps aside in app mode
    tt = ui.theme_toggle()
    js = tt.split("<script>", 1)[1]
    check(js.find('if(r.hasAttribute("data-app"))return;') > 0
          and js.find('if(r.hasAttribute("data-app"))return;') < js.find("localStorage"),
          "the theme toggle's script returns before reading storage when "
          "data-app is set - the app owns data-theme")
    # the three theme states are still fully declared (app-set data-theme
    # paints the same tokens as a toggle-set one)
    check(':root[data-theme="dark"]' in css and
          ':root:not([data-theme="light"])' in css,
          "an app-set data-theme=\"dark\" hits the same explicit block the "
          "toggle uses; light stays the bare :root")


def main():
    print("UI DESIGN SYSTEM ACCEPTANCE TEST")
    test_icons()
    test_tokens()
    test_escaping()
    test_sparkline()
    test_distinct()
    test_components()
    test_purity()
    test_type_scale()
    test_v4()
    test_brand()
    test_app_mode()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d of %d FAILURE(S):" % (len(FAILURES), CHECKS[0])))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
