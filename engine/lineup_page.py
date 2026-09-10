"""THE LINEUP BUILDER: the lineup as the object, one row per slot.

    python -m engine.lineup_page --league espn-1 --week 3
    ./lineup.sh espn-1 3            (wrapper - warms caches, opens the page)

Writes lineup-<league>-week<N>.html to the project root (atomic tmp+replace,
the discipline engine/board.py uses) and prints the absolute path as its
LAST stdout line so lineup.sh can open it.

WHAT IT IS. The host apps' lineup screens are a list of slots with a
number beside each name. This page keeps that shape - the reader already
thinks in slots - and puts the DECISION on the row: every starting slot in
the league's own configured order (LeagueConfig.roster_spots; W/R/T reads
FLEX, DEF reads D/ST) shows the starter, his flags, his game and kickoff,
his projection, the model's verdict chip with its percentage, and the
matchup meter. A CHALLENGER line opens beneath a slot ONLY when a bench
player genuinely contests it - engine/lineup's close-call verdicts decide
that, and the line carries the challenger's projection, a split bar of the
room's weight (engine/consensus rows for both men), his meter and the
one-line reason. K and D/ST rows carry the HOLD-vs-STREAM read from
engine/dk instead of a bench challenger: the best available on the wire,
his opponent, the delta and the claim cost. Below, the BENCH shows only the
players competing above; an expander reveals the rest. The footer strip
carries the projected starting total and the delta of every proposed swap,
and the "Set lineup on ESPN/Yahoo" verb deep-links to the host lineup page
through engine/home's HOST_URLS recipes.

PHONE-FIRST. The acceptance bar is 390px: no horizontal page scroll,
nothing spills a line. Names truncate with an ellipsis, team and opponent
codes never wrap, every row is at least 44px tall, and the slot label
collapses to a two-letter chip with its index. Desktop simply widens the
same rows - there is one layout, not two.

COMPOSITION, NOT REIMPLEMENTATION. Every number is computed by the module
that owns it; this file arranges them.

  the legal lineup, close calls, alerts .. engine/lineup      (build)
  the room's weight per player ........... engine/consensus   (build_consensus)
  the matchup grade ...................... engine/matchups    (matchup_for)
  hold-vs-stream for DST and K ........... engine/dk          (weekly_call)
  the host deep link ..................... engine/home        (host_link)
  the shell, chips, meters, faces ........ engine/ui

HONEST DEGRADATION. engine/dk may not exist yet: without it every K and
D/ST row says "streaming read unavailable" in place and falls back to the
ordinary bench challenger. A dead feed leaves a banner, never a guess: no
schedule means no bye and no kickoff, not a bye guessed from silence; no
consensus means the split bar states it is drawn from projection odds, not
the room. A partial roster (yahoo-main's rivals are unknown) still gets its
challengers - they are my own bench - but the streaming candidates are
marked unverified, because "best available" cannot be proven without the
other rosters.

READ-ONLY. This page writes the one HTML file it is asked to write and
nothing else: it never advances the %owned momentum baseline (it does not
read the wire at all), never writes the streaming log, never records
source-ledger votes. engine/dk is called with force=False and is itself a
read. tests/lineup_page_test.py hashes data/cache/espn-owned-snapshot.json
and data/streaming_log.jsonl across two renders to hold that line.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

try:
    from engine import ui
    from engine import weekly
    from engine import lineup as lineup_mod
    from engine import consensus as consensus_mod
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, norm_pos, repo_path)
except ImportError:  # run directly as `python engine/lineup_page.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import ui
    from engine import weekly
    from engine import lineup as lineup_mod
    from engine import consensus as consensus_mod
    from engine.models import (FLEX_ELIGIBLE, LeagueConfig, Player,
                               load_players, norm_pos, repo_path)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE_NAME = "lineup-%s-week%d.html"
BENCH_SLOTS = ("BN", "BE", "BENCH", "IR")

# The line the K/D/ST rows print when engine/dk cannot be read. Tests pin
# the phrase; keep it.
STREAM_UNAVAILABLE = "streaming read unavailable"

# Slot vocabulary: config spot -> (display label, two-letter chip)
_SLOT_DISPLAY = {"DEF": "D/ST", "K": "K", "QB": "QB", "RB": "RB",
                 "WR": "WR", "TE": "TE"}
_SLOT_SHORT = {"DEF": "DS", "K": "K", "QB": "QB", "RB": "RB", "WR": "WR",
               "TE": "TE", "FLEX": "FL"}
_DK_KEY = {"DEF": "DST", "K": "K"}     # lineup pos -> engine/dk call key

_SHORT_STATUS = {"questionable": "Q", "doubtful": "D", "out": "OUT",
                 "ir": "IR", "pup": "PUP", "sus": "SUSP", "suspended": "SUSP",
                 "cov": "COV", "dnr": "DNR", "holdout": "HOLDOUT"}


# --- small pure helpers -----------------------------------------------------

def fmt_pts(value) -> str:
    """A projection as one number, or an em dash for none filed. None and
    0.0 are different facts: 0.0 is a filed zero, None is silence."""
    if value is None:
        return "—"
    try:
        return "%.1f" % float(value)
    except (TypeError, ValueError):
        return "—"


def fmt_delta(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(v) < 0.05:
        v = 0.0                      # never print "-0.0"
    return "%+.1f" % v


def fmt_kick(iso) -> str:
    """'Sun 1:00pm' - one short token that never wraps."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    h = dt.hour % 12 or 12
    return "%s %d:%02d%s" % (dt.strftime("%a"), h, dt.minute,
                             "pm" if dt.hour >= 12 else "am")


