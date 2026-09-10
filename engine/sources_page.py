"""THE RECEIPTS: every voice in the model, and whether it has been right.

    python -m engine.sources_page                 # current week, espn-1 basis
    python -m engine.sources_page --week 3
    python -m engine.sources_page --league yahoo-main
    ./sources_page.sh                             # wrapper - opens the page

Writes sources.html to the project root (atomic tmp+replace, the same
discipline as engine/board.py) and prints the absolute path as its LAST
stdout line so the shell wrapper can open it. ./board.sh also refreshes
this page after every board render, because the board links here and a
link that 404s is a promise broken.

WHAT IT ANSWERS. The board's scoreboard is one row per source - enough to
read a dissenting chip against its owner's form. This page is the full
receipt for each voice: one card per source, the enabled ones first and
heaviest first, the disabled ones in a quieter section below.

  DECAY STRIP    at the top: the 2025 archive phases out of every headline
                 number on a fixed schedule by completed week of this
                 season (100% -> 60% -> 30% -> 0%). The schedule is READ
                 from engine/performance.BACKFILL_DECAY / backfill_weight,
                 never restated here, and the current step carries the
                 gold rule.
  ONE CARD       per source: a large nameplate (the face, 44px), the
                 weight, the form state, the BLENDED headline hit rate with
                 the label that says what it is made of and the note that
                 says how, the sample size, the current streak, a wide
                 weekly sparkline, per-position split bars, the start-split
                 against the sit-split, and a provenance line that says
                 "reconstructed 2025 archive" or "live 2026 calls" - never
                 a bare number.
  NO-DATA        is a fact, not a failure. A creator who has never been
                 graded says exactly why, in engine/performance.py's own
                 words (CREATOR_REASON): no history - starts accumulating
                 week 1. Nothing is invented to fill the card.

DESIGN SYSTEM (engine/ui.py v3). Light editorial paper, navy shell, ONE
accent (gold). There is no green and no red anywhere on this page: hit
rates are ink numbers, the split bars are INK meters (a fill of the text
colour on a hairline track), and attention is a gold rule. Every colour is
a var(--wr-*) token; this module declares no hex of its own. ui.py has no
horizontal bar component, so `ink_meter()` below builds one locally from
the tokens - it is the one component this page had to draw itself.

READ-ONLY. engine/performance.py is used through source_scoreboard(),
history_series(), blend_bases() and backfill_weight(), which read
data/performance_history.jsonl and the source ledger and write neither.
backfill_feed()/backfill_all()/append_history(), which append rows, are
never called from here; sources.save_sources() is never called either. A
test parses this file's AST for all of them and byte-checks the data files
either side of two renders.

SELF-CONTAINED, FONTS ONLY. The page fetches nothing but the typefaces the
shared stylesheet names: no external stylesheet, no image (the source
faces are embedded by ui.avatar_css()), no data. The only script is the
shell's light/dark toggle, which degrades to following the OS.

Tests redirect the registry, the history file and the ledger into a
tempdir; see tests/sources_page_test.py.
"""

import argparse
import glob
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    from engine import performance as perf_mod
    from engine import sources as sources_mod
    from engine import ui, weekly
    from engine.models import LeagueConfig, repo_path
except ImportError:  # run directly as `python engine/sources_page.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import performance as perf_mod
    from engine import sources as sources_mod
    from engine import ui, weekly
    from engine.models import LeagueConfig, repo_path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAGUE_DIR = os.path.join(HERE, "leagues")
OUT_NAME = "sources.html"
DEFAULT_LEAGUE = "espn-1"

SPARK_W = 360           # the wide sparkline - this page has the room
SPARK_H = 44

esc = ui.esc


# --- shared with the board --------------------------------------------------

def league_choices(league_dir: Optional[str] = None) -> List[Tuple[str, str]]:
    """[(id, name)] for every league yaml, in a stable order - the shell's
    league switcher. A yaml that will not parse is listed by its filename
    rather than dropped, so the switcher never silently loses a league."""
    out = []
    for path in sorted(glob.glob(os.path.join(league_dir or LEAGUE_DIR,
                                              "*.yaml"))):
        lid = os.path.splitext(os.path.basename(path))[0]
        name = lid
        try:
            import yaml
            with open(path) as fh:
                raw = yaml.safe_load(fh) or {}
            lid = str(raw.get("id") or lid)
            name = str(raw.get("name") or lid)
        except Exception:  # noqa: BLE001 - a broken yaml is still a league
            pass
        out.append((lid, name))
    return out


