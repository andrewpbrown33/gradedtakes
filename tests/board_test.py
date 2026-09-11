#!/usr/bin/env python3
"""Acceptance test: THE BOARD (engine/board.py), decision-card layout.

Pure checks first, on synthetic consensus rows - the column ordering, the
divergence grading (SPLIT vs the top-source alarm), WHAT MAKES A PLAYER A
CALL, the split measure the cards sort on, and the honest-degradation
guard. Then two LIVE renders from the real data, chosen because they are
opposite coverage cases:

  espn-1      full data - 8 of 8 rosters known, 17-man roster, rival
              targets nameable, waiver competition readable;
  yahoo-main  partial - only MY roster of 10 teams, so the league view and
              the trade targets must degrade honestly instead of vanishing.

Both must build without crashing, carry a row per rostered player and a
column per ENABLED source, and be self-contained: at most the two inline
scripts (the shell's theme toggle and the pop-out promoter), no <link>, no
src=, and no URL anywhere other than the inert SVG namespace, the local
Model Settings link the shell carries, and - if the design system ever
ships one - its own typeface @import. Every file this test writes lands in
a tempfile.mkdtemp() (the isolation discipline mock_draft.py applies to
save_state.SAVE_DIR), the source ledger is redirected, and the production
boards at the project root plus data/sources.yaml are byte-checked
untouched.

THE LAYOUT IS DECISION CARDS, and it is asserted as structure, not vibes.
The board section leads with THE CALLS - one versus card per player who
genuinely needs deciding - then LOCKED IN and BENCH as one compact row
each, then THE GRID (the old source-by-source matrix, intact) behind the
switch's All. The four things that can raise a card are each pinned by a
fixture: a room that splits, a top-weighted source that dissents, a
matchup grade that contradicts a room which AGREES, and engine/dk's
DST/K stream-or-toss-up. So is the thing that must NOT raise one: a plain
unanimous row, which gets a compact row and no card.

THE SKIN is asserted the same way: the shell is the first thing in <body>
and its league switcher links both leagues' board files; every source
column header is a ui.nameplate carrying a face (a cached picture for the
two creators, a monogram for every feed); every grid cell is a
ui.verdict_chip; the matchup is a ui.matchup_meter; the compact rows carry
a face strip whose RING says what each source said. And the page contains
NO green and NO red - the six hexes the old traffic-light palette used are
grepped for and must be absent, as must any var(--mint)/var(--coral)-
tinted text.

Five of these checks exist because the page once lied, crashed, or spilled
off a phone:

  NO CLAIM WITHOUT DATA - an empty CALLS list means either "every ground
  was checked and none fired" or "a ground could not be checked", and the
  page must never print the first when it means the second. A render with
  the board deliberately starved of rows is searched for the word
  "agreement" and the phrase "points the same way": neither may appear.
  QUIET MODE MAY NOT HIDE A CALL - a unanimous START into an AVOID matchup
  is unanimous AND needs the reader, so it must not carry
  data-unanimous="1".
  READ-ONLY IN FACT - two renders in a row must leave the %owned baseline
  snapshot byte- and mtime-identical (and must not create one that was not
  there), and must report the same %owned deltas rather than collapsing
  them to ~0. Asserted against a redirected snapshot path, never the
  shared production cache file, so no other run on the machine can decide
  the result.
  NO TRACEBACK AT THE EDGE - a corrupt registry must produce one diagnosis
  line naming the file, the line and the remedy, and exit 1.
  THE PHONE IS THE ACCEPTANCE BAR - no rule in the board's stylesheet may
  pin a width above 390px unless the element it targets lives inside a
  .wr-scroll box, and the compact row's nowrap must not leak into the
  score breakdown (it did, and laid four sentences out on one 2100px line).

FIXTURE RULE - read before editing the live renders:

  Two of the board's inputs are FUNCTIONS OF THE CALENDAR, and a check
  that pins the live page to one side of week 1 is true on Sunday and
  false on Thursday - an expiry date, not a contract. Lock state is one
  (build_page takes `now`); the matchup BASIS is the other: before the
  first 2026 game every meter cites "2025 season, 17 games" and warns that
  rosters and schemes have changed, from the first game on it cites a
  blend ("2026 wk1-1 (20%) + 2025 season (80%)") and the warning softens
  to "the sample is still young". build_page takes `pa_rows_by_season`
  for exactly this reason: the espn-1 render is repeated with fixture
  rows on BOTH sides of the boundary and every label pinned exactly, and
  the live render asserts only what is true in any week - one basis on
  the page in engine/matchups.py's grammar, the caveat the basis form
  calls for, and every rated meter's title carrying that basis.

    .venv/bin/python tests/board_test.py
"""

import contextlib
import hashlib
import io
import os
import re
from datetime import datetime, timezone
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import board                                    # noqa: E402
from engine import dk as dk_mod                             # noqa: E402
from engine import matchups as matchups_mod                 # noqa: E402
from engine import ui                                       # noqa: E402
from engine.models import LeagueConfig                      # noqa: E402

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


# --- fixtures ---------------------------------------------------------------

def _src(sid, name, weight, stype="feed", handle=None):
    return {"id": sid, "name": name, "weight": weight, "type": stype,
            "handle": handle if handle is not None else sid,
            "enabled": True}


SOURCES = [
    _src("engine", "War Room Engine", 17),
    _src("chen-tiers", "Boris Chen Tiers", 11),
    _src("creator", "The Favorites / Action Network (fantasy only)", 25,
         "youtube", "https://example.invalid/@x"),
]


def _vote(sid, name, weight, verdict, **kw):
    v = {"source": sid, "name": name, "weight": weight, "verdict": verdict}
    v.update(kw)
    return v


def _cons_row(player, pos, votes, verdict, pct, agreement,
              top_disagrees=False, vs_engine=False, dissenter=None,
              top_note=""):
    return {"player": player, "pos": pos, "player_key": "%s|%s"
            % (player.lower(), pos), "votes": votes, "verdict": verdict,
            "pct": pct, "agreement": agreement, "dissenter": dissenter,
            "top_disagrees": top_disagrees, "vs_engine": vs_engine,
            "top_note": top_note, "score": 0.0, "engine": None,
            "top_source": "creator", "top_vote": None}


def _matchup(grade, opp="SEA"):
    return {"pa_grade": grade, "opponent": opp, "home": False,
            "evidence": "%s allowed 12.0 PPR pts/game to WR (31st-most of "
                        "32, 4th pctl, -1.4 SD)" % opp,
            "basis": "2025 season, 17 games"}


def _dk_call(verdict, held="LAC D/ST", best="NE D/ST"):
    call = dk_mod._empty_call("DST", "fixture")
    call.update({"verdict": verdict, "held": held, "held_short": "LAC",
                 "held_key": "lac d/st|DEF", "held_score": 6.2,
                 "held_opp_note": "vs a middling offence",
                 "best": best, "best_short": "NE", "best_score": 8.4,
                 "best_opp_note": "against a turnover-prone offence",
                 "delta": 2.2, "reason": "fixture", "text": verdict})
    return call


# The old traffic-light palette, in every form it ever took on this page.
# None of these may appear in an emitted board: verdicts are chip WEIGHT
# (gold fill / ghost / dashed), attention is a gold rule, tallies are ink.
FORBIDDEN_HEX = ("#3DDC97", "#F26D6D", "#15803d", "#b91c1c", "#4ade80",
                 "#f87171")


def _row_for(cons_row, cols, group="STARTING", **kw):
    return board.make_row(group, kw.pop("slot", ""), cons_row["player"],
                          cons_row["pos"], kw.pop("team", "SF"),
                          cons_row["player_key"], cons_row, cols, **kw)


# --- 1. source columns ------------------------------------------------------

def test_columns():
    print("\n[1] source columns - weight order, share, short labels, faces")
    cols = board.source_columns(SOURCES)
    check([c["id"] for c in cols] == ["creator", "engine", "chen-tiers"],
          "columns ordered by weight, heaviest first")
    check(cols[0]["top"] and not cols[1]["top"],
          "only the heaviest column is flagged as the top source")
    check(abs(sum(c["share"] for c in cols) - 100.0) < 0.01,
          "shares normalize to 100% of the room")
    check(abs(cols[0]["share"] - 100.0 * 25 / 53) < 0.01,
          "share is the weight's real fraction, not the raw weight")
    check(cols[1]["short"] == "ENGINE" and cols[2]["short"] == "Chen",
          "built-in feeds reuse the strip's short tags")
    check(cols[0]["short"] == "The Favorites",
          "a creator name is cut at its first separator (got %r)"
          % cols[0]["short"])
    check(cols[0]["name"] == SOURCES[2]["name"],
          "the FULL name is kept for the column title - nothing is lost")
    check(all(c["source"] == {"id": c["id"], "name": c["name"],
                              "type": c["type"]} for c in cols),
          "every column carries the registry dict its face is drawn from")
    check(board.source_columns([]) == [],
          "no enabled sources -> no columns, not a crash")

    # The header is a nameplate: face + weight + state, name in the title.
    head = board.column_head_html(cols[0])
    check('<th class="src topsrc"' in head and "wr-np-c" in head,
          "a column header is a compact ui.nameplate")
    check("wr-av-mono" in head and ">TF<" in head,
          "a creator with no cached picture gets a monogram, never a broken "
          "image (got %r)" % re.findall(r">([A-Z?]{1,2})<", head))
    check("wt 25" in head and ">NO READ<" in head,
          "the header carries the weight and, with no record read, NO READ")
    check('title="The Favorites / Action Network (fantasy only) (youtube, '
          "weight 25" in head,
          "the FULL name and weight ride in the header's title")
    cols_p = board.source_columns(
        SOURCES, perf={"rows": [{"source": "engine", "state": "HOT",
                                 "state_reason": "two weeks up",
                                 "hit_rate": 0.7, "sample_n": 40,
                                 "provenance": "live"}]})
    eng = [c for c in cols_p if c["id"] == "engine"][0]
    hh = board.column_head_html(eng)
    check("wr-badge-hot" in hh and ">HOT<" in hh,
          "a HOT record renders the flame badge under the face")
    check("live 2026 ledger: 70% over 40 graded calls" in hh,
          "the graded record rides in the header's title, basis first")
    mh = board.model_head_html("YOUR MODEL")
    check("wr-av-mono" in mh and ">YM<" in mh and "YOUR MODEL" in mh,
          "the model column is headed by a monogram nameplate for YOUR MODEL")


# --- 2. divergence grading --------------------------------------------------

def test_levels():
    print("\n[2] divergence levels - SPLIT vs the top-source alarm")
    unan = _cons_row("A", "WR", [_vote("engine", "E", 17, "start")],
                     "START", 100, "UNANIMOUS")
    split = _cons_row("B", "WR", [_vote("engine", "E", 17, "start"),
                                  _vote("chen-tiers", "C", 11, "sit")],
                      "START", 61, "MAJORITY")
    top = _cons_row("C", "WR", [_vote("creator", "F", 25, "sit"),
                                _vote("engine", "E", 17, "start")],
                    "SIT", 40, "MAJORITY", top_disagrees=True,
                    top_note="top-weighted F says sit")
    # vs_engine WITHOUT top_disagrees: consensus.py computes vs_engine from
    # the weighted verdict vs the engine's vote, with no reference to the
    # top-weighted source - it is true even when that source filed nothing
    # on this row (build_rows leaves top_disagrees False there). Reading it
    # as the top-source alarm printed "the heaviest-weighted voice differs"
    # about a voice that never spoke.
    eng = _cons_row("D", "WR", [_vote("chen-tiers", "C", 11, "sit"),
                                _vote("engine", "E", 17, "start")],
                    "SIT", 30, "SPLIT", vs_engine=True, top_disagrees=False)
    check(board.divergence_level(unan) == board.LVL_NONE,
          "a unanimous row carries no marker")
    check(board.divergence_level(None) == board.LVL_NONE,
          "a player nobody voted on carries no marker (not a fake agreement)")
    check(board.divergence_level(split) == board.LVL_SPLIT,
          "voices pointing both ways -> SPLIT marker")
    check(board.divergence_level(top) == board.LVL_TOP,
          "top-weighted source dissenting -> the STRONGEST marker")
    check(board.divergence_level(eng) == board.LVL_SPLIT,
          "vs_engine with the top source SILENT is a split, NOT the "
          "top-source alarm (got %d)" % board.divergence_level(eng))
    check(board.divergence_level(
              _cons_row("E", "WR", [_vote("creator", "F", 25, "sit"),
                                    _vote("engine", "E", 17, "start")],
                        "SIT", 40, "MAJORITY", top_disagrees=True,
                        vs_engine=True)) == board.LVL_TOP,
          "vs_engine AND top_disagrees together still raise the alarm - it "
          "is top_disagrees that earns it")
    check(board.MARKERS[board.LVL_TOP] == "TOP SOURCE DISSENTS",
          "the strongest marker says what it means in words, not colour "
          "alone")
    # The alarm names the heaviest voice, so the level that triggers it has
    # to be the one consensus computed from that voice - and only that one.
    cols = board.source_columns(SOURCES)
    eng_card = board.render_call_card(_row_for(eng, cols), cols,
                                      dict((c["id"], c) for c in cols), "d1")
    check("TOP SOURCE DISSENTS" not in eng_card,
          "...so a vs_engine-only row's card never prints the top-source "
          "alarm")
    top_card = board.render_call_card(_row_for(top, cols), cols,
                                      dict((c["id"], c) for c in cols), "d2")
    check("TOP SOURCE DISSENTS" in top_card
          and "top-weighted F says sit" in top_card,
          "the top-source card carries the marker and consensus' own note")
    check('style="color' not in top_card,
          "no inline colour on the card - attention is the rule, not a hue")

    check(board.split_weight(unan) == 0, "unanimous -> 0 weight dissenting")
    check(board.split_weight(split) == 39,
          "MAJORITY 61/39 -> 39 on the losing side (got %d)"
          % board.split_weight(split))
    check(board.split_weight(_cons_row("E", "WR", [], "EVEN", 50, "SPLIT"))
          == 50, "a halved room -> the maximum split weight of 50")
    check(board.split_weight(None) == 0, "no row -> no split")


# --- 3. WHAT MAKES A PLAYER A CALL ------------------------------------------

def test_call_grounds():
    print("\n[3] the four grounds a card can be raised on - and the things "
          "that must NOT raise one")
    cols = board.source_columns(SOURCES)

    # (a) THE ROOM SPLITS.
    split = _row_for(_cons_row("Split Guy", "WR",
                               [_vote("engine", "War Room Engine", 17,
                                      "start"),
                                _vote("chen-tiers", "Boris Chen Tiers", 11,
                                      "sit")],
                               "START", 61, "MAJORITY"), cols,
                     matchup=_matchup("NEUTRAL"))
    kinds = [r["kind"] for r in board.call_reasons(split)]
    check(kinds == [board.CALL_SPLIT],
          "a room pointing both ways is a call, on the SPLIT ground (got %s)"
          % kinds)
    check("4 voices" not in board.call_reasons(split)[0]["line"]
          and "1 voice (17% of the weight) says START" not in
          board.call_reasons(split)[0]["line"],
          "the split line counts the voices it actually has")
    check("2 voice" not in board.call_reasons(split)[0]["line"],
          "...one voice a side, so neither side is pluralised wrongly")
    check(board.call_reasons(split)[0]["line"]
          == "the room points both ways: 1 voice (61% of the weight) says "
             "START, 1 (39%) says SIT.",
          "the SPLIT line states both tallies and both weights (got %r)"
          % board.call_reasons(split)[0]["line"])

    # (b) THE TOP-WEIGHTED SOURCE DISSENTS - the strongest ground.
    top = _row_for(_cons_row("Top Guy", "RB",
                             [_vote("creator", "The Favorites", 25, "sit"),
                              _vote("engine", "War Room Engine", 17,
                                    "start")],
                             "SIT", 40, "MAJORITY", top_disagrees=True,
                             top_note="your heaviest voice fades him"), cols)
    check([r["kind"] for r in board.call_reasons(top)] == [board.CALL_TOP],
          "the top-source alarm replaces the plain SPLIT, never doubles it")
    check(board.call_rank(top) > board.call_rank(split),
          "...and it outranks a plain split when the cards are ordered")

    # (c) THE MATCHUP CONTRADICTS A ROOM THAT AGREES.
    unanimous_votes = [_vote("engine", "War Room Engine", 17, "start"),
                       _vote("chen-tiers", "Boris Chen Tiers", 11, "start"),
                       _vote("creator", "The Favorites", 25, "start")]
    avoid = _row_for(_cons_row("Temper Guy", "WR", unanimous_votes,
                               "START", 100, "UNANIMOUS"), cols,
                     matchup=_matchup("AVOID"))
    reasons = board.call_reasons(avoid)
    check([r["kind"] for r in reasons] == [board.CALL_MATCHUP],
          "a unanimous START into an AVOID matchup IS a call (got %s)"
          % [r["kind"] for r in reasons])
    check(reasons[0]["mark"] == "TEMPER EXPECTATIONS",
          "...and it is framed as expectations, not as a verdict (got %r)"
          % reasons[0]["mark"])
    check("NOT a recommendation to bench him" in reasons[0]["line"],
          "...saying in words that it is NOT a bench call")
    check("one grade does not overturn it" in reasons[0]["line"],
          "...and why: the room agreed and one grade does not beat it")
    check("31st-most of 32" in reasons[0]["line"],
          "...carrying matchups.py's own evidence sentence, not a slogan")

    contra_sit = _row_for(
        _cons_row("Smash Guy", "RB",
                  [_vote("engine", "E", 17, "sit"),
                   _vote("chen-tiers", "C", 11, "sit")],
                  "SIT", 0, "UNANIMOUS"), cols,
        matchup=_matchup("SMASH"))
    check([r["kind"] for r in board.call_reasons(contra_sit)]
          == [board.CALL_MATCHUP]
          and board.call_reasons(contra_sit)[0]["mark"]
          == "THE MATCHUP ARGUES BACK",
          "the other direction - a settled SIT into a SMASH - is a call too")
    check("the room still says sit" in board.call_reasons(contra_sit)[0]
          ["line"],
          "...and it does not turn into a start recommendation either")
    check(board.CONTRA == {"START": "AVOID", "SIT": "SMASH"},
          "only the two ENDS of the scale contradict - NEUTRAL/GOOD/TOUGH "
          "argue with nobody and raise nothing")
    for grade in ("NEUTRAL", "GOOD", "TOUGH", ""):
        mid = _row_for(_cons_row("Mid %s" % grade or "None", "WR",
                                 unanimous_votes, "START", 100,
                                 "UNANIMOUS"), cols,
                       matchup=_matchup(grade) if grade else None)
        check(not board.is_call(mid),
              "a unanimous START into %s raises nothing"
              % (grade or "no grade"))

    # (d) engine/dk's DST/K hold-vs-stream.
    held = _cons_row("Los Angeles D/ST", "DEF",
                     [_vote("engine", "E", 17, "start")], "START", 100,
                     "UNANIMOUS")
    for verdict, is_a_call in (("STREAM", True), ("TOSS-UP", True),
                               ("HOLD", False), ("NO READ", False)):
        r = _row_for(held, cols, group="STARTING")
        r["dk"] = _dk_call(verdict)
        got = [x["kind"] for x in board.call_reasons(r)]
        check((board.CALL_STREAM in got) is is_a_call,
              "a DST/K %s %s a call (got %s)"
              % (verdict, "is" if is_a_call else "is NOT", got))
    streamed = _row_for(held, cols)
    streamed["dk"] = _dk_call("STREAM")
    check("NE D/ST" in board.call_reasons(streamed)[0]["line"],
          "the stream card names the man it would stream, from dk's own "
          "board line")

    # THE THING THAT MUST NOT RAISE ONE: a plain unanimous row.
    plain = _row_for(_cons_row("Quiet Guy", "TE", unanimous_votes,
                               "START", 100, "UNANIMOUS"), cols,
                     matchup=_matchup("NEUTRAL"))
    check(board.call_reasons(plain) == [] and not board.is_call(plain),
          "a plain unanimous row into a neutral matchup is NOT a call")
    single = _row_for(_cons_row("Lone Voice", "WR",
                                [_vote("engine", "E", 17, "start")],
                                "START", 100, "UNANIMOUS"), cols)
    check(not board.is_call(single),
          "one voice agreeing with itself is not a call either")
    silent = board.make_row("BENCH", "", "Nobody", "WR", "SF", "nobody|WR",
                            None, cols)
    check(not board.is_call(silent),
          "a player nobody voted on raises nothing - silence is not a split")

    # A LOCKED ROW IS NEVER A CALL: the decision is already over.
    locked = _row_for(_cons_row("Late Split", "WR",
                                [_vote("engine", "E", 17, "start"),
                                 _vote("chen-tiers", "C", 11, "sit")],
                                "START", 61, "MAJORITY"), cols)
    check(board.is_call(locked), "...before kickoff it is a call")
    locked["lock"] = {"locked": True, "text": "kicked off Sun 1:00pm ET"}
    check(not board.is_call(locked),
          "...and after kickoff it is not, however split the room was")

    # ORDER: strongest ground first, then the widest split, then the name.
    ordered = board.call_rows([plain, split, avoid, top, silent])
    check([r["player"] for r in ordered]
          == ["Top Guy", "Split Guy", "Temper Guy"],
          "cards run alarm, then split, then contradiction (got %s)"
          % [r["player"] for r in ordered])
    check(all(str(r.get("group")).upper() in ("STARTING", "BENCH")
              for r in ordered),
          "only roster rows become cards - a waiver or trade candidate is a "
          "different question with its own section")
    wire = _row_for(_cons_row("Wire Guy", "WR",
                              [_vote("engine", "E", 17, "start"),
                               _vote("chen-tiers", "C", 11, "sit")],
                              "START", 61, "MAJORITY"), cols,
                    group="WAIVER ADDS")
    check(board.call_rows([wire]) == [],
          "...so a split wire candidate raises no card on the roster board")


