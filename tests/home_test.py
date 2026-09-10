#!/usr/bin/env python3
"""Acceptance test: the landing page, v3 (engine/home.py).

WHAT THIS SUITE PROTECTS. The landing page is the surface the user opens
every day of the week and acts from - on a phone before kickoff, on a
desktop with the inbox beside the rosters. Eight things can silently ruin
it, and none of them shows up as an exception:

  [1] A SIGNAL THAT DOES NOT FIRE. A starter on bye whose row carries no bye
      mark is worse than no page at all. Every signal is asserted against a
      planted fact, and asserted ABSENT when its fact is absent.

  [2] A CLEAN BILL NOBODY EARNED. "Nothing needs you" is a claim about
      checks that RAN. Dead feeds are planted and the page must say what it
      could not check instead of reporting the silence as calm.

  [3] A VERB THAT GOES NOWHERE, OR TO THE WRONG PLACE. Every inbox item
      carries a verb; with `host:` configured it opens the host page for
      THAT league in a new tab, without it the item still renders and says
      which key is missing. A link built from a guessed id is a link to
      someone else's team.

  [4] AN ITEM ON THE WRONG SHELF. The inbox is three shelves by urgency -
      Do now / Before lock / This week. A bye starter filed under "This
      week" is a missed lock. Every kind is planted and its shelf asserted.

  [5] A SIDEBAR THAT IS NOT ONE, A STACK THAT SCROLLS SIDEWAYS. On a wide
      screen the inbox is a sticky right rail (asserted against the emitted
      CSS at the 1000px rule); on a phone it stacks on top, three rows then
      a native disclosure, never a horizontal scroller.

  [6] A DECISION OFFERED AFTER IT IS MADE. Once a game has kicked off the
      row is muted, the item is muted and its verb becomes a lock. Asserted
      with a fixture schedule and an injected clock on both sides of it.

  [7] A PLAYER CARD THAT KNOWS ONE LEAGUE. With two leagues, the card names
      every league, where he sits there, the room's verdict there, and the
      verbs for THAT league's host; with one league it says nothing at all.

  [8] A RENDER THAT WRITES. Opening the page must leave the %owned baseline
      (data/cache/espn-owned-snapshot.json) byte-identical - hashed before
      and after a double render - and the module must never pass
      advance=True.

Plus the contracts every page shares: the v3 design system only (no hex,
no artwork, none of the retired green/red hexes anywhere in the output),
the type scale floor (nothing below 11px), the phone (no fixed width past
390px outside a scroll box), self-containment beyond the host deep links,
escaping of everything that came from a feed - and the ui bridge: every
v4 component is reached through getattr with a fallback, and the page
renders both with and without them.

HERMETIC. Every check drives the PURE half of engine/home.py with fixture
snapshots. Nothing here fetches, and nothing here writes anywhere except a
tempdir. The two real league yamls are opened READ-ONLY to prove the page
renders for the leagues that actually exist and that their `host:` ids
reach the links.

    .venv/bin/python tests/home_test.py
"""

import hashlib
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import board as board_mod                        # noqa: E402
from engine import home, ui                                  # noqa: E402
from engine.models import LeagueConfig, host_of              # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET_TZ = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 - no tz database: naive fixtures still work
    ET_TZ = None

FAILURES = []
CHECKS = [0]

VIEWPORT = 390
TOUCH_FLOOR = 44
VERB_MIN_W = 88
TYPE_FLOOR = 11
HOSTILE = "<script>alert(\"xss\")</script> & 'q' </span> --> é"

# The retired traffic-light palette. None of these may survive in any
# emitted page - v3 encodes verdicts by weight, not by hue.
FORBIDDEN = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80", "#f87171")

# The only hosts a page may point at, beyond itself: the two platforms the
# verbs open, the shell's local Model Settings panel, and (should the
# fonts ever move back out of the file) the font CDN.
ALLOWED_HOSTS = ("fantasy.espn.com", "football.fantasysports.yahoo.com",
                 "127.0.0.1:8787", "fonts.googleapis.com", "fonts.gstatic.com")

OWNED_SNAP = os.path.join(HERE, "data", "cache", "espn-owned-snapshot.json")


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET_TZ) if ET_TZ else datetime(y, mo, d, h, mi)


def _iso(y, mo, d, h=0, mi=0):
    return _dt(y, mo, d, h, mi).isoformat()


# Fixture week: Thu 9/10 night, a Sunday slate, Sun night, Mon night.
THU = _iso(2026, 9, 10, 20, 15)
SUN_EARLY = _iso(2026, 9, 13, 13, 0)
SUN_LATE = _iso(2026, 9, 13, 16, 25)
SUN_NIGHT = _iso(2026, 9, 13, 20, 20)
MON = _iso(2026, 9, 14, 20, 15)
KICKOFFS = [THU] + [SUN_EARLY] * 8 + [SUN_LATE] * 4 + [SUN_NIGHT, MON]
NOW = _dt(2026, 9, 9, 12, 0)          # Wednesday noon, before the first lock
FRIDAY = _dt(2026, 9, 11, 9, 0)       # after Thursday's kick, before Sunday


# --- fixtures ---------------------------------------------------------------

def row(name, pos="WR", team="ATL", group="STARTING", slot="WR", **kw):
    """A roster row in the shape gather_league() produces."""
    base = {
        "name": name, "pos": pos, "team": team,
        "key": "%s|%s" % (name.lower(), pos),
        "slot": slot, "group": group, "open": False,
        "meta": "%s vs XXX" % team, "opponent": "XXX", "home": True,
        "proj": 12.5, "proj_source": "espn", "actual": None,
        "status": "", "bye": False,
        "lean": "START" if group == "STARTING" else "SIT",
        "pct": 100 if group == "STARTING" else 0,
        "agreement": "UNANIMOUS", "top_note": "", "level": 0,
        "split_weight": 0,
        "voices": [("War Room Engine", "start", ""),
                   ("ESPN Projections", "start", "")],
        "quotes": [], "hot_backers": [], "matchup": None,
        "kickoff_iso": SUN_EARLY, "kickoff": "", "locked": False,
        "own_pct": None, "start_pct": None, "own_known": False,
        "trend_adds": None,
        "anchor": "p-fix-1",
    }
    base.update(kw)
    return base


def open_slot(slot="TE", anchor="p-fix-9"):
    return {"name": home.OPEN_SLOT, "pos": "", "team": "", "key": "",
            "slot": slot, "group": "STARTING", "open": True, "meta": "",
            "opponent": "", "home": None, "proj": None, "proj_source": "",
            "actual": None, "status": "", "bye": None,
            "lean": None, "pct": None, "agreement": "", "top_note": "",
            "level": 0, "split_weight": 0, "voices": [], "quotes": [],
            "hot_backers": [], "matchup": None, "kickoff_iso": "",
            "kickoff": "", "locked": False, "own_pct": None,
            "start_pct": None, "own_known": False, "trend_adds": None,
            "anchor": anchor}


def snapshot(rows_starting=(), rows_bench=(), **kw):
    snap = {
        "id": "fix-league", "name": "Fixture League", "week": 4,
        "teams": 10, "scoring": "ppr",
        "record": "not tracked (no standings feed connected)",
        "platform": "espn", "host": {"league_id": "111", "team_id": "7"},
        "error": None, "error_text": "", "degraded": [], "unchecked": [],
        "notes": [], "unresolved": [],
        "starters": list(rows_starting), "bench": list(rows_bench),
        "kickoffs": list(KICKOFFS),
        "scoreboard": [
            {"source": "engine", "name": "War Room Engine", "type": "feed",
             "weight": 17, "state": "NO-DATA", "state_reason": "empty ledger"},
            {"source": "the-favorites", "name": "The Favorites",
             "type": "youtube", "weight": 17, "state": "NO-DATA",
             "state_reason": "empty ledger"},
        ],
        "waivers": {"claims": [], "notes": [], "pool": 180, "mode": "faab",
                    "rivals_known": True},
        "board_href": "board-fix-league-week4.html", "board_exists": True,
    }
    snap.update(kw)
    return snap


def clean_snapshot():
    """A team with nothing wrong with it: healthy, playing, agreed on."""
    return snapshot(
        [row("Alpha Back", pos="RB", slot="RB", kickoff_iso=THU),
         row("Bravo Wideout", pos="WR", slot="WR", anchor="p-fix-2")],
        [row("Charlie Bench", pos="WR", group="BENCH", slot="",
             anchor="p-fix-3")])


def other_snapshot(**kw):
    """A second league, on Yahoo, with its own host ids."""
    s = clean_snapshot()
    s.update({"id": "other", "name": "Other League", "platform": "yahoo",
              "host": {"league_id": "428", "team_id": "5"},
              "board_href": "board-other-week4.html"})
    for j, r in enumerate(s["starters"] + s["bench"], start=1):
        r["anchor"] = home.anchor_id("other", j)
    s.update(kw)
    return s


def page(snaps, week=4, now=None, exposure=None):
    return home.build_page(week, snapshots=snaps, stamp="FIXED STAMP",
                           now=now or NOW, exposure=exposure)


def titles(html):
    return re.findall(r'title="([^"]*)"', html) + re.findall(
        r"<title>(.*?)</title>", html, flags=re.S)


def icon_names_in(html):
    return set(re.findall(r'class="wr-icon wr-icon-([a-z-]+)', html))


def _balanced(html, start, tag="div"):
    """The <tag ...>...</tag> element opening at `start`, by tag depth -
    the rows and the inbox nest their own kind, so a non-greedy regex
    would stop at the first inner close."""
    depth = 0
    for m in re.finditer(r"<%s\b|</%s>" % (tag, tag), html[start:]):
        depth += 1 if not m.group(0).startswith("</") else -1
        if depth == 0:
            return html[start:start + m.end()]
    return html[start:]


def rows_in(html):
    """Every roster row (<div class="home-r ...">) as its own string."""
    return [_balanced(html, m.start())
            for m in re.finditer(r'<div class="home-r(?: [^"]*)?"', html)]


def row_html(html, player):
    """The one roster row holding this player, isolated."""
    key = 'data-player="%s"' % ui.esc(player.lower())
    return next((r for r in rows_in(html) if key in r.split(">", 1)[0]), "")


def inbox_html(html):
    i = html.find('<section class="wr-card home-attention"')
    return _balanced(html, i, "section") if i >= 0 else ""


def shelf_html(html, key):
    i = html.find('<section class="home-inb-g home-inb-g-%s">' % key)
    return _balanced(html, i, "section") if i >= 0 else ""


def main_html(html):
    m = re.search(r"<main class=\"wr-page\">.*?</main>", html, flags=re.S)
    return m.group(0) if m else ""


def css_block(css, selector):
    """The declarations of the rule whose selector list IS `selector` -
    anchored to the start of its line, so `.home-r3` never matches the
    tail of `.home-r-locked .home-r3`."""
    m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


@contextmanager
def without_ui(*names):
    """Hide v4 components from engine/ui for the duration - the page must
    render on its fallbacks exactly as it would before they landed."""
    saved = {}
    for n in names:
        if hasattr(ui, n):
            saved[n] = getattr(ui, n)
            setattr(ui, n, None)
    try:
        yield
    finally:
        for n, v in saved.items():
            setattr(ui, n, v)


# --- [1] it renders, with the shell, for the leagues that exist -------------