def blend_for(row: Dict, week: Optional[int] = None) -> Dict:
    """The decay-blended headline for one scoreboard row, AS OF `week`.

    source_scoreboard() already attaches `blend`, computed for the number
    of completed weeks it could derive on its own. A page is rendered for a
    named week, so when the two disagree the blend is recomputed through
    the same performance.blend_bases() over the row's own bases - the
    function is theirs, only the week is ours. Without bases to recompute
    from, the row's blend stands.
    """
    blend = dict(row.get("blend") or {})
    if week is None:
        return blend
    done = perf_mod.weeks_completed(week)
    bases = row.get("bases")
    if blend.get("weeks_played") == done or not isinstance(bases, dict):
        return blend
    return perf_mod.blend_bases(bases, done)


# --- pure helpers -----------------------------------------------------------

def pct(value, dash: str = "—") -> str:
    """A rate as a percentage, or the dash. None is NOT 0%."""
    if value is None:
        return dash
    try:
        return "%d%%" % int(round(100.0 * float(value)))
    except (TypeError, ValueError):
        return dash


def headline(blend: Dict) -> Tuple[str, str, str]:
    """(number, label, note) - '63%', '2025 archive', the blend's note.

    A missing rate is the words "no graded call", never 0%, and then the
    label is empty: "no graded call · 2025 archive" would say two things
    about a number that does not exist.
    """
    rate = (blend or {}).get("hit_rate")
    note = str((blend or {}).get("note") or "")
    if rate is None:
        return "no graded call", "", note
    return pct(rate), str((blend or {}).get("label") or ""), note


def provenance_line(row: Dict) -> str:
    """What the row's own numbers rest on, in words a reader can trust."""
    prov = (row or {}).get("provenance") or "none"
    if prov == perf_mod.PROV_LIVE:
        return "live %d calls" % weekly.SEASON
    if prov == perf_mod.PROV_BACKFILL:
        return "reconstructed %d archive" % perf_mod.SEASON_BACKFILL
    return "no graded calls on any basis"


def streak_text(row: Dict) -> str:
    n = int((row or {}).get("streak") or 0)
    d = int((row or {}).get("streak_dir") or 0)
    if n <= 0 or d == 0:
        return "no run - the latest solid week sits on its own baseline"
    return "%d straight week%s %s its own baseline" % (
        n, "" if n == 1 else "s", "above" if d > 0 else "below")


def state_html(state, reason: str = "") -> str:
    """HOT / COLD as ui.py badges; every other state as words.

    STEADY is deliberately words too: ui.streak_badge() renders ANY unknown
    state as the STEADY badge, which is the right default for a player with
    no trend and the wrong one for a source with no record, so the badge
    path is taken only for the two states that earn a glyph.
    """
    key = str(state or "NO-DATA").strip().upper()
    if key in ("HOT", "COLD"):
        badge = ui.streak_badge(key.lower(), "sm")
        if reason:
            return '<span class="rc-state" title="%s">%s</span>' % (
                esc(reason), badge)
        return badge
    t = ' title="%s"' % esc(reason) if reason else ""
    return '<span class="rc-state rc-state-w"%s>%s</span>' % (t, esc(key))


def ink_meter(label, rate, n=None, title: Optional[str] = None) -> str:
    """One horizontal split bar in ink - a LOCAL component.

    engine/ui.py has sparklines and the five-segment matchup meter but no
    proportional bar, so this page draws its own from the tokens: the fill
    is the text colour on a hairline track, the width is the rate. No hue
    anywhere - a 40% RB read is not "red", it is 40%. A missing rate draws
    an empty track and the dash, never a zero-width bar pretending to be a
    measurement.
    """
    if rate is None:
        width = 0
        val = "—"
    else:
        try:
            width = max(0, min(100, int(round(100.0 * float(rate)))))
        except (TypeError, ValueError):
            width = 0
        val = "%d%%" % width
    if n is not None:
        val += ' <small>(%s)</small>' % esc(n)
    t = ' title="%s"' % esc(title) if title else ""
    return ('<div class="rc-bar%s"%s><span class="rc-bar-l">%s</span>'
            '<span class="rc-bar-t"><span class="rc-bar-f" style="width:%d%%">'
            '</span></span><span class="rc-bar-v wr-num">%s</span></div>'
            % (" rc-bar-none" if rate is None else "", t, esc(label), width,
               val))


