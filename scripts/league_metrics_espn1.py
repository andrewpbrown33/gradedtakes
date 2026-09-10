#!/usr/bin/env python
"""Deterministic league metric table for The Original 8 (espn-1), 2026 draft.

Computes, per team, from data/league-espn-1.json + data/rankings-espn.csv:
  1. Best legal starting lineup (QB,2RB,2WR,TE,2FLEX W/R/T,K,DST) greedy by proj.
  2. Juggernaut index per group: RB top3 / WR top3 / QB top1 / TE top1 sums.
  3. Bench points, roster VBD vs engine replacement levels, ADP steals/reaches (>=8).
  4. Bye clusters (>=3 projected starters out same week).
League-wide: rank on each metric + best 3 undrafted per position (waiver scarcity).

Writes data/league-metrics-espn-1.json and prints the table.
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.models import LeagueConfig, DraftState, load_players
from engine.recommend import replacement_levels

LEAGUE_JSON = os.path.join(ROOT, "data", "league-espn-1.json")
RANKINGS = os.path.join(ROOT, "data", "rankings-espn.csv")
LEAGUE_YAML = os.path.join(ROOT, "leagues", "espn-1.yaml")
OUT = os.path.join(ROOT, "data", "league-metrics-espn-1.json")

FLEX_ELIG = ("RB", "WR", "TE")


def norm_pos(p):
    return "DST" if p in ("DEF", "D/ST", "DST") else p


def best_lineup(players):
    """Greedy-by-projection legal lineup. Returns (starters list, total)."""
    pool = sorted(players, key=lambda p: -p["proj"])
    need = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DST": 1}
    slots = []
    used = set()
    # dedicated slots first: take best-by-proj at each position
    for pos, n in need.items():
        cands = [p for p in pool if norm_pos(p["pos"]) == pos][:n]
        for i, p in enumerate(cands):
            slot = pos if n == 1 else "%s%d" % (pos, i + 1)
            slots.append((slot, p))
            used.add(id(p))
    # 2 flex: best remaining RB/WR/TE by projection
    flex = [p for p in pool
            if norm_pos(p["pos"]) in FLEX_ELIG and id(p) not in used][:2]
    for i, p in enumerate(flex):
        slots.append(("FLEX%d" % (i + 1), p))
        used.add(id(p))
    total = sum(p["proj"] for _, p in slots)
    return slots, round(total, 1)


def top_n_sum(players, pos, n):
    projs = sorted((p["proj"] for p in players if norm_pos(p["pos"]) == pos),
                   reverse=True)
    return round(sum(projs[:n]), 1)


def main():
    league_data = json.load(open(LEAGUE_JSON))
    teams = league_data["teams"]

    # rankings board (ADP + pool) and engine replacement levels
    board = list(csv.DictReader(open(RANKINGS)))
    adp_by_name = {r["name"]: float(r["adp"]) for r in board if r["adp"]}

    cfg = LeagueConfig.load(LEAGUE_YAML)
    players = load_players(RANKINGS)
    state = DraftState(cfg, players)
    repl = replacement_levels(state)  # pos -> baseline proj of last starter
    repl = {norm_pos(k): v for k, v in repl.items()}

    drafted_names = set(p["player"] for t in teams.values() for p in t["players"])

    results = {}
    for slot_id in sorted(teams, key=int):
        t = teams[slot_id]
        roster = t["players"]
        starters, start_pts = best_lineup(roster)
        starter_ids = set(id(p) for _, p in starters)

        groups = {
            "RB_top3": top_n_sum(roster, "RB", 3),
            "WR_top3": top_n_sum(roster, "WR", 3),
            "QB_top1": top_n_sum(roster, "QB", 1),
            "TE_top1": top_n_sum(roster, "TE", 1),
        }

        total_proj = round(sum(p["proj"] for p in roster), 1)
        bench_pts = round(total_proj - start_pts, 1)

        vbd = round(sum(p["proj"] - repl[norm_pos(p["pos"])]
                        for p in roster if norm_pos(p["pos"]) in repl), 1)

        steals = reaches = 0
        for p in roster:
            adp = adp_by_name.get(p["player"])
            if adp is None:
                continue
            diff = p["overall"] - adp  # + => fell past ADP (steal)
            if diff >= 8:
                steals += 1
            elif diff <= -8:
                reaches += 1

        byes = Counter(p["bye"] for _, p in starters)
        clusters = sorted((wk, n) for wk, n in byes.items() if n >= 3)

        results[slot_id] = {
            "team": t["name"],
            "slot": int(slot_id),
            "starter_points": start_pts,
            "lineup": [
                {"slot": s, "player": p["player"], "pos": norm_pos(p["pos"]),
                 "nfl": p["nfl"], "bye": p["bye"], "proj": p["proj"]}
                for s, p in starters],
            "groups": groups,
            "total_proj": total_proj,
            "bench_points": bench_pts,
            "vbd_sum": vbd,
            "adp_steals_ge8": steals,
            "adp_reaches_ge8": reaches,
            "bye_clusters": [{"week": wk, "starters_out": n}
                             for wk, n in clusters],
        }

    # league-wide ranks (1 = best; higher value = better on every metric here)
    rank_metrics = ["starter_points", "RB_top3", "WR_top3", "QB_top1",
                    "TE_top1", "bench_points", "vbd_sum", "adp_steals_ge8"]
    vals = {}
    for m in rank_metrics:
        for sid, r in results.items():
            vals.setdefault(m, {})[sid] = (
                r["groups"][m] if m in r["groups"] else r[m])
    ranks = defaultdict(dict)
    for m, d in vals.items():
        order = sorted(d, key=lambda s: -d[s])
        for i, sid in enumerate(order):
            # standard competition ranking on ties
            ranks[sid][m] = 1 + sum(1 for o in d.values() if o > d[sid])
    for sid in results:
        results[sid]["ranks"] = ranks[sid]

    # waiver pool: best 3 undrafted per position by proj_points
    pool = defaultdict(list)
    for r in board:
        if r["name"] in drafted_names or not r["proj_points"]:
            continue
        pool[norm_pos(r["pos"])].append(
            {"player": r["name"], "nfl": r["team"], "bye": int(r["bye"] or 0),
             "proj": float(r["proj_points"]), "rank": int(r["rank"])})
    waiver = {pos: sorted(ps, key=lambda x: -x["proj"])[:3]
              for pos, ps in sorted(pool.items())}

    out = {
        "league": league_data["league"],
        "season": league_data["season"],
        "replacement_levels": {k: round(v, 1) for k, v in sorted(repl.items())},
        "teams": results,
        "waiver_pool_top3": waiver,
        "notes": {
            "lineup_rule": "QB,2RB,2WR,TE,2FLEX(W/R/T),K,DST greedy by projection",
            "vbd": "sum over roster of proj - engine replacement level (pos-matched, negatives kept)",
            "adp": "steal: drafted >=8 picks after ADP; reach: >=8 picks before ADP",
            "bye_cluster": ">=3 projected starters share a bye week",
        },
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2)

    # ---------- print ----------
    W = 118
    print("=" * W)
    print("THE ORIGINAL 8 (espn-1) -- 2026 POST-DRAFT METRIC TABLE  [full PPR, 8-team, lineup QB/2RB/2WR/TE/2FLEX/K/DST]")
    print("=" * W)
    print("Engine replacement levels: " + "  ".join(
        "%s %.1f" % (k, v) for k, v in sorted(repl.items())))
    print("-" * W)
    hdr = ("%-4s %-22s %8s %8s %8s %7s %7s %7s %8s %7s %6s %6s %s"
           % ("Slot", "Team", "Starters", "RBtop3", "WRtop3", "QBtop1",
              "TEtop1", "Bench", "VBDsum", "Steals", "Reach", "TotPrj",
              "ByeClusters"))
    print(hdr)
    print("-" * W)
    order = sorted(results.values(), key=lambda r: -r["starter_points"])
    for r in order:
        g = r["groups"]
        bc = ",".join("wk%d:%d" % (c["week"], c["starters_out"])
                      for c in r["bye_clusters"]) or "-"
        print("%-4d %-22s %8.1f %8.1f %8.1f %7.1f %7.1f %7.1f %8.1f %7d %6d %6.1f %s"
              % (r["slot"], r["team"], r["starter_points"], g["RB_top3"],
                 g["WR_top3"], g["QB_top1"], g["TE_top1"], r["bench_points"],
                 r["vbd_sum"], r["adp_steals_ge8"], r["adp_reaches_ge8"],
                 r["total_proj"], bc))
    print("-" * W)
    print("RANKS (1=best)")
    print("%-4s %-22s %9s %7s %7s %7s %7s %6s %4s %7s"
          % ("Slot", "Team", "Starters", "RBtop3", "WRtop3", "QBtop1",
             "TEtop1", "Bench", "VBD", "Steals"))
    for r in order:
        k = r["ranks"]
        print("%-4d %-22s %9d %7d %7d %7d %7d %6d %4d %7d"
              % (r["slot"], r["team"], k["starter_points"], k["RB_top3"],
                 k["WR_top3"], k["QB_top1"], k["TE_top1"], k["bench_points"],
                 k["vbd_sum"], k["adp_steals_ge8"]))
    print("-" * W)
    print("BEST LINEUPS")
    for r in order:
        lu = "  ".join("%s:%s(%.0f)" % (s["slot"], s["player"], s["proj"])
                       for s in r["lineup"])
        print("%-22s %7.1f | %s" % (r["team"], r["starter_points"], lu))
    print("-" * W)
    print("WAIVER POOL -- best 3 undrafted per position (scarcity left on the wire)")
    for pos, ps in waiver.items():
        row = "  ".join("%s %s (%.1f, rk%d)" % (p["player"], p["nfl"],
                                                p["proj"], p["rank"])
                        for p in ps)
        print("%-4s %s" % (pos, row))
    print("=" * W)
    print("Saved -> %s" % os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