def _cget(obj, key, default=None):
    """Read a field from a dict OR an object - engine/dk's Call may be
    either, and this page must not care."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def slot_labels(roster_spots: Sequence[str]) -> List[Dict]:
    """Starting slots in CONFIG order: [{spot, pos, kind, label, short}].

    Repeated labels are numbered (RB1, RB2, FLEX1, FLEX2); a label that
    appears once stays bare (QB, TE, K, D/ST). `pos` is the lineup module's
    slot key - the normalized position for a hard slot, the config token
    (W/R/T) for a flex - so rows from lineup.build can be matched back.
    """
    raw = []
    for spot in roster_spots:
        s = str(spot or "").strip().upper()
        if not s or s in BENCH_SLOTS:
            continue
        if s in FLEX_ELIGIBLE:
            raw.append({"spot": s, "pos": s, "kind": "flex", "base": "FLEX",
                        "short": _SLOT_SHORT["FLEX"]})
        else:
            p = norm_pos(s)
            raw.append({"spot": s, "pos": p, "kind": "hard",
                        "base": _SLOT_DISPLAY.get(p, p),
                        "short": _SLOT_SHORT.get(p, p[:2])})
    counts: Dict[str, int] = {}
    for r in raw:
        counts[r["base"]] = counts.get(r["base"], 0) + 1
    seen: Dict[str, int] = {}
    for r in raw:
        if counts[r["base"]] > 1:
            seen[r["base"]] = seen.get(r["base"], 0) + 1
            r["index"] = seen[r["base"]]
            r["label"] = "%s%d" % (r["base"], r["index"])
        else:
            r["index"] = 0
            r["label"] = r["base"]
    return raw


def order_rows(league: LeagueConfig,
               rows: Sequence[Tuple[str, Optional[Player]]]) -> List[Dict]:
    """lineup.build's (slot, player) rows re-sequenced into config order.

    best_lineup fills hard slots first and flex groups after; the host app
    lists slots as the league configured them, and so does this page.
    Each slot consumes the next unconsumed row with its key.
    """
    pending = [list(r) for r in rows]
    out = []
    for lab in slot_labels(league.roster_spots):
        player = None
        for i, (slot, p) in enumerate(pending):
            if slot == lab["pos"]:
                player = p
                del pending[i]
                break
        entry = dict(lab)
        entry["player"] = player
        out.append(entry)
    return out


def game_of(player: Optional[Player], schedule: Optional[Dict]) -> Dict:
    """{opp, kick, iso, bye, known} - never guesses when the schedule is
    down (known=False), and a team absent from the map is a bye."""
    if player is None or schedule is None or not player.team:
        return {"opp": "", "kick": "", "iso": "", "bye": False,
                "known": schedule is not None and bool(player and player.team)}
    game = schedule.get(player.team)
    if not game:
        return {"opp": "", "kick": "", "iso": "", "bye": True, "known": True}
    return {"opp": "%s %s" % ("vs" if game.get("home") else "@",
                              game.get("opponent", "")),
            "kick": fmt_kick(game.get("kickoff_iso", "")),
            "iso": game.get("kickoff_iso", ""), "bye": False, "known": True}


def flags_of(player: Optional[Player], weekly_pts, game: Dict,
             injuries: Optional[Dict], now: Optional[datetime] = None
             ) -> List[Dict]:
    """The status marks beside a name, in a fixed order: injury · bye ·
    projection silence/zero · locked. A mark that is not true emits
    nothing; an absent injury feed emits nothing rather than 'healthy'."""
    out: List[Dict] = []
    if player is None:
        return out
    status = ((injuries or {}).get(player.nkey) or "").strip()
    if status:
        low = status.lower()
        out.append({"kind": "injury", "label": _SHORT_STATUS.get(low, status.upper()[:6]),
                    "note": "injury status filed: %s" % status,
                    "level": "red" if low in lineup_mod.RED_STATUSES else "warn"})
    if game.get("bye"):
        out.append({"kind": "bye", "label": "BYE",
                    "note": "no game this week - replace before lock",
                    "level": "red"})
    if weekly_pts is None:
        out.append({"kind": "noproj", "label": "NO PROJ",
                    "note": "no weekly projection filed - verify he is active",
                    "level": "warn"})
    elif float(weekly_pts) == 0.0:
        out.append({"kind": "zero", "label": "0.0 FILED",
                    "note": "the feed projects zero - injured or not playing",
                    "level": "red"})
    iso = game.get("iso") or ""
    if iso and now is not None:
        try:
            kick = datetime.fromisoformat(iso)
            if kick.tzinfo is not None and now.tzinfo is not None \
                    and kick <= now:
                out.append({"kind": "locked", "label": "LOCKED",
                            "note": "his game has started - this is final",
                            "level": "info"})
        except ValueError:
            pass
    return out


def verdict_of(cons_row: Optional[Dict], contest: Optional[Dict],
               stream: Optional[Dict] = None) -> Dict:
    """The model's chip for a starter: {key, pct, title, basis}.

    Basis order: engine/dk's hold-vs-stream verdict for K/D/ST when it was
    read (HOLD = start him, STREAM = sit him for the wire, TOSS-UP = even);
    else the room's weighted verdict (engine/consensus) with the weight
    share behind the winning side; else, for a contested slot, the
    engine's own P(starter outscores the challenger); else a bare START on
    projection with no percentage claimed.
    """
    if stream and stream.get("verdict") in ("HOLD", "STREAM", "TOSS-UP"):
        v = stream["verdict"]
        key = {"HOLD": "start", "STREAM": "sit", "TOSS-UP": "even"}[v]
        # the pct is dk's own: P(held beats best) on a HOLD / TOSS-UP,
        # P(best beats held) on a STREAM - the odds behind the word shown.
        pct = stream.get("confidence") if v == "STREAM" else stream.get("held_pct")
        if pct is None and cons_row:
            pct = consensus_mod.display_pct(cons_row)
        return {"key": key, "pct": pct, "basis": "stream",
                "title": "engine/dk says %s - %s" % (
                    v, stream.get("reason") or "no reason given")}
    if cons_row:
        key = {"START": "start", "SIT": "sit", "FLEX": "flex",
               "EVEN": "even"}.get(str(cons_row.get("verdict")).upper())
        return {"key": key, "pct": consensus_mod.display_pct(cons_row),
                "basis": "room",
                "title": "your model: %s" % consensus_mod.format_voices(
                    cons_row, max_quote=60)}
    if contest:
        pct = int(contest.get("pct") or 0)
        key = "even" if pct <= lineup_mod.COIN_FLIP_PCT else "start"
        return {"key": key, "pct": pct, "basis": "odds",
                "title": "no room vote on file - P(starter outscores the "
                         "challenger) from projection error"}
    return {"key": "start", "pct": None, "basis": "projection",
            "title": "no room vote on file and no bench contest - starts "
                     "on projection"}


def room_split(cons_a: Optional[Dict], cons_b: Optional[Dict],
               engine_pct: Optional[int]) -> Dict:
    """{a, b, basis, label} - the weight behind the starter vs the
    challenger. From the room when both men have a consensus row (each
    row's start-ward share, normalized between the two); otherwise from
    the engine's odds, and the basis says which."""
    if cons_a and cons_b:
        pa = float(cons_a.get("pct") or 0)
        pb = float(cons_b.get("pct") or 0)
        tot = pa + pb
        a = 50.0 if tot <= 0 else 100.0 * pa / tot
        return {"a": int(round(a)), "b": int(round(100 - a)), "basis": "room",
                "label": "weight of the room: %d%% start-ward on the starter, "
                         "%d%% on the challenger" % (int(round(pa)),
                                                    int(round(pb)))}
    p = max(0, min(100, int(engine_pct if engine_pct is not None else 50)))
    return {"a": p, "b": 100 - p, "basis": "odds",
            "label": "no room vote for both men - projection odds: %d%% the "
                     "starter outscores the challenger" % p}


def stream_line(call, pos: str) -> Dict:
    """One engine/dk Call -> the facts the row prints.

    {verdict, held, held_score, best, best_team, best_opp, best_score,
    delta, cost, reason, candidates}. Missing fields stay None - the line
    prints what it has and claims nothing else.
    """
    def _name(x):
        if x is None:
            return ""
        if isinstance(x, str):
            return x
        for k in ("name", "player", "label", "key"):
            v = _cget(x, k)
            if v:
                return str(v)
        return str(x)

    def _field(x, keys):
        if x is None or isinstance(x, str):
            return None
        for k in keys:
            v = _cget(x, k)
            if v not in (None, ""):
                return v
        return None

    best = _cget(call, "best")
    verdict = str(_cget(call, "verdict") or "NO READ").upper()
    if verdict not in ("HOLD", "STREAM", "TOSS-UP", "NO READ"):
        verdict = "NO READ"
    cost = _field(call, ("cost", "claim_cost", "claim", "faab", "band",
                         "priority"))
    if cost is None:
        cost = _field(best, ("cost", "claim_cost", "claim", "faab", "band",
                             "priority"))
    cands = list(_cget(call, "candidates") or ())
    # dk's Call carries best_opp as a bare code and the venue side only on
    # the candidate view; join them so the line can say "vs CAR" / "@ CAR".
    best_key = _cget(call, "best_key")
    cand = next((c for c in cands if isinstance(c, dict)
                 and best_key and c.get("key") == best_key), None)
    opp = _field(best, ("opp", "opponent"))
    home = _field(best, ("home",))
    if opp is None:
        opp = _cget(call, "best_opp")
    if cand is not None:
        opp = cand.get("opp") or opp
        home = cand.get("home") if home is None else home
    opp_text = ""
    if opp:
        opp_text = ("%s %s" % ("vs" if home else "@", opp)
                    if home is not None else str(opp))
    held_pct = _num(_cget(call, "held_pct"))
    conf = _num(_cget(call, "confidence"))
    return {"pos": pos, "verdict": verdict,
            "held": _name(_cget(call, "held")),
            "held_score": _num(_cget(call, "held_score")),
            "best": _name(best),
            "best_team": _field(best, ("team",)) or (cand or {}).get("team"),
            "best_opp": opp_text, "best_score": _num(_cget(call, "best_score")),
            "delta": _num(_cget(call, "delta")),
            "cost": (str(cost) if cost is not None else ""),
            "cost_short": cost_token(cost),
            "held_pct": held_pct, "confidence": conf,
            "unverified": bool(_cget(call, "unverified")),
            "reason": str(_cget(call, "reason") or ""),
            "candidates": cands}


def cost_token(cost) -> str:
    """The claim cost as one short token a phone line can hold; the full
    sentence from engine/dk rides in the title. 'FAAB 1-3%' / 'priority ·
    burn' / 'priority · wait for FA' / the first clause otherwise."""
    text = " ".join(str(cost or "").split())
    if not text:
        return ""
    low = text.lower()
    if "faab band" in low:
        band = text[low.index("faab band") + len("faab band"):].strip()
        band = band.split(";")[0].split(" - ")[0].strip() or "?"
        return "FAAB %s" % band
    if "priority" in low:
        return ("priority · wait for FA" if "not worth" in low
                else "priority · burn")
    first = text.split(" - ")[0].split(";")[0].strip()
    return ui.trim(first, 28)


def streaming_calls(league: LeagueConfig, week: int,
                    roster_players: Sequence[Player],
                    players: Sequence[Player], matcher) -> Tuple[Optional[Dict], str]:
    """engine/dk's weekly_call, or (None, why). Import is deferred and
    guarded: the module is being built beside this one and may not exist;
    absence is a note on the row, never a dead page. force=False always -
    this page is a read."""
    try:
        from engine import dk as dk_mod   # noqa: PLC0415 - optional module
    except ImportError as exc:
        return None, ("%s — engine/dk.py not importable (%s); hold-vs-stream "
                      "not judged, bench challengers shown instead"
                      % (STREAM_UNAVAILABLE, str(exc).splitlines()[0][:80]))
    try:
        calls = dk_mod.weekly_call(league, week, list(roster_players),
                                   list(players), matcher, force=False)
    except Exception as exc:  # noqa: BLE001 - the row carries the error
        return None, ("%s (%s: %s)" % (STREAM_UNAVAILABLE, type(exc).__name__,
                                      str(exc).splitlines()[0][:120]
                                      if str(exc) else "no detail"))
    if not isinstance(calls, dict):
        return None, ("%s — engine/dk returned %s, not a {DST, K} mapping"
                      % (STREAM_UNAVAILABLE, type(calls).__name__))
    return calls, ""


def host_verb(league: LeagueConfig) -> Dict:
    """{label, href, note} - the 'Set lineup on ESPN/Yahoo' verb through
    engine/home's recipes; absent host -> no link and the quiet note."""
    snap = {"platform": str(getattr(league, "platform", "") or "").lower(),
            "host": getattr(league, "host", None), "id": league.id}
    try:
        from engine import home as home_mod   # noqa: PLC0415 - heavy import
        href = home_mod.host_link(snap, "team")
        plat = home_mod.PLATFORM_LABEL.get(snap["platform"])
        note = "" if href else home_mod.host_note(snap)
    except Exception as exc:  # noqa: BLE001 - a verb, never a broken page
        href, plat = "", None
        note = "no link — host recipes unreadable (%s: %s)" % (
            type(exc).__name__, str(exc).splitlines()[0][:80] if str(exc)
            else "no detail")
    label = "Set lineup on %s" % plat if (href and plat) else "Set lineup"
    return {"label": label, "href": href, "note": note}


def swap_deltas(model: Dict) -> List[Dict]:
    """Every proposed change and what it is worth, in projected points:
    'swap X in for Y' for each bench challenger (challenger minus starter),
    'claim X' for each streaming read that named a best available with a
    delta. Negative deltas are listed too - the reader sees WHY the
    starter holds, not only when he does not."""
    out = []
    for s in model.get("slots") or []:
        p = s.get("player")
        ch = s.get("challenger")
        st = s.get("stream")
        if st and st.get("best") and st.get("delta") is not None:
            out.append({"kind": "claim", "slot": s["label"],
                        "label": "claim %s" % st["best"],
                        "delta": round(float(st["delta"]), 1),
                        "cost": st.get("cost_short") or cost_token(st.get("cost")),
                        "cost_full": st.get("cost") or ""})
        elif ch and p is not None:
            a = float(p.proj_points or 0.0)
            b = float(ch["player"].proj_points or 0.0)
            out.append({"kind": "swap", "slot": s["label"],
                        "label": "swap %s in for %s" % (
                            ch["player"].surname(), p.surname()),
                        "delta": round(b - a, 1), "cost": ""})
    return out


# --- assembly (pure: every feed is injected) -------------------------------

def assemble(league: LeagueConfig, week: int, roster: Optional[Dict],
             proj: Dict[str, Dict], schedule: Optional[Dict] = None,
             lines: Optional[Dict] = None, injuries: Optional[Dict] = None,
             sigmas: Optional[Dict[str, float]] = None, matcher=None,
             cmap: Optional[Dict[str, Dict]] = None,
             matchup_of: Optional[Callable] = None,
             dk_calls: Optional[Dict] = None, dk_note: str = "",
             leagues: Sequence = (), notes: Sequence[str] = (),
             rivals_known: Optional[bool] = None,
             now: Optional[datetime] = None) -> Dict:
    """Everything render_page needs, as data. Tests drive this directly."""
    week = int(week)
    look = matchup_of or (lambda _p: None)
    cmap = cmap or {}
    names = list(roster["players"]) if roster else []
    b = lineup_mod.build(league, names, week, proj, schedule=schedule,
                         lines=lines, injuries=injuries, sigmas=sigmas,
                         matcher=matcher)
    verdict_by_starter = {}
    for v in b["verdicts"]:
        verdict_by_starter.setdefault(v.get("a_key"), v)
    by_key = dict((p.key, p) for _, p in b["rows"] if p is not None)
    for p in b["bench"]:
        by_key[p.key] = p

    def _m(p):
        try:
            return look(p)
        except Exception:  # noqa: BLE001 - a meter, never a dead row
            return None

    slots = []
    competitors: Dict[str, List[str]] = {}
    for entry in order_rows(league, b["rows"]):
        p = entry["player"]
        s = dict(entry)
        s["open"] = p is None
        s["weekly"] = (b["meta"].get(p.key) or {}).get("weekly") if p else None
        s["game"] = game_of(p, schedule)
        s["flags"] = flags_of(p, s["weekly"], s["game"], injuries, now=now)
        s["cons"] = cmap.get(p.key) if p else None
        s["matchup"] = _m(p) if p else None
        s["implied"] = ((lines or {}).get(p.team) or {}).get("implied_total") \
            if (p and lines) else None
        contest = verdict_by_starter.get(p.key) if p else None
        stream = None
        stream_note = ""
        if p is not None and entry["kind"] == "hard" and entry["pos"] in _DK_KEY:
            call = (dk_calls or {}).get(_DK_KEY[entry["pos"]])
            if call is not None:
                stream = stream_line(call, entry["pos"])
                if rivals_known is False:
                    stream["unverified"] = True    # dk says so too; belt and braces
            else:
                stream_note = dk_note or ("%s — no %s call returned"
                                          % (STREAM_UNAVAILABLE,
                                             _DK_KEY[entry["pos"]]))
        s["stream"] = stream
        s["stream_note"] = stream_note
        challenger = None
        if contest and stream is None:
            cp = by_key.get(contest.get("b_key"))
            if cp is not None:
                text = contest.get("text") or ""
                reason = text.rsplit(" - ", 1)[-1] if " - " in text else text
                challenger = {
                    "player": cp,
                    "weekly": (b["meta"].get(cp.key) or {}).get("weekly"),
                    "game": game_of(cp, schedule),
                    "flags": flags_of(cp, (b["meta"].get(cp.key) or {}).get("weekly"),
                                      game_of(cp, schedule), injuries, now=now),
                    "pct": int(contest.get("pct") or 0),
                    "reason": reason, "text": text,
                    "cons": cmap.get(cp.key),
                    "matchup": _m(cp),
                    "split": room_split(s["cons"], cmap.get(cp.key),
                                        contest.get("pct")),
                }
                competitors.setdefault(cp.key, []).append(entry["label"])
        s["challenger"] = challenger
        s["verdict"] = verdict_of(s["cons"], contest, stream) if p else None
        slots.append(s)

    bench = []
    for p in sorted(b["bench"], key=lambda x: -float(x.proj_points or 0.0)):
        wk = (b["meta"].get(p.key) or {}).get("weekly")
        g = game_of(p, schedule)
        bench.append({"player": p, "weekly": wk, "game": g,
                      "flags": flags_of(p, wk, g, injuries, now=now),
                      "cons": cmap.get(p.key), "matchup": _m(p),
                      "competes": competitors.get(p.key, [])})

    first = None
    kicks = [(s["game"]["iso"], s["player"]) for s in slots
             if s.get("player") is not None and s["game"].get("iso")]
    if kicks:
        kicks.sort(key=lambda t: t[0])
        first = {"name": kicks[0][1].name, "kick": fmt_kick(kicks[0][0])}

    model = {
        "league": league, "week": week, "roster": roster,
        "known": len(names), "size": (roster or {}).get("size") or 0,
        "slots": slots, "bench": bench, "competitors": competitors,
        "total": float(b["total"] or 0.0), "missing": list(b["missing"]),
        "unresolved": list(b["unresolved"]), "alerts": list(b["alerts"]),
        "verdicts": list(b["verdicts"]), "sigmas": b["sigmas"],
        "schedule_known": schedule is not None,
        "injuries_known": injuries is not None,
        "room_known": bool(cmap),
        "dk_note": dk_note, "dk_read": dk_calls is not None,
        "rivals_known": rivals_known,
        "first_kick": first, "host": host_verb(league),
        "leagues": list(leagues), "notes": list(notes),
    }
    model["swaps"] = swap_deltas(model)
    return model


# --- rendering ----------------------------------------------------------------

_esc = ui.esc


def _flag_html(flag: Dict) -> str:
    kind = flag.get("kind")
    if kind == "injury":
        return ('<span class="wr-badge wr-badge-injury lu-flag-%s" title="%s">%s'
                '<span class="wr-badge-l">%s</span></span>'
                % (_esc(flag.get("level") or "warn"), _esc(flag.get("note")),
                   ui.icon("injury", 20), _esc(flag.get("label"))))
    if kind == "bye":
        return ui.flag_badge("bye", note=flag.get("note"))
    if kind == "locked":
        return ui.flag_badge("locked", note=flag.get("note"))
    tone = "bad" if flag.get("level") == "red" else "lean"
    return ui.stat_pill("", flag.get("label") or "", tone=tone,
                        title=flag.get("note"))


def _flags_html(flags: Sequence[Dict]) -> str:
    if not flags:
        return ""
    return '<span class="lu-flags">%s</span>' % "".join(_flag_html(f) for f in flags)


def _game_html(p: Optional[Player], game: Dict, schedule_known: bool,
               flags: Sequence[Dict] = ()) -> str:
    bits = []
    if p is not None and p.team:
        bits.append('<span class="lu-team">%s</span>' % _esc(p.team))
    if game.get("bye"):
        bits.append('<span class="lu-opp">BYE</span>')
    elif game.get("opp"):
        bits.append('<span class="lu-opp">%s</span>' % _esc(game["opp"]))
    elif not schedule_known:
        bits.append('<span class="lu-opp lu-dim" title="schedule feed '
                    'unavailable - opponent and kickoff not read">no schedule'
                    '</span>')
    if game.get("kick"):
        bits.append('<span class="lu-kick">%s</span>' % _esc(game["kick"]))
    return ('<div class="lu-game">%s%s</div>'
            % ("".join(bits), _flags_html(flags)))


def _meter_html(m: Optional[Dict], size: str = "md") -> str:
    if not m:
        return ui.matchup_meter(None, label=True, size=size,
                                title="no matchup read for this row")
    return ui.matchup_meter(m.get("pa_grade"), label=True, size=size,
                            title=m.get("reason") or m.get("evidence")
                            or "matchup grade %s" % (m.get("pa_grade") or "unknown"))


def _slot_html(s: Dict) -> str:
    """The slot label: full word on desktop, two-letter chip on a phone."""
    idx = s.get("index") or 0
    return ('<div class="lu-slot" title="%s"><span class="lu-slot-f">%s</span>'
            '<span class="lu-slot-s" aria-hidden="true">%s%s</span></div>'
            % (_esc(s["label"]), _esc(s["label"]), _esc(s["short"]),
               ('<i>%d</i>' % idx) if idx else ""))


def _tag(label: str, tone: str, title: str = "") -> str:
    """A small local word-tag in the chip vocabulary (weight, not hue):
    tone 'fill' (gold), 'ghost', 'dash'. Built from ui's chip classes."""
    cls = {"fill": "wr-chip-start", "ghost": "wr-chip-sit",
           "dash": "wr-chip-lean"}.get(tone, "wr-chip-none")
    t = ' title="%s"' % _esc(title) if title else ""
    return ('<span class="wr-chip wr-chip-sm %s lu-tag"%s><span class="wr-chip-l">%s'
            '</span></span>' % (cls, t, _esc(label)))


def render_split(split: Dict) -> str:
    a, bb = int(split.get("a") or 0), int(split.get("b") or 0)
    return ('<span class="lu-split" role="img" aria-label="%s">'
            '<span class="lu-split-a" style="width:%d%%"></span>'
            '<span class="lu-split-b" style="width:%d%%"></span></span>'
            '<span class="lu-split-l wr-num" title="%s">%d·%d</span>'
            % (_esc(split.get("label")), a, bb, _esc(split.get("label")), a, bb))


def render_challenger(s: Dict) -> str:
    ch = s["challenger"]
    cp = ch["player"]
    return (
        '<div class="lu-vs" data-slot="%s">'
        '<span class="lu-vs-k">VS</span>'
        '<div class="lu-vs-who">%s<span class="lu-n">%s</span>'
        '<span class="lu-opp">%s</span>%s</div>'
        '<span class="lu-proj wr-num" title="his weekly projection">%s</span>'
        '<div class="lu-tail">%s%s</div>'
        '<p class="lu-why">%s</p>'
        '</div>'
        % (_esc(s["label"]), ui.pos_badge(cp.pos), _esc(cp.name),
           _esc("BYE" if ch["game"].get("bye") else ch["game"].get("opp") or ""),
           _flags_html(ch["flags"]),
           fmt_pts(ch["weekly"]),
           render_split(ch["split"]), _meter_html(ch["matchup"], "sm"),
           _esc(ch["reason"]))
    )


def render_stream(s: Dict) -> str:
    """The HOLD-vs-STREAM line for a K or D/ST row."""
    st = s["stream"]
    v = st["verdict"]
    tone = {"HOLD": "fill", "STREAM": "fill", "TOSS-UP": "dash"}.get(v, "ghost")
    tag = _tag(v, tone, title=st.get("reason") or "")
    if v == "NO READ" or not st.get("best"):
        why = st.get("reason") or "no wire candidate could be read"
        return ('<div class="lu-vs lu-stream" data-slot="%s">'
                '<span class="lu-vs-k">%s</span>'
                '<div class="lu-vs-who"><span class="lu-n lu-dim">no read on the wire</span></div>'
                '<span class="lu-proj wr-num">—</span>'
                '<div class="lu-tail">%s</div><p class="lu-why">%s</p></div>'
                % (_esc(s["label"]), ui.icon("waiver_add", 20, title="the wire"),
                   tag, _esc(why)))
    best = st["best"]
    delta = st.get("delta")
    bits = []
    if st.get("best_score") is not None:
        bits.append('<span class="wr-num">%s</span>' % fmt_pts(st["best_score"]))
    if st.get("held_score") is not None:
        bits.append('<span class="lu-dim">vs held <span class="wr-num">%s</span></span>'
                    % fmt_pts(st["held_score"]))
    cost = st.get("cost") or ""
    unverified = ""
    if st.get("unverified"):
        unverified = ('<span class="lu-unv" title="rival rosters are unknown, so '
                      '\'best available\' cannot be proven free - verify on the '
                      'host before claiming">unverified</span>')
    why = st.get("reason") or ""
    scores = " · ".join(bits)
    if scores:
        why = ("%s · %s" % (_esc(why), scores)) if why else scores
    else:
        why = _esc(why)
    return (
        '<div class="lu-vs lu-stream" data-slot="%s">'
        '<span class="lu-vs-k" title="best available on the wire">%s</span>'
        '<div class="lu-vs-who">%s<span class="lu-n">%s</span>'
        '<span class="lu-opp">%s</span>%s</div>'
        '<span class="lu-proj wr-num" title="his streaming score this week">%s</span>'
        '<div class="lu-tail">%s<span class="lu-delta wr-num" title="best available '
        'minus the held score">%s</span>%s</div>'
        '<p class="lu-why">%s</p>'
        '</div>'
        % (_esc(s["label"]), ui.icon("waiver_add", 20, title="the wire"),
           ui.pos_badge(s["pos"]), _esc(best),
           _esc(st.get("best_opp") or ""), unverified,
           fmt_pts(st.get("best_score")) if st.get("best_score") is not None else "—",
           tag, fmt_delta(delta) if delta is not None else "—",
           ('<span class="lu-cost" title="%s">claim: %s</span>'
            % (_esc(cost), _esc(st.get("cost_short") or cost_token(cost))))
           if cost else "",
           why)
    )


def render_slot(s: Dict, schedule_known: bool) -> str:
    p = s.get("player")
    if p is None:
        body = ('<div class="lu-who"><div class="lu-name"><span class="lu-n lu-dim">'
                'open — no known player fits</span></div>'
                '<div class="lu-game lu-dim">an empty seat here is missing roster '
                'data, not a benched player</div></div>'
                '<span class="lu-proj wr-num">—</span>'
                '<div class="lu-tail">%s</div>'
                % ui.verdict_chip(None, title="no player to judge"))
        return ('<div class="lu-group lu-open"><article class="lu-row" data-slot="%s">'
                '%s%s</article></div>' % (_esc(s["label"]), _slot_html(s), body))
    vd = s["verdict"] or {}
    chip = ui.verdict_chip(vd.get("key"), vd.get("pct"), title=vd.get("title"))
    hot = bool((s.get("cons") or {}).get("top_disagrees")) or vd.get("key") == "sit" \
        or (s.get("stream") or {}).get("verdict") == "STREAM"
    tone = " lu-row-hot" if hot else ""
    if s.get("challenger") or s.get("stream"):
        tone += " lu-row-contested"
    imp = s.get("implied")
    proj_title = "weekly projection"
    if imp is not None:
        proj_title += " · team implied total %.1f" % float(imp)
    row = (
        '<article class="lu-row%s" data-slot="%s">'
        '%s'
        '<div class="lu-who"><div class="lu-name">%s<span class="lu-n">%s</span></div>%s</div>'
        '<span class="lu-proj wr-num" title="%s">%s</span>'
        '<div class="lu-tail">%s%s</div>'
        '</article>'
        % (tone, _esc(s["label"]), _slot_html(s), ui.pos_badge(p.pos), _esc(p.name),
           _game_html(p, s["game"], schedule_known, s["flags"]),
           _esc(proj_title), fmt_pts(s["weekly"]),
           chip, _meter_html(s.get("matchup")))
    )
    extra = ""
    if s.get("stream"):
        extra = render_stream(s)
    elif s.get("challenger"):
        extra = render_challenger(s)
    if s.get("stream_note"):
        extra += ('<p class="lu-stream-note" data-slot="%s">%s%s</p>'
                  % (_esc(s["label"]), ui.icon("news", 20), _esc(s["stream_note"])))
    return '<div class="lu-group">%s%s</div>' % (row, extra)


def render_bench_row(bp: Dict, schedule_known: bool) -> str:
    p = bp["player"]
    competes = bp.get("competes") or []
    note = ""
    if competes:
        note = ('<span class="lu-competes">contests %s</span>'
                % _esc(", ".join(competes)))
    return (
        '<article class="lu-row lu-bench%s" data-bench="%s">'
        '<div class="lu-slot"><span class="lu-slot-f">BENCH</span>'
        '<span class="lu-slot-s" aria-hidden="true">BN</span></div>'
        '<div class="lu-who"><div class="lu-name">%s<span class="lu-n">%s</span>%s</div>%s</div>'
        '<span class="lu-proj wr-num">%s</span>'
        '<div class="lu-tail">%s</div>'
        '</article>'
        % (" lu-competitor" if competes else "", _esc(p.key), ui.pos_badge(p.pos),
           _esc(p.name), note, _game_html(p, bp["game"], schedule_known, bp["flags"]),
           fmt_pts(bp["weekly"]), _meter_html(bp.get("matchup"), "sm"))
    )


def render_bench(model: Dict) -> str:
    bench = model.get("bench") or []
    comp = [b for b in bench if b.get("competes")]
    rest = [b for b in bench if not b.get("competes")]
    sk = model["schedule_known"]
    head = ui.section_header("Bench", "%d competing · %d resting"
                             % (len(comp), len(rest)))
    if comp:
        top = "".join(render_bench_row(b, sk) for b in comp)
    else:
        top = ('<p class="wr-note lu-bench-none">no bench player contests a '
               'starting slot this week - every call is decided by a clear margin.</p>')
    more = ""
    if rest:
        more = ui.popover(
            '<span class="lu-more">the rest of the bench <span class="wr-sec-n">'
            '(%d)</span></span>' % len(rest),
            '<div class="lu-rows">%s</div>'
            % "".join(render_bench_row(b, sk) for b in rest), cls="lu-rest")
    elif not bench:
        more = '<p class="wr-note">no bench players are known.</p>'
    return ('<section class="wr-card lu-card" id="bench">%s<div class="lu-rows">%s</div>%s'
            '</section>' % (head, top, more))


def render_footer(model: Dict) -> str:
    swaps = model.get("swaps") or []
    items = []
    for sw in swaps:
        cost = (' <span class="lu-cost" title="%s">%s</span>'
                % (_esc(sw.get("cost_full") or sw["cost"]), _esc(sw["cost"]))) \
            if sw.get("cost") else ""
        items.append('<li class="lu-swap"><span class="lu-swap-l">%s</span>'
                     '<span class="lu-swap-d wr-num">%s</span>%s</li>'
                     % (_esc(sw["label"]), fmt_delta(sw["delta"]), cost))
    host = model["host"]
    if host.get("href"):
        verb = ('<a class="lu-verb" href="%s" target="_blank" rel="noopener noreferrer">%s%s</a>'
                % (_esc(host["href"]), ui.icon("trade", 20), _esc(host["label"])))
    else:
        verb = ('<span class="lu-verb lu-verb-none" title="%s">%s</span>'
                '<span class="lu-host-note">%s</span>'
                % (_esc(host.get("note")), _esc(host["label"]), _esc(host.get("note"))))
    open_n = len(model.get("missing") or [])
    total_note = ("projected starting total, %d slot%s open"
                  % (open_n, "" if open_n == 1 else "s")) if open_n else \
        "projected starting total"
    return (
        '<footer class="wr-card lu-foot" id="strip">'
        '<div class="lu-total"><span class="wr-kicker">%s</span>'
        '<span class="lu-total-n wr-num">%.1f</span></div>'
        '<div class="lu-swaps"><span class="wr-kicker">proposed changes</span>%s</div>'
        '<div class="lu-act">%s</div>'
        '<p class="lu-ro">read-only: this page never advances the %%owned momentum '
        'baseline, never writes the streaming log and never records source-ledger '
        'votes. Regenerate with <code>./lineup.sh %s %d</code>.</p>'
        '</footer>'
        % (_esc(total_note), model["total"],
           ('<ul class="lu-swap-list">%s</ul>' % "".join(items)) if items
           else '<p class="wr-note">no swap is proposed - the lineup stands as built.</p>',
           verb, _esc(model["league"].id), int(model["week"]))
    )


def _banners(model: Dict) -> str:
    out = []
    lg = model["league"]
    if model.get("roster") is None:
        out.append(ui.banner("NO ROSTER FILE - data/rosters/%s.yaml is missing or "
                             "has no players; every slot below is open."
                             % lg.id, tone="bad"))
    elif model["size"] and model["known"] < model["size"]:
        out.append(ui.banner("PARTIAL ROSTER: %d of %d players known - the lineup "
                             "uses KNOWN players only; an open slot means no known "
                             "player fits, not that the seat is empty."
                             % (model["known"], model["size"])))
    if model.get("unresolved"):
        out.append(ui.banner("UNRESOLVED: %s - no projection source matched these "
                             "names; fix the spelling in the roster file."
                             % ", ".join(model["unresolved"])))
    if not model["schedule_known"]:
        out.append(ui.banner("schedule feed unavailable - opponents, kickoffs and "
                             "byes were not read, not guessed.", tone="info"))
    if not model["injuries_known"]:
        out.append(ui.banner("injury feed unavailable - statuses not checked, not "
                             "assumed healthy.", tone="info"))
    if not model["room_known"]:
        out.append(ui.banner("the room could not be weighed (engine/consensus "
                             "returned no rows) - verdict chips and split bars are "
                             "drawn from projection odds and say so.", tone="info"))
    if model.get("rivals_known") is False:
        out.append(ui.banner("rival rosters unknown for this league - bench "
                             "challengers are complete (they are your own bench) "
                             "but streaming candidates are UNVERIFIED: a 'best "
                             "available' may already be rostered. Paste the league "
                             "rosters in Model Settings to verify.", tone="info"))
    for n in model.get("notes") or []:
        out.append(ui.banner(n, tone="info"))
    return "".join(out)


_CSS = """
  .lu-head { margin: 0 0 14px; }
  .lu-lede { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center;
             color: var(--wr-muted); font-size: 13px; margin: 0 0 6px; }
  .lu-lede b { color: var(--wr-text); }
  .lu-verb { display: inline-flex; align-items: center; gap: 7px;
             background: var(--wr-nav); color: var(--wr-nav-text);
             border-radius: 999px; padding: 8px 16px; min-height: 36px;
             font-weight: 700; font-size: 12.5px; letter-spacing: 0.02em;
             text-decoration: none; box-shadow: inset 0 -3px 0 var(--wr-rule);
             white-space: nowrap; }
  .lu-verb-none { background: transparent; color: var(--wr-dim);
                  border: 1px dashed var(--wr-hairline-2); box-shadow: none; }
  .lu-host-note { color: var(--wr-dim); font-size: 11.5px; margin-left: 8px; }
  .lu-card { padding: 12px 14px 8px; }
  .lu-rows { display: flex; flex-direction: column; }
  .lu-group { border-bottom: 1px solid var(--wr-hairline); }
  .lu-group:last-child { border-bottom: none; }
  .lu-row {
    display: grid; align-items: center; gap: 2px 12px;
    grid-template-columns: 68px minmax(0, 1fr) 58px auto;
    grid-template-areas: "slot who proj tail";
    min-height: 52px; padding: 9px 6px; border-radius: 8px;
  }
  .lu-row-hot { background: var(--wr-wash-hot);
                box-shadow: inset 3px 0 0 var(--wr-rule); }
  .lu-slot { grid-area: slot; align-self: center; }
  .lu-slot-f { display: inline-block; font-size: 11px; letter-spacing: 0.14em;
               font-weight: 700; color: var(--wr-gold); text-transform: uppercase; }
  .lu-slot-s { display: none; }
  .lu-who { grid-area: who; min-width: 0; }
  .lu-name { display: flex; align-items: center; gap: 7px; min-width: 0; }
  .lu-n { font-weight: 700; font-size: 14.5px; min-width: 0; flex: 0 1 auto;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lu-dim { color: var(--wr-dim); font-weight: 500; }
  .lu-game { display: flex; align-items: center; gap: 8px; min-width: 0;
             color: var(--wr-muted); font-size: 12px; white-space: nowrap;
             overflow: hidden; }
  .lu-team { font-weight: 700; letter-spacing: 0.04em; flex: none; }
  .lu-opp, .lu-kick { white-space: nowrap; flex: none; }
  .lu-flags { display: inline-flex; align-items: center; gap: 4px; flex: none; }
  .lu-flag-red { box-shadow: inset 3px 0 0 var(--wr-text); }
  .lu-competes { color: var(--wr-gold); font-size: 11px; font-weight: 700;
                 letter-spacing: 0.06em; text-transform: uppercase;
                 white-space: nowrap; flex: none; }
  .lu-proj { grid-area: proj; text-align: right; font-size: 17px;
             font-weight: 700; white-space: nowrap; }
  .lu-tail { grid-area: tail; display: flex; align-items: center; gap: 10px;
             justify-content: flex-end; min-width: 0; flex-wrap: wrap; }
  /* challenger + streaming lines */
  .lu-vs {
    display: grid; align-items: center; gap: 2px 12px;
    grid-template-columns: 68px minmax(0, 1fr) 58px auto;
    grid-template-areas: "k who proj tail" "k why why why";
    padding: 0 6px 10px 6px; min-height: 44px;
  }
  .lu-vs-k { grid-area: k; font-size: 11px; letter-spacing: 0.14em;
             font-weight: 700; color: var(--wr-dim); text-align: right;
             padding-right: 4px; display: inline-flex; justify-content: flex-end; }
  .lu-vs-who { grid-area: who; display: flex; align-items: center; gap: 7px;
               min-width: 0; }
  .lu-vs .lu-proj { font-size: 14px; color: var(--wr-muted); }
  .lu-vs .lu-n { font-size: 13.5px; }
  .lu-vs .lu-opp { color: var(--wr-muted); font-size: 12px; }
  .lu-why { grid-area: why; margin: 0; color: var(--wr-dim); font-size: 12px;
            min-width: 0; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; }
  .lu-split { display: inline-flex; width: 84px; height: 8px; border-radius: 4px;
              overflow: hidden; background: var(--wr-raised);
              border: 1px solid var(--wr-hairline-2); flex: none; }
  .lu-split-a { background: var(--wr-rule); height: 100%; }
  .lu-split-b { background: var(--wr-meter-mid); height: 100%; opacity: 0.55; }
  .lu-split-l { font-size: 11px; color: var(--wr-muted); font-weight: 700;
                letter-spacing: 0.04em; }
  .lu-delta { font-size: 14px; font-weight: 700; }
  .lu-cost { color: var(--wr-gold); font-size: 11px; font-weight: 700;
             letter-spacing: 0.06em; text-transform: uppercase; white-space: nowrap; }
  .lu-unv { color: var(--wr-gold); font-size: 11px; font-weight: 700;
            letter-spacing: 0.1em; text-transform: uppercase;
            border: 1px dashed var(--wr-gold); border-radius: 4px;
            padding: 0 4px; white-space: nowrap; flex: none; }
  .lu-tag { flex: none; }
  .lu-stream-note { margin: 0; padding: 0 6px 10px 6px; color: var(--wr-dim);
                    font-size: 12px; display: flex; gap: 6px; align-items: flex-start; }
  .lu-stream-note .wr-icon { flex: none; margin-top: 1px; }
  /* bench */
  .lu-bench .lu-slot-f { color: var(--wr-dim); }
  .lu-competitor .lu-slot-f { color: var(--wr-gold); }
  .lu-rest > .wr-pop-s { padding: 10px 6px; font-weight: 700; }
  .lu-rest .wr-pop-d { border-left: none; margin-left: 0; padding-left: 0; }
  /* footer strip */
  .lu-foot { display: grid; gap: 12px 24px; align-items: start;
             grid-template-columns: auto minmax(0, 1fr) auto; margin-top: 14px; }
  .lu-total { display: flex; flex-direction: column; }
  .lu-total-n { font-size: 34px; font-weight: 700; line-height: 1; }
  .lu-swaps .wr-kicker { display: block; }
  .lu-swap-list { list-style: none; margin: 0; padding: 0; display: flex;
                  flex-direction: column; gap: 4px; }
  .lu-swap { display: flex; align-items: baseline; gap: 10px; font-size: 13px;
             min-width: 0; }
  .lu-swap-l { min-width: 0; overflow: hidden; text-overflow: ellipsis;
               white-space: nowrap; }
  .lu-swap-d { font-weight: 700; flex: none; }
  .lu-act { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
  .lu-ro { grid-column: 1 / -1; margin: 0; color: var(--wr-dim); font-size: 11.5px; }
  .lu-ro code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .lu-legend { margin-top: 14px; }

  /* PHONE-FIRST: one layout, the same rows, narrower. The slot word
     becomes a two-letter chip; the verdict and the meter drop to a second
     line under the name; nothing is allowed to wrap or spill. */
  @media (max-width: 700px) {
    .wr-page { padding: 14px 10px 48px; }
    .lu-card { padding: 8px 8px 6px; }
    .lu-row, .lu-vs {
      grid-template-columns: 36px minmax(0, 1fr) auto;
      gap: 3px 8px; padding: 8px 4px;
    }
    .lu-row { grid-template-areas: "slot who proj" "slot tail tail"; }
    .lu-vs { grid-template-areas: "k who proj" "k tail tail" "k why why";
             padding-bottom: 10px; }
    .lu-slot-f { display: none; }
    .lu-slot-s {
      display: inline-flex; align-items: center; justify-content: center;
      position: relative; width: 32px; height: 32px; border-radius: 7px;
      background: var(--wr-raised); border: 1px solid var(--wr-hairline-2);
      color: var(--wr-text); font-size: 11px; font-weight: 700;
      letter-spacing: 0.02em; font-style: normal;
    }
    .lu-slot-s i { font-style: normal; font-size: 11px; line-height: 1;
                   color: var(--wr-gold); margin-left: 1px; }
    .lu-bench .lu-slot-s { color: var(--wr-dim); }
    .lu-tail { justify-content: flex-start; gap: 8px; }
    .lu-proj { font-size: 16px; }
    .lu-vs-k { justify-content: center; padding-right: 0; }
    .lu-why { white-space: normal; }
    .lu-foot { grid-template-columns: minmax(0, 1fr); }
    .lu-act { align-items: flex-start; }
    .lu-verb { width: 100%; justify-content: center; box-sizing: border-box; }
    .lu-lede { font-size: 12.5px; }
    .lu-competes { display: none; }
  }
"""


def render_page(model: Dict) -> str:
    lg = model["league"]
    week = int(model["week"])
    slots = model["slots"]
    contested = sum(1 for s in slots if s.get("challenger") or
                    ((s.get("stream") or {}).get("verdict") in ("STREAM", "TOSS-UP")))
    lede = ['<b>Week %d</b>' % week,
            '%d starting slot%s' % (len(slots), "" if len(slots) == 1 else "s"),
            '%d contested' % contested]
    if model.get("first_kick"):
        lede.append('first kickoff %s (%s) — decide before then'
                    % (_esc(model["first_kick"]["kick"]),
                       _esc(model["first_kick"]["name"])))
    host = model["host"]
    if host.get("href"):
        verb = ('<a class="lu-verb" href="%s" target="_blank" rel="noopener noreferrer">%s%s</a>'
                % (_esc(host["href"]), ui.icon("trade", 20), _esc(host["label"])))
    else:
        verb = ('<span class="lu-host-note">%s</span>' % _esc(host.get("note")))
    starters = "".join(render_slot(s, model["schedule_known"]) for s in slots)
    legend = ui.legend((
        ("start", "START - the model backs him in this slot"),
        ("sit", "SIT - the model would bench him"),
        ("toss_up", "TOSS-UP - either call is defensible"),
        ("injury", "an injury status is filed"),
        ("bye", "no game this week"),
        ("waiver_add", "best available on the wire (the streaming read)"),
        ("locked", "his game has started - this is final"),
    ))
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Lineup · %s · week %d</title>\n%s\n<style>%s</style>\n</head>\n'
        '<body>\n%s\n<main class="wr-page lu-page">\n'
        '<header class="lu-head"><p class="wr-kicker">Lineup Builder</p>'
        '<h1 class="wr-display wr-h1">%s</h1>'
        '<p class="lu-lede">%s</p><div class="lu-lede">%s</div></header>\n'
        '%s\n'
        '<section class="wr-card lu-card" id="starters">%s'
        '<div class="lu-rows">%s</div></section>\n'
        '%s\n%s\n<div class="lu-legend">%s</div>\n</main>\n</body>\n</html>\n'
        % (_esc(lg.name), week, ui.style_tag(), _CSS,
           ui.shell("lineup", lg.id, week, model.get("leagues") or (),
                    subtitle="Lineup Builder · week %d" % week),
           _esc(lg.name), " · ".join(lede), verb,
           _banners(model),
           ui.section_header("Starters", "%d slots in your league's order"
                             % len(slots)),
           starters, render_bench(model), render_footer(model), legend)
    )


