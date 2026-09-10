#!/usr/bin/env python3
"""Acceptance test: THE TRADE DESK (engine/tradedesk.py).

Pure checks first - the depth meter mapping, the snapshot path guard, the
write-once snapshot, the trend arithmetic, one proposal card rendered from
a synthetic target. Then two LIVE renders from the real league data, chosen
because they are opposite coverage cases:

  espn-1      full - 8 of 8 rosters known, so the grid carries a column per
              team with mine first, the needs matrix is 8 x 4, proposals are
              nameable and the waiver stacks name rivals;
  yahoo-main  partial - 1 of 10 rosters known, so the page renders MY
              column, the coverage line and the call to action, and invents
              nothing about the nine unknown teams.

Then a synthetic three-team league in a throwaway project root walks the
needs snapshot through two weeks with a real roster move between them, so
the week-over-week deltas are computed, not staged.

NO NETWORK, EVER: urllib.request.urlopen is replaced for the whole run and
every feed (market, rest-of-season points, xFP, trending) is injected.
EVERY WRITE LANDS IN A tempfile.mkdtemp(): the html goes to an explicit
out_path, the needs snapshot to an explicit cache_dir, and the module's
default cache directory is redirected as well, so a code path that forgot
its argument would still miss data/cache. The production league yamls,
roster files, the espn-1 capture, data/sources.yaml and every
league-needs-* file already in data/cache are byte- and mtime-checked
untouched at the end.

Three checks exist because this page could lie:

  WRITE ONCE - a second render (and a render over a corrupt file) leaves
  the week's snapshot byte- and mtime-identical. A rewritten snapshot would
  erase the very history the trend card is for.
  NO TREND FROM ONE WEEK - with one snapshot the card says "trend needs 2+
  weeks" and draws no table; the deltas appear only once two weeks exist.
  NOTHING INVENTED - the partial league renders exactly one column and
  one needs row, and no placeholder team name anywhere.

    .venv/bin/python tests/tradedesk_test.py
"""

import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import tradedesk, trades, ui                    # noqa: E402
from engine.models import LeagueConfig, load_players        # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


# --- isolation: no network, no production write ------------------------------

class NetworkAttempted(Exception):
    pass


def _no_urlopen(*args, **kwargs):
    target = args[0] if args else "?"
    raise NetworkAttempted("network call attempted: %r"
                           % getattr(target, "full_url", target))


urllib.request.urlopen = _no_urlopen      # every engine module calls it here

SCRATCH = tempfile.mkdtemp(prefix="tradedesk-test-")
ORIG_CACHE_DIR = tradedesk.CACHE_DIR
tradedesk.CACHE_DIR = os.path.join(SCRATCH, "default-cache")

REAL_CACHE = os.path.join(HERE, "data", "cache")
WATCHED = [os.path.join(HERE, p) for p in (
    "leagues/espn-1.yaml", "leagues/yahoo-main.yaml",
    "data/rosters/espn-1.yaml", "data/rosters/yahoo-main.yaml",
    "data/league-espn-1.json", "data/sources.yaml")]


def _md5(path):
    if not os.path.exists(path):
        return None
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def _stat(path):
    return (_md5(path), os.stat(path).st_mtime_ns
            if os.path.exists(path) else None)


def _real_needs_listing():
    if not os.path.isdir(REAL_CACHE):
        return []
    return sorted((n, os.stat(os.path.join(REAL_CACHE, n)).st_mtime_ns)
                  for n in os.listdir(REAL_CACHE)
                  if n.startswith(tradedesk.SNAPSHOT_STEM + "-"))


PRODUCTION_BEFORE = dict((p, _stat(p)) for p in WATCHED)
NEEDS_BEFORE = _real_needs_listing()


# --- fixtures -----------------------------------------------------------------

def synthetic_feeds(players):
    """Every feed build_desk would otherwise fetch, from the pool itself."""
    market = {}
    for p in players:
        if p.pos in trades.MARKET_POSITIONS:
            market[p.key] = max(50.0, 10000.0 - 40.0 * float(p.rank))
    ros = dict((p.key, float(p.proj_points or 0.0)) for p in players)
    return {"market": market, "ros_map": ros, "xfp": ({}, ""),
            "trending": {}, "market_note": "synthetic market (test feed)"}


_SVG_NS = "http://www.w3.org/2000/svg"
_ALLOWED_URLS = (_SVG_NS, "http://127.0.0.1:8787/")
FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171")
SECTIONS = (("grid", "League grid"), ("needs", "Needs matrix"),
            ("targets", "Trade targets"), ("waivers", "Waiver competition"),
            ("trend", "Needs over time"))


def _section(html, id_):
    start = html.find('<section class="wr-card td-sec" id="%s">' % id_)
    if start < 0:
        return ""
    end = html.find("<section", start + 10)
    if end < 0:
        end = html.find("</main>", start)
    return html[start:end]


def _columns(html):
    """[(team name, mine)] in grid order, from the column heads."""
    out = []
    for me, inner in re.findall(
            r'<th class="td-th( td-me)?" scope="col"><span class="td-th-name">'
            r'(.*?)</span><span class="td-th-sub">', html):
        inner = inner.replace('<span class="td-you">you</span>', "")
        name = re.sub(r"<[^>]+>", "", inner).strip()
        out.append((name, bool(me)))
    return out


def _main_is_xml(html):
    m = re.search(r"<main class=\"wr-page[^\"]*\">.*?</main>", html, re.S)
    if not m:
        return False, "no <main>"
    frag = m.group(0).replace("<br>", "<br/>")
    try:
        ET.fromstring(frag)
        return True, ""
    except ET.ParseError as exc:
        return False, str(exc)