def test_renders():
    print("\n[1] the page renders with the shell - for both real leagues and "
          "for none")
    ids = home.league_ids()
    check("espn-1" in ids and "yahoo-main" in ids,
          "league_ids() discovers both configured leagues: %s" % ", ".join(ids))

    snaps = []
    for lid in ("espn-1", "yahoo-main"):
        cfg = LeagueConfig.load(os.path.join(HERE, "leagues", "%s.yaml" % lid))
        snaps.append(snapshot(
            [row("Starter %s" % lid, pos="RB", slot="RB", bye=True,
                 kickoff_iso="")],
            [row("Bench %s" % lid, pos="WR", group="BENCH", slot="")],
            id=cfg.id, name=cfg.name, teams=cfg.teams,
            platform=cfg.platform, host=cfg.host,
            scoring=cfg.scoring_label(),
            board_href="board-%s-week4.html" % cfg.id))
    html = page(snaps)

    check('<header class="wr-nav">' in html and html.index('class="wr-nav"')
          < html.index('<main class="wr-page">'),
          "ui.shell() is the first thing in <body>, before the page's <main>")
    check('href="home.html" aria-current="page"' in html,
          "the shell marks Home as the current page")
    check('href="home.html#league-espn-1"' in html
          and 'href="home.html#league-yahoo-main"' in html,
          "the shell's league switcher targets #league-<id> on this page")
    check("<style>" in html and html.index("<style>") < html.index("</head>"),
          "ui.style_tag() is in <head>")
    check('class="wr-kicker"' in html and "wr-display" in html,
          "the header uses the design system's kicker and display face")

    for lid, cfg_name in (("espn-1", "The Original 8"),
                          ("yahoo-main", "Kid's Table")):
        check('id="league-%s"' % lid in html,
              "a card per configured league - %s has id=league-%s" % (lid, lid))
        check(ui.esc(cfg_name) in html or cfg_name in html,
              "%s's real league name is printed" % lid)
        check('href="board-%s-week4.html"' % lid in html,
              "%s links to its own board for this week" % lid)
    check(("fantasy.espn.com/football/team?leagueId=284298483&amp;teamId=8"
           "&amp;seasonId=2026") in html,
          "the real ESPN host ids (leagues/espn-1.yaml host:) reach the "
          "team link")
    check("football.fantasysports.yahoo.com/f1/428472/5" in html,
          "the real Yahoo host ids (leagues/yahoo-main.yaml host:) reach the "
          "team link")
    check("full PPR" in html,
          "the scoring is spelled for a human ('full PPR'), not 'ppr'")
    check("<h1" in html and "Week 4" in html and "week 4" in html,
          "the page states the week it is about")
    check("Wed Sep 9" in html,
          "the header line carries today's date (from the injected now)")

    empty = page([])
    check("No leagues configured" in empty and "nothing is being assumed"
          in empty,
          "zero leagues renders a stated absence, not a blank page")
    check("first lock unknown — no league could be read" in empty,
          "...and the lock line says why it knows nothing")


# --- [2] the signals fire, and only when their fact is true -----------------

def test_signals():
    print("\n[2] every mark fires on its fact - and stays silent without it")

    bye = row("Bye Guy", pos="RB", slot="RB", bye=True, kickoff_iso="")
    calm = row("Calm Guy", pos="WR", slot="WR", anchor="p-fix-2")
    html = page([snapshot([bye, calm])])
    b_html, c_html = row_html(html, "Bye Guy"), row_html(html, "Calm Guy")
    check(len(rows_in(html)) == 2 and b_html and c_html
          and "wr-chip-start" in c_html and "Calm Guy" not in b_html,
          "each roster row is isolated as its own element, so an 'absent "
          "mark' check below is a real check and not an empty string")
    check('class="home-st' in b_html and ">BYE<" in b_html,
          "a player on bye carries the BYE status pill")
    check('class="home-st' not in c_html,
          "...and a player with a game carries no pill - it is not decoration")
    check(any("no game this week" in t for t in titles(b_html)),
          "the pill carries a title saying what it means")
    check("home-r-flag" in b_html and "home-r-flag" not in c_html,
          "a starter on bye carries the row flag (the gold rule); a calm "
          "row does not")
    check("no game" in b_html.split("home-r3-mid")[-1].split("wr-r3-mid")[-1]
          and "home-oppw" not in b_html,
          "...and his middle column says 'no game' with no opponent chip")

    split = row("Split Guy", pos="RB", slot="RB", level=board_mod.LVL_SPLIT,
                agreement="MAJORITY", split_weight=33, pct=67,
                voices=[("War Room Engine", "start", ""),
                        ("Boris Chen Tiers", "sit", "")])
    html = page([snapshot([split, calm])])
    s_html = row_html(html, "Split Guy")
    check("wr-icon-dissent" in s_html,
          "a split decision carries the dissent mark")
    check("wr-icon-dissent" not in row_html(html, "Calm Guy"),
          "...and a unanimous row does not")
    check(any("both ways" in t for t in titles(s_html)),
          "the dissent mark says the voices point both ways")

    top = row("Top Guy", pos="RB", slot="RB", level=board_mod.LVL_TOP,
              top_note="top-weighted The Favorites says sit - disagrees "
                       "with the weighted verdict")
    t_html = row_html(page([snapshot([top])]), "Top Guy")
    check("wr-icon-dissent" in t_html and
          any("top-weighted" in t for t in titles(t_html)),
          "a TOP SOURCE DISSENT reuses the dissent mark with the board's "
          "own wording")

    hurt = row("Hurt Guy", pos="WR", slot="WR", status="Questionable")
    out = row("Out Guy", pos="WR", slot="WR", status="Out", anchor="p-fix-5")
    pup = row("Pup Guy", pos="TE", group="BENCH", slot="", status="PUP",
              anchor="p-fix-6")
    html = page([snapshot([hurt, out, calm], [pup])])
    h_html, o_html = row_html(html, "Hurt Guy"), row_html(html, "Out Guy")
    check('class="home-st home-st-warn"' in h_html and ">Q<" in h_html,
          "a Questionable status is a 'Q' pill at warning weight")
    check(any("injury status filed" in t for t in titles(h_html))
          and any("Questionable" in t for t in titles(h_html)),
          "...whose title names the filed word")
    check('class="home-st' not in row_html(html, "Calm Guy"),
          "...and a player with no filed status shows none - absence of a "
          "report is not a clean bill, and not a badge either")
    check('class="home-st home-st-alarm"' in o_html
          and (">O<" in o_html or ">OUT<" in o_html),
          "an OUT-class status draws its pill at full ink weight")
    check('class="home-st home-st-alarm"' in row_html(html, "Pup Guy")
          and ">PUP<" in row_html(html, "Pup Guy"),
          "a status the design system does not badge (PUP) still gets a "
          "pill from the page's fallback - the word is never dropped")

    quoted = row("Quoted Guy", pos="WR", slot="WR",
                 quotes=[("The Favorites", "I am starting him everywhere")],
                 voices=[("The Favorites", "start",
                          "I am starting him everywhere")])
    html = page([snapshot([quoted, calm])])
    q_html = row_html(html, "Quoted Guy")
    check('class="home-dot-w"' in q_html
          and any("own words" in t for t in titles(q_html)),
          "a creator call in the creator's own words shows the news dot, "
          "titled")
    check('class="home-dot-w"' not in row_html(html, "Calm Guy"),
          "...and a row with no creator call does not")
    check("I am starting him everywhere" in q_html,
          "...and the card quotes him")

    hot = row("Hot Guy", pos="WR", slot="WR", hot_backers=["The Favorites"])
    html = page([snapshot([hot, calm])])
    check("wr-icon-hot-streak" in row_html(html, "Hot Guy"),
          "a hot source backing the lean shows the hot-streak mark")
    check("wr-icon-hot-streak" not in row_html(html, "Calm Guy"),
          "...and nothing shows it when no source is running hot")

    locked = row("Locked Guy", pos="WR", slot="WR", locked=True)
    html = page([snapshot([locked, calm])])
    check("wr-icon-locked" in row_html(html, "Locked Guy"),
          "a kicked-off game shows the locked mark")
    check("wr-icon-locked" not in row_html(html, "Calm Guy"),
          "...and a game still to come does not")

    # the verdict chip and the matchup meter are columns, not marks
    silent = row("Silent Guy", pos="WR", slot="WR", lean=None, pct=None,
                 voices=[], anchor="p-fix-7")
    sitter = row("Sit Guy", pos="WR", group="BENCH", slot="", lean="SIT",
                 pct=15, anchor="p-fix-8")
    html = page([snapshot([calm, silent], [sitter])])
    check("wr-chip-start" in row_html(html, "Calm Guy")
          and "wr-chip-sit" in row_html(html, "Sit Guy"),
          "the room's verdict is a chip in its own column - gold fill for "
          "START, ghost for SIT")
    check("wr-chip-unfiled" in row_html(html, "Silent Guy")
          and "silence, not agreement" in row_html(html, "Silent Guy"),
          "a player no voice voted on gets the unfiled chip and the words "
          "'silence, not agreement' - never a guessed verdict")

    avoid = row("Avoid Guy", pos="WR", slot="WR",
                matchup={"pa_grade": "AVOID", "opponent": "SEA", "pos": "WR",
                         "pa_per_game": 26.3, "pa_rank": 29, "pa_of": 32,
                         "basis": "2025 season, 17 games",
                         "evidence": "SEA allowed 26.3 ...", "reason": ""},
                opponent="SEA", home=False, meta="ATL @ SEA")
    smash = row("Smash Guy", pos="TE", slot="TE", anchor="p-fix-2",
                matchup={"pa_grade": "SMASH", "opponent": "PIT", "pos": "TE",
                         "pa_per_game": 16.6, "pa_rank": 3, "pa_of": 32,
                         "basis": "2025 season, 17 games",
                         "evidence": "PIT allowed 16.6 ...", "reason": ""},
                opponent="PIT", home=True, meta="ATL vs PIT")
    none = row("None Guy", pos="WR", slot="WR", anchor="p-fix-3",
               matchup={"pa_grade": None, "reason": "on bye"})
    html = page([snapshot([avoid, smash, none,
                           row("Calm Guy", pos="WR", slot="WR",
                               anchor="p-fix-4")])])
    a_html, s_html = row_html(html, "Avoid Guy"), row_html(html, "Smash Guy")
    check("wr-meter-lo" in a_html and 'title="matchup: AVOID vs SEA' in a_html,
          "an AVOID matchup renders the meter at one segment with the grade "
          "in its title")
    check("wr-meter-hi" in s_html and 'title="matchup: SMASH vs PIT' in s_html,
          "a SMASH matchup fills the meter, grade in the title")
    check("4th-stingiest of 32" in a_html and "2025 season" in a_html,
          "...and the title restates the evidence WITH its basis")
    check('class="home-oppw"' in a_html and "SEA" in a_html.split("home-oppw")[1]
          and ("@" in a_html.split("home-oppw")[1].split("</span></span>")[0]),
          "the opponent chip reads '@ SEA' for an away game")
    check("vs" in s_html.split("home-oppw")[1][:200] and "PIT" in s_html,
          "...and 'vs PIT' at home")
    lo = a_html.split("home-oppw")[1][:400]
    hi = s_html.split("home-oppw")[1][:400]
    check(("-avoid" in lo or "-lo" in lo) and ("-smash" in hi or "-hi" in hi),
          "the opponent chip takes the matchup's tone - avoid vs smash")
    check("wr-meter-none" in row_html(html, "None Guy")
          and "not graded — on bye" in row_html(html, "None Guy"),
          "an ungraded matchup is five hollow segments and the reason - "
          "never an invented grade")
    check("wr-meter-none" in row_html(html, "Calm Guy"),
          "no matchup dict at all is also 'not graded'")

    # the contradiction that flags a row
    starter_sit = row("Wrong Starter", pos="RB", slot="RB", lean="SIT", pct=20)
    bench_start = row("Wrong Bench", pos="RB", group="BENCH", slot="",
                      lean="START", pct=80, anchor="p-fix-2")
    html = page([snapshot([starter_sit], [bench_start, row(
        "Right Bench", pos="WR", group="BENCH", slot="", anchor="p-fix-3")])])
    check("home-r-split" in row_html(html, "Wrong Starter")
          and "home-r-split" in row_html(html, "Wrong Bench"),
          "a starter the room wants benched, and a bench player it wants "
          "started, both carry the split flag")
    check("home-r-flag" not in row_html(html, "Right Bench"),
          "...and a bench player the room agrees to bench stays unflagged")
    check("he is in your lineup" in row_html(html, "Wrong Starter"),
          "the contradiction is stated in the chip's title")
    check(home.contradicts_slot(starter_sit) and
          home.contradicts_slot(bench_start) and
          not home.contradicts_slot(row("x")),
          "contradicts_slot() is the single definition the flag, the chip "
          "title and the inbox all read")
    check('data-unanimous="1"' in row_html(html, "Right Bench")
          and 'data-unanimous="1"' not in row_html(html, "Wrong Bench")
          and 'data-unanimous="1"' not in row_html(html, "Wrong Starter"),
          "a row with nothing to say is marked data-unanimous for the "
          "preferences layer's quiet mode; any flagged row is not")