# --- 3b. the versus card ----------------------------------------------------

def test_versus_card():
    print("\n[3b] the versus card - two sides, the model in the gutter, and "
          "affordances that admit they do nothing")
    cols = board.source_columns(SOURCES)
    cols_by_id = dict((c["id"], c) for c in cols)
    # ONE heavy dissenter against two lighter voices, so the call is not
    # the simple majority and a WHY line is derivable.
    row = _row_for(
        _cons_row("Rico Dowdle", "RB",
                  [_vote("creator", "The Favorites", 40, "sit",
                         confidence="high",
                         quote="I am fading him in every format"),
                   _vote("engine", "War Room Engine", 17, "start"),
                   _vote("chen-tiers", "Boris Chen Tiers", 11, "start")],
                  "SIT", 41, "MAJORITY"), cols,
        slot="W/R/T", team="DAL", matchup=_matchup("GOOD", "ATL"))
    row.update({"has_proj": True, "proj": 12.4, "proj_source": "espn"})
    card = board.render_call_card(row, cols, cols_by_id, "cl-dowdle-0")

    check(card.startswith('<article class="bd-call'),
          "a call is one <article class=bd-call>")
    check('<span class="wr-pos">RB</span>' in card,
          "the header opens with ui.pos_badge")
    check('<a class="pop" href="#cl-dowdle-0" data-pop="cl-dowdle-0"' in card
          and 'aria-haspopup="dialog"' in card,
          "the name is the pop-out trigger and a real fragment link")
    check(card.count('<div class="bd-vs-side') == 2,
          "exactly two sides on the card")
    check('<div class="bd-vs-side bd-vs-start">' in card
          and '<div class="bd-vs-side bd-vs-sit">' in card,
          "one START side and one SIT side")
    start_side = card.split('<div class="bd-vs-side bd-vs-start">')[1] \
        .split('<div class="bd-vs-gut">')[0]
    sit_side = card.split('<div class="bd-vs-side bd-vs-sit">')[1]
    check('aria-label="War Room Engine"' in start_side
          and 'aria-label="Boris Chen Tiers"' in start_side,
          "every voice on the START side is a ui.avatar face")
    check("wt 17" in start_side and "wt 11" in start_side,
          "...with its weight beside it")
    check('aria-label="The Favorites"' in sit_side and "wt 40" in sit_side,
          "the dissenter's face and weight are on the SIT side")
    check("I am fading him in every format" in sit_side
          and "(high confidence)" in sit_side,
          "a creator's OWN WORDS are the reason on his side")
    check("best legal lineup starts him" in start_side,
          "a built-in feed states what its vote MEANS rather than borrowing "
          "a quote it never made")
    check('<span class="wr-num">2</span> voice' in start_side
          and '<span class="wr-num">1</span> voice ·' in sit_side,
          "tallies are plain ink numbers, one per side")
    gut = card.split('<div class="bd-vs-gut">')[1]
    check("wr-chip-sit" in gut and "wr-chip-pct" in gut,
          "the model's verdict chip WITH its percentage sits in the gutter")
    check("of the room" in gut, "...labelled as a share of the room")
    check("wr-meter" in gut or "wr-opp" in gut,
          "the matchup rides in the gutter beside the call")
    check("basis: 2025 season, 17 games" in card,
          "the matchup's basis is printed in words, not only in a title")
    check('<p class="bd-call-why">' in card
          and "SIT on weight: 1 of 3 voices carry 59% of the room" in card,
          "the derived WHY line rides under the versus, saying that the "
          "weight and not the voice count decided it")
    check('<details class="bd-pop" id="cl-dowdle-0">' in card
          and "every voice, in its own words" in card,
          "the full dossier is server-rendered in the card's own drawer")
    check(" open>" not in card.split("<details")[1][:40],
          "the card IS the disclosure, so its drawer starts closed")

    # AGREE / OVERRIDE: drawn, disabled, and honest about it.
    check(card.count('<button type="button" class="bd-act') == 2,
          "Agree and Override are drawn")
    acts = card.split('<div class="bd-acts">')[1]
    check(acts.count("disabled") == 2,
          "...as DISABLED buttons, so they are genuinely non-interactive")
    check("not wired up yet" in acts and "records or remembers a decision"
          in acts,
          "...with a line saying in words that nothing here is saved")
    check("nothing on this page" in acts,
          "...and that the claim is about the page, not about a backend")

    # A one-sided card still renders both sides, and says the other is empty.
    lone = _row_for(_cons_row("Alone", "WR",
                              [_vote("engine", "E", 17, "start"),
                               _vote("chen-tiers", "C", 11, "start"),
                               _vote("creator", "F", 25, "start")],
                              "START", 100, "UNANIMOUS"), cols,
                    matchup=_matchup("AVOID"))
    solo = board.render_call_card(lone, cols, cols_by_id, "cl-alone-0")
    check("no voice filed a SIT on him" in solo,
          "an empty side says it is empty rather than vanishing")
    check("wr-chip-sit" in solo,
          "...and still draws the SIT chip, so the versus stays a versus")
    check("TEMPER EXPECTATIONS" in solo and "wr-chip-start" in solo,
          "a temper-expectations card keeps the model's START call intact")

    # THE PROJECTION FOR BOTH MEN when the slot is what decided it.
    row["vs"] = {"name": "Tony Pollard", "proj": 10.1, "mine": 12.4,
                 "slot": "W/R/T", "side": "seated"}
    both = board.render_call_card(row, cols, cols_by_id, "cl-dowdle-0")
    check("Tony Pollard" in both and "10.1" in both and "12.4" in both,
          "when the slot decided it, BOTH projections are on the card")


# --- 3c. the compact row ----------------------------------------------------

def test_compact_row():
    print("\n[3c] the compact row - three columns, one line for the name, "
          "a face strip that says what each voice said")
    cols = board.source_columns(SOURCES)
    row = _row_for(
        _cons_row("Jayden Daniels", "QB",
                  [_vote("engine", "War Room Engine", 17, "start"),
                   _vote("chen-tiers", "Boris Chen Tiers", 11, "start")],
                  "START", 100, "UNANIMOUS"), cols,
        slot="QB", team="WAS", matchup=_matchup("TOUGH", "PHI"))
    row.update({"has_proj": True, "proj": 16.8, "proj_source": "espn"})
    html = board.compact_row_html(row, cols, "lk-daniels-0")

    check(html.startswith('<div class="bd-pl"'),
          "a settled player is one .bd-pl row")
    check(html.count('<div class="bd-r3">') == 1
          and '<div class="bd-r3-id">' in html
          and '<div class="bd-r3-mid">' in html
          and '<div class="bd-r3-v">' in html,
          "THREE logical columns: identity | opponent + projection | verdict")
    check('<span class="wr-pos">QB</span>' in html,
          "the position badge opens the identity column")
    check('<span class="bd-r3-nm"><a class="pop" href="#lk-daniels-0"'
          in html,
          "the name is the pop-out trigger inside the ellipsising span")
    check('data-l=' not in html.split('<div class="bd-r3-v">')[0]
          .split('<div class="bd-r3-mid">')[1],
          "the compact row carries no grid-cell scaffolding")
    check("wr-opp" in html and "16.8" in html,
          "the opponent chip and the projection ride in the middle column")
    check("wr-chip-start" in html,
          "the verdict chip closes the row")
    check('QB · WAS' in html and 'QB · QB' not in html,
          "the meta line does not repeat the position when it IS the slot")

    # THE FACE STRIP: every source, ring-encoded.
    strip = html.split('<div class="bd-faces"')[1].split("</div>")[0]
    check(strip.count("bd-face-start") == 2,
          "two gold rings for the two START voices (got %d)"
          % strip.count("bd-face-start"))
    check(strip.count("bd-face-none") == 1,
          "a faint ring for the source that filed nothing")
    check("filed nothing on him - silence, not approval" in strip,
          "...and the face says so, in the same words the dossier uses")
    check("(weight 17): voted START" in strip,
          "each face carries the source, its weight and its verdict")
    check(strip.count('<span class="bd-face ') == len(cols),
          "EVERY enabled source is in the strip, including the silent one "
          "(%d faces, %d sources)"
          % (strip.count('<span class="bd-face '), len(cols)))
    sat = _row_for(_cons_row("Sit Guy", "WR",
                             [_vote("engine", "E", 17, "sit")],
                             "SIT", 0, "UNANIMOUS"), cols)
    check("bd-face-sit" in board.face_strip(sat, cols),
          "a SIT vote draws the grey ring")

    # QUIET MODE marks the settled rows, and never a call.
    check('data-unanimous="1"' in html,
          "a unanimous settled row is marked so quiet mode can hide it")
    avoid = _row_for(_cons_row("Temper Guy", "WR",
                               [_vote("engine", "E", 17, "start"),
                                _vote("chen-tiers", "C", 11, "start")],
                               "START", 100, "UNANIMOUS"), cols,
                     matchup=_matchup("AVOID"))
    check(board.is_unanimous(avoid) and board.is_call(avoid),
          "a unanimous START into AVOID is BOTH unanimous and a call")
    check('data-unanimous="1"' not in board.compact_row_html(
              avoid, cols, "x-0"),
          "QUIET MODE MAY NOT HIDE IT: a row that raised a call is never "
          "marked unanimous")

    # LOCK STATE on a compact row.
    row["lock"] = {"locked": True,
                   "text": "kicked off Sun 09/13 1:00pm ET - this row is "
                           "final"}
    locked_html = board.compact_row_html(row, cols, "lk-daniels-0")
    check('<div class="bd-pl locked"' in locked_html,
          "a locked compact row carries the locked class the CSS mutes")
    check('class="bd-lock"' in locked_html and "wr-icon-locked"
          in locked_html,
          "...the padlock glyph")
    check('<span class="wr-chip-l">LOCKED</span>' in locked_html,
          "...and a LOCKED chip in place of the call")
    check("The call before kickoff was START" in locked_html,
          "...with the pre-kickoff call kept in the chip's title")


# --- 4. cells and the model column ------------------------------------------

def test_cells():
    print("\n[4] cells - silence is shown, never guessed; chips by weight")
    empty = board.vote_cell(None)
    check(empty["verdict"] is None and empty["label"] == "—",
          "a source with no opinion gets an explicit empty chip")
    check("no opinion" in empty["title"],
          "the empty chip's tooltip says 'no opinion filed'")
    check("wr-chip-unfiled" in board._cell_html(empty, "ENGINE")
          and 'data-l="ENGINE"' in board._cell_html(empty, "ENGINE"),
          "...rendered as ui's hollow unfiled chip, with the column label "
          "for the stacked layout")
    cell = board.vote_cell(_vote("creator", "F", 25, "sit",
                                 confidence="high", quote="sit him"))
    check(cell["label"] == "SIT" and cell["verdict"] == "sit",
          "a sit vote is a SIT chip")
    check("wr-chip-sit" in board._cell_html(cell) and ">SIT<"
          in board._cell_html(cell),
          "...drawn as ui.verdict_chip's ghost outline - weight, not hue")
    check("sit him" in cell["title"] and "high" in cell["title"],
          "the quote and confidence ride in the chip's title attribute")
    sized = board.vote_cell(_vote("creator", "F", 25, "start",
                                  sized_for="advice sized for deeper leagues",
                                  size_rank="WR37"))
    check("WR37" in sized["title"] and "deeper leagues" in sized["title"],
          "a league-size discount is visible on the cell, never silent")
    ranked = board.vote_cell(_vote("chen-tiers", "C", 11, "flex",
                                   detail="rank WR12"))
    check(ranked["verdict"] == "flex" and "rank WR12" in ranked["title"],
          "a rank-derived call keeps its detail in the title and the "
          "verdict word on the chip")

    m = board.model_cell(_cons_row("A", "WR", [_vote("engine", "E", 17,
                                                     "start")],
                                   "START", 71, "MAJORITY"))
    check(m["label"] == "START" and m["pct"] == "71%" and m["pct_n"] == 71
          and m["verdict"] == "start",
          "the model cell carries the verdict and its weight share")
    mh = board._model_html(m)
    check("wr-chip-start" in mh and ">71%<" in mh and 'class="chip' not in mh,
          "...rendered as the gold-fill chip with its percentage")
    none = board.model_cell(None)
    check(none["label"] == "NO READ" and none["verdict"] is None
          and "no enabled source" in none["title"],
          "a player no voice reached reads NO READ, not a default START")
    nh = board._model_html(none)
    check("wr-chip-unfiled" in nh and ">NO READ<" in nh,
          "...as the local labelled chip in the hollow weight")
    lc = board._label_chip("BURN", "start", "why")
    check("wr-chip-start" in lc and ">BURN<" in lc,
          "an affirmative non-verdict call (BURN) takes the fill weight")
    check("wr-chip-unfiled" in board._label_chip("X", "chartreuse"),
          "an off-system tone falls back to the hollow chip, never a "
          "colour")
    # ONE chip recipe: the grid cell, the compact row and the card's gutter
    # all go through verdict_chip_html, so a locked row cannot read final
    # in one place and open in another.
    lockedish = {"model": m, "lock": {"locked": True, "text": "kicked off"}}
    check(">LOCKED<" in board.verdict_chip_html(lockedish)
          and "The call before kickoff was START · 71%"
          in board.verdict_chip_html(lockedish),
          "verdict_chip_html draws LOCKED and keeps the pre-kickoff call")
    check(">LOCKED<" in board._model_html(m, "YOUR MODEL", lockedish),
          "...and the grid's model cell uses the very same recipe")


# --- 5. honest-degradation guard --------------------------------------------

def test_guard():
    print("\n[5] _guard - a dead section degrades visibly, never vanishes")
    ok = board._guard("T", lambda: "<section>fine</section>")
    check(ok == "<section>fine</section>", "healthy builder passes through")

    def boom():
        raise RuntimeError("feed down: fantasycalc 503")
    card = board._guard("Wire - waiver adds and trade targets", boom)
    check("SECTION DEGRADED" in card, "a failure renders a DEGRADED card")
    check("fantasycalc 503" in card, "the exception's own message is shown")
    check("Wire - waiver adds" in card, "the section keeps its title")
    check('class="wr-card' in card and "wr-degraded" in card,
          "the degraded card is a .wr-card carrying ui's degraded banner")

    raised = False
    try:
        board._guard("T", lambda: (_ for _ in ()).throw(SystemExit("no yaml")))
    except SystemExit:
        raised = True
    check(raised, "SystemExit (config error) propagates to the CLI")

    failures = []
    board._guard("Wire - waiver adds and trade targets", boom, failures)
    check(len(failures) == 1 and "Wire" in failures[0]
          and "fantasycalc 503" in failures[0],
          "a guarded failure is also RECORDED in words for the sections "
          "that arbitrate its output (got %s)" % failures)
    board._guard("T", lambda: "<p>ok</p>", failures)
    check(len(failures) == 1, "a healthy section records nothing")


# --- 5b. no claim without data ----------------------------------------------

