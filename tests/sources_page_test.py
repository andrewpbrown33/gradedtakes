#!/usr/bin/env python3
"""Acceptance test: THE RECEIPTS (engine/sources_page.py).

Pure checks first - the headline formatting, the provenance and streak
words, the ink meter, the decay strip read off engine/performance.py's own
schedule, and the week-aware blend. Then a SYNTHETIC render on a tempdir
registry + history + ledger (one of every species: an archived feed with
live rows on top, an archived feed alone, a feed with no archive, two
creators, a hostile name, and two DISABLED sources), then a LIVE render on
the real registry and history for espn-1.

What the page must never do, and what is pinned here:

  NO INVENTED RECORD - a creator who has never been graded reads NO-DATA
  and says exactly why, in performance.py's own words (CREATOR_REASON);
  its sparkline is EMPTY, never a flat line at zero, and its position
  split says "nothing graded" rather than 0%.
  NO BARE NUMBER - every headline carries the blend label that says what
  it is made of ("2025 archive", "2025-weighted") with the blend note in
  its title, and every card carries a provenance line in words.
  READ-ONLY IN FACT - the registry, the history file and the ledger are
  byte- and mtime-identical either side of two renders, and the module's
  AST calls none of the functions that could write them.
  NO GREEN, NO RED - the six traffic-light hexes are absent, the split
  bars are ink on a hairline track, and the page's own CSS reads nothing
  but var(--wr-*) tokens.
  SELF-CONTAINED - one inline script (the shell's theme toggle), no <link>,
  no src=, no URL beyond the SVG namespace, the local Model Settings link
  and (if the design system ever ships one) its own typeface import.

    .venv/bin/python tests/sources_page_test.py
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import performance as perf                       # noqa: E402
from engine import sources as sources_mod                    # noqa: E402
from engine import sources_page as sp                        # noqa: E402
from engine import ui                                        # noqa: E402

FAILURES = []
TMP = None

FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171")
_SVG_NS = "http://www.w3.org/2000/svg"
_LOCAL_PANEL = "http://127.0.0.1:8787/"
_FONTS_RE = re.compile(r'@import url\("https://fonts\.googleapis\.com/[^"]*"\);')
HOSTILE = '<script>alert(1)</script> & "Co"'


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


# --- fixtures ---------------------------------------------------------------

def graded_rows(source, spec, pos="RB", lid="test-league", season=2025,
                edge=1.0):
    """[(week, calls, hits)] -> graded rows in performance's row shape."""
    out = []
    for week, n, hits in spec:
        for i in range(n):
            hit = i < hits
            out.append({"source": source, "league": lid, "season": season,
                        "week": week, "player": "p%d-%d" % (week, i),
                        "player_key": "p%d-%d" % (week, i),
                        "pos": pos if i % 3 else "WR",
                        "call": "start" if i % 2 else "sit",
                        "actual": 10.0, "replacement": 9.0,
                        "margin": edge, "edge": edge if hit else -edge,
                        "band": perf.band_of(edge), "hit": hit,
                        "provenance": perf.PROV_BACKFILL})
    return out


