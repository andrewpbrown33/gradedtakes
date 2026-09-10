"""Crash-proof persistence: autosave after every mutation, plus an append-only log.

Drafts crash and browsers die. Two independent artifacts are written so a
session can always be rebuilt: a full JSON snapshot (atomic replace) and an
append-only JSONL event log.
"""

import glob
import json
import os
import sys
import time
from typing import List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(HERE, "saves")


def _stamp() -> str:
    return time.strftime("%Y%m%d")


def save_path(league_id: str) -> str:
    return os.path.join(SAVE_DIR, "%s-%s.json" % (league_id, _stamp()))


def log_path(league_id: str) -> str:
    return os.path.join(SAVE_DIR, "%s-%s.picks.jsonl" % (league_id, _stamp()))


def snapshot(state) -> dict:
    return {
        "league_id": state.league.id,
        "league_path": state.league.path,
        "teams": state.teams,
        "rounds": state.league.rounds,
        "my_slot": state.my_slot,
        "rankings_csv": state.league.rankings_csv,
        "active_branch": state.active_branch,
        "branch_log": state.branch_log,
        "fired_triggers": state.fired_triggers,
        "picks": [p.to_dict() for p in
                  sorted(state.picks.values(), key=lambda x: x.overall)],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def save(state) -> str:
    """Atomically write the snapshot so a crash mid-write cannot corrupt it."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    path = save_path(state.league.id)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(snapshot(state), fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def log_event(league_id: str, event: dict) -> None:
    os.makedirs(SAVE_DIR, exist_ok=True)
    event = dict(event)
    event["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path(league_id), "a") as fh:
        fh.write(json.dumps(event) + "\n")


def latest_save(league_id: Optional[str] = None) -> Optional[str]:
    pattern = "%s-*.json" % (league_id or "*")
    files = [f for f in glob.glob(os.path.join(SAVE_DIR, pattern))
             if not f.endswith(".tmp")]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def restore(state, path: str) -> int:
    """Replay a snapshot into a fresh DraftState. Returns picks restored."""
    from .models import Pick

    with open(path, "r") as fh:
        data = json.load(fh)

    # The save's my_slot WINS over the league yaml. The save records the
    # draft that actually ran; the yaml is pre-draft guesswork and can go
    # stale (a stale yaml once resumed a crashed draft recommending for the
    # wrong team). Warn loudly on a conflict so a mis-edited save cannot
    # flip the board silently either.
    if data.get("my_slot"):
        saved_slot = int(data["my_slot"])
        yaml_slot = state.league.my_slot
        if yaml_slot and int(yaml_slot) != saved_slot:
            sys.stderr.write(
                "\n"
                "  !! MY-SLOT CONFLICT: this save says my_slot %d, but %s\n"
                "  !! says my_slot %s. Resuming with the SAVE's slot %d - the\n"
                "  !! save reflects the draft that actually ran. If the yaml\n"
                "  !! is right, fix the save (or delete it and re-sync).\n\n"
                % (saved_slot, state.league.path or "the league yaml",
                   yaml_slot, saved_slot))
        state.league.my_slot = saved_slot

    restored = 0
    # Sorted by overall so old saves (no per-pick "seq") get application
    # order stamped in overall order - the best available fallback. New
    # saves carry seq and keep their true order regardless of row order.
    rows = sorted(data.get("picks", []), key=lambda r: int(r["overall"]))
    for row in rows:
        key = row["player_key"]
        seq = row.get("seq")
        pick = Pick(int(row["overall"]), int(row["team"]), key,
                    row.get("raw", ""),
                    seq=int(seq) if seq is not None else None)
        state.picks[pick.overall] = pick
        if key in state.by_key:
            state.drafted[key] = pick
        # Placeholders ('__skipped__') and unknown keys still occupy their
        # overall - dropping them would shift every later pick onto the
        # wrong team.
        restored += 1

    state.active_branch = data.get("active_branch")
    state.branch_log = [tuple(b) for b in data.get("branch_log", [])]
    state.fired_triggers = list(data.get("fired_triggers", []))
    return restored


def list_saves(league_id: Optional[str] = None) -> List[str]:
    pattern = "%s-*.json" % (league_id or "*")
    return sorted(glob.glob(os.path.join(SAVE_DIR, pattern)),
                  key=os.path.getmtime, reverse=True)