def decay_steps(weeks_done: int) -> List[Dict]:
    """The phase-out schedule as steps, read from engine/performance.py.

    One step per completed-week count from 0 up to the retirement week; the
    last step is "N+" because backfill_weight() is 0 from there on. The
    current step is the one for `weeks_done`, clamped into the schedule.
    """
    retired = int(perf_mod.BACKFILL_RETIRED_AFTER)
    try:
        done = max(0, int(weeks_done))
    except (TypeError, ValueError):
        done = 0
    cur = min(done, retired)
    steps = []
    for w in range(0, retired + 1):
        weight = perf_mod.backfill_weight(w)
        if w == 0:
            label = "0 weeks completed"
            sub = "pre-season: the archive is all there is"
        elif w < retired:
            label = "%d week%s completed" % (w, "" if w == 1 else "s")
            sub = "live record taking over"
        else:
            label = "%d+ weeks completed" % w
            sub = "archive retired - this season only"
        steps.append({"weeks": w, "weight": weight, "current": w == cur,
                      "label": label, "sub": sub})
    return steps


# --- renderers (pure: data in, html out) ------------------------------------

def render_decay_strip(weeks_done: int) -> str:
    steps = decay_steps(weeks_done)
    items = []
    for s in steps:
        items.append(
            '<li class="rc-step%s"%s><span class="rc-step-w wr-num">%d%%</span>'
            '<span class="rc-step-l">%s</span><span class="rc-step-s">%s</span>'
            '</li>'
            % (" cur" if s["current"] else "",
               ' aria-current="step"' if s["current"] else "",
               int(round(100 * s["weight"])), esc(s["label"]), esc(s["sub"])))
    now = perf_mod.backfill_weight(weeks_done)
    body = '<ol class="rc-strip">%s</ol>' % "".join(items)
    body += ('<p class="wr-note">now: %d completed week%s of %d, so the %d '
             'archive carries %d%% of every headline below and this '
             'season\'s live ledger carries %d%%. It never comes back once '
             'retired, and the two records are still shown unmixed on each '
             'card. Schedule: engine/performance.BACKFILL_DECAY, read here, '
             'not restated.</p>'
             % (weeks_done, "" if weeks_done == 1 else "s", weekly.SEASON,
                perf_mod.SEASON_BACKFILL, int(round(100 * now)),
                int(round(100 * (1.0 - now)))))
    return body


def _source_dict(row: Dict) -> Dict:
    return {"id": row.get("source") or row.get("id"),
            "name": row.get("name") or row.get("source"),
            "type": row.get("type") or "feed"}


def _split_bars(row: Dict) -> str:
    per = row.get("per_position") or {}
    items = sorted(per.items(), key=lambda kv: (-(kv[1].get("n") or 0),
                                                kv[0]))
    bars = "".join(
        ink_meter(pos, blk.get("rate"), blk.get("n") or 0,
                  title="%s: %d of %d graded calls right"
                        % (pos, blk.get("hits") or 0, blk.get("n") or 0))
        for pos, blk in items)
    if not bars:
        return ('<p class="wr-note">no per-position split - nothing '
                'graded.</p>')
    return '<div class="rc-bars">%s</div>' % bars


def _direction_bars(row: Dict) -> str:
    starts = row.get("start_split") or {}
    sits = row.get("sit_split") or {}
    if not (starts.get("n") or sits.get("n")):
        return ""
    return ('<div class="rc-bars">%s%s</div>'
            '<p class="wr-note">the split matters: benching is the easier '
            'half of the job.</p>'
            % (ink_meter("START calls", starts.get("rate"),
                         starts.get("n") or 0,
                         title="%d of %d start calls right"
                               % (starts.get("hits") or 0,
                                  starts.get("n") or 0)),
               ink_meter("SIT calls", sits.get("rate"), sits.get("n") or 0,
                         title="%d of %d sit calls right"
                               % (sits.get("hits") or 0,
                                  sits.get("n") or 0))))


def _sparkline(row: Dict) -> str:
    values = row.get("sparkline_values") or []
    labels = row.get("sparkline_weeks") or []
    if values:
        span = ("weeks %s-%s" % (labels[0], labels[-1]) if labels
                else "by week")
        return ('<div class="rc-spark">%s<span class="rc-spark-l">weekly '
                'hit rate, %s (thin weeks withheld)</span></div>'
                % (ui.sparkline(values, width=SPARK_W, height=SPARK_H,
                                title="weekly hit rate by week"),
                   esc(span)))
    return ('<div class="rc-spark">%s<span class="rc-spark-l">no weekly '
            'series to draw - an empty sparkline, not a flat one</span>'
            '</div>'
            % ui.sparkline([], width=SPARK_W, height=SPARK_H,
                           title="no weekly series"))


