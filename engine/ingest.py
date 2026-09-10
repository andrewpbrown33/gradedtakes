"""Forgiving pick ingestion: parse messy pasted text, fuzzy-match player names.

Designed for a 30-second clock: never blocks, never asks a question mid-draft.
High-confidence matches are auto-accepted; ambiguous ones take the best
candidate and raise a visible warning that `undo` can fix.
"""

import difflib
import re
from typing import Dict, List, Optional, Tuple

from .models import Player, norm_name, norm_pos

NFL_TEAMS = {
    "ARI": ["cardinals", "arizona"], "ATL": ["falcons", "atlanta"],
    "BAL": ["ravens", "baltimore"], "BUF": ["bills", "buffalo"],
    "CAR": ["panthers", "carolina"], "CHI": ["bears", "chicago"],
    "CIN": ["bengals", "cincinnati"], "CLE": ["browns", "cleveland"],
    "DAL": ["cowboys", "dallas"], "DEN": ["broncos", "denver"],
    "DET": ["lions", "detroit"], "GB": ["packers", "green bay"],
    "HOU": ["texans", "houston"], "IND": ["colts", "indianapolis"],
    "JAC": ["jaguars", "jacksonville", "jags"], "JAX": ["jaguars", "jacksonville"],
    "KC": ["chiefs", "kansas city"], "LV": ["raiders", "las vegas", "oakland"],
    "LAC": ["chargers", "la chargers", "los angeles chargers"],
    "LAR": ["rams", "la rams", "los angeles rams"],
    "MIA": ["dolphins", "miami"], "MIN": ["vikings", "minnesota"],
    "NE": ["patriots", "new england", "pats"], "NO": ["saints", "new orleans"],
    "NYG": ["giants", "new york giants"], "NYJ": ["jets", "new york jets"],
    "PHI": ["eagles", "philadelphia"], "PIT": ["steelers", "pittsburgh"],
    "SF": ["49ers", "niners", "san francisco"], "SEA": ["seahawks", "seattle"],
    "TB": ["buccaneers", "bucs", "tampa bay", "tampa"],
    "TEN": ["titans", "tennessee"], "WAS": ["commanders", "washington"],
}
TEAM_ABBRS = set(NFL_TEAMS.keys())
POS_TOKENS = {"QB", "RB", "WR", "TE", "K", "PK", "DEF", "DST", "D/ST", "DS"}

# Lines that carry no pick information.
SKIP_LINE = re.compile(
    r"^\s*(round\s*\d+|draft\s*results?|pick\s*history|results?|team|players?|"
    r"my\s*team|on\s*the\s*clock|[-=_*\s]+)\s*$", re.I)

# Dragged-in files and pasted paths are noise, never picks.
FILE_PATH = re.compile(r"^\s*(/|~/|file:)|\.(png|jpe?g|heic|gif|pdf|csv|txt|"
                       r"mov|mp4)\b", re.I)


class Match(object):
    def __init__(self, player: Player, score: float, ambiguous: bool = False,
                 runner_up: Optional[Player] = None):
        self.player = player
        self.score = score
        self.ambiguous = ambiguous
        self.runner_up = runner_up


class ParsedLine(object):
    def __init__(self, raw: str, name_text: str, overall: Optional[int] = None,
                 pos_hint: Optional[str] = None, team_hint: Optional[str] = None):
        self.raw = raw
        self.name_text = name_text
        self.overall = overall
        self.pos_hint = pos_hint
        self.team_hint = team_hint


def _strip_pick_markers(text: str) -> Tuple[str, Optional[int]]:
    """Pull an overall pick number off the front of a line, if present."""
    overall = None
    s = text.strip()

    # "Pick 14:", "Pick #14", "#14"
    m = re.match(r"^\s*(?:pick|selection)?\s*#?\s*(\d{1,3})\s*[.):\-]\s+", s, re.I)
    # "1.05" / "1-05" round.pick form takes priority when it looks like one
    m_rp = re.match(r"^\s*(?:r(?:ound)?\s*)?(\d{1,2})[.\-](\d{1,2})\b[\s:.)\-]*", s, re.I)

    if m_rp and not re.match(r"^\s*\d{1,3}\.\s", s):
        s = s[m_rp.end():]
        # round/pick converted by caller (needs team count); keep as marker
        overall = -1  # sentinel: positional info present but needs conversion
        return s.strip(), overall
    if m:
        overall = int(m.group(1))
        s = s[m.end():]
        return s.strip(), overall

    # "(14) Name"
    m2 = re.match(r"^\s*\((\d{1,3})\)\s*", s)
    if m2:
        overall = int(m2.group(1))
        s = s[m2.end():]
    return s.strip(), overall