def assert_page(html, label):
    check(html.startswith("<!doctype html>"),
          "%s: page is a full document" % label)
    for id_, title in SECTIONS:
        check(_section(html, id_) != "" and title in _section(html, id_),
              "%s: section present: %s" % (label, title))
    low = html.lower()
    _shell_scripts = (ui.shell("home", None, 1, ()).lower().count("<script")
                      + ui.style_tag().lower().count("<script"))
    check(low.count("<script") <= _shell_scripts,
          "%s: no script beyond the shell's own (theme toggle, preferences boot) (got %d, shell %d)"
          % (label, low.count("<script"), _shell_scripts))
    check("<script src" not in low, "%s: no script is fetched" % label)
    check("<script src" not in low, "%s: no fetched script" % label)
    # engine/pwa.py adds two link relations through ui.style_tag() so the
    # page installs on a phone; neither is fetched to paint it. A
    # stylesheet, a favicon or a preload still fails - see board_test.
    _links = re.findall(r"<link\b[^>]*>", low)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in _links),
          "%s: the only <link>s are the app manifest and the touch icon, "
          "neither fetched at open (%s)" % (label, _links or "none"))
    check(" src=" not in low,
          "%s: no embedded resource (faces and fonts are data: URIs in CSS)"
          % label)
    scrubbed = html
    for u in _ALLOWED_URLS:
        scrubbed = scrubbed.replace(u, "")
    check(not re.search(r"https?://", scrubbed),
          "%s: no URL beyond the SVG namespace and the local Model Settings "
          "link" % label)
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low, "%s: forbidden colour absent: %s"
              % (label, hx))
    check('class="wr-nav"' in html and "WAR ROOM" in html,
          "%s: the shared shell (navy header) is present" % label)
    check('aria-current="page">Trade Desk</a>' in html,
          "%s: the shell marks Trade Desk as the current page" % label)
    check(html.find('class="wr-nav"') < html.find('<main class="wr-page'),
          "%s: shell first in <body>, content in <main class=\"wr-page\">"
          % label)
    check("<style>" in html and "--wr-canvas:" in html
          and "--wr-rule:" in html,
          "%s: ui.style_tag() tokens embedded" % label)
    own_css = html[html.find(".td-page"):html.find("</style>\n</head>")]
    check(own_css and not re.search(r"#[0-9a-fA-F]{3,8}\b", own_css),
          "%s: the page's own CSS carries no hex colour - tokens only"
          % label)
    check(html.count("<table") == html.count('<div class="wr-scroll"><table'),
          "%s: every table scrolls inside .wr-scroll (no page-wide "
          "horizontal scroll)" % label)
    check("min-height: 44px" in html, "%s: tap targets sized 44px" % label)
    ok, why = _main_is_xml(html)
    check(ok, "%s: <main> is well-formed markup (escaping intact)%s"
          % (label, "" if ok else " - " + why))
    check('class="wr-kicker"' in html and 'class="wr-h1 wr-display"' in html,
          "%s: kicker + display headline" % label)


# --- [1] pure: depth mapping ----------------------------------------------------

def test_depth():
    print("\n[1] depth meter: startable net -> five grades")
    for net, level in ((-5, 1), (-2, 1), (-1, 2), (0, 3), (1, 4), (2, 5),
                       (7, 5), ("junk", 3), (None, 3)):
        check(tradedesk.depth_level(net) == level,
              "net %r -> level %d" % (net, level))
    check(tradedesk.depth_grade(2) == "smash"
          and tradedesk.depth_grade(0) == "neutral"
          and tradedesk.depth_grade(-2) == "avoid",
          "grades map onto ui.matchup_meter's five words")
    m = tradedesk.depth_meter("RB", 1)
    check('class="wr-meter' in m and "RB depth 4/5" in m,
          "meter is ui.matchup_meter titled 'RB depth 4/5'")
    check(m.count("wr-meter-on") == 4 and "SMASH" not in m
          and "GOOD" not in m,
          "four segments lit, matchup vocabulary hidden")
    lo = tradedesk.depth_meter("WR", -2)
    check("WR depth 1/5" in lo and lo.count("wr-meter-on") == 1
          and "2 WR short" in lo, "a two-deep hole lights one segment")
    check("exactly covered" in tradedesk.depth_title("TE", 0),
          "zero net reads as exactly covered")
    check(tradedesk.fmt_net(-1) == "−1" and tradedesk.fmt_net(0) == "0"
          and tradedesk.fmt_net(3) == "+3"
          and tradedesk.fmt_net(None) == "—",
          "net formatting: minus sign, plus sign, dash for unknown")


# --- [2] pure: snapshot path + write-once ---------------------------------------

def test_snapshot_paths():
    print("\n[2] snapshot path: data/cache and nowhere else")
    tmp = tempfile.mkdtemp(prefix="td-path-", dir=SCRATCH)
    p = tradedesk.snapshot_path("espn-1", 3, tmp)
    check(os.path.basename(p) == "league-needs-espn-1-week3.json"
          and os.path.dirname(p) == os.path.abspath(tmp),
          "league-needs-<league>-week<N>.json directly under the cache dir")
    check(ORIG_CACHE_DIR.endswith(os.path.join("data", "cache")),
          "the production default is data/cache")
    check(os.path.dirname(tradedesk.snapshot_path("x", 1))
          == os.path.abspath(tradedesk.CACHE_DIR),
          "no cache_dir -> the module default")
    for bad_id in ("../evil", "a/b", "", "x y", ".hidden"):
        try:
            tradedesk.snapshot_path(bad_id, 1, tmp)
            check(False, "league id %r rejected" % bad_id)
        except ValueError:
            check(True, "league id %r rejected" % bad_id)
    for bad_week in (0, -1, "zero"):
        try:
            tradedesk.snapshot_path("ok", bad_week, tmp)
            check(False, "week %r rejected" % (bad_week,))
        except ValueError:
            check(True, "week %r rejected" % (bad_week,))


