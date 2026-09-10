"""Rival-tendency miner: what each manager's past drafts say they will do.

Turns historical draft results into per-manager tendencies - position-by-round
frequency, earliest QB/TE/K round, and a reach number (how far ahead of ADP a
manager takes players) - then derives a favors_positions list compatible with
engine/intel.py's managers schema. That list is the one that matters live:
Intel.manager_appetite() folds it straight into survival odds, so "he always
hoards RBs" stops being folklore and starts moving the wait/pick math.

Two loaders:

* from_saves(paths)  - our own saves/*.json snapshots. Positions come off the
  player_key suffix ("puka nacua|WR"); ADP is looked up in data/rankings.csv,
  a fair proxy for this season's saves and increasingly noisy for older ones.
* from_espn(lg_by_year) - ESPN draft history via espn-api, using the same raw
  draft feed engine/espn.py reads. UNTESTED LIVE: it needs the cookies from
  SETUP_ESPN.md, so the live run is a runbook item, not a test.

MERGE ORDER (the contract this module's yaml depends on): Intel.merge() lets
the LATER file win outright - intel.py does self.managers.update(other.managers),
so a slot present in a later file replaces the earlier read for that slot.
warroom.py loads data/player_intel.yaml first and merges data/my_calls.yaml
LAST. A mined tendencies file must therefore be merged BETWEEN the two:

    base.merge(Intel.load("data/tendencies.<league>.yaml"), matcher)   # mined
    base.merge(Intel.load("data/my_calls.yaml"), matcher)              # user

With that ordering the user's qualitative my_calls read on any slot replaces
the mined one - an explicit opinion is a replacement, not a second vote.
Verified in tests/tendencies_test.py.
"""

import json
import os
from statistics import median
from typing import Dict, List, Optional

import yaml

from .models import load_players, norm_pos

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ESPN defaultPositionId -> fantasy position (espn-api uses the same table).
ESPN_POS_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}


def _round_of(overall: int, teams: int) -> int:
    return (overall - 1) // teams + 1


