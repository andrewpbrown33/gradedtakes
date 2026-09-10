#!/usr/bin/env python3
"""Calibration harness - a TOOL, not a test suite.

This does NOT run as part of the standard 8 suites. It backtests the
survival model against drafts that actually happened and gives the
projection blend one honest sanity number.

    .venv/bin/python tests/calibration.py                    # real saves + a fresh 160-pick practice draft
    .venv/bin/python tests/calibration.py --saves 'saves/yahoo-main-*.json'
    .venv/bin/python tests/calibration.py --no-practice      # skip the generated draft
    .venv/bin/python tests/calibration.py --espn-history     # also try historical ESPN league drafts (needs cookies)

WHAT THE SURVIVAL BACKTEST DOES
  Replay each save pick-by-pick. At every vantage pick v (board = picks
  1..v-1), take a one-round horizon h = v + teams and ask the live model:
  "P(player survives from v to h)?" for (a) the player actually picked at v
  and (b) a rank-spread sample of still-available players. The outcome is
  observable: picked by a rival inside [v, h-1] -> 0, untouched -> 1, picked
  by MY slot -> sample dropped (the model never counts me as a threat, so
  that counterfactual is contaminated). Predictions come from
  engine.recommend.survival_odds with intel=None (base curve + roster need;
  manager-tendency bumps are out of scope here).

HONESTY NOTES (also printed with results)
  - Predictions use TODAY'S rankings.csv ADP/stdev, not draft-day values.
  - The real yahoo save is 33 picks: small-n, deciles are thin.
  - The practice draft's rivals are ADP-driven bots, i.e. partly
    self-fulfilling for an ADP-based model - expect flattering calibration.
  - The refit suggestion is REPORT ONLY. Nothing is auto-applied.
"""

import argparse
import glob as globlib
import json
import math
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import state as save_state                          # noqa: E402
from engine.models import (DraftState, LeagueConfig, Pick,      # noqa: E402
                           load_players)
from engine.recommend import (_p_still_there, effective_adp,    # noqa: E402
                              effective_scale, survival_odds,
                              team_needs_pos)

LINE = "=" * 74


# --- survival model, re-derivable under a scale multiplier ------------------
def predict(now, horizon, adp, scale, exponent, mult=1.0):
    """Mirror of survival_odds() math with an adjustable spread multiplier.

    mult=1.0 must reproduce the live model exactly (cross-checked at
    runtime); other mults power the refit grid search.
    """
    s = scale * mult
    p_now = _p_still_there(now - 0.5, adp, s)
    p_then = _p_still_there(horizon - 0.5, adp, s)
    if p_now <= 1e-6:
        base = 0.02 if horizon - now > 6 else 0.15
    else:
        base = max(0.0, min(1.0, p_then / p_now))
    if exponent is not None:
        base = base ** exponent
    return max(0.0, min(1.0, base))


# --- backtest over one save -------------------------------------------------
def load_league_for_save(data):
    path = data.get("league_path") or ""
    if not path or not os.path.exists(path):
        guess = os.path.join(HERE, "leagues", "%s.yaml" % data.get("league_id"))
        path = guess if os.path.exists(guess) else \
            os.path.join(HERE, "leagues", "yahoo-main.yaml")
    league = LeagueConfig.load(path)
    if data.get("teams"):
        league.teams = int(data["teams"])
    if data.get("my_slot"):
        league.my_slot = int(data["my_slot"])
    if data.get("rounds"):
        league.rounds = int(data["rounds"])
    return league


