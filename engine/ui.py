#!/usr/bin/env python3
"""Shared presentation vocabulary for every Graded Takes page.

WHY THIS MODULE EXISTS
----------------------
engine/board.py and engine/digest.py each grew their own hand-rolled CSS.
They agree on the identity - navy canvas, gold rules, mint/coral verdicts -
but they agree by coincidence, not by construction, so the two pages drift
apart every time one of them is edited. This module is the single place
that owns the LOOK: the colour tokens, the icon set, and the small set of
components that both pages (and the roster page) compose from.

    from engine import ui
    ui.css()                       # the whole stylesheet, tokens included
    ui.icon("hot_streak", 20)      # one inline <svg>, currentColor stroke
    ui.verdict_chip("start", 78)   # the board's verdict language

THREE-STATE THEMING - the rule this module enforces
---------------------------------------------------
A page has three theme states, not two:

    bare :root                                        -> light
    @media (prefers-color-scheme: dark)
        :root:not([data-theme="light"])               -> system dark
    :root[data-theme="dark"]                          -> explicit dark

Every token is declared in ALL THREE. A colour that exists only inside the
media query is a colour that vanishes the moment a reader sets an explicit
theme, and a `:root[data-theme="dark"]` block that is missing a token is a
half-themed page. `_LIGHT` and `_DARK` are validated to carry identical key
sets at import time so the three blocks can never fall out of step, and
tests/ui_test.py asserts the same thing against the rendered CSS.

EVERY HEX LIVES IN A TOKEN BLOCK. Component rules reference `var(--wr-*)`
and nothing else - that is what makes a single palette edit reach all three
pages instead of one.

THE VERDICT FILL DOES NOT CHANGE WITH THE THEME. `--wr-chip-start` is the gold #F2B722 in
light and in dark, deliberately: the verdict chip is the visual language of
the board, and a chip that repaints itself with the OS theme is a chip the
reader has to learn twice. Only the SURFACES around it re-theme.

ICONS
-----
Stroke-based, drawn on one 24x24 grid, rendered at 20 or 24. No emoji, no
dingbats, no icon font - an emoji is a different typeface on every machine
and cannot inherit a semantic colour. `stroke="currentColor"` means an icon
dropped inside a mint chip comes out mint, inside coral comes out coral,
and inside a grayscale print comes out as line art that still reads.

The set is designed for 20px FIRST. Every silhouette is distinguishable at
that size from every other silhouette in the set - see `ICON_NOTES`, which
records the distinguishing feature of each, and which the test suite
requires every icon to carry.

Three rules fell out of actually rendering the set and looking at it, and
they are worth keeping:

  A RING IS TOLD BY ITS INTERIOR. The set has one two-ring form
  (`consensus`, interlocked, nothing inside) and a family of single-ring
  forms that differ ONLY by what sits inside the ring: `waiver_add` a full
  cross, `drop` a single bar, `info` a dot over a stem, `clock` two hands,
  `search` a ring pushed off-centre with a tail, `settings` a hub with
  teeth outside. No two ring glyphs may share an interior - the test suite
  enforces it - because at 20px the ring itself is the same shape every
  time and the interior is the whole message. `toss_up` was drawn as a
  ring-and-bar and then as a coin under a flipping arc; both lost to this
  rule. It is a balance now: a post, a beam, and two bowls hung from the
  ends, which shares a family with nothing.

  DO NOT DRAW A CHARACTER. `dissent` was first drawn as two rings held
  apart by a diagonal divider. Rendered, it was a PERCENT SIGN - on a page
  whose every verdict chip ends in a literal percentage. It is now a stem
  forking into two arrows flying apart, which is also the better metaphor.
  An icon that resolves into a glyph the page already prints is worse than
  a dull icon. (`injury` is the one deliberate exception: a medical cross
  IS the character everyone reads as "hurt", and it is drawn fat and
  twelve-sided so it cannot be confused with the thin plus inside
  `waiver_add`.)

  SAY THE VERB, NOT THE NOUN. `news` was a megaphone, which rendered as the
  volume control every reader has already learnt to mean "sound", then a
  bell, which at 20px was the generic notification chrome of every app. It
  is a lightning bolt now - the only zigzag in the set, and the same mark
  `news_dot` abbreviates to a single gold point beside a name.
  `matchup_avoid` is crenellated for the same reason - the notched top
  keeps its outline from settling into the plain rectangle shared by
  `wall`, `calendar` and `locked`.

TYPE SCALE
----------
One scale, four sizes, declared as tokens so a page never invents a
number: `--wr-t1` 17px (titles), `--wr-t2` 15px (body), `--wr-t3` 13px
(meta, chips), `--wr-t4` 11px (pills, badges, kickers - the floor). A
fifth, `--wr-t0` 26px, is the display size and is used by exactly one
rule (`.wr-h1`). On desktop (>= 701px) `--wr-t3` steps down to 12px; the
floor never moves, so nothing on any page is ever set under 11px. Every
`font-size` in the emitted stylesheet is either one of these tokens or
one of these numbers, and tests/ui_test.py audits the sheet for both.

Phones are the reason: the sportsbook and app audits both found that
crowded rows and sub-11px text are what break the reader's flow, so the
slot row is glyph-encoded into THREE columns (identity | opponent +
projection | verdict - see `row3`) and the explanation of every glyph
moves out of the flow and into a hover `title` and the `legend_popover`.

SHEETS
------
`sheet()` is a <dialog> styled as a bottom sheet on phones and a centred
modal from 701px. It needs `sheets_script()` once per page to open by
`[data-sheet]` and close by `[data-sheet-close]`, the backdrop, or Escape.
Without JS the <details> beside it opens the same content in flow, so
every sheet's content is reachable with scripting off.

ESCAPING
--------
Everything that came from outside - player names, source names, creator
quotes, error strings - goes through `esc()` before it reaches the page.
The handful of parameters that take composed HTML are named `*_html` and
are documented as trusted; build them from this module's own helpers.
"""

import html as _html
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# --- escaping ---------------------------------------------------------------

def esc(text) -> str:
    """Escape untrusted text for both element bodies and attributes."""
    return _html.escape("" if text is None else str(text), quote=True)


class _Raw(str):
    """Markup this module already built, marked so a component that takes
    EITHER a name or markup can tell them apart without guessing from a
    leading "<" - which is exactly the character a hostile feed string
    would start with."""
    __slots__ = ()


def raw(markup: str) -> str:
    """Mark composed markup as trusted for slots that also take names -
    `legend([(ui.raw(ui.status_pill("Q")), "questionable")])`. Only ever
    wrap the output of this module's own components."""
    return _Raw(markup)


def trim(text, limit: int = 120) -> str:
    """Collapse whitespace and cut to `limit`, keeping the cut visible."""
    flat = " ".join(str("" if text is None else text).split())
    if len(flat) <= limit:
        return flat
    return flat[:max(1, limit - 1)].rstrip() + "…"


# --- tokens -----------------------------------------------------------------

TOKEN_PREFIX = "--wr-"

# v3 identity: LIGHT is the default - a warm editorial paper with navy ink
# and one accent, gold. Dark is the same identity inverted, not a second
# brand. There is deliberately NO green and NO red anywhere in the system:
# verdicts are encoded by WEIGHT (gold fill = start, ghost outline = sit,
# dashed = toss-up) and attention by a gold RULE, so nothing on a page ever
# reads as the generic dashboard traffic-light.
_LIGHT = {
    "canvas":      "#F4F2EC",
    "panel":       "#FFFFFF",
    "raised":      "#F8F7F3",
    "hairline":    "#E4E1D8",
    "hairline-2":  "#CFCABB",
    "text":        "#101B33",
    "muted":       "#5B6478",
    "dim":         "#5F6A80",
    "gold":        "#8F6606",      # text-safe gold on paper (AA on white)
    "mint":        "#1F4E9E",      # 'positive' is deep ink-blue, not green
    "coral":       "#7A6A55",      # 'negative' recedes to taupe, not red
    "slate":       "#5F6A80",
    "rule":        "#F2B722",      # the identity gold: fills, rules, marks
    "chip-ink":    "#101B33",
    "chip-start":  "#F2B722",      # solid fill
    "chip-sit":    "#CFCABB",      # ghost border
    "chip-lean":   "#8F6606",      # dashed
    "chip-none":   "#B8BDC9",
    "wash-hot":    "#FFF3D1",
    "wash-cold":   "#EEF1F6",
    "wash-good":   "#EDF2FA",
    "wash-bad":    "#F3F0EA",
    "wash-split":  "#F8F4E8",
    "shadow":      "#101B3314",
    "nav":         "#101B33",      # the top bar is navy in BOTH themes
    "nav-text":    "#EAF0FA",
    "meter-hi":    "#F2B722",
    "meter-mid":   "#101B33",
    "meter-lo":    "#B8BDC9",
    "nav-raised":  "#1B2B4D",
    "nav-line":    "#34497A",
}

_DARK = {
    "canvas":      "#0D1730",
    "panel":       "#14213D",
    "raised":      "#1B2B4D",
    "hairline":    "#27395E",
    "hairline-2":  "#34497A",
    "text":        "#EAF0FA",
    "muted":       "#9AA9C7",
    "dim":         "#8391B0",
    "gold":        "#F2B722",
    "mint":        "#8FB4FF",
    "coral":       "#B3A48E",
    "slate":       "#8391B0",
    "rule":        "#F2B722",
    "chip-ink":    "#101B33",
    "chip-start":  "#F2B722",
    "chip-sit":    "#34497A",
    "chip-lean":   "#F2B722",
    "chip-none":   "#3A4E78",
    "wash-hot":    "#2A2410",
    "wash-cold":   "#16233F",
    "wash-good":   "#16243F",
    "wash-bad":    "#22293A",
    "wash-split":  "#1F2B48",
    "shadow":      "#00000059",
    "nav":         "#101B33",
    "nav-text":    "#EAF0FA",
    "meter-hi":    "#F2B722",
    "meter-mid":   "#EAF0FA",
    "meter-lo":    "#3A4E78",
    "nav-raised":  "#1B2B4D",
    "nav-line":    "#34497A",
}

if set(_LIGHT) != set(_DARK):                        # pragma: no cover
    raise RuntimeError(
        "theme token sets diverged: %s"
        % sorted(set(_LIGHT) ^ set(_DARK)))

TOKEN_NAMES: Tuple[str, ...] = tuple(sorted(_LIGHT))

# Compatibility aliases for the names board.py and digest.py already write
# in their markup. They are declared ONCE, in bare :root, as var()
# references - a custom property resolves at USE time, so the alias follows
# whichever theme block last set the token it points at. Putting a hex here
# instead would be a colour that needs re-stating in all three blocks.
_ALIASES = (
    ("canvas", "canvas"), ("panel", "panel"), ("panel-2", "raised"),
    ("line", "hairline"), ("line-2", "hairline-2"),
    ("ink", "text"), ("muted", "muted"), ("slate", "slate"),
    ("gold", "gold"), ("gold-rule", "rule"),
    ("mint", "mint"), ("coral", "coral"),
    ("good", "mint"), ("bad", "coral"), ("warn", "gold"),
    ("chip-ink", "chip-ink"),
    ("hot-bg", "wash-hot"), ("split-bg", "wash-split"),
    ("warn-bg", "wash-hot"), ("bad-bg", "wash-bad"),
)


def _decls(values: Dict[str, str], indent: str) -> str:
    return "".join("%s%s%s: %s;\n" % (indent, TOKEN_PREFIX, k, values[k])
                   for k in TOKEN_NAMES)


def tokens_css() -> str:
    """The token block, in all three theme states.

    Emitted from one pair of dicts so the light block and the two dark
    blocks cannot list different properties.
    """
    alias = "".join("    --%s: var(%s%s);\n" % (a, TOKEN_PREFIX, t)
                    for a, t in _ALIASES)
    return (
        "  :root {\n"
        "%s"
        "\n"
        "    /* aliases for existing board/digest markup - these resolve\n"
        "       through the tokens above, so they follow every theme. */\n"
        "%s"
        "    color-scheme: light dark;\n"
        "  }\n"
        "\n"
        "  @media (prefers-color-scheme: dark) {\n"
        "    :root:not([data-theme=\"light\"]) {\n"
        "%s"
        "    }\n"
        "  }\n"
        "\n"
        "  :root[data-theme=\"dark\"] {\n"
        "%s"
        "  }\n"
        % (_decls(_LIGHT, "    "), alias,
           _decls(_DARK, "      "), _decls(_DARK, "    "))
    )


# --- icons ------------------------------------------------------------------

ICON_GRID = 24
ICON_SIZES: Tuple[int, int] = (20, 24)
_STROKE_TARGET = 1.7      # device px of stroke we want at any rendered size


def _stroke_for(size: int) -> float:
    """Keep optical weight constant as the render size changes.

    The art is drawn on a 24-unit grid. Rendered at 20px a 1.7-unit stroke
    would thin to 1.42 device px and the set would look lighter at the size
    it is used most, so the width is scaled back up by the grid ratio.
    """
    return round(_STROKE_TARGET * ICON_GRID / float(size), 2)


