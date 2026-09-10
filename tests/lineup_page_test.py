#!/usr/bin/env python3
"""Acceptance test: THE LINEUP BUILDER (engine/lineup_page.py).

Pure checks first, on a fixture league and roster of our own construction
(no assertion rides on what leagues/*.yaml says today): the slot order and
numbering, one row per starting slot, exactly one challenger line under a
contested slot and none under an uncontested one, the K and D/ST rows
carrying engine/dk's hold-vs-stream line when dk is importable and the
honest "streaming read unavailable" fallback when it is not (sys.modules
monkeypatch, both directions), the bench showing only competitors by
default, the swap deltas to the tenth, the host verb present and absent,
the phone CSS, the palette, and self-containment. Then two LIVE renders
from the real league data (espn-1 full, yahoo-main partial - my roster
known, no rivals), written into a tempfile.mkdtemp(), with the network
disabled for the whole run so every feed answers from its cache.

READ-ONLY IN FACT: data/cache/espn-owned-snapshot.json, the streaming log,
the source ledger, data/sources.yaml and both roster files are byte- and
mtime-checked across two renders.

    .venv/bin/python tests/lineup_page_test.py
"""

import contextlib
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import engine                                                # noqa: E402
from engine import lineup_page as lp                         # noqa: E402
from engine import ui                                        # noqa: E402
from engine.models import LeagueConfig                       # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _md5(path):
    if not os.path.exists(path):
        return None
    return hashlib.md5(open(path, "rb").read()).hexdigest()


# --- no network, ever --------------------------------------------------------

def _no_urlopen(*args, **kwargs):
    raise urllib.error.URLError("network disabled by lineup_page_test")


urllib.request.urlopen = _no_urlopen


# --- fixtures ---------------------------------------------------------------

LEAGUE_DATA = {
    "id": "fx-lineup-page", "name": "Fixture Lineup League", "teams": 10,
    "platform": "espn", "my_slot": 1,
    "roster_spots": ["QB", "RB", "RB", "WR", "WR", "TE", "W/R/T", "W/R/T",
                     "K", "DEF"] + ["BN"] * 6,
    "rounds": 16, "rankings_csv": "data/rankings.csv",
    "scoring": {"reception": 1},
    "host": {"league_id": 111, "team_id": 7},
}
LEAGUE = LeagueConfig(LEAGUE_DATA)
SLOT_LABELS = ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX1", "FLEX2",
               "K", "D/ST"]

# (name, pos, team, weekly projection). Planted so that:
#   FLEX1 Yani 13.0 and FLEX2 Zulu 12.5 are both contested by Carl 12.0
#   RB2 Bob 15.5 is NOT contested (Carl is 3.5 back, past the 3.0 margin)
#   K and DEF are contested by the bench K / DEF within 0.5
#   nothing else is close
ROSTER = [
    ("Quincy Quarter", "QB", "BUF", 20.0),
    ("Aaron Alpha", "RB", "DET", 18.0),
    ("Bob Bravo", "RB", "SF", 15.5),
    ("Walt Whiskey", "WR", "CIN", 19.0),
    ("Xavier Xray", "WR", "MIA", 17.0),
    ("Tom Tango", "TE", "KC", 11.0),
    ("Yani Yankee", "WR", "DAL", 13.0),       # FLEX1
    ("Zulu Zephyr", "WR", "SEA", 12.5),       # FLEX2
    ("Carl Charlie", "RB", "NYJ", 12.0),      # bench - contests both flexes
    ("Kick Kappa", "K", "BAL", 8.0),
    ("Ravens D/ST", "DEF", "BAL", 7.0),
    ("Victor Victory", "RB", "GB", 5.5),      # bench, on bye in the fixture
    ("Uniform Upton", "TE", "PHI", 5.0),      # bench
    ("Sierra Sloan", "QB", "LAR", 14.0),      # bench
    ("Papa Pike", "K", "NYG", 7.5),           # bench - contests K
    ("Broncos D/ST", "DEF", "DEN", 6.5),      # bench - contests D/ST
]
STARTERS = ["Quincy Quarter", "Aaron Alpha", "Bob Bravo", "Walt Whiskey",
            "Xavier Xray", "Tom Tango", "Yani Yankee", "Zulu Zephyr",
            "Kick Kappa", "Ravens D/ST"]


def _proj():
    out = {}
    for name, pos, team, pts in ROSTER:
        out[name_key(name)] = {"proj": float(pts), "pos": pos, "team": team,
                               "source": "espn"}
    return out


def _roster(names=None):
    return {"name": "Fixture", "size": 16,
            "players": list(names or [r[0] for r in ROSTER]),
            "path": "data/rosters/fx.yaml"}