def _team(slot, name, mine, net, known=10):
    surplus = [(p, n) for p, n in net.items() if n > 0]
    holes = [(p, -n) for p, n in net.items() if n < 0]
    return {"slot": slot, "name": name, "mine": mine, "known": known,
            "net": dict(net), "surplus": surplus, "holes": holes}


def test_write_once():
    print("\n[3] snapshot: written once, never rewritten")
    tmp = tempfile.mkdtemp(prefix="td-snap-", dir=SCRATCH)
    net = {"QB": 0, "RB": 1, "WR": -1, "TE": 0}
    doc = tradedesk.snapshot_doc("t1", 2, 2026,
                                 [_team("1", "Me", True, net)], (1, 3))
    path, written = tradedesk.write_snapshot_if_absent(doc, tmp)
    check(written and os.path.exists(path)
          and path == tradedesk.snapshot_path("t1", 2, tmp),
          "first write lands at the snapshot path")
    on_disk = json.load(open(path))
    check(on_disk["teams"]["1"]["net"]["RB"] == 1
          and on_disk["teams"]["1"]["surplus"] == [["RB", 1]]
          and on_disk["teams"]["1"]["holes"] == [["WR", 1]]
          and on_disk["coverage"] == {"known": 1, "expected": 3}
          and on_disk["week"] == 2 and on_disk["league"] == "t1",
          "the document carries net, tags and coverage per known team")
    before = _stat(path)
    changed = tradedesk.snapshot_doc(
        "t1", 2, 2026, [_team("1", "Me", True, {"QB": 2, "RB": 2, "WR": 2,
                                                 "TE": 2})], (1, 3))
    path2, written2 = tradedesk.write_snapshot_if_absent(changed, tmp)
    check(path2 == path and not written2 and _stat(path) == before,
          "a second write for the same week is refused; file byte- and "
          "mtime-identical")
    check(sorted(os.listdir(tmp)) == [os.path.basename(path)],
          "no temp file left behind, nothing else written")

    corrupt = tradedesk.snapshot_path("t1", 3, tmp)
    with open(corrupt, "w") as fh:
        fh.write("not json")
    c_before = _stat(corrupt)
    _, written3 = tradedesk.write_snapshot_if_absent(
        tradedesk.snapshot_doc("t1", 3, 2026, [], (0, 3)), tmp)
    check(not written3 and _stat(corrupt) == c_before,
          "even a corrupt week file is never rewritten")
    docs, bad = tradedesk.load_snapshots("t1", tmp)
    check([d["week"] for d in docs] == [2] and len(bad) == 1
          and "week3" in bad[0] and "could not be read" in bad[0],
          "the corrupt file is reported by name and skipped, not dropped")

    with open(tradedesk.snapshot_path("t2", 1, tmp), "w") as fh:
        json.dump(tradedesk.snapshot_doc("t2", 1, 2026, [], (0, 2)), fh)
    with open(tradedesk.snapshot_path("t1", 9, tmp), "w") as fh:
        json.dump(dict(tradedesk.snapshot_doc("t1", 9, 2026, [], (0, 2)),
                       week=4), fh)
    docs, bad = tradedesk.load_snapshots("t1", tmp)
    check([d["week"] for d in docs] == [2] and len(bad) == 2
          and any("says week 4" in b for b in bad),
          "another league's file is ignored; a file whose week disagrees "
          "with its name is skipped with a note")


# --- [4] pure: trend arithmetic -------------------------------------------------

def _snap(week, teams):
    return {"league": "t", "week": week, "season": 2026,
            "positions": ["QB", "RB", "WR", "TE"],
            "coverage": {"known": len(teams), "expected": 3},
            "teams": teams}


