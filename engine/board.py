"""THE BOARD: every roster decision and every voice on one page.

    python -m engine.board --league espn-1 --week 3
    ./board.sh espn-1 3          (wrapper - opens the page)

Writes board-<league>-week<N>.html to the project root (atomic tmp+replace,
same discipline as engine/digest.py and engine/strip.py) and prints the
absolute path as its LAST stdout line so board.sh can open it. The page is
static HTML that fetches nothing but its typefaces - no external
stylesheet, no image (every source face is embedded), no data - and reads
in light or dark through the shared CSS tokens.

WHAT IT ANSWERS. The digest is a briefing you read top to bottom; the board
is a picture you scan. One question drives the whole layout: "who am I
starting, benching, adding and shopping - and where do the voices I listen
to disagree with my model?" Four sections, one league per page:

  1. MASTHEAD    league, week, record, and the coverage line - how many
                 rosters are actually known and which sources are enabled
                 at what weight, each as a nameplate. The page never opens
                 with a number it cannot support.
  2. THE BOARD   the centrepiece, ordered by CERTAINTY and not by roster
                 order - see DECISION CARDS below. THE CALLS first (one
                 versus card per player who genuinely needs deciding),
                 then LOCKED IN and BENCH as one compact row each, then
                 THE GRID - the old source-by-source matrix, kept intact
                 behind the segmented control's All.
  3. WIRE        waiver shortlist and named trade targets rendered in the
                 SAME matrix shape, so a candidate can be compared to an
                 owned player at a glance - the model column carries the
                 add verdict (FAAB band or burn-priority) or the trade
                 verdict instead of a start/sit.
  4. LEAGUE      the other teams as compact columns with their positional
                 surplus/hole tags, my cross-league exposure highlighted,
                 and named trade targets marked on the roster that holds
                 them.
  5. SCOREBOARD  one row per source: nameplate, the decay-blended headline
                 hit rate with the label that says what it is made of,
                 sample size, form state, streak, sparkline and provenance
                 - the "should I listen to this voice" answer, with the
                 honest NO-DATA state for creators who have never been
                 graded. The full receipt per source is sources.html.

DECISION CARDS - THE ORGANISING PRINCIPLE IS CERTAINTY
======================================================
The board used to LEAD with the source-by-source matrix: every rostered
player a row, every enabled source a column. It works, and it is still
here - but it spends most of its width showing AGREEMENT, which is the
least interesting thing on the page. On week 1 of the ESPN league twelve
of its seventeen rows drew the same verdict from every voice that spoke.
So the lead is now the part that is UNDECIDED, and the matrix is one view
behind the switch rather than the default.

  THE CALLS. One card per player who genuinely needs a decision, and a
  player qualifies on exactly four derivable grounds (call_reasons):

    1. THE ROOM SPLITS - divergence_level == LVL_SPLIT: the voices point
       both ways.
    2. THE TOP-WEIGHTED SOURCE DISSENTS - LVL_TOP, consensus' own
       top_disagrees, which supersedes the plain split rather than
       doubling it.
    3. THE MATCHUP CONTRADICTS A ROOM THAT AGREES - a settled START into
       an AVOID, or a settled SIT into a SMASH. Only the two ENDS of the
       scale count; NEUTRAL / GOOD / TOUGH argue with nobody.
    4. engine/dk's DST or K hold-vs-stream verdict is STREAM or TOSS-UP.

  Nothing else raises a card, and a card names which ground raised it -
  "this is a call because..." - so the section can never read as an
  editor's hunch.
  A CONTRADICTED UNANIMOUS START IS NOT A BENCH RECOMMENDATION. When every
  voice says START into an AVOID matchup, the card says TEMPER
  EXPECTATIONS and states the matchup evidence. It does not suggest
  sitting him: the room was unanimous and the matchup is context, and the
  page has no basis for overriding seven voices with one grade.
  A LOCKED ROW IS NOT A CALL. Once his game has kicked off the decision is
  over, so a locked row never raises a card however split the room was.
  The count of rows held back that way is printed, never silently dropped.
  THE VERSUS LAYOUT. START side | model gutter | SIT side. Each side lists
  the sources on it as ui.avatar faces with their weights and their own
  words where a quote exists; the gutter carries the model's verdict chip
  with its percentage, the opponent chip and the matchup meter with its
  basis sentence. Beneath: the WHY line when one can be derived
  (call_why - weight overrode the voice majority, or the lineup seated a
  lower-polling player on projection), the projection for BOTH men when
  the slot is what decided it, and the Agree / Override affordances.
  AGREE / OVERRIDE ARE NOT WIRED, AND SAY SO. They are DISABLED buttons -
  genuinely non-interactive, and announced as disabled rather than merely
  drawn grey - and one line under them states in words that nothing on
  this page records or remembers a decision. A control that looks like it
  saves and does not is worse than no control.

  LOCKED IN / BENCH. Everything that does NOT need deciding is one compact
  row: position badge, name (one line, ellipsis, never wrapped), opponent
  chip, projection, a strip of the source faces (a gold ring voted START,
  a grey ring voted SIT, a faint ring filed nothing) and the verdict chip.
  Listed, never summarised away: the group header states the count, so a
  reader can always see that the quiet part of the roster is all there.
  THE GRID. The full matrix, unchanged in substance, behind All.

THE DESIGN SYSTEM (engine/ui.py v3) - and what changed in this skin
====================================================================
Light editorial paper is the default identity, the shell is navy, and there
is ONE accent: gold. There is NO green and NO red anywhere on this page.
The verdict language is encoded by WEIGHT, not hue - ui.verdict_chip:
a gold fill is START, a ghost outline is SIT, a dashed outline is a lean -
and attention is a gold RULE, never a coloured word. The old board's own
.chip.good/.chip.bad recipes and its --mint/--coral tints are gone;
tallies are plain ink numbers with the chip beside them.

  SOURCES ARE FACES. A column header is ui.nameplate(source, weight, state,
  compact=True): the source's cached picture (or its monogram), its weight,
  and its current form, with the full name in the header's title. The model
  column is headed by a monogram nameplate for YOUR MODEL. The versus
  cards, the compact rows' face strip and the dossier use the same faces,
  so a voice looks the same everywhere it speaks.
  MATCHUPS ARE METERS. ui.matchup_meter - five segments filled from the
  left - replaces the SMASH/AVOID badge in the drawer and the dialog. It
  carries the grade, the basis and engine/matchups.py's evidence sentence.
  ONE SHELL. ui.shell() is the first thing in <body>: the navy bar, the
  league switcher between the leagues' board files, the page links and the
  mobile tab bar. Content lives in <main class="wr-page">; every section is
  a .wr-card; the grid is a .wr-table inside a .wr-scroll box with a
  sticky header row and a sticky player column.

THE UI PRINCIPLES, AND WHICH CHOICE SERVES WHICH
================================================
The v1 matrix put everything on the row: chip, percentage, agreement class,
evidence sentence, and the rest hidden in `title=` attributes nobody hovers.
It read well and it did not scale. Five named principles replaced it, and
every structural choice below is annotated in the code with the principle
it serves so the next edit can tell decoration from load-bearing. They
carry over to the decision cards unchanged - a card, a compact row and a
grid row are three densities of the same object.

  PROGRESSIVE DISCLOSURE (Nielsen). A row's default state shows only what
  a start/sit decision needs AT A GLANCE: the verdict chip per source, the
  model column, and the divergence marker. Everything with a longer
  reading time - the quotes, the weighted arithmetic, the matchup evidence,
  each source's record - lives one level down, behind a <details> drawer
  whose <summary> carries a PEEK (a one-line preview of what is inside).
  A bare chevron makes the reader pay a click to find out whether paying
  the click was worth it; the peek is what makes the disclosure honest.
  Rows collapse by default. Divergent rows (SPLIT and above) default OPEN,
  because those are the rows that need thought and the ones the reader
  came for - defaults should favour the decision, not the tidy screenshot.

  DEFERRED DETAIL / POP-OUT (the "focus" half of focus+context). The row
  keeps CONTEXT; the pop-out gives FOCUS. Clicking a player name opens the
  full dossier in a native <dialog>: every source's verdict with its own
  words, the matchup meter and its evidence, the model's weighted math
  written out term by term, and each source's season record. <dialog> +
  showModal() is chosen over a hand-rolled div because it brings the top
  layer, the ::backdrop, inert background content, Escape-to-dismiss and a
  real focus trap for free - all of which a div re-implements badly.
  THE CONTENT IS NEVER JS-ONLY. The dossier lives in the document as the
  <details> drawer described above. With no JavaScript that drawer is the
  feature; the script only PROMOTES it into the dialog. Nothing on this
  page is reachable only by running code (see NO SCRIPT, ONE EXCEPTION).
  Precisely: with scripting off, the player-name link is an ordinary
  fragment jump to that player's drawer, :target highlights it, and the
  drawer's own <summary> opens it by click or keyboard. The stronger claim
  - that a browser auto-expands a <details> containing the fragment target
  - is in the spec but is NOT shipped everywhere; it was tried against a
  real browser here, the drawer stayed shut, and the design was changed
  rather than the claim kept.

  REPUTATION AT THE POINT OF USE. A dissenting chip is only actionable if
  you know whether that voice has been right lately, and making the reader
  cross-reference a legend at the bottom of the page is making the reader
  do a join. So every source column header carries the source's weight AND
  its streak state from engine/performance.py, right above its own column
  of chips. Today every state is NO-DATA and that IS the finding.

  SCANNABILITY (Fitts/Tufte housekeeping). The header row and the player
  column are sticky, so a chip 9 columns right is still attributable to a
  row and a source while scrolling. Every player is one <tbody>, which
  gives the row band a real element to hang a background on and keeps the
  drawer bound to its player. tabular-nums everywhere so percentages form
  a column. Under 700px the table restructures into stacked cards - each
  cell carrying its own column label - rather than making a phone drag a
  1000px-wide grid sideways; the page itself never scrolls sideways.

  RESPECT THE EXISTING LANGUAGE. Chips, faces, meters, icons, badges and
  the shell come from engine/ui.py, not from a second hand-rolled palette.
  That is the whole reason ui.py exists (see its docstring); the board's
  job is to compose. The two things ui.py lacks - a labelled chip for a
  non-verdict model call (BURN, FAAB 12%, TRADE FOR) and nothing else - are
  built locally below from the same classes and tokens, and say so.

V4 - THE CALL AS A PERCENTAGE, THE NUMBER YOU TAP, LOCKS, THE SWITCH
=====================================================================
Layout-independent additions: every one hangs on a row and its cells, so
all four of them survived the move from the heat grid to decision cards
intact - a card, a compact row and a grid cell draw the same call, the
same number, the same padlock.

  THE CALL IS A PERCENTAGE. The model column reads "START · 67% of the
  room": the share of the room's WEIGHT behind the call, over the sources
  that voted. Beneath it, ONE line of WHY whenever the percentage alone
  would mislead - and only when it can be derived: weight_why() when the
  call is not the simple majority of voices ("START on weight: 1 of 3
  voices carry 52% of the room; the 2 dissenters share 48%"), slot_why()
  when the lineup seated a lower-polling player on projection ("Pollard
  polls higher for START (70% vs 63%) but the lineup fills the W/R/T on
  projection: Dowdle 12.4 vs Pollard 10.1"). No third source; no line
  when nothing can be derived. Beside the chip, the matchup as a 1-5
  rating (ui.opp_chip + ui.matchup_meter) with the basis sentence - year
  and games - in its title.
  TAP THE NUMBER. Each roster row carries its weekly projection as a
  score cell (ui.score_cell); tapping it opens the breakdown: which feed
  the number came from and the blend rule, the room's votes, the matchup
  (stated as context - the projection is NOT adjusted by it), and the
  actual once the game is played, bold, with the projection muted beside
  it. No projection filed prints a dash, never 0.0.
  LOCK STATE. A row whose game has kicked off - decided from the nflverse
  schedule's kickoff_iso against one fixed clock per render, and from
  nothing else - carries the padlock glyph, is muted to 60%, and its
  verdict chip becomes LOCKED with the pre-kickoff call kept beside it. A
  day-only kickoff, a missing or unreadable time, a schedule that could
  not be read: never locked, and the row says why. Actuals are asked for
  only once something has kicked off, and attach to locked rows only.
  THE SHEET. The pop-out is ui.sheet() when the design system ships it -
  a bottom sheet at a medium detent on a phone, a centred card on a
  desktop - rendered ONCE as the page's shell; each row's dossier stays
  the native <details> drawer below and is promoted into that shell. The
  drawer IS the fallback, so nothing is JS-only. ui.sheets_script() rides
  once. Without ui.sheet the page's own <dialog> is the shell, styled to
  the same detent.
  THE SWITCH. Calls / Locked in / Bench / All at the top of the board
  section, 44px tall: fragment links (ui.segmented, or the local control),
  CSS :target with scripting off, a data-view attribute with it on; each
  block carries data-sec, and the grid's own rows keep data-grp. All is
  where THE GRID lives, so the source-by-source read never disappears -
  it stops being the default.
  THE LEGEND is a "?" popover (ui.legend_popover as the shell, the page's
  own chip/meter/mark key spliced in); every glyph carries a title.
  QUIET MODE. Rows where two or more voices all agree carry
  data-unanimous="1"; engine/prefs sets data-quiet="1" on <html> and the
  stylesheet hides them, printing the hidden count so a quiet board never
  reads as a shorter roster. A row that raised a CALL is never marked,
  however unanimous its votes were: quiet mode may not hide a row that
  needs the reader, and a unanimous START into an AVOID matchup is exactly
  such a row.
  COMPONENTS BY NAME. Every new component is reached through getattr(ui,
  name) with a local fallback of the same contract (ui_components_present()
  reports which path each took), so the page renders either way.
  TYPE SCALE 17 / 15 / 13, floor 11px - nothing on the page is smaller.

NO SCRIPT, ONE EXCEPTION - AND WHAT IT MAY NOT DO
=================================================
v1 shipped zero JavaScript. v2 ships ONE inline script of its own, ~40
lines, whose entire job is to move an existing <details> element into the
shared <dialog> and call showModal(). It is worth the exception because
Escape, the focus trap and the top layer cannot be had without it, and it
is safe because of what it is not: not external (the page still loads
nothing from the network but its typefaces, has no <link>, no src=), not a
framework, and not a source of content. Delete the script and every fact
on this page is still readable, because the script only relocates markup
the server already wrote. Its failure mode is the fallback, by
construction: if <dialog> is unsupported the click is left alone and the
anchor jumps to the drawer. The shell contributes a second, smaller inline
script - the light/dark toggle - which degrades to following the OS.
tests/board_test.py pins all of that.

COMPOSITION, NOT REIMPLEMENTATION. Every number on the page is computed by
the module that owns it; this file arranges and colours them.

  consensus rows + weights ... engine/consensus  (build_consensus)
  starters vs bench .......... engine/lineup     (build)
  DEF/K hold-or-stream ....... engine/dk         (weekly_call: the DST/K
                                                  rows' verdict + drawer line)
  add candidates + FAAB ...... engine/waivers    (score_pool, competition)
  named trade targets ........ engine/trades     (load_rival_view,
                                                  rival_targets, constructs)
  every roster in the league .. engine/leagueview (load_league_view)
  league-size relevance ....... engine/leaguesize (relevance)
  cross-league holdings ....... engine/exposure   (Exposure.load)
  source records + the blend .. engine/performance (source_scoreboard,
                                                  blend_bases)
  the league switcher ......... engine/sources_page (league_choices)

HONEST DEGRADATION. Each section is built inside a guard: a dead feed or a
missing file renders that section WITH a visible degradation note carrying
the real exception, never a silently missing panel. Coverage is stated in
positive-only terms everywhere - a player on no known roster is UNKNOWN,
not a free agent - and a source with nothing to say gets an empty column,
which is itself the finding.

NO CLAIM WITHOUT DATA. Degradation is not only about what a dead section
shows in its own card; it is about what the REST of the page is then
allowed to say. An empty CALLS list has two unrelated causes - the room
was weighed and agreed, or nothing was weighed at all - and the section
must never print the first when it means the second. So the positive claim
("nothing needed deciding") is composed only when rows carrying real votes
were actually arbitrated AND every check that can raise a card actually
ran; otherwise THE CALLS states what it could not read and asserts
nothing. That is stricter than it sounds, because a card can be raised on
four grounds and each has its own feed: a dead matchup table means the
matchup-contradiction check DID NOT RUN, and an empty list then cannot
mean "no matchup contradicts the room". call_coverage() collects exactly
those holes, and render_calls prints them. Same rule for the TOP SOURCE
DISSENTS alarm: it fires on the top-weighted source's own vote (consensus'
top_disagrees), never on a different fact that merely correlates with it.

WRITE DISCIPLINE. The board is READ-ONLY except for the one HTML file it is
asked to write, and read-only means in fact, not in intent. It does NOT
record source-ledger votes (recording stays the digest's job, so opening
the board twice can never inflate a source's record) and it does NOT
advance the %owned momentum baseline: it calls waivers.owned_momentum with
advance=False, so data/cache/espn-owned-snapshot.json is read and left
alone. Only a deliberate refresh - the digest, or python -m engine.waivers
- rolls that baseline forward. Rendering twice therefore reports the same
deltas instead of collapsing them to ~0 against a snapshot the previous
render had just written. Feed caches under data/cache/ still refill on
their normal freshness windows; nothing else on disk changes.

The v2 sections widen the read surface, so the same rule is restated for
them. engine/performance.py is used through source_scoreboard(),
history_series() and blend_bases(), which only READ
data/performance_history.jsonl and the ledger - backfill_feed()/
backfill_all(), which append rows, are never called from here.
engine/matchups.py is used through pa_table() and matchup_for();
matchups.register() is NEVER called, because registering the matchup
source would rewrite data/sources.yaml - a live user file - as a side
effect of drawing a page. A test parses this module for all of them.

FAILURE AT THE EDGE. A section can degrade; a load that happens before any
section exists cannot. main() wraps the whole render path, so a corrupt
data/sources.yaml, a missing rankings csv or an unreadable roster leaves
one diagnosis line naming the file and the remedy, and exit code 1 - never
a traceback out of ./board.sh (see render_failure).

Tests redirect roster_dir/calls_dir/out_path into a tempdir.
"""

import argparse
import html as _html
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from engine import consensus as consensus_mod
    from engine import dk as dk_mod
    from engine import leaguesize, leagueview, lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import performance as perf_mod
    from engine import trades, ui, waivers, weekly
    from engine.exposure import Exposure
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, missing_rankings_message,
                               repo_path)
    from engine.projections import fetch_injury_status, norm_team
    from engine.sources_page import blend_for, league_choices
except ImportError:  # run directly as `python engine/board.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import consensus as consensus_mod
    from engine import dk as dk_mod
    from engine import leaguesize, leagueview, lineup as lineup_mod
    from engine import matchups as matchups_mod
    from engine import performance as perf_mod
    from engine import trades, ui, waivers, weekly
    from engine.exposure import Exposure
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, missing_rankings_message,
                               repo_path)
    from engine.projections import fetch_injury_status, norm_team
    from engine.sources_page import blend_for, league_choices

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOP_ADDS = 8            # waiver rows on the board
TOP_TARGETS = 6         # named trade targets
QUOTE_CHARS = 220       # quote length kept in a title attribute
PEEK_CHARS = 96         # the drawer summary's one-line preview
DOSSIER_QUOTE = 320     # a quote inside the pop-out is read, not scanned

# PROGRESSIVE DISCLOSURE. A row whose voices point both ways opens by
# default: those are the rows that need thought, and a default that hides
# them optimizes for a tidy screenshot instead of for the decision.
OPEN_AT_LEVEL = 1       # == LVL_SPLIT, defined just below

# The shared pop-out's element ids. One dialog for the whole page: the
# script moves the drawer that was clicked into it, so the dossier exists
# exactly once in the document and find-in-page still finds it.
DLG_ID = "wr-dlg"
DLG_SLOT = "wr-dlg-slot"

# Divergence marker strength.
LVL_NONE = 0            # every voice points the same way (or only one voted)
LVL_SPLIT = 1           # the room points both ways
LVL_TOP = 2             # the single heaviest voice dissents - the alarm

MARKERS = {
    LVL_SPLIT: "SPLIT",
    LVL_TOP: "TOP SOURCE DISSENTS",
}

# Verdict chips are ui.verdict_chip: weight, not hue. This maps a vote's
# verdict onto the chip's key; the chip prints the WORD next to the weight
# so it survives a grayscale print and a colour-blind reader.
VERDICT_KEYS = {"start": "start", "sit": "sit", "flex": "flex",
                "even": "even"}

# What a built-in feed's vote MEANS, so the divergence panel can state a
# reason for a voice that has no quote. Keyed by the registry handle, which
# is what identifies a built-in feed (ids are user-editable, handles are not).
FEED_REASONS = {
    "engine": {
        "start": "our best legal lineup starts him this week",
        "sit": "our best legal lineup leaves him on the bench",
        "flex": "our lineup has him as a flex-level call",
    },
    "espn-proj": {
        "start": "ESPN's own weekly projection puts him in the best legal "
                 "lineup",
        "sit": "on ESPN's weekly projection alone he does not make the "
               "lineup",
        "flex": "ESPN's projection has him on the flex line",
    },
    "sleeper-proj": {
        "start": "Sleeper's own weekly projection puts him in the best legal "
                 "lineup",
        "sit": "on Sleeper's weekly projection alone he does not make the "
               "lineup",
        "flex": "Sleeper's projection has him on the flex line",
    },
    "chen-tiers": {
        "start": "his Boris Chen tier is inside this league's positional "
                 "starter cutoff",
        "sit": "his Boris Chen tier is past this league's positional "
               "starter cutoff",
        "flex": "his Boris Chen tier sits on the starter cutoff",
    },
}


def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


def _trim(text: str, limit: int = QUOTE_CHARS) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit - 3].rstrip() + "..."


# --- ui components that may not have landed yet -----------------------------
# engine/ui.py is being extended concurrently (score_cell, sheet +
# sheets_script, legend_popover, segmented, opp_chip, status_pill). The
# board calls each by NAME through getattr and carries a local fallback
# with the same contract, so the page renders identically whether or not
# the component has shipped. ui_components_present() reports which path
# each took; tests and the render report read it.

UI_COMPONENTS = ("score_cell", "sheet", "sheets_script", "legend_popover",
                 "segmented", "opp_chip", "status_pill")


def ui_component(name: str) -> Optional[Callable]:
    fn = getattr(ui, name, None)
    return fn if callable(fn) else None


def ui_components_present() -> Dict[str, bool]:
    """{component name: True if engine/ui.py ships it right now}."""
    return dict((n, ui_component(n) is not None) for n in UI_COMPONENTS)


def _via_ui(name: str, fallback: Callable, *args) -> str:
    """Call ui.<name>(*args) when it exists and returns markup; otherwise
    the local fallback. A component that raises - a signature this page
    guessed wrong, a validation error - falls back too, because a broken
    row is worse than a plain one. The fallback is the contract; ui's
    version is the upgrade."""
    fn = ui_component(name)
    if fn is not None:
        try:
            out = fn(*args)
            if isinstance(out, str) and out.strip():
                return out
        except Exception:  # noqa: BLE001 - the fallback is the contract
            pass
    return fallback(*args)


# The five-step matchup rating as a number, for the title sentence and the
# score breakdown ("4/5"). Same steps ui.matchup_meter fills, stated here
# so the words and the meter can never disagree.
MATCHUP_STEPS = {"SMASH": 5, "GOOD": 4, "NEUTRAL": 3, "TOUGH": 2, "AVOID": 1}

# The Calls / Locked in / Bench / All switch. Each of the board's four
# blocks carries data-sec with one of these keys; the control filters on it
# (CSS :target with the script off, a data-view attribute with it on).
# ALL is where THE GRID lives, so the source-by-source matrix the owner
# liked is still one tap away - it is simply no longer the default.
SEG_VIEWS = (("calls", "Calls"), ("locked", "Locked in"),
             ("bench", "Bench"), ("all", "All"))
SEG_DEFAULT = "calls"

# The grid's own rows keep data-grp so a reader (and a test) can still tell
# a starter's row from a bench row inside the matrix.
_GRP_OF = {"STARTING": "starters", "BENCH": "bench"}


def group_view(group: str) -> str:
    """Which grid band a matrix group belongs to; anything that is neither
    a starter nor a bench row (unresolved names, wire rows) is 'other'."""
    return _GRP_OF.get(str(group or "").upper(), "other")


# --- WHAT MAKES A PLAYER A CALL ---------------------------------------------
# Four grounds, each derived from a module that owns the fact. Nothing else
# raises a card, and every card names the ground that raised it.
CALL_SPLIT = "split"        # the room points both ways (consensus)
CALL_TOP = "top"            # the heaviest voice dissents (consensus)
CALL_MATCHUP = "matchup"    # the matchup contradicts a room that agrees
CALL_STREAM = "stream"      # DST/K hold-vs-stream is not a HOLD (engine/dk)

# Sort strength: the alarm first, then the genuinely divided, then the
# quieter contradictions. Ties break on the weight sitting on the losing
# side, then on the name, so the order never depends on dict iteration.
CALL_RANK = {CALL_TOP: 3, CALL_SPLIT: 2, CALL_STREAM: 2, CALL_MATCHUP: 1}

# The matchup grades that CONTRADICT a settled room. Only the two ends
# count: NEUTRAL/GOOD/TOUGH argue with nobody, and a card raised on them
# would be noise dressed as a finding.
CONTRA = {"START": "AVOID", "SIT": "SMASH"}


# --- palette ----------------------------------------------------------------
# THE PALETTE LIVES IN engine/ui.py, and this page composes it. Every rule
# below references a var(--wr-*) token and nothing else: no hex, no named
# colour, none of the old --mint/--coral aliases. A verdict is a chip weight
# (ui.verdict_chip), attention is a gold rule, and a tally is an ink number.
# tests/board_test.py greps the emitted page for the forbidden hues.

