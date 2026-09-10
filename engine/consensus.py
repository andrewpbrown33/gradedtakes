"""Creator consensus: weigh every voice in the room on each lineup decision.

    python -m engine.consensus --league yahoo-main --week 3

For a league+week this module builds one row per player merging two kinds of
voices, weighted by data/sources.yaml (weights are relative 0-100 and
NORMALIZED here, over the sources that actually voted on that player):

  (a) creator calls from data/creator_calls/week-<N>.yaml (engine/calls.py) -
      each call keeps its confidence tier and verbatim quote so the strip can
      show evidence, never just an opinion;
  (b) built-in 'feed' voices for enabled feed sources in the registry:
        engine       our own lineup verdict - starters "start", bench "sit"
                     (best legal lineup under the merged weekly projections);
        espn-proj    "start" iff the player makes the best legal lineup when
        sleeper-proj every roster player is scored by THAT source's weekly
                     projections alone (engine/weekly.py tags per-player
                     source; the per-source maps come from its transforms);
        chen-tiers   start-lean iff the player's Boris Chen tier is <= the
                     positional starter cutoff: the tier of the Nth-best
                     tiered player at his position, N = starters the league
                     demands there (teams x starter share, flex split evenly).

WEIGHTED VERDICT: score = sum(weight_i * value_i) / sum(weight_i) with
value = +1 start, -1 sit, +0.5 flex-lean; a rank call (e.g. "WR12") converts
to start when the rank is inside the positional starter demand, else sit,
and keeps its "rank WR12" detail visible. score > 0 reads START, < 0 SIT,
and the printed percentage is the weight share behind the winning side:
pct = 50 * (1 + score) start-ward (so 100% = unanimous start, 50% = even).

LEAGUE-SIZE NORMALIZATION (engine/leaguesize.py): creator calls are passed
through leaguesize.adjust_calls BEFORE they are weighed. Public advice is
written for 10-12 teams; the ESPN league here has EIGHT, where replacement
level is far higher and a "deep sleeper add" is a player nobody would
roster. A call about a player who is IRRELEVANT at this league's depth
(positional rank past the starter pool plus a bench round per team) is
DOWNGRADED, never dropped: its confidence falls one tier and its vote
weight is multiplied by leaguesize.DOWNGRADE_WEIGHT. The vote carries
sized_for / size_rank / size_note, format_voices prints them inline, and
adjust_calls' notes name every downgraded call - a silent discount would
be exactly the dishonesty this module exists to prevent. A source's own
weight and its top-weighted standing are untouched: one badly-sized take
discounts that take, not that voice. Built-in feed voices are already
computed from THIS league's starter demand and are left alone.

AGREEMENT CLASSES (per row):
  UNANIMOUS     every voice points the same way (a 1-voice row is trivially
                unanimous - the vote count in the breakdown says so);
  LONE-DISSENT  exactly one voice on the LOSING side of the weighted
                verdict, with >= 2 voices winning - named, because
                "everyone but X" is the useful shape (a single heavy voice
                that WINS the weight is not a dissenter);
  SPLIT         both directions present and |score| < 0.15 - the weight is
                genuinely divided;
  MAJORITY      both directions present, one side clearly heavier.

TOP-WEIGHTED FLAG: the row flags when the user's single top-weighted enabled
source disagrees (by start/sit direction) with the final weighted verdict or
with the engine's own vote. That is the "you trust this voice most and it is
telling you something different" alarm.

SOURCE LEDGER (data/source_ledger.jsonl - same humility-ledger discipline as
data/streaming_log.jsonl): votes are LOGGED when consensus renders in the
digest, before outcomes are known, and SCORED later once the week's actuals
land - never recomputed after the fact, so no voice gets a revisionist
grade. Rows are keyed per LEAGUE: one record per (league, week, source,
player), and score_ledger grades only the calling league's rows - two
leagues sharing a week and a player keep separate rows and separate grades
(their starter demands differ, so their replacement levels do too). Rows
written before league tagging existed carry no league; they are graded ONCE
under whichever league scores them first and tagged legacy=True with that
league filled in - never re-graded, never duplicated by a re-record. SCORING RULE (the one rule, documented here): a start-side call
(start/flex, or a rank that converted to start) is a HIT when the player's
actual points >= his positional replacement - the Nth-best actual score at
his position that week, N = the league's positional starter demand; a sit
call is a HIT when the player scores BELOW that replacement. Actuals come
from the nflverse ffopportunity file (engine/nflverse.fetch_xfp for the
current season), which is offense-only: K/DEF votes and players with no
actual filed are marked unscorable, visibly, not deleted. Tests must
redirect consensus.LEDGER_PATH to a tempdir (same rule as streaming.LOG_PATH).

DEF/K ROWS ARE HOLD-OR-STREAM CALLS (engine/dk.py). A defense or kicker
has no bench rival; its alternative is the best one genuinely available
on the wire this week. So for the held DST and K the ENGINE voice votes
the dk call - start on HOLD, sit on STREAM, flex-lean on TOSS-UP - and
after weighing, apply_dk() sets the row's headline verdict to that call
(HOLD -> START, STREAM -> SIT with the candidate named in `dk_note`,
TOSS-UP -> EVEN) with pct = P(held outscores the best available) under
lineup's own DEF/K sigma (see dk.py CONFIDENCE). The other voices keep
their own votes and the weighted score is untouched, so the dossier's
arithmetic still adds up; the row simply carries `dk` (the whole call)
so every page can print why. build_consensus(dk_calls=...) takes a
precomputed call (home/board compute one per render); None computes it
here, guarded; False skips it.

HONEST DEGRADATION: a feed voice that cannot be built (dead feed, no
projections) goes silent WITH a note in the result - the row shows "-" for
that source, never a guessed vote. Calls from disabled/unknown sources are
counted in a note, not silently dropped. Absence of any creator opinion on
a player is NORMAL (nobody talks about your bench K) - only the digest's
Room section raises a degradation banner, and only when enabled creator
sources exist but the week's calls file is empty.
"""