def _schedule():
    """Every fixture team plays except GB (bye). Kickoffs carry a zone."""
    teams = sorted(set(r[2] for r in ROSTER)) + ["NO", "ARI"]
    out = {}
    for i, t in enumerate(teams):
        if t == "GB":
            continue
        out[t] = {"opponent": "OPP", "home": (i % 2 == 0),
                 "kickoff_iso": "2026-09-13T13:00:00-04:00"}
    out["DAL"]["kickoff_iso"] = "2026-09-10T20:15:00-04:00"    # first kickoff
    out["DAL"]["opponent"] = "PHI"
    return out


def _cons_row(name, pos, verdict, pct):
    return {"player": name, "player_key": "%s|%s" % (name_key(name), pos),
            "pos": pos, "verdict": verdict, "pct": pct,
            "votes": [{"source": "engine", "name": "War Room Engine",
                       "weight": 17, "verdict": verdict.lower()}],
            "agreement": "UNANIMOUS", "dissenter": None, "score": 0.5,
            "engine": verdict.lower(), "vs_engine": False,
            "top_source": "engine", "top_vote": verdict.lower(),
            "top_disagrees": False, "top_note": ""}


def _cmap():
    rows = [_cons_row("Yani Yankee", "WR", "START", 80),
            _cons_row("Carl Charlie", "RB", "SIT", 25)]
    return dict((r["player_key"], r) for r in rows)


def _matchup_of(p):
    grade = {"DET": "SMASH", "NYJ": "AVOID", "DAL": "GOOD"}.get(p.team)
    return {"pa_grade": grade, "reason": "" if grade else "no read for %s" % p.pos,
            "evidence": "%s allowed a lot to %s" % (p.team, p.pos)}


def _dk_calls(verdict_dst="STREAM"):
    """The shape engine/dk documents, with the fields the page reads."""
    return {
        "DST": {"pos": "DST", "held": "Ravens D/ST", "held_score": 6.8,
                "best": "NE D/ST", "best_key": "ne dst", "best_score": 8.4,
                "best_opp": "CAR", "delta": 1.6, "verdict": verdict_dst,
                "reason": "NE beats BAL by +1.6, past the 1.5-pt margin",
                "cost": "costs a waiver claim - FAAB band 1-3%",
                "confidence": 59, "held_pct": 41, "unverified": False,
                "candidates": [{"name": "NE D/ST", "key": "ne dst",
                                "team": "NE", "opp": "CAR", "home": True,
                                "proj": 7.9, "adj": 0.5, "score": 8.4,
                                "opp_note": "CAR implied 17.5"}]},
        "K": {"pos": "K", "held": "Kick Kappa", "held_score": 9.9,
              "best": "Jake Bates", "best_key": "jake bates",
              "best_score": 9.6, "best_opp": "NO", "delta": -0.3,
              "verdict": "HOLD",
              "reason": "nothing available beats Kappa by more than 0.5",
              "cost": ("costs a waiver claim - priority league: NOT worth "
                       "burning priority - wait for him to clear"),
              "confidence": 48, "held_pct": 52, "unverified": False,
              "candidates": [{"name": "Jake Bates", "key": "jake bates",
                              "team": "DET", "opp": "NO", "home": False,
                              "proj": 9.4, "adj": 0.2, "score": 9.6,
                              "opp_note": ""}]},
    }


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _assemble(dk_calls=None, dk_note="", league=None, cmap=None, **kw):
    return lp.assemble(league or LEAGUE, 1, _roster(), _proj(),
                       schedule=_schedule(), lines={"DET": {"implied_total": 28.0}},
                       injuries={name_key("Bob Bravo"): "Questionable"},
                       sigmas=dict(lp.lineup_mod.DEFAULT_SIGMA), matcher=None,
                       cmap=_cmap() if cmap is None else cmap,
                       matchup_of=_matchup_of, dk_calls=dk_calls,
                       dk_note=dk_note, leagues=[("fx-lineup-page", "Fixture")],
                       now=NOW, **kw)


def _groups(html):
    """[(slot label, group html)] for the STARTERS card, in page order."""
    card = html.split('id="starters"', 1)[1].split('id="bench"', 1)[0]
    out = []
    for m in re.finditer(r'<div class="lu-group[^"]*">(.*?)</div>\s*(?=<div class="lu-group|</div></section>)',
                         card, re.S):
        g = m.group(0)
        slot = re.search(r'data-slot="([^"]+)"', g).group(1)
        out.append((slot, g))
    return out


def _bench_top(html):
    card = html.split('id="bench"', 1)[1].split("</section>", 1)[0]
    top = card.split("<details", 1)[0]
    rest = card.split("<details", 1)[1] if "<details" in card else ""
    return top, rest