# --- live gathering ------------------------------------------------------------

def build_page(league_id: str, week: int, force: bool = False,
               roster_dir: Optional[str] = None,
               calls_dir: Optional[str] = None,
               registry_path: Optional[str] = None) -> str:
    """The whole page as a string. Every feed degrades on its own."""
    league_path = os.path.join(HERE, "leagues", "%s.yaml" % league_id)
    if not os.path.exists(league_path):
        raise SystemExit("no league yaml: %s" % repo_path(league_path))
    league = LeagueConfig.load(league_path)
    week = weekly._check_week(week)
    scoring = league.scoring_label()
    notes: List[str] = []

    players: List[Player] = []
    matcher = None
    csv_path = os.path.join(HERE, league.rankings_csv)
    if os.path.exists(csv_path):
        try:
            from engine.ingest import Matcher   # noqa: PLC0415
            players = load_players(csv_path)
            matcher = Matcher(players)
        except Exception as exc:  # noqa: BLE001
            notes.append("rankings pool unreadable (%s) - names resolve "
                         "through the projection feed only" % exc)
    else:
        notes.append("no rankings csv at %s - names resolve through the "
                     "projection feed only" % league.rankings_csv)

    roster = lineup_mod.load_roster(league_id, dirpath=roster_dir)

    try:
        proj = weekly.fetch_weekly_projections(week, scoring=scoring,
                                               force=force, quiet=True)
    except Exception as exc:  # noqa: BLE001 - stated, and the page still stands
        proj = {}
        notes.append("weekly projections unavailable (%s) - no lineup can be "
                     "built; every slot below is open until the feed is back"
                     % exc)
    try:
        schedule = weekly.fetch_schedule(week, force=force)
    except Exception:  # noqa: BLE001
        schedule = None
    try:
        lines = weekly.fetch_game_lines(week, force=force) or None
    except Exception:  # noqa: BLE001
        lines = None
    injuries = None
    try:
        from engine.projections import fetch_injury_status   # noqa: PLC0415
        injuries = fetch_injury_status(quiet=True)
    except Exception:  # noqa: BLE001
        injuries = None
    try:
        sigmas = lineup_mod.position_sigma()
    except Exception:  # noqa: BLE001
        sigmas = dict(lineup_mod.DEFAULT_SIGMA)

    cmap: Dict[str, Dict] = {}
    try:
        cons = consensus_mod.build_consensus(league_id, week, roster_dir=roster_dir,
                                             calls_dir=calls_dir,
                                             registry_path=registry_path,
                                             force=force)
        cmap = consensus_mod.consensus_map(cons)
        for n in cons.get("notes") or []:
            notes.append(n)
    except Exception as exc:  # noqa: BLE001 - the banner says so
        notes.append("consensus unavailable (%s: %s)"
                     % (type(exc).__name__, str(exc).splitlines()[0][:120]
                        if str(exc) else "no detail"))

    # matchup grades: one PA table, pure lookup per player, never a write
    # (matchups.register() is not called - it rewrites data/sources.yaml).
    mstate = {"table": None, "err": ""}
    try:
        from engine import matchups as matchups_mod   # noqa: PLC0415
        mstate["table"] = matchups_mod.pa_table(league, force=force)
    except Exception as exc:  # noqa: BLE001
        mstate["err"] = "%s: %s" % (type(exc).__name__,
                                    str(exc).splitlines()[0][:120] if str(exc)
                                    else "no detail")
        notes.append("matchup grades unavailable (%s) - meters are hollow, "
                     "not neutral" % mstate["err"])

    def _matchup_of(player):
        if mstate["table"] is None or schedule is None:
            return None
        try:
            return matchups_mod.matchup_for(player, week, league,
                                            table=mstate["table"],
                                            schedule=schedule)
        except Exception:  # noqa: BLE001
            return None

    # who is on my roster, for dk and the rivals read
    names = list(roster["players"]) if roster else []
    roster_players: List[Player] = []
    if names and proj:
        rp, _, _ = lineup_mod.resolve_roster(names, proj, matcher)
        roster_players = rp

    rivals_known: Optional[bool] = None
    try:
        from engine import trades as trades_mod   # noqa: PLC0415
        my_keys = set(p.key for p in roster_players)
        rival = trades_mod.load_rival_view(league, matcher, players, my_keys=my_keys)
        rivals_known = bool(rival.available)
    except Exception:  # noqa: BLE001 - unknown stays unknown
        rivals_known = None

    dk_calls, dk_note = streaming_calls(league, week, roster_players, players,
                                        matcher)

    try:
        from engine.sources_page import league_choices   # noqa: PLC0415
        leagues = league_choices()
    except Exception:  # noqa: BLE001
        leagues = [(league.id, league.name)]

    model = assemble(league, week, roster, proj, schedule=schedule, lines=lines,
                     injuries=injuries, sigmas=sigmas, matcher=matcher, cmap=cmap,
                     matchup_of=_matchup_of, dk_calls=dk_calls, dk_note=dk_note,
                     leagues=leagues, notes=notes, rivals_known=rivals_known,
                     now=datetime.now(timezone.utc))
    return render_page(model)