def collect_samples(data):
    """Replay one save; return (samples, n_picks, n_cross_mismatch).

    Each sample: dict(now, h, adp, scale, exponent, pred, outcome, name, pos).
    pred is the LIVE survival_odds output; (adp, scale, exponent) let the
    refit grid recompute it under a different spread multiplier.
    """
    league = load_league_for_save(data)
    players = load_players(os.path.join(HERE, league.rankings_csv))
    state = DraftState(league, players)

    rows = sorted(data.get("picks", []), key=lambda r: int(r["overall"]))
    board = {}
    for r in rows:
        board[int(r["overall"])] = (r["player_key"], int(r["team"]))
    if not board:
        return [], 0, 0
    n_total = max(board)
    teams = league.teams
    my_slot = league.my_slot

    samples, mismatch = [], 0
    for v in range(1, n_total + 1):
        h = v + teams
        if h <= n_total + 1 and v in board:
            avail = [p for p in state.players if p.key not in state.drafted]
            avail.sort(key=lambda p: p.rank)
            cands = avail[:12] + avail[12:52:4]
            nxt = state.by_key.get(board[v][0])
            if nxt is not None and nxt.key not in state.drafted and nxt not in cands:
                cands.append(nxt)

            between = [state.team_at(n) for n in range(v, h)
                       if state.team_at(n) != my_slot]
            tb = sorted(set(between))
            for p in cands:
                outcome, dropped = 1, False
                for n in range(v, h):
                    row = board.get(n)
                    if row and row[0] == p.key:
                        if my_slot is not None and row[1] == my_slot:
                            dropped = True
                        else:
                            outcome = 0
                        break
                if dropped:
                    continue
                if tb:
                    needy = sum(1.0 for t in tb if team_needs_pos(state, t, p.pos))
                    exponent = 0.85 + 0.5 * (needy / float(len(tb)))
                else:
                    exponent = None
                pred = survival_odds(state, p, horizon=h)  # the LIVE model
                mine = predict(v, h, effective_adp(p), effective_scale(p),
                               exponent)
                if abs(pred - mine) > 1e-9:
                    mismatch += 1
                samples.append({
                    "now": v, "h": h, "adp": effective_adp(p),
                    "scale": effective_scale(p), "exponent": exponent,
                    "pred": pred, "outcome": outcome,
                    "name": p.name, "pos": p.pos,
                })

        # now actually place pick v (mirrors state.restore: placeholders and
        # unknown keys still occupy their overall so the board never shifts)
        if v in board:
            key, team = board[v]
            pk = Pick(v, team, key, "")
            state.picks[v] = pk
            if key in state.by_key:
                state.drafted[key] = pk
    return samples, n_total, mismatch


# --- scoring ----------------------------------------------------------------
def brier(samples, mult=None):
    if not samples:
        return float("nan")
    tot = 0.0
    for s in samples:
        p = s["pred"] if mult is None else predict(
            s["now"], s["h"], s["adp"], s["scale"], s["exponent"], mult)
        tot += (p - s["outcome"]) ** 2
    return tot / len(samples)


def reliability_lines(samples):
    bins = [[] for _ in range(10)]
    for s in samples:
        i = min(9, int(s["pred"] * 10))
        bins[i].append(s)
    out = ["  decile        n   avg-pred   observed      gap",
           "  " + "-" * 47]
    for i, b in enumerate(bins):
        label = "%2d-%3d%%" % (i * 10, (i + 1) * 10)
        if not b:
            out.append("  %-9s %5d       -          -        -" % (label, 0))
            continue
        ap = sum(s["pred"] for s in b) / len(b)
        ob = sum(s["outcome"] for s in b) / float(len(b))
        out.append("  %-9s %5d    %6.3f     %6.3f   %+7.3f"
                   % (label, len(b), ap, ob, ob - ap))
    return out


def refit_lines(samples):
    grid = [round(0.80 + 0.05 * i, 2) for i in range(17)]  # 0.80 .. 1.60
    scored = [(m, brier(samples, m)) for m in grid]
    best = min(scored, key=lambda x: x[1])
    cur = brier(samples)
    out = ["  refit grid (scale multiplier -> Brier):"]
    row = "   "
    for m, b in scored:
        cell = " %4.2fx:%.4f" % (m, b)
        if len(row) + len(cell) > 76:
            out.append(row)
            row = "   "
        row += cell
    out.append(row)
    out.append("  current (1.00x) Brier %.4f | best %.2fx -> Brier %.4f"
               % (cur, best[0], best[1]))
    out.append("  REPORT ONLY - no multiplier has been applied to the engine.")
    return out