# name -> (svg body, one-line silhouette note)
#
# The note is not decoration: it is the record of what makes this shape
# unmistakable at 20px, and tests/ui_test.py requires every icon to carry
# one. If two notes ever read the same, the two icons look the same.
_ICONS = {
    # --- verdicts ------------------------------------------------------------
    "start": (
        '<path d="M8 5.2 L19 12 L8 18.8 Z"/>',
        "a bare right-pointing play triangle - the only pure triangle in "
        "the set",
    ),
    "sit": (
        '<path d="M5 7.6 H19"/>'
        '<path d="M3 13.2 H21"/>'
        '<path d="M6.6 7.6 V20.2"/>'
        '<path d="M17.4 7.6 V20.2"/>',
        "a bench - a wide seat bar crossed by two full-height uprights that "
        "carry a shorter back rail above it, symmetric about the centre",
    ),
    "toss_up": (
        '<path d="M12 4.2 V20"/>'
        '<path d="M8 20 H16"/>'
        '<path d="M4.4 7.2 H19.6"/>'
        '<path d="M4.4 7.2 V11.4"/>'
        '<path d="M1.6 11.4 A2.8 2.8 0 0 0 7.2 11.4"/>'
        '<path d="M19.6 7.2 V11.4"/>'
        '<path d="M16.8 11.4 A2.8 2.8 0 0 0 22.4 11.4"/>',
        "a balance scale - a post on a foot, a level beam across its top, "
        "and a shallow bowl hung by a short string from each end",
    ),
    # --- form ----------------------------------------------------------------
    "hot_streak": (
        '<path d="M12 2.8 c 3.6 3.4 5.8 6.3 5.8 9.5 '
        'a 5.8 5.8 0 1 1 -11.6 0 c 0 -3.2 2.2 -6.1 5.8 -9.5 Z"/>'
        '<path d="M12 11.6 c 1.9 1.8 2.8 3.1 2.8 4.5 '
        'a 2.8 2.8 0 1 1 -5.6 0 c 0 -1.4 0.9 -2.7 2.8 -4.5 Z"/>',
        "a flame - a pointed teardrop with a second small teardrop curling "
        "inside it, which is what stops it reading as a water drop",
    ),
    "cold_streak": (
        '<path d="M12 3.6 V20.4"/>'
        '<path d="M4.7 7.8 L19.3 16.2"/>'
        '<path d="M4.7 16.2 L19.3 7.8"/>'
        '<path d="M9 6.6 L12 3.6 L15 6.6"/>'
        '<path d="M9 17.4 L12 20.4 L15 17.4"/>',
        "a six-spoke snowflake - three crossed lines with symmetric barbs "
        "at both ends of the vertical, so it cannot read as one arrow",
    ),
    "trend_up": (
        '<path d="M3.4 17.2 L9.4 11.2 L13.4 15.2 L20.6 8"/>'
        '<path d="M14.6 8 H20.6 V14"/>',
        "a chart line that dips once and then climbs off the top-right "
        "corner under an open arrowhead - the only rising zigzag",
    ),
    "trend_down": (
        '<path d="M3.4 6.8 L9.4 12.8 L13.4 8.8 L20.6 16"/>'
        '<path d="M14.6 16 H20.6 V10"/>',
        "a chart line that lifts once and then falls off the bottom-right "
        "corner under an open arrowhead - the only falling zigzag",
    ),
    # --- status --------------------------------------------------------------
    "injury": (
        '<path d="M9 3 H15 V9 H21 V15 H15 V21 H9 V15 H3 V9 H9 Z"/>',
        "a fat medical cross - one closed twelve-sided outline with arms "
        "as thick as they are long, nothing inside it",
    ),
    "bye": (
        '<path d="M20.2 15.2 A 8.6 8.6 0 1 1 8.8 3.8 '
        'A 6.8 6.8 0 0 0 20.2 15.2 Z"/>',
        "a crescent moon - one solid curved sliver, no straight edges "
        "anywhere, for the week he is resting",
    ),
    "locked": (
        '<rect x="4" y="10.4" width="16" height="10.4" rx="2.2"/>'
        '<path d="M7.6 10.4 V7.2 A 4.4 4.4 0 0 1 16.4 7.2 V10.4"/>'
        '<path d="M12 14.2 v2.6"/>',
        "a padlock - a wide rounded body under a narrow semicircular "
        "shackle, with a short keyhole stroke centred inside",
    ),
    "news": (
        '<path d="M13.4 2.6 L5.2 13.4 H11.2 L10.6 21.4 L18.8 10.6 '
        'H12.8 Z"/>',
        "a lightning bolt - one closed zigzag leaning right, wide at the "
        "shoulder and tapering to a point at the foot",
    ),
    # --- matchups ------------------------------------------------------------
    "matchup_smash": (
        '<rect x="10.6" y="4.6" width="12" height="5.6" rx="1.4" '
        'transform="rotate(45 16.6 7.4)"/>'
        '<path d="M4.5 19.5 L14.9 9.1"/>',
        "a hammer - a fat bar canted up-right with a thin handle running "
        "down-left from it, heavy end high",
    ),
    "matchup_avoid": (
        '<path d="M3 20.5 V7.5 H6.5 V10.5 H10.25 V7.5 H13.75 V10.5 '
        'H17.5 V7.5 H21 V20.5 Z"/>'
        '<path d="M3 15 H21"/>'
        '<path d="M12 10.5 V15"/>'
        '<path d="M8 15 V20.5"/>'
        '<path d="M16 15 V20.5"/>',
        "a fortress wall with three battlements notched into its top edge, "
        "so its outline is never the plain rectangle of a lock or a bin",
    ),
    "wall": (
        '<rect x="3" y="5" width="18" height="14" rx="1.2"/>'
        '<path d="M3 9.7 H21"/>'
        '<path d="M3 14.3 H21"/>'
        '<path d="M12 5 V9.7"/>'
        '<path d="M8 9.7 V14.3"/>'
        '<path d="M16 9.7 V14.3"/>'
        '<path d="M12 14.3 V19"/>',
        "a plain brick wall - a flat-topped rectangle cut into three "
        "courses with staggered joints, no battlements, no lid",
    ),
    # --- moves ---------------------------------------------------------------
    "waiver_add": (
        '<circle cx="12" cy="12" r="8.6"/>'
        '<path d="M12 8.2 V15.8"/>'
        '<path d="M8.2 12 H15.8"/>',
        "a single ring with a thin full cross inside - one circle, both "
        "arms, the ring family's plus",
    ),
    "drop": (
        '<circle cx="12" cy="12" r="8.6"/>'
        '<path d="M8.2 12 H15.8"/>',
        "a single ring with one horizontal bar inside and nothing else - "
        "the ring family's minus",
    ),
    "trade": (
        '<path d="M3.5 9 H19"/>'
        '<path d="M15.8 5.8 L19 9 L15.8 12.2"/>'
        '<path d="M20.5 15 H5"/>'
        '<path d="M8.2 11.8 L5 15 L8.2 18.2"/>',
        "two long horizontal arrows stacked and pointing opposite ways - "
        "the only parallel-arrow glyph",
    ),
    # --- the sources ---------------------------------------------------------
    "dissent": (
        '<path d="M3.2 12 H9.4"/>'
        '<path d="M9.4 12 L17.6 5.4"/>'
        '<path d="M13.6 6 L17.6 5.4 L16.2 9.1"/>'
        '<path d="M9.4 12 L17.6 18.6"/>'
        '<path d="M13.6 18 L17.6 18.6 L16.2 14.9"/>',
        "one stem entering from the left and forking into two arrows that "
        "fly apart - the voices splitting off a shared question",
    ),
    "consensus": (
        '<circle cx="9" cy="12" r="6.2"/>'
        '<circle cx="15" cy="12" r="6.2"/>',
        "two large rings side by side on the level, interlocked so they "
        "share a lens - no divider, nothing between them",
    ),
    # --- chrome --------------------------------------------------------------
    "expand": (
        '<path d="M6.4 9.4 L12 15 L17.6 9.4"/>',
        "a single wide chevron pointing down - one stroke, nothing else",
    ),
    "close": (
        '<path d="M6.4 6.4 L17.6 17.6"/>'
        '<path d="M17.6 6.4 L6.4 17.6"/>',
        "a saltire - two diagonals crossing at the centre with no vertical "
        "and no barbs, which is what keeps it from the snowflake",
    ),
    "info": (
        '<circle cx="12" cy="12" r="8.6"/>'
        '<path d="M12 7.9 h0"/>'
        '<path d="M12 11 V16.4"/>',
        "a single ring with a lowercase i inside - a dot above a short "
        "stem, both on the centre line; the ring family's letter",
    ),
    "settings": (
        '<circle cx="12" cy="12" r="6.4"/>'
        '<circle cx="12" cy="12" r="2.2"/>'
        '<path d="M18.4 12 H21.6"/>'
        '<path d="M2.4 12 H5.6"/>'
        '<path d="M12 2.4 V5.6"/>'
        '<path d="M12 18.4 V21.6"/>'
        '<path d="M16.5 16.5 L18.8 18.8"/>'
        '<path d="M5.2 18.8 L7.5 16.5"/>'
        '<path d="M5.2 5.2 L7.5 7.5"/>'
        '<path d="M16.5 7.5 L18.8 5.2"/>',
        "a gear - a ring around a small hub with eight short teeth "
        "radiating outside the ring, the only glyph with strokes outside "
        "its circle on every side",
    ),
    "sheet_handle": (
        '<path d="M6 12 H18"/>',
        "a drag grabber - one short horizontal bar alone in the middle of "
        "the grid, drawn heavier than the rest of the set by the sheet",
    ),
    "calendar": (
        '<rect x="3" y="5" width="18" height="16" rx="2"/>'
        '<path d="M3 10.2 H21"/>'
        '<path d="M8 3 V7.2"/>'
        '<path d="M16 3 V7.2"/>',
        "a calendar page - a tall rounded rectangle with a ruled header "
        "band and two binding pegs poking above its top edge",
    ),
    "clock": (
        '<circle cx="12" cy="12" r="8.6"/>'
        '<path d="M12 7.2 V12 L15.4 14"/>',
        "a single ring with two hands inside meeting at the centre, one "
        "straight up and one to four o'clock - the ring family's dial",
    ),
    "search": (
        '<circle cx="10.6" cy="10.6" r="6.4"/>'
        '<path d="M15.3 15.3 L21 21"/>',
        "a magnifier - a ring pushed up-left of centre with a tail running "
        "off it to the bottom-right corner, the only off-centre ring",
    ),
}

ICON_NOTES: Dict[str, str] = {k: v[1] for k, v in _ICONS.items()}


def icon_names() -> List[str]:
    return sorted(_ICONS)


def icon(name: str, size: int = 20, title: Optional[str] = None,
         cls: str = "") -> str:
    """One inline, accessible <svg>.

    `title` given   -> role="img" plus a <title> child; the icon is a
                       labelled image and screen readers announce it.
    `title` omitted -> aria-hidden="true" and focusable="false"; the icon
                       is decoration beside text that already says it, and
                       announcing it twice is worse than not at all.
    """
    if name not in _ICONS:
        raise KeyError("unknown icon %r; have: %s"
                       % (name, ", ".join(icon_names())))
    try:
        size = int(size)
    except (TypeError, ValueError):
        raise ValueError("icon size must be an integer, got %r" % (size,))
    if not 8 <= size <= 64:
        raise ValueError("icon size %d outside the sane 8-64 range" % size)

    body = _ICONS[name][0]
    klass = ("wr-icon wr-icon-%s %s" % (name.replace("_", "-"), cls)).strip()
    if title:
        a11y = ' role="img"'
        label = "<title>%s</title>" % esc(title)
    else:
        a11y = ' aria-hidden="true" focusable="false"'
        label = ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" class="%s" width="%d" '
        'height="%d" viewBox="0 0 %d %d" fill="none" stroke="currentColor" '
        'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"%s>'
        '%s%s</svg>'
        % (esc(klass), size, size, ICON_GRID, ICON_GRID,
           _stroke_for(size), a11y, label, body)
    )


# --- position badges (typographic, not pictograms) --------------------------

POSITIONS: Tuple[str, ...] = ("QB", "RB", "WR", "TE", "K", "DST")
_POS_ALIAS = {"DEF": "DST", "D/ST": "DST", "DST": "DST", "PK": "K",
              "K": "K", "QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE"}


def normalize_pos(pos) -> str:
    key = str("" if pos is None else pos).strip().upper()
    return _POS_ALIAS.get(key, key)


def pos_badge(pos, title: Optional[str] = None) -> str:
    """A position chip.

    Deliberately typographic. A pictogram for "tight end" is a pictogram
    nobody can read at 20px, and the two letters already ARE the symbol
    every fantasy player knows. Monochrome on purpose: the palette's
    colours are spent on VERDICTS, and a rainbow of position colours would
    compete with the only hues that carry meaning on this page.
    """
    code = normalize_pos(pos)
    known = code in POSITIONS
    # An unknown code still renders - a league with an oddball slot should
    # see it, not a blank - but it is cut to chip length first. A chip is
    # two or three glyphs wide by definition; a feed that hands us a
    # paragraph does not get to set the column width.
    label = (code if known else trim(code, 6)) if code else "—"
    attrs = ' title="%s"' % esc(title) if title else ""
    return ('<span class="wr-pos%s%s"%s>%s</span>'
            % (" wr-pos-wide" if len(label) > 2 else "",
               "" if known else " wr-pos-unk", attrs, esc(label)))


# --- verdict chips ----------------------------------------------------------

# verdict key -> (label, css tone, icon name)
_VERDICTS = {
    "start": ("START", "start", "start"),
    "sit":   ("SIT", "sit", "sit"),
    "flex":  ("FLEX", "lean", "toss_up"),
    "even":  ("TOSS-UP", "none", "toss_up"),
}
_VERDICT_ALIAS = {
    "start": "start", "play": "start", "in": "start",
    "sit": "sit", "bench": "sit", "out": "sit",
    "flex": "flex", "lean": "flex",
    "even": "even", "toss-up": "even", "toss_up": "even",
    "tossup": "even", "split": "even",
}
_CHIP_SIZES = {"sm": 20, "md": 20, "lg": 24}
# the hover explanation every chip carries when the page gives it none -
# a glyph without a title is a glyph the reader has to go and look up
_VERDICT_TITLES = {
    "start": "START - the call is to play him",
    "sit": "SIT - the call is to bench him",
    "flex": "FLEX - a lean, not a lock",
    "even": "TOSS-UP - either call is defensible",
    None: "no verdict filed",
}


def verdict_chip(verdict, pct=None, size: str = "md",
                 title: Optional[str] = None) -> str:
    """The board's verdict language, as one chip.

    The WORD rides next to the colour so the chip survives a grayscale
    print and a colour-blind reader, and the ICON rides next to the word so
    it survives being scanned at speed. An unknown verdict is rendered as a
    hollow "no opinion filed" chip rather than guessed at - inventing a
    verdict for a source that never filed one is the exact dishonesty the
    consensus ledger exists to prevent.
    """
    if size not in _CHIP_SIZES:
        raise ValueError("chip size must be one of %s, got %r"
                         % (sorted(_CHIP_SIZES), size))
    key = _VERDICT_ALIAS.get(str("" if verdict is None else verdict)
                             .strip().lower())
    if key is None:
        label, tone, ico = "—", "unfiled", None
    else:
        label, tone, ico = _VERDICTS[key]

    glyph = icon(ico, _CHIP_SIZES[size]) if ico else ""
    pct_html = ""
    if pct is not None:
        try:
            n = int(round(float(pct)))
        except (TypeError, ValueError):
            n = None
        if n is not None:
            n = max(0, min(100, n))
            pct_html = '<span class="wr-chip-pct">%d%%</span>' % n
    attrs = ' title="%s"' % esc(title or _VERDICT_TITLES[key])
    return ('<span class="wr-chip wr-chip-%s wr-chip-%s"%s>%s'
            '<span class="wr-chip-l">%s</span>%s</span>'
            % (tone, esc(size), attrs, glyph, esc(label), pct_html))