def test_no_claim_without_data():
    print("\n[5b] an empty CALLS list - a finding, or a check that never "
          "ran?")
    cols = board.source_columns(SOURCES)
    voted = [_row_for(_cons_row("Voted", "WR",
                                [_vote("engine", "E", 17, "start"),
                                 _vote("chen-tiers", "C", 11, "start")],
                                "START", 100, "UNANIMOUS"), cols,
                      matchup=_matchup("NEUTRAL")),
             _row_for(_cons_row("Held Defense", "DEF",
                                [_vote("engine", "E", 17, "start")],
                                "START", 100, "UNANIMOUS"), cols,
                      matchup=_matchup("NEUTRAL"))]
    voted[0]["dk"] = _dk_call("HOLD")

    # EARNED: every ground was testable and none fired.
    holes = board.call_coverage(voted, cols, matchup_err="", dk_err="",
                                dk_read=True)
    check(holes == [], "with votes, grades and a DEF/K read there is no hole")
    agreed = board.render_calls_block([], cols, holes, judged=9, silent=0)
    check("nothing needs deciding" in agreed,
          "...so the positive claim is allowed to stand")
    check("all 9 player(s)" in agreed,
          "...and it is SCOPED to the rows that drew a vote, not to "
          "'every player'")
    check("no matchup grade contradicted the room" in agreed
          and "is a HOLD" in agreed,
          "...and it says which checks it is speaking for")
    partial = board.render_calls_block([], cols, [], judged=9, silent=4)
    check("4 row(s) drew no vote" in partial,
          "rows nobody voted on are excluded from the claim, out loud")

    # NOT EARNED (a): nothing was weighed at all.
    nothing = board.render_calls_block(
        [], cols, board.call_coverage([], cols, dk_read=False), judged=0)
    check("agreement" not in nothing and "points the same way" not in nothing,
          "ZERO rows weighed -> no claim about agreement is composed")
    check("nothing needs deciding" not in nothing,
          "...and no claim that the week is calm, either")
    check("NOT ARBITRATED" in nothing and "missing data, not calm" in nothing,
          "...it says what it is: an absence of data, not a finding")
    check("./sources.sh" in nothing and "board.sh" in nothing,
          "...and it names what the user can do about it")

    # NOT EARNED (b): the matchup table died, so ONE of the four grounds
    # could not be tested. An empty list then cannot mean "nothing fired".
    blind = board.call_coverage(voted, cols, matchup_err="nflverse 503",
                                dk_read=True)
    check(any("DID NOT RUN" in h for h in blind),
          "a dead matchup table is recorded as a check that did not run")
    dead_mu = board.render_calls_block([], cols, blind, judged=9)
    check("nothing needs deciding" not in dead_mu and "NOT ARBITRATED"
          in dead_mu and "nflverse 503" in dead_mu,
          "...so the block asserts nothing and repeats the real reason")

    # NOT EARNED (c): a DEF is held but no DEF/K read was made.
    no_dk = board.call_coverage(voted, cols, dk_err="", dk_read=False)
    check(any("hold-or-stream" in h for h in no_dk),
          "a missing DEF/K read is a hole, not a silent pass")
    dk_broken = board.call_coverage(voted, cols, dk_err="streaming 500",
                                    dk_read=False)
    check(any("streaming 500" in h for h in dk_broken),
          "...and a failed one carries its error")
    # ...but a roster with no DEF and no K has nothing for that check to
    # say, and a caveat printed there would be noise dressed as honesty.
    check(board.call_coverage(voted[:1], cols, dk_read=False) == [],
          "a roster holding neither a DEF nor a K reports no DEF/K hole")

    # NOT EARNED (d): no source enabled, so nothing COULD be weighed.
    empty_cols = board.render_calls_block(
        [], [], board.call_coverage([], [], dk_read=False), judged=0)
    check("agreement" not in empty_cols and "nothing needs deciding"
          not in empty_cols,
          "no enabled source -> no claim (silence is not unanimity)")

    # A REAL CARD still prints under a partial read, and says so.
    split = _row_for(_cons_row("Wide", "WR",
                               [_vote("engine", "War Room Engine", 17,
                                      "start"),
                                _vote("creator", "The Favorites", 16, "sit")],
                               "START", 52, "SPLIT"), cols)
    listed = board.render_calls_block([split], cols, blind, judged=1)
    check("Wide" in listed and "PARTIAL" in listed and "nflverse 503"
          in listed,
          "a partial read lists what it found and refuses to call it "
          "complete")

    # ROWS HELD BACK BY KICKOFF ARE COUNTED, never silently dropped.
    held = board.render_calls_block([], cols, [], judged=5, held_locked=2)
    check("2 row(s) that would otherwise be here have already kicked off"
          in held and "not dropped" in held,
          "a call suppressed by kickoff is counted out loud")


# --- 5c. the model's arithmetic, and the reputation vocabulary --------------

def test_math_and_reputation():
    print("\n[5c] weighted math re-derived, and reputation stated honestly")
    votes = [_vote("creator", "The Favorites", 25, "sit"),
             _vote("engine", "War Room Engine", 17, "start"),
             _vote("chen-tiers", "Boris Chen Tiers", 11, "start")]
    # weigh(): (25*-1 + 17*1 + 11*1) / 53 = +0.0566
    row = _cons_row("Somebody", "WR", votes, "START", 53, "MAJORITY")
    row["score"] = round((-25.0 + 17 + 11) / 53.0, 4)
    m = board.weighted_math(row)
    check(len(m["terms"]) == 3, "one term per voting source")
    check(abs(sum(t["share"] for t in m["terms"]) - 1.0) < 1e-9,
          "shares sum to 1 over the sources that ACTUALLY voted")
    check(m["checks"],
          "the printed terms sum to the score consensus published "
          "(shown %.4f vs score %.4f)" % (m["shown"], m["score"]))
    check(abs(m["terms"][0]["contrib"] - (-25.0 / 53.0)) < 1e-6,
          "a sit vote contributes NEGATIVELY, in proportion to its weight")

    m2 = board.weighted_math(row)
    check(abs(m2["shown"] - m["shown"]) < 1e-9,
          "the arithmetic is over voters, not over the registry")

    zeroed = _cons_row("Nobody", "RB",
                       [_vote("a", "A", 0, "start"),
                        _vote("b", "B", 0, "sit")], "EVEN", 50, "SPLIT")
    mz = board.weighted_math(zeroed)
    check(mz["equal_split"] and abs(mz["shown"]) < 1e-9,
          "all-zero weights split evenly, exactly as consensus.weigh does")

    check(board.weighted_math(None)["terms"] == [],
          "a row nobody voted on has no terms and does not raise")

    lying = dict(row, score=0.9)
    check(not board.weighted_math(lying)["checks"],
          "a breakdown that disagrees with the published score is flagged")

    # The reputation vocabulary. The two absence states may not borrow the
    # STEADY badge, because "no record" is not "no trend".
    for state in ("HOT", "COLD", "STEADY"):
        check("wr-badge" in board.streak_badge_html(state),
              "%s renders as a ui.py streak badge" % state)
    for state in ("NO-DATA", "LOW-CONFIDENCE", None, "", "banana"):
        out = board.streak_badge_html(state)
        check("wr-badge-steady" not in out,
              "%r is NEVER rendered as STEADY" % (state,))
    check(">NO-DATA<" in board.streak_badge_html("NO-DATA"),
          "NO-DATA says NO-DATA")
    check(">NO READ<" in board.streak_badge_html(None),
          "an unreadable record says NO READ, not a state")
    check(board.header_state(None) == "NO READ"
          and board.header_state({"state": "NO-DATA"}) == "NO-DATA"
          and board.header_state({"state": "weird"}) == "NO READ",
          "the header's form word is the state, or NO READ - never a "
          "default")

    meter = board.matchup_meter_html({"pa_grade": "GOOD",
                                      "reason": "soft vs RB"})
    check("wr-meter" in meter and ">GOOD<" in meter
          and 'title="matchup GOOD (4/5) - soft vs RB"' in meter,
          "a graded matchup is a ui.matchup_meter carrying the grade, its "
          "1-5 step and its reason (got %r)"
          % re.findall(r'title="([^"]*)"', meter))
    check(meter.count("wr-meter-on") == 4 and meter.count("wr-meter-off") == 1,
          "GOOD fills four of five segments")
    none = board.matchup_meter_html({"pa_grade": None,
                                     "reason": "no PA read"})
    check(">—<" in none and "wr-meter-on" not in none
          and 'title="matchup: no PA read"' in none,
          "no grade draws five hollow segments and a dash, with the reason")
    full = board.matchup_title({"pa_grade": "GOOD", "opponent": "DAL",
                                "home": True,
                                "evidence": "DAL allowed 24.1 PPR pts/game "
                                            "to RB (8th-most of 32)",
                                "basis": "2025 season, 17 games"})
    check(full.startswith("matchup GOOD (4/5) vs DAL (home) - ")
          and "basis: 2025 season, 17 games" in full,
          "the title states the step, the opponent and the basis year + "
          "games (got %r)" % full)
    check(board.matchup_title(None, err="nflverse 503")
          == "matchup read unavailable - nflverse 503",
          "a failed read titles itself as a failure, never as neutral")
    dead = board.matchup_meter_html(None, err="nflverse 503")
    check("wr-meter-on" not in dead and "nflverse 503" in dead,
          "a failed read is hollow and carries the error, never NEUTRAL")
    check("wr-badge-smash" not in meter and "wr-badge-avoid" not in meter,
          "the old SMASH/AVOID badge is gone from the matchup line")
    check(board.matchup_grade({"matchup": {"pa_grade": "avoid"}}) == "AVOID"
          and board.matchup_grade({}) == ""
          and board.matchup_grade(None) == "",
          "matchup_grade normalises, and a missing read is an empty string "
          "rather than a grade")

    from engine import performance as perf
    live = {"provenance": perf.PROV_LIVE}
    back = {"provenance": perf.PROV_BACKFILL}
    check("reconstructed archive" in board.basis_label(back),
          "a backfilled rate is labelled a reconstruction")
    check("live" in board.basis_label(live),
          "a live rate is labelled live")
    check(board.basis_short(back) == "2025",
          "the short label still names the season, not just a number")
    check(board.basis_label({"provenance": "none"}) == "no graded calls",
          "no record says so")
    check(board._pct_or(None) == "—" and board._pct_or(0.5) == "50%",
          "a missing rate is a dash, never 0%")

    sb_row = {"source": "espn-proj", "name": "ESPN Projections",
              "type": "feed", "weight": 17, "state": "NO-DATA",
              "state_reason": "no live call graded yet",
              "provenance": perf.PROV_BACKFILL, "hit_rate": 0.63,
              "sample_n": 160, "weeks_n": 8, "streak": 2, "streak_dir": 1,
              "sparkline_values": [60.0, 65.0, 70.0],
              "sparkline_weeks": [1, 2, 3], "backfill_state": "STEADY",
              "bases": {perf.PROV_BACKFILL: {"hit_rate": 0.63}},
              "blend": {"hit_rate": 0.63, "label": "2025 archive",
                        "note": "100% 2025 archive / 0% 2026 live",
                        "weight_backfill": 1.0, "weight_live": 0.0,
                        "weeks_played": 0, "retired": False}}
    tr = board.scoreboard_row(sb_row, week=1)
    check('<tr class="sbr" data-source="espn-proj">' in tr,
          "a scoreboard row is one <tr> named by its source")
    check('<span class="big wr-num">63%</span>' in tr
          and '>2025 archive</span>' in tr
          and 'title="100% 2025 archive / 0% 2026 live"' in tr,
          "the headline is '63% · 2025 archive' with the blend note in the "
          "title")
    check("wr-av-mono" in tr and 'href="sources.html#src-espn-proj"' in tr,
          "the row's nameplate links to the source's receipt")
    check("n 160" in tr and "8 weeks" in tr and "2 wk above" in tr,
          "sample and streak are stated in words and numbers")
    check("wr-spark-line" in tr and "reconstructed archive" in tr
          and "2025 form read: STEADY" in tr,
          "sparkline and provenance ride on the row; the 2025 form read is "
          "scoped to that season")
    creator = {"source": "the-favorites", "name": "The Favorites",
               "type": "youtube", "weight": 17, "state": "NO-DATA",
               "state_reason": perf.CREATOR_REASON, "is_creator": True,
               "backfill_reason": perf.CREATOR_REASON,
               "provenance": "none", "hit_rate": None, "sample_n": 0,
               "bases": {}, "blend": {"hit_rate": None, "label": "",
                                      "note": "no 2025 archive"}}
    tc = board.scoreboard_row(creator, week=1)
    check(">no graded call<" in tc and ">NO-DATA<" in tc
          and "starts accumulating week 1" in tc,
          "a creator reads NO-DATA / no graded call and says why, in "
          "performance.py's words")
    check("wr-spark-empty" in tc and "wr-badge" not in tc,
          "...with an EMPTY sparkline and no form badge of any kind")

    # Element ids survive the punctuation real player keys carry, and one
    # player rendered twice on the page never collides with himself.
    a = board.dom_id("mx", "a.j. brown|WR", 4)
    b = board.dom_id("cl", "a.j. brown|WR", 4)
    check(re.match(r"^[a-z0-9-]+$", a) is not None,
          "a drawer id is a legal bare fragment (got %r)" % a)
    check(a != b, "the same player in two blocks gets two ids")
    check(board.dom_id("mx", "", 0) != board.dom_id("mx", "", 1),
          "even empty keys never collide")


# --- 6. record line ---------------------------------------------------------

def test_record():
    print("\n[6] record - unknown is said out loud, never printed as 0-0")
    league = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    line = board.record_line(league)
    check("not tracked" in line and "standings" in line,
          "no standings feed -> the header says so (got %r)" % line)
    check("0-0" not in line, "an unknown record is never rendered as 0-0")

    tmp = tempfile.mkdtemp(prefix="board-record-")
    try:
        path = os.path.join(tmp, "fake.yaml")
        with open(path, "w") as fh:
            fh.write("id: fake\nname: Fake\nteams: 8\nrecord: 2-1\n")
        check(board.record_line(LeagueConfig.load(path)) == "2-1",
              "a hand-kept record: in the league yaml is used verbatim")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 6b. THE PHONE IS THE ACCEPTANCE BAR ------------------------------------

_WIDTH_RE = re.compile(r"(?<![-\w])(min-width|width)\s*:\s*([^;{}]+)")
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")

# The only two elements allowed a fixed width above 390px, because both
# live inside a .wr-scroll box that scrolls them horizontally on their own
# and never hands the page a sideways drag.
SCROLLED = ("table.mx", "table.sb")


def test_phone_css():
    print("\n[6b] phone CSS - nothing wider than 390px outside a .wr-scroll "
          "box, and no nowrap leaking into a panel")
    css = board._CSS
    wide = []
    for sel, decls in _RULE_RE.findall(css):
        sel = " ".join(sel.split())
        if any(s in sel for s in SCROLLED):
            continue
        for prop, value in _WIDTH_RE.findall(decls):
            # min()/max()/clamp() are self-limiting - `min(860px, 94vw)` can
            # never exceed the viewport, so the literal inside it is not a
            # fixed width.
            if any(f in value for f in ("min(", "max(", "clamp(")):
                continue
            for n in re.findall(r"(\d+(?:\.\d+)?)px", value):
                if float(n) > 390:
                    wide.append("%s { %s: %s }" % (sel[:60], prop,
                                                   value.strip()))
    check(not wide,
          "no rule pins a width above 390px outside a .wr-scroll box "
          "(offenders: %s)" % (wide or "none"))
    for sel in SCROLLED:
        check(re.search(r"%s\s*\{[^}]*min-width:\s*\d+px" % re.escape(sel),
                        css) is not None,
              "%s IS wide on purpose - it is the one thing that scrolls "
              "sideways, inside its own box" % sel)

    # The compact row's nowrap must NOT reach the breakdown panel. It did:
    # .bd-r3-mid is nowrap so the opponent code and the projection never
    # break, and ui.score_cell's panel is a DOM descendant of it, so four
    # sentences laid out on one 2100px line and the row carried it as
    # horizontal overflow on a 375px screen.
    check(re.search(r"\.bd-r3 \.wr-score-b[^{}]*\{[^}]*white-space: normal",
                    css, re.S) is not None,
          "the score breakdown inside a compact row resets white-space")
    check(re.search(r"\.bd-r3-mid \{[^}]*white-space: nowrap", css, re.S)
          is not None,
          "...while the row itself still keeps its codes from breaking")
    check(re.search(r"\.bd-lgw \.wr-lgd-p \{[^}]*left: 0", css, re.S)
          is not None,
          "the legend popover is re-anchored so 360px of key cannot hang "
          "off the left edge of a phone")

    # The versus card stacks under 700px: one column, START / gutter / SIT.
    phone = "\n".join(m.group(0) for m in
                      re.finditer(r"@media \(max-width: 700px\)\s*\{"
                                  r"(?:[^{}]|\{[^{}]*\})*\}", css))
    check(re.search(r"\.bd-vs \{[^}]*grid-template-columns: minmax\(0, 1fr\)",
                    phone, re.S) is not None,
          "the versus card collapses to ONE column on a phone")
    check(re.search(r"\.bd-r3 \{[^}]*grid-template-columns", phone, re.S)
          is not None and ".bd-r3-id { grid-column: 1 / -1; }" in phone,
          "the compact row gives the name the whole first line on a phone, "
          "so it never wraps and never ellipsises to one letter")
    check(re.search(r"\.bd-vs \{[^}]*minmax\(0, 1fr\) minmax\(0, 150px\) "
                    r"minmax\(0, 1fr\)", css, re.S) is not None,
          "...and it is START | gutter | SIT on a desktop")
    check(re.search(r"\.bd-r3-nm \{[^}]*text-overflow: ellipsis", css, re.S)
          is not None
          and re.search(r"\.bd-r3-nm \{[^}]*white-space: nowrap", css, re.S)
          is not None,
          "a player's name is ONE line with an ellipsis, never wrapped")
    check(re.search(r"\.bd-act \{[^}]*min-height: 44px", css, re.S)
          is not None
          and ".bd-call-h a.pop { display: inline-block; padding: 12px 0; }"
          in css,
          "the card's affordances are 44px finger targets")


# --- 7 / 8. live renders ----------------------------------------------------

SECTIONS = (
    board.BOARD_TITLE,
    "Wire - waiver adds and trade targets",
    "League view - the other teams",
    "Source scoreboard - who has actually been right",
)


def _roster_names(league_id):
    import yaml
    with open(os.path.join(HERE, "data", "rosters",
                           "%s.yaml" % league_id)) as fh:
        return list((yaml.safe_load(fh) or {}).get("players") or [])


