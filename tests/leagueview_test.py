#!/usr/bin/env python3
"""Acceptance test: full-league roster ingestion (engine/leagueview.py).

The leagues we cannot API-read (Yahoo today) only ever know the other
nine rosters if the user pastes them, so this suite is mostly about the
two ways that goes wrong: inventing a player who was never there, and
losing a line nobody was told about.

  * THREE MESSY PASTE FORMATS, parsed to the same store shape: a Yahoo
    lineup copy (tab columns, slot labels, kickoff tails, injury tags,
    "Team 2:" markers), an ESPN league-rosters copy (name + record
    header, STARTERS/BENCH dividers, "Wsh"/"D/ST", stat columns), and a
    hand-typed list ("Team:"/"Manager -" markers, numbered lines,
    lowercase names, a bare "Baltimore" defense).
  * NOTHING IS INVENTED: a name the rankings pool does not carry is
    reported in .unmatched, verbatim, and appears on NO roster - and a
    bogus line in the MIDDLE of a roster is reported rather than
    splitting the block into a phantom team.
  * A COLUMN HEADER IS FURNITURE: a line whose tokens are all header
    words ("PROJ PTS OPP") is skipped, not read as a team name - it used
    to take the team slot and push the REAL name below it into
    .unmatched. Checked against both the layout that misparsed and a list
    of real team names that must survive the rule.
  * COVERAGE MATH: 0/10 -> 1/10 (my roster alone) -> 3/10 after a paste,
    complete() only at full coverage, and claim_status() answering
    "unknown" rather than "free" until then.
  * MERGE PRECEDENCE, per team slot: captured draft > pasted store > my
    own roster file, checked by deleting one layer at a time.
  * SLOT DISCIPLINE: a re-paste updates the team whose NAME matches, a
    stranger never overwrites an occupied slot (my own roster's included),
    a full league refuses the extra team with a reason, and a player the
    paste moves is removed from his old roster and reported.
  * THE PANEL: guard_scoped_write now allows data/league-*.json and still
    refuses its neighbours; a LIVE server on an ephemeral 127.0.0.1 port
    with data_root in a tempdir previews (writing NOTHING), then saves,
    then reports the new coverage on reload; an unknown league id, an
    empty paste and an all-junk paste each bounce.

Production data/league-*.json, data/rosters/ and leagues/ are byte- and
listing-checked untouched throughout.

    .venv/bin/python tests/leagueview_test.py
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import leagueview as lv                          # noqa: E402
from engine import sources_ui as ui                          # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.models import LeagueConfig, load_players         # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


RANKINGS = os.path.join(HERE, "data", "rankings.csv")
POOL = load_players(RANKINGS)
MATCHER = Matcher(POOL)

LEAGUE_YAML = """\
id: %(id)s
name: %(name)s
platform: yahoo
teams: %(teams)d
my_slot: %(slot)d
waiver_mode: faab
roster_spots: [QB, RB, RB, WR, WR, TE, W/R/T, W/R/T, K, DEF, BN, BN]
rounds: 12
rankings_csv: data/rankings.csv
scoring:
  reception: 1
team_names: []
"""


def _root(league_id="testlg", name="Test League", teams=10, slot=1,
          roster=("Jahmyr Gibbs", "Drake London", "Sam LaPorta")):
    """A throwaway project root: leagues/, data/rosters/, a rankings csv.

    Every leagueview entry point takes data_root, so the whole suite runs
    against this tempdir - the tempdir-redirect discipline tests/
    mock_draft.py applies to save_state, expressed as an argument.
    """
    tmp = tempfile.mkdtemp(prefix="leagueview-")
    os.makedirs(os.path.join(tmp, "leagues"))
    os.makedirs(os.path.join(tmp, "data", "rosters"))
    shutil.copy(RANKINGS, os.path.join(tmp, "data", "rankings.csv"))
    with open(os.path.join(tmp, "leagues", "%s.yaml" % league_id), "w") as fh:
        fh.write(LEAGUE_YAML % {"id": league_id, "name": name,
                                "teams": teams, "slot": slot})
    if roster is not None:
        with open(os.path.join(tmp, "data", "rosters",
                               "%s.yaml" % league_id), "w") as fh:
            fh.write("league: %s\nname: My Team\nsize: 12\nplayers:\n%s\n"
                     % (league_id,
                        "\n".join("- %s" % p for p in roster)))
    return tmp


def _cfg(root, league_id="testlg"):
    return lv.load_config(league_id, root)


def _names(team):
    return [r["player"] for r in team.players]


# --- fixtures: three shapes a user can actually copy --------------------------

PASTE_YAHOO = """\
Kid's Table — Teams