# --- [3] the inbox: facts, verbs, links ------------------------------------

def test_inbox():
    print("\n[3] the inbox - the planted problem, the verb that fixes it, and "
          "the honest all-clear")

    clean = clean_snapshot()
    html = page([clean])
    check("Nothing needs you — 2 starters checked across 1 league" in html,
          "a clean team says 'nothing needs you' and states HOW MUCH was "
          "checked, so the all-clear is auditable")
    check('id="home-inbox"' in html
          and html.index('id="home-inbox"') < html.index('id="league-fix-league"'),
          "the inbox precedes the league cards in the document, so a phone "
          "reads it first")

    planted = clean_snapshot()
    planted["starters"][0]["bye"] = True
    items, caveats = home.attention_items([planted])
    hit = [i for i in items if "on BYE" in i["text"]]
    check(bool(hit) and hit[0]["severity"] == "bad",
          "a starter on bye reaches the inbox as a critical")
    check(hit and hit[0]["kind"] == "bye" and hit[0]["verb"] == "Swap him out on ESPN"
          and hit[0]["short_verb"] == "Swap",
          "...with the verb for that kind, naming the platform, and a short "
          "verb for the button")
    check(hit and hit[0]["href"] ==
          "https://fantasy.espn.com/football/team?leagueId=111&teamId=7&seasonId=2026",
          "...and the host link is THIS league's ESPN team page for this season")
    check(hit and hit[0]["subject"] == "Alpha Back"
          and hit[0]["short"] == "on BYE, starting",
          "...and a one-line form: the player, and a few words")
    html = page([planted])
    inbox = inbox_html(html)
    check("Alpha Back" in inbox and "on BYE, starting" in inbox
          and "Nothing needs you" not in html,
          "the planted problem is named on the page and the all-clear is gone")
    check(('<a class="home-act" href="https://fantasy.espn.com/football/team?'
           'leagueId=111&amp;teamId=7&amp;seasonId=2026" target="_blank" '
           'rel="noopener noreferrer" title="Swap him out on ESPN">Swap</a>') in inbox,
          "the verb is a short button that opens the host page in a new tab, "
          "escaped as an attribute, the full verb in its title")
    check('href="#p-fix-1"' in inbox,
          "the fact itself still links to the player's row on this page")
    check("wr-icon-bye" in inbox,
          "the item carries the bye mark")
    check("Alpha Back is on BYE and is in your starting lineup." in inbox,
          "...and the full sentence rides in the item's title for hover and "
          "screen readers")

    yahoo = clean_snapshot()
    yahoo.update({"id": "kid", "name": "Kid League", "platform": "yahoo",
                  "host": {"league_id": "428", "team_id": "5"}})
    yahoo["starters"][0]["status"] = "Out"
    items, _ = home.attention_items([yahoo])
    hit = [i for i in items if i["kind"] == "out"]
    check(hit and hit[0]["href"] == "https://football.fantasysports.yahoo.com/f1/428/5"
          and hit[0]["verb"] == "Replace him on Yahoo",
          "a Yahoo league's verb opens the Yahoo team page")

    nohost = clean_snapshot()
    nohost["host"] = None
    nohost["starters"][0]["bye"] = True
    items, _ = home.attention_items([nohost])
    hit = [i for i in items if i["kind"] == "bye"]
    check(hit and not hit[0]["href"] and hit[0]["verb"] == "Swap him out",
          "without host: the item still renders, verb intact, with no link")
    check(hit and "add host: {league_id, team_id} to leagues/fix-league.yaml"
          in hit[0]["host_note"],
          "...and the note names the exact key that would add one")
    html = page([nohost])
    check("home-act-none" in inbox_html(html) and "fantasy.espn.com" not in html
          and "add host: {league_id, team_id}" in inbox_html(html),
          "...rendered as a ghost button carrying the note, and no ESPN URL "
          "is fabricated anywhere")

    odd = clean_snapshot()
    odd.update({"platform": "sleeper", "host": {"league_id": "1", "team_id": "2"}})
    odd["starters"][0]["bye"] = True
    items, _ = home.attention_items([odd])
    check(items and not items[0]["href"]
          and "no deep-link recipe for the sleeper platform" in items[0]["host_note"],
          "a platform without a recipe gets no link and says so - ids alone "
          "never conjure a URL")

    cases = [
        ({"status": "Out"}, "bad", "OUT", "Replace him"),
        ({"status": "Questionable"}, "warn", "Questionable", "Check his status"),
        ({"proj": 0.0}, "bad", "projects 0.0", "Replace him"),
        ({"proj": None}, "warn", "no projection filed", "Verify him"),
        ({"matchup": {"pa_grade": "AVOID", "opponent": "SEA", "pos": "WR",
                      "pa_per_game": 26.3, "pa_rank": 29, "pa_of": 32,
                      "basis": "2025 season, 17 games", "evidence": "e",
                      "reason": ""}}, "warn", "AVOID matchup", "Rethink the slot"),
    ]
    for patch, severity, phrase, verb in cases:
        snap = clean_snapshot()
        snap["starters"][0].update(patch)
        items, _ = home.attention_items([snap])
        hit = [i for i in items if phrase in i["text"]]
        check(bool(hit) and hit[0]["severity"] == severity,
              "a starter with %s reaches the inbox at severity %s"
              % (list(patch)[0] if len(patch) == 1 else "a bad matchup",
                 severity))
        check(hit and hit[0]["verb"].startswith(verb) and hit[0]["href"],
              "...with the verb '%s' and a host link" % verb)

    snap = clean_snapshot()
    snap["starters"].append(open_slot("TE"))
    items, _ = home.attention_items([snap])
    hit = [i for i in items if "The TE slot is empty" in i["text"]]
    check(hit and hit[0]["severity"] == "bad" and hit[0]["verb"] == "Fill the slot on ESPN",
          "an open starting slot is a critical with its own verb")
    check(not any("no projection filed" in i["text"] for i in items),
          "...and it is NOT also reported as a missing projection")

    light = clean_snapshot()
    light["starters"][0].update({"level": board_mod.LVL_SPLIT,
                                 "agreement": "LONE-DISSENT",
                                 "split_weight": 17, "pct": 83})
    items, _ = home.attention_items([light])
    check(not any(i["kind"] == "split" for i in items),
          "a lone dissent at 17%% of the weight does NOT claim to need you "
          "(floor is %d%%)" % home.SPLIT_ATTENTION)
    heavy = clean_snapshot()
    heavy["starters"][0].update({"level": board_mod.LVL_SPLIT,
                                 "agreement": "MAJORITY",
                                 "split_weight": 33, "pct": 67})
    items, _ = home.attention_items([heavy])
    hit = [i for i in items if i["kind"] == "split"]
    check(hit and "genuine start/sit split" in hit[0]["text"]
          and hit[0]["verb"] == "Set your lineup on ESPN",
          "a third of the room's weight on the losing side does, with the "
          "lineup verb")
    contradicting = clean_snapshot()
    contradicting["starters"][0].update({"level": board_mod.LVL_SPLIT,
                                         "lean": "SIT", "pct": 20,
                                         "split_weight": 20})
    items, _ = home.attention_items([contradicting])
    check(any("in your lineup but the room leans sit" in i["text"]
              for i in items),
          "a light split that CONTRADICTS the lineup still earns the inbox")

    claimed = clean_snapshot()
    claimed["waivers"] = {"claims": [{"name": "Woody Marks", "pos": "RB",
                                      "team": "HOU", "score": 12.3,
                                      "band": "FAAB 9-15%",
                                      "detail": "score 12.3: ROS +18.2 vs RB bar"}],
                          "notes": [], "pool": 200, "mode": "faab",
                          "rivals_known": True}
    items, _ = home.attention_items([claimed])
    hit = [i for i in items if i["kind"] == "claim"]
    check(hit and "Woody Marks (RB, HOU) is worth a claim — FAAB 9-15%" in hit[0]["text"],
          "a free agent the wire rates worth a claim reaches the inbox with "
          "the wire's own band")
    check(hit and hit[0]["href"] == "https://fantasy.espn.com/football/players/add?leagueId=111"
          and hit[0]["verb"] == "Claim him on ESPN" and hit[0]["short_verb"] == "Claim",
          "...and its verb opens the host's WAIVER page, not the team page")
    html = page([claimed])
    check("wr-icon-waiver-add" in inbox_html(html)
          and "1 free agent worth a claim" in html,
          "the claim carries the add mark, and the league card points at it")

    blind = clean_snapshot()
    blind["waivers"] = dict(claimed["waivers"], rivals_known=False)
    items, _ = home.attention_items([blind])
    html = page([blind])
    check(not any(i["kind"] == "claim" for i in items)
          and "Woody Marks" not in inbox_html(html),
          "with the other teams' rosters UNKNOWN no claim reaches the inbox - "
          "the pool cannot tell a free agent from a rostered star")
    check("no claim is surfaced" in html
          and "cannot tell a free agent from a rostered star" in html,
          "...and the league card says exactly why")

    snap = clean_snapshot()
    snap["unresolved"] = ["Some Rookie"]
    items, _ = home.attention_items([snap])
    hit = [i for i in items if "matched no player" in i["text"]]
    check(hit and hit[0]["verb"] == "Open your roster on ESPN",
          "a roster name that matched nothing is surfaced with a roster verb")
    check("listed nowhere above, not dropped silently" in page([snap]),
          "...and the league card says so too")

    a, b = clean_snapshot(), other_snapshot()
    b["starters"][0]["status"] = "Doubtful"
    a["starters"][1]["bye"] = True
    items, _ = home.attention_items([a, b])
    check(len(items) == 2 and {i["league"] for i in items} ==
          {"Fixture League", "Other League"},
          "the inbox spans every league and names which team each item is")
    check(items[0]["severity"] == "bad",
          "criticals sort above warnings, so the cap can never hide one")

    # the overflow disclosure: every item stays on the page
    many = clean_snapshot()
    many["bench"] = [row("Bench %02d" % i, pos="WR", group="BENCH", slot="",
                         lean="START", pct=80, level=board_mod.LVL_SPLIT,
                         split_weight=30, anchor="p-fix-%d" % (10 + i))
                     for i in range(home.ATTENTION_MAX + 3)]
    items, _ = home.attention_items([many])
    html = page([many])
    inbox = inbox_html(html)
    check(len(items) == home.ATTENTION_MAX + 3
          and "3 more warnings not listed above — show them" in inbox,
          "past the display cap the inbox says exactly how many more there are")
    check(all(("Bench %02d" % i) in inbox for i in range(home.ATTENTION_MAX + 3)),
          "...and every one of them is still on the page, inside the "
          "disclosure - the cap hides nothing")
    check('<details class="wr-pop home-att-over"' in inbox,
          "...as a native <details>, no script needed to open it")

    two = [clean_snapshot(), other_snapshot()]
    for s in two:
        s["starters"][0]["bye"] = True
    html = page(two)
    ids = set(re.findall(r'id="([^"]+)"', html))
    targets = set(re.findall(r'href="#([^"]+)"', html))
    check(targets and targets <= ids,
          "every in-page link lands on an element that exists: dangling %s"
          % sorted(targets - ids))
    check(len(set(re.findall(r'id="(p-[^"]+)"', html))) ==
          len(re.findall(r'id="(p-[^"]+)"', html)),
          "...and no two rows share an anchor, across leagues")


# --- [4] three shelves by urgency ------------------------------------------

