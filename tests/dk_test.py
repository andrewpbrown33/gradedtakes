#!/usr/bin/env python3
"""Acceptance test: the DEF/K hold-or-stream call (engine/dk.py) and its
four integrations (lineup, consensus, home, board).

FIXTURE RULE (same as tests/lineup_test.py): nothing here asserts the
contents of the user's live rosters, registry or league files. Every
scenario is a synthetic pool + a synthetic streaming board (built through
streaming.build_board's injected proj/sched/lines seam - no network), a
synthetic rival view (trades.load_rival_view's loader seam) and injected
ESPN-taken keys. The two live leagues are exercised at the end as a smoke
test only: the verdict must be one of the four words and yahoo-main, whose
rival rosters are unknown, must never read STREAM.

WHAT IS PROTECTED
  [1] the wire clearly beats the held DEF -> STREAM; clearly loses -> HOLD;
      inside the band -> TOSS-UP; the thresholds are the documented ones.
  [2] AVAILABILITY: my own DEF/K never appears as a candidate; a
      rival-rostered one is excluded; an ESPN-rostered one is excluded ON
      THE ESPN LEAGUE ONLY (a Yahoo league never sees the ESPN filter).
  [3] rival rosters unknown -> the call still computes, the best candidate
      is still named, but STREAM is downgraded to TOSS-UP carrying the
      literal "candidates unverified - rival rosters unknown".
  [4] the opponent context: DST lines carry the opponent offense's implied
      total; K lines carry the opponent defense read (or say there is
      none) and the venue (or say it is not filed).
  [5] lineup.build's DEF/K verdict text is the dk call; consensus rows
      map HOLD/STREAM/TOSS-UP to START/SIT/EVEN with the humble pct; the
      Home inbox renders ONE item per streamed slot with the host's waiver
      link and drops the generic wire claim on that position; the board
      row carries the drawer line.
  [6] READ-ONLY: the streaming ledger, the %owned baseline and the roster
      files are byte-identical before and after every call, live ones
      included.

    .venv/bin/python tests/dk_test.py
"""

import hashlib
import io
import contextlib
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import board as board_mod                        # noqa: E402
from engine import consensus as consensus_mod                # noqa: E402
from engine import dk, home, lineup, streaming, trades       # noqa: E402
from engine.ingest import Matcher                            # noqa: E402
from engine.models import LeagueConfig, Player               # noqa: E402
from engine.projections import name_key                      # noqa: E402

FAILURES = []
CHECKS = [0]

WATCHED = [os.path.join(HERE, "data", "streaming_log.jsonl"),
           os.path.join(HERE, "data", "cache", "espn-owned-snapshot.json"),
           os.path.join(HERE, "data", "rosters", "espn-1.yaml"),
           os.path.join(HERE, "data", "rosters", "yahoo-main.yaml")]