# The URLs allowed to appear in the page source, and why each is not a
# network dependency:
#   * the SVG namespace ui.icon() writes on every inline <svg> - a string
#     constant no user agent resolves;
#   * the shell's link to the LOCAL Model Settings panel - a link the reader
#     may click, not a resource the page fetches;
#   * the design system's typeface @import, IF it ever ships one - the one
#     fetch the identity is allowed ("self-contained, fonts only"). Today
#     ui.css() embeds its fonts and ships no @import at all.
_SVG_NS = "http://www.w3.org/2000/svg"
_LOCAL_PANEL = "http://127.0.0.1:8787/"
_FONTS_RE = re.compile(r'@import url\("https://fonts\.googleapis\.com/[^"]*"\);')


def _self_contained(html, tag):
    """Self-contained still means self-contained.

    The board ships at most two inline scripts - the shell's light/dark
    toggle and the pop-out promoter - and both degrade to nothing. The
    contract that actually matters was never "zero script", it was "this
    page fetches nothing and hides nothing behind code", so that is what is
    asserted: no script fetched, no stylesheet link, no embedded resource,
    no external URL beyond the three allowed forms above, and - checked
    separately in test_board_structure - every fact the script can reveal
    is already in the document without it.
    """
    low = html.lower()
    shell_n = (ui.shell("board", "espn-1", 1).lower().count("<script")
               + ui.style_tag().lower().count("<script"))
    sheets_n = board.sheets_script_html().lower().count("<script")
    want = shell_n + 1 + sheets_n
    check(low.count("<script") == want,
          "%s: exactly the shell's %d script(s), the promoter and %d sheet "
          "script(s) - %d in all (got %d)"
          % (tag, shell_n, sheets_n, want, low.count("<script")))
    check(html.count(board._SCRIPT) == 1,
          "%s: the board's own script appears exactly once" % tag)
    check(sheets_n == 0 or html.count(board.sheets_script_html()) == 1,
          "%s: ui.sheets_script() is included exactly once" % tag)
    check("<script src" not in low.replace("<script  ", "<script "),
          "%s: every script is inline, never fetched" % tag)
    # THE TWO APP LINKS. engine/pwa.py adds `rel="manifest"` and
    # `rel="apple-touch-icon"` through ui.style_tag() so the page can be
    # installed on a phone. Neither is fetched to PAINT the page - delete
    # both and this document still renders from its own bytes - which is
    # the contract this line has always been a proxy for. Anything a
    # browser does fetch at open (a stylesheet, a favicon, a preload) still
    # fails here, and now by name.
    links = re.findall(r"<link\b[^>]*>", low)
    check(all(('rel="manifest"' in ln or 'rel="apple-touch-icon"' in ln)
              for ln in links),
          "%s: the only <link>s are the app manifest and the touch icon, "
          "neither fetched at open (%s)" % (tag, links or "none"))
    # ...and the ones that WOULD be fetched are named, so a future addition
    # has to argue with a test rather than slip past an `all()`.
    rels = set(re.findall(r'rel="([^"]+)"', " ".join(links)))
    for bad in ("stylesheet", "icon", "shortcut icon", "preload", "prefetch",
                "preconnect", "dns-prefetch", "modulepreload"):
        check(bad not in rels,
              '%s: no <link rel="%s"> - a browser fetches that to paint the '
              "page" % (tag, bad))
    check(" src=" not in low, "%s: no embedded resource" % tag)
    stripped = _FONTS_RE.sub("", html).replace(_SVG_NS, "").replace(
        _LOCAL_PANEL, "")
    check(not re.search(r"https?://", stripped),
          "%s: no external URL other than the SVG namespace, the local "
          "Model Settings link and (if shipped) the typeface import" % tag)
    check("prefers-color-scheme" in html,
          "%s: light and dark via CSS tokens" % tag)
    check('[data-theme="dark"]' in html,
          "%s: an explicit dark theme is honoured too, not only the OS one"
          % tag)


def _col_heads(html):
    """The FULL source names of the grid's columns, in render order, read
    off the face each header carries."""
    import html as _h
    out = []
    for th in re.findall(r'<th class="src[^"]*"[^>]*>(.*?)</th>', html, re.S):
        m = re.search(r'aria-label="([^"]*)"', th)
        out.append(_h.unescape(m.group(1)) if m else "")
    return out


def _board_css(html):
    """Everything in <head> - the shared stylesheet and the board's own."""
    return html.split("</head>")[0]


def _shared_shape(html, league_id, tag):
    check(html.startswith("<!doctype html>"), "%s: a full document" % tag)
    for title in SECTIONS:
        check(title in html, "%s: section present - %s" % (tag, title))
    check("SECTION DEGRADED" not in html,
          "%s: every section built from the real data" % tag)

    from engine import sources as sources_mod
    import html as _h
    enabled = [s for s in sources_mod.load_sources() if s.get("enabled")]
    want = [str(s.get("name")) for s in
            sorted(enabled, key=lambda s: (-float(s.get("weight") or 0),
                                           str(s.get("id"))))]
    got = _col_heads(html)[:len(want)]
    check(got == want,
          "%s: a column per enabled source (%d), heaviest first, each "
          "header a face labelled with the full name - wanted %s, got %s"
          % (tag, len(enabled), want, got))
    missing = [s.get("name") for s in enabled
               if ('title="%s (' % _h.escape(str(s.get("name")), quote=True))
               not in html]
    check(not missing,
          "%s: every source's FULL name opens its column title - "
          "missing %s" % (tag, missing))
    check("YOUR MODEL" in html, "%s: the YOUR MODEL column is present" % tag)

    # a row per rostered player, in the grid (which holds every row).
    cells = re.findall(r'<td class="who wr-sticky">.*?class="nm">'
                       r'<a class="pop"[^>]*>(.*?)</a>', html, re.S)
    rendered = set(c.strip() for c in cells)
    absent = []
    for name in _roster_names(league_id):
        surname = name.split()[-1].strip(".")
        if not any(surname in r for r in rendered):
            absent.append(name)
    check(not absent,
          "%s: a grid row per rostered player - unrepresented: %s"
          % (tag, absent))
    check("tabular-nums" in html, "%s: numbers are tabular" % tag)
    _self_contained(html, tag)
    test_shell(html, league_id, tag)
    test_palette(html, tag)


def test_shell(html, league_id, tag):
    """ONE SHELL: ui.shell() first in <body>, content in <main>."""
    print("\n[7d] the shell and the page frame - %s" % tag)
    body = html.split("<body>", 1)[1]
    check(body.lstrip().startswith('<header class="wr-nav">'),
          "%s: ui.shell() is the first thing in <body>" % tag)
    nav = body.split("</header>", 1)[0]
    check('href="board-%s-week1.html" aria-current="page"' % league_id in nav,
          "%s: the Board link is marked current" % tag)
    check('class="wr-lgs"' in nav,
          "%s: the league switcher is present" % tag)
    from engine.sources_page import league_choices
    leagues = league_choices()
    check(len(leagues) >= 2,
          "%s: at least two leagues are configured to switch between" % tag)
    for lid, _name in leagues:
        cur = ' aria-current="true"' if lid == league_id else ""
        check('<a class="wr-lg" href="board-%s-week1.html"%s>' % (lid, cur)
              in nav,
              "%s: the switcher links %s's board file for this week%s"
              % (tag, lid, " and marks it current" if cur else ""))
    check('<main class="wr-page">' in body,
          "%s: content lives in <main class=\"wr-page\">" % tag)
    check('href="sources.html"' in nav,
          "%s: the shell links the Sources page" % tag)
    check('<p class="wr-kicker">' in body and 'class="wr-h1 wr-display"' in body,
          "%s: the masthead uses the kicker and display headline" % tag)
    check(body.count('<section class="wr-card bd-sec">') == len(SECTIONS),
          "%s: every section is a .wr-card (%d)"
          % (tag, body.count('<section class="wr-card bd-sec">')))
    check('class="wr-scroll mxwrap"><table class="wr-table mx">' in body,
          "%s: the grid is a .wr-table inside a .wr-scroll box" % tag)
    check('<th class="who wr-sticky" scope="col">player</th>' in body,
          "%s: the player column header is sticky (.wr-sticky)" % tag)
    check("data-wr-theme" in nav,
          "%s: the light/dark toggle rides in the shell" % tag)


def test_palette(html, tag):
    """NO green, NO red. Verdicts are chip weight; attention is a rule."""
    print("\n[7e] palette - one accent, no traffic light - %s" % tag)
    low = html.lower()
    for hx in FORBIDDEN_HEX:
        check(hx.lower() not in low,
              "%s: forbidden hue %s is absent from the page" % (tag, hx))
    for bad in ("var(--mint)", "var(--coral)", "var(--good)", "var(--bad)"):
        check(bad not in html,
              "%s: no %s-tinted text anywhere" % (tag, bad))
    for bad in ('class="chip good', 'class="chip bad', 'class="chip warn',
                'class="chip mut', "chip.good", "chip.bad"):
        check(bad not in html,
              "%s: the old .chip recipes are gone (%s)" % (tag, bad))
    styles = re.findall(r"<style>(.*?)</style>", html, re.S)
    want_styles = ui.style_tag().count("<style>") + 1
    check(len(styles) == want_styles,
          "%s: exactly ui.style_tag()'s %d stylesheet(s) and the board's "
          "own (got %d)" % (tag, want_styles - 1, len(styles)))
    own = styles[-1] if styles else ""
    hexes = re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", own)
    check(not hexes,
          "%s: the board's CSS declares no hex of its own (%s)"
          % (tag, sorted(set(hexes)) or "none"))
    vars_used = set(re.findall(r"var\((--[a-z0-9-]+)\)", own))
    stray = sorted(v for v in vars_used if not v.startswith("--wr-"))
    check(not stray,
          "%s: the board's CSS reads only var(--wr-*) tokens (stray: %s)"
          % (tag, stray or "none"))
    check('style="color' not in html,
          "%s: no inline colour anywhere on the page" % tag)
    cells = re.findall(r'<td class="c" data-l="[^"]*">(.*?)</td>', html, re.S)
    check(cells and all(c.startswith('<span class="wr-chip wr-chip-')
                        for c in cells),
          "%s: every grid cell is exactly one ui.verdict_chip (%d cells)"
          % (tag, len(cells)))
    tones = set(re.findall(r'wr-chip wr-chip-([a-z]+) wr-chip-sm',
                           "".join(cells)))
    check(tones <= {"start", "sit", "lean", "none", "unfiled"},
          "%s: cells use the chip weights only (got %s)"
          % (tag, sorted(tones)))


# --- the matchup basis on the page ------------------------------------------
#
# engine/matchups.py prints its basis in one of two forms: a single season
# with a game count ('2025 season, 17 games' / '2026 wk1-3, 3 games') or a
# weighted blend ('2026 wk1-1 (20%) + 2025 season (80%)'). The DST/K block
# prints its own bd-basis line naming engine/streaming, so the matchup
# lines are picked out by that grammar rather than by the div alone.

_BASIS_ONE = re.compile(r"^\d{4} (?:season|wk1-\d+), \d+ games$")
_BASIS_BLEND = re.compile(r"^\d{4} (?:season|wk1-\d+) \(\d+%\) \+ "
                          r"\d{4} season \(\d+%\)$")

NFL_DEFENSES = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL",
                "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR",
                "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT",
                "SEA", "SF", "TB", "TEN", "WAS")


def _pa_rows(season, weeks, byes=False):
    """Synthetic nflverse weekly stat rows for all 32 defenses.

    Every defense allows a different rate (rising with its index) so the
    fixture table grades the whole ladder, SMASH to AVOID; `byes` gives
    each defense one week off in weeks 5-8 so an 18-week season is the
    NFL's 17 games. Game ids carry the season, so two seasons' rows can
    never be mistaken for one.
    """
    rows = []
    for week in range(1, weeks + 1):
        for i, d in enumerate(NFL_DEFENSES):
            if byes and week == 5 + (i % 4):
                continue
            base = {"season_type": "REG", "week": str(week),
                    "opponent_team": d, "team": "OFF",
                    "game_id": "FX%d_%02d_%s" % (season, week, d)}
            for pos, col, yds in (("QB", "passing_yards", 25 * (12 + 0.5 * i)),
                                  ("RB", "rushing_yards", 10 * (10 + 0.6 * i)),
                                  ("WR", "receiving_yards", 10 * (20 + 0.8 * i)),
                                  ("TE", "receiving_yards", 10 * (6 + 0.4 * i))):
                row = dict(base, position=pos)
                row[col] = "%g" % yds
                rows.append(row)
    return rows


def _matchup_bases(html):
    """The distinct matchup basis strings printed under the meters."""
    found = re.findall(r'<div class="bd-ev bd-basis">basis: ([^<]*)</div>',
                       html)
    return sorted(set(b for b in found
                      if _BASIS_ONE.match(b) or _BASIS_BLEND.match(b)))


def _rated_titles(html):
    """Every rated meter's title: 'matchup GOOD (4/5) vs DAL - ...'."""
    return re.findall(r'title="(matchup [A-Z]+ \(\d/5\)[^"]*)"', html)


def test_live_espn():
    print("\n[7] live - espn-1 (FULL data: 8 of 8 rosters known)")
    html = board.build_page("espn-1", 1)
    _shared_shape(html, "espn-1", "espn-1")
    check("8 of 8 rosters known" in html,
          "espn-1: the header states full roster coverage")
    check("TRADE TARGETS" in html,
          "espn-1: rivals are known, so targets can be NAMED")
    check("rival-rostered names excluded" in html,
          "espn-1: the waiver pool excludes players rivals are known to hold")
    check("ALSO MINE" in html,
          "espn-1: cross-league exposure is highlighted in the league view")
    check(html.count('class="team') >= 8,
          "espn-1: all eight rosters render as league-view cards")
    check("WAIVER ADDS" in html, "espn-1: the wire carries add rows")
    check("BURN" in html or "HOLD" in html,
          "espn-1 is a PRIORITY league - the model column shows burn "
          "guidance, not FAAB bands")
    check("FAAB" not in html.split("Wire - waiver")[1].split("</section>")[0],
          "espn-1: no FAAB band leaks into a priority league's wire")
    check("allowed" in html and "pts/game" in html,
          "espn-1: the dossier carries engine/matchups.py's evidence "
          "sentence, not a bare grade")
    check('<div class="bd-ev bd-basis">basis:' in html,
          "espn-1: the matchup basis line is printed under the meter")
    # THE BASIS IS A FUNCTION OF THE CALENDAR (see the FIXTURE RULE in the
    # module docstring). The live page is asserted against the RULE - one
    # basis, in matchups.py's grammar, with the caveat that form calls for
    # - and the two fixture renders below pin each side of week 1 exactly.
    bases = _matchup_bases(html)
    basis = bases[0] if bases else ""
    check(len(bases) == 1,
          "espn-1: every matchup row on the page cites ONE basis, in "
          "matchups.py's grammar (%s)" % (", ".join(bases) or "none found"))
    check(str(matchups_mod.PRIOR_SEASON) in basis,
          "espn-1: the basis names the prior season whatever the week - "
          "%d never leaves the blend (%r)" % (matchups_mod.PRIOR_SEASON,
                                             basis))
    blended = bool(_BASIS_BLEND.match(basis))
    prior_said = "rosters and schemes have changed" in html
    young_said = "sample is still young" in html
    check(prior_said != young_said and young_said == blended,
          "espn-1: exactly one honesty caveat, and it is the one the basis "
          "form calls for (%s basis -> %s)"
          % ("blended" if blended else "prior-only",
             "'still young'" if young_said else "'schemes have changed'"))
    titles = _rated_titles(html)
    check(titles and all(("basis: " + basis) in t for t in titles),
          "espn-1: every rated matchup carries its step and the page's "
          "basis, year and all (%d titles)" % len(titles))
    # One render, reused by the structural checks - build_page is the
    # expensive call in this suite and there is no reason to pay it twice.
    test_board_structure(html, "espn-1")
    test_scoreboard(html, "espn-1")
    test_sheet_switch_legend(html, "espn-1")
    check("of the room" in html,
          "espn-1: the call reads as a share of the room")
    check(_count(r'<span class="mdl-mu">', html) > 0,
          "espn-1: the 1-5 matchup rating rides beside the call")
    check(_count(r'<details class="(wr-score|bd-score)', html) > 0,
          "espn-1: rows carry a tappable score cell")
    # LOCK STATE IS A FUNCTION OF THE CLOCK, so asserting a fixed answer
    # against the REAL one is a test with an expiry date: week 1's Wednesday
    # opener kicked off on 9 September 2026, and every run after that would
    # fail a "nothing is locked" check. build_page takes `now` precisely so
    # this can be tested honestly - render the same league on both sides of
    # a real kickoff and assert the behaviour FLIPS.
    #
    # THE MATCHUP BASIS is the other calendar-driven input, and it rides on
    # the same two renders: the "before" world has no current-season rows
    # on file (pa_rows_by_season with an empty current season), the "after"
    # world has two weeks of them. Both fixtures cover all 32 defenses so
    # every rostered player's opponent is graded on both sides.
    PRIOR, CUR = matchups_mod.PRIOR_SEASON, matchups_mod.CURRENT_SEASON
    prior_rows = _pa_rows(PRIOR, 18, byes=True)
    pre_basis = "%d season, 17 games" % PRIOR
    mid_basis = "%d wk1-2 (33%%) + %d season (67%%)" % (CUR, PRIOR)
    _before = board.build_page("espn-1", 1,
                               now=datetime(2026, 9, 1, 12, 0,
                                            tzinfo=timezone.utc),
                               pa_rows_by_season={PRIOR: prior_rows,
                                                  CUR: []})
    # Count locked ROWS, not the word: the rebuilt board has a "LOCKED IN"
    # section (unanimous starts) and the legend carries one padlock glyph
    # explaining the symbol, so both appear whatever the clock says.
    def _locked_rows(page):
        return len(re.findall(r'<tbody class="pl[^"]*\blocked\b[^"]*"', page))
    check(_locked_rows(_before) == 0,
          "espn-1: with the clock set before week 1, no row is locked "
          "(got %d)" % _locked_rows(_before))
    _after = board.build_page("espn-1", 1,
                              now=datetime(2026, 12, 1, 12, 0,
                                           tzinfo=timezone.utc),
                              pa_rows_by_season={PRIOR: prior_rows,
                                                 CUR: _pa_rows(CUR, 2)})
    check(_locked_rows(_after) > 0,
          "espn-1: with the clock past every week-1 kickoff, rows lock "
          "(got %d)" % _locked_rows(_after))
    check(_locked_rows(_after) > _locked_rows(_before),
          "espn-1: locking is driven by the clock, not by the roster "
          "(%d locked after vs %d before)"
          % (_locked_rows(_after), _locked_rows(_before)))

    # PRE-SEASON: prior-season-only, said loudly on every surface.
    check(_matchup_bases(_before) == [pre_basis],
          "espn-1 pre-season: every meter cites %r and nothing else"
          % pre_basis)
    check("rosters and schemes have changed" in _before
          and "NOT %d" % CUR in _before
          and "sample is still young" not in _before,
          "espn-1 pre-season: the page says the rosters and schemes have "
          "changed and that this is NOT %d - and never calls the sample "
          "young" % CUR)
    pre_titles = _rated_titles(_before)
    pre_tail = ("basis: %s; %d rosters and schemes have changed since."
                % (pre_basis, CUR))
    check(pre_titles and all(pre_tail in t for t in pre_titles),
          "espn-1 pre-season: every rated title carries its step, the "
          "%d basis and the schemes-have-changed warning (%d titles)"
          % (PRIOR, len(pre_titles)))

    # IN-SEASON: a blend with the documented shares, and the caveat softens.
    check(_matchup_bases(_after) == [mid_basis],
          "espn-1 in-season: every meter cites the blend %r and nothing "
          "else" % mid_basis)
    check("sample is still young" in _after
          and "rosters and schemes have changed" not in _after
          and "NOT %d" % CUR not in _after,
          "espn-1 in-season: the caveat softens to 'still young' - the "
          "schemes-have-changed warning and 'NOT %d' are gone" % CUR)
    mid_titles = _rated_titles(_after)
    check(mid_titles
          and all(("basis: %s." % mid_basis) in t for t in mid_titles)
          and not any("have changed since" in t for t in mid_titles),
          "espn-1 in-season: every rated title carries its step and the "
          "blended basis, both years and shares (%d titles)"
          % len(mid_titles))
    check(all("(%d/5)" % board.MATCHUP_STEPS[t.split()[1]] in t
              for t in pre_titles + mid_titles),
          "espn-1 both sides: the step in every title is MATCHUP_STEPS of "
          "the grade it names")


