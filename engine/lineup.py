"""Weekly lineup optimizer: fill the legal lineup, frame every close call.

    python -m engine.lineup --league yahoo-main --week 1

Fills the league's legal starting lineup from data/rosters/<league>.yaml,
maximizing this week's projections (engine/weekly.py feeds), and then does
the part a projection table can't: VERDICT FRAMING for every non-obvious
call. A bench player within ~3 projected points of a hard-slot starter (~5
for a flex spot - flex contests are inherently the arguable calls) gets a
one-line verdict:

    Start A over B - 62% - A median 12.4 (7-19) vs B 11.1 (6-16) - reason

When source consensus is available (engine/consensus.py: creator calls plus
the built-in feed voices in data/sources.yaml), each close call also gets a
consensus strip - one line per voice, then the weighted verdict and whether
the top-weighted source agrees. The strip appears only when consensus data
exists for that player; silence is normal, not degraded.

CONFIDENCE METHOD (computed once, cached, documented here):
Weekly projection error is estimated per position from the nflverse 2025
xFP file (ffopportunity ep_weekly): for every player-week where the
expected-points model saw startable usage (xfp >= 5.0 - mop-up weeks would
shrink the spread), the residual is actual - expected fantasy points, and
sigma(pos) is the population stddev of those residuals pooled by the file's
own position column. The projection is treated as the median of a normal
with that sigma, so P(A beats B) = Phi((projA - projB) / sqrt(sigA^2 +
sigB^2)) and the printed range is median +/- 1 sigma (floored at zero).
2025 values land near QB 6.0 / RB 5.8 / WR 5.3 / TE 4.5. K and DEF never
appear in the xFP file (it is offense-only), so they keep documented
defaults (K 4.8, DEF 6.5 - kicker scoring is tighter, DEF swingier). The
result is cached in data/cache/proj-sigma-2025.json with the method noted
inside; offline with no cache falls back to the defaults rather than dying.

HONESTY RULES (same contract as engine/exposure.py):
Roster files are partial by design - yahoo-main currently knows 3 of 16
players. The lineup is built from KNOWN players only and every report
carries a banner saying so; an open slot means "no KNOWN player fits",
never "you have nobody". A missing weekly projection is "no projection
filed", distinct from a filed 0.0 (red alert: injured/not playing). Bye
detection is by absence from the week's schedule map; when the schedule
feed is down, bye/lock info is skipped with a note instead of guessed.
"""

import argparse
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

try:
    from engine.grader import best_lineup
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, norm_pos)
    from engine.nflverse import CACHE_DIR, XFP_URL, _fetch_csv
    from engine.projections import name_key
    from engine.recommend import Ansi
    from engine.weekly import _check_week
except ImportError:  # run directly as `python engine/lineup.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.grader import best_lineup
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, norm_pos)
    from engine.nflverse import CACHE_DIR, XFP_URL, _fetch_csv
    from engine.projections import name_key
    from engine.recommend import Ansi
    from engine.weekly import _check_week

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTER_DIR = os.path.join(HERE, "data", "rosters")

XFP_SEASON = 2025
STARTABLE_XFP = 5.0
SIGMA_CACHE = "proj-sigma-%d.json" % XFP_SEASON
# K/DEF are absent from the offense-only xFP file; documented judgment
# values (kickers cluster tight, defenses swing on TDs/turnovers).
DEFAULT_SIGMA = {"QB": 6.0, "RB": 5.8, "WR": 5.3, "TE": 4.5,
                 "K": 4.8, "DEF": 6.5}
MIN_SIGMA_SAMPLES = 50

VERDICT_MARGIN_HARD = 3.0   # bench within this of a hard-slot starter
VERDICT_MARGIN_FLEX = 5.0   # flex calls are arguable further out
COIN_FLIP_PCT = 55          # <= this reads as a coin flip
IMPLIED_GAP = 3.0           # implied-total gap worth citing as a reason

# Sleeper statuses that mean "do not start without checking" vs "monitor".
RED_STATUSES = ("out", "ir", "pup", "sus", "suspended", "cov", "dnr")
WARN_STATUSES = ("questionable", "doubtful", "holdout")


# --- projection-error sigma -------------------------------------------------