def _round_pick_overall(text: str, teams: int) -> Tuple[str, Optional[int]]:
    m = re.match(r"^\s*(?:r(?:ound)?\s*)?(\d{1,2})[.\-](\d{1,2})\b[\s:.)\-]*", text, re.I)
    if not m:
        return text, None
    rnd, pk = int(m.group(1)), int(m.group(2))
    if rnd < 1 or pk < 1 or pk > teams:
        return text, None
    return text[m.end():].strip(), (rnd - 1) * teams + pk


def parse_line(raw: str, teams: int = 10) -> Optional[ParsedLine]:
    """Turn one messy line into a name + optional pick/pos/team hints."""
    line = raw.strip()
    if not line or SKIP_LINE.match(line) or FILE_PATH.search(line):
        return None
    line = re.sub(r"\s+", " ", line)

    # Strip common noise words.
    line = re.sub(r"\b(selected|drafted|selects|picks|takes|auto[- ]?pick(ed)?|"
                  r"keeper)\b", " ", line, flags=re.I)

    # Round.pick form (1.05) first, then plain pick numbers.
    rest, overall = _round_pick_overall(line, teams)
    if overall is None:
        rest, ov = _strip_pick_markers(line)
        overall = None if (ov is None or ov == -1) else ov
    else:
        rest = rest

    # Position hint: "WR - CIN", ", WR", "(WR)"
    pos_hint = None
    m = re.search(r"[\s,\-|(\[]+(QB|RB|WR|TE|PK|K|DEF|DST|D/ST)\b", rest, re.I)
    if m:
        pos_hint = norm_pos(m.group(1))
        rest = (rest[:m.start()] + " " + rest[m.end():]).strip()

    # NFL team hint anywhere as a standalone token.
    team_hint = None
    tokens = re.split(r"[\s,\-|()\[\]/]+", rest)
    kept = []
    for t in tokens:
        if not t:
            continue
        up = t.upper().rstrip(".")
        if up in TEAM_ABBRS and team_hint is None and len(kept) > 0:
            team_hint = up
            continue
        kept.append(t)
    rest = " ".join(kept).strip(" ,-|.")

    # Drop trailing bye-week / rank noise like "bye 11" or "#23"
    rest = re.sub(r"\bbye\s*\d+\b", " ", rest, flags=re.I)
    rest = re.sub(r"#\d+", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" ,-|.")

    if not rest or not re.search(r"[a-zA-Z]", rest):
        return None
    return ParsedLine(raw.strip(), rest, overall, pos_hint, team_hint)