def fixtures():
    """A tempdir with a league, a registry, a history file and a ledger."""
    ldir = os.path.join(TMP, "leagues")
    os.makedirs(ldir, exist_ok=True)
    with open(os.path.join(ldir, "test-league.yaml"), "w") as fh:
        fh.write("id: test-league\nname: Test League\nteams: 2\n"
                 "roster_spots: [QB, RB, RB, BN]\nscoring: {reception: 1}\n")
    with open(os.path.join(ldir, "other.yaml"), "w") as fh:
        fh.write("id: other\nname: Other League\nteams: 4\n"
                 "roster_spots: [QB, RB, BN]\n")
    reg = os.path.join(TMP, "sources.yaml")
    sources_mod.save_sources([
        {"id": "espn-proj", "name": "ESPN Projections", "type": "feed",
         "handle": "espn-proj", "enabled": True, "weight": 17},
        {"id": "sleeper-proj", "name": "Sleeper Projections", "type": "feed",
         "handle": "sleeper-proj", "enabled": True, "weight": 11},
        {"id": "chen-tiers", "name": "Boris Chen Tiers", "type": "feed",
         "handle": "chen-tiers", "enabled": True, "weight": 11},
        {"id": "the-favorites", "name": "The Favorites", "type": "youtube",
         "handle": "https://example.invalid/@x", "enabled": True,
         "weight": 17},
        {"id": "sharp-or-square", "name": "Sharp or Square", "type": "rss",
         "handle": "https://example.invalid/rss", "enabled": True,
         "weight": 17},
        {"id": "hostile", "name": HOSTILE, "type": "url",
         "handle": "https://example.invalid/page", "enabled": True,
         "weight": 1},
        {"id": "off-air", "name": "Disabled Creator", "type": "youtube",
         "handle": "https://example.invalid/@off", "enabled": False,
         "weight": 5},
        {"id": "old-feed", "name": "Retired Feed", "type": "feed",
         "handle": "espn-proj", "enabled": False, "weight": 3},
    ], reg)
    hist = os.path.join(TMP, "history.jsonl")
    perf.append_history(
        graded_rows("espn-proj", [(w, 20, 13) for w in range(1, 9)])
        + graded_rows("sleeper-proj", [(w, 20, 12) for w in range(1, 9)])
        + graded_rows("old-feed", [(w, 20, 13) for w in range(1, 5)])
        + graded_rows("espn-proj", [(1, 20, 20)], lid="other"),
        path=hist)
    ledger = os.path.join(TMP, "ledger.jsonl")
    with open(ledger, "w") as fh:
        for i in range(8):
            fh.write(json.dumps({
                "league": "test-league", "week": 1, "source": "espn-proj",
                "player": "live%d" % i, "player_key": "live%d" % i,
                "pos": "RB", "verdict": "start" if i % 2 else "sit",
                "actual": 14.0, "replacement": 10.0,
                "hit": i < 6}) + "\n")
    return dict(league_dir=ldir, registry_path=reg, history_path=hist,
                ledger_path=ledger)


def _cards(html, section_id):
    seg = html.split('id="%s"' % section_id, 1)[1].split("</section>", 1)[0]
    return re.findall(r'<article class="rc-card[^"]*" id="src-[^"]+" '
                      r'data-source="([^"]+)">(.*?)</article>', seg, re.S)


# --- 1. pure helpers --------------------------------------------------------

