"""Core data model: players, league config, and live draft state."""

import csv
import os
import re
import unicodedata
from typing import Dict, List, Optional

import yaml

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
FLEX_ELIGIBLE = {"W/R/T": ["WR", "RB", "TE"], "W/R": ["WR", "RB"],
                 "W/T": ["WR", "TE"], "R/W/T": ["WR", "RB", "TE"],
                 "FLEX": ["WR", "RB", "TE"], "Q/W/R/T": ["QB", "WR", "RB", "TE"],
                 "SUPERFLEX": ["QB", "WR", "RB", "TE"]}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_path(path: str) -> str:
    """A file path as it may safely appear in a message someone else reads.

    Every "which file is missing" string in this project can reach a
    PUBLISHED page. publish.py puts a failed renderer's last two lines of
    output into that person's index.html and heartbeat.json, and
    engine/home.py puts the exception text straight onto the league card.
    An absolute path there hands the reader the owner's macOS username and
    home directory - who is running this and where - and none of that is
    part of the answer to "which file is missing".

    Inside the repo the answer is the repo-relative path, which is also
    the more useful one (it is what the runbook and the commands use).
    Anywhere else - a sandbox, a --root override, a temp dir - it is the
    basename alone, because the directory is the part that identifies a
    machine.
    """
    text = str(path or "")
    if not text:
        return text
    try:
        rel = os.path.relpath(os.path.abspath(text), REPO_ROOT)
    except (ValueError, OSError):
        return os.path.basename(text)
    if os.path.isabs(rel) or rel.split(os.sep)[0] == os.pardir:
        return os.path.basename(text)
    return rel