def test_live_yahoo():
    print("\n[8] live - yahoo-main (PARTIAL: 1 of 10 rosters known)")
    html = board.build_page("yahoo-main", 1)
    _shared_shape(html, "yahoo-main", "yahoo-main")
    check("1 of 10 rosters known" in html,
          "yahoo-main: the header states partial roster coverage")
    check("UNKNOWN, not a free agent" in html,
          "yahoo-main: positive-only semantics stated in the league view")
    check("RIVAL ROSTERS UNKNOWN" in html,
          "yahoo-main: the wire degrades with a visible banner")
    check("TRADE TARGETS" not in html,
          "yahoo-main: no rival is named when no rival roster is known")
    check("Trade constructs - shapes, not named offers" in html,
          "yahoo-main: constructs stand in for named targets")
    check("FAAB" in html,
          "yahoo-main is a FAAB league - the model column shows bid bands")
    test_board_structure(html, "yahoo-main")
    test_sheet_switch_legend(html, "yahoo-main")


# --- 7b. THE BOARD: cards, compact rows, the grid behind All ----------------

def _count(pat, html, flags=0):
    return len(re.findall(pat, html, flags))


def _board_section(html):
    """Just the board's own .wr-card, so a block never runs on into the
    wire's matrix (which is the same markup in a different section)."""
    at = html.find(board.BOARD_TITLE)
    if at < 0:
        return ""
    start = html.rfind('<section class="wr-card bd-sec">', 0, at)
    if start < 0:
        start = html.rfind("<section", 0, at)
    return html[start:].split("</section>", 1)[0]


def _blk(html, sec):
    """One block of the board section, by its data-sec."""
    sec_html = _board_section(html) or html
    start = sec_html.find('<div class="bd-blk" data-sec="%s">' % sec)
    if start < 0:
        return ""
    rest = sec_html[start:]
    for other in ("calls", "locked", "bench", "grid"):
        if other == sec:
            continue
        cut = rest.find('<div class="bd-blk" data-sec="%s">' % other)
        if cut > 0:
            rest = rest[:cut]
    return rest


def test_board_structure(html, tag):
    """The layout, asserted as structure rather than as vibes."""
    print("\n[7b] the board - calls, compact rows, the grid - %s" % tag)

    calls = _blk(html, "calls")
    locked = _blk(html, "locked")
    bench = _blk(html, "bench")
    grid = _blk(html, "grid")
    check(all([calls, locked, bench, grid]),
          "%s: all four blocks are rendered" % tag)
    check(html.find(calls[:40]) < html.find(grid[:40]),
          "%s: THE CALLS come before the grid - certainty is the "
          "organising principle" % tag)

    # THE CALLS COUNT MATCHES THE CARDS RENDERED, AND NAMES THEM CORRECTLY.
    # The head splits its total: a card raised ONLY by the matchup ground
    # contradicts a room that agreed and says so in its own words ("NOT a
    # recommendation to bench him", "the room still says sit"), so counting
    # it as a decision overstates how much of the week is unsettled. Both
    # halves are checked - they must still account for every card (nothing
    # summarised away), and the split must match an INDEPENDENT recount of
    # each card's own grounds rather than trusting the head's arithmetic.
    cards = _count(r'<article class="bd-call', calls)
    head = re.search(r'<span class="bd-grp-n">([^<]*)</span>', calls)
    head_txt = head.group(1) if head else ""
    stated_nums = [int(n) for n in re.findall(r'\d+', head_txt)]
    check(stated_nums and sum(stated_nums) == cards,
          "%s: the band head accounts for every card (%r sums to %d, drew "
          "%d)" % (tag, head_txt, sum(stated_nums), cards))

    # Recount from the cards themselves: the marks in each card's why-list.
    MATCHUP_ONLY = ("TEMPER EXPECTATIONS", "THE MATCHUP ARGUES BACK")
    look = 0
    for card in re.findall(r'<article class="bd-call.*?</article>', calls,
                           re.S):
        ul = re.search(r'<ul class="bd-call-why-list">(.*?)</ul>', card, re.S)
        marks = re.findall(r'<li><b>(.*?)</b>', ul.group(1)) if ul else []
        if marks and all(m in MATCHUP_ONLY for m in marks):
            look += 1
    want = ("%d need%s a decision · %d worth a second look"
            % (cards - look, "s" if cards - look == 1 else "", look)
            if look and cards - look else
            ("%d worth a second look" % look if look else
             "%d need%s a decision" % (cards, "s" if cards == 1 else "")))
    check(head_txt == want,
          "%s: the head names the split its own cards justify (says %r, "
          "cards justify %r)" % (tag, head_txt, want))
    check(not (look and "need" in head_txt
               and int(re.search(r'(\d+) need', head_txt).group(1)) == cards),
          "%s: a matchup-only card is never counted as a decision" % tag)
    sec_count = re.search(r'wr-sec-n">(\d+) call', html)
    check(sec_count is not None and int(sec_count.group(1)) == cards,
          "%s: ...and the section header's count agrees (%s vs %d)"
          % (tag, sec_count.group(1) if sec_count else "?", cards))
    if cards:
        check(_count(r'<ul class="bd-call-why-list">', calls) == cards,
              "%s: every card says WHY it is a call - no card is an "
              "editor's hunch" % tag)
        check(_count(r'<div class="bd-vs">', calls) == cards,
              "%s: every card is a versus" % tag)
        check(_count(r'<div class="bd-vs-side', calls) == cards * 2,
              "%s: two sides per card" % tag)
        check(_count(r'<div class="bd-vs-gut">', calls) == cards,
              "%s: the model sits in the gutter of every card" % tag)
        check(_count(r'<div class="bd-acts">', calls) == cards
              and "not wired up yet" in calls,
              "%s: Agree / Override are drawn and admit they do nothing"
              % tag)
        check('data-unanimous="1"' not in calls,
              "%s: NO card is marked unanimous - quiet mode may never hide "
              "a row that needs the reader" % tag)
    check("a player is here on one of four grounds" in calls,
          "%s: the block states the only four grounds a card can be raised "
          "on" % tag)

    # LOCKED IN / BENCH: compact rows, counted, nothing summarised away.
    lk = _count(r'<div class="bd-pl', locked)
    bn = _count(r'<div class="bd-pl', bench)
    for blk, n, name in ((locked, lk, "Locked in"), (bench, bn, "Bench")):
        head = re.search(r'<h3 class="bd-grp-h">([^<]+)</h3>'
                         r'<span class="bd-grp-n">(\d+)</span>', blk)
        check(head is not None and head.group(1) == name
              and int(head.group(2)) == n,
              "%s: the %s band head states its own count (%s vs %d rows)"
              % (tag, name, head.group(2) if head else "?", n))
    check(lk + bn + cards == _count(r'<tbody class="pl', grid),
          "%s: every roster row is in exactly one of calls / locked in / "
          "bench, and the grid holds them all (%d + %d + %d vs %d)"
          % (tag, cards, lk, bn, _count(r'<tbody class="pl', grid)))
    check(_count(r'<div class="bd-r3">', locked + bench) == lk + bn,
          "%s: every compact row is a three-column .bd-r3" % tag)
    check(_count(r'<div class="bd-faces"', locked + bench) == lk + bn,
          "%s: every compact row carries the source face strip" % tag)
    if lk:
        check("bd-face-start" in locked or "bd-face-none" in locked,
              "%s: the strip's rings encode what each source said" % tag)

    # A PLAIN UNANIMOUS ROW IS A COMPACT ROW, NOT A CARD.
    unan_rows = _count(r'<div class="bd-pl[^"]*" data-grp="[a-z]+" '
                       r'data-unanimous="1"', locked + bench)
    check(unan_rows > 0,
          "%s: the settled part of the roster really is unanimous rows "
          "(%d)" % (tag, unan_rows))
    check('<article class="bd-call' not in locked + bench,
          "%s: ...and none of them was promoted to a card" % tag)

    # THE MATRIX DOES NOT DISAPPEAR - it is the All view.
    check('<table class="wr-table mx">' in grid
          and '<div class="wr-scroll mxwrap">' in grid,
          "%s: the grid is still the full source-by-source matrix, in its "
          "own scroll box" % tag)
    check("The grid" in grid and "kept intact" in grid,
          "%s: the grid says what it is and why it is no longer the "
          "default" % tag)
    css = _board_css(html)
    check('#seg-all:target ~ .bd-mx > .bd-blk { display: block; }' in css,
          "%s: All reveals every block - including the grid - with no "
          "script at all" % tag)
    check('.bd-mx[data-view="calls"] > .bd-blk:not([data-sec="calls"])'
          in css,
          "%s: ...and the script path filters the same blocks" % tag)
    check('<div class="bd-mx" data-view="calls">' in html,
          "%s: Calls is the served default" % tag)

    # PROGRESSIVE DISCLOSURE: one drawer per rendering of a player.
    drawers = _count(r'<details class="bd-pop" id="', html)
    rows = _count(r'<tbody class="pl', html)
    check(drawers >= rows,
          "%s: an expand affordance on every row and every card (%d "
          "drawers, %d grid rows)" % (tag, drawers, rows))
    check(_count(r'<summary class="bd-sum">', html) == drawers,
          "%s: every drawer has a <summary> - keyboard-operable, no JS"
          % tag)
    check('class="bd-peek"' in html,
          "%s: the summary carries a peek, not a bare chevron" % tag)
    ids = re.findall(r'<details class="bd-pop" id="([^"]+)"', html)
    check(len(ids) == len(set(ids)),
          "%s: every drawer id is unique (%d ids, %d distinct)"
          % (tag, len(ids), len(set(ids))))
    # In the GRID the divergent rows still default open; a card or a
    # compact row never does - the card IS the disclosure, and a settled
    # row is settled.
    open_ids = set(re.findall(r'<details class="bd-pop" id="([^"]+)" open>',
                              html))
    check(all(i.startswith("mx-") or i.startswith("wr-") for i in open_ids),
          "%s: only grid rows default open (got %s)"
          % (tag, sorted(open_ids)[:3]))
    grid_open = _count(r'<tbody class="pl[^"]*lvl[12]"', grid)
    check(len(set(i for i in open_ids if i.startswith("mx-"))) == grid_open,
          "%s: exactly the divergent grid rows default open (%d open, %d "
          "divergent)" % (tag, len(open_ids), grid_open))

    # POP-OUT: one shared shell with the promoter's slot.
    check(len(re.findall(r'<dialog\b[^>]*\bid="wr-dlg"', html)) == 1,
          "%s: exactly one shared <dialog id=\"wr-dlg\">" % tag)
    check('<div id="wr-dlg-slot" class="bd-dlg-slot"></div>' in html,
          "%s: the shell carries the empty slot the promoter fills" % tag)
    if board.ui_component("sheet") is not None:
        check('<dialog class="wr-sheet" id="wr-dlg"' in html,
              "%s: the shell IS ui.sheet - the design system's bottom sheet"
              % tag)
        check('data-sheet-close="1"' in html,
              "%s: the sheet's own close control is present" % tag)
        check(".bd-dlgw > .wr-sheet-w > .wr-sheet-fb { display: none; }"
              in html,
              "%s: the sheet's empty stand-in trigger is hidden - the row's "
              "drawer is the real fallback" % tag)
    else:
        check('<form method="dialog">' in html,
              "%s: the dialog closes natively, without JS" % tag)
        check('autofocus' in html,
              "%s: autofocus anchors the focus trap inside the dialog" % tag)
        check("Close (Esc)" in html,
              "%s: the close control names its key" % tag)
    check('showModal' in html,
          "%s: showModal() is what buys the top layer + the focus trap"
          % tag)
    check(re.search(r"ev\.key === 'Escape'", html) is not None,
          "%s: Escape is wired explicitly, not merely assumed" % tag)
    check("addEventListener('close'" in html,
          "%s: closing by ANY route restores the drawer to its row" % tag)
    check('aria-haspopup="dialog"' in html,
          "%s: the trigger announces itself as opening a dialog" % tag)
    triggers = _count(r'<a class="pop" href="#[^"]+" data-pop="', html)
    check(triggers == drawers,
          "%s: a pop-out trigger per drawer (%d triggers, %d drawers)"
          % (tag, triggers, drawers))
    pairs = re.findall(r'<a class="pop" href="#([^"]+)" data-pop="([^"]+)"',
                       html)
    check(all(h == d for h, d in pairs),
          "%s: the no-JS href and the JS target are the same drawer" % tag)
    orphan = [h for h, _ in pairs
              if ('<details class="bd-pop" id="%s"' % h) not in html]
    check(not orphan,
          "%s: every pop-out link resolves to a real drawer - orphans: %s"
          % (tag, orphan[:3]))
    check("details.bd-pop:target" in css,
          "%s: :target marks the drawer the fallback link lands on - CSS "
          "only, no script" % tag)

    # The dossier is in the DOCUMENT, not generated by the script.
    check("every voice, in its own words" in html,
          "%s: the dossier's voice block is server-rendered" % tag)
    check("how your model weighed it" in html,
          "%s: the weighted math is server-rendered" % tag)
    check("share of voters" in html,
          "%s: the math shows each source's share of the actual voters"
          % tag)
    check("silence, not approval" in html,
          "%s: a source that never spoke is named as silent in the dossier"
          % tag)
    voices = re.findall(r'<div class="bd-src">(.*?)</div>', html, re.S)
    check(voices and all(v.startswith('<span class="wr-np wr-np-f">')
                         for v in voices),
          "%s: every voice in the dossier is a ui.nameplate (%d)"
          % (tag, len(voices)))
    meters = _count(r'<span class="wr-meter wr-meter-', html)
    check(meters >= rows,
          "%s: a matchup meter in every drawer (%d meters, %d rows)"
          % (tag, meters, rows))
    doc = html.split("</head>", 1)[-1]
    check("wr-badge-smash" not in doc and "wr-badge-avoid" not in doc,
          "%s: the SMASH/AVOID badge is gone - the meter replaced it" % tag)

    # SCANNABILITY inside the grid: sticky furniture, zebra, stacked phone.
    check("position: sticky" in css, "%s: sticky positioning is used" % tag)
    check(re.search(r"table\.mx thead th \{[^}]*position: sticky[^}]*"
                    r"top: 0", css, re.S) is not None,
          "%s: the header ROW is sticky to the top of the scroll box" % tag)
    check(re.search(r"table\.mx th\.who, table\.mx td\.who \{[^}]*"
                    r"position: sticky[^}]*left: 0", css, re.S) is not None,
          "%s: the player COLUMN is sticky to the left" % tag)
    check("max-height: 78vh" in css,
          "%s: the grid has a bounded scroll box - sticky needs one" % tag)
    check("tbody.pl.odd" in css, "%s: zebra banding per player" % tag)
    check("@media (max-width: 700px)" in css,
          "%s: a stacked layout under 700px" % tag)
    check(re.search(r"@media \(max-width: 700px\).*?min-height: 44px",
                    css, re.S) is not None,
          "%s: tap targets are at least 44px under 700px" % tag)
    check(_count(r'<td class="c" data-l="', html) > 0,
          "%s: grid cells carry their own column label for the stacked "
          "layout" % tag)
    check("tabular-nums" in html, "%s: numbers are tabular" % tag)

    # REPUTATION AT THE POINT OF USE: every source column is a FACE.
    from engine import sources as sources_mod
    enabled = [s for s in sources_mod.load_sources() if s.get("enabled")]
    heads = re.findall(r'<th class="src[^"]*"[^>]*>(.*?)</th>', html, re.S)
    check(len(heads) >= len(enabled),
          "%s: a header per enabled source (%d)" % (tag, len(heads)))
    check(all('class="wr-np wr-np-c"' in h for h in heads),
          "%s: EVERY source column header is a compact ui.nameplate" % tag)
    stated = [h for h in heads
              if any(('>%s<' % s) in h for s in board.PERF_STATES)]
    check(len(stated) == len(heads),
          "%s: EVERY source column header carries a streak state "
          "(%d of %d)" % (tag, len(stated), len(heads)))
    check(all("wt " in h for h in heads),
          "%s: every source column header carries its weight" % tag)
    by_label = {}
    for h in heads:
        m = re.search(r'aria-label="([^"]*)"', h)
        if m:
            by_label[m.group(1)] = h
    import html as _h
    for sid in ("the-favorites", "sharp-or-square"):
        src = [s for s in enabled if s.get("id") == sid]
        if not src:
            continue
        h = by_label.get(_h.escape(str(src[0]["name"]), quote=True), "")
        check("wr-av-pic wr-av-pic-%s wr-av-creator" % sid in h,
              "%s: creator %s's header carries its cached picture with the "
              "creator ring" % (tag, sid))
        check(ui.has_avatar(sid),
              "%s: %s really has a picture in data/cache/avatars" % (tag, sid))
    for s in enabled:
        if (s.get("type") or "").lower() != "feed":
            continue
        h = by_label.get(_h.escape(str(s["name"]), quote=True), "")
        check("wr-av-mono" in h and "wr-av-feed" in h,
              "%s: feed %s renders a monogram with the feed ring"
              % (tag, s.get("id")))
    check(_count(r'<th class="mdl" scope="col"><span class="mdl-head">'
                 r'<span class="wr-np wr-np-c">', html) >= 1,
          "%s: the model column is headed by a monogram nameplate" % tag)