def _f(val) -> Optional[float]:
    s = (str(val) if val is not None else "").strip()
    if not s or s.upper() == "NA":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sigma_from_rows(rows: List[Dict]) -> Tuple[Dict[str, float],
                                                Dict[str, int]]:
    """Pure transform: xFP player-weeks -> per-position residual stddev.

    Residual = actual - expected fantasy points, startable weeks only
    (xfp >= STARTABLE_XFP). Positions come from the file's own column;
    anything outside QB/RB/WR/TE (DB rows, 'NA' misc) is ignored.
    """
    res = {}
    for r in rows:
        pos = norm_pos(r.get("position") or "")
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        xfp = _f(r.get("total_fantasy_points_exp"))
        act = _f(r.get("total_fantasy_points"))
        if xfp is None or act is None or xfp < STARTABLE_XFP:
            continue
        res.setdefault(pos, []).append(act - xfp)

    sigmas, counts = {}, {}
    for pos, vals in res.items():
        counts[pos] = len(vals)
        if len(vals) < MIN_SIGMA_SAMPLES:
            continue  # too thin to beat the documented default
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        sigmas[pos] = round(math.sqrt(var), 2)
    return sigmas, counts


def position_sigma(force: bool = False) -> Dict[str, float]:
    """Per-position weekly projection-error sigma; cached once per season.

    See the module docstring for the method. Offline with no xFP cache the
    documented DEFAULT_SIGMA values are returned (and NOT cached, so the
    real numbers land on the next online run).
    """
    path = os.path.join(CACHE_DIR, SIGMA_CACHE)
    if os.path.exists(path) and not force:
        try:
            with open(path, "r") as fh:
                cached = json.load(fh)
            sig = cached.get("sigma") or {}
            if all(p in sig for p in DEFAULT_SIGMA):
                return dict((p, float(sig[p])) for p in sig)
        except (ValueError, OSError):
            pass  # corrupt cache: recompute below

    try:
        rows = _fetch_csv(XFP_URL % XFP_SEASON,
                          "nflverse-xfp-%d.csv" % XFP_SEASON,
                          "total_fantasy_points_exp", force=force)
    except RuntimeError:
        return dict(DEFAULT_SIGMA)

    computed, counts = _sigma_from_rows(rows)
    sigma = dict(DEFAULT_SIGMA)
    sigma.update(computed)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as fh:
            json.dump({
                "season": XFP_SEASON,
                "method": ("stddev of (actual - expected) fantasy points per "
                           "player-week from ffopportunity ep_weekly, weeks "
                           "with xfp >= %.1f, pooled by position; K/DEF are "
                           "documented defaults (file is offense-only)"
                           % STARTABLE_XFP),
                "samples": counts,
                "sigma": sigma,
            }, fh, indent=2)
    except OSError:
        pass  # cache write is best-effort
    return sigma


def p_first_beats(proj_a: float, proj_b: float,
                  sig_a: float, sig_b: float) -> float:
    """P(A outscores B) under independent normals centered on the medians."""
    denom = math.sqrt(sig_a * sig_a + sig_b * sig_b)
    if denom < 1e-9:
        return 0.5 if proj_a == proj_b else (1.0 if proj_a > proj_b else 0.0)
    z = (proj_a - proj_b) / denom
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# --- roster loading and resolution ------------------------------------------