# --- streak + matchup badges ------------------------------------------------

_STREAKS = {
    "hot": ("HOT", "hot", "hot_streak", "on a hot streak"),
    "cold": ("COLD", "cold", "cold_streak", "on a cold streak"),
}
_STREAK_ALIAS = {"hot": "hot", "heater": "hot", "up": "hot", "rising": "hot",
                 "cold": "cold", "slump": "cold", "down": "cold",
                 "falling": "cold"}


def streak_badge(state, size: str = "md") -> str:
    """hot / cold, or an honest muted STEADY with no icon at all.

    There is no "steady" pictogram in the set because there is nothing to
    draw: a player who is neither hot nor cold has no trend, and an icon
    invented to fill the slot would claim a signal that is not there.
    """
    px = _CHIP_SIZES.get(size, 20)
    key = _STREAK_ALIAS.get(str("" if state is None else state)
                            .strip().lower())
    if key is None:
        return ('<span class="wr-badge wr-badge-steady">'
                '<span class="wr-badge-l">STEADY</span></span>')
    label, tone, ico, note = _STREAKS[key]
    return ('<span class="wr-badge wr-badge-%s" title="%s">%s'
            '<span class="wr-badge-l">%s</span></span>'
            % (tone, esc(note), icon(ico, px), esc(label)))


_MATCHUPS = {
    "smash": ("SMASH", "smash", "matchup_smash",
              "a matchup to attack - this defence gives it up"),
    "avoid": ("AVOID", "avoid", "matchup_avoid",
              "a matchup to avoid - this defence is a wall"),
}
_MATCHUP_ALIAS = {"smash": "smash", "great": "smash", "plus": "smash",
                  "good": "smash", "a": "smash",
                  "avoid": "avoid", "tough": "avoid", "bad": "avoid",
                  "minus": "avoid", "f": "avoid"}


def matchup_badge(grade, size: str = "md") -> str:
    """smash / avoid, or a muted NEUTRAL badge carrying no icon."""
    px = _CHIP_SIZES.get(size, 20)
    key = _MATCHUP_ALIAS.get(str("" if grade is None else grade)
                             .strip().lower())
    if key is None:
        return ('<span class="wr-badge wr-badge-neutral">'
                '<span class="wr-badge-l">NEUTRAL</span></span>')
    label, tone, ico, note = _MATCHUPS[key]
    return ('<span class="wr-badge wr-badge-%s" title="%s">%s'
            '<span class="wr-badge-l">%s</span></span>'
            % (tone, esc(note), icon(ico, px), esc(label)))


def flag_badge(kind, size: str = "md", note: Optional[str] = None) -> str:
    """injury / bye / locked / news - the status flags beside a name."""
    px = _CHIP_SIZES.get(size, 20)
    flags = {
        "injury": ("QUESTIONABLE", "injury", "injury",
                   "an injury status is filed"),
        "bye": ("BYE", "bye", "bye", "no game this week"),
        "locked": ("LOCKED", "locked", "locked",
                   "his game has started - this is final"),
        "news": ("NEWS", "news", "news", "there is news to read"),
    }
    key = str("" if kind is None else kind).strip().lower()
    if key not in flags:
        raise KeyError("unknown flag %r; have: %s"
                       % (kind, ", ".join(sorted(flags))))
    label, tone, ico, default_note = flags[key]
    attrs = ' title="%s"' % esc(note or default_note)
    return ('<span class="wr-badge wr-badge-%s"%s>%s'
            '<span class="wr-badge-l">%s</span></span>'
            % (tone, attrs, icon(ico, px), esc(label)))


# --- stat pill --------------------------------------------------------------

_PILL_TONES = ("neutral", "good", "bad", "lean")


def stat_pill(label, value, tone: str = "neutral",
              title: Optional[str] = None) -> str:
    """A small label/value pair - xFP 14.2, RANK 8, FAAB 12%."""
    if tone not in _PILL_TONES:
        raise ValueError("pill tone must be one of %s, got %r"
                         % (list(_PILL_TONES), tone))
    attrs = ' title="%s"' % esc(title) if title else ""
    return ('<span class="wr-pill wr-pill-%s"%s>'
            '<span class="wr-pill-l">%s</span>'
            '<span class="wr-pill-v">%s</span></span>'
            % (tone, attrs, esc(label), esc(value)))


# --- sparkline --------------------------------------------------------------

def _numbers(values: Optional[Iterable]) -> List[float]:
    out: List[float] = []
    for v in (values or ()):
        if isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")):   # NaN / inf
            continue
        out.append(f)
    return out


def sparkline(values: Optional[Iterable], width: int = 72, height: int = 20,
              title: Optional[str] = None) -> str:
    """A weekly trend, as inline SVG.

    Three degenerate cases, all of which reach this function in real use
    in week 1 of a season with an empty ledger, and none of which may
    divide by zero:

      no points  -> a dashed baseline and nothing else. An empty series is
                    drawn as EMPTY, never as a flat line at zero, because a
                    flat line is a claim about the data.
      one point  -> a single dot, centred. There is no trend to draw from
                    one week and no line is drawn pretending otherwise.
      flat       -> hi == lo, so the vertical span is forced to 1.0 and
                    every point lands on the mid-line.
    """
    width = max(8, int(width))
    height = max(8, int(height))
    pts = _numbers(values)
    sw = 1.6
    pad = sw / 2.0 + 1.0
    y_top, y_bot = pad, height - pad
    x_left, x_right = pad, width - pad
    inner_w = max(0.0, x_right - x_left)
    inner_h = max(0.0, y_bot - y_top)
    mid = y_top + inner_h / 2.0

    if title:
        a11y = ' role="img"'
        label = "<title>%s</title>" % esc(title)
    else:
        a11y = ' aria-hidden="true" focusable="false"'
        label = ""
    head = ('<svg xmlns="http://www.w3.org/2000/svg" class="wr-spark" '
            'width="%d" height="%d" viewBox="0 0 %d %d" fill="none" '
            'stroke="currentColor" stroke-width="%s" stroke-linecap="round" '
            'stroke-linejoin="round"%s>%s'
            % (width, height, width, height, sw, a11y, label))

    if not pts:
        return (head + '<path class="wr-spark-empty" d="M%s %s H%s"/></svg>'
                % (_n(x_left), _n(mid), _n(x_right)))

    lo, hi = min(pts), max(pts)
    span = hi - lo
    if span <= 0:
        span = 1.0                       # flat series: never divide by zero

    def _y(v: float) -> float:
        return y_bot - ((v - lo) / span) * inner_h

    if len(pts) == 1:
        cx = x_left + inner_w / 2.0
        return (head + '<path class="wr-spark-dot" d="M%s %s h0"/></svg>'
                % (_n(cx), _n(mid)))

    step = inner_w / float(len(pts) - 1)          # len >= 2 here, always
    coords = [(x_left + i * step, _y(v)) for i, v in enumerate(pts)]
    d = "M" + " L".join("%s %s" % (_n(x), _n(y)) for x, y in coords)
    lx, ly = coords[-1]
    return (head
            + '<path class="wr-spark-line" d="%s"/>' % d
            + '<path class="wr-spark-dot" d="M%s %s h0"/>' % (_n(lx), _n(ly))
            + '</svg>')


def _n(v: float) -> str:
    """Trim float noise out of path data."""
    s = "%.2f" % float(v)
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# --- rows, sections, banners ------------------------------------------------

def player_row(name, pos=None, team=None, note=None,
               badges: Sequence[str] = (), trailing_html: str = "",
               locked: bool = False, tone: str = "") -> str:
    """One player line: badge, name, meta, status cluster, trailing slot.

    `name`, `pos`, `team` and `note` are UNTRUSTED and are escaped here.
    `badges` and `trailing_html` are trusted HTML - build them from this
    module's chips and pills, never from raw feed text.
    """
    meta_bits = [b for b in (normalize_pos(pos) if pos else None,
                             str(team).strip() if team else None) if b]
    meta = " · ".join(esc(b) for b in meta_bits)
    cluster = "".join(badges or ())
    if locked:
        cluster = flag_badge("locked",
                             note="his game has started - this is final") \
            + cluster
    klass = "wr-row" + ((" wr-row-" + tone) if tone else "")
    return (
        '<div class="%s">'
        '<div class="wr-row-id">%s<span class="wr-row-name">%s</span></div>'
        '%s%s%s</div>'
        % (esc(klass),
           pos_badge(pos) if pos else "",
           esc(name),
           ('<div class="wr-row-meta">%s</div>' % meta) if meta else "",
           ('<div class="wr-row-note">%s</div>' % esc(note)) if note else "",
           ('<div class="wr-row-tail">%s%s</div>' % (cluster, trailing_html))
           if (cluster or trailing_html) else "")
    )


def popover(summary_html: str, detail_html: str, open_: bool = False,
            cls: str = "") -> str:
    """Progressive disclosure on native <details>.

    No JS. <details> already gives keyboard focus, the Enter/Space toggle,
    the disclosure semantics and find-in-page inside the collapsed body -
    all of which a hand-rolled div-and-click widget throws away. The
    chevron rotates in CSS off the [open] attribute.

    Both arguments are trusted HTML; escape their parts with esc() first.
    """
    return (
        '<details class="wr-pop %s"%s><summary class="wr-pop-s">'
        '<span class="wr-pop-sum">%s</span>%s</summary>'
        '<div class="wr-pop-d">%s</div></details>'
        % (esc(cls), " open" if open_ else "", summary_html,
           icon("expand", 20, cls="wr-pop-chev"), detail_html)
    )


def section_header(title, count_note=None, notes: Sequence = ()) -> str:
    """The card head both pages already speak: gold rule, uppercase title,
    a dim count beside it, and muted notes under it."""
    head = esc(title)
    if count_note:
        head += ' <span class="wr-sec-n">%s</span>' % esc(count_note)
    body = "".join('<p class="wr-note">%s</p>' % esc(n)
                   for n in (notes or ()) if n)
    return ('<header class="wr-sec"><h2 class="wr-sec-h">%s</h2>%s</header>'
            % (head, body))


def banner(text, tone: str = "warn", ico: Optional[str] = "news") -> str:
    """A page-level statement of fact the reader must not miss."""
    tones = {"warn": "warn", "bad": "bad", "good": "good", "info": "info"}
    if tone not in tones:
        raise ValueError("banner tone must be one of %s, got %r"
                         % (sorted(tones), tone))
    glyph = icon(ico, 20) if ico else ""
    return ('<div class="wr-banner wr-banner-%s">%s'
            '<span class="wr-banner-t">%s</span></div>'
            % (tone, glyph, esc(text)))


def degraded_banner(title, err) -> str:
    """The honesty contract, word for word as board.py already states it.

    A section that died says so IN PLACE and carries its own error. It is
    never dropped, because a missing section reads as "nothing to report"
    and that is a lie about what the page could see.
    """
    if isinstance(err, BaseException):
        msg = trim(str(err).strip() or type(err).__name__, 240)
        kind = type(err).__name__
    else:
        msg = trim(err, 240)
        kind = ""
    detail = ("%s: %s" % (kind, msg)) if kind else msg
    return ('<div class="wr-banner wr-banner-warn wr-degraded">%s'
            '<span class="wr-banner-t"><b>SECTION DEGRADED</b> — %s. '
            'The rest of the page still stands; rerun once the feed is back '
            '(<code>--force</code> refetches).</span></div>'
            % (icon("news", 20), esc("%s — %s" % (title, detail))))


def legend(items: Sequence[Tuple[str, str]] = ()) -> str:
    """A key for the icon vocabulary. `items` is (glyph, meaning) where
    `glyph` is an icon name, or one of this module's own components (a
    status pill, an opp chip) wrapped in `raw()` so the key can explain
    everything a row prints. A plain string that is not an icon name
    raises - it is never emitted, however much it looks like markup.
    Omitted, it renders the whole icon set so a page can never ship a
    glyph the reader has no way to decode.

    Pages should prefer `legend_popover()`, which tucks this behind a "?"
    control instead of spending a block of the page on it.
    """
    pairs = list(items) if items else [(n, ICON_NOTES[n].split(" - ")[0])
                                       for n in icon_names()]
    cells = []
    for g, m in pairs:
        if isinstance(g, _Raw):
            glyph = str(g)                  # trusted: one of our components
        else:
            glyph = icon(str(g or ""), 20, title=str(m))   # KeyError otherwise
        cells.append('<span class="wr-legend-i">%s<span>%s</span></span>'
                     % (glyph, esc(m)))
    return '<div class="wr-legend">%s</div>' % "".join(cells)


# --- type scale (v4) ----------------------------------------------------------
# Phone sizes. t4 is the FLOOR: nothing on any page renders under 11px.
# t0 is the display size and is spent on exactly one rule, .wr-h1.

TYPE_SCALE: Dict[str, int] = {"t0": 26, "t1": 17, "t2": 15, "t3": 13, "t4": 11}
# From 701px the meta size steps down one pixel; the floor does not move.
TYPE_SCALE_DESKTOP: Dict[str, int] = {"t3": 12}
TYPE_FLOOR = 11
DESKTOP_MIN = 701      # the shell's phone breakpoint is max-width: 700px
# Desktop is written as the NEGATION of the phone query rather than a
# min-width, so the phone-first audits (which forbid any fixed width over
# 390px in the sheet) read it as what it is: everything that is not a phone.
DESKTOP_MQ = "not all and (max-width: %dpx)" % (DESKTOP_MIN - 1)


