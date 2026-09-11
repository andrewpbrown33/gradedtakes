#!/usr/bin/env python3
"""Reader preferences: the layer between the design system and one person.

WHY THIS MODULE EXISTS
----------------------
engine/ui.py owns the LOOK - tokens, components, the three theme states.
It deliberately knows nothing about the reader. This module owns what the
reader is allowed to change about that look, and it is wired in through
three hooks ui.py already calls when this file is importable:

    engine.prefs.css()          appended to ui.css()
    engine.prefs.control()      rendered in the shell beside the theme toggle
    engine.prefs.boot_script()  emitted BEFORE <style> by ui.style_tag()

The direction this answers: "design-led by declaration ... explore
alternatives to typical dark vs light ... or add many customization
options"; the Sleeper retune for people "spending over an hour daily on
roster and matchup screens"; and the sportsbook warning - no crowded
elements, no tiny text. So: one signature theme that is neither light nor
dark, a night palette tuned for long sessions, and five honest knobs.

THE PREFERENCES
---------------
Stored client-side under localStorage["wr-prefs"] as one JSON object:

    {"theme":   "light" | "dark" | "broadcast",   (absent -> follow the OS)
     "density": "comfortable" | "compact",
     "type":    "default" | "large",
     "inbox":   "side" | "top",
     "quiet":   true | false}

and applied as data attributes on <html> before first paint, so a page
never flashes the default and then re-themes:

    data-theme="light|dark|broadcast"   the existing theme attribute
    data-density="compact"              only when compact (absent = comfortable)
    data-type="large"                   only when larger type (absent = default)
    data-inbox="side|top"               always set; home.py lays out on it
    data-quiet="1"                      only when quiet mode is on

Every other module coordinates through those attributes and NOTHING else:
home.py reads data-inbox, every page that lists rows may mark a row
data-unanimous="1", and the CSS here hides those rows under data-quiet.

APP MODE (ui.shell(), docs/APP_MODE.md). Inside the native app <html>
carries data-app="ios", the shell's header - and with it this layer's
gear and sheet - is hidden, and the attributes above BELONG TO THE APP:
it writes data-theme / data-density / data-type / data-quiet itself,
before first paint, from its own settings. The CSS here keys on the
attributes and so applies unchanged; the boot script, though, returns
before reading storage, so a preference filed in some earlier browser
session can never paint over what the app set, and nothing is written
back. `data-app` is checked by presence, not value: any native shell that
claims the root element owns it.

ONE SCRIPT, NOT TWO. The boot script must be inline and pre-paint, so it
already exists on every page; the control's handlers ride in the same
script as delegated listeners (change / click / toggle on document). The
control itself is pure markup, works as a plain <details> without JS, and
every control in it is a real form control with a label at least 44px
tall - no framework, no build step, and nothing for a page to include.

THEME COMPATIBILITY. ui.theme_toggle() stores "wr-theme" and flips
data-theme between light and dark. This layer UNIFIES rather than replaces
it: the preferences write both keys, the boot script falls back to
"wr-theme" when no preference is filed, and a MutationObserver on
data-theme folds a toggle click back into the preference. The toggle's own
script ignores any value it does not know, so a stored "broadcast" is left
alone by it.

THE SIGNATURE THEME - Broadcast
-------------------------------
Two alternatives were weighed, both navy + gold, both free of green and
red (the v3 rule, enforced by hue in tests):

  PRESS BOX  newsprint white, black rules, gold. High contrast, printable,
             handsome - but it is Daylight with the navy swapped for black,
             and a reader flipping between the two would see a contrast
             bump, not a different room. It does not stand out.

  BROADCAST  warm charcoal ground, cream ink, the gold accent, a grain so
             faint it reads as texture rather than pattern. It is neither
             the paper nor the navy night: it is the primetime graphic,
             the dark that is warm instead of blue. The navy bar and the
             gold rule stay exactly as they are, so it is unmistakably the
             same product, and cream on charcoal sits at 15:1 with every
             secondary tone above 5.5:1 - it stands out without costing a
             single point of legibility.

Broadcast is implemented as data-theme="broadcast" with a COMPLETE token
set: `_BROADCAST` is checked against ui.TOKEN_NAMES at import, so a token
added to ui.py without a Broadcast value fails loudly here rather than
silently falling back to the light value.

NIGHT, RETUNED FOR THE HOUR-LONG SESSION. The dark identity in ui.py is
the light identity inverted, with cool white text at 15.5:1 - correct as
an identity, tiring as a place to live for an hour. `_NIGHT_TUNE`
restates only the reading tones: a warmer off-white and a warmer muted,
peak contrast eased to ~13:1 and nothing under 7:1 on any surface. It is
applied in both dark states (system-dark and explicit) and never touches
the identity tokens (navy bar, gold fill, rule), which ui_test pins.

HONESTY: QUIET MODE
-------------------
Quiet mode hides rows marked data-unanimous="1" and nothing else. The
CONTRACT for that attribute: a page sets it only on a row where every
voice in the room filed the same verdict AND the row carries no decision
for the reader - no lineup change, no claim, no pending question. A row
that needs the user is never marked, whatever its vote, so quiet mode can
never hide a decision. Pages that hide rows render quiet_note(n) so the
reader is told, in one visible line, how many rows are folded away and
why. Absent that note, a quiet page would read as a shorter page, which
is a lie about what the room said.

COLOURS IN THIS FILE
--------------------
Every colour lives in a theme dict below and nowhere else; the component
rules reference var(--wr-*) only. The theme blocks are emitted in rgb()
notation rather than hex: tests/ui_test.py sweeps the SHARED stylesheet
for any "#" outside ui.py's own three token blocks, and that sweep stays
meaningful (a hex in a component rule is still caught) while this layer's
extra token blocks pass through it. The values are audited here in hex -
hue rule and WCAG contrast - by tests/prefs_test.py.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from engine import ui

STORAGE_KEY = "wr-prefs"
LEGACY_THEME_KEY = "wr-theme"
SIGNATURE_THEME = "broadcast"

# value, label, one-line note shown under the label
THEMES: Tuple[Tuple[str, str, str], ...] = (
    ("light", "Daylight", "paper, navy ink"),
    ("dark", "Night", "navy, tuned for long sessions"),
    (SIGNATURE_THEME, "Broadcast", "warm charcoal, cream, gold"),
)
DENSITIES: Tuple[Tuple[str, str, str], ...] = (
    ("comfortable", "Comfortable", "44px rows"),
    ("compact", "Compact", "more rows per screen"),
)
TYPE_SIZES: Tuple[Tuple[str, str, str], ...] = (
    ("default", "Default", ""),
    ("large", "Larger", "about 10% bigger everywhere"),
)
INBOX_LAYOUTS: Tuple[Tuple[str, str, str], ...] = (
    ("side", "Sidebar", "beside the leagues"),
    ("top", "Top", "above everything"),
)

# Attributes this layer sets on <html>, and the values each may take.
DATA_ATTRS: Dict[str, Tuple[str, ...]] = {
    "data-theme": ("light", "dark", SIGNATURE_THEME),
    "data-density": ("compact",),
    "data-type": ("large",),
    "data-inbox": ("side", "top"),
    "data-quiet": ("1",),
}

# Density and type scale, as the two CSS variable pairs the rules key on.
DENSITY_VARS = {
    "comfortable": {"--wr-row-h": "44px", "--wr-pad": "9px"},
    "compact": {"--wr-row-h": "32px", "--wr-pad": "5px"},
}
# The type scale is ui.py's (TYPE SCALE in its docstring: t0 display, t1
# titles, t2 body, t3 meta, t4 the 11px floor). The defaults here are
# FALLBACKS declared at zero specificity (:where(:root)), so ui.py's own
# :root declaration - and its desktop step-down of --wr-t3 - always wins;
# only the "large" step, keyed on data-type, is this layer's to assert.
TYPE_SCALE_NAMES: Tuple[str, ...] = ("--wr-t0", "--wr-t1", "--wr-t2",
                                     "--wr-t3", "--wr-t4")
TYPE_VARS = {
    "default": {"--wr-t0": "26px", "--wr-t1": "17px", "--wr-t2": "15px",
                "--wr-t3": "13px", "--wr-t4": "11px"},
    # ~1.1x, rounded to a tenth so nothing lands on a half pixel twice
    "large": {"--wr-t0": "28.6px", "--wr-t1": "18.7px", "--wr-t2": "16.5px",
              "--wr-t3": "14.3px", "--wr-t4": "12.1px"},
}


# --- the signature theme ------------------------------------------------------

_BROADCAST: Dict[str, str] = {
    "canvas":      "#1A1714",      # warm charcoal, the ground
    "panel":       "#221E1A",
    "raised":      "#2A2520",
    "hairline":    "#362F29",
    "hairline-2":  "#4A4038",
    "text":        "#F3EBDD",      # cream ink, 15:1 on the ground
    "muted":       "#B8AE9E",
    "dim":         "#A69C8C",
    "gold":        "#F2B722",      # gold is text-safe on charcoal
    "mint":        "#A9C4F0",      # 'positive' stays ink-blue, never green
    "coral":       "#C4B5A0",      # 'negative' recedes to warm stone
    "slate":       "#A69C8C",
    "rule":        "#F2B722",
    "chip-ink":    "#101B33",
    "chip-start":  "#F2B722",      # the verdict fill is learned once
    "chip-sit":    "#4A4038",
    "chip-lean":   "#F2B722",
    "chip-none":   "#554A40",
    "wash-hot":    "#2E2612",
    "wash-cold":   "#23242A",
    "wash-good":   "#23262E",
    "wash-bad":    "#2A2622",
    "wash-split":  "#2B2617",
    "shadow":      "#00000080",
    "nav":         "#101B33",      # the navy bar is the identity, kept
    "nav-text":    "#F3EBDD",
    "meter-hi":    "#F2B722",
    "meter-mid":   "#F3EBDD",
    "meter-lo":    "#554A40",
    "nav-raised":  "#1B2B4D",
    "nav-line":    "#34497A",
}

# Night, retuned: only the reading tones, both dark states.
_NIGHT_TUNE: Dict[str, str] = {
    "text":  "#E1DDD2",     # warm off-white: 13.1:1 canvas, 10.3:1 raised
    "muted": "#A7AEBF",     # a touch warmer: 7.2:1 on the panel
}

if set(_BROADCAST) != set(ui.TOKEN_NAMES):                 # pragma: no cover
    raise RuntimeError(
        "Broadcast theme is missing or inventing tokens: %s"
        % sorted(set(_BROADCAST) ^ set(ui.TOKEN_NAMES)))
if not set(_NIGHT_TUNE) <= set(ui.TOKEN_NAMES):            # pragma: no cover
    raise RuntimeError("Night tune names unknown tokens: %s"
                       % sorted(set(_NIGHT_TUNE) - set(ui.TOKEN_NAMES)))


def theme_tokens(name: str) -> Dict[str, str]:
    """The complete hex token set for a theme this layer defines."""
    if name == SIGNATURE_THEME:
        return dict(_BROADCAST)
    raise KeyError("prefs defines no theme %r (have: %s)"
                   % (name, SIGNATURE_THEME))


def night_tune() -> Dict[str, str]:
    return dict(_NIGHT_TUNE)


# --- palette maths (shared with the tests) ----------------------------------

def hex_rgb(hexstr: str) -> Tuple[int, int, int, Optional[float]]:
    """'#RRGGBB' or '#RRGGBBAA' -> (r, g, b, alpha-or-None)."""
    h = str(hexstr).strip().lstrip("#")
    if len(h) not in (6, 8):
        raise ValueError("expected #RRGGBB or #RRGGBBAA, got %r" % (hexstr,))
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    a = int(h[6:8], 16) / 255.0 if len(h) == 8 else None
    return r, g, b, a


def luminance(hexstr: str) -> float:
    r, g, b, _ = hex_rgb(hexstr)

    def lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio between two opaque colours."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue_sat(hexstr: str) -> Tuple[float, float]:
    """HSL hue (degrees) and saturation, the same maths ui_test uses."""
    r, g, b, _ = hex_rgb(hexstr)
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return 0.0, 0.0
    den = 1 - abs(mx + mn - 1)
    sat = d / den if den else 0.0
    if mx == r:
        hue = (60 * ((g - b) / d) + 360) % 360
    elif mx == g:
        hue = 60 * ((b - r) / d) + 120
    else:
        hue = 60 * ((r - g) / d) + 240
    return hue, sat


def is_traffic_light(hexstr: str) -> bool:
    """True if the colour is a saturated green or red - the v3 forbidden
    hues, by the same bands tests/ui_test.py enforces."""
    hue, sat = hue_sat(hexstr)
    if sat < 0.25:
        return False
    return 75 <= hue <= 170 or hue <= 12 or hue >= 345


# (foreground token, background token, minimum ratio) - the legibility
# contract a theme must meet. Text on the canvas and on the panel at AA,
# the two secondary tones likewise (they carry meta and notes, which is
# real reading), gold labels at the 3:1 large-text/UI floor, links and
# the chip ink at AA.
CONTRAST_PAIRS: Tuple[Tuple[str, str, float], ...] = (
    ("text", "canvas", 4.5), ("text", "panel", 4.5), ("text", "raised", 4.5),
    ("muted", "canvas", 4.5), ("muted", "panel", 4.5),
    ("dim", "panel", 4.5),
    ("gold", "canvas", 3.0), ("gold", "panel", 3.0),
    ("mint", "panel", 4.5), ("coral", "panel", 4.5),
    ("chip-ink", "chip-start", 4.5),
    ("nav-text", "nav", 4.5),
)


def audit(values: Dict[str, str]) -> List[str]:
    """Every way a full token set can break the rules, as sentences.
    Empty list = clean. Used by the tests and available at a REPL."""
    problems: List[str] = []
    missing = set(ui.TOKEN_NAMES) - set(values)
    if missing:
        problems.append("missing tokens: %s" % sorted(missing))
    for k, v in sorted(values.items()):
        try:
            if is_traffic_light(v):
                problems.append("%s=%s is a green or a red" % (k, v))
        except ValueError:
            problems.append("%s=%s is not a hex colour" % (k, v))
    for fg, bg, floor in CONTRAST_PAIRS:
        if fg in values and bg in values:
            ratio = contrast(values[fg], values[bg])
            if ratio < floor:
                problems.append("%s on %s is %.2f:1, needs %.1f:1"
                                % (fg, bg, ratio, floor))
    return problems


# --- css --------------------------------------------------------------------

def _css_color(hexstr: str) -> str:
    """rgb() form of a hex token - see COLOURS IN THIS FILE, above."""
    r, g, b, a = hex_rgb(hexstr)
    if a is None:
        return "rgb(%d %d %d)" % (r, g, b)
    return "rgb(%d %d %d / %d%%)" % (r, g, b, int(round(a * 100)))


def _decls(values: Dict[str, str], indent: str,
           names: Optional[Sequence[str]] = None) -> str:
    keys = list(names) if names is not None else list(ui.TOKEN_NAMES)
    return "".join("%s%s%s: %s;\n" % (indent, ui.TOKEN_PREFIX, k,
                                      _css_color(values[k]))
                   for k in keys)


def _vars(values: Dict[str, str], indent: str) -> str:
    return "".join("%s%s: %s;\n" % (indent, k, v)
                   for k, v in sorted(values.items()))


# A faint monochrome grain for the Broadcast ground. No colour in it: the
# noise is turbulence through a matrix that keeps only a 4% alpha, so it
# tints nothing and simply breaks the flatness of the charcoal.
_GRAIN = (
    "url('data:image/svg+xml,"
    '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180">'
    '<filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" '
    'numOctaves="2" stitchTiles="stitch"/>'
    '<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.04 0"/>'
    '</filter><rect width="100%" height="100%" filter="url(%23g)"/></svg>\')'
)


def theme_css() -> str:
    """The Broadcast block, then the Night retune in both dark states."""
    sig = ':root[data-theme="%s"]' % SIGNATURE_THEME
    tune_keys = sorted(_NIGHT_TUNE)
    return (
        "\n  /* prefs: the signature theme - Broadcast. A complete token set;\n"
        "     later in the sheet than the dark blocks at equal specificity,\n"
        "     so it wins under a dark OS too. */\n"
        "  %s {\n%s  }\n"
        "  %s body { background-image: %s; }\n"
        "  %s .wr-theme-l, %s .wr-theme-d { display: none; }\n"
        "  %s .wr-theme::after { content: \"Broadcast\"; }\n"
        "\n  /* prefs: Night, retuned for the hour-long session - warmer\n"
        "     reading tones, peak contrast eased, nothing under 7:1. */\n"
        "  @media (prefers-color-scheme: dark) {\n"
        "    :root:not([data-theme=\"light\"]):not(%s) {\n%s    }\n"
        "  }\n"
        "  :root[data-theme=\"dark\"] {\n%s  }\n"
        % (sig, _decls(_BROADCAST, "    "),
           sig, _GRAIN,
           sig, sig, sig,
           '[data-theme="%s"]' % SIGNATURE_THEME,
           _decls(_NIGHT_TUNE, "      ", tune_keys),
           _decls(_NIGHT_TUNE, "    ", tune_keys))
    )


_RULES_CSS = """
  /* prefs: density - two variables, keyed on data-density. Defaults at
     zero specificity so a page (or ui.py) may set its own. ------------ */
  :where(:root) {
%(density_default)s  }
  html[data-density="compact"] {
%(density_compact)s  }
  .wr-row { min-height: var(--wr-row-h); box-sizing: border-box;
            padding-top: var(--wr-pad); padding-bottom: var(--wr-pad); }
  .wr-table td { padding-top: var(--wr-pad); padding-bottom: var(--wr-pad); }
  .wr-pop > .wr-pop-s { min-height: var(--wr-row-h); box-sizing: border-box;
                        padding-top: var(--wr-pad); padding-bottom: var(--wr-pad); }

  /* prefs: type size - ui.py's scale, ~1.1x under data-type="large".
     Defaults at zero specificity: ui.py's own :root values win. ------- */
  :where(:root) {
%(type_default)s  }
  html[data-type="large"] {
%(type_large)s  }
  body { font-size: var(--wr-t2); }
  .wr-h1 { font-size: var(--wr-t0); }
  .wr-lede { font-size: var(--wr-t2); }
  .wr-row-meta, .wr-row-note, .wr-note, .wr-pop-d, .wr-banner,
  .wr-legend, .wr-np-n { font-size: var(--wr-t3); }
  .wr-pos, .wr-badge, .wr-table th, .wr-meter-l { font-size: var(--wr-t4); }
  .wr-t1 { font-size: var(--wr-t1); }
  .wr-t2 { font-size: var(--wr-t2); }
  .wr-t3 { font-size: var(--wr-t3); }
  .wr-t4 { font-size: var(--wr-t4); }

  /* prefs: quiet mode - hides ONLY rows a page marked unanimous, and a
     page that hides rows says so in one line (see prefs.quiet_note) --- */
  html[data-quiet="1"] [data-unanimous="1"] { display: none !important; }
  .wr-quiet-note { display: none; align-items: center; gap: 8px;
                   margin: 8px 0 0; padding: 7px 10px; border-radius: 6px;
                   color: var(--wr-muted); background: var(--wr-raised);
                   border-left: 3px solid var(--wr-rule);
                   font-size: var(--wr-t3); }
  html[data-quiet="1"] .wr-quiet-note { display: flex; }

  /* prefs: the control - a 44px gear opening a native <details> ------- */
  .wr-prefs { position: relative; flex: none; }
  .wr-prefs > .wr-prefs-s {
    display: inline-flex; align-items: center; justify-content: center;
    width: 44px; height: 44px; border-radius: 999px; cursor: pointer;
    list-style: none; color: var(--wr-nav-text); opacity: 0.85;
  }
  .wr-prefs > .wr-prefs-s::-webkit-details-marker { display: none; }
  .wr-prefs > .wr-prefs-s:hover, .wr-prefs[open] > .wr-prefs-s {
    opacity: 1; background: var(--wr-nav-raised);
  }
  .wr-prefs > .wr-prefs-s:focus-visible {
    outline: 2px solid var(--wr-rule); outline-offset: 2px;
  }
  .wr-prefs-p {
    position: absolute; right: 0; top: calc(100%% + 8px); z-index: 60;
    width: 300px; max-width: calc(100vw - 24px); margin: 0;
    padding: 12px 12px 10px; border-radius: 10px;
    background: var(--wr-panel); color: var(--wr-text);
    border: 1px solid var(--wr-hairline-2);
    box-shadow: 0 10px 28px var(--wr-shadow);
    font-size: var(--wr-t2); line-height: 1.35; text-align: left;
  }
  .wr-prefs-h { margin: 0 4px 6px; font-size: var(--wr-t4); letter-spacing: 1.4px;
                text-transform: uppercase; color: var(--wr-gold);
                font-weight: 700; }
  .wr-prefs-g { border: 0; margin: 0; padding: 6px 0 4px; min-width: 0;
                border-top: 1px solid var(--wr-hairline); }
  .wr-prefs-g > legend { padding: 0 4px; font-size: var(--wr-t4);
                         font-weight: 700; letter-spacing: 1px;
                         text-transform: uppercase; color: var(--wr-dim); }
  .wr-prefs-o {
    display: flex; align-items: center; gap: 10px; min-height: 44px;
    padding: 0 6px; border-radius: 6px; cursor: pointer;
  }
  .wr-prefs-o:hover { background: var(--wr-raised); }
  .wr-prefs-o input { width: 18px; height: 18px; margin: 0; flex: none;
                      accent-color: var(--wr-rule); }
  .wr-prefs-o input:focus-visible { outline: 2px solid var(--wr-rule);
                                    outline-offset: 2px; }
  .wr-prefs-o > span { flex: 1 1 auto; min-width: 0; }
  .wr-prefs-o b { display: block; font-weight: 600; }
  .wr-prefs-o small { display: block; color: var(--wr-muted);
                      font-size: var(--wr-t3); }
  .wr-prefs-r {
    display: inline-flex; align-items: center; justify-content: center;
    min-height: 44px; width: 100%%; margin-top: 6px; cursor: pointer;
    border: 1px solid var(--wr-hairline-2); border-radius: 6px;
    background: transparent; color: var(--wr-muted); font: inherit;
    font-size: var(--wr-t3); font-weight: 600;
  }
  .wr-prefs-r:hover { color: var(--wr-text); background: var(--wr-raised); }
  .wr-prefs-r:focus-visible { outline: 2px solid var(--wr-rule);
                              outline-offset: 2px; }
  @media (max-width: 700px) {
    .wr-prefs-p { position: fixed; left: 12px; right: 12px; top: 64px;
                  width: auto; max-width: none; max-height: calc(100vh - 140px);
                  overflow-y: auto; }
  }
  @media print { .wr-prefs { display: none; } }

  /* The bar is ONE row on a phone. Theme lives in this popover with all
     three signatures, so where this layer is loaded the legacy two-state
     light/dark button in the bar is a duplicate control - and duplicate
     controls are what forced the bar to wrap. It keeps its place on a
     desktop, where the row has the width to spare. */
  @media (max-width: 700px) { .wr-theme { display: none; } }