_CSS = """
  /* ---- masthead ------------------------------------------------------- */
  .bd-mast { margin: 0 0 16px; }
  .bd-mast .wr-lede { margin-bottom: 8px; }
  .bd-cov { margin: 0 0 10px; font-size: 12.5px; color: var(--wr-muted); }
  .bd-cov b { color: var(--wr-text); }
  .srcbar { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; }
  .srcbar .s {
    display: inline-flex; padding: 3px 10px 3px 4px;
    border: 1px solid var(--wr-hairline); border-radius: 999px;
    background: var(--wr-panel);
  }
  .srcbar .s.top { border-color: var(--wr-rule); }
  .srcbar .s .wr-np-n { font-size: 12px; }

  /* ---- sections (wr-card) ---------------------------------------------- */
  section.bd-sec { margin-top: 14px; }
  section.bd-sec .wr-sec { margin-bottom: 10px; }
  h3.sub {
    margin: 16px 0 6px; font-size: 11px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--wr-dim);
  }
  .note { color: var(--wr-muted); font-size: 12px; margin: 4px 0; }
  /* attention is a gold RULE on ink text - never a coloured sentence */
  .note.warn {
    color: var(--wr-text); border-left: 3px solid var(--wr-rule);
    padding-left: 9px; background: var(--wr-wash-hot);
    padding-top: 5px; padding-bottom: 5px; border-radius: 0 6px 6px 0;
  }
  .note.bad { color: var(--wr-text); font-weight: 600;
              border-left: 3px solid var(--wr-text); padding-left: 9px; }
  .note code, ul.flat code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
  }

  /* ---- MATRIX V2 -------------------------------------------------------
     SCANNABILITY. The matrix is a data grid, so it gets a data grid's
     furniture: its own scroll box on BOTH axes, a sticky header row and a
     sticky player column, so a chip nine columns to the right is still
     attributable to a row and a source while you are scrolled away from
     both. A sticky element needs a real scrolling ancestor with a bounded
     height - `overflow:auto` alone makes THIS box the scroll container and
     then `top:0` never fires - hence max-height. Sticky cells also need an
     opaque background of their own, because they are painted OVER the
     cells they cover; every row-level wash below is therefore repeated on
     the sticky cell rather than inherited from the row. The shared
     .wr-table rule pins headers 57px under the viewport's nav; inside this
     box the header pins to the box, so `top` is restated as 0. */
  .mxwrap {
    overflow: auto; max-height: 78vh;
    border: 1px solid var(--wr-hairline); border-radius: 8px;
    background: var(--wr-panel);
  }
  table.mx { min-width: 960px; font-size: 13px; }
  table.mx th {
    text-align: center; vertical-align: bottom; padding: 8px 6px 6px;
    letter-spacing: 0.06em;
  }
  table.mx thead th {
    position: sticky; top: 0; z-index: 4; background: var(--wr-panel);
  }
  table.mx th.who, table.mx th.mdl { text-align: left; }
  table.mx th.who, table.mx td.who { min-width: 240px; }
  table.mx th.src { min-width: 74px; }
  table.mx th.mdl, table.mx td.mdl { min-width: 200px; }
  table.mx thead th.who { z-index: 6; }
  table.mx th.who, table.mx td.who {
    position: sticky; left: 0; z-index: 3; background: var(--wr-panel);
    border-right: 1px solid var(--wr-hairline);
  }
  table.mx td {
    padding: 6px; border-bottom: 1px solid var(--wr-hairline);
    vertical-align: middle; text-align: center;
  }
  table.mx td.who, table.mx td.mdl { text-align: left; }
  table.mx td.who { white-space: nowrap; }
  table.mx tbody.grp td {
    background: var(--wr-raised); color: var(--wr-dim); text-align: left;
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    font-weight: 700; padding: 7px 10px;
    border-bottom: 1px solid var(--wr-hairline-2);
    position: sticky; left: 0;
  }

  /* SCANNABILITY - zebra. Every player is one <tbody>, so the band has a
     real element to hang a background on and the drawer can never drift
     away from the row it belongs to. The parity class is written by the
     renderer, not by :nth-of-type - the group bands are <tbody>s too and
     would otherwise flip the stripe at every heading. The :hover variants
     keep the shared table hover from erasing a divergence wash. */
  table.mx tbody.pl td, table.mx tbody.pl tr:hover td {
    background: var(--wr-panel);
  }
  table.mx tbody.pl.odd td, table.mx tbody.pl.odd tr:hover td,
  table.mx tbody.pl.odd td.who { background: var(--wr-raised); }
  table.mx tbody.lvl1 td, table.mx tbody.lvl1 tr:hover td,
  table.mx tbody.lvl1 td.who, table.mx tbody.lvl1.odd td,
  table.mx tbody.lvl1.odd tr:hover td { background: var(--wr-wash-split); }
  table.mx tbody.lvl2 td, table.mx tbody.lvl2 tr:hover td,
  table.mx tbody.lvl2 td.who, table.mx tbody.lvl2.odd td,
  table.mx tbody.lvl2.odd tr:hover td { background: var(--wr-wash-hot); }
  table.mx tbody.lvl1 td.who { box-shadow: inset 3px 0 0 var(--wr-hairline-2); }
  table.mx tbody.lvl2 td.who { box-shadow: inset 3px 0 0 var(--wr-rule); }

  /* source column header: a FACE, the weight, the form. REPUTATION AT THE
     POINT OF USE - the state sits directly above that source's own column
     of chips, so "is this dissenter worth listening to" is answered
     without a trip to a legend. The full name rides in the title. */
  table.mx th.src .wr-np-c { margin: 0 auto; }
  table.mx th.src .wr-np-s { white-space: normal; max-width: 86px;
                             line-height: 1.15; }
  table.mx th.topsrc { box-shadow: inset 0 -3px 0 var(--wr-rule); }
  .mdl-head { display: inline-flex; align-items: center; gap: 8px; }
  .mdl-l { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
           color: var(--wr-dim); font-weight: 700; }

  .who .nm { font-weight: 700; }
  .who .slot {
    display: inline-block; min-width: 46px; color: var(--wr-gold);
    font-size: 11px; font-weight: 800; letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .who .meta { color: var(--wr-muted); font-size: 12px; font-weight: 400; }
  .who .mark {
    font-size: 11px; letter-spacing: 0.08em; font-weight: 700;
    text-transform: uppercase; margin-top: 1px;
  }
  .who .mark.l1 { color: var(--wr-muted); }
  .who .mark.l2 { color: var(--wr-gold); }

  /* POP-OUT trigger. The player's own name is the affordance, because the
     name is what the reader is already pointing at. It is an <a> to a real
     fragment so it still works with the script deleted. */
  a.pop {
    color: inherit; text-decoration: none;
    border-bottom: 1px dotted var(--wr-hairline-2); cursor: pointer;
  }
  a.pop:hover, a.pop:focus-visible { border-bottom-color: var(--wr-rule); }
  a.pop:focus-visible { outline: 2px solid var(--wr-rule);
                        outline-offset: 2px; }
  .who .popmark { color: var(--wr-dim); margin-left: 4px; }

  /* a LOCAL chip for the non-verdict model calls (BURN, FAAB 12%, TRADE
     FOR, OPEN): ui.py has no labelled chip, so this reuses its .wr-chip
     weight classes - fill / ghost / hollow - and adds nothing of its own */
  .bd-lchip { font-size: 11px; padding: 1px 7px; }
  .c .wr-chip { vertical-align: middle; }

  /* ---- the row drawer (PROGRESSIVE DISCLOSURE) -------------------------
     <details> and not a div-with-a-click: it brings the disclosure
     semantics, keyboard toggle and find-in-page-opens-it behaviour for
     free, and it works with zero script. The drawer lives in its own
     full-width row under the player, and its inner block is sticky-left so
     the prose stays where the reader's eye is when the grid is scrolled
     sideways. */
  table.mx tr.dr > td {
    padding: 0; border-bottom: 1px solid var(--wr-hairline); text-align: left;
  }
  .drin { position: sticky; left: 0; max-width: 1000px; padding: 0 8px 0 0; }
  details.bd-pop > summary {
    list-style: none; cursor: pointer; padding: 5px 8px 6px 10px;
    display: flex; align-items: center; gap: 6px; min-height: 30px;
    color: var(--wr-muted); font-size: 12px; max-width: 720px;
  }
  details.bd-pop > summary::-webkit-details-marker { display: none; }
  details.bd-pop > summary:focus-visible {
    outline: 2px solid var(--wr-rule); outline-offset: -2px;
    border-radius: 4px;
  }
  details.bd-pop > summary:hover { color: var(--wr-text); }
  /* THE NO-SCRIPT PATH. With the script gone the player-name link is an
     ordinary fragment jump, so :target marks where the reader landed and
     the summary right there is what opens the drawer. Pure CSS, works in
     every browser, and it promises nothing more than it does. */
  details.bd-pop:target > summary {
    outline: 2px solid var(--wr-rule); outline-offset: -2px;
    border-radius: 4px; color: var(--wr-text);
  }
  details.bd-pop:target > summary .bd-more { text-decoration: underline; }
  .bd-chev { color: var(--wr-dim); transition: transform 120ms ease; }
  details.bd-pop[open] > summary .bd-chev { transform: rotate(180deg); }
  .bd-peek { flex: 1 1 auto; min-width: 0; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }
  .bd-more {
    font-size: 11px; font-weight: 800; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--wr-gold); white-space: nowrap;
  }
  .bd-body {
    padding: 4px 12px 12px 10px; border-top: 1px dashed var(--wr-hairline);
    background: var(--wr-panel);
  }
  .bd-h {
    margin: 10px 0 4px; font-size: 11px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--wr-gold); font-weight: 800;
  }
  .bd-h:first-child { margin-top: 4px; }
  .bd-src {
    display: grid; grid-template-columns: minmax(150px, 230px) auto 1fr;
    gap: 4px 10px; align-items: center; font-size: 12.5px;
    padding: 5px 0; border-bottom: 1px solid var(--wr-hairline);
  }
  .bd-src:last-of-type { border-bottom: none; }
  /* a grid item stretches to its track by default, which turned the
     verdict chip into a full-width bar - a chip is a chip. */
  .bd-src > .wr-chip { justify-self: start; }
  .bd-src .wr-np-n { font-size: 12.5px; white-space: normal; }
  .bd-src .wr-np-sub { white-space: normal; }
  .bd-src .q { color: var(--wr-text); }
  .bd-src .q.mutq { color: var(--wr-muted); font-style: italic; }
  /* tbody.pl clips (overflow:hidden) so its rounded corner is honest, so
     anything wider than the card must carry its own scroller or it is
     silently truncated with no scrollbar and no gesture to recover it. */
  .bd-mathw { max-width: 100%; }
  table.bd-math {
    border-collapse: collapse; font-size: 12px; margin-top: 2px;
    font-variant-numeric: tabular-nums; width: auto;
  }
  table.bd-math th, table.bd-math td {
    padding: 2px 10px 2px 0; text-align: right; border-bottom: none;
    background: transparent; position: static;
  }
  table.bd-math th { color: var(--wr-muted); font-size: 11px;
                     text-transform: uppercase; letter-spacing: 0.06em; }
  table.bd-math th:first-child, table.bd-math td:first-child {
    text-align: left;
  }
  table.bd-math tr.sum td { border-top: 1px solid var(--wr-hairline-2);
                            font-weight: 700; padding-top: 4px; }
  .bd-ev { font-size: 12.5px; color: var(--wr-text); margin: 3px 0; }
  .bd-ev.cav { color: var(--wr-muted); }
  .bd-ev.bd-basis { color: var(--wr-muted); font-size: 12px; }
  .bd-mu { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .bd-opp { color: var(--wr-muted); }
  .bd-list { margin: 3px 0 0; padding-left: 18px; }
  .bd-list li { font-size: 12.5px; margin: 2px 0; color: var(--wr-muted); }
  .bd-list li b { color: var(--wr-text); }

  /* ---- the pop-out (DEFERRED DETAIL) ---------------------------------- */
  dialog.bd-dlg {
    border: 1px solid var(--wr-hairline-2); border-radius: 10px; padding: 0;
    background: var(--wr-panel); color: var(--wr-text);
    max-width: min(860px, 94vw); width: min(860px, 94vw);
    max-height: 86vh; overflow: auto;
  }
  dialog.bd-dlg::backdrop { background: var(--wr-nav); opacity: 0.6; }
  .bd-dlg-bar {
    position: sticky; top: 0; z-index: 2; background: var(--wr-panel);
    border-bottom: 2px solid var(--wr-rule);
    padding: 9px 12px; display: flex; align-items: center; gap: 10px;
  }
  .bd-dlg-bar .t {
    flex: 1 1 auto; font-size: 12px; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--wr-gold); font-weight: 800;
  }
  .bd-x {
    font: inherit; font-size: 12px; font-weight: 700; cursor: pointer;
    color: var(--wr-text); background: var(--wr-raised);
    border: 1px solid var(--wr-hairline-2); border-radius: 6px;
    padding: 6px 12px; min-height: 32px;
  }
  .bd-x:hover { border-color: var(--wr-rule); }
  .bd-x:focus-visible { outline: 2px solid var(--wr-rule);
                        outline-offset: 2px; }
  .bd-dlg-slot { padding: 4px 12px 14px; }
  /* Inside the pop-out the drawer is the CONTENT, not a disclosure: the
     summary strip would be a control that does nothing useful there. */
  .bd-dlg-slot details.bd-pop > summary { display: none; }
  .bd-dlg-slot .bd-body { border-top: none; padding-left: 0; }

  .mdl .pct { color: var(--wr-muted); font-size: 12px; margin-left: 5px; }
  .mdl .agree {
    display: block; color: var(--wr-muted); font-size: 11px;
    letter-spacing: 0.04em; text-transform: uppercase; margin-top: 2px;
  }
  .mdl .agree.hot { color: var(--wr-gold); }
  .mdl .why { display: block; color: var(--wr-muted); font-size: 11px; }

  /* ---- divergence cards ------------------------------------------------ */
  .dv { display: grid; gap: 12px; margin-top: 6px;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  .dv-card {
    border: 1px solid var(--wr-hairline); border-radius: 9px;
    padding: 12px 14px 10px; background: var(--wr-raised); min-width: 0;
  }
  .dv-card.l2 { border-color: var(--wr-rule);
                box-shadow: inset 0 3px 0 var(--wr-rule); }
  .dv-hd { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .dv-hd .nm { font-weight: 700; font-size: 14.5px; }
  .dv-hd .meta { color: var(--wr-muted); font-size: 12px; }
  .dv-side {
    display: grid; grid-template-columns: auto minmax(0, 1fr);
    gap: 6px 10px; align-items: start; padding: 8px 0;
    border-top: 1px solid var(--wr-hairline);
  }
  .dv-side .wr-chip { margin-top: 1px; }
  .dv-tally { font-size: 12px; color: var(--wr-muted); }
  .dv-tally .wr-num { color: var(--wr-text); font-weight: 700; }
  .dv-faces { display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 4px 0; }
  .dv-faces .wr-np-n { font-size: 12px; }
  .dv-faces .wr-np-m { font-size: 11px; }
  .dv-rsn { font-size: 12.5px; color: var(--wr-muted); }
  .dv-rsn .src { color: var(--wr-text); font-weight: 600; }
  .dv-model {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    padding: 8px 0 2px; border-top: 1px solid var(--wr-hairline);
  }
  .dv-alarm {
    margin-top: 8px; padding: 8px 10px; font-size: 12.5px;
    border-left: 3px solid var(--wr-rule); background: var(--wr-wash-hot);
    border-radius: 0 6px 6px 0; color: var(--wr-text);
  }
  .dv-alarm b { display: block; font-size: 11px; letter-spacing: 0.1em;
                text-transform: uppercase; color: var(--wr-gold); }
  .dv details { margin-top: 6px; }
  .dv details > summary {
    cursor: pointer; color: var(--wr-gold); font-size: 11px;
    letter-spacing: 0.06em; text-transform: uppercase; font-weight: 700;
    min-height: 24px;
  }
  .dv details ul { margin: 5px 0 0; padding-left: 18px; }
  .dv details li { font-size: 12px; margin: 2px 0; color: var(--wr-muted); }
  .dv details li b { color: var(--wr-text); }

  /* ---- source scoreboard (one row per source) --------------------------- */
  table.sb { min-width: 860px; }
  table.sb th { top: 0; }
  table.sb td { vertical-align: middle; }
  table.sb td.wr-sticky { min-width: 220px; }
  table.sb tr.top td.wr-sticky { box-shadow: inset 3px 0 0 var(--wr-rule); }
  .sb .big { font-size: 19px; font-weight: 700; letter-spacing: -0.02em;
             line-height: 1.1; }
  .sb .big.none { font-size: 12px; font-weight: 700; color: var(--wr-dim); }
  .sb .lab { display: block; font-size: 11px; letter-spacing: 0.1em;
             text-transform: uppercase; color: var(--wr-gold);
             font-weight: 700; cursor: help; }
  .sb .st-w { font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
              color: var(--wr-dim); border: 1px solid var(--wr-hairline-2);
              border-radius: 999px; padding: 1px 8px; white-space: nowrap; }
  .sb .sub { display: block; color: var(--wr-dim); font-size: 11px; }
  .sb .spark { color: var(--wr-gold); }
  .sb .wr-np a, .sb a.wr-np { color: inherit; }
  .sb-link { margin-top: 8px; font-size: 12.5px; }

  /* ---- league view ---------------------------------------------------- */
  .teams { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
  .team {
    flex: 1 1 220px; min-width: 205px; max-width: 300px;
    background: var(--wr-raised); border: 1px solid var(--wr-hairline);
    border-radius: 7px; padding: 9px 10px 8px;
  }
  .team.mine { border-color: var(--wr-rule);
               box-shadow: inset 0 3px 0 var(--wr-rule); }
  .team .tn { font-weight: 700; font-size: 13px; }
  .team .tn .slot { color: var(--wr-muted); font-weight: 400; font-size: 11px; }
  .team .tags { margin: 4px 0 6px; display: flex; flex-wrap: wrap; gap: 4px; }
  .team ul { margin: 0; padding: 0; list-style: none; }
  .team li {
    font-size: 12px; padding: 1px 0; border-bottom: 1px solid var(--wr-hairline);
    display: flex; justify-content: space-between; gap: 6px;
  }
  .team li:last-child { border-bottom: none; }
  .team li .p { white-space: nowrap; overflow: hidden;
                text-overflow: ellipsis; }
  .team li .p .ps { color: var(--wr-dim); font-size: 11px; }
  .team li .fl { white-space: nowrap; font-size: 11px; font-weight: 800;
                 letter-spacing: 0.06em; color: var(--wr-gold); }
  .team li.exp .p { color: var(--wr-gold); }
  .team li.tgt { background: var(--wr-wash-hot);
                 box-shadow: inset 3px 0 0 var(--wr-rule); padding-left: 5px; }
  .team .src { color: var(--wr-muted); font-size: 11px; margin-top: 5px; }

  ul.flat { margin: 6px 0; padding-left: 20px; }
  ul.flat li { margin: 3px 0; font-size: 13px; }

  .legend {
    margin-top: 10px; font-size: 12px; color: var(--wr-muted);
    display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center;
  }
  .legend .mark { font-weight: 700; letter-spacing: 0.06em;
                  text-transform: uppercase; font-size: 11px; }
  .legend .mark.l1 { color: var(--wr-muted); }
  .legend .mark.l2 { color: var(--wr-gold); }
  footer.bd-foot {
    margin-top: 22px; color: var(--wr-muted); font-size: 12px;
    border-top: 1px solid var(--wr-hairline); padding-top: 10px;
  }
  footer.bd-foot code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
  }

  /* ---- SCANNABILITY under 700px: stack, do not drag ---------------------
     A phone must not be handed a 960px grid to pan sideways. The table
     restructures into one card per player and every source cell prints its
     own column label from data-l - which is why that attribute exists on
     the cell rather than only in the (now hidden) header row. Every tap
     target is at least 44px tall. */
  @media (max-width: 700px) {
    .mxwrap { max-height: none; overflow: visible; border: none;
              background: transparent; }
    /* EVERY selector below is anchored with > to the matrix's OWN rows.
       A descendant selector here reaches into the tables nested inside the
       drawer (table.bd-math), and un-tabling a derivation leaves a column
       of bare numbers with their headers cut off - which is exactly what
       the descendant form did before this was scoped. */
    table.mx { display: block; min-width: 0; }
    table.mx > thead { display: none; }
    table.mx > tbody { display: block; }
    table.mx > tbody.grp > tr > td {
      display: block; position: static; border-radius: 6px;
      margin-top: 10px;
    }
    table.mx > tbody.pl {
      display: block; border: 1px solid var(--wr-hairline); border-radius: 8px;
      margin: 8px 0; overflow: hidden; background: var(--wr-panel);
    }
    table.mx > tbody.lvl1 { border-color: var(--wr-hairline-2); }
    table.mx > tbody.lvl2 { border-color: var(--wr-rule); }
    table.mx > tbody > tr { display: block; }
    table.mx > tbody > tr > td, table.mx > thead > tr > th.who,
    table.mx > tbody > tr > td.who {
      display: block; position: static; text-align: left; white-space: normal;
      min-width: 0; box-shadow: none; border-right: none;
    }
    table.mx > tbody > tr > td.who {
      border-bottom: 1px solid var(--wr-hairline-2); padding: 10px 10px; }
    .who a.pop { display: inline-block; padding: 12px 0; }
    table.mx > tbody > tr > td.c {
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; border-bottom: 1px solid var(--wr-hairline); min-height: 44px;
      padding: 4px 10px;
    }
    table.mx > tbody > tr > td.c::before {
      content: attr(data-l); color: var(--wr-muted); font-size: 11px;
      letter-spacing: 0.06em; text-transform: uppercase; font-weight: 700;
      flex: 0 1 auto; min-width: 0; overflow: hidden;
      text-overflow: ellipsis; white-space: nowrap;
    }
    table.mx > tbody > tr > td.mdl { border-bottom: none; padding: 8px 10px; }
    table.mx > tbody > tr > td.mdl::before {
      content: attr(data-l); display: block; color: var(--wr-muted);
      font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
      font-weight: 700; margin-bottom: 2px;
    }
    .drin { position: static; max-width: none; }
    details.bd-pop > summary { min-height: 44px; }
    .bd-src { grid-template-columns: 1fr; gap: 2px; }
    .dv { grid-template-columns: 1fr; }
    .dv details > summary { min-height: 44px; display: flex;
                            align-items: center; }
    .team { max-width: none; }
    dialog.bd-dlg { width: 96vw; max-width: 96vw; }

    /* the source scoreboard: one card per source, every cell printing its
       own column name from data-l. 860px of grid to pan sideways is not a
       phone layout, and the 44px tap floor still holds. */
    table.sb { display: block; min-width: 0; }
    table.sb > thead { display: none; }
    table.sb > tbody { display: block; }
    table.sb > tbody > tr {
      display: block; border: 1px solid var(--wr-hairline);
      border-radius: 8px; margin: 8px 0; background: var(--wr-panel);
    }
    table.sb > tbody > tr.top { border-color: var(--wr-rule); }
    table.sb > tbody > tr > td {
      display: block; position: static; text-align: left; min-width: 0;
      width: auto; box-shadow: none; border-right: none;
      border-bottom: 1px solid var(--wr-hairline); padding: 8px 10px;
    }
    table.sb > tbody > tr > td:last-child { border-bottom: none; }
    table.sb > tbody > tr > td.wr-sticky {
      min-width: 0; border-bottom: 1px solid var(--wr-hairline-2); }
    table.sb > tbody > tr.top > td.wr-sticky {
      box-shadow: inset 3px 0 0 var(--wr-rule); }
    table.sb > tbody > tr > td[data-l]::before {
      content: attr(data-l); display: block; color: var(--wr-muted);
      font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
      font-weight: 700; margin-bottom: 2px;
    }
  }

  @media print {
    section.bd-sec { break-inside: avoid; }
    /* PROGRESSIVE DISCLOSURE has no meaning on paper: print every drawer
       open, so a printed board is not a page of collapsed stubs. */
    .mxwrap { max-height: none; overflow: visible; }
    details.bd-pop > .bd-body { display: block; }
    details.bd-pop > summary { display: none; }
    table.mx thead th, table.mx th.who, table.mx td.who,
    table.mx tbody.grp td { position: static; }
  }
"""

# --- v4: the call as a percentage, the number you tap, locks, the switch --
# Layout-independent on purpose: everything below hangs on a row (<tbody>)
# and its cells, so it survives whichever matrix layout the owner picks.
# Type scale is 17 / 15 / 13 with an 11px floor - nothing on this page is
# set smaller than 11px, the sportsbook-app failure this board must avoid.
_CSS += """
  /* ---- the call: "START · 67% of the room", and the WHY beneath ------- */
  .mdl-of { color: var(--wr-muted); font-size: 12px; margin-left: 4px;
            white-space: nowrap; }
  .mdl-was { display: block; color: var(--wr-dim); font-size: 12px;
             margin-top: 2px; }
  .mdl-why { display: block; color: var(--wr-text); font-size: 13px;
             margin-top: 4px; max-width: 320px; line-height: 1.35;
             white-space: normal; }
  .mdl-why b { color: var(--wr-gold); font-weight: 700; }
  .mdl-mu { display: inline-flex; align-items: center; gap: 6px;
            margin-left: 8px; vertical-align: middle; }
  .mdl-mu .bd-opp { font-size: 12px; }

  /* ---- the number: tap the score for its breakdown ------------------- */
  .who-in { display: flex; align-items: center; justify-content: space-between;
            gap: 12px; }
  .who-id { min-width: 0; }
  details.bd-score { display: inline-block; white-space: normal; }
  details.bd-score > summary {
    list-style: none; cursor: pointer; display: inline-flex;
    align-items: baseline; gap: 5px; min-height: 30px;
    padding: 2px 6px; border-radius: 6px; border: 1px solid transparent;
  }
  details.bd-score > summary::-webkit-details-marker { display: none; }
  details.bd-score > summary:hover,
  details.bd-score[open] > summary { border-color: var(--wr-hairline-2);
                                     background: var(--wr-raised); }
  details.bd-score > summary:focus-visible { outline: 2px solid var(--wr-rule);
                                            outline-offset: 2px; }
  .bd-score-v { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; }
  .bd-score-v.act { color: var(--wr-text); }
  .bd-score-p { font-size: 13px; font-weight: 700; color: var(--wr-text); }
  .bd-score-p.mut { color: var(--wr-muted); font-weight: 400; }
  .bd-score-l { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
                color: var(--wr-dim); font-weight: 700; }
  .bd-score-b { max-width: 300px; padding: 6px 8px 8px; font-size: 13px;
                color: var(--wr-muted); border-left: 2px solid var(--wr-rule);
                margin: 4px 0 2px 6px; }
  .bd-score-b ul { margin: 0; padding-left: 16px; }
  .bd-score-b li { margin: 3px 0; }
  .bd-score-b li b { color: var(--wr-text); }
  /* the same list inside ui.score_cell's own breakdown panel */
  ul.bd-score-l { margin: 0; padding-left: 16px; font-size: 13px;
                  color: var(--wr-muted); max-width: 300px; }
  ul.bd-score-l li { margin: 3px 0; }
  ul.bd-score-l li b { color: var(--wr-text); }

  /* ---- the shared pop-out shell, when it is ui.sheet ------------------
     The sheet ships an (empty) <details> trigger beside its dialog for
     pages that have no other fallback. This page's fallback is the row's
     own drawer, so that stray trigger is hidden; the dossier still opens
     in place with scripting off. */
  .bd-dlgw > .wr-sheet-w > .wr-sheet-fb { display: none; }
  .bd-dlgw .bd-dlg-slot details.bd-pop > summary { display: none; }
  .bd-dlgw .bd-dlg-slot .bd-body { border-top: none; padding-left: 0; }

  /* ---- lock state: a glyph and a muted row after kickoff -------------- */
  .who .bd-lock { color: var(--wr-dim); margin-right: 5px; }
  table.mx tbody.pl.locked > tr.r > td { opacity: 0.6; }
  table.mx tbody.pl.locked > tr.r > td.who .bd-lock { opacity: 1; }

  /* ---- quiet mode: engine/prefs sets data-quiet on <html> -------------
     Only rows that raised NO call are ever marked data-unanimous, so this
     rule can never hide a player who needs the reader. */
  html[data-quiet="1"] table.mx tbody.pl[data-unanimous="1"],
  html[data-quiet="1"] .bd-pl[data-unanimous="1"] { display: none; }
  .bd-quiet-note { display: none; }
  html[data-quiet="1"] .bd-quiet-note { display: block; }

  /* ---- the Starters / Bench / All switch (44px tall) ------------------ */
  .bd-seg-t { display: block; height: 0; overflow: hidden; }
  .bd-seg {
    display: inline-flex; align-items: stretch; gap: 2px; min-height: 44px;
    padding: 3px; margin: 0 0 10px; border-radius: 11px;
    border: 1px solid var(--wr-hairline-2); background: var(--wr-raised);
  }
  .bd-seg-a {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 88px; padding: 0 16px; border-radius: 8px;
    color: var(--wr-muted); text-decoration: none; font-weight: 700;
    font-size: 13px; letter-spacing: 0.02em;
  }
  .bd-seg-a:hover { color: var(--wr-text); }
  .bd-seg-a:focus-visible { outline: 2px solid var(--wr-rule);
                            outline-offset: -2px; }
  .bd-seg-a[aria-current="true"] {
    background: var(--wr-panel); color: var(--wr-text);
    box-shadow: 0 1px 2px var(--wr-shadow), inset 0 -2px 0 var(--wr-rule);
  }
  /* THE SWITCH FILTERS BLOCKS, NOT ROWS. Each view is one .bd-blk with a
     data-sec; the default (calls) is written into the markup as
     data-view, so a reader with no script still lands on the calls.
     script on: the container carries data-view */
  .bd-mx[data-view="calls"] > .bd-blk:not([data-sec="calls"]),
  .bd-mx[data-view="locked"] > .bd-blk:not([data-sec="locked"]),
  .bd-mx[data-view="bench"] > .bd-blk:not([data-sec="bench"]) {
    display: none;
  }
  /* script off: the links are fragment jumps and :target does the filter.
     An id selector outranks any number of classes, so these override the
     data-view default written above whichever way the reader arrived. */
  #seg-calls:target ~ .bd-mx > .bd-blk,
  #seg-locked:target ~ .bd-mx > .bd-blk,
  #seg-bench:target ~ .bd-mx > .bd-blk { display: none; }
  #seg-calls:target ~ .bd-mx > .bd-blk[data-sec="calls"],
  #seg-locked:target ~ .bd-mx > .bd-blk[data-sec="locked"],
  #seg-bench:target ~ .bd-mx > .bd-blk[data-sec="bench"],
  #seg-all:target ~ .bd-mx > .bd-blk { display: block; }
  #seg-calls:target ~ .bd-seg .bd-seg-a,
  #seg-locked:target ~ .bd-seg .bd-seg-a,
  #seg-bench:target ~ .bd-seg .bd-seg-a,
  #seg-all:target ~ .bd-seg .bd-seg-a {
    background: transparent; color: var(--wr-muted); box-shadow: none;
  }
  #seg-calls:target ~ .bd-seg .bd-seg-a[href="#seg-calls"],
  #seg-locked:target ~ .bd-seg .bd-seg-a[href="#seg-locked"],
  #seg-bench:target ~ .bd-seg .bd-seg-a[href="#seg-bench"],
  #seg-all:target ~ .bd-seg .bd-seg-a[href="#seg-all"] {
    background: var(--wr-panel); color: var(--wr-text);
    box-shadow: 0 1px 2px var(--wr-shadow), inset 0 -2px 0 var(--wr-rule);
  }
  /* THE SAME TWO RULES FOR THE CONTROL THAT IS ACTUALLY ON THE PAGE.
     The block above styles .bd-seg-a, which only _segmented_fallback emits.
     When ui.segmented exists - which it does - segmented_html wraps it in
     .bd-segw and the pills are .wr-seg-a marked with aria-SELECTED, so with
     the script off the blocks filtered correctly while all four pills kept
     the state written into the markup: the switch always looked like
     "Calls" whichever view the reader was on. These carry an id, so they
     outrank ui.py's .wr-seg-a[aria-selected="true"] both ways. The values
     mirror that rule (colour + a 3px inset rule), not the fallback's. */
  #seg-calls:target ~ .bd-segw .wr-seg-a,
  #seg-locked:target ~ .bd-segw .wr-seg-a,
  #seg-bench:target ~ .bd-segw .wr-seg-a,
  #seg-all:target ~ .bd-segw .wr-seg-a {
    color: var(--wr-muted); box-shadow: none;
  }
  #seg-calls:target ~ .bd-segw .wr-seg-a[href="#seg-calls"],
  #seg-locked:target ~ .bd-segw .wr-seg-a[href="#seg-locked"],
  #seg-bench:target ~ .bd-segw .wr-seg-a[href="#seg-bench"],
  #seg-all:target ~ .bd-segw .wr-seg-a[href="#seg-all"] {
    color: var(--wr-text); box-shadow: inset 0 -3px 0 var(--wr-rule);
  }

  /* ---- the legend is a "?" popover, not a paragraph of glyphs --------- */
  details.bd-legend { display: inline-block; margin-top: 10px; }
  details.bd-legend > summary {
    list-style: none; cursor: pointer; display: inline-flex;
    align-items: center; justify-content: center; gap: 8px;
    min-width: 44px; min-height: 44px; padding: 0 14px 0 10px;
    border-radius: 999px; border: 1px solid var(--wr-hairline-2);
    color: var(--wr-muted); font-size: 13px; font-weight: 700;
    background: var(--wr-raised);
  }
  details.bd-legend > summary::-webkit-details-marker { display: none; }
  details.bd-legend > summary:hover,
  details.bd-legend[open] > summary { color: var(--wr-text);
                                      border-color: var(--wr-rule); }
  details.bd-legend > summary:focus-visible { outline: 2px solid var(--wr-rule);
                                             outline-offset: 2px; }
  .bd-legend-q { display: inline-flex; align-items: center; justify-content: center;
                 width: 24px; height: 24px; border-radius: 50%;
                 background: var(--wr-nav); color: var(--wr-nav-text);
                 font-size: 15px; font-weight: 700; }
  .bd-legend-b { margin-top: 8px; padding: 12px 14px; max-width: 720px;
                 border: 1px solid var(--wr-hairline); border-radius: 9px;
                 background: var(--wr-panel); box-shadow: 0 2px 8px var(--wr-shadow); }
  .bd-legend-b .legend { margin-top: 0; font-size: 13px; gap: 10px 18px; }

  /* ---- the pop-out as a bottom sheet on a phone (medium detent) -------
     The same <dialog>: on desktop it is the modal, under 700px it is a
     sheet pinned to the bottom edge at ~62vh with a drag handle drawn
     on its bar. Nothing is re-implemented; showModal() still supplies the
     top layer, the backdrop, Escape and the focus trap. */
  @media (max-width: 700px) {
    dialog.bd-dlg {
      width: 100vw; max-width: 100vw; max-height: 62vh;
      margin: auto 0 0; border-radius: 16px 16px 0 0; border-bottom: none;
    }
    .bd-dlg-bar::before {
      content: ""; display: block; width: 40px; height: 4px; border-radius: 2px;
      background: var(--wr-hairline-2); position: absolute; top: 4px;
      left: 50%; margin-left: -20px;
    }
    .bd-dlg-bar { padding-top: 14px; }
    .who-in { display: block; }
    details.bd-score { margin-top: 4px; }
    details.bd-score > summary, details.bd-legend > summary { min-height: 44px; }
    .bd-seg { display: flex; }
    .bd-seg-a { flex: 1 1 0; min-width: 0; }
    .mdl-why { max-width: none; }
  }
  @media print {
    details.bd-score > .bd-score-b, details.bd-legend > .bd-legend-b { display: block; }
    .bd-seg { display: none; }
  }
"""