def test_helpers():
    print("\n[1] helpers - words for every number, ink for every bar")
    check(sp.pct(None) == "—" and sp.pct(0.634) == "63%",
          "a missing rate is a dash, never 0%")
    num, lab, note = sp.headline({"hit_rate": 0.63, "label": "2025 archive",
                                  "note": "all archive"})
    check((num, lab, note) == ("63%", "2025 archive", "all archive"),
          "the headline is the number, the blend label and the note")
    num, lab, _ = sp.headline({"hit_rate": None, "label": "2025 archive",
                               "note": "x"})
    check(num == "no graded call" and lab == "",
          "no rate -> 'no graded call' with NO label beside it")
    check(sp.headline({}) == ("no graded call", "", ""),
          "an empty blend does not raise")

    check(sp.provenance_line({"provenance": perf.PROV_LIVE})
          == "live 2026 calls",
          "a live basis reads 'live 2026 calls'")
    check(sp.provenance_line({"provenance": perf.PROV_BACKFILL})
          == "reconstructed 2025 archive",
          "a backfill basis reads 'reconstructed 2025 archive'")
    check("no graded calls" in sp.provenance_line({"provenance": "none"}),
          "no basis says so")

    check("no run" in sp.streak_text({"streak": 0, "streak_dir": 0}),
          "no streak is 'no run', not a 0")
    check(sp.streak_text({"streak": 3, "streak_dir": 1})
          == "3 straight weeks above its own baseline",
          "a run is stated with its direction and its baseline")
    check("1 straight week below" in sp.streak_text({"streak": 1,
                                                     "streak_dir": -1}),
          "singular week, downward run")

    check("wr-badge-hot" in sp.state_html("HOT", "why")
          and 'title="why"' in sp.state_html("HOT", "why"),
          "HOT is the flame badge with the reason in its title")
    for st in ("STEADY", "NO-DATA", "LOW-CONFIDENCE", None, "weird"):
        out = sp.state_html(st)
        check("wr-badge" not in out and "rc-state-w" in out,
              "%r is words, never a badge (STEADY is not a badge either: "
              "ui would draw it for any unknown state)" % (st,))
    check(">NO-DATA<" in sp.state_html(None),
          "an absent state reads NO-DATA")

    bar = sp.ink_meter("RB", 0.634, 140, title="RB: 88 of 140")
    check('style="width:63%"' in bar and ">RB<" in bar and "63%" in bar
          and "(140)" in bar and 'title="RB: 88 of 140"' in bar,
          "an ink meter fills to the rate and prints it with the sample")
    empty = sp.ink_meter("TE", None, 0)
    check('style="width:0%"' in empty and 'rc-bar-v wr-num">— <small>(0)'
          in empty and "rc-bar-none" in empty and "0%" not in empty.split(
              'rc-bar-v')[1],
          "a missing rate draws an EMPTY track and a dash, not a 0% bar")
    check('style="width:100%"' in sp.ink_meter("X", 4.0),
          "a rate is clamped into 0-100")
    check("color" not in bar and "#" not in bar,
          "the meter carries no colour of its own - the CSS paints it ink")

    # The decay strip is READ from performance.py's schedule.
    steps = sp.decay_steps(0)
    check(len(steps) == perf.BACKFILL_RETIRED_AFTER + 1 == 4,
          "four steps: 0, 1, 2 and 3+ completed weeks")
    check([s["weight"] for s in steps]
          == [perf.backfill_weight(w) for w in range(4)],
          "every step's weight is performance.backfill_weight(w) - read, "
          "not restated")
    check([round(100 * s["weight"]) for s in steps] == [100, 60, 30, 0],
          "...which today reads 100 -> 60 -> 30 -> 0")
    for weeks, want in ((0, 0), (1, 1), (2, 2), (3, 3), (9, 3), (-2, 0),
                        ("junk", 0)):
        got = [s["weeks"] for s in sp.decay_steps(weeks) if s["current"]]
        check(got == [want],
              "%r completed weeks -> the current step is %d (got %s)"
              % (weeks, want, got))
    check(steps[-1]["label"].startswith("3+"),
          "the last step is labelled 3+ - the archive stays retired")
    strip = sp.render_decay_strip(1)
    check(strip.count('class="rc-step cur"') == 1
          and strip.count('aria-current="step"') == 1,
          "exactly one step is marked current, and marked accessibly")
    check("now: 1 completed week of 2026" in strip
          and "carries 60% of every headline" in strip,
          "the strip says where this week stands in words")
    check("BACKFILL_DECAY" in strip and "not restated" in strip,
          "the strip names its source of truth")

    # The blend follows the page's week, through performance.blend_bases.
    bases = {perf.PROV_LIVE: {"hit_rate": 0.50},
             perf.PROV_BACKFILL: {"hit_rate": 0.70}}
    row = {"bases": bases, "blend": perf.blend_bases(bases, 0)}
    check(abs(sp.blend_for(row, 1)["hit_rate"] - 0.70) < 1e-9,
          "week 1 (0 completed) keeps the row's own blend")
    b2 = sp.blend_for(row, 2)
    check(abs(b2["hit_rate"] - (0.6 * 0.7 + 0.4 * 0.5)) < 1e-9
          and b2["weeks_played"] == 1,
          "week 2 (1 completed) recomputes through blend_bases")
    check(sp.blend_for({"blend": {"hit_rate": 0.4}}, 5) == {"hit_rate": 0.4},
          "a row without bases keeps its blend rather than guessing")
    check(sp.blend_for(row, None) == row["blend"],
          "no week -> the row's blend, untouched")

    leagues = sp.league_choices()
    check(len(leagues) >= 2 and all(isinstance(x, tuple) and len(x) == 2
                                    for x in leagues),
          "league_choices lists every configured league as (id, name)")
    check(("espn-1", "The Original 8 (ESPN)") in leagues,
          "...with the league's display name")