def source_card(row: Dict, blend: Dict, top: bool = False) -> str:
    """One enabled source's full receipt."""
    sid = row.get("source") or ""
    state = row.get("state") or "NO-DATA"
    reason = row.get("state_reason") or ""
    num, label, note = headline(blend)
    plate = ui.nameplate(_source_dict(row), row.get("weight"),
                         state if state.upper() in ("HOT", "COLD") else None,
                         size=44)
    if num == "no graded call":
        head_num = '<span class="rc-big rc-big-none">%s</span>' % esc(num)
    else:
        head_num = ('<span class="rc-big wr-num">%s</span>'
                    '<span class="rc-lab" title="%s">%s</span>'
                    % (esc(num), esc(note), esc(label)))
    head = ('<div class="rc-head">%s<div class="rc-headline">%s</div></div>'
            % (plate, head_num))

    rate = row.get("hit_rate")
    why = ""
    if rate is None:
        why = row.get("backfill_reason") or reason or ""
        if row.get("is_creator"):
            why = row.get("backfill_reason") or perf_mod.CREATOR_REASON
    # The state's reason is printed once. When it IS the "why" below (a
    # creator's NO-DATA reason is its backfill reason), the line under the
    # state would repeat the callout word for word, so it rides in the
    # state's title instead.
    reason_line = "" if (why and why == reason) else esc(ui.trim(reason, 220))
    body = ('<div class="rc-form">%s<span class="rc-reason">%s</span></div>'
            % (state_html(state, reason), reason_line))
    if rate is None:
        body += '<p class="rc-why">%s</p>' % esc(why)
    else:
        n = int(row.get("sample_n") or 0)
        facts = [
            'n <b class="wr-num">%d</b> graded calls across <b class="wr-num">'
            '%d</b> week%s' % (n, row.get("weeks_n") or 0,
                               "" if (row.get("weeks_n") or 0) == 1 else "s"),
            'streak: %s' % esc(streak_text(row)),
        ]
        if row.get("avg_edge") is not None:
            facts.append('avg edge <b class="wr-num">%+.1f</b> pts'
                         % row["avg_edge"])
        if row.get("unscorable_n"):
            facts.append('%d call(s) unscorable (bye/inactive), graded '
                         'neither way' % row["unscorable_n"])
        body += ('<ul class="rc-facts">%s</ul>'
                 % "".join("<li>%s</li>" % f for f in facts))

    body += _sparkline(row)
    body += '<h4 class="rc-h4">by position</h4>' + _split_bars(row)
    dirs = _direction_bars(row)
    if dirs:
        body += '<h4 class="rc-h4">start calls against sit calls</h4>' + dirs

    prov = provenance_line(row)
    extra = ""
    if (row.get("backfill_state")
            and row.get("provenance") != perf_mod.PROV_LIVE):
        extra = (" · %d form read: %s, as of the end of that season - not a "
                 "statement about this week"
                 % (perf_mod.SEASON_BACKFILL, row["backfill_state"]))
    bases = row.get("bases") or {}
    if isinstance(bases, dict) and len(bases) > 1:
        extra += " · both bases on file, shown unmixed: " + "; ".join(
            "%s %s over n%d" % (k, pct(v.get("hit_rate")),
                                v.get("sample_n") or 0)
            for k, v in sorted(bases.items()))
    body += '<p class="rc-prov">basis: %s%s</p>' % (esc(prov), esc(extra))

    return ('<article class="rc-card%s" id="src-%s" data-source="%s">%s%s'
            '</article>'
            % (" top" if top else "", esc(sid), esc(sid), head, body))