import argparse
import datetime
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

try:
    from engine.grader import best_lineup
    from engine.models import LeagueConfig, Player, load_players
    from engine.projections import name_key
    from engine import weekly
    from engine import lineup as lineup_mod
except ImportError:  # run directly as `python engine/consensus.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.grader import best_lineup
    from engine.models import LeagueConfig, Player, load_players
    from engine.projections import name_key
    from engine import weekly
    from engine import lineup as lineup_mod

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_PATH = os.path.join(HERE, "data", "source_ledger.jsonl")

VERDICT_VALUE = {"start": 1.0, "flex": 0.5, "sit": -1.0}
SPLIT_BAND = 0.15          # |score| below this with both sides present = SPLIT
CONF_RANK = {"high": 3, "med": 2, "low": 1}

# Compact voice labels for the terminal strip; unknown ids use display names.
SHORT_NAMES = {"engine": "ENGINE", "espn-proj": "ESPN",
               "sleeper-proj": "Sleeper", "chen-tiers": "Chen"}

SCOREBOARD_MIN_WEEKS = 2   # scored weeks before a hit-rate means anything

# Smallest league-size discount a call's vote may carry (see build_rows).
MIN_WEIGHT_FACTOR = 0.05


def _w(source: Dict) -> float:
    try:
        return max(0.0, float(source.get("weight") or 0))
    except (TypeError, ValueError):
        return 0.0


def _sign(x: float) -> int:
    return 1 if x > 1e-9 else (-1 if x < -1e-9 else 0)


# --- pure scoring core ------------------------------------------------------

def starters_demand(league: LeagueConfig) -> Dict[str, int]:
    """Starters the whole league demands per position (flex split evenly)."""
    out = {}
    for pos, share in league.starter_counts().items():
        n = int(round(league.teams * share))
        if n > 0:
            out[pos] = n
    return out


def rank_verdict(value, pos: str, demand: Dict[str, int]) -> Optional[str]:
    """A positional rank call -> start inside the starter demand, else sit."""
    n = demand.get(pos)
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if not n or v < 1:
        return None
    return "start" if v <= n else "sit"


def weigh(votes: List[Dict]) -> Tuple[float, int]:
    """(score, start-ward pct). Weights normalized over the voting sources;
    all-zero weights fall back to an equal split (silence about weights is
    not a verdict about them)."""
    total = sum(_w(v) for v in votes)
    if total <= 0:
        vals = [VERDICT_VALUE[v["verdict"]] for v in votes]
        score = sum(vals) / len(vals) if vals else 0.0
    else:
        score = sum(_w(v) * VERDICT_VALUE[v["verdict"]] for v in votes) / total
    return round(score, 4), int(round(50.0 * (1.0 + score)))


def verdict_of(score: float) -> str:
    s = _sign(score)
    return "START" if s > 0 else ("SIT" if s < 0 else "EVEN")


def agreement(votes: List[Dict], score: float) -> Tuple[str, Optional[str]]:
    """Agreement class per the module docstring; LONE-DISSENT names names.

    The dissenting side is the side that LOSES the weighted verdict - a
    single heavy voice that WINS the weight is a majority-of-weight, not a
    dissenter. Dead-even weight with both sides present is SPLIT.
    """
    dirs = [_sign(VERDICT_VALUE[v["verdict"]]) for v in votes]
    if len(set(dirs)) <= 1:
        return "UNANIMOUS", None
    wsign = _sign(score)
    if wsign == 0:
        return "SPLIT", None
    losers = [v for v, d in zip(votes, dirs) if d != wsign]
    winners = [v for v, d in zip(votes, dirs) if d == wsign]
    if len(losers) == 1 and len(winners) >= 2:
        lone = losers[0]
        return "LONE-DISSENT", lone.get("name") or lone.get("source")
    if abs(score) < SPLIT_BAND:
        return "SPLIT", None
    return "MAJORITY", None