# --- 2. synthetic render ----------------------------------------------------

def test_synthetic():
    print("\n[2] synthetic render - one of every species, week 2")
    fx = fixtures()
    html = sp.build_page("test-league", 2, **fx)
    check(html.startswith("<!doctype html>") and html.rstrip().endswith(
        "</html>"), "a complete document")

    enabled = _cards(html, "enabled")
    check([sid for sid, _ in enabled]
          == ["espn-proj", "sharp-or-square", "the-favorites",
              "chen-tiers", "sleeper-proj", "hostile"],
          "enabled cards, heaviest weight first, id as the tiebreak "
          "(got %s)" % [s for s, _ in enabled])
    cards = dict(enabled)
    check('<article class="rc-card top" id="src-espn-proj"' in html,
          "the heaviest source carries the gold rule")

    # ESPN: archive + live -> the BLEND, labelled, with the note in title.
    e = cards["espn-proj"]
    check('<span class="rc-big wr-num">69%</span>' in e,
          "espn-proj's headline is the decay blend: 60%% of 65%% archive + "
          "40%% of 75%% live = 69%% (got %s)"
          % re.findall(r'rc-big wr-num">([^<]*)<', e))
    check('>%s</span>' % perf.blend_label(0.6) in e,
          "...labelled %r beside the number" % perf.blend_label(0.6))
    check('title="60% 2025 archive / 40% 2026 live' in e,
          "...with the blend note in the label's title")
    check("live 2026 calls" in e and "both bases on file, shown unmixed"
          in e and "backfill-2025 65% over n160" in e
          and "live 75% over n8" in e,
          "the provenance line names the basis AND shows both records "
          "unmixed")
    check(">LOW-CONFIDENCE<" in e,
          "8 live calls over 1 week reads LOW-CONFIDENCE, never HOT")
    check("wr-badge-hot" not in e and "wr-badge-steady" not in e,
          "...and no badge is drawn for it")
    check("n <b class=\"wr-num\">8</b> graded calls" in e,
          "the sample is the headline basis's own (8 live calls)")

    # Sleeper: archive only -> the archive, said so, with every split.
    s = cards["sleeper-proj"]
    check('<span class="rc-big wr-num">60%</span>' in s
          and '>%s</span>' % perf.blend_label(1.0) in s,
          "sleeper-proj's headline is its archive rate, labelled "
          "%r" % perf.blend_label(1.0))
    check("reconstructed 2025 archive" in s
          and "2025 form read:" in s,
          "an archive-only card says so and scopes the 2025 form read")
    check("wr-spark-line" in s and "weeks 1-8" in s,
          "a wide sparkline of the weekly hit rate, with its week span")
    check('width="%d"' % sp.SPARK_W in s,
          "...drawn wide (%dpx)" % sp.SPARK_W)
    bars = re.findall(r'<div class="rc-bar"[^>]*><span class="rc-bar-l">'
                      r'([^<]*)</span>', s)
    check("RB" in bars and "WR" in bars,
          "per-position split bars for every graded position (got %s)"
          % bars)
    check("START calls" in bars and "SIT calls" in bars,
          "the start-split and the sit-split are bars too")
    check("benching is the easier half of the job" in s,
          "...with the sentence that says why the split matters")
    check(">NO-DATA<" in s and "has not been played" in s,
          "current form is NO-DATA with performance.py's reason - the "
          "archive never leaks into 'now'")
    check("streak: 1 straight week above its own baseline" in s
          or "streak: no run" in s,
          "the streak is stated in words")

    # Chen: a feed with no archive says which archive is missing.
    c = cards["chen-tiers"]
    check(">no graded call<" in c
          and ui.esc(perf.NO_ARCHIVE_REASON["chen-tiers"]) in c,
          "a feed with no archive reads 'no graded call' and names the "
          "missing archive")
    check("wr-spark-empty" in c and "no per-position split" in c,
          "...with an empty sparkline and no invented split")

    # Creators: NO-DATA, the reason in performance.py's words, no badge.
    for sid in ("the-favorites", "sharp-or-square"):
        seg = cards[sid]
        check(">NO-DATA<" in seg and ">no graded call<" in seg,
              "%s reads NO-DATA / no graded call" % sid)
        check(ui.esc(perf.CREATOR_REASON) in seg,
              "%s says exactly why: %r" % (sid, perf.CREATOR_REASON[:40]))
        visible = re.sub(r' title="[^"]*"', "", seg)
        check(visible.count("starts accumulating week 1") == 1,
              "%s says it once in visible text - not as the state's reason "
              "AND the callout (the state's title may carry it too)" % sid)
        check("wr-badge" not in seg,
              "%s carries no form badge of any kind" % sid)
        check("wr-spark-empty" in seg and "wr-spark-line" not in seg,
              "%s's sparkline is EMPTY, not a flat line at zero" % sid)
        check("no per-position split - nothing graded" in seg,
              "%s's position split says nothing was graded, not 0%%" % sid)
        check("wr-av-creator" in seg,
              "%s wears the creator ring" % sid)
    check("wr-av-pic-the-favorites" in cards["the-favorites"],
          "the-favorites' card carries its cached picture (by id, so the "
          "synthetic registry finds it too)")

    # Hostile text comes out inert.
    h = cards["hostile"]
    check("&lt;script&gt;alert(1)&lt;/script&gt;" in h
          and "<script>alert" not in html,
          "a hostile source name is escaped everywhere it appears")

    # Disabled sources: a quieter section, named, weighed, NOT in the model.
    quiet = _cards(html, "disabled")
    check([sid for sid, _ in quiet] == ["off-air", "old-feed"],
          "disabled sources sit in their own section, heaviest first "
          "(got %s)" % [s for s, _ in quiet])
    q = dict(quiet)
    check(all("rc-quiet" in html.split('id="src-%s"' % sid)[0][-60:]
              for sid in q),
          "disabled cards are the quiet variant")
    check("DISABLED - not in your model this week" in q["off-air"]
          and "weight of 5 counts for nothing" in q["off-air"],
          "a disabled source says its vote counts for nothing while off")
    check(ui.esc(perf.CREATOR_REASON) in q["off-air"]
          and "wr-spark-empty" in q["off-air"],
          "a disabled creator still reads its honest NO-DATA reason")
    check("65% on the reconstructed 2025 archive" in q["old-feed"]
          and "n <b class=\"wr-num\">80</b>" in q["old-feed"]
          and "wr-spark-line" in q["old-feed"],
          "a disabled feed's record is still read and shown, labelled")
    check("counts for nothing" in q["old-feed"],
          "...and it still says the vote is off")

    # The decay strip at week 2 = 1 completed week -> the 60% step.
    strip = html.split('id="decay"')[1].split("</section>")[0]
    cur = re.findall(r'<li class="rc-step cur" aria-current="step">'
                     r'<span class="rc-step-w wr-num">(\d+)%</span>'
                     r'<span class="rc-step-l">([^<]*)</span>', strip)
    check(cur == [("60", "1 week completed")],
          "week 2 highlights the 1-completed-week step at 60%% (got %s)"
          % cur)
    check(strip.count('class="rc-step') == 4
          + strip.count('class="rc-step-w') + strip.count('class="rc-step-l')
          + strip.count('class="rc-step-s'),
          "four steps on the strip")

    # The shell, on the Sources page.
    body = html.split("<body>", 1)[1]
    check(body.lstrip().startswith('<header class="wr-nav">'),
          "ui.shell() is the first thing in <body>")
    check('href="sources.html" aria-current="page"' in body,
          "the Sources link is marked current")
    check('class="wr-lgs"' in body and "Test League" in body
          and "Other League" in body,
          "the league switcher lists every league in the given league dir")
    check('<main class="wr-page">' in body,
          "content lives in <main class=\"wr-page\">")
    lede = re.search(r'<p class="wr-lede">(.*?)</p>', body, re.S)
    check(lede is not None and "Test League" in lede.group(1)
          and "ppr scoring, 2 teams" in lede.group(1),
          "the lede names the league whose replacement level graded the "
          "record")
    _self_contained(html, "synthetic", scripts=1)
    _palette(html, "synthetic")

    # Week 1 and week 9 move the strip; the cards keep their own bases.
    h1 = sp.build_page("test-league", 1, **fx)
    check('<span class="rc-step-w wr-num">100%</span>' in
          h1.split('class="rc-step cur"')[1][:80],
          "week 1 highlights the pre-season 100% step")
    e1 = dict(_cards(h1, "enabled"))["espn-proj"]
    check('<span class="rc-big wr-num">65%</span>' in e1
          and '>%s</span>' % perf.blend_label(1.0) in e1,
          "at week 1 (0 completed weeks) the espn-proj headline is the "
          "archive's 65%% even with live rows on file - the schedule says "
          "the archive carries 100%% until a week is complete - labelled "
          "%r" % perf.blend_label(1.0))
    check("live 75% over n8" in e1,
          "...while the live record is still shown unmixed beside it")
    h9 = sp.build_page("test-league", 9, **fx)
    check('<span class="rc-step-w wr-num">0%</span>' in
          h9.split('class="rc-step cur"')[1][:80],
          "week 9 highlights the retired 0% step")