def type_css() -> str:
    """The scale as tokens plus the .wr-t0..t4 utility classes."""
    phone = "".join("    --wr-%s: %dpx;\n" % (k, v)
                    for k, v in sorted(TYPE_SCALE.items()))
    desk = "".join("      --wr-%s: %dpx;\n" % (k, v)
                   for k, v in sorted(TYPE_SCALE_DESKTOP.items()))
    lh = {"t0": "1.1", "t1": "1.3", "t2": "1.45", "t3": "1.4", "t4": "1.5"}
    classes = "".join("  .wr-%s { font-size: var(--wr-%s); line-height: %s; }\n"
                      % (k, k, lh[k]) for k in sorted(TYPE_SCALE))
    return (
        "\n  /* type scale: one set of sizes, t4 is the floor ------------- */\n"
        "  :root {\n%s  }\n"
        "  @media %s {\n    :root {\n%s    }\n  }\n"
        "%s" % (phone, DESKTOP_MQ, desk, classes)
    )


# --- status pill (v4) ---------------------------------------------------------
# Sleeper's Q / D / O / IR badges, as weight not hue: ink on paper with the
# gold rule when he may still play, ink FILL when he will not, ghost when
# the status is the calendar's (bye) or the clock's (locked).

# code -> (long word, weight class)
_STATUS = {
    "Q":    ("Questionable", "rule"),
    "D":    ("Doubtful", "rule"),
    "O":    ("Out", "fill"),
    "IR":   ("Injured reserve", "fill"),
    "SUSP": ("Suspended", "fill"),
    "BYE":  ("Bye week", "ghost"),
    "LOCK": ("Locked - his game has started", "ghost"),
}
_STATUS_ALIAS = {
    "q": "Q", "questionable": "Q", "gtd": "Q", "game-time decision": "Q",
    "d": "D", "doubtful": "D",
    "o": "O", "out": "O",
    "ir": "IR", "injured reserve": "IR", "injured_reserve": "IR",
    "ir-r": "IR", "reserve": "IR",
    "susp": "SUSP", "sus": "SUSP", "suspended": "SUSP", "suspension": "SUSP",
    "bye": "BYE", "bye week": "BYE",
    "lock": "LOCK", "locked": "LOCK", "started": "LOCK", "final": "LOCK",
}
STATUS_CODES: Tuple[str, ...] = tuple(_STATUS)


def normalize_status(text) -> Optional[str]:
    """A feed's status word -> one of STATUS_CODES, or None if it is not
    one we badge (PUP, NA and 'healthy' are None: no pill, no guess)."""
    key = str("" if text is None else text).strip().lower()
    return _STATUS_ALIAS.get(key)


def status_pill(code, note: Optional[str] = None) -> str:
    """Q / D / O / IR / SUSP / BYE / LOCK as a 1-4 letter pill.

    An <abbr>: the pill IS an abbreviation, and its title (the long word,
    then the note) is what the browser and the screen reader expand it
    to. Unknown codes raise - use normalize_status() to decide whether a
    feed's word earns a pill at all.
    """
    key = normalize_status(code) or str("" if code is None else code)\
        .strip().upper()
    if key not in _STATUS:
        raise KeyError("unknown status %r; have: %s"
                       % (code, ", ".join(STATUS_CODES)))
    word, weight = _STATUS[key]
    title = ("%s - %s" % (word, trim(note, 160))) if note else word
    return ('<abbr class="wr-st wr-st-%s wr-st-%s" title="%s">%s</abbr>'
            % (key.lower(), weight, esc(title), esc(key)))


# --- news dot (v4) ------------------------------------------------------------

def news_dot(unread: bool = True, title: Optional[str] = None) -> str:
    """An 8px gold dot after a name: filled while unread, hollow once read.

    It is an image with a label, not a decoration - the dot is the whole
    signal, there is no word beside it to repeat.
    """
    state = "unread" if unread else "read"
    label = title or ("unread news" if unread else "news, already read")
    return ('<span class="wr-dot wr-dot-%s" role="img" aria-label="%s" '
            'title="%s"></span>' % (state, esc(label), esc(label)))


# --- trending arrows (v4) -----------------------------------------------------
# INPUT. engine/waivers.fetch_trending_adds() returns {name_key: adds in
# the last 24h} from Sleeper's trending endpoint; a page looks the player
# up and passes direction="up" with the count as `magnitude`. Drops come
# from the same endpoint with type=drop and are passed as "down". The
# component only renders: it never decides who is trending.

TREND_STRONG = 1000     # 24h adds at which the up-arrow turns gold
_TREND_ALIAS = {"up": "up", "add": "up", "adds": "up", "rising": "up",
                "down": "down", "drop": "down", "drops": "down",
                "falling": "down"}


def _magnitude(magnitude) -> Tuple[Optional[int], bool]:
    """-> (count or None, strong?). Accepts a count or 'strong'/'mild'."""
    if magnitude is None or isinstance(magnitude, bool):
        return None, False
    if isinstance(magnitude, str):
        k = magnitude.strip().lower()
        return None, k in ("strong", "hot", "big")
    try:
        n = int(round(float(magnitude)))
    except (TypeError, ValueError):
        return None, False
    return n, n >= TREND_STRONG


def trend_arrow(direction, magnitude=None, title: Optional[str] = None) -> str:
    """up / down as a stroke arrow in ink; a STRONG up-trend is gold.

    Anything that is not up or down renders NOTHING - a player who is not
    trending has no arrow, and no glyph is invented to fill the slot.
    """
    d = _TREND_ALIAS.get(str("" if direction is None else direction)
                         .strip().lower())
    if d is None:
        return ""
    n, strong = _magnitude(magnitude)
    strong = strong and d == "up"     # the accent marks a reason to ACT
    if not title:
        verb = "trending up" if d == "up" else "trending down"
        if n is not None:
            title = "%s - %s %s in the last 24h" % (
                verb, "{:,}".format(n), "adds" if d == "up" else "drops")
        else:
            title = "%s on the waiver wire" % verb
    return ('<span class="wr-trend wr-trend-%s%s">%s</span>'
            % (d, " wr-trend-strong" if strong else "",
               icon("trend_" + d, 20, title=title)))


# --- opponent chip (v4) -------------------------------------------------------
# Sleeper's colour-coded opponent label, with the colour taken out: the
# GRADE of the matchup is the chip's weight. Gold fill = smash, gold outline
# = good, hairline = neutral, ink outline = tough, ink fill + wall = avoid.

_OPP_NOTES = {
    "smash": "%s gives this position up - a matchup to attack",
    "good": "%s is a favourable matchup for this position",
    "neutral": "%s is an average matchup for this position",
    "tough": "%s is a tough matchup for this position",
    "avoid": "%s is a wall against this position - a matchup to avoid",
    "none": "the matchup against %s is not graded",
}


def opp_chip(opponent, grade=None, home=True,
             title: Optional[str] = None) -> str:
    """'vs KC' / '@ KC' with the matchup grade encoded as weight.

    `grade` speaks the meter's vocabulary (smash/good/neutral/tough/avoid
    or A-F); anything else is the ungraded dotted chip, never a guess.
    `home` True -> 'vs', False -> '@', None -> no prefix. The title carries
    the basis sentence; pass one when the page knows the numbers.
    """
    key = _METER_ALIAS.get(str("" if grade is None else grade)
                           .strip().lower()) or "none"
    code = trim(str("" if opponent is None else opponent).strip().upper(), 4)
    shown = code or "—"
    prefix = "" if home is None else ("vs" if home else "@")
    wall = icon("wall", 12, cls="wr-opp-wall") if key == "avoid" else ""
    t = title or (_OPP_NOTES[key] % (code or "an unknown opponent"))
    return ('<span class="wr-opp wr-opp-%s" title="%s">%s'
            '<span class="wr-opp-c">%s</span>%s</span>'
            % (key, esc(t),
               ('<span class="wr-opp-p">%s</span>' % prefix) if prefix else "",
               esc(shown), wall))


# --- projected vs actual (v4) -------------------------------------------------

def _pts(value) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return "%.1f" % f


def score_cell(proj, actual=None, breakdown_html: Optional[str] = None,
               title: Optional[str] = None) -> str:
    """Before kickoff: the projection. Once an actual exists: the actual in
    bold with the projection muted beneath it. Given `breakdown_html`
    (trusted), the number becomes a <details> summary so tapping it
    reveals the breakdown - no JS, keyboard and find-in-page for free.
    """
    p, a = _pts(proj), _pts(actual)
    if a is not None:
        state = "live"
        inner = ('<span class="wr-score-a wr-num">%s</span>'
                 '<span class="wr-score-p wr-num">%s</span>'
                 % (a, ("proj " + p) if p is not None else "no projection"))
        t = title or ("%s scored, %s projected" % (a, p if p is not None
                                                   else "nothing"))
    elif p is not None:
        state = "proj"
        inner = ('<span class="wr-score-p wr-score-only wr-num">%s</span>'
                 '<span class="wr-score-l">proj</span>' % p)
        t = title or ("projected %s" % p)
    else:
        state = "none"
        inner = ('<span class="wr-score-p wr-score-only wr-num">—</span>'
                 '<span class="wr-score-l">proj</span>')
        t = title or "no projection filed"
    if breakdown_html is None:
        return ('<span class="wr-score wr-score-%s" title="%s">%s</span>'
                % (state, esc(t), inner))
    return ('<details class="wr-score wr-score-%s wr-score-x">'
            '<summary class="wr-score-s" title="%s">%s</summary>'
            '<div class="wr-score-b">%s</div></details>'
            % (state, esc(t + " - tap for the breakdown"), inner,
               breakdown_html))


# --- legend as disclosure (v4) ------------------------------------------------

def legend_popover(items: Sequence[Tuple[str, str]] = (),
                   label: str = "what the marks mean") -> str:
    """A "?" control (44px hit area, 24px ring) that opens the legend as a
    <details> popover. Same `items` as legend(); no JS."""
    return ('<details class="wr-lgd"><summary class="wr-lgd-b" title="%s" '
            'aria-label="%s"><span class="wr-lgd-q" aria-hidden="true">?'
            '</span></summary><div class="wr-lgd-p">%s</div></details>'
            % (esc(label), esc(label), legend(items)))


# --- bottom sheet (v4) --------------------------------------------------------
# HOW A PAGE USES IT
#   1. emit ui.sheet("p-12", "Ja'Marr Chase", body_html) once, anywhere in
#      <body> - beside the row is fine, the end of <main> is fine;
#   2. any element with data-sheet="p-12" opens it (the sheet's own
#      summary is one such trigger; a row's score cell can be another);
#   3. include ui.sheets_script() once, after the last sheet.
# With JS the <dialog> opens modal - a bottom sheet on phones, a centred
# card from 701px - and closes on the close button, the backdrop or
# Escape. Without JS the <details> beside it opens the same content in
# flow, so nothing is ever unreachable.

_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_id(value) -> str:
    sid = _ID_RE.sub("-", str("" if value is None else value).strip())
    return sid.strip("-") or "sheet"


def sheet(id, title, body_html: str, summary_html: Optional[str] = None,
          cls: str = "") -> str:
    """A <dialog> bottom sheet with a no-JS <details> fallback beside it.

    `title` is untrusted and escaped; `body_html` and `summary_html` are
    trusted. `summary_html` is what the fallback trigger shows; it
    defaults to the title.
    """
    sid = _safe_id(id)
    summ = summary_html if summary_html else esc(title)
    klass = ("wr-sheet-w " + cls).strip()
    return (
        '<div class="%s">'
        '<details class="wr-sheet-fb">'
        '<summary class="wr-sheet-fb-s" data-sheet="%s" title="%s">%s%s'
        '</summary></details>'
        '<dialog class="wr-sheet" id="%s" aria-labelledby="%s-t">'
        '<div class="wr-sheet-in">'
        '<div class="wr-sheet-h">%s</div>'
        '<header class="wr-sheet-head">'
        '<h3 class="wr-sheet-t wr-t1" id="%s-t">%s</h3>'
        '<button type="button" class="wr-sheet-x" data-sheet-close="1" '
        'aria-label="close">%s</button></header>'
        '<div class="wr-sheet-b">%s</div>'
        '</div></dialog></div>'
        % (esc(klass), esc(sid), esc("open: %s" % title), summ,
           icon("expand", 20, cls="wr-sheet-fb-chev"),
           esc(sid), esc(sid),
           icon("sheet_handle", 24, title="drag handle"),
           esc(sid), esc(title),
           icon("close", 24),
           body_html)
    )


def sheets_script() -> str:
    """The one tiny script that drives every sheet on a page. Include it
    ONCE, after the sheets. It degrades to the <details> fallback."""
    return (
        '<script>(function(){var d=document;'
        'd.documentElement.classList.add("wr-js");'
        'd.addEventListener("click",function(e){'
        'var t=e.target;if(!t||!t.closest)return;'
        'var o=t.closest("[data-sheet]");'
        'if(o){var g=d.getElementById(o.getAttribute("data-sheet"));'
        'if(g&&g.showModal){e.preventDefault();if(!g.open){g.showModal();}'
        'return;}}'
        'var c=t.closest("[data-sheet-close]");'
        'if(c){var p=c.closest("dialog");if(p&&p.close){p.close();}return;}'
        'if(t.tagName==="DIALOG"&&t.classList.contains("wr-sheet")&&t.open)'
        '{t.close();}});})();</script>'
    )


# --- segmented control (v4) ---------------------------------------------------

def segmented(name, options: Sequence, active, cls: str = "") -> str:
    """2-4 equal segments, 44px tall, role=tablist, gold underline on the
    active one. `options` = [(key, label)] for buttons (data-seg=key) or
    [(key, label, href)] for links - static pages pass anchors to #ids."""
    opts = list(options or ())
    if not 2 <= len(opts) <= 4:
        raise ValueError("segmented wants 2-4 options, got %d" % len(opts))
    cells = []
    for opt in opts:
        key, label = opt[0], opt[1]
        href = opt[2] if len(opt) > 2 else None
        sel = "true" if str(key) == str(active) else "false"
        if href:
            cells.append('<a class="wr-seg-a" role="tab" aria-selected="%s" '
                         'href="%s">%s</a>' % (sel, esc(href), esc(label)))
        else:
            cells.append('<button type="button" class="wr-seg-a" role="tab" '
                         'aria-selected="%s" data-seg="%s">%s</button>'
                         % (sel, esc(key), esc(label)))
    klass = ("wr-seg " + cls).strip()
    return ('<div class="%s" role="tablist" aria-label="%s">%s</div>'
            % (esc(klass), esc(name), "".join(cells)))