def build_rows(sources: List[Dict], universe: Dict[str, Dict],
               calls: List[Dict], feed_votes: Dict[str, Dict[str, str]],
               demand: Dict[str, int],
               engine_id: str = "engine") -> List[Dict]:
    """The pure heart: enabled sources + votes -> consensus rows.

    sources: ENABLED registry entries (any order; sorted by weight here).
    universe: {player_key: {"name", "pos"}} - the roster players; keys that
    appear only in calls are added from the calls themselves.
    feed_votes: {source_id: {player_key: "start"|"sit"|"flex"}}.
    """
    ordered = sorted(sources, key=lambda s: -_w(s))
    by_id = dict((s.get("id"), s) for s in ordered)
    top_id = ordered[0].get("id") if ordered else None

    # One call per (source, player): highest confidence wins, first on ties -
    # a source that contradicts itself must not vote twice.
    grouped = {}
    for c in calls:
        sid = c.get("source")
        key = c.get("player_key") or ""
        if sid not in by_id or "|" not in key:
            continue
        k = (sid, key)
        prev = grouped.get(k)
        if prev is None or (CONF_RANK.get(c.get("confidence"), 0)
                            > CONF_RANK.get(prev.get("confidence"), 0)):
            grouped[k] = c

    uni = dict((k, dict(v)) for k, v in universe.items())
    for (_, key), c in grouped.items():
        if key not in uni:
            nkey, _, pos = key.partition("|")
            uni[key] = {"name": c.get("player") or nkey.title(), "pos": pos}

    rows = []
    for key, info in uni.items():
        votes = []
        for s in ordered:
            sid = s.get("id")
            vote = None
            if (s.get("type") or "").strip().lower() == "feed":
                fv = (feed_votes.get(sid) or {}).get(key)
                if fv in VERDICT_VALUE:
                    vote = {"source": sid, "name": s.get("name") or sid,
                            "weight": _w(s), "verdict": fv}
            else:
                c = grouped.get((sid, key))
                if c is not None:
                    verdict = c.get("verdict")
                    detail = None
                    if verdict == "rank":
                        conv = rank_verdict(c.get("value"), info["pos"],
                                            demand)
                        if conv is None:
                            continue
                        detail = "rank %s%s" % (info["pos"], c.get("value"))
                        verdict = conv
                    if verdict not in VERDICT_VALUE:
                        continue
                    # League-size normalization (engine/leaguesize.py) may
                    # have downgraded this call: the factor is a real
                    # discount on THIS call's weight, never on the source's
                    # standing (top_id below still reads the raw weight -
                    # one bad-sized take does not demote a voice).
                    try:
                        factor = float(c.get("weight_factor", 1.0))
                    except (TypeError, ValueError):
                        factor = 1.0
                    # Floored above zero on purpose. A factor of 0 would zero
                    # the vote's weight, and weigh() reads an all-zero set as
                    # "no weights configured" and splits evenly - so a mute
                    # would come back as a FULL-strength vote. Normalization
                    # downgrades and never drops, so 0 is not a valid factor.
                    factor = max(MIN_WEIGHT_FACTOR, min(1.0, factor))
                    vote = {"source": sid, "name": s.get("name") or sid,
                            "weight": _w(s) * factor, "verdict": verdict,
                            "confidence": c.get("confidence") or "",
                            "quote": c.get("quote") or ""}
                    if detail:
                        vote["detail"] = detail
                    # Tag fields ride onto the vote so the strip can say WHY
                    # this voice was discounted - a silent discount would be
                    # exactly the dishonesty this engine exists to avoid.
                    if c.get("sized_for"):
                        vote["sized_for"] = c["sized_for"]
                        vote["weight_factor"] = factor
                        for fld in ("size_rank", "size_note", "relevance"):
                            if c.get(fld):
                                vote[fld] = c[fld]
            if vote is not None:
                votes.append(vote)
        if not votes:
            continue

        score, pct = weigh(votes)
        agree, dissenter = agreement(votes, score)
        wsign = _sign(score)
        engine_vote = next((v for v in votes if v["source"] == engine_id),
                           None)
        esign = _sign(VERDICT_VALUE[engine_vote["verdict"]]) \
            if engine_vote else 0
        vs_engine = bool(engine_vote) and esign != 0 and wsign != 0 \
            and esign != wsign

        top_vote = next((v for v in votes if v["source"] == top_id), None)
        top_disagrees = False
        reasons = []
        if top_vote is not None:
            tsign = _sign(VERDICT_VALUE[top_vote["verdict"]])
            if wsign != 0 and tsign != wsign:
                top_disagrees = True
                reasons.append("the weighted verdict")
            if engine_vote is not None and top_vote["source"] != engine_id \
                    and esign != 0 and tsign != esign:
                top_disagrees = True
                reasons.append("the engine")
        top_note = ""
        if top_disagrees:
            top_note = ("top-weighted %s says %s - disagrees with %s"
                        % (top_vote.get("name") or top_id,
                           top_vote["verdict"], " and ".join(reasons)))

        rows.append({
            "player": info["name"], "player_key": key, "pos": info["pos"],
            "votes": votes, "score": round(score, 3), "pct": pct,
            "verdict": verdict_of(score),
            "agreement": agree, "dissenter": dissenter,
            "engine": engine_vote["verdict"] if engine_vote else None,
            "vs_engine": vs_engine,
            "top_source": top_id,
            "top_vote": top_vote["verdict"] if top_vote else None,
            "top_disagrees": top_disagrees, "top_note": top_note,
        })
    rows.sort(key=lambda r: (r["pos"], r["player"]))
    return rows