# --- 3. live render ---------------------------------------------------------

def test_live():
    print("\n[3] live render - espn-1, the real registry and history")
    html = sp.build_page("espn-1", 1)
    enabled = [s for s in sources_mod.load_sources() if s.get("enabled")]
    want = [s["id"] for s in sorted(enabled,
                                    key=lambda s: (-float(s.get("weight")
                                                          or 0),
                                                   str(s.get("id"))))]
    got = [sid for sid, _ in _cards(html, "enabled")]
    check(got == want,
          "one card per enabled source, heaviest first (wanted %s, got %s)"
          % (want, got))
    cards = dict(_cards(html, "enabled"))
    for sid in ("the-favorites", "sharp-or-square"):
        check(ui.has_avatar(sid),
              "%s has a cached picture in data/cache/avatars" % sid)
        check("wr-av-pic wr-av-pic-%s wr-av-creator" % sid in cards.get(sid,
                                                                       ""),
              "%s's card carries that picture with the creator ring" % sid)
        check(ui.esc(perf.CREATOR_REASON) in cards.get(sid, "")
              and ">NO-DATA<" in cards.get(sid, ""),
              "%s is NO-DATA and says why in performance.py's words" % sid)
    for s in enabled:
        if (s.get("type") or "").lower() == "feed":
            check("wr-av-mono" in cards.get(s["id"], "")
                  and "wr-av-feed" in cards.get(s["id"], ""),
                  "feed %s renders a monogram with the feed ring" % s["id"])
    archived = [sid for sid in cards if "rc-big wr-num" in cards[sid]]
    check(archived,
          "at least one feed carries a 2025 reconstruction headline")
    for sid in archived:
        check('>%s</span>' % perf.blend_label(1.0) in cards[sid]
              and "reconstructed 2025 archive" in cards[sid],
              "%s's headline is labelled '2025 archive' and its provenance "
              "line says reconstructed" % sid)
        check("wr-spark-line" in cards[sid]
              and 'class="rc-bar"' in cards[sid],
              "%s draws its sparkline and its split bars" % sid)
    check("NO LIVE RECORD EXISTS YET" in html,
          "pre-season, the page says no live record exists yet")
    strip = html.split('id="decay"')[1].split("</section>")[0]
    check('<li class="rc-step cur" aria-current="step"><span class="rc-step-w '
          'wr-num">100%</span>' in strip,
          "week 1 = 0 completed weeks: the 100% step is current")
    check("Not in your model" in html,
          "the disabled section exists even when every source is enabled")
    check('href="board-espn-1-week1.html"' in html,
          "the shell links back to the board")
    check("<title>Sources - the receipts (week 1)</title>" in html,
          "the page is titled as the receipts")
    check("read-only:" in html and "./sources_page.sh" in html,
          "the footer states the read-only guarantee and how to regenerate")
    _self_contained(html, "live", scripts=1)
    _palette(html, "live")
    check("@media (max-width: 700px)" in _own_css(html)
          and "grid-template-columns: 1fr" in _own_css(html),
          "the cards stack under 700px - the page never scrolls sideways")