def load_roster(league_id: str,
                dirpath: Optional[str] = None) -> Optional[Dict]:
    """Parse data/rosters/<league>.yaml -> {name, size, players, ...} or None.

    Also carries `source` and `auto_refresh` straight off the file. A roster
    written by the paste importer (engine/espn_public.import_pasted_league)
    stamps `auto_refresh: false` because a private ESPN league cannot be
    re-read: every number downstream is as old as the last paste. That fact
    is useless on disk, so stale_note() turns it into a line every renderer
    puts on the page. A file without the key reads as auto_refresh True -
    the shape every roster yaml predating the field assumed.
    """
    import yaml
    path = os.path.join(dirpath or ROSTER_DIR, "%s.yaml" % league_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("players"), list):
        return None
    names = []
    for raw in data["players"]:
        n = (str(raw.get("name", "")) if isinstance(raw, dict)
             else str(raw or "")).strip()
        if n:
            names.append(n)
    try:
        size = int(data.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return {"name": str(data.get("name") or league_id),
            "size": size or len(names), "players": names, "path": path,
            "source": str(data.get("source") or "").strip().lower(),
            "auto_refresh": data.get("auto_refresh") is not False,
            "stamped_at": str(data.get("pasted_at")
                              or data.get("fetched_at") or "").strip()}


def stale_note(roster: Optional[Dict]) -> str:
    """One line saying this roster does not refresh itself, else ''.

    A frozen roster is COMPLETE, not partial, so no coverage banner fires
    for it - which is exactly how a paste-fed page came to present month-old
    numbers as current. Every renderer that shows a roster calls this.
    """
    if not roster or roster.get("auto_refresh", True):
        return ""
    when = roster.get("stamped_at") or "an unrecorded time"
    src = roster.get("source") or "a manual import"
    return ("%s is PASTE-FED (%s, %s) - it does NOT refresh on its own, so "
            "every number on this page is as old as that paste. Re-paste the "
            "roster after every add, drop or trade."
            % (roster.get("name") or "this roster", src, when))


def resolve_roster(names: List[str], proj: Dict[str, Dict], matcher=None
                   ) -> Tuple[List[Player], Dict[str, Dict], List[str]]:
    """Roster names -> (Player list, meta by player.key, unresolved names).

    Resolution: direct name_key hit into the weekly projections first; the
    fuzzy Matcher (rankings pool) second, which also carries DEF aliases
    ('Seahawks D/ST' == 'Seattle Seahawks') and pos/team for players with
    no weekly number. meta[key]["weekly"] keeps None-vs-0.0 honest: None
    means no projection filed, 0.0 is a filed zero.
    """
    players, meta, unresolved = [], {}, []
    def_by_team = dict((rec["team"], rec) for rec in proj.values()
                       if rec.get("pos") == "DEF" and rec.get("team"))
    for i, raw in enumerate(names):
        name = str(raw).strip()
        if not name:
            continue
        rec = proj.get(name_key(name))
        display, pos, team = name, "", ""
        if rec is None and matcher is not None:
            m = matcher.match(name)
            if m is not None and m.score >= 70:
                display = m.player.name
                pos, team = m.player.pos, m.player.team
                if pos == "DEF" and team in def_by_team:
                    rec = def_by_team[team]
                else:
                    rec = proj.get(name_key(m.player.name))
        if rec is not None:
            pos = rec["pos"]
            team = rec.get("team") or team
        if not pos:
            unresolved.append(name)
            continue
        p = Player(rank=i + 1, name=display, pos=pos, team=team,
                   proj_points=(rec["proj"] if rec else 0.0))
        meta[p.key] = {"weekly": (rec["proj"] if rec else None),
                       "source": (rec.get("source", "") if rec else "")}
        players.append(p)
    return players, meta, unresolved


# --- verdicts and alerts ----------------------------------------------------

def frame_verdict(a: Player, b: Player, sigmas: Dict[str, float],
                  reason: str) -> Tuple[str, int]:
    """The one-line verdict format, plus its confidence percent."""
    sa = sigmas.get(a.pos, 6.0)
    sb = sigmas.get(b.pos, 6.0)
    pa = float(a.proj_points or 0.0)
    pb = float(b.proj_points or 0.0)
    pct = int(round(100.0 * p_first_beats(pa, pb, sa, sb)))
    line = ("Start %s over %s - %d%% - %s median %.1f (%.0f-%.0f) vs "
            "%s %.1f (%.0f-%.0f) - %s"
            % (a.name, b.name, pct, a.surname(), pa, max(0.0, pa - sa),
               pa + sa, b.surname(), pb, max(0.0, pb - sb), pb + sb, reason))
    return line, pct


def _verdict_reason(pct: int, a: Player, b: Player, is_flex: bool,
                    lines: Optional[Dict], injuries: Optional[Dict]) -> str:
    b_status = ((injuries or {}).get(b.nkey) or "").strip().lower()
    if b_status in RED_STATUSES:
        return "%s is %s" % (b.surname(), b_status.upper())
    if pct <= COIN_FLIP_PCT:
        return "coin flip - either call is defensible"
    if lines:
        ia = (lines.get(a.team) or {}).get("implied_total")
        ib = (lines.get(b.team) or {}).get("implied_total")
        if ia is not None and ib is not None and ia - ib >= IMPLIED_GAP:
            return ("%s implied %.1f vs %s %.1f" % (a.team, ia, b.team, ib))
    if b_status in WARN_STATUSES:
        return ("higher median, and %s is %s"
                % (b.surname(), b_status.capitalize()))
    return ("higher median holds the %s" % ("flex" if is_flex else "slot"))


def lineup_verdicts(rows: List[Tuple[str, Optional[Player]]],
                    bench: List[Player], meta: Dict[str, Dict],
                    sigmas: Dict[str, float],
                    lines: Optional[Dict] = None,
                    injuries: Optional[Dict] = None) -> List[Dict]:
    """Verdict framing for every non-obvious call.

    A call is non-obvious when the best eligible bench player projects
    within VERDICT_MARGIN_HARD of a hard-slot starter, or within
    VERDICT_MARGIN_FLEX of a flex starter. Bench players with NO filed
    projection never contest - a made-up 0.0 is not an argument.
    """
    out = []
    for slot, starter in rows:
        if starter is None:
            continue
        elig = FLEX_ELIGIBLE.get(slot)
        is_flex = elig is not None
        margin = VERDICT_MARGIN_FLEX if is_flex else VERDICT_MARGIN_HARD
        cands = [p for p in bench
                 if (p.pos in elig if is_flex else p.pos == slot)
                 and (meta.get(p.key) or {}).get("weekly") is not None]
        if not cands:
            continue
        cand = max(cands, key=lambda p: float(p.proj_points or 0.0))
        gap = float(starter.proj_points or 0.0) - float(cand.proj_points or 0.0)
        if gap > margin:
            continue
        sa = sigmas.get(starter.pos, 6.0)
        sb = sigmas.get(cand.pos, 6.0)
        pct = int(round(100.0 * p_first_beats(
            float(starter.proj_points or 0.0),
            float(cand.proj_points or 0.0), sa, sb)))
        reason = _verdict_reason(pct, starter, cand, is_flex, lines, injuries)
        text, pct = frame_verdict(starter, cand, sigmas, reason)
        out.append({"slot": slot, "a": starter.name, "b": cand.name,
                    "a_key": starter.key, "b_key": cand.key,
                    "pct": pct, "text": text})
    return out


def starter_alerts(rows: List[Tuple[str, Optional[Player]]],
                   meta: Dict[str, Dict], week: int,
                   schedule: Optional[Dict] = None,
                   injuries: Optional[Dict] = None) -> List[Dict]:
    """Red alerts and warnings for the chosen starters.

    RED: on bye (absent from the week's schedule map), filed 0.0
    projection, or an Out/IR-class injury status. WARN: no projection
    filed, or Questionable/Doubtful. Schedule None = feed down, so bye
    detection is skipped (never guessed)."""
    out = []
    for slot, p in rows:
        if p is None:
            continue
        weekly = (meta.get(p.key) or {}).get("weekly")
        status = ((injuries or {}).get(p.nkey) or "").strip()
        if schedule is not None and p.team and p.team not in schedule:
            out.append({"level": "red", "player": p.name, "slot": slot,
                        "text": "%s %s - on BYE (no week-%d game) - replace "
                                "before lock" % (slot, p.name, week)})
        if status.lower() in RED_STATUSES:
            out.append({"level": "red", "player": p.name, "slot": slot,
                        "text": "%s %s - injury status %s - replace before "
                                "lock" % (slot, p.name, status.upper())})
        elif status.lower() in WARN_STATUSES:
            out.append({"level": "warn", "player": p.name, "slot": slot,
                        "text": "%s %s - %s - check status before kickoff"
                                % (slot, p.name, status.capitalize())})
        if weekly == 0.0:
            out.append({"level": "red", "player": p.name, "slot": slot,
                        "text": "%s %s - projects 0.0 this week (injured or "
                                "not playing)" % (slot, p.name)})
        elif weekly is None:
            out.append({"level": "warn", "player": p.name, "slot": slot,
                        "text": "%s %s - no weekly projection filed - verify "
                                "he is active" % (slot, p.name)})
    return out


# --- assembly ---------------------------------------------------------------

def build(league: LeagueConfig, roster_names: List[str], week: int,
          proj: Dict[str, Dict], schedule: Optional[Dict] = None,
          lines: Optional[Dict] = None, injuries: Optional[Dict] = None,
          sigmas: Optional[Dict[str, float]] = None,
          matcher=None, dk_calls: Optional[Dict[str, Dict]] = None) -> Dict:
    """Everything the report needs, as data - tests drive this directly.

    `dk_calls` is engine/dk.weekly_call's {"DST", "K"} result. When given,
    the DEF and K slots' verdicts are the HOLD/STREAM call against the
    wire ("HOLD LAC", "STREAM NE D/ST +1.6 over LAC") instead of a
    projection contest against my own bench - a defense's real
    alternative is the best free one, not my second defense. None keeps
    the plain bench contest (the shape every existing caller gets).
    """
    sigmas = sigmas or dict(DEFAULT_SIGMA)
    players, meta, unresolved = resolve_roster(roster_names, proj, matcher)
    rows, total, missing = best_lineup(league, players)
    started = set(id(p) for _, p in rows if p is not None)
    bench = [p for p in players if id(p) not in started]
    verdicts = lineup_verdicts(rows, bench, meta, sigmas, lines, injuries)
    if dk_calls:
        verdicts = apply_dk_verdicts(verdicts, rows, dk_calls)
    return {
        "rows": rows, "bench": bench, "meta": meta, "total": total,
        "missing": missing, "unresolved": unresolved, "sigmas": sigmas,
        "verdicts": verdicts,
        "alerts": starter_alerts(rows, meta, week, schedule, injuries),
        "dk": dk_calls or None,
    }


def apply_dk_verdicts(verdicts: List[Dict],
                      rows: List[Tuple[str, Optional[Player]]],
                      dk_calls: Dict[str, Dict]) -> List[Dict]:
    """Replace the DEF/K slot verdicts with engine/dk's call (pure).

    A slot with a NO READ call keeps whatever bench contest it had - the
    wire read failing is not a reason to hide a real close call.
    """
    from engine import dk as dk_mod
    out = []
    swapped = set()
    for slot, starter in rows:
        s = norm_pos(slot)
        if s not in dk_mod.SLOT_OF or starter is None:
            continue
        call = (dk_calls or {}).get(dk_mod.SLOT_OF[s])
        v = dk_mod.lineup_verdict(call, slot) if call else None
        if v is None:
            continue
        if not v.get("a_key"):
            v["a_key"] = starter.key
        v["a"] = starter.name if v.get("a") in (None, "") else v["a"]
        out.append(v)
        swapped.add(slot)
    kept = [v for v in verdicts if v.get("slot") not in swapped]
    return kept + out


# --- rendering --------------------------------------------------------------

def _fmt_kickoff(iso: str) -> str:
    if not iso:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso)
        clock = dt.strftime("%I:%M%p").lstrip("0").lower()
        return "%s %s ET" % (dt.strftime("%a %m/%d"), clock)
    except ValueError:
        return iso


