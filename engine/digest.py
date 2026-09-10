"""Tuesday digest: one self-contained HTML brief for the week ahead.

    python -m engine.digest --league yahoo-main [--week N] [--force]

Writes digest-<league>-week<N>.html to the project root (atomic tmp+replace,
same as engine/strip.py) and prints the absolute path as its LAST stdout
line so wrappers (season.sh) can open it. The page is static HTML on the
shared design system (engine/ui.py, v3): ui.style_tag() supplies every
token and component, ui.shell() the navy header and league switcher, and
this module adds only a thin layer of digest classes written against
var(--wr-*) tokens - no hex colour lives here. There is no green and no red
anywhere: a verdict is encoded by WEIGHT (gold fill / ghost / dashed, via
ui.verdict_chip and the dg-chip family) and attention by a gold RULE beside
ink text. Sources appear as faces (ui.nameplate; pictures cached by
engine/sources.fetch_avatar). The page fetches nothing: fonts and faces
are embedded by engine/assets, and the theme toggle is the one inline
script.

COMPOSITION, NOT REIMPLEMENTATION: every section is produced by importing
the module that owns the logic -

  (a) waiver shortlist + FAAB bands (or burn-priority guidance when the
      league yaml says waiver_mode: priority) . engine/waivers
  (b) lineup verdicts + red alerts . engine/lineup    (build)
  (c) DEF/K streaming plan ........ engine/streaming  (build_board, plans)
  (d) trade constructs ............ engine/trades     (suggest_constructs)
  (e) injury flags on my roster ... engine/projections.fetch_injury_status
  (f) YOUR MODEL .................. engine/consensus  (build_consensus)
  (g) coverage banner ............. data/rosters/<league>.yaml known/size

YOUR MODEL (branding for the consensus section - internally still
render_room / build_consensus) is the source-agreement matrix: rows are
this week's contested lineup calls plus any player where the sources SPLIT
or the top-weighted voice disagrees; columns are the enabled sources by
weight; cells are verdict chips, with the weighted verdict phrased as
"Your model says START - 71%". It carries a degradation banner ONLY when
enabled creator sources exist but the week's calls file is empty - absence
of creator opinion is otherwise normal. Rendering the section also updates
the source ledger (data/source_ledger.jsonl): this week's votes are
recorded before outcomes are known (keyed per league - see
engine/consensus.py), and last week's pending votes are scored once
actuals land (rule documented in engine/consensus.py). A source scoreboard
joins the section once two scored weeks exist.

HONEST DEGRADATION: each section is built inside a guard; a dead feed or a
missing file renders the section WITH a visible "section degraded" note
(the exception's own message) instead of the section silently vanishing.
The roster-coverage banner rides on top of the whole page whenever the
roster file is partial (positive-only semantics - see engine/exposure.py).

WRITE DISCIPLINE: the digest writes only under data/cache/ (feed
snapshots - with ESPN cookies present the waivers section refreshes
data/cache/espn-owned-snapshot.json, the history %owned momentum needs),
the source ledger data/source_ledger.jsonl (YOUR MODEL's vote/score records -
idempotent appends and outcome fills only; tests redirect
consensus.LEDGER_PATH), plus the one HTML file; it never touches saves/,
data/rosters/, or the streaming log (data/streaming_log.jsonl stays the
streaming CLI's).

Default week = the current week derived from the nflverse schedule (the
smallest regular-season week whose last game has not finished yet). When
the schedule feed is down there is no honest default, so the CLI asks for
an explicit --week instead of guessing.
"""

import argparse
import glob
import html as _html
import os
import sys
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple

try:
    from engine import streaming, trades, ui, waivers, weekly
    from engine.grader import positional_gaps, surplus_positions
    from engine.ingest import Matcher
    from engine.models import (LeagueConfig, Player, load_players,
                               missing_rankings_message, repo_path)
    from engine.projections import fetch_injury_status
    from engine import consensus as consensus_mod
    from engine import lineup as lineup_mod
except ImportError:  # run directly as `python engine/digest.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import streaming, trades, ui, waivers, weekly
    from engine.grader import positional_gaps, surplus_positions
    from engine.ingest import Matcher
    from engine.models import (LeagueConfig, Player, load_players,
                               missing_rankings_message, repo_path)
    from engine.projections import fetch_injury_status
    from engine import consensus as consensus_mod
    from engine import lineup as lineup_mod

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOP_WAIVERS = 8        # shortlist rows on the page
STREAM_HORIZON = 3     # weeks the streaming plan looks ahead
STREAM_TOP = 5         # DEF/K rows per table


# --- current week from the schedule -----------------------------------------