# --- 1. slots in config order ----------------------------------------------

def test_slots():
    print("\n[1] starting slots: config order, numbering, FLEX and D/ST words")
    labs = lp.slot_labels(LEAGUE.roster_spots)
    check([l["label"] for l in labs] == SLOT_LABELS,
          "labels in config order with repeats numbered (got %s)"
          % [l["label"] for l in labs])
    check([l["short"] for l in labs] == ["QB", "RB", "RB", "WR", "WR", "TE",
                                         "FL", "FL", "K", "DS"],
          "every slot has a two-letter chip")
    check(all(l["kind"] == ("flex" if l["base"] == "FLEX" else "hard")
              for l in labs), "flex spots are flagged as flex")
    yahoo = LeagueConfig({"id": "y", "roster_spots": ["QB", "WR", "WR", "RB",
                                                      "RB", "TE", "W/R/T",
                                                      "W/R/T", "K", "DEF",
                                                      "BN"]})
    check([l["label"] for l in lp.slot_labels(yahoo.roster_spots)]
          == ["QB", "WR1", "WR2", "RB1", "RB2", "TE", "FLEX1", "FLEX2", "K",
              "D/ST"],
          "a league that lists WR before RB keeps ITS order")
    m = _assemble(dk_calls=_dk_calls())
    check([s["label"] for s in m["slots"]] == SLOT_LABELS,
          "assemble() yields one entry per starting slot in config order")
    check([s["player"].name for s in m["slots"]] == STARTERS,
          "the best legal lineup fills them (got %s)"
          % [s["player"].name for s in m["slots"]])
    html = lp.render_page(m)
    check([g[0] for g in _groups(html)] == SLOT_LABELS,
          "the page renders exactly one row group per slot, in order")
    check(html.count('class="lu-row') >= 10,
          "every slot renders a .lu-row")
    check('<span class="lu-slot-f">FLEX1</span>' in html
          and '<span class="lu-slot-s" aria-hidden="true">FL<i>1</i></span>' in html,
          "FLEX1 carries both its word and its two-letter chip")
    check('<span class="lu-slot-f">D/ST</span>' in html and ">DS</span>" in html,
          "the DEF slot reads D/ST on desktop and DS on a phone")


# --- 2. one challenger line, or none ----------------------------------------

def test_challengers():
    print("\n[2] a contested slot renders exactly one challenger line")
    m = _assemble(dk_calls=_dk_calls())
    html = lp.render_page(m)
    groups = dict(_groups(html))
    for slot in ("FLEX1", "FLEX2"):
        n = groups[slot].count('class="lu-vs"')
        check(n == 1, "%s (contested by Carl Charlie) has ONE challenger line "
                      "(got %d)" % (slot, n))
        check("Carl Charlie" in groups[slot], "...naming the challenger")
    for slot in ("QB", "RB1", "RB2", "WR1", "WR2", "TE"):
        check('class="lu-vs' not in groups[slot],
              "%s (uncontested) has no challenger line" % slot)
    f1 = groups["FLEX1"]
    check('class="lu-split"' in f1 and "76·24" in f1,
          "the split bar carries the room's weight 76·24 (80 vs 25 start-ward)")
    check("weight of the room" in f1, "...and says it is the room's, not odds")
    f2 = groups["FLEX2"]
    check("projection odds" in f2,
          "a challenger with no room vote draws the bar from projection odds "
          "and says so")
    check('<p class="lu-why">' in f1, "the one-line reason is printed")
    check(f1.count("wr-meter") >= 2, "both the starter and the challenger "
                                      "carry a matchup meter")
    ch = m["slots"][6]["challenger"]
    check(ch["player"].name == "Carl Charlie" and ch["split"]["a"] == 76
          and ch["split"]["basis"] == "room", "assemble() split data agrees")
    # verdict chips
    check('wr-chip-start' in groups["FLEX1"] and "80%" in groups["FLEX1"],
          "FLEX1 chip is the room's START 80%")
    check("START" in groups["QB"] and "wr-chip-pct" not in groups["QB"].split("lu-tail")[1].split("wr-meter")[0],
          "an uncontested starter with no room vote is START with no % claimed")
    # flags
    check('lu-flags' in groups["RB2"] and ">Q<" in groups["RB2"],
          "Bob Bravo's Questionable status is a Q flag on his row")
    check("Wed 8:15pm" not in html and "Thu 8:15pm" in groups["FLEX1"],
          "kickoffs print as one short token")
    check("first kickoff Thu 8:15pm (Yani Yankee)" in html,
          "the lede names the first kickoff")


# --- 3. K and D/ST: the streaming line, and the honest fallback -------------