def _matchup(p: Player, schedule: Optional[Dict]) -> str:
    if schedule is None or not p.team:
        return ""
    game = schedule.get(p.team)
    if game is None:
        return "BYE"
    return "%s %s" % ("vs" if game.get("home") else "@",
                      game.get("opponent", ""))


def lineup_report(league: LeagueConfig, roster: Optional[Dict], week: int,
                  proj: Dict[str, Dict], schedule: Optional[Dict] = None,
                  lines: Optional[Dict] = None,
                  injuries: Optional[Dict] = None,
                  sigmas: Optional[Dict[str, float]] = None,
                  matcher=None, consensus: Optional[Dict[str, Dict]] = None,
                  color: bool = True, width: int = 74,
                  dk_calls: Optional[Dict[str, Dict]] = None) -> str:
    c = Ansi(color)
    bar, thin = "=" * width, "-" * width
    scoring = league.scoring_label()
    out = [c.cyan(bar),
           c.bold(" LINEUP   %s   week %d   (%s scoring)"
                  % (league.name, week, scoring))]

    if roster is None:
        out.append(c.red(" NO ROSTER FILE: data/rosters/%s.yaml is missing "
                         "or has no players." % league.id))
        out.append(" Create it ({league, name, size, players: [names]}) - "
                   "see data/rosters/.")
        out.append(c.cyan(bar))
        return "\n".join(out)

    names = roster["players"]
    known, size = len(names), roster["size"]
    if known < size:
        out.append(c.yellow(
            " PARTIAL ROSTER: %d of %d players known in %s -"
            % (known, size, os.path.relpath(roster.get("path", ""), HERE)
               if roster.get("path") else "the roster file")))
        out.append(c.yellow(
            " lineup below uses KNOWN players only; an open slot means no "
            "known player fits,"))
        out.append(c.yellow(
            " NOT that the slot is truly empty. Add names as they become "
            "known."))

    b = build(league, names, week, proj, schedule=schedule, lines=lines,
              injuries=injuries, sigmas=sigmas, matcher=matcher,
              dk_calls=dk_calls)

    if b["unresolved"]:
        out.append(c.yellow(" UNRESOLVED: %s - no projection source matched "
                            "these names; fix spelling in the roster file."
                            % ", ".join(b["unresolved"])))
    if schedule is None:
        out.append(c.dim(" (schedule feed unavailable - bye detection and "
                         "kickoff locks skipped, not guessed)"))

    # Starters.
    out.append(thin)
    out.append(c.bold(" STARTERS  (median, range = median +/- 1 sigma of "
                      "weekly projection error)"))
    sigmas = b["sigmas"]
    for slot, p in b["rows"]:
        if p is None:
            out.append(c.dim("   %-6s (open - no known player fits)" % slot))
            continue
        weekly = (b["meta"].get(p.key) or {}).get("weekly")
        sig = sigmas.get(p.pos, 6.0)
        med = float(p.proj_points or 0.0)
        rng = ("%.1f (%.0f-%.0f)" % (med, max(0.0, med - sig), med + sig)
               if weekly is not None else "  no proj filed")
        imp = (lines or {}).get(p.team, {}).get("implied_total")
        garnish = ("imp %.1f" % imp) if imp is not None else ""
        game = (schedule or {}).get(p.team) if schedule is not None else None
        kick = _fmt_kickoff(game["kickoff_iso"]) if game else ""
        row = ("   %-6s %-22s %-10s %-9s %-16s %s"
               % (slot, p.name[:22],
                  ("%s %s" % (p.team, _matchup(p, schedule))).strip()[:10],
                  garnish, rng, kick))
        alert_lv = [a["level"] for a in b["alerts"] if a["player"] == p.name]
        if "red" in alert_lv:
            out.append(c.red(row))
        elif "warn" in alert_lv:
            out.append(c.yellow(row))
        else:
            out.append(row)
    out.append("   filled-slot total: %.1f median pts" % b["total"])

    # Verdicts.
    out.append(thin)
    out.append(c.bold(" VERDICTS  (every call within %.0f pts, %.0f at "
                      "flex - confidence is P(starter outscores bench)%s)"
                      % (VERDICT_MARGIN_HARD, VERDICT_MARGIN_FLEX,
                         "; DEF/K are HOLD-or-STREAM calls against the "
                         "best AVAILABLE one - engine/dk" if dk_calls
                         else "")))
    if not b["verdicts"]:
        out.append("   none - every slot is decided by a clear margin")
    for v in b["verdicts"]:
        out.append("   [%s] %s" % (v["slot"], v["text"]))
        # Consensus strip: one line per voice, then the weighted verdict.
        # Rendered ONLY when consensus data exists for that player - silence
        # (no creator opinion on a bench player) is normal, not degraded.
        for key, who in ((v.get("a_key"), v["a"]), (v.get("b_key"), v["b"])):
            row = (consensus or {}).get(key)
            if not row:
                continue
            try:
                from engine import consensus as consensus_mod
            except ImportError:
                break
            out.append(c.dim("        %s: %s"
                             % (who, consensus_mod.format_voices(row))))
            wline = consensus_mod.format_weighted(row)
            out.append(c.yellow("           %s" % wline)
                       if row.get("top_disagrees") else
                       c.dim("           %s" % wline))

    # Alerts.
    out.append(thin)
    out.append(c.bold(" ALERTS"))
    if not b["alerts"]:
        out.append("   none - no bye, zero-projection, or injury-flagged "
                   "starters")
    for a in b["alerts"]:
        tag = "RED ALERT" if a["level"] == "red" else "WARN     "
        line = "   %s  %s" % (tag, a["text"])
        out.append(c.red(line) if a["level"] == "red" else c.yellow(line))

    # Bench.
    if b["bench"]:
        out.append(thin)
        out.append(c.bold(" BENCH"))
        for p in sorted(b["bench"],
                        key=lambda x: -float(x.proj_points or 0.0)):
            weekly = (b["meta"].get(p.key) or {}).get("weekly")
            out.append("   %-4s %-22s %s"
                       % (p.pos, p.name[:22],
                          ("%.1f" % weekly) if weekly is not None
                          else "no proj filed"))

    # Locks.
    if schedule is not None:
        kicks = []
        for _, p in b["rows"]:
            if p is not None and p.team in schedule:
                kicks.append((schedule[p.team]["kickoff_iso"], p))
        if kicks:
            kicks.sort(key=lambda t: t[0])
            iso, first = kicks[0]
            out.append(thin)
            out.append(" LOCKS: %s kicks off first - %s - decide verdicts "
                       "before then" % (first.name, _fmt_kickoff(iso)))

    out.append(c.cyan(bar))
    return "\n".join(out)