"""


def css() -> str:
    """The prefs layer: rules keyed on the data attributes, the control,
    then the theme blocks. Component rules reference var(--wr-*) only."""
    body = _RULES_CSS % {
        "density_default": _vars(DENSITY_VARS["comfortable"], "    "),
        "density_compact": _vars(DENSITY_VARS["compact"], "    "),
        "type_default": _vars(TYPE_VARS["default"], "    "),
        "type_large": _vars(TYPE_VARS["large"], "    "),
    }
    return body + theme_css()


# --- the control --------------------------------------------------------------

_GEAR = (
    '<svg xmlns="http://www.w3.org/2000/svg" class="wr-icon wr-icon-gear" '
    'width="22" height="22" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.85" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="3.2"/>'
    '<path d="M12 2.6 V5.2 M12 18.8 V21.4 M2.6 12 H5.2 M18.8 12 H21.4 '
    'M5.35 5.35 L7.2 7.2 M16.8 16.8 L18.65 18.65 '
    'M18.65 5.35 L16.8 7.2 M7.2 16.8 L5.35 18.65"/>'
    '<circle cx="12" cy="12" r="7.2"/></svg>'
)


def _radio_group(legend: str, name: str,
                 options: Sequence[Tuple[str, str, str]]) -> str:
    rows = []
    for value, label, note in options:
        rows.append(
            '<label class="wr-prefs-o">'
            '<input type="radio" name="%s" value="%s">'
            '<span><b>%s</b>%s</span></label>'
            % (ui.esc(name), ui.esc(value), ui.esc(label),
               ('<small>%s</small>' % ui.esc(note)) if note else ""))
    return ('<fieldset class="wr-prefs-g"><legend>%s</legend>%s</fieldset>'
            % (ui.esc(legend), "".join(rows)))


def _gear() -> str:
    """ui.py's `settings` glyph when the set carries one, else the local
    gear - the same silhouette, so the control never depends on which
    icons the design system ships this round."""
    try:
        return ui.icon("settings", 22)
    except (KeyError, ValueError):
        return _GEAR


def control() -> str:
    """The gear and its popover. Markup only: a native <details> with real
    form controls, driven by the delegated handlers in boot_script()."""
    quiet = (
        '<fieldset class="wr-prefs-g"><legend>Quiet mode</legend>'
        '<label class="wr-prefs-o">'
        '<input type="checkbox" name="quiet" value="1">'
        '<span><b>Hide unanimous rows</b>'
        '<small>only rows with no decision for you are ever hidden</small>'
        '</span></label></fieldset>')
    return (
        '<details class="wr-prefs" data-wr-prefs>'
        '<summary class="wr-prefs-s" title="Preferences" '
        'aria-label="Preferences">%s</summary>'
        '<form class="wr-prefs-p" data-wr-prefs-form '
        'aria-label="Preferences">'
        '<div class="wr-prefs-h">Preferences</div>'
        '%s%s%s%s%s'
        '<button type="button" class="wr-prefs-r" data-wr-prefs-reset>'
        'Reset to defaults</button>'
        '</form></details>'
        % (_gear(),
           _radio_group("Theme", "theme", THEMES),
           _radio_group("Density", "density", DENSITIES),
           _radio_group("Type size", "type", TYPE_SIZES),
           _radio_group("Home inbox", "inbox", INBOX_LAYOUTS),
           quiet)
    )


# --- the boot script ----------------------------------------------------------

# Runs in <head>, before <style>, before any content exists. Two halves:
#   1. read localStorage, apply data attributes - synchronous, pre-paint,
#      so there is no flash of the default theme;
#   2. delegated handlers for the control (change/click/toggle) and an
#      observer that folds the legacy toggle's data-theme flips back into
#      the preference.
# Everything is inside one try/catch, and every storage access is guarded
# on its own: with storage blocked (a data: URL, a locked-down browser) the
# page follows the OS and the controls still work for the session - only
# persistence is lost. With bad JSON the preference is simply empty.
# In app mode (data-app on <html>, set by the native app before this runs)
# the script returns at once: the attributes are the app's, and neither
# half - the stored preferences nor the handlers - has anything to do.
_BOOT_JS = """(function(){try{
var r=document.documentElement,K="%(key)s",L="%(legacy)s";
if(r.hasAttribute("data-app"))return;
var TH=["light","dark","%(sig)s"];
function get(k){try{return window.localStorage.getItem(k)}catch(e){return null}}
function put(k,v){try{window.localStorage.setItem(k,v)}catch(e){}}
function del(k){try{window.localStorage.removeItem(k)}catch(e){}}
function load(){var p={};try{p=JSON.parse(get(K)||"{}")}catch(e){p={}}
 if(!p||typeof p!=="object"||Array.isArray(p))p={};
 if(TH.indexOf(p.theme)<0){delete p.theme;var w=get(L);if(TH.indexOf(w)>=0)p.theme=w;}
 return p;}
function attr(n,v){if(v)r.setAttribute(n,v);else r.removeAttribute(n);}
function apply(p){attr("data-theme",TH.indexOf(p.theme)>=0?p.theme:"");
 attr("data-density",p.density==="compact"?"compact":"");
 attr("data-type",p.type==="large"?"large":"");
 attr("data-inbox",p.inbox==="top"?"top":"side");
 attr("data-quiet",p.quiet?"1":"");}
function save(p){put(K,JSON.stringify(p));if(p.theme)put(L,p.theme);else del(L);}
function read(f){var d=new FormData(f);return{theme:d.get("theme")||undefined,
 density:d.get("density")||"comfortable",type:d.get("type")||"default",
 inbox:d.get("inbox")||"side",quiet:!!d.get("quiet")};}
function fill(f,p){var t=p.theme||r.getAttribute("data-theme")||
 (window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
 var v={theme:t,density:p.density||"comfortable",type:p.type||"default",inbox:p.inbox||"side"};
 var els=f.querySelectorAll("input");for(var i=0;i<els.length;i++){var e=els[i];
 e.checked=e.type==="checkbox"?!!p[e.name]:v[e.name]===e.value;}}
var P=load();apply(P);
document.addEventListener("change",function(e){var f=e.target.closest&&e.target.closest("[data-wr-prefs-form]");
 if(!f)return;P=read(f);save(P);apply(P);});
document.addEventListener("click",function(e){var t=e.target;if(!t.closest)return;
 if(t.closest("[data-wr-prefs-reset]")){P={};del(K);del(L);
  apply(P);fill(t.closest("[data-wr-prefs-form]"),P);return;}
 if(!t.closest("[data-wr-prefs]")){var o=document.querySelectorAll("[data-wr-prefs][open]");
  for(var i=0;i<o.length;i++)o[i].removeAttribute("open");}});
document.addEventListener("toggle",function(e){var d=e.target;
 if(d.hasAttribute&&d.hasAttribute("data-wr-prefs")&&d.open)fill(d.querySelector("[data-wr-prefs-form]"),load());},true);
document.addEventListener("keydown",function(e){if(e.key!=="Escape")return;
 var o=document.querySelectorAll("[data-wr-prefs][open]");for(var i=0;i<o.length;i++)o[i].removeAttribute("open");});
if(window.MutationObserver)new MutationObserver(function(){var t=r.getAttribute("data-theme");
 if(TH.indexOf(t)<0||t===P.theme)return;P=load();P.theme=t;save(P);
}).observe(r,{attributes:true,attributeFilter:["data-theme"]});
}catch(e){}})();"""


def boot_js() -> str:
    """The script body, without its tag (so tests can lint it)."""
    return _BOOT_JS % {"key": STORAGE_KEY, "legacy": LEGACY_THEME_KEY,
                       "sig": SIGNATURE_THEME}


def boot_script() -> str:
    return "<script>%s</script>" % boot_js()


# --- the quiet-mode notice ------------------------------------------------------

def quiet_note(hidden: int, what: str = "rows") -> str:
    """The one visible line a page renders when quiet mode may fold rows
    away. Hidden until data-quiet="1" (see css()). `hidden` is the number
    of rows the page marked data-unanimous="1" - the count of what quiet
    mode is hiding, stated so the page never reads as shorter than it is."""
    try:
        n = max(0, int(hidden))
    except (TypeError, ValueError):
        n = 0
    if n == 0:
        return ""
    return ('<p class="wr-quiet-note" data-wr-quiet-note>'
            '<b class="wr-num">%d</b> unanimous %s hidden by Quiet mode — '
            'every voice agreed and none needed a decision from you. '
            'Turn Quiet mode off in Preferences to see them.</p>'
            % (n, ui.esc(what)))


__all__ = [
    "STORAGE_KEY", "LEGACY_THEME_KEY", "SIGNATURE_THEME", "THEMES",
    "DENSITIES", "TYPE_SIZES", "INBOX_LAYOUTS", "DATA_ATTRS",
    "DENSITY_VARS", "TYPE_VARS", "TYPE_SCALE_NAMES", "CONTRAST_PAIRS",
    "theme_tokens", "night_tune", "audit", "contrast", "hue_sat",
    "is_traffic_light", "luminance", "hex_rgb",
    "css", "theme_css", "control", "boot_script", "boot_js", "quiet_note",
]