# --- strip formatting (shared by lineup CLI and consensus CLI) --------------

def format_voices(row: Dict, max_quote: int = 40) -> str:
    """'ENGINE start | YourCreator sit (high, "quote...") | ESPN start'.

    A voice downgraded by league-size normalization carries its reason
    inline - '[WR37 - advice sized for deeper leagues]' - so the user reads
    the discount and its cause in the same glance as the vote itself.
    """
    parts = []
    for v in row["votes"]:
        name = SHORT_NAMES.get(v["source"], v.get("name") or v["source"])
        word = v.get("detail") or v["verdict"]
        extra = ""
        if v.get("confidence"):
            q = re.sub(r"\s+", " ", v.get("quote") or "").strip()
            if len(q) > max_quote:
                q = q[:max_quote - 3].rstrip() + "..."
            extra = (" (%s, \"%s\")" % (v["confidence"], q) if q
                     else " (%s)" % v["confidence"])
        if v.get("sized_for"):
            extra += (" [%s - %s]" % (v["size_rank"], v["sized_for"])
                      if v.get("size_rank") else " [%s]" % v["sized_for"])
        parts.append("%s %s%s" % (name, word, extra))
    return " | ".join(parts)


def display_pct(row: Dict) -> int:
    """pct behind the WINNING side (row['pct'] is always start-ward)."""
    if row["verdict"] == "SIT":
        return 100 - row["pct"]
    if row["verdict"] == "EVEN":
        return 50
    return row["pct"]


def format_weighted(row: Dict) -> str:
    """The weighted verdict, phrased as the user's own model speaking:
    'Your model says START - 71%' (branding directive - the weights are
    the user's, so the verdict is theirs)."""
    tail = ""
    if row.get("top_vote") is not None:
        tail = (" - top-weighted source %s"
                % ("DISAGREES" if row.get("top_disagrees") else "AGREES"))
    return "Your model says %s - %d%%%s" % (row["verdict"],
                                            display_pct(row), tail)


# --- live data gathering (each piece patchable in tests) --------------------

def load_week_calls(week: int, calls_dir: Optional[str] = None) -> List[Dict]:
    """This week's creator calls; a missing file is simply an empty week."""
    import yaml
    from engine.calls import CALLS_DIR
    path = os.path.join(calls_dir or CALLS_DIR, "week-%d.yaml" % int(week))
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as fh:
            doc = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        return []
    return [c for c in (doc.get("calls") or []) if isinstance(c, dict)]


def _merged_projections(week: int, scoring: str,
                        force: bool = False) -> Dict[str, Dict]:
    return weekly.fetch_weekly_projections(week, scoring=scoring,
                                           force=force, quiet=True)


def _espn_map(week: int, scoring: str, force: bool = False) -> Dict[str, Dict]:
    records = weekly._espn_weekly_records(scoring, force=force, quiet=True)
    return weekly._weekly_from_espn(records, week)


def _sleeper_map(week: int, scoring: str,
                 force: bool = False) -> Dict[str, Dict]:
    from engine.projections import UA, _fetch_json
    payload = _fetch_json(
        weekly.SLEEPER_WEEKLY_URL % (weekly.SEASON, week),
        "sleeper-proj-wk%d-%d.json" % (week, weekly.SEASON),
        {"User-Agent": UA, "Accept": "application/json"},
        force=force, quiet=True)
    return weekly._weekly_from_sleeper(payload, scoring)


def _chen_tiers(scoring: str, force: bool = False) -> Dict[str, int]:
    from engine import tiers
    return tiers.fetch(scoring, force=force, quiet=True)


def _lookup(src_map: Dict[str, Dict], player: Player) -> Optional[Dict]:
    """Per-source projection for a resolved roster player (DEF by team)."""
    rec = src_map.get(name_key(player.name))
    if rec is None and player.pos == "DEF" and player.team:
        for r in src_map.values():
            if r.get("pos") == "DEF" and r.get("team") == player.team:
                return r
    return rec