def current_week(rows: Optional[List[Dict]] = None,
                 today: Optional[date] = None) -> Optional[int]:
    """Smallest regular-season week whose last game is today or later.

    Pure when `rows` (nflverse games.csv rows) and `today` are injected.
    None = the season is over, or the rows carry no usable dates - callers
    must then ask for an explicit week rather than guess.
    """
    if rows is None:
        rows = weekly._schedule_rows()
    today = today or date.today()
    last_day: Dict[int, date] = {}
    for r in rows:
        if (r.get("season") != str(weekly.SEASON)
                or r.get("game_type") != "REG"):
            continue
        try:
            w = int(r.get("week") or 0)
            d = datetime.strptime((r.get("gameday") or "").strip(),
                                  "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if w >= 1 and (w not in last_day or d > last_day[w]):
            last_day[w] = d
    for w in sorted(last_day):
        if last_day[w] >= today:
            return w
    return None


# --- html plumbing ----------------------------------------------------------

def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


# The digest's own layer over the design system. Every colour is a
# var(--wr-*) token; there is no hex here and no green or red anywhere.
# Chips carry meaning by WEIGHT - gold fill (the call to make), ghost
# outline (the quiet no), dashed (a lean) - and attention is a gold rule
# beside ink text, never a red fill. Prefixed dg- so nothing here can
# collide with the system's wr- vocabulary.
_DIGEST_CSS = """
  .dg-mast { margin: 0 0 16px; }
  .dg-wk { color: var(--wr-gold); font-weight: 500; font-size: 0.72em;
           letter-spacing: 0.04em; }
  .dg-sec + .dg-sec { margin-top: 14px; }
  .dg-banner { margin: 0 0 14px; }
  .dg-banner b { color: var(--wr-gold); letter-spacing: 0.04em; }
  .dg-sub { margin: 14px 0 6px; font-size: 11px; letter-spacing: 0.12em;
            text-transform: uppercase; color: var(--wr-gold); }
  .dg-table { font-size: 13.5px; }
  .dg-table th.dg-r, .dg-table td.dg-r { text-align: right; }
  .dg-table td { vertical-align: top; }
  .dg-who { font-weight: 700; }
  .dg-meta { color: var(--wr-muted); font-weight: 400; font-size: 12px; }
  .dg-why { color: var(--wr-muted); font-size: 12px; margin-top: 1px;
            overflow-wrap: anywhere; }
  .dg-open { color: var(--wr-dim); font-style: italic; }
  .dg-chip {
    display: inline-flex; align-items: center; gap: 4px;
    border-radius: 5px; padding: 2px 8px; border: 1px solid transparent;
    font-size: 11.5px; font-weight: 700; letter-spacing: 0.4px;
    white-space: nowrap; line-height: 1.35; color: var(--wr-text);
  }
  .dg-chip-fill  { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                   border-color: var(--wr-chip-start); }
  .dg-chip-ghost { color: var(--wr-muted); border-color: var(--wr-chip-sit); }
  .dg-chip-dash  { color: var(--wr-chip-lean);
                   border: 1px dashed var(--wr-chip-lean); }
  .dg-chip-flag  { color: var(--wr-text); background: var(--wr-wash-hot);
                   border-color: var(--wr-hairline-2);
                   box-shadow: inset 3px 0 0 var(--wr-rule); }
  .dg-attn { color: var(--wr-text); padding-left: 9px;
             box-shadow: inset 3px 0 0 var(--wr-rule); }
  .dg-attn code, .dg-foot code, .wr-note code {
    font-family: "Spline Sans Mono", ui-monospace, SFMono-Regular, Menlo,
                 monospace; font-size: 11.5px;
  }
  .dg-list { margin: 6px 0; padding-left: 20px; }
  .dg-list li { margin: 3px 0; font-size: 13.5px; }
  .dg-alerts { list-style: none; padding-left: 0; }
  .dg-alert { padding-left: 10px; box-shadow: inset 3px 0 0 var(--wr-rule); }
  .dg-alert-red { font-weight: 700; }
  .dg-verdict { font-weight: 700; }
  .dg-verdict .dg-slot { color: var(--wr-gold); }
  .dg-plan { font-size: 13.5px; margin: 6px 0; }
  .dg-plan b { color: var(--wr-text); }
  .dg-path { color: var(--wr-muted); font-size: 12px; }
  .dg-hot td { background: var(--wr-wash-hot); }
  .dg-hot td:first-child { box-shadow: inset 3px 0 0 var(--wr-rule); }
  .dg-agree { color: var(--wr-muted); font-size: 11px; text-transform: uppercase;
              letter-spacing: 0.6px; margin-top: 3px; }
  .dg-agree-hot { color: var(--wr-gold); }
  .dg-say { display: block; color: var(--wr-dim); font-size: 11px;
            letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 3px; }
  .dg-vote { display: inline-flex; flex-direction: column; gap: 2px; }
  .dg-vd { color: var(--wr-dim); font-size: 11px; letter-spacing: 0.04em; }
  .dg-table th .wr-np { vertical-align: middle; }
  .dg-inputs { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 6px 0 2px; }
  .dg-foot {
    margin-top: 22px; color: var(--wr-muted); font-size: 12px;
    border-top: 1px solid var(--wr-hairline); padding-top: 10px;
  }
  @media print { .dg-hot td { background: transparent; } }

  /* ---- PHONE: stack, do not pan ----------------------------------------
     A phone must not be handed the 9-column agreement matrix to drag
     sideways - and it must not lose the player's name off the left edge
     while it does. Under 700px every digest table restructures into one
     card per row, and each cell prints its own column name from data-l,
     which is why that attribute rides on the CELL rather than only in the
     (now hidden) header row. This is the pattern already proven on the
     board's table.mx / table.sb.

     EVERY selector below is anchored with > to the digest table's OWN
     rows. A descendant selector here would reach into any table nested
     inside a cell and un-table it, leaving a column of bare numbers with
     their headers cut off. */
  @media (max-width: 700px) {
    .dg-table { display: block; min-width: 0; }
    .dg-table > thead { display: none; }
    .dg-table > tbody { display: block; }
    .dg-table > tbody > tr {
      display: block; border: 1px solid var(--wr-hairline);
      border-radius: 8px; margin: 8px 0; overflow: hidden;
      background: var(--wr-panel);
    }
    .dg-table > tbody > tr.dg-hot {
      border-color: var(--wr-rule); box-shadow: inset 3px 0 0 var(--wr-rule); }
    .dg-table > tbody > tr.dg-hot > td:first-child { box-shadow: none; }
    .dg-table > tbody > tr > td {
      display: block; position: static; width: auto; min-width: 0;
      text-align: left; padding: 8px 10px;
      border-bottom: 1px solid var(--wr-hairline);
    }
    .dg-table > tbody > tr > td:last-child { border-bottom: none; }
    /* an empty cell would otherwise be a dead 33px strip in the card */
    .dg-table > tbody > tr > td:empty { display: none; }
    .dg-table > tbody > tr > td[data-l]::before {
      content: attr(data-l); display: block; color: var(--wr-muted);
      font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
      font-weight: 700; margin-bottom: 2px;
    }
    /* numbers keep their right edge: label left, value right on one line */
    .dg-table > tbody > tr > td.dg-r {
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 10px; text-align: right;
    }
    .dg-table > tbody > tr > td.dg-r::before {
      display: inline; margin-bottom: 0; flex: 0 1 auto; min-width: 0;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      text-align: left;
    }
    /* the identity cell leads its card and carries no label of its own */
    .dg-table > tbody > tr > td.dg-id {
      border-bottom: 1px solid var(--wr-hairline-2); }
    .dg-table > tbody > tr > td.dg-id::before { content: none; }
    /* a player's name is one line, always; the meta drops beneath it so
       nothing competes with it for the width */
    .dg-who { display: block; min-width: 0; }
    .dg-who > .dg-nm {
      display: block; white-space: nowrap; overflow: hidden;
      text-overflow: ellipsis; min-width: 0;
    }
    .dg-who > .dg-meta { display: block; }
  }
"""


def _style_tag() -> str:
    """The system's stylesheet (tokens, components, v3 layer, cached avatar
    rules) plus the digest layer - one <style>, nothing linked.

    THE ONE-LINE EXCEPTION. Every other renderer calls ui.style_tag(), so
    every other page picked up the installable-app <head> tags for free
    when engine/pwa.py hooked that function. This module builds its own
    <style> around ui.css() instead, so it has to ask for the tags by
    name or the ledger would be the one page on the phone that is not part
    of the app. See engine/pwa.py.
    """
    # prefs_boot() FIRST and before the stylesheet: it is the pre-paint
    # script that stamps the reader's stored theme, density and quiet mode
    # onto <html>. Emitted after </head> it still works, but the page paints
    # light first and then flips - a white flash on a phone in Night or
    # Broadcast. Every other page gets this through ui.style_tag(); this one
    # builds its own <style>, so it has to ask by name.
    return "%s%s<style>%s%s</style>" % (ui.prefs_boot(), ui.head_tags(),
                                        ui.css(), _DIGEST_CSS)


_CHIP_TONE = {"fill": "dg-chip dg-chip-fill", "ghost": "dg-chip dg-chip-ghost",
              "dash": "dg-chip dg-chip-dash", "flag": "dg-chip dg-chip-flag"}


def _chip(tone: str, text, title: Optional[str] = None) -> str:
    """A digest chip by WEIGHT: fill (do it), ghost (quiet no), dash (lean),
    flag (attention - ink on a gold rule). Never a hue."""
    if tone not in _CHIP_TONE:
        raise ValueError("chip tone must be one of %s, got %r"
                         % (sorted(_CHIP_TONE), tone))
    attrs = (' title="%s"' % _esc(title)) if title else ""
    return '<span class="%s"%s>%s</span>' % (_CHIP_TONE[tone], attrs, _esc(text))


def _note(text_html: str, attention: bool = False) -> str:
    """A muted note; attention=True keeps the ink and adds the gold rule.
    `text_html` is trusted - escape its parts with _esc() first."""
    return '<p class="wr-note%s">%s</p>' % (" dg-attn" if attention else "",
                                            text_html)


def _card(title: str, body_html: str, notes: Optional[List[str]] = None
          ) -> str:
    return ('<section class="wr-card dg-sec">%s%s</section>'
            % (ui.section_header(title, notes=[n for n in (notes or []) if n]),
               body_html))


def _degraded(title: str, exc: BaseException) -> str:
    """The honesty contract, in the system's own words (ui.degraded_banner):
    the section stays, titled, carrying the exception's message."""
    return ('<section class="wr-card dg-sec">%s%s</section>'
            % (ui.section_header(title), ui.degraded_banner(title, exc)))


def _guard(title: str, builder: Callable[[], str]) -> str:
    """Run one section builder; a failure renders a visible degradation
    card (honest-degradation contract) instead of dropping the section."""
    try:
        return builder()
    except SystemExit:            # config errors are for the CLI to raise
        raise
    except BaseException as exc:  # noqa: BLE001 - the note shows the error
        if isinstance(exc, KeyboardInterrupt):
            raise
        return _degraded(title, exc)


# --- section renderers (pure: data in, html out) ----------------------------

def _table(head_cells: List[str], rows_html: str) -> str:
    """A wr-table in a wr-scroll box. `head_cells` are trusted <th> strings."""
    return ('<div class="wr-scroll"><table class="wr-table dg-table">'
            '<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
            % ("".join(head_cells), rows_html))


def _th(text, right: bool = False) -> str:
    return '<th%s>%s</th>' % (' class="dg-r"' if right else "", _esc(text))


def _who(name, meta=None) -> str:
    """Player identity: the NAME in its own element so it can never wrap.

    The name rides in .dg-nm rather than as a bare text node because the
    phone layer gives it nowrap + ellipsis and drops .dg-meta to a second
    line; text-overflow needs a real box to clip against, and an anonymous
    block (what a bare text node gets once .dg-meta goes block) does not
    inherit it. The title carries the full name so an ellipsis - which the
    stacked card is far too wide to ever trigger - is never a dead end.
    Desktop is unchanged: both spans are inline there.
    """
    meta_html = (' <span class="dg-meta">%s</span>' % _esc(meta)) if meta else ""
    return ('<span class="dg-who"><span class="dg-nm" title="%s">%s</span>%s'
            '</span>' % (_esc(name), _esc(name), meta_html))


def render_waivers(ranked, victim, drop_note: str, roster,
                   notes: List[str], top_n: int = TOP_WAIVERS,
                   mode: str = "faab") -> str:
    priority = (mode == "priority")
    rows = []
    for i, cand in enumerate(ranked[:top_n], start=1):
        p = cand.player
        why = ["ros %+.1f vs %s" % (cand.ros_gain, cand.ros_basis),
               "xfp %+.1f (%s)" % (cand.xfp_pts, cand.xfp_detail),
               "trend %+.1f (%s)" % (cand.trend_pts, cand.trend_detail)]
        if cand.owned_detail:
            why.append("owned %+.1f (%s)" % (cand.owned_pts,
                                             cand.owned_detail))
        if priority:
            why.append(cand.burn_detail)
            if cand.scarcity > 1.0 and cand.burn == "NO":
                why.append("thin %s pool (%.2fx scarcity) - a rival may "
                           "claim the fallback first"
                           % (p.pos, cand.scarcity))
        elif cand.scarcity > 1.0:
            why.append("FAAB band uses %.2fx scarcity (thin %s pool)"
                       % (cand.scarcity, p.pos))
        # the call to make is the FILLED chip; a pass is the ghost
        if priority:
            tone = "fill" if cand.burn == "YES" else "ghost"
            chip_text = "burn priority? %s" % cand.burn
        else:
            tone = "fill" if cand.score > 0 else "ghost"
            chip_text = "FAAB %s" % cand.faab
        rows.append(
            '<tr><td class="dg-r wr-num" data-l="rank">%d</td>'
            '<td class="dg-id">%s<div class="dg-why">%s</div></td>'
            '<td class="dg-r wr-num" data-l="score">%.1f</td>'
            '<td data-l="%s">%s</td></tr>'
            % (i, _who(p.name, "%s%s" % (p.pos, "-" + p.team if p.team else "")),
               _esc(" · ".join(why)), cand.score,
               "claim" if priority else "bid", _chip(tone, chip_text)))
    table = (_table([_th("#", right=True),
                     _th("player (score = ROS-over-starter + xFP-regression "
                         "+ trending)"),
                     _th("score", right=True),
                     _th("claim" if priority else "bid")], "".join(rows))
             if rows else _note("no candidates scored.", attention=True))

    if victim is None:
        drop = _note("drop candidate: %s" % _esc(drop_note), attention=True)
    else:
        drop = ('<p><b>Drop candidate:</b> %s <span class="dg-meta">(%s)'
                '</span></p>' % (_esc(victim.short_label()), _esc(drop_note)))
        if roster is not None and len(roster.keys) < roster.size:
            drop += _note("drawn from the %d/%d known players only - the real "
                          "worst drop may be an uncaptured name."
                          % (len(roster.keys), roster.size))
    title = ("Waiver shortlist - priority claims" if priority
             else "Waiver shortlist - FAAB bands")
    return _card(title, table + drop, notes)


def render_lineup(b: Dict, roster: Optional[Dict], week: int,
                  schedule: Optional[Dict], lines: Optional[Dict],
                  notes: List[str]) -> str:
    title = "Lineup - week %d verdicts and alerts" % week
    if roster is None:
        return _card(title, _note("no roster file (data/rosters/&lt;league&gt;"
                                  ".yaml) - nothing to line up. Create it to "
                                  "unlock this section.", attention=True))
    sigmas = b["sigmas"]
    rows_html = []
    for slot, p in b["rows"]:
        if p is None:
            rows_html.append('<tr><td data-l="slot">%s</td>'
                             '<td colspan="4" class="dg-open dg-id">'
                             'open - no KNOWN player fits (partial roster, '
                             'not an empty seat)</td></tr>' % _esc(slot))
            continue
        weekly_pts = (b["meta"].get(p.key) or {}).get("weekly")
        sig = sigmas.get(p.pos, 6.0)
        med = float(p.proj_points or 0.0)
        rng = ("%.1f (%.0f-%.0f)" % (med, max(0.0, med - sig), med + sig)
               if weekly_pts is not None else "no proj filed")
        game = (schedule or {}).get(p.team) if schedule is not None else None
        matchup = (("vs " if game.get("home") else "@ ") + game["opponent"]
                   if game else ("BYE" if schedule is not None and p.team
                                 else ""))
        kick = lineup_mod._fmt_kickoff(game["kickoff_iso"]) if game else ""
        levels = [a["level"] for a in b["alerts"] if a["player"] == p.name]
        # attention by weight: RED is ink on the gold rule, WARN a dashed lean
        flag = (_chip("flag", "RED") if "red" in levels else
                _chip("dash", "WARN") if "warn" in levels else "")
        rows_html.append(
            '<tr><td data-l="slot">%s</td><td class="dg-id">%s</td>'
            '<td class="dg-r wr-num" data-l="median (range)">%s</td>'
            '<td data-l="kickoff">%s</td><td%s>%s</td></tr>'
            % (_esc(slot), _who(p.name, "%s %s" % (p.team, matchup)),
               _esc(rng), _esc(kick),
               ' data-l="alert"' if flag else "", flag))
    body = _table([_th("slot"), _th("player"), _th("median (range)", right=True),
                   _th("kickoff"), "<th></th>"], "".join(rows_html))
    body += _note("filled-slot total %.1f median pts; range = median &plusmn; "
                  "1 sigma of weekly projection error (engine/lineup.py "
                  "method note)." % b["total"])

    body += '<h3 class="dg-sub">Verdicts</h3>'
    if b["verdicts"]:
        body += '<ul class="dg-list">%s</ul>' % "".join(
            '<li class="dg-verdict"><span class="dg-slot">[%s]</span> %s</li>'
            % (_esc(v["slot"]), _esc(v["text"])) for v in b["verdicts"])
    else:
        body += _note("none - every filled slot is decided by a clear margin.")

    body += '<h3 class="dg-sub">Alerts</h3>'
    if b["alerts"]:
        body += '<ul class="dg-list dg-alerts">%s</ul>' % "".join(
            '<li class="dg-alert dg-alert-%s">%s %s</li>'
            % ("red" if a["level"] == "red" else "warn",
               "RED ALERT -" if a["level"] == "red" else "WARN -",
               _esc(a["text"]))
            for a in b["alerts"])
    else:
        body += _note("none - no bye, zero-projection, or injury-flagged "
                      "starters among KNOWN players.")

    if b["bench"]:
        bench = ", ".join(
            "%s %s (%s)" % (p.pos, p.name,
                            ("%.1f" % (b["meta"].get(p.key) or {})
                             .get("weekly"))
                            if (b["meta"].get(p.key) or {}).get("weekly")
                            is not None else "no proj")
            for p in sorted(b["bench"],
                            key=lambda x: -float(x.proj_points or 0.0)))
        body += _note("bench: %s" % _esc(bench))
    if b["unresolved"]:
        body += _note("unresolved roster names (fix spelling in the roster "
                      "file): %s" % _esc(", ".join(b["unresolved"])),
                      attention=True)
    return _card(title, body, notes)


def _fmt_stream_row(i: int, c: Dict) -> str:
    opp = ("vs " if c["home"] else "@ ") + c["opp"]
    driver = ("opp implied" if c["pos"] == "DEF" else "own implied")
    imp = ("%s %.1f, adj %+.2f" % (driver, c["implied"], c["adj"])
           if c["implied"] is not None else "no line, adj 0.00")
    note = (" · %s" % _esc(c["note"])) if c["note"] else ""
    return ('<tr><td class="dg-r wr-num" data-l="rank">%d</td>'
            '<td class="dg-id">%s</td>'
            '<td class="dg-r wr-num" data-l="proj">%.2f</td>'
            '<td data-l="matchup driver">%s%s</td>'
            '<td class="dg-r wr-num" data-l="score">%.2f</td></tr>'
            % (i, _who(c["name"], opp), c["proj"], _esc(imp), note,
               c["score"]))


def render_streaming(week_boards, plans: Dict, names: Dict[str, str],
                     weeks: List[int], notes: List[str],
                     top: int = STREAM_TOP) -> str:
    body = ""
    first_week, first_board = week_boards[0]
    for pos in streaming.STREAM_POS:
        cands = first_board[pos]
        body += ('<h3 class="dg-sub">%s - week %d top %d available</h3>'
                 % (pos, first_week, min(top, len(cands))))
        if not cands:
            body += _note("no candidates - projections or schedule missing "
                          "for week %d." % first_week, attention=True)
        else:
            body += _table([_th("#", right=True), _th("streamer"),
                            _th("proj", right=True), _th("matchup driver"),
                            _th("score", right=True)],
                           "".join(_fmt_stream_row(i, c)
                                   for i, c in enumerate(cands[:top], 1)))
        plan = plans.get(pos)
        if plan is None:
            body += _note("no multi-week plan - no candidates across weeks "
                          "%d-%d." % (weeks[0], weeks[-1]), attention=True)
            continue
        hold, chain = plan["hold"], plan["chain"]
        hold_name = names.get(hold["key"], hold["key"])
        hold_path = " | ".join(
            ("wk%d %.2f (%s %s)" % (w, c["score"],
                                    "vs" if c["home"] else "@", c["opp"]))
            if c else "wk%d bye/none" % w
            for w, c in hold["per_week"])
        chain_path = " | ".join(
            "wk%d %s %.2f" % (w, names.get(k, k or "(none)"), s)
            for w, k, s in chain["path"])
        # HOLD / CHAIN are plain bold ink - the verdict chip below decides
        body += ('<p class="dg-plan"><b>HOLD</b> %s - %.2f pts over weeks '
                 '%d-%d, one move<br><span class="dg-path">%s</span></p>'
                 % (_esc(hold_name), hold["total"], weeks[0], weeks[-1],
                    _esc(hold_path)))
        body += ('<p class="dg-plan"><b>CHAIN</b> %.2f gross - %.1f move tax '
                 '(%d move(s)) = %.2f net<br><span class="dg-path">%s</span>'
                 '</p>' % (chain["gross"],
                           streaming.MOVE_COST * max(0, chain["moves"] - 1),
                           chain["moves"], chain["net"], _esc(chain_path)))
        if plan["recommendation"] == "chain":
            body += ('<p class="dg-plan">%s nets %+.2f over the hold.</p>'
                     % (_chip("fill", "VERDICT: CHAIN"),
                        chain["net"] - hold["total"]))
        else:
            body += ('<p class="dg-plan">%s - chaining does not clear the '
                     'move tax.</p>'
                     % _chip("fill", "VERDICT: HOLD %s" % hold_name))
    return _card("DEF / K streaming plan - weeks %d-%d"
                 % (weeks[0], weeks[-1]), body, notes)


def render_trades(league, roster_players: List[Player], known: int,
                  size: int, market: Dict[str, float],
                  projv: Dict[str, float], constructs: List[str],
                  notes: List[str]) -> str:
    body = ""
    if roster_players:
        rows = []
        for p in roster_players:
            mv, pv = market.get(p.key), projv.get(p.key)
            note = trades.disagreement(mv, pv)
            rows.append('<tr><td class="dg-id">%s</td>'
                        '<td class="dg-r wr-num" data-l="market">%s</td>'
                        '<td class="dg-r wr-num" data-l="proj (our ROS)">%s</td>'
                        '<td%s>%s</td></tr>'
                        % (_who(p.name,
                                p.pos + ("-" + p.team if p.team else "")),
                           ("%.0f" % mv) if mv is not None else "-",
                           ("%.0f" % pv) if pv is not None else "-",
                           ' data-l="gap"' if note else "",
                           _chip("dash", note) if note else ""))
        body += _table([_th("known holding"),
                        _th("market (FantasyCalc)", right=True),
                        _th("proj (our ROS)", right=True), _th("gap")],
                       "".join(rows))
    else:
        body += _note("no roster captured - holdings table empty until "
                      "data/rosters/%s.yaml has names." % _esc(league.id),
                      attention=True)

    shim = trades._RosterState(league, roster_players)
    gaps = positional_gaps(shim, 0)
    surplus = surplus_positions(shim, 0)
    body += ("<p><b>Need:</b> %s<br><b>Ammo:</b> %s</p>"
             % (_esc(", ".join(gaps) if gaps else
                     "none - every starting slot covered"),
                _esc(", ".join(surplus) if surplus else
                     "none among known players")))

    body += '<h3 class="dg-sub">Constructs to shop</h3>'
    if constructs:
        body += '<ul class="dg-list">%s</ul>' % "".join(
            "<li>%s</li>" % _esc(s) for s in constructs)
    else:
        body += _note("too little roster known to shape a trade - capture "
                      "more names in data/rosters/%s.yaml." % _esc(league.id))
    body += _note(_esc(trades.rival_note(league)))
    return _card("Trade constructs - shapes, not named offers", body, notes)


def render_injuries(roster_players: List[Player],
                    injuries: Optional[Dict[str, str]], known: int,
                    size: int) -> str:
    title = "Injury flags - my roster"
    if injuries is None:
        return _card(title, _note("injury feed unavailable - no statuses to "
                                  "show (not the same as healthy).",
                                  attention=True))
    if not roster_players:
        return _card(title, _note("no known roster players to check.",
                                  attention=True))
    flagged = []
    for p in roster_players:
        status = (injuries.get(p.nkey) or "").strip()
        if not status:
            continue
        # a RED status is attention (ink on the gold rule), WARN a dashed
        # lean, anything milder a ghost - weight, not hue
        tone = ("flag" if status.lower() in lineup_mod.RED_STATUSES else
                "dash" if status.lower() in lineup_mod.WARN_STATUSES
                else "ghost")
        flagged.append("<li>%s %s</li>"
                       % (_chip(tone, status.upper()),
                          _esc(p.short_label())))
    if flagged:
        body = '<ul class="dg-list dg-alerts">%s</ul>' % "".join(flagged)
    else:
        body = ("<p>No filed injury reports among the %d known players."
                "</p>" % len(roster_players))
    body += _note("positive-only feed: a missing report is \"no report "
                  "filed\", never \"healthy\" - and only %d/%d roster spots "
                  "are known." % (known, size))
    return _card(title, body)


def _room_cell(vote: Optional[Dict]) -> str:
    """One source's vote as the system's verdict chip (START gold fill, SIT
    ghost, FLEX dashed); the rank detail and confidence ride under it, the
    quote in the title. No vote = a dash, never an invented one."""
    if vote is None:
        return '<span class="dg-vd">&mdash;</span>'
    quote = (vote.get("quote") or "").strip()
    bits = [b for b in (vote.get("detail"), vote.get("confidence")) if b]
    detail = ('<span class="dg-vd">%s</span>' % _esc(" · ".join(bits))
              if bits else "")
    return ('<span class="dg-vote">%s%s</span>'
            % (ui.verdict_chip(vote["verdict"], size="sm",
                               title=quote or None), detail))


def render_room(cons: Dict, week: int, sb: Dict,
                notes: List[str]) -> str:
    """The agreement matrix: contested calls x enabled sources.

    Pure renderer - consensus rows in, HTML out. Rows shown: this week's
    close lineup calls, plus any SPLIT row and any row where the
    top-weighted voice disagrees with the weighted verdict or the engine
    (those rows are also highlighted). Sources are FACES: each column head
    is a compact nameplate (avatar + weight, the name on hover) and the
    inputs line under the matrix carries the full nameplates. No URLs are
    ever emitted - quotes ride in title attributes, provenance stays in the
    calls yaml.
    """
    sources = cons.get("sources") or []
    close = set(cons.get("close_keys") or [])
    body = ""

    if cons.get("creator_enabled") and not cons.get("calls_count"):
        body += _note("DEGRADED - no creator calls ingested this week - run: "
                      "<code>python -m engine.calls --week %d</code>"
                      % int(week), attention=True)

    show = [r for r in cons.get("rows") or []
            if r["player_key"] in close or r["agreement"] == "SPLIT"
            or r.get("top_disagrees") or r.get("vs_engine")]
    if show:
        head = "".join('<th>%s</th>'
                       % ui.nameplate(s, weight=s.get("weight"),
                                      compact=True, size=28)
                       for s in sources)
        rows_html = []
        for r in show:
            by_src = dict((v["source"], v) for v in r["votes"])
            # data-l carries the source's name so the stacked card names the
            # voice beside its vote - the column head is a face, and a face
            # cannot be printed by content: attr().
            cells = "".join(
                '<td data-l="%s">%s</td>'
                % (_esc(s.get("name") or s.get("id") or "source"),
                   _room_cell(by_src.get(s.get("id"))))
                for s in sources)
            agree = r["agreement"]
            if r.get("dissenter"):
                agree += " - dissenter: %s" % r["dissenter"]
            hot = bool(r.get("top_disagrees") or r.get("vs_engine"))
            note = ('<div class="dg-agree dg-agree-hot">%s</div>'
                    % _esc(r["top_note"])) if r.get("top_note") else ""
            rows_html.append(
                '<tr%s><td class="dg-id">%s</td>%s'
                '<td><span class="dg-say">Your model says</span>%s'
                '<div class="dg-agree">%s</div>%s</td></tr>'
                % (' class="dg-hot"' if hot else "",
                   _who(r["player"], r["pos"]), cells,
                   ui.verdict_chip(r["verdict"], consensus_mod.display_pct(r),
                                   title="weight share behind the winning "
                                         "side (flex-leans count half)"),
                   _esc(agree), note))
        body += _table([_th("player")] + [head] + [_th("your model")],
                       "".join(rows_html))
        body += _note("highlighted rows: the heaviest-weighted voice differs "
                      "from the engine or from your model's verdict. pct = "
                      "weight share behind the winning side (flex-leans "
                      "count half).")
    else:
        body += _note("no contested lineup calls and no split opinions this "
                      "week - your model's inputs and the engine agree on "
                      "every decision they can see.")

    plates = "".join(ui.nameplate(s, weight=s.get("weight"), size=24)
                     for s in sources)
    body += _note("your model's inputs (weight, normalized when the verdict "
                  "is computed):%s" % (" none enabled" if not sources else ""))
    if sources:
        body += '<div class="dg-inputs">%s</div>' % plates

    sb_weeks = sb.get("weeks") or []
    if len(sb_weeks) >= consensus_mod.SCOREBOARD_MIN_WEEKS and sb.get("rows"):
        body += ('<h3 class="dg-sub">Source scoreboard - weeks %s</h3>'
                 % ", ".join(str(w) for w in sb_weeks))
        body += _table([_th("source"), _th("scored calls", right=True),
                        _th("hits", right=True), _th("hit rate", right=True),
                        _th("weeks", right=True)],
                       "".join(
                           '<tr><td class="dg-id">%s</td>'
                           '<td class="dg-r wr-num" data-l="scored calls">%d'
                           '</td>'
                           '<td class="dg-r wr-num" data-l="hits">%d</td>'
                           '<td class="dg-r wr-num" data-l="hit rate">%.0f%%'
                           '</td>'
                           '<td class="dg-r wr-num" data-l="weeks">%d</td></tr>'
                           % (ui.nameplate(r["source"], size=22), r["scored"],
                              r["hits"], r["pct"], r["weeks"])
                           for r in sb["rows"]))
        body += _note("hit = a start-side call whose player outscored his "
                      "positional replacement (Nth-best actual at the "
                      "position, N = league starter demand); sit calls "
                      "invert. Rule + ledger: engine/consensus.py, "
                      "data/source_ledger.jsonl.")
    elif sb_weeks:
        body += _note("source scoreboard appears once %d scored weeks exist "
                      "in the ledger (%d so far) - one week is noise, not a "
                      "track record."
                      % (consensus_mod.SCOREBOARD_MIN_WEEKS, len(sb_weeks)))

    body += _note("model settings: <code>./sources.sh</code> &middot; ingest "
                  "creator calls: <code>python -m engine.calls --week %d"
                  "</code>" % int(week))
    return _card("YOUR MODEL - source agreement matrix", body, notes)


def _attention_banner(inner_html: str) -> str:
    """A page-level statement the reader must not miss - the system's warn
    banner (gold rule, hot wash) around trusted HTML built from _esc()."""
    return ('<div class="wr-banner wr-banner-warn dg-banner">%s'
            '<span class="wr-banner-t">%s</span></div>'
            % (ui.icon("news", 20), inner_html))


def coverage_banner(league_id: str, roster) -> str:
    if roster is None:
        return _attention_banner(
            "<b>NO ROSTER FILE</b> for %s (data/rosters/%s.yaml). Nothing "
            "below can exclude your own players or protect starters. Create "
            "the file to unlock everything." % (_esc(league_id),
                                                _esc(league_id)))
    known = len(roster.keys)
    if known >= roster.size:
        return ""
    return _attention_banner(
        "<b>PARTIAL ROSTER: %s known %d/%d.</b> Every section below runs on "
        "KNOWN players only (positive-only semantics): a player not listed "
        "may still be rostered - by you or a rival - and no list here is "
        "complete. Fill data/rosters/%s.yaml to full strength to unlock "
        "everything." % (_esc(roster.name), known, roster.size,
                         _esc(league_id)))


def league_pairs(root: Optional[str] = None) -> List[Tuple[str, str]]:
    """[(id, name)] for every readable leagues/*.yaml - the shell's league
    switcher. An unreadable file is skipped, never fatal to the page."""
    out = []
    for path in sorted(glob.glob(os.path.join(root or HERE, "leagues",
                                              "*.yaml"))):
        try:
            cfg = LeagueConfig.load(path)
        except Exception:  # noqa: BLE001 - one bad yaml never hides the rest
            continue
        out.append((str(cfg.id), str(cfg.name)))
    return out


# --- assembly ---------------------------------------------------------------

def build_digest(league_id: str, week: int, force: bool = False,
                 roster_dir: Optional[str] = None) -> str:
    """The whole page as a string. Sections degrade independently."""
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        raise SystemExit(missing_rankings_message(league, csv_path))
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

    injuries: Optional[Dict[str, str]] = None
    try:
        injuries = fetch_injury_status(quiet=True)
    except Exception:  # noqa: BLE001 - the injury section says so
        injuries = None

    # (a) waivers ------------------------------------------------------------
    def _waivers() -> str:
        # Platform-guarded: ESPN rosters / ownership are read only for the
        # ESPN league, and a Yahoo digest never rolls the ESPN baseline.
        taken, taken_note = waivers.espn_taken_keys(matcher, league=league)
        # The digest is the weekly refresh (it records ledger votes too), so
        # it is the run that advances the %owned baseline - see this module's
        # WRITE DISCIPLINE note and waivers.owned_momentum. Read-only pages
        # (the board) read that baseline without moving it. A same-day rerun
        # keeps the baseline (waivers.MIN_BASELINE_AGE_H).
        owned, owned_note = waivers.owned_momentum(advance=True,
                                                   league=league)
        rival = trades.load_rival_view(league, matcher, players,
                                       my_keys=my_keys)
        rival_keys = rival.rostered_keys() if rival.available else set()
        ros_map = waivers.build_ros_map(players, week, scoring, force=force)
        baselines = waivers.starter_baselines(league, roster_players,
                                              ros_map, players)
        xfp_map, xfp_label = waivers.fetch_xfp_signal(force=force)
        trending = waivers.fetch_trending_adds(force=force)
        pool = [p for p in players
                if p.key not in my_keys and p.key not in taken
                and p.key not in rival_keys]
        ranked = waivers.score_pool(pool, ros_map, baselines, xfp_map,
                                    trending, owned_delta=owned,
                                    xfp_label=xfp_label)
        if waiver_mode == "priority":
            waivers.priority_guidance(ranked)
        claims_ok, claims_reason = waivers.claim_gate(rival)
        if claims_ok:
            victim, drop_note = waivers.drop_candidate(league, roster_players,
                                                       ros_map)
        else:
            # No claim, so no cut to make room for one.
            waivers.suppress_claims(ranked, claims_reason)
            victim, drop_note = None, ("no drop suggested - no claim is "
                                       "surfaced while rival rosters are "
                                       "unknown")
        notes = [n for n in (roster_banner, taken_note, owned_note) if n]
        if rival.available:
            notes.append("pool: %d ranked players; %d rival-rostered names "
                         "excluded (%s)." % (len(pool), len(rival_keys),
                                             rival.reason))
        else:
            notes.append("RIVAL ROSTERS UNKNOWN - %s" % claims_reason)
            notes.append("pool: %d ranked players not known-mine - the real "
                         "wire is thinner than this list." % len(pool))
        if xfp_label:
            notes.append("xFP regression uses %s data - 2026 weeks not "
                         "filed yet." % xfp_label)
        if waiver_mode == "priority":
            notes.append("priority league: a claim spends queue position, "
                         "not budget. MY QUEUE: %s."
                         % waivers.priority_position_note(league))
        # THIS LEAGUE's name and THIS league's waiver mode. Both were once
        # hardcoded to the author's own league ("Kid's Table uses FAB;
        # waivers process Tuesday"), which put one owner's league name and
        # one owner's waiver schedule onto every Yahoo league's page - a
        # cross-tenant leak that publish.py's pre-flight refuses, and a
        # false claim besides. Nothing here may name a league we are not
        # rendering. The processing day is NOT read from Yahoo, so it is
        # given as Yahoo's default and labelled as one.
        if getattr(league, "platform", "") == "yahoo" and waiver_mode == "faab":
            notes.append("%s uses FAB (blind budget bids). Yahoo's default "
                         "is Tuesday processing with bids in the night "
                         "before - we do not read your league's waiver "
                         "schedule, so confirm it in Yahoo." % league.name)
        return render_waivers(ranked, victim, drop_note, roster, notes,
                              mode=waiver_mode)

    # (b) lineup -------------------------------------------------------------
    def _lineup() -> str:
        roster_l = lineup_mod.load_roster(league_id, dirpath=roster_dir)
        proj = weekly.fetch_weekly_projections(week, scoring=scoring,
                                               force=force, quiet=True)
        try:
            schedule = weekly.fetch_schedule(week, force=force)
        except RuntimeError:
            schedule = None
        lines = weekly.fetch_game_lines(week, force=force) or None
        b = lineup_mod.build(league, roster_l["players"] if roster_l else [],
                             week, proj, schedule=schedule, lines=lines,
                             injuries=injuries,
                             sigmas=lineup_mod.position_sigma(),
                             matcher=matcher)
        notes = []
        stale = lineup_mod.stale_note(roster_l)
        if stale:
            notes.append(stale)
        if roster_l and len(roster_l["players"]) < roster_l["size"]:
            notes.append("lineup uses KNOWN players only (%d of %d) - an "
                         "open slot means no known player fits, not an "
                         "empty seat." % (len(roster_l["players"]),
                                          roster_l["size"]))
        if schedule is None:
            notes.append("schedule feed unavailable - bye detection and "
                         "kickoff locks skipped, not guessed.")
        if injuries is None:
            notes.append("injury feed unavailable - statuses not checked.")
        return render_lineup(b, roster_l, week, schedule, lines, notes)

    # (b2) your model (the consensus section) ---------------------------------
    def _room() -> str:
        cons = consensus_mod.build_consensus(league_id, week,
                                             roster_dir=roster_dir,
                                             force=force)
        room_notes = list(cons["notes"])
        # Ledger: record this week's votes before outcomes are known, then
        # score any pending prior week whose actuals have landed. Appends
        # are idempotent; verdicts are never rewritten (humility-ledger
        # rule - see engine/consensus.py).
        try:
            added = consensus_mod.record_votes(week, cons["rows"],
                                               league=cons["league"])
            if added:
                room_notes.append("recorded %d vote(s) for week %d in the "
                                  "source ledger (scored once actuals land)."
                                  % (added, week))
            sc = consensus_mod.score_ledger(league, players, week)
            if sc.get("scored"):
                room_notes.append(
                    "scored %d pending vote(s) against week %s actuals."
                    % (sc["scored"],
                       ", ".join(str(w) for w in sc["weeks"])))
            if sc.get("note"):
                room_notes.append("pending votes not scored yet: %s."
                                  % sc["note"])
        except OSError as exc:
            room_notes.append("source ledger not updated (%s)." % exc)
        sb = consensus_mod.scoreboard(consensus_mod.read_ledger())
        return render_room(cons, week, sb, room_notes)

    # (c) streaming ----------------------------------------------------------
    def _streaming() -> str:
        roster_keys, coverage = streaming._roster_keys(
            league_id, dirpath=roster_dir)
        last = min(week + STREAM_HORIZON - 1, weekly.FINAL_WEEK)
        weeks = list(range(week, last + 1))
        notes, week_boards = [], []
        for w in weeks:
            try:
                board = streaming.build_board(w, scoring, force=force,
                                              quiet=True)
                board = streaming.filter_available(board, roster_keys, None)
            except RuntimeError as exc:
                notes.append("week %d feeds unavailable (%s) - skipped."
                             % (w, exc))
                board = {"DEF": [], "K": []}
            week_boards.append((w, board))
        names: Dict[str, str] = {}
        for _, board in week_boards:
            for pos in streaming.STREAM_POS:
                for cand in board[pos]:
                    names.setdefault(cand["key"], cand["name"])
        plans = {}
        for pos in streaming.STREAM_POS:
            week_maps = [(w, dict((c["key"], c) for c in board[pos]))
                         for w, board in week_boards]
            plans[pos] = streaming.plan_position(week_maps)
        if coverage is None:
            notes.append("no roster file - NOTHING is excluded; every "
                         "candidate may already be taken.")
        else:
            disp, kn, sz = coverage
            notes.append("availability is positive-only: %s roster known "
                         "%d/%d, other teams' rosters unknown - a listed "
                         "streamer may already be rostered." % (disp, kn, sz))
        notes.append("digest is read-only: nothing appended to the "
                     "streaming humility ledger (the streaming CLI logs).")
        return render_streaming(week_boards, plans, names, weeks, notes)

    # (d) trades -------------------------------------------------------------
    def _trades() -> str:
        raw = trades.fetch_fantasycalc(trades.ppr_param(league),
                                       trades.num_qbs_param(league),
                                       quiet=True)
        market = trades.market_values(players, trades.parse_rows(raw),
                                      matcher)
        projv = trades.proj_scale_values(league, players, market)
        constructs = trades.suggest_constructs(league, roster_players,
                                               known, size)
        notes = ["market = FantasyCalc redraft values; proj = our VBD "
                 "quantile-mapped to the same scale (engine/trades.py)."]
        if size and known < size:
            notes.append("gap/ammo read stands on %d/%d known players - "
                         "directional only." % (known, size))
        return render_trades(league, roster_players, known, size, market,
                             projv, constructs, notes)

    # assemble ---------------------------------------------------------------
    waiver_title = ("Waiver shortlist - priority claims"
                    if waiver_mode == "priority"
                    else "Waiver shortlist - FAAB bands")
    sections = [
        _guard(waiver_title, _waivers),
        _guard("Lineup - week %d verdicts and alerts" % week, _lineup),
        _guard("YOUR MODEL - source agreement matrix", _room),
        _guard("DEF / K streaming plan", _streaming),
        _guard("Trade constructs - shapes, not named offers", _trades),
        _guard("Injury flags - my roster",
               lambda: render_injuries(roster_players, injuries, known,
                                       size)),
    ]

    stamp = datetime.now().astimezone().strftime("%a %Y-%m-%d %I:%M %p %Z")
    title = "%s - week %d digest" % (league.name, week)
    shell = ui.shell("digest", league_id, week, league_pairs())
    masthead = ('<header class="dg-mast">'
                '<p class="wr-kicker">The Ledger &middot; Tuesday digest</p>'
                '<h1 class="wr-h1 wr-display">%s <span class="dg-wk wr-num">'
                'week %d</span></h1>'
                '<p class="wr-lede">%s scoring &middot; %d teams &middot; '
                'generated %s</p></header>'
                % (_esc(league.name), week, _esc(scoring), league.teams,
                   _esc(stamp)))
    footer = ('<footer class="dg-foot">data refreshed %s from local caches '
              '(standard data/cache freshness windows; a section says so '
              'when its feed was down).<br>regenerate: <code>./season.sh %s '
              '%d</code> &middot; force fresh feeds: <code>.venv/bin/python '
              '-m engine.digest --league %s --week %d --force</code>'
              '<br>see the same week as a picture - every player against '
              'every source, and where they disagree: THE BOARD, '
              '<code>./board.sh %s %d</code> (writes '
              'board-%s-week%d.html)</footer>'
              % (_esc(stamp), _esc(league_id), week, _esc(league_id), week,
                 _esc(league_id), week, _esc(league_id), week))

    return ('<!doctype html>\n<html lang="en"><head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, '
            'initial-scale=1">\n'
            '<title>%s</title>\n%s\n</head><body>\n'
            '%s\n<main class="wr-page">\n%s\n%s\n%s\n%s\n</main>\n'
            '</body></html>\n'
            % (_esc(title), _style_tag(), shell, masthead,
               coverage_banner(league_id, roster),
               "\n".join(sections), footer))


def write_digest(league_id: str, week: int, force: bool = False,
                 out_path: Optional[str] = None,
                 roster_dir: Optional[str] = None) -> str:
    """Build and atomically write the digest; returns the path written."""
    html = build_digest(league_id, week, force=force, roster_dir=roster_dir)
    out = out_path or os.path.join(HERE,
                                   "digest-%s-week%d.html" % (league_id, week))
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
        prog="python -m engine.digest",
        description="Tuesday digest: waivers, lineup, streaming, trades, and "
                    "injury flags in one self-contained HTML brief. Prints "
                    "the output path as the last line.")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--out", default=None,
                    help="output path (default: digest-<league>-week<N>.html "
                         "in the project root)")
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when caches are fresh")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
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

    path = write_digest(args.league, week, force=args.force,
                        out_path=args.out)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