# --- 4. read-only + IO + CLI ------------------------------------------------

def test_readonly_and_io():
    print("\n[4] read-only in fact, atomic write, the CLI contract")
    import ast
    src = open(os.path.join(HERE, "engine", "sources_page.py")).read()
    called = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                called.add(fn.attr)
            elif isinstance(fn, ast.Name):
                called.add(fn.id)
    for banned in ("backfill_feed", "backfill_all", "append_history",
                   "save_sources", "register", "record_votes",
                   "score_ledger", "add_paste", "set_weight", "enable",
                   "disable", "fetch_source"):
        check(banned not in called,
              "sources_page.py never calls %s()" % banned)
    body = src.split('"""', 2)[2]
    # The hex scan skips HTML entities (&#183; is a middle dot, not a colour).
    hexes = re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", body)
    check(not hexes,
          "engine/sources_page.py declares no colour of its own (%s)"
          % (sorted(set(hexes)) or "none"))
    check("var(--mint)" not in body and "var(--coral)" not in body
          and "var(--good)" not in body and "var(--bad)" not in body,
          "...and never reads the old --mint/--coral aliases")

    watched = [os.path.join(HERE, "data", "sources.yaml"),
               os.path.join(HERE, "data", "performance_history.jsonl"),
               os.path.join(HERE, "data", "source_ledger.jsonl"),
               os.path.join(HERE, "leagues", "espn-1.yaml"),
               os.path.join(HERE, "sources.html")]

    def _state():
        return dict((p, (_md5(p), os.stat(p).st_mtime_ns
                         if os.path.exists(p) else None))
                    for p in watched)

    before = _state()
    out = os.path.join(TMP, "receipts.html")
    path = sp.write_page("espn-1", 1, out_path=out)
    check(path == out and os.path.exists(out),
          "write_page writes the requested path and returns it")
    check(not os.path.exists(out + ".tmp"),
          "atomic write leaves no .tmp behind")
    out2 = os.path.join(TMP, "cli.html")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sp.main(["--week", "1", "--out", out2])
    lines = buf.getvalue().strip().splitlines()
    check(rc == 0, "CLI exits 0")
    check(lines and lines[-1] == out2,
          "CLI prints the written path as its LAST stdout line "
          "(sources_page.sh contract)")
    after = _state()
    for p in watched:
        check(after[p] == before[p],
              "two renders leave %s byte- and mtime-identical"
              % os.path.relpath(p, HERE))

    # A corrupt registry: one line, exit 1, nothing written.
    bad = os.path.join(TMP, "bad.yaml")
    with open(bad, "w") as fh:
        fh.write("sources:\n  - id: chen-tiers\n   weight: 11\n")
    out3 = os.path.join(TMP, "bad.html")
    real = sources_mod.SOURCES_PATH
    try:
        sources_mod.SOURCES_PATH = bad
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sp.main(["--week", "1", "--out", out3])
        said = buf.getvalue().strip()
    finally:
        sources_mod.SOURCES_PATH = real
    check(rc == 1, "a corrupt registry exits 1 (got %r)" % rc)
    check(len(said.splitlines()) == 1 and "Traceback" not in said,
          "the diagnosis is ONE line, no traceback (got %r)" % said[:120])
    check("not valid YAML" in said and "line 3" in said
          and "./sources.sh" in said,
          "it names the file, the line and the remedy (got %r)" % said)
    check(not os.path.exists(out3), "nothing was written")
    check("no league yaml" in str(_raises(lambda: sp.build_page(
        "nope", 1, league_dir=TMP))),
          "an unknown league is a SystemExit naming the missing yaml")


