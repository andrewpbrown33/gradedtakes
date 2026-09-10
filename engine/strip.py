"""On-clock strip: one tiny always-glanceable HTML card, refreshed by the browser.

This is NOT a dashboard and NOT a browser extension. It is a single horizontal
strip - park a narrow browser window over the draft client and glance at it:
the pick to make (huge), one reason, the survival number, the nearest tier
cliff, how far away my next pick is, and a roster meter against this league's
positional demand. A meta refresh tag reloads it every 3 seconds, so whatever
keeps calling render() after each ingested pick keeps the window current with
zero moving parts on the browser side.

render() is a pure function of the draft state: it recomputes everything from
the arguments it is handed (reusing recommend.recommend(), the same engine the
terminal answers with) and its only side effect is the atomic tmp+replace
write of strip.html. It deliberately does NOT call injury_badges() or any
fetcher - nothing here may block on the network while someone is on the clock.
"""

import html as _html
import math
import os
from typing import Dict, List, Optional, Tuple

from .models import POSITIONS, fmt_pick
from .recommend import pct, recommend, tier_alerts

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(HERE, "strip.html")

REFRESH_SECONDS = 3

# Bench demand lands on the onesie-plus-skill positions; nobody benches K/DEF.
BENCH_ELIGIBLE = ("QB", "RB", "WR", "TE")


# --- roster meter ----------------------------------------------------------
def league_demand(league) -> Dict[str, int]:
    """Per-position draft demand for THIS league's roster shape.

    Starting demand (flex split evenly among eligibles, per starter_counts)
    plus the bench spots spread across QB/RB/WR/TE proportionally to that same
    starting demand, rounded up per position. Ceilings, not a quota: the
    rounding means the sum can exceed the round count by one or two, which is
    fine - the meter answers "am I behind at RB?", not "is my math exact".
    """
    starters = league.starter_counts()
    bench = float(league.bench_spots())
    skill = sum(starters.get(p, 0.0) for p in BENCH_ELIGIBLE)
    out = {}
    for pos in POSITIONS:
        want = starters.get(pos, 0.0)
        if bench > 0 and skill > 0 and pos in BENCH_ELIGIBLE:
            want += bench * starters.get(pos, 0.0) / skill
        out[pos] = int(math.ceil(want - 1e-9))
    return out


def roster_meter(state) -> List[Tuple[str, int, int]]:
    """(pos, have, demand) rows for MY roster vs league demand.

    Empty without a draft slot - there is no "my roster" to meter.
    """
    if not state.my_slot:
        return []
    counts = state.pos_counts(state.my_slot)
    demand = league_demand(state.league)
    return [(pos, counts.get(pos, 0), demand[pos])
            for pos in POSITIONS if demand[pos] > 0]


# --- html ------------------------------------------------------------------
def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


_CSS = """
  html, body { margin: 0; padding: 0; background: #10151b; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #e8edf2; font-variant-numeric: tabular-nums;
  }
  .strip {
    display: flex; align-items: center; gap: 14px;
    padding: 10px 14px; min-height: 64px;
    background: #1a212b; border-bottom: 2px solid #2a3442;
    white-space: nowrap; overflow-x: auto;
  }
  .ctx { display: flex; flex-direction: column; gap: 2px; min-width: 92px; }
  .ctx .now { font-size: 13px; font-weight: 700; color: #7dd3fc; }
  .ctx .next { font-size: 12px; color: #8b98a5; }
  .ctx .next.hot { color: #4ade80; font-weight: 700; }
  .pick { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .pick .who { font-size: 26px; font-weight: 800; line-height: 1.1; color: #4ade80; }
  .pick .who .meta { font-size: 13px; font-weight: 600; color: #8b98a5; margin-left: 6px; }
  .pick .why { font-size: 12px; color: #b9c4cf; }
  .chip {
    font-size: 12px; font-weight: 700; color: #10151b;
    background: #7dd3fc; border-radius: 4px; padding: 3px 8px;
  }
  .cliff {
    font-size: 12px; font-weight: 700; color: #fbbf24;
    border: 1px solid #fbbf24; border-radius: 4px; padding: 3px 8px;
    max-width: 340px; overflow: hidden; text-overflow: ellipsis;
  }
  .flag { font-size: 11px; font-weight: 700; color: #fbbf24; }
  .meter { display: flex; gap: 8px; margin-left: auto; }
  .cell { font-size: 12px; text-align: center; color: #8b98a5; }
  .cell b { display: block; font-size: 14px; color: #e8edf2; }
  .cell.short b { color: #fbbf24; }
  .cell.full b { color: #4ade80; }
  .waiting { font-size: 22px; font-weight: 800; color: #8b98a5; }
"""