def projection_lineup_verdicts(league: LeagueConfig,
                               roster_players: List[Player],
                               src_map: Dict[str, Dict]) -> Dict[str, str]:
    """start/sit per player under ONE source's projections alone.

    Only players that source actually projects get a vote - a player it
    never filed a number for is silence, not a sit.
    """
    clones = []
    for p in roster_players:
        rec = _lookup(src_map, p)
        if rec is None:
            continue
        clones.append(Player(rank=p.rank, name=p.name, pos=p.pos,
                             team=p.team, proj_points=float(rec["proj"])))
    if not clones:
        return {}
    rows, _, _ = best_lineup(league, clones)
    started = set(p.key for _, p in rows if p is not None)
    return dict((c.key, "start" if c.key in started else "sit")
                for c in clones)


def chen_cutoffs(pool: List[Player], tiers_map: Dict[str, int],
                 demand: Dict[str, int]) -> Dict[str, int]:
    """Per-position starter-cutoff tier: the tier of the Nth-best tiered
    player at that position (N = league starter demand). Fewer tiered
    players than demand means everyone tiered is inside the cutoff."""
    per_pos = {}
    for p in pool:
        t = tiers_map.get(p.nkey)
        if t is not None:
            per_pos.setdefault(p.pos, []).append(int(t))
    out = {}
    for pos, ts in per_pos.items():
        n = demand.get(pos)
        if not n:
            continue
        ts.sort()
        out[pos] = ts[n - 1] if len(ts) >= n else ts[-1]
    return out


def chen_verdicts(universe: Dict[str, Dict], tiers_map: Dict[str, int],
                  cutoffs: Dict[str, int]) -> Dict[str, str]:
    out = {}
    for key, info in universe.items():
        nkey = key.partition("|")[0]
        t = tiers_map.get(nkey)
        cut = cutoffs.get(info.get("pos") or "")
        if t is None or cut is None:
            continue
        out[key] = "start" if int(t) <= cut else "sit"
    return out