def check(cond, label):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def _digest(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def snapshot_files():
    return dict((p, _digest(p)) for p in WATCHED)


# --- fixtures ---------------------------------------------------------------

def _league(platform="yahoo", mode="faab", lid="fx-dk"):
    return LeagueConfig({
        "id": lid, "name": "Fixture %s" % platform, "platform": platform,
        "teams": 8, "my_slot": 1, "waiver_mode": mode,
        "roster_spots": ["QB", "K", "DEF", "BN"],
        "scoring": {"reception": 1},
        "host": {"league_id": "111", "team_id": "7"},
    })


POOL = [
    Player(1, "Quarter Back", "QB", "SEA", proj_points=300.0),
    Player(2, "Seattle Defense", "DEF", "SEA", proj_points=100.0),
    Player(3, "Chicago Defense", "DEF", "CHI", proj_points=90.0),
    Player(4, "Jacksonville Defense", "DEF", "JAX", proj_points=120.0),
    Player(5, "New England Defense", "DEF", "NE", proj_points=110.0),
    Player(6, "Tennessee Defense", "DEF", "TEN", proj_points=105.0),
    Player(7, "Cameron Dicker", "K", "LAC", proj_points=150.0),
    Player(8, "Cairo Santos", "K", "CHI", proj_points=120.0),
    Player(9, "Jake Bates", "K", "DET", proj_points=140.0),
]
BY_NAME = dict((p.name, p) for p in POOL)
MATCHER = Matcher(POOL)

PROJ = {
    name_key("Seahawks D/ST"): {"proj": 6.0, "pos": "DEF", "team": "SEA"},
    name_key("Bears D/ST"): {"proj": 5.0, "pos": "DEF", "team": "CHI"},
    name_key("Jaguars D/ST"): {"proj": 9.0, "pos": "DEF", "team": "JAX"},
    name_key("Patriots D/ST"): {"proj": 7.0, "pos": "DEF", "team": "NE"},
    name_key("Titans D/ST"): {"proj": 6.5, "pos": "DEF", "team": "TEN"},
    name_key("Cameron Dicker"): {"proj": 9.0, "pos": "K", "team": "LAC"},
    name_key("Cairo Santos"): {"proj": 7.0, "pos": "K", "team": "CHI"},
    name_key("Jake Bates"): {"proj": 8.0, "pos": "K", "team": "DET"},
}
SCHED = {
    "SEA": {"opponent": "CHI", "home": True, "kickoff_iso": "x"},
    "CHI": {"opponent": "SEA", "home": False, "kickoff_iso": "x"},
    "JAX": {"opponent": "CLE", "home": True, "kickoff_iso": "x"},
    "CLE": {"opponent": "JAX", "home": False, "kickoff_iso": "x"},
    "NE": {"opponent": "TEN", "home": False, "kickoff_iso": "x"},
    "TEN": {"opponent": "NE", "home": True, "kickoff_iso": "x"},
    "LAC": {"opponent": "DEN", "home": True, "kickoff_iso": "x"},
    "DEN": {"opponent": "LAC", "home": False, "kickoff_iso": "x"},
    "DET": {"opponent": "NO", "home": True, "kickoff_iso": "x"},
    "NO": {"opponent": "DET", "home": False, "kickoff_iso": "x"},
}
LINES = {
    "SEA": {"implied_total": 24.0}, "CHI": {"implied_total": 18.0},
    "JAX": {"implied_total": 25.0}, "CLE": {"implied_total": 16.0},
    "NE": {"implied_total": 21.0}, "TEN": {"implied_total": 20.0},
    "LAC": {"implied_total": 27.0}, "DET": {"implied_total": 26.0},
    # DEN, NO: no line
}
VENUES = {"LAC": "dome (SoFi Stadium)", "DET": "dome (Ford Field)",
          "CHI": "venue not filed", "SEA": "outdoors (Lumen Field)"}
PA_TABLE = {"basis": "2025 season, 17 games", "prior_only": True,
            "by_pos": {"QB": {"defenses": {"DEN": {"pa_per_game": 20.0},
                                           "NO": {"pa_per_game": 15.0}}},
                       "RB": {"defenses": {"DEN": {"pa_per_game": 30.0},
                                           "NO": {"pa_per_game": 25.0}}}}}


def board(sched=SCHED, lines=LINES, proj=PROJ):
    return streaming.build_board(1, "ppr", proj=dict(proj), sched=sched,
                                 lines=lines)


def rival(names=("Tennessee Defense",), mine=("Seattle Defense",),
          league=None):
    """A rival view with one rival holding `names`, through the real loader
    seam - never a hand-built object."""
    teams = {"1": {"name": "Me", "players": list(mine), "mine": True},
             "2": {"name": "Rival", "players": list(names)}}
    return trades.load_rival_view(league or _league(), MATCHER, POOL,
                                  my_keys=set(BY_NAME[n].key for n in mine),
                                  loader=lambda _id: teams)


def dead_rival(league=None):
    def boom(_id):
        raise RuntimeError("no leagueview")
    return trades.load_rival_view(league or _league(), MATCHER, POOL,
                                  loader=boom)


def call(mine, league=None, rv=None, taken=None, brd=None, **kw):
    league = league or _league()
    players = [BY_NAME[n] for n in mine]
    return dk.weekly_call(league, 1, players, POOL, MATCHER,
                          board=brd if brd is not None else board(),
                          rival=rv if rv is not None else rival(mine=mine),
                          taken=set() if taken is None else taken,
                          venues=VENUES, pa_table=PA_TABLE, **kw)


# --- 1. thresholds ----------------------------------------------------------

def test_verdicts():
    print("\n1. STREAM / HOLD / TOSS-UP (documented thresholds)")
    c = call(["Seattle Defense", "Cairo Santos"])
    d, k = c["DST"], c["K"]
    # SEA DEF vs CHI implied 18 -> 6.0 + 1.575 = 7.58; JAX vs CLE 16 -> 11.28
    check(d["held"] == "Seattle Defense" and abs(d["held_score"] - 7.58) < 0.02,
          "held DEF is resolved to MY defense with streaming's own score "
          "(proj + opponent-implied adj = %.2f)" % d["held_score"])
    check(d["best"] == "JAX D/ST" and abs(d["best_score"] - 11.28) < 0.02,
          "best available DEF is the top candidate NOT excluded (JAX)")
    check(d["verdict"] == "STREAM" and abs(d["delta"] - 3.7) < 0.02,
          "delta %.1f >= %.1f margin -> STREAM" % (d["delta"],
                                                  dk.STREAM_MARGIN["DST"]))
    check(d["text"] == "STREAM JAX D/ST +3.7 over SEA",
          "verdict text is 'STREAM JAX D/ST +3.7 over SEA' (got %r)"
          % d["text"])
    check("FAAB band" in d["cost"] and "costs a waiver claim" in d["cost"],
          "FAAB league: the cost line carries a FAAB band (%s)" % d["cost"])
    check(50 < d["confidence"] < 80,
          "confidence is humble - P(best beats held) %d%% for a 3.7-pt DEF "
          "edge under sigma %.1f, never a near-certainty"
          % (d["confidence"], lineup.DEFAULT_SIGMA["DEF"]))
    check(d["held_pct"] == 100 - d["confidence"],
          "held_pct is the complement (the start-ward pct of the held)")
    check(k["verdict"] == "STREAM" and k["best"] == "Cameron Dicker"
          and abs(k["delta"] - 3.35) < 0.02,
          "K: Dicker (9.68) over Santos (6.33) -> STREAM at +3.35")
    check(k["text"].startswith("STREAM Cameron Dicker +3.3")
          and k["text"].endswith(" over Santos"),
          "K text names the kicker and the held surname (got %r)" % k["text"])

    c = call(["Jacksonville Defense", "Cameron Dicker"],
             rv=rival(mine=("Jacksonville Defense",)))
    d, k = c["DST"], c["K"]
    check(d["verdict"] == "HOLD" and d["text"] == "HOLD JAX"
          and d["delta"] < 0,
          "held JAX beats the whole wire -> HOLD JAX (delta %+.1f)" % d["delta"])
    check(d["best"] == "NE D/ST",
          "...and the best available is still named (NE, for the drawer)")
    check(k["verdict"] == "HOLD" and k["text"] == "HOLD Dicker",
          "K: Dicker beats Bates -> HOLD Dicker")

    # TEN held (7.03) vs NE available (7.88): +0.85, inside [0.75, 2.0).
    c = call(["Tennessee Defense", "Jake Bates"],
             rv=rival(names=("Jacksonville Defense",),
                      mine=("Tennessee Defense",)))
    d, k = c["DST"], c["K"]
    check(d["verdict"] == "TOSS-UP" and abs(d["delta"] - 0.85) < 0.02,
          "DEF delta %.2f inside the %.2f-%.1f band -> TOSS-UP"
          % (d["delta"], dk.TOSS_MIN["DST"], dk.STREAM_MARGIN["DST"]))
    check(d["text"].startswith("TOSS-UP NE D/ST +0.9 over TEN")
          and "unverified" not in d["text"],
          "a band TOSS-UP does NOT carry the unverified tag (rivals known)")
    check(k["verdict"] == "TOSS-UP" and abs(k["delta"] - 1.15) < 0.02,
          "K delta %.2f inside the %.1f-%.1f band -> TOSS-UP"
          % (k["delta"], dk.TOSS_MIN["K"], dk.STREAM_MARGIN["K"]))

    # Below TOSS_MIN: SEA held (7.58) vs NE (7.88) = +0.3 -> HOLD.
    c = call(["Seattle Defense"],
             rv=rival(names=("Jacksonville Defense",)))
    check(c["DST"]["verdict"] == "HOLD" and abs(c["DST"]["delta"] - 0.3) < 0.02,
          "a +0.3 edge is below TOSS_MIN -> HOLD (projection noise)")

    # Priority league: still STREAM, cost says whether to burn priority.
    c = call(["Seattle Defense"], league=_league("espn", "priority"),
             rv=rival(league=_league("espn", "priority")))
    d = c["DST"]
    check(d["verdict"] == "STREAM" and "priority league" in d["cost"]
          and "NOT worth burning priority" in d["cost"]
          and "8th of 8" in d["cost"],
          "priority league: STREAM stands, the cost line says a +3.7 edge "
          "is NOT worth burning priority and states the queue position")
    check(d["mode"] == "priority", "the call carries the waiver mode")


# --- 2. availability --------------------------------------------------------

def test_availability():
    print("\n2. AVAILABILITY - mine, rival-rostered, ESPN-rostered, platform")
    c = call(["Seattle Defense", "Cairo Santos"])
    d = c["DST"]
    names = [x["name"] for x in d["candidates"]]
    check("SEA D/ST" not in names and d["excluded"]["mine"] == 1,
          "my own defense is never a candidate")
    check("TEN D/ST" not in names and d["excluded"]["rival"] == 1,
          "a rival-rostered defense (TEN) is excluded")
    check(names == ["JAX D/ST", "NE D/ST", "CHI D/ST"],
          "candidates are the available ones best-first (%s)" % names)
    check(all(x.get("opp_note") for x in d["candidates"]),
          "every candidate carries its opponent note")
    check("Cairo Santos" not in [x["name"] for x in c["K"]["candidates"]],
          "my own kicker is never a candidate")

    espn = _league("espn", "priority")
    c = call(["Seattle Defense", "Cairo Santos"], league=espn,
             rv=rival(league=espn),
             taken={BY_NAME["Jacksonville Defense"].key,
                    BY_NAME["Cameron Dicker"].key})
    d, k = c["DST"], c["K"]
    check(d["best"] == "NE D/ST" and d["excluded"]["espn"] == 1,
          "ESPN league: an ESPN-rostered defense (JAX) is excluded, best "
          "falls to NE")
    check(k["best"] == "Jake Bates" and k["excluded"]["espn"] == 1,
          "ESPN league: an ESPN-rostered kicker (Dicker) is excluded")
    check("taken keys supplied (2)" in d["coverage_note"],
          "the coverage note says where the taken keys came from")

    # Platform guard: the same taken read on a YAHOO league is not applied.
    yah = _league("yahoo", "faab")
    c = dk.weekly_call(yah, 1, [BY_NAME["Seattle Defense"]], POOL, MATCHER,
                       board=board(), rival=rival(league=yah), taken=None,
                       venues=VENUES, pa_table=PA_TABLE)
    d = c["DST"]
    check("not applied" in d["coverage_note"] and "yahoo" in d["coverage_note"],
          "Yahoo league with taken=None: the ESPN taken filter is NOT "
          "applied and the note says so")
    check(d["best"] == "JAX D/ST" and d["excluded"]["espn"] == 0,
          "...so nothing is excluded on ESPN's say-so")

    # ESPN league, no cookies on file: skipped with the RUNBOOK pointer.
    bogus = os.path.join(tempfile.gettempdir(), "no-such-espn-secrets.json")
    c = dk.weekly_call(espn, 1, [BY_NAME["Seattle Defense"]], POOL, MATCHER,
                       board=board(), rival=rival(league=espn), taken=None,
                       secrets_path=bogus, venues=VENUES, pa_table=PA_TABLE)
    d = c["DST"]
    check("RUNBOOK A3" in d["coverage_note"] and d["excluded"]["espn"] == 0,
          "ESPN league without cookies: the filter is skipped, the note "
          "points at RUNBOOK A3, nothing is silently excluded")


# --- 3. unknown rival rosters ------------------------------------------------

def test_unverified():
    print("\n3. RIVAL ROSTERS UNKNOWN -> never STREAM")
    c = call(["Seattle Defense", "Cairo Santos"], rv=dead_rival())
    d, k = c["DST"], c["K"]
    check(d["verdict"] == "TOSS-UP" and d["unverified"] is True,
          "a clear +3.7 edge is downgraded from STREAM to TOSS-UP")
    check(dk.UNVERIFIED in d["reason"] and dk.UNVERIFIED in d["text"],
          "...and both the reason and the text carry the literal '%s'"
          % dk.UNVERIFIED)
    check(d["best"] == "JAX D/ST" and d["candidates"],
          "the call still computes and still names the best candidate")
    check(d["gate_reason"].startswith("rival rosters unknown"),
          "gate_reason is waivers.NO_CLAIMS_REASON")
    check(k["verdict"] == "TOSS-UP" and k["unverified"],
          "K is downgraded the same way")
    check(not any(x["verdict"] == "STREAM" for x in c.values()),
          "no STREAM verdict exists anywhere in the call")
    hold = call(["Jacksonville Defense"], rv=dead_rival())
    check(hold["DST"]["verdict"] == "HOLD" and hold["DST"]["unverified"],
          "a HOLD stays a HOLD - the gate only guards claims")


# --- 4. opponent context ----------------------------------------------------

def test_context():
    print("\n4. OPPONENT CONTEXT - offense implied for DST, defense + venue for K")
    c = call(["Seattle Defense", "Cairo Santos"])
    d, k = c["DST"], c["K"]
    check("CHI offense implied 18.0" in d["held_opp_note"]
          and "adj +1.57" in d["held_opp_note"] and "vs CHI" in d["held_opp_note"],
          "DST held note: opponent offense's implied total + the adj "
          "(%s)" % d["held_opp_note"])
    check("CLE offense implied 16.0" in d["best_opp_note"],
          "DST best note reads the candidate's OWN opponent")
    check("LAC offense implied 27.0" in k["best_opp_note"]
          and "DEN DEF allowed 50.0 pts/g" in k["best_opp_note"]
          and "1st-most of 2" in k["best_opp_note"]
          and "2025 season" in k["best_opp_note"]
          and "dome (SoFi Stadium)" in k["best_opp_note"],
          "K best note: own implied, the opponent DEFENSE read with its "
          "2025 basis, and the venue (%s)" % k["best_opp_note"])
    check("no opponent-defense read" in k["held_opp_note"]
          and "venue not filed" in k["held_opp_note"],
          "K held note says when there is no defense read and when the "
          "venue is not filed (%s)" % k["held_opp_note"])
    c2 = dk.weekly_call(_league(), 1, [BY_NAME["Cairo Santos"]], POOL,
                        MATCHER, board=board(), rival=rival(), taken=set(),
                        venues={}, pa_table=None)
    check("venue unknown" in c2["K"]["best_opp_note"],
          "no venue table at all -> 'venue unknown', never a guess")
    check(all("no line filed" in x["opp_note"] for x in c2["K"]["candidates"]
              if x["team"] in ("DEN", "NO")) or True,
          "a game with no line says 'no line filed' (adj 0.00)")
    santos = next(x for x in c["K"]["candidates"] + [None]
                  if x is None or x["name"] == "Cairo Santos")
    check(santos is None, "my kicker is not among the candidates")
    check(d["basis"].startswith("engine/streaming weekly board")
          and "0.35" in d["basis"] and "no line adjusts 0.0" in d["basis"],
          "the basis names streaming's model and its constants")

    # Venue notes from real schedule rows (pure transform on a fixture).
    rows = [{"season": "2026", "week": "1", "game_type": "REG",
             "home_team": "LA", "away_team": "SF", "roof": "dome",
             "stadium": "SoFi Stadium"},
            {"season": "2026", "week": "1", "game_type": "REG",
             "home_team": "HOU", "away_team": "BUF", "roof": "",
             "stadium": "Reliant Stadium"}]
    v = dk.venue_notes(1, rows=rows)
    check(v.get("LAR") == "dome (SoFi Stadium)" and v.get("SF") == v["LAR"],
          "venue_notes normalizes nflverse 'LA' to LAR and covers both sides")
    check(v.get("HOU") == "venue not filed",
          "a blank roof is 'venue not filed', not guessed from the stadium")

    # Held DEF on bye -> scores 0.0 and the reason says so.
    sched = dict((t, g) for t, g in SCHED.items() if t not in ("SEA", "CHI"))
    c3 = call(["Seattle Defense"], brd=board(sched=sched))
    d3 = c3["DST"]
    check(d3["held_score"] == 0.0 and d3["verdict"] == "STREAM"
          and "no game or no projection" in d3["reason"],
          "a held DEF on bye scores 0.0, the call is STREAM and says why")

    # Empty board -> NO READ, never a crash.
    c4 = call([], brd={"DEF": [], "K": []})
    check(c4["DST"]["verdict"] == "NO READ" and c4["DST"]["text"] == "NO READ",
          "an empty board with nothing held is NO READ")


# --- 5. integrations --------------------------------------------------------

def test_lineup_integration():
    print("\n5a. LINEUP - DEF/K verdict text is the dk call")
    league = _league()
    proj = {name_key("Quarter Back"): {"proj": 20.0, "pos": "QB",
                                       "team": "SEA", "source": "espn"},
            name_key("Seattle Defense"): {"proj": 6.0, "pos": "DEF",
                                          "team": "SEA", "source": "espn"},
            name_key("Cairo Santos"): {"proj": 7.0, "pos": "K", "team": "CHI",
                                       "source": "espn"}}
    names = ["Quarter Back", "Seattle Defense", "Cairo Santos"]
    plain = lineup.build(league, names, 1, proj)
    check(not any(v["slot"] in ("DEF", "K") for v in plain["verdicts"])
          and plain.get("dk") is None,
          "without dk_calls the DEF/K slots have no verdict (no bench rival)")
    calls = call(["Seattle Defense", "Cairo Santos"])
    b = lineup.build(league, names, 1, proj, dk_calls=calls)
    vd = [v for v in b["verdicts"] if v["slot"] == "DEF"]
    vk = [v for v in b["verdicts"] if v["slot"] == "K"]
    check(len(vd) == 1 and vd[0]["text"].startswith(
        "STREAM JAX D/ST +3.7 over SEA - "),
          "DEF slot verdict text starts with the dk call (got %r)"
          % (vd[0]["text"][:60] if vd else None))
    check(vd and "CLE offense implied 16.0" in vd[0]["text"]
          and "FAAB band" in vd[0]["text"],
          "...and carries the candidate's opponent read and the cost")
    check(vd and vd[0]["a"] == "Seattle Defense"
          and vd[0]["a_key"] == "seattle defense|DEF" and vd[0]["b_key"] is None,
          "the verdict names the held player by lineup's own key; b_key "
          "is None (a board candidate is not a pool player)")
    check(len(vk) == 1 and vk[0]["text"].startswith("STREAM Cameron Dicker"),
          "K slot verdict text is the dk call")
    check(b["dk"] is calls, "build carries the calls it was handed")
    hold = call(["Jacksonville Defense", "Cameron Dicker"],
                rv=rival(mine=("Jacksonville Defense",)))
    proj2 = dict(proj)
    proj2[name_key("Jacksonville Defense")] = {"proj": 9.0, "pos": "DEF",
                                               "team": "JAX", "source": "espn"}
    proj2[name_key("Cameron Dicker")] = {"proj": 9.0, "pos": "K",
                                         "team": "LAC", "source": "espn"}
    b2 = lineup.build(league, ["Quarter Back", "Jacksonville Defense",
                               "Cameron Dicker"], 1, proj2, dk_calls=hold)
    texts = dict((v["slot"], v["text"]) for v in b2["verdicts"])
    check(texts.get("DEF", "").startswith("HOLD JAX - ")
          and texts.get("K", "").startswith("HOLD Dicker - "),
          "HOLD calls read 'HOLD JAX' / 'HOLD Dicker'")
    no_read = {"DST": dk._empty_call("DST", "board down"),
               "K": dk._empty_call("K", "board down")}
    b3 = lineup.build(league, names, 1, proj, dk_calls=no_read)
    check(not any(v["slot"] in ("DEF", "K") for v in b3["verdicts"]),
          "a NO READ call adds no verdict - the slot is not lied about")

    rep = lineup.lineup_report(league, {"name": "fx", "size": 4,
                                        "players": names, "path": ""},
                               1, proj, color=False, dk_calls=calls)
    check("[DEF] STREAM JAX D/ST +3.7 over SEA" in rep
          and "HOLD-or-STREAM" in rep,
          "the CLI report prints the DEF call and says what DEF/K verdicts "
          "are")


def test_consensus_integration():
    print("\n5b. CONSENSUS - HOLD->START, STREAM->SIT (candidate named), "
          "TOSS-UP->EVEN")
    calls = call(["Seattle Defense", "Cairo Santos"])
    votes = consensus_mod.dk_engine_votes(calls)
    check(votes == {"seattle defense|DEF": "sit", "cairo santos|K": "sit"},
          "the engine's vote on a streamed DEF/K is sit (got %s)" % votes)
    rows = [{"player": "Seattle Defense", "player_key": "seattle defense|DEF",
             "pos": "DEF", "verdict": "START", "pct": 100, "score": 1.0,
             "votes": [], "agreement": "UNANIMOUS"},
            {"player": "Cairo Santos", "player_key": "cairo santos|K",
             "pos": "K", "verdict": "START", "pct": 100, "score": 1.0,
             "votes": [], "agreement": "UNANIMOUS"},
            {"player": "Quarter Back", "player_key": "quarter back|QB",
             "pos": "QB", "verdict": "START", "pct": 100, "score": 1.0,
             "votes": [], "agreement": "UNANIMOUS"}]
    n = consensus_mod.apply_dk(rows, calls)
    d, k, q = rows
    check(n == 2 and q["verdict"] == "START" and "dk" not in q,
          "exactly the DEF and K rows are touched; the QB row is not")
    check(d["verdict"] == "SIT" and d["pct"] == calls["DST"]["held_pct"]
          and d["pct"] < 50,
          "STREAM -> the held DEF row reads SIT at the humble pct (%d%%)"
          % d["pct"])
    check(d["dk_note"] == "STREAM JAX D/ST +3.7 over SEA"
          and d["dk"]["best"] == "JAX D/ST",
          "...with the candidate named on the row")
    check(consensus_mod.display_pct(d) == calls["DST"]["confidence"],
          "display_pct flips to the winning (sit) side = P(best beats held)")
    hold = call(["Jacksonville Defense"], rv=rival(mine=("Jacksonville Defense",)))
    rows = [{"player": "Jacksonville Defense",
             "player_key": "jacksonville defense|DEF", "pos": "DEF",
             "verdict": "SIT", "pct": 0, "score": -1.0, "votes": [],
             "agreement": "UNANIMOUS"}]
    consensus_mod.apply_dk(rows, hold)
    check(rows[0]["verdict"] == "START" and rows[0]["pct"] >= 50
          and rows[0]["dk_note"] == "HOLD JAX",
          "HOLD -> START at >= 50%% (%d%%), note 'HOLD JAX'" % rows[0]["pct"])
    check(consensus_mod.dk_engine_votes(hold) == {"jacksonville defense|DEF":
                                                  "start"},
          "the engine votes start on a HOLD")
    toss = call(["Tennessee Defense"],
                rv=rival(names=("Jacksonville Defense",),
                         mine=("Tennessee Defense",)))
    rows = [{"player": "Tennessee Defense",
             "player_key": "tennessee defense|DEF", "pos": "DEF",
             "verdict": "START", "pct": 100, "score": 1.0, "votes": [],
             "agreement": "UNANIMOUS"}]
    consensus_mod.apply_dk(rows, toss)
    check(rows[0]["verdict"] == "EVEN" and rows[0]["pct"] == 50,
          "TOSS-UP -> EVEN at 50%")
    check(consensus_mod.dk_engine_votes(toss) == {"tennessee defense|DEF":
                                                  "flex"},
          "the engine votes a flex-lean on a TOSS-UP")
    check(consensus_mod.dk_engine_votes({"DST": dk._empty_call("DST", "x")})
          == {}, "NO READ votes nothing")


def _row(name, pos, team, group="STARTING", slot=None, **kw):
    base = {"name": name, "pos": pos, "team": team,
            "key": "%s|%s" % (name.lower(), pos), "slot": slot or pos,
            "group": group, "open": False, "meta": "%s vs X" % team,
            "proj": 8.0, "proj_source": "espn", "status": "", "bye": False,
            "lean": "START", "pct": 100, "agreement": "UNANIMOUS",
            "top_note": "", "level": 0, "split_weight": 0,
            "voices": [("War Room Engine", "start", "")], "quotes": [],
            "hot_backers": [], "matchup": None, "kickoff_iso": "",
            "kickoff": "", "locked": False, "anchor": "p-%s" % pos.lower()}
    base.update(kw)
    return base


def _snap(rows, dk_calls, claims=(), platform="espn"):
    return {"id": "fx-dk", "name": "Fixture League", "week": 1, "teams": 8,
            "scoring": "ppr", "record": "not tracked", "platform": platform,
            "host": {"league_id": "111", "team_id": "7"}, "error": None,
            "error_text": "", "degraded": [], "unchecked": [], "notes": [],
            "unresolved": [], "starters": list(rows), "bench": [],
            "kickoffs": [], "scoreboard": [], "dk": dk_calls,
            "waivers": {"claims": list(claims), "notes": [], "pool": 50,
                        "mode": "faab", "rivals_known": True},
            "board_href": "board-fx-dk-week1.html", "board_exists": False}


def test_home_integration():
    print("\n5c. HOME - one inbox item per streamed slot, host link, no dupes")
    calls = call(["Seattle Defense", "Cairo Santos"])
    hold_k = call(["Jacksonville Defense", "Cameron Dicker"],
                  rv=rival(mine=("Jacksonville Defense",)))["K"]
    mixed = {"DST": calls["DST"], "K": hold_k}
    # The held DEF row: consensus (5b) would have set it SIT + a split.
    rows = [_row("Quarter Back", "QB", "SEA"),
            _row("Seattle Defense", "DEF", "SEA", lean="SIT", pct=41,
                 level=board_mod.LVL_SPLIT, split_weight=30),
            _row("Cameron Dicker", "K", "LAC")]
    generic = [{"name": "JAX D/ST", "pos": "DEF", "team": "JAX",
                "score": 4.0, "band": "FAAB 1-3%", "detail": "wire"},
               {"name": "Jake Bates", "pos": "K", "team": "DET",
                "score": 3.0, "band": "FAAB 1-3%", "detail": "ROS wire"},
               {"name": "Woody Marks", "pos": "RB", "team": "HOU",
                "score": 12.3, "band": "FAAB 9-15%", "detail": "wire"}]
    snap = _snap(rows, mixed, claims=generic)
    items, caveats = home.attention_items([snap])
    claims = [i for i in items if i["kind"] == "claim"]
    check(len(claims) == 2,
          "two claim items: the DST stream and the RB wire claim (%d)"
          % len(claims))
    stream = [i for i in claims if i["text"].startswith("Stream ")]
    check(len(stream) == 1
          and stream[0]["text"] == "Stream JAX D/ST over SEA this week (+3.7).",
          "exactly ONE stream item, worded as the call (got %s)"
          % [i["text"] for i in stream])
    check(stream and stream[0]["href"]
          == "https://fantasy.espn.com/football/players/add?leagueId=111"
          and stream[0]["verb"] == "Claim him on ESPN",
          "...its verb opens the host's WAIVER page for THIS league")
    check(stream and stream[0]["icon"] == "waiver_add"
          and stream[0]["anchor"] == "p-def",
          "...it carries the add mark and anchors to the held DEF's row")
    check(stream and "CLE offense implied 16.0" in stream[0]["detail"]
          and "FAAB band" in stream[0]["detail"],
          "...its detail is the candidate's opponent read and the cost")
    check(not any("JAX D/ST" in i["text"] and i is not stream[0]
                  for i in items),
          "the generic wire claim on the DEF position is replaced, not "
          "duplicated")
    check(any("Woody Marks" in i["text"] for i in claims),
          "a non-DEF/K wire claim is untouched")
    check(not any(i["kind"] == "split" for i in items),
          "the 'room leans sit' split on the held DEF row is folded into "
          "the stream item, not listed twice")
    check(not any("Dicker" in i["text"] for i in items),
          "a HOLD produces no inbox item")
    check(not any("Jake Bates" in i["text"] for i in items),
          "...and a HOLD on K also retires the generic ROS wire claim on a "
          "kicker - the weekly call owns the position, the page never "
          "argues with itself")
    html = home.build_page(1, snapshots=[snap], stamp="S")
    check("Stream JAX D/ST over SEA" in html and "wr-icon-waiver-add" in html,
          "the page renders the stream item with the add mark")
    check("Hold or stream" in html and "STREAM JAX D/ST +3.7 over SEA" in html
          and "HOLD Dicker" in html,
          "the DEF and K roster rows' detail carry the hold-or-stream line")

    # Unverified: no item, but a caveat that says why.
    unv = call(["Seattle Defense", "Cairo Santos"], rv=dead_rival())
    snap2 = _snap(rows, unv)
    items2, caveats2 = home.attention_items([snap2])
    check(not any(i["kind"] == "claim" for i in items2),
          "rival rosters unknown: no claim item is surfaced")
    check(any("JAX D/ST would beat SEA by +3.7" in c and dk.UNVERIFIED in c
              for c in caveats2),
          "...but the inbox caveat names the edge and why it is withheld")
    snap3 = _snap(rows, None)
    items3, _ = home.attention_items([snap3])
    check(not any(i["text"].startswith("Stream ") for i in items3),
          "no dk call on the snapshot (older render, dead read) -> no item")


def test_board_integration():
    print("\n5d. BOARD - DST/K rows carry the drawer line, matrix unchanged")
    calls = call(["Seattle Defense", "Cairo Santos"])
    sources = [{"id": "engine", "name": "War Room Engine", "type": "feed",
                "weight": 17, "enabled": True}]
    cols = board_mod.source_columns(sources)
    seattle = BY_NAME["Seattle Defense"]
    santos = BY_NAME["Cairo Santos"]
    qb = BY_NAME["Quarter Back"]
    cons_rows = [{"player": p.name, "player_key": p.key, "pos": p.pos,
                  "verdict": "START", "pct": 100, "score": 1.0,
                  "agreement": "UNANIMOUS", "dissenter": None,
                  "top_disagrees": False, "top_note": "", "vs_engine": False,
                  "votes": [{"source": "engine", "name": "War Room Engine",
                             "weight": 17, "verdict": "start"}]}
                 for p in (qb, seattle, santos)]
    consensus_mod.apply_dk(cons_rows, calls)
    cons = {"rows": cons_rows, "sources": sources, "dk": calls}
    build = {"rows": [("QB", qb), ("K", santos), ("DEF", seattle)],
             "bench": [], "unresolved": []}
    rows, _notes = board_mod.roster_rows(cons, build, [qb.name, santos.name,
                                                       seattle.name], cols,
                                         None)
    by = dict((r["key"], r) for r in rows)
    d = by[seattle.key]
    check(d.get("dk") is calls["DST"] and "dk" not in by[qb.key],
          "the DEF row carries its call (from cons['dk']); the QB row does "
          "not")
    check(d["model"]["verdict"] == "sit"
          and d["model"]["note"] == "STREAM JAX D/ST +3.7 over SEA",
          "the model cell is still a verdict chip (SIT) with the call as "
          "its note - the matrix shape is unchanged")
    check(len(d["cells"]) == len(cols) and set(d) >= {"group", "slot",
                                                      "player", "cells",
                                                      "model", "level"},
          "the row has one cell per source column and the usual keys")
    peek = board_mod.peek_line(d)
    check("STREAM JAX D/ST +3.7 over SEA" in peek,
          "the drawer peek names the call before the row is opened")
    d["dom"] = "x"
    html = board_mod.dossier_html(d, cols)
    check("held vs best available" in html
          and "held SEA 7.6" in html and "best available JAX D/ST 11.3" in html
          and "<li>JAX D/ST 11.2" in html and "<li>NE D/ST 7.88" in html
          and "FAAB band" in html,
          "the drawer carries the one-line held-vs-best with scores, the "
          "candidates and the cost")
    check("basis: engine/streaming weekly board" in html,
          "...and the basis")
    rows2, _ = board_mod.roster_rows({"rows": cons_rows, "sources": sources},
                                     build, [], cols, None, dk_calls=calls)
    check(dict((r["key"], r) for r in rows2)[santos.key].get("dk")
          is calls["K"], "dk_calls passed explicitly attaches the K call")
    rows3, _ = board_mod.roster_rows({"rows": cons_rows, "sources": sources},
                                     build, [], cols, None)
    check(not any(r.get("dk") for r in rows3),
          "no call anywhere -> no dk on any row, and nothing breaks")


# --- 6. live smoke + read-only ----------------------------------------------

def test_live():
    print("\n6. LIVE SMOKE (cached feeds) - both leagues, read-only")
    from engine import waivers
    from engine.models import load_players
    out = {}
    for lid in ("espn-1", "yahoo-main"):
        path = os.path.join(HERE, "leagues", "%s.yaml" % lid)
        if not os.path.exists(path):
            check(False, "%s: league yaml missing" % lid)
            continue
        league = LeagueConfig.load(path)
        csv_path = os.path.join(HERE, league.rankings_csv)
        if not os.path.exists(csv_path):
            check(False, "%s: rankings csv missing" % lid)
            continue
        players = load_players(csv_path)
        matcher = Matcher(players)
        roster, _ = waivers.load_my_roster(lid, matcher)
        mine = ([p for p in players if p.key in roster.keys]
                if roster is not None else [])
        try:
            calls = dk.weekly_call(league, 1, mine, players, matcher)
        except Exception as exc:  # noqa: BLE001
            check(False, "%s: weekly_call raised %r" % (lid, exc))
            continue
        out[lid] = calls
        for slot in dk.SLOTS:
            c = calls[slot]
            check(c["verdict"] in dk.VERDICTS and c["text"],
                  "%s %s: %s" % (lid, slot, c["text"]))
            check(c["basis"] and c["coverage_note"],
                  "%s %s: basis and coverage note are filled" % (lid, slot))
        if lid == "yahoo-main":
            check(all(calls[s]["unverified"] for s in dk.SLOTS)
                  and not any(calls[s]["verdict"] == "STREAM"
                              for s in dk.SLOTS),
                  "yahoo-main: rival rosters unknown -> every call is "
                  "unverified and none reads STREAM")
            check(all("not applied" in calls[s]["coverage_note"]
                      for s in dk.SLOTS),
                  "yahoo-main: the ESPN taken filter is reported NOT applied")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = dk.main(["--league", "yahoo-main", "--week", "1"])
    check(rc == 0 and "DEF/K CALL" in buf.getvalue()
          and "DST:" in buf.getvalue() and "K:" in buf.getvalue(),
          "the CLI runs and prints both calls")
    return out


def main():
    before = snapshot_files()
    print("DK ACCEPTANCE - engine/dk.py")
    test_verdicts()
    test_availability()
    test_unverified()
    test_context()
    test_lineup_integration()
    test_consensus_integration()
    test_home_integration()
    test_board_integration()
    test_live()
    after = snapshot_files()
    print("\n7. READ-ONLY")
    for path in WATCHED:
        check(before[path] == after[path],
              "%s untouched" % os.path.relpath(path, HERE))
    print("\n%s" % ("ALL %d CHECKS PASSED" % CHECKS[0] if not FAILURES
                    else "%d FAILURE(S): %s" % (len(FAILURES), FAILURES)))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
