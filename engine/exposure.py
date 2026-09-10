"""Cross-league exposure flags: players I already roster in my other leagues.

Reads data/rosters/<league-id>.yaml files and answers one question during a
draft: "do I already hold this player somewhere else?" The answer is
FLAG-ONLY and POSITIVE-ONLY:

  * A flag means the player IS known to be on one of my other rosters.
  * NO flag means NO INFORMATION - never "not rostered". Roster files are
    expected to be partial (a few captured names out of a full roster), so
    absence of evidence is not evidence of absence. Callers must never render
    "not rostered elsewhere" from an empty flag list.

Coverage tracking makes the gap visible: each roster file declares its
expected size, and banner_text() produces a one-line warning whenever any
league's known count falls short, so the flag's limits stay on screen.
"""

import glob
import os
from typing import Dict, List, Optional, Tuple

import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.join(HERE, "data", "rosters")

MATCH_THRESHOLD = 70  # same bar intel.py uses for research-doc names


class LeagueRoster(object):
    """One league's known holdings, resolved to player keys."""

    __slots__ = ("league_id", "name", "size", "keys", "unresolved", "path")

    def __init__(self, league_id: str, name: str, size: int, path: str = ""):
        self.league_id = league_id
        self.name = name
        self.size = size
        self.path = path
        self.keys = set()        # resolved player keys
        self.unresolved = []     # names that did not match the pool


class Exposure(object):
    """Flag-only view over my rosters in other leagues.

    Build with Exposure.load(matcher); ask flag(player_key) for the leagues
    known to hold a player. Check .available before rendering the feature at
    all - when False there is no roster data, and showing empty flags would
    read as "not rostered anywhere", which the data cannot support.
    """

    def __init__(self):
        self.leagues = []       # [LeagueRoster] in load order
        self._flags = {}        # player_key -> [league display names]

    # --- construction ------------------------------------------------------
    @classmethod
    def empty(cls) -> "Exposure":
        """No roster data: flag() always [], coverage() [], available False."""
        return cls()

    @classmethod
    def load(cls, matcher, exclude_league_id: Optional[str] = None,
             dirpath: Optional[str] = None) -> "Exposure":
        """Load every roster file in dirpath except the excluded league.

        The league being drafted should be excluded (exclude_league_id) - its
        roster is the live draft board, not outside exposure. Names resolve
        through the fuzzy matcher; ones that miss are collected per league in
        .unresolved rather than crashing or silently vanishing.

        A missing directory or a directory with no valid roster files yields
        Exposure.empty() semantics (available False) so callers can refuse to
        render the feature instead of degrading silently.
        """
        exp = cls()
        dirpath = dirpath or DEFAULT_DIR
        if not os.path.isdir(dirpath):
            return exp

        for path in sorted(glob.glob(os.path.join(dirpath, "*.yaml"))):
            roster = cls._load_file(path, matcher)
            if roster is None:
                continue
            if exclude_league_id and roster.league_id == exclude_league_id:
                continue
            exp.leagues.append(roster)
            for key in roster.keys:
                names = exp._flags.setdefault(key, [])
                if roster.name not in names:
                    names.append(roster.name)
        return exp

    @staticmethod
    def _load_file(path: str, matcher) -> Optional["LeagueRoster"]:
        """Parse one roster yaml; None if it is not a valid roster file."""
        try:
            with open(path, "r") as fh:
                data = yaml.safe_load(fh)
        except (yaml.YAMLError, IOError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        raw_players = data.get("players")
        if not isinstance(raw_players, list):
            return None

        stem = os.path.splitext(os.path.basename(path))[0]
        league_id = str(data.get("league") or stem)
        name = str(data.get("name") or league_id)
        try:
            size = int(data.get("size") or 0)
        except (TypeError, ValueError):
            size = 0

        roster = LeagueRoster(league_id, name, size, path)
        for raw in raw_players:
            pname = str(raw.get("name", "")) if isinstance(raw, dict) else str(raw or "")
            pname = pname.strip()
            if not pname:
                continue
            m = matcher.match(pname)
            if m is None or m.score < MATCH_THRESHOLD:
                roster.unresolved.append(pname)
                continue
            roster.keys.add(m.player.key)
        # size defaults to the listed count so a file without `size` reads
        # as fully known rather than falsely partial.
        if roster.size <= 0:
            roster.size = len(raw_players)
        return roster

    # --- queries -----------------------------------------------------------
    @property
    def available(self) -> bool:
        """True when at least one roster file loaded; gate all rendering on it."""
        return bool(self.leagues)

    def flag(self, player_key: str) -> List[str]:
        """League display names KNOWN to hold this player.

        An empty list means NO INFORMATION - it must never be presented as
        "not rostered elsewhere". Rosters are partial by design (see the
        module docstring); only a positive hit is meaningful.
        """
        return list(self._flags.get(player_key, []))

    def coverage(self) -> List[Tuple[str, int, int]]:
        """(league_display_name, known_count, expected_size) per league."""
        return [(r.name, len(r.keys), r.size) for r in self.leagues]

    def partial(self) -> bool:
        """True if any league's known holdings fall short of its full size."""
        return any(len(r.keys) < r.size for r in self.leagues)

    def unresolved(self) -> List[Tuple[str, List[str]]]:
        """(league_display_name, [names that did not match]) per league."""
        return [(r.name, list(r.unresolved)) for r in self.leagues if r.unresolved]

    def overlap(self, state) -> List[Tuple[object, List[str]]]:
        """Players on MY current roster that are flagged, as (player, leagues).

        For the post-draft / report view: which of my picks double up on
        holdings in other leagues. Uses state.my_roster(); same positive-only
        caveat - an absent player is unknown, not clean.
        """
        out = []
        for player in state.my_roster():
            leagues = self.flag(player.key)
            if leagues:
                out.append((player, leagues))
        return out

    def banner_text(self) -> str:
        """One-line coverage warning when any roster is partial, else ''."""
        gaps = ["%s roster known %d/%d" % (r.name, len(r.keys), r.size)
                for r in self.leagues if len(r.keys) < r.size]
        if not gaps:
            return ""
        return "%s - no flag does NOT mean not rostered" % "; ".join(gaps)

    def __len__(self):
        return len(self._flags)