class Matcher(object):
    """Fuzzy name matcher over the player pool."""

    def __init__(self, players: List[Player]):
        self.players = players
        self.aliases = {}   # normalized alias -> [players]
        for p in players:
            self._add(norm_name(p.name), p)
            for alias in self._extra_aliases(p):
                self._add(alias, p)

    def _add(self, alias: str, player: Player):
        if not alias:
            return
        self.aliases.setdefault(alias, [])
        if player not in self.aliases[alias]:
            self.aliases[alias].append(player)

    def _extra_aliases(self, p: Player) -> List[str]:
        out = []
        if p.pos == "DEF":
            base = norm_name(p.name).replace(" defense", "").strip()
            out.append(base)
            names = NFL_TEAMS.get(p.team, [])
            for n in names:
                out.append(norm_name(n))
                out.append(norm_name(n + " defense"))
                out.append(norm_name(n + " def"))
            if p.team:
                out.append(norm_name(p.team))
                out.append(norm_name(p.team + " def"))
        if p.pos == "K":
            out.append(norm_name(p.name + " k"))
        return [a for a in out if a]

    def match(self, text: str, pos_hint: Optional[str] = None,
              team_hint: Optional[str] = None,
              exclude_keys: Optional[set] = None) -> Optional[Match]:
        q = norm_name(text)
        if not q:
            return None
        exclude_keys = exclude_keys or set()
        qtokens = set(q.split())

        scored = []
        for p in self.players:
            score = self._score(p, q, qtokens, pos_hint, team_hint)
            if score > 0:
                scored.append((score, p))
        if not scored:
            return None

        scored.sort(key=lambda sp: (-sp[0], sp[1].rank))
        best_list = scored

        # A confident hit on an already-drafted player must stay that player, so
        # re-pasting a block reports duplicates instead of drafting someone else.
        # Only a weak hit falls through to a close undrafted alternative (two
        # players sharing a surname, one already gone).
        if exclude_keys and scored[0][1].key in exclude_keys and scored[0][0] < 90:
            live = [sp for sp in scored if sp[1].key not in exclude_keys]
            if live and scored[0][0] - live[0][0] <= 10:
                best_list = live

        best_score, best = best_list[0]
        runner = best_list[1][1] if len(best_list) > 1 else None
        runner_score = best_list[1][0] if len(best_list) > 1 else 0.0

        if best_score < 55:
            return None
        ambiguous = (best_score < 72) or (runner_score and best_score - runner_score < 8)
        return Match(best, best_score, ambiguous, runner if ambiguous else None)

    def _score(self, p: Player, q: str, qtokens: set,
               pos_hint: Optional[str], team_hint: Optional[str]) -> float:
        cand_names = [norm_name(p.name)] + self._extra_aliases(p)
        best = 0.0
        for cand in cand_names:
            if not cand:
                continue
            if cand == q:
                best = max(best, 100.0)
                continue
            ctokens = set(cand.split())
            if not ctokens:
                continue
            inter = ctokens & qtokens
            coverage = len(inter) / float(len(ctokens))
            precision = len(inter) / float(len(qtokens)) if qtokens else 0.0
            token_score = 62 * coverage + 28 * precision
            last = cand.split()[-1]
            if last in qtokens:
                token_score += 12
            ratio = difflib.SequenceMatcher(None, cand, q).ratio()
            best = max(best, token_score, ratio * 88)

        if best <= 0:
            return 0.0
        if pos_hint:
            best += 8 if p.pos == pos_hint else -30
        if team_hint:
            best += 6 if p.team == team_hint else -2
        # Nudge toward likelier players when everything else ties.
        best += max(0.0, 3.0 - (p.rank / 100.0))
        return best


class IngestResult(object):
    def __init__(self):
        self.applied = []      # (Pick, Player)
        self.duplicates = []   # Player already drafted
        self.warnings = []     # human-readable strings
        self.unmatched = []    # raw lines


def _explode_commas(raw: str, state, matcher: Matcher) -> List[str]:
    """Split 'nacua, chase, robinson' into one pick per segment.

    Only when at least two comma segments independently match distinct players
    does the line become a list; otherwise it stays whole, so single-pick forms
    like 'Lamb, DAL' and 'CeeDee Lamb, CIN' keep working.
    """
    if "," not in raw:
        return [raw]
    def is_bare_hint(seg):
        """A lone team/position code ('DAL', 'WR') is a hint, not a pick."""
        tok = seg.strip().upper().rstrip(".")
        return tok in TEAM_ABBRS or tok in POS_TOKENS

    segments = [s.strip() for s in raw.split(",")
                if s.strip() and not is_bare_hint(s)]
    if len(segments) < 2:
        return [raw]
    matched_keys = set()
    for seg in segments:
        parsed = parse_line(seg, state.teams)
        if parsed is None:
            continue
        m = matcher.match(parsed.name_text, parsed.pos_hint, parsed.team_hint,
                          exclude_keys=set(state.drafted.keys()))
        if m is not None and m.score >= 62:
            matched_keys.add(m.player.key)
    return segments if len(matched_keys) >= 2 else [raw]


def ingest_text(text: str, state, matcher: Matcher) -> IngestResult:
    """Parse and apply one or many pick lines. Idempotent on repeats."""
    result = IngestResult()
    for raw_line in text.splitlines():
        for raw in _explode_commas(raw_line, state, matcher):
            parsed = parse_line(raw, state.teams)
            if parsed is None:
                continue
            m = matcher.match(parsed.name_text, parsed.pos_hint, parsed.team_hint,
                              exclude_keys=set(state.drafted.keys()))
            if m is None:
                result.unmatched.append(parsed.raw)
                continue
            if state.is_drafted(m.player.key):
                result.duplicates.append(m.player)
                continue

            overall = parsed.overall
            if overall is not None and (overall < 1 or overall > state.total_picks()
                                        or overall in state.picks):
                overall = None
            pick = state.apply_pick(m.player, overall, parsed.raw)
            result.applied.append((pick, m.player))
            if m.ambiguous:
                alt = (" (or %s?)" % m.runner_up.name) if m.runner_up else ""
                result.warnings.append(
                    "'%s' matched %s%s - `undo` if wrong" %
                    (parsed.name_text, m.player.name, alt))
    return result