# --- v5: DECISION CARDS -----------------------------------------------------
# The lead is CERTAINTY, so the page's densest object is the one that is
# still undecided. Three densities of the same player, in the same
# vocabulary: a versus CARD (a call), a compact ROW (settled), a grid CELL
# (the matrix, behind All). Every rule below reads var(--wr-*) and nothing
# else, and every fixed width is under 390px unless it lives inside a
# .wr-scroll box - the phone is the acceptance bar, not an afterthought.
_CSS += """
  /* ---- the four views ------------------------------------------------- */
  .bd-blk { display: block; margin: 0 0 4px; }
  .bd-blk + .bd-blk { margin-top: 18px; }
  .bd-grp {
    display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px;
    margin: 0 0 8px; padding-bottom: 5px;
    border-bottom: 2px solid var(--wr-rule);
  }
  .bd-grp-h {
    margin: 0; font-size: 13px; letter-spacing: 0.12em; font-weight: 800;
    text-transform: uppercase; color: var(--wr-text);
  }
  .bd-grp-n { font-size: 12px; color: var(--wr-muted); font-weight: 600; }
  .bd-grp-s { flex: 1 1 100%; font-size: 12px; color: var(--wr-muted); }

  /* ---- THE CALLS: one versus card per undecided player ---------------- */
  .bd-calls { display: grid; gap: 14px; grid-template-columns: 1fr; }
  .bd-call {
    border: 1px solid var(--wr-hairline-2); border-radius: 10px;
    background: var(--wr-panel); padding: 12px 14px 10px; min-width: 0;
  }
  /* attention is a gold RULE, never a coloured word */
  .bd-call.l2 { box-shadow: inset 0 3px 0 var(--wr-rule);
                border-color: var(--wr-rule); }
  .bd-call-h {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    min-height: 32px;
  }
  .bd-call-h .nm { font-weight: 700; font-size: 17px; letter-spacing: -0.01em;
                   min-width: 0; overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; max-width: 100%; }
  /* the card's title IS the pop-out trigger, so it is a finger target */
  .bd-call-h a.pop { display: inline-block; padding: 12px 0; }
  .bd-call-h .meta { color: var(--wr-muted); font-size: 12px; }
  .bd-call-tag {
    font-size: 11px; font-weight: 800; letter-spacing: 0.09em;
    text-transform: uppercase; color: var(--wr-text);
    border-left: 3px solid var(--wr-rule); padding-left: 8px;
  }
  .bd-call-why-list { margin: 8px 0 2px; padding: 0; list-style: none; }
  .bd-call-why-list li {
    font-size: 13px; color: var(--wr-text); margin: 4px 0; padding: 5px 9px;
    background: var(--wr-wash-hot); border-left: 3px solid var(--wr-rule);
    border-radius: 0 6px 6px 0;
  }
  .bd-call-why-list li b {
    display: block; font-size: 11px; letter-spacing: 0.09em;
    text-transform: uppercase; color: var(--wr-gold);
  }

  /* THE VERSUS. Three tracks on a desktop - START | the model | SIT - and
     ONE track under 700px, stacked in that same reading order, so a phone
     never has to scroll a card sideways to see who is on the other side. */
  .bd-vs {
    display: grid; gap: 10px; margin: 10px 0 2px;
    grid-template-columns: minmax(0, 1fr) minmax(0, 150px) minmax(0, 1fr);
    align-items: start;
  }
  .bd-vs-side {
    min-width: 0; border: 1px solid var(--wr-hairline); border-radius: 8px;
    background: var(--wr-raised); padding: 8px 9px;
  }
  .bd-vs-hd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .bd-vs-t { font-size: 12px; color: var(--wr-muted); }
  .bd-vs-t .wr-num { color: var(--wr-text); font-weight: 700; }
  .bd-vs-l { margin: 6px 0 0; padding: 0; list-style: none; }
  .bd-vs-l li {
    display: grid; grid-template-columns: auto minmax(0, 1fr);
    gap: 2px 8px; align-items: start; padding: 5px 0;
    border-top: 1px solid var(--wr-hairline);
  }
  .bd-vs-l li:first-child { border-top: none; }
  .bd-vs-who { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
  .bd-vs-n { flex: 0 1 auto; font-size: 13px; font-weight: 700; min-width: 0;
             overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bd-vs-w { flex: none; font-size: 11px; color: var(--wr-muted);
             font-weight: 700; }
  .bd-vs-q { grid-column: 2; font-size: 12.5px; color: var(--wr-text);
             line-height: 1.35; }
  .bd-vs-q.mutq { color: var(--wr-muted); font-style: italic; }
  .bd-vs-none { font-size: 12.5px; color: var(--wr-muted); margin: 6px 0 0; }
  /* the gutter: the model's own call, and the matchup beside it */
  .bd-vs-gut {
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    text-align: center; padding: 8px 6px; min-width: 0;
    border: 1px dashed var(--wr-hairline-2); border-radius: 8px;
  }
  .bd-vs-vs {
    font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
    font-weight: 800; color: var(--wr-dim);
  }
  .bd-vs-of { font-size: 11px; color: var(--wr-muted); }
  .bd-vs-mu { display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
              justify-content: center; }
  .bd-vs-basis { font-size: 11px; color: var(--wr-muted); line-height: 1.3; }

  /* the derived WHY, and the projections it turns on */
  .bd-call-why {
    margin: 8px 0 0; font-size: 13px; color: var(--wr-text);
    line-height: 1.4;
  }
  .bd-call-num {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    margin-top: 8px; padding-top: 8px;
    border-top: 1px solid var(--wr-hairline);
  }
  .bd-call-vs-p { font-size: 12.5px; color: var(--wr-muted); }
  .bd-call-vs-p b { color: var(--wr-text); }

  /* AGREE / OVERRIDE. Inert on purpose: they are <span>s, not buttons, and
     the line under them says in words that nothing here is saved. They are
     still 44px so they do not read as broken chrome. */
  .bd-acts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
             margin-top: 10px; }
  .bd-act {
    display: inline-flex; align-items: center; justify-content: center;
    min-height: 44px; min-width: 104px; padding: 0 16px; border-radius: 9px;
    font-size: 13px; font-weight: 700; letter-spacing: 0.02em;
    border: 1px solid var(--wr-hairline-2); color: var(--wr-muted);
    background: var(--wr-raised); font-family: inherit; cursor: not-allowed;
  }
  .bd-act[disabled] { opacity: 0.75; }
  .bd-act-y { border-color: var(--wr-rule); color: var(--wr-text); }
  .bd-acts-n { flex: 1 1 100%; font-size: 11px; color: var(--wr-muted); }

  /* ---- LOCKED IN / BENCH: one compact row each ------------------------
     THREE logical columns and no more at 375px: identity | opponent +
     projection | verdict. The name is one line with an ellipsis - never
     wrapped - and the face strip sits under it inside the same column. */
  .bd-pl {
    border-bottom: 1px solid var(--wr-hairline); padding: 2px 0;
  }
  .bd-pl:last-child { border-bottom: none; }
  .bd-r3 {
    display: grid; grid-template-columns: minmax(0, 1fr) auto auto;
    align-items: center; column-gap: 10px; min-height: 48px; padding: 4px 2px;
  }
  .bd-r3-id { min-width: 0; }
  .bd-r3-top { display: flex; align-items: center; gap: 7px; min-width: 0; }
  .bd-r3-top > * { flex: none; }
  .bd-r3-nm {
    flex: 0 1 auto; min-width: 0; overflow: hidden; white-space: nowrap;
    text-overflow: ellipsis; font-size: 15px; font-weight: 700;
  }
  .bd-r3-meta { color: var(--wr-muted); font-size: 11px; letter-spacing: 0.06em;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bd-r3-mid { display: flex; align-items: center; justify-content: flex-end;
               gap: 8px; white-space: nowrap; }
  .bd-r3-v { display: flex; align-items: center; justify-content: flex-end; }
  .bd-pl.locked > .bd-r3 { opacity: 0.6; }
  .bd-pl.locked > .bd-r3 .bd-lock { opacity: 1; }

  /* THE FACE STRIP. A gold ring voted START, a grey ring voted SIT, a
     faint ring filed nothing at all. Weight, not hue - and every face
     carries the source's name, its weight and its verdict in a title.
     The avatar's OWN ring is suppressed inside the strip: two concentric
     rings on a 24px face is a smudge, and the verdict is the ring that
     has to read here. */
  .bd-faces { display: flex; flex-wrap: wrap; gap: 6px; margin: 1px 2px 5px; }
  .bd-faces .wr-av { display: block; box-shadow: none; }
  .bd-face { display: inline-flex; border-radius: 50%; }
  .bd-face-start { box-shadow: 0 0 0 2px var(--wr-rule); }
  .bd-face-sit { box-shadow: 0 0 0 2px var(--wr-hairline-2); }
  .bd-face-lean { box-shadow: 0 0 0 2px var(--wr-hairline-2); }
  .bd-face-none { box-shadow: 0 0 0 1px var(--wr-hairline); opacity: 0.4; }

  /* TAP THE NUMBER, ON A PHONE. ui.score_cell anchors its breakdown panel
     to the score cell itself (position:absolute; right:0), which is right
     for a table cell on the right-hand edge of a grid and wrong for a
     compact row, where the cell sits mid-line and a 220px panel would hang
     off the left of a 390px screen. Re-anchored here to the ROW, so the
     panel opens under it at the row's own width. Nothing in ui.py is
     changed; this page states where its own panels go.

     .who-in IS THE THIRD PLACE THIS HAPPENS, and it was missed. The grid's
     name cell is flex/space-between, so the score sits at the RIGHT of a
     ~300px sticky column and its details box is only 40px wide. That box
     is position:relative (ui.py), so it - not the cell - is the containing
     block, and right:0 put a 246px panel at left:-158. Nothing scrolls
     left of the origin in LTR, and the grid's own .wr-scroll had nothing
     to scroll, so the text was not merely clipped, it was unreachable.
     Measured at 375/390/430 on both leagues: 17 panels, 136 elements at
     negative x, page scrollX 0. */
  .bd-r3, .bd-call-num, .who-in { position: relative; }
  .bd-r3 details.wr-score, .bd-call-num details.wr-score,
  .who-in details.wr-score { position: static; }
  /* white-space: normal is LOAD-BEARING, not tidiness. .bd-r3-mid is
     nowrap so the opponent code and the projection never break mid-token,
     and the breakdown panel is a DOM descendant of it - so it inherited
     nowrap and laid its four sentences out on one 2100px line, which the
     row then carried as horizontal overflow on a 375px screen. Measured,
     not guessed: tests/board_test.py pins it. td.who is nowrap for the same
     reason, so the grid's panel needs the same release. */
  .bd-r3 .wr-score-b, .bd-call-num .wr-score-b, .who-in .wr-score-b,
  .bd-r3 .bd-score-b, .bd-call-num .bd-score-b, .who-in .bd-score-b {
    left: 2px; right: 2px; min-width: 0; max-width: none;
    white-space: normal;
  }
  /* the same correction for the legend's own popover */
  .bd-lgw { position: relative; }
  .bd-lgw .wr-lgd { position: static; }
  .bd-lgw .wr-lgd-p { left: 0; right: auto; width: auto;
                      max-width: min(360px, 100%); }

  /* the drawer under a compact row or a card - same <details> as the grid */
  .bd-pl > details.bd-pop, .bd-call > details.bd-pop { margin: 0 0 4px; }
  .bd-pl > details.bd-pop > summary,
  .bd-call > details.bd-pop > summary { padding-left: 2px; max-width: none; }

  /* ---- phone: the acceptance bar --------------------------------------
     390px, zero horizontal overflow, nothing under 11px, 44px targets.
     The versus card stacks START / gutter / SIT in that order; the gutter
     becomes a full-width band rather than a narrow column. */
  @media (max-width: 700px) {
    .bd-vs { grid-template-columns: minmax(0, 1fr); }
    .bd-vs-gut { flex-direction: row; flex-wrap: wrap; justify-content: center;
                 gap: 6px 10px; }
    .bd-vs-basis { flex: 1 1 100%; }
    .bd-call { padding: 11px 11px 9px; }
    .bd-call-h .nm { font-size: 15px; }
    .bd-act { flex: 1 1 auto; min-width: 0; }
    /* THE COMPACT ROW ON A PHONE. Three columns on one line at 375px
       leaves the name about 45px, which is an ellipsis and one letter. So
       identity takes the whole first line - the name gets the full width
       it needs and still never wraps - and the opponent + projection pair
       sits opposite the verdict on the second. Two logical columns there,
       three in the row as a whole, and nothing horizontal to scroll. */
    .bd-r3 { grid-template-columns: minmax(0, 1fr) auto; column-gap: 8px;
             row-gap: 2px; padding-bottom: 6px; }
    .bd-r3-id { grid-column: 1 / -1; }
    /* The compact row's name is its ONLY way into the dossier, so it has to
       be a finger target like the card title (.bd-call-h a.pop) and the
       matrix cell (.who a.pop) already are - inline leaves it 17px tall.
       Padding alone is not enough here: .bd-r3-nm is the ellipsis box, and
       an inline-block child that overflows it gets hard-clipped mid-word
       with no ellipsis painted. So the truncation moves ONTO the anchor -
       max-width bounds it to the span, and it does its own one-line
       ellipsis. Name still never wraps; target measures 46.75px. */
    .bd-r3-nm a.pop {
      display: inline-block; max-width: 100%; vertical-align: bottom;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      padding: 12px 0;
    }
    .bd-r3-mid { gap: 6px; justify-content: flex-start; }
    .bd-grp { position: static; }
  }
  @media print {
    .bd-mx > .bd-blk { display: block !important; }
    .bd-call, .bd-pl { break-inside: avoid; }
    .bd-acts { display: none; }
  }
"""


# --- the one script, and the bound on what it may do ------------------------
#
# DEFERRED DETAIL. Everything this does is RELOCATE a <details> the server
# already wrote into the shared <dialog> and call showModal(). It creates no
# content, fetches nothing, and stores nothing. Read it as the definition of
# what "one exception to no-script" is allowed to mean here:
#
#   * it bails out immediately if <dialog>/showModal is missing, leaving the
#     anchor's href to jump to the drawer - the fallback IS the default path;
#   * showModal() (not .open = true) is what buys the top layer, the inert
#     background, the ::backdrop, Escape-to-dismiss and the focus trap. The
#     close button carries `autofocus`, so focus lands INSIDE the dialog and
#     the trap has something to hold;
#   * a marker node remembers where the drawer came from, and the dialog's
#     own `close` event puts it back - so the dossier exists exactly once in
#     the document and find-in-page keeps working after the pop-out closes;
#   * the previous open state is restored too, so promoting a row to the
#     pop-out and closing it does not silently expand a collapsed row.
#
# It is deliberately one delegated listener on the document rather than a
# listener per row: 17 rows today, but the wire and the off-roster block
# push that past 30, and 30 listeners to open one dialog is waste.
_SCRIPT = """
(function () {
  var dlg = document.getElementById('%(dlg)s');
  var slot = document.getElementById('%(slot)s');
  if (!dlg || !slot || typeof dlg.showModal !== 'function') return;
  var mark = document.createComment('drawer'), live = null, wasOpen = false;

  function restore() {
    if (live && mark.parentNode) {
      mark.parentNode.insertBefore(live, mark);
      mark.parentNode.removeChild(mark);
      live.open = wasOpen;
    }
    live = null;
  }
  dlg.addEventListener('close', restore);

  /* Escape. showModal() already dismisses on Escape wherever the close
     request is implemented, and this listener is not a replacement for
     that - it is insurance, because the button is LABELLED "Close (Esc)"
     and a label is a promise. The `open` guard means whichever path gets
     there first, `close` fires exactly once and the drawer is restored
     exactly once. Verified by keyboard against the rendered page. */
  dlg.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && dlg.open) { ev.preventDefault(); dlg.close(); }
  });

  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('[data-pop]')
                                           : null;
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
    var el = document.getElementById(a.getAttribute('data-pop'));
    if (!el) return;                 /* nothing to move: let the href jump */
    ev.preventDefault();
    if (dlg.open) { dlg.close(); }
    el.parentNode.insertBefore(mark, el);
    wasOpen = !!el.open;
    slot.appendChild(el);
    el.open = true;
    live = el;
    var t = dlg.querySelector('.bd-dlg-t, .wr-sheet-t');
    if (t) { t.textContent = a.getAttribute('data-pop-title') || 'detail'; }
    dlg.showModal();
  });

  /* THE SWITCH. Calls / Locked in / Bench / All is a row of fragment
     links; with the script off :target does the filtering in CSS. With it
     on, the click is intercepted so the page does not jump, the block
     container takes a data-view attribute and the same CSS hides the
     other blocks. The value is read off data-seg, a data-value, the
     href's hash or the label text, in that order, so the design system's
     own control works here the day it lands without this handler knowing
     its markup. */
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest
      ? ev.target.closest('[data-seg-wrap] a, [data-seg-wrap] button') : null;
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
    var box = a.closest('[data-seg-wrap]');
    var wrap = box && box.parentNode ? box.parentNode.querySelector('.bd-mx')
                                     : null;
    if (!wrap) return;
    var v = a.getAttribute('data-seg') || a.getAttribute('data-value')
      || (a.getAttribute('href') || '').replace(/^#(seg-)?/, '')
      || a.textContent.trim().toLowerCase();
    ev.preventDefault();
    wrap.setAttribute('data-view', v);
    var all = box.querySelectorAll('a, button');
    for (var i = 0; i < all.length; i++) {
      var on = all[i] === a;
      if (on) { all[i].setAttribute('aria-current', 'true'); }
      else { all[i].removeAttribute('aria-current'); }
      if (all[i].hasAttribute('aria-selected')) {
        all[i].setAttribute('aria-selected', on ? 'true' : 'false');
      }
    }
  });
})();
""" % {"dlg": DLG_ID, "slot": DLG_SLOT}


def _sheets_script_fallback() -> str:
    """No design-system sheet script yet: the dialog promoter above already
    makes the pop-out a bottom sheet under 700px (CSS) and a modal above.
    Nothing to add."""
    return ""


def sheets_script_html() -> str:
    """ui.sheets_script() ONCE per page when it exists, else nothing."""
    return _via_ui("sheets_script", _sheets_script_fallback)


def _dialog_fallback(dom, title, body_html, summary_html) -> str:
    """The page's own pop-out shell: a bare <dialog> with a native close
    (form method=dialog, so it needs no script), autofocus to anchor the
    focus trap, and the slot the promoter fills. Under 700px the CSS
    pins it to the bottom edge at a medium detent."""
    return (
        '<dialog id="%s" class="bd-dlg" aria-label="%s">'
        '<div class="bd-dlg-bar">'
        '<span class="t bd-dlg-t">%s</span>'
        '<form method="dialog">'
        '<button class="bd-x" value="close" autofocus>Close (Esc)</button>'
        '</form></div>%s</dialog>'
        % (_esc(dom), _esc(title), _esc(title), body_html))


def dialog_html() -> str:
    """The ONE shared pop-out plus its script.

    THE POP-OUT IS ui.sheet WHEN IT EXISTS: the design system's bottom
    sheet (medium detent on a phone, a centred card from 701px, its own
    handle and close control) is rendered ONCE with an empty slot as its
    body, and the promoter moves the clicked row's drawer into that slot.
    The dossier therefore lives in the document exactly once - in its
    drawer, a native <details> that opens in place with scripting off -
    and the sheet is only ever a container for it. ui.sheets_script()
    rides after it once (close button, backdrop); the promoter supplies
    the open and the restore. With no ui.sheet the page's own <dialog>
    is the shell, styled to the same detent.

    Empty on purpose: a <dialog> with no `open` attribute renders nothing,
    so with JavaScript off this contributes zero pixels and zero claims.
    """
    slot = '<div id="%s" class="bd-dlg-slot"></div>' % DLG_SLOT
    shell = _via_ui("sheet", _dialog_fallback, DLG_ID, "player detail",
                    slot, "player detail")
    return ('<div class="bd-dlgw">%s</div>\n<script>%s</script>%s'
            % (shell, _SCRIPT, sheets_script_html()))


# --- shell helpers ----------------------------------------------------------

def _card(title: str, body_html: str, notes: Optional[Sequence[str]] = None,
          count_note: str = "") -> str:
    """One section: a .wr-card with the shared gold-rule section head."""
    return ("<section class=\"wr-card bd-sec\">%s%s</section>"
            % (ui.section_header(title, count_note or None,
                                 [n for n in (notes or []) if n]),
               body_html))


def _degraded(title: str, exc: BaseException) -> str:
    """A dead section says so, in place, carrying its own error."""
    return ("<section class=\"wr-card bd-sec\">%s%s</section>"
            % (ui.section_header(title), ui.degraded_banner(title, exc)))