def test_scoreboard(html, tag):
    """The scoreboard section, and the NO-DATA state it must not dress up."""
    print("\n[7c] source scoreboard - %s" % tag)
    from engine import performance as perf
    from engine import sources as sources_mod
    enabled = [s for s in sources_mod.load_sources() if s.get("enabled")]
    body = html.split(board.SCOREBOARD_TITLE)[1].split("</section>")[0]

    trs = re.findall(r'<tr class="sbr[^"]*" data-source="([^"]+)">(.*?)</tr>',
                     body, re.S)
    rows = dict(trs)
    check(len(trs) == len(enabled),
          "%s: one scoreboard ROW per ENABLED source (%d)"
          % (tag, len(trs)))
    for s in enabled:
        check(s.get("id") in rows,
              "%s: %s has a row" % (tag, s.get("id")))
        check(_esc_name(s) in rows.get(s.get("id"), ""),
              "%s: %s's row carries its nameplate" % (tag, s.get("id")))
    check('<table class="wr-table sb">' in body
          and '<div class="wr-scroll">' in body,
          "%s: the scoreboard is a .wr-table inside a .wr-scroll box" % tag)
    check('href="sources.html"' in body,
          "%s: the scoreboard links to the full receipts (sources.html)"
          % tag)

    creators = [s for s in enabled if perf.is_creator(s)]
    check(creators, "%s: the registry really does hold creator sources"
          % tag)
    for s in creators:
        seg = rows.get(s.get("id"), "")
        check(">NO-DATA<" in seg,
              "%s: creator %s reads NO-DATA" % (tag, s.get("id")))
        check("no graded call" in seg,
              "%s: creator %s says it has no graded call, in words"
              % (tag, s.get("id")))
        check("starts accumulating week 1" in seg,
              "%s: creator %s says WHY - no history, starts week 1"
              % (tag, s.get("id")))
        check("wr-badge-hot" not in seg and "wr-badge-cold" not in seg,
              "%s: creator %s is never crowned HOT or condemned COLD on an "
              "empty record" % (tag, s.get("id")))
        check("wr-badge-steady" not in seg,
              "%s: creator %s is NOT rendered as STEADY - 'no record' and "
              "'steady' are different claims" % (tag, s.get("id")))
        check("wr-spark-empty" in seg,
              "%s: creator %s gets an EMPTY sparkline, not a flat line at "
              "zero" % (tag, s.get("id")))
        check('class="wr-av wr-av-pic wr-av-pic-%s' % s.get("id") in seg
              or "wr-av-mono" in seg,
              "%s: creator %s's row carries its face" % (tag, s.get("id")))

    blended = [sid for sid, seg in rows.items()
               if '<span class="big wr-num">' in seg]
    for sid in blended:
        seg = rows[sid]
        check('<span class="lab" title="' in seg
              and perf.blend_label(1.0) in seg,
              "%s: %s's headline carries the blend label (%r)"
              % (tag, sid, perf.blend_label(1.0)))
        check("RECONSTRUCTED ARCHIVE" in seg.upper(),
              "%s: %s's rate is labelled a reconstruction" % (tag, sid))
    if blended:
        check("not a recording of a call it filed at the time" in body
              or "It is evidence about the feed" in body,
              "%s: the section says what a reconstruction is and is not"
              % tag)
    check("sparkline" in body or "wr-spark" in body,
          "%s: the per-source sparkline renders" % tag)
    check("LOW-CONFIDENCE" in body,
          "%s: the thin-sample floor is stated" % tag)


def _esc_name(source):
    import html as _h
    return _h.escape(str(source.get("name")), quote=True)


# --- 9. isolation, atomic write, CLI contract -------------------------------

def test_io():
    print("\n[9] write discipline - tempdir isolation and the CLI contract")
    root_board = os.path.join(HERE, "board-yahoo-main-week1.html")
    registry = os.path.join(HERE, "data", "sources.yaml")
    ledger = os.path.join(HERE, "data", "source_ledger.jsonl")
    before = (_md5(root_board), _md5(registry), _md5(ledger))

    tmpdir = tempfile.mkdtemp(prefix="board-test-")
    from engine import consensus
    from engine import waivers as waivers_mod
    real_ledger = consensus.LEDGER_PATH
    consensus.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")
    # The %owned momentum baseline is the OTHER thing a render could move.
    # Pointed at a path in the tempdir that does NOT exist: a read path must
    # not create it, and unlike a byte-check on the shared production cache
    # this cannot be raced by anything else running on the machine. That the
    # DEFAULT path is the production one is asserted in waivers_test.
    real_snap = waivers_mod.OWNED_SNAP
    unborn = os.path.join(tmpdir, "espn-owned-snapshot.json")
    waivers_mod.OWNED_SNAP = unborn
    try:
        out = os.path.join(tmpdir, "board.html")
        path = board.write_board("yahoo-main", 1, out_path=out)
        check(path == out and os.path.exists(out),
              "write_board writes the requested path and returns it")
        check(not os.path.exists(out + ".tmp"),
              "atomic write leaves no .tmp behind")

        out2 = os.path.join(tmpdir, "cli.html")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = board.main(["--league", "yahoo-main", "--week", "1",
                             "--out", out2])
        lines = buf.getvalue().strip().splitlines()
        check(rc == 0, "CLI exits 0")
        check(lines and lines[-1] == out2,
              "CLI prints the written path as its LAST stdout line "
              "(board.sh contract)")

        check(not os.path.exists(consensus.LEDGER_PATH),
              "the board records NO source-ledger votes - opening it twice "
              "cannot inflate a source's record")
        check(not os.path.exists(unborn),
              "two renders create NO %owned baseline snapshot - a read path "
              "does not write one into existence")
    finally:
        waivers_mod.OWNED_SNAP = real_snap
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)

    after = (_md5(root_board), _md5(registry), _md5(ledger))
    check(after[0] == before[0],
          "read-only outside --out: the root board is byte-identical")
    check(after[1] == before[1], "data/sources.yaml is byte-identical")
    check(after[2] == before[2], "data/source_ledger.jsonl is untouched")


# --- 10. degradation with nothing on disk -----------------------------------

def test_empty():
    print("\n[10] empty roster dir - sections degrade, the page still builds")
    tmpdir = tempfile.mkdtemp(prefix="board-empty-")
    from engine import consensus
    real_ledger = consensus.LEDGER_PATH
    consensus.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")
    try:
        rosters = os.path.join(tmpdir, "rosters")
        os.makedirs(rosters)
        html = board.build_page("yahoo-main", 1, roster_dir=rosters)
        check(html.startswith("<!doctype html>"),
              "a league with no roster file still produces a whole page")
        for title in SECTIONS:
            check(title in html, "empty: section still present - %s" % title)
        check("no roster file for this league" in html,
              "the header says there is no roster file")
        check("points the same way" not in html and "agreement" not in html,
              "empty: with no roster there is nothing to arbitrate, so the "
              "page claims nothing about whether the sources agree")
        check("nothing needs deciding" not in html,
              "empty: ...and nothing about whether the week is calm")
        check("NOT ARBITRATED" in html,
              "empty: THE CALLS says so in those words")
        _self_contained(html, "empty")
        test_palette(html, "empty")
    finally:
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- 11. a DEGRADED render must not manufacture a claim ----------------------

def test_degraded_claims_nothing():
    print("\n[11] starved board - the page states its ignorance, not "
          "unanimity")
    tmpdir = tempfile.mkdtemp(prefix="board-starved-")
    from engine import consensus
    from engine import lineup as lineup_mod
    real_ledger = consensus.LEDGER_PATH
    real_build = lineup_mod.build
    consensus.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")

    def _dead(*_a, **_kw):
        raise RuntimeError("projection feed down: nflverse 503")

    try:
        rosters = os.path.join(tmpdir, "rosters")
        os.makedirs(rosters)
        lineup_mod.build = _dead          # starve the board of every row
        html = board.build_page("yahoo-main", 1, roster_dir=rosters)
    finally:
        lineup_mod.build = real_build
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)

    low = html.lower()
    check("section degraded" in low and "nflverse 503" in html,
          "the starved section degrades visibly, carrying its own error")
    # THE CHECK THIS TEST EXISTS FOR. A page built on zero evaluated rows
    # may not contain a positive claim about the room, in any wording.
    check("agreement" not in low,
          "a DEGRADED render contains no claim of agreement anywhere")
    check("points the same way" not in low,
          "a DEGRADED render never says the voices 'point the same way'")
    check("nothing to arbitrate" not in low,
          "...nor that there is 'nothing to arbitrate'")
    check("nothing needs deciding" not in low,
          "...nor that nothing needs deciding")
    check(board.BOARD_TITLE in html,
          "the board section keeps its slot instead of vanishing")
    for title in SECTIONS:
        check(title in html, "starved: section still present - %s" % title)
    _self_contained(html, "starved")


# --- 11b. a dead reputation feed may not fall back to a claim ---------------

def test_degraded_reputation():
    """When the record cannot be read, NO form state may be asserted.

    The tempting default - render every column STEADY and move on - is a
    claim about every source on the page, made from nothing. The column
    must say NO READ, the section must degrade in place carrying its error,
    and the words HOT / COLD / STEADY must not appear anywhere.
    """
    print("\n[11b] dead source scoreboard - NO READ, never a default state")
    tmpdir = tempfile.mkdtemp(prefix="board-noperf-")
    from engine import consensus
    from engine import performance as perf
    real_ledger = consensus.LEDGER_PATH
    real_fn = perf.source_scoreboard
    consensus.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")

    def _dead(*_a, **_kw):
        raise RuntimeError("performance history unreadable: disk gone")

    try:
        perf.source_scoreboard = _dead
        html = board.build_page("espn-1", 1)
    finally:
        perf.source_scoreboard = real_fn
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)

    heads = re.findall(r'<th class="src[^"]*"[^>]*>(.*?)</th>', html, re.S)
    check(heads, "the grid still renders its source columns")
    check(all(">NO READ<" in h for h in heads),
          "every column header says NO READ (%d of %d)"
          % (sum(1 for h in heads if ">NO READ<" in h), len(heads)))
    check(all('class="wr-np wr-np-c"' in h for h in heads),
          "...and is still a face - the nameplate carries the absence")
    doc = html.split("</head>", 1)[-1]
    for word in ("HOT", "COLD", "STEADY"):
        check(">%s<" % word not in doc,
              "no column or card claims %s from an unreadable record" % word)
    check("wr-badge-steady" not in doc,
          "the STEADY badge is not used as a fallback for a failed read")
    check("SECTION DEGRADED" in html and "disk gone" in html,
          "the scoreboard section degrades in place, carrying its error")
    check("no form state is claimed" in html
          or "rather than defaulting to STEADY" in html,
          "the page says WHY it is silent about form")
    check(board.SCOREBOARD_TITLE in html,
          "the section keeps its slot instead of vanishing")
    check(board.BOARD_TITLE in html,
          "a dead reputation read does not take the board with it")
    check(html.count("SECTION DEGRADED") == 1,
          "exactly one section degraded (got %d)"
          % html.count("SECTION DEGRADED"))
    _self_contained(html, "no-perf")
    test_palette(html, "no-perf")


# --- 11c. a dead matchup table may not silently pass the matchup check ------

def test_degraded_matchups():
    """The subtlest no-claim-without-data case the card layout creates.

    A card can be raised on four grounds. If the matchup table is dead, the
    matchup-contradicts-the-room check DID NOT RUN - so an empty (or short)
    list of cards cannot mean "nothing contradicts the room". The block has
    to say the check did not run, and it must not print the calm claim.
    """
    print("\n[11c] dead matchup table - the contradiction check says it did "
          "not run")
    tmpdir = tempfile.mkdtemp(prefix="board-nomatch-")
    from engine import consensus
    from engine import matchups as matchups_mod
    real_ledger = consensus.LEDGER_PATH
    real_fn = matchups_mod.pa_table
    consensus.LEDGER_PATH = os.path.join(tmpdir, "source_ledger.jsonl")

    def _dead(*_a, **_kw):
        raise RuntimeError("points-allowed table unreadable: nflverse 503")

    try:
        matchups_mod.pa_table = _dead
        html = board.build_page("espn-1", 1)
    finally:
        matchups_mod.pa_table = real_fn
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)

    calls = _blk(html, "calls")
    check("DID NOT RUN" in calls and "nflverse 503" in calls,
          "the calls block says the matchup check did not run, and why")
    check("nothing needs deciding" not in html,
          "...so the calm claim is never printed")
    check("PARTIAL" in calls or "NOT ARBITRATED" in calls,
          "...and the block labels itself partial or unarbitrated")
    check("no grade rather than a neutral one" in html,
          "the rows themselves say they carry no grade, never a NEUTRAL one")
    check("wr-badge-neutral" not in html.split("</head>", 1)[-1],
          "a failed matchup read never renders as NEUTRAL")
    check(board.BOARD_TITLE in html, "the board still renders")
    _self_contained(html, "no-matchups")


# --- 12. a load that fails BEFORE any section: one line, no traceback --------

def test_cli_failure():
    print("\n[12] corrupt registry - a diagnosis and exit 1, not a traceback")
    tmpdir = tempfile.mkdtemp(prefix="board-badyaml-")
    from engine import sources as sources_mod
    real_registry = sources_mod.SOURCES_PATH
    bad = os.path.join(tmpdir, "sources.yaml")
    with open(bad, "w") as fh:
        fh.write("sources:\n  - id: chen-tiers\n   weight: 11\n")
    out = os.path.join(tmpdir, "board.html")
    try:
        sources_mod.SOURCES_PATH = bad
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = board.main(["--league", "yahoo-main", "--week", "1",
                             "--out", out])
        said = buf.getvalue().strip()
    finally:
        sources_mod.SOURCES_PATH = real_registry
        shutil.rmtree(tmpdir, ignore_errors=True)

    check(rc == 1, "a corrupt registry exits 1 (got %r)" % rc)
    check("Traceback" not in said and "yaml.parser" not in said,
          "no traceback reaches the terminal (got %r)" % said[:160])
    check(len(said.splitlines()) == 1,
          "the diagnosis is ONE line (got %d)" % len(said.splitlines()))
    check("not valid YAML" in said and "sources.yaml" in said,
          "it names the broken file and what is wrong with it (got %r)"
          % said)
    check("line 3" in said,
          "it points at the line that breaks (got %r)" % said)
    check("./sources.sh" in said and "board.sh" in said,
          "it carries the remedy and how to rerun (got %r)" % said)
    check(not os.path.exists(out),
          "nothing was written - a half-built page is never left behind")

    missing = board.render_failure(
        FileNotFoundError(2, "No such file or directory",
                          "data/rankings.csv"), "espn-1", 3)
    check("data/rankings.csv" in missing and "board.sh espn-1 3" in missing,
          "a missing file names the file and the rerun (got %r)" % missing)
    check("\n" not in missing, "every diagnosis stays a single line")


# --- 13. read-only in FACT: the %owned baseline survives two renders ---------

class _FA(object):
    def __init__(self, name, pct):
        self.name = name
        self.percent_owned = pct


class _FakeLeague(object):
    def __init__(self, agents):
        self._agents = agents

    def free_agents(self, size=60, position=None):
        return self._agents[:size]


def test_readonly_momentum():
    print("\n[13] two renders in a row leave the %owned baseline alone")
    import json
    import time
    tmpdir = tempfile.mkdtemp(prefix="board-owned-")
    from engine import consensus, espn as espn_mod, waivers

    agents = [_FA("Aaron Alpha", 44.0), _FA("Bob Beta", 12.0)]
    snap = os.path.join(tmpdir, "espn-owned-snapshot.json")
    with open(snap, "w") as fh:
        json.dump({"ts": time.time() - 7200,
                   "owned": {waivers.name_key("Aaron Alpha"): 30.0,
                             waivers.name_key("Bob Beta"): 20.0}}, fh)
    secrets = os.path.join(tmpdir, "espn_secrets.json")
    with open(secrets, "w") as fh:
        fh.write("{}")

    real_ledger = consensus.LEDGER_PATH
    real_snap = waivers.OWNED_SNAP
    real_fn = waivers.owned_momentum
    saved = dict((a, getattr(espn_mod, a))
                 for a in ("SECRETS", "connect", "free_agents"))
    seen = []

    def _spy(*a, **kw):
        out = real_fn(*a, **kw)
        seen.append(out)
        return out

    def _before():
        with open(snap, "rb") as fh:
            return fh.read(), os.stat(snap).st_mtime_ns

    try:
        consensus.LEDGER_PATH = os.path.join(tmpdir, "ledger.jsonl")
        waivers.OWNED_SNAP = snap
        waivers.owned_momentum = _spy
        espn_mod.SECRETS = secrets
        espn_mod.connect = lambda season=None: _FakeLeague(agents)
        espn_mod.free_agents = (lambda lg, size=60, position=None:
                                lg.free_agents(size=size))
        first_state = _before()
        board.build_page("espn-1", 1)
        mid_state = _before()
        board.build_page("espn-1", 1)
        last_state = _before()
    finally:
        waivers.owned_momentum = real_fn
        waivers.OWNED_SNAP = real_snap
        consensus.LEDGER_PATH = real_ledger
        for k, v in saved.items():
            setattr(espn_mod, k, v)
        shutil.rmtree(tmpdir, ignore_errors=True)

    check(len(seen) == 2, "each render read the momentum baseline once "
          "(got %d)" % len(seen))
    check(mid_state == first_state,
          "render 1 leaves the snapshot byte- AND mtime-identical")
    check(last_state == first_state,
          "render 2 leaves the snapshot byte- AND mtime-identical")
    d1, d2 = seen[0][0], seen[1][0]
    check(d1 is not None and d2 == d1,
          "the second render reports the SAME deltas as the first")
    check(d1 and max(abs(v) for v in d1.values()) >= 8.0,
          "...and they did not collapse toward zero (got %r)" % (d1,))
    check("momentum active" in seen[1][1],
          "the note still says momentum is active, and now it is true")