def quiet_card(source: Dict, series: Optional[Dict],
               err: str = "") -> str:
    """A disabled source: named, weighed, and NOT in the model this week.

    Its record is still read (history_series, one source at a time) so a
    reader deciding whether to switch it back on can see what it has done -
    but the card is quieter, and says in words that its vote counts for
    nothing while it is off.
    """
    sid = source.get("id") or ""
    plate = ui.nameplate({"id": sid, "name": source.get("name") or sid,
                          "type": source.get("type") or "feed"},
                         source.get("weight"), None, size=32)
    body = ('<p class="rc-off">DISABLED - not in your model this week; its '
            'weight of %g counts for nothing until it is switched back on in '
            'Model Settings.</p>' % (float(source.get("weight") or 0)))
    if err:
        body += ('<p class="wr-note">record unavailable - %s. No state is '
                 'claimed.</p>' % esc(ui.trim(err, 160)))
    elif series:
        rate = series.get("baseline")
        basis = series.get("basis") or "none"
        if rate is None:
            body += ('<p class="rc-why">%s</p>'
                     % esc(perf_mod.CREATOR_REASON
                           if perf_mod.is_creator(source)
                           else (series.get("state_reason")
                                 or "no graded calls on this basis")))
        else:
            n = sum(int(w.get("n") or 0) for w in series.get("weeks") or [])
            body += ('<p class="rc-facts-line">%s on %s · n <b class="wr-num">'
                     '%d</b> · form read %s</p>'
                     % (esc(pct(rate)),
                        esc("the reconstructed %d archive"
                            % perf_mod.SEASON_BACKFILL
                            if basis == perf_mod.PROV_BACKFILL
                            else "live %d calls" % weekly.SEASON),
                        n, esc(series.get("state") or "NO-DATA")))
        body += _sparkline({"sparkline_values": series.get("values") or [],
                            "sparkline_weeks": series.get("labels") or []})
    return ('<article class="rc-card rc-quiet" id="src-%s" data-source="%s">'
            '<div class="rc-head">%s</div>%s</article>'
            % (esc(sid), esc(sid), plate, body))


def _degraded_section(title: str, exc) -> str:
    return ('<section class="wr-card rc-sec">%s%s</section>'
            % (ui.section_header(title), ui.degraded_banner(title, exc)))


# --- assembly ---------------------------------------------------------------

