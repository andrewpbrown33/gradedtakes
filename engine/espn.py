"""Read-only ESPN Fantasy connection with live draft auto-ingest.

ESPN has no official API; this uses the same private endpoints the website
uses, authenticated with two cookies you copy from your own browser. Setup is
in SETUP_ESPN.md.

Read-only by design: this module can watch your league but cannot change it.
No add, drop, or draft-pick call is wired up.
"""

import json
import os
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(HERE, "data", "espn_secrets.json")


class EspnError(RuntimeError):
    pass


def load_secrets() -> Dict:
    if not os.path.exists(SECRETS):
        raise EspnError(
            "No data/espn_secrets.json yet. Follow SETUP_ESPN.md steps 1-3 "
            "(about two minutes, done once).")
    with open(SECRETS) as fh:
        s = json.load(fh)
    missing = [k for k in ("league_id", "espn_s2", "swid") if not s.get(k)]
    if missing:
        raise EspnError("data/espn_secrets.json is missing: %s" % ", ".join(missing))
    swid = str(s["swid"]).strip()
    if not (swid.startswith("{") and swid.endswith("}")):
        raise EspnError(
            "The SWID cookie needs its curly braces, like {ABC-123-...}. "
            "Re-copy it from the browser.")
    try:
        os.chmod(SECRETS, 0o600)
    except OSError:
        pass
    return s


def connect(season: Optional[int] = None):
    """Return an authenticated espn_api League."""
    try:
        from espn_api.football import League
    except ImportError as exc:
        raise EspnError("espn-api not installed - run ./setup.sh (%s)" % exc)

    import datetime
    s = load_secrets()
    season = season or datetime.date.today().year

    last = None
    for yr in (season, season - 1):
        try:
            return League(league_id=int(s["league_id"]), year=yr,
                          espn_s2=s["espn_s2"], swid=s["swid"])
        except Exception as exc:
            last = exc
    msg = str(last)
    if "401" in msg or "Private" in msg or "not authorized" in msg.lower():
        raise EspnError(
            "ESPN rejected the cookies (private league / 401). They expire when "
            "you log out - re-copy espn_s2 and SWID per SETUP_ESPN.md step 2.")
    raise EspnError("Could not reach ESPN: %s" % msg)


def league_facts(lg) -> Dict:
    st = getattr(lg, "settings", None)
    slots = {}
    rec_pts = None
    if st is not None:
        # espn_api 0.46 exposes lineup slots as position_slot_counts.
        slots = dict(getattr(st, "position_slot_counts", {}) or {})
        # statId 53 is "Each reception" in ESPN's scoring settings.
        for item in (getattr(st, "scoring_format", None) or []):
            if isinstance(item, dict) and item.get("id") == 53:
                rec_pts = item.get("points")
                break
    return {
        "name": getattr(st, "name", None) or "ESPN league",
        "teams": len(getattr(lg, "teams", []) or []),
        "year": getattr(lg, "year", None),
        "roster_slots": slots,
        "scoring_type": getattr(st, "scoring_type", None),
        "reception_points": rec_pts,
        "team_names": [getattr(t, "team_name", "?") for t in (lg.teams or [])],
    }


def my_team_index(lg) -> Optional[int]:
    """1-based draft slot of the logged-in user's team, if ESPN exposes it."""
    for i, t in enumerate(lg.teams or [], start=1):
        for attr in ("owners", "owner"):
            val = getattr(t, attr, None)
            if val:
                # espn_api marks the requesting user's team when it can.
                if isinstance(val, list) and any(
                        isinstance(o, dict) and o.get("id") for o in val):
                    pass
    # ESPN does not reliably flag "my" team; the draft slot comes from config.
    return None


def draft_picks(lg) -> List[Dict]:
    """Every pick made so far as {overall, name, keeper} dicts.

    Reads ESPN's raw draft feed directly. espn_api's own _fetch_draft returns
    early unless 'drafted' is set - and that flag means the draft is COMPLETE,
    so during a live draft lg.draft would always look empty. A fresh list is
    built on every call; nothing is appended to lg.draft.

    Overall is derived from round and pick-in-round so it matches the war
    room's own numbering even when ESPN omits it. Picks whose playerId is not
    in ESPN's player map are KEPT with name "" - the caller places a
    placeholder so the board never shifts.

    No two returned picks ever share an overall: a duplicate
    (roundId, roundPickNumber) entry is dropped (first one wins), and an
    index-derived guess that collides with a round-derived overall slides to
    the next open slot instead of double-booking it.
    """
    data = lg.espn_request.get_league_draft()
    raw = (data.get("draftDetail") or {}).get("picks") or []
    teams = len(getattr(lg, "teams", []) or []) or 10
    pmap = getattr(lg, "player_map", {}) or {}
    rounds = []      # (overall, pick) with authoritative round info
    guesses = []     # (index-derived overall, pick) - ESPN omitted the round
    for i, p in enumerate(raw):
        rnd = int(p.get("roundId") or 0)
        rpick = int(p.get("roundPickNumber") or 0)
        if rnd and rpick:
            rounds.append(((rnd - 1) * teams + rpick, p))
        else:
            guesses.append((i + 1, p))
    used = set()
    resolved = []
    for overall, p in rounds:
        if overall in used:      # duplicate slot glitch - first entry wins
            continue
        used.add(overall)
        resolved.append((overall, p))
    for overall, p in guesses:   # guesses never steal a claimed overall
        while overall in used:
            overall += 1
        used.add(overall)
        resolved.append((overall, p))
    out = [{"overall": overall,
            "name": pmap.get(p.get("playerId"), "") or "",
            "keeper": bool(p.get("keeper"))}
           for overall, p in resolved]
    out.sort(key=lambda r: r["overall"])
    return out


def free_agents(lg, size: int = 60, position: Optional[str] = None):
    return lg.free_agents(size=size, position=position)