def test_streaming_rows():
    print("\n[3] K and D/ST rows: dk's line when importable, the fallback when not")
    m = _assemble(dk_calls=_dk_calls())
    html = lp.render_page(m)
    groups = dict(_groups(html))
    k, d = groups["K"], groups["D/ST"]
    check(k.count("lu-stream") == 1 and d.count("lu-stream") == 1,
          "each of K and D/ST carries exactly one streaming line")
    check('class="lu-vs' in d and "Papa Pike" not in k and "Broncos" not in d,
          "the streaming line REPLACES the bench challenger on those rows")
    check("NE D/ST" in d and "vs CAR" in d and "+1.6" in d,
          "D/ST names the best available, his opponent (venue from the "
          "candidate view) and the delta")
    check("claim: FAAB 1-3%" in d, "...and the claim cost as a short token")
    check("priority · wait for FA" in k,
          "a priority-league cost paragraph collapses to one token")
    check('title="costs a waiver claim - priority league' in k,
          "...with the full sentence in the title")
    check(">STREAM<" in d and ">HOLD<" in k, "the dk verdict word is on the line")
    check("wr-chip-sit" in d and "59%" in d,
          "a STREAM verdict makes the held D/ST's chip SIT with dk's own odds")
    check("wr-chip-start" in k and "52%" in k,
          "a HOLD verdict keeps the held K on START with P(held beats best)")
    check("8.4" in d and "vs held" in d and "6.8" in d,
          "best score and held score both print")
    check(lp.STREAM_UNAVAILABLE not in html,
          "with dk present nothing says the read was unavailable")

    # the honest fallback: no dk at all
    m2 = _assemble(dk_calls=None, dk_note=lp.STREAM_UNAVAILABLE
                   + " — engine/dk.py not importable")
    html2 = lp.render_page(m2)
    g2 = dict(_groups(html2))
    for slot, who in (("K", "Papa Pike"), ("D/ST", "Broncos D/ST")):
        check(lp.STREAM_UNAVAILABLE in g2[slot],
              "%s says '%s' in place" % (slot, lp.STREAM_UNAVAILABLE))
        check(g2[slot].count('class="lu-vs"') == 1 and who in g2[slot],
              "%s falls back to its bench challenger %s" % (slot, who))
        check('class="lu-vs lu-stream"' not in g2[slot],
              "%s draws no streaming line" % slot)

    # NO READ from dk: the line says so, invents no candidate
    calls = _dk_calls()
    calls["DST"] = {"pos": "DST", "verdict": "NO READ", "best": None,
                    "reason": "streaming board unavailable", "delta": None}
    html3 = lp.render_page(_assemble(dk_calls=calls))
    g3 = dict(_groups(html3))
    check("NO READ" in g3["D/ST"] and "streaming board unavailable" in g3["D/ST"]
          and "no read on the wire" in g3["D/ST"],
          "a NO READ call prints its reason and no candidate")

    # unverified (rivals unknown) is stamped on the line
    html4 = lp.render_page(_assemble(dk_calls=_dk_calls(), rivals_known=False))
    check("unverified" in dict(_groups(html4))["D/ST"]
          and "rival rosters unknown" in html4,
          "rivals unknown -> the candidate is marked unverified and the "
          "banner says why")


def test_dk_monkeypatch():
    print("\n[4] streaming_calls() against a patched engine.dk, both ways")
    saved_mod = sys.modules.get("engine.dk")
    saved_attr = getattr(engine, "dk", None)
    seen = []

    fake = types.ModuleType("engine.dk")

    def weekly_call(league, week, my_roster_players, players, matcher,
                    force=False, **kw):
        seen.append({"league": league.id, "week": week, "force": force,
                     "n": len(list(my_roster_players))})
        return _dk_calls()
    fake.weekly_call = weekly_call
    try:
        sys.modules["engine.dk"] = fake
        engine.dk = fake
        calls, note = lp.streaming_calls(LEAGUE, 1, [], [], None)
        check(calls is not None and set(calls) == {"DST", "K"} and note == "",
              "an importable dk returns its {DST, K} calls and no note")
        check(seen and seen[0]["force"] is False,
              "weekly_call is asked with force=False - a read, never a refetch")

        def boom(*a, **k):
            raise RuntimeError("wire on fire")
        fake.weekly_call = boom
        calls, note = lp.streaming_calls(LEAGUE, 1, [], [], None)
        check(calls is None and lp.STREAM_UNAVAILABLE in note
              and "wire on fire" in note,
              "a dk that raises yields no calls and a note carrying the error")

        sys.modules["engine.dk"] = None       # makes `from engine import dk` fail
        if hasattr(engine, "dk"):
            delattr(engine, "dk")
        calls, note = lp.streaming_calls(LEAGUE, 1, [], [], None)
        check(calls is None and lp.STREAM_UNAVAILABLE in note
              and "not importable" in note,
              "no dk module at all -> the honest fallback note")
    finally:
        if saved_mod is not None:
            sys.modules["engine.dk"] = saved_mod
        else:
            sys.modules.pop("engine.dk", None)
        if saved_attr is not None:
            engine.dk = saved_attr
        elif hasattr(engine, "dk"):
            delattr(engine, "dk")