_CSS = """
  .rc-mast { margin: 0 0 16px; }
  .rc-sec + .rc-sec { margin-top: 14px; }
  .rc-sec .wr-sec { margin-bottom: 10px; }

  /* decay strip: four steps, the current one on the gold rule ---------- */
  .rc-strip {
    list-style: none; margin: 4px 0 0; padding: 0;
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
  }
  .rc-step {
    border: 1px solid var(--wr-hairline); border-radius: 8px;
    padding: 10px 12px; background: var(--wr-raised);
    display: flex; flex-direction: column; gap: 2px; min-width: 0;
  }
  .rc-step.cur {
    background: var(--wr-wash-hot); border-color: var(--wr-rule);
    box-shadow: inset 0 3px 0 var(--wr-rule);
  }
  .rc-step-w { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
  .rc-step.cur .rc-step-w { color: var(--wr-gold); }
  .rc-step-l { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
               color: var(--wr-text); font-weight: 700; }
  .rc-step-s { font-size: 11.5px; color: var(--wr-muted); }

  /* cards --------------------------------------------------------------- */
  .rc-grid { display: grid; gap: 12px;
             grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  .rc-card {
    border: 1px solid var(--wr-hairline); border-radius: 10px;
    padding: 14px 16px 12px; background: var(--wr-panel); min-width: 0;
  }
  .rc-card.top { box-shadow: inset 0 3px 0 var(--wr-rule); }
  .rc-quiet { background: var(--wr-raised); opacity: 0.86; }
  .rc-head { display: flex; align-items: center; justify-content: space-between;
             gap: 12px; flex-wrap: wrap; }
  .rc-head .wr-np-n { font-size: 15px; white-space: normal; }
  .rc-headline { display: flex; flex-direction: column; align-items: flex-end;
                 line-height: 1.1; }
  .rc-big { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }
  .rc-big-none { font-size: 13px; font-weight: 700; color: var(--wr-dim); }
  .rc-lab { font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
            color: var(--wr-gold); font-weight: 700; cursor: help;
            border-bottom: 1px dotted var(--wr-hairline-2); }
  .rc-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
             margin: 10px 0 4px; }
  .rc-state-w { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
                color: var(--wr-dim); border: 1px solid var(--wr-hairline-2);
                border-radius: 999px; padding: 1px 8px; }
  .rc-reason { font-size: 12px; color: var(--wr-muted); }
  .rc-why { font-size: 12.5px; color: var(--wr-text); margin: 6px 0;
            padding-left: 10px; border-left: 3px solid var(--wr-rule); }
  .rc-off { font-size: 12px; color: var(--wr-muted); margin: 8px 0 4px;
            letter-spacing: 0.02em; }
  .rc-facts { margin: 4px 0 6px; padding: 0; list-style: none;
              display: flex; flex-wrap: wrap; gap: 4px 16px;
              font-size: 12px; color: var(--wr-muted); }
  .rc-facts b { color: var(--wr-text); }
  .rc-facts-line { font-size: 12px; color: var(--wr-muted); margin: 4px 0; }
  .rc-facts-line b { color: var(--wr-text); }
  .rc-spark { margin: 8px 0 2px; color: var(--wr-gold); }
  .rc-spark .wr-spark { max-width: 100%; height: auto; display: block; }
  .rc-spark-l { display: block; font-size: 11px; color: var(--wr-muted);
                margin-top: 2px; }
  .rc-h4 { margin: 12px 0 4px; font-size: 11px; letter-spacing: 0.12em;
           text-transform: uppercase; color: var(--wr-dim); }
  .rc-bars { display: flex; flex-direction: column; gap: 4px; }
  .rc-bar { display: grid; grid-template-columns: 78px minmax(0, 1fr) 84px;
            align-items: center; gap: 8px; font-size: 12px; }
  .rc-bar-l { font-weight: 700; letter-spacing: 0.06em; color: var(--wr-muted);
              font-size: 11px; }
  .rc-bar-t { display: block; height: 8px; border-radius: 4px;
              background: var(--wr-hairline); overflow: hidden; }
  .rc-bar-f { display: block; height: 100%; background: var(--wr-text);
              border-radius: 4px; }
  .rc-bar-v { text-align: right; color: var(--wr-text); }
  .rc-bar-v small { color: var(--wr-dim); font-size: 11px; }
  .rc-bar-none .rc-bar-v { color: var(--wr-dim); }
  .rc-prov { font-size: 11.5px; color: var(--wr-muted); margin: 10px 0 0;
             border-top: 1px solid var(--wr-hairline); padding-top: 8px; }

  footer.rc-foot {
    margin-top: 22px; color: var(--wr-muted); font-size: 11.5px;
    border-top: 1px solid var(--wr-hairline); padding-top: 10px;
  }
  footer.rc-foot code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
  }

  @media (max-width: 700px) {
    .rc-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .rc-grid { grid-template-columns: 1fr; }
    .rc-headline { align-items: flex-start; }
    .rc-bar { grid-template-columns: 64px minmax(0, 1fr) 76px; }
  }
  @media print {
    .rc-card { break-inside: avoid; }
  }
"""