def survival_report(title, data, extra_notes=()):
    print("\n%s\nSURVIVAL BACKTEST: %s\n%s" % (LINE, title, LINE))
    samples, n_picks, mismatch = collect_samples(data)
    picked = len(data.get("picks", []))
    print("  picks in save: %d | vantage points with a full observable" % picked)
    print("  one-round window: %d | samples: %d (outcome base rate %.3f)"
          % (max(0, n_picks - int(data.get("teams") or 10) + 1),
             len(samples),
             (sum(s["outcome"] for s in samples) / float(len(samples)))
             if samples else float("nan")))
    for note in extra_notes:
        print("  NOTE: %s" % note)
    print("  NOTE: predictions use TODAY'S rankings.csv ADP, not draft-day ADP.")
    print("  NOTE: intel/manager tendencies excluded (intel=None).")
    if mismatch:
        print("  WARNING: %d samples disagreed with the local re-derivation "
              "(refit grid suspect)." % mismatch)
    if not samples:
        print("  no usable samples - skipped.")
        return None
    print()
    for ln in reliability_lines(samples):
        print(ln)
    print("\n  Brier score: %.4f  (predicting the base rate every time "
          "would score %.4f)" % (brier(samples), _base_rate_brier(samples)))
    print()
    for ln in refit_lines(samples):
        print(ln)
    return samples


def _base_rate_brier(samples):
    base = sum(s["outcome"] for s in samples) / float(len(samples))
    return sum((base - s["outcome"]) ** 2 for s in samples) / len(samples)


# --- projection backtest stub ----------------------------------------------
def spearman(pairs):
    """Spearman-lite by hand: Pearson on average-ranked data (tie-aware)."""
    def avg_ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            r = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = r
            i = j + 1
        return ranks

    xs = avg_ranks([p[0] for p in pairs])
    ys = avg_ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def projection_backtest():
    print("\n%s\nPROJECTION BACKTEST (STUB)\n%s" % (LINE, LINE))
    try:
        from engine.nflverse import fetch_xfp
        xfp = fetch_xfp(2025)
    except Exception as exc:
        print("  could not load 2025 xFP data: %s - skipped." % exc)
        return
    players = load_players(os.path.join(HERE, "data", "rankings.csv"))
    pairs = []
    for p in players:
        if p.proj_points is None:
            continue
        weeks = xfp.get(p.nkey)
        if not weeks:
            continue
        actual = sum(w["actual"] for w in weeks)
        pairs.append((float(p.proj_points), actual))
    if len(pairs) < 10:
        print("  only %d joined players - skipped." % len(pairs))
        return
    rho = spearman(pairs)
    print("  Spearman-lite rho: %.3f  (blend proj_points vs 2025 actual "
          "season points, n=%d)" % (rho, len(pairs)))
    print("  CAVEAT: this is a STUB and an optimistic number - the 2026 blend")
    print("  is partly built FROM 2025 outcomes, and 2025 actuals are not a")
    print("  2026 backtest. It exists to catch gross ordering breakage only.")


# --- ESPN history mode ------------------------------------------------------
def espn_history():
    print("\n%s\nESPN HISTORY MODE\n%s" % (LINE, LINE))
    try:
        from engine import espn
        lg = espn.connect()
    except Exception as exc:
        print("  needs cookies (RUNBOOK A3) - ESPN history unavailable: %s"
              % exc)
        return
    try:
        from engine.ingest import Matcher
        facts = espn.league_facts(lg)
        picks = espn.draft_picks(lg)
        if len(picks) < 30:
            print("  ESPN draft feed has %d picks (<30) - skipped."
                  % len(picks))
            return
        teams = int(facts.get("teams") or 10)
        league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                                "yahoo-main.yaml"))
        players = load_players(os.path.join(HERE, "data", "rankings.csv"))
        matcher = Matcher(players)
        rows = []
        for pk in picks:
            m = matcher.match(pk["name"]) if pk.get("name") else None
            key = m.player.key if m is not None else "__skipped__"
            team = ((pk["overall"] - 1) % (2 * teams))
            team = team + 1 if team < teams else 2 * teams - team
            rows.append({"overall": pk["overall"], "team": team,
                         "player_key": key, "raw": pk.get("name", "")})
        data = {"league_id": "espn-history", "league_path": league.path,
                "teams": teams, "rounds": int(facts.get("rounds") or 16),
                "my_slot": None, "picks": rows}
        survival_report(
            "ESPN historical draft (%d picks)" % len(rows), data,
            extra_notes=["historical league draft consumed live from ESPN - "
                         "name matching is best-effort; unmatched picks hold "
                         "placeholders."])
    except Exception as exc:
        print("  ESPN history fetch failed after connect: %s" % exc)