def _one_line(text: str, limit: int = 240) -> str:
    """Collapse any message to a single readable line."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def _guard(title: str, builder: Callable[[], str],
           failures: Optional[List[str]] = None) -> str:
    """Run one section builder; a failure renders a visible degradation
    card instead of dropping the section (honest-degradation contract).

    `failures`, when given, also collects a one-line record of what died.
    Sections that ARBITRATE other sections' output (the divergence panel)
    read that list so they can state what they could not see instead of
    reporting the silence as if it were a finding.
    """
    try:
        return builder()
    except SystemExit:              # config errors belong to the CLI
        raise
    except BaseException as exc:    # noqa: BLE001 - the card shows the error
        if isinstance(exc, KeyboardInterrupt):
            raise
        if failures is not None:
            failures.append("%s could not be built (%s: %s)"
                            % (title.split(" - ")[0], type(exc).__name__,
                               _one_line(str(exc).strip()
                                         or type(exc).__name__, 120)))
        return _degraded(title, exc)


def _label_chip(label: str, tone: str = "unfiled", title: str = "") -> str:
    """A LOCAL chip for a model call that is not a verdict.

    ui.verdict_chip speaks START / SIT / FLEX / TOSS-UP and nothing else,
    and the wire's model column says BURN, HOLD, FAAB 12%, PASS, TRADE FOR,
    OPEN, NO MATCH. ui.py has no labelled chip, so this reuses its .wr-chip
    weight classes - `start` is the gold fill (an affirmative call), `sit`
    the ghost outline (a pass), `unfiled` the hollow slot (no call at all)
    - and adds no colour of its own.
    """
    tone = tone if tone in ("start", "sit", "lean", "none", "unfiled") \
        else "unfiled"
    attrs = ' title="%s"' % _esc(title) if title else ""
    return ('<span class="wr-chip wr-chip-%s wr-chip-sm bd-lchip"%s>'
            '<span class="wr-chip-l">%s</span></span>'
            % (tone, attrs, _esc(label)))


# --- pure matrix construction ----------------------------------------------

def short_name(source: Dict) -> str:
    """A column-width label for a source.

    Built-in feeds reuse the terminal strip's short tags so one voice reads
    the same everywhere; a creator's name is cut at its first separator
    ("The Favorites / Action Network" -> "The Favorites"). The FULL name and
    weight always ride in the column's title attribute, so nothing is lost -
    only the label gets shorter. On the v3 board the label is what the
    stacked mobile layout prints beside each cell; the header itself is the
    source's face.
    """
    sid = source.get("id")
    tag = consensus_mod.SHORT_NAMES.get(sid)
    if tag:
        return tag
    name = " ".join(str(source.get("name") or sid or "?").split())
    for sep in (" / ", "/", " (", "(", " - ", ":"):
        cut = name.find(sep)
        if cut > 2:
            name = name[:cut].strip()
    if len(name) > 20:
        name = name[:19].rstrip() + "…"
    return name


def source_columns(sources: Sequence[Dict],
                   perf: Optional[Dict] = None) -> List[Dict]:
    """Enabled sources as matrix columns: weight desc, share normalized.

    The share is what the weight is actually WORTH on a row where every
    source votes - the number the masthead shows, so a 17 next to a 10 is
    never mistaken for a percentage it is not.

    REPUTATION AT THE POINT OF USE. `perf` is engine/performance.py's
    source_scoreboard() output; when it is given, each column also carries
    that source's record under "perf". When it is NOT given - because the
    scoreboard could not be read - the key is absent and every renderer
    below prints "reputation unavailable" rather than a default state. That
    asymmetry is the point: "STEADY" is a claim, and a claim we cannot
    support may not be the fallback for a failure to read.

    Each column also carries `source`: the registry dict trimmed to what
    ui.nameplate() needs (id, name, type), so the face drawn in the header
    is the same face drawn in the divergence cards and the dossier.
    """
    ordered = sorted(sources, key=lambda s: (-consensus_mod._w(s),
                                             str(s.get("id"))))
    total = sum(consensus_mod._w(s) for s in ordered) or 1.0
    by_src = dict((r.get("source"), r)
                  for r in ((perf or {}).get("rows") or []))
    cols = []
    for i, s in enumerate(ordered):
        w = consensus_mod._w(s)
        cols.append({
            "id": s.get("id"),
            "name": s.get("name") or s.get("id"),
            "short": short_name(s),
            "handle": (s.get("handle") or "").strip(),
            "type": (s.get("type") or "").strip().lower(),
            "weight": w,
            "share": 100.0 * w / total,
            "top": i == 0,
            "perf": by_src.get(s.get("id")),
            "source": {"id": s.get("id"), "name": s.get("name") or s.get("id"),
                       "type": (s.get("type") or "").strip().lower()},
        })
    return cols


# The five states engine/performance.py can return, and what each one is
# ALLOWED to look like here. HOT/COLD are ui.py badges; STEADY and the two
# honest-absence states are WORDS, because ui.streak_badge() renders an
# unknown state as "STEADY" - correct for a player with no trend, a lie for
# a source that has never been graded. A source with no record must read as
# "no record", never as "steady".
PERF_STATES = ("HOT", "COLD", "STEADY", "LOW-CONFIDENCE", "NO-DATA")
_UI_STREAK = {"HOT": "hot", "COLD": "cold", "STEADY": "steady"}


def streak_badge_html(state: Optional[str], size: str = "sm",
                      title: str = "") -> str:
    """One reputation badge, or an honest muted statement of absence."""
    key = str(state or "").strip().upper()
    if key in ("HOT", "COLD"):
        return ui.streak_badge(_UI_STREAK[key], size=size)
    if key == "STEADY":
        return ui.streak_badge("steady", size=size)
    label = key if key in PERF_STATES else "NO READ"
    hint = title or ("engine/performance.py has graded no call for this "
                     "source on this basis")
    return ('<span class="st-w" title="%s">%s</span>'
            % (_esc(hint), _esc(label)))


def header_state(perf: Optional[Dict]) -> str:
    """The form word a column header carries, for ui.nameplate(state=...).

    None (the record could not be read) -> NO READ, in words - never a
    default state. The nameplate draws HOT/COLD as badges and every other
    state as the word itself.
    """
    if perf is None:
        return "NO READ"
    state = str(perf.get("state") or "NO-DATA").strip().upper()
    return state if state in PERF_STATES else "NO READ"


def _pct_or(value, dash: str = "—") -> str:
    """A rate as a percentage, or the dash. None is NOT 0%."""
    if value is None:
        return dash
    try:
        return "%d%%" % int(round(100.0 * float(value)))
    except (TypeError, ValueError):
        return dash


def basis_label(row: Optional[Dict]) -> str:
    """What the headline number on a scoreboard row actually rests on.

    `provenance` comes straight from performance.py: "live", "backfill-2025"
    or "none". A backfilled figure is a RECONSTRUCTION of a past call, so it
    is labelled every single time it is printed - never shown bare next to a
    live number as though the two were the same kind of fact.
    """
    if not row:
        return ""
    prov = row.get("provenance") or "none"
    if prov == "none":
        return "no graded calls"
    if prov == perf_mod.PROV_LIVE:
        return "live %d ledger" % weekly.SEASON
    return "%s (reconstructed archive)" % prov


def basis_short(row: Optional[Dict]) -> str:
    """The same fact, in the width a column header actually has.

    Still a label, not a bare number: "2025" in front of a rate says the
    rate is not from this season, which is the claim that matters. The full
    sentence rides in the header's title attribute and is spelled out in
    the scoreboard section below, so nothing is only implied.
    """
    if not row:
        return ""
    prov = row.get("provenance") or "none"
    if prov == "none":
        return ""
    if prov == perf_mod.PROV_LIVE:
        return "live"
    return prov.replace("backfill-", "")


def divergence_level(row: Optional[Dict]) -> int:
    """How loudly this row disagrees with itself.

    LVL_TOP is the alarm the user asked for BY NAME - "TOP SOURCE
    DISSENTS" - so it fires on exactly one signal: consensus.build_rows'
    `top_disagrees`, which is computed from the top-weighted source's own
    vote (against the weighted verdict, or against the engine).

    `vs_engine` is a DIFFERENT fact: the weighted verdict differs from the
    engine's vote, which says nothing about who the heaviest voice is - it
    is true even when the top-weighted source filed no vote on this row at
    all (consensus.py sets top_disagrees=False there, because the top
    source did not speak). Reading it as the top-source alarm printed "the
    heaviest-weighted voice differs" about a voice that never voted. The
    room still points both ways in that case, so it earns LVL_SPLIT.

    A unanimous row - including a row with only one voice - is LVL_NONE,
    and a one-voice row is never dressed up as agreement.
    """
    if not row:
        return LVL_NONE
    if row.get("top_disagrees"):
        return LVL_TOP
    if (row.get("vs_engine")
            or row.get("agreement") in ("SPLIT", "MAJORITY",
                                        "LONE-DISSENT")):
        return LVL_SPLIT
    return LVL_NONE


def split_weight(row: Optional[Dict]) -> int:
    """Weight share (0-50) sitting on the LOSING side of the verdict.

    50 = the room is exactly halved; 0 = nobody dissents. This is the
    divergence panel's sort key, so "biggest split first" means the most
    weight in disagreement, not merely the most voices.
    """
    if not row:
        return 0
    pct = int(row.get("pct") or 0)
    return min(pct, 100 - pct)


def vote_cell(vote: Optional[Dict]) -> Dict:
    """One matrix cell. None -> an explicit 'no opinion', never a blank.

    `verdict` is the key ui.verdict_chip() draws (start / sit / flex), or
    None for the hollow "no opinion filed" chip. A call's detail ("rank
    WR12") and its quote ride in the title; the chip itself prints the
    verdict word, because the word is what the weight encodes.
    """
    if vote is None:
        return {"label": "—", "verdict": None, "title": "no opinion filed"}
    verdict = str(vote.get("verdict") or "").strip().lower()
    key = VERDICT_KEYS.get(verdict)
    label = (key or verdict).upper() if (key or verdict) else "—"
    bits = ["%s: %s" % (vote.get("name") or vote.get("source"),
                        vote.get("detail") or verdict)]
    if vote.get("confidence"):
        bits.append("confidence %s" % vote["confidence"])
    if vote.get("quote"):
        bits.append("“%s”" % _trim(vote["quote"]))
    if vote.get("sized_for"):
        bits.append("%s - %s" % (vote.get("size_rank") or "league size",
                                 vote["sized_for"]))
    return {"label": label, "verdict": key, "title": " | ".join(bits),
            "detail": vote.get("detail") or ""}


_MODEL_KEYS = {"START": "start", "SIT": "sit", "FLEX": "flex",
               "EVEN": "even"}


def model_cell(row: Optional[Dict]) -> Dict:
    """The YOUR MODEL column for a consensus row.

    `verdict` (start / sit / flex / even) is what ui.verdict_chip draws,
    with `pct_n` as the chip's percentage; `label`/`pct` are the same facts
    as text for the peek line and the dossier.
    """
    if not row:
        return {"label": "NO READ", "verdict": None, "tone": "unfiled",
                "pct": "", "pct_n": None,
                "agree": "no voice filed an opinion", "hot": False,
                "title": "no enabled source and no built-in feed voted on "
                         "this player"}
    verdict = row["verdict"]
    key = _MODEL_KEYS.get(str(verdict).upper())
    agree = row["agreement"]
    if row.get("dissenter"):
        agree += " - dissenter: %s" % row["dissenter"]
    pct_n = consensus_mod.display_pct(row)
    return {
        "label": verdict, "verdict": key,
        "tone": key or "unfiled",
        "pct": "%d%%" % pct_n, "pct_n": pct_n,
        "agree": agree, "hot": bool(row.get("top_disagrees")
                                    or row.get("vs_engine")),
        "note": row.get("top_note") or "",
        "title": consensus_mod.format_voices(row, max_quote=60),
    }


_DOM_SAFE = "abcdefghijklmnopqrstuvwxyz0123456789"


def dom_id(prefix: str, key: str, seq: int) -> str:
    """A stable, collision-proof element id for one row's drawer.

    Player keys are "name|POS", which is not a legal bare id fragment and
    which repeats across sections (an owned player can also appear in the
    off-roster block). `seq` is appended so two rows for the same player in
    different sections still get distinct ids - a duplicate id would send
    every pop-out to whichever drawer the browser found first.
    """
    flat = "".join(ch if ch in _DOM_SAFE else "-"
                   for ch in str(key or "row").lower())[:40]
    return "%s-%s-%d" % (prefix, flat.strip("-") or "row", seq)


def make_row(group: str, slot: str, name: str, pos: str, team: str,
             key: str, cons_row: Optional[Dict], cols: Sequence[Dict],
             model: Optional[Dict] = None, meta: str = "",
             relevance: str = "", matchup: Optional[Dict] = None) -> Dict:
    """One matrix row: the player, a cell per source column, a model cell.

    `model` overrides the YOUR MODEL cell - the wire section swaps the
    start/sit verdict for an add or trade verdict while keeping every
    source column identical, which is what lets a candidate be read
    against an owned player without re-learning the shape.

    `matchup` is engine/matchups.py's matchup_for() dict for this player,
    or None when that read was unavailable. It is carried, never
    substituted: a missing matchup shows as missing in the dossier.
    """
    by_src = {}
    if cons_row:
        for v in cons_row.get("votes") or []:
            by_src[v.get("source")] = v
    level = divergence_level(cons_row)
    return {
        "group": group, "slot": slot, "player": name, "pos": pos,
        "team": team, "key": key, "meta": meta, "relevance": relevance,
        "cells": [vote_cell(by_src.get(c["id"])) for c in cols],
        "model": model if model is not None else model_cell(cons_row),
        "level": level, "marker": MARKERS.get(level, ""),
        "cons": cons_row, "split": split_weight(cons_row),
        "voices": len(by_src), "matchup": matchup,
    }


# --- the model's arithmetic, written out ------------------------------------

def weighted_math(cons_row: Optional[Dict]) -> Dict:
    """The weighted verdict as terms a reader can add up themselves.

    This re-derives, rather than re-states, what consensus.weigh() did:
    each voting source's raw weight, its share of THE SOURCES THAT ACTUALLY
    VOTED (not of the whole registry - a source that stayed silent dilutes
    nobody), the verdict's value (+1 start / +0.5 flex / -1 sit) and the
    product. The terms sum to the score consensus already published, and
    `checks` records whether they do: if this function and consensus ever
    disagree, the page says so instead of quietly showing plausible
    arithmetic for a different number.

    The all-zero-weights case follows weigh() exactly - an equal split,
    because silence about weights is not a verdict about them.
    """
    if not cons_row:
        return {"terms": [], "total": 0.0, "score": 0.0, "shown": 0.0,
                "checks": True, "equal_split": False, "pct": 50,
                "verdict": "NO READ", "display_pct": 50}
    votes = list(cons_row.get("votes") or [])
    total = sum(float(v.get("weight") or 0.0) for v in votes)
    equal = total <= 0
    terms = []
    shown = 0.0
    for v in votes:
        w = float(v.get("weight") or 0.0)
        value = consensus_mod.VERDICT_VALUE.get(v.get("verdict"), 0.0)
        share = (1.0 / len(votes)) if (equal and votes) else (
            w / total if total > 0 else 0.0)
        contrib = share * value
        shown += contrib
        terms.append({
            "source": v.get("source"),
            "name": v.get("name") or v.get("source"),
            "weight": w, "share": share, "value": value,
            "verdict": v.get("verdict"), "contrib": contrib,
            "sized_for": v.get("sized_for") or "",
            "factor": v.get("weight_factor"),
        })
    score = float(cons_row.get("score") or 0.0)
    return {
        "terms": terms, "total": total, "score": score,
        "shown": round(shown, 4), "equal_split": equal,
        "checks": abs(round(shown, 3) - round(score, 3)) <= 0.002,
        "pct": cons_row.get("pct"), "verdict": cons_row.get("verdict"),
        "display_pct": consensus_mod.display_pct(cons_row),
    }


def side_votes(cons_row: Dict, start_side: bool) -> List[Dict]:
    """The votes on one side of a row, heaviest first."""
    side = []
    for v in cons_row.get("votes") or []:
        value = consensus_mod.VERDICT_VALUE.get(v.get("verdict"), 0.0)
        if (value > 0) == bool(start_side) and value != 0:
            side.append(v)
    side.sort(key=lambda v: (-float(v.get("weight") or 0.0),
                             str(v.get("source"))))
    return side


def tally_text(cons_row: Dict) -> Tuple[int, int, int, int]:
    """(start voices, start weight %, sit voices, sit weight %)."""
    s_n = b_n = 0
    s_w = b_w = 0.0
    for v in cons_row.get("votes") or []:
        value = consensus_mod.VERDICT_VALUE.get(v.get("verdict"), 0.0)
        w = float(v.get("weight") or 0.0)
        if value > 0:
            s_n += 1
            s_w += w
        elif value < 0:
            b_n += 1
            b_w += w
    total = (s_w + b_w) or 1.0
    return s_n, int(round(100.0 * s_w / total)), b_n, \
        int(round(100.0 * b_w / total))


# --- THE CALL AS A PERCENTAGE, AND WHY ---------------------------------------
# "START · 67% of the room" is the model column's language: the share of
# the room's WEIGHT that sits behind the call. A percentage on its own can
# mislead in exactly two ways, and each gets a one-line WHY beneath the
# chip - derived, never composed:
#
#   WEIGHT DECIDED IT. The call is not the simple majority of voices: fewer
#   voices (or as many) won because they carry more weight. Derived from
#   the consensus row's own votes and weights (weight_why).
#   THE SLOT DECIDED IT. A bench player polls HIGHER for START than the man
#   the lineup seated in a slot he is eligible for. The lineup fills slots
#   on projection, not on the poll, so the reason is the projection gap -
#   read off engine/lineup's build (slot_why).
#
# When neither can be derived the line is omitted. There is no third
# source of reasons and no fallback sentence.

def weight_why(cons_row: Optional[Dict]) -> str:
    """'START on weight: 2 of 5 voices carry 61% of the room; the 3
    dissenters share 39%' - or '' when a plain majority decided it."""
    if not cons_row:
        return ""
    verdict = str(cons_row.get("verdict") or "").upper()
    if verdict not in ("START", "SIT"):
        return ""
    s_n, s_pct, b_n, b_pct = tally_text(cons_row)
    if verdict == "START":
        win_n, win_pct, lose_n, lose_pct = s_n, s_pct, b_n, b_pct
    else:
        win_n, win_pct, lose_n, lose_pct = b_n, b_pct, s_n, s_pct
    total = win_n + lose_n
    if total < 2 or lose_n == 0 or win_n > lose_n:
        return ""                  # a simple majority: nothing to explain
    if win_n == lose_n:
        return ("%d voice%s each way - the weight decides it: %d%% of the "
                "room behind %s, %d%% behind the other side"
                % (win_n, "" if win_n == 1 else "s", win_pct, verdict,
                   lose_pct))
    return ("%s on weight: %d of %d voices carry %d%% of the room; the %d "
            "dissenter%s share %d%%"
            % (verdict, win_n, total, win_pct, lose_n,
               "" if lose_n == 1 else "s", lose_pct))


def _start_share(row: Optional[Dict]) -> Optional[int]:
    """The start-ward share of the room on a matrix row, or None."""
    cons = (row or {}).get("cons")
    if not cons:
        return None
    try:
        return int(cons.get("pct"))
    except (TypeError, ValueError):
        return None


def slot_why(rows: Sequence[Dict], lineup_build: Optional[Dict]) -> int:
    """Mark the rows where the lineup's slot logic, not the poll, decided.

    For every seated starter, the highest-polling BENCH player eligible for
    that slot who polls higher for START gets both rows a line: the
    starter's says who polls higher and why he still sits (the projection
    gap the lineup filled the slot on); the bench row says the same from
    his side. Only stated when the projections actually explain it - a
    starter projected BELOW the bench man is a case this function cannot
    explain and says nothing about. Returns the number of rows marked.
    """
    if not lineup_build or not rows:
        return 0
    by_key = dict((r["key"], r) for r in rows
                  if r.get("key") and r.get("cons"))
    meta = lineup_build.get("meta") or {}
    bench = [p for p in (lineup_build.get("bench") or [])
             if p is not None and p.key in by_key]

    def _proj(player) -> Optional[float]:
        m = meta.get(player.key) or {}
        return m.get("weekly")

    marked = 0
    starters = [(slot, p) for slot, p in (lineup_build.get("rows") or [])
                if p is not None and p.key in by_key]
    # weakest-polling starter first, so a bench man contested by two slots
    # is explained against the seat he came closest to winning.
    starters.sort(key=lambda sp: (_start_share(by_key[sp[1].key]) or 0))
    for slot, starter in starters:
        s_row = by_key[starter.key]
        s_pct = _start_share(s_row)
        if s_pct is None:
            continue
        elig = FLEX_ELIGIBLE.get(str(slot).upper()) or [starter.pos]
        cands = [b for b in bench if b.pos in elig and b.key != starter.key
                 and (_start_share(by_key[b.key]) or 0) > s_pct]
        if not cands:
            continue
        b = max(cands, key=lambda q: (_start_share(by_key[q.key]) or 0,
                                      q.name))
        b_row = by_key[b.key]
        b_pct = _start_share(b_row) or 0
        ps, pb = _proj(starter), _proj(b)
        if pb is None and ps is not None:
            s_line = ("%s polls higher for START (%d%% vs %d%%) but has no "
                      "weekly projection filed, so the lineup cannot seat "
                      "him in the %s" % (b.name, b_pct, s_pct, slot))
            b_line = ("polls %d%% START, but no weekly projection is filed "
                      "for him, so the lineup cannot seat him over %s (%s "
                      "%.1f)" % (b_pct, starter.name, slot, ps))
        elif ps is not None and pb is not None and ps > pb:
            s_line = ("%s polls higher for START (%d%% vs %d%%) but the "
                      "lineup fills the %s on projection: %s %.1f vs %s %.1f"
                      % (b.name, b_pct, s_pct, slot, starter.surname(), ps,
                         b.surname(), pb))
            b_line = ("polls %d%% START, but the lineup fills the %s on "
                      "projection and has %s ahead: %.1f vs %.1f"
                      % (b_pct, slot, starter.name, ps, pb))
        else:
            continue               # the projections do not explain it
        if not s_row.get("slot_why"):
            s_row["slot_why"] = s_line
            # THE PROJECTION FOR BOTH MEN. A decision card that says "the
            # slot decided it" has to show the two numbers the slot was
            # decided on, so the pair is carried structurally and not only
            # inside the sentence.
            s_row["vs"] = {"name": b.name, "proj": pb, "mine": ps,
                           "slot": slot, "side": "seated"}
            marked += 1
        if not b_row.get("slot_why"):
            b_row["slot_why"] = b_line
            b_row["vs"] = {"name": starter.name, "proj": ps, "mine": pb,
                           "slot": slot, "side": "benched"}
            marked += 1
    return marked


def call_why(row: Dict) -> str:
    """The WHY line under the model's call, or '' when none is derivable."""
    bits = [weight_why(row.get("cons")), row.get("slot_why") or ""]
    return " · ".join(b for b in bits if b)


def is_unanimous(row: Dict) -> bool:
    """Two or more voices, all pointing the same way. A single voice is not
    'unanimous' - it is one opinion - and is never marked as agreement."""
    cons = row.get("cons") or {}
    votes = cons.get("votes") or []
    return len(votes) >= 2 and str(cons.get("agreement") or "").upper() \
        == "UNANIMOUS"


# --- THE CALLS: who genuinely needs deciding, and on what ground -------------
# The whole page now hangs off this predicate, so it is written to be read:
# four grounds, each traced to the module that owns the fact, each carrying
# the sentence the card prints. A ground that cannot be checked (a dead
# matchup table, no DEF/K read) does NOT silently return False - the caller
# asks call_coverage() what did not run and prints it, because "no card"
# and "no check" are different claims.

def matchup_grade(row: Optional[Dict]) -> str:
    """The row's matchup grade in upper case, or '' when there is none."""
    m = (row or {}).get("matchup") or {}
    return str(m.get("pa_grade") or "").strip().upper()


def call_reasons(row: Optional[Dict]) -> List[Dict]:
    """Every ground on which this row needs a decision, strongest first.

    Empty list = this row does not need one. The four grounds:

      TOP SOURCE DISSENTS - consensus' own top_disagrees (LVL_TOP).
      SPLIT - the room points both ways (LVL_SPLIT).
      MATCHUP CONTRADICTS THE ROOM - the room agrees and the matchup grade
        points the other way. A unanimous START into an AVOID is the case
        the owner asked for BY NAME, and it is framed as TEMPER
        EXPECTATIONS: the room was unanimous, the grade is context, and
        this page has no basis for turning one grade into a bench call.
      STREAM / TOSS-UP - engine/dk says the held DST or K is not a HOLD.

    A LOCKED row raises nothing: his game has kicked off, so the decision
    is over and a card would be asking for something that cannot be given.
    """
    row = row or {}
    if (row.get("lock") or {}).get("locked"):
        return []
    out: List[Dict] = []
    cons = row.get("cons") or None
    level = int(row.get("level") or LVL_NONE)
    votes = list((cons or {}).get("votes") or [])

    if level >= LVL_TOP:
        out.append({
            "kind": CALL_TOP, "mark": MARKERS[LVL_TOP],
            "line": (cons or {}).get("top_note")
                    or "your heaviest-weighted voice differs from the "
                       "verdict your model reached.",
        })
    elif level >= LVL_SPLIT:
        s_n, s_pct, b_n, b_pct = tally_text(cons) if cons else (0, 0, 0, 0)
        out.append({
            "kind": CALL_SPLIT, "mark": MARKERS[LVL_SPLIT],
            "line": ("the room points both ways: %d voice%s (%d%% of the "
                     "weight) say%s START, %d (%d%%) say%s SIT."
                     % (s_n, "" if s_n == 1 else "s",
                        s_pct, "s" if s_n == 1 else "",
                        b_n, b_pct, "s" if b_n == 1 else "")),
        })

    call = row.get("dk") or None
    if call and str(call.get("verdict") or "") in ("STREAM", "TOSS-UP"):
        out.append({
            "kind": CALL_STREAM, "mark": str(call["verdict"]),
            "line": ("engine/dk rates the man you hold against the best "
                     "genuinely available one: %s"
                     % dk_mod.board_line(call)),
        })

    # THE MATCHUP CONTRADICTS THE ROOM. Only meaningful when the room
    # actually agreed - a split row is already a call, and a row nobody
    # voted on has no room to contradict.
    grade = matchup_grade(row)
    verdict = str((cons or {}).get("verdict") or "").upper()
    if (cons and votes and level == LVL_NONE and grade
            and CONTRA.get(verdict) == grade):
        m = row.get("matchup") or {}
        who = "every voice that spoke" if len(votes) > 1 else "the one voice"
        if verdict == "START":
            head = "TEMPER EXPECTATIONS"
            line = ("%s says START and the matchup is the worst grade there "
                    "is. This is NOT a recommendation to bench him - the "
                    "room agreed and one grade does not overturn it - it is "
                    "a warning about the ceiling. %s"
                    % (who.capitalize(), m.get("evidence")
                       or m.get("reason") or "no evidence sentence filed."))
        else:
            head = "THE MATCHUP ARGUES BACK"
            line = ("%s says SIT into the best grade there is. Worth a "
                    "second look before you leave him out; the room still "
                    "says sit. %s"
                    % (who.capitalize(), m.get("evidence")
                       or m.get("reason") or "no evidence sentence filed."))
        out.append({"kind": CALL_MATCHUP, "mark": head, "line": line})

    out.sort(key=lambda r: -CALL_RANK.get(r["kind"], 0))
    return out


def is_call(row: Optional[Dict]) -> bool:
    """Does this row need a decision? The one predicate the page orders on."""
    return bool(call_reasons(row))


def call_rank(row: Dict) -> int:
    """The strongest ground this row raises, as a number (0 = no call)."""
    return max([CALL_RANK.get(r["kind"], 0)
                for r in call_reasons(row)] or [0])


def call_rows(rows: Sequence[Dict]) -> List[Dict]:
    """The rows that need deciding, strongest ground first.

    Roster rows only. A waiver candidate or a trade target is a different
    question with its own section and its own verdict vocabulary, and
    mixing them in here would make "the calls" mean two things at once.
    """
    picked = [r for r in rows
              if str(r.get("group") or "").upper() in ("STARTING", "BENCH")
              and is_call(r)]
    picked.sort(key=lambda r: (-call_rank(r), -int(r.get("split") or 0),
                               -int(r.get("voices") or 0),
                               str(r.get("player") or "")))
    return picked


def call_coverage(rows: Sequence[Dict], cols: Sequence[Dict],
                  matchup_err: str = "", dk_err: str = "",
                  dk_read: bool = True) -> List[str]:
    """Which of the four checks could NOT run, in words.

    This is the whole no-claim-without-data machinery for THE CALLS. An
    empty card list only MEANS "nothing needs deciding" when every ground
    was actually testable; whatever is in this list is a hole, and the
    section prints it instead of the claim.
    """
    holes: List[str] = []
    if not cols:
        holes.append("no source is enabled, so no room could be weighed at "
                     "all and neither the SPLIT nor the TOP SOURCE check "
                     "could run - enable sources with ./sources.sh")
    elif not any(r.get("voices") for r in rows):
        holes.append("no player row carried a single filed vote this week, "
                     "so the SPLIT and TOP SOURCE checks had nothing to "
                     "weigh")
    if matchup_err:
        holes.append("matchup grades could not be read (%s), so the "
                     "matchup-contradicts-the-room check DID NOT RUN"
                     % _one_line(matchup_err, 120))
    elif not any(matchup_grade(r) for r in rows):
        holes.append("no roster row carried a matchup grade, so the "
                     "matchup-contradicts-the-room check found nothing to "
                     "test rather than testing and clearing it")
    # The DEF/K ground is only a hole when there is a DEF or a K to hold.
    # A roster without one has nothing for that check to say, and printing
    # "no DEF/K read was made" there would be noise dressed as a caveat.
    if any(str(r.get("pos") or "").upper() in ("DEF", "DST", "K")
           for r in rows):
        if dk_err:
            holes.append("the DEF/K hold-or-stream call could not be read "
                         "(%s), so no card could be raised on it"
                         % _one_line(dk_err, 120))
        elif not dk_read:
            holes.append("you hold a DEF or a K but no hold-or-stream read "
                         "was made this week, so no card could be raised "
                         "on it")
    return holes


def held_by_kickoff(rows: Sequence[Dict]) -> int:
    """How many rows WOULD have raised a card if their game had not started.

    Counted exactly - by asking call_reasons the same question with the
    lock lifted - because "held back" and "never existed" are different
    facts about the same empty space, and the section prints the number.
    """
    n = 0
    for row in rows:
        if not (row.get("lock") or {}).get("locked"):
            continue
        if str(row.get("group") or "").upper() not in ("STARTING", "BENCH"):
            continue
        probe = dict(row)
        probe["lock"] = {}
        if call_reasons(probe):
            n += 1
    return n


# --- LOCK STATE, from the schedule and nothing else --------------------------

def _fmt_kick(dt: datetime) -> str:
    clock = dt.strftime("%I:%M%p").lstrip("0").lower()
    return "%s %s" % (dt.strftime("%a %m/%d"), clock)


