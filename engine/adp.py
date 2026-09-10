"""Fetch ADP from Fantasy Football Calculator's free API and cache it on disk.

Used to seed data/rankings.csv so the war room works before Andrew's own
rankings CSV is dropped in. Runs on the standard library only.
"""

import csv
import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# FFC labels kickers "PK" and defenses "DEF"; we normalize to K/DEF everywhere.
POS_MAP = {"PK": "K", "DST": "DEF", "D/ST": "DEF"}


def normalize_pos(pos: str) -> str:
    p = (pos or "").strip().upper()
    return POS_MAP.get(p, p)


def cache_path(scoring: str, teams: int, year: int) -> str:
    return os.path.join(CACHE_DIR, "ffc-%s-%dteam-%d.json" % (scoring, teams, year))


def fetch(scoring: str = "ppr", teams: int = 10, year: int = 2026,
          max_age_hours: float = 6.0, quiet: bool = False) -> List[Dict]:
    """Return FFC ADP rows. Uses a disk cache; falls back to stale cache offline."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(scoring, teams, year)

    if os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            with open(path, "r") as fh:
                return json.load(fh)["players"]

    url = ("https://fantasyfootballcalculator.com/api/v1/adp/%s"
           "?teams=%d&year=%d&position=all" % (scoring, teams, year))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.load(resp)
        if not payload.get("players"):
            raise ValueError("FFC returned no players")
        with open(path, "w") as fh:
            json.dump(payload, fh)
        if not quiet:
            meta = payload.get("meta", {})
            print("  ADP: %d players from FFC (%s, %d-team, %s to %s)" % (
                len(payload["players"]), meta.get("type", scoring), teams,
                meta.get("start_date", "?"), meta.get("end_date", "?")))
        return payload["players"]
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            if not quiet:
                print("  ADP fetch failed (%s) - using cached copy" % type(exc).__name__)
            with open(path, "r") as fh:
                return json.load(fh)["players"]
        raise RuntimeError("Could not fetch ADP and no cache exists: %s" % exc)


def assign_tiers(rows: List[Dict]) -> Dict[str, int]:
    """Derive tiers per position from ADP gaps. Returns {player_key: tier}."""
    by_pos = {}
    for r in rows:
        by_pos.setdefault(normalize_pos(r["position"]), []).append(r)

    tiers = {}
    for pos, players in by_pos.items():
        players.sort(key=lambda p: float(p["adp"]))
        tier = 1
        size = 0
        prev_adp = None
        for p in players:
            adp = float(p["adp"])
            if prev_adp is not None:
                gap = adp - prev_adp
                # A real cliff, or a tier that has grown unwieldy, starts a new tier.
                if gap > max(4.0, 0.08 * prev_adp) or size >= 8:
                    tier += 1
                    size = 0
            tiers["%s|%s" % (p["name"], pos)] = tier
            size += 1
            prev_adp = adp
    return tiers


def seed_rankings_csv(dest: str, scoring: str = "ppr", teams: int = 10,
                      year: int = 2026, quiet: bool = False) -> int:
    """Write a starter rankings CSV from FFC ADP. Returns the row count."""
    rows = fetch(scoring, teams, year, quiet=quiet)
    rows = sorted(rows, key=lambda r: float(r["adp"]))
    tiers = assign_tiers(rows)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "name", "pos", "team", "bye", "tier", "adp", "adp_stdev",
                    "proj_points", "notes", "flags"])
        for i, r in enumerate(rows, start=1):
            pos = normalize_pos(r["position"])
            w.writerow([i, r["name"], pos, r.get("team", ""), r.get("bye", "") or "",
                        tiers.get("%s|%s" % (r["name"], pos), 1),
                        r["adp"], r.get("stdev", "") or "", "", "", ""])
    return len(rows)


if __name__ == "__main__":
    dest = os.path.join(HERE, "data", "rankings.csv")
    n = seed_rankings_csv(dest)
    print("Wrote %d players to %s" % (n, dest))