def test_trend_rows():
    print("\n[4] trend rows: deltas only from two or more weeks")
    wk1 = _snap(1, {"1": {"name": "Me", "mine": True,
                          "net": {"QB": 0, "RB": 1, "WR": -1, "TE": 0}},
                    "2": {"name": "Rival", "mine": False,
                          "net": {"QB": 0, "RB": 0, "WR": 0, "TE": 0}}})
    wk2 = _snap(2, {"2": {"name": "Rival", "mine": False,
                          "net": {"QB": 0, "RB": 0, "WR": 0, "TE": 0}},
                    "1": {"name": "Me", "mine": True,
                          "net": {"QB": 0, "RB": -1, "WR": 0, "TE": 0}},
                    "3": {"name": "Late", "mine": False,
                          "net": {"QB": 1, "RB": 0, "WR": 0, "TE": 0}}})
    one = tradedesk.trend_rows([wk1])
    check(one["weeks"] == [1] and not one["enough"]
          and all(c["dir"] is None and tradedesk.TREND_NOTE in c["label"]
                  for r in one["rows"] for c in r["cells"].values()),
          "one week: not enough, every cell says so, no direction")
    empty = tradedesk.trend_rows([])
    check(empty == {"weeks": [], "enough": False, "rows": []},
          "no snapshots: empty, not fabricated")

    two = tradedesk.trend_rows([wk2, wk1])
    check(two["weeks"] == [1, 2] and two["enough"],
          "two weeks: sorted by week, enough for a trend")
    check([r["slot"] for r in two["rows"]] == ["1", "2", "3"]
          and two["rows"][0]["mine"], "my team first, then slot order")
    me = two["rows"][0]["cells"]
    check(me["RB"]["dir"] == "up" and me["RB"]["first"] == 1
          and me["RB"]["last"] == -1 and me["RB"]["delta"] == -2
          and me["RB"]["label"] == "RB need ↑ since wk 1",
          "fewer startable RB than week 1 -> 'RB need ↑ since wk 1'")
    check(me["WR"]["dir"] == "down"
          and me["WR"]["label"] == "WR need ↓ since wk 1",
          "hole closed -> 'WR need ↓ since wk 1'")
    check(me["QB"]["dir"] == "flat"
          and me["QB"]["label"] == "QB steady since wk 1",
          "unchanged -> steady")
    late = two["rows"][2]["cells"]["QB"]
    check(late["dir"] is None and late["series"] == [None, 1]
          and tradedesk.TREND_NOTE in late["label"],
          "a team known for one week only carries no direction")


# --- [5] pure: one proposal card ------------------------------------------------

def test_target_card():
    print("\n[5] proposal card: both valuations, both sides' pts/wk")
    t = {"team": "Rival <Co>", "slot": "2", "shape": "+1 startable RB, -1 WR",
         "give": {"name": "A & B", "pos": "WR", "team": "KC", "key": "a|WR"},
         "get": {"name": "C Dee", "pos": "RB", "team": "SF", "key": "c|RB"},
         "give_market": 4321.4, "get_market": 5000, "give_proj": 4000,
         "get_proj": 5200, "market_pct": 0.157, "proj_pct": 0.3,
         "blended_pct": 0.22, "my_delta_wk": 1.26, "their_delta_wk": -0.8,
         "flag": "decline", "note": "LOPSIDED our way - they likely decline",
         "rationale": "they can spare a RB we are short of; we pay from WR "
                      "depth", "accept_odds": 0.15, "systems_disagree": True,
         "command": 'python -m engine.trades --league x --offer '
                    '"give: A & B | get: C Dee"'}
    html = tradedesk.render_target_card(t, 3)
    check(html.startswith('<article class="td-offer td-offer-decline">'),
          "a likely-decline card carries the gold rule class")
    check("Rival &lt;Co&gt;" in html and "A &amp; B" in html
          and "A & B" not in html, "names and the command are escaped")
    check(html.count('wr-pill-l">market<') == 2
          and html.count('wr-pill-l">our ROS<') == 2
          and "4,321" in html and "5,000" in html and "5,200" in html,
          "give and get each carry market AND our-ROS valuations")
    check('td-imp-l">you</span><span class="wr-num">+1.3</span> pts/wk'
          in html
          and 'td-imp-l">them</span><span class="wr-num">−0.8</span> '
              'pts/wk' in html,
          "pts/wk impact for BOTH sides, as .wr-num")
    check("+16%" in html and "+30%" in html and "15%" in html,
          "market %, projection % and acceptance odds shown")
    check("<b>they likely decline</b>" in html,
          "the honesty flag is spelled out")
    check("disagree hard" in html and 'class="wr-icon' in html,
          "market-vs-projection dissent flagged with the dissent icon")
    check('<code class="td-cmd wr-mono">python -m engine.trades' in html,
          "the CLI evaluator command rides on the card")
    check('<span class="wr-pos">WR</span>' in html
          and '<span class="wr-pos">RB</span>' in html,
          "position badges on both sides")
    t2 = dict(t, flag="", note="fair value, but their starters do not gain",
              systems_disagree=False)
    h2 = tradedesk.render_target_card(t2, 1)
    check("they likely decline" not in h2 and "td-offer-decline" not in h2
          and "fair value" in h2, "an unflagged card carries no flag")
    check("worth asking" in tradedesk.render_target_card(
        dict(t, flag="lopsided"), 1)
        and "we overpay" in tradedesk.render_target_card(
            dict(t, flag="overpay"), 1),
        "lopsided-but-sellable and overpay read as themselves")


# --- [6] live: espn-1 (full coverage) ------------------------------------------