def _raises(fn):
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001
        return exc
    return None


# --- 5. degradation ---------------------------------------------------------

def test_degraded():
    print("\n[5] a dead scoreboard - the page stands, claims nothing")
    real = perf.source_scoreboard

    def _dead(*_a, **_kw):
        raise RuntimeError("performance history unreadable: disk gone")

    try:
        perf.source_scoreboard = _dead
        html = sp.build_page("espn-1", 1)
    finally:
        perf.source_scoreboard = real
    check("SECTION DEGRADED" in html and "disk gone" in html,
          "the cards section degrades in place, carrying its error")
    check(html.count("SECTION DEGRADED") == 1,
          "exactly one section degraded")
    doc = html.split("</head>", 1)[-1]
    for word in ("HOT", "COLD", "STEADY", "NO-DATA", "LOW-CONFIDENCE"):
        check(">%s<" % word not in doc,
              "no card claims %s from an unreadable record" % word)
    check("rc-big wr-num" not in doc,
          "no hit rate is printed from an unreadable record")
    check("Voices on the registry" in html and "wr-av-creator" in html,
          "the registry's voices are still listed by name and face")
    check("record unavailable this render" in html,
          "...each saying its record is unavailable, not empty")
    check('id="decay"' in html and "Not in your model" in html,
          "the decay strip and the disabled section still render")
    _self_contained(html, "degraded", scripts=1)
    _palette(html, "degraded")