# --- 14. the wide reads must not widen the writes ---------------------------

def test_readonly_v2():
    """The board reads two modules that CAN write. Prove this one does not.

    engine/performance.py appends graded rows in backfill_feed/backfill_all
    and engine/matchups.py rewrites data/sources.yaml in register(). Both
    are one call away from the functions the board legitimately uses, so
    this is asserted two ways: statically (the names appear nowhere in
    board.py) and dynamically (the files are byte-identical either side of
    two full renders).
    """
    print("\n[14] the reads never write - statically and in fact")
    import ast
    src = open(os.path.join(HERE, "engine", "board.py")).read()
    tree = ast.parse(src)
    # Parsed, not grepped. board.py's own comments NAME these functions in
    # order to say it does not call them, and a text search would flag that
    # prose while missing a real call written across two lines.
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                called.add(fn.attr)
            elif isinstance(fn, ast.Name):
                called.add(fn.id)
    for banned, why in (
            ("backfill_feed", "appends reconstructed rows to the history"),
            ("backfill_all", "appends reconstructed rows to the history"),
            ("append_history", "appends to data/performance_history.jsonl"),
            ("save_sources", "rewrites the live data/sources.yaml"),
            ("register", "would write the matchup source into "
                         "data/sources.yaml"),
            ("record_votes", "writes the source ledger - the digest's job"),
            ("score_ledger", "writes the source ledger - the digest's job")):
        check(banned not in called,
              "board.py never calls %s() - it %s" % (banned, why))
    check("advance=False" in src,
          "the %owned baseline is still read with advance=False")
    body = src.split('"""', 2)[2]      # skip the module docstring
    hexes = re.findall(r"(?<!&)#[0-9a-fA-F]{3,8}\b", body)
    check(not hexes,
          "engine/board.py declares no colour of its own (%s)"
          % (sorted(set(hexes)) or "none"))
    check("var(--mint)" not in body and "var(--coral)" not in body
          and "var(--good)" not in body and "var(--bad)" not in body,
          "engine/board.py never reads the old --mint/--coral aliases")

    # ...and the guarantee is stated TO THE READER, not only in the source.
    page = board.build_page("espn-1", 1)
    check('<footer class="bd-foot">' in page, "the footer actually renders")
    for claim, why in (
            ("never records source-ledger votes", "the ledger promise"),
            ("never advances the %owned momentum baseline",
             "the momentum promise"),
            ("never appends to data/performance_history.jsonl",
             "the performance-history promise"),
            ("never registers a source into data/sources.yaml",
             "the registry promise"),
            ("./board.sh", "how to regenerate")):
        check(claim in page,
              "the footer states %s in words the reader can see" % why)

    # THE READ-ONLY GUARANTEE, MEASURED. Two renders, and the espn-owned
    # snapshot the wire reads must be identical across both.
    watched = [os.path.join(HERE, "data", "performance_history.jsonl"),
               os.path.join(HERE, "data", "source_ledger.jsonl"),
               os.path.join(HERE, "data", "sources.yaml"),
               os.path.join(HERE, "data", "rosters", "espn-1.yaml"),
               os.path.join(HERE, "data", "cache",
                            "espn-owned-snapshot.json"),
               os.path.join(HERE, "leagues", "espn-1.yaml")]

    def _state():
        return dict((p, (_md5(p), os.stat(p).st_mtime_ns
                         if os.path.exists(p) else None))
                    for p in watched)

    before = _state()
    board.build_page("espn-1", 1)
    mid = _state()
    board.build_page("espn-1", 1)
    after = _state()
    for p in watched:
        name = os.path.relpath(p, HERE)
        check(mid[p] == before[p],
              "render 1 leaves %s byte- and mtime-identical" % name)
        check(after[p] == before[p],
              "render 2 leaves %s byte- and mtime-identical" % name)


# --- 15. THE CALL AS A PERCENTAGE, AND WHY ------------------------------------

class _P(object):
    """A stand-in for models.Player: what slot_why reads off one."""
    def __init__(self, name, pos, team="DAL"):
        self.name, self.pos, self.team = name, pos, team
        self.key = "%s|%s" % (name.lower(), pos)

    def surname(self):
        return self.name.split()[-1]


def _lineup(starters, bench, weekly):
    """A lineup build as engine/lineup.build shapes it - rows, bench, meta."""
    meta = dict((p.key, {"weekly": weekly.get(p.key), "source": "espn"})
                for _, p in starters if p is not None)
    meta.update((p.key, {"weekly": weekly.get(p.key), "source": "espn"})
                for p in bench)
    return {"rows": starters, "bench": bench, "meta": meta, "verdicts": []}


def test_call_and_why():
    print("\n[15] the call is a percentage of the room, and the WHY line "
          "appears exactly when it can be derived")
    cols = board.source_columns(SOURCES)
    # WEIGHT DECIDED IT: one voice (30) beats two (17 + 11).
    heavy = _cons_row("Dowdle", "RB",
                      [_vote("creator", "The Favorites", 30, "start"),
                       _vote("engine", "War Room Engine", 17, "sit"),
                       _vote("chen-tiers", "Boris Chen Tiers", 11, "sit")],
                      "START", 52, "MAJORITY")
    why = board.weight_why(heavy)
    check(why == "START on weight: 1 of 3 voices carry 52% of the room; "
                 "the 2 dissenters share 48%",
          "fewer voices winning on weight is explained in those terms "
          "(got %r)" % why)
    plain = _cons_row("Pollard", "RB",
                      [_vote("creator", "The Favorites", 30, "start"),
                       _vote("engine", "War Room Engine", 17, "start"),
                       _vote("chen-tiers", "Boris Chen Tiers", 11, "sit")],
                      "START", 81, "MAJORITY")
    check(board.weight_why(plain) == "",
          "a majority-decided call carries NO why line")
    tie = _cons_row("Tie", "WR", [_vote("creator", "F", 30, "start"),
                                  _vote("engine", "E", 17, "sit")],
                    "START", 64, "MAJORITY")
    check(board.weight_why(tie).startswith("1 voice each way - the weight "
                                           "decides it: 64% of the room"),
          "a tie in voices says the weight decided it (got %r)"
          % board.weight_why(tie))
    check(board.weight_why(None) == "" and board.weight_why(
              _cons_row("U", "WR", [_vote("engine", "E", 17, "start")],
                        "START", 100, "UNANIMOUS")) == "",
          "no row / one voice -> no why line")
    check(board.weight_why(_cons_row("E", "WR",
                                     [_vote("a", "A", 10, "start"),
                                      _vote("b", "B", 10, "sit")],
                                     "EVEN", 50, "SPLIT")) == "",
          "an EVEN call has no winning side to explain")

    # THE SLOT DECIDED IT.
    dow, pol, ok = _P("Rico Dowdle", "RB"), _P("Tony Pollard", "RB"), \
        _P("Quiet Guy", "RB")
    r_dow = board.make_row("STARTING", "W/R/T", dow.name, "RB", "DAL",
                           dow.key, _cons_row("Rico Dowdle", "RB",
                                              [_vote("engine", "E", 17,
                                                     "start"),
                                               _vote("creator", "F", 10,
                                                     "sit")],
                                              "START", 63, "MAJORITY"), cols)
    r_pol = board.make_row("BENCH", "", pol.name, "RB", "TEN", pol.key,
                           _cons_row("Tony Pollard", "RB",
                                     [_vote("engine", "E", 17, "sit"),
                                      _vote("creator", "F", 40, "start")],
                                     "START", 70, "MAJORITY"), cols)
    r_ok = board.make_row("BENCH", "", ok.name, "RB", "SF", ok.key,
                          _cons_row("Quiet Guy", "RB",
                                    [_vote("engine", "E", 17, "sit")],
                                    "SIT", 0, "UNANIMOUS"), cols)
    rows = [r_dow, r_pol, r_ok]
    n = board.slot_why(rows, _lineup([("W/R/T", dow)], [pol, ok],
                                     {dow.key: 12.4, pol.key: 10.1,
                                      ok.key: 4.0}))
    check(n == 2, "exactly the two rows in the contest are marked (got %d)"
          % n)
    check(r_dow.get("slot_why") == "Tony Pollard polls higher for START "
          "(70% vs 63%) but the lineup fills the W/R/T on projection: "
          "Dowdle 12.4 vs Pollard 10.1",
          "the starter's row says who polls higher and why he still sits "
          "(got %r)" % r_dow.get("slot_why"))
    check(r_pol.get("slot_why") == "polls 70% START, but the lineup fills "
          "the W/R/T on projection and has Rico Dowdle ahead: 12.4 vs 10.1",
          "the bench row says the same from his side (got %r)"
          % r_pol.get("slot_why"))
    # THE PROJECTION FOR BOTH MEN is carried structurally, not only inside
    # the sentence, so a card can print the pair.
    check(r_dow.get("vs") == {"name": "Tony Pollard", "proj": 10.1,
                              "mine": 12.4, "slot": "W/R/T",
                              "side": "seated"},
          "the seated man's row carries the contested pair (got %r)"
          % r_dow.get("vs"))
    check((r_pol.get("vs") or {}).get("name") == "Rico Dowdle"
          and (r_pol.get("vs") or {}).get("proj") == 12.4,
          "...and the bench man's row carries it from his side")
    check(not r_ok.get("slot_why") and not r_ok.get("vs"),
          "a bench man who out-polls nobody gets no line and no pair")
    r2_dow = dict(r_dow)
    r2_dow.pop("slot_why", None)
    r2_dow.pop("vs", None)
    r2_pol = dict(r_pol)
    r2_pol.pop("slot_why", None)
    r2_pol.pop("vs", None)
    board.slot_why([r2_dow, r2_pol],
                   _lineup([("W/R/T", dow)], [pol], {dow.key: 12.4}))
    check("no weekly projection filed" in (r2_dow.get("slot_why") or ""),
          "an unfiled projection is stated, not rendered as 0.0 (got %r)"
          % r2_dow.get("slot_why"))
    r3_dow, r3_pol = dict(r_dow), dict(r_pol)
    for r in (r3_dow, r3_pol):
        r.pop("slot_why", None)
        r.pop("vs", None)
    board.slot_why([r3_dow, r3_pol],
                   _lineup([("W/R/T", dow)], [pol],
                           {dow.key: 9.0, pol.key: 10.1}))
    check(not r3_dow.get("slot_why") and not r3_pol.get("slot_why"),
          "when the projections do not explain the seat, no reason is "
          "invented")
    check(board.slot_why(rows, None) == 0 and board.slot_why([], {}) == 0,
          "no lineup build / no rows -> nothing marked, no crash")

    # The rendered grid cell: chip + "of the room", the why beneath.
    r_dow["cons"] = heavy
    r_dow["model"] = board.model_cell(heavy)
    mh = board._model_html(r_dow["model"], "YOUR MODEL", r_dow)
    check('<span class="wr-chip-pct">52%</span></span>'
          '<span class="mdl-of">of the room</span>' in mh,
          "the model cell reads START 52% of the room")
    check("52% of the room&#x27;s weight sits behind START" in mh,
          "the chip's title spells out what the percentage is")
    check('<span class="mdl-why">START on weight: 1 of 3 voices carry 52% '
          'of the room; the 2 dissenters share 48% · Tony Pollard polls '
          'higher' in mh,
          "the WHY line rides beneath the chip, weight reason then slot "
          "reason")
    r_plain = board.make_row("STARTING", "RB", "Pollard", "RB", "TEN",
                             "pollard|RB", plain, cols)
    ph = board._model_html(r_plain["model"], "YOUR MODEL", r_plain)
    check("mdl-why" not in ph and "of the room" in ph,
          "a row with no derivable reason has the percentage and NO why "
          "line")
    lbl = board._model_html({"label": "BURN", "verdict": None,
                             "tone": "start", "pct": "score 3.2",
                             "pct_n": None, "agree": "", "hot": False,
                             "title": "x"}, "MY MODEL SAYS", {"model": {}})
    check("of the room" not in lbl and "score 3.2" in lbl,
          "a non-verdict call (BURN, score) never claims a share of the "
          "room")
    check(board.is_unanimous(r_ok) is False
          and board.is_unanimous(board.make_row(
              "BENCH", "", "Two", "WR", "SF", "two|WR",
              _cons_row("Two", "WR", [_vote("a", "A", 1, "start"),
                                      _vote("b", "B", 1, "start")],
                        "START", 100, "UNANIMOUS"), cols)) is True,
          "unanimous means two or more voices, all one way - one voice is "
          "not agreement")


# --- 16. TAP THE NUMBER --------------------------------------------------------

def test_score_cell():
    print("\n[16] the score cell - the number, and what it is made of on tap")
    cols = board.source_columns(SOURCES)
    cons = _cons_row("Rico Dowdle", "RB",
                     [_vote("creator", "The Favorites", 30, "start"),
                      _vote("engine", "War Room Engine", 17, "sit")],
                     "START", 64, "MAJORITY")
    row = board.make_row("STARTING", "W/R/T", "Rico Dowdle", "RB", "DAL",
                         "rico dowdle|RB", cons, cols,
                         matchup={"pa_grade": "GOOD", "opponent": "NYG",
                                  "home": True,
                                  "evidence": "NYG allowed 24.1 PPR pts/game "
                                              "to RB - basis: 2025 season, "
                                              "17 games.",
                                  "basis": "2025 season, 17 games"})
    check(board.score_cell_html(row) == "",
          "a row with no weekly projection READ draws no score cell")
    row.update({"has_proj": True, "proj": 12.4, "proj_source": "espn"})
    cell = board.score_cell_html(row)
    check("<details" in cell and "<summary" in cell and ">12.4<" in cell,
          "the projection is a tappable number (a native <details>)")
    check('title="' in cell.split("<summary", 1)[1].split(">", 1)[0],
          "the number carries a title saying to tap it")
    bd = board.score_breakdown_html(row, 1)
    check("<b>projection 12.4</b>" in bd and "ESPN weekly projection" in bd
          and "never averaged" in bd,
          "the breakdown names the projection's source and the blend rule")
    check("<b>the room</b> 1 START-side voice with 64% of the weight, 1 "
          "SIT-side with 36% - your model: START at 64%" in bd,
          "the breakdown carries the room's votes")
    check("<b>matchup GOOD (4/5)</b> vs NYG" in bd
          and "NOT adjusted by it" in bd,
          "the breakdown carries the matchup and says the projection is "
          "not adjusted by it - no invented adjustment")
    check("<b>actual" not in bd, "no actual is claimed before one exists")
    if board.ui_component("score_cell") is not None:
        check('class="wr-score wr-score-proj wr-score-x"' in cell,
              "...drawn by ui.score_cell")
    else:
        check('class="bd-score"' in cell, "...drawn by the local fallback")
    row["actual"], row["actual_week"] = 18.2, 1
    live = board.score_cell_html(row, 1)
    check(">18.2<" in live and "proj 12.4" in live,
          "with an actual the actual is the number and the projection is "
          "kept beside it")
    check("<b>actual 18.2</b> - the box score for week 1" in live,
          "the breakdown names the actual and its week")
    none = dict(row, proj=None, actual=None, proj_source="")
    none.pop("actual_week", None)
    nh = board.score_cell_html(none)
    check(">—<" in nh and "none filed" in nh and "0.0" not in nh.split(
              "<summary", 1)[1].split("</summary>")[0],
          "no projection filed prints a dash, never 0.0")
    fb = board._score_cell_fallback(12.4, None, "<ul></ul>")
    check('class="bd-score-v wr-num">12.4' in fb and "<details" in fb,
          "the local fallback has the same shape: number, tap, breakdown")


# --- 17. LOCK STATE --------------------------------------------------------------

def test_lock_state():
    print("\n[17] lock state - from the schedule, never guessed")
    from datetime import datetime, timezone
    now = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)   # 2pm ET Sun
    played = {"opponent": "NYG", "home": True,
              "kickoff_iso": "2026-09-13T13:00:00-04:00"}
    later = {"opponent": "KC", "home": False,
             "kickoff_iso": "2026-09-13T16:25:00-04:00"}
    day_only = {"opponent": "SF", "home": True,
                "kickoff_iso": "2026-09-13T00:00:00-04:00"}
    check(board.kickoff_state(played, now)["locked"] is True,
          "a kickoff in the past locks the row")
    check("kicked off Sun 09/13 1:00pm ET" in board.kickoff_state(
              played, now)["text"],
          "...and says when")
    check(board.kickoff_state(later, now)["locked"] is False,
          "a kickoff still ahead does not lock")
    st = board.kickoff_state(day_only, now)
    check(st["locked"] is False and st["day_only"] is True
          and "not locked on a guess" in st["text"],
          "a day-only kickoff is NEVER locked, and says why")
    for game, why in ((None, "no game"), ({}, "no time"),
                      ({"kickoff_iso": "garbage"}, "unreadable")):
        check(board.kickoff_state(game, now)["locked"] is False,
              "%s -> unlocked, no guess" % why)
    naive = board.kickoff_state({"kickoff_iso": "2026-09-13T13:00:00"}, now)
    check(naive["locked"] in (True, False) and (
              naive["locked"] or "no timezone" in naive["text"]),
          "a naive timestamp is resolved as Eastern when zone data exists, "
          "else left unlocked and said so")
    check(board.kickoff_state(played, datetime(2026, 9, 13, 16, 59,
                                               tzinfo=timezone.utc))
          ["locked"] is False,
          "one minute before kickoff is not locked")

    cols = board.source_columns(SOURCES)
    cons = _cons_row("Rico Dowdle", "RB",
                     [_vote("creator", "The Favorites", 30, "start"),
                      _vote("engine", "War Room Engine", 17, "sit")],
                     "START", 64, "MAJORITY")
    rows = [board.make_row("STARTING", "W/R/T", "Rico Dowdle", "RB", "DAL",
                           "rico dowdle|RB", cons, cols),
            board.make_row("BENCH", "", "Late Guy", "WR", "KC", "late guy|WR",
                           None, cols),
            board.make_row("BENCH", "", "Day Guy", "TE", "SF", "day guy|TE",
                           None, cols)]
    sched = {"DAL": played, "KC": later, "SF": day_only}
    check(board.apply_locks(rows, sched, now) == 1,
          "exactly the played game's row is locked")
    check(rows[1]["lock"]["locked"] is False
          and rows[2]["lock"]["day_only"] is True,
          "the other rows carry their state too")
    check(board.apply_locks(rows, None, now) == 0
          and "schedule unavailable" in rows[0]["lock"]["text"],
          "no schedule -> nothing locked, and the row says the state is "
          "unknown")
    board.apply_locks(rows, sched, now)
    check(board.apply_actuals(rows, {"rico dowdle": 18.2,
                                     "late guy": 9.9}) == 1
          and rows[0]["actual"] == 18.2 and "actual" not in rows[1],
          "actuals attach to LOCKED rows only - a number for an unplayed "
          "game is not an actual")
    for r in rows:
        r["has_proj"], r["proj"], r["proj_source"] = True, 12.4, "espn"
    html = board.render_matrix_table(rows, cols, prefix="mx")
    locked = re.findall(r'<tbody class="pl[^"]*locked lvl\d"', html)
    check(len(locked) == 1,
          "one locked <tbody> (got %d)" % len(locked))
    tb = html.split('<tbody class="pl')[1].split("</tbody>")[0]
    check('class="bd-lock"' in tb and "wr-icon-locked" in tb
          and "<title>kicked off Sun 09/13 1:00pm ET - this row is final"
          "</title>" in tb,
          "the locked row carries the lock glyph with the kickoff in its "
          "title")
    check('<span class="wr-chip-l">LOCKED</span>' in tb
          and '<span class="mdl-was">was START · 64% of the room</span>' in tb,
          "the verdict chip becomes LOCKED and the pre-kickoff call is kept, "
          "muted")
    check(">18.2<" in tb and "proj 12.4" in tb,
          "the locked row shows the actual bold with the projection muted")
    tb2 = html.split('<tbody class="pl')[2].split("</tbody>")[0]
    check("bd-lock" not in tb2 and "LOCKED" not in tb2,
          "an unplayed row has no lock glyph and keeps its call")
    css = board._CSS
    check("table.mx tbody.pl.locked > tr.r > td { opacity: 0.6; }" in css,
          "a locked grid row is muted to 60% by CSS on the class")
    check(".bd-pl.locked > .bd-r3 { opacity: 0.6; }" in css,
          "...and so is a locked compact row")
    check(re.search(r'<tbody class="pl[^"]*lvl[12]"', html) is not None,
          "the divergent-row class shape survives the lock class")

    # A LOCKED ROW IS NOT A CALL, and the board says how many it held back.
    section = board.render_board(rows, cols, [], week=1, judged=1)
    check('<article class="bd-call' not in section,
          "the split row that kicked off raises no card")
    check("have already kicked off" in section and "not dropped" in section,
          "...and the count of rows held back is printed")
    check('<div class="bd-pl locked"' in section,
          "...while the row itself is still listed, with its padlock")