def test_live_espn():
    print("\n[6] live render: espn-1 (8 of 8 rosters known)")
    tmp = tempfile.mkdtemp(prefix="td-espn-", dir=SCRATCH)
    cache = os.path.join(tmp, "cache")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    feeds = synthetic_feeds(players)
    store = json.load(open(os.path.join(HERE, "data", "league-espn-1.json")))
    names = [store["teams"][s]["name"] for s in sorted(store["teams"],
                                                       key=int)]

    desk = tradedesk.build_desk("espn-1", 1, cache_dir=cache, feeds=feeds)
    html = tradedesk.render_page(desk)
    check(desk["coverage"]["text"] == "8 of 8 rosters known"
          and desk["coverage"]["complete"]
          and "8 of 8 rosters known" in html,
          "coverage line rendered: 8 of 8 rosters known")
    check(not desk["errors"], "no section degraded (errors: %s)"
          % desk["errors"])
    assert_page(html, "espn-1")

    cols = _columns(html)
    check([n for n, _ in cols] == names,
          "grid: one column per known team, in slot order (%d)" % len(cols))
    check(cols and cols[0][1] and cols[0][0] == store["teams"]["1"]["name"]
          and not any(m for _, m in cols[1:]),
          "my team is the first column and the only one marked mine")
    grid = _section(html, "grid")
    check('class="td-th td-me"' in grid
          and "inset 0 3px 0 var(--wr-rule)" in html,
          "my column carries the gold rule")
    check(">starters<" in grid and ">bench<" in grid
          and all('wr-sticky">%s<' % s in grid
                  for s in ("QB", "RB", "WR", "TE", "FLEX", "K", "DST")),
          "starters over bench, one row per slot, slot column sticky")
    check(re.search(r"hole −\d [A-Z]+", grid)
          and re.search(r"surplus \+\d [A-Z]+", grid),
          "SURPLUS / HOLE tags from trades.positional_net on the heads")
    check("engine/trades.py positional_net" in grid,
          "the tags say where they come from")
    if desk["exposure"]["available"]:
        check(grid.count(">also yours<") >= 1
              and "you also hold him in" in grid,
              "players I also hold in the other league are marked")
    else:
        check("unavailable, not empty" in grid,
              "no other roster on file is said, not shown as empty")
    check("UNKNOWN, not a free agent" in grid,
          "positive-only reading stated")

    needs = _section(html, "needs")
    check(needs.count('<td class="td-nm"') == 8 * 4,
          "needs matrix: 8 teams x QB/RB/WR/TE cells")
    check(len(re.findall(r'title="(?:QB|RB|WR|TE) depth [1-5]/5', needs))
          == 32 and needs.count('<span class="wr-meter ') == 32
          and needs.count("wr-meter-on") + needs.count("wr-meter-off")
          == 32 * 5,
          "every cell is a five-segment depth meter with a depth title")
    check('class="td-me-row"' in needs and "down the column" in needs,
          "my row marked; the column read is footed")

    targets = desk["targets"]
    tsec = _section(html, "targets")
    n = len(targets)
    check(n >= 1, "synthetic feeds still yield proposals (%d)" % n)
    check(tsec.count('<article class="td-offer') == n,
          "one card per proposal")
    cards = tsec.split('<article class="td-offer')[1:]
    check(all(c.count('wr-pill-l">market<') == 2
              and c.count('wr-pill-l">our ROS<') == 2
              and 'td-imp-l">you</span>' in c and 'td-imp-l">them</span>' in c
              and c.count("</span> pts/wk</span>") == 2 for c in cards),
          "every card: both valuations for give and get, pts/wk for both "
          "sides")
    check(tsec.count("<b>they likely decline</b>")
          == sum(1 for t in targets if t["flag"] == "decline"),
          "the decline flag appears exactly where trades.py raised it")
    check(all(t["team"] in names[1:] for t in targets),
          "every proposal names a known rival, never me")
    check(tsec.count("python -m engine.trades --league espn-1 --offer") >= n
          and "offer evaluator stays in the CLI" in tsec,
          "each card carries its CLI command; the page stays read-only")
    check(grid.count('td-mark-tgt" title=')
          == len(set(t["get"]["key"] for t in targets))
          and grid.count('td-mark-offer" title=')
          == len(set(t["give"]["key"] for t in targets)),
          "TARGET / OFFER marks in the grid match the proposals")

    w = desk["waivers"]
    wsec = _section(html, "waivers")
    check(not w["err"] and len(w["rows"]) >= 1
          and all(r["pos"] in ("QB", "RB", "WR", "TE") for r in w["rows"]),
          "waiver competition read over %d skill-position candidates"
          % len(w["rows"]))
    check(wsec.count("<tr>") == len(w["rows"]) + 1,
          "one table row per candidate")
    stacked = [rv["name"] for r in w["rows"] for rv in r["rivals"]]
    check(all(s in names[1:] for s in stacked),
          "every stacked name is a known rival team (%d names)"
          % len(stacked))
    check("K/DST streamers" in wsec and "board-espn-1-week1.html" in wsec,
          "streamers are pointed at the board, not faked a need")
    check("never a claim about what anyone will do" in wsec,
          "the stack is described as a read, not a prediction")

    tr = desk["trend"]
    tsec2 = _section(html, "trend")
    check(tr["weeks"] == [1] and not tr["enough"]
          and tradedesk.TREND_NOTE in tsec2
          and "only week 1 is on file" in tsec2
          and '<table class="wr-table td-trend"' not in tsec2,
          "one week on file: 'trend needs 2+ weeks', no table drawn")
    snap = tradedesk.snapshot_path("espn-1", 1, cache)
    check(tr["snapshot"] == {"path": snap, "written": True, "skipped": ""}
          and os.path.exists(snap),
          "week-1 snapshot written to the cache dir")
    doc = json.load(open(snap))
    check(doc["league"] == "espn-1" and doc["week"] == 1
          and sorted(doc["teams"], key=int) == [str(i) for i in range(1, 9)]
          and doc["coverage"] == {"known": 8, "expected": 8}
          and doc["teams"]["1"]["mine"]
          and all(set(t["net"]) == {"QB", "RB", "WR", "TE"}
                  for t in doc["teams"].values()),
          "snapshot: every known team's depth, tags and coverage")
    check(doc["teams"]["1"]["holes"]
          == [[p, n] for p, n in desk["teams"][0]["holes"]],
          "snapshot tags equal the page's")
    before = _stat(snap)

    out = os.path.join(tmp, "tradedesk-espn-1-week1.html")
    path = tradedesk.write_tradedesk("espn-1", 1, out_path=out,
                                     cache_dir=cache, feeds=feeds)
    html2 = open(path).read()
    check(path == out and html2.startswith("<!doctype html>")
          and _columns(html2) == cols,
          "write_tradedesk writes the page to the given path")
    check(_stat(snap) == before,
          "re-render leaves the snapshot byte- and mtime-identical")
    check("already on file" in _section(html2, "trend"),
          "the second render says the snapshot was left untouched")
    check(sorted(os.listdir(cache)) == [os.path.basename(snap)]
          and sorted(os.listdir(tmp)) == ["cache", os.path.basename(out)],
          "nothing written but the page and the one snapshot")
    check(not os.path.exists(tradedesk.CACHE_DIR)
          or not os.listdir(tradedesk.CACHE_DIR),
          "the default cache dir was not used when cache_dir is given")
    check("never rewritten" in html and "advances no baseline" in html,
          "the footer states the write discipline")