def test_urgency():
    print("\n[4] the inbox is three shelves by urgency, and every kind lands "
          "on the right one")
    check([k for k, _l, _n in home.URGENCY] == ["now", "lock", "week"],
          "the shelves are Do now · Before lock · This week, in that order")
    check(set(home.URGENCY_OF) == set(home.VERBS),
          "every inbox kind has a shelf: %s"
          % sorted(set(home.VERBS) ^ set(home.URGENCY_OF)))

    def kinds_on(snap):
        items, _ = home.attention_items([snap])
        return dict((i["kind"], i["urgency"]) for i in items)

    s = clean_snapshot()
    s["starters"][0]["bye"] = True
    s["starters"][1]["status"] = "Out"
    s["starters"].append(open_slot("TE"))
    s["starters"].append(row("Zero Guy", pos="WR", slot="FLEX", proj=0.0,
                             anchor="p-fix-4"))
    got = kinds_on(s)
    check(got.get("bye") == "now" and got.get("out") == "now"
          and got.get("open") == "now" and got.get("zero") == "now",
          "a bye starter, an OUT starter, an empty slot and a filed zero are "
          "all 'Do now': %s" % got)

    s = clean_snapshot()
    s["starters"][0]["status"] = "Questionable"
    s["starters"][1].update({"level": board_mod.LVL_SPLIT, "split_weight": 33,
                             "agreement": "MAJORITY", "pct": 67})
    s["starters"].append(row("Blank Guy", pos="WR", slot="FLEX", proj=None,
                             anchor="p-fix-4"))
    s["starters"][0]["matchup"] = {"pa_grade": "AVOID", "opponent": "SEA",
                                   "pos": "RB", "pa_per_game": 26.3,
                                   "pa_rank": 29, "pa_of": 32,
                                   "basis": "2025", "evidence": "e", "reason": ""}
    got = kinds_on(s)
    check(got.get("injury") == "lock" and got.get("split") == "lock"
          and got.get("noproj") == "lock" and got.get("avoid") == "lock",
          "questionable, a split, a missing projection and an AVOID matchup "
          "are 'Before lock': %s" % got)

    s = clean_snapshot()
    s["waivers"] = {"claims": [{"name": "Woody Marks", "pos": "RB",
                                "team": "HOU", "band": "FAAB 9-15%",
                                "detail": ""}],
                    "notes": [], "pool": 200, "mode": "faab",
                    "rivals_known": True}
    s["unresolved"] = ["Some Rookie"]
    s["starters"].append(row("Held DST", pos="DEF", team="ATL", slot="DST",
                             anchor="p-fix-4"))
    s["dk"] = {"DST": {"verdict": "STREAM", "pos": "DST", "best": "New England",
                       "best_short": "NE", "held": "Atlanta", "held_short": "ATL",
                       "delta": 1.6, "best_opp_note": "vs a rookie QB",
                       "held_opp_note": "at a top offense", "best_score": 8.1,
                       "held_score": 6.5, "cost": "", "held_pct": 35,
                       "reason": "r"}}
    got = kinds_on(s)
    items, _ = home.attention_items([s])
    check(got.get("claim") == "week" and got.get("unresolved") == "week",
          "a waiver claim, a DEF/K stream and roster housekeeping are 'This "
          "week': %s" % got)
    streams = [i for i in items if i["kind"] == "claim" and "Stream" in i["text"]]
    check(len(streams) == 1 and streams[0]["subject"] == "NE D/ST"
          and "stream over ATL +1.6" in streams[0]["short"],
          "the DEF/K stream is ONE item, subject the streamer, no duplicate")

    html = page([s])
    inbox = inbox_html(html)
    for key, label in (("now", "Do now"), ("lock", "Before lock"),
                       ("week", "This week")):
        sh = shelf_html(inbox, key)
        check(sh and label in sh and 'class="home-inb-n wr-num"' in sh,
              "the '%s' shelf renders with a count badge even when empty" % label)
    check(inbox.index("home-inb-g-now") < inbox.index("home-inb-g-lock")
          < inbox.index("home-inb-g-week"),
          "...in urgency order")
    check('<span class="home-inb-n wr-num">0</span>' in shelf_html(inbox, "now")
          and "nothing" in shelf_html(inbox, "now"),
          "an empty shelf says 'nothing' and counts 0 - the structure is "
          "persistent, the repeat reader learns it once")
    check('<span class="home-inb-n wr-num">3</span>' in shelf_html(inbox, "week"),
          "the This week badge counts its three items")
    html = page([planted_now()])
    check("Alpha Back" in shelf_html(inbox_html(html), "now")
          and "Alpha Back" not in shelf_html(inbox_html(html), "week"),
          "a planted bye starter renders on the Do now shelf and nowhere else")


def planted_now():
    s = clean_snapshot()
    s["starters"][0]["bye"] = True
    return s


# --- [5] the sidebar on a desktop, the stack on a phone -------------------

def test_sidebar_and_stack():
    print("\n[5] a sticky sidebar from %dpx; a three-then-more stack below it"
          % home.SIDEBAR_MIN_PX)
    html = page([clean_snapshot()])
    body = main_html(html)
    check('<div class="home-grid"><aside class="home-side" aria-label="needs you">'
          in body and body.index('class="home-side"') < body.index('class="home-main"'),
          "the inbox is an <aside class=home-side> that precedes the main "
          "column in the document")
    check(body.index('class="home-head"') < body.index('class="home-grid"'),
          "the week header spans the top, above the two columns")
    check(body.index('id="home-inbox"') < body.index("home-week")
          < body.index('id="league-fix-league"'),
          "document order: inbox, then the strip, then the league cards")

    css = home.page_css()
    wide = re.search(r"@media \(min-width: 1000px\)\s*\{(.*?)\n  \}", css, re.S)
    check(wide is not None, "the stylesheet carries a (min-width: 1000px) block")
    w = wide.group(1) if wide else ""
    check("grid-template-columns: minmax(0, 1fr) 320px" in w,
          "...that lays the page out as content + a 320px rail")
    side = css_block(w, ':root:not([data-inbox="top"]) .home-side')
    check("position: sticky" in side and "grid-column: 2" in side
          and "overflow-y: auto" in side and "top: 66px" in side,
          "...with the rail sticky under the shell, in the right column, "
          "scrolling inside itself")
    check(':root:not([data-inbox="top"])' in w,
          "...and the whole rail is conditional on the preferences layer "
          "not forcing data-inbox=top")
    check(".home-inb-x { display: flex; }" in w and ".home-inb-more { display: none; }" in w,
          "...in the rail every item shows and the 'show more' toggle is gone")
    check("  .home-inb-x { display: none; }" in css,
          "outside the rail, items past the first %d hide" % home.STACK_VISIBLE)
    check(".home-inb:has(.home-inb-more[open]) .home-inb-x { display: flex; }" in css,
          "...and reappear when the native <details> is opened - CSS only")
    check("@supports not selector(:has(*))" in css,
          "...with an honest fallback for a browser without :has(): show all")
    check(":root[data-quiet=\"1\"]" in css,
          "the preferences layer's quiet mode is honoured in CSS")
    check("overflow-x" not in css_block(css, ".home-inb")
          and "overflow-x" not in css_block(css, ".home-att")
          and "overflow-x" not in css_block(css, ".home-side"),
          "the stacked inbox is never a horizontal scroller")

    act = css_block(css, ".home-act")
    check("min-height: 44px" in act and "min-width: 88px" in act,
          "the verb button is %dpx tall and at least %dpx wide"
          % (TOUCH_FLOOR, VERB_MIN_W))
    go = css_block(css, ".home-att-go")
    check("min-height: 44px" in go, "...and the fact beside it is a 44px target")

    many = clean_snapshot()
    many["bench"] = [row("Bench %02d" % i, pos="WR", group="BENCH", slot="",
                         lean="START", pct=80, level=board_mod.LVL_SPLIT,
                         split_weight=30, anchor="p-fix-%d" % (10 + i))
                     for i in range(5)]
    inbox = inbox_html(page([many]))
    lis = re.findall(r'<li class="home-att-item[^"]*"', inbox)
    check(len(lis) == 5 and sum("home-inb-x" in li for li in lis) == 2
          and not any("home-inb-x" in li for li in lis[:3]),
          "five items: the first three are visible in the stack, two carry "
          "the hidden class")
    check('<details class="wr-pop home-inb-more">' in inbox
          and "show 2 more" in inbox and "show fewer" in inbox,
          "...and a native <details> says 'show 2 more'")
    few = inbox_html(page([planted_now()]))
    check("home-inb-more" not in few and "home-inb-x" not in few,
          "with three or fewer items there is no disclosure at all")
    check(inbox.count("home-att-lg") == 5 and "Fixture League" in inbox,
          "each row names its league in the small tag")


# --- [6] a started game locks the row and the item -------------------------

def test_lock_muting():
    print("\n[6] after kickoff the row is muted, the item is muted, the verb "
          "is a lock - from the fixture schedule and an injected clock")
    s = clean_snapshot()
    s["starters"][0]["status"] = "Questionable"      # Alpha Back, Thursday
    s["starters"][1]["status"] = "Questionable"      # Bravo Wideout, Sunday
    before = page([s], now=NOW)
    after = page([s], now=FRIDAY)
    check("home-r-locked" not in row_html(before, "Alpha Back")
          and "home-r-locked" not in row_html(before, "Bravo Wideout"),
          "on Wednesday neither row is locked")
    a_after = row_html(after, "Alpha Back")
    check("home-r-locked" in a_after and "wr-icon-locked" in a_after,
          "on Friday the Thursday player's row is muted and carries the lock "
          "mark")
    check("home-r-locked" not in row_html(after, "Bravo Wideout"),
          "...and the Sunday player's row is not")
    check("already started — this is final" in a_after,
          "...and his card says the game has started")
    check("no live scoring feed is connected" in a_after,
          "...and the score cell's title says no actual is filed because no "
          "scoring feed is connected - not a zero")
    items, _ = home.attention_items([s], now=FRIDAY)
    locked = [i for i in items if i["subject"] == "Alpha Back"]
    live = [i for i in items if i["subject"] == "Bravo Wideout"]
    check(locked and locked[0]["locked"] and live and not live[0]["locked"],
          "attention_items(now=) marks the started item locked")
    check(items.index(live[0]) < items.index(locked[0]),
          "...and sorts it under the live one on its shelf")
    inbox = inbox_html(after)
    li = re.search(r'<li class="home-att-item[^"]*home-att-locked"[^>]*>.*?</li>',
                   inbox, re.S)
    check(li is not None and "Alpha Back" in li.group(0),
          "the inbox row for the started game carries the muted class")
    check(li is not None and 'class="home-act home-act-locked"' in li.group(0)
          and ">Locked<" in li.group(0) and "fantasy.espn.com" not in li.group(0),
          "...and its verb is 'Locked' with no link - a decision already made "
          "is not offered")
    check(".home-r-locked .home-r3 { opacity: 0.55; }" in home.page_css()
          or ".home-r-locked" in home.page_css(),
          "the muting is a stylesheet rule on the row class")
    check(home.row_locked(s["starters"][0], FRIDAY) is True
          and home.row_locked(s["starters"][0], NOW) is False
          and home.row_locked(open_slot(), FRIDAY) is False,
          "row_locked() reads the kickoff against the clock; an open slot "
          "never locks")


# --- [7] the player card knows every league ---------------------------------