# --- the three-column slot row (v4) -------------------------------------------
# identity | opponent + projection | verdict. Three logical columns at phone
# width and no more: names ellipsize, codes never wrap, min-height 48px so
# the row is a finger target. With `expanded_html` the row is a <details>
# whose summary is the row itself.

def row3(identity_html: str, middle_html: str, verdict_html: str,
         expanded_html: Optional[str] = None, cls: str = "") -> str:
    """The canonical slot row. All four arguments are trusted HTML - build
    them from row3_identity(), opp_chip(), score_cell(), verdict_chip()."""
    cols = ('<div class="wr-r3-id">%s</div>'
            '<div class="wr-r3-mid">%s</div>'
            '<div class="wr-r3-v">%s</div>'
            % (identity_html, middle_html, verdict_html))
    klass = ("wr-r3 " + cls).strip()
    if expanded_html is None:
        return '<div class="%s">%s</div>' % (esc(klass), cols)
    return ('<details class="%s wr-r3-x"><summary class="wr-r3-s">%s%s'
            '</summary><div class="wr-r3-d">%s</div></details>'
            % (esc(klass), cols, icon("expand", 20, cls="wr-r3-chev"),
               expanded_html))


def row3_identity(name, pos=None, team=None, extras_html: str = "") -> str:
    """The first column: position chip, ellipsizing name, then the glyph
    cluster (status pill, news dot, trend arrow) the page hands in as
    trusted `extras_html`. `name`, `pos`, `team` are escaped here."""
    team_html = ('<span class="wr-r3-team">%s</span>'
                 % esc(str(team).strip())) if team else ""
    return ('%s<span class="wr-r3-name" title="%s">%s</span>%s%s'
            % (pos_badge(pos) if pos else "", esc(name), esc(name),
               team_html, extras_html))


# --- stylesheet -------------------------------------------------------------

_COMPONENT_CSS = """
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--wr-canvas);
    color: var(--wr-text);
    font-family: "Archivo", -apple-system, "Segoe UI", Roboto, Helvetica,
                 Arial, sans-serif;
    font-size: var(--wr-t2); line-height: 1.45;
    font-variant-numeric: tabular-nums;
    -webkit-text-size-adjust: 100%;
    -webkit-font-smoothing: antialiased;
  }
  /* three voices: display for verdict words, UI for everything, mono for
     numbers - a number is never set in the display face */
  .wr-display, h1.wr-display, h2.wr-display {
    font-family: "Archivo Black", "Archivo", -apple-system, sans-serif;
    font-weight: 400; letter-spacing: 0.01em;
  }
  .wr-num, .wr-chip-pct, .wr-pill-v, .wr-mono {
    font-family: "Spline Sans Mono", ui-monospace, SFMono-Regular, Menlo,
                 monospace;
    font-variant-numeric: tabular-nums;
  }
  a { color: var(--wr-mint); }

  /* icons ---------------------------------------------------------------- */
  .wr-icon { display: inline-block; vertical-align: -0.22em; flex: none; }

  /* position badges ------------------------------------------------------ */
  .wr-pos {
    display: inline-block; min-width: 2.35em; text-align: center;
    padding: 1px 5px; border-radius: 4px;
    background: var(--wr-raised); border: 1px solid var(--wr-hairline-2);
    color: var(--wr-muted);
    font-size: var(--wr-t4); font-weight: 700; letter-spacing: 0.9px;
    line-height: 1.5; text-transform: uppercase;
  }
  .wr-pos-wide { letter-spacing: 0.4px; }
  .wr-pos-unk { font-style: italic; letter-spacing: 0.4px; }

  /* verdict chips -------------------------------------------------------- */
  .wr-chip {
    display: inline-flex; align-items: center; gap: 4px;
    border-radius: 5px; padding: 2px 7px 2px 5px;
    border: 1px solid transparent;
    color: var(--wr-text); background: transparent;
    font-weight: 700; letter-spacing: 0.5px; white-space: nowrap;
    font-size: var(--wr-t3); line-height: 1.35;
  }
  .wr-chip-sm { font-size: var(--wr-t4); padding: 1px 6px 1px 4px; }
  .wr-chip-lg { font-size: var(--wr-t2); padding: 4px 10px 4px 7px; }
  /* verdicts by WEIGHT, never by hue: fill / ghost / dashed */
  .wr-chip-start { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                   border-color: var(--wr-chip-start); }
  .wr-chip-sit   { background: transparent; color: var(--wr-muted);
                   border-color: var(--wr-chip-sit); }
  .wr-chip-lean  { background: transparent; color: var(--wr-chip-lean);
                   border: 1px dashed var(--wr-chip-lean); }
  .wr-chip-none  { background: transparent; color: var(--wr-dim);
                   border-color: transparent; }
  .wr-chip-unfiled {
    background: transparent; color: var(--wr-dim);
    border-color: transparent;
  }
  .wr-chip-pct { opacity: 0.78; font-weight: 700; letter-spacing: 0.2px; }

  /* status badges -------------------------------------------------------- */
  .wr-badge {
    display: inline-flex; align-items: center; gap: 3px;
    border-radius: 999px; padding: 1px 8px 1px 5px;
    border: 1px solid var(--wr-hairline-2);
    background: var(--wr-raised); color: var(--wr-muted);
    font-size: var(--wr-t4); font-weight: 700; letter-spacing: 0.7px;
    white-space: nowrap; line-height: 1.6;
  }
  .wr-badge-hot   { color: var(--wr-gold);  background: var(--wr-wash-hot);
                    border-color: var(--wr-gold); }
  .wr-badge-cold  { color: var(--wr-dim);   background: var(--wr-wash-cold); }
  .wr-badge-smash { color: var(--wr-gold);  background: var(--wr-wash-hot);
                    border-color: var(--wr-gold); }
  .wr-badge-avoid { color: var(--wr-text);  background: var(--wr-wash-bad);
                    border-color: var(--wr-hairline-2); }
  /* attention is a gold RULE on ink text - never a red fill */
  .wr-badge-injury{ color: var(--wr-text);  background: var(--wr-wash-hot);
                    box-shadow: inset 3px 0 0 var(--wr-rule); }
  .wr-badge-bye   { color: var(--wr-dim); }
  .wr-badge-locked{ color: var(--wr-dim); }
  .wr-badge-news  { color: var(--wr-gold); }
  .wr-badge-steady, .wr-badge-neutral { color: var(--wr-dim); }

  /* stat pills ----------------------------------------------------------- */
  .wr-pill {
    display: inline-flex; align-items: baseline; gap: 4px;
    border: 1px solid var(--wr-hairline); border-radius: 5px;
    padding: 1px 7px; background: var(--wr-raised);
    font-size: var(--wr-t3); white-space: nowrap; line-height: 1.6;
  }
  .wr-pill-l {
    color: var(--wr-dim); font-size: var(--wr-t4); font-weight: 700;
    letter-spacing: 1px; text-transform: uppercase;
  }
  .wr-pill-v { color: var(--wr-text); font-weight: 700; }
  .wr-pill-good .wr-pill-v { color: var(--wr-mint); }
  .wr-pill-bad  .wr-pill-v { color: var(--wr-coral); }
  .wr-pill-lean .wr-pill-v { color: var(--wr-gold); }

  /* sparkline ------------------------------------------------------------ */
  .wr-spark { display: inline-block; vertical-align: middle;
              color: var(--wr-muted); }
  .wr-spark-line { stroke: currentColor; }
  .wr-spark-dot  { stroke: currentColor; stroke-width: 3.4; }
  .wr-spark-empty { stroke: var(--wr-hairline-2); stroke-dasharray: 2 3; }

  /* player rows ---------------------------------------------------------- */
  .wr-row {
    display: grid; gap: 1px 10px; align-items: baseline;
    grid-template-columns: minmax(0, 1fr) auto;
    padding: 7px 2px; border-bottom: 1px solid var(--wr-hairline);
  }
  .wr-row:last-child { border-bottom: none; }
  .wr-row-id { display: flex; align-items: center; gap: 7px;
               min-width: 0; grid-column: 1; }
  .wr-row-name { font-weight: 700; overflow-wrap: anywhere; }
  .wr-row-meta, .wr-row-note {
    grid-column: 1; color: var(--wr-muted); font-size: var(--wr-t3);
  }
  .wr-row-note { color: var(--wr-dim); }
  .wr-row-tail {
    grid-column: 2; grid-row: 1 / span 3; align-self: center;
    display: flex; flex-wrap: wrap; justify-content: flex-end;
    align-items: center; gap: 5px;
  }
  .wr-row-good { background: var(--wr-wash-good); }
  .wr-row-bad  { background: var(--wr-wash-bad); }
  .wr-row-hot  { background: var(--wr-wash-hot); }
  .wr-row-split{ background: var(--wr-wash-split); }

  /* popover (native <details>) -------------------------------------------- */
  .wr-pop { border-top: 1px solid var(--wr-hairline); }
  .wr-pop > .wr-pop-s {
    display: flex; align-items: center; gap: 8px; cursor: pointer;
    padding: 7px 2px; list-style: none; color: var(--wr-text);
  }
  .wr-pop > .wr-pop-s::-webkit-details-marker { display: none; }
  .wr-pop > .wr-pop-s:focus-visible {
    outline: 2px solid var(--wr-rule); outline-offset: 2px;
    border-radius: 4px;
  }
  .wr-pop-sum { flex: 1 1 auto; min-width: 0; }
  .wr-pop-chev { color: var(--wr-dim); transition: transform 120ms ease; }
  .wr-pop[open] > .wr-pop-s .wr-pop-chev { transform: rotate(180deg); }
  .wr-pop-d {
    padding: 2px 2px 12px; color: var(--wr-muted); font-size: var(--wr-t3);
    border-left: 2px solid var(--wr-hairline-2); margin-left: 3px;
    padding-left: 10px;
  }
  @media (prefers-reduced-motion: reduce) {
    .wr-pop-chev { transition: none; }
  }

  /* section heads + banners ---------------------------------------------- */
  .wr-sec { margin: 0 0 8px; }
  .wr-sec-h {
    margin: 0; font-size: var(--wr-t3); letter-spacing: 1.4px;
    text-transform: uppercase; color: var(--wr-gold);
  }
  .wr-sec-n { color: var(--wr-dim); letter-spacing: 0.6px; }
  .wr-note { color: var(--wr-muted); font-size: var(--wr-t3); margin: 4px 0 0; }
  .wr-banner {
    display: flex; align-items: flex-start; gap: 8px;
    border: 1px solid var(--wr-hairline-2); border-left-width: 3px;
    border-radius: 6px; padding: 9px 12px; margin: 12px 0 0;
    font-size: var(--wr-t3); background: var(--wr-raised);
  }
  .wr-banner .wr-icon { margin-top: 1px; }
  .wr-banner-t { flex: 1 1 auto; min-width: 0; }
  .wr-banner-warn { background: var(--wr-wash-hot);
                    border-color: var(--wr-gold); color: var(--wr-text); }
  .wr-banner-bad  { background: var(--wr-wash-bad);
                    border-color: var(--wr-text); }
  .wr-banner-good { background: var(--wr-wash-good);
                    border-color: var(--wr-mint); }
  .wr-banner-info { background: var(--wr-wash-split); }
  .wr-banner code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: var(--wr-t4);
  }

  /* legend ---------------------------------------------------------------- */
  .wr-legend {
    display: flex; flex-wrap: wrap; gap: 6px 16px;
    color: var(--wr-muted); font-size: var(--wr-t3);
  }
  .wr-legend-i { display: inline-flex; align-items: center; gap: 5px; }

  /* the page must never scroll sideways; wide content scrolls in its box */
  .wr-scroll { overflow-x: auto; }

  @media print {
    body { background: var(--wr-panel); }
    .wr-pop[open] > .wr-pop-d, .wr-pop > .wr-pop-d { display: block; }
  }
"""




# --- avatars + nameplates (v3) -----------------------------------------------
# A source is a FACE, not a column label. Creator avatars are fetched once
# into data/cache/avatars/<source-id>.jpg (see engine/sources.fetch_avatar)
# and embedded as data URIs - the pages stay self-contained. Anything with
# no picture gets a monogram in the identity colours, never a broken image.

from engine import assets as _assets


def _avatar_data_uri(source_id: str) -> Optional[str]:
    return _assets.avatar_data_uri(source_id)


def has_avatar(source_id: str) -> bool:
    return _assets.avatar_data_uri(source_id) is not None


def avatar_css() -> str:
    """One CSS rule per cached picture (read by engine/assets, never here)."""
    return _assets.avatar_css()