def build_page(league_id: str = DEFAULT_LEAGUE, week: int = 1,
               registry_path: Optional[str] = None,
               history_path: Optional[str] = None,
               ledger_path: Optional[str] = None,
               league_dir: Optional[str] = None) -> str:
    """The whole page as a string. The card section degrades on its own."""
    league_path = os.path.join(league_dir or LEAGUE_DIR, "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    week = int(week)
    weeks_done = perf_mod.weeks_completed(week)
    registry = sources_mod.load_sources(registry_path)
    enabled = [s for s in registry if s.get("enabled")]
    disabled = sorted((s for s in registry if not s.get("enabled")),
                      key=lambda s: (-float(s.get("weight") or 0),
                                     str(s.get("id"))))
    leagues = league_choices(league_dir)

    # --- the receipts -----------------------------------------------------
    sb, sb_err = None, None
    try:
        sb = perf_mod.source_scoreboard(league, registry_path=registry_path,
                                        path=history_path,
                                        ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001 - the section carries the error
        sb_err = exc

    title_in = "In your model - enabled sources, heaviest weight first"
    if sb_err is not None:
        cards_html = _degraded_section(title_in, sb_err)
        # The registry is still readable, so the ROSTER of voices is still
        # shown - names and weights, and nothing about form.
        plates = "".join(
            '<article class="rc-card" data-source="%s">'
            '<div class="rc-head">%s</div><p class="wr-note">record '
            'unavailable this render - no form state or hit rate is '
            'claimed.</p></article>'
            % (esc(s.get("id")),
               ui.nameplate({"id": s.get("id"), "name": s.get("name"),
                             "type": s.get("type")}, s.get("weight"), None,
                            size=44))
            for s in sorted(enabled, key=lambda s: (-float(s.get("weight")
                                                           or 0),
                                                    str(s.get("id")))))
        cards_html += ('<section class="wr-card rc-sec">%s<div class="rc-grid">'
                       '%s</div></section>'
                       % (ui.section_header("Voices on the registry",
                                            "%d enabled" % len(enabled)),
                          plates))
    else:
        rows = list((sb or {}).get("rows") or [])
        cards = []
        for i, r in enumerate(rows):
            cards.append(source_card(r, blend_for(r, week), top=(i == 0)))
        notes = list((sb or {}).get("notes") or [])
        notes.append("weight is what you set in Model Settings (./sources.sh); "
                     "the record is what engine/performance.py graded. They "
                     "are independent on purpose: this page reports the "
                     "record and never re-weights anyone off it.")
        notes.append("a source is never crowned on a thin sample: below %d "
                     "graded calls or %d graded weeks the state is "
                     "LOW-CONFIDENCE and can be neither HOT nor COLD."
                     % (perf_mod.MIN_GRADED_CALLS, perf_mod.MIN_GRADED_WEEKS))
        graded = sum(1 for r in rows if r.get("hit_rate") is not None)
        live = sum(1 for r in rows
                   if r.get("provenance") == perf_mod.PROV_LIVE)
        pre = ""
        if rows and live == 0:
            pre = ('<p class="rc-why">NO LIVE RECORD EXISTS YET. Week 1 of %d '
                   'has not been graded, so every CURRENT-form state below '
                   'is NO-DATA by fact, not by failure - a HOT badge is not '
                   'available to be earned yet. What the feeds do have is a '
                   'labelled %d reconstruction.</p>'
                   % (weekly.SEASON, perf_mod.SEASON_BACKFILL))
        cards_html = ('<section class="wr-card rc-sec" id="enabled">%s%s'
                      '<div class="rc-grid">%s</div>'
                      '<p class="wr-note">a rate labelled <b>%s</b> is a '
                      'RECONSTRUCTION: engine/performance.py replayed that '
                      'feed\'s published %d weekly archive against what '
                      'actually happened, graded by this league\'s own '
                      'replacement level. It is evidence about the feed, '
                      'not a recording of a call it filed at the time, and '
                      'the blend above says exactly how much of the headline '
                      'it still carries.</p></section>'
                      % (ui.section_header(
                             title_in,
                             "%d source(s) · %d with any graded record"
                             % (len(rows), graded), notes),
                         pre, "".join(cards) or
                         '<p class="wr-note">no source is enabled - switch '
                         'one on in Model Settings (./sources.sh).</p>',
                         esc(perf_mod.PROV_BACKFILL),
                         perf_mod.SEASON_BACKFILL))

    # --- the quiet section: disabled voices -------------------------------
    quiet = []
    for s in disabled:
        series, err = None, ""
        try:
            series = perf_mod.history_series(s.get("id"), league=league,
                                             path=history_path,
                                             ledger_path=ledger_path)
        except Exception as exc:  # noqa: BLE001 - one card, not the page
            err = "%s: %s" % (type(exc).__name__, exc)
        quiet.append(quiet_card(s, series, err))
    if quiet:
        quiet_html = ('<section class="wr-card rc-sec" id="disabled">%s'
                      '<div class="rc-grid">%s</div></section>'
                      % (ui.section_header(
                             "Not in your model - disabled sources",
                             "%d disabled" % len(quiet),
                             ["a disabled source's record is still read so "
                              "you can decide whether to switch it back on; "
                              "its vote counts for nothing while it is off."]),
                         "".join(quiet)))
    else:
        quiet_html = ('<section class="wr-card rc-sec" id="disabled">%s'
                      '<p class="wr-note">every registered source is enabled - '
                      'nothing is sitting out.</p></section>'
                      % ui.section_header("Not in your model - disabled "
                                          "sources", "0 disabled"))

    decay_html = ('<section class="wr-card rc-sec" id="decay">%s%s</section>'
                  % (ui.section_header(
                         "The archive phase-out - what the headline is made of",
                         None,
                         ["the %d reconstruction is the only evidence that "
                          "exists before week 1 and is worthless once this "
                          "season has spoken for itself, so it fades out of "
                          "every headline on a fixed schedule by completed "
                          "week." % perf_mod.SEASON_BACKFILL]),
                     render_decay_strip(weeks_done)))

    stamp = datetime.now().astimezone().strftime("%a %Y-%m-%d %I:%M %p %Z")
    mast = ('<header class="rc-mast"><p class="wr-kicker">The Receipts · '
            'week %d</p><h1 class="wr-h1 wr-display">Who has actually been '
            'right</h1><p class="wr-lede">Every voice in your model, graded '
            'against %s\'s own replacement level (%s scoring, %d teams). '
            'Generated %s.</p></header>'
            % (week, esc(league.name), esc(league.scoring_label()),
               league.teams, esc(stamp)))
    footer = ('<footer class="rc-foot">read-only: this page reads '
              'data/performance_history.jsonl and data/source_ledger.jsonl '
              'and writes neither; it never backfills, never appends a '
              'graded row, and never touches data/sources.yaml - rendering '
              'twice changes nothing but this file.<br>the page fetches '
              'nothing but its typefaces: no external stylesheet, no image '
              '(the faces are embedded), no data. Its only script is the '
              'light/dark toggle.<br>regenerate: <code>./sources_page.sh</code> '
              '&#183; a different basis: <code>.venv/bin/python -m '
              'engine.sources_page --league %s --week %d</code> &#183; '
              'weights and on/off: <code>./sources.sh</code></footer>'
              % (esc(league.id), week))

    title = "Sources - the receipts (week %d)" % week
    return ("<!doctype html>\n<html lang=\"en\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">\n"
            "<title>%s</title>\n%s\n<style>%s</style>\n</head><body>\n"
            "%s\n<main class=\"wr-page\">\n%s\n%s\n%s\n%s\n%s\n</main>\n"
            "</body></html>\n"
            % (esc(title), ui.style_tag(), _CSS,
               ui.shell("sources", league.id, week, leagues=leagues),
               mast, decay_html, cards_html, quiet_html, footer))


def render_failure(exc: BaseException, league_id: str = "",
                   week: Optional[int] = None) -> str:
    """One legible line for a failure before any section could be built."""
    rerun = ("rerun ./sources_page.sh%s once it parses"
             % (" --week %d" % week if week else ""))
    name = type(exc).__name__
    problem = getattr(exc, "problem", None)
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark",
                                                         None)
    flat = lambda t, n: ui.trim(t, n)  # noqa: E731
    if problem is not None or mark is not None:
        where = flat(getattr(mark, "name", "") or "the registry", 120)
        spot = ("" if mark is None
                else " (line %d, column %d)" % (mark.line + 1,
                                                mark.column + 1))
        return ("cannot render the receipts: %s is not valid YAML%s - %s. Fix "
                "that file by hand, or restore the built-in registry with "
                "./sources.sh, then %s."
                % (where, spot, flat(problem or name, 120), rerun))
    if isinstance(exc, OSError):
        target = getattr(exc, "filename", "")
        return ("cannot render the receipts: %s%s - restore that file, then "
                "%s." % (flat(getattr(exc, "strerror", None) or str(exc)
                              or name, 120),
                         " (%s)" % flat(target, 120) if target else "", rerun))
    return ("cannot render the receipts: %s: %s - this failed before any "
            "section could be built, so nothing was written. Check "
            "leagues/%s.yaml and data/sources.yaml, then %s."
            % (name, flat(str(exc).strip() or name, 160),
               flat(league_id or "<league>", 60), rerun))


def write_page(league_id: str = DEFAULT_LEAGUE, week: int = 1,
               out_path: Optional[str] = None, **kwargs) -> str:
    """Build and atomically write the page; returns the path written."""
    html = build_page(league_id, week, **kwargs)
    out = out_path or os.path.join(HERE, OUT_NAME)
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
        prog="python -m engine.sources_page",
        description="THE RECEIPTS: one card per source - weight, form, the "
                    "decay-blended hit rate, sample, streak, sparkline and "
                    "splits - plus the archive phase-out schedule. Prints "
                    "the output path as its last line.")
    ap.add_argument("--league", default=DEFAULT_LEAGUE,
                    help="which league's replacement level grades the record "
                         "(default: %s)" % DEFAULT_LEAGUE)
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--out", default=None,
                    help="output path (default: %s in the project root)"
                         % OUT_NAME)
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

    try:
        path = write_page(args.league, week, out_path=args.out)
    except KeyboardInterrupt:
        raise
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, str):
            print(ui.trim(code, 240))
            return 1
        return int(code or 0)
    except BaseException as exc:  # noqa: BLE001 - the diagnosis replaces it
        print(render_failure(exc, args.league, week))
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