def test_cross_league():
    print("\n[7] the player card: ownership across every league, with each "
          "league's own verbs")
    a, b = clean_snapshot(), other_snapshot()
    # Alpha Back is on both rosters: starting here, benched there
    b["starters"] = [row("Alpha Back", pos="RB", group="BENCH", slot="",
                         lean="START", pct=80, anchor="p-other-1")]
    b["bench"] = [row("Zed Nobody", pos="TE", group="BENCH", slot="",
                      anchor="p-other-2")]
    overlap = {"available": True, "rosters": [
        ("fix-league", "Fixture League", {"alpha back|RB", "bravo wideout|WR",
                                          "charlie bench|WR"}),
        ("other", "Other League", {"alpha back|RB", "zed nobody|TE"})],
        "banner": ""}
    html = page([a, b], exposure=overlap)
    card = row_html(html, "Alpha Back")
    check('class="home-xl"' in card and "Across your leagues" in card,
          "a doubled player's card carries the cross-league block")
    lines = re.findall(r'<div class="home-xl-r">.*?</div>', card, re.S)
    check(len(lines) == 2 and "Fixture League" in lines[0]
          and "Other League" in lines[1],
          "one line per league, in league order")
    check("starting · RB" in lines[0] and "bench · RB" in lines[1],
          "...each saying where he sits there")
    check("wr-chip-start" in lines[0] and "80%" in lines[1],
          "...and the room's verdict THERE, as a chip")
    check(('href="https://fantasy.espn.com/football/team?leagueId=111&amp;'
           'teamId=7&amp;seasonId=2026" target="_blank" rel="noopener noreferrer" '
           'title="Trade on ESPN">Trade</a>') in lines[0]
          and 'title="Drop on ESPN">Drop</a>' in lines[0],
          "the ESPN league's line offers Trade and Drop on the ESPN host")
    check('href="https://football.fantasysports.yahoo.com/f1/428/5" target="_blank" '
          'rel="noopener noreferrer" title="Trade on Yahoo">Trade</a>' in lines[1]
          and 'title="Drop on Yahoo">Drop</a>' in lines[1],
          "...and the Yahoo league's line offers them on the Yahoo host")
    check("Correlated risk — Alpha Back is on 2 of your rosters" in card,
          "...with the correlated-risk note")
    check('href="#p-other-1"' in lines[1] and 'href="#p-fix-1"' in lines[0],
          "each league name links to his row in that league's card")

    # Bravo is held here only: the other league offers a Claim
    card = row_html(html, "Bravo Wideout")
    lines = re.findall(r'<div class="home-xl-r">.*?</div>', card, re.S)
    check(len(lines) == 2 and "not rostered by you" in lines[1]
          and 'href="https://football.fantasysports.yahoo.com/f1/428/players" '
          'target="_blank" rel="noopener noreferrer" title="Claim on Yahoo">Claim</a>' in lines[1],
          "a player held in one league gets 'not rostered by you' and a Claim "
          "verb on the other league's waiver page")
    check("Correlated risk" not in card and "Trade" not in lines[1],
          "...no risk note, and no Trade/Drop where he is not held")
    check("free agent" not in card.lower(),
          "...and he is never called a free agent - a rival may hold him")

    # a single league: nothing to cross, and the block says nothing
    single = page([clean_snapshot()])
    check('class="home-xl"' not in single and "Across your leagues" not in single,
          "with ONE league no card carries a cross-league block at all")

    # an unreadable league, and a league with no roster rows
    dead = snapshot(id="dead", name="Dead League")
    dead["error"] = IOError("no league yaml")
    dead["error_text"] = "IOError: no league yaml"
    bare = other_snapshot(starters=[], bench=[])
    html = page([a, dead, bare], exposure={"available": True, "rosters": [
        ("fix-league", "Fixture League", {"alpha back|RB"})], "banner": ""})
    card = row_html(html, "Alpha Back")
    check("unknown — league could not be read" in card,
          "a league that could not be read is 'unknown', never 'not rostered'")
    check("unknown — no roster file for this league" in card,
          "...and so is a league with no roster rows and no roster file")
    got = home.cross_league("alpha back|RB", [a, b], overlap)
    check([e["rostered"] for e in got] == [True, True]
          and got[1]["group"] == "BENCH"
          and [v["short_verb"] for v in got[0]["verbs"]] == ["Trade", "Drop"],
          "cross_league() is the pure source: rostered flags, slot and verbs")
    check(home.cross_league("alpha back|RB", [a], overlap) == []
          and home.cross_league("", [a, b], overlap) == [],
          "...empty for one league, empty for no key")
    bare_rows = other_snapshot(starters=[], bench=[])
    got = home.cross_league("alpha back|RB", [a, bare_rows],
                            {"available": True, "rosters": [
                                ("other", "Other League", {"zed nobody|TE"})]})
    check(got[1]["rostered"] is False and got[1]["verbs"][0]["short_verb"] == "Claim",
          "...engine/exposure's key set answers when a league has no rows")


# --- [8] no clean bill without the checks that earn it ----------------------

def test_honesty():
    print("\n[8] no clean bill without the checks that earn it")

    dead = clean_snapshot()
    dead["unchecked"] = ["the schedule feed is down, so BYE weeks, kickoffs "
                         "and locks were NOT checked"]
    items, caveats = home.attention_items([dead])
    check(not items and caveats,
          "a dead feed produces no items and one caveat - silence is not a "
          "finding")
    html = page([dead])
    check("Nothing needs you" in html
          and "Some checks did not run" in html
          and "BYE weeks, kickoffs and locks were NOT checked" in html,
          "the all-clear rides beside an explicit statement of what it could "
          "not check, so the two are never read as one clean bill")

    skipped = clean_snapshot()
    skipped["waivers"] = None
    skipped["unchecked"] = ["the waiver wire was skipped (--skip-waivers), "
                            "so no claim was checked"]
    html = page([skipped])
    check("no claim was checked" in html,
          "a wire that was not read says so - an empty inbox never implies "
          "an empty wire")

    broken = snapshot(id="dead-league", name="Dead League")
    broken["error"] = IOError("no league yaml")
    broken["error_text"] = "IOError: no league yaml"
    items, caveats = home.attention_items([broken])
    check(any("nothing about that team was checked" in c for c in caveats),
          "a league that could not be read at all becomes a caveat")
    html = page([broken])
    check("SECTION DEGRADED" in html and "no league yaml" in html
          and 'id="league-dead-league"' in html,
          "...its card degrades in place, carrying the real error, and keeps "
          "its id so the switcher still lands")
    check("Nothing could be checked" in html and "Nothing needs you" not in html,
          "when NO league was readable the page says it could not look")

    degraded = clean_snapshot()
    degraded["degraded"] = [("the injury report", RuntimeError("HTTP 503"))]
    degraded["unchecked"] = ["the injury feed is down, so no status was "
                             "checked and no player is assumed healthy"]
    html = page([degraded])
    check("SECTION DEGRADED" in html and "HTTP 503" in html
          and "no player is assumed healthy" in html,
          "a dead feed inside a live league degrades visibly, in place, and "
          "the page refuses to assume health it did not verify")

    partial = clean_snapshot()
    partial["notes"] = ["Coverage: 1 of 10 rosters known — a player on none "
                        "of them is UNKNOWN, not a free agent; my 16-man "
                        "roster, 16 resolved"]
    html = page([partial])
    check("1 of 10 rosters known" in html and 'class="wr-note"' in html,
          "partial roster coverage shows as a quiet note in the league card")

    noform = clean_snapshot()
    noform["scoreboard"] = None
    html = page([noform])
    check("Source form was not read" in html and "none is assumed steady" in html,
          "an unread source scoreboard is a stated absence in the pulse, not "
          "a row of steady faces")

    # ownership context: present, absent-from-feed, and not-read are three
    # different sentences
    s = clean_snapshot()
    s["starters"][0].update({"own_pct": 91.1, "start_pct": 78.4, "own_known": True})
    s["starters"][1].update({"own_known": True})
    html = page([s])
    a, b, c = (row_html(html, "Alpha Back"), row_html(html, "Bravo Wideout"),
               row_html(html, "Charlie Bench"))
    check('class="home-ctx-t"' in a and "rostered 91% · started 78%" in a,
          "ESPN roster % and start % render as the 13px context line when "
          "the feed has him")
    check("rostered in 91% of ESPN leagues, started in 78%" in a
          and "every ESPN league, not this one" in a,
          "...and the card says whose rates they are")
    check("rostered" not in b.split("wr-sheet-b")[0].split("wr-r3-d")[0]
          and "ESPN filed no roster or start rate for him" in b,
          "a player the feed does not carry has no context line and a card "
          "that says the feed filed nothing")
    check("rostered" not in c.split("wr-sheet-b")[0].split("wr-r3-d")[0]
          and "roster and start rates were not read this render" in c,
          "...and when the feed was not read at all the card says that - "
          "three different facts, three different sentences")


# --- [9] the week strip + the lock line ------------------------------------

def test_week_strip():
    print("\n[9] the week strip and the first lock - derived, never invented")

    html = page([clean_snapshot()])
    strip = re.search(r'<section class="wr-card home-week">.*?</section>',
                      html, flags=re.S).group(0)
    labels = [s.strip() for s in
              re.findall(r'<div class="home-win-l">([^<]+)', strip)]
    check(labels == ["Thu night", "Sun early", "Sun late", "Sun night",
                     "Mon night"],
          "the five windows appear in kickoff order: %s" % labels)
    first = re.search(r'<div class="home-win home-win-first">.*?</div>\s*<div',
                      strip, flags=re.S)
    check(first is not None and "Thu night" in first.group(0)
          and "first lock" in first.group(0),
          "the first-lock window is the Thursday one and carries the mark")
    check("home-win-first" in html and "inset 0 3px 0 var(--wr-rule)" in html,
          "...drawn as the gold rule, not a fill")
    thu = re.search(r'home-win home-win-first.*?</div>\s*</div>', strip,
                    flags=re.S).group(0)
    check('<b class="wr-num">1</b>' in thu,
          "Alpha Back plays Thursday, so that window counts 1 starter")
    check("Thu 8:15 PM ET · 1 game" in strip and "8 games" in strip,
          "each window states its first kickoff and how many games it holds")

    two = [clean_snapshot(), other_snapshot()]
    html = page(two)
    check("ESPN 1 · Yahoo 1" in html,
          "with two leagues each window breaks its count down per league")

    check("first lock Thu 8:15 PM ET · 2 of your starters play then "
          "(ESPN 1 · Yahoo 1)" in html,
          "the header states the first lock and who of yours is in it")
    one = page([clean_snapshot()])
    check("first lock Thu 8:15 PM ET · 1 of your starters plays then" in one,
          "...with the grammar right for one")

    later = page([clean_snapshot()], now=_dt(2026, 9, 13, 15, 0))
    check("first lock passed (Thu 8:15 PM ET) · next lock Sun 4:25 PM ET"
          in later,
          "once the first lock has passed the header names the NEXT lock")
    done = page([clean_snapshot()], now=_dt(2026, 9, 15, 9, 0))
    check("every game this week has kicked off" in done,
          "...and after the last game it says the week is final")
    check("home-win-past" in later,
          "a window that has kicked off is drawn faded")

    byed = clean_snapshot()
    byed["starters"][1].update({"bye": True, "kickoff_iso": ""})
    html = page([byed])
    check("1 of your starters has no game this week (bye)" in html,
          "a starter on bye is counted in no window and the strip says so")

    nosched = clean_snapshot()
    nosched["kickoffs"] = []
    for r in nosched["starters"] + nosched["bench"]:
        r["kickoff_iso"] = ""
    html = page([nosched])
    check("Game windows unknown — the schedule feed filed no kickoff" in html
          and "home-win" not in main_html(html).replace("home-window", ""),
          "no kickoffs at all -> the strip is a stated absence, not five "
          "empty columns")
    check("first lock unknown — the schedule feed filed no kickoff" in html,
          "...and the lock line says the same")

    # a day without a clock: the day is shown, no time is invented
    midnight = _iso(2026, 9, 9, 0, 0)
    tbd = clean_snapshot()
    tbd["kickoffs"] = [midnight] + list(KICKOFFS)
    tbd["starters"][0]["kickoff_iso"] = midnight
    html = page([tbd])
    check(home.time_known(midnight) is False and home.time_known(THU) is True,
          "a 00:00 stamp is read as 'time not filed' (weekly._kickoff_iso "
          "stamps midnight for a blank gametime); a real clock is known")
    check("first lock Wed 9/9 (time not filed) · 1 of your starters plays "
          "then" in html,
          "the lock line shows the DAY and says the time was not filed - and "
          "at noon that day it is NOT reported as passed, because unknown is "
          "not locked")
    check(home.is_locked(midnight, _dt(2026, 9, 9, 23, 0)) is False
          and home.is_locked(midnight, _dt(2026, 9, 10, 0, 30)) is True,
          "a day-only kickoff locks only once its day is over")
    check("Wed (time not filed)" in html and "12:00 AM" not in html,
          "the strip column says the same and no midnight clock is printed")
    check("has a day but no clock in the schedule feed" in html,
          "...with a note explaining the column")
    r = row_html(html, "Alpha Back")
    check(">Wed 9/9<" in r and "time not filed by the schedule feed" in r,
          "the row's kickoff shows the day alone, the title says why")

    # the window rule itself
    wins = {home.game_window(_iso(2026, 9, 13, 9, 30))["label"]: "morning",
            home.game_window(_iso(2026, 9, 13, 13, 0))["label"]: "early",
            home.game_window(_iso(2026, 9, 13, 16, 5))["label"]: "late",
            home.game_window(_iso(2026, 9, 13, 20, 20))["label"]: "night",
            home.game_window(_iso(2026, 9, 10, 20, 15))["label"]: "thu",
            home.game_window(_iso(2026, 9, 14, 20, 15))["label"]: "mon",
            home.game_window(_iso(2026, 9, 12, 16, 30))["label"]: "sat"}
    check(list(wins) == ["Sun morning", "Sun early", "Sun late", "Sun night",
                         "Thu night", "Mon night", "Sat late"],
          "game_window() maps clocks to windows: %s" % list(wins))
    check(home.game_window("") is None and home.game_window("junk") is None,
          "...and refuses to place a kickoff it cannot parse")


