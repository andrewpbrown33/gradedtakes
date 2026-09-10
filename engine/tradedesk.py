#!/usr/bin/env python3
"""THE TRADE DESK - the board's league view, promoted to its own page.

    python -m engine.tradedesk --league espn-1 [--week N] [--out PATH] [--force]
    -> tradedesk-<league>-week<N>.html   (the path is printed as the LAST line)

The owner called the board's league view "a powerful resource to identify
needs and weaknesses over time". This page is that view given room to
breathe, plus the one thing a single render can never show: time.

FIVE READS, ONE PAGE - every number computed by the module that owns it:

  1. LEAGUE GRID     every known roster as a COLUMN, starters over bench,
                     my team first under the gold rule. Cells carry the
                     marks that matter at a trade desk: ALSO YOURS (a
                     player I also hold in my other league, engine/exposure),
                     TARGET (a player a proposal below asks for), OFFER (a
                     player a proposal below gives). Each column head
                     carries the SURPLUS / HOLE tags from
                     engine.trades.positional_net - imported, not rewritten.
  2. NEEDS MATRIX    teams x QB/RB/WR/TE, one five-segment ink meter per
                     cell (ui.matchup_meter, relabelled as depth). Read a
                     ROW for a team's shape; read a COLUMN for who is
                     starved at a position.
  3. TRADE TARGETS   engine.trades.rival_targets, one card each: give / get,
                     BOTH valuations (FantasyCalc market + our ROS on the
                     same scale), pts/wk for BOTH sides, the "they likely
                     decline" flag, the one-line rationale, and the exact
                     CLI command that evaluates the offer. Read-only page:
                     the offer evaluator stays in the CLI.
  4. WAIVER COMP.    engine.waivers' competition read over the top waiver
                     candidates: which rivals are structurally short at the
                     position, which would start him - as stacks of names.
  5. NEEDS OVER TIME one snapshot per week, data/cache/league-needs-
                     <league>-week<N>.json, written ONLY when the week's
                     file is absent and NEVER rewritten. Two or more weeks
                     on file -> per-team, per-position deltas ("RB need
                     up since wk 1"). One week -> the page says "trend
                     needs 2+ weeks". A trend is never fabricated.

HONESTY. Coverage is stated on every render ("1 of 10 rosters known").
A league where only my own roster is known renders MY column, the needs
row for it, the constructs, and a plain call to action - nothing about an
unknown team is invented, no empty column stands in for one, and the
snapshot carries only the teams it can see.

WRITE DISCIPLINE. This module writes exactly two things: the html it was
asked for (atomic tmp+replace) and, once per league-week, the needs
snapshot above (exclusive create - an existing file is left byte for byte
as it was). It never advances the %owned baseline (engine.waivers'
momentum component is not read at all), never records a ledger vote, and
never touches saves/, data/rosters/, leagues/ or data/sources.yaml. The
feed caches it reads (FantasyCalc, ESPN kona, nflverse, Sleeper) belong to
the modules that own them and follow their own freshness rules.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from engine import leagueview, trades, ui, waivers, weekly
    from engine.exposure import Exposure
    from engine.grader import best_lineup
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, load_players,
                               missing_rankings_message, repo_path)
except ImportError:  # run directly as `python engine/tradedesk.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import leagueview, trades, ui, waivers, weekly
    from engine.exposure import Exposure
    from engine.grader import best_lineup
    from engine.ingest import Matcher
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, load_players,
                               missing_rankings_message, repo_path)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
LEAGUE_DIR = os.path.join(HERE, "leagues")

POSITIONS: Tuple[str, ...] = tuple(trades.MARKET_POSITIONS)   # QB RB WR TE
SNAPSHOT_STEM = "league-needs"
TREND_MIN_WEEKS = 2
TREND_NOTE = "trend needs 2+ weeks"
CTA = ("paste the league rosters in Model Settings → League rosters to "
       "light this up")
WAIVER_TOP = 8

_ROW_ORDER = ("QB", "RB", "WR", "TE", "FLEX", "K", "DST")
_POS_ORDER = ("QB", "RB", "WR", "TE", "K", "DEF", "DST")
_LEAGUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Arrows and the delta glyph are literal characters, never named entities:
# the page stays parseable as XML, which is what makes the escaping check in
# the test suite meaningful.
_UP, _DOWN, _TO, _MINUS = "↑", "↓", "→", "−"


# --- depth: startable net -> a five-segment meter ----------------------------
# positional_net is "startable bodies minus starting demand". Clamped to
# -2..+2 it maps onto the meter's five levels; the meter's own tone rule
# then does the reading - gold for depth a rival can spare, ink for exactly
# covered, dim for a hole. The matchup vocabulary (SMASH/AVOID) is hidden:
# label=False, and the title says "depth", never "matchup".

_DEPTH_GRADE = {2: "smash", 1: "good", 0: "neutral", -1: "tough", -2: "avoid"}


def _clamp_net(net) -> int:
    try:
        n = int(round(float(net)))
    except (TypeError, ValueError):
        n = 0
    return max(-2, min(2, n))


def depth_level(net) -> int:
    """1..5 from a startable net (-2 or worse .. +2 or better)."""
    return _clamp_net(net) + 3


def depth_grade(net) -> str:
    """The matchup_meter grade word that draws depth_level(net) segments."""
    return _DEPTH_GRADE[_clamp_net(net)]


def depth_title(pos: str, net) -> str:
    try:
        n = int(round(float(net)))
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        why = "+%d startable %s beyond starting demand" % (n, pos)
    elif n < 0:
        why = "%d %s short of starting demand" % (-n, pos)
    else:
        why = "starting demand at %s exactly covered" % pos
    return "%s depth %d/5 — %s" % (pos, depth_level(net), why)


def depth_meter(pos: str, net, size: str = "sm") -> str:
    return ui.matchup_meter(depth_grade(net), label=False,
                            title=depth_title(pos, net), size=size)


def fmt_net(net) -> str:
    try:
        n = int(round(float(net)))
    except (TypeError, ValueError):
        return "—"
    if n < 0:
        return "%s%d" % (_MINUS, -n)
    return "+%d" % n if n > 0 else "0"


# --- snapshots: one file per league-week, never rewritten --------------------

def snapshot_path(league_id: str, week, cache_dir: Optional[str] = None) -> str:
    """data/cache/league-needs-<league>-week<N>.json - and nowhere else.

    The league id is validated against a strict pattern so a path separator
    or a dot-dot can never steer the write out of the cache directory, and
    the resolved path is checked to sit under it anyway.
    """
    lid = str(league_id or "").strip()
    if not _LEAGUE_ID.match(lid):
        raise ValueError("league id %r is not a plain identifier" % league_id)
    wk = int(week)
    if wk < 1:
        raise ValueError("week must be >= 1 (got %r)" % week)
    root = os.path.abspath(cache_dir or CACHE_DIR)
    path = os.path.abspath(os.path.join(
        root, "%s-%s-week%d.json" % (SNAPSHOT_STEM, lid, wk)))
    if os.path.dirname(path) != root:
        raise ValueError("snapshot path escaped the cache dir: %s" % path)
    return path


def snapshot_doc(league_id: str, week, season, teams: Sequence[Dict],
                 coverage: Tuple[int, int],
                 positions: Sequence[str] = POSITIONS,
                 stamp: Optional[str] = None) -> Dict:
    """The per-week record: each known team's startable net and its tags.

    `teams` are the grid entries build_desk() assembles (slot, name, mine,
    known, net, surplus, holes). Only what the render could actually see
    goes in - an unknown roster has no entry, and coverage says how many
    are missing.
    """
    out_teams = {}
    for t in teams:
        out_teams[str(t["slot"])] = {
            "name": str(t.get("name") or ""),
            "mine": bool(t.get("mine")),
            "known": int(t.get("known") or 0),
            "net": dict((pos, int(t.get("net", {}).get(pos, 0)))
                        for pos in positions),
            "surplus": [[pos, int(n)] for pos, n in (t.get("surplus") or [])],
            "holes": [[pos, int(n)] for pos, n in (t.get("holes") or [])],
        }
    return {
        "league": str(league_id), "week": int(week), "season": int(season),
        "written": stamp or datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "coverage": {"known": int(coverage[0]), "expected": int(coverage[1])},
        "positions": list(positions),
        "teams": out_teams,
    }


def write_snapshot_if_absent(doc: Dict, cache_dir: Optional[str] = None
                             ) -> Tuple[str, bool]:
    """(path, written). An existing week's file is never touched.

    The new file is staged to a temp name and LINKED into place: os.link
    refuses to clobber, so two renders racing for the same week cannot
    overwrite each other, and a crash mid-write leaves no half-file under
    the real name. Filesystems without hard links fall back to a
    replace that is still gated on the file not existing.
    """
    path = snapshot_path(doc["league"], doc["week"], cache_dir)
    if os.path.exists(path):
        return path, False
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    written = False
    try:
        try:
            os.link(tmp, path)
            written = True
        except FileExistsError:
            written = False
        except OSError:
            if not os.path.exists(path):
                os.replace(tmp, path)
                written = True
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path, written


def load_snapshots(league_id: str, cache_dir: Optional[str] = None
                   ) -> Tuple[List[Dict], List[str]]:
    """(docs sorted by week, notes about files that could not be read).

    A malformed file is reported and skipped - never rewritten, never
    silently dropped, because a missing week would read as "nothing
    changed" in the trend below.
    """
    lid = str(league_id or "").strip()
    if not _LEAGUE_ID.match(lid):
        return [], ["league id %r is not a plain identifier" % league_id]
    root = os.path.abspath(cache_dir or CACHE_DIR)
    pattern = os.path.join(root, "%s-%s-week*.json" % (SNAPSHOT_STEM, lid))
    docs, bad = [], []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        m = re.search(r"-week(\d+)\.json$", base)
        if not m:
            continue
        week = int(m.group(1))
        try:
            with open(path, "r") as fh:
                doc = json.load(fh)
        except (ValueError, IOError, OSError) as exc:
            bad.append("%s could not be read (%s) - delete it by hand to "
                       "retake that week" % (base, type(exc).__name__))
            continue
        if (not isinstance(doc, dict) or str(doc.get("league")) != lid
                or not isinstance(doc.get("teams"), dict)):
            bad.append("%s is not a needs snapshot for %s - skipped"
                       % (base, lid))
            continue
        try:
            if int(doc.get("week")) != week:
                bad.append("%s says week %s inside - skipped"
                           % (base, doc.get("week")))
                continue
        except (TypeError, ValueError):
            bad.append("%s carries no week - skipped" % base)
            continue
        docs.append(doc)
    docs.sort(key=lambda d: int(d["week"]))
    return docs, bad


def _slot_key(slot) -> Tuple[int, int, str]:
    try:
        return (0, int(str(slot)), "")
    except (TypeError, ValueError):
        return (1, 0, str(slot))


def trend_rows(snaps: Sequence[Dict],
               positions: Optional[Sequence[str]] = None) -> Dict:
    """Week-over-week movement per team and position - pure.

    {"weeks": [..], "enough": bool, "rows": [{slot, name, mine, cells:
    {pos: {series, first, last, delta, dir, since, label}}}]}. `dir` is
    "up" when the NEED rose (fewer startable bodies against demand),
    "down" when it eased, "flat" when unchanged, None when the team is
    known for fewer than two weeks. With fewer than TREND_MIN_WEEKS
    snapshots `enough` is False and no row carries a direction.
    """
    # Sorted here, not trusted from the caller: a newest-first list would
    # read every delta backwards, and "since wk N" would name the wrong week.
    snaps = sorted((s for s in (snaps or [])
                    if isinstance(s, dict) and s.get("week") is not None),
                   key=lambda s: int(s["week"]))
    weeks = [int(s["week"]) for s in snaps]
    if not snaps:
        return {"weeks": [], "enough": False, "rows": []}
    pos_list = list(positions or snaps[-1].get("positions") or POSITIONS)
    latest = snaps[-1].get("teams") or {}
    order = sorted(latest, key=lambda s: (0 if latest[s].get("mine") else 1,
                                          _slot_key(s)))
    enough = len(snaps) >= TREND_MIN_WEEKS
    rows = []
    for slot in order:
        entry = latest[slot]
        cells = {}
        for pos in pos_list:
            series, present = [], []
            for s in snaps:
                t = (s.get("teams") or {}).get(slot)
                net = None
                if isinstance(t, dict):
                    net = (t.get("net") or {}).get(pos)
                    try:
                        net = int(net) if net is not None else None
                    except (TypeError, ValueError):
                        net = None
                series.append(net)
                if net is not None:
                    present.append(int(s["week"]))
            vals = [v for v in series if v is not None]
            cell = {"series": series, "first": None, "last": None,
                    "delta": None, "dir": None, "since": None, "label": ""}
            if enough and len(vals) >= 2:
                first, last = vals[0], vals[-1]
                delta = last - first
                cell.update({"first": first, "last": last, "delta": delta,
                             "since": present[0]})
                if delta < 0:
                    cell["dir"] = "up"
                    cell["label"] = "%s need %s since wk %d" % (pos, _UP,
                                                                present[0])
                elif delta > 0:
                    cell["dir"] = "down"
                    cell["label"] = "%s need %s since wk %d" % (pos, _DOWN,
                                                                present[0])
                else:
                    cell["dir"] = "flat"
                    cell["label"] = "%s steady since wk %d" % (pos,
                                                               present[0])
            elif vals:
                cell["last"] = vals[-1]
                cell["label"] = ("%s known %d week - %s"
                                 % (pos, len(vals), TREND_NOTE))
            cells[pos] = cell
        rows.append({"slot": slot, "name": entry.get("name") or "",
                     "mine": bool(entry.get("mine")), "cells": cells})
    return {"weeks": weeks, "enough": enough, "rows": rows}


# --- lineup rows for the grid ------------------------------------------------

def _slot_label(slot: str) -> str:
    s = str(slot or "").strip().upper()
    if s in FLEX_ELIGIBLE:
        return "FLEX"
    return ui.normalize_pos(s)


def _pos_rank(pos: str) -> int:
    p = ui.normalize_pos(pos)
    try:
        return _POS_ORDER.index(p)
    except ValueError:
        return len(_POS_ORDER)


def lineup_rows(league: LeagueConfig, players: Sequence) -> Tuple[List, List, float]:
    """(starters, bench, lineup_pts): starters as [(slot label, Player or
    None)] in the canonical QB/RB/WR/TE/FLEX/K/DST order, bench sorted by
    position then rank. grader.best_lineup does the filling."""
    rows, total, _missing = best_lineup(league, list(players))
    labels = [_slot_label(s) for s, _ in rows]

    def _order(i):
        try:
            return (_ROW_ORDER.index(labels[i]), i)
        except ValueError:
            return (len(_ROW_ORDER), i)

    idx = sorted(range(len(rows)), key=_order)
    starters = [(labels[i], rows[i][1]) for i in idx]
    used = set(id(p) for _, p in rows if p is not None)
    bench = sorted((p for p in players if id(p) not in used),
                   key=lambda p: (_pos_rank(p.pos),
                                  float(getattr(p, "rank", 0) or 0)))
    return starters, bench, float(total)


# --- gathering (impure; every feed injectable and guarded) -------------------

def _one_line(text, limit: int = 160) -> str:
    return ui.trim(str(text).splitlines()[0] if str(text) else "", limit)


def _err(exc: BaseException) -> str:
    return "%s: %s" % (type(exc).__name__,
                       _one_line(str(exc).strip() or type(exc).__name__))


def _feed(feeds: Optional[Dict], key: str, fn):
    """A test-injected feed when present, else the real read."""
    if feeds and key in feeds:
        return feeds[key]
    return fn()


def _cell(player, exposure, target_keys: Dict[str, str],
          offer_keys: set) -> Dict:
    also = []
    if exposure is not None and getattr(exposure, "available", False):
        try:
            also = list(exposure.flag(player.key))
        except Exception:  # noqa: BLE001 - a mark is decoration
            also = []
    return {"key": player.key, "name": player.name, "pos": player.pos,
            "team": player.team or "",
            "proj": (float(player.proj_points)
                     if player.proj_points else None),
            "also": also, "target": target_keys.get(player.key, ""),
            "offer": player.key in offer_keys}


def _team_entry(league: LeagueConfig, team, source: str, exposure,
                target_keys: Dict[str, str], offer_keys: set) -> Dict:
    starters, bench, total = lineup_rows(league, team.players)
    return {
        "slot": str(team.slot), "name": team.name, "mine": bool(team.is_me),
        "source": source, "known": len(team.players),
        "unresolved": list(team.unresolved or []),
        "net": dict(team.net or {}), "surplus": list(team.surplus or []),
        "holes": list(team.holes or []), "lineup_pts": total,
        "starters": [{"slot": lbl,
                      "player": (_cell(p, exposure, target_keys, offer_keys)
                                 if p is not None else None)}
                     for lbl, p in starters],
        "bench": [_cell(p, exposure, target_keys, offer_keys) for p in bench],
    }


def _market_age_note(league: LeagueConfig) -> str:
    try:
        path = trades.cache_path(trades.ppr_param(league),
                                 trades.num_qbs_param(league))
        if os.path.exists(path):
            import time
            hours = (time.time() - os.path.getmtime(path)) / 3600.0
            return ("FantasyCalc market values cached %.1fh ago" % hours
                    if hours < 48 else
                    "FantasyCalc market values cached %.0f days ago"
                    % (hours / 24.0))
    except Exception:  # noqa: BLE001 - a note, never a failure
        pass
    return "FantasyCalc market values"


def build_desk(league_id: str, week, force: bool = False,
               roster_dir: Optional[str] = None,
               data_root: Optional[str] = None,
               cache_dir: Optional[str] = None,
               feeds: Optional[Dict] = None,
               write_snapshot: bool = True) -> Dict:
    """Everything the page needs, as plain data. Sections degrade in place.

    `feeds` lets a test inject {"market", "ros_map", "xfp", "trending"}
    so nothing here has to touch the network; production reads each one
    through the module that owns it. The needs snapshot is written (once)
    to `cache_dir` (default data/cache) unless write_snapshot is False.
    """
    week = int(week)
    league_path = os.path.join(data_root or HERE, "leagues",
                               "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    csv_path = os.path.join(data_root or HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        raise SystemExit(missing_rankings_message(league, csv_path))
    players = load_players(csv_path)
    matcher = Matcher(players)
    scoring = league.scoring_label()
    waiver_mode = getattr(league, "waiver_mode", "faab")

    desk: Dict = {
        "league": {"id": league.id, "name": league.name, "week": week,
                   "teams_expected": int(league.teams or 0),
                   "waiver_mode": waiver_mode, "scoring": scoring,
                   "my_slot": league.my_slot, "platform": league.platform},
        "leagues": [], "errors": {}, "notes": [],
        "positions": list(POSITIONS),
        "stamp": datetime.now().astimezone().strftime(
            "%a %Y-%m-%d %I:%M %p %Z"),
    }
    try:
        desk["leagues"] = [(c.id, c.name)
                           for c in leagueview.list_configs(data_root)]
    except Exception:  # noqa: BLE001 - the switcher is navigation
        desk["leagues"] = [(league.id, league.name)]

    # -- my roster + every roster the league view can hand over ------------
    roster, known, size, unresolved = trades.load_my_roster(
        league, matcher, players, dirpath=roster_dir)
    my_keys = set(p.key for p in roster)
    desk["roster"] = {"known": known, "size": size,
                      "unresolved": list(unresolved)}

    # ONE read of engine/leagueview.py (honouring data_root) feeds both the
    # coverage line and trades.load_rival_view, through the same
    # {slot: {name, players, mine}} mapping trades' own default loader
    # builds - the shape logic stays in trades.py, and a test's tempdir
    # root can never be bypassed for the production store.
    lv, lv_err = None, None
    sources = {}
    coverage = {"known": 0, "expected": int(league.teams or 0),
                "text": "league rosters not read", "complete": False,
                "banner": "", "notes": []}
    try:
        lv = leagueview.load_league_view(league, matcher, data_root=data_root)
        sources = dict((t.slot, t.source_label) for t in lv.teams)
        coverage = {"known": lv.known_teams, "expected": lv.expected_teams,
                    "text": lv.coverage_text(), "complete": lv.complete(),
                    "banner": lv.banner_text(), "notes": list(lv.notes)}
    except Exception as exc:  # noqa: BLE001 - coverage then says so
        lv_err = exc
        desk["errors"]["coverage"] = _err(exc)
        coverage["text"] = "league rosters not read (%s)" % _err(exc)
    desk["coverage"] = coverage

    def _loader(_lid):
        if lv is None:
            raise RuntimeError("engine/leagueview.py could not read the "
                               "league (%s)" % _err(lv_err))
        teams_map = {}
        for t in lv.teams:
            teams_map[str(t.slot)] = {"name": t.name,
                                      "players": list(t.players),
                                      "mine": bool(t.mine)}
        return teams_map, lv.coverage_text()

    view = trades.load_rival_view(league, matcher, players, my_keys=my_keys,
                                  loader=_loader)
    if view.me is not None:
        have = set(p.key for p in roster)
        extra = [p for p in view.me.players if p.key not in have]
        if extra:
            roster = sorted(roster + extra, key=lambda p: p.rank)
            known = len(roster)
            desk["roster"]["known"] = known
    desk["rivals_available"] = bool(view.available)
    desk["rival_reason"] = view.reason

    try:
        repl = trades.replacement_from_pool(league, players)
    except Exception as exc:  # noqa: BLE001
        repl = None
        desk["errors"]["shape"] = _err(exc)

    teams = []
    if view.me is not None:
        teams.append(view.me)
    elif roster:
        me = trades.RivalTeam(str(league.my_slot or "?"), league.name)
        me.players = list(roster)
        me.is_me = True
        teams.append(me)
        sources.setdefault(me.slot, "my roster file")
    teams += list(view.teams)
    if repl is not None:
        for t in teams:
            try:
                trades.shape_team(league, t, repl)
            except Exception as exc:  # noqa: BLE001 - one bad team, one note
                desk["notes"].append("shape read unavailable for %s (%s)"
                                     % (t.name, _err(exc)))

    try:
        exposure = Exposure.load(matcher, exclude_league_id=league.id,
                                 dirpath=roster_dir)
    except Exception as exc:  # noqa: BLE001 - marks are decoration
        exposure = None
        desk["errors"]["exposure"] = _err(exc)
    desk["exposure"] = {
        "available": bool(exposure is not None and exposure.available),
        "coverage": list(exposure.coverage()) if exposure is not None
        and exposure.available else [],
        "banner": exposure.banner_text() if exposure is not None
        and exposure.available else "",
    }

    # -- trade targets (needs the market; guarded) ------------------------
    targets, constructs = [], []
    desk["market_note"] = ""
    try:
        def _market():
            raw = trades.fetch_fantasycalc(trades.ppr_param(league),
                                           trades.num_qbs_param(league),
                                           quiet=True)
            return trades.market_values(players, trades.parse_rows(raw),
                                        matcher)
        market = _feed(feeds, "market", _market)
        projv = trades.proj_scale_values(league, players, market)
        if view.available and repl is not None:
            targets = trades.rival_targets(league, players, roster, view,
                                           market, projv, repl=repl)
        desk["market_note"] = (feeds or {}).get(
            "market_note") or _market_age_note(league)
    except Exception as exc:  # noqa: BLE001 - the card carries the error
        desk["errors"]["targets"] = _err(exc)
    try:
        constructs = trades.suggest_constructs(league, roster, known, size)
    except Exception as exc:  # noqa: BLE001
        desk["notes"].append("constructs unavailable (%s)" % _err(exc))
    desk["constructs"] = list(constructs)
    desk["targets"] = [_target_entry(t, league) for t in targets]

    target_keys = dict((t.get.key, t.team.name) for t in targets)
    offer_keys = set(t.give.key for t in targets)
    desk["teams"] = [_team_entry(league, t, sources.get(str(t.slot),
                                                        "my roster file"
                                                        if t.is_me else ""),
                                 exposure, target_keys, offer_keys)
                     for t in teams]
    desk["slots"] = ([s["slot"] for s in desk["teams"][0]["starters"]]
                     if desk["teams"] else [])
    desk["bench_rows"] = max([len(t["bench"]) for t in desk["teams"]] or [0])

    # -- waiver competition (guarded) -------------------------------------
    desk["waivers"] = _gather_waivers(league, players, roster, view, repl,
                                      week, scoring, waiver_mode, force,
                                      feeds, desk)

    # -- needs over time --------------------------------------------------
    desk["trend"] = _gather_trend(league, week, desk, cache_dir,
                                  write_snapshot and repl is not None)
    return desk


def _target_entry(t, league: LeagueConfig) -> Dict:
    if t.accept_label == "they likely decline":
        flag = "decline"
    elif t.lopsided:
        flag = "lopsided"
    elif t.overpay:
        flag = "overpay"
    else:
        flag = ""
    return {
        "team": t.team.name, "slot": str(t.team.slot),
        "shape": t.team.shape_label(),
        "give": {"name": t.give.name, "pos": t.give.pos,
                 "team": t.give.team or "", "key": t.give.key},
        "get": {"name": t.get.name, "pos": t.get.pos,
                "team": t.get.team or "", "key": t.get.key},
        "give_market": t.give_market, "get_market": t.get_market,
        "give_proj": t.give_proj, "get_proj": t.get_proj,
        "market_pct": t.market_pct, "proj_pct": t.proj_pct,
        "blended_pct": t.blended_pct,
        "my_delta_wk": t.my_delta_wk, "their_delta_wk": t.their_delta_wk,
        "flag": flag, "note": t.lopsided_note, "rationale": t.rationale,
        "accept_odds": t.accept_odds, "systems_disagree": bool(
            t.systems_disagree),
        "command": 'python -m engine.trades --league %s --offer "give: %s | '
                   'get: %s"' % (league.id, t.give.name, t.get.name),
    }


def _gather_waivers(league, players, roster, view, repl, week, scoring,
                    waiver_mode, force, feeds, desk) -> Dict:
    out = {"rows": [], "err": "", "mode": waiver_mode, "pool": 0,
           "excluded": 0, "streamers": 0, "available": bool(view.available),
           "notes": []}
    if not view.available:
        return out
    try:
        my_keys = set(p.key for p in roster)
        rival_keys = view.rostered_keys()
        pool = [p for p in players
                if p.key not in my_keys and p.key not in rival_keys]
        out["pool"], out["excluded"] = len(pool), len(rival_keys)
        ros_map = _feed(feeds, "ros_map",
                        lambda: waivers.build_ros_map(players, week, scoring,
                                                      force=force))
        baselines = waivers.starter_baselines(league, roster, ros_map,
                                              players)
        xfp_map, xfp_label = _feed(feeds, "xfp",
                                   lambda: waivers.fetch_xfp_signal(
                                       force=force))
        trending = _feed(feeds, "trending",
                         lambda: waivers.fetch_trending_adds(force=force))
        ranked = waivers.score_pool(pool, ros_map, baselines, xfp_map,
                                    trending, xfp_label=xfp_label)
        comp = waivers.waiver_competition(league, view, pool, ros_map,
                                          players, repl=repl)
        waivers.apply_competition(ranked, comp)
        if waiver_mode == "priority":
            waivers.priority_guidance(ranked)
            waivers.priority_competition(ranked, comp)
        if xfp_label:
            out["notes"].append("xFP regression uses %s data - %d weeks not "
                                "filed yet" % (xfp_label, weekly.SEASON))
        # Structural need (positional_net) is defined at QB/RB/WR/TE only;
        # a K/DST streamer's stack could only ever say "no rival shows a
        # need", which is a hole in the vocabulary, not a read. They stay
        # on the board's shortlist and the count is stated below.
        skill = [c for c in ranked if c.player.pos in POSITIONS]
        out["streamers"] = len(ranked) - len(skill)
        for c in skill[:WAIVER_TOP]:
            read = comp.get(c.player.key)
            out["rows"].append({
                "name": c.player.name, "pos": c.player.pos,
                "team": c.player.team or "", "score": c.score,
                "faab": c.faab, "burn": c.burn, "burn_detail": c.burn_detail,
                "rivals": [
                    {"name": n,
                     "short": n in (read.structural if read else []),
                     "start": n in (read.upgrade if read else [])}
                    for n in (read.teams if read else [])],
                "comp_detail": c.comp_detail, "comp_factor": c.comp_factor,
            })
    except Exception as exc:  # noqa: BLE001 - the card carries the error
        out["err"] = _err(exc)
    return out


def _gather_trend(league, week, desk, cache_dir, do_write) -> Dict:
    trend = {"weeks": [], "enough": False, "rows": [], "bad": [],
             "snapshot": {"path": "", "written": False, "skipped": ""},
             "written_stamps": {}, "err": ""}
    try:
        season = int(getattr(weekly, "SEASON", 0) or 0)
        if do_write and desk["teams"]:
            doc = snapshot_doc(league.id, week, season, desk["teams"],
                               (desk["coverage"]["known"],
                                desk["coverage"]["expected"]))
            path, written = write_snapshot_if_absent(doc, cache_dir)
            trend["snapshot"] = {"path": path, "written": written,
                                 "skipped": ""}
        elif not desk["teams"]:
            trend["snapshot"]["skipped"] = ("no roster is known, so no needs "
                                            "snapshot was taken")
        else:
            trend["snapshot"]["skipped"] = ("the shape read failed, so no "
                                            "needs snapshot was taken")
        snaps, bad = load_snapshots(league.id, cache_dir)
        trend.update(trend_rows(snaps, POSITIONS))
        trend["bad"] = bad
        trend["written_stamps"] = dict((int(s["week"]),
                                        str(s.get("written") or ""))
                                       for s in snaps)
    except Exception as exc:  # noqa: BLE001
        trend["err"] = _err(exc)
    return trend


# --- rendering (pure over the desk dict) -------------------------------------

def _card(title, body: str, count_note=None, notes: Sequence = (),
          id_: str = "") -> str:
    return ('<section class="wr-card td-sec"%s>%s%s</section>'
            % (' id="%s"' % ui.esc(id_) if id_ else "",
               ui.section_header(title, count_note, notes), body))


def _tag(label: str, weight: str, title: Optional[str] = None) -> str:
    return ('<span class="td-tag td-tag-%s"%s>%s</span>'
            % (ui.esc(weight),
               ' title="%s"' % ui.esc(title) if title else "",
               ui.esc(label)))


def shape_tags(entry: Dict) -> str:
    tags = [_tag("surplus %s %s" % (fmt_net(n), pos), "solid",
                 "+%d startable %s beyond starting demand" % (n, pos))
            for pos, n in entry.get("surplus") or []]
    tags += [_tag("hole %s %s" % (fmt_net(-n), pos), "dash",
                  "%d %s short of starting demand" % (n, pos))
             for pos, n in entry.get("holes") or []]
    if not tags:
        tags.append(_tag("no surplus, no hole", "ghost",
                         "startable bodies exactly cover starting demand"))
    return '<div class="td-tags">%s</div>' % "".join(tags)


def _player_cell(cell: Optional[Dict], slot: str = "") -> str:
    if cell is None:
        return ('<div class="td-cell td-open">%s<span class="td-name">'
                'no known player</span></div>'
                % (ui.pos_badge(slot) if slot and slot != "FLEX" else
                   '<span class="wr-pos wr-pos-wide">FLEX</span>'))
    marks = []
    if cell.get("target"):
        marks.append('<span class="td-mark td-mark-tgt" title="%s">target'
                     '</span>' % ui.esc("a proposal below asks %s for him"
                                        % cell["target"]))
    if cell.get("offer"):
        marks.append('<span class="td-mark td-mark-offer" title="a proposal '
                     'below gives him">offer</span>')
    if cell.get("also"):
        marks.append('<span class="td-mark td-mark-mine" title="%s">also '
                     'yours</span>'
                     % ui.esc("you also hold him in %s"
                              % ", ".join(cell["also"])))
    proj = cell.get("proj")
    meta = [ui.esc(cell.get("team") or "")]
    if proj:
        meta.append('<span class="wr-num">%d</span>' % int(round(proj)))
    return ('<div class="td-cell">%s<span class="td-name">%s</span>'
            '<span class="td-meta">%s</span>%s</div>'
            % (ui.pos_badge(cell.get("pos")), ui.esc(cell.get("name")),
               " · ".join(m for m in meta if m),
               ('<span class="td-marks">%s</span>' % "".join(marks))
               if marks else ""))


def render_grid(desk: Dict) -> str:
    teams = desk.get("teams") or []
    cov = desk.get("coverage") or {}
    lg = desk["league"]
    notes = []
    banners = []
    if not cov.get("complete"):
        banners.append(ui.banner(
            "%s. %s (./sources.sh)." % (cov.get("text", "coverage unknown"),
                                         CTA), tone="warn"))
    if desk.get("errors", {}).get("coverage"):
        notes.append("league rosters could not be read: %s"
                     % desk["errors"]["coverage"])
    for n in cov.get("notes") or []:
        notes.append(n)
    exp = desk.get("exposure") or {}
    if exp.get("available"):
        notes.append("ALSO YOURS marks a player you also hold in %s. %s"
                     % ("; ".join("%s (%d/%d known)" % c
                                  for c in exp["coverage"]),
                        exp.get("banner") or ""))
    else:
        notes.append("no other league roster on file - ALSO YOURS marks are "
                     "unavailable, not empty.")
    notes.append("SURPLUS / HOLE tags are startable bodies against this "
                 "league's starting demand (engine/trades.py positional_net): "
                 "what a team can spare and what it is short of. Positive-"
                 "only: a player on no column here is UNKNOWN, not a free "
                 "agent.")
    if not teams:
        body = "".join(banners) + (
            '<p class="wr-note">no roster in this league is known, so there '
            'is no column to draw. %s.</p>' % ui.esc(CTA))
        return _card("League grid", body, None, notes, id_="grid")

    head = ['<th class="wr-sticky">slot</th>']
    for t in teams:
        cls = " td-me" if t.get("mine") else ""
        sub = "slot %s · %s" % (t["slot"], t.get("source") or "")
        head.append(
            '<th class="td-th%s" scope="col"><span class="td-th-name">%s%s'
            '</span><span class="td-th-sub">%s · <span class="wr-num">'
            '%d</span> known</span>%s</th>'
            % (cls, ui.esc(t["name"]),
               ' <span class="td-you">you</span>' if t.get("mine") else "",
               ui.esc(sub), int(t.get("known") or 0), shape_tags(t)))
    rows = ['<tr class="td-group"><td colspan="%d">starters</td></tr>'
            % (len(teams) + 1)]
    slots = desk.get("slots") or []
    for i, slot in enumerate(slots):
        cells = []
        for t in teams:
            st = t["starters"][i] if i < len(t["starters"]) else None
            # data-l is the cell's own column name, so the stacked phone
            # layout below can label it once the header row is a list.
            cells.append('<td%s data-l="%s">%s</td>'
                         % (' class="td-me"' if t.get("mine") else "",
                            ui.esc(t["name"]),
                            _player_cell(st["player"] if st else None, slot)))
        rows.append('<tr><td class="wr-sticky">%s</td>%s</tr>'
                    % (ui.esc(slot), "".join(cells)))
    bench_n = int(desk.get("bench_rows") or 0)
    if bench_n:
        rows.append('<tr class="td-group"><td colspan="%d">bench</td></tr>'
                    % (len(teams) + 1))
    for i in range(bench_n):
        cells = []
        for t in teams:
            b = t["bench"][i] if i < len(t["bench"]) else None
            cells.append('<td%s data-l="%s">%s</td>'
                         % (' class="td-me"' if t.get("mine") else "",
                            ui.esc(t["name"]),
                            _player_cell(b) if b is not None else
                            '<div class="td-cell td-open"><span class="td-name">'
                            '—</span></div>'))
        rows.append('<tr><td class="wr-sticky">bn %d</td>%s</tr>'
                    % (i + 1, "".join(cells)))
    table = ('<div class="wr-scroll"><table class="wr-table td-grid">'
             '<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
             % ("".join(head), "".join(rows)))
    unres = [(t["name"], t["unresolved"]) for t in teams if t["unresolved"]]
    for name, names in unres:
        notes.append("%s: %d roster name(s) the rankings pool could not "
                     "place, shown nowhere rather than guessed: %s"
                     % (name, len(names), ", ".join(names)))
    count = "%d of %d rosters" % (len(teams), lg.get("teams_expected") or 0)
    return _card("League grid", "".join(banners) + table, count, notes,
                 id_="grid")


def render_needs(desk: Dict) -> str:
    teams = desk.get("teams") or []
    positions = desk.get("positions") or list(POSITIONS)
    notes = ["one meter per cell: five segments = two or more startable "
             "bodies to spare, three = starting demand exactly covered, one "
             "= two or more short. Gold is depth a team can spare; dim is a "
             "hole. Read across for a team's shape, down for who is starved "
             "at a position."]
    if desk.get("errors", {}).get("shape"):
        body = ui.degraded_banner("Needs matrix", desk["errors"]["shape"])
        return _card("Needs matrix", body, None, notes, id_="needs")
    if not teams:
        return _card("Needs matrix",
                     '<p class="wr-note">no roster is known, so there is no '
                     'row to draw. %s.</p>' % ui.esc(CTA), None, notes,
                     id_="needs")
    head = ['<th class="wr-sticky">team</th>']
    head += ['<th scope="col">%s</th>' % ui.esc(pos) for pos in positions]
    rows = []
    short = dict((pos, 0) for pos in positions)
    spare = dict((pos, 0) for pos in positions)
    for t in teams:
        cells = []
        for pos in positions:
            net = (t.get("net") or {}).get(pos, 0)
            if net < 0:
                short[pos] += 1
            elif net > 0:
                spare[pos] += 1
            # data-l is the column name, shown as an inline label once the
            # table stacks into cards at phone width (audit rule 11).
            cells.append('<td class="td-nm" data-l="%s">'
                         '<span class="td-nm-in">%s'
                         '<span class="wr-num td-net">%s</span></span></td>'
                         % (ui.esc(pos), depth_meter(pos, net), fmt_net(net)))
        rows.append('<tr%s><td class="wr-sticky">%s%s</td>%s</tr>'
                    % (' class="td-me-row"' if t.get("mine") else "",
                       ui.esc(t["name"]),
                       ' <span class="td-you">you</span>' if t.get("mine")
                       else "", "".join(cells)))
    foot = ['<td class="wr-sticky">down the column</td>']
    for pos in positions:
        bits = []
        if short[pos]:
            bits.append("%d short" % short[pos])
        if spare[pos]:
            bits.append("%d can spare" % spare[pos])
        foot.append('<td data-l="%s">%s</td>'
                    % (ui.esc(pos), ui.esc(", ".join(bits) or "all covered")))
    table = ('<div class="wr-scroll"><table class="wr-table td-needs">'
             '<thead><tr>%s</tr></thead><tbody>%s</tbody>'
             '<tfoot><tr>%s</tr></tfoot></table></div>'
             % ("".join(head), "".join(rows), "".join(foot)))
    cov = desk.get("coverage") or {}
    if not cov.get("complete"):
        notes.insert(0, "%s - the matrix shows the rows it can see and "
                        "nothing for the rest." % cov.get("text", ""))
    return _card("Needs matrix", table,
                 "%d team%s x %s" % (len(teams), "" if len(teams) == 1
                                     else "s", "/".join(positions)),
                 notes, id_="needs")


def _fmt_val(v) -> str:
    try:
        return format(int(round(float(v))), ",d")
    except (TypeError, ValueError):
        return "—"


def _signed(v, digits: int = 1) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    s = ("%+." + str(digits) + "f") % f
    return s.replace("-", _MINUS, 1) if s.startswith("-") else s


def _pct(v) -> str:
    try:
        return _signed(100.0 * float(v), 0) + "%"
    except (TypeError, ValueError):
        return "—"


def _side(label: str, p: Dict, market, proj) -> str:
    return ('<div class="td-side"><span class="td-side-l">%s</span>'
            '<div class="td-side-p">%s<span class="td-name">%s</span>'
            '<span class="td-meta">%s</span></div>'
            '<div class="td-vals">%s%s</div></div>'
            % (ui.esc(label), ui.pos_badge(p.get("pos")),
               ui.esc(p.get("name")), ui.esc(p.get("team") or ""),
               ui.stat_pill("market", _fmt_val(market),
                            title="FantasyCalc redraft trade value"),
               ui.stat_pill("our ROS", _fmt_val(proj),
                            title="our rest-of-season VBD, quantile-mapped "
                                  "onto the market's scale")))


def render_target_card(t: Dict, n: int) -> str:
    flag = t.get("flag") or ""
    cls = " td-offer-decline" if flag == "decline" else ""
    flag_html = ""
    if flag == "decline":
        flag_html = ('<p class="td-flag"><b>they likely decline</b> — %s'
                     '</p>' % ui.esc(t.get("note")))
    elif flag == "lopsided":
        flag_html = ('<p class="td-flag"><b>lopsided, worth asking</b> — '
                     '%s</p>' % ui.esc(t.get("note")))
    elif flag == "overpay":
        flag_html = ('<p class="td-flag"><b>we overpay</b> — %s</p>'
                     % ui.esc(t.get("note")))
    elif t.get("note"):
        flag_html = '<p class="td-why">%s</p>' % ui.esc(t.get("note"))
    if t.get("systems_disagree"):
        flag_html += ('<p class="td-flag">%s market and our projections '
                      'disagree hard on this one — that split is the '
                      'thesis</p>' % ui.icon("dissent", 20))
    odds = ""
    try:
        odds = ui.stat_pill("odds", "%d%%" % int(round(100 * float(
            t.get("accept_odds") or 0))), title="acceptance proxy from "
            "engine/trades.py - value fairness x their lineup gain")
    except (TypeError, ValueError):
        odds = ""
    return (
        '<article class="td-offer%s">'
        '<header class="td-offer-h"><span class="td-offer-n wr-num">%d</span>'
        '<span class="td-offer-to">to <b>%s</b></span>'
        '<span class="td-offer-shape">%s</span></header>'
        '<div class="td-sides">%s<span class="td-swap">%s</span>%s</div>'
        '<div class="td-impact">'
        '<span class="td-imp"><span class="td-imp-l">you</span>'
        '<span class="wr-num">%s</span> pts/wk</span>'
        '<span class="td-imp"><span class="td-imp-l">them</span>'
        '<span class="wr-num">%s</span> pts/wk</span>'
        '<span class="td-imp"><span class="td-imp-l">market</span>'
        '<span class="wr-num">%s</span></span>'
        '<span class="td-imp"><span class="td-imp-l">our ROS</span>'
        '<span class="wr-num">%s</span></span>%s</div>'
        '%s<p class="td-why">%s</p>'
        '<code class="td-cmd wr-mono">%s</code></article>'
        % (cls, n, ui.esc(t.get("team")), ui.esc(t.get("shape")),
           _side("you give", t["give"], t.get("give_market"),
                 t.get("give_proj")),
           ui.icon("trade", 20, title="for"),
           _side("you get", t["get"], t.get("get_market"), t.get("get_proj")),
           _signed(t.get("my_delta_wk")), _signed(t.get("their_delta_wk")),
           _pct(t.get("market_pct")), _pct(t.get("proj_pct")), odds,
           flag_html, ui.esc(t.get("rationale")), ui.esc(t.get("command"))))


def render_targets(desk: Dict) -> str:
    lg = desk["league"]
    targets = desk.get("targets") or []
    notes = []
    body = ""
    err = desk.get("errors", {}).get("targets")
    if err:
        body += ui.degraded_banner("Trade targets", err)
    if not desk.get("rivals_available"):
        body += ui.banner("RIVAL ROSTERS UNKNOWN — %s. No rival is named "
                          "and no offer is invented; %s (./sources.sh)."
                          % (desk.get("rival_reason") or trades.RIVALS_UNKNOWN,
                             CTA), tone="warn")
    elif not targets and not err:
        body += ui.banner("no 1-for-1 clears the bar: every offer we can "
                          "build either fails to upgrade our starting lineup "
                          "or asks a rival to lose points. The constructs "
                          "below still stand.", tone="info", ico=None)
    if targets:
        body += '<div class="td-offers">%s</div>' % "".join(
            render_target_card(t, i) for i, t in enumerate(targets, start=1))
        notes.append("ranked by our pts/wk gain times the odds the other "
                     "manager says yes; a lopsided offer is labelled, not "
                     "hidden. %s." % (desk.get("market_note") or
                                      "FantasyCalc market values"))
        notes.append("the offer evaluator stays in the CLI: each card carries "
                     "its exact command, and any other offer is "
                     'python -m engine.trades --league %s --offer "give: A | '
                     'get: B".' % lg["id"])
    constructs = desk.get("constructs") or []
    if constructs:
        body += ('<h3 class="td-h3">Constructs — shapes to shop, not '
                 'offers to named rivals</h3><ul class="td-list">%s</ul>'
                 % "".join('<li>%s</li>' % ui.esc(c) for c in constructs))
    elif not targets:
        body += ('<p class="wr-note">too little roster known to shape a '
                 'trade - capture more names in data/rosters/%s.yaml.</p>'
                 % ui.esc(lg["id"]))
    if desk.get("rivals_available"):
        notes.append(desk.get("rival_reason") or "")
    count = ("%d proposal%s" % (len(targets), "" if len(targets) == 1
                                else "s")) if targets else None
    return _card("Trade targets", body, count, [n for n in notes if n],
                 id_="targets")


def render_waivers(desk: Dict) -> str:
    lg = desk["league"]
    w = desk.get("waivers") or {}
    notes = list(w.get("notes") or [])
    body = ""
    if not w.get("available"):
        body += ui.banner("competition cannot be read: %s. %s "
                          "(./sources.sh)." % (desk.get("rival_reason")
                                               or trades.RIVALS_UNKNOWN, CTA),
                          tone="warn")
        body += ('<p class="wr-note"><a class="td-link" href="%s">the '
                 'waiver shortlist itself lives on the board →</a></p>'
                 % ui.esc("board-%s-week%d.html" % (lg["id"], lg["week"])))
        return _card("Waiver competition", body, None, notes, id_="waivers")
    if w.get("err"):
        body += ui.degraded_banner("Waiver competition", w["err"])
        return _card("Waiver competition", body, None, notes, id_="waivers")
    rows = w.get("rows") or []
    if not rows:
        body += '<p class="wr-note">no waiver candidate scored.</p>'
        return _card("Waiver competition", body, None, notes, id_="waivers")
    priority = w.get("mode") == "priority"
    head = ('<tr><th class="wr-sticky">candidate</th><th>score</th><th>%s'
            '</th><th>who else needs him</th></tr>'
            % ("burn priority?" if priority else "faab band"))
    trs = []
    for r in rows:
        stack = []
        for rv in r.get("rivals") or []:
            cls = ["td-stk"]
            why = []
            if rv.get("short"):
                cls.append("td-stk-short")
                why.append("structurally short at %s" % r["pos"])
            if rv.get("start"):
                cls.append("td-stk-start")
                why.append("he would crack their starting lineup")
            stack.append('<span class="%s" title="%s">%s</span>'
                         % (" ".join(cls), ui.esc("; ".join(why)),
                            ui.esc(rv["name"])))
        stack_html = ('<div class="td-stack">%s</div>' % "".join(stack)
                      if stack else
                      '<span class="td-none">no rival roster shows a need at '
                      '%s</span>' % ui.esc(r["pos"]))
        if priority:
            verdict = (_tag("burn", "solid", r.get("burn_detail"))
                       if r.get("burn") == "YES"
                       else _tag("hold", "ghost", r.get("burn_detail")))
        else:
            verdict = _tag(r.get("faab") or "pass", "ghost",
                           "bid band includes %.2fx rival pressure"
                           % float(r.get("comp_factor") or 1.0)
                           if float(r.get("comp_factor") or 1.0) > 1.0
                           else "bid band from score x scarcity")
        trs.append(
            '<tr><td class="wr-sticky"><div class="td-cell">%s<span '
            'class="td-name">%s</span><span class="td-meta">%s</span></div>'
            '</td><td class="wr-num" data-l="score">%.1f</td>'
            '<td data-l="%s">%s</td>'
            '<td data-l="who else needs him">%s</td></tr>'
            % (ui.pos_badge(r["pos"]), ui.esc(r["name"]),
               ui.esc(r.get("team") or ""), float(r.get("score") or 0.0),
               "burn priority?" if priority else "faab band",
               verdict, stack_html))
    body += ('<div class="wr-scroll"><table class="wr-table td-waivers">'
             '<thead>%s</thead><tbody>%s</tbody></table></div>'
             % (head, "".join(trs)))
    notes.append("a rival counts when the pickup would actually change "
                 "their team: dashed = structurally short startable bodies "
                 "at the position, solid = he would crack their starting "
                 "lineup (engine/waivers.py waiver_competition). A stack "
                 "is a read on likely bidders, never a claim about what "
                 "anyone will do.")
    notes.append("QB/RB/WR/TE only: structural need is defined at the four "
                 "skill positions (engine/trades.py positional_net); the %d "
                 "K/DST streamers scored stay on the board's shortlist "
                 "(board-%s-week%d.html)."
                 % (int(w.get("streamers") or 0), lg["id"], lg["week"]))
    notes.append("pool: %d ranked players, %d rival-rostered names excluded. "
                 "%%owned momentum is not read here - this page never "
                 "advances that baseline." % (int(w.get("pool") or 0),
                                              int(w.get("excluded") or 0)))
    if priority:
        notes.append("priority league: a claim spends queue position, not "
                     "budget. %s" % waivers.priority_position_note(
                         _league_stub(lg)))
    return _card("Waiver competition", body,
                 "top %d candidates" % len(rows), notes, id_="waivers")


class _LeagueStub(object):
    """Just enough of a LeagueConfig for priority_position_note()."""

    def __init__(self, lg: Dict):
        self.teams = int(lg.get("teams_expected") or 0)
        self.my_slot = lg.get("my_slot")


def _league_stub(lg: Dict) -> "_LeagueStub":
    return _LeagueStub(lg)


def render_trend(desk: Dict) -> str:
    lg = desk["league"]
    tr = desk.get("trend") or {}
    positions = desk.get("positions") or list(POSITIONS)
    notes = []
    body = ""
    if tr.get("err"):
        body += ui.degraded_banner("Needs over time", tr["err"])
    snap = tr.get("snapshot") or {}
    if snap.get("path"):
        rel = os.path.relpath(snap["path"], HERE) \
            if snap["path"].startswith(HERE) else snap["path"]
        notes.append("week %d snapshot %s %s" % (
            lg["week"], "written to" if snap.get("written")
            else "already on file at (left untouched)", rel))
    elif snap.get("skipped"):
        notes.append(snap["skipped"])
    for b in tr.get("bad") or []:
        notes.append(b)
    weeks = tr.get("weeks") or []
    if weeks:
        notes.append("weeks on file: %s" % ", ".join(str(w) for w in weeks))
    if not tr.get("enough"):
        body += ui.banner(
            "%s — %s. Rerun the desk next week and this card fills in "
            "with movement per team and position; nothing is extrapolated "
            "from one reading." % (TREND_NOTE,
                                   ("only week %d is on file" % weeks[0])
                                   if len(weeks) == 1 else
                                   "no needs snapshot is on file yet"),
            tone="info", ico=None)
        return _card("Needs over time", body, None, notes, id_="trend")
    rows = tr.get("rows") or []
    head = ['<th class="wr-sticky">team</th>']
    head += ['<th scope="col">%s</th>' % ui.esc(pos) for pos in positions]
    trs = []
    for r in rows:
        cells = []
        for pos in positions:
            c = (r.get("cells") or {}).get(pos) or {}
            series = [v for v in (c.get("series") or []) if v is not None]
            spark = ui.sparkline(series, width=56, height=16,
                                 title="%s startable net, wk %s: %s"
                                 % (pos, "/".join(str(w) for w in weeks),
                                    ", ".join(fmt_net(v) for v in series)))
            d = c.get("dir")
            if d is None:
                cells.append('<td><span class="td-tr td-tr-none">%s<span '
                             'class="td-tr-l">%s</span></span></td>'
                             % (spark, ui.esc(c.get("label") or TREND_NOTE)))
                continue
            cells.append(
                '<td><span class="td-tr td-tr-%s">%s<span class="td-tr-l">'
                '%s</span><span class="wr-num td-tr-n">%s %s %s</span></span>'
                '</td>' % (ui.esc(d), spark, ui.esc(c.get("label")),
                           fmt_net(c.get("first")), _TO,
                           fmt_net(c.get("last"))))
        trs.append('<tr%s><td class="wr-sticky">%s%s</td>%s</tr>'
                   % (' class="td-me-row"' if r.get("mine") else "",
                      ui.esc(r.get("name")),
                      ' <span class="td-you">you</span>' if r.get("mine")
                      else "", "".join(cells)))
    body += ('<div class="wr-scroll"><table class="wr-table td-trend">'
             '<thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
             % ("".join(head), "".join(trs)))
    notes.append("need %s = fewer startable bodies against starting demand "
                 "than the first week on file; need %s = more. The number "
                 "is the startable net then %s now; the spark is every week "
                 "between." % (_UP, _DOWN, _TO))
    return _card("Needs over time", body,
                 "%d weeks" % len(weeks), notes, id_="trend")


LEGEND = (
    ("trade", "a named 1-for-1 proposal, give for get"),
    ("dissent", "market and our projections disagree hard"),
)


def page_css() -> str:
    """Trade-desk layout on top of the design system. Tokens only."""
    return """
  .td-page .wr-card + .wr-card { margin-top: 14px; }
  .td-h3 { font-size: 12px; letter-spacing: 1.2px; text-transform: uppercase;
           color: var(--wr-muted); margin: 14px 0 6px; }
  .td-list { margin: 0; padding-left: 18px; color: var(--wr-text); }
  .td-list li { margin: 4px 0; }
  .td-lede { display: flex; flex-wrap: wrap; gap: 4px 14px;
             color: var(--wr-muted); font-size: 13px; margin: 0 0 14px; }
  .td-you { color: var(--wr-gold); font-size: 11px; letter-spacing: 0.14em;
            text-transform: uppercase; font-weight: 700; }

  /* the grid: one column per known roster ------------------------------ */
  .td-grid th, .td-grid td { min-width: 150px; vertical-align: top; }
  .td-grid th.wr-sticky, .td-grid td.wr-sticky {
    min-width: 58px; width: 58px; color: var(--wr-dim); font-size: 11px;
    letter-spacing: 0.1em; text-transform: uppercase; font-weight: 700;
    vertical-align: middle; }
  .td-grid th.td-th { text-transform: none; letter-spacing: 0;
                      vertical-align: top; }
  .td-grid th.td-me { box-shadow: inset 0 3px 0 var(--wr-rule); }
  .td-grid td.td-me { background: var(--wr-wash-split); }
  .td-th-name { display: block; font-size: 13px; color: var(--wr-text);
                font-weight: 700; overflow-wrap: anywhere; }
  .td-th-sub { display: block; font-weight: 500; color: var(--wr-dim);
               font-size: 11px; margin-top: 1px; }
  .td-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  .td-tag { display: inline-flex; align-items: center; gap: 3px;
            border-radius: 4px; padding: 1px 6px; font-size: 11px;
            font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
            border: 1px solid transparent; white-space: nowrap; line-height: 1.5; }
  .td-tag-solid { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                  border-color: var(--wr-chip-start); }
  .td-tag-dash { color: var(--wr-chip-lean); border: 1px dashed var(--wr-chip-lean);
                 background: transparent; }
  .td-tag-ghost { color: var(--wr-muted); border-color: var(--wr-chip-sit);
                  background: transparent; }
  .td-group td { background: var(--wr-raised); color: var(--wr-dim);
                 font-size: 11px; letter-spacing: 0.12em;
                 text-transform: uppercase; font-weight: 700; padding: 5px 10px; }
  .td-cell { display: flex; flex-wrap: wrap; align-items: baseline;
             gap: 2px 6px; min-width: 0; }
  .td-name { font-weight: 700; overflow-wrap: anywhere; }
  .td-meta { color: var(--wr-muted); font-size: 11.5px; }
  .td-open .td-name { color: var(--wr-dim); font-weight: 500; font-style: italic; }
  .td-marks { display: inline-flex; gap: 4px; flex-wrap: wrap; flex-basis: 100%; }
  .td-mark { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
             text-transform: uppercase; color: var(--wr-gold);
             border-radius: 3px; padding: 0 4px; border: 1px solid var(--wr-gold);
             line-height: 1.6; }
  .td-mark-tgt { background: var(--wr-chip-start); color: var(--wr-chip-ink);
                 border-color: var(--wr-chip-start); }
  .td-mark-offer { border-style: dashed; }

  /* the needs matrix ----------------------------------------------------- */
  .td-needs td, .td-needs th { text-align: center; }
  .td-needs td.wr-sticky, .td-needs th.wr-sticky { text-align: left;
                                                    font-weight: 700; }
  .td-me-row td.wr-sticky { box-shadow: inset 3px 0 0 var(--wr-rule); }
  .td-nm-in { display: inline-flex; align-items: center; gap: 7px; }
  .td-net { font-weight: 700; min-width: 2.2ch; text-align: right; }
  .td-needs tfoot td { color: var(--wr-muted); font-size: 11.5px;
                       border-bottom: none; font-style: italic; }

  /* the proposal cards --------------------------------------------------- */
  .td-offers { display: grid; gap: 12px;
               grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
  .td-offer { border: 1px solid var(--wr-hairline); border-radius: 8px;
              padding: 12px 14px; background: var(--wr-panel);
              display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .td-offer-decline { box-shadow: inset 3px 0 0 var(--wr-rule); }
  .td-offer-h { display: flex; flex-wrap: wrap; align-items: baseline;
                gap: 4px 10px; }
  .td-offer-n { color: var(--wr-gold); font-weight: 700; }
  .td-offer-shape { color: var(--wr-muted); font-size: 12px; }
  .td-sides { display: grid; gap: 8px; align-items: start;
              grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); }
  .td-side { min-width: 0; }
  .td-side-l { display: block; font-size: 11px; letter-spacing: 0.14em;
               text-transform: uppercase; color: var(--wr-dim);
               font-weight: 700; margin-bottom: 3px; }
  .td-side-p { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 6px; }
  .td-vals { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
  .td-swap { color: var(--wr-dim); align-self: center; }
  .td-impact { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12.5px;
               align-items: baseline; }
  .td-imp-l { color: var(--wr-dim); font-size: 11px; letter-spacing: 0.12em;
              text-transform: uppercase; font-weight: 700; margin-right: 5px; }
  .td-flag { margin: 0; font-size: 12px; color: var(--wr-text); }
  .td-flag b { letter-spacing: 0.08em; text-transform: uppercase;
               font-size: 11px; }
  .td-why { margin: 0; color: var(--wr-muted); font-size: 12.5px; }
  .td-cmd { display: block; font-size: 11px; color: var(--wr-muted);
            background: var(--wr-raised); border: 1px solid var(--wr-hairline);
            border-radius: 5px; padding: 6px 8px; overflow-wrap: anywhere; }

  /* the waiver stacks ---------------------------------------------------- */
  .td-waivers td { vertical-align: top; }
  .td-stack { display: flex; flex-direction: column; gap: 3px;
              align-items: flex-start; }
  .td-stk { font-size: 11.5px; font-weight: 600; padding: 1px 7px;
            border-radius: 4px; border: 1px solid var(--wr-hairline-2);
            background: var(--wr-raised); color: var(--wr-text);
            white-space: nowrap; }
  .td-stk-short { border-style: dashed; border-color: var(--wr-gold);
                  color: var(--wr-gold); }
  .td-stk-start { border-color: var(--wr-text); }
  .td-none { color: var(--wr-dim); font-size: 12px; }

  /* the trend ------------------------------------------------------------ */
  .td-trend td { vertical-align: top; }
  .td-tr { display: inline-flex; flex-direction: column; gap: 2px;
           align-items: flex-start; }
  .td-tr-l { font-size: 12px; font-weight: 600; }
  .td-tr-up .td-tr-l { color: var(--wr-gold); }
  .td-tr-none .td-tr-l { color: var(--wr-dim); font-weight: 500; }
  .td-tr-n { font-size: 11.5px; color: var(--wr-muted); }

  /* tap targets + footer ------------------------------------------------- */
  .td-link { display: inline-flex; align-items: center; min-height: 44px;
             padding: 0 4px; font-weight: 600; }
  .td-page .wr-pop > .wr-pop-s { min-height: 44px; }
  .td-foot { margin-top: 18px; color: var(--wr-muted); font-size: 12px;
             line-height: 1.5; }
  .td-foot code { font-size: 11px; }

  @media (max-width: 700px) {
    .td-sides { grid-template-columns: minmax(0, 1fr); }
    .td-swap { justify-self: start; }
    /* THE GRID STACKS - it does not narrow. Nine columns at 136px is a
       1224px floor written into the phone rule: four and a half viewports
       of sideways panning for this page's central artifact. Instead the
       team headers become a list of team blocks (name, slot, source, known
       count and shape tags all kept) and each roster slot becomes a card
       whose cells print their own team name from data-l - nothing is
       unlabelled, and nothing is off-screen. */
    .td-grid { display: block; min-width: 0; }
    .td-grid > thead, .td-grid > tbody { display: block; }
    .td-grid > thead > tr, .td-grid > tbody > tr { display: block; }
    .td-grid > thead > tr > th.wr-sticky { display: none; }
    .td-grid > thead > tr > th {
      display: block; position: static; width: auto; min-width: 0;
      box-shadow: none; padding: 9px 10px;
      border-bottom: 1px solid var(--wr-hairline);
    }
    .td-grid > thead > tr > th.td-me {
      box-shadow: inset 3px 0 0 var(--wr-rule); }
    .td-grid > tbody > tr {
      display: block; border: 1px solid var(--wr-hairline);
      border-radius: 8px; margin: 8px 0; background: var(--wr-panel);
    }
    .td-grid > tbody > tr.td-group {
      border: none; border-radius: 0; margin: 14px 0 4px;
      background: transparent;
    }
    .td-grid > tbody > tr > td {
      display: block; position: static; width: auto; min-width: 0;
      text-align: left; box-shadow: none; padding: 8px 10px;
      border-bottom: 1px solid var(--wr-hairline);
    }
    .td-grid > tbody > tr > td:last-child { border-bottom: none; }
    .td-grid > tbody > tr > td.wr-sticky {
      width: auto; min-width: 0;
      border-bottom: 1px solid var(--wr-hairline-2);
    }
    .td-grid > tbody > tr > td[data-l]::before {
      content: attr(data-l); display: block; color: var(--wr-muted);
      font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
      font-weight: 700; margin-bottom: 2px;
    }
  }

  /* MOBILE FIT (audit rule 11): a table with more than three columns
     stacks into one card per row at phone width rather than asking the
     reader to pan it sideways. Each cell shows its column name from
     data-l, so a number never loses the header that gave it meaning. */
  @media (max-width: 600px) {
    table.td-needs, table.td-waivers { display: block; min-width: 0; }
    table.td-needs thead, table.td-waivers thead { display: none; }
    table.td-needs tbody, table.td-waivers tbody,
    table.td-needs tfoot, table.td-waivers tfoot,
    table.td-needs tr, table.td-waivers tr { display: block; width: auto; }
    table.td-needs tr, table.td-waivers tr {
      border: 1px solid var(--wr-hairline); border-radius: 8px;
      padding: 8px 10px; margin: 0 0 8px; background: var(--wr-panel); }
    table.td-needs td, table.td-waivers td,
    table.td-needs th, table.td-waivers th {
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; width: auto; min-height: 34px; padding: 4px 0;
      border: none; text-align: left; position: static; }
    table.td-needs td[data-l]::before, table.td-waivers td[data-l]::before {
      content: attr(data-l); color: var(--wr-dim);
      font-size: var(--wr-t4); letter-spacing: .08em; font-weight: 700;
      text-transform: uppercase; flex: none; }
    table.td-needs td.wr-sticky, table.td-waivers td.wr-sticky {
      font-weight: 700; border-bottom: 1px solid var(--wr-hairline);
      padding-bottom: 6px; margin-bottom: 4px; }
    table.td-needs td.td-nm { justify-content: space-between; }
    table.td-needs .td-nm-in { display: inline-flex; align-items: center;
                               gap: 8px; }
  }
"""


def render_page(desk: Dict) -> str:
    """The complete trade desk as one self-contained string."""
    lg = desk["league"]
    cov = desk.get("coverage") or {}
    ro = desk.get("roster") or {}
    week = int(lg["week"])
    title = "%s — week %d trade desk" % (lg["name"], week)

    lede = ['<span>%s</span>' % ui.esc(cov.get("text") or "coverage unknown")]
    if ro.get("size"):
        lede.append('<span>my roster known <span class="wr-num">%d/%d</span>'
                    '</span>' % (int(ro.get("known") or 0), int(ro["size"])))
    else:
        lede.append('<span>no roster file for this league</span>')
    if desk.get("market_note"):
        lede.append('<span>%s</span>' % ui.esc(desk["market_note"]))
    lede.append('<span>rendered %s</span>' % ui.esc(desk.get("stamp") or ""))

    def _guard(title_, fn):
        try:
            return fn(desk)
        except Exception as exc:  # noqa: BLE001 - the card carries the error
            return _card(title_, ui.degraded_banner(title_, exc))

    sections = [
        _guard("League grid", render_grid),
        _guard("Needs matrix", render_needs),
        _guard("Trade targets", render_targets),
        _guard("Waiver competition", render_waivers),
        _guard("Needs over time", render_trend),
    ]
    notes = "".join('<p class="wr-note">%s</p>' % ui.esc(n)
                    for n in (desk.get("notes") or []) if n)
    legend = ('<section class="wr-card td-sec"><h3 class="td-h3">What the '
              'marks mean</h3>%s<p class="wr-note">SURPLUS / HOLE tags and the '
              'meters are startable bodies against starting demand; ALSO '
              'YOURS is cross-league exposure; TARGET and OFFER point at the '
              'proposal cards.</p></section>' % ui.legend(LEGEND))
    footer = (
        '<footer class="td-foot">%s'
        'Every number here is computed by the module that owns it — '
        'trades, waivers, leagueview, exposure, grader — and this page '
        'only arranges them. It writes this file and, once per week, '
        '<code>data/cache/%s-%s-week%d.json</code> (never rewritten); it '
        'records no ledger vote and advances no baseline, so opening it '
        'twice changes nothing else.<br>regenerate: '
        '<code>./tradedesk.sh %s %d</code> · evaluate any offer: '
        '<code>python -m engine.trades --league %s --offer "give: A | get: '
        'B"</code> · the full board: <code>./board.sh %s %d</code> '
        '· rosters and weights: <code>./sources.sh</code></footer>'
        % (notes, ui.esc(SNAPSHOT_STEM), ui.esc(lg["id"]), week,
           ui.esc(lg["id"]), week, ui.esc(lg["id"]), ui.esc(lg["id"]), week))

    return ("<!doctype html>\n<html lang=\"en\"><head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1\">\n"
            "<title>%s</title>\n%s\n<style>%s</style>\n</head><body>\n"
            "%s\n<main class=\"wr-page td-page\">\n"
            '<p class="wr-kicker">Trade desk · week %d</p>'
            '<h1 class="wr-h1 wr-display">%s</h1>'
            '<div class="td-lede">%s</div>\n'
            "%s\n%s\n%s\n</main>\n</body></html>\n"
            % (ui.esc(title), ui.style_tag(), page_css(),
               ui.shell("trades", lg["id"], week,
                        leagues=desk.get("leagues") or [],
                        subtitle="the league, read for needs and weaknesses"),
               week, ui.esc(lg["name"]), "".join(lede),
               "\n".join(sections), legend, footer))


# --- assembly + CLI ----------------------------------------------------------

def default_out_path(league_id: str, week) -> str:
    return os.path.join(HERE, "tradedesk-%s-week%d.html" % (league_id,
                                                              int(week)))


def build_page(league_id: str, week, **kwargs) -> str:
    return render_page(build_desk(league_id, week, **kwargs))


def write_tradedesk(league_id: str, week, out_path: Optional[str] = None,
                    **kwargs) -> str:
    """Build and atomically write the page; returns the path written."""
    html = build_page(league_id, week, **kwargs)
    out = out_path or default_out_path(league_id, week)
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(html)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)
    return out


def render_failure(exc: BaseException, league_id: str = "",
                   week: Optional[int] = None) -> str:
    """One legible line for a failure that killed the whole render."""
    return ("could not build the trade desk for %s%s: %s: %s\n"
            "  every card degrades on its own, so this failed before any "
            "card existed - check leagues/%s.yaml, the rankings csv it "
            "names, and data/rosters/%s.yaml."
            % (league_id or "<league>", (" week %d" % week) if week else "",
               type(exc).__name__, ui.trim(str(exc), 240),
               league_id or "<league>", league_id or "<league>"))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.tradedesk",
        description="THE TRADE DESK: every known roster as a column, the "
                    "needs matrix, ranked rival-aware trade targets, waiver "
                    "competition and needs over time - one self-contained "
                    "HTML page. Prints the output path as its last line.")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--out", default=None,
                    help="output path (default: tradedesk-<league>-week<N>"
                         ".html in the project root)")
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when caches are fresh")
    ap.add_argument("--roster-dir", default=None,
                    help="read rosters from this directory instead of "
                         "data/rosters/ (read-only). publish.py hands each "
                         "person a copy holding only the leagues they own, "
                         "so the page cannot name a league that is not "
                         "theirs")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
        try:
            from engine.digest import current_week
            week = current_week()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - feed down or digest unimportable
            print("cannot derive the current week (%s: %s) - pass --week "
                  "explicitly" % (type(exc).__name__, ui.trim(str(exc), 160)))
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
        path = write_tradedesk(args.league, week, out_path=args.out,
                               force=args.force, roster_dir=args.roster_dir)
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