# --- 5. the bench --------------------------------------------------------

def test_bench():
    print("\n[5] the bench shows only competitors by default")
    html = lp.render_page(_assemble(dk_calls=_dk_calls()))
    top, rest = _bench_top(html)
    check("Carl Charlie" in top and "contests FLEX1, FLEX2" in top,
          "Carl Charlie is on the bench face, tagged with the slots he contests")
    for name in ("Victor Victory", "Uniform Upton", "Sierra Sloan"):
        check(name not in top and name in rest,
              "%s rests behind the expander" % name)
    check("Papa Pike" in rest and "Broncos D/ST" in rest,
          "the bench K and D/ST rest too - dk's wire read replaced them")
    check('class="wr-pop lu-rest"' in html and "the rest of the bench" in html
          and "(5)" in html, "the expander is a native <details> counting five")
    check("1 competing · 5 resting" in html, "the count line is honest")
    check("BYE" in rest.split("Victor Victory")[1].split("</article>")[0],
          "Victor Victory (GB, absent from the schedule) carries the BYE flag")
    # without dk the bench K and D/ST are competitors
    html2 = lp.render_page(_assemble(dk_calls=None, dk_note="x"))
    top2, _ = _bench_top(html2)
    check("Papa Pike" in top2 and "Broncos D/ST" in top2
          and "3 competing · 3 resting" in html2,
          "without dk the bench K and D/ST compete, and the count says so")
    # nobody competes
    m3 = _assemble(dk_calls=_dk_calls(),
                   cmap={})
    for s in m3["slots"]:
        s["challenger"] = None
    for b in m3["bench"]:
        b["competes"] = []
    html3 = lp.render_page(m3)
    check("no bench player contests a starting slot" in html3,
          "an uncontested lineup says so instead of an empty box")


# --- 6. swap deltas --------------------------------------------------------

def test_swaps():
    print("\n[6] swap deltas, to the tenth, and the footer strip")
    m = _assemble(dk_calls=_dk_calls())
    swaps = m["swaps"]
    got = dict((s["label"], s["delta"]) for s in swaps)
    check(got.get("swap Charlie in for Yankee") == -1.0,
          "swap Charlie in for Yankee: -1.0 (12.0 - 13.0)")
    check(got.get("swap Charlie in for Zephyr") == -0.5,
          "swap Charlie in for Zephyr: -0.5 (12.0 - 12.5)")
    check(got.get("claim NE D/ST") == 1.6, "claim NE D/ST: +1.6 from dk's delta")
    check(got.get("claim Jake Bates") == -0.3,
          "claim Jake Bates: -0.3 - a HOLD still shows why")
    check(len(swaps) == 4, "exactly four proposed changes (got %d)" % len(swaps))
    # 20 + 18 + 15.5 + 19 + 17 + 11 + 13 + 12.5 + 8 + 7
    check(abs(m["total"] - 141.0) < 0.01,
          "projected starting total 141.0 (got %.1f)" % m["total"])
    html = lp.render_page(m)
    check('<footer class="wr-card lu-foot"' in html
          and '<span class="lu-total-n wr-num">141.0</span>' in html,
          "the footer strip carries the total as a .wr-num")
    check("swap Charlie in for Yankee" in html and ">-1.0<" in html
          and "claim NE D/ST" in html and ">+1.6<" in html
          and "FAAB 1-3%" in html,
          "every swap prints with its signed delta and the claim cost")
    check("never advances the %owned momentum baseline" in html
          and "never writes the streaming log" in html
          and "./lineup.sh fx-lineup-page 1" in html,
          "the read-only promise is stated to the reader, with the rerun")
    check(lp.fmt_delta(-0.04) == "+0.0" and lp.fmt_delta(2) == "+2.0",
          "fmt_delta never prints -0.0")
    check(lp.cost_token("costs a waiver claim - FAAB band 4-8%") == "FAAB 4-8%"
          and lp.cost_token("") == "",
          "cost_token reads a FAAB band and stays empty on nothing")


# --- 7. the host verb ------------------------------------------------------