# --- [10] league cards ------------------------------------------------------

def test_league_cards():
    print("\n[10] one card per league: record, coverage, projected total, links")
    snap = clean_snapshot()
    snap["starters"][0]["proj"] = 20.25
    snap["starters"][1]["proj"] = 10.0
    html = page([snap])
    card = re.search(r'<section class="wr-card home-league" id="league-fix-league">'
                     r".*?</section>", html, flags=re.S).group(0)
    check('<span class="wr-num">30.2</span>' in card or
          '<span class="wr-num">30.3</span>' in card,
          "the projected starting-lineup total is the sum of the starters' "
          "projections, in the numeric face")
    check("projected starting lineup" in card,
          "...labelled as such")
    check("record not tracked" in card and 'title="not tracked (no standings '
          'feed connected)"' in card,
          "no standings feed -> 'record not tracked', never 0-0, with the "
          "reason in the title")
    tracked = clean_snapshot()
    tracked["record"] = "2-1"
    check('record <b class="wr-num">2-1</b>' in page([tracked]),
          "a hand-kept record in the league yaml is printed")
    check("ESPN · 10 teams · full PPR · week 4" in card,
          "the platform, size, scoring and week are one line")
    for href, label in (("board-fix-league-week4.html", "Board"),
                        ("digest-fix-league-week4.html", "Ledger"),
                        ("tradedesk-fix-league-week4.html", "Trade Desk")):
        check('href="%s"' % href in card and label in card,
              "the card links to the league's %s (%s)" % (label, href))
    check('href="https://fantasy.espn.com/football/team?leagueId=111&amp;'
          'teamId=7&amp;seasonId=2026" target="_blank" rel="noopener noreferrer">Your '
          'team on ESPN</a>' in card,
          "...and to the team on its host, in a new tab")

    missing = clean_snapshot()
    missing["pages"] = home.page_links_pure("fix-league", 4)
    missing["pages"]["trades"]["exists"] = False
    check("(not built yet)" in page([missing]),
          "a sibling page that does not exist yet is linked AND marked, "
          "never hidden")

    part = clean_snapshot()
    part["starters"][1]["proj"] = None
    check("1 of 2 starters projected" in page([part]),
          "a partial sum says how many starters it rests on")
    none = clean_snapshot()
    for r in none["starters"]:
        r["proj"] = None
    check("no starter has a projection filed" in page([none]),
          "no projections at all is a dash and a sentence, not 0.0")


# --- [11] roster rows: three columns, a card behind each ---------------------

def test_roster_rows():
    print("\n[11] roster rows: identity | middle | verdict, 44px tall, a card "
          "behind each, the '?' at the head")
    html = page([clean_snapshot()])
    check('<div class="home-roster-h"><span class="wr-sec-h">Roster</span>' in html
          and "2 starting · 1 bench" in html,
          "the roster has a head that counts starters and bench")
    # the quiet-mode count note may sit between the head and the list
    head = re.search(r'<div class="home-roster-h">.*?</div>\s*'
                     r'(?:<p class="wr-quiet-note".*?</p>\s*)?'
                     r'<div class="home-roster"', html, re.S)
    check(head is not None and 'class="home-legend-w"' in head.group(0)
          and ">?<" in head.group(0),
          "...and carries the '?' legend popover - no legend block at the "
          "bottom of the page")
    check("What the marks mean" not in html and 'class="wr-card home-legend"' not in html,
          "...the old bottom legend card is gone")

    # QUIET MODE OWES THE READER A LINE. Rows marked data-unanimous="1" are
    # folded away by engine/prefs' stylesheet; without a visible count a
    # quiet roster reads as a SHORTER roster, which is a lie about what the
    # room said. (engine/prefs.py states this contract; it was unwired once.)
    # count ELEMENTS carrying the mark - the stylesheet also contains the
    # literal selector, and counting that would fake the total.
    marked = len(re.findall(r'<[^>]+data-unanimous="1"', html))
    notes = re.findall(r'<p class="wr-quiet-note"[^>]*>(.*?)</p>', html, re.S)
    if marked:
        check(notes, "quiet mode: %d row(s) are marked hidable, so the page "
                     "prints a count note (found %d)" % (marked, len(notes)))
        counted = sum(int(n) for note in notes
                      for n in re.findall(r"<b[^>]*>(\d+)</b>", note))
        check(counted == marked,
              "...and the notes account for EVERY hidden row (%d marked, "
              "%d counted) - an uncounted row would vanish in silence"
              % (marked, counted))
        check(all("quiet" in n.lower() for n in notes),
              "...and each names quiet mode as the reason they are gone")
        check(html.index('<p class="wr-quiet-note')
              < html.index('<div class="home-roster"'),
              "...and the first note sits above the roster it describes")
    else:
        check('<p class="wr-quiet-note"' not in html,
              "nothing marked hidable -> no quiet note is printed")
    starting = html.index("Starting <span")
    bench = html.index("Bench <span")
    alpha = html.index('data-player="alpha back"')
    charlie = html.index('data-player="charlie bench"')
    check(starting < alpha < bench < charlie,
          "starters come first, under a Starting group row; bench after")
    r = row_html(html, "Alpha Back")
    check(r.startswith('<div class="home-r"') and 'data-player="alpha back"' in r,
          "the row is a .home-r element carrying a lowercase data-player key "
          "for the jump box")
    three = (("wr-r3-id" in r and "wr-r3-mid" in r and "wr-r3-v" in r)
             or ("home-r3-id" in r and "home-r3-mid" in r and "home-r3-ver" in r))
    check(three, "the row has exactly the three columns: identity, middle, verdict")
    check('<span class="wr-pos"' in r and "Alpha Back" in r,
          "identity: the position badge and the name")
    check('class="home-oppw"' in r and "XXX" in r and "Thu 8:15 PM" in r,
          "middle: the opponent chip and the short kickoff")
    check('class="home-scorew"' in r and ">12.5<" in r,
          "middle: the score cell with the projection")
    check("wr-chip-start" in r and "wr-meter" in r,
          "verdict: the chip and the meter")
    check("The room" in r and "Projection" in r and "Kickoff" in r,
          "the card behind the row repeats every signal in words")
    check("wr-sheet" in r or "wr-r3-x" in r or 'class="wr-pop home-pop"' in r,
          "...as a sheet, or row3's own expander, or the popover - whichever "
          "has landed")

    trend = clean_snapshot()
    trend["starters"][0]["trend_adds"] = 1234
    t = row_html(page([trend]), "Alpha Back")
    check('class="home-trend"' in t and any("1,234" in x or "1234" in x or "1.2k" in x
                                            for x in titles(t) + [t]),
          "a trending player carries the trend mark with the add count")
    check('class="home-trend"' not in row_html(page([clean_snapshot()]), "Alpha Back"),
          "...and an untrending one carries nothing")

    css = home.page_css()
    check("min-height: 44px" in css_block(css, ".home-r"),
          "every roster row keeps the %dpx tap floor in the emitted CSS"
          % TOUCH_FLOOR)
    for sel in (".home-act", ".home-att-go", ".home-link", ".home-lg-links a",
                ".home-jump-q"):
        check("min-height: 44px" in css_block(css, sel),
              "%s keeps a %dpx tap floor" % (sel, TOUCH_FLOOR))
    r3 = css_block(css, ".home-r3")
    check("grid-template-columns: minmax(0, 1fr) auto auto" in r3,
          "the local three-column grid: the name shrinks, the other two do not")

    opened = clean_snapshot()
    opened["starters"].append(open_slot("TE"))
    html = page([opened])
    r = next((x for x in rows_in(html) if "(open slot)" in x), "")
    check(r and 'data-player=""' in r and "nobody on the roster fits the TE slot" in r
          and "wr-chip" not in r and "wr-meter" not in r,
          "an open slot renders as a row with no chip, no meter, and a "
          "sentence - it is a hole in the data, not a player")


# --- [12] the exposure ribbon ------------------------------------------------

def test_exposure():
    print("\n[12] the exposure ribbon appears only with overlap")
    a, b = clean_snapshot(), other_snapshot()
    b["starters"] = [row("Alpha Back", pos="RB", group="BENCH", slot="",
                         anchor="p-other-1")]
    b["bench"] = []
    overlap = {"available": True, "rosters": [
        ("fix-league", "Fixture League", {"alpha back|RB", "bravo wideout|WR"}),
        ("other", "Other League", {"alpha back|RB", "zed nobody|TE"})],
        "banner": ""}
    html = page([a, b], exposure=overlap)
    check('class="wr-card home-expo"' in html and "1 shared" in html,
          "two rosters sharing one player render the ribbon")
    check("<b>Alpha Back</b>" in html and "starts in Fixture League" in html
          and "benched in Other League" in html,
          "...naming him and where he sits on each roster")
    check("Correlated risk" in html,
          "...with the correlated-risk note")
    check("Bravo Wideout</b>" not in html.split("home-expo")[-1].split("</section>")[0],
          "a player held once is not in the ribbon")

    disjoint = {"available": True, "rosters": [
        ("fix-league", "Fixture League", {"alpha back|RB"}),
        ("other", "Other League", {"zed nobody|TE"})], "banner": ""}
    ribbon = 'class="wr-card home-expo"'
    check(ribbon not in page([a, b], exposure=disjoint),
          "two rosters with nothing in common render no ribbon at all")
    check(ribbon not in page([a, b], exposure=None)
          and ribbon not in page([a, b]),
          "no exposure data renders no ribbon - absence is not a claim")
    single = {"available": True, "rosters": [
        ("fix-league", "Fixture League", {"alpha back|RB"})], "banner": ""}
    check(ribbon not in page([a], exposure=single),
          "one roster cannot overlap with itself")

    partial = dict(overlap)
    partial["banner"] = ("Other League roster known 3/16 - no flag does NOT "
                         "mean not rostered")
    html = page([a, b], exposure=partial)
    check("no flag does NOT mean not rostered" in html,
          "a partial roster's coverage banner rides with the ribbon")

    got = home.exposure_overlap(overlap, [a, b])
    check(len(got) == 1 and got[0]["name"] == "Alpha Back"
          and [lg["group"] for lg in got[0]["leagues"]] == ["STARTING", "BENCH"],
          "exposure_overlap() names the player from the rows and keeps each "
          "league's slot")


# --- [13] the source pulse + the jump box -----------------------------------