def kickoff_state(game: Optional[Dict],
                  now: Optional[datetime] = None) -> Dict:
    """Has this team's game kicked off? Decided from the schedule's
    kickoff_iso against `now`, and from nothing else.

    NEVER GUESSED. A missing time, an unreadable time, a day-only time
    (the schedule row carried a date but no clock - engine/weekly fills
    those as 00:00, and no NFL game kicks off at midnight) or a naive
    timestamp with no zone data to resolve it all come back unlocked, with
    `text` saying why. Locking a row is a claim that the decision is over;
    that claim is made only on a real timestamp that has passed.
    """
    out = {"locked": False, "kickoff": "", "day_only": False, "text": ""}
    if not game:
        out["text"] = "no game on the schedule for this team"
        return out
    iso = str(game.get("kickoff_iso") or "").strip()
    out["kickoff"] = iso
    if not iso:
        out["text"] = "no kickoff time on the schedule - not locked on a guess"
        return out
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        out["text"] = ("kickoff unreadable (%s) - not locked on a guess"
                       % _one_line(iso, 40))
        return out
    if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
        out["day_only"] = True
        out["text"] = ("kickoff day only (%s), no clock time - not locked "
                       "on a guess" % dt.strftime("%a %m/%d"))
        return out
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
        except Exception:  # noqa: BLE001 - no tz data: cannot compare
            out["text"] = ("kickoff carries no timezone - not locked on a "
                           "guess")
            return out
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now >= dt:
        out["locked"] = True
        out["text"] = "kicked off %s ET - this row is final" % _fmt_kick(dt)
    else:
        out["text"] = "kicks off %s ET" % _fmt_kick(dt)
    return out


def apply_locks(rows: Sequence[Dict], schedule: Optional[Dict],
                now: Optional[datetime] = None) -> int:
    """Attach kickoff_state to every row with a team; returns locks set.
    schedule None (feed down) locks nothing and says so on each row."""
    n = 0
    for row in rows:
        team = norm_team(row.get("team") or "")
        if not team:
            continue
        if schedule is None:
            row["lock"] = {"locked": False, "kickoff": "", "day_only": False,
                           "text": "schedule unavailable - lock state "
                                   "unknown, not assumed"}
            continue
        st = kickoff_state(schedule.get(team), now)
        row["lock"] = st
        if st["locked"]:
            n += 1
    return n


def apply_actuals(rows: Sequence[Dict],
                  actuals: Optional[Dict[str, float]]) -> int:
    """Attach the box-score actual to LOCKED rows only. A number for a game
    that has not been played is not an actual, whatever the file says.
    `actuals` is {name key: points} for this week; None = not read."""
    if not actuals:
        return 0
    n = 0
    for row in rows:
        if not (row.get("lock") or {}).get("locked"):
            continue
        nkey = str(row.get("key") or "").partition("|")[0]
        if nkey and nkey in actuals:
            try:
                row["actual"] = float(actuals[nkey])
                n += 1
            except (TypeError, ValueError):
                continue
    return n


# --- renderers (pure: data in, html out) ------------------------------------

def _plate_source(cols_by_id: Dict, vote: Dict) -> Dict:
    """The registry dict a vote's face is drawn from - the column's, so the
    same source looks the same in the header and on the card."""
    col = cols_by_id.get(vote.get("source"))
    if col and col.get("source"):
        return col["source"]
    return {"id": vote.get("source"), "name": vote.get("name")
            or vote.get("source"), "type": "feed"}


def render_masthead(league: LeagueConfig, week: int, cols: Sequence[Dict],
                    record: str, coverage: str, roster_line: str,
                    stamp: str) -> str:
    """The page head under the shell: kicker, league, the coverage line, and
    every enabled source as a nameplate with its weight and real share."""
    plates = "".join(
        '<span class="s%s">%s</span>'
        % (" top" if c["top"] else "",
           ui.nameplate(c["source"], c["weight"], None, size=24,
                        sub="%.0f%% of the room" % c["share"]))
        for c in cols) or '<span class="note">no sources enabled</span>'
    return ('<header class="bd-mast">'
            '<p class="wr-kicker">The Board · week %d</p>'
            '<h1 class="wr-h1 wr-display">%s</h1>'
            '<p class="wr-lede">%s scoring · %d teams · record: %s · '
            'generated %s</p>'
            '<p class="bd-cov"><b>coverage:</b> %s · %s</p>'
            '<div class="srcbar">%s</div>'
            '</header>'
            % (week, _esc(league.name), _esc(league.scoring_label()),
               league.teams, _esc(record), _esc(stamp), _esc(coverage),
               _esc(roster_line), plates))


def matchup_meter_html(m: Optional[Dict], err: str = "") -> str:
    """The matchup as ui.matchup_meter - five segments, the grade word, and
    engine/matchups.py's own reason in the title. No grade draws five
    hollow segments and a dash; a grade is never invented to fill it."""
    if err or not m:
        return ui.matchup_meter(None, label=True,
                                title=_one_line(err, 160) if err
                                else "no matchup read for this row")
    return ui.matchup_meter(m.get("pa_grade"), label=True,
                            title=matchup_title(m))


def matchup_title(m: Optional[Dict], err: str = "") -> str:
    """The basis sentence every matchup glyph carries in its title.

    'matchup GOOD (4/5) vs DAL - DAL allowed 24.1 PPR pts/game to RB
    (8th-most of 32, 76th pctl, +0.8 SD) - basis: 2025 season, 17 games;
    2026 rosters and schemes have changed since.' The evidence sentence is
    engine/matchups.py's own, basis year and games included; a row with no
    grade carries matchups.py's reason instead, never a neutral stand-in.
    """
    if err:
        return "matchup read unavailable - %s" % _one_line(err, 160)
    if not m:
        return "no matchup read for this row"
    grade = str(m.get("pa_grade") or "").upper()
    opp = m.get("opponent") or ""
    where = "" if m.get("home") is None else (" (home)" if m.get("home")
                                              else " (away)")
    if not grade:
        return "matchup: %s" % (m.get("reason") or m.get("evidence")
                                or "no grade")
    steps = MATCHUP_STEPS.get(grade)
    head = "matchup %s%s%s" % (grade,
                               " (%d/5)" % steps if steps else "",
                               " vs %s%s" % (opp, where) if opp else "")
    ev = m.get("evidence") or m.get("reason") or ""
    basis = m.get("basis") or ""
    if basis and "basis:" not in ev:
        ev = ("%s - basis: %s" % (ev, basis)) if ev else "basis: %s" % basis
    return "%s - %s" % (head, ev) if ev else head


def _opp_chip_fallback(opponent, grade, home, title) -> str:
    """'vs DAL' as plain text when ui.opp_chip has not shipped."""
    if not opponent:
        return ""
    return ('<span class="bd-opp" title="%s">%s %s</span>'
            % (_esc(title), "vs" if home else "@", _esc(opponent)))


def matchup_inline_html(row: Dict, err: str = "") -> str:
    """The matchup beside the call: the opponent chip (ui.opp_chip when it
    exists) and the FIVE-STEP RATING - ui.matchup_meter, no word, the basis
    sentence in the title of both. No grade = five hollow segments; a
    failed read = hollow segments carrying the error. Never a neutral."""
    m = row.get("matchup")
    if err or not m:
        if not (err or row.get("cons")):
            return ""
        title = matchup_title(m, err)
        return ('<span class="mdl-mu">%s</span>'
                % ui.matchup_meter(None, label=False, size="sm", title=title))
    title = matchup_title(m)
    opp = _via_ui("opp_chip", _opp_chip_fallback, m.get("opponent"),
                  m.get("pa_grade"), bool(m.get("home")), title)
    meter = ui.matchup_meter(m.get("pa_grade"), label=False, size="sm",
                             title=title)
    return '<span class="mdl-mu">%s%s</span>' % (opp, meter)


# --- TAP THE NUMBER: the score cell and its breakdown ------------------------

def score_breakdown_html(row: Dict, week: Optional[int] = None) -> str:
    """What the number is made of, in the order the reader will ask:
    the projection and where it came from, what the room said, the
    matchup (context only - the projection is NOT adjusted by it, and the
    line says so), and the actual when the game has been played."""
    items = []
    proj = row.get("proj")
    src = str(row.get("proj_source") or "").strip().lower()
    src_name = {"espn": "ESPN", "sleeper": "Sleeper"}.get(src, src or "")
    if proj is None:
        items.append("<li><b>projection</b> none filed for him this week - "
                     "the lineup seats an unfiled number as 0.0, which is "
                     "an absence, not a forecast</li>")
    else:
        items.append("<li><b>projection %.1f</b> - %s weekly projection. "
                     "ESPN is primary and Sleeper fills only the players "
                     "ESPN skips; the two are never averaged, so this is "
                     "one source's number</li>"
                     % (proj, _esc(src_name or "one feed's")))
    cons = row.get("cons")
    if cons:
        s_n, s_pct, b_n, b_pct = tally_text(cons)
        items.append("<li><b>the room</b> %d START-side voice%s with %d%% of "
                     "the weight, %d SIT-side with %d%% - your model: %s at "
                     "%d%%</li>"
                     % (s_n, "" if s_n == 1 else "s", s_pct, b_n, b_pct,
                        _esc(cons.get("verdict") or "—"),
                        consensus_mod.display_pct(cons)))
    else:
        items.append("<li><b>the room</b> no voice filed an opinion on "
                     "him</li>")
    m = row.get("matchup")
    if m and m.get("pa_grade"):
        grade = str(m["pa_grade"]).upper()
        steps = MATCHUP_STEPS.get(grade)
        items.append("<li><b>matchup %s%s</b>%s - context beside the call; "
                     "the projection above is NOT adjusted by it. %s</li>"
                     % (_esc(grade), " (%d/5)" % steps if steps else "",
                        _esc(" vs %s" % m["opponent"]) if m.get("opponent")
                        else "",
                        _esc(m.get("evidence") or m.get("reason") or "")))
    elif m:
        items.append("<li><b>matchup</b> %s</li>"
                     % _esc(m.get("reason") or "no grade"))
    else:
        items.append("<li><b>matchup</b> no read for this row</li>")
    if row.get("actual") is not None:
        items.append("<li><b>actual %.1f</b> - the box score for week %s "
                     "(nflverse, offence only); the projection stays beside "
                     "it, muted, so the miss is visible</li>"
                     % (row["actual"], week if week else "?"))
    return '<ul class="bd-score-l">%s</ul>' % "".join(items)


def _score_cell_fallback(proj, actual, breakdown_html) -> str:
    """The number, tap for the breakdown. With an actual, the actual is
    bold and the projection muted beside it; without one, the projection
    is the number. No number at all prints a dash - never 0.0."""
    if actual is not None:
        face = ('<span class="bd-score-v act wr-num">%.1f</span>'
                '<span class="bd-score-p mut wr-num">proj %s</span>'
                % (float(actual), "%.1f" % float(proj) if proj is not None
                   else "—"))
    elif proj is not None:
        face = ('<span class="bd-score-v wr-num">%.1f</span>'
                '<span class="bd-score-l">proj</span>' % float(proj))
    else:
        face = ('<span class="bd-score-v wr-num">—</span>'
                '<span class="bd-score-l">no proj</span>')
    return ('<details class="bd-score"><summary class="bd-score-s" '
            'title="tap the number for its breakdown">%s</summary>'
            '<div class="bd-score-b">%s</div></details>'
            % (face, breakdown_html))


def score_cell_html(row: Dict, week: Optional[int] = None) -> str:
    """ui.score_cell(proj, actual, breakdown_html) or the local fallback.
    Rows with no weekly projection READ at all (wire rows, unresolved
    names) draw nothing: a score cell claims there is a number behind it."""
    if not row.get("has_proj"):
        return ""
    return _via_ui("score_cell", _score_cell_fallback, row.get("proj"),
                   row.get("actual"), score_breakdown_html(row, week))


def peek_line(row: Dict) -> str:
    """The one-line preview on the drawer's summary.

    PROGRESSIVE DISCLOSURE only works if the reader can tell whether
    opening is worth it. A bare chevron makes them pay a click to find out;
    this says what is behind it - how many voices spoke, how many left
    actual words, the matchup grade, and the model's own line - so an
    unopened row is still informative.
    """
    bits = []
    cons = row.get("cons")
    votes = list((cons or {}).get("votes") or [])
    quoted = sum(1 for v in votes if (v.get("quote") or "").strip())
    if votes:
        bits.append("%d voice%s" % (len(votes), "" if len(votes) == 1
                                    else "s"))
        bits.append("%d quoted" % quoted if quoted
                    else "no quote captured")
    else:
        bits.append("no voice filed an opinion")
    m = row.get("matchup") or {}
    if m.get("pa_grade"):
        bits.append("matchup %s%s" % (m["pa_grade"],
                                      " vs %s" % m["opponent"]
                                      if m.get("opponent") else ""))
    elif m.get("reason"):
        bits.append(_trim(m["reason"], 46))
    model = row.get("model") or {}
    if model.get("label"):
        bits.append("model %s%s" % (model["label"],
                                    " %s" % model["pct"]
                                    if model.get("pct") else ""))
    if row.get("dk"):
        bits.append(dk_mod.verdict_text(row["dk"]))
    return _trim(" · ".join(bits), PEEK_CHARS)


# --- the pop-out dossier ----------------------------------------------------

def _voice_block(row: Dict, cols: Sequence[Dict]) -> str:
    """Every source's verdict, its own words, and its record - in one list.

    EVERY enabled source appears, including the ones that said nothing.
    Dropping the silent ones would turn the dossier into a list of people
    who agree with something, and "this voice never mentioned him" is a
    fact the reader needs as much as any vote. Each voice is its nameplate
    - the same face as its column header - with the record as the sub-line.
    """
    by_src = {}
    for v in ((row.get("cons") or {}).get("votes") or []):
        by_src[v.get("source")] = v
    out = []
    for c in cols:
        v = by_src.get(c["id"])
        perf = c.get("perf")
        # The reputation suffix is deliberately terse HERE and spelled out
        # ONCE below the list. This line repeats under every source on every
        # row - seven times per player - so the long form would be several
        # hundred copies of the same sentence, which is noise, not honesty.
        # The season prefix ("2025") is what carries the claim: it says the
        # rate is not from this season.
        if perf is None:
            rep = "record unavailable"
        else:
            rep = "%s%s" % (perf.get("state") or "NO-DATA",
                            "" if perf.get("hit_rate") is None
                            else " · %s %s (n%d)"
                                 % (basis_short(perf),
                                    _pct_or(perf["hit_rate"]),
                                    perf["sample_n"]))
        plate = ui.nameplate(c["source"], c["weight"], None, size=24, sub=rep)
        if v is None:
            chip = ui.verdict_chip(None, size="sm", title="no opinion filed")
            words = ('<span class="q mutq">no opinion filed on %s - this '
                     'voice never mentioned him, which is silence, not '
                     'approval</span>' % _esc(row["player"]))
        else:
            cell = vote_cell(v)
            chip = ui.verdict_chip(cell["verdict"], size="sm",
                                   title=cell["title"])
            quote = (v.get("quote") or "").strip()
            if quote:
                words = ('<span class="q">&#8220;%s&#8221;%s</span>'
                         % (_esc(_trim(quote, DOSSIER_QUOTE)),
                            _esc(" (%s confidence)" % v["confidence"])
                            if v.get("confidence") else ""))
            else:
                handle = c.get("handle") or c["id"]
                meaning = (FEED_REASONS.get(handle, {})
                           .get(v.get("verdict")) or "")
                words = ('<span class="q mutq">%s</span>'
                         % _esc(meaning or "voted %s; no quote was captured "
                                "with this call" % v.get("verdict")))
            if v.get("detail"):
                words += ('<span class="q mutq"> [%s]</span>'
                          % _esc(v["detail"]))
            if v.get("sized_for"):
                words += ('<span class="q mutq"> [%s - %s, this call\'s '
                          'weight discounted]</span>'
                          % (_esc(v.get("size_rank") or "league size"),
                             _esc(v["sized_for"])))
        out.append('<div class="bd-src">%s%s%s</div>' % (plate, chip, words))
    if not out:
        return '<p class="note">no source is enabled</p>'
    # The key to the terse suffix above, stated once per dossier - it has
    # to live inside the drawer, because the drawer is what pops out.
    out.append('<p class="note">under each name: weight, then current form '
               'and the graded record. A year (%d) means a reconstruction '
               'of that season\'s archive, not a live call; NO-DATA means '
               'nothing graded. Detail: the scoreboard section, and '
               'sources.html.</p>' % perf_mod.SEASON_BACKFILL)
    return "".join(out)


def _matchup_block(row: Dict, err: str = "") -> str:
    """The matchup meter, its basis, and the sentence matchups.py wrote."""
    if err:
        return ('<p class="note warn">matchup read unavailable - %s. No '
                'grade is shown rather than a neutral one, because '
                '"neutral" is a finding and this is a failure.</p>'
                % _esc(_one_line(err, 160)))
    m = row.get("matchup")
    if not m:
        return ('<p class="note">no matchup read for this row.</p>')
    head = ('<div class="bd-ev bd-mu">%s%s</div>'
            % (matchup_meter_html(m),
               '<span class="bd-opp">vs %s</span>' % _esc(m["opponent"])
               if m.get("opponent") else ""))
    basis = ""
    if m.get("basis"):
        basis = ('<div class="bd-ev bd-basis">basis: %s</div>'
                 % _esc(m["basis"]))
    ev = ('<div class="bd-ev">%s</div>'
          % _esc(m.get("evidence") or m.get("reason") or ""))
    cav = ""
    if m.get("caveat"):
        cav = '<div class="bd-ev cav">%s</div>' % _esc(m["caveat"])
    return head + basis + ev + cav


def _math_block(row: Dict) -> str:
    """The weighted verdict, term by term.

    The reader can add the last column up and land on the score the model
    published. That is the whole point: a percentage nobody can reconstruct
    is a number you either take on faith or ignore.
    """
    cons = row.get("cons")
    if not cons:
        model = row.get("model") or {}
        bits = [b.strip() for b in str(model.get("title") or "").split("|")
                if b.strip()]
        if not bits:
            return ('<p class="note">no voice filed an opinion on this row, '
                    'so there is no weighted verdict to show.</p>')
        return ('<ul class="bd-list">%s</ul>'
                % "".join("<li>%s</li>" % _esc(b) for b in bits))
    math = weighted_math(cons)
    rows_html = []
    for t in math["terms"]:
        rows_html.append(
            "<tr><td>%s</td><td>%g</td><td>%.3f</td><td>%s</td>"
            "<td>%+.3f</td></tr>"
            % (_esc(t["name"]), t["weight"], t["share"],
               _esc("%+.1f" % t["value"]), t["contrib"]))
    note = ""
    if math["equal_split"]:
        note = ('<p class="note">every voting source carries weight 0, so '
                'the weights are split evenly - silence about weights is '
                'not a verdict about them.</p>')
    if not math["checks"]:
        note += ('<p class="note bad">these terms sum to %+.3f but the '
                 'consensus score is %+.3f - do not trust the breakdown '
                 'until that is reconciled.</p>'
                 % (math["shown"], math["score"]))
    return (
        '<div class="wr-scroll bd-mathw">'
        '<table class="bd-math"><tr><th>source</th><th>weight</th>'
        '<th>share of voters</th><th>verdict</th><th>contribution</th></tr>'
        '%s<tr class="sum"><td>weighted score</td><td></td><td></td>'
        '<td></td><td>%+.3f</td></tr></table></div>'
        '<p class="note">score &#8594; %s at %d%% (%s%s). Share is of the '
        'sources that ACTUALLY voted on this row, not of the whole '
        'registry: a source that stayed silent dilutes nobody.</p>%s'
        % ("".join(rows_html), math["score"], _esc(math["verdict"] or "—"),
           math["display_pct"], _esc(cons.get("agreement") or ""),
           _esc(" - dissenter: %s" % cons["dissenter"])
           if cons.get("dissenter") else "", note))


def _dk_block(call: Dict) -> str:
    """The DST/K row's one line: held vs the best genuinely available,
    each with its opponent read, then the top candidates and the cost.
    The verdict on this row IS this call (engine/dk), which is why the
    weighted score below it can point the other way and still be right
    about what the projection voices said."""
    out = ['<div class="bd-ev">%s</div>' % _esc(dk_mod.board_line(call))]
    cands = call.get("candidates") or []
    if cands:
        out.append('<ul class="bd-list">%s</ul>' % "".join(
            "<li>%s</li>" % _esc("%s %.2f - %s" % (c["name"], c["score"],
                                                   c.get("opp_note") or ""))
            for c in cands))
    if call.get("coverage_note"):
        out.append('<div class="bd-ev cav">%s</div>'
                   % _esc(call["coverage_note"]))
    out.append('<div class="bd-ev bd-basis">basis: %s</div>'
               % _esc(call.get("basis") or dk_mod.BASIS))
    return "".join(out)


def dossier_html(row: Dict, cols: Sequence[Dict],
                 matchup_err: str = "") -> str:
    """Everything about one player that does not belong on the row.

    Four blocks, in the order a decision actually needs them: what the room
    said (with its own words), what the schedule is about to do to him, how
    the model turned the first into a verdict, and - when the row carries a
    non-start/sit model (a waiver add, a trade target) - the components
    behind that call.
    """
    parts = ['<div class="bd-h">every voice, in its own words</div>',
             _voice_block(row, cols)]
    if row.get("dk"):
        parts += ['<div class="bd-h">held vs best available (engine/dk)'
                  '</div>', _dk_block(row["dk"])]
    parts += ['<div class="bd-h">matchup</div>',
              _matchup_block(row, matchup_err),
              '<div class="bd-h">how your model weighed it</div>',
              _math_block(row)]
    model = row.get("model") or {}
    if row.get("cons") and model.get("title") and model.get("why"):
        bits = [b.strip() for b in str(model["title"]).split("|") if
                b.strip()]
        if bits:
            parts.append('<div class="bd-h">model components</div>')
            parts.append('<ul class="bd-list">%s</ul>'
                         % "".join("<li>%s</li>" % _esc(b) for b in bits))
    perf_missing = any(c.get("perf") is None for c in cols)
    if perf_missing:
        parts.append('<p class="note warn">source records are unavailable '
                     'for at least one column, so no streak state is '
                     'asserted for it.</p>')
    return "".join(parts)


def drawer_block(row: Dict, cols: Sequence[Dict], dom: str,
                 matchup_err: str = "", open_: Optional[bool] = None) -> str:
    """The disclosure drawer itself: summary peek + the dossier.

    This element IS the pop-out's content. The script moves this very node
    into the dialog, so there is one copy of the dossier per RENDERING of
    the player - which is what keeps find-in-page, printing and the no-JS
    path all reading the same bytes.

    THE DRAWER IS THE FALLBACK, and stays a native <details> on purpose.
    ui.sheet() renders its content inside a closed <dialog> with an EMPTY
    <details> beside it, so a per-row sheet would make every dossier
    reachable only by running code - no find-in-page, no print, nothing
    with scripting off. The sheet is therefore the page's one SHELL
    (dialog_html), and this drawer is what the promoter moves into it.

    `dom` is passed rather than read off the row because one player is
    rendered up to twice on this page - once as a card or a compact row,
    once in the grid - and two elements sharing an id would send every
    pop-out on that player to whichever the browser reached first.
    """
    if open_ is None:
        open_ = int(row.get("level") or 0) >= OPEN_AT_LEVEL
    return (
        '<details class="bd-pop" id="%s"%s>'
        '<summary class="bd-sum">%s<span class="bd-peek">%s</span>'
        '<span class="bd-more">detail</span></summary>'
        '<div class="bd-body">%s</div></details>'
        % (_esc(dom), " open" if open_ else "",
           ui.icon("expand", 20, cls="bd-chev"), _esc(peek_line(row)),
           dossier_html(row, cols, matchup_err)))


def drawer_html(row: Dict, cols: Sequence[Dict], span: int,
                matchup_err: str = "") -> str:
    """The grid's drawer: the same block, in its own full-width table row.
    Its inner box is sticky-left so the prose stays where the reader's eye
    is when the grid is scrolled sideways."""
    return ('<tr class="dr"><td colspan="%d"><div class="drin">%s</div>'
            '</td></tr>'
            % (span, drawer_block(row, cols, row["dom"], matchup_err)))


def _cell_html(cell: Dict, label: str = "") -> str:
    # SCANNABILITY: data-l carries this cell's column label so the stacked
    # sub-700px layout can print it per cell once the header row is hidden.
    # The chip is ui.verdict_chip and nothing else: weight, not hue.
    return ('<td class="c" data-l="%s">%s</td>'
            % (_esc(label), ui.verdict_chip(cell.get("verdict"), size="sm",
                                            title=cell.get("title") or "")))


def _model_html(model: Dict, head: str = "YOUR MODEL",
                row: Optional[Dict] = None, matchup_err: str = "") -> str:
    """The model column: THE CALL AS A PERCENTAGE.

    A verdict chip reads "START 67%" and the words "of the room" follow it:
    the share of the room's weight behind the call, over the sources that
    voted. Beside it, the 1-5 matchup rating with its basis sentence in the
    title; beneath it, the WHY line whenever the percentage alone would
    mislead (call_why) - and nothing when no reason can be derived.

    After kickoff the chip becomes LOCKED and the call it replaced is kept
    beside it, muted: a locked row is final, not forgotten.

    Non-verdict calls (BURN, FAAB 12%, TRADE FOR, OPEN) keep the local
    labelled chip; their number is a score, not a share, so no "of the
    room" is attached to it.
    """
    row = row or {}
    lock = row.get("lock") or {}
    # ONE chip recipe for the whole page: the grid cell, the compact row and
    # the versus card's gutter all draw the call through verdict_chip_html,
    # so a locked row can never read as final in one place and open in
    # another.
    chip = verdict_chip_html({"model": model, "lock": lock})
    pct = ""
    if lock.get("locked"):
        was = "%s%s" % (model.get("label") or "—",
                        " · %s" % model["pct"] if model.get("pct") else "")
        pct = ('<span class="mdl-was">was %s%s</span>'
               % (_esc(was), " of the room"
                  if model.get("pct_n") is not None else ""))
    elif model.get("verdict"):
        if model.get("pct_n") is not None:
            pct = '<span class="mdl-of">of the room</span>'
    else:
        pct = ('<span class="pct wr-num">%s</span>' % _esc(model["pct"])
               if model.get("pct") else "")
    mu = matchup_inline_html(row, matchup_err) if row else ""
    agree = ""
    if model.get("agree"):
        agree = ('<span class="agree%s">%s</span>'
                 % (" hot" if model.get("hot") else "", _esc(model["agree"])))
    reason = call_why(row) if row else ""
    call = ('<span class="mdl-why">%s</span>' % _esc(reason)) if reason else ""
    # The evidence is long by design (a burn-priority argument is a
    # sentence); the row shows the head of it and the cell's title carries
    # the whole thing, so a tall row never buries the matrix.
    why = ('<span class="why">%s</span>' % _esc(_trim(model["why"], 88))
           if model.get("why") else "")
    note = ('<span class="agree hot">%s</span>' % _esc(model["note"])
            if model.get("note") else "")
    return ('<td class="mdl" data-l="%s">%s%s%s%s%s%s%s</td>'
            % (_esc(head), chip, pct, mu, agree, call, why, note))


def _row_html(row: Dict, cols: Sequence[Dict], model_head: str,
              matchup_err: str = "") -> str:
    """One player: a scan row plus its drawer, inside their own <tbody>.

    SCANNABILITY. The <tbody> is what makes the pair one object - the zebra
    band, the divergence wash and the hover all hang on it, and the drawer
    can never drift away from the row it explains. In v1 the wash was
    painted per <td>, which meant the sticky player cell (which is painted
    OVER its neighbours) lost it.
    """
    slot = ('<span class="slot">%s</span>' % _esc(row["slot"])
            if row["slot"] else "")
    meta = " · ".join(x for x in (row["pos"], row["team"],
                                         row["relevance"], row["meta"]) if x)
    mark = ""
    if row["level"] >= LVL_SPLIT:
        mark = ('<div class="mark l%d">&#9670; %s</div>'
                % (row["level"], _esc(row["marker"])))
    # SCANNABILITY - zebra parity is assigned HERE, not by :nth-of-type.
    # The group bands are <tbody> elements too, so nth-of-type counts them
    # and every band boundary flips the stripe, which puts two same-shade
    # rows next to each other exactly where the eye is re-anchoring.
    band = " odd" if row.get("band") else " even"
    # DEFERRED DETAIL: the name is the pop-out trigger. With the script
    # present the handler cancels the jump and opens the modal.
    #
    # WITHOUT the script, the href navigates to this player's drawer, which
    # :target then highlights - and the drawer's own <summary> opens it,
    # by click or by keyboard. That is the whole fallback, and it is stated
    # in exactly those terms because the tempting stronger claim is false:
    # "the browser expands a <details> to reveal a fragment target inside
    # it" is in the HTML spec but is NOT shipped everywhere (verified by
    # rendering this page and measuring - the drawer stayed closed). So the
    # link points at the DRAWER, not at a node buried inside it, and the
    # page never promises an expansion it cannot deliver.
    name_html = (pop_anchor(row, row["dom"])
                 + '<span class="popmark" aria-hidden="true">&#8599;</span>')
    span = len(cols) + 2
    # LOCK STATE: from the schedule (apply_locks), never guessed. The glyph
    # carries the kickoff in its title; the muting is CSS on the class.
    lock = row.get("lock") or {}
    locked = bool(lock.get("locked"))
    lock_html = lock_glyph(row)
    # QUIET MODE: engine/prefs hides rows every voice agreed on; the row
    # says it is one so the stylesheet can. A row that raised a CALL is
    # never marked, however unanimous - quiet mode may not hide a player
    # who needs the reader.
    unan = (' data-unanimous="1"' if (is_unanimous(row) and not is_call(row))
            else "")
    return (
        '<tbody class="pl%s%s lvl%d" data-grp="%s"%s>'
        '<tr class="r"><td class="who wr-sticky"><div class="who-in">'
        '<div class="who-id">%s%s<span class="nm">%s</span> '
        '<span class="meta">%s</span>%s</div>%s</div></td>%s%s</tr>%s</tbody>'
        % (band, " locked" if locked else "", row["level"],
           group_view(row["group"]), unan, lock_html, slot, name_html,
           _esc(meta), mark, score_cell_html(row, row.get("actual_week")),
           "".join(_cell_html(c, cols[i]["short"] if i < len(cols) else "")
                   for i, c in enumerate(row["cells"])),
           _model_html(row["model"], model_head, row, matchup_err),
           drawer_html(row, cols, span, matchup_err)))