def test_host_verb():
    print("\n[7] 'Set lineup on <host>' present and absent")
    hv = lp.host_verb(LEAGUE)
    check(hv["href"].startswith("https://fantasy.espn.com/football/team?")
          and "leagueId=111" in hv["href"] and "teamId=7" in hv["href"]
          and hv["label"] == "Set lineup on ESPN" and not hv["note"],
          "espn + host -> the ESPN team page and the verb (got %s)" % hv["href"])
    html = lp.render_page(_assemble(dk_calls=_dk_calls()))
    check('class="lu-verb" href="https://fantasy.espn.com/football/team?'
          in html and 'target="_blank" rel="noopener noreferrer"' in html,
          "the verb is a link that opens a new tab")
    check(html.count("Set lineup on ESPN") == 2,
          "the verb appears in the lede and in the footer strip")
    y = LeagueConfig({"id": "y", "platform": "yahoo", "roster_spots": ["QB"],
                      "host": {"league_id": 428, "team_id": 5}})
    hy = lp.host_verb(y)
    check(hy["href"] == "https://football.fantasysports.yahoo.com/f1/428/5"
          and hy["label"] == "Set lineup on Yahoo", "yahoo recipe")
    nohost = LeagueConfig(dict(LEAGUE_DATA, host=None))
    hn = lp.host_verb(nohost)
    check(hn["href"] == "" and "add host:" in hn["note"],
          "no host: key -> no link and the quiet note naming the key")
    html2 = lp.render_page(_assemble(dk_calls=_dk_calls(), league=nohost))
    check("fantasy.espn.com" not in html2 and "lu-verb-none" in html2
          and "add host:" in html2,
          "...and the page renders the note, not a dead link")
    sleeper = LeagueConfig(dict(LEAGUE_DATA, platform="sleeper"))
    check("no deep-link recipe" in lp.host_verb(sleeper)["note"],
          "an unknown platform says there is no recipe")


# --- 8. phone-first CSS ----------------------------------------------------

def _css_of(html):
    return "".join(re.findall(r"<style>(.*?)</style>", html, re.S))


def test_phone_css():
    print("\n[8] phone-first: 390px must not scroll sideways or spill a line")
    html = lp.render_page(_assemble(dk_calls=_dk_calls()))
    css = _css_of(html)
    check('<meta name="viewport" content="width=device-width, initial-scale=1">'
          in html, "the viewport meta is set")
    check("@media (max-width: 700px)" in css, "a phone media query exists")
    phone = css.split("PHONE-FIRST", 1)[1]
    check(".lu-slot-f { display: none; }" in phone
          and "display: inline-flex" in phone.split(".lu-slot-s {", 1)[1],
          "on a phone the slot word hides and the two-letter chip shows")
    check(re.search(r"\.lu-n \{[^}]*white-space: nowrap;[^}]*overflow: hidden;"
                    r"[^}]*text-overflow: ellipsis", css),
          "player names truncate with an ellipsis")
    check(re.search(r"\.lu-opp, \.lu-kick \{ white-space: nowrap", css),
          "team/opponent codes and kickoffs never wrap")
    check(re.search(r"\.lu-row \{[^}]*min-height: 52px", css)
          and re.search(r"\.lu-vs \{[^}]*min-height: 44px", css),
          "rows are at least 44px tall")
    check("minmax(0, 1fr)" in css and "min-width: 0" in css,
          "the name column can shrink (minmax(0,1fr) + min-width:0)")
    # No fixed width wider than a phone anywhere outside .wr-scroll.
    wide = []
    for m in re.finditer(r"(?<![-\w])(min-)?width:\s*(\d+(?:\.\d+)?)px", css):
        if float(m.group(2)) > 390:
            wide.append(m.group(0))
    check(not wide, "no fixed width > 390px in the emitted CSS (got %s)" % wide)
    # nothing in the page's own markup pins a pixel width either
    body = html.split("</head>", 1)[1]
    pinned = re.findall(r'style="[^"]*width:\s*(\d+)px', body)
    check(not [w for w in pinned if int(w) > 390],
          "no inline pixel width > 390px in the body")
    check("overflow-x" not in _css_of(html).split("PHONE-FIRST", 1)[1]
          or "overflow-x: auto" not in phone,
          "the phone layout never resorts to a sideways scroll")


# --- 9. palette + self-containment ------------------------------------------

FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171")
_SVG_NS = "http://www.w3.org/2000/svg"
_LOCAL_PANEL = "http://127.0.0.1:8787/"


