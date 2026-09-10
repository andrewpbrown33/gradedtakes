#!/usr/bin/env python3
"""Full-league rosters for leagues no API can read for us (Yahoo, today).

ESPN's Original 8 is fully captured (data/draft-espn-1-2026.csv ->
data/league-espn-1.json), so "who holds Bijan?" is answerable there. Yahoo
is not connected and only MY 16 are known, which makes trade targets,
waiver competition and roster-hole reads guesswork. This module closes
that gap the only honest way left: the user pastes what the league-rosters
page shows, we parse it, show exactly what we understood BEFORE writing,
and store it in the same shape the engine already reads for espn-1.

THREE LAYERS, ONE VIEW (load_league_view)
  1. captured draft data   data/draft-<id>-<season>.csv   (highest)
  2. the pasted store      data/league-<id>.json
  3. my own roster         data/rosters/<id>.yaml         (lowest)
Precedence is per TEAM SLOT, not per file: a slot the draft capture knows
is never overwritten by a paste, and a slot the store knows is never
overwritten by my own-roster file. Each team carries the layer it came
from, so the panel and CLI can show where every roster came from.

COVERAGE IS ALWAYS REPORTED. A LeagueView says "3 of 10 rosters known" and
never pretends otherwise. The rule the whole project already applies to
data/rosters (engine/exposure.py) applies here too, one level up: a player
who appears on NO known roster is UNKNOWN, not a free agent - claim_status()
returns "unknown" until every roster is in, and only then "free". Callers
must not render "available" from silence.

PASTING NEVER INVENTS A PLAYER. parse_league_paste() matches each line
against the rankings pool through engine.ingest (the same parser and fuzzy
Matcher the draft room uses); anything under MATCH_MIN is reported as an
unmatched line, verbatim, for the human to fix - never guessed onto a
rival's roster, never silently dropped. Recognized page furniture (slot
labels, kickoff times, stat headers) is counted as skipped, separately, so
"unmatched" stays a short list worth reading.

    python -m engine.leagueview --league yahoo-main
    python -m engine.leagueview --league yahoo-main --summary
    python -m engine.leagueview --league yahoo-main --paste-file rosters.txt
    python -m engine.leagueview --league yahoo-main --paste-file r.txt --save

--paste-file previews and writes NOTHING until --save is added, the same
preview-then-confirm the Model Settings panel's "League rosters" section
uses (engine/sources_ui.py).
"""

import argparse
import csv
import difflib
import glob
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import yaml

try:
    from engine.ingest import NFL_TEAMS, Matcher, parse_line
    from engine.models import LeagueConfig, Player, load_players, norm_name, norm_pos
except ImportError:  # run directly as `python engine/leagueview.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.ingest import NFL_TEAMS, Matcher, parse_line
    from engine.models import LeagueConfig, Player, load_players, norm_name, norm_pos

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Same bar engine/exposure.py and engine/intel.py use for pasted names.
# Below it a line is REPORTED, never guessed onto somebody's roster.
MATCH_MIN = 70

# Layer labels (also the precedence order, strongest first).
SRC_DRAFT = "draft"     # data/draft-<id>-<season>.csv
SRC_STORE = "store"     # data/league-<id>.json (what pastes write)
SRC_OWN = "own"         # data/rosters/<id>.yaml (my roster only)
SRC_LABELS = {SRC_DRAFT: "draft capture", SRC_STORE: "pasted store",
              SRC_OWN: "my roster file"}


def _default_season() -> int:
    try:
        from engine.weekly import SEASON  # noqa: PLC0415 - one int, lazy
        return int(SEASON)
    except Exception:  # noqa: BLE001 - a season is never worth a crash
        return 2026


# --- paths -------------------------------------------------------------------

def store_path(league_id: str, data_root: Optional[str] = None) -> str:
    """data/league-<id>.json - the league-wide roster store this module owns."""
    return os.path.join(data_root or HERE, "data", "league-%s.json" % league_id)


def draft_capture_path(league_id: str,
                       data_root: Optional[str] = None) -> Optional[str]:
    """Newest data/draft-<id>-<season>.csv, or None when none was captured."""
    pattern = os.path.join(data_root or HERE, "data",
                           "draft-%s-*.csv" % league_id)
    found = sorted(glob.glob(pattern))
    return found[-1] if found else None


def own_roster_path(league_id: str, data_root: Optional[str] = None) -> str:
    """data/rosters/<id>.yaml - MY roster (engine/exposure.py's file)."""
    return os.path.join(data_root or HERE, "data", "rosters",
                        "%s.yaml" % league_id)


def league_config_path(league_id: str, data_root: Optional[str] = None) -> str:
    return os.path.join(data_root or HERE, "leagues", "%s.yaml" % league_id)


def load_config(league_id: str,
                data_root: Optional[str] = None) -> LeagueConfig:
    """leagues/<id>.yaml as a LeagueConfig (raises if it is not there)."""
    return LeagueConfig.load(league_config_path(league_id, data_root))


def list_configs(data_root: Optional[str] = None) -> List[LeagueConfig]:
    """Every readable leagues/*.yaml, by id. Unparsable files are skipped."""
    out = []
    for path in sorted(glob.glob(os.path.join(data_root or HERE, "leagues",
                                              "*.yaml"))):
        try:
            out.append(LeagueConfig.load(path))
        except Exception:  # noqa: BLE001 - one bad file never hides the rest
            continue
    return sorted(out, key=lambda c: c.id)


# --- store I/O ---------------------------------------------------------------

def _row(player: Player) -> Dict:
    """A pool Player as a store row - the espn-1 shape, exactly."""
    return {"player": player.name, "pos": player.pos, "nfl": player.team,
            "bye": player.bye, "proj": player.proj_points}


def _raw_row(name: str) -> Dict:
    """A name we could not resolve to the pool: kept verbatim, never faked."""
    return {"player": name, "pos": "", "nfl": "", "bye": None, "proj": None}