def _page(body: str) -> str:
    return ("<!doctype html>\n<html><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta http-equiv=\"refresh\" content=\"%d\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>on the clock</title>\n"
            "<style>%s</style>\n"
            "</head><body>\n%s\n</body></html>\n"
            % (REFRESH_SECONDS, _CSS, body))


def _meter_html(meter) -> str:
    cells = []
    for pos, have, want in meter:
        cls = "cell short" if have < want else "cell full"
        cells.append("<span class=\"%s\"><b>%d/%d</b>%s</span>"
                     % (cls, have, want, _esc(pos)))
    return "<div class=\"meter\">%s</div>" % "".join(cells)


def _strip_html(state, tree, intel, exposure) -> str:
    current = state.current_pick()
    recs = recommend(state, tree, top_n=1, intel=intel)
    if not recs:
        return ("<div class=\"strip\"><span class=\"waiting\">"
                "draft complete - no players left to recommend</span>%s</div>"
                % _meter_html(roster_meter(state)))

    top = recs[0]
    p = top.player

    # Pick context: where the draft is, and how far away I am.
    nxt = state.next_my_pick()
    if nxt is None:
        next_txt, hot = "no picks left", False
    elif nxt == current:
        next_txt, hot = "ON THE CLOCK", True
    else:
        next_txt, hot = "mine in %d (%s)" % (nxt - current,
                                             fmt_pick(nxt, state.teams)), False
    ctx = ("<div class=\"ctx\"><span class=\"now\">PICK %d (%s)</span>"
           "<span class=\"next%s\">%s</span></div>"
           % (current, _esc(fmt_pick(current, state.teams)),
              " hot" if hot else "", _esc(next_txt)))

    # The pick itself: huge name, one reason. Exposure is flag-only and
    # positive-only (engine/exposure) - a missing flag renders nothing.
    reason = top.reasons[0] if top.reasons else "best available"
    flag = ""
    if exposure is not None and exposure.available:
        held = exposure.flag(p.key)
        if held:
            flag = ("<span class=\"flag\">also yours in %s</span>"
                    % _esc(", ".join(held)))
    meta = p.pos + ("-" + p.team if p.team else "")
    pick = ("<div class=\"pick\"><span class=\"who\">%s"
            "<span class=\"meta\">%s</span></span>"
            "<span class=\"why\">%s%s</span></div>"
            % (_esc(p.name), _esc(meta), _esc(reason),
               (" &nbsp;" + flag) if flag else ""))

    surv = "<span class=\"chip\">%s survives</span>" % _esc(pct(top.survival))

    # Nearest tier cliff, if any. tier_alerts already filters to the ones that
    # cost something before my next pick; the strip has room for exactly one.
    cliffs = tier_alerts(state)
    cliff = ("<span class=\"cliff\">CLIFF %s</span>" % _esc(cliffs[0])
             if cliffs else "")

    return ("<div class=\"strip\">%s%s%s%s%s</div>"
            % (ctx, pick, surv, cliff, _meter_html(roster_meter(state))))


# --- entry point -----------------------------------------------------------
def render(state, tree=None, intel=None, exposure=None, matcher=None,
           path: Optional[str] = None) -> str:
    """Render the on-clock strip for this state and atomically write it.

    Returns the path written (strip.html in the project root by default).
    `matcher` is accepted for signature parity with on_clock_block() and
    future rival-branch chips; the strip does not use it yet. Without a draft
    slot there is nothing to answer, so the card says so instead of guessing.
    """
    if state.my_slot:
        body = _strip_html(state, tree, intel, exposure)
    else:
        body = ("<div class=\"strip\"><span class=\"waiting\">"
                "waiting for draft - no draft slot set</span></div>")

    out = path or DEFAULT_PATH
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(_page(body))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)
    return out