def build_consensus(league_id: str, week: int,
                    roster_dir: Optional[str] = None,
                    calls_dir: Optional[str] = None,
                    registry_path: Optional[str] = None,
                    force: bool = False,
                    dk_calls=None) -> Dict:
    """Everything the strip, matrix, and ledger need, for one league+week.

    Read-only: this function fetches (through the normal data/cache
    discipline) and computes, but never writes the ledger - recording is the
    digest's explicit job (record_votes / score_ledger).

    dk_calls: engine/dk.weekly_call's result to apply to the DST/K rows;
    None computes one here (guarded - a failure is a note, and the rows
    keep their projection verdicts); False skips the read entirely."""
    week = int(week)
    league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                            "%s.yaml" % league_id))
    csv_path = os.path.join(HERE, league.rankings_csv)
    pool = load_players(csv_path)
    from engine.ingest import Matcher
    matcher = Matcher(pool)
    scoring = league.scoring_label()
    demand = starters_demand(league)

    from engine import sources as sources_mod
    registry = sources_mod.load_sources(registry_path)
    enabled = [s for s in registry if s.get("enabled")]
    ordered = sorted(enabled, key=lambda s: -_w(s))
    creator_enabled = any((s.get("type") or "").strip().lower() != "feed"
                          for s in enabled)
    enabled_ids = set(s.get("id") for s in enabled)

    calls = load_week_calls(week, calls_dir)
    skipped = sum(1 for c in calls if c.get("source") not in enabled_ids)
    calls = [c for c in calls if c.get("source") in enabled_ids]
    notes: List[str] = []
    if skipped:
        notes.append("%d call(s) from disabled/unknown sources ignored "
                     "(enable them in data/sources.yaml to count them)"
                     % skipped)

    # LEAGUE-SIZE NORMALIZATION (engine/leaguesize.py). Outside advice is
    # written for 10-12 teams; this league may not be one. A call about a
    # player who is IRRELEVANT at this depth is downgraded and tagged here,
    # BEFORE any weighing, so the discount is part of the verdict rather
    # than a footnote to it. Built-in feed voices need no adjustment - they
    # are computed from THIS league's own starter demand already.
    from engine import leaguesize
    size_ctx = leaguesize.replacement_context(league, players=pool)
    calls, size_notes = leaguesize.adjust_calls(calls, size_ctx)
    notes.extend(size_notes)

    roster = lineup_mod.load_roster(league_id, dirpath=roster_dir)
    names = roster["players"] if roster else []
    feed_handles = dict((s.get("id"),
                         (s.get("handle") or s.get("id") or "").strip())
                        for s in enabled
                        if (s.get("type") or "").strip().lower() == "feed")
    engine_id = next((sid for sid, h in feed_handles.items()
                      if h == "engine"), "engine")

    players: List[Player] = []
    close_keys: List[str] = []
    feed_votes: Dict[str, Dict[str, str]] = {}
    merged = None
    if names:
        try:
            merged = _merged_projections(week, scoring, force=force)
        except Exception as exc:  # noqa: BLE001 - the note carries the error
            notes.append("weekly projections unavailable (%s) - engine and "
                         "projection voices are absent this week" % exc)
    elif feed_handles:
        notes.append("no roster file (data/rosters/%s.yaml) - engine and "
                     "projection voices have nothing to vote on" % league_id)

    if merged is not None:
        b = lineup_mod.build(league, names, week, merged, matcher=matcher)
        players = [p for _, p in b["rows"] if p is not None] + b["bench"]
        if b["unresolved"]:
            notes.append("unresolved roster names skipped: %s"
                         % ", ".join(b["unresolved"]))
        for v in b["verdicts"]:
            for k in (v.get("a_key"), v.get("b_key")):
                if k and k not in close_keys:
                    close_keys.append(k)
        started = set(p.key for _, p in b["rows"] if p is not None)
        # DEF/K: the engine's vote on the HELD defense/kicker is the
        # hold-or-stream call against the wire (engine/dk), not "he is in
        # the best lineup" - he always is; there is no second defense.
        if dk_calls is None and any(p.pos in ("DEF", "K") for p in players):
            try:
                from engine import dk as dk_mod
                dk_calls = dk_mod.weekly_call(league, week, players, pool,
                                              matcher, force=force)
            except Exception as exc:  # noqa: BLE001 - a note, not a crash
                notes.append("DEF/K stream call unavailable (%s) - DST/K "
                             "rows keep their projection verdicts" % exc)
                dk_calls = None
        dk_votes = dk_engine_votes(dk_calls) if dk_calls else {}
        for sid, handle in feed_handles.items():
            if handle == "engine":
                feed_votes[sid] = dict(
                    (p.key, dk_votes.get(p.key)
                     or ("start" if p.key in started else "sit"))
                    for p in players)
        for handle, mapper in (("espn-proj", _espn_map),
                               ("sleeper-proj", _sleeper_map)):
            sid = next((i for i, h in feed_handles.items() if h == handle),
                       None)
            if sid is None:
                continue
            try:
                feed_votes[sid] = projection_lineup_verdicts(
                    league, players, mapper(week, scoring, force=force))
            except Exception as exc:  # noqa: BLE001
                notes.append("%s voice unavailable (%s) - absent, not "
                             "guessed" % (sid, exc))

    universe = dict((p.key, {"name": p.name, "pos": p.pos}) for p in players)
    full_universe = dict(universe)
    for c in calls:
        key = c.get("player_key") or ""
        if "|" in key and key not in full_universe:
            nkey, _, pos = key.partition("|")
            full_universe[key] = {"name": c.get("player") or nkey.title(),
                                  "pos": pos}

    chen_sid = next((sid for sid, h in feed_handles.items()
                     if h == "chen-tiers"), None)
    if chen_sid is not None and full_universe:
        try:
            tmap = _chen_tiers(scoring, force=force)
            feed_votes[chen_sid] = chen_verdicts(
                full_universe, tmap, chen_cutoffs(pool, tmap, demand))
        except Exception as exc:  # noqa: BLE001
            notes.append("chen-tiers voice unavailable (%s) - absent, not "
                         "guessed" % exc)

    rows = build_rows(ordered, universe, calls, feed_votes, demand,
                      engine_id=engine_id)
    if dk_calls:
        apply_dk(rows, dk_calls)
    return {"week": week, "league": league.id, "sources": ordered,
            "rows": rows, "close_keys": close_keys, "notes": notes,
            "creator_enabled": creator_enabled, "calls_count": len(calls),
            "size_context": size_ctx.summary(),
            "dk": dk_calls if dk_calls else None}


# --- DEF/K hold-or-stream (engine/dk) applied to the rows (pure) ------------

def dk_engine_votes(dk_calls) -> Dict[str, str]:
    """{held player_key: engine vote} from a dk call set. start on HOLD,
    sit on STREAM, flex on TOSS-UP; NO READ votes nothing (silence)."""
    from engine import dk as dk_mod
    out = {}
    for call in (dk_calls or {}).values():
        key = (call or {}).get("held_key")
        vote = dk_mod.consensus_vote(call or {})
        if key and vote:
            out[key] = vote
    return out


def apply_dk(rows: List[Dict], dk_calls) -> int:
    """Set the held DST/K rows' headline verdict from the dk call.

    HOLD -> START, STREAM -> SIT (the candidate named in dk_note), TOSS-UP
    -> EVEN; pct = P(held outscores best) (dk.consensus_verdict). The
    votes and the weighted score are left alone - the arithmetic the
    dossier prints stays reconstructible - and the whole call rides on the
    row as `dk`. Returns the number of rows touched."""
    from engine import dk as dk_mod
    by_key = {}
    for call in (dk_calls or {}).values():
        if call and call.get("held_key"):
            by_key[call["held_key"]] = call
    n = 0
    for row in rows or []:
        call = by_key.get(row.get("player_key"))
        if call is None:
            continue
        cv = dk_mod.consensus_verdict(call)
        if cv is None:
            continue
        row["verdict"], row["pct"] = cv
        row["dk"] = call
        row["dk_note"] = dk_mod.verdict_text(call)
        n += 1
    return n