def test_palette_and_contained(html=None, tag="fixture"):
    print("\n[9] %s: no green, no red, nothing fetched" % tag)
    html = html or lp.render_page(_assemble(dk_calls=_dk_calls()))
    low = html.lower()
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low, "%s: %s absent" % (tag, hx))
    own = lp._CSS
    check(not re.findall(r"#[0-9a-fA-F]{3,8}\b", own),
          "%s: the page's own CSS declares no colour of its own" % tag)
    check("var(--mint)" not in own and "var(--coral)" not in own
          and "var(--good)" not in own and "var(--bad)" not in own,
          "%s: never reads the old --mint/--coral aliases" % tag)
    check(all(("var(--wr-" in ln) for ln in own.splitlines()
              if re.search(r"(color|background|border-color|fill):", ln)
              and "transparent" not in ln and "inherit" not in ln),
          "%s: every colour is a var(--wr-*) token" % tag)
    _shell_scripts = (ui.shell("home", None, 1, ()).lower().count("<script")
                      + ui.style_tag().lower().count("<script") + 1)  # +1: sheets_script
    check(low.count("<script") <= _shell_scripts,
          "%s: no script beyond the shell's own plus the sheet opener (got %d)" % (tag, low.count("<script")))
    check("<script src" not in low, "%s: no script is fetched" % tag)
    # engine/pwa.py adds two link relations through ui.style_tag() so the
    # page installs on a phone; neither is fetched to paint it. A
    # stylesheet, a favicon or a preload still fails - see board_test.
    _links = re.findall(r"<link\b[^>]*>", low)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in _links) and " src=" not in low,
          "%s: no embedded resource, and the only <link>s are the app "
          "manifest and the touch icon (%s)" % (tag, _links or "none"))
    stripped = html.replace(_SVG_NS, "").replace(_LOCAL_PANEL, "")
    stripped = re.sub(r'class="lu-verb" href="https?://[^"]*"', "", stripped)
    check(not re.search(r"https?://", stripped),
          "%s: no URL beyond the SVG namespace, the local panel and the host "
          "deep link" % tag)
    check("prefers-color-scheme" in html and '[data-theme="dark"]' in html,
          "%s: three-state theming" % tag)
    check(html.startswith("<!doctype html>") and html.index("<style>") <
          html.index("</head>"), "%s: ui.style_tag() in <head>" % tag)
    body = html.split("<body>", 1)[1]
    check(body.lstrip().startswith('<header class="wr-nav">'),
          "%s: ui.shell() is the first thing in <body>" % tag)
    check('<main class="wr-page' in html and 'class="wr-card' in html
          and 'class="wr-kicker">Lineup Builder' in html
          and 'class="wr-display wr-h1"' in html,
          "%s: .wr-page / .wr-card / kicker / display headline" % tag)
    check('aria-current="page"' in body.split("</header>", 1)[0],
          "%s: the shell marks an active page (board, until NAV_PAGES gains "
          "a lineup entry)" % tag)


def test_escaping():
    print("\n[10] a hostile name is escaped, not interpreted")
    roster = _roster(["<img src=x onerror=alert(1)> Quarter"] +
                     [r[0] for r in ROSTER][1:])
    proj = _proj()
    proj[name_key("<img src=x onerror=alert(1)> Quarter")] = {
        "proj": 20.0, "pos": "QB", "team": "BUF", "source": "espn"}
    m = lp.assemble(LEAGUE, 1, roster, proj, schedule=_schedule(),
                    sigmas=dict(lp.lineup_mod.DEFAULT_SIGMA), dk_calls=_dk_calls())
    html = lp.render_page(m)
    check("<img" not in html and "&lt;img" in html,
          "the hostile name reaches the page escaped")


# --- 11. live renders, both leagues -----------------------------------------

def _slots_of(html):
    return [g[0] for g in _groups(html)]


def test_live(league_id, expect_slots, tmp):
    print("\n[11] live render: %s (network disabled, caches only)" % league_id)
    out = os.path.join(tmp, "lineup-%s-week1.html" % league_id)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        path = lp.write_lineup(league_id, 1, out_path=out)
    check(path == out and os.path.exists(out), "write_lineup wrote the path it returns")
    check(not os.path.exists(out + ".tmp"), "no .tmp left behind")
    html = open(out).read()
    got = _slots_of(html)
    check(got == expect_slots,
          "%s: one row per starting slot in config order (got %s)" % (league_id, got))
    check("Lineup Builder" in html and "Set lineup on" in html,
          "%s: kicker and host verb present" % league_id)
    groups = dict(_groups(html))
    for slot in ("K", "D/ST"):
        g = groups.get(slot, "")
        check(("lu-stream" in g) or (lp.STREAM_UNAVAILABLE in g),
              "%s: the %s row carries the streaming line or the honest "
              "fallback" % (league_id, slot))
    check('id="bench"' in html and 'id="strip"' in html,
          "%s: bench and footer strip render" % league_id)
    check("open — no known player fits" not in html,
          "%s: every slot is filled from the known roster" % league_id)
    test_palette_and_contained(html, tag=league_id)
    return html