def column_head_html(col: Dict) -> str:
    """One source column header: a face, the weight, the form state.

    REPUTATION AT THE POINT OF USE - principle 3. ui.nameplate(compact=True)
    draws the three in the order they are needed: WHO is talking (the
    cached picture, or the monogram), HOW MUCH they count, and WHETHER they
    have been right lately. The third is the one the user asked for by name
    and the one that must never be invented: when the record could not be
    read the state reads NO READ, and when it was read and is empty it reads
    NO-DATA with the reason in the title. The full name, the share, and the
    graded record ride in the header's title, so hovering answers all of
    "who is this, how much do they count, have they been right".
    """
    perf = col.get("perf")
    title = ("%s (%s, weight %g - %.0f%% of the room when every source "
             "votes)" % (col["name"], col["type"] or "source", col["weight"],
                         col["share"]))
    if perf is None:
        title += (" | the source scoreboard could not be read for this "
                  "render, so no form state is claimed for this column")
    else:
        title += " | current form: %s - %s" % (perf.get("state"),
                                               perf.get("state_reason") or "")
        if perf.get("hit_rate") is None:
            title += " | %s" % (perf.get("backfill_reason") or
                                "no graded calls on any basis")
        else:
            title += " | %s: %s over %d graded calls" % (
                basis_label(perf), _pct_or(perf["hit_rate"]),
                perf["sample_n"])
            if perf.get("backfill_state"):
                title += (" | 2025 reconstruction reads %s as of the end of "
                          "that season" % perf["backfill_state"])
    plate = ui.nameplate(col["source"], col["weight"], header_state(perf),
                         size=28, compact=True)
    return ('<th class="src%s" scope="col" title="%s">%s</th>'
            % (" topsrc" if col["top"] else "", _esc(title), plate))


def model_head_html(head: str = "YOUR MODEL") -> str:
    """The model column header: a monogram nameplate, and the words."""
    plate = ui.nameplate({"id": "your-model", "name": head, "type": "feed"},
                         None, None, size=28, compact=True)
    return ('<th class="mdl" scope="col"><span class="mdl-head">%s'
            '<span class="mdl-l">%s</span></span></th>' % (plate, _esc(head)))


def render_matrix_table(rows: Sequence[Dict], cols: Sequence[Dict],
                        model_head: str = "YOUR MODEL",
                        empty: str = "no rows",
                        matchup_err: str = "", prefix: str = "mx") -> str:
    """The matrix itself - group bands, a cell per source, a model column.

    One <thead> (sticky) and one <tbody> per player (the zebra band and the
    drawer's home). Group bands get their own <tbody class="grp"> so they
    never join a player's band and take its wash. The table is a .wr-table
    inside a .wr-scroll box, so the page never scrolls sideways.

    `prefix` namespaces the drawer element ids. The roster matrix and the
    wire matrix are two separate tables that can legitimately hold the same
    player, and two elements with the same id would send every pop-out on
    that player to whichever drawer the browser reached first.
    """
    if not rows:
        return "<p class=\"note\">%s</p>" % _esc(empty)
    ncols = len(cols) + 2
    head = "".join(column_head_html(c) for c in cols)
    body, seen, band = [], None, 0
    for i, row in enumerate(rows):
        row["dom"] = dom_id(prefix, row.get("key") or row.get("player"), i)
        if row["group"] != seen:
            seen = row["group"]
            band = 0            # each group band restarts the zebra
            body.append('<tbody class="grp"><tr><td colspan="%d">%s</td>'
                        '</tr></tbody>' % (ncols, _esc(seen)))
        row["band"] = band
        band ^= 1
        body.append(_row_html(row, cols, model_head, matchup_err))
    return ('<div class="wr-scroll mxwrap"><table class="wr-table mx">'
            '<thead><tr><th class="who wr-sticky" scope="col">player</th>%s'
            '%s</tr></thead>%s</table></div>'
            % (head, model_head_html(model_head), "".join(body)))


# --- DECISION CARDS ---------------------------------------------------------
# Three densities of the same player in the same vocabulary: a versus CARD
# when he needs deciding, a compact ROW when he does not, a grid CELL under
# All. Every one of them composes ui.py - pos_badge, avatar, verdict_chip,
# opp_chip, matchup_meter, score_cell - and adds no second palette.

def pop_anchor(row: Dict, dom: str) -> str:
    """The player's own name as the pop-out trigger.

    DEFERRED DETAIL: the name is the affordance because the name is what
    the reader is already pointing at. It is an <a> to a REAL fragment, so
    with the script deleted it still takes the reader to that rendering's
    own drawer, :target highlights it, and the drawer's <summary> opens it.
    """
    return ('<a class="pop" href="#%s" data-pop="%s" data-pop-title="%s" '
            'aria-haspopup="dialog">%s</a>'
            % (_esc(dom), _esc(dom),
               _esc("%s - %s" % (row["player"],
                                 str(row.get("group") or "").lower())),
               _esc(row["player"])))


def verdict_chip_html(row: Dict) -> str:
    """The row's call as ONE chip, wherever it is drawn.

    After kickoff it is the LOCKED chip and the pre-kickoff call is kept in
    its title: a locked row is final, not forgotten. A non-verdict model
    call (BURN, FAAB 12%, TRADE FOR, OPEN) keeps the local labelled chip.
    """
    model = row.get("model") or {}
    lock = row.get("lock") or {}
    if lock.get("locked"):
        was = "%s%s" % (model.get("label") or "—",
                        " · %s" % model["pct"] if model.get("pct") else "")
        return _label_chip("LOCKED", "none",
                           "%s. The call before kickoff was %s."
                           % (lock.get("text") or "kicked off", was))
    if model.get("verdict"):
        title = model.get("title") or ""
        if model.get("pct_n") is not None:
            title = ("%d%% of the room's weight sits behind %s, over the "
                     "sources that voted | %s"
                     % (model["pct_n"], model.get("label") or "the call",
                        title))
        return ui.verdict_chip(model["verdict"], model.get("pct_n"),
                               size="sm", title=title)
    return _label_chip(model.get("label") or "—",
                       model.get("tone") or "unfiled",
                       model.get("title") or "")


def lock_glyph(row: Dict) -> str:
    """The padlock, from the schedule and never guessed (apply_locks)."""
    lock = row.get("lock") or {}
    if not lock.get("locked"):
        return ""
    return ('<span class="bd-lock">%s</span>'
            % ui.icon("locked", 20,
                      title=lock.get("text") or "his game has kicked off"))


def _is_creator(kind) -> bool:
    return str(kind or "").strip().lower() in ("youtube", "rss", "url",
                                               "paste")


def face_strip(row: Dict, cols: Sequence[Dict]) -> str:
    """Every enabled source as a face, with what it said encoded as a RING.

    A gold ring voted START, a grey ring voted SIT, a faint ring filed
    nothing at all. EVERY source appears, including the silent ones -
    dropping them would turn the strip into a list of people who agree, and
    "this voice never mentioned him" is a fact the reader needs as much as
    any vote. The name, the weight and the verdict ride in each face's
    title, so the strip is scannable without being cryptic.
    """
    by_src = {}
    for v in ((row.get("cons") or {}).get("votes") or []):
        by_src[v.get("source")] = v
    out = []
    for c in cols:
        v = by_src.get(c["id"])
        if v is None:
            ring = "none"
            said = ("filed nothing on him - silence, not approval")
        else:
            key = VERDICT_KEYS.get(str(v.get("verdict") or "").strip()
                                   .lower())
            ring = key if key in ("start", "sit") else "lean"
            said = "voted %s" % str(key or v.get("verdict") or "?").upper()
            quote = (v.get("quote") or "").strip()
            if quote:
                said += " - “%s”" % _trim(quote, 120)
        title = "%s (weight %g): %s" % (c["name"], c["weight"], said)
        out.append('<span class="bd-face bd-face-%s">%s</span>'
                   % (ring, ui.avatar(c["id"], c["name"], size=24,
                                      kind="creator" if _is_creator(c["type"])
                                      else "feed", title=title)))
    if not out:
        return ('<div class="bd-faces"><span class="note">no source is '
                'enabled, so no voice could speak on him</span></div>')
    return ('<div class="bd-faces" aria-label="what each source said about '
            '%s">%s</div>' % (_esc(row["player"]), "".join(out)))


def compact_row_html(row: Dict, cols: Sequence[Dict], dom: str,
                     matchup_err: str = "", week: Optional[int] = None,
                     mark_quiet: bool = True) -> str:
    """One settled player: THREE logical columns and no more.

    identity (position badge, padlock, name on ONE line with an ellipsis,
    the slot and team beneath) | opponent chip + the tappable projection |
    the verdict chip. The face strip runs full width under the row, so the
    three columns stay three columns at 375px and the name never wraps.
    The drawer below is the same <details> the grid uses, closed by
    default: this row is settled, and its detail is a choice, not a duty.
    """
    lock = row.get("lock") or {}
    slot = str(row.get("slot") or "")
    pos = str(row.get("pos") or "")
    meta = " · ".join(x for x in (slot, "" if pos == slot else pos,
                                  row.get("team") or "",
                                  row.get("relevance") or "",
                                  row.get("meta") or "") if x)
    # QUIET MODE may never hide a row that needs the reader, so a row that
    # raised a call is never marked however unanimous its votes were.
    unan = ""
    if mark_quiet and is_unanimous(row) and not is_call(row):
        unan = ' data-unanimous="1"'
    return (
        '<div class="bd-pl%s" data-grp="%s"%s>'
        '<div class="bd-r3">'
        '<div class="bd-r3-id"><div class="bd-r3-top">%s%s'
        '<span class="bd-r3-nm">%s</span>'
        '<span class="popmark" aria-hidden="true">&#8599;</span></div>'
        '<div class="bd-r3-meta">%s</div></div>'
        '<div class="bd-r3-mid">%s%s</div>'
        '<div class="bd-r3-v">%s</div></div>'
        '%s%s</div>'
        % (" locked" if lock.get("locked") else "",
           group_view(row.get("group")), unan,
           ui.pos_badge(row.get("pos")) if row.get("pos") else "",
           lock_glyph(row), pop_anchor(row, dom), _esc(meta),
           matchup_inline_html(row, matchup_err),
           score_cell_html(row, row.get("actual_week") or week),
           verdict_chip_html(row),
           face_strip(row, cols),
           drawer_block(row, cols, dom, matchup_err, open_=False)))


def _vs_side(row: Dict, cols_by_id: Dict, start_side: bool) -> str:
    """One half of the versus: the chip, the ink tally, and every voice on
    that side as a face, its weight and its OWN WORDS where a quote was
    captured. A built-in feed with no quote states what its vote MEANS
    (FEED_REASONS) rather than borrowing words it never said."""
    cons = row.get("cons") or None
    verdict = "start" if start_side else "sit"
    votes = side_votes(cons, start_side) if cons else []
    s_n, s_pct, b_n, b_pct = tally_text(cons) if cons else (0, 0, 0, 0)
    n, pct = (s_n, s_pct) if start_side else (b_n, b_pct)
    items = []
    for v in votes:
        col = cols_by_id.get(v.get("source")) or {}
        src = _plate_source(cols_by_id, v)
        name = v.get("name") or v.get("source") or "?"
        quote = _trim((v.get("quote") or "").strip(), DOSSIER_QUOTE)
        if quote:
            words = ('<span class="bd-vs-q">&#8220;%s&#8221;%s</span>'
                     % (_esc(quote),
                        _esc(" (%s confidence)" % v["confidence"])
                        if v.get("confidence") else ""))
        else:
            handle = col.get("handle") or v.get("source")
            reason = FEED_REASONS.get(handle, {}).get(v.get("verdict"))
            words = ('<span class="bd-vs-q mutq">%s</span>'
                     % _esc(reason or ("voted %s; no quote was captured with "
                                       "this call" % v.get("verdict"))))
        wt = ""
        try:
            wt = ('<span class="bd-vs-w wr-num">wt %d</span>'
                  % int(round(float(v.get("weight") or 0))))
        except (TypeError, ValueError):
            wt = ""
        items.append('<li>%s<span class="bd-vs-who">'
                     '<span class="bd-vs-n">%s</span>%s</span>%s</li>'
                     % (ui.avatar(src.get("id"), name, size=24,
                                  kind="creator" if _is_creator(src.get("type"))
                                  else "feed", title=name),
                        _esc(name), wt, words))
    body = ('<ul class="bd-vs-l">%s</ul>' % "".join(items) if items
            else '<p class="bd-vs-none">no voice filed a %s on him</p>'
                 % verdict.upper())
    return ('<div class="bd-vs-side bd-vs-%s"><div class="bd-vs-hd">%s'
            '<span class="bd-vs-t"><span class="wr-num">%d</span> voice%s · '
            '<span class="wr-num">%d%%</span> of the weight</span></div>%s'
            '</div>'
            % (verdict, ui.verdict_chip(verdict, size="sm"), n,
               "" if n == 1 else "s", pct, body))


def _vs_gutter(row: Dict, matchup_err: str = "") -> str:
    """The centre: the model's own call as a chip with its percentage, and
    the matchup as an opponent chip + a 1-5 meter with its basis stated in
    words underneath - not only hidden in a title."""
    model = row.get("model") or {}
    of = ('<span class="bd-vs-of">of the room</span>'
          if model.get("pct_n") is not None and not (row.get("lock") or {})
          .get("locked") else "")
    m = row.get("matchup") or {}
    if matchup_err:
        basis = "matchup read unavailable - %s" % _one_line(matchup_err, 120)
    elif m and m.get("basis"):
        basis = "basis: %s" % m["basis"]
    elif m:
        basis = m.get("reason") or "no matchup grade filed for this row"
    else:
        basis = "no matchup read for this row"
    return ('<div class="bd-vs-gut"><span class="bd-vs-vs">versus</span>'
            '%s%s<span class="bd-vs-mu">%s</span>'
            '<span class="bd-vs-basis">%s</span></div>'
            % (verdict_chip_html(row), of,
               matchup_inline_html(row, matchup_err) or
               ui.matchup_meter(None, label=False, size="sm",
                                title=matchup_title(m, matchup_err)),
               _esc(basis)))


def _acts_html() -> str:
    """AGREE / OVERRIDE - and the truth about them.

    They are DISABLED buttons, not links dressed as buttons: a disabled
    button is genuinely non-interactive, announces as disabled to a screen
    reader, and looks like what it is. The line beneath states in words
    that nothing on this page saves a decision, because a control that
    looks like it persists and does not is worse than no control at all.
    """
    return ('<div class="bd-acts">'
            '<button type="button" class="bd-act bd-act-y" disabled '
            'title="not wired yet - this board saves nothing">Agree</button>'
            '<button type="button" class="bd-act" disabled '
            'title="not wired yet - this board saves nothing">Override'
            '</button>'
            '<span class="bd-acts-n">Agree / Override are not wired up yet: '
            'nothing on this page records or remembers a decision, and the '
            'board writes no file but itself.</span></div>')


def render_call_card(row: Dict, cols: Sequence[Dict], cols_by_id: Dict,
                     dom: str, matchup_err: str = "",
                     week: Optional[int] = None) -> str:
    """One player who needs deciding, as a versus card.

    The card leads with WHY IT IS A CALL - one line per ground, each named
    - because a section called "the calls" that does not say what raised
    each card is an editor's hunch wearing a data page's clothes.
    """
    reasons = call_reasons(row)
    level = int(row.get("level") or LVL_NONE)
    meta = " · ".join(x for x in (row.get("pos") or "", row.get("team") or "",
                                  str(row.get("group") or "").lower(),
                                  row.get("slot") or "",
                                  row.get("relevance") or "") if x)
    why_list = "".join('<li><b>%s</b>%s</li>' % (_esc(r["mark"]),
                                                 _esc(r["line"]))
                       for r in reasons)
    why = call_why(row)
    vs_note = ""
    vs = row.get("vs") or {}
    if vs.get("proj") is not None:
        vs_note = ('<span class="bd-call-vs-p">the %s he is measured '
                   'against: <b>%s %.1f</b></span>'
                   % (_esc(vs.get("slot") or "slot"), _esc(vs.get("name")
                                                           or "?"),
                      float(vs["proj"])))
    return (
        '<article class="bd-call l%d">'
        '<header class="bd-call-h">%s<span class="nm">%s</span>'
        '<span class="popmark" aria-hidden="true">&#8599;</span>'
        '<span class="meta">%s</span></header>'
        '<ul class="bd-call-why-list">%s</ul>'
        '<div class="bd-vs">%s%s%s</div>'
        '%s<div class="bd-call-num">%s%s</div>%s%s</article>'
        % (level, ui.pos_badge(row.get("pos")) if row.get("pos") else "",
           pop_anchor(row, dom), _esc(meta), why_list,
           _vs_side(row, cols_by_id, True), _vs_gutter(row, matchup_err),
           _vs_side(row, cols_by_id, False),
           ('<p class="bd-call-why">%s</p>' % _esc(why)) if why else "",
           score_cell_html(row, row.get("actual_week") or week), vs_note,
           _acts_html(),
           drawer_block(row, cols, dom, matchup_err, open_=False)))


def _group_head(title: str, count: str, sub: str = "") -> str:
    """A group band that STATES ITS COUNT. Nothing on this board is
    summarised away, so every band says how many rows it is holding."""
    return ('<div class="bd-grp"><h3 class="bd-grp-h">%s</h3>'
            '<span class="bd-grp-n">%s</span>%s</div>'
            % (_esc(title), _esc(count),
               '<span class="bd-grp-s">%s</span>' % _esc(sub) if sub else ""))


CALLS_LEDE = ("a player is here on one of four grounds, and each card says "
              "which: the room splits, your top-weighted source dissents, "
              "the matchup contradicts a room that agrees, or engine/dk "
              "rates the DST/K you hold as a stream or a toss-up.")


def calls_count_text(cards: Sequence[Dict]) -> str:
    """The band's count, split by what each card actually asks of the reader.

    THE HEAD MUST NOT OVERSTATE THE WEEK. A card raised on the matchup ground
    alone contradicts a room that AGREED, and its own text says so in as many
    words - "this is NOT a recommendation to bench him", "the room still says
    sit". Counting those as decisions told the reader more of their lineup was
    unsettled than is: espn-1 week 1 printed "5 need a decision" over three
    real ones and two second looks.

    CALL_MATCHUP is the lowest ground, so call_rank == its rank means the
    matchup was the ONLY ground raised; anything else (a split room, a
    dissenting top source, a DST/K engine/dk will not call a HOLD) outranks
    it. The two numbers always sum to the number of cards - nothing is
    summarised away, it is only named correctly.
    """
    look = sum(1 for r in cards if call_rank(r) == CALL_RANK[CALL_MATCHUP])
    dec = len(cards) - look
    if look and dec:
        return ("%d need%s a decision · %d worth a second look"
                % (dec, "s" if dec == 1 else "", look))
    if look:
        return "%d worth a second look" % look
    return "%d need%s a decision" % (dec, "s" if dec == 1 else "")


def render_calls_block(cards: Sequence[Dict], cols: Sequence[Dict],
                       holes: Sequence[str], judged: int = 0,
                       silent: int = 0, held_locked: int = 0,
                       matchup_err: str = "",
                       week: Optional[int] = None) -> str:
    """THE CALLS - and the claim it is allowed to make about an empty list.

    An empty list has two completely different causes and they must never
    be printed the same way. Either every ground was actually testable and
    none fired - a finding - or one of the four checks could not run, which
    is the absence of a finding. `holes` (call_coverage) is the second
    case, and the block then states what it could not see and asserts
    NOTHING about whether the week needs you.
    """
    cols_by_id = dict((c["id"], c) for c in cols)
    holes = [h for h in holes if h]
    body = ""
    if holes:
        if cards:
            body += ('<p class="note warn">PARTIAL - %d row(s) were '
                     'weighed and the cards below are real, but not every '
                     'ground could be checked, so there may be calls this '
                     'list does not carry.</p>' % judged)
        else:
            body += ('<p class="note warn">NOT ARBITRATED - this section is '
                     'making NO claim about whether your week needs you. '
                     'An empty list here is missing data, not calm.</p>')
        body += ('<ul class="flat">%s</ul>'
                 % "".join("<li>%s</li>" % _esc(h) for h in holes))
        body += ('<p class="note">what fixes it: rerun <code>./board.sh'
                 '</code> once the feed above is back (<code>--force</code> '
                 'refetches), ingest this week\'s creator calls with '
                 '<code>python -m engine.calls --week N</code>, and check '
                 'which voices are enabled with <code>./sources.sh</code>.'
                 '</p>')
    elif not cards:
        body += ('<p class="note">nothing needs deciding: all %d player(s) '
                 'that drew a vote got the same call from every voice that '
                 'filed one, no matchup grade contradicted the room, and '
                 'the DST/K you hold is a HOLD. %d source(s) enabled.</p>'
                 % (judged, len(cols)))
        if silent > 0:
            body += ('<p class="note">%d row(s) drew no vote at all and are '
                     'NOT covered by that statement - an empty row is a '
                     'source that never spoke, not a source that '
                     'approves.</p>' % silent)
    if held_locked:
        body += ('<p class="note">%d row(s) that would otherwise be here '
                 'have already kicked off, so their decision is over. They '
                 'are listed below with the padlock and a LOCKED chip, not '
                 'dropped.</p>' % held_locked)
    if cards:
        body += ('<div class="bd-calls">%s</div>'
                 % "".join(render_call_card(r, cols, cols_by_id,
                                            dom_id("cl", r.get("key")
                                                   or r["player"], i),
                                            matchup_err, week)
                           for i, r in enumerate(cards)))
        body += ('<p class="note">ordered by the strength of the ground: '
                 'the top-source alarm first, then the widest genuine split '
                 '(the weight sitting on the LOSING side of the verdict), '
                 'then the contradictions. Waiver and trade candidates are '
                 'a different question and stay in the wire below.</p>')
    return ('<div class="bd-blk" data-sec="calls">%s%s</div>'
            % (_group_head("The calls", calls_count_text(cards),
                           CALLS_LEDE), body))


def render_rows_block(sec: str, title: str, sub: str, groups: Sequence,
                      cols: Sequence[Dict], prefix: str,
                      matchup_err: str = "",
                      week: Optional[int] = None) -> str:
    """LOCKED IN / BENCH: compact rows, listed, never summarised away.

    `groups` is [(sub-heading or '', rows)] so the bench block can carry
    the unplaced rows - an open starting slot, a roster name no projection
    matched - under their own head with their own count instead of
    quietly filing them as bench players, which they are not.
    """
    total = sum(len(rows) for _, rows in groups)
    body = []
    seq = 0
    for head, rows in groups:
        if not rows:
            continue
        if head:
            body.append('<h3 class="sub">%s · %d</h3>' % (_esc(head),
                                                          len(rows)))
        for r in rows:
            body.append(compact_row_html(
                r, cols, dom_id(prefix, r.get("key") or r["player"], seq),
                matchup_err, week))
            seq += 1
    if not body:
        body.append('<p class="note">no row in this group.</p>')
    return ('<div class="bd-blk" data-sec="%s">%s%s</div>'
            % (_esc(sec),
               _group_head(title, "%d" % total, sub), "".join(body)))


def legend_items() -> List[Tuple[str, str]]:
    """(glyph html, meaning) for every mark the matrix can print. EVERY
    glyph carries a title, so the popover is a courtesy, not the only key."""
    return [
        (ui.verdict_chip("start", size="sm",
                         title="START - the gold fill: the room's weight "
                               "sits on starting him"),
         "START · 67% of the room: the share of the room's weight behind "
         "the call, over the sources that voted"),
        (ui.verdict_chip("sit", size="sm",
                         title="SIT - the ghost outline: the weight sits on "
                               "benching him"),
         "SIT - the weight sits on benching him"),
        (ui.verdict_chip("flex", size="sm",
                         title="FLEX - a dashed lean: a flex-level call"),
         "FLEX - a flex-level lean"),
        (ui.verdict_chip(None, size="sm", title="no opinion filed"),
         "no opinion filed - that voice never mentioned him; silence, not "
         "approval"),
        (ui.matchup_meter("good", label=False, size="sm",
                          title="matchup rating, 1-5 segments filled from "
                                "the left; hover any meter for its basis"),
         "matchup 1-5: five = a defence that gives it up, one = a wall; "
         "hover for the evidence and the basis year"),
        ('<span class="bd-score-v wr-num" title="tap the number for its '
         'breakdown">12.4</span>',
         "the number is this week's projection - tap it for the source, "
         "the room's votes and the matchup; after kickoff the actual "
         "replaces it in bold with the projection muted beside it"),
        ('<span class="bd-lock">%s</span>'
         % ui.icon("locked", 20, title="LOCKED - his game has kicked off"),
         "LOCKED - his game has kicked off: the row is muted and the call "
         "is final"),
        ('<span class="bd-faces"><span class="bd-face bd-face-start">%s</span>'
         '<span class="bd-face bd-face-sit">%s</span>'
         '<span class="bd-face bd-face-none">%s</span></span>'
         % (ui.avatar("legend-a", "voted START", size=24,
                      title="a gold ring: this source voted START"),
            ui.avatar("legend-b", "voted SIT", size=24,
                      title="a grey ring: this source voted SIT"),
            ui.avatar("legend-c", "filed nothing", size=24,
                      title="a faint ring: this source filed nothing - "
                            "silence, not approval")),
         "the face strip on a compact row: a gold ring voted START, a grey "
         "ring voted SIT, a faint ring filed nothing at all. Hover any face "
         "for that source's weight and its own words"),
        ('<span class="bd-call-tag" title="what raised this card">&#9670; '
         'SPLIT</span>',
         "on a card, the ground that raised it - SPLIT, TOP SOURCE "
         "DISSENTS, TEMPER EXPECTATIONS, THE MATCHUP ARGUES BACK, STREAM "
         "or TOSS-UP. A card is never raised on anything else"),
        ('<button type="button" class="bd-act" disabled title="not wired '
         'yet - this board saves nothing">Agree</button>',
         "Agree / Override are drawn but NOT wired: they are disabled "
         "buttons, and nothing on this page records or remembers a "
         "decision"),
        ('<span class="mark l1" title="SPLIT - the room points both ways">'
         '&#9670; SPLIT</span>',
         "in the grid, the room points both ways"),
        ('<span class="mark l2" title="TOP SOURCE DISSENTS - your heaviest '
         'voice differs from the model or the engine">&#9670; TOP SOURCE '
         'DISSENTS</span>',
         "your heaviest voice differs from the model or the engine"),
        (ui.icon("expand", 20, title="open the row's detail"),
         "open a row for the quotes, the meter and the arithmetic; tap a "
         "player's name for the sheet (Esc closes it). A column head is "
         "the source's face, weight and current form - hover it for the "
         "name and the record"),
    ]


def _legend_popover_fallback(items) -> str:
    """A '?' control that opens the key. Native <details>: keyboard-
    operable, no script, 44px tall."""
    cells = "".join('<span class="wr-legend-i">%s<span>%s</span></span>'
                    % (g, _esc(m)) for g, m in items)
    return ('<details class="bd-legend"><summary class="bd-legend-s" '
            'aria-label="legend - what the marks mean" '
            'title="what the marks on this board mean">'
            '<span class="bd-legend-q" aria-hidden="true">?</span>legend'
            '</summary><div class="bd-legend-b"><div class="legend">%s'
            '</div></div></details>' % cells)