Team 2: Waiver Wire Warriors  (2-1)
QB\tJosh Allen Buf - QB\tSun 1:00 pm vs NYJ\t21.4
WR\tJa'Marr Chase Cin - WR\tQ\t24.8
WR\tMalik Nabers NYG - WR
RB\tDe'Von Achane Mia - RB
TE\tTrey McBride Ari - TE
W/R/T\tTony Pollard Ten - RB
K\tBrandon Aubrey Dal - K
DEF\tDenver Def Den - DEF
Bench
BN\tJordan Love GB - QB
BN\tZzyzx Quorblatt Nyx - WR
BN\tJaylen Waddle Mia - WR
BN\tEmpty

Team 3: Golden Brown Gibbs (1-2)
QB\tJalen Hurts Phi - QB
RB\tBijan Robinson Atl - RB
WR\tPuka Nacua LAR - WR
TE\tGeorge Kittle SF - TE
K\tCameron Dicker LAC - K
DEF\tSeattle Def Sea - DEF
"""

PASTE_ESPN = """\
Brock Hard (2-1)
STARTERS
QB   Jayden Daniels Wsh QB   Sun 4:25 PM @ LA   19.8
RB   Jonathan Taylor Ind RB  Q  18.2
WR   Justin Jefferson Min WR
WR   Nico Collins Hou WR
TE   Brock Bowers LV TE
FLEX Tetairoa McMillan Car WR
BENCH
BN   Caleb Williams Chi QB
IR   Mystery Guy Xyz WR

Mike (sea)Hawk  (0-3)
QB   Patrick Mahomes KC QB
RB   Ashton Jeanty LV RB
WR   Rome Odunze Chi WR
K    Jake Bates Det K
D/ST Houston Def Hou D/ST
"""

PASTE_PLAIN = """\
Team: The Ligmaneers
1. Lamar Jackson, QB
2. Saquon Barkley (RB - PHI) bye 9
3. CeeDee Lamb WR DAL
4. Travis Kelce TE
5. Not A Real Person WR
6. Baltimore
7. Ka'imi Fairbairn