class Tendencies(object):
    """Per-manager reads mined from historical drafts.

    Input seasons: a list, one entry per historical draft. Each entry is
    either a plain list of picks or {"teams": n, "picks": [...]}; each pick a
    dict with overall, team (slot or ESPN teamId - any stable id), position,
    and optional adp at draft time. Team count is inferred from the distinct
    ids when not given, which is right for any completed snake draft.
    """

    EARLY_ROUNDS = 6      # the window where tendencies decide survival odds
    FAVOR_RATIO = 1.5     # early share must beat the room's by this factor...
    FAVOR_LIFT = 0.12     # ...and by this many absolute share points
    MIN_EARLY_PICKS = 2   # one early pick is an anecdote, not a tendency
    EARLY_BY = 2          # onesie attacked >= 2 rounds before the room = a read
    ONESIES = ("QB", "TE", "K")   # one-starter spots where timing IS the read
    MIN_REACH_N = 3       # fewer ADP-known picks than this says nothing

    def __init__(self, seasons: List, league: str = "league"):
        self.league = league
        self.seasons = [self._norm_season(s) for s in (seasons or [])]
        self.seasons = [s for s in self.seasons if s["picks"]]
        self.profiles = {}   # manager id -> profile dict
        self._mine()

    # --- loaders -----------------------------------------------------------
    @classmethod
    def from_saves(cls, paths: List[str], rankings_csv: Optional[str] = None,
                   league: Optional[str] = None) -> "Tendencies":
        """Build from our own save JSONs (saves/*.json), one draft per file.

        The manager id is the draft slot, so this only tracks a manager
        across saves when the draft order held; ADP comes from TODAY's
        rankings CSV, so reach numbers from old saves are approximate.
        """
        if rankings_csv is None:
            rankings_csv = os.path.join(HERE, "data", "rankings.csv")
        adp_by_key = {}
        if os.path.exists(rankings_csv):
            for p in load_players(rankings_csv):
                if p.adp is not None:
                    adp_by_key[p.key] = float(p.adp)

        seasons = []
        lid = league
        for path in paths:
            with open(path, "r") as fh:
                data = json.load(fh)
            if lid is None:
                lid = data.get("league_id")
            picks = []
            for row in data.get("picks", []) or []:
                key = row.get("player_key", "") or ""
                pos = key.rsplit("|", 1)[-1] if "|" in key else ""
                picks.append({"overall": row.get("overall"),
                              "team": row.get("team"),
                              "position": pos,
                              "adp": adp_by_key.get(key)})
            seasons.append({"teams": data.get("teams"), "picks": picks})
        return cls(seasons, league=lid or "league")

    @classmethod
    def from_espn(cls, lg_by_year, league: str = "espn") -> "Tendencies":
        """Build from ESPN draft history. UNTESTED LIVE (needs cookies).

        lg_by_year: {year: espn_api League} (or an iterable of Leagues), each
        connected via engine.espn.connect(season=year). Reads the raw draft
        feed the way engine/espn.py's draft_picks does - espn_api's own
        lg.draft is empty unless ESPN flags the draft complete - and derives
        overall from roundId/roundPickNumber, sliding index-derived guesses
        past claimed slots so no two picks share an overall. Positions come
        from ESPN's pro-player list (defaultPositionId); unknown ids keep
        position "" and drop out of the frequency math rather than lying.

        The manager id is the ESPN teamId, stable across seasons; pass
        slot_map to emit_yaml to line those ids up with THIS year's draft
        slots. ESPN's draft feed carries no ADP, so reach stays unknown.
        """
        if isinstance(lg_by_year, dict):
            leagues = [lg_by_year[y] for y in sorted(lg_by_year)]
        else:
            leagues = list(lg_by_year)

        seasons = []
        for lg in leagues:
            pos_by_id = {}
            try:
                for pro in (lg.espn_request.get_pro_players() or []):
                    pid = pro.get("id")
                    pos = ESPN_POS_ID.get(pro.get("defaultPositionId"))
                    if pid is not None and pos:
                        pos_by_id[pid] = pos
            except Exception:
                pos_by_id = {}   # positions degrade to "", never crash

            data = lg.espn_request.get_league_draft()
            raw = (data.get("draftDetail") or {}).get("picks") or []
            teams = len(getattr(lg, "teams", []) or []) or 10
            used = set()
            picks = []
            for i, p in enumerate(raw):
                rnd = int(p.get("roundId") or 0)
                rpick = int(p.get("roundPickNumber") or 0)
                overall = (rnd - 1) * teams + rpick if rnd and rpick else i + 1
                while overall in used:   # never double-book a slot
                    overall += 1
                used.add(overall)
                picks.append({"overall": overall,
                              "team": p.get("teamId"),
                              "position": pos_by_id.get(p.get("playerId"), ""),
                              "adp": None})
            seasons.append({"teams": teams, "picks": picks})
        return cls(seasons, league=league)

    # --- normalization -----------------------------------------------------
    def _norm_season(self, season) -> Dict:
        if isinstance(season, dict):
            teams = season.get("teams")
            raw = season.get("picks", []) or []
        else:
            teams = None
            raw = list(season or [])

        picks = []
        for r in raw:
            overall = r.get("overall")
            team = r.get("team", r.get("team_slot_or_id", r.get("slot",
                          r.get("team_id"))))
            if overall is None or team is None:
                continue
            adp = r.get("adp", r.get("adp_at_time"))
            picks.append({"overall": int(overall), "team": team,
                          "pos": norm_pos(r.get("position", r.get("pos", ""))),
                          "adp": float(adp) if adp is not None else None})
        if not teams:
            teams = len(set(p["team"] for p in picks)) or 1
        return {"teams": int(teams), "picks": picks}

    # --- mining ------------------------------------------------------------
    def _blank(self, mid) -> Dict:
        return {"id": mid, "drafts": set(), "picks": 0,
                "pos_by_round": {},   # round -> {pos: count} across seasons
                "early": {},          # pos -> count in rounds 1..EARLY_ROUNDS
                "early_total": 0,
                "firsts": {},         # pos -> [first round, one per season]
                "deltas": []}         # adp - overall, where adp is known

    def _mine(self) -> None:
        mgr = {}
        for si, season in enumerate(self.seasons):
            teams = season["teams"]
            season_first = {}   # (mid, pos) -> earliest round this season
            for pk in season["picks"]:
                mid = pk["team"]
                d = mgr.setdefault(mid, self._blank(mid))
                d["drafts"].add(si)
                d["picks"] += 1
                pos = pk["pos"]
                if not pos:
                    continue   # unknown position: no information, not "other"
                rnd = _round_of(pk["overall"], teams)
                by_rnd = d["pos_by_round"].setdefault(rnd, {})
                by_rnd[pos] = by_rnd.get(pos, 0) + 1
                if rnd <= self.EARLY_ROUNDS:
                    d["early"][pos] = d["early"].get(pos, 0) + 1
                    d["early_total"] += 1
                k = (mid, pos)
                if k not in season_first or rnd < season_first[k]:
                    season_first[k] = rnd
                if pk["adp"] is not None:
                    d["deltas"].append(pk["adp"] - pk["overall"])
            for (mid, pos), rnd in season_first.items():
                mgr[mid]["firsts"].setdefault(pos, []).append(rnd)

        league_early = {}
        league_early_total = 0
        for d in mgr.values():
            for pos, cnt in d["early"].items():
                league_early[pos] = league_early.get(pos, 0) + cnt
            league_early_total += d["early_total"]

        typical = {}   # mid -> {pos: median of per-season first rounds}
        for mid, d in mgr.items():
            typical[mid] = dict((pos, median(rnds))
                                for pos, rnds in d["firsts"].items())

        self.profiles = {}
        for mid, d in mgr.items():
            self.profiles[mid] = self._profile(mid, d, typical,
                                               league_early, league_early_total)

    def _profile(self, mid, d, typical, league_early, league_early_total) -> Dict:
        scored = []   # (strength, pos, human why)

        # Early-round share vs the ROOM (self excluded, so a hoarder cannot
        # drag the baseline up toward himself).
        for pos, cnt in sorted(d["early"].items()):
            tot = d["early_total"]
            if not tot or cnt < self.MIN_EARLY_PICKS:
                continue
            share = cnt / float(tot)
            base_tot = league_early_total - tot
            base = ((league_early.get(pos, 0) - cnt) / float(base_tot)
                    if base_tot > 0 else 0.0)
            if share >= base * self.FAVOR_RATIO and share - base >= self.FAVOR_LIFT:
                scored.append((share / max(base, 1e-9), pos,
                               "%s %d%% of rds 1-%d (room %d%%)"
                               % (pos, round(share * 100), self.EARLY_ROUNDS,
                                  round(base * 100))))

        # Onesie timing: attacking QB/TE/K rounds before the room is a read
        # even though the share math never trips (everyone drafts exactly one).
        for pos in self.ONESIES:
            mine = typical.get(mid, {}).get(pos)
            others = [t[pos] for m2, t in typical.items()
                      if m2 != mid and pos in t]
            if mine is None or not others:
                continue
            room = median(others)
            if mine <= room - self.EARLY_BY and \
                    pos not in [p for _, p, _ in scored]:
                scored.append((1.0 + (room - mine) / 4.0, pos,
                               "first %s rd %d (room rd %d)"
                               % (pos, int(mine), int(round(room)))))

        scored.sort(key=lambda t: (-t[0], t[1]))
        favors = [pos for _, pos, _ in scored[:3]]
        whys = [why for _, _, why in scored[:3]]

        reach = None
        if len(d["deltas"]) >= self.MIN_REACH_N:
            reach = sum(d["deltas"]) / float(len(d["deltas"]))
            if reach >= 2:
                whys.append("takes players ~%d picks before ADP" % round(reach))
            elif reach <= -2:
                whys.append("waits ~%d picks past ADP" % round(-reach))

        earliest = dict((pos, min(rnds)) for pos, rnds in d["firsts"].items())
        note = "mined from %d draft%s" % (len(d["drafts"]),
                                          "" if len(d["drafts"]) == 1 else "s")
        note += ": " + "; ".join(whys) if whys else ": no strong read"

        return {"id": mid,
                "drafts": len(d["drafts"]),
                "picks": d["picks"],
                "pos_by_round": d["pos_by_round"],
                "earliest": earliest,
                "typical_first": dict(typical.get(mid, {})),
                "reach": reach,
                "reach_n": len(d["deltas"]),
                "favors_positions": favors,
                "note": note}

    # --- access ------------------------------------------------------------
    def profile(self, mid) -> Optional[Dict]:
        return self.profiles.get(mid)

    def __len__(self):
        return len(self.profiles)

    # --- output ------------------------------------------------------------
    def emit_yaml(self, path: str, slot_map: Optional[Dict] = None,
                  min_drafts: int = 1) -> int:
        """Write data/tendencies.<league>.yaml in the my_calls managers format.

        slot_map translates mined manager ids (ESPN teamIds, or old draft
        slots) to THIS year's draft slots; ids that are not int-able and not
        mapped are skipped, because Intel keys managers by int(slot).
        Returns the number of manager rows written.
        """
        rows = []
        for mid in sorted(self.profiles, key=lambda m: str(m)):
            prof = self.profiles[mid]
            if prof["drafts"] < min_drafts:
                continue
            slot = slot_map.get(mid, mid) if slot_map else mid
            try:
                slot = int(slot)
            except (TypeError, ValueError):
                continue
            rows.append({"slot": slot,
                         "name": "Team %d" % slot,
                         "favors_positions": list(prof["favors_positions"]),
                         "reach": round(prof["reach"], 1) if prof["reach"]
                                  is not None else 0,
                         "note": prof["note"]})
        rows.sort(key=lambda r: r["slot"])

        header = (
            "# Mined rival tendencies - written by engine/tendencies.py from %d\n"
            "# historical draft(s). Same managers schema as data/my_calls.yaml.\n"
            "#\n"
            "# MERGE ORDER MATTERS: Intel.merge() lets the LATER file win per\n"
            "# slot (intel.py updates the managers dict). Merge this file AFTER\n"
            "# data/player_intel.yaml but BEFORE data/my_calls.yaml, so your\n"
            "# hand-written manager reads always replace these mined ones.\n"
            % len(self.seasons))
        body = yaml.safe_dump({"managers": rows}, default_flow_style=False,
                              sort_keys=False)
        with open(path, "w") as fh:
            fh.write(header + "\n" + body)
        return len(rows)

    def summary(self) -> str:
        """One line per manager, for the runbook eyeball check."""
        lines = []
        for mid in sorted(self.profiles, key=lambda m: str(m)):
            p = self.profiles[mid]
            lines.append("Team %-4s %s" % (mid, p["note"]))
        return "\n".join(lines)