def _initials(name) -> str:
    words = [w for w in re.split(r"[\s/&()\-]+", str(name or "").strip())
             if w and w[0].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def avatar(source_id, name=None, size: int = 28, kind: Optional[str] = None,
           title: Optional[str] = None) -> str:
    """A round face for a source: the cached picture, else a monogram.

    `kind` = 'creator' draws the gold ring (a human voice); feeds get the
    hairline ring. Size in px. The name is the accessible label.
    """
    sid = str(source_id or "").strip()
    label = str(name or sid or "source")
    px = max(16, int(size))
    ring = "wr-av-creator" if (kind or "").lower() == "creator" else "wr-av-feed"
    t = ' title="%s"' % esc(title) if title else ""
    if _avatar_data_uri(sid):
        return ('<span class="wr-av wr-av-pic wr-av-pic-%s %s" role="img" '
                'aria-label="%s" style="width:%dpx;height:%dpx"%s></span>'
                % (esc(sid), ring, esc(label), px, px, t))
    ini = _initials(label)
    fs = int(round(px * (0.42 if len(ini) > 1 else 0.5)))
    # a monogram is glyph art, not text, but at avatar sizes a reader could
    # try to read it, so it obeys the type floor; only a sub-24px face
    # (the matrix column) may set its letters smaller than that
    if px >= 24:
        fs = max(TYPE_FLOOR, fs)
    return ('<span class="wr-av wr-av-mono %s" role="img" aria-label="%s" '
            'style="width:%dpx;height:%dpx;font-size:%dpx"%s>%s</span>'
            % (ring, esc(label), px, px, fs, t, esc(ini)))


def nameplate(source, weight=None, state=None, size: int = 28,
              compact: bool = False, href: Optional[str] = None,
              sub: Optional[str] = None) -> str:
    """avatar + name + weight + form. `source` is a registry dict or an id.

    compact=True is the matrix-column form: face and weight only, the name
    carried in the title so hovering answers 'who is this'.
    """
    if isinstance(source, dict):
        sid = source.get("id") or ""
        name = source.get("name") or sid
        kind = "creator" if (source.get("type") or "").lower() in (
            "youtube", "rss", "url", "paste") else "feed"
    else:
        sid = str(source or "")
        name = sid
        kind = "feed"
    w_html = ""
    if weight is not None:
        try:
            w_html = '<span class="wr-np-w wr-num">wt %d</span>' % int(
                round(float(weight)))
        except (TypeError, ValueError):
            w_html = ""
    st_html = ""
    if state:
        k = str(state).strip().lower()
        if k in ("hot", "cold"):
            st_html = streak_badge(k, "sm")
        else:
            st_html = ('<span class="wr-np-s">%s</span>'
                       % esc(str(state).upper().replace("_", "-")))
    face = avatar(sid, name, size=size, kind=kind,
                  title=name if compact else None)
    if compact:
        inner = ('%s<span class="wr-np-t wr-np-t-c">%s%s</span>'
                 % (face, w_html, st_html))
    else:
        sub_html = ('<span class="wr-np-sub">%s</span>' % esc(sub)) if sub else ""
        inner = ('%s<span class="wr-np-t"><span class="wr-np-n">%s</span>'
                 '<span class="wr-np-m">%s%s</span>%s</span>'
                 % (face, esc(name), w_html, st_html, sub_html))
    if href:
        return '<a class="wr-np wr-np-%s" href="%s">%s</a>' % (
            "c" if compact else "f", esc(href), inner)
    return '<span class="wr-np wr-np-%s">%s</span>' % (
        "c" if compact else "f", inner)


# --- matchup meter (v3) ------------------------------------------------------
# Five segments, filled from the left: how favourable the spot is. Tone by
# weight not hue - gold when it is a spot to attack, ink when it is neutral,
# dim when it is a wall. Unknown = five hollow segments and a dash; a grade
# is never invented to fill the slot.

_METER = {"smash": 5, "good": 4, "neutral": 3, "tough": 2, "avoid": 1}
_METER_ALIAS = {"smash": "smash", "great": "smash", "a": "smash",
                "good": "good", "plus": "good", "b": "good",
                "neutral": "neutral", "even": "neutral", "c": "neutral",
                "tough": "tough", "minus": "tough", "d": "tough",
                "avoid": "avoid", "bad": "avoid", "f": "avoid"}


def matchup_meter(grade, label: bool = True, title: Optional[str] = None,
                  size: str = "md") -> str:
    key = _METER_ALIAS.get(str("" if grade is None else grade).strip().lower())
    n = _METER.get(key, 0)
    tone = "hi" if n >= 4 else ("mid" if n == 3 else ("lo" if n else "none"))
    seg_w, seg_h, gap = (5, 11, 2) if size == "sm" else (6, 13, 2)
    width = 5 * seg_w + 4 * gap
    rects = []
    for i in range(5):
        x = i * (seg_w + gap)
        cls = "wr-meter-on" if i < n else "wr-meter-off"
        rects.append('<rect class="%s" x="%d" y="0" width="%d" height="%d" '
                     'rx="1.5"/>' % (cls, x, seg_w, seg_h))
    lbl = ""
    if label:
        lbl = '<span class="wr-meter-l">%s</span>' % esc(
            key.upper() if key else "—")
    t = esc(title) if title else (
        "matchup: %s" % (key if key else "unknown"))
    return ('<span class="wr-meter wr-meter-%s" title="%s">'
            '<svg class="wr-meter-svg" width="%d" height="%d" viewBox="0 0 %d %d" '
            'aria-hidden="true">%s</svg>%s</span>'
            % (tone, t, width, seg_h, width, seg_h, "".join(rects), lbl))


# --- the shell: one navigation for every page (v3) ---------------------------
# Static pages, so the nav is links between sibling files. The wordmark is the
# product name, GRADED TAKES (gradedtakes.com); "War Room" was the working
# title and survives only in internal identifiers (the wr- CSS prefix, module
# and file names, cache names), never in text a reader sees.
PRODUCT_NAME = "Graded Takes"
WORDMARK = "GRADED TAKES"

# APP MODE. The native iPhone app (ios/, "Graded Takes") shows every page
# inside a WKWebView and draws its OWN header and tab bar around it. When
# <html> carries data-app="ios" the page's shell chrome is hidden by CSS
# (see APP_MODE_CSS, appended by component_css(), and docs/APP_MODE.md);
# the markup is still emitted, so one HTML file serves the browser, the
# installed web app and the native app alike.
APP_ATTR = "data-app"
APP_VALUES = ("ios",)

NAV_PAGES = (
    ("home", "Home", "home.html"),
    ("lineup", "Lineup", "lineup-{league}-week{week}.html"),
    ("board", "Board", "board-{league}-week{week}.html"),
    ("digest", "Ledger", "digest-{league}-week{week}.html"),
    ("trades", "Trade Desk", "tradedesk-{league}-week{week}.html"),
    ("sources", "Sources", "sources.html"),
    ("model", "Model Settings", "http://127.0.0.1:8787/"),
)
_NAV_ICON = {"home": "consensus", "lineup": "start", "board": "expand", "digest": "news",
             "trades": "trade", "sources": "hot_streak", "model": "waiver_add"}


def shell(active: str, league: Optional[str] = None,
          week: Optional[int] = None, leagues: Sequence = (),
          subtitle: Optional[str] = None, title: Optional[str] = None) -> str:
    """Top bar + league switcher-as-title + mobile tab bar.
    `leagues` = [(id, name)].

    THE LEAGUE SWITCHER IS THE PAGE TITLE (audit #9). The current league's
    name is the biggest text in the bar, with a chevron; the other leagues
    sit in a <details> popover beneath it - no JS. A page with no league of
    its own (home) titles itself "All leagues" unless it passes `title`.
    The `.wr-lgs` / `.wr-lg` classes and markup are unchanged inside the
    popover, so pages that style them keep working.

    Pages that need a league (board/ledger/trade desk) link to the current
    league's file; with no league the link falls back to the first one.

    APP MODE - THE CONTRACT (docs/APP_MODE.md is the long form)
    -----------------------------------------------------------
    The native app sets ONE attribute on the root element, before first
    paint:

        <html data-app="ios">

    and the stylesheet (APP_MODE_CSS, shipped inside css() so every page
    inherits it without a renderer changing) answers with:

      * `.wr-nav` is display:none - the whole sticky header: the wordmark,
        the league switcher, the nav links, the WK badge, the theme toggle
        and the preferences gear (the prefs <details> lives inside the
        header, so its sheet goes with it);
      * `.wr-tabs` is display:none at every width - the phone tab bar;
      * the space they reserved is released: the body's bottom padding
        (60px + the home indicator, kept for the fixed tab bar) drops to
        the device's own safe-area inset (0 when the native chrome already
        encloses the web view), `--wr-nav-h` and the html scroll-padding
        go to 0 so an in-page `#anchor` lands at the very top, and the
        `.wr-nav-sub` subtitle strip is hidden with the bar it belongs to.

    Nothing else changes: cards, tables, sheets, popovers, the quiet-mode
    note and the offline banner render exactly as in a browser, and the
    markup for the header and tabs is STILL EMITTED - the same file serves
    a browser tab, the installed web app and the native app.

    What the native app provides instead: its own header (title, league
    switcher, week), its own tab bar (Home / Lineup / Board / Ledger /
    Trade), and its own theme and settings. The preferences layer
    (engine/prefs.py) still applies - its CSS keys on the same attributes
    - so the app drives it with data-theme="light|dark|broadcast",
    data-density="compact", data-type="large" and data-quiet="1" on the
    same element. In app mode the page's own scripts neither read nor
    write those attributes from storage: the theme toggle's script bails
    out, and the prefs boot script leaves whatever the app set untouched
    (prefs.boot_js), so an attribute the app writes at document start is
    the attribute the page paints with.
    """
    lg = league or (leagues[0][0] if leagues else "")
    wk = int(week) if week else 1

    def href(tpl):
        return tpl.format(league=esc(lg), week=wk)

    links = []
    tabs = []
    TAB_KEYS = ("home", "lineup", "board", "digest", "trades")   # 5 on a phone
    for key, label, tpl in NAV_PAGES:
        cur = ' aria-current="page"' if key == active else ""
        ext = ' target="_blank" rel="noopener noreferrer"' if tpl.startswith("http") else ""
        note = ' title="opens the Model Settings panel (./sources.sh must be running)"' \
            if key == "model" else ""
        links.append('<a class="wr-nav-a" href="%s"%s%s%s>%s</a>'
                     % (href(tpl), cur, ext, note, esc(label)))
        if key in TAB_KEYS:
            tabs.append('<a class="wr-tab" href="%s"%s%s>%s<span>%s</span></a>'
                        % (href(tpl), cur, ext,
                           icon(_NAV_ICON.get(key, "expand"), 22),
                           esc(label.split()[0])))
    switch = ""
    if leagues:
        items = []
        cur_name = None
        for lid, lname in leagues:
            # a page with no league of its own marks no league current
            is_cur = bool(league) and lid == lg
            cur = ' aria-current="true"' if is_cur else ""
            if is_cur:
                cur_name = lname
            target = ("board-%s-week%d.html" % (esc(lid), wk)
                      if active in ("board", "digest", "trades")
                      else "home.html#league-%s" % esc(lid))
            if active == "digest":
                target = "digest-%s-week%d.html" % (esc(lid), wk)
            if active == "trades":
                target = "tradedesk-%s-week%d.html" % (esc(lid), wk)
            if active == "lineup":
                target = "lineup-%s-week%d.html" % (esc(lid), wk)
            items.append('<a class="wr-lg" href="%s"%s>%s</a>'
                         % (target, cur, esc(lname)))
        head = title or (cur_name if league else None) or "All leagues"
        switch = (
            '<details class="wr-lgsw">'
            '<summary class="wr-lgs-t" title="switch league">'
            '<span class="wr-lgs-cur wr-display">%s</span>%s</summary>'
            '<nav class="wr-lgs" aria-label="league">%s</nav></details>'
            % (esc(head), icon("expand", 20, cls="wr-lgs-chev"),
               "".join(items)))
    elif title:
        switch = ('<span class="wr-lgs-t wr-lgs-static">'
                  '<span class="wr-lgs-cur wr-display">%s</span></span>'
                  % esc(title))
    # THE SUBTITLE IS NOT STICKY. It sits directly under the bar and
    # scrolls away with the page, so the pinned chrome is one row: a
    # 54px bar plus its rule, never the 83-156px the wrapped bar and a
    # pinned subtitle used to cost on a phone.
    sub_html = ('<div class="wr-nav-sub"><span class="wr-nav-sub-in">%s</span>'
                '</div>' % esc(subtitle)) if subtitle else ""
    return (
        '<header class="wr-nav">'
        '<div class="wr-nav-in">'
        '<a class="wr-mark" href="home.html" aria-label="%s - home">'
        '<span class="wr-mark-sq" aria-hidden="true"></span>'
        '<span class="wr-mark-t wr-display">%s</span></a>'
        '%s'
        '<nav class="wr-nav-links" aria-label="pages">%s</nav>'
        '<span class="wr-nav-week wr-num">WK %d</span>'
        '%s%s'
        '</div></header>%s'
        '<nav class="wr-tabs" aria-label="pages">%s</nav>'
        % (PRODUCT_NAME, WORDMARK, switch, "".join(links), wk, theme_toggle(),
           prefs_control(), sub_html, "".join(tabs)))


def theme_toggle() -> str:
    """Light/dark switch persisted per browser. The shell's one script (pages may add small local ones); it is the
    system, and it degrades to nothing: without JS the page follows the OS.

    APP MODE: the button is hidden with the header, and the script returns
    before touching storage - in app mode `data-theme` belongs to the
    native app (see shell()), and a stored value from an earlier browser
    session must not paint over it."""
    return (
        '<button class="wr-theme" type="button" data-wr-theme '
        'aria-label="toggle light or dark">'
        '<span class="wr-theme-l">Light</span><span class="wr-theme-d">Dark</span>'
        '</button>'
        '<script>(function(){try{var r=document.documentElement;'
        'if(r.hasAttribute("data-app"))return;'
        'var k="wr-theme";var v=localStorage.getItem(k);'
        'if(v==="light"||v==="dark"){r.setAttribute("data-theme",v);}'
        'document.addEventListener("click",function(e){'
        'var b=e.target.closest&&e.target.closest("[data-wr-theme]");'
        'if(!b)return;var cur=r.getAttribute("data-theme");'
        'var dark=cur?cur==="dark":(window.matchMedia&&matchMedia('
        '"(prefers-color-scheme: dark)").matches);'
        'var nxt=dark?"light":"dark";r.setAttribute("data-theme",nxt);'
        'try{localStorage.setItem(k,nxt);}catch(_){}});}catch(_){}})();'
        '</script>')


_V3_CSS = """
  /* avatars ------------------------------------------------------------- */
  .wr-av {
    display: inline-flex; align-items: center; justify-content: center;
    border-radius: 50%; flex: none; vertical-align: middle;
    background: var(--wr-nav); color: var(--wr-nav-text);
    font-weight: 700; letter-spacing: 0.02em; line-height: 1;
    box-shadow: 0 0 0 2px var(--wr-panel), 0 0 0 3.5px var(--wr-hairline-2);
    overflow: hidden;
  }
  .wr-av-pic { background-size: cover; background-position: center;
               background-color: var(--wr-raised); }
  .wr-av-creator { box-shadow: 0 0 0 2px var(--wr-panel),
                               0 0 0 3.5px var(--wr-rule); }

  /* nameplates ---------------------------------------------------------- */
  .wr-np { display: inline-flex; align-items: center; gap: 9px;
           color: inherit; text-decoration: none; min-width: 0; }
  .wr-np-c { flex-direction: column; gap: 5px; }
  .wr-np-t { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
  .wr-np-t-c { align-items: center; gap: 2px; }
  .wr-np-n { font-weight: 700; font-size: var(--wr-t3); overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }
  .wr-np-m { display: flex; align-items: center; gap: 6px;
             color: var(--wr-muted); font-size: var(--wr-t4); }
  .wr-np-w { color: var(--wr-gold); font-weight: 600; letter-spacing: 0.04em; }
  .wr-np-s { color: var(--wr-dim); font-size: var(--wr-t4); letter-spacing: 0.08em; }
  .wr-np-sub { color: var(--wr-dim); font-size: var(--wr-t4); }

  /* matchup meter ------------------------------------------------------- */
  .wr-meter { display: inline-flex; align-items: center; gap: 6px;
              white-space: nowrap; }
  .wr-meter-svg { display: block; }
  .wr-meter-off { fill: var(--wr-meter-lo); opacity: 0.45; }
  .wr-meter-hi  .wr-meter-on { fill: var(--wr-meter-hi); }
  .wr-meter-mid .wr-meter-on { fill: var(--wr-meter-mid); }
  .wr-meter-lo  .wr-meter-on { fill: var(--wr-meter-lo); }
  .wr-meter-l { font-size: var(--wr-t4); font-weight: 700; letter-spacing: 0.08em;
                color: var(--wr-muted); }
  .wr-meter-hi .wr-meter-l { color: var(--wr-gold); }
  .wr-meter-mid .wr-meter-l { color: var(--wr-text); }

  /* the shell ----------------------------------------------------------- */
  /* EVERY in-page anchor has to clear the pinned bar. scroll-padding-top on
     the scrolling element is the only thing that does that for `#id` jumps,
     :target, and find-in-page alike - without it a fragment lands squarely
     behind the header and the reader sees the row above the one they asked
     for. --wr-nav-h is the bar plus headroom; the subtitle strip below it
     is not sticky and is deliberately not counted. */
  :root { --wr-nav-h: 72px; }
  html { scroll-padding-top: var(--wr-nav-h); }
  .wr-nav { background: var(--wr-nav); color: var(--wr-nav-text);
            border-bottom: 3px solid var(--wr-rule);
            position: sticky; top: 0; z-index: 50; }
  .wr-nav-in { max-width: 1240px; margin: 0 auto; padding: 0 18px;
               min-height: 54px; display: flex; align-items: center; gap: 18px; }
  .wr-mark { display: inline-flex; align-items: center; gap: 9px;
             color: var(--wr-nav-text); text-decoration: none; flex: none; }
  .wr-mark-sq { width: 12px; height: 12px; background: var(--wr-rule);
                transform: rotate(45deg); border-radius: 1px; }
  .wr-mark-t { font-size: var(--wr-t2); letter-spacing: 0.08em; }
  .wr-lgs { display: flex; gap: 2px; background: var(--wr-nav-raised);
            border-radius: 7px; padding: 3px; }
  .wr-lg { color: var(--wr-nav-text); opacity: 0.72; text-decoration: none;
           font-size: var(--wr-t3); font-weight: 600; padding: 5px 10px;
           border-radius: 5px; white-space: nowrap; }
  .wr-lg[aria-current="true"] { opacity: 1; background: var(--wr-rule);
                                color: var(--wr-chip-ink); }
  .wr-nav-links { display: flex; gap: 2px; margin-left: auto; }
  .wr-nav-a { color: var(--wr-nav-text); opacity: 0.72; text-decoration: none;
              font-size: var(--wr-t3); font-weight: 600; padding: 8px 11px;
              border-radius: 6px; white-space: nowrap; }
  .wr-nav-a:hover { opacity: 1; background: var(--wr-nav-raised); }
  .wr-nav-a[aria-current="page"] { opacity: 1;
              box-shadow: inset 0 -3px 0 var(--wr-rule); border-radius: 0; }
  .wr-nav-week { font-size: var(--wr-t3); opacity: 0.8; letter-spacing: 0.06em; }
  .wr-nav-sub { display: block; background: var(--wr-nav);
                color: var(--wr-nav-text);
                border-bottom: 1px solid var(--wr-nav-line); }
  .wr-nav-sub-in { display: block; max-width: 1240px; margin: 0 auto;
                   padding: 6px 18px 8px; font-size: var(--wr-t3);
                   opacity: 0.72; }
  .wr-theme { border: 1px solid var(--wr-nav-line); background: transparent;
              color: var(--wr-nav-text); border-radius: 999px; padding: 4px 10px;
              font: inherit; font-size: var(--wr-t4); cursor: pointer; min-height: 28px; }
  .wr-theme-d { display: none; }
  :root[data-theme="dark"] .wr-theme-d { display: inline; }
  :root[data-theme="dark"] .wr-theme-l { display: none; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .wr-theme-d { display: inline; }
    :root:not([data-theme="light"]) .wr-theme-l { display: none; }
  }
  .wr-tabs { display: none; }
  @media (max-width: 700px) {
    .wr-nav-links, .wr-nav-week { display: none; }
    /* ONE ROW, and it stays one row. Wrapping was what pushed the pinned
       chrome to 83-156px - a fifth of an iPhone 13 mini - so the bar does
       not wrap: the mark and the gear hold their size and the league name
       is the thing that gives, truncating with an ellipsis inside a
       switcher that still opens the full list. */
    .wr-nav-in { gap: 10px; flex-wrap: nowrap; min-height: 44px;
                 padding: 4px 12px; }
    .wr-lgsw { min-width: 0; }
    .wr-lgs-t, .wr-lgs-static { min-width: 0; }
    .wr-lgs-cur { min-width: 0; overflow: hidden; text-overflow: ellipsis;
                  white-space: nowrap; }
    .wr-lgs { max-width: 100%; overflow-x: auto; }
    .wr-tab { min-width: 0; overflow: hidden; padding: 0 2px; }
    .wr-tab span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
    .wr-tabs { display: flex; position: fixed; left: 0; right: 0; bottom: 0;
               z-index: 50; background: var(--wr-nav); color: var(--wr-nav-text);
               border-top: 1px solid var(--wr-nav-line);
               padding-bottom: env(safe-area-inset-bottom); }
    .wr-tab { flex: 1 1 0; display: flex; flex-direction: column; align-items: center;
              justify-content: center; gap: 2px; min-height: 52px;
              color: var(--wr-nav-text); opacity: 0.7; text-decoration: none;
              font-size: var(--wr-t4); font-weight: 600; }
    .wr-tab[aria-current="page"] { opacity: 1; color: var(--wr-rule); }
    body { padding-bottom: 60px; }
  }

  /* page frame + cards: the paper, the table --------------------------- */
  .wr-page { max-width: 1240px; margin: 0 auto; padding: 22px 18px 48px; }
  .wr-card { background: var(--wr-panel); border: 1px solid var(--wr-hairline);
             border-radius: 10px; padding: 16px 18px;
             box-shadow: 0 1px 2px var(--wr-shadow); }
  .wr-card + .wr-card { margin-top: 14px; }
  .wr-table { width: 100%; border-collapse: separate; border-spacing: 0; }
  .wr-table th { text-align: left; font-size: var(--wr-t4); letter-spacing: 0.1em;
                 text-transform: uppercase; color: var(--wr-dim);
                 font-weight: 700; padding: 8px 10px;
                 border-bottom: 2px solid var(--wr-hairline-2);
                 background: var(--wr-panel); position: sticky; top: 0; z-index: 2; }
  .wr-table td { padding: 9px 10px; border-bottom: 1px solid var(--wr-hairline);
                 vertical-align: middle; }
  .wr-table tbody tr:hover td { background: var(--wr-raised); }
  .wr-table td.wr-sticky, .wr-table th.wr-sticky { position: sticky; left: 0;
                 background: var(--wr-panel); z-index: 3; }
  .wr-kicker { font-size: var(--wr-t4); letter-spacing: 0.14em; text-transform: uppercase;
               color: var(--wr-gold); font-weight: 700; margin: 0 0 6px; }
  .wr-h1 { font-size: var(--wr-t0); margin: 0 0 4px; line-height: 1.1; }
  .wr-lede { color: var(--wr-muted); margin: 0 0 14px; font-size: var(--wr-t2); }
"""

# --- embedded fonts (v3) -----------------------------------------------------
# The type is part of the identity and the pages fetch NOTHING at open time,
# so the woff2 subsets are embedded as data URIs by engine/assets.


def fonts_css() -> str:
    return _assets.fonts_css()



_V4_CSS = """
  /* status pills: weight, never hue --------------------------------------- */
  .wr-st, abbr.wr-st {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 1.9em; height: 18px; padding: 0 5px; box-sizing: border-box;
    border-radius: 4px; border: 1px solid var(--wr-hairline-2);
    background: var(--wr-panel); color: var(--wr-text);
    font-size: var(--wr-t4); font-weight: 700; letter-spacing: 0.06em;
    line-height: 1; text-transform: uppercase; white-space: nowrap;
    text-decoration: none; vertical-align: middle; cursor: help; flex: none;
  }
  .wr-st-rule  { box-shadow: inset 3px 0 0 var(--wr-rule); padding-left: 7px; }
  .wr-st-fill  { background: var(--wr-text); color: var(--wr-panel);
                 border-color: var(--wr-text); }
  .wr-st-ghost { color: var(--wr-dim); background: transparent; }

  /* news dot --------------------------------------------------------------- */
  .wr-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-left: 5px; vertical-align: middle; flex: none;
    background: var(--wr-rule); box-shadow: 0 0 0 1.5px var(--wr-rule);
  }
  .wr-dot-read { background: transparent; }

  /* trending arrows -------------------------------------------------------- */
  .wr-trend { display: inline-flex; align-items: center; flex: none;
              color: var(--wr-muted); vertical-align: middle; }
  .wr-trend-down { color: var(--wr-dim); }
  .wr-trend-up.wr-trend-strong { color: var(--wr-gold); }

  /* opponent chip: the grade is the weight ---------------------------------- */
  .wr-opp {
    display: inline-flex; align-items: center; gap: 3px; height: 20px;
    padding: 0 6px; box-sizing: border-box; border-radius: 5px;
    border: 1px solid var(--wr-hairline); color: var(--wr-text);
    font-size: var(--wr-t4); font-weight: 700; letter-spacing: 0.04em;
    white-space: nowrap; cursor: help; flex: none;
  }
  .wr-opp-p { font-weight: 600; color: var(--wr-muted); }
  .wr-opp-smash { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                  border-color: var(--wr-chip-start); }
  .wr-opp-smash .wr-opp-p { color: var(--wr-chip-ink); }
  .wr-opp-good  { border: 1.5px solid var(--wr-rule); }
  .wr-opp-neutral { border-color: var(--wr-hairline); }
  .wr-opp-tough { border: 1.5px solid var(--wr-text); }
  .wr-opp-avoid { background: var(--wr-text); color: var(--wr-panel);
                  border-color: var(--wr-text); }
  .wr-opp-avoid .wr-opp-p { color: var(--wr-panel); opacity: 0.8; }
  .wr-opp-none  { color: var(--wr-dim); border-style: dotted; }
  .wr-opp-wall  { margin-left: 1px; }

  /* projected vs actual ---------------------------------------------------- */
  .wr-score { display: inline-flex; flex-direction: column;
              align-items: flex-end; line-height: 1.15; position: relative; }
  .wr-score-p { font-size: var(--wr-t3); color: var(--wr-muted); }
  .wr-score-only { font-size: var(--wr-t2); color: var(--wr-text);
                   font-weight: 600; }
  .wr-score-none .wr-score-only { color: var(--wr-dim); }
  .wr-score-l { font-size: var(--wr-t4); color: var(--wr-dim);
                letter-spacing: 0.08em; text-transform: uppercase; }
  .wr-score-a { font-size: var(--wr-t1); font-weight: 700; color: var(--wr-text); }
  .wr-score-live .wr-score-p { font-size: var(--wr-t4); }
  /* A TAP TARGET IS TWO-DIMENSIONAL. min-height alone made this 44px tall
     and 37.6-40px wide - a score is 3-4 glyphs, so the summary shrink-wraps
     to the number and the 44px bar was only half met. Measured on the board
     at 375/390/430: every one of these summaries was under width. */
  details.wr-score > .wr-score-s {
    list-style: none; cursor: pointer; display: flex; flex-direction: column;
    align-items: flex-end; justify-content: center;
    min-height: 44px; min-width: 44px;
    padding: 0 2px; border-radius: 4px;
  }
  details.wr-score > .wr-score-s::-webkit-details-marker { display: none; }
  .wr-score-s:focus-visible { outline: 2px solid var(--wr-rule);
                              outline-offset: 2px; }
  .wr-score-x[open] > .wr-score-s { box-shadow: inset 0 -2px 0 var(--wr-rule); }
  .wr-score-b {
    position: absolute; right: 0; top: 100%; z-index: 20;
    min-width: 220px; max-width: 320px; padding: 10px 12px; text-align: left;
    background: var(--wr-panel); border: 1px solid var(--wr-hairline-2);
    border-radius: 8px; box-shadow: 0 6px 18px var(--wr-shadow);
    font-size: var(--wr-t3); color: var(--wr-text); font-weight: 400;
  }

  /* legend as a "?" disclosure ---------------------------------------------- */
  .wr-lgd { display: inline-block; position: relative; }
  .wr-lgd > .wr-lgd-b {
    list-style: none; cursor: pointer; display: inline-flex;
    align-items: center; justify-content: center;
    width: 44px; height: 44px; border-radius: 50%;
  }
  .wr-lgd > .wr-lgd-b::-webkit-details-marker { display: none; }
  .wr-lgd-q {
    display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 50%; box-sizing: border-box;
    border: 1.5px solid var(--wr-hairline-2); color: var(--wr-muted);
    font-size: var(--wr-t3); font-weight: 700; line-height: 1;
  }
  .wr-lgd[open] .wr-lgd-q, .wr-lgd-b:hover .wr-lgd-q {
    border-color: var(--wr-gold); color: var(--wr-gold); }
  .wr-lgd-b:focus-visible { outline: 2px solid var(--wr-rule);
                            outline-offset: -2px; }
  .wr-lgd-p {
    position: absolute; right: 0; top: 100%; z-index: 30;
    width: min(360px, 92vw); padding: 12px 14px; box-sizing: border-box;
    background: var(--wr-panel); border: 1px solid var(--wr-hairline-2);
    border-radius: 10px; box-shadow: 0 8px 24px var(--wr-shadow);
  }
  .wr-lgd-p .wr-legend { flex-direction: column; gap: 8px;
                         font-size: var(--wr-t3); color: var(--wr-text); }

  /* bottom sheet ------------------------------------------------------------- */
  .wr-sheet-w { display: block; }
  .wr-sheet-fb > .wr-sheet-fb-s {
    list-style: none; cursor: pointer; display: inline-flex;
    align-items: center; gap: 6px; min-height: 44px; padding: 0 4px;
    color: var(--wr-mint); font-weight: 600; font-size: var(--wr-t3);
    border-radius: 6px;
  }
  .wr-sheet-fb > .wr-sheet-fb-s::-webkit-details-marker { display: none; }
  .wr-sheet-fb-chev { color: var(--wr-dim); }
  .wr-sheet-fb-s:focus-visible { outline: 2px solid var(--wr-rule);
                                 outline-offset: 2px; }
  .wr-sheet { border: 0; padding: 0; margin: 0; box-sizing: border-box;
              background: var(--wr-panel); color: var(--wr-text); }
  /* no JS: opening the <details> shows the sheet in flow, as a card */
  .wr-sheet-fb[open] + .wr-sheet:not([open]) {
    display: block; position: static; width: auto; max-width: none;
    max-height: none; margin-top: 8px; border: 1px solid var(--wr-hairline-2);
    border-radius: 10px; box-shadow: 0 1px 2px var(--wr-shadow);
  }
  .wr-sheet-fb[open] + .wr-sheet:not([open]) .wr-sheet-h,
  .wr-sheet-fb[open] + .wr-sheet:not([open]) .wr-sheet-x { display: none; }
  /* JS: a bottom sheet on phones */
  .wr-sheet[open] {
    position: fixed; left: 0; right: 0; bottom: 0; top: auto;
    width: 100%; max-width: 100%; min-height: 40vh; max-height: 60vh;
    margin: 0; border-radius: 16px 16px 0 0; overflow: auto;
    box-shadow: 0 -8px 32px var(--wr-shadow);
    padding-bottom: env(safe-area-inset-bottom);
  }
  .wr-sheet::backdrop { background: var(--wr-shadow); }
  .wr-sheet-in { padding: 6px 16px 18px; }
  .wr-sheet-h { display: flex; justify-content: center;
                color: var(--wr-hairline-2); padding: 2px 0 4px; }
  .wr-sheet-h .wr-icon { stroke-width: 4; }
  .wr-sheet-head { display: flex; align-items: center; gap: 10px;
                   padding-bottom: 8px; margin-bottom: 10px;
                   border-bottom: 1px solid var(--wr-hairline); }
  .wr-sheet-t { margin: 0; flex: 1 1 auto; min-width: 0;
                font-size: var(--wr-t1); line-height: 1.3; }
  .wr-sheet-x {
    flex: none; width: 44px; height: 44px; margin-right: -12px; border: 0;
    background: transparent; color: var(--wr-muted); border-radius: 50%;
    cursor: pointer; display: inline-flex; align-items: center;
    justify-content: center; padding: 0;
  }
  .wr-sheet-x:hover { color: var(--wr-text); background: var(--wr-raised); }
  .wr-sheet-x:focus-visible { outline: 2px solid var(--wr-rule);
                              outline-offset: -2px; }
  .wr-sheet-b { font-size: var(--wr-t2); }
  @media not all and (max-width: 700px) {
    /* from 701px up the sheet is a centred modal card */
    .wr-sheet[open] {
      top: 50%; left: 50%; right: auto; bottom: auto;
      transform: translate(-50%, -50%); width: min(560px, 92vw);
      min-height: 0; max-height: 80vh; border-radius: 12px; padding-bottom: 0;
    }
    .wr-sheet[open] .wr-sheet-h { display: none; }
  }

  /* segmented control -------------------------------------------------------- */
  .wr-seg { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
            height: 44px; margin: 0 0 12px;
            border-bottom: 1px solid var(--wr-hairline); }
  .wr-seg-a {
    display: flex; align-items: center; justify-content: center;
    height: 44px; padding: 0 8px; border: 0; background: transparent;
    color: var(--wr-muted); font: inherit; font-size: var(--wr-t3);
    font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    text-decoration: none; cursor: pointer; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis; border-radius: 4px 4px 0 0;
  }
  .wr-seg-a[aria-selected="true"] { color: var(--wr-text);
                                    box-shadow: inset 0 -3px 0 var(--wr-rule); }
  .wr-seg-a:hover { color: var(--wr-text); background: var(--wr-raised); }
  .wr-seg-a:focus-visible { outline: 2px solid var(--wr-rule);
                            outline-offset: -2px; }

  /* the three-column slot row ------------------------------------------------ */
  .wr-r3 {
    display: grid; grid-template-columns: minmax(0, 1fr) auto auto;
    align-items: center; column-gap: 10px; min-height: 48px;
    padding: 4px 2px; border-bottom: 1px solid var(--wr-hairline);
  }
  .wr-r3:last-child { border-bottom: none; }
  .wr-r3-id { display: flex; align-items: center; gap: 7px; min-width: 0;
              font-size: var(--wr-t2); font-weight: 700; }
  .wr-r3-id > * { flex: none; }
  .wr-r3-name { flex: 0 1 auto; min-width: 0; overflow: hidden;
                white-space: nowrap; text-overflow: ellipsis; }
  .wr-r3-team { color: var(--wr-dim); font-weight: 600;
                font-size: var(--wr-t4); letter-spacing: 0.06em; }
  .wr-r3-mid { display: flex; align-items: center; justify-content: flex-end;
               gap: 8px; white-space: nowrap; }
  .wr-r3-v { display: flex; align-items: center; justify-content: flex-end; }
  details.wr-r3 { display: block; padding: 0; }
  details.wr-r3 > .wr-r3-s {
    display: grid; grid-template-columns: minmax(0, 1fr) auto auto 24px;
    align-items: center; column-gap: 10px; min-height: 48px;
    padding: 4px 2px; list-style: none; cursor: pointer;
  }
  details.wr-r3 > .wr-r3-s::-webkit-details-marker { display: none; }
  .wr-r3-s:focus-visible { outline: 2px solid var(--wr-rule);
                           outline-offset: -2px; border-radius: 4px; }
  .wr-r3-chev { color: var(--wr-dim); transition: transform 120ms ease; }
  .wr-r3[open] > .wr-r3-s .wr-r3-chev { transform: rotate(180deg); }
  .wr-r3-d { padding: 4px 2px 12px; font-size: var(--wr-t3);
             color: var(--wr-muted); }
  @media (max-width: 700px) {
    .wr-r3, details.wr-r3 > .wr-r3-s { column-gap: 8px; }
    .wr-r3-mid { gap: 6px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .wr-r3-chev, .wr-lgs-chev { transition: none; }
  }

  /* the shell's title switcher ------------------------------------------------ */
  .wr-lgsw { position: relative; flex: 0 1 auto; min-width: 0; }
  .wr-lgsw > .wr-lgs-t, .wr-lgs-static {
    list-style: none; cursor: pointer; display: inline-flex;
    align-items: center; gap: 6px; min-height: 44px; max-width: 100%;
    padding: 0 4px; color: var(--wr-nav-text); border-radius: 6px;
  }
  .wr-lgs-static { cursor: default; }
  .wr-lgsw > .wr-lgs-t::-webkit-details-marker { display: none; }
  .wr-lgs-t:focus-visible { outline: 2px solid var(--wr-rule);
                            outline-offset: -2px; }
  .wr-lgs-cur { font-size: var(--wr-t1); letter-spacing: 0.02em;
                min-width: 0; overflow: hidden; text-overflow: ellipsis;
                white-space: nowrap; }
  .wr-lgs-chev { color: var(--wr-nav-text); opacity: 0.7; flex: none;
                 transition: transform 120ms ease; }
  .wr-lgsw[open] > .wr-lgs-t .wr-lgs-chev { transform: rotate(180deg); }
  .wr-lgsw > .wr-lgs {
    position: absolute; left: 0; top: 100%; z-index: 60;
    flex-direction: column; min-width: 200px; max-width: min(320px, 90vw);
    overflow: visible; padding: 4px; border-radius: 8px;
    background: var(--wr-nav-raised); border: 1px solid var(--wr-nav-line);
    box-shadow: 0 10px 28px var(--wr-shadow);
  }
  .wr-lgsw > .wr-lgs .wr-lg { display: flex; align-items: center;
                              min-height: 44px; padding: 8px 12px;
                              font-size: var(--wr-t2); }
"""


# APP MODE (docs/APP_MODE.md). One attribute on the root element -
# <html data-app="ios"> - and the page's own shell chrome steps aside for
# the native app's. Every selector is anchored on html[data-app="ios"],
# which is (0,1,1) specific: it beats the bare `body` and `:root` rules the
# component sheet and engine/pwa.py's safe-area layer write, whatever the
# order the layers are concatenated in, and it can never fire outside the
# app. Nothing here touches a card, a table, a sheet or a popover.
APP_MODE_CSS = """
  /* app mode: the native app draws the header and the tab bar ----------- */
  html[data-app="ios"] .wr-nav,
  html[data-app="ios"] .wr-nav-sub,
  html[data-app="ios"] .wr-tabs { display: none; }
  /* no pinned bar: in-page anchors land at the very top ... */
  html[data-app="ios"] { --wr-nav-h: 0px; scroll-padding-top: 0; }
  /* ... and the 60px (+ home indicator) the fixed tab bar reserved goes
     back to the page. The device's own bottom inset is all that is left,
     and it is 0 when the native chrome already encloses the web view. */
  html[data-app="ios"] body { padding-bottom: env(safe-area-inset-bottom, 0px); }
"""


def component_css() -> str:
    """The layers this module OWNS - the type scale and every component
    rule - without the fonts, the tokens, the avatar rules or the optional
    prefs layer. This is the sheet tests/ui_test.py audits for the type
    scale: every font-size in it is a scale token or a scale number.
    APP_MODE_CSS rides last so the app-mode contract reaches every page
    that includes css() without a renderer changing."""
    return type_css() + _COMPONENT_CSS + _V3_CSS + _V4_CSS + APP_MODE_CSS


def css() -> str:
    """The whole stylesheet: tokens in all three theme states, the type
    scale, then the components - which reference nothing but `var(--wr-*)`
    - then the v3 layer (avatars, nameplates, meter, shell, page frame),
    the v4 layer (pills, dots, arrows, opp chips, scores, sheets, rows) and
    one rule per cached avatar picture."""
    return (fonts_css() + tokens_css() + component_css()
            + avatar_css() + _pwa_css() + _prefs_css())


def _pwa_css() -> str:
    """Optional layer: engine/pwa.py's safe-area padding for an installed
    home-screen window. Absent -> nothing. It sits BEFORE the prefs layer
    so the reader's own preferences still win every tie."""
    try:
        from engine import pwa as _pwa
    except Exception:  # noqa: BLE001 - the layer is optional by design
        return ""
    try:
        return _pwa.safe_area_css()
    except Exception:  # noqa: BLE001
        return ""


def _prefs_css() -> str:
    """Optional layer: engine/prefs.py (themes, density, type scale, layout
    preferences) adds its CSS here when present. Absent -> nothing."""
    try:
        from engine import prefs as _prefs
    except Exception:  # noqa: BLE001 - the layer is optional by design
        return ""
    try:
        return _prefs.css()
    except Exception:  # noqa: BLE001
        return ""


def prefs_control() -> str:
    """The shell's preferences control, from engine/prefs.py when present."""
    try:
        from engine import prefs as _prefs
        return _prefs.control()
    except Exception:  # noqa: BLE001
        return ""


def prefs_boot() -> str:
    """Pre-paint script applying stored preferences (engine/prefs.py)."""
    try:
        from engine import prefs as _prefs
        return _prefs.boot_script()
    except Exception:  # noqa: BLE001
        return ""


# THE REFERRER POLICY IS A PRIVACY LOCK, NOT A NICETY.
# Published pages live at an unguessable path — https://host/<token>/… — and
# that token is what keeps one reader's pages private from another before any
# login happens. A browser puts the FULL current URL in the Referer header of
# every outbound request, so one tap on "Set lineup on ESPN" would hand the
# secret path to ESPN, and any embedded third-party asset would hand it to
# that host. `no-referrer` sends the header nowhere, ever. It costs nothing:
# no page here needs a referrer, and the host platforms do not read one.
REFERRER_POLICY = "no-referrer"


def humanize_error(err, fallback: str = "the feed did not answer") -> str:
    """An exception, rewritten for someone who is not a programmer.

    Degradation notes are a promise this product keeps - a section that
    cannot speak says so. But the promise is to a READER, and a reader is
    not served by `RuntimeError: Could not fetch https://github.com/...`.
    Two things come out: the exception CLASS NAME, which means nothing to
    them, and any URL, which is noise on a page and a needless mention of a
    private path's neighbours. The MEANING stays - what failed, and the
    status code if there was one.
    """
    text = str(err if not isinstance(err, BaseException) else err).strip()
    if isinstance(err, BaseException):
        text = str(err).strip() or err.__class__.__name__
    if not text:
        return fallback
    text = re.sub(r"\b[A-Za-z_]*(?:Error|Exception)\b:?\s*", "", text)
    text = re.sub(r"https?://\S+", "the feed", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—:;,")
    return text or fallback


def referrer_meta() -> str:
    return '<meta name="referrer" content="%s">' % REFERRER_POLICY


def head_tags() -> str:
    """The installable-app <head> set, from engine/pwa.py when present, and
    the referrer policy that protects the published token path.

    THE ONE HOOK. Every renderer already calls `style_tag()` and drops the
    result in <head>, so emitting the app tags from there is what let ten
    pages become installable without a line changing in any of the six
    renderers. Absent engine/pwa.py -> nothing, and the pages are exactly
    what they were.
    """
    try:
        from engine import pwa as _pwa
        app_tags = _pwa.head_tags()
    except Exception:  # noqa: BLE001 - the layer is optional by design
        app_tags = ""
    # The policy ships whether or not the app layer does.
    return referrer_meta() + app_tags


def style_tag() -> str:
    # prefs_boot() STAYS FIRST: it is a pre-paint script and anything ahead
    # of it is a frame of the wrong theme. The app tags follow it and the
    # stylesheet follows them.
    return prefs_boot() + head_tags() + "<style>%s</style>" % css()