# --- CLI --------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.lineup",
        description="Fill the best legal lineup for a week and frame every "
                    "close call as a verdict.")
    ap.add_argument("--league", default="yahoo-main")
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds, ignoring caches")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args(argv)

    try:
        week = _check_week(args.week)
    except ValueError as exc:
        print(exc)
        return 1

    league_path = os.path.join(HERE, "leagues", "%s.yaml" % args.league)
    if not os.path.exists(league_path):
        print("no league yaml at leagues/%s.yaml" % args.league)
        return 1
    league = LeagueConfig.load(league_path)
    roster = load_roster(args.league)

    from engine import weekly
    try:
        proj = weekly.fetch_weekly_projections(
            week, scoring=league.scoring_label(), force=args.force,
            quiet=True)
    except RuntimeError as exc:
        print("weekly projections unavailable (%s) - cannot build a lineup "
              "without them" % exc)
        return 1
    try:
        schedule = weekly.fetch_schedule(week, force=args.force)
    except RuntimeError:
        schedule = None
    lines = weekly.fetch_game_lines(week, force=args.force) or None

    injuries = None
    try:
        from engine.projections import fetch_injury_status
        injuries = fetch_injury_status(quiet=True)
    except RuntimeError:
        pass

    matcher = None
    try:
        from engine.ingest import Matcher
        csv_path = os.path.join(HERE, league.rankings_csv)
        if os.path.exists(csv_path):
            matcher = Matcher(load_players(csv_path))
    except Exception:
        matcher = None

    # Consensus strips ride along when the room has opinions; a failure to
    # build consensus (dead feeds, no registry) silences the strips - the
    # lineup itself never depends on them.
    consensus = None
    try:
        from engine import consensus as consensus_mod
        consensus = consensus_mod.consensus_map(
            consensus_mod.build_consensus(args.league, week,
                                          force=args.force))
    except Exception:  # noqa: BLE001 - strips are garnish, never a blocker
        consensus = None

    # DEF/K: hold or stream against the wire (engine/dk). Read-only and
    # guarded - a dead wire read leaves the plain bench contest in place.
    dk_calls = None
    if matcher is not None and roster is not None:
        try:
            from engine import dk as dk_mod
            mine, _meta, _unres = resolve_roster(roster["players"], proj,
                                                 matcher)
            dk_calls = dk_mod.weekly_call(league, week, mine,
                                          matcher.players, matcher,
                                          force=args.force)
        except Exception as exc:  # noqa: BLE001 - garnish, never a blocker
            print("(DEF/K stream call unavailable: %s - DEF/K verdicts fall "
                  "back to the bench contest)" % exc)
            dk_calls = None

    color = (not args.no_color) and sys.stdout.isatty()
    print(lineup_report(league, roster, week, proj, schedule=schedule,
                        lines=lines, injuries=injuries,
                        sigmas=position_sigma(), matcher=matcher,
                        consensus=consensus, color=color,
                        dk_calls=dk_calls))
    return 0


if __name__ == "__main__":
    sys.exit(main())
