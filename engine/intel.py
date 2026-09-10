"""Player intel overlay: research theses the engine reasons with.

Keeps hand-written research (conviction buys, fades, injury watches, playoff
schedule) separate from the rankings CSV, so swapping in your own rankings
never loses the intel - and so every adjustment shows its reason on screen.
"""

import os
from typing import Dict, List, Optional, Tuple

import yaml


def _team(value) -> str:
    """Normalize a team code, restoring codes YAML mangled into booleans."""
    if value is False:
        return "NO"
    if value is True:
        return "YES"
    return str(value).strip().upper()


class Intel(object):
    def __init__(self, data: Dict, path: str = ""):
        self.path = path
        self.meta = data.get("meta", {}) or {}
        self.raw_players = list(data.get("players", []) or [])
        sched = data.get("playoff_schedule", {}) or {}
        # str() guards the YAML "Norway problem": an unquoted NO (New Orleans)
        # parses as the boolean False.
        self.playoff_good = set(_team(t) for t in (sched.get("favorable") or []))
        self.playoff_bad = set(_team(t) for t in (sched.get("tough") or []))
        self.playoff_bonus = float(sched.get("bonus", 3))
        self.playoff_from_round = int(sched.get("from_round", 8))

        self.adjust = {}      # player_key -> (points, note)
        self.unresolved = []  # names that did not match the pool
        self.never_draft = {}  # player_key -> reason (hard exclusions)
        self.raw_never = list(data.get("never_draft", []) or [])

        # What each rival manager tends to do - sharpens survival odds, since a
        # generic "does this team need a RB" model misses a manager who always
        # reaches for his own city's players.
        self.managers = {}     # slot -> {"positions": set, "teams": set, "note": str}
        for row in (data.get("managers", []) or []):
            slot = row.get("slot")
            if not slot:
                continue
            self.managers[int(slot)] = {
                "name": row.get("name", "Team %s" % slot),
                "positions": set(_team(p) for p in (row.get("favors_positions") or [])),
                "teams": set(_team(t) for t in (row.get("favors_teams") or [])),
                "note": row.get("note", "") or "",
                "reach": float(row.get("reach", 0) or 0),
            }

    @classmethod
    def load(cls, path: str) -> "Intel":
        with open(path, "r") as fh:
            return cls(yaml.safe_load(fh) or {}, path)

    @classmethod
    def empty(cls) -> "Intel":
        return cls({})

    def resolve(self, matcher, players=None) -> None:
        """Bind intel to the player pool and stamp notes onto the players."""
        for row in self.raw_players:
            name = row.get("name")
            if not name:
                continue
            m = matcher.match(name)
            if m is None or m.score < 70:
                self.unresolved.append(name)
                continue
            pts = float(row.get("adjust", 0) or 0)
            note = row.get("note", "") or ""
            self.adjust[m.player.key] = (pts, note)
            if note and not m.player.notes:
                m.player.notes = note

        for row in self.raw_never:
            name = row.get("name") if isinstance(row, dict) else str(row)
            if not name:
                continue
            m = matcher.match(name)
            if m is None or m.score < 70:
                self.unresolved.append(name)
                continue
            reason = (row.get("reason", "") if isinstance(row, dict) else "") \
                or "on my never-draft list"
            self.never_draft[m.player.key] = reason

    def merge(self, other: "Intel", matcher) -> int:
        """Layer another intel file on top. The later file wins outright.

        Used for the user's own calls, which override the research doc rather
        than averaging with it - an explicit opinion is a replacement, not a
        second vote.
        """
        other.resolve(matcher)
        overridden = 0
        for key, (pts, note) in other.adjust.items():
            if key in self.adjust:
                overridden += 1
            self.adjust[key] = (pts, note)
        self.unresolved.extend(other.unresolved)
        if other.playoff_good or other.playoff_bad:
            self.playoff_good = other.playoff_good
            self.playoff_bad = other.playoff_bad
        self.never_draft.update(other.never_draft)
        self.managers.update(other.managers)
        return overridden

    def for_player(self, key: str) -> Optional[Tuple[float, str]]:
        return self.adjust.get(key)

    def manager_appetite(self, slot: int, player) -> float:
        """How much more likely this manager is to take this player, 0 = no read.

        Returns a 0..1 bump folded into the survival hazard.
        """
        m = self.managers.get(slot)
        if not m:
            return 0.0
        bump = 0.0
        if player.pos in m["positions"]:
            bump += 0.6
        if player.team and player.team in m["teams"]:
            bump += 0.5
        return min(1.0, bump)

    def manager_note(self, slot: int) -> str:
        m = self.managers.get(slot)
        return m["note"] if m else ""

    def playoff_adjust(self, player, rnd: int) -> Tuple[float, str]:
        """Weeks 15-17 slate: a late-round tiebreaker, never a headline reason."""
        if rnd < self.playoff_from_round or not player.team:
            return 0.0, ""
        if player.team in self.playoff_good:
            return self.playoff_bonus, "easy Wk15-17 slate"
        if player.team in self.playoff_bad:
            return -self.playoff_bonus, "tough Wk15-17 slate"
        return 0.0, ""

    def __len__(self):
        return len(self.adjust)