# --- [7] live: yahoo-main (partial coverage) -----------------------------------

def test_live_yahoo():
    print("\n[7] live render: yahoo-main (1 of 10 rosters known)")
    tmp = tempfile.mkdtemp(prefix="td-yahoo-", dir=SCRATCH)
    cache = os.path.join(tmp, "cache")
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "yahoo-main.yaml"))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    desk = tradedesk.build_desk("yahoo-main", 1, cache_dir=cache,
                                feeds=synthetic_feeds(players))
    html = tradedesk.render_page(desk)
    assert_page(html, "yahoo-main")
    check(desk["coverage"]["text"] == "1 of 10 rosters known"
          and not desk["coverage"]["complete"]
          and html.count("1 of 10 rosters known") >= 2,
          "coverage line rendered: 1 of 10 rosters known")
    check(not desk["errors"], "no section degraded (errors: %s)"
          % desk["errors"])
    cols = _columns(html)
    check(len(cols) == 1 and cols[0][1] and "Kid" in cols[0][0],
          "exactly one column - mine - and it is marked mine")
    check(tradedesk.CTA in html.replace("&#x27;", "'")
          and "Model Settings" in html,
          "call to action: paste the league rosters in Model Settings")
    check(not desk["rivals_available"]
          and "RIVAL ROSTERS UNKNOWN" in _section(html, "targets")
          and "no offer is invented" in _section(html, "targets")
          and _section(html, "targets").count("<article") == 0,
          "no rival named, no offer invented")
    check("Constructs" in _section(html, "targets")
          and _section(html, "targets").count("<li>") >= 1,
          "shapes to shop still stand")
    check("competition cannot be read" in _section(html, "waivers")
          and "board-yahoo-main-week1.html" in _section(html, "waivers"),
          "waiver competition says why and points at the board")
    needs = _section(html, "needs")
    check(needs.count('<td class="td-nm"') == 4
          and needs.count("<tr") == 3,
          "needs matrix: one row (mine) x four cells, head and foot")
    check(not re.search(r"Team (?:[2-9]|10)\b", html)
          and html.count('<th class="td-th') == 1,
          "nothing invented about the nine unknown teams")
    check(tradedesk.TREND_NOTE in _section(html, "trend"),
          "one week on file: trend needs 2+ weeks")
    snap = tradedesk.snapshot_path("yahoo-main", 1, cache)
    doc = json.load(open(snap))
    check(list(doc["teams"]) == ["1"] and doc["teams"]["1"]["mine"]
          and doc["coverage"] == {"known": 1, "expected": 10},
          "snapshot carries only the one known roster and says 1 of 10")


# --- [8] synthetic league: two weeks, a real move between them ----------------

SYNTH_YAML = """id: synth
name: Synth League
platform: test
teams: 3
my_slot: 1
waiver_mode: faab
roster_spots: [QB, RB, RB, WR, WR, TE, W/R/T, K, DEF, BN, BN, BN]
rounds: 12
rankings_csv: data/rankings.csv
scoring: {reception: 1}
team_names: [Me Myself, Rival Two, Rival Three]
"""


_FIRST = ("Amos", "Bert", "Cyrus", "Dane", "Eli", "Finn", "Gus", "Hal",
          "Ike", "Jon", "Kai", "Lou", "Max", "Ned", "Otto", "Paz", "Quin",
          "Rex", "Sid", "Tom", "Uri", "Vic", "Wes", "Xan", "Yul", "Zed")
_LAST = ("Arden", "Baird", "Cole", "Dunn")
_NFL = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
        "DET", "GB", "HOU", "IND", "JAX", "KC")
_DEFS = (("Denver Defense", "DEN"), ("Houston Defense", "HOU"),
         ("Chicago Defense", "CHI"), ("Seattle Defense", "SEA"))


def _synthetic_pool_csv(path):
    """A deterministic rankings pool - 8 QB, 30 RB, 30 WR, 8 TE, 4 K, 4 DEF
    with projections falling in even steps - so replacement levels, and
    every startable net downstream, are a function of league shape alone
    and never of whatever the real rankings say this week."""
    rows, k = [], 0
    for pos, n, top, step in (("QB", 8, 400.0, 12.0), ("RB", 30, 340.0, 8.0),
                              ("WR", 30, 335.0, 8.0), ("TE", 8, 240.0, 12.0),
                              ("K", 4, 170.0, 5.0), ("DEF", 4, 130.0, 5.0)):
        for i in range(n):
            if pos == "DEF":
                name, team = _DEFS[i]
            else:
                name = "%s %s" % (_FIRST[k % len(_FIRST)],
                                  _LAST[k // len(_FIRST)])
                team = _NFL[k % len(_NFL)]
                k += 1
            rows.append((name, pos, team, top - step * i))
    rows.sort(key=lambda r: -r[3])
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "name", "pos", "team", "bye", "tier", "adp",
                    "adp_stdev", "proj_points", "notes", "flags", "ecr",
                    "ecr_sd"])
        for i, (name, pos, team, proj) in enumerate(rows, start=1):
            w.writerow([i, name, pos, team, 5 + i % 9, 1 + i // 12, float(i),
                        1.0, "%.1f" % proj, "", "", "", ""])