# The icon-name half of the key, for ui.legend_popover, which speaks
# (icon name, meaning) pairs and cannot draw a chip, a meter or a mark.
LEGEND_ICONS = (
    ("start", "the play triangle inside a START chip"),
    ("sit", "the bench inside a SIT chip"),
    ("toss_up", "the balance inside a FLEX / TOSS-UP chip"),
    ("locked", "his game has kicked off - the row is final"),
    ("expand", "opens a row's detail"),
)


def _legend() -> str:
    """The '?' popover. ui.legend_popover draws the shell and the icon key;
    the page's own glyphs - chips, the meter, the number, the marks - are
    spliced into its panel, because the key must show the marks AS THEY
    ARE PRINTED. If the shell is not the shape this expects, the local
    popover carries the whole key instead."""
    extra = "".join('<span class="wr-legend-i">%s<span>%s</span></span>'
                    % (g, _esc(m)) for g, m in legend_items())
    fn = ui_component("legend_popover")
    if fn is not None:
        try:
            out = fn(list(LEGEND_ICONS))
        except Exception:  # noqa: BLE001 - the fallback is the contract
            out = ""
        tail = "</div></details>"
        if isinstance(out, str) and out.startswith("<details") \
                and out.endswith(tail):
            return (out[:-len(tail)]
                    + '<div class="legend bd-legend-x">%s</div>' % extra
                    + tail)
    return _legend_popover_fallback(legend_items())


def _segmented_fallback(name, options, active) -> str:
    """Calls / Locked in / Bench / All as fragment links, 44px tall. With
    the script off :target filters the blocks; with it on, the promoter
    script intercepts the click and sets data-view on the block box."""
    links = "".join(
        '<a class="bd-seg-a" href="#seg-%s" data-seg="%s"%s>%s</a>'
        % (_esc(v), _esc(v), ' aria-current="true"' if v == active else "",
           _esc(label))
        for v, label in options)
    return ('<nav class="bd-seg" data-seg-wrap aria-label="%s">%s</nav>'
            % (_esc(name), links))


def segmented_html(active: str = SEG_DEFAULT) -> str:
    """The :target anchors, then the control - ui.segmented when it exists,
    wrapped so the script can find it, else the local fallback."""
    targets = "".join('<span id="seg-%s" class="bd-seg-t"></span>' % v
                      for v, _ in SEG_VIEWS)
    fn = ui_component("segmented")
    if fn is not None:
        # (key, label, href) triples: links, not buttons, so the control
        # still switches the view with scripting off (CSS :target).
        try:
            out = fn("show", [(v, label, "#seg-%s" % v)
                              for v, label in SEG_VIEWS], active)
            if isinstance(out, str) and out.strip():
                return (targets + '<div class="bd-segw" data-seg-wrap>%s'
                        '</div>' % out)
        except Exception:  # noqa: BLE001 - the fallback is the contract
            pass
    return targets + _segmented_fallback("show", list(SEG_VIEWS), active)


BOARD_TITLE = "The board - what needs deciding, and what does not"

GRID_LEDE = ("the original read, kept intact: every rostered player a row, "
             "every enabled source a column, your model last. It is here "
             "rather than at the top because most of its width shows "
             "AGREEMENT - the least interesting thing on the page.")


def render_board(rows: Sequence[Dict], cols: Sequence[Dict],
                 notes: Sequence[str], matchup_err: str = "",
                 week: Optional[int] = None, judged: int = 0,
                 silent: int = 0, holes: Sequence[str] = ()) -> str:
    """THE BOARD: the calls, then locked in, then the bench, then the grid.

    ORDERED BY CERTAINTY, NOT BY ROSTER ORDER. The four blocks are the four
    views of the switch above them, and every row on the roster is in
    exactly one of the first three - nothing is summarised away, and the
    band head of each states its count so a reader can see that.
    """
    cards = call_rows(rows)
    card_keys = set(id(r) for r in cards)
    starting, bench, other = [], [], []
    for r in rows:
        if id(r) in card_keys:
            continue
        grp = str(r.get("group") or "").upper()
        if grp.startswith("STARTING"):
            starting.append(r)
        elif grp.startswith("BENCH"):
            bench.append(r)
        else:
            other.append(r)

    locked = sum(1 for r in rows if (r.get("lock") or {}).get("locked"))
    held = held_by_kickoff(rows)
    unanimous = sum(1 for r in rows if is_unanimous(r) and not is_call(r))
    whys = sum(1 for r in rows if call_why(r))

    blocks = [
        render_calls_block(cards, cols, holes, judged=judged, silent=silent,
                           held_locked=held, matchup_err=matchup_err,
                           week=week),
        render_rows_block(
            "locked", "Locked in",
            "the starting lineup nobody argued about - one compact row "
            "each, listed so nothing is hidden. The face strip says what "
            "every source said: a gold ring voted START, a grey ring SIT, "
            "a faint ring filed nothing.",
            [("", starting)], cols, "lk", matchup_err, week),
        render_rows_block(
            "bench", "Bench",
            "the same treatment for everyone not in the lineup.",
            [("Bench", bench),
             ("Not placed - an open slot, or a roster name no projection "
              "matched", other)],
            cols, "bn", matchup_err, week),
        '<div class="bd-blk" data-sec="grid">%s%s</div>'
        % (_group_head("The grid", "%d rows × %d sources" % (len(rows),
                                                             len(cols)),
                       GRID_LEDE),
           render_matrix_table(
               rows, cols, "YOUR MODEL",
               "no roster rows - data/rosters/<league>.yaml is empty or "
               "missing, so there is nothing to lay out",
               matchup_err=matchup_err, prefix="mx")),
    ]
    # THE SWITCH sits above the blocks and is a sibling of the container
    # its :target rules reach, so the no-script CSS path still filters.
    body = ('<div class="bd-board">%s<div class="bd-mx" data-view="%s">%s'
            '</div></div>'
            % (segmented_html(SEG_DEFAULT), SEG_DEFAULT, "".join(blocks)))
    if unanimous:
        # Printed only under data-quiet="1" (CSS): the hidden rows are
        # counted out loud, so quiet mode never reads as a shorter roster.
        body += ('<p class="note bd-quiet-note">quiet mode: %d unanimous '
                 'row(s) hidden - every voice agreed on them and none of '
                 'them raised a call. Turn quiet off in the preferences '
                 'control to see them.</p>' % unanimous)
    # The legend's panel is anchored to THIS wrapper, not to the 44px "?"
    # button: ui.legend_popover pins it right:0 against its own trigger,
    # which on a 390px screen would hang 360px of key off the left edge.
    body += '<div class="bd-lgw">%s</div>' % _legend()
    notes = list(notes)
    notes.append("the call reads as a percentage - START · 67% of the room "
                 "is the share of the room's WEIGHT behind the call, over "
                 "the sources that voted. A line beneath it says why "
                 "whenever the simple majority of voices did not decide it, "
                 "or the lineup seated a lower-polling player on "
                 "projection; no line means no reason could be derived, not "
                 "that there is none. Beside it, the matchup as a 1-5 "
                 "rating - hover it for the basis. Tap any number for what "
                 "it is made of.")
    if locked:
        notes.append("%d row(s) are LOCKED - their game has kicked off per "
                     "the nflverse schedule; they are muted and final, and "
                     "a locked row never raises a call because its decision "
                     "is already over. A kickoff the schedule lists by day "
                     "only is never treated as locked." % locked)
    count = "%d call%s · %d locked in · %d bench · %d rows" % (
        len(cards), "" if len(cards) == 1 else "s", len(starting),
        len(bench) + len(other), len(rows))
    if locked:
        count += " · %d kicked off" % locked
    if whys:
        count += " · %d explained" % whys
    return _card(BOARD_TITLE, body, notes, count)


def render_wire(add_rows: Sequence[Dict], trade_rows: Sequence[Dict],
                off_rows: Sequence[Dict], cols: Sequence[Dict],
                constructs: Sequence[str], notes: Sequence[str],
                banners: Sequence[str], matchup_err: str = "") -> str:
    rows = list(add_rows) + list(trade_rows) + list(off_rows)
    body = "".join(ui.banner(b, "warn") for b in banners if b)
    body += render_matrix_table(
        rows, cols, "MY MODEL SAYS",
        "no add or trade candidate cleared the bar this week",
        matchup_err=matchup_err, prefix="wr")
    if constructs:
        body += ("<h3 class=\"sub\">Trade constructs - shapes, not named "
                 "offers</h3><ul class=\"flat\">%s</ul>"
                 % "".join("<li>%s</li>" % _esc(c) for c in constructs))
    if trade_rows:
        # The pts/wk on each trade row is the lineup gain, not the sort key -
        # saying so beats letting the column look mis-ordered.
        body += ("<p class=\"note\">trade targets are in engine/trades.py's "
                 "own ranked order (value balance, the rival's acceptance "
                 "odds, and our lineup gain together), so the pts/wk shown "
                 "is one input to that rank and not the column it is sorted "
                 "by.</p>")
    body += ("<p class=\"note\">same shape as the grid on purpose: "
             "a candidate's source column reads exactly like an owned "
             "player's, so a wire add and the man he would replace can be "
             "compared without changing how you read a row. An empty source "
             "cell means that voice never mentioned him - not that it "
             "approves.</p>")
    return _card("Wire - waiver adds and trade targets", body, notes,
                 "%d adds · %d targets" % (len(add_rows),
                                                  len(trade_rows)))


SCOREBOARD_TITLE = "Source scoreboard - who has actually been right"


def streak_cell(row: Dict) -> str:
    """The current run, as words a reader can check against the sparkline."""
    n = int(row.get("streak") or 0)
    d = int(row.get("streak_dir") or 0)
    if n <= 0 or d == 0:
        return "—"
    return "%d wk %s" % (n, "above" if d > 0 else "below")


def scoreboard_row(row: Dict, week: Optional[int] = None) -> str:
    """One source's record as one table row, every claim carrying its basis.

    The three things this must never do, because performance.py went to
    real trouble to make them expressible:
      * print a hit rate without saying what it is made of - the headline
        is the decay BLEND (row["blend"]) and prints its label ("2025
        archive", "mostly 2026") beside the number with the note in the
        title, and the provenance column names the basis in words;
      * let a creator's empty record look like a failure - it is a FACT,
        and its own reason says so in words;
      * dress the 2025 backfill up as current form. `state` is live-only by
        construction; the 2025 read is shown separately and labelled "as of
        the end of 2025".
    """
    sid = row.get("source") or ""
    is_top = bool(row.get("top"))
    plate = ui.nameplate({"id": sid, "name": row.get("name") or sid,
                          "type": row.get("type") or "feed"},
                         row.get("weight"), None, size=28,
                         sub=("%.0f%% of the room" % row["share"]
                              if row.get("share") else None),
                         href="sources.html#src-%s" % sid)
    blend = blend_for(row, week)
    rate = blend.get("hit_rate")
    if rate is None:
        # "no graded call" already IS the basis; printing basis_label's "no
        # graded calls" beside it would say the same thing twice and dilute
        # the one line that matters.
        headline = '<span class="big none">no graded call</span>'
    else:
        headline = ('<span class="big wr-num">%s</span>'
                    '<span class="lab" title="%s">%s</span>'
                    % (_pct_or(rate), _esc(blend.get("note") or ""),
                       _esc(blend.get("label") or "")))

    n = int(row.get("sample_n") or 0)
    if n:
        sample = ('<span class="wr-num">n %d</span><span class="sub">%d week%s'
                  '%s</span>'
                  % (n, row.get("weeks_n") or 0,
                     "" if (row.get("weeks_n") or 0) == 1 else "s",
                     "" if not row.get("unscorable_n")
                     else " · %d unscorable" % row["unscorable_n"]))
    else:
        sample = '<span class="sub">—</span>'

    reason = row.get("state_reason") or ""
    if rate is None and row.get("is_creator"):
        reason = row.get("backfill_reason") or reason
    form = ('%s<span class="sub">%s</span>'
            % (streak_badge_html(row.get("state"), title=reason),
               _esc(_trim(reason, 110))))

    values = row.get("sparkline_values") or []
    if values:
        labels = row.get("sparkline_weeks") or []
        spark = ('<span class="spark">%s</span><span class="sub">weeks %s '
                 '(thin weeks withheld)</span>'
                 % (ui.sparkline(values, width=104, height=22,
                                 title="weekly hit rate by week"),
                    _esc("%s-%s" % (labels[0], labels[-1]) if labels
                         else "n/a")))
    else:
        spark = ('<span class="spark">%s</span><span class="sub">no weekly '
                 'series - an empty sparkline, not a flat one</span>'
                 % ui.sparkline([], width=104, height=22,
                                title="no weekly series"))

    prov = basis_label(row)
    if (row.get("backfill_state")
            and row.get("provenance") != perf_mod.PROV_LIVE):
        prov += ('<span class="sub">%d form read: %s, as of the end of that '
                 'season</span>'
                 % (perf_mod.SEASON_BACKFILL, _esc(row["backfill_state"])))
    return ('<tr class="sbr%s" data-source="%s"><td class="wr-sticky">%s</td>'
            '<td data-l="headline">%s</td><td data-l="sample">%s</td>'
            '<td data-l="current form">%s</td>'
            '<td class="wr-num" data-l="streak">%s</td>'
            '<td data-l="weekly hit rate">%s</td><td data-l="basis">%s</td>'
            '</tr>'
            % (" top" if is_top else "", _esc(sid), plate, headline, sample,
               form, _esc(streak_cell(row)), spark, prov))