# --- shared checks ----------------------------------------------------------

def _own_css(html):
    styles = re.findall(r"<style>(.*?)</style>", html, re.S)
    return styles[-1] if len(styles) > 1 else ""


def _self_contained(html, tag, scripts=None):
    low = html.lower()
    # the shell's own scripts: theme toggle + the preferences boot script.
    # Always derived - an explicit count from an older caller is ignored.
    scripts = (ui.shell("home", None, 1, ()).lower().count("<script")
               + ui.style_tag().lower().count("<script"))
    check(low.count("<script") <= scripts,
          "%s: no script beyond the shell's own (theme toggle, preferences boot) - got %d, shell %d"
          % (tag, low.count("<script"), scripts))
    check("<script src" not in low, "%s: no script is fetched" % tag)
    # engine/pwa.py adds two link relations through ui.style_tag() so the
    # page installs on a phone; neither is fetched to paint it. A
    # stylesheet, a favicon or a preload still fails - see board_test.
    links = re.findall(r"<link\b[^>]*>", low)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in links),
          "%s: the only <link>s are the app manifest and the touch icon, "
          "neither fetched at open (%s)" % (tag, links or "none"))
    check(" src=" not in low, "%s: no embedded resource" % tag)
    stripped = _FONTS_RE.sub("", html).replace(_SVG_NS, "").replace(
        _LOCAL_PANEL, "")
    check(not re.search(r"https?://", stripped),
          "%s: no external URL other than the SVG namespace, the local "
          "Model Settings link and (if shipped) the typeface import" % tag)
    check("prefers-color-scheme" in html and '[data-theme="dark"]' in html,
          "%s: light and dark via the shared tokens" % tag)
    check(html.count("<style>") == 2,
          "%s: ui.style_tag() plus the page's own stylesheet, nothing else"
          % tag)


def _palette(html, tag):
    low = html.lower()
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low,
              "%s: forbidden hue %s is absent" % (tag, hx))
    for bad in ("var(--mint)", "var(--coral)", "var(--good)", "var(--bad)",
                'style="color'):
        check(bad not in html, "%s: no %s anywhere" % (tag, bad))
    own = _own_css(html)
    check(own and not re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", own),
          "%s: the page's own CSS declares no hex" % tag)
    stray = sorted(v for v in set(re.findall(r"var\((--[a-z0-9-]+)\)", own))
                   if not v.startswith("--wr-"))
    check(not stray,
          "%s: the page's CSS reads only var(--wr-*) tokens (stray: %s)"
          % (tag, stray or "none"))
    check(re.search(r"\.rc-bar-f \{[^}]*background: var\(--wr-text\)", own)
          is not None,
          "%s: the split bars are INK - the fill is the text colour" % tag)
    check(re.search(r"\.rc-step\.cur \{[^}]*var\(--wr-rule\)", own)
          is not None,
          "%s: the current decay step is marked by the gold rule" % tag)


def main():
    global TMP
    print("SOURCES PAGE (THE RECEIPTS) ACCEPTANCE TEST")
    TMP = tempfile.mkdtemp(prefix="sources-page-test-")
    try:
        test_helpers()
        test_synthetic()
        test_live()
        test_readonly_and_io()
        test_degraded()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