def consensus_map(cons: Optional[Dict]) -> Dict[str, Dict]:
    if not cons:
        return {}
    return dict((r["player_key"], r) for r in cons.get("rows") or [])


# --- source ledger (humility-ledger discipline) -----------------------------

def read_ledger(path: Optional[str] = None) -> List[Dict]:
    """All parseable entries; a corrupt line is skipped, not fatal."""
    path = path or LEDGER_PATH
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _write_ledger(entries: List[Dict], path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for e in entries:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    os.replace(tmp, path)


def record_votes(week: int, rows: List[Dict],
                 path: Optional[str] = None,
                 league: Optional[str] = None) -> int:
    """Append this week's votes as pending records; returns count appended.

    Idempotent PER LEAGUE: one record per (league, week, source, player) -
    re-rendering a digest never duplicates, two leagues weighing the same
    player in the same week keep separate rows, and the FIRST recorded
    verdict stands (the humility rule: what was said at the time is the
    record). A pre-league-tagging row (no league field) already IS the
    record for its (week, source, player) - re-recording under any league
    does not duplicate it."""
    path = path or LEDGER_PATH
    seen = set((e.get("league"), e.get("week"), e.get("source"),
                e.get("player_key"))
               for e in read_ledger(path))
    stamp = datetime.date.today().isoformat()
    lines = []
    for row in rows:
        for v in row.get("votes") or []:
            k = (league, int(week), v.get("source"), row.get("player_key"))
            legacy_k = (None, int(week), v.get("source"),
                        row.get("player_key"))
            if k in seen or legacy_k in seen:
                continue
            seen.add(k)
            rec = {"week": int(week), "source": v.get("source"),
                   "player": row.get("player"),
                   "player_key": row.get("player_key"),
                   "pos": row.get("pos"), "verdict": v.get("verdict"),
                   "logged": stamp, "actual": None, "replacement": None,
                   "hit": None}
            if league is not None:
                rec["league"] = league
            if v.get("detail"):
                rec["detail"] = v["detail"]
            lines.append(json.dumps(rec, sort_keys=True))
    if lines:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    return len(lines)


def week_actuals(weeks, force: bool = False) -> Dict[int, Dict[str, float]]:
    """{week: {nkey: actual pts}} from the current season's ffopportunity
    file. Offense-only by nature. Raises RuntimeError offline+uncached."""
    from engine import nflverse
    wanted = set(int(w) for w in weeks)
    data = nflverse.fetch_xfp(weekly.SEASON, force=force)
    out: Dict[int, Dict[str, float]] = {}
    for nkey, wk_list in data.items():
        for w in wk_list:
            if w["week"] in wanted:
                out.setdefault(w["week"], {})[nkey] = float(w["actual"])
    return out


def replacement_points(act_map: Dict[str, float], positions: Dict[str, str],
                       demand: Dict[str, int]) -> Dict[str, float]:
    """Nth-best actual per position, N = league starter demand there."""
    per_pos: Dict[str, List[float]] = {}
    for nkey, pts in act_map.items():
        pos = positions.get(nkey)
        if pos:
            per_pos.setdefault(pos, []).append(float(pts))
    out = {}
    for pos, vals in per_pos.items():
        n = demand.get(pos)
        if not n:
            continue
        vals.sort(reverse=True)
        out[pos] = vals[n - 1] if len(vals) >= n else vals[-1]
    return out


def score_entries(entries: List[Dict],
                  actuals_by_week: Dict[int, Dict[str, float]],
                  positions: Dict[str, str],
                  demand: Dict[str, int]) -> int:
    """Fill hit/actual/replacement on pending entries (in place); returns
    the number scored. The scoring rule lives in the module docstring."""
    repl = dict((wk, replacement_points(act, positions, demand))
                for wk, act in actuals_by_week.items())
    scored = 0
    for e in entries:
        if e.get("hit") is not None or e.get("unscorable"):
            continue
        act_map = actuals_by_week.get(e.get("week"))
        if act_map is None:
            continue
        verdict = e.get("verdict")
        if verdict == "rank":
            e["unscorable"] = "rank calls are graded only through their " \
                              "start/sit conversion"
            continue
        if verdict not in VERDICT_VALUE:
            e["unscorable"] = "unknown verdict %r" % (verdict,)
            continue
        nkey, _, key_pos = (e.get("player_key") or "").partition("|")
        pos = e.get("pos") or key_pos
        pts = act_map.get(nkey)
        if pts is None:
            e["unscorable"] = ("no actual filed (actuals feed is "
                               "offense-only)")
            continue
        r = repl.get(e["week"], {}).get(pos)
        if r is None:
            e["unscorable"] = "no positional replacement computable"
            continue
        startish = VERDICT_VALUE[verdict] > 0
        e["actual"] = round(float(pts), 2)
        e["replacement"] = round(float(r), 2)
        e["hit"] = bool(pts >= r) if startish else bool(pts < r)
        scored += 1
    return scored


def score_ledger(league: LeagueConfig, pool: List[Player], upto_week: int,
                 path: Optional[str] = None, force: bool = False) -> Dict:
    """Score THIS league's pending votes for weeks before `upto_week` whose
    actuals exist. Atomic rewrite (verdicts untouched - only outcome fields
    fill). Rows belonging to other leagues are never touched - each league
    grades under its own starter demand. Rows written before league tagging
    (no league field) are graded once under the first league that scores
    them, tagged legacy=True with that league filled in. Never raises for a
    down actuals feed; the note says so instead."""
    path = path or LEDGER_PATH
    lid = getattr(league, "id", None)
    entries = read_ledger(path)
    mine = [e for e in entries if e.get("league") in (lid, None)]
    legacy = [e for e in mine if e.get("league") is None]
    pending = sorted(set(e["week"] for e in mine
                         if e.get("hit") is None and not e.get("unscorable")
                         and isinstance(e.get("week"), int)
                         and 1 <= e["week"] < int(upto_week)))
    if not pending:
        return {"scored": 0, "weeks": []}
    try:
        actuals = week_actuals(pending, force=force)
    except RuntimeError as exc:
        return {"scored": 0, "weeks": [],
                "note": "actuals feed unavailable (%s)" % exc}
    if not actuals:
        return {"scored": 0, "weeks": [],
                "note": "no actuals filed yet for week(s) %s"
                        % ", ".join(str(w) for w in pending)}
    positions = dict((p.nkey, p.pos) for p in pool)
    n = score_entries(mine, actuals, positions, starters_demand(league))
    tagged = 0
    for e in legacy:   # graded (or ruled unscorable) here -> this league's
        if e.get("hit") is not None or e.get("unscorable"):
            e["league"] = lid
            e["legacy"] = True
            tagged += 1
    if n or tagged:
        _write_ledger(entries, path)
    return {"scored": n, "weeks": sorted(actuals)}


def scoreboard(entries: List[Dict]) -> Dict:
    """Per-source hit rates over SCORED entries only.

    {"weeks": sorted scored weeks, "rows": [{source, hits, scored, weeks,
    pct}]}. Callers should not render a hit-rate before
    SCOREBOARD_MIN_WEEKS distinct scored weeks exist - one week is noise.
    """
    per: Dict[str, Dict] = {}
    weeks = set()
    for e in entries:
        if e.get("hit") is None:
            continue
        weeks.add(e.get("week"))
        d = per.setdefault(e.get("source"),
                           {"source": e.get("source"), "hits": 0,
                            "scored": 0, "week_set": set()})
        d["scored"] += 1
        d["hits"] += 1 if e["hit"] else 0
        d["week_set"].add(e.get("week"))
    rows = []
    for d in per.values():
        d["weeks"] = len(d.pop("week_set"))
        d["pct"] = round(100.0 * d["hits"] / d["scored"], 1)
        rows.append(d)
    rows.sort(key=lambda d: (-d["pct"], -d["scored"], str(d["source"])))
    return {"weeks": sorted(w for w in weeks if w is not None), "rows": rows}


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.consensus",
        description="Weighted source consensus per player for a league+week "
                    "(read-only - the digest records the ledger).")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds, ignoring caches")
    args = ap.parse_args(argv)

    cons = build_consensus(args.league, args.week, force=args.force)
    srcs = ", ".join("%s %g" % (s.get("name") or s.get("id"), _w(s))
                     for s in cons["sources"])
    print("CONSENSUS - %s week %d" % (cons["league"], cons["week"]))
    print("  sources (weight): %s" % (srcs or "none enabled"))
    for n in cons["notes"]:
        print("  NOTE: %s" % n)
    if cons["creator_enabled"] and cons["calls_count"] == 0:
        print("  DEGRADED: no creator calls ingested this week - run: "
              "python -m engine.calls --week %d" % cons["week"])
    if not cons["rows"]:
        print("  no rows - nothing to weigh (no roster, no calls).")
        return 0
    for row in cons["rows"]:
        flags = [row["agreement"]]
        if row["dissenter"]:
            flags.append("dissenter: %s" % row["dissenter"])
        print("  %-24s %s" % (row["player"], "  ".join(flags)))
        print("      %s" % format_voices(row))
        print("      %s" % format_weighted(row))
        if row["top_note"]:
            print("      !! %s" % row["top_note"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