def render_scoreboard(sb: Optional[Dict], cols: Sequence[Dict],
                      notes: Sequence[str], err: str = "",
                      week: Optional[int] = None) -> str:
    """The per-source scoreboard - principle 5, and the honesty contract.

    In September 2026 EVERY current-form state is NO-DATA, and that is the
    finding, not a bug: no week has been played, so no source has a live
    graded call. The section says exactly that once, at the top, and then
    shows what each source DOES have - which for three algorithmic feeds is
    a labelled 2025 reconstruction and for the creators is nothing at all.
    """
    if err:
        return _degraded(SCOREBOARD_TITLE, RuntimeError(err))
    rows = list((sb or {}).get("rows") or [])
    if not rows:
        body = ('<p class="note warn">no source record could be read, so '
                'this section asserts nothing about any voice\'s form. '
                'That is a hole, not a verdict.</p>')
        return _card(SCOREBOARD_TITLE, body, notes)

    share = dict((c["id"], c["share"]) for c in cols)
    top_id = cols[0]["id"] if cols else None
    trs = []
    for r in rows:
        r = dict(r)
        r["share"] = share.get(r.get("source"))
        r["top"] = r.get("source") == top_id
        trs.append(scoreboard_row(r, week))

    live = sum(1 for r in rows if r.get("provenance") == perf_mod.PROV_LIVE)
    graded = sum(1 for r in rows if r.get("hit_rate") is not None)
    body = ""
    if live == 0:
        body += ('<p class="note warn">NO LIVE RECORD EXISTS YET. '
                 'Week 1 of %d has not been played and data/source_ledger'
                 '.jsonl holds no graded call, so every CURRENT-form state '
                 'below is NO-DATA by fact, not by failure. A HOT badge is '
                 'not available to be earned yet.</p>' % weekly.SEASON)
    body += ('<div class="wr-scroll"><table class="wr-table sb"><thead><tr>'
             '<th class="wr-sticky" scope="col">source</th>'
             '<th scope="col">headline</th><th scope="col">sample</th>'
             '<th scope="col">current form</th><th scope="col">streak</th>'
             '<th scope="col">weekly hit rate</th><th scope="col">basis</th>'
             '</tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))
    body += ('<p class="sb-link"><a href="sources.html">The full receipts - '
             'per-position splits, start calls against sit calls, and the '
             'archive phase-out schedule: sources.html</a></p>')
    body += ('<p class="note">the headline is the decay BLEND: the label '
             'beside it says what it is made of and its title says how. A '
             'rate resting on <b>%s</b> is a RECONSTRUCTION: '
             'engine/performance.py replayed that feed\'s published 2025 '
             'weekly archive against what actually happened, graded by this '
             'league\'s own replacement level. It is evidence about the '
             'feed, not a recording of a call it filed at the time, and it '
             'is never averaged with a live number except through that '
             'stated blend.</p>'
             % _esc(perf_mod.PROV_BACKFILL))
    body += ('<p class="note">a source is never crowned on a thin sample: '
             'below %d graded calls or %d graded weeks the state is '
             'LOW-CONFIDENCE and can be neither HOT nor COLD. A creator who '
             'has never been graded reads NO-DATA - which is the honest '
             'answer to "should I listen to them", not a criticism of '
             'them.</p>' % (perf_mod.MIN_GRADED_CALLS,
                            perf_mod.MIN_GRADED_WEEKS))
    return _card(SCOREBOARD_TITLE, body, list(notes)
                 + list((sb or {}).get("notes") or []),
                 "%d source(s) · %d with any graded record"
                 % (len(rows), graded))


def render_league(teams: Sequence[Dict], notes: Sequence[str],
                  banners: Sequence[str]) -> str:
    body = "".join(ui.banner(b, "warn") for b in banners if b)
    if not teams:
        body += ("<p class=\"note\">no roster in this league is known, so "
                 "there is nothing to lay out. Paste rosters in Model "
                 "Settings (<code>./sources.sh</code> &#8594; Leagues) to "
                 "fill this in.</p>")
        return _card("League view - the other teams", body, notes)
    cards = []
    for t in teams:
        # Surplus and hole as ink pills that SAY which they are - no green
        # for a surplus, no red for a hole.
        tags = "".join(
            ui.stat_pill("SURPLUS" if kind == "surplus" else "HOLE", label,
                         tone="neutral")
            for kind, label in t["tags"]) or \
            ui.stat_pill("SHAPE", "no surplus or hole", tone="neutral")
        lis = []
        for p in t["players"]:
            cls = []
            if p.get("exposure"):
                cls.append("exp")
            if p.get("target"):
                cls.append("tgt")
            flags = []
            if p.get("target"):
                flags.append('<span class="fl">TARGET</span>')
            if p.get("exposure"):
                flags.append('<span class="fl" title="%s">ALSO MINE</span>'
                             % _esc("you also hold him in: %s"
                                    % ", ".join(p["exposure"])))
            lis.append('<li class="%s"><span class="p">%s '
                       '<span class="ps">%s</span></span>%s</li>'
                       % (" ".join(cls), _esc(p["name"]), _esc(p["pos"]),
                          "".join(flags)))
        cards.append(
            '<div class="team%s"><div class="tn">%s <span class="slot">'
            'slot %s%s</span></div><div class="tags">%s</div>'
            '<ul>%s</ul><div class="src">%s</div></div>'
            % (" mine" if t["mine"] else "", _esc(t["name"]),
               _esc(t["slot"]), " · MINE" if t["mine"] else "",
               tags, "".join(lis) or '<li><span class="p">no known '
               'players</span></li>', _esc(t["source"])))
    body += '<div class="teams">%s</div>' % "".join(cards)
    body += ("<p class=\"note\">surplus/hole tags are startable bodies "
             "against this league's starting demand (engine/trades.py "
             "positional_net) - what a rival can spare and what he needs. "
             "ALSO MINE marks a player you hold in another league; TARGET "
             "marks a named trade target above. Positive-only: a player on "
             "no roster shown here is UNKNOWN, not a free agent.</p>")
    return _card("League view - the other teams", body, notes,
                 "%d roster(s) shown" % len(teams))


# --- gathering (impure; each piece is guarded by the caller) ----------------

def record_line(league: LeagueConfig) -> str:
    """The league record, or an honest account of why there is none.

    No host API is connected (RUNBOOK: ESPN cookies read rosters, not
    standings), so unless the league yaml carries a hand-kept `record:` the
    truthful answer is that we do not know it - not 0-0.
    """
    rec = ""
    try:
        import yaml
        with open(league.path) as fh:
            raw = yaml.safe_load(fh) or {}
        rec = str(raw.get("record") or "").strip()
    except (OSError, ValueError, ImportError):
        rec = ""
    if rec:
        return rec
    return "not tracked (no standings feed connected)"


def _relevance_tag(player: Player, ctx) -> str:
    """FRINGE/IRRELEVANT worth showing next to a name; CORE is the norm."""
    try:
        rel = leaguesize.relevance(player, ctx)
    except Exception:  # noqa: BLE001 - a tag is never worth a section
        return ""
    return rel.lower() if rel in ("FRINGE", "IRRELEVANT") else ""


def _plain_model(label: str, title: str) -> Dict:
    """A model cell that is a statement of absence, not a call."""
    return {"label": label, "verdict": None, "tone": "unfiled", "pct": "",
            "pct_n": None, "agree": "", "hot": False, "title": title}


def roster_rows(cons: Dict, lineup_build: Dict,
                roster_names: Sequence[str], cols: Sequence[Dict],
                ctx, matchup_of: Optional[Callable] = None,
                dk_calls: Optional[Dict[str, Dict]] = None
                ) -> Tuple[List[Dict], List[str]]:
    """STARTING / BENCH / UNRESOLVED rows for my roster.

    Every name in the roster file gets a row: a name the projections could
    not resolve still appears, flagged, rather than quietly shrinking the
    roster to the part we happened to match.

    `dk_calls` (engine/dk.weekly_call, or cons["dk"]) attaches the
    hold-or-stream call to the held DST/K rows: the matrix keeps its shape
    - the model chip is still the consensus verdict, which consensus has
    already set from this call - and the call itself rides as row["dk"],
    printed as the model cell's note and as one line in the drawer.
    """
    cmap = consensus_mod.consensus_map(cons)
    notes: List[str] = []
    rows: List[Dict] = []
    # A missing matchup lookup yields None per player, which the dossier
    # renders as an absence. Never a NEUTRAL grade: neutral is a finding.
    look = matchup_of or (lambda _p: None)
    dk_calls = dk_calls or (cons or {}).get("dk") or {}
    dk_by_key = dict((c["held_key"], c) for c in dk_calls.values()
                     if c and c.get("held_key"))

    def _attach(row: Dict, player) -> Dict:
        call = dk_by_key.get(player.key)
        if call is None:
            return row
        row["dk"] = call
        model = row.get("model") or {}
        model["note"] = dk_mod.verdict_text(call)
        row["model"] = model
        return row

    # THE NUMBER. Every roster row carries the weekly projection the
    # lineup was built on (meta[key]["weekly"]: None = none filed, which is
    # not 0.0) and which feed it came from, so the score cell can say what
    # it is made of. has_proj marks that a read was made at all.
    meta = lineup_build.get("meta") or {}

    def _with_proj(row: Dict, player) -> Dict:
        m = meta.get(player.key) or {}
        row["has_proj"] = True
        row["proj"] = m.get("weekly")
        row["proj_source"] = m.get("source") or ""
        return row

    starters = lineup_build.get("rows") or []
    filled = sum(1 for _, p in starters if p is not None)
    for slot, p in starters:
        if p is None:
            rows.append({
                "group": "STARTING", "slot": slot, "player": "(open slot)",
                "pos": "", "team": "", "key": "", "meta": "no known player "
                "fits this slot", "relevance": "",
                "cells": [vote_cell(None) for _ in cols],
                "model": _plain_model(
                    "OPEN", "no known player fits this slot - an empty seat "
                            "here means missing roster data, not a benched "
                            "player"),
                "level": LVL_NONE, "marker": "", "cons": None, "split": 0,
                "voices": 0})
            continue
        rows.append(_with_proj(_attach(
            make_row("STARTING", slot, p.name, p.pos, p.team, p.key,
                     cmap.get(p.key), cols, relevance=_relevance_tag(p, ctx),
                     matchup=look(p)), p), p))

    for p in lineup_build.get("bench") or []:
        rows.append(_with_proj(_attach(
            make_row("BENCH", "", p.name, p.pos, p.team, p.key,
                     cmap.get(p.key), cols, relevance=_relevance_tag(p, ctx),
                     matchup=look(p)), p), p))

    # THE SLOT DECIDED IT: derived from the lineup build, or not stated.
    slot_why(rows, lineup_build)

    unresolved = list(lineup_build.get("unresolved") or [])
    for name in unresolved:
        rows.append({
            "group": "UNRESOLVED ROSTER NAMES", "slot": "", "player": name,
            "pos": "", "team": "", "key": "", "relevance": "",
            "meta": "no projection matched this name",
            "cells": [vote_cell(None) for _ in cols],
            "model": _plain_model(
                "NO MATCH", "this roster name did not resolve against the "
                            "rankings pool, so no voice - ours included - "
                            "could vote on him"),
            "level": LVL_NONE, "marker": "", "cons": None, "split": 0,
            "voices": 0})

    known = len(roster_names)
    if known and filled + len(lineup_build.get("bench") or []) < known:
        notes.append("%d of %d roster names resolved to a projected player; "
                     "the rest are listed under UNRESOLVED, not dropped."
                     % (filled + len(lineup_build.get("bench") or []), known))
    if unresolved:
        notes.append("unresolved: %s" % ", ".join(unresolved))
    return rows, notes


def add_rows(ranked: Sequence, cmap: Dict[str, Dict], cols: Sequence[Dict],
             mode: str, ctx, top_n: int = TOP_ADDS,
             matchup_of: Optional[Callable] = None) -> List[Dict]:
    """Waiver candidates in matrix shape; model column = the add verdict.

    The model cell here is a labelled chip, not a verdict chip: BURN and a
    FAAB band are affirmative calls (the gold fill), HOLD and PASS are a
    pass (the ghost outline).
    """
    look = matchup_of or (lambda _p: None)
    out = []
    for i, cand in enumerate(ranked[:top_n], start=1):
        p = cand.player
        if mode == "priority":
            label = "BURN" if cand.burn == "YES" else "HOLD"
            tone = "start" if cand.burn == "YES" else "sit"
            why = cand.burn_detail
        else:
            label = ("FAAB %s" % cand.faab if cand.faab != "pass"
                     else "PASS")
            tone = "start" if cand.score > 0 and cand.faab != "pass" else "sit"
            why = ""
        detail = ["score %.1f" % cand.score,
                  "ros %+.1f vs %s" % (cand.ros_gain, cand.ros_basis),
                  "xfp %+.1f (%s)" % (cand.xfp_pts, cand.xfp_detail),
                  "trend %+.1f (%s)" % (cand.trend_pts, cand.trend_detail)]
        if cand.owned_detail:
            detail.append("owned %+.1f (%s)" % (cand.owned_pts,
                                                cand.owned_detail))
        if cand.comp_detail:
            detail.append(cand.comp_detail)
        if cand.burn_detail:
            detail.append(cand.burn_detail)
        model = {"label": label, "verdict": None, "tone": tone,
                 "pct": "score %.1f" % cand.score, "pct_n": None,
                 "agree": "", "hot": False,
                 "why": why or cand.comp_detail or "",
                 "title": " | ".join(detail)}
        out.append(make_row("WAIVER ADDS", "#%d" % i, p.name, p.pos, p.team,
                            p.key, cmap.get(p.key), cols, model=model,
                            relevance=_relevance_tag(p, ctx),
                            matchup=look(p)))
    return out


def target_rows(targets: Sequence, cmap: Dict[str, Dict],
                cols: Sequence[Dict], ctx,
                limit: int = TOP_TARGETS,
                matchup_of: Optional[Callable] = None) -> List[Dict]:
    """Named trade targets in matrix shape; model column = the trade verdict."""
    look = matchup_of or (lambda _p: None)
    out = []
    for t in targets[:limit]:
        p = t.get
        model = {
            "label": "TRADE FOR", "verdict": None, "tone": "start",
            "pct": "%+.1f pts/wk" % t.my_delta_wk, "pct_n": None,
            "agree": "",
            "hot": bool(getattr(t, "lopsided", False)),
            "why": "give %s · %s accepts ~%d%%"
                   % (t.give.surname(), t.team.name,
                      int(round(100 * t.accept_odds))),
            "title": "%s | %s | %s"
                     % (t.summary(), t.value_label(), t.starters_label()),
        }
        out.append(make_row("TRADE TARGETS", "GET", p.name, p.pos,
                            p.team, p.key, cmap.get(p.key), cols,
                            model=model,
                            meta="from %s · give %s"
                                 % (t.team.name, t.give.short_label()),
                            relevance=_relevance_tag(p, ctx),
                            matchup=look(p)))
    return out


def offroster_rows(cons: Dict, owned_keys, shown_keys,
                   cols: Sequence[Dict]) -> List[Dict]:
    """Consensus rows for players a creator named who I do not roster.

    These exist only when a creator call landed on somebody outside my
    roster - a start/sit take on a player I could add. Showing them here
    keeps the call visible instead of letting it fall off the page.
    """
    out = []
    for r in cons.get("rows") or []:
        key = r["player_key"]
        if key in owned_keys or key in shown_keys:
            continue
        out.append(make_row("CREATOR CALLS ON PLAYERS I DO NOT ROSTER", "",
                            r["player"], r["pos"], "", key, r, cols))
    out.sort(key=lambda r: (-r["split"], r["player"]))
    return out


def league_cards(view, rival_view, exposure, targets,
                 repl) -> Tuple[List[Dict], List[str]]:
    """Compact per-team cards: shape tags, exposure and target highlights."""
    target_keys = dict((t.get.key, t.team.name) for t in targets or [])
    teams = []
    if rival_view is not None and getattr(rival_view, "me", None) is not None:
        teams.append(rival_view.me)
    teams += list(getattr(rival_view, "teams", None) or [])

    cards, notes = [], []
    for team in teams:
        try:
            trades.shape_team(view.league, team, repl)
        except Exception as exc:  # noqa: BLE001 - a tag never kills the card
            notes.append("shape read unavailable for %s (%s)"
                         % (team.name, exc))
        tags = [("surplus", "+%d %s" % (n, pos)) for pos, n in team.surplus]
        tags += [("hole", "-%d %s" % (n, pos)) for pos, n in team.holes]
        players = []
        for p in sorted(team.players, key=lambda q: (q.pos, q.rank)):
            players.append({
                "name": p.short_label() if hasattr(p, "short_label")
                        else p.name,
                "pos": p.pos,
                "exposure": exposure.flag(p.key) if exposure is not None
                            else [],
                "target": p.key in target_keys and not team.is_me,
            })
        src = "%d known player(s)" % len(team.players)
        if team.unresolved:
            src += " · %d name(s) unmatched" % len(team.unresolved)
        cards.append({"name": team.name, "slot": team.slot,
                      "mine": bool(team.is_me), "tags": tags,
                      "players": players, "source": src})
    return cards, notes


# --- assembly ---------------------------------------------------------------

def build_page(league_id: str, week: int, force: bool = False,
               roster_dir: Optional[str] = None,
               calls_dir: Optional[str] = None,
               registry_path: Optional[str] = None,
               data_root: Optional[str] = None,
               now: Optional[datetime] = None,
               pa_rows_by_season: Optional[Dict[int, List[Dict]]] = None
               ) -> str:
    """The whole board as a string. Every section degrades on its own.

    `now` is the clock lock state is judged against (default: the real
    one, UTC). Tests pass a fixed instant so a fixture schedule can hold a
    played game without the wall clock deciding the result.

    `pa_rows_by_season` is the matching seam for the OTHER calendar-driven
    input, the points-allowed basis: {season: nflverse weekly stat rows},
    handed straight to engine/matchups.pa_table(rows_by_season=...), which
    then skips nflverse entirely. Tests use it to render the same league
    with and without current-season games on file. Default None: the live
    fetch, unchanged.
    """
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        raise SystemExit(missing_rankings_message(league, csv_path))
    week = int(week)
    players = load_players(csv_path)
    matcher = Matcher(players)
    scoring = league.scoring_label()
    waiver_mode = getattr(league, "waiver_mode", "faab")

    roster, roster_banner = waivers.load_my_roster(league_id, matcher,
                                                  dirpath=roster_dir)
    my_keys = set(roster.keys) if roster is not None else set()
    roster_players = [p for p in players if p.key in my_keys]
    known = len(my_keys)
    size = roster.size if roster is not None else 0
    roster_line = (("my roster known %d/%d" % (known, size)) if size
                   else "no roster file for this league")

    # Shared reads. A failure in any of these is caught by the section that
    # needs it, so one dead feed never blanks the page.
    state = {"cons": None, "build": None, "ctx": None, "view": None,
             "rival": None, "targets": [], "exposure": None,
             "repl": None, "cols": [], "shown": set(),
             # every section that died, in words - read by the divergence
             # panel so it can report what it could not see instead of
             # reporting the resulting silence as unanimity.
             "blocked": []}

    try:
        state["ctx"] = leaguesize.replacement_context(league, players=players)
    except Exception:  # noqa: BLE001 - relevance tags are decoration
        state["ctx"] = None

    # DEF/K hold-or-stream (engine/dk): ONE read per render, handed to the
    # consensus so the DST/K rows carry it. Read-only (no ledger append, no
    # %owned baseline); a failure is a note and the rows keep their
    # projection verdicts.
    state["dk"] = None
    if any(p.pos in ("DEF", "K") for p in roster_players):
        try:
            state["dk"] = dk_mod.weekly_call(league, week, roster_players,
                                             players, matcher, force=force)
        except Exception as exc:  # noqa: BLE001 - the matrix note says so
            state["dk"] = None
            state["dk_err"] = "%s: %s" % (type(exc).__name__,
                                          _one_line(str(exc), 160))

    cons = consensus_mod.build_consensus(league_id, week,
                                         roster_dir=roster_dir,
                                         calls_dir=calls_dir,
                                         registry_path=registry_path,
                                         force=force,
                                         dk_calls=state["dk"] or False)
    state["cons"] = cons

    # --- REPUTATION AT THE POINT OF USE (principle 3) ---------------------
    # Read the per-source record BEFORE the columns are built, because the
    # column header carries it. READ-ONLY: source_scoreboard() reads
    # data/performance_history.jsonl and the ledger and writes neither;
    # backfill_feed()/backfill_all(), which append rows, are not called from
    # this module at all.
    #
    # A failure here leaves perf=None, and source_columns() then omits the
    # "perf" key entirely so every header renders NO READ. It must never
    # fall back to a default state: STEADY is a claim, and a claim we cannot
    # support is not an acceptable substitute for a failure to read.
    try:
        state["perf"] = perf_mod.source_scoreboard(
            league, registry_path=registry_path)
    except Exception as exc:  # noqa: BLE001 - the section carries the error
        state["perf"] = None
        state["perf_err"] = "%s: %s" % (type(exc).__name__,
                                        _one_line(str(exc), 160))

    cols = source_columns(cons.get("sources") or [], perf=state.get("perf"))
    state["cols"] = cols

    # --- matchup grades for the dossier (engine/matchups.py) --------------
    # One PA table and one schedule fetch for the whole page; matchup_for is
    # then pure lookup per player. matchups.register() is deliberately NOT
    # called - registering the matchup source would rewrite the live
    # data/sources.yaml as a side effect of drawing a page.
    # THE SCHEDULE is read once, on its own guard: it feeds the matchup
    # opponent AND the lock state, and a dead points-allowed table must not
    # take the kickoff times down with it. `now` is fixed once per render
    # so every row is judged against the same clock.
    state["now"] = now if now is not None else datetime.now(timezone.utc)
    state["sched"] = None
    state["sched_err"] = ""
    try:
        state["sched"] = weekly.fetch_schedule(week, force=force)
    except Exception as exc:  # noqa: BLE001 - lock state stays unknown
        state["sched_err"] = "%s: %s" % (type(exc).__name__,
                                         _one_line(str(exc), 160))

    mstate = {"table": None, "sched": state["sched"], "err": "", "cache": {}}
    try:
        if state["sched"] is None:
            raise RuntimeError("schedule unavailable: %s"
                               % ui.humanize_error(state["sched_err"], "no read"))
        mstate["table"] = matchups_mod.pa_table(
            league, force=force, rows_by_season=pa_rows_by_season)
    except Exception as exc:  # noqa: BLE001 - the dossier carries the error
        mstate["err"] = "%s: %s" % (type(exc).__name__,
                                    _one_line(str(exc), 160))

    def _lock_rows(rows: Sequence[Dict]) -> int:
        """Lock state from the schedule; actuals for the locked rows only.
        The actuals file is fetched ONLY when some game has kicked off -
        before that nothing can be actual, so nothing is asked for."""
        n = apply_locks(rows, state["sched"], state["now"])
        if n and state.get("actuals") is None and "actuals_err" not in state:
            try:
                got = consensus_mod.week_actuals([week], force=force)
                state["actuals"] = dict((got or {}).get(week) or {})
            except Exception as exc:  # noqa: BLE001 - the note says so
                state["actuals_err"] = "%s: %s" % (type(exc).__name__,
                                                   _one_line(str(exc), 160))
        if n and state.get("actuals"):
            apply_actuals(rows, state["actuals"])
            for r in rows:
                if r.get("actual") is not None:
                    r["actual_week"] = week
        return n

    def _matchup_of(player):
        """matchup_for(), cached per player key; None on any failure.

        A player with no grade is a player with no grade - the dossier
        prints matchups.py's own `reason` string for it. What must not
        happen is a thrown exception here killing the matrix, since the
        matchup is context on a row, not the row itself.
        """
        if mstate["err"] or mstate["table"] is None:
            return None
        key = getattr(player, "key", None) or getattr(player, "name", "")
        if key in mstate["cache"]:
            return mstate["cache"][key]
        try:
            m = matchups_mod.matchup_for(player, week, league,
                                         table=mstate["table"],
                                         schedule=mstate["sched"])
        except Exception as exc:  # noqa: BLE001
            mstate["err"] = "%s: %s" % (type(exc).__name__,
                                        _one_line(str(exc), 160))
            return None
        mstate["cache"][key] = m
        return m

    # (2) the board: the calls, locked in, the bench, the grid --------------
    def _board() -> str:
        roster_l = lineup_mod.load_roster(league_id, dirpath=roster_dir)
        names = roster_l["players"] if roster_l else []
        proj = weekly.fetch_weekly_projections(week, scoring=scoring,
                                               force=force, quiet=True)
        try:
            injuries = fetch_injury_status(quiet=True)
        except Exception:  # noqa: BLE001 - the note says so
            injuries = None
        b = lineup_mod.build(league, names, week, proj, injuries=injuries,
                             matcher=matcher)
        state["build"] = b
        rows, notes = roster_rows(cons, b, names, cols, state["ctx"],
                                  matchup_of=_matchup_of,
                                  dk_calls=state.get("dk"))
        state["rows"] = rows
        state["shown"] = set(r["key"] for r in rows if r["key"])
        notes = list(notes)
        if roster_banner:
            notes.insert(0, roster_banner)
        # LOCK STATE + ACTUALS, from the schedule and the box score.
        locked_n = _lock_rows(rows)
        if state["sched"] is None:
            notes.append("schedule unavailable (%s) - no row is marked "
                         "LOCKED; lock state is unknown, not assumed open."
                         % (state["sched_err"] or "no read"))
        if locked_n and state.get("actuals_err"):
            notes.append("actuals unavailable (%s) - locked rows show the "
                         "projection only, with no actual claimed."
                         % ui.humanize_error(state["actuals_err"]))
        elif locked_n and not state.get("actuals"):
            notes.append("no box-score actual is on file yet for this "
                         "week's played games - locked rows keep their "
                         "projection, muted, until the file lands.")
        if cons.get("creator_enabled") and not cons.get("calls_count"):
            notes.append("no creator calls ingested for week %d - the "
                         "creator columns are empty because nothing was "
                         "extracted, not because those voices agree. Run: "
                         "python -m engine.calls --week %d" % (week, week))
        if injuries is None:
            notes.append("injury feed unavailable - statuses not checked, "
                         "not assumed healthy.")
        if state.get("dk"):
            notes.append("DST and K rows are HOLD-or-STREAM calls against "
                         "the best genuinely AVAILABLE defense/kicker this "
                         "week (engine/dk: %s) - the model chip is that "
                         "call, the note beside it names it, and the drawer "
                         "carries held vs best with each one's opponent."
                         % " / ".join(dk_mod.verdict_text(state["dk"][s])
                                      for s in dk_mod.SLOTS
                                      if state["dk"].get(s)))
        elif state.get("dk_err"):
            notes.append("DEF/K stream call unavailable (%s) - the DST/K "
                         "rows keep their projection verdicts."
                         % state["dk_err"])
        for n in cons.get("notes") or []:
            notes.append(n)
        notes.append("columns are your ENABLED sources, heaviest first - "
                     "each header is that source's face, its raw registry "
                     "weight (normalized per row over the sources that "
                     "actually voted) and its current form; hover for the "
                     "name and the record. Change them in Model Settings: "
                     "./sources.sh")
        notes.append("the form under each face comes from "
                     "engine/performance.py, so a dissenting chip can be "
                     "read against whether that voice has been right lately. "
                     "The full record is in the source scoreboard below and "
                     "on sources.html.")
        if state.get("perf") is None:
            notes.append("source records could not be read (%s) - every "
                         "column header says NO READ rather than defaulting "
                         "to STEADY, which would be a claim."
                         % state.get("perf_err", "unknown error"))
        if mstate["err"]:
            notes.append("matchup grades unavailable (%s) - the pop-out "
                         "shows no grade rather than a neutral one."
                         % mstate["err"])
        elif mstate["table"] is not None and mstate["table"].get("caveat"):
            notes.append(mstate["table"]["caveat"])
        # A partial roster is not a HOLE in the calls: the rows that exist
        # were genuinely arbitrated and the claim is already scoped to
        # them, so this caveat rides as a note rather than suppressing a
        # real finding.
        if size and known < size:
            notes.append("your roster is known %d/%d, so nothing here "
                         "speaks for the %d player(s) not in the capture - "
                         "they were never put in front of a source. Paste "
                         "the rest in Model Settings (./sources.sh -> "
                         "Leagues)." % (known, size, size - known))
        # NO CLAIM WITHOUT DATA. What was ACTUALLY weighed, and which of
        # the four grounds a card can be raised on could not be checked.
        judged = sum(1 for r in rows if r.get("voices"))
        holes = call_coverage(rows, cols, matchup_err=mstate["err"],
                              dk_err=state.get("dk_err") or "",
                              dk_read=bool(state.get("dk")))
        if any(is_call(r) for r in rows) and not cons.get("calls_count"):
            # Only a claim ABOUT the cards below, so it needs cards below.
            notes.append("every disagreement below is between BUILT-IN "
                         "feeds; no creator call was ingested this week, so "
                         "no creator quote can appear on a card.")
        return render_board(rows, cols, notes, matchup_err=mstate["err"],
                            week=week, judged=judged,
                            silent=len(rows) - judged, holes=holes)

    # (3) wire --------------------------------------------------------------
    def _wire() -> str:
        cmap = consensus_mod.consensus_map(cons)
        notes, banners = [], []

        rival = trades.load_rival_view(league, matcher, players,
                                       my_keys=my_keys)
        state["rival"] = rival
        rival_keys = rival.rostered_keys() if rival.available else set()

        # Both ESPN reads are platform-guarded: on a Yahoo league they are
        # NOT applied (the note says so) - ESPN rosters and ownership are
        # facts about the ESPN league only.
        taken, taken_note = waivers.espn_taken_keys(matcher, league=league)
        # advance=False (the default) is the whole point: the board READS
        # the %owned baseline and leaves it where it found it. Advancing it
        # here made a second render measure the wire against a snapshot the
        # first render had just written seconds earlier, collapsing every
        # delta to ~0 while the note still read "momentum active".
        owned, owned_note = waivers.owned_momentum(advance=False,
                                                   league=league)
        ros_map = waivers.build_ros_map(players, week, scoring, force=force)
        baselines = waivers.starter_baselines(league, roster_players,
                                              ros_map, players)
        xfp_map, xfp_label = waivers.fetch_xfp_signal(force=force)
        trending = waivers.fetch_trending_adds(force=force)
        pool = [p for p in players if p.key not in my_keys
                and p.key not in taken and p.key not in rival_keys]
        ranked = waivers.score_pool(pool, ros_map, baselines, xfp_map,
                                    trending, owned_delta=owned,
                                    xfp_label=xfp_label)
        comp = waivers.waiver_competition(league, rival,
                                          pool + roster_players, ros_map,
                                          players)
        waivers.apply_competition(ranked, comp)
        if waiver_mode == "priority":
            waivers.priority_guidance(ranked)
            waivers.priority_competition(ranked, comp)
        claims_ok, claims_reason = waivers.claim_gate(rival)
        if not claims_ok:
            # Same rule the home page applies: without rival rosters no
            # claim is surfaced - the candidates stay as a pool read.
            waivers.suppress_claims(ranked, claims_reason)

        arows = add_rows(ranked, cmap, cols, waiver_mode, state["ctx"],
                         matchup_of=_matchup_of)

        # trades
        repl = trades.replacement_from_pool(league, players)
        state["repl"] = repl
        raw = trades.fetch_fantasycalc(trades.ppr_param(league),
                                       trades.num_qbs_param(league),
                                       quiet=True)
        market = trades.market_values(players, trades.parse_rows(raw),
                                      matcher)
        projv = trades.proj_scale_values(league, players, market)
        targets = trades.rival_targets(league, players, roster_players,
                                       rival, market, projv, repl=repl)
        state["targets"] = targets
        trows = target_rows(targets, cmap, cols, state["ctx"],
                            matchup_of=_matchup_of)
        constructs = trades.suggest_constructs(league, roster_players,
                                               known, size)

        shown = set(state.get("shown") or ())
        shown |= set(r["key"] for r in arows + trows if r["key"])
        orows = offroster_rows(cons, my_keys, shown, cols)
        state["wire_rows"] = arows + trows + orows
        # A wire candidate whose game has started is as locked as anyone.
        _lock_rows(state["wire_rows"])

        if rival.available:
            notes.append("pool: %d ranked players; %d rival-rostered names "
                         "excluded (%s)" % (len(pool), len(rival_keys),
                                            rival.reason))
        else:
            banners.append("RIVAL ROSTERS UNKNOWN - %s. The add list is "
                           "everyone our pool does not know to be mine, so "
                           "the real wire is thinner than this: NO CLAIM IS "
                           "SURFACED (bands read n/a) and no trade target "
                           "can be named. Constructs below say the shape "
                           "instead. Paste the league rosters in Model "
                           "Settings -> Leagues to unlock it." % rival.reason)
            notes.append("pool: %d ranked players not known-mine."
                         % len(pool))
            notes.append(waivers.NO_COMPETITION)
        if not targets and rival.available:
            banners.append("no named trade target cleared the bar: every "
                           "1-for-1 we can build either fails to upgrade our "
                           "starting lineup or asks a rival to lose points. "
                           "The constructs below still stand.")
        for n in (taken_note, owned_note):
            if n:
                notes.append(n)
        if xfp_label:
            notes.append("xFP regression uses %s data - %d weeks not filed "
                         "yet." % (xfp_label, weekly.SEASON))
        if waiver_mode == "priority":
            notes.append("priority league: a claim spends queue position, "
                         "not budget. MY QUEUE: %s"
                         % waivers.priority_position_note(league))
        if size and known < size:
            notes.append("add/trade reads stand on %d/%d known players - "
                         "directional only." % (known, size))
        return render_wire(arows, trows, orows, cols, constructs, notes,
                           banners, matchup_err=mstate["err"])

    # (4) source scoreboard -------------------------------------------------
    def _scoreboard() -> str:
        notes = []
        if state.get("perf") is None:
            return render_scoreboard(None, cols, notes,
                                     err=state.get("perf_err")
                                     or "the source scoreboard could not be "
                                        "built", week=week)
        notes.append("weight is what you set in Model Settings "
                     "(./sources.sh); hit rate is what engine/performance.py "
                     "graded. They are independent on purpose - this page "
                     "reports the record, it does not silently re-weight "
                     "anyone off it.")
        return render_scoreboard(state["perf"], cols, notes, week=week)

    # (5) league view -------------------------------------------------------
    def _league() -> str:
        view = leagueview.load_league_view(league, matcher,
                                           data_root=data_root)
        state["view"] = view
        rival = state.get("rival")
        if rival is None:
            rival = trades.load_rival_view(league, matcher, players,
                                           my_keys=my_keys)
            state["rival"] = rival
        repl = state.get("repl")
        if repl is None:
            repl = trades.replacement_from_pool(league, players)
        try:
            exposure = Exposure.load(matcher, exclude_league_id=league.id,
                                     dirpath=roster_dir)
        except Exception:  # noqa: BLE001 - highlights are decoration
            exposure = None
        cards, card_notes = league_cards(view, rival, exposure,
                                         state.get("targets") or [], repl)
        notes = list(card_notes)
        banners = []
        if not view.complete():
            banners.append("%s - paste the missing rosters in Model Settings "
                           "(./sources.sh -> Leagues) to complete this view."
                           % view.banner_text())
        notes.extend(view.notes)
        if exposure is not None and exposure.available:
            notes.append("cross-league exposure from %s"
                         % "; ".join("%s %d/%d" % c
                                     for c in exposure.coverage()))
        else:
            notes.append("no other league roster on file - ALSO MINE "
                         "highlights are unavailable, not empty.")
        return render_league(cards, notes, banners)

    # A section that dies still occupies its slot, carrying its own error.
    # THE BOARD arbitrates its own rows now - the calls are raised from the
    # roster read, not from the wire - so it decides for itself what it
    # could not check (call_coverage) and nothing else can suppress a
    # finding it legitimately produced.
    failed = state["blocked"]
    board_html = _guard(BOARD_TITLE, _board, failed)
    wire_html = _guard("Wire - waiver adds and trade targets", _wire, failed)
    league_html = _guard("League view - the other teams", _league)
    scoreboard_html = _guard(SCOREBOARD_TITLE, _scoreboard)
    sections = [board_html, wire_html, league_html, scoreboard_html]

    view = state.get("view")
    coverage = (view.coverage_text() if view is not None
                else "league rosters not read")
    stamp = datetime.now().astimezone().strftime("%a %Y-%m-%d %I:%M %p %Z")
    masthead = render_masthead(league, week, cols, record_line(league),
                               coverage, roster_line, stamp)
    footer = ('<footer class="bd-foot">every number here is computed by the '
              "module that owns it - consensus, lineup, waivers, trades, "
              "leagueview, leaguesize, matchups, performance - and this page "
              "only arranges them. Read-only: the board never records "
              "source-ledger votes (that stays the digest's job, so opening "
              "the board twice cannot inflate a source's record), never "
              "advances the %%owned momentum baseline (only the digest or "
              "the waiver report does), never appends to "
              "data/performance_history.jsonl, and never registers a source "
              "into data/sources.yaml - so rendering twice changes nothing "
              "but this file.<br>the page fetches nothing but its typefaces: "
              "no external stylesheet, no image (every source face is "
              "embedded), no data. Its inline scripts are the shell's "
              "light/dark toggle, the pop-out promoter (which only moves an "
              "already-written detail drawer into the sheet and switches "
              "the Calls / Locked in / Bench / All view) and, when the "
              "design system "
              "ships one, its sheet script; with scripting off, every "
              "drawer still opens in place, the switch still works through "
              "the page fragment, and no fact is lost.<br>regenerate: "
              "<code>./board.sh %s %d</code> &#183; force fresh feeds: "
              "<code>.venv/bin/python -m engine.board --league %s --week %d "
              "--force</code> &#183; weights: <code>./sources.sh</code> "
              "&#183; the receipts: <a href=\"sources.html\">sources.html</a>"
              "</footer>"
              % (_esc(league_id), week, _esc(league_id), week))

    title = "%s - week %d board" % (league.name, week)
    # THE FOOTER IS PART OF THE CONTRACT, NOT DECORATION - and until the v2
    # rework it was built and then dropped: `footer` was composed here and
    # never interpolated, so no board ever printed the read-only guarantee
    # or the regenerate commands. It is in the page now, and a test asserts
    # it stays there, because a guarantee the reader cannot see is a
    # guarantee only the source code makes.
    #
    # ONE SHELL. ui.shell() is the first thing in <body>; the league
    # switcher links the sibling leagues' board files for this week.
    return ("<!doctype html>\n<html lang=\"en\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">\n"
            "<title>%s</title>\n%s\n<style>%s</style>\n</head><body>\n"
            "%s\n<main class=\"wr-page\">\n%s\n%s\n%s\n</main>\n%s\n"
            "</body></html>\n"
            % (_esc(title), ui.style_tag(), _CSS,
               ui.shell("board", league_id, week, leagues=league_choices()),
               masthead, "\n".join(sections), footer, dialog_html()))


def render_failure(exc: BaseException, league_id: str = "",
                   week: Optional[int] = None) -> str:
    """One legible line for a failure that killed the WHOLE render.

    Everything a section can survive is already caught by _guard and shown
    in place. What reaches here happened BEFORE any section could be
    built - a corrupt registry, a missing rankings csv, an unreadable
    roster - so there is no page to degrade, only a person at a terminal
    who needs to know which file is broken and what to do about it. A
    ParserError traceback answers neither question.
    """
    # Only the VARIABLE parts are trimmed. A remedy truncated by a long
    # tempdir path would defeat the whole point of this line existing.
    rerun = ("rerun ./board.sh %s%s once it parses"
             % (_one_line(league_id or "<league>", 60),
                " %d" % week if week else ""))
    name = type(exc).__name__

    # PyYAML carries the file and position of the break - use them.
    problem = getattr(exc, "problem", None)
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark",
                                                         None)
    if problem is not None or mark is not None:
        where = _one_line(getattr(mark, "name", "") or "the registry", 120)
        spot = ("" if mark is None
                else " (line %d, column %d)" % (mark.line + 1,
                                                mark.column + 1))
        return ("cannot render the board: %s is not valid YAML%s - %s. Fix "
                "that file by hand, or restore the built-in registry with "
                "./sources.sh, then %s."
                % (where, spot, _one_line(problem or name, 120), rerun))

    if isinstance(exc, (FileNotFoundError, IsADirectoryError,
                        PermissionError)):
        target = _one_line(getattr(exc, "filename", "")
                           or "a file the board needs", 120)
        return ("cannot render the board: %s (%s) - restore or re-create "
                "that file, then %s."
                % (_one_line(getattr(exc, "strerror", None) or name, 120),
                   target, rerun))
    if isinstance(exc, OSError):
        target = getattr(exc, "filename", "")
        return ("cannot render the board: %s%s - check the file and disk, "
                "then %s."
                % (_one_line(getattr(exc, "strerror", None) or str(exc)
                             or name, 120),
                   " (%s)" % _one_line(target, 120) if target else "", rerun))

    return ("cannot render the board: %s: %s - this failed before any "
            "section could be built, so nothing was written. Check the "
            "league yaml, data/sources.yaml and the rankings csv named by "
            "leagues/%s.yaml, then %s."
            % (name, _one_line(str(exc).strip() or name, 160),
               _one_line(league_id or "<league>", 60), rerun))


def write_board(league_id: str, week: int, force: bool = False,
                out_path: Optional[str] = None,
                roster_dir: Optional[str] = None,
                calls_dir: Optional[str] = None,
                registry_path: Optional[str] = None,
                data_root: Optional[str] = None) -> str:
    """Build and atomically write the board; returns the path written."""
    html = build_page(league_id, week, force=force, roster_dir=roster_dir,
                      calls_dir=calls_dir, registry_path=registry_path,
                      data_root=data_root)
    out = out_path or os.path.join(HERE, "board-%s-week%d.html"
                                   % (league_id, week))
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(html)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)
    return out


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.board",
        description="THE BOARD: the calls that need deciding as versus "
                    "cards, everything settled as one compact row each, "
                    "the full source-by-source grid behind the switch, "
                    "waiver and trade candidates in the grid's shape, and "
                    "the league view - one self-contained HTML page. "
                    "Prints the output path as its last line.")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--out", default=None,
                    help="output path (default: board-<league>-week<N>.html "
                         "in the project root)")
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when caches are fresh")
    ap.add_argument("--roster-dir", default=None,
                    help="read rosters from this directory instead of "
                         "data/rosters/ (read-only). publish.py hands each "
                         "person a copy holding only the leagues they own, "
                         "so the page cannot name a league that is not "
                         "theirs")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
        from engine.digest import current_week
        try:
            week = current_week()
        except RuntimeError as exc:
            print("cannot derive the current week (schedule feed down: %s) - "
                  "pass --week explicitly" % exc)
            return 1
        if week is None:
            print("no remaining %d regular-season week found in the schedule "
                  "- pass --week explicitly" % weekly.SEASON)
            return 1
        print("week %d (current, from the nflverse schedule)" % week)
    try:
        week = weekly._check_week(week)
    except ValueError as exc:
        print(exc)
        return 1

    # THE WHOLE RENDER PATH IS WRAPPED. Sections degrade in place inside
    # build_page; anything that dies before them (a corrupt data/sources.yaml,
    # a missing rankings csv, an unreadable roster) would otherwise leave a
    # raw traceback on the terminal running ./board.sh. One diagnosis line,
    # exit 1, no stack.
    try:
        path = write_board(args.league, week, force=args.force,
                           out_path=args.out, roster_dir=args.roster_dir)
    except KeyboardInterrupt:
        raise
    except SystemExit as exc:
        # build_page raises SystemExit with a written-for-humans message
        # for the config errors it can name itself.
        code = exc.code
        if isinstance(code, str):
            print(_one_line(code))
            return 1
        return int(code or 0)
    except BaseException as exc:  # noqa: BLE001 - the diagnosis replaces it
        print(render_failure(exc, args.league, week))
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