def test_pulse_and_jump():
    print("\n[13] the source pulse and the jump box")
    html = page([clean_snapshot()])
    pulse = re.search(r'<section class="wr-card home-pulse">.*?</section>',
                      html, flags=re.S).group(0)
    check(pulse.count('class="wr-np wr-np-c"') == 2 and "2 enabled" in pulse,
          "every enabled source is a compact nameplate, once")
    check(pulse.count('href="sources.html"') >= 3,
          "each nameplate and the section link point at sources.html")
    check("wt 17" in pulse and "NO-DATA" in pulse,
          "a nameplate carries the weight and the current-form state")
    check("wr-av-creator" in pulse and "wr-av-feed" in pulse,
          "a creator gets the gold ring; a feed the hairline ring")
    check("ledger is empty until a week is played" in pulse,
          "all NO-DATA states are explained as a fact about the record")

    two = [clean_snapshot(), other_snapshot()]
    two[1]["scoreboard"][0]["state"] = "HOT"
    html = page(two)
    check("MIXED" in html and "Form differs by league" in html
          and "Other League HOT" in html,
          "a source whose form differs between leagues says so instead of "
          "averaging two records into one face")

    html = page([clean_snapshot()])
    check('<div class="home-jump" id="home-jump" hidden>' in html,
          "the jump box is present and hidden until script reveals it")
    check('<input class="home-jump-q" id="home-jump-q" type="search"' in html,
          "...a search input")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    check(scripts and not re.search(r"<script[^>]*src=", html),
          "%d inline scripts - the shell's, the jump box, the sheets - and "
          "nothing fetched" % len(scripts))
    js = next((s for s in scripts if "home-jump" in s), "")
    check("box.hidden=false" in js and '.home-r[data-player]' in js
          and len(js.strip().splitlines()) <= 15,
          "the jump script reveals the box and filters .home-r[data-player] "
          "rows, in %d lines" % len(js.strip().splitlines()))
    body = main_html(html)
    check(body.index('id="home-jump"') < body.index('id="league-fix-league"')
          and body.index('id="home-jump"') > body.index("home-week"),
          "the box sits below the week strip and above the league cards it "
          "filters")


# --- [14] the design system, and nothing else --------------------------------

def test_design_system():
    print("\n[14] the v3 design system only - no second palette, nothing "
          "fetched beyond the host links, the type floor held")
    html = page([clean_snapshot()])
    lower = html.lower()
    bad = [c for c in FORBIDDEN if c.lower() in lower]
    check(not bad, "none of the retired green/red hexes survives in the "
                   "emitted page: %s" % (bad or "none found"))

    src = open(os.path.join(HERE, "engine", "home.py")).read()
    body = src.split('"""', 2)[2]
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
    check(not hexes,
          "engine/home.py declares no colour of its own (%s)"
          % (hexes or "none found"))
    for artwork in ("<svg", "<path", "<circle", "<rect ", "viewBox"):
        check(artwork not in body,
              "engine/home.py draws no %r - the marks are ui.icon()" % artwork)
    check(body.count("var(--wr-") >= 40,
          "its stylesheet is written entirely against the shared tokens")
    check("ui.shell(" in body and "ui.style_tag()" in body
          and "ui.verdict_chip(" in body and "ui.matchup_meter(" in body
          and "ui.nameplate(" in body,
          "it composes the shell, the chip, the meter and the nameplate "
          "from engine/ui rather than redrawing them")
    sizes = [float(s) for s in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px",
                                          home._PAGE_CSS + home._TYPE_SCALE_CSS)]
    check(sizes and min(sizes) >= TYPE_FLOOR,
          "nothing in the page stylesheet is set below %dpx (smallest %s)"
          % (TYPE_FLOOR, min(sizes) if sizes else "-"))
    check(all(("wr-t%d" % i) in html for i in (2, 3, 4)),
          "the markup speaks the type scale classes (17/15/13/11)")

    no_ns = re.sub(r"xmlns=[\"']http://www\.w3\.org/2000/svg[\"']", "", html)
    no_ns = re.sub(r"url\(\"data:[^\"]*\"\)", "", no_ns)
    urls = set(re.findall(r"https?://[^\s\"'<>)]+", no_ns))
    stray = sorted(u for u in urls if not any(h in u for h in ALLOWED_HOSTS))
    check(not stray,
          "no external URL beyond the host deep links, the shell's local "
          "panel and the font CDN: %s" % (stray or "none"))
    for bad in ("<img", "<iframe", "srcset"):
        check(bad not in lower, "no %r - nothing on this page is fetched at "
                                "open time" % bad)
    # engine/pwa.py adds two link relations through ui.style_tag() so the
    # page installs on a phone. NEITHER is fetched to paint it: delete both
    # and home.html still renders from its own bytes. A rel="stylesheet", a
    # rel="icon" or a preload - the things a browser really does fetch at
    # open - still fail here, and now by name.
    links = re.findall(r"<link\b[^>]*>", lower)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in links),
          "the only <link>s are the app manifest and the touch icon, "
          "neither fetched at open time (%s)" % (links or "none"))
    check(not re.search(r"url\(\s*[\"']?https?://", html),
          "no CSS url() points off the page (fonts and faces are data URIs)")
    check(html.startswith("<!doctype html>") and html.rstrip().endswith("</html>"),
          "one complete document")

    xml_safe = {"amp", "lt", "gt", "quot", "apos"}
    named = set(re.findall(r"&([a-zA-Z][a-zA-Z0-9]*);", html)) - xml_safe
    check(not named,
          "no HTML-only named entity (%s) - the markup stays XML-parseable"
          % (sorted(named) or "none found"))

    # every mark inside <main> that is not self-labelled is in the legend
    full = clean_snapshot()
    full["starters"][0].update({"status": "Out", "trend_adds": 1500,
                                "hot_backers": ["The Favorites"],
                                "level": board_mod.LVL_SPLIT, "split_weight": 30,
                                "quotes": [("The Favorites", "start him")]})
    full["starters"][1].update({"bye": True, "kickoff_iso": ""})
    html2 = page([full], now=FRIDAY)
    used = icon_names_in(main_html(html2))
    selflabelled = {"expand", "consensus", "start", "sit", "toss-up", "trade",
                    "close", "sheet-handle", "wall"}
    legend_html = home.legend_pop_html()
    documented = set(n.replace("_", "-") for n, _m in home.legend_items()) \
        | icon_names_in(legend_html)
    check(used - selflabelled <= documented,
          "every mark the page prints is in the legend popover: undocumented %s"
          % sorted(used - selflabelled - documented))
    for name, _meaning in home.LEGEND:
        check(name in ui.icon_names(),
              "the legend entry %r is a real icon in the design system" % name)
    glyphs = re.findall(r"<svg .*?</svg>", legend_html, flags=re.S)
    check(glyphs and all("<title>" in g for g in glyphs),
          "every glyph in the legend carries a <title> (%d glyphs)" % len(glyphs))

    ok = True
    for frag in re.findall(r"<svg .*?</svg>", html, flags=re.S)[:80]:
        try:
            ET.fromstring(frag)
        except ET.ParseError:
            ok = False
            break
    check(ok, "every inline icon on the page parses as well-formed XML")


# --- [15] the ui bridge -------------------------------------------------------

def test_ui_bridge():
    print("\n[15] the ui bridge: every v4 component is optional, and the page "
          "renders on its fallbacks")
    have = home.ui_components()
    check(set(home.UI_NAMES) <= set(have) and "type_scale" in have,
          "ui_components() reports every name it reaches for: %s"
          % ", ".join("%s=%s" % (k, "yes" if v else "fallback")
                      for k, v in sorted(have.items())))
    s = clean_snapshot()
    s["starters"][0].update({"status": "Questionable", "trend_adds": 1200,
                             "quotes": [("The Favorites", "start him")],
                             "matchup": {"pa_grade": "SMASH", "opponent": "PIT",
                                         "pos": "RB", "pa_per_game": 30.0,
                                         "pa_rank": 1, "pa_of": 32,
                                         "basis": "2025", "evidence": "e",
                                         "reason": ""}})
    with_ui = page([s])
    with without_ui(*home.UI_NAMES):
        check(not any(home.ui_components()[n] for n in home.UI_NAMES),
              "with the components hidden, ui_components() says fallback")
        fb = page([s])
        r = row_html(fb, "Alpha Back")
        for cls, what in (("home-r3", "the local three-column grid"),
                          ("home-oppc", "the local opponent chip"),
                          ("home-score", "the local score cell"),
                          ("home-dot", "the local news dot"),
                          ("wr-badge-injury", "the flag badge as status pill"),
                          ("wr-pill", "a stat pill as the trend mark"),
                          ('class="wr-pop home-pop"', "ui.popover as the card")):
            check(cls in r, "fallback row uses %s (%s)" % (what, cls))
        check('class="home-legend-pop"' in fb or "home-legend-pop" in fb,
              "fallback legend is a local <details> popover")
        check(">Q<" in r and "1.2k" in r and "PIT" in r and ">12.5<" in r,
              "...and says the same facts: Q, 1.2k adds, PIT, 12.5")
        check("<script" in fb and fb.count("<script") >= 1,
              "...with no sheets script, the page still carries its own")
        check(".wr-t2 { font-size: 15px; }" in home.page_css()
              or home.ui_has_type_scale(),
              "the type-scale twins are emitted only while ui lacks them")
    check(with_ui != fb,
          "the two renders differ - the bridge really switched paths")
    for n in home.UI_NAMES:
        check(getattr(ui, n, None) is not None or not have[n],
              "%s restored after the fallback render" % n)
    check(home.ui_components() == have, "ui_components() is back to what it was")


# --- [16] mobile ---------------------------------------------------------------

def test_mobile():
    print("\n[16] it fits a %dpx phone" % VIEWPORT)
    css = home.page_css()
    wide = [m.group(0) for m in re.finditer(
        r"(?<![\w(-])(min-width|width)\s*:\s*(\d+(?:\.\d+)?)px", css)
        if float(m.group(2)) > VIEWPORT]
    check(not wide, "no fixed width in the whole stylesheet (ui + page) "
                    "exceeds %dpx outside a media query: %s"
          % (VIEWPORT, wide or "none found"))
    over = [m.group(0) for m in re.finditer(
        r"(?<![\w(-])(min-width|width)\s*:\s*(\d+(?:\.\d+)?)rem", css)
        if float(m.group(2)) * 16 > VIEWPORT]
    check(not over, "and no rem width does either: %s" % (over or "none"))
    check("@media (max-width: 700px)" in home._PAGE_CSS,
          "the page has its own narrow-screen block at the shell's breakpoint")
    check("overflow-wrap: anywhere" in home._PAGE_CSS,
          "long names wrap instead of pushing the page sideways")
    check("overflow-x: auto" in css_block(home._PAGE_CSS, ".home-strip"),
          "the week strip scrolls inside its own box")
    check("overflow-x" not in css_block(home._PAGE_CSS, ".home-roster")
          and "overflow-x" not in css_block(home._PAGE_CSS, ".home-r3"),
          "the roster does not: three columns fit the phone, no sideways box")
    html = page([clean_snapshot()])
    check('name="viewport"' in html and "width=device-width" in html,
          "the page declares a device-width viewport")
    check('grid-template-columns: minmax(0, 1fr) auto auto' in css,
          "the three columns are a grid whose first column can shrink")


# --- [17] escaping -------------------------------------------------------------

def test_escaping():
    print("\n[17] hostile feed text comes out inert")
    r = row(HOSTILE, pos="WR", slot="WR", status=HOSTILE,
            quotes=[(HOSTILE, HOSTILE)],
            voices=[(HOSTILE, "start", HOSTILE)],
            hot_backers=[HOSTILE], meta=HOSTILE, opponent=HOSTILE,
            proj_source=HOSTILE, kickoff=HOSTILE, kickoff_iso="",
            matchup={"pa_grade": "AVOID", "opponent": HOSTILE, "pos": "WR",
                     "pa_per_game": 1.0, "pa_rank": 30, "pa_of": 32,
                     "basis": HOSTILE, "evidence": HOSTILE, "reason": ""})
    snap = snapshot([r], name=HOSTILE, record=HOSTILE,
                    notes=[HOSTILE], unresolved=[HOSTILE],
                    host={"league_id": HOSTILE, "team_id": HOSTILE},
                    waivers={"claims": [{"name": HOSTILE, "pos": HOSTILE,
                                         "team": HOSTILE, "band": HOSTILE,
                                         "detail": HOSTILE}],
                             "notes": [], "pool": 1, "mode": "faab"},
                    scoreboard=[{"source": HOSTILE, "name": HOSTILE,
                                 "type": "youtube", "weight": 5,
                                 "state": HOSTILE, "state_reason": HOSTILE}],
                    board_href=HOSTILE)
    other = other_snapshot(name=HOSTILE, host={"league_id": HOSTILE,
                                               "team_id": HOSTILE})
    html = page([snap, other], exposure={"available": True, "rosters": [
        ("fix-league", HOSTILE, {r["key"]}), ("other", HOSTILE, {r["key"]})],
        "banner": HOSTILE})
    check("<script>alert" not in html,
          "an injected <script> tag never reaches the page as markup")
    check("&lt;script&gt;" in html,
          "...it is present, escaped, so the reader sees what the feed said")
    check(html.count("<body>") == 1 and "</span> --> é" not in html,
          "a premature </span> in feed text does not break out of its element")
    hrefs = re.findall(r'href="(https://[^"]*)"', html)
    check(hrefs and all("<" not in h and "'" not in h and " " not in h
                        for h in hrefs)
          and any("%3Cscript%3E" in h for h in hrefs),
          "hostile host ids are URL-quoted inside the deep link, never "
          "interpolated raw - in the inbox and in the cross-league verbs")
    frag = row_html(html, HOSTILE)
    try:
        ET.fromstring("<div>%s</div>" % frag)
        ok = True
    except ET.ParseError as exc:
        ok = False
        print("      parse error: %s" % exc)
    check(bool(frag) and ok, "the row holding the hostile name stays "
                             "well-formed XML")
    check(bool(frag) and "home-xl" in frag and "&lt;script&gt;" in
          frag.split("home-xl")[1],
          "...and its cross-league lines escape the hostile league name")