def row_key(row: Dict) -> str:
    """Player.key for a store row ('jahmyr gibbs|RB')."""
    return "%s|%s" % (norm_name(str(row.get("player") or "")),
                      norm_pos(str(row.get("pos") or "")))


def row_nkey(row: Dict) -> str:
    return norm_name(str(row.get("player") or ""))


def row_label(row: Dict) -> str:
    """'Jahmyr Gibbs (RB-DET)' - what the preview and CLI print."""
    pos = str(row.get("pos") or "")
    nfl = str(row.get("nfl") or "")
    if not pos and not nfl:
        return str(row.get("player") or "")
    return "%s (%s%s)" % (row.get("player"), pos or "?",
                          "-" + nfl if nfl else "")


def load_store(league_id: str, data_root: Optional[str] = None) -> Optional[Dict]:
    """The league-wide store, or None when absent/unreadable/malformed."""
    path = store_path(league_id, data_root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as fh:
            doc = json.load(fh)
    except (ValueError, IOError, OSError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("teams"), dict):
        return None
    return doc


def save_store(doc: Dict, league_id: str,
               data_root: Optional[str] = None) -> str:
    """Atomically write data/league-<id>.json. Returns the path written.

    Temp-file + os.replace, the discipline every writer in this project
    uses (engine/sources.py, engine/connections.py) - a crash mid-write
    can never leave a half-parsed league on disk.
    """
    path = store_path(league_id, data_root)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def empty_store(league: LeagueConfig, season: Optional[int] = None) -> Dict:
    return {"league": league.id, "season": int(season or _default_season()),
            "teams": {}}


# --- the merged view ---------------------------------------------------------

class TeamRoster(object):
    """One team's known roster, and which layer it came from."""

    __slots__ = ("slot", "name", "players", "source", "mine")

    def __init__(self, slot: str, name: str, players: List[Dict],
                 source: str, mine: bool = False):
        self.slot = str(slot)
        self.name = name
        self.players = list(players)
        self.source = source
        self.mine = mine

    @property
    def source_label(self) -> str:
        return SRC_LABELS.get(self.source, self.source)

    def keys(self) -> List[str]:
        return [row_key(r) for r in self.players]

    def to_store(self) -> Dict:
        return {"name": self.name, "players": [dict(r) for r in self.players]}

    def __len__(self):
        return len(self.players)

    def __repr__(self):
        return "<TeamRoster %s %s %d players from %s>" % (
            self.slot, self.name, len(self.players), self.source)


class LeagueView(object):
    """Every roster we know in one league, with coverage stated out loud.

    known_teams/expected_teams drive coverage_text() ("3 of 10 rosters
    known"). claim_status() is the honest answer to "can I have him?":
    "held" names the team, "unknown" means our rosters simply do not say,
    and "free" is returned ONLY when every roster is known.
    """

    def __init__(self, league: LeagueConfig, teams: List[TeamRoster],
                 season: int, notes: Optional[List[str]] = None,
                 unresolved: Optional[List[str]] = None):
        self.league = league
        self.league_id = league.id
        self.name = league.name
        self.expected_teams = int(league.teams or 0)
        self.season = season
        self.teams = sorted(teams, key=_slot_sort_key)
        self.notes = list(notes or [])
        # own-roster names that did not resolve to the rankings pool
        self.unresolved = list(unresolved or [])
        self._by_key = {}
        self._by_nkey = {}
        for team in self.teams:
            for r in team.players:
                self._by_key.setdefault(row_key(r), team)
                nk = row_nkey(r)
                if nk:
                    self._by_nkey.setdefault(nk, team)

    # -- coverage ------------------------------------------------------------
    @property
    def known_teams(self) -> int:
        return sum(1 for t in self.teams if t.players)

    def complete(self) -> bool:
        return (self.expected_teams > 0
                and self.known_teams >= self.expected_teams)

    def coverage(self) -> Tuple[int, int]:
        return self.known_teams, self.expected_teams

    def coverage_text(self) -> str:
        return "%d of %d rosters known" % (self.known_teams,
                                           self.expected_teams)

    def banner_text(self) -> str:
        """Honest-degradation line for partial coverage ('' when complete)."""
        if self.complete():
            return ""
        return ("%s: %s - a player on none of them is UNKNOWN, not a free "
                "agent" % (self.name, self.coverage_text()))

    def source_counts(self) -> Dict[str, int]:
        counts = {SRC_DRAFT: 0, SRC_STORE: 0, SRC_OWN: 0}
        for t in self.teams:
            if t.players:
                counts[t.source] = counts.get(t.source, 0) + 1
        return counts

    # -- queries -------------------------------------------------------------
    def team(self, slot: str) -> Optional[TeamRoster]:
        return next((t for t in self.teams if t.slot == str(slot)), None)

    def my_team(self) -> Optional[TeamRoster]:
        return next((t for t in self.teams if t.mine), None)

    def owner_of(self, player_key: str) -> Optional[TeamRoster]:
        """The team KNOWN to hold this player key, else None (= unknown)."""
        team = self._by_key.get(player_key)
        if team is not None:
            return team
        # An own-roster name we could not resolve carries no position, so
        # fall back to the name half of the key rather than lose the hit.
        return self._by_nkey.get((player_key or "").split("|")[0])

    def claim_status(self, player_key: str) -> Tuple[str, str]:
        """('held', team name) / ('free', '') / ('unknown', coverage text).

        'free' is only ever returned at full coverage - with a gap the
        honest answer is 'unknown', and callers must render it that way.
        """
        team = self.owner_of(player_key)
        if team is not None:
            return "held", team.name
        if self.complete():
            return "free", ""
        return "unknown", self.coverage_text()

    def held_keys(self) -> Dict[str, str]:
        """{player_key: team name} across every known roster."""
        return dict((k, t.name) for k, t in self._by_key.items())

    def __repr__(self):
        return "<LeagueView %s %s>" % (self.league_id, self.coverage_text())


def _slot_sort_key(team: TeamRoster):
    try:
        return (0, int(team.slot), "")
    except (TypeError, ValueError):
        return (1, 0, team.slot)


def _teams_from_draft(league: LeagueConfig,
                      data_root: Optional[str]) -> Dict[str, TeamRoster]:
    """Captured draft csv -> {slot: TeamRoster}. Absent file -> {}."""
    path = draft_capture_path(league.id, data_root)
    if not path:
        return {}
    try:
        with open(path, "r", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (IOError, OSError, csv.Error):
        return {}
    by_slot = {}
    names = {}
    for r in rows:
        slot = str(r.get("slot") or "").strip()
        player = str(r.get("player") or "").strip()
        if not slot or not player:
            continue
        names.setdefault(slot, str(r.get("team") or "").strip())
        row = {"player": player, "pos": norm_pos(r.get("pos") or ""),
               "nfl": str(r.get("nfl") or "").strip().upper(),
               "bye": _int_or_none(r.get("bye")),
               "proj": _float_or_none(r.get("proj"))}
        for extra, cast in (("round", _int_or_none),
                            ("overall", _int_or_none)):
            val = cast(r.get(extra))
            if val is not None:
                row[extra] = val
        by_slot.setdefault(slot, []).append(row)
    out = {}
    for slot, players in by_slot.items():
        out[slot] = TeamRoster(slot, names.get(slot) or "Team %s" % slot,
                               players, SRC_DRAFT,
                               mine=_is_my_slot(league, slot))
    return out


def _teams_from_store(league: LeagueConfig,
                      data_root: Optional[str]) -> Tuple[Dict[str, TeamRoster], int]:
    doc = load_store(league.id, data_root)
    if doc is None:
        return {}, 0
    out = {}
    for slot, entry in (doc.get("teams") or {}).items():
        if not isinstance(entry, dict):
            continue
        players = [p for p in (entry.get("players") or [])
                   if isinstance(p, dict) and str(p.get("player") or "").strip()]
        out[str(slot)] = TeamRoster(
            str(slot), str(entry.get("name") or "Team %s" % slot), players,
            SRC_STORE, mine=_is_my_slot(league, slot))
    season = doc.get("season")
    return out, int(season) if isinstance(season, int) else 0


def _teams_from_own(league: LeagueConfig, data_root: Optional[str],
                    matcher: Optional[Matcher]
                    ) -> Tuple[Dict[str, TeamRoster], List[str]]:
    """MY roster yaml -> {my_slot: TeamRoster}, plus names that missed.

    Names resolve through the same fuzzy Matcher when one is supplied; an
    unresolved name is still carried (it IS on my roster - the file is the
    user's own) but stays position-less rather than being invented.
    """
    path = own_roster_path(league.id, data_root)
    if not os.path.exists(path):
        return {}, []
    try:
        with open(path, "r") as fh:
            doc = yaml.safe_load(fh)
    except (yaml.YAMLError, IOError, OSError):
        return {}, []
    if not isinstance(doc, dict) or not isinstance(doc.get("players"), list):
        return {}, []
    unresolved, players = [], []
    for raw in doc["players"]:
        name = (str(raw.get("name", "")) if isinstance(raw, dict)
                else str(raw or "")).strip()
        if not name:
            continue
        match = matcher.match(name) if matcher is not None else None
        if match is not None and match.score >= MATCH_MIN:
            players.append(_row(match.player))
        else:
            if matcher is not None:
                unresolved.append(name)
            players.append(_raw_row(name))
    if not players:
        return {}, unresolved
    slot = str(league.my_slot) if league.my_slot else "1"
    name = str(doc.get("name") or league.name)
    return ({slot: TeamRoster(slot, name, players, SRC_OWN, mine=True)},
            unresolved)


def _is_my_slot(league: LeagueConfig, slot) -> bool:
    return bool(league.my_slot) and str(league.my_slot) == str(slot)


def _int_or_none(val) -> Optional[int]:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(val) -> Optional[float]:
    try:
        return float(str(val).strip())
    except (TypeError, ValueError):
        return None


def load_league_view(league: LeagueConfig, matcher: Optional[Matcher] = None,
                     data_root: Optional[str] = None) -> LeagueView:
    """Merge the three layers into one view. Never raises on missing files.

    Precedence per team slot: captured draft > pasted store > my roster.
    A league with nothing on disk yields a view with zero known rosters -
    coverage_text() says so, which is the point.
    """
    notes = []
    draft = _teams_from_draft(league, data_root)
    store, season = _teams_from_store(league, data_root)
    own, unresolved = _teams_from_own(league, data_root, matcher)

    merged = {}
    for layer in (own, store, draft):        # weakest first; stronger wins
        for slot, team in layer.items():
            merged[slot] = team
    if draft:
        notes.append("%d roster(s) from the draft capture (%s)"
                     % (len(draft),
                        os.path.basename(draft_capture_path(league.id,
                                                            data_root) or "")))
    # Only worth a note when the two layers actually DISAGREE - the store
    # is often just a mirror of the capture, and crying conflict over
    # identical rosters would train the reader to ignore the line.
    shadowed = sorted((s for s in set(store) & set(draft)
                       if sorted(store[s].keys()) != sorted(draft[s].keys())),
                      key=lambda s: _slot_sort_key(TeamRoster(s, "", [],
                                                              SRC_STORE)))
    if shadowed:
        notes.append("draft capture outranks the DIFFERING pasted store for "
                     "slot(s) %s" % ", ".join(shadowed))
    if unresolved:
        notes.append("%d name(s) in my roster file did not match the "
                     "rankings pool: %s" % (len(unresolved),
                                            ", ".join(unresolved)))
    return LeagueView(league, list(merged.values()),
                      season or _default_season(), notes, unresolved)


def coverage_rows(data_root: Optional[str] = None) -> List[Dict]:
    """Coverage per league, cheap enough for a page render (no matcher).

    [{'id','name','known','expected','text','complete','teams':[...]}] -
    what engine/sources_ui.py's League rosters card renders.
    """
    out = []
    for cfg in list_configs(data_root):
        try:
            view = load_league_view(cfg, None, data_root)
        except Exception:  # noqa: BLE001 - one bad league never blanks the card
            continue
        out.append({
            "id": view.league_id, "name": view.name,
            "known": view.known_teams, "expected": view.expected_teams,
            "text": view.coverage_text(), "complete": view.complete(),
            "banner": view.banner_text(),
            "teams": [{"slot": t.slot, "name": t.name, "count": len(t),
                       "source": t.source, "source_label": t.source_label,
                       "mine": t.mine} for t in view.teams],
        })
    return out


# --- paste parsing -----------------------------------------------------------

# Whole-line page furniture. Matched against the WHOLE line only, so a team
# called "Bench Mob" or "Total Chaos" is never eaten as a header.
_SLOT_WORDS = {
    "qb", "rb", "wr", "te", "k", "pk", "def", "dst", "d/st", "dl", "lb", "db",
    "flex", "w/r", "w/t", "w/r/t", "r/w/t", "q/w/r/t", "superflex", "op",
    "bn", "be", "bench", "ir", "taxi", "reserve", "starters", "starter",
    "lineup", "roster", "rosters", "players", "player", "pos", "position",
    "opp", "proj", "projected", "pts", "points", "total", "totals", "status",
    "action", "actions", "add", "drop", "move", "edit", "compare", "trade",
    "empty", "empty slot", "free agent", "fa", "waivers", "waiver",
    "watch list", "notes", "note", "bye", "byes", "injured reserve",
}
_TIME_LINE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", re.I)
_DAY_LINE = re.compile(r"^(?:sun|mon|tue|tues|wed|thu|thur|thurs|fri|sat)\b",
                       re.I)
_OPP_LINE = re.compile(r"^(?:@|vs\.?\s+)[A-Za-z]{2,4}\s*$", re.I)
_RESULT_LINE = re.compile(r"^(?:final|[wlt])\s*[,\d\s\-]*$", re.I)
_NUMERIC_LINE = re.compile(r"^[\d\s.,%$:+\-/()]+$")
_RECORD_TAIL = re.compile(r"[\(\[]?\s*\d{1,2}\s*-\s*\d{1,2}(?:\s*-\s*\d{1,2})?"
                          r"\s*[\)\]]?\s*$")
# "Team 3: Name" / "Manager - Name". A dash needs spaces around it so a
# team actually CALLED "Roster-Ruiners" keeps its whole name.
_TEAM_MARKER = re.compile(
    r"^\s*(?:team|roster|manager|owner)\s*#?\s*(\d*)\s*"
    r"(?::\s*|\s+[\-–—]\s+)(.+)$", re.I)
# Kickoff / opponent / result tail glued onto a player row by the copy.
_SCHED_TAIL = re.compile(
    r"\s+(?:(?:sun|mon|tue|tues|wed|thu|thur|thurs|fri|sat|bye|final)\b"
    r"|@\s*[A-Za-z]{2,4}\b|vs\.?\s+[A-Za-z]{2,4}\b|\d{1,2}:\d{2}).*$", re.I)
_DASHED = re.compile(r"^[\s\-=*_–—]*(.+?)[\s\-=*_–—]*$")
_TRAIL_STATS = re.compile(r"(?:\s+[-+]?\d+(?:\.\d+)?){1,6}\s*$")
_TRAIL_TAGS = re.compile(
    r"(?:\s+(?:Q|D|O|P|IR|SUS|PUP|NA|GTD|DTD|OUT|DNP|NFI|COV|SSPD))+\s*$")
_LEAD_SLOT = re.compile(
    r"^\s*(QB|RB|WR|TE|K|PK|DEF|DST|D/ST|FLEX|W/R/T|W/R|W/T|R/W/T|Q/W/R/T|"
    r"SUPERFLEX|OP|BN|BE|BENCH|IR|TAXI)\b[\s.:|)\-]+", re.I)
_LEAD_POS = {"QB", "RB", "WR", "TE", "K", "PK", "DEF", "DST", "D/ST"}
# Abbreviations the fantasy sites print that engine/ingest.py's NFL_TEAMS
# does not carry. Rewritten to the canonical code so they read as team
# hints instead of polluting the name.
_TEAM_FIXES = {"WSH": "WAS", "WFT": "WAS", "LA": "LAR", "SD": "LAC",
               "OAK": "LV", "STL": "LAR", "ARZ": "ARI", "BLT": "BAL",
               "CLV": "CLE", "HST": "HOU", "JAG": "JAX"}

# Column-header vocabulary. Every roster page prints a header ROW above the
# players - "POS PLAYER OPP PROJ PTS" - and no single token of it is the
# whole line, so the whole-line tests above miss it. An unrecognized line
# lands exactly where a team NAME goes, so the header became a phantom team
# and pushed the real name that followed it into .unmatched. A line whose
# tokens are ALL header words is therefore furniture too, which is what the
# module docstring already promises ("stat headers" are skipped).
_HEADER_WORDS = _SLOT_WORDS | {
    "fpts", "fpt", "ppg", "avg", "average", "rank", "rk", "own", "owned",
    "rost", "rostered", "opponent", "score", "scored", "start", "started",
    "sit", "proj.", "projection", "projections", "wk", "week", "last",
    "next", "gp", "games", "tot", "team", "teams", "slot", "record", "res",
    "result", "results", "matchup", "time", "kickoff", "game", "%st",
    "%rost", "%own",
}
# A token that is only ever a number ("12", "0.0", "-", "%") neither makes
# a line a header nor rules it out; a header needs at least two real header
# WORDS, so "Total 12" stays a name and "PROJ PTS" does not.
_HEADER_MIN_WORDS = 2
_TOKEN_EDGE = " .,;:|()[]{}%#*/\\-–—_\"'"


def _is_header_row(text: str) -> bool:
    """True when every token of a multi-token line is column-header furniture.

    Deliberately conservative: a single-token line is left to the
    whole-line _SLOT_WORDS test, purely numeric tokens are ignored rather
    than counted, and two real header words are required - so a team
    actually called "Total Chaos" or "Bench Mob" keeps its name.
    """
    words = 0
    for token in text.split():
        tok = token.strip(_TOKEN_EDGE)
        if not tok or _NUMERIC_LINE.match(tok):
            continue
        if tok.lower() not in _HEADER_WORDS:
            return False
        words += 1
    return words >= _HEADER_MIN_WORDS


def _is_junk_line(line: str) -> bool:
    """True for recognized roster-page furniture (counted, not reported).

    Whole-line only, and checked again after a leading slot label is
    stripped so ESPN's "BN  Empty" reads as furniture too. A line that
    merely CARRIES a kickoff time is a player row with the schedule glued
    on (_clean_for_player strips that tail) - only a line that is nothing
    but a schedule row is furniture. A multi-column stat header ("PROJ PTS
    OPP") is furniture as well: see _is_header_row.
    """
    s = " ".join(line.split()).strip(" .:|-()[]")
    if not s:
        return True
    for candidate in (s, _LEAD_SLOT.sub("", s).strip(" .:|-()[]")):
        low = candidate.lower()
        if low in _SLOT_WORDS or _NUMERIC_LINE.match(candidate):
            return True
        if _OPP_LINE.match(candidate) or _RESULT_LINE.match(candidate):
            return True
        if _DAY_LINE.match(candidate) and _TIME_LINE.search(candidate):
            return True
    # "Team 4: Roster" names a team explicitly - an explicit marker always
    # beats the header heuristic, so a declared name is never eaten.
    if _TEAM_MARKER.match(s):
        return False
    return _is_header_row(s)


def _player_row_strength(line: str) -> int:
    """How strongly a line reads as a ROSTER ROW rather than a team header.

    2 - structural: a leading slot label, a numbered-list prefix, or a
        trailing '- WR' position tail. Nothing overrules this, so one
        name the pool does not carry is reported instead of splitting a
        roster block in two.
    1 - suggestive: an NFL team code somewhere in the line. Fantasy team
        names carry those too ("The KC Crew"), so a blank line above -
        the separator every roster page prints between teams - is allowed
        to overrule it.
    0 - nothing player-shaped about it.
    """
    s = " ".join(line.split())
    if _LEAD_SLOT.match(s) or re.match(r"^\d{1,2}\s*[.)]\s+\S", s):
        return 2
    if re.search(r"[\s\-,|(\[]\s*(QB|RB|WR|TE|K|PK|DEF|DST|D/ST)\s*[)\]]?\s*$",
                 s, re.I):
        return 2
    for tok in s.split():
        bare = tok.strip(".,|()[]").upper()
        if bare in NFL_TEAMS or bare in _TEAM_FIXES:
            return 1
    return 0


def _team_name_of(line: str) -> str:
    """Clean a header line into a team name ('' when nothing is left)."""
    s = " ".join(line.split())
    marker = _TEAM_MARKER.match(s)
    if marker:
        s = marker.group(2)
    dashed = _DASHED.match(s)
    if dashed:
        s = dashed.group(1)
    s = _RECORD_TAIL.sub("", s).strip()
    s = re.sub(r"\b\(?\d+(?:st|nd|rd|th)\)?\s*(?:place)?\s*$", "", s,
               flags=re.I).strip()
    s = re.sub(r"\broster\s*$", "", s, flags=re.I).strip(" ,:;-|")
    return " ".join(s.split())


def _clean_for_player(line: str) -> str:
    """Strip roster-page decoration so engine/ingest.parse_line can read it.

    A LEADING slot label that names a position is moved to the end (where
    parse_line reads it as a position hint) rather than discarded; a
    flex/bench label is simply dropped. Trailing stat columns, injury
    tags and win-loss records go; site-specific team abbreviations are
    rewritten to the codes engine/ingest.py knows.
    """
    s = " ".join(line.replace("\t", " ").split())
    lead = _LEAD_SLOT.match(s)
    tail_pos = ""
    if lead:
        label = lead.group(1).upper()
        s = s[lead.end():]
        if label in _LEAD_POS:
            tail_pos = " " + label
    if len(s.split()) > 2:
        s = _SCHED_TAIL.sub("", s).strip()
    for _ in range(3):
        new = _TRAIL_TAGS.sub("", _TRAIL_STATS.sub("", s)).strip()
        if new == s:
            break
        s = new
    s = re.sub(r"\((\d{1,2}-\d{1,2}(?:-\d{1,2})?)\)", " ", s)
    tokens = []
    for tok in s.split():
        bare = tok.strip(".,|()[]").upper()
        fixed = _TEAM_FIXES.get(bare)
        tokens.append(fixed if fixed and fixed in NFL_TEAMS else tok)
    return (" ".join(tokens) + tail_pos).strip()


_DEF_MARKER = re.compile(r"\b(?:def|dst|d/?st|defense|defence)\b", re.I)


def _defense_plausible(name_text: str, pos_hint: Optional[str],
                       player: Player) -> bool:
    """Reject a defense match a fantasy TEAM NAME only looked like.

    'GB' is an alias of the Green Bay defense, so "GB Bandits" scores 89
    against it - and a team called that would be silently drafted as a
    defense. A defense hit therefore has to be explained: either the line
    says DEF/D/ST/Defense, or every word in it belongs to that team's own
    names ("Baltimore", "Minnesota D/ST", "Denver Def"). Never applies to
    real players, whose surnames carry the match on their own.
    """
    if player.pos != "DEF":
        return True
    if pos_hint == "DEF" or _DEF_MARKER.search(name_text or ""):
        return True
    known = set()
    for alias in ([player.name, player.team]
                  + list(NFL_TEAMS.get(player.team, []))):
        known |= set(norm_name(alias).split())
    words = set(norm_name(name_text).split())
    return bool(words) and words <= known


class ParsedTeam(object):
    """One team block a paste produced: a name (maybe) and matched players."""

    __slots__ = ("name", "named", "players", "lines", "ambiguous", "slot_hint")

    def __init__(self, name: str, named: bool = True,
                 slot_hint: str = ""):
        self.name = name or "(unnamed team)"
        self.named = named
        # "Team 4: Name" carries the user's own slot number - honored when
        # that slot is free, and always reported in the assignment note.
        self.slot_hint = str(slot_hint or "")
        self.players = []       # store rows
        self.lines = []         # the raw line each row came from
        self.ambiguous = []     # (raw line, chosen name, runner-up name)

    def __len__(self):
        return len(self.players)

    def __repr__(self):
        return "<ParsedTeam %s %d players>" % (self.name, len(self.players))


class LeaguePaste(object):
    """What one paste produced - shown in full BEFORE anything is written."""

    def __init__(self):
        self.teams = []         # [ParsedTeam] with >=1 player each
        self.unmatched = []     # [(team name, raw line)] - REPORTED, not dropped
        self.skipped = []       # [raw line] recognized page furniture
        self.duplicates = []    # [(team name, player name)] repeat in one team
        self.conflicts = []     # [(player name, first team, second team)]
        self.warnings = []      # human-readable, shown in the preview

    @property
    def matched(self) -> int:
        return sum(len(t) for t in self.teams)

    def summary(self) -> str:
        return ("%d team(s), %d player(s) matched, %d line(s) unmatched, "
                "%d skipped" % (len(self.teams), self.matched,
                                len(self.unmatched), len(self.skipped)))


def parse_league_paste(text: str, matcher: Matcher,
                       league: Optional[LeagueConfig] = None) -> LeaguePaste:
    """Parse pasted league-rosters text into per-team rosters.

    Tolerates the shapes a user can actually copy: a team-name line
    followed by player lines, "Team 3: Name" markers, numbered lists,
    ESPN's leading slot labels, Yahoo's "Name Team - POS" tails, byes,
    stat columns and injury tags.

    Team headers are found by elimination: a non-junk line that does NOT
    resolve to a player starts a new team, but only once the current team
    already has players (or before any team exists). That way a mangled
    NAME inside a roster is reported as an unmatched line instead of
    silently splitting the block in two.

    NOTHING IS INVENTED. Every player row comes from a >= MATCH_MIN match
    against the rankings pool; every other line lands in .unmatched (worth
    reading) or .skipped (page furniture), and a team header that never
    collected a player is reported too.
    """
    result = LeaguePaste()
    teams_n = int(league.teams) if league is not None and league.teams else 10
    current = None
    pending = []          # teams in order, including empty ones (pruned later)
    claimed = {}          # player key -> team name (first claim wins)
    keys_here = set()     # keys on the CURRENT team (duplicate detection)
    after_blank = True    # a blank line is the separator between teams

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            after_blank = True
            continue
        was_after_blank, after_blank = after_blank, False
        if _is_junk_line(line):
            result.skipped.append(raw.strip())
            continue

        marker = _TEAM_MARKER.match(" ".join(line.split()))
        if marker:
            current = ParsedTeam(_team_name_of(line),
                                 slot_hint=marker.group(1))
            pending.append(current)
            keys_here = set()
            continue

        parsed = parse_line(_clean_for_player(line), teams_n)
        match = None
        if parsed is not None:
            match = matcher.match(parsed.name_text, parsed.pos_hint,
                                  parsed.team_hint)
            if match is not None and not _defense_plausible(
                    parsed.name_text, parsed.pos_hint, match.player):
                match = None
        if match is not None and match.score >= MATCH_MIN:
            if current is None:
                current = ParsedTeam("", named=False)
                pending.append(current)
                keys_here = set()
            key = match.player.key
            if key in keys_here:
                result.duplicates.append((current.name, match.player.name))
                continue
            if key in claimed and claimed[key] != current.name:
                result.conflicts.append((match.player.name, claimed[key],
                                         current.name))
                continue
            claimed[key] = current.name
            keys_here.add(key)
            current.players.append(_row(match.player))
            current.lines.append(raw.strip())
            if match.ambiguous:
                current.ambiguous.append(
                    (raw.strip(), match.player.name,
                     match.runner_up.name if match.runner_up else ""))
            continue

        # Not a player. A new team starts here only when the current one
        # already has players (or there is no current one at all) and the
        # line is not structurally a roster row - an unmatched NAME must
        # be reported, never turned into a phantom team that swallows the
        # rows below it.
        strength = _player_row_strength(line)
        if ((current is None or current.players)
                and (strength == 0 or (strength == 1 and was_after_blank))):
            name = _team_name_of(line)
            if not name:
                result.skipped.append(raw.strip())
                continue
            current = ParsedTeam(name)
            pending.append(current)
            keys_here = set()
        else:
            result.unmatched.append((current.name if current else "",
                                     raw.strip()))

    for team in pending:
        if team.players:
            result.teams.append(team)
        else:
            # A header that never collected a player is reported, never
            # written - it is far likelier a mangled name than a team.
            result.unmatched.append(("", team.name))

    for team in result.teams:
        if not team.named:
            result.warnings.append(
                "one block had no team-name line - it is stored as "
                "\"%s\"; add a name line above it and re-paste to fix"
                % team.name)
        if team.ambiguous:
            for raw_line, chosen, runner in team.ambiguous:
                result.warnings.append(
                    "%s: '%s' read as %s%s - check before saving"
                    % (team.name, raw_line, chosen,
                       " (or %s?)" % runner if runner else ""))
    if league is not None and league.teams and len(result.teams) > league.teams:
        result.warnings.append(
            "%d team blocks parsed but %s has only %d teams - check the "
            "split above" % (len(result.teams), league.name, league.teams))
    for player, first, second in result.conflicts:
        result.warnings.append(
            "%s appears on both %s and %s - kept on %s, drop the stale one "
            "and re-paste" % (player, first, second, first))
    return result


# --- applying a paste to the store -------------------------------------------

class PasteApply(object):
    """The plan for writing a paste - inspectable before anything lands."""

    def __init__(self, store: Dict):
        self.store = store
        self.assignments = []   # [(ParsedTeam, slot, note)]
        self.refused = []       # [(team name, why)]
        self.moved = []         # [(player, from team, to team)]
        # Claimed by a paste but ALSO listed in a layer this module does
        # not write (the draft capture, my roster yaml): [(player, team,
        # layer)]. Reported, never silently resolved.
        self.contested = []

    def teams_written(self) -> int:
        return len(self.assignments)

    def rows(self) -> List[Dict]:
        """JSON-able assignment rows for the panel preview."""
        return [{"team": t.name, "slot": slot, "note": note,
                 "count": len(t),
                 "players": [row_label(r) for r in t.players]}
                for t, slot, note in self.assignments]


def _norm_team_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    return " ".join(s.split())


def apply_paste(parsed: LeaguePaste, league: LeagueConfig,
                store: Optional[Dict] = None,
                view: Optional[LeagueView] = None,
                season: Optional[int] = None) -> PasteApply:
    """Fold parsed teams into a store doc. Pure - writes nothing.

    A pasted team lands on the slot whose name matches (exactly, then
    fuzzily), then on the slot a "Team 4:" marker named, then on the next
    free one. An existing slot is NEVER overwritten except by a name
    match, so a re-paste updates the right team and a stranger can never
    silently replace one - my own roster's slot and every draft-captured
    slot included (pass `view` so they are visible here). When the league
    is full and nothing matches, the team is refused WITH the reason
    rather than shoehorned in. Players the paste moved off another roster
    are removed there and reported - nobody ends up on two rosters.
    """
    doc = json.loads(json.dumps(store)) if store else empty_store(league, season)
    doc.setdefault("league", league.id)
    doc.setdefault("season", int(season or _default_season()))
    doc.setdefault("teams", {})
    plan = PasteApply(doc)

    existing = dict((str(s), str((e or {}).get("name") or ""))
                    for s, e in (doc.get("teams") or {}).items()
                    if isinstance(e, dict))
    by_name = dict((_norm_team_name(n), s) for s, n in existing.items() if n)
    taken = set(existing)
    # Slots the OTHER layers already own (my roster file, the draft
    # capture). Their names are match targets, but a nameless block must
    # never be dropped on top of one.
    outranks = {}
    for t in (view.teams if view is not None else []):
        if t.source == SRC_STORE:
            continue
        taken.add(t.slot)
        if t.name:
            by_name.setdefault(_norm_team_name(t.name), t.slot)
        if t.source == SRC_DRAFT:
            outranks[t.slot] = t.source_label
    # Slot names the league config declares, so a first paste lands on the
    # same slot numbering the draft capture and league yaml already use.
    for i, cfg_name in enumerate(league.team_names or [], start=1):
        by_name.setdefault(_norm_team_name(str(cfg_name)), str(i))

    for team in parsed.teams:
        norm = _norm_team_name(team.name)
        slot, note = None, ""
        if team.named and norm and norm in by_name:
            slot = by_name[norm]
            note = ("replaces the %d player(s) stored for slot %s"
                    % (len(((doc["teams"].get(slot) or {}).get("players")
                            or [])), slot)
                    if slot in existing else "name matches slot %s" % slot)
        elif team.named and norm:
            close = difflib.get_close_matches(norm, list(by_name), 1, 0.86)
            if close:
                slot = by_name[close[0]]
                note = "name-matched to slot %s (%s)" % (
                    slot, existing.get(slot) or close[0])
        if slot is None and _valid_slot(team.slot_hint, league, taken):
            slot = team.slot_hint
            note = "slot %s as the paste numbered it" % slot
        if slot is None:
            slot = _next_free_slot(taken, league)
            note = "new slot %s" % slot if slot else ""
        if slot is None:
            plan.refused.append(
                (team.name, "%s already has all %d rosters and this name "
                            "matches none of them" % (league.name,
                                                      league.teams)))
            continue
        if slot in outranks:
            note = ("%s; the %s still outranks the store for that slot"
                    % (note or "slot %s" % slot, outranks[slot]))
        taken.add(slot)
        by_name[norm or "slot-%s" % slot] = slot
        doc["teams"][slot] = {"name": team.name,
                              "players": [dict(r) for r in team.players]}
        plan.assignments.append((team, slot, note))

        # A player this paste puts on one roster cannot still sit on another.
        keys = set(row_key(r) for r in team.players)
        for other in (view.teams if view is not None else []):
            if other.slot == slot or other.source == SRC_STORE:
                continue
            for r in other.players:
                if row_key(r) in keys:
                    plan.contested.append((str(r.get("player")), other.name,
                                           other.source_label))
        for other_slot, entry in doc["teams"].items():
            if other_slot == slot or not isinstance(entry, dict):
                continue
            keep = []
            for r in entry.get("players") or []:
                if row_key(r) in keys:
                    plan.moved.append((str(r.get("player")),
                                       str(entry.get("name") or other_slot),
                                       team.name))
                else:
                    keep.append(r)
            entry["players"] = keep
    return plan


def _valid_slot(hint: str, league: LeagueConfig, taken) -> bool:
    """A paste's own team number is honored only when it is a real, free
    slot in THIS league - '7' in an 8-team league, never in a 4-team one."""
    if not hint or hint in taken:
        return False
    try:
        return 1 <= int(hint) <= int(league.teams or 0)
    except (TypeError, ValueError):
        return False


def _next_free_slot(taken, league: LeagueConfig) -> Optional[str]:
    for i in range(1, int(league.teams or 0) + 1):
        if str(i) not in taken:
            return str(i)
    return None


def coverage_after(plan: PasteApply, league: LeagueConfig,
                   view: Optional[LeagueView] = None) -> Tuple[int, int]:
    """Coverage this plan WOULD produce - the preview's before/after line."""
    slots = set()
    if view is not None:
        slots |= set(t.slot for t in view.teams
                     if t.source != SRC_STORE and t.players)
    for slot, entry in (plan.store.get("teams") or {}).items():
        if isinstance(entry, dict) and entry.get("players"):
            slots.add(str(slot))
    return len(slots), int(league.teams or 0)


# One board, cached by path+mtime: the panel previews several pastes in a
# row and must not reload a 268-row csv each time. Single entry on
# purpose - two leagues alternating simply reload, which stays correct.
_MATCHER_CACHE = {}


def matcher_for(league: LeagueConfig,
                data_root: Optional[str] = None) -> Optional[Matcher]:
    """Fuzzy Matcher over this league's rankings pool, None when it is
    missing (a paste cannot be matched without a board - say so, never
    guess)."""
    path = os.path.join(data_root or HERE, league.rankings_csv)
    if not os.path.exists(path):
        return None
    try:
        stamp = (path, os.path.getmtime(path))
    except OSError:
        return None
    if _MATCHER_CACHE.get("stamp") != stamp:
        _MATCHER_CACHE["stamp"] = stamp
        _MATCHER_CACHE["matcher"] = Matcher(load_players(path))
    return _MATCHER_CACHE["matcher"]


# --- CLI ---------------------------------------------------------------------

def _print_view(view: LeagueView, full: bool) -> None:
    print("%s (%s) - %s" % (view.name, view.league_id, view.coverage_text()))
    counts = view.source_counts()
    print("  layers: %s" % ", ".join(
        "%s %d" % (SRC_LABELS[k], counts.get(k, 0))
        for k in (SRC_DRAFT, SRC_STORE, SRC_OWN)))
    banner = view.banner_text()
    if banner:
        print("  %s" % banner)
    for note in view.notes:
        print("  note: %s" % note)
    print("")
    for team in view.teams:
        print("  [%s] %s%s - %d player(s), %s"
              % (team.slot, team.name, "  (mine)" if team.mine else "",
                 len(team), team.source_label))
        if full:
            for r in team.players:
                print("        %s" % row_label(r))
    if view.expected_teams > view.known_teams:
        print("\n  %d roster(s) still unknown - paste them in the Model "
              "Settings panel (League rosters) or with --paste-file."
              % (view.expected_teams - view.known_teams))


def _print_paste(parsed: LeaguePaste, plan: PasteApply) -> None:
    print("PARSED: %s" % parsed.summary())
    for team, slot, note in plan.assignments:
        print("\n  %s -> slot %s%s"
              % (team.name, slot, "  (%s)" % note if note else ""))
        for r in team.players:
            print("      %s" % row_label(r))
    for team, why in plan.refused:
        print("\n  REFUSED %s - %s" % (team, why))
    if parsed.unmatched:
        print("\n  UNMATCHED (%d) - nothing was invented for these lines:"
              % len(parsed.unmatched))
        for team, line in parsed.unmatched:
            print("      %-22s %s" % (team or "(no team)", line))
    if parsed.duplicates:
        print("\n  duplicates ignored: %s"
              % ", ".join("%s on %s" % (p, t) for t, p in parsed.duplicates))
    if plan.moved:
        print("\n  moved off their old roster: %s"
              % ", ".join("%s (%s -> %s)" % m for m in plan.moved))
    if plan.contested:
        print("\n  ALSO LISTED ELSEWHERE (not touched by this write - fix "
              "the other file if the paste is right):")
        for player, team, layer in plan.contested:
            print("      %s is on %s in the %s" % (player, team, layer))
    if parsed.skipped:
        print("\n  skipped %d page-furniture line(s)" % len(parsed.skipped))
    for w in parsed.warnings:
        print("  WARNING: %s" % w)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.leagueview",
        description="League-wide rosters for leagues no API can read: "
                    "merge what we know, report coverage, ingest pasted "
                    "rosters.")
    ap.add_argument("--league", default="yahoo-main",
                    help="league id (leagues/<id>.yaml); default yahoo-main")
    ap.add_argument("--paste-file", default=None,
                    help="file of pasted league rosters to parse (previews "
                         "only; add --save to write)")
    ap.add_argument("--save", action="store_true",
                    help="write the parsed rosters to data/league-<id>.json")
    ap.add_argument("--summary", action="store_true",
                    help="print coverage AND every known roster in full")
    ap.add_argument("--data-root", default=None,
                    help="project root to read/write under (default: this "
                         "checkout)")
    args = ap.parse_args(argv)

    root = args.data_root
    try:
        league = load_config(args.league, root)
    except (IOError, OSError):
        print("No league config at %s" % league_config_path(args.league, root))
        return 2

    matcher = matcher_for(league, root)
    if matcher is None and args.paste_file:
        print("Rankings CSV missing (%s) - a paste cannot be matched against "
              "the player pool without it."
              % os.path.join(root or HERE, league.rankings_csv))
        return 2

    if args.paste_file:
        with open(args.paste_file, "r") as fh:
            text = fh.read()
        parsed = parse_league_paste(text, matcher, league)
        plan = apply_paste(parsed, league, load_store(league.id, root),
                           load_league_view(league, matcher, root))
        _print_paste(parsed, plan)
        if not args.save:
            print("\nNOTHING WRITTEN - re-run with --save to store this.")
            return 0
        path = save_store(plan.store, league.id, root)
        print("\nWrote %d roster(s) to %s" % (plan.teams_written(), path))

    view = load_league_view(league, matcher, root)
    print("")
    _print_view(view, args.summary or bool(args.paste_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