def _row(p):
    return {"player": p.name, "pos": p.pos, "nfl": p.team, "bye": p.bye,
            "proj": p.proj_points}


def _write_synth(root, rosters):
    """rosters = {slot: (name, [Player])}; writes the store + my yaml."""
    store = {"league": "synth", "season": 2026, "teams": dict(
        (slot, {"name": name, "players": [_row(p) for p in ps]})
        for slot, (name, ps) in rosters.items())}
    with open(os.path.join(root, "data", "league-synth.json"), "w") as fh:
        json.dump(store, fh, indent=1)
    name, mine = rosters["1"]
    with open(os.path.join(root, "data", "rosters", "synth.yaml"), "w") as fh:
        fh.write("league: synth\nname: %s\nsize: 12\nplayers:\n%s"
                 % (name, "".join("- %s\n" % p.name for p in mine)))


def test_synthetic_two_weeks():
    print("\n[8] synthetic league: needs over two weeks, one real move")
    root = tempfile.mkdtemp(prefix="td-synth-", dir=SCRATCH)
    for d in ("leagues", "data", os.path.join("data", "rosters"), "cache"):
        os.makedirs(os.path.join(root, d))
    with open(os.path.join(root, "leagues", "synth.yaml"), "w") as fh:
        fh.write(SYNTH_YAML)
    _synthetic_pool_csv(os.path.join(root, "data", "rankings.csv"))
    league = LeagueConfig.load(os.path.join(root, "leagues", "synth.yaml"))
    players = load_players(os.path.join(root, "data", "rankings.csv"))
    repl = trades.replacement_from_pool(league, players)
    check(len(players) == 84 and players[0].rank == 1,
          "fixture: the synthetic pool loads through load_players")

    def top(pos, n):
        return sorted((p for p in players if p.pos == pos),
                      key=lambda p: -float(p.proj_points or 0))[:n]

    def startable(ps):
        return all(float(p.proj_points) > float(repl.get(p.pos, 0.0))
                   for p in ps)
    qb, rb, wr, te = top("QB", 3), top("RB", 8), top("WR", 6), top("TE", 3)
    k, d = top("K", 3), top("DEF", 3)
    # The argument below rests on exactly these being startable by trades.py's
    # own bar (projects above league-wide replacement): my four RB and Rival
    # Two's two RB and two WR. Everything else may fall where it falls.
    check(startable(rb[0:6]) and startable(wr[0:4]),
          "fixture: six RB and four WR sit above replacement (repl %s)"
          % dict((p, round(float(v), 1)) for p, v in repl.items()))
    wk1 = {"1": ("Me Myself", [qb[0]] + rb[0:4] + wr[0:2] + [te[0], k[0], d[0]]),
           "2": ("Rival Two", [qb[1]] + rb[4:6] + wr[2:4] + [te[1], k[1], d[1]]),
           "3": ("Rival Three", [qb[2]] + rb[6:8] + wr[4:6] + [te[2], k[2],
                                                                d[2]])}
    _write_synth(root, wk1)
    kw = dict(data_root=root, roster_dir=os.path.join(root, "data", "rosters"),
              cache_dir=os.path.join(root, "cache"),
              feeds=synthetic_feeds(players))
    desk1 = tradedesk.build_desk("synth", 1, **kw)
    html1 = tradedesk.render_page(desk1)
    check(not desk1["errors"] and desk1["coverage"]["text"]
          == "3 of 3 rosters known", "week 1 builds from the tempdir root "
          "(errors: %s)" % desk1["errors"])
    check([n for n, _ in _columns(html1)]
          == ["Me Myself", "Rival Two", "Rival Three"]
          and _columns(html1)[0][1], "three columns, mine first")
    me1 = desk1["teams"][0]
    check(me1["mine"] and me1["net"]["RB"] == 1
          and ("RB", 1) in me1["surplus"],
          "week 1: four startable RB against two slots and a flex = +1")
    check(desk1["teams"][1]["net"]["WR"] == -1,
          "week 1: Rival Two is one WR short once the flex is charged")
    check(tradedesk.TREND_NOTE in _section(html1, "trend")
          and desk1["trend"]["snapshot"]["written"],
          "week 1 alone: 'trend needs 2+ weeks', snapshot written")
    check(desk1["leagues"] == [("synth", "Synth League")],
          "the league switcher lists the tempdir's leagues only")
    check("no other league roster on file" in _section(html1, "grid"),
          "no exposure file in the tempdir: said, not shown as empty")
    snap1 = tradedesk.snapshot_path("synth", 1, kw["cache_dir"])
    s1 = _stat(snap1)

    # The move: my fourth RB goes to Rival Two. Store and my yaml both say so.
    wk2 = {"1": ("Me Myself", [qb[0]] + rb[0:3] + wr[0:2] + [te[0], k[0], d[0]]),
           "2": ("Rival Two", [qb[1]] + rb[4:6] + [rb[3]] + wr[2:4]
                 + [te[1], k[1], d[1]]),
           "3": wk1["3"]}
    _write_synth(root, wk2)
    desk2 = tradedesk.build_desk("synth", 2, **kw)
    html2 = tradedesk.render_page(desk2)
    tr = desk2["trend"]
    check(not desk2["errors"] and tr["weeks"] == [1, 2] and tr["enough"],
          "week 2: both snapshots read, trend enough")
    check(_stat(snap1) == s1, "the week-1 snapshot is untouched by week 2")
    check(sorted(os.listdir(kw["cache_dir"]))
          == [os.path.basename(snap1),
              os.path.basename(tradedesk.snapshot_path(
                  "synth", 2, kw["cache_dir"]))],
          "exactly two snapshot files, nothing else in the cache dir")
    rows = dict((r["slot"], r) for r in tr["rows"])
    check(rows["1"]["cells"]["RB"]["dir"] == "up"
          and rows["1"]["cells"]["RB"]["label"] == "RB need ↑ since wk 1"
          and rows["1"]["cells"]["RB"]["first"] == 1
          and rows["1"]["cells"]["RB"]["last"] == 0,
          "after giving up an RB: 'RB need ↑ since wk 1' (+1 -> 0)")
    check(rows["2"]["cells"]["WR"]["dir"] == "down"
          and rows["2"]["cells"]["WR"]["label"] == "WR need ↓ since wk 1",
          "Rival Two's flex is now an RB: 'WR need ↓ since wk 1'")
    check(rows["1"]["cells"]["QB"]["label"] == "QB steady since wk 1"
          and all(c["dir"] == "flat" for c in rows["3"]["cells"].values()),
          "untouched positions and the untouched team read steady")
    tsec = _section(html2, "trend")
    check('<table class="wr-table td-trend"' in tsec
          and "RB need ↑ since wk 1" in tsec
          and "WR need ↓ since wk 1" in tsec
          and "+1 → 0" in tsec and 'class="wr-spark"' in tsec
          and "weeks on file: 1, 2" in tsec and ">2 weeks<" in tsec,
          "the trend table renders the deltas with sparklines")
    first_row = tsec.split("<tbody>")[1].split("</tr>")[0]
    check('class="td-me-row"' in first_row and "Me Myself" in first_row,
          "my team is the first trend row")
    assert_page(html2, "synth wk2")
    check(sorted(os.listdir(root)) == ["cache", "data", "leagues"]
          and sorted(os.listdir(os.path.join(root, "data")))
          == ["league-synth.json", "rankings.csv", "rosters"],
          "the tempdir root gained nothing but the cache files")