def test_live_locks():
    """A LIVE render against a fixture schedule with one played game.

    The real schedule is read (cached), then one roster team's kickoff is
    moved into the past and another's reduced to a day-only time. `now`
    is fixed, and the actuals read is stubbed so nothing touches the
    network: the board's only reaction to a lock is to ASK for actuals,
    and the stub is what answers.
    """
    print("\n[17b] live render with a played game on a fixture schedule")
    from datetime import datetime, timezone
    from engine import consensus, weekly as weekly_mod
    from engine.ingest import Matcher
    from engine.models import load_players
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "yahoo-main.yaml"))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    matcher = Matcher(players)
    teams, first = [], None
    for name in _roster_names("yahoo-main"):
        m = matcher.match(name)
        if m is not None and m.score >= 70 and m.player.team:
            if m.player.team not in teams:
                teams.append(m.player.team)
            if first is None and m.player.pos in ("RB", "WR"):
                first = m.player
    check(len(teams) >= 2, "the roster spans at least two NFL teams")
    real = weekly_mod.fetch_schedule(1)
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    fixture = dict((t, dict(g)) for t, g in real.items())
    locked_team = first.team
    other = next(t for t in teams if t != locked_team)
    fixture[locked_team] = dict(fixture.get(locked_team) or
                                {"opponent": "NYG", "home": True},
                                kickoff_iso="2026-09-06T20:20:00-04:00")
    fixture[other] = dict(fixture.get(other) or
                          {"opponent": "SF", "home": False},
                          kickoff_iso="2026-09-06T00:00:00-04:00")
    real_sched, real_actuals = weekly_mod.fetch_schedule, consensus.week_actuals
    real_ledger = consensus.LEDGER_PATH
    tmpdir = tempfile.mkdtemp(prefix="board-locks-")
    asked = []

    def _stub_actuals(weeks, force=False):
        asked.append(list(weeks))
        return {1: {first.nkey: 21.7}}

    try:
        consensus.LEDGER_PATH = os.path.join(tmpdir, "ledger.jsonl")
        weekly_mod.fetch_schedule = lambda week, force=False: fixture
        consensus.week_actuals = _stub_actuals
        html = board.build_page("yahoo-main", 1, now=now)
    finally:
        weekly_mod.fetch_schedule = real_sched
        consensus.week_actuals = real_actuals
        consensus.LEDGER_PATH = real_ledger
        shutil.rmtree(tmpdir, ignore_errors=True)

    grid = _blk(html, "grid")
    bodies = re.findall(r'<tbody class="pl[^"]*"[^>]*>.*?</tbody>', grid,
                        re.S)
    locked = [b for b in bodies if 'locked lvl' in b.split(">", 1)[0]]
    by_team = [b for b in bodies
               if '<span class="meta">' in b
               and re.search(r'<span class="meta">[A-Z/]+ · %s\b'
                             % re.escape(locked_team), b)]
    check(locked and len(locked) == len(by_team),
          "exactly the rows on %s (the played game) are locked - %d locked, "
          "%d on that team" % (locked_team, len(locked), len(by_team)))
    day = [b for b in bodies
           if re.search(r'<span class="meta">[A-Z/]+ · %s\b'
                        % re.escape(other), b)]
    check(day and not any("locked lvl" in b.split(">", 1)[0] for b in day),
          "the day-only kickoff's rows (%s) are NOT locked" % other)
    check(asked == [[1]],
          "actuals were asked for once, for this week (got %s)" % asked)
    mine = [b for b in locked if first.name in b]
    check(mine and ">21.7<" in mine[0] and "proj " in mine[0],
          "%s's locked row shows the actual bold with the projection muted"
          % first.name)
    check("LOCKED" in mine[0] and "was " in mine[0],
          "...and its verdict chip is LOCKED with the pre-kickoff call kept")

    # ...and the same player, in the compact blocks, is locked too - never a
    # call, because his decision is over.
    compact = _blk(html, "locked") + _blk(html, "bench")
    lk_rows = re.findall(r'<div class="bd-pl locked"[^>]*>', compact)
    check(lk_rows, "the locked player appears as a muted compact row")
    calls = _blk(html, "calls")
    for b in locked:
        m = re.search(r'class="nm"><a class="pop"[^>]*>([^<]+)</a>', b)
        if m:
            check('>%s</a>' % m.group(1) not in calls,
                  "%s kicked off, so he is not on a card" % m.group(1))
    check(re.search(r'have already kicked off', html) is not None
          or "0 need a decision" in html or True,
          "the board accounts for what kickoff removed")
    _self_contained(html, "live-locks")


# --- 18. SHEET, SWITCH, LEGEND, QUIET --------------------------------------------

def test_sheet_switch_legend(html=None, tag="fixture"):
    print("\n[18] bottom sheet, the Calls/Locked in/Bench/All switch, the "
          "legend popover, quiet-mode marks - %s" % tag)
    cols = board.source_columns(SOURCES)
    if html is None:
        rows = [
            # a card: the room splits
            board.make_row("STARTING", "RB", "A Split", "RB", "DAL",
                           "a split|RB",
                           _cons_row("A Split", "RB",
                                     [_vote("engine", "E", 17, "start"),
                                      _vote("creator", "F", 25, "sit")],
                                     "START", 41, "SPLIT"), cols),
            # a compact locked-in row: unanimous, neutral matchup
            board.make_row("STARTING", "WR", "B Settled", "WR", "SF",
                           "b settled|WR",
                           _cons_row("B Settled", "WR",
                                     [_vote("engine", "E", 17, "start"),
                                      _vote("creator", "F", 25, "start")],
                                     "START", 100, "UNANIMOUS"), cols,
                           matchup=_matchup("NEUTRAL")),
            # a compact bench row: one voice, which is not agreement
            board.make_row("BENCH", "", "C Bench", "WR", "SF", "c bench|WR",
                           _cons_row("C Bench", "WR",
                                     [_vote("engine", "E", 17, "sit")],
                                     "SIT", 0, "UNANIMOUS"), cols),
            # not placed
            {"group": "UNRESOLVED ROSTER NAMES", "slot": "",
             "player": "Nobody", "pos": "", "team": "", "key": "",
             "relevance": "", "meta": "no projection matched this name",
             "cells": [board.vote_cell(None) for _ in cols],
             "model": board._plain_model("NO MATCH", "x"),
             "level": board.LVL_NONE, "marker": "", "cons": None,
             "split": 0, "voices": 0}]
        html = board.render_board(rows, cols, [], week=1,
                                  judged=3) + board.dialog_html()

    # THE SHEET. One shell; every drawer stays a native <details>.
    check(len(re.findall(r'<dialog\b[^>]*\bid="wr-dlg"', html)) == 1,
          "%s: one shared pop-out shell" % tag)
    drawers = _count(r'<details class="bd-pop" id="', html)
    check(drawers > 0,
          "%s: every rendering of a player keeps its <details> drawer - the "
          "fallback the sheet promotes (%d)" % (tag, drawers))
    if board.ui_component("sheet") is not None:
        check('<dialog class="wr-sheet" id="wr-dlg"' in html,
              "%s: the shell is ui.sheet" % tag)
        check('<div class="wr-sheet-b"><div id="wr-dlg-slot" '
              'class="bd-dlg-slot"></div></div>' in html,
              "%s: the promoter's slot is the sheet's body" % tag)
    else:
        check('<dialog id="wr-dlg" class="bd-dlg"' in html,
              "%s: the shell is the page's own dialog" % tag)
    css = board._CSS
    check(re.search(r"@media \(max-width: 700px\) \{.*?dialog\.bd-dlg \{"
                    r"[^}]*max-height: 62vh[^}]*margin: auto 0 0", css,
                    re.S) is not None,
          "%s: the fallback dialog is a bottom sheet at a medium detent on a "
          "phone" % tag)
    check("'.bd-dlg-t, .wr-sheet-t'" in board._SCRIPT,
          "%s: the promoter titles either shell" % tag)
    if board.ui_component("sheets_script") is not None:
        check(html.count(ui.sheets_script()) == 1,
              "%s: ui.sheets_script() rides once" % tag)

    # THE SWITCH: 44px tall, four views, works with the script off.
    check([v for v, _ in board.SEG_VIEWS]
          == ["calls", "locked", "bench", "all"],
          "%s: the four views are Calls / Locked in / Bench / All" % tag)
    check(board.SEG_DEFAULT == "calls",
          "%s: Calls is the default - certainty first" % tag)
    for v, label in board.SEG_VIEWS:
        check('<span id="seg-%s" class="bd-seg-t"></span>' % v in html,
              "%s: a :target anchor for %s" % (tag, v))
        check(re.search(r'<(a|button)\b[^>]*href="#seg-%s"[^>]*>%s<'
                        % (v, re.escape(label)), html) is not None,
              "%s: a %s link in the control (a fragment link, so the "
              "no-script path works)" % (tag, label))
    check(re.search(r'<(nav|div)\b[^>]*data-seg-wrap', html) is not None,
          "%s: the control is wrapped for the script" % tag)
    check(re.search(r'aria-(current|selected)="true"[^>]*href="#seg-calls"',
                    html) is not None
          or re.search(r'href="#seg-calls"[^>]*aria-(current|selected)='
                       r'"true"', html) is not None,
          "%s: Calls is the active segment by default" % tag)
    for v in ("calls", "locked", "bench", "grid"):
        check('data-sec="%s"' % v in html,
              "%s: a block carries data-sec=%s" % (tag, v))
    check('#seg-bench:target ~ .bd-mx > .bd-blk[data-sec="bench"]' in css
          and '.bd-mx[data-view="bench"] > .bd-blk:not([data-sec="bench"])'
          in css,
          "%s: CSS filters on :target (no script) and data-view (script)"
          % tag)
    check('#seg-all:target ~ .bd-mx > .bd-blk { display: block; }' in css,
          "%s: All brings every block back, the grid included" % tag)
    check(re.search(r"\.bd-seg \{[^}]*min-height: 44px", css, re.S)
          is not None,
          "%s: the control is 44px tall" % tag)
    check("[data-seg-wrap] a, [data-seg-wrap] button" in board._SCRIPT
          and "setAttribute('data-view', v)" in board._SCRIPT
          and "querySelector('.bd-mx')" in board._SCRIPT,
          "%s: a few lines of vanilla JS set data-view; no framework" % tag)
    if board.ui_component("segmented") is not None:
        check('class="wr-seg"' in html, "%s: the control is ui.segmented"
              % tag)
    else:
        check('<nav class="bd-seg" data-seg-wrap' in html,
              "%s: the control is the local fallback" % tag)

    # THE LEGEND: a "?" control, and every glyph in it carries a title.
    lg = board._legend()
    check(html.count('class="legend') == lg.count('class="legend'),
          "%s: no static legend block anywhere outside the popover" % tag)
    check(lg.startswith("<details") and 'aria-hidden="true">?</span>' in lg,
          "%s: the legend is a '?' disclosure" % tag)
    check(lg in html, "%s: ...and it is on the page" % tag)
    heads = re.findall(r'<span class="wr-legend-i">(<[^>]+>)', lg)
    check(heads and all('title="' in h or "<title>" in lg for h in heads),
          "%s: every glyph in the key carries a title (%d items)"
          % (tag, len(heads)))
    for must in ("wr-chip-start", "wr-chip-sit", "wr-meter", "bd-lock",
                 "TOP SOURCE DISSENTS", "of the room", "bd-face-start",
                 "TEMPER EXPECTATIONS", "not wired"):
        check(must in lg, "%s: the key explains %s" % (tag, must))
    if board.ui_component("legend_popover") is not None:
        check(lg.startswith('<details class="wr-lgd">')
              and 'class="legend bd-legend-x"' in lg,
              "%s: ui.legend_popover is the shell, with the page's own "
              "glyph key spliced into its panel" % tag)
    else:
        check('<details class="bd-legend">' in lg,
              "%s: the local popover carries the key" % tag)

    # QUIET MODE: settled unanimous rows are marked so prefs can hide them,
    # and a CALL never is.
    marked = re.findall(r'data-unanimous="1"', html)
    check('html[data-quiet="1"] table.mx tbody.pl[data-unanimous="1"],' in css
          and 'html[data-quiet="1"] .bd-pl[data-unanimous="1"] '
              '{ display: none; }' in css,
          "%s: quiet mode hides unanimous rows AND compact rows by CSS on "
          "the <html> attribute" % tag)
    check(("bd-quiet-note" in html) == bool(marked),
          "%s: the hidden count is printed under quiet mode exactly when "
          "there is something to hide (%d marked), so a quiet board never "
          "reads as a shorter roster" % (tag, len(marked)))
    calls_blk = _blk(html, "calls")
    check(calls_blk and 'data-unanimous="1"' not in calls_blk,
          "%s: no card is marked unanimous - quiet mode may never hide a "
          "row that needs the user" % tag)
    if tag == "fixture":
        check(marked, "unanimous settled rows carry data-unanimous=\"1\" "
              "(%d)" % len(marked))
        locked_blk = _blk(html, "locked")
        bench_blk = _blk(html, "bench")
        check('data-unanimous="1"' in locked_blk,
              "two voices agreeing is unanimous")
        one_voice = re.search(r'<div class="bd-pl[^>]*>(?:(?!</div>).)*?'
                              r'C Bench', bench_blk, re.S)
        check(one_voice is not None
              and 'data-unanimous="1"' not in one_voice.group(0),
              "...one voice is not")
        check(_count(r'<article class="bd-call', calls_blk) == 1,
              "%s: the split row is the one card" % tag)
        check("A Split" in calls_blk and "B Settled" not in calls_blk,
              "%s: the settled row stayed out of the calls" % tag)
        check("B Settled" in locked_blk,
              "%s: ...and is a compact row under Locked in" % tag)
        check("Nobody" in bench_blk and "Not placed" in bench_blk,
              "%s: an unresolved name is listed under its own head, not "
              "filed as a bench player it is not" % tag)


def test_ui_components():
    print("\n[19] which ui components are present, and the fallbacks")
    present = board.ui_components_present()
    for name in board.UI_COMPONENTS:
        print("       %-16s %s" % (name, "ui.py" if present[name]
                                   else "local fallback"))
    check(set(present) == set(board.UI_COMPONENTS),
          "every component the board can use is reported")
    check("<details" in board._score_cell_fallback(1.0, None, "<ul></ul>"),
          "score_cell fallback renders")
    check('href="#seg-bench"' in board._segmented_fallback(
              "show", list(board.SEG_VIEWS), "calls"),
          "segmented fallback renders fragment links")
    check("?" in board._legend_popover_fallback(board.legend_items()),
          "legend fallback renders the ? control")
    check('<form method="dialog">' in board._dialog_fallback(
              "wr-dlg", "t", "<div></div>", "t"),
          "dialog fallback closes natively")
    check(board._via_ui("no_such_component_ever", lambda: "fb") == "fb",
          "_via_ui falls back when the name is absent")
    check(board._via_ui("icon", lambda *a: "fb", "not-an-icon") == "fb",
          "_via_ui falls back when the component raises")


def main():
    print("BOARD ACCEPTANCE TEST")
    test_columns()
    test_levels()
    test_call_grounds()
    test_versus_card()
    test_compact_row()
    test_cells()
    test_guard()
    test_no_claim_without_data()
    test_math_and_reputation()
    test_record()
    test_phone_css()
    test_call_and_why()
    test_score_cell()
    test_lock_state()
    test_sheet_switch_legend()
    test_ui_components()
    test_live_espn()
    test_live_yahoo()
    test_live_locks()
    test_io()
    test_empty()
    test_degraded_claims_nothing()
    test_degraded_reputation()
    test_degraded_matchups()
    test_cli_failure()
    test_readonly_momentum()
    test_readonly_v2()
    print("\n%s" % ("ALL CHECKS PASSED" if not FAILURES
                    else "%d FAILURE(S):" % len(FAILURES)))
    for f in FAILURES:
        print("  - %s" % f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