# --- practice-draft generation (tempdir-isolated) ---------------------------
def generate_practice_save(seed=20260829):
    """Run rehearse.py's bots for a full 160-pick draft, save it through the
    real save path with SAVE_DIR redirected to a tempdir, and return the
    parsed save JSON. Production saves/ is never touched."""
    import rehearse  # bots only; its interactive loop is __main__-guarded

    real_save_dir = save_state.SAVE_DIR
    tmpdir = tempfile.mkdtemp(prefix="calibration-saves-")
    save_state.SAVE_DIR = tmpdir
    try:
        league = LeagueConfig.load(os.path.join(HERE, "leagues",
                                                "yahoo-main.yaml"))
        league.id = "calib-practice"
        players = load_players(os.path.join(HERE, league.rankings_csv))
        state = DraftState(league, players)
        rng = random.Random(seed)
        temperament = dict((t, rng.uniform(2, 11))
                           for t in range(1, league.teams + 1))
        while not state.is_complete():
            team = state.on_the_clock()
            p = rehearse.bot_choice(state, team, rng, temperament)
            state.apply_pick(p)
        path = save_state.save(state)
        with open(path) as fh:
            return json.load(fh)
    finally:
        save_state.SAVE_DIR = real_save_dir
        shutil.rmtree(tmpdir, ignore_errors=True)


# --- driver -----------------------------------------------------------------
def dedupe_saves(paths):
    """Same draft saved on different days = same data; keep the newest only."""
    seen, keep = {}, []
    for path in sorted(paths, key=os.path.getmtime, reverse=True):
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (IOError, ValueError) as exc:
            print("  skipping unreadable save %s (%s)" % (path, exc))
            continue
        sig = tuple((int(r["overall"]), r["player_key"])
                    for r in sorted(data.get("picks", []),
                                    key=lambda r: int(r["overall"])))
        if sig in seen:
            print("  %s duplicates %s - skipped." % (
                os.path.basename(path), os.path.basename(seen[sig])))
            continue
        seen[sig] = path
        keep.append((path, data))
    return keep


def main():
    ap = argparse.ArgumentParser(
        description="Calibration harness (tool, not a suite)")
    ap.add_argument("--saves", default=os.path.join(HERE, "saves",
                                                    "yahoo-main-*.json"),
                    help="glob of save JSONs to backtest")
    ap.add_argument("--espn-history", action="store_true",
                    help="also consume historical ESPN league drafts "
                         "(needs cookies, RUNBOOK A3)")
    ap.add_argument("--no-practice", action="store_true",
                    help="skip the generated 160-pick practice draft")
    ap.add_argument("--seed", type=int, default=20260829)
    args = ap.parse_args()

    print(LINE)
    print("CALIBRATION HARNESS - survival + projection backtests (report only)")
    print(LINE)

    paths = [p for p in globlib.glob(args.saves) if not p.endswith(".tmp")]
    if not paths:
        print("  no saves match %s" % args.saves)
    for path, data in dedupe_saves(paths):
        n = len(data.get("picks", []))
        if n < 30:
            print("  %s has %d picks (<30) - skipped." %
                  (os.path.basename(path), n))
            continue
        notes = []
        if n < 60:
            notes.append("SMALL-N: only %d real picks - deciles are thin, "
                         "treat gaps as directional, not gospel." % n)
        survival_report(os.path.basename(path), data, extra_notes=notes)

    if not args.no_practice:
        data = generate_practice_save(seed=args.seed)
        survival_report(
            "generated practice draft (%d picks, rehearse bots, seed %d)"
            % (len(data.get("picks", [])), args.seed), data,
            extra_notes=["rival bots draft BY ADP, the same signal the model "
                         "predicts from - calibration here is flattering by "
                         "construction."])

    projection_backtest()

    if args.espn_history:
        espn_history()

    print("\n%s\ndone. nothing was refit, nothing was written outside "
          "tempdirs.\n%s" % (LINE, LINE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