Manager - Couch Potatoes
Christian McCaffrey
amon-ra st brown
george pickens
Minnesota D/ST
"""


# --- 1. store shape + I/O ----------------------------------------------------

def test_store_io():
    print("\n[1] store I/O - data/league-<id>.json, the espn-1 shape")
    root = _root()
    try:
        cfg = _cfg(root)
        check(lv.store_path(cfg.id, root).endswith(
            os.path.join("data", "league-testlg.json")),
            "store path is data/league-<id>.json")
        check(lv.load_store(cfg.id, root) is None,
              "absent store loads as None, not a crash")

        doc = lv.empty_store(cfg)
        doc["teams"]["4"] = {"name": "Team Four", "players": [
            {"player": "Bijan Robinson", "pos": "RB", "nfl": "ATL",
             "bye": 11, "proj": 352.8}]}
        path = lv.save_store(doc, cfg.id, root)
        check(os.path.exists(path) and not os.path.exists(path + ".tmp"),
              "atomic write leaves no .tmp behind")
        back = lv.load_store(cfg.id, root)
        check(back == doc, "round-trips byte-for-byte through json")

        # The shape the engine ALREADY reads for espn-1 - not a new dialect.
        real = json.load(open(os.path.join(HERE, "data",
                                           "league-espn-1.json")))
        check(sorted(back) == sorted(real), "top-level keys match espn-1")
        check(sorted(back["teams"]["4"]) == sorted(real["teams"]["1"]),
              "team keys match espn-1 (name + players)")
        mine = set(back["teams"]["4"]["players"][0])
        theirs = set(real["teams"]["1"]["players"][0])
        check(mine <= theirs and {"player", "pos", "nfl", "bye", "proj"} <= mine,
              "player row keys are a subset of espn-1's (draft extras aside)")

        with open(path, "w") as fh:
            fh.write("{not json")
        check(lv.load_store(cfg.id, root) is None,
              "corrupt store loads as None (honest empty), never raises")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 2. the three messy paste formats ----------------------------------------

def test_paste_yahoo():
    print("\n[2] paste format A - Yahoo lineup copy (tabs, slots, kickoffs)")
    root = _root()
    try:
        cfg = _cfg(root)
        got = lv.parse_league_paste(PASTE_YAHOO, MATCHER, cfg)
        check(len(got.teams) == 2, "two teams parsed (got %d)" % len(got.teams))
        names = [t.name for t in got.teams]
        check(names == ["Waiver Wire Warriors", "Golden Brown Gibbs"],
              "'Team 2: Name (2-1)' -> clean team names (got %s)" % names)
        check(got.teams[0].slot_hint == "2" and got.teams[1].slot_hint == "3",
              "the paste's own team numbers are kept as slot hints")

        first = _names(got.teams[0])
        check("Josh Allen" in first,
              "a kickoff tail glued to the row ('Sun 1:00 pm vs NYJ') does "
              "not eat the player")
        check("Ja'Marr Chase" in first, "an injury tag + stat column survive")
        check("Denver Defense" in first, "'Denver Def Den - DEF' -> defense")
        check("Brandon Aubrey" in first, "kicker row matched")
        check(len(first) == 10, "10 players on team 1 (got %d)" % len(first))
        check(_names(got.teams[1])[0] == "Jalen Hurts", "second block intact")

        check(any("Zzyzx" in line for _team, line in got.unmatched),
              "the invented bench name is REPORTED unmatched")
        check(not any("Zzyzx" in n for t in got.teams for n in _names(t)),
              "...and appears on nobody's roster - nothing invented")
        check(got.unmatched[0][0] == "Waiver Wire Warriors",
              "the unmatched line names the team it sat under")
        check(len(got.teams[0]) == 10,
              "a bogus line MID-roster does not split the block in two")
        check(any("Empty" in s for s in got.skipped),
              "'BN Empty' counted as page furniture, not as a lost player")
        check(any("Kid's Table" in line for _t, line in got.unmatched),
              "the page title heads no team, so it is reported not dropped")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_paste_espn():
    print("\n[3] paste format B - ESPN rosters copy (records, Wsh, D/ST)")
    root = _root()
    try:
        cfg = _cfg(root)
        got = lv.parse_league_paste(PASTE_ESPN, MATCHER, cfg)
        check([t.name for t in got.teams] == ["Brock Hard", "Mike (sea)Hawk"],
              "'Name (2-1)' headers -> names without the record (got %s)"
              % [t.name for t in got.teams])
        first = _names(got.teams[0])
        check("Jayden Daniels" in first,
              "'Wsh' is rewritten to WAS and read as a team hint")
        check("Tetairoa McMillan" in first, "a FLEX row is a player row")
        check("Caleb Williams" in first,
              "the BENCH divider does not end the team")
        check(not any(s.strip().lower() in ("starters", "bench")
                      for _t, s in got.unmatched),
              "STARTERS/BENCH dividers are furniture, never unmatched lines")
        check("Houston Defense" in _names(got.teams[1]),
              "'D/ST Houston Def Hou D/ST' -> the Houston defense")
        check(any("Mystery Guy" in line for _t, line in got.unmatched),
              "the IR row we cannot resolve is reported")
        check(not any("Mystery" in n for t in got.teams for n in _names(t)),
              "...and nobody rosters him")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_paste_plain():
    print("\n[4] paste format C - hand-typed list (numbers, markers, lower)")
    root = _root()
    try:
        cfg = _cfg(root)
        got = lv.parse_league_paste(PASTE_PLAIN, MATCHER, cfg)
        check([t.name for t in got.teams] == ["The Ligmaneers",
                                              "Couch Potatoes"],
              "'Team:' and 'Manager -' markers both name a team (got %s)"
              % [t.name for t in got.teams])
        first = _names(got.teams[0])
        check("Lamar Jackson" in first and "Saquon Barkley" in first,
              "numbered lines with trailing pos/bye junk match")
        check("Baltimore Defense" in first,
              "a bare team name ('Baltimore') resolves to that defense")
        check("Ka'imi Fairbairn" in first, "an apostrophe name matches")
        second = _names(got.teams[1])
        check("Amon-Ra St. Brown" in second and "George Pickens" in second,
              "lowercase, punctuation-free names match")
        check("Minnesota Defense" in second, "'Minnesota D/ST' -> defense")
        check(any("Not A Real Person" in line for _t, line in got.unmatched),
              "the invented name is reported, not guessed at")
        check(len(got.teams[0]) == 6,
              "the invented name did not become a team (got %d players)"
              % len(got.teams[0]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_never_invents():
    print("\n[5] never invents - garbage in, garbage REPORTED")
    root = _root()
    try:
        cfg = _cfg(root)
        got = lv.parse_league_paste(
            "Ghost Squad\nZzyzx Quorblatt\nQqqq Wwww\nMmmm Nnnn\n",
            MATCHER, cfg)
        check(got.teams == [], "no team survives with zero matched players")
        lines = [line for _t, line in got.unmatched]
        check(len([l for l in lines if l != "Ghost Squad"]) == 3,
              "all three junk names reported (got %s)" % lines)
        check("Ghost Squad" in lines,
              "a header that collected nobody is reported too")
        check(got.matched == 0, "zero players matched")

        empty = lv.parse_league_paste("", MATCHER, cfg)
        check(empty.teams == [] and empty.unmatched == [],
              "empty text parses to nothing, quietly")

        # A team name carrying an NFL code is common ("The KC Crew"). The
        # blank line every roster page prints between teams settles it.
        got = lv.parse_league_paste(
            "The KC Crew\nBijan Robinson\nCeeDee Lamb\n"
            "\nGB Bandits\nJosh Allen\nSaquon Barkley\n", MATCHER, cfg)
        check([t.name for t in got.teams] == ["The KC Crew", "GB Bandits"],
              "a blank line above outranks an NFL code inside a team name "
              "(got %s)" % [t.name for t in got.teams])
        check(len(got.teams[0]) == 2 and len(got.teams[1]) == 2,
              "and each block keeps its own two players")
        check(not any(r["pos"] == "DEF" for t in got.teams
                      for r in t.players),
              "'GB Bandits' is NOT drafted as the Green Bay defense - a "
              "defense hit must be explained by the words on the line")
        ok = lv.parse_league_paste("Team 1: X\nGreen Bay Def\nBaltimore\n",
                                   MATCHER, cfg)
        check([r["player"] for r in ok.teams[0].players]
              == ["Green Bay Defense", "Baltimore Defense"],
              "...while real defense rows still match (got %s)"
              % [r["player"] for r in ok.teams[0].players])

        # ...but a slot-labelled row is a roster row no matter what sits
        # above it: a blank line must not turn a bench entry into a team.
        got = lv.parse_league_paste(
            "Team 1: Splitters\nBijan Robinson\n"
            "\nBN\tZzyzx Quorblatt Nyx - WR\nBN\tCeeDee Lamb Dal - WR\n",
            MATCHER, cfg)
        check(len(got.teams) == 1 and len(got.teams[0]) == 2,
              "a blank line before a bench block does not start a team")
        check(any("Zzyzx" in line for _t, line in got.unmatched),
              "...and the unresolvable bench row is still reported")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 5b. column headers are furniture, not team names -------------------------

def test_column_header_is_junk():
    print("\n[5b] a stat-header ROW is page furniture, never a team name")
    root = _root()
    try:
        cfg = _cfg(root)
        # The layout that used to misparse: a repeated column header between
        # two roster blocks. The header took the team slot, and the REAL
        # name on the next line - now sitting above an empty team - was
        # reported as an unmatched line instead of naming its roster.
        got = lv.parse_league_paste(
            "Waiver Wire Warriors\n"
            "QB\tJosh Allen Buf - QB\n"
            "RB\tDe'Von Achane Mia - RB\n"
            "\n"
            "PROJ PTS OPP\n"
            "Golden Brown Gibbs\n"
            "QB\tJalen Hurts Phi - QB\n"
            "RB\tBijan Robinson Atl - RB\n", MATCHER, cfg)
        names = [t.name for t in got.teams]
        check(names == ["Waiver Wire Warriors", "Golden Brown Gibbs"],
              "both real teams keep their names (got %s)" % names)
        check("PROJ PTS OPP" not in names,
              "the column header is NOT a team")
        check(any("PROJ" in s for s in got.skipped),
              "...it is counted as furniture (skipped), not silently lost")
        check(not any("Golden Brown Gibbs" in line
                      for _t, line in got.unmatched),
              "the real team name is no longer displaced into unmatched")
        check(len(got.teams[1]) == 2,
              "and the second block's players land on it (got %d)"
              % len(got.teams[1]))

        # Header shapes the sites actually print.
        for header in ("POS PLAYER OPP PROJ PTS", "Player Team Pos Proj",
                       "FPTS PPG %ROST", "Starters Proj Pts",
                       "PLAYER, TEAM POS  PROJ"):
            check(lv._is_junk_line(header),
                  "header row is furniture: %r" % header)

        # ...and the conservatism that keeps a real name safe. One header
        # word does not make a header, and an explicit marker always wins.
        for name in ("Total Chaos", "Bench Mob", "The Ligmaneers",
                     "Waiver Wire Warriors", "Sit Happens", "Team 4: Roster",
                     "Kid's Table — Teams", "Mike (sea)Hawk (0-3)"):
            check(not lv._is_junk_line(name),
                  "a real team name survives: %r" % name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 6. coverage math --------------------------------------------------------

def test_coverage():
    print("\n[6] coverage math - always stated, never assumed")
    root = _root(teams=10, slot=1)
    try:
        cfg = _cfg(root)
        view = lv.load_league_view(cfg, MATCHER, root)
        check(view.coverage() == (1, 10) and
              view.coverage_text() == "1 of 10 rosters known",
              "my roster alone = 1 of 10 (got %s)" % view.coverage_text())
        check(not view.complete(), "1 of 10 is not complete")
        check("not a free agent" in view.banner_text(),
              "the partial banner carries the positive-only caveat")

        gibbs = [p for p in POOL if p.name == "Jahmyr Gibbs"][0]
        chase = [p for p in POOL if p.name == "Ja'Marr Chase"][0]
        check(view.claim_status(gibbs.key) == ("held", "My Team"),
              "a player on a known roster is HELD, by name")
        status, detail = view.claim_status(chase.key)
        check(status == "unknown" and "1 of 10" in detail,
              "a player on no known roster is UNKNOWN, with the coverage "
              "(got %s/%s)" % (status, detail))
        check(view.owner_of(chase.key) is None, "owner_of is None, not a lie")

        parsed = lv.parse_league_paste(PASTE_YAHOO, MATCHER, cfg)
        plan = lv.apply_paste(parsed, cfg, None, view)
        check(lv.coverage_after(plan, cfg, view) == (3, 10),
              "the preview projects 3 of 10 before anything is written")
        lv.save_store(plan.store, cfg.id, root)
        after = lv.load_league_view(cfg, MATCHER, root)
        check(after.coverage() == (3, 10),
              "and 3 of 10 is what the reloaded view reports")
        check(after.claim_status(chase.key) == ("held",
                                                "Waiver Wire Warriors"),
              "the pasted roster now answers who holds Chase")

        # A fully-known league is the ONLY place 'free' may be spoken.
        full = _root(league_id="small", name="Small", teams=2, slot=1)
        try:
            scfg = _cfg(full, "small")
            doc = lv.empty_store(scfg)
            doc["teams"]["2"] = {"name": "Them", "players": [
                {"player": "Ja'Marr Chase", "pos": "WR", "nfl": "CIN",
                 "bye": 6, "proj": 337.5}]}
            lv.save_store(doc, "small", full)
            sview = lv.load_league_view(scfg, MATCHER, full)
            check(sview.complete() and sview.banner_text() == "",
                  "2 of 2 rosters known: complete, no banner")
            bijan = [p for p in POOL if p.name == "Bijan Robinson"][0]
            check(sview.claim_status(bijan.key) == ("free", ""),
                  "only at full coverage does an unrostered player read FREE")
        finally:
            shutil.rmtree(full, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 7. merge precedence -----------------------------------------------------

DRAFT_CSV = """\
overall,round,slot,team,player,pos,nfl,bye,proj,adp
1,1,1,Drafted Team,Bijan Robinson,RB,ATL,11,352.8,1.9
2,1,2,My Team,Puka Nacua,WR,LAR,11,356.3,3.0
"""


def test_precedence():
    print("\n[7] merge precedence - draft > store > my own roster, per slot")
    root = _root(teams=4, slot=2)
    try:
        cfg = _cfg(root)
        store = lv.empty_store(cfg)
        store["teams"]["1"] = {"name": "Stored One", "players": [
            {"player": "CeeDee Lamb", "pos": "WR", "nfl": "DAL",
             "bye": 14, "proj": 293.7}]}
        store["teams"]["2"] = {"name": "Stored Mine", "players": [
            {"player": "Travis Kelce", "pos": "TE", "nfl": "KC",
             "bye": 10, "proj": 200.0}]}
        lv.save_store(store, cfg.id, root)
        with open(os.path.join(root, "data", "draft-testlg-2026.csv"),
                  "w") as fh:
            fh.write(DRAFT_CSV)

        view = lv.load_league_view(cfg, MATCHER, root)
        one, two = view.team("1"), view.team("2")
        check(one.source == lv.SRC_DRAFT and _names(one) == ["Bijan Robinson"],
              "slot 1: the draft capture beats the store")
        check(two.source == lv.SRC_DRAFT and _names(two) == ["Puka Nacua"],
              "slot 2: the draft capture beats BOTH the store and my roster")
        check(two.mine, "my_slot is still flagged as mine through the capture")
        check(any("outranks" in n for n in view.notes),
              "the shadowed, DIFFERING store slots are called out in notes")

        os.remove(os.path.join(root, "data", "draft-testlg-2026.csv"))
        view = lv.load_league_view(cfg, MATCHER, root)
        check(view.team("1").source == lv.SRC_STORE
              and view.team("2").source == lv.SRC_STORE,
              "without the capture the store speaks for both slots")
        check(_names(view.team("2")) == ["Travis Kelce"],
              "slot 2: the store beats my own roster file")

        os.remove(lv.store_path(cfg.id, root))
        view = lv.load_league_view(cfg, MATCHER, root)
        check(view.coverage() == (1, 4), "store gone: 1 of 4 rosters known")
        check(view.team("2").source == lv.SRC_OWN
              and view.team("1") is None,
              "with no capture and no store, only my own roster remains")
        check(_names(view.team("2"))[:2] == ["Jahmyr Gibbs", "Drake London"],
              "my roster file's names resolve through the pool")
        check(view.source_counts()[lv.SRC_OWN] == 1,
              "source_counts reports the layer each roster came from")

        # An own-roster name the pool does not carry is KEPT (it is the
        # user's own file) but never given an invented position.
        with open(os.path.join(root, "data", "rosters", "testlg.yaml"),
                  "a") as fh:
            fh.write("- Zzyzx Quorblatt\n")
        view = lv.load_league_view(cfg, MATCHER, root)
        rows = view.team("2").players
        ghost = [r for r in rows if r["player"] == "Zzyzx Quorblatt"]
        check(len(ghost) == 1 and ghost[0]["pos"] == "" and
              ghost[0]["proj"] is None,
              "an unresolved own-roster name is kept, position-less")
        check("Zzyzx Quorblatt" in view.unresolved,
              "...and reported in .unresolved")

        empty = _root(league_id="bare", name="Bare", teams=8, roster=None)
        try:
            bview = lv.load_league_view(_cfg(empty, "bare"), MATCHER, empty)
            check(bview.coverage() == (0, 8) and bview.teams == [],
                  "a league with nothing on disk is 0 of 8, not an error")
            check(bview.claim_status("anyone|RB")[0] == "unknown",
                  "and every player is UNKNOWN there")
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 8. slot discipline ------------------------------------------------------

def test_slots():
    print("\n[8] slot discipline - who gets overwritten, and who never does")
    root = _root(teams=4, slot=1)
    try:
        cfg = _cfg(root)
        view = lv.load_league_view(cfg, MATCHER, root)
        parsed = lv.parse_league_paste(PASTE_YAHOO, MATCHER, cfg)
        plan = lv.apply_paste(parsed, cfg, None, view)
        slots = dict((t.name, s) for t, s, _n in plan.assignments)
        check("1" not in slots.values(),
              "slot 1 holds MY roster - no pasted stranger lands on it")
        check(slots["Waiver Wire Warriors"] == "2",
              "the paste's own 'Team 2:' number is honored when free")

        first = lv.save_store(plan.store, cfg.id, root)
        check(os.path.basename(first) == "league-testlg.json", "store written")

        # A re-paste of the same team, one player lighter, must UPDATE it.
        again = lv.parse_league_paste(
            "Team 9: Waiver Wire Warriors\nJosh Allen Buf - QB\n"
            "Ja'Marr Chase Cin - WR\n", MATCHER, cfg)
        view2 = lv.load_league_view(cfg, MATCHER, root)
        plan2 = lv.apply_paste(again, cfg, lv.load_store(cfg.id, root), view2)
        team, slot, note = plan2.assignments[0]
        check(slot == "2", "the NAME match wins over the new '9' hint")
        check("replaces" in note, "the note says what it replaces (%s)" % note)
        check(len(plan2.store["teams"]["2"]["players"]) == 2,
              "the slot now holds exactly the re-pasted roster")

        # A player moving teams leaves his old roster, loudly.
        moved = lv.parse_league_paste(
            "Team 3: Golden Brown Gibbs\nJosh Allen Buf - QB\n", MATCHER, cfg)
        plan3 = lv.apply_paste(moved, cfg, plan2.store, view2)
        check(("Josh Allen", "Waiver Wire Warriors", "Golden Brown Gibbs")
              in plan3.moved, "the move is reported (got %s)" % plan3.moved)
        check(all(p["player"] != "Josh Allen"
                  for p in plan3.store["teams"]["2"]["players"]),
              "...and he is gone from the roster he left - never on two")

        # A player the paste claims who is also in a layer we cannot edit.
        contest = lv.parse_league_paste(
            "Team 4: Rivals\nJahmyr Gibbs Det - RB\n", MATCHER, cfg)
        plan4 = lv.apply_paste(contest, cfg, plan3.store, view2)
        check(any(c[0] == "Jahmyr Gibbs" and "roster file" in c[2]
                  for c in plan4.contested),
              "a clash with my own roster file is reported, not silently "
              "resolved (got %s)" % plan4.contested)

        # A full league refuses the extra team WITH a reason.
        full = lv.empty_store(cfg)
        for i in range(1, 5):
            full["teams"][str(i)] = {"name": "Team %d" % i, "players": [
                {"player": "CeeDee Lamb", "pos": "WR", "nfl": "DAL",
                 "bye": 14, "proj": 293.7}]}
        plan5 = lv.apply_paste(
            lv.parse_league_paste("Team 7: Late Arrivals\nBijan Robinson\n",
                                  MATCHER, cfg), cfg, full, None)
        check(plan5.assignments == [] and plan5.refused,
              "a 5th team in a 4-team league is refused, not shoehorned in")
        check("matches none of them" in plan5.refused[0][1],
              "the refusal says why (%s)" % plan5.refused[0][1])
        check(all(len(e["players"]) == 1
                  for e in plan5.store["teams"].values()),
              "and nothing was overwritten on the way out")
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- 9. the panel's write allowlist ------------------------------------------

def test_guard():
    print("\n[9] guard_scoped_write - data/league-*.json joins the allowlist")
    tmp = tempfile.mkdtemp(prefix="leagueview-guard-")
    try:
        for rel in ["data/league-yahoo-main.json", "data/league-espn-1.json"]:
            p = os.path.join(tmp, *rel.split("/"))
            check(ui.guard_scoped_write(p, tmp) == p, "allowed: %s" % rel)
        for rel in ["data/league-.json",            # empty stem
                    "data/league.json",             # no dash
                    "data/league-x.json.evil",
                    "data/leagues-x.json",
                    "data/x/league-y.json",         # no subdirs
                    "league-x.json",                # not under data/
                    "data/league-metrics-espn-1.json.tmp"]:
            p = os.path.join(tmp, *rel.split("/"))
            try:
                ui.guard_scoped_write(p, tmp)
                check(False, "refused: %s" % rel)
            except PermissionError:
                check(True, "refused: %s" % rel)
        check("data/league-*.json" in ui.LEAGUE_SCOPE,
              "the documented scope names the new surface")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- 10. live panel round-trip ------------------------------------------------

class _StatusOnlyConnections(object):
    """Keeps GET / off the real engine.connections (hermetic)."""

    def status(self):
        return {p: {"connected": False, "detail": "", "leagues": [],
                    "next_step": "not connected"}
                for p in ("sleeper", "espn", "yahoo")}


def _post(port, path, obj):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path),
        data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _get(port, path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path),
                                timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def test_panel_roundtrip():
    print("\n[10] LIVE panel - preview writes nothing, save writes once")
    root = _root(league_id="yahoo-main", name="Kid's Table", teams=10, slot=1)
    saved_conn = ui.CONNECTIONS
    ui.CONNECTIONS = _StatusOnlyConnections()
    srv = ui.make_server(0, os.path.join(root, "data", "sources.yaml"),
                         data_root=root)
    thread = threading.Thread(target=srv.serve_forever)
    thread.daemon = True
    thread.start()
    store = lv.store_path("yahoo-main", root)
    try:
        port = srv.server_address[1]
        code, page = _get(port, "/")
        check(code == 200 and "card-league-rosters" in page,
              "GET / renders the League rosters card")
        check("1 of 10 rosters known" in page,
              "the card states this league's coverage")
        check("Kid&#x27;s Table" in page or "Kid&#39;s Table" in page,
              "league names are HTML-escaped")

        code, res = _post(port, "/league/preview",
                          {"league": "yahoo-main", "text": PASTE_YAHOO})
        check(code == 200 and res["ok"], "preview accepted")
        check(res["before"] == "1 of 10 rosters known"
              and res["after"] == "3 of 10 rosters known",
              "preview shows coverage before -> after (%s -> %s)"
              % (res["before"], res["after"]))
        check([t["team"] for t in res["teams"]]
              == ["Waiver Wire Warriors", "Golden Brown Gibbs"],
              "preview names every team it parsed")
        check(any("Zzyzx" in u["line"] for u in res["unmatched"]),
              "preview reports the unmatched line verbatim")
        check(res["skipped"] >= 1, "preview counts skipped furniture")
        check(not os.path.exists(store), "PREVIEW WROTE NOTHING")

        code, res = _post(port, "/league/save",
                          {"league": "yahoo-main", "text": PASTE_YAHOO})
        check(code == 200 and res["ok"] and res["saved"], "save accepted")
        check(res["written"] == 2 and res["path"]
              == os.path.join("data", "league-yahoo-main.json"),
              "save reports what it wrote, where (%s)" % res["path"])
        check(os.path.exists(store), "the store file exists after save")
        doc = json.load(open(store))
        check(sorted(doc["teams"]) == ["2", "3"],
              "the two pasted teams landed on free slots, not mine")
        check([p["player"] for p in doc["teams"]["3"]["players"]][0]
              == "Jalen Hurts", "the stored rows carry the matched players")

        code, page = _get(port, "/")
        check("3 of 10 rosters known" in page,
              "a reload shows the new coverage")

        for body, why in [
                ({"league": "nope", "text": PASTE_YAHOO}, "unknown league"),
                ({"league": "../../etc/passwd", "text": PASTE_YAHOO},
                 "traversal id"),
                ({"league": "yahoo-main", "text": "   "}, "empty paste"),
                ({"league": "yahoo-main", "text": 5}, "non-string paste")]:
            code, res = _post(port, "/league/save", body)
            check(code == 400 and not res["ok"], "%s refused (%s)"
                  % (why, res.get("error", "")[:48]))
        before = open(store).read()
        code, res = _post(port, "/league/save",
                          {"league": "yahoo-main", "text": "Bench\nQB\n---"})
        check(code == 400 and "nothing to save" in res["error"],
              "an all-junk paste saves nothing")
        check(open(store).read() == before,
              "...and the store on disk is byte-identical after every bounce")
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
        ui.CONNECTIONS = saved_conn
        shutil.rmtree(root, ignore_errors=True)


# --- 11. production data untouched -------------------------------------------

def test_production_untouched(before):
    print("\n[11] production data untouched")
    now = _production_state()
    check(now == before, "data/league-*.json, data/rosters/ and leagues/ are "
                         "unchanged by this suite")
    check(not os.path.exists(os.path.join(HERE, "data",
                                          "league-yahoo-main.json")),
          "no store was created for the real yahoo-main league")


def _production_state():
    state = {}
    for rel in ("data", "data/rosters", "leagues"):
        d = os.path.join(HERE, rel)
        state[rel] = sorted(os.listdir(d)) if os.path.isdir(d) else []
    espn = os.path.join(HERE, "data", "league-espn-1.json")
    state["espn-1"] = open(espn, "rb").read() if os.path.exists(espn) else b""
    return state


def main():
    print("=" * 74)
    print("LEAGUE ROSTER INGESTION ACCEPTANCE TEST")
    print("=" * 74)
    before = _production_state()
    test_store_io()
    test_paste_yahoo()
    test_paste_espn()
    test_paste_plain()
    test_never_invents()
    test_column_header_is_junk()
    test_coverage()
    test_precedence()
    test_slots()
    test_guard()
    test_panel_roundtrip()
    test_production_untouched(before)

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