def norm_name(name: str) -> str:
    """Lowercase, strip punctuation and generational suffixes for matching.

    Accents are NFKD-folded to ASCII first ('Piñeiro' == 'Pineiro'): the old
    regex dropped non-ASCII letters outright, so accented and plain spellings
    of the same name produced different keys, and any data source that spells
    a name the other way (nflverse ECR, games-played files) silently missed.
    This is THE one name normalizer - every fetcher and Player key goes
    through it, so cross-source joins cannot disagree about folding.
    """
    s = unicodedata.normalize("NFKD", name or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", "", s)
    tokens = [t for t in s.split() if t and t not in SUFFIXES]
    return " ".join(tokens)


def norm_pos(pos: str) -> str:
    p = (pos or "").strip().upper()
    return {"PK": "K", "DST": "DEF", "D/ST": "DEF", "DS": "DEF"}.get(p, p)


class Player(object):
    __slots__ = ("rank", "name", "pos", "team", "bye", "tier", "adp", "adp_stdev",
                 "espn_adp", "proj_points", "ecr", "ecr_sd", "notes", "flags",
                 "key", "nkey")

    def __init__(self, rank, name, pos, team="", bye=None, tier=1, adp=None,
                 adp_stdev=None, espn_adp=None, proj_points=None, ecr=None,
                 ecr_sd=None, notes="", flags=""):
        self.rank = rank
        self.name = name
        self.pos = norm_pos(pos)
        self.team = (team or "").upper()
        self.bye = bye
        self.tier = tier
        self.adp = adp
        self.adp_stdev = adp_stdev
        self.espn_adp = espn_adp
        self.proj_points = proj_points
        self.ecr = ecr          # FantasyPros consensus overall rank (optional)
        self.ecr_sd = ecr_sd    # spread across the experts behind that rank
        self.notes = notes or ""
        self.flags = flags or ""
        self.key = "%s|%s" % (norm_name(name), self.pos)
        self.nkey = norm_name(name)

    def __repr__(self):
        return "<%s %s %s r%s>" % (self.name, self.pos, self.team, self.rank)

    def label(self) -> str:
        bye = " bye%s" % self.bye if self.bye else ""
        return "%s (%s%s%s)" % (self.name, self.pos,
                                "-" + self.team if self.team else "", bye)

    def short_label(self) -> str:
        return "%s (%s%s)" % (self.name, self.pos,
                              "-" + self.team if self.team else "")

    def surname(self) -> str:
        """Display name for tight columns - suffixes dropped, spelling intact."""
        if self.pos == "DEF":
            return self.team or self.name.split()[0]
        parts = [t for t in self.name.split()
                 if t.lower().strip(".") not in SUFFIXES]
        return parts[-1] if parts else self.name


def _num(val, cast=float):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return cast(s)
    except ValueError:
        return None


# Header variants seen in Yahoo / ESPN / FantasyPros exports.
HEADER_ALIASES = {
    "rank": ["rank", "rk", "overall", "overall rank", "my rank", "ovr"],
    "name": ["name", "player", "player name", "playername", "full name"],
    "pos": ["pos", "position", "pos."],
    "team": ["team", "tm", "nfl team", "pro team"],
    "bye": ["bye", "bye week", "byeweek"],
    "tier": ["tier", "my tier"],
    "adp": ["adp", "avg pick", "average pick", "adp ppr"],
    "adp_stdev": ["adp_stdev", "stdev", "std dev", "sd"],
    "espn_adp": ["espn_adp", "espn adp", "room adp", "room_adp"],
    "proj_points": ["proj_points", "proj", "projection", "projected points",
                    "fpts", "points", "proj pts"],
    # 'ecr_sd' on purpose - a bare 'sd' header is already an adp_stdev alias.
    "ecr": ["ecr", "consensus", "consensus rank"],
    "ecr_sd": ["ecr_sd", "ecr sd", "ecr stdev"],
    "notes": ["notes", "note", "comment", "comments"],
    "flags": ["flags", "flag", "tags"],
}


def load_players(csv_path: str) -> List[Player]:
    """Load the rankings CSV, tolerating missing columns and header variants."""
    with open(csv_path, "r", newline="") as fh:
        reader = csv.reader(fh)
        rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("Rankings CSV %s is empty" % csv_path)

    header = [c.strip().lower() for c in rows[0]]
    col = {}
    for field, aliases in HEADER_ALIASES.items():
        for i, h in enumerate(header):
            if h in aliases:
                col[field] = i
                break

    for required in ("name", "pos"):
        if required not in col:
            raise ValueError("Rankings CSV needs a '%s' column. Found: %s"
                             % (required, ", ".join(header)))

    players = []
    for i, row in enumerate(rows[1:], start=1):
        def cell(field, default=""):
            idx = col.get(field)
            if idx is None or idx >= len(row):
                return default
            return row[idx].strip()

        name = cell("name")
        if not name:
            continue
        players.append(Player(
            rank=_num(cell("rank"), int) or i,
            name=name,
            pos=cell("pos"),
            team=cell("team"),
            bye=_num(cell("bye"), int),
            tier=_num(cell("tier"), int) or 1,
            adp=_num(cell("adp")),
            adp_stdev=_num(cell("adp_stdev")),
            espn_adp=_num(cell("espn_adp")),
            proj_points=_num(cell("proj_points")),
            ecr=_num(cell("ecr")),
            ecr_sd=_num(cell("ecr_sd")),
            notes=cell("notes"),
            flags=cell("flags"),
        ))

    players.sort(key=lambda p: p.rank)
    # Re-rank densely so downstream value curves are well behaved.
    for i, p in enumerate(players, start=1):
        p.rank = i
    return players


def host_of(raw) -> Optional[Dict[str, str]]:
    """{league_id, team_id} as strings, or None for anything less.

    Both ids must be present and non-empty: a league id alone cannot open a
    team page, and a link to the wrong team is worse than no link. Ids are
    kept as strings - they are path/query fragments, not numbers to sum.
    """
    if not isinstance(raw, dict):
        return None
    out = {}
    for key in ("league_id", "team_id"):
        val = raw.get(key)
        if val is None or isinstance(val, bool):
            return None
        text = str(val).strip()
        if not text:
            return None
        out[key] = text
    return out


class LeagueConfig(object):
    def __init__(self, data: Dict, path: str = ""):
        self.path = path
        self.id = data.get("id") or os.path.splitext(os.path.basename(path))[0]
        self.name = data.get("name", self.id)
        self.platform = data.get("platform", "")
        self.teams = int(data.get("teams", 10))
        slot = data.get("my_slot")
        self.my_slot = int(slot) if slot else None
        self.scoring = data.get("scoring", {}) or {}
        self.roster_spots = list(data.get("roster_spots", []))
        self.team_names = list(data.get("team_names", []) or [])
        self.rounds = int(data.get("rounds") or len(self.roster_spots) or 16)
        self.rankings_csv = data.get("rankings_csv", "data/rankings.csv")
        self.strategy_file = data.get("strategy_file", "")
        # How this league allocates waiver claims: 'faab' (blind budget bids)
        # or 'priority' (inverse-standings queue). Absent = 'faab', the shape
        # every league yaml predating the field assumed.
        self.waiver_mode = str(data.get("waiver_mode") or "faab").strip().lower()
        # Where this team lives on its host platform, for the landing page's
        # deep links: {league_id, team_id}. OPTIONAL. Absent, malformed or
        # half-filled reads as None - every page then renders without a link
        # and says which key would add one. It is never inferred from other
        # keys (espn_league_id names the league, not the team).
        self.host = host_of(data.get("host"))

    @classmethod
    def load(cls, path: str) -> "LeagueConfig":
        with open(path, "r") as fh:
            return cls(yaml.safe_load(fh) or {}, path)

    @property
    def ppr(self) -> float:
        return float(self.scoring.get("reception", 0) or 0)

    def scoring_label(self) -> str:
        """Fetcher scoring token derived from THIS league's reception value.

        Matches what engine/projections.py and engine/tiers.py accept, so a
        reseed command can never quietly use another league's format.
        """
        if self.ppr >= 1:
            return "ppr"
        if self.ppr > 0:
            return "half"
        return "std"

    def starter_counts(self) -> Dict[str, float]:
        """Starting demand per position, splitting flex evenly among eligibles."""
        counts = dict((p, 0.0) for p in POSITIONS)
        for spot in self.roster_spots:
            s = spot.strip().upper()
            if s in ("BN", "BE", "BENCH", "IR"):
                continue
            if s in FLEX_ELIGIBLE:
                elig = FLEX_ELIGIBLE[s]
                for p in elig:
                    counts[p] = counts.get(p, 0.0) + 1.0 / len(elig)
            else:
                s = norm_pos(s)
                counts[s] = counts.get(s, 0.0) + 1.0
        return counts

    def hard_starter_counts(self) -> Dict[str, int]:
        """Dedicated (non-flex) starting spots per position."""
        counts = dict((p, 0) for p in POSITIONS)
        for spot in self.roster_spots:
            s = spot.strip().upper()
            if s in ("BN", "BE", "BENCH", "IR") or s in FLEX_ELIGIBLE:
                continue
            s = norm_pos(s)
            counts[s] = counts.get(s, 0) + 1
        return counts

    def flex_spots(self) -> List[List[str]]:
        out = []
        for spot in self.roster_spots:
            s = spot.strip().upper()
            if s in FLEX_ELIGIBLE:
                out.append(FLEX_ELIGIBLE[s])
        return out

    def bench_spots(self) -> int:
        return sum(1 for s in self.roster_spots
                   if s.strip().upper() in ("BN", "BE", "BENCH"))


def missing_rankings_message(league: "LeagueConfig", csv_path: str) -> str:
    """Loud, copy-pasteable error for a league whose rankings CSV is absent.

    A per-league CSV is intentionally never auto-created: seeding it silently
    would bake in whatever scoring/team-count defaults the seeder happens to
    have, and every VBD baseline, survival odd, and tier downstream would then
    belong to a different league's format. Instead the exact reseed sequence -
    ADP seed, projections fill, Chen tiers - is printed with THIS league's
    scoring and team count already filled in.
    """
    label = league.scoring_label()
    ffc = {"ppr": "ppr", "half": "half-ppr", "std": "standard"}[label]
    rel = league.rankings_csv
    lines = [
        "rankings CSV not found: %s (league %s)"
        % (repo_path(csv_path), league.id),
        "",
        "This league points at its own CSV on purpose - values, VBD baselines,",
        "survival odds, and tiers must come from THIS league's scoring (%s)"
        % ("full PPR" if label == "ppr" else
           "half PPR" if label == "half" else "standard"),
        "and team count (%d), not another league's file." % league.teams,
        "",
        "Verify teams/scoring in %s, then run the reseed command once league"
        % (repo_path(league.path) if league.path else "the league yaml"),
        "settings are confirmed:",
        "",
        "  .venv/bin/python -c \"from engine.adp import seed_rankings_csv; "
        "seed_rankings_csv('%s', scoring='%s', teams=%d)\"" % (rel, ffc, league.teams),
        "  .venv/bin/python engine/projections.py %s %s" % (rel, label),
    ]
    if label != "std":   # Chen publishes no standard-scoring RB/WR/TE files
        lines.append("  .venv/bin/python -c \"from engine.tiers import "
                     "apply_to_csv; apply_to_csv('%s', scoring='%s')\""
                     % (rel, label))
    else:
        lines.append("  (no Chen tier feed for standard scoring - the seeded "
                     "ADP-gap tiers stand)")
    return "\n".join(lines)


class Pick(object):
    __slots__ = ("overall", "team", "player_key", "raw", "seq")

    def __init__(self, overall: int, team: int, player_key: str, raw: str = "",
                 seq: Optional[int] = None):
        self.overall = overall
        self.team = team
        self.player_key = player_key
        self.raw = raw
        self.seq = seq          # application order; stamped by the board

    def to_dict(self):
        return {"overall": self.overall, "team": self.team,
                "player_key": self.player_key, "raw": self.raw,
                "seq": self.seq}


class PickBoard(dict):
    """overall -> Pick mapping that stamps application order on insert.

    A keeper parked at overall 100 while the draft is on pick 12 makes
    overall order lie about recency. Every insertion path (apply_pick,
    restore, placeholder writes) goes through __setitem__, which stamps
    picks lacking a seq and keeps the counter ahead of any pre-stamped
    pick from a restored save.
    """

    def __init__(self, *args, **kwargs):
        super(PickBoard, self).__init__(*args, **kwargs)
        self.next_seq = 0
        for pick in self.values():
            self.next_seq = max(self.next_seq, pick.seq or 0)

    def __setitem__(self, overall, pick):
        if getattr(pick, "seq", None) is None:
            self.next_seq += 1
            pick.seq = self.next_seq
        else:
            self.next_seq = max(self.next_seq, pick.seq)
        dict.__setitem__(self, overall, pick)


def _applied_order(pick: Pick):
    # seq is stamped on insert; overall is a fallback for hand-built picks.
    return pick.seq if pick.seq is not None else pick.overall


def team_on_clock(overall: int, teams: int) -> int:
    """1-based team slot picking at this overall pick number (standard snake)."""
    rnd = (overall - 1) // teams + 1
    idx = (overall - 1) % teams + 1
    return idx if rnd % 2 == 1 else teams - idx + 1


def round_and_pick(overall: int, teams: int):
    return ((overall - 1) // teams + 1, (overall - 1) % teams + 1)


def fmt_pick(overall: int, teams: int) -> str:
    rnd, pk = round_and_pick(overall, teams)
    return "%d.%02d" % (rnd, pk)


class DraftState(object):
    def __init__(self, league: LeagueConfig, players: List[Player]):
        self.league = league
        self.players = players
        self.by_key = dict((p.key, p) for p in players)
        self.picks = PickBoard()   # overall -> Pick, seq-stamped on insert
        self.drafted = {}          # player_key -> Pick
        self.active_branch = None
        self.branch_log = []       # [(overall, branch_id, reason)]
        self.fired_triggers = []   # trigger ids already applied
        self.pending_alerts = []

    # --- board -------------------------------------------------------------
    @property
    def teams(self) -> int:
        return self.league.teams

    @property
    def my_slot(self) -> Optional[int]:
        return self.league.my_slot

    def current_pick(self) -> int:
        n = 1
        while n in self.picks:
            n += 1
        return n

    def total_picks(self) -> int:
        return self.teams * self.league.rounds

    def is_complete(self) -> bool:
        return self.current_pick() > self.total_picks()

    def available(self, pos: Optional[str] = None) -> List[Player]:
        pos = norm_pos(pos) if pos else None
        out = [p for p in self.players if p.key not in self.drafted]
        if pos:
            out = [p for p in out if p.pos == pos]
        return out

    def is_drafted(self, key: str) -> bool:
        return key in self.drafted

    def roster(self, team: int) -> List[Player]:
        keys = [pk.player_key for pk in sorted(self.picks.values(),
                                               key=lambda x: x.overall)
                if pk.team == team]
        return [self.by_key[k] for k in keys if k in self.by_key]

    def my_roster(self) -> List[Player]:
        return self.roster(self.my_slot) if self.my_slot else []

    def pos_counts(self, team: int) -> Dict[str, int]:
        counts = dict((p, 0) for p in POSITIONS)
        for pl in self.roster(team):
            counts[pl.pos] = counts.get(pl.pos, 0) + 1
        return counts

    # --- turn tracking -----------------------------------------------------
    def team_at(self, overall: int) -> int:
        return team_on_clock(overall, self.teams)

    def on_the_clock(self) -> int:
        return self.team_at(self.current_pick())

    def is_my_turn(self) -> bool:
        return self.my_slot is not None and self.on_the_clock() == self.my_slot

    def my_picks_overall(self) -> List[int]:
        if not self.my_slot:
            return []
        return [n for n in range(1, self.total_picks() + 1)
                if self.team_at(n) == self.my_slot]

    def next_my_pick(self, after: Optional[int] = None) -> Optional[int]:
        start = self.current_pick() if after is None else after + 1
        for n in self.my_picks_overall():
            if n >= start:
                return n
        return None

    def picks_until_mine(self) -> Optional[int]:
        nxt = self.next_my_pick()
        return None if nxt is None else nxt - self.current_pick()

    def my_pick_after_this(self) -> Optional[int]:
        """The pick after the one I'm on (or next) - the survival horizon."""
        nxt = self.next_my_pick()
        if nxt is None:
            return None
        return self.next_my_pick(after=nxt)

    def current_round(self) -> int:
        return round_and_pick(min(self.current_pick(), self.total_picks()),
                              self.teams)[0]

    def recent_picks(self, n: int = 5) -> List[Pick]:
        """Last n picks in APPLICATION order - a keeper parked at a high
        overall must not masquerade as the newest pick in run detection."""
        got = sorted(self.picks.values(), key=_applied_order)
        return got[-n:]

    # --- mutation ----------------------------------------------------------
    def apply_pick(self, player: Player, overall: Optional[int] = None,
                   raw: str = "") -> Pick:
        if player.key in self.drafted:
            raise ValueError("%s is already drafted" % player.name)
        if overall is None:
            overall = self.current_pick()
        pick = Pick(overall, self.team_at(overall), player.key, raw)
        self.picks[overall] = pick
        self.drafted[player.key] = pick
        return pick

    def undo_last(self) -> Optional[Pick]:
        """Remove the most recently APPLIED pick - not the highest overall,
        which would yank a keeper instead of the pick just made."""
        if not self.picks:
            return None
        pick = max(self.picks.values(), key=_applied_order)
        self.picks.pop(pick.overall)
        self.drafted.pop(pick.player_key, None)
        self.branch_log = [b for b in self.branch_log if b[0] < pick.overall]
        return pick

    def team_label(self, team: int) -> str:
        if team == self.my_slot:
            return "ME (Team %d)" % team
        if 0 < team <= len(self.league.team_names):
            return self.league.team_names[team - 1]
        return "Team %d" % team