def default_path(league_id: str, week: int) -> str:
    return os.path.join(HERE, PAGE_NAME % (league_id, int(week)))


def write_lineup(league_id: str, week: int, force: bool = False,
                 out_path: Optional[str] = None,
                 roster_dir: Optional[str] = None,
                 calls_dir: Optional[str] = None,
                 registry_path: Optional[str] = None) -> str:
    """Build and atomically write the page; returns the path written."""
    html = build_page(league_id, week, force=force, roster_dir=roster_dir,
                      calls_dir=calls_dir, registry_path=registry_path)
    out = out_path or default_path(league_id, week)
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(html)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, out)
    return out


# --- CLI ------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.lineup_page",
        description="THE LINEUP BUILDER: one row per starting slot with the "
                    "model's verdict, the matchup meter, the bench challenger "
                    "or the hold-vs-stream read, and the swap deltas - one "
                    "self-contained HTML page. Prints the output path as its "
                    "last line.")
    ap.add_argument("--league", default="espn-1")
    ap.add_argument("--week", type=int, default=None,
                    help="NFL week (default: current week from the schedule)")
    ap.add_argument("--out", default=None,
                    help="output path (default: lineup-<league>-week<N>.html "
                         "in the project root)")
    ap.add_argument("--force", action="store_true",
                    help="refetch feeds even when caches are fresh")
    args = ap.parse_args(argv)

    week = args.week
    if week is None:
        from engine.digest import current_week   # noqa: PLC0415
        try:
            week = current_week()
        except RuntimeError as exc:
            print("cannot derive the current week (schedule feed down: %s) - "
                  "pass --week explicitly" % exc)
            return 1
        if week is None:
            print("no remaining %d regular-season week found in the schedule "
                  "- pass --week explicitly" % weekly.SEASON)
            return 1
        print("week %d (current, from the nflverse schedule)" % week)
    try:
        week = weekly._check_week(week)
    except ValueError as exc:
        print(exc)
        return 1
    try:
        path = write_lineup(args.league, week, force=args.force,
                            out_path=args.out)
    except KeyboardInterrupt:
        raise
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, str):
            print(code.splitlines()[0])
            return 1
        return int(code or 0)
    except BaseException as exc:  # noqa: BLE001 - one diagnosis line, no stack
        print("cannot render the lineup page: %s: %s - check leagues/%s.yaml, "
              "data/rosters/%s.yaml and the feeds, then rerun ./lineup.sh %s %d"
              % (type(exc).__name__, str(exc).splitlines()[0][:160] if str(exc)
                 else "no detail", args.league, args.league, args.league, week))
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
