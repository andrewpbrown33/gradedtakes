"""Fetch Boris Chen's expert-consensus tiers and cache them on disk.

borischen.co clusters FantasyPros expert consensus ranks with a Gaussian
mixture model, which draws far better tier breaks than our ADP-gap heuristic.
The plain-text output files live on S3 as lines like

    Tier 1: Josh Allen, Lamar Jackson, Drake Maye

RB/WR/TE/FLX come in PPR and HALF flavors; QB/K/DST are format-free.
Runs on the standard library only. Run manually with `python -m engine.tiers`.
"""

import csv
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from .ingest import NFL_TEAMS
from .models import HEADER_ALIASES, norm_name, norm_pos

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "data", "cache")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

BASE_URL = "https://s3-us-west-1.amazonaws.com/fftiers/out/text_%s.txt"

# FLX goes first so the positional files win any name conflicts on merge.
FETCH_ORDER = ["FLX", "RB", "WR", "TE", "QB", "K", "DST"]
FORMAT_FREE = {"QB", "K", "DST"}
SCORING_FMT = {"ppr": "PPR", "half-ppr": "HALF", "half": "HALF"}

TIER_LINE = re.compile(r"^\s*Tier\s+(\d+)\s*:\s*(.+)$", re.I | re.M)


def _norm(name: str) -> str:
    """norm_name with diacritics folded first, so Pineiro matches Piñeiro."""
    folded = unicodedata.normalize("NFKD", name or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return norm_name(folded)


def _file_stem(pos: str, scoring: str) -> str:
    """'RB' + 'ppr' -> 'RB-PPR'; QB/K/DST carry no format suffix."""
    if pos in FORMAT_FREE:
        return pos
    fmt = SCORING_FMT.get((scoring or "").strip().lower())
    if fmt is None:
        raise ValueError("Unknown scoring '%s' (want: %s)"
                         % (scoring, ", ".join(sorted(SCORING_FMT))))
    return "%s-%s" % (pos, fmt)


def cache_path(stem: str) -> str:
    return os.path.join(CACHE_DIR, "chen-%s.txt" % stem)


def _fetch_text(stem: str, max_age_hours: float = 6.0, force: bool = False,
                quiet: bool = False) -> str:
    """Return one tier file's text. Disk cache; stale-cache fallback offline."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(stem)

    if not force and os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h < max_age_hours:
            with open(path, "r") as fh:
                return fh.read()

    url = BASE_URL % stem
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            text = resp.read().decode("utf-8", "replace")
        if not TIER_LINE.search(text):
            raise ValueError("no 'Tier N:' lines in %s" % url)
        with open(path, "w") as fh:
            fh.write(text)
        return text
    except (urllib.error.URLError, ValueError, OSError) as exc:
        if os.path.exists(path):
            if not quiet:
                print("  Tiers fetch failed for %s (%s) - using cached copy"
                      % (stem, type(exc).__name__))
            with open(path, "r") as fh:
                return fh.read()
        raise RuntimeError("Could not fetch Chen tiers '%s' and no cache "
                           "exists: %s" % (stem, exc))


def parse_tier_text(text: str) -> List[Tuple[int, List[str]]]:
    """'Tier 1: A, B' lines -> [(1, ['A', 'B']), ...]."""
    out = []
    for line in text.splitlines():
        m = TIER_LINE.match(line)
        if not m:
            continue
        names = [n.strip() for n in m.group(2).split(",") if n.strip()]
        if names:
            out.append((int(m.group(1)), names))
    return out


def _dst_abbr(raw_name: str) -> Optional[str]:
    """'San Francisco 49ers' / '49ers' -> 'SF' via the ingest alias table."""
    q = _norm(raw_name)
    best, best_len = None, 0
    for abbr, aliases in NFL_TEAMS.items():
        for alias in aliases + [abbr.lower()]:
            a = _norm(alias)
            if a and (q == a or (" %s " % a) in (" %s " % q)):
                if len(a) > best_len:
                    best, best_len = abbr, len(a)
    return best


def _dst_keys(raw_name: str) -> List[str]:
    """Every normalized alias a defense might appear under in our pool.

    Chen says 'Los Angeles Rams'; our pool says 'LA Rams Defense'. Emit the
    ingest aliases plus Defense/Def/DST-suffixed forms so both sides hit.
    """
    bases = [raw_name]
    abbr = _dst_abbr(raw_name)
    if abbr:
        bases.extend(NFL_TEAMS[abbr] + [abbr])
    keys = []
    for base in bases:
        for suffix in ("", " defense", " def", " dst", " d/st"):
            k = _norm(base + suffix)
            if k and k not in keys:
                keys.append(k)
    return keys


def fetch(scoring: str = "ppr", force: bool = False,
          max_age_hours: float = 6.0, quiet: bool = False) -> Dict[str, int]:
    """Return {normalized_name: tier} merged across all positions.

    FLX is merged first, so RB/WR/TE tiers from the positional files win on
    conflict. DST entries are fanned out to every team alias (see _dst_keys).
    """
    tiers = {}
    for pos in FETCH_ORDER:
        stem = _file_stem(pos, scoring)
        text = _fetch_text(stem, max_age_hours, force=force, quiet=quiet)
        for tier, names in parse_tier_text(text):
            for name in names:
                keys = _dst_keys(name) if pos == "DST" else [_norm(name)]
                for key in keys:
                    if key:
                        tiers[key] = tier
    if not quiet:
        print("  Tiers: Boris Chen %s, %d files, %d name keys"
              % (scoring, len(FETCH_ORDER), len(tiers)))
    return tiers


def apply_to_csv(csv_path: str, scoring: str = "ppr", force: bool = False,
                 quiet: bool = False) -> int:
    """Overwrite the tier column in a rankings CSV with Chen tiers, in place.

    Unmatched rows keep their existing (ADP-gap) tier, so an offline run with
    no cache degrades to a no-op rather than wrecking the file. Returns the
    number of rows updated.
    """
    tiers = fetch(scoring, force=force, quiet=quiet)

    with open(csv_path, "r", newline="") as fh:
        rows = [r for r in csv.reader(fh)]
    if not rows:
        raise ValueError("Rankings CSV %s is empty" % csv_path)

    header = [c.strip().lower() for c in rows[0]]
    col = {}
    for field in ("name", "pos", "team", "tier"):
        for i, h in enumerate(header):
            if h in HEADER_ALIASES[field]:
                col[field] = i
                break
    for required in ("name", "tier"):
        if required not in col:
            raise ValueError("Rankings CSV needs a '%s' column. Found: %s"
                             % (required, ", ".join(header)))

    matched = 0
    for row in rows[1:]:
        if col["name"] >= len(row) or col["tier"] >= len(row):
            continue
        tier = tiers.get(_norm(row[col["name"]]))
        if tier is None and "pos" in col and "team" in col \
                and col["pos"] < len(row) and col["team"] < len(row) \
                and norm_pos(row[col["pos"]]) == "DEF":
            tier = tiers.get(_norm(row[col["team"]]))
        if tier is not None:
            row[col["tier"]] = str(tier)
            matched += 1

    with open(csv_path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    if not quiet:
        print("  Tiers: %d of %d rows updated in %s"
              % (matched, len(rows) - 1, csv_path))
    return matched


if __name__ == "__main__":
    dest = os.path.join(HERE, "data", "rankings.csv")
    n = apply_to_csv(dest)
    print("Applied Chen tiers to %d players in %s" % (n, dest))