def test_readonly(tmp):
    print("\n[12] two renders leave every data file alone")
    watched = [os.path.join(HERE, "data", "cache", "espn-owned-snapshot.json"),
               os.path.join(HERE, "data", "streaming_log.jsonl"),
               os.path.join(HERE, "data", "source_ledger.jsonl"),
               os.path.join(HERE, "data", "sources.yaml"),
               os.path.join(HERE, "data", "rosters", "espn-1.yaml"),
               os.path.join(HERE, "data", "rosters", "yahoo-main.yaml"),
               os.path.join(HERE, "leagues", "espn-1.yaml"),
               os.path.join(HERE, "leagues", "yahoo-main.yaml")]

    def _state():
        return dict((p, (_md5(p), os.stat(p).st_mtime_ns
                         if os.path.exists(p) else None)) for p in watched)

    before = _state()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lp.write_lineup("espn-1", 1, out_path=os.path.join(tmp, "a.html"))
        mid = _state()
        lp.write_lineup("espn-1", 1, out_path=os.path.join(tmp, "b.html"))
    after = _state()
    for p in watched:
        name = os.path.relpath(p, HERE)
        check(mid[p] == before[p] and after[p] == before[p],
              "%s byte- and mtime-identical across two renders" % name)
    # Parsed, not grepped: the module's comments NAME these functions to
    # say it does not call them, and a text search would flag the prose.
    import ast
    src = open(os.path.join(HERE, "engine", "lineup_page.py")).read()
    called = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                called.add(fn.attr)
            elif isinstance(fn, ast.Name):
                called.add(fn.id)
    for banned, why in (
            ("owned_momentum", "would read (and could advance) the %owned "
                               "baseline"),
            ("log_top_pick", "appends to the streaming log"),
            ("record_votes", "writes the source ledger"),
            ("score_ledger", "writes the source ledger"),
            ("save_sources", "rewrites data/sources.yaml"),
            ("register", "writes the matchup source into data/sources.yaml"),
            ("backfill_feed", "appends to the performance history"),
            ("backfill_all", "appends to the performance history")):
        check(banned not in called,
              "engine/lineup_page.py never calls %s() - it %s" % (banned, why))
    check("force=False" in src, "dk is called with force=False")


def test_cli(tmp):
    print("\n[13] CLI")
    out = os.path.join(tmp, "cli.html")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = lp.main(["--league", "espn-1", "--week", "1", "--out", out])
    lines = [l for l in buf.getvalue().splitlines() if l.strip()]
    check(rc == 0 and lines and lines[-1] == out,
          "exit 0 and the written path is the LAST stdout line")
    with contextlib.redirect_stdout(io.StringIO()):
        rc2 = lp.main(["--league", "espn-1", "--week", "99", "--out", out])
    check(rc2 == 1, "an impossible week exits 1")
    with contextlib.redirect_stdout(io.StringIO()):
        rc3 = lp.main(["--league", "no-such-league", "--week", "1", "--out", out])
    check(rc3 == 1, "a missing league exits 1 without a traceback")
    check(lp.default_path("espn-1", 3) == os.path.join(HERE, "lineup-espn-1-week3.html"),
          "the default output is lineup-<league>-week<N>.html in the project root")
    sh = open(os.path.join(HERE, "lineup.sh")).read()
    check("engine.lineup_page" in sh and "warm_caches" in sh
          and "tail -n 1" in sh and "open \"$page\"" in sh,
          "lineup.sh mirrors board.sh: warm caches, print path, open on a tty")


def main():
    print("LINEUP BUILDER ACCEPTANCE TEST")
    test_slots()
    test_challengers()
    test_streaming_rows()
    test_dk_monkeypatch()
    test_bench()
    test_swaps()
    test_host_verb()
    test_phone_css()
    test_palette_and_contained()
    test_escaping()
    tmp = tempfile.mkdtemp(prefix="lineup-page-test-")
    try:
        test_live("espn-1", ["QB", "RB1", "RB2", "WR1", "WR2", "TE", "FLEX1",
                             "FLEX2", "K", "D/ST"], tmp)
        yhtml = test_live("yahoo-main", ["QB", "WR1", "WR2", "RB1", "RB2", "TE",
                                         "FLEX1", "FLEX2", "K", "D/ST"], tmp)
        check("rival rosters unknown" in yhtml or lp.STREAM_UNAVAILABLE in yhtml,
              "yahoo-main: the partial-coverage honesty is stated")
        test_readonly(tmp)
        test_cli(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
