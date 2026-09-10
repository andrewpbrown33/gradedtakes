#!/usr/bin/env python3
"""Acceptance test: trade analyzer (engine/trades.py).

No network anywhere: FantasyCalc is exercised from a fixture written into a
REDIRECTED cache dir (trades.CACHE_DIR -> tempdir, restored in finally, same
isolation rule as mock_draft's SAVE_DIR redirect - never write into the real
data/cache from a test). Covers: the ppr/numQbs param mapping from league
scoring, fixture parse + name mapping onto our pool, the stale-cache offline
fallback, the quantile projection scale, lopsided-offer verdicts in both
directions plus CLOSE and the systems-disagree hold, lineup impact sign,
offer parsing, and no-offer trade constructs.

Rival-awareness is proved on a synthetic mirror league (one rival RB-rich
and WR-poor, us the reverse) with an INJECTED leagueview loader, so the
named-target math is tested whether or not engine/leagueview.py exists yet;
the same section proves every degradation path - missing module, garbage
shapes, a league where only my own roster is known - lands on the literal
"rival rosters unknown - constructs only" line.

    .venv/bin/python tests/trades_test.py
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import trades                                          # noqa: E402
from engine.ingest import Matcher                                  # noqa: E402
from engine.models import LeagueConfig, Player, load_players       # noqa: E402

FAILURES = []


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def load_pool():
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "yahoo-main.yaml"))
    players = load_players(os.path.join(HERE, league.rankings_csv))
    return league, players


def fc_row(name, pos, value, rank):
    """A raw FantasyCalc-schema row, as the live API returns it."""
    return {"player": {"name": name, "position": pos}, "value": value,
            "overallRank": rank, "redraftValue": value}


# --- 1. ppr / numQbs param mapping ------------------------------------------
def test_param_mapping():
    print("\n1. FANTASYCALC PARAM MAPPING (league scoring -> query params)")
    league, _ = load_pool()
    check(trades.ppr_param(league) == "1",
          "yahoo-main (reception=1) maps to ppr=1")
    check(trades.num_qbs_param(league) == 1,
          "yahoo-main (no QB-eligible flex) maps to numQbs=1")

    half = LeagueConfig({"teams": 12, "scoring": {"reception": 0.5},
                         "roster_spots": ["QB", "RB", "WR", "FLEX"]})
    check(trades.ppr_param(half) == "0.5", "reception=0.5 maps to ppr=0.5")
    std = LeagueConfig({"teams": 10, "scoring": {},
                        "roster_spots": ["QB", "RB", "WR"]})
    check(trades.ppr_param(std) == "0", "no reception scoring maps to ppr=0")
    sflex = LeagueConfig({"teams": 10, "scoring": {"reception": 1},
                          "roster_spots": ["QB", "SUPERFLEX", "RB", "WR"]})
    check(trades.num_qbs_param(sflex) == 2,
          "SUPERFLEX league maps to numQbs=2")
    check(trades.cache_path("1", 1).endswith("fantasycalc-1qb-ppr1.json"),
          "cache filename carries both params")


# --- 2. fixture fetch + parse + pool mapping + stale fallback ---------------
def test_fixture_fetch_and_mapping():
    print("\n2. FIXTURE FETCH, PARSE, POOL MAPPING (cache redirected; "
          "no network)")
    league, players = load_pool()
    matcher = Matcher(players)

    fixture = [
        fc_row("Jahmyr Gibbs", "RB", 10573, 1),
        fc_row("Jamar Chase", "WR", 9522, 2),           # fuzzy: apostrophe+r
        fc_row("Kenneth Walker III", "RB", 4200, 3),    # suffix normalizes
        fc_row("Puka Nacua", "WR", 9229, 4),
        fc_row("Zay Flowers", "WR", 3672, 5),
        fc_row("Nobody Fakeman", "WR", 9999, 6),        # not in our pool
    ]

    real_cache = trades.CACHE_DIR
    trades.CACHE_DIR = tempfile.mkdtemp(prefix="trades-cache-")
    real_urlopen = trades.urllib.request.urlopen
    try:
        path = trades.cache_path("1", 1)
        os.makedirs(trades.CACHE_DIR, exist_ok=True)
        with open(path, "w") as fh:
            json.dump(fixture, fh)

        rows = trades.fetch_fantasycalc("1", 1, max_age_hours=9999,
                                        quiet=True)
        check(len(rows) == 6, "fresh cache served without touching the net")

        parsed = trades.parse_rows(rows)
        check(parsed[0]["name"] == "Jahmyr Gibbs"
              and parsed[0]["pos"] == "RB"
              and parsed[0]["value"] == 10573.0,
              "raw FantasyCalc schema flattens to name/pos/value")

        market = trades.market_values(players, parsed, matcher)
        by_name = dict((p.key, p) for p in players)
        gibbs = next(p for p in players if p.name == "Jahmyr Gibbs")
        chase = next(p for p in players if p.name == "Ja'Marr Chase")
        walker = next(p for p in players if p.name == "Kenneth Walker")
        check(market.get(gibbs.key) == 10573.0, "exact name maps by key")
        check(market.get(chase.key) == 9522.0,
              "misspelled 'Jamar Chase' fuzzy-maps to Ja'Marr Chase")
        check(market.get(walker.key) == 4200.0,
              "'Kenneth Walker III' suffix-normalizes onto the pool")
        check(len(market) == 5 and by_name,
              "the row matching nobody in the pool is dropped, not guessed")

        # Stale fallback: cache expired + network down -> serve stale copy.
        def _down(*a, **k):
            raise urllib.error.URLError("no route to host")
        trades.urllib.request.urlopen = _down
        rows2 = trades.fetch_fantasycalc("1", 1, max_age_hours=0.0,
                                         quiet=True)
        check(len(rows2) == 6,
              "expired cache + dead network falls back to the stale copy")

        # No cache at all + dead network -> loud RuntimeError.
        os.remove(path)
        try:
            trades.fetch_fantasycalc("1", 1, max_age_hours=0.0, quiet=True)
            check(False, "no cache + dead network raises")
        except RuntimeError:
            check(True, "no cache + dead network raises")
    finally:
        trades.urllib.request.urlopen = real_urlopen
        shutil.rmtree(trades.CACHE_DIR, ignore_errors=True)
        trades.CACHE_DIR = real_cache


# --- 3. projection view on the market scale ---------------------------------
def synthetic_market(players, projv_order=None):
    """Market dict over QB/RB/WR/TE pool: geometric decay in rank order.

    projv_order=True keys the decay to VBD order instead, so market and
    projections agree perfectly (for CLOSE-verdict construction).
    """
    pool = [p for p in players if p.pos in trades.MARKET_POSITIONS]
    if projv_order:
        from engine.models import DraftState
        from engine.recommend import replacement_levels, vbd
        league, _ = load_pool()
        state = DraftState(league, players)
        repl = replacement_levels(state)
        pool = sorted(pool, key=lambda p: -vbd(p, repl))
    market = {}
    for i, p in enumerate(pool[:200]):
        market[p.key] = round(10000.0 * (0.97 ** i), 1)
    return market


def test_proj_scale():
    print("\n3. PROJECTION VIEW ON THE MARKET SCALE (quantile map)")
    league, players = load_pool()
    market = synthetic_market(players)
    projv = trades.proj_scale_values(league, players, market)

    from engine.models import DraftState
    from engine.recommend import replacement_levels, vbd
    state = DraftState(league, players)
    repl = replacement_levels(state)
    pool = sorted((p for p in players
                   if p.pos in trades.MARKET_POSITIONS and p.proj_points),
                  key=lambda p: -vbd(p, repl))
    top, second, last = pool[0], pool[1], pool[-1]
    check(projv[top.key] == max(market.values()),
          "our #1 by VBD gets the market's top value (%s)" % top.name)
    check(projv[top.key] >= projv[second.key] >= projv[last.key],
          "quantile map is monotonic in VBD order")
    floor = min(market.values())
    kdef = [p for p in players if p.pos in ("K", "DEF")]
    check(kdef and all(projv[p.key] == floor for p in kdef),
          "K/DEF are floored - fungible streamers, never trade currency")

    check(trades.disagreement(9000.0, 3000.0) == "MARKET>>PROJ"
          and trades.disagreement(3000.0, 9000.0) == "PROJ>>MARKET"
          and trades.disagreement(9000.0, 8000.0) == ""
          and trades.disagreement(None, 5000.0) == "",
          "per-player disagreement gates on ratio AND absolute size")


# --- 4. offer verdicts ------------------------------------------------------
def test_offer_verdicts():
    print("\n4. OFFER VERDICTS (synthetic lopsided offers, both directions)")
    league, players = load_pool()
    market = synthetic_market(players, projv_order=True)
    projv = trades.proj_scale_values(league, players, market)
    by_value = sorted((k for k in market), key=lambda k: -market[k])
    by_key = dict((p.key, p) for p in players)
    stud = by_key[by_value[0]]
    scrub = by_key[by_value[-1]]
    roster = [by_key[k] for k in by_value[40:44]]   # mid-tier known roster

    rep = trades.evaluate_offer(league, players, [scrub], [stud],
                                market, projv, roster, 16)
    check(rep.verdict == "ACCEPT",
          "give %s / get %s -> ACCEPT" % (scrub.surname(), stud.surname()))
    check(rep.market_pct > 0.5 and rep.proj_pct > 0.5,
          "lopsided margin is huge under BOTH systems")
    check(rep.lineup_delta_wk > 0,
          "landing the stud upgrades the actual lineup (pts/wk positive)")

    rep2 = trades.evaluate_offer(league, players, [stud], [scrub],
                                 market, projv, roster, 16)
    check(rep2.verdict == "DECLINE", "the same offer reversed -> DECLINE")
    check(rep2.lineup_delta_wk < 0, "and it downgrades the lineup")

    # Adjacent players under value systems that agree -> CLOSE.
    a, b = by_key[by_value[20]], by_key[by_value[21]]
    rep3 = trades.evaluate_offer(league, players, [a], [b],
                                 market, projv, roster, 16)
    check(rep3.verdict == "CLOSE",
          "trading adjacent values (%s for %s) -> CLOSE"
          % (a.surname(), b.surname()))

    # Hard disagreement: market loves A, projections love B -> held at CLOSE.
    m2 = {a.key: 9000.0, b.key: 1000.0}
    p2 = {a.key: 1000.0, b.key: 9000.0}
    rep4 = trades.evaluate_offer(league, players, [a], [b], m2, p2,
                                 roster, 16)
    check(rep4.verdict == "CLOSE" and rep4.systems_disagree,
          "market/proj pointing opposite ways is held at CLOSE and flagged")

    txt = trades.offer_report_text(league, rep, 4, 16, [], color=False)
    check("VERDICT: ACCEPT" in txt and "PARTIAL ROSTER" in txt,
          "offer report prints the verdict AND the partial-roster banner")
    check("pts/wk" in txt and "KNOWN players" in txt,
          "starter impact line is present and scoped to known players")


# --- 5. offer parsing -------------------------------------------------------
def test_offer_parsing():
    print("\n5. OFFER STRING PARSING")
    g, t = trades.parse_offer("give: A. Player, B Player | get: C Player")
    check(g == ["A. Player", "B Player"] and t == ["C Player"],
          "give/get sides split on commas")
    g2, t2 = trades.parse_offer("GET: X | GIVE: Y")
    check(g2 == ["Y"] and t2 == ["X"], "order and case do not matter")
    for bad in ("give: A", "get: B", "nonsense", "give: | get: B"):
        try:
            trades.parse_offer(bad)
            check(False, "malformed offer %r raises" % bad)
        except ValueError:
            check(True, "malformed offer %r raises" % bad)


# --- 6. no-offer constructs -------------------------------------------------
def test_constructs():
    print("\n6. NO-OFFER MODE (gaps/ammo via grader logic + constructs)")
    league, players = load_pool()
    rbs = [p for p in players if p.pos == "RB"][:5]     # 5 RB > 2 hard + 2 flex
    qb = next(p for p in players if p.pos == "QB")
    roster = rbs + [qb]

    shim = trades._RosterState(league, roster)
    from engine.grader import positional_gaps, surplus_positions
    check(any(s.startswith("RB") for s in surplus_positions(shim, 0)),
          "5 known RBs read as surplus through grader's own logic")
    check(any(g.startswith("WR") for g in positional_gaps(shim, 0)),
          "open WR starting demand reads as a gap")

    constructs = trades.suggest_constructs(league, roster, len(roster), 16)
    check(1 <= len(constructs) <= 3, "2-3 constructs, never a flood")
    check(any("RB" in s and "shop" in s for s in constructs),
          "construct says to shop the RB surplus")
    check(not any(":" in s and "Team" in s for s in constructs),
          "constructs name shapes, not fabricated rival offers")

    # Thin roster (the real 3/16 situation): still honest, still helpful.
    thin = [p for p in players if p.pos == "WR"][:3]
    thin_constructs = trades.suggest_constructs(league, thin, 3, 16)
    check(thin_constructs and any("KNOWN" in s or "known" in s
                                  for s in thin_constructs),
          "thin-roster constructs admit how little is known")

    market = synthetic_market(players)
    projv = trades.proj_scale_values(league, players, market)
    txt = trades.no_offer_report_text(league, thin, 3, 16, [], market,
                                      projv, color=False)
    check("PARTIAL ROSTER" in txt and "3 of 16" in txt,
          "no-offer report carries the honest coverage banner")
    check("TRADE CONSTRUCTS" in txt and "not offers to named rivals" in txt,
          "report frames suggestions as constructs")
    check("rival" in txt, "rival-naming status line present (guarded hook)")


# --- 7. rival-aware named targets -------------------------------------------
def _p(rank, name, pos, proj):
    return Player(rank=rank, name=name, pos=pos, team="XXX", proj_points=proj)


REPL = {"QB": 100.0, "RB": 100.0, "WR": 100.0, "TE": 100.0}


def mirror_league():
    """A league where WE are WR-rich/RB-poor and one rival is the mirror.

    Startable bar is REPL (100) for every position, so the counts below are
    readable by eye: hard slots QB1/RB2/WR2/TE1 plus one W/R/T flex.
    """
    league = LeagueConfig({"id": "mirror", "name": "Mirror League", "teams": 3,
                           "roster_spots": ["QB", "RB", "RB", "WR", "WR",
                                            "TE", "W/R/T", "BN", "BN", "BN"],
                           "rounds": 10, "scoring": {"reception": 1}})
    mine = [_p(1, "Quinn Quarter", "QB", 200), _p(2, "Rob Alpha", "RB", 180),
            _p(3, "Rob Scrub", "RB", 60), _p(4, "Wes Alpha", "WR", 200),
            _p(5, "Wes Beta", "WR", 190), _p(6, "Wes Gamma", "WR", 180),
            _p(7, "Wes Delta", "WR", 170), _p(8, "Ted Alpha", "TE", 150)]
    # The mirror: 4 startable RB (2 of them spare), 1 startable WR.
    swap = [_p(11, "Sid Quarter", "QB", 200), _p(12, "Rick Alpha", "RB", 190),
            _p(13, "Rick Beta", "RB", 185), _p(14, "Rick Gamma", "RB", 175),
            _p(15, "Rick Delta", "RB", 165), _p(16, "Ron Alpha", "WR", 195),
            _p(17, "Ron Scrub", "WR", 50), _p(18, "Tim Alpha", "TE", 150)]
    # Same RB surplus, but the spare is a stud AND their WR2 is already fine:
    # nothing we can pay with makes their starting lineup better.
    steal = [_p(21, "Sam Quarter", "QB", 200), _p(22, "Stu Alpha", "RB", 300),
             _p(23, "Stu Beta", "RB", 290), _p(24, "Stu Gamma", "RB", 285),
             _p(25, "Stu Delta", "RB", 280), _p(26, "Sal Alpha", "WR", 195),
             _p(27, "Sal Beta", "WR", 190), _p(28, "Tom Alpha", "TE", 150)]
    # Stud RB depth too, but a hole at WR2 - so the same "unfair" price
    # still upgrades THEIR starters, which is a different conversation.
    open_wr = [_p(31, "Hal Quarter", "QB", 200), _p(32, "Hank Alpha", "RB", 300),
               _p(33, "Hank Beta", "RB", 290), _p(34, "Hank Gamma", "RB", 285),
               _p(35, "Hank Delta", "RB", 280), _p(36, "Hal Alpha", "WR", 195),
               _p(37, "Hal Scrub", "WR", 40), _p(38, "Hal Tight", "TE", 150)]
    players = mine + swap + steal + open_wr
    teams = {"1": {"name": "Us", "players": [p.name for p in mine]},
             "2": {"name": "Mirror Mikes",
                   "players": [{"player": p.name, "pos": p.pos} for p in swap]},
             "3": {"name": "Steal City",
                   "players": [p.name for p in steal]},
             "4": {"name": "Hole At Wide",
                   "players": [p.name for p in open_wr]}}
    market = dict((p.key, round(20.0 * float(p.proj_points), 1))
                  for p in players)
    projv = dict(market)
    return league, players, mine, teams, market, projv


def test_rival_targets():
    print("\n7. RIVAL-AWARE TARGETS (synthetic mirror: they are RB-rich/"
          "WR-poor, we are the reverse)")
    league, players, mine, teams, market, projv = mirror_league()
    matcher = Matcher(players)

    def loader(league_id):
        return teams, {"teams_known": 3, "source": "synthetic"}

    view = trades.load_rival_view(league, matcher, players,
                                  my_keys=set(p.key for p in mine),
                                  loader=loader)
    check(view.available and len(view.teams) == 3,
          "leagueview shape {slot: {name, players}} loads 3 rivals")
    check(view.me is not None and view.me.name == "Us",
          "my own team is identified by roster overlap and kept out of the "
          "rival list")
    check(all(len(t.players) == 8 for t in view.teams),
          "rival rosters resolve onto our pool (plain names AND dict rows)")

    my_net = trades.positional_net(league, mine, REPL)
    check(my_net["WR"] == 1 and my_net["RB"] == -1,
          "our shape: +1 startable WR (flex already spent), -1 RB "
          "(got %s)" % my_net)
    mirror = next(t for t in view.teams if t.name == "Mirror Mikes")
    trades.shape_team(league, mirror, REPL)
    check("+1 startable RB" in mirror.shape_label()
          and "-1 WR" in mirror.shape_label(),
          "their shape reads '%s'" % mirror.shape_label())

    targets = trades.rival_targets(league, players, mine, view, market, projv,
                                   repl=REPL, limit=12)
    check(bool(targets), "named targets are produced, not just constructs")
    swap = next((t for t in targets if t.team.name == "Mirror Mikes"), None)
    check(swap is not None, "the mirror rival gets a proposal")
    check(swap is not None and swap.give.pos == "WR" and swap.get.pos == "RB",
          "the obvious swap is proposed: give WR depth, get RB "
          "(%s)" % (swap.headline() if swap else "none"))
    check(swap is not None and swap.give_market > 0 and swap.get_market > 0
          and swap.give_proj > 0 and swap.get_proj > 0,
          "both value systems are priced on both sides of the offer")
    check(swap is not None and "market" in swap.value_label()
          and "proj" in swap.value_label(),
          "the printed value line carries market AND proj")
    check(swap is not None and swap.my_delta_wk > 0 and swap.their_delta_wk > 0,
          "starter impact is computed for BOTH sides and both gain (%s)"
          % (swap.starters_label() if swap else "none"))
    check(swap is not None and not swap.lopsided
          and swap.accept_odds == trades.ACCEPT_MUTUAL,
          "an even-value swap that helps both lineups is the sellable one")
    check(swap is not None and "Mirror Mikes is +1 startable RB" in
          swap.summary() and "offer" in swap.summary(),
          "the headline names the team, its shape, and the players")

    steal = next((t for t in targets if t.team.name == "Steal City"), None)
    check(steal is not None and steal.lopsided
          and steal.blended_pct >= trades.LOPSIDED_BAND,
          "prying a stud loose for depth is flagged lopsided, not sold as a "
          "plan")
    check(steal is not None and steal.their_delta_wk <= 0,
          "the flag is earned: their starting lineup does not gain either")
    check(steal is not None and "they likely decline" in steal.lopsided_note,
          "...and says so in the words a manager needs: '%s'"
          % (steal.lopsided_note if steal else "none"))
    check(steal is not None and steal.accept_odds == trades.ACCEPT_LOPSIDED,
          "the acceptance odds drop to the floor for a proposal like that")
    check(steal is None or swap is None or swap.score > steal.score,
          "the acceptable trade outranks the fantasy one (%.2f vs %.2f)"
          % (swap.score if swap else -1, steal.score if steal else -1))

    # Same unfair-looking price, but it fills a hole in THEIR lineup.
    hole = next((t for t in targets if t.team.name == "Hole At Wide"), None)
    check(hole is not None and hole.lopsided and hole.their_delta_wk > 0,
          "a rival with an actual WR hole gains starters on the same price")
    check(hole is not None and "worth asking" in hole.lopsided_note
          and "they likely decline" not in hole.lopsided_note,
          "...so it is flagged lopsided but NOT written off: '%s'"
          % (hole.lopsided_note if hole else "none"))
    check(hole is not None and steal is not None
          and hole.accept_odds > steal.accept_odds,
          "'he cannot start that depth' beats 'he just loses value'")

    txt = trades.no_offer_report_text(league, mine, len(mine), 10, [],
                                      market, projv, color=False, view=view,
                                      targets=targets, repl=REPL)
    check("NAMED TARGETS" in txt and "offer" in txt,
          "the report grows a NAMED TARGETS section")
    check("they likely decline" in txt,
          "the lopsided warning survives into the rendered report")
    check("starters: me" in txt and "pts/wk" in txt,
          "both-sides starter impact is printed in pts/wk")


# --- 8. honest degradation with no rival data -------------------------------
def test_rivals_unknown():
    print("\n8. HONEST DEGRADATION (no leagueview, bad shapes, own team only)")
    league, players, mine, teams, market, projv = mirror_league()
    matcher = Matcher(players)

    def boom(league_id):
        raise ImportError("engine/leagueview.py not present")

    view = trades.load_rival_view(league, matcher, players,
                                  my_keys=set(p.key for p in mine),
                                  loader=boom)
    check(not view.available and view.teams == [],
          "a missing leagueview yields an unavailable view, not a crash")
    check(view.reason.startswith(trades.RIVALS_UNKNOWN),
          "the reason opens with the exact line: %r" % trades.RIVALS_UNKNOWN)
    check("ImportError" in view.reason,
          "...and names the real cause instead of hand-waving")
    check(trades.rival_targets(league, players, mine, view, market, projv,
                               repl=REPL) == [],
          "no rival data -> zero named targets, never an invented one")

    for bad in (None, {}, [], "nope", {"teams": "not a mapping"}):
        v = trades.load_rival_view(league, matcher, players,
                                   loader=lambda _id, b=bad: b)
        check(not v.available and v.reason.startswith(trades.RIVALS_UNKNOWN),
              "garbage from leagueview (%r) degrades honestly" % (bad,))

    # A league where only MY roster is known (Kid's Table today).
    only_me = {"1": {"name": "Us", "players": [p.name for p in mine]}}
    v = trades.load_rival_view(league, matcher, players,
                               my_keys=set(p.key for p in mine),
                               loader=lambda _id: only_me)
    check(not v.available and "none of them a rival" in v.reason,
          "knowing only my own roster is NOT rival data, and says so")

    txt = trades.no_offer_report_text(league, mine, len(mine), 10, [],
                                      market, projv, color=False, view=view,
                                      targets=[], repl=REPL)
    check(trades.RIVALS_UNKNOWN in txt,
          "the report prints '%s' verbatim" % trades.RIVALS_UNKNOWN)
    check("no rival is named, no offer is invented" in txt,
          "...and states the limit instead of showing an empty list")
    check("TRADE CONSTRUCTS" in txt,
          "the constructs section still runs - degradation loses the "
          "targets, not the help")

    txt2 = trades.no_offer_report_text(league, mine, len(mine), 10, [],
                                       market, projv, color=False)
    check(trades.RIVALS_UNKNOWN in txt2,
          "a caller that passes no view at all gets the same honest line")


# --- 9. integration with the shipped engine/leagueview.py -------------------
def test_leagueview_integration():
    print("\n9. INTEGRATION (real engine/leagueview.py, real league data, "
          "synthetic market - still no network)")
    if trades._leagueview is None:
        check(False, "engine/leagueview.py importable")
        return

    espn = LeagueConfig.load(os.path.join(HERE, "leagues", "espn-1.yaml"))
    players = load_players(os.path.join(HERE, espn.rankings_csv))
    matcher = Matcher(players)
    roster, known, size, unresolved = trades.load_my_roster(espn, matcher,
                                                            players)
    view = trades.load_rival_view(espn, matcher, players,
                                  my_keys=set(p.key for p in roster))
    check(view.available,
          "the DEFAULT loader reaches leagueview and returns rivals (%s)"
          % view.reason)
    check(len(view.teams) == espn.teams - 1,
          "%d rivals for an %d-team league - my own team excluded exactly "
          "once (got %d)" % (espn.teams - 1, espn.teams, len(view.teams)))
    check(view.me is not None and view.me.is_me,
          "my team is identified, so no proposal trades with myself")
    check(all(t.players for t in view.teams),
          "every rival roster resolved onto our rankings pool")

    market = synthetic_market(players)
    projv = trades.proj_scale_values(espn, players, market)
    repl = trades.replacement_from_pool(espn, players)
    targets = trades.rival_targets(espn, players, roster, view, market, projv,
                                   repl=repl)
    check(all(t.get.key not in set(p.key for p in roster) for t in targets),
          "no target asks for a player we already hold")
    check(all(t.give.key in set(p.key for p in roster) for t in targets),
          "no target offers a player we do not hold")
    check(all(t.my_delta_wk > 0 for t in targets),
          "every surviving proposal upgrades OUR starting lineup")
    txt = trades.no_offer_report_text(espn, roster, known, size, unresolved,
                                      market, projv, color=False, view=view,
                                      targets=targets, repl=repl)
    check("NAMED TARGETS" in txt and "rival rosters known" in txt,
          "the live report names rivals instead of the unknown line")

    # Kid's Table: leagueview knows only MY roster, so this must degrade.
    yahoo = LeagueConfig.load(os.path.join(HERE, "leagues",
                                           "yahoo-main.yaml"))
    ypool = load_players(os.path.join(HERE, yahoo.rankings_csv))
    ymatch = Matcher(ypool)
    yroster, _, _, _ = trades.load_my_roster(yahoo, ymatch, ypool)
    yview = trades.load_rival_view(yahoo, ymatch, ypool,
                                   my_keys=set(p.key for p in yroster))
    check(not yview.available
          and yview.reason.startswith(trades.RIVALS_UNKNOWN),
          "Kid's Table has no rival rosters and says so: %s" % yview.reason)


def main():
    print("=" * 74)
    print("TRADE ANALYZER TEST (engine/trades.py) - no network, cache "
          "redirected")
    test_param_mapping()
    test_fixture_fetch_and_mapping()
    test_proj_scale()
    test_offer_verdicts()
    test_offer_parsing()
    test_constructs()
    test_rival_targets()
    test_rivals_unknown()
    test_leagueview_integration()

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