# --- [9] CLI edges ---------------------------------------------------------------

def test_cli():
    print("\n[9] CLI: one diagnosis line at the edge, never a traceback")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tradedesk.main(["--league", "no-such-league", "--week", "1"])
    out = buf.getvalue()
    check(rc == 1 and "no league yaml" in out and "Traceback" not in out,
          "unknown league: exit 1 with the missing path named")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tradedesk.main(["--league", "espn-1", "--week", "99"])
    check(rc == 1 and "week must be 1-18" in buf.getvalue(),
          "bad week: exit 1 with the valid range")
    msg = tradedesk.render_failure(ValueError("boom"), "espn-1", 2)
    check("could not build the trade desk for espn-1 week 2" in msg
          and "ValueError: boom" in msg and "leagues/espn-1.yaml" in msg,
          "a whole-render failure names the league, week and the files to "
          "check")
    check(tradedesk.default_out_path("espn-1", 3)
          == os.path.join(HERE, "tradedesk-espn-1-week3.html"),
          "default output: tradedesk-<league>-week<N>.html at the root")
    sh = open(os.path.join(HERE, "tradedesk.sh")).read()
    check(os.access(os.path.join(HERE, "tradedesk.sh"), os.X_OK)
          and "python -m engine.tradedesk" in sh and "open \"$page\"" in sh
          and "tail -n 1" in sh,
          "tradedesk.sh is executable, runs the module and opens the last "
          "printed path")


# --- [10] production untouched -------------------------------------------------

def test_readonly():
    print("\n[10] production files untouched")
    for p in WATCHED:
        check(_stat(p) == PRODUCTION_BEFORE[p],
              "%s byte- and mtime-identical" % os.path.relpath(p, HERE))
    check(_real_needs_listing() == NEEDS_BEFORE,
          "data/cache gained or changed no league-needs-* file")
    check(not os.path.exists(tradedesk.CACHE_DIR)
          or not os.listdir(tradedesk.CACHE_DIR),
          "the redirected default cache dir stayed empty")
    for name in ("tradedesk-espn-1-week1.html", "tradedesk-yahoo-main-week1"
                 ".html", "tradedesk-synth-week1.html"):
        path = os.path.join(HERE, name)
        check(not os.path.exists(path)
              or os.stat(path).st_mtime_ns < START_NS,
              "no %s written to the project root by this run" % name)


START_NS = max((os.stat(p).st_mtime_ns for p in WATCHED
                if os.path.exists(p)), default=0)


def main():
    global START_NS
    import time
    START_NS = int(time.time() * 1e9)
    print("TRADE DESK ACCEPTANCE TEST")
    test_depth()
    test_snapshot_paths()
    test_write_once()
    test_trend_rows()
    test_target_card()
    test_live_espn()
    test_live_yahoo()
    test_synthetic_two_weeks()
    test_cli()
    test_readonly()
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