# --- [18] write discipline + the read-only guarantee ----------------------------

def test_write_discipline():
    print("\n[18] it writes exactly one file, and advances nothing")
    before_hash = None
    if os.path.exists(OWNED_SNAP):
        before_hash = hashlib.sha256(open(OWNED_SNAP, "rb").read()).hexdigest()
        before_mtime = os.stat(OWNED_SNAP).st_mtime
    tmp = tempfile.mkdtemp(prefix="home-test-")
    try:
        out = os.path.join(tmp, "page.html")
        path = home.write_home(4, out_path=out, snapshots=[clean_snapshot()],
                               stamp="FIXED", now=NOW)
        check(path == out and os.path.exists(out),
              "write_home returns the path it wrote")
        check(sorted(os.listdir(tmp)) == ["page.html"],
              "exactly one file appeared - no stray .tmp left behind")
        first = open(out).read()
        home.write_home(4, out_path=out, snapshots=[clean_snapshot()],
                        stamp="FIXED", now=NOW)
        check(open(out).read() == first,
              "rendering twice with the same inputs produces the same bytes")
        check(home.DEFAULT_PATH == os.path.join(HERE, "home.html"),
              "the default output is home.html in the project root")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if before_hash is not None:
        after_hash = hashlib.sha256(open(OWNED_SNAP, "rb").read()).hexdigest()
        check(after_hash == before_hash
              and os.stat(OWNED_SNAP).st_mtime == before_mtime,
              "data/cache/espn-owned-snapshot.json is byte-identical (and "
              "untouched) after a double render - the baseline never moves")
    else:
        check(not os.path.exists(OWNED_SNAP),
              "no %%owned snapshot existed and the render did not create one")

    src = open(os.path.join(HERE, "engine", "home.py")).read()
    check("advance=False" in src and "advance=True" not in src,
          "the wire read passes owned_momentum(advance=False) and the module "
          "never says advance=True anywhere")
    for word in ("save_sources", "record_vote", "append_ledger", "os.remove",
                 "shutil."):
        check(word not in src,
              "engine/home.py contains no %r - it writes one HTML file and "
              "nothing else" % word)
    check("json.dump(" not in src and "open(" not in src.replace(
        'with open(tmp, "w") as fh', ""),
          "...and opens no file for writing but the page itself")


# --- [19] the host config ----------------------------------------------------------

def test_host_config():
    print("\n[19] LeagueConfig.host: optional, strict, never guessed")
    check(host_of({"league_id": 284298483, "team_id": 8})
          == {"league_id": "284298483", "team_id": "8"},
          "both ids present -> a host dict of strings")
    check(host_of(None) is None and host_of("x") is None
          and host_of({}) is None,
          "absent or malformed -> None, no error")
    check(host_of({"league_id": 1}) is None
          and host_of({"league_id": 1, "team_id": ""}) is None
          and host_of({"league_id": 1, "team_id": None}) is None,
          "a half-filled host is None - a league id alone cannot open a team")
    check(LeagueConfig({"id": "x"}).host is None,
          "a league yaml without host: still loads, host None")
    espn = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    yahoo = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
    check(espn.host == {"league_id": "284298483", "team_id": "8"},
          "leagues/espn-1.yaml carries host {284298483, 8}")
    check(yahoo.host == {"league_id": "428472", "team_id": "5"},
          "leagues/yahoo-main.yaml carries host {428472, 5}")
    check(espn.waiver_mode == "priority" and yahoo.waiver_mode == "faab"
          and espn.teams == 8 and yahoo.teams == 10,
          "...and nothing else in either file changed")
    snap = {"platform": "espn", "host": None, "id": "e"}
    check(home.host_link(snap, "team") == "" and home.host_link(snap, "players") == ""
          and home.host_link(snap, "trade") == "" and home.host_link(snap, "drop") == "",
          "host_link() builds nothing without host - not even the waiver "
          "page from espn_league_id")
    snap["host"] = {"league_id": "9", "team_id": ""}
    check(home.host_link(snap, "team") == "" and home.host_link(snap, "trade") == "",
          "...and no team-shaped link (team, trade, drop) without a team id")
    check(home.host_link(snap, "players") ==
          "https://fantasy.espn.com/football/players/add?leagueId=9",
          "...while the waiver page needs only the league id")
    check(set(home.HOST_URLS["espn"]) == set(home.HOST_URLS["yahoo"])
          == {"team", "players", "trade", "drop"},
          "both hosts carry the same four recipes")


# --- [20] the small pure helpers -------------------------------------------------

def test_helpers():
    print("\n[20] the helpers that decide what the page may claim")
    check(home.fmt_pts(None) == "—" and home.fmt_pts(0.0) == "0.0"
          and home.fmt_pts("junk") == "—",
          "None (nothing filed) and 0.0 (a filed zero) stay different facts")
    check(home.fmt_count(87) == "87" and home.fmt_count(1234) == "1.2k"
          and home.fmt_count("x") == "—",
          "fmt_count: 87, 1.2k, and a dash for junk")
    check(home.opponent_label("ATL", None, schedule_known=True) == "BYE"
          and home.opponent_label("ATL", None, schedule_known=False) == "",
          "no game in a KNOWN schedule is a bye; in an UNKNOWN one it is "
          "nothing")
    check(home.opponent_label("ATL", {"opponent": "PIT", "home": False}) == "@ PIT"
          and home.opponent_label("ATL", {"opponent": "PIT", "home": True}) == "vs PIT",
          "away reads '@ OPP', home reads 'vs OPP'")
    check(home.opp_of({"opponent": "PIT", "home": False}) == ("PIT", False)
          and home.opp_of({"meta": "ATL @ SEA"}) == ("SEA", False)
          and home.opp_of({"meta": "ATL vs SEA"}) == ("SEA", True)
          and home.opp_of({"meta": "ATL"}) == ("", None),
          "opp_of reads the gathered keys first, then the meta, else unknown")
    check(home.row_opp_label({"bye": True}) == "BYE"
          and home.row_opp_label({"open": True}) == ""
          and home.row_opp_label({"opponent": "KC", "home": True}) == "vs KC",
          "row_opp_label: BYE, nothing for an open slot, 'vs KC'")

    check(home.is_locked("") is False and home.is_locked("not-a-date") is False,
          "an unparseable or missing kickoff is NOT locked")
    past = (datetime.now() - timedelta(hours=2)).isoformat()
    future = (datetime.now() + timedelta(hours=2)).isoformat()
    check(home.is_locked(past) is True and home.is_locked(future) is False,
          "a kickoff in the past locks, one in the future does not")
    check(home.is_locked("2026-09-13T13:00:00+00:00",
                         datetime(2026, 9, 13, 15, 0, 0)) is False,
          "a naive/aware mismatch refuses to answer rather than guessing")

    check(home.kickoff_label(SUN_EARLY) == "Sun 9/13 1:00 PM ET"
          and home.lock_label(SUN_EARLY) == "Sun 1:00 PM ET"
          and home.short_kick(SUN_EARLY) == "Sun 1:00 PM",
          "labels: 'Sun 9/13 1:00 PM ET' in a card, 'Sun 1:00 PM ET' as a "
          "lock, 'Sun 1:00 PM' on a row")
    check(home.kickoff_label("") == "" and home.kickoff_label("x") == ""
          and home.short_kick("") == "",
          "an unfiled kickoff renders as nothing")
    check(home.kickoff_label(_iso(2026, 9, 9, 0, 0)) == "Wed 9/9 (time not filed)"
          and home.short_kick(_iso(2026, 9, 9, 0, 0)) == "Wed 9/9",
          "a midnight stamp renders as the day and 'time not filed'")
    check(home.today_label(_dt(2026, 9, 5, 8, 0)) == "Sat Sep 5",
          "today reads 'Sat Sep 5'")
    check(home.status_code("Questionable") == "Q" and home.status_code("Out") == "OUT"
          and home.status_code("Injured Reserve") == "IR"
          and home.status_code("Something Long") == "SOME…"
          and home.status_code("") == "",
          "status_code: Q, OUT, IR, an unknown word trimmed, nothing for none")

    m = {"opponent": "SEA", "pos": "WR", "pa_per_game": 26.3, "pa_rank": 29,
         "pa_of": 32, "basis": "2025 season, 17 games"}
    line = home.short_matchup(m)
    check("4th-stingiest of 32" in line and "2025 season" in line,
          "short_matchup inverts the rank correctly and keeps the basis")
    check(home.short_matchup({"reason": "on bye"}) == "on bye",
          "an ungraded matchup falls back to its reason")

    check(home.anchor_id("espn-1", 3) == "p-espn-1-3"
          and "/" not in home.anchor_id("a/b", 1),
          "row anchors are stable, league-scoped, and cannot escape")
    check(home.chip_key("START") == "start" and home.chip_key("EVEN") == "even"
          and home.chip_key(None) is None,
          "the consensus verdict maps onto the chip's key; None stays None")

    snap = clean_snapshot()
    check(home.lineup_total(snap) == (25.0, 2, 2),
          "lineup_total sums starters' projections and counts what it rests on")
    snap["starters"].append(open_slot())
    check(home.lineup_total(snap) == (25.0, 2, 2),
          "...ignoring open slots")

    check(home.short_labels([clean_snapshot()]) == {"Fixture League": "ESPN"},
          "a single league is labelled by its platform")
    two = [clean_snapshot(), clean_snapshot()]
    two[1].update({"name": "Other League"})
    check(home.short_labels(two) == {"Fixture League": "Fixture League",
                                     "Other League": "Other League"},
          "...two leagues on the SAME platform fall back to their names")

    items = [{"urgency": "week", "locked": False, "severity": "warn", "league": "a"},
             {"urgency": "now", "locked": True, "severity": "bad", "league": "a"},
             {"urgency": "now", "locked": False, "severity": "warn", "league": "b"},
             {"urgency": "now", "locked": False, "severity": "bad", "league": "b"}]
    got = sorted(items, key=home.item_sort_key)
    check([(i["urgency"], i["locked"], i["severity"]) for i in got] ==
          [("now", False, "bad"), ("now", False, "warn"), ("now", True, "bad"),
           ("week", False, "warn")],
          "item_sort_key: shelf, then live before locked, then critical first")
    check(home.is_unanimous(row("x")) and not home.is_unanimous(row("x", status="Out"))
          and not home.is_unanimous(row("x", lean=None))
          and not home.is_unanimous(open_slot()),
          "is_unanimous: a calm row only - a status, an unfiled lean or an "
          "open slot is never quiet")


def main():
    print("LANDING PAGE v3 ACCEPTANCE TEST")
    test_renders()
    test_signals()
    test_inbox()
    test_urgency()
    test_sidebar_and_stack()
    test_lock_muting()
    test_cross_league()
    test_honesty()
    test_week_strip()
    test_league_cards()
    test_roster_rows()
    test_exposure()
    test_pulse_and_jump()
    test_design_system()
    test_ui_bridge()
    test_mobile()
    test_escaping()
    test_write_discipline()
    test_host_config()
    test_helpers()
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d of %d FAILURE(S):" % (len(FAILURES), CHECKS[0])))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
