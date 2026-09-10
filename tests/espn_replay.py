#!/usr/bin/env python3
"""Acceptance test: replay a scripted ESPN feed through the real live() loop.

A fake espn module stands in for the network: connect() returns a stub league
and draft_picks() serves cumulative pick lists poll by poll, the way ESPN's
real draft endpoint does. The script includes a keeper landing mid-board, an
unmatchable name, a nameless pick, an exact repeat payload (dedupe), one poll
that raises, and my back-to-back snake-turn picks at overalls 12 and 13.

    .venv/bin/python tests/espn_replay.py
"""

import contextlib
import datetime
import glob
import io
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import espn_cli                                  # noqa: E402
from engine import state as save_state                       # noqa: E402
from engine.models import DraftState, LeagueConfig, Pick, load_players  # noqa: E402
from engine.recommend import on_clock_block                  # noqa: E402
from engine.strategy import StrategyTree                     # noqa: E402

FAILURES = []
LEAGUE_ID = "espn-replay"

LEAGUE_YAML = """\
# Throwaway league for the ESPN replay test - 12 teams, drafting 12th.
id: espn-replay
name: "ESPN replay (test)"
platform: espn
teams: 12
my_slot: 12
roster_spots: [QB, RB, RB, WR, WR, TE, W/R/T, K, DEF, BN, BN, BN, BN, BN, BN, BN]
rounds: 16
rankings_csv: data/rankings.csv
scoring:
  reception: 0.5
team_names: []
"""


def check(cond, label):
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILURES.append(label)


def clean_saves():
    for f in glob.glob(os.path.join(HERE, "saves", "%s-*" % LEAGUE_ID)):
        os.remove(f)


class FakeEspn(object):
    """Stands in for engine.espn: exactly the two callables live() touches."""

    def __init__(self, feed, teams):
        self.feed = feed          # one payload (or Exception) per poll
        self.polls = 0
        self.lg = types.SimpleNamespace(year=datetime.date.today().year,
                                        teams=[object()] * teams)

    def connect(self):
        return self.lg

    def draft_picks(self, lg):
        payload = self.feed[min(self.polls, len(self.feed) - 1)]
        self.polls += 1
        if isinstance(payload, Exception):
            raise payload
        # Fresh dicts, sorted by overall - same contract as the real reader.
        return sorted([dict(p) for p in payload], key=lambda r: r["overall"])


def build_feed(players):
    """Cumulative poll payloads. Slot 12 owns overalls 12 and 13 (snake turn)."""
    def e(overall, name, keeper=False):
        return {"overall": overall, "name": name, "keeper": keeper}

    real = lambda o: e(o, players[o - 1].name)
    poll1 = [real(1), real(2), real(3),
             e(100, players[99].name, keeper=True)]
    poll2 = poll1 + [real(4), real(5),
                     e(6, "Zzyzx Fakeplayer"),   # never matches
                     e(7, ""),                   # playerId not in player_map
                     real(8)]
    poll3 = poll2 + [real(9), real(10), real(11)]   # poll2 repeated verbatim
    poll5 = poll3 + [real(12)]
    poll6 = poll5 + [real(13)]
    return [poll1, poll2, poll3,
            RuntimeError("injected feed failure"),   # poll 4 dies mid-draft
            poll5, poll6]


def rebuild_board(cfg_path, players, saved):
    """The saved board, placeholders included - restore() would drop those."""
    st = DraftState(LeagueConfig.load(cfg_path), players)
    for row in saved["picks"]:
        key = row["player_key"]
        if key in st.by_key:
            st.apply_pick(st.by_key[key], int(row["overall"]))
        else:
            st.picks[int(row["overall"])] = Pick(int(row["overall"]),
                                                 int(row["team"]), key,
                                                 row.get("raw", ""))
    return st


def main():
    print("=" * 74)
    print("ESPN REPLAY - live() driven end-to-end by a scripted feed")
    print("=" * 74)

    players = load_players(os.path.join(HERE, "data", "rankings.csv"))
    feed = build_feed(players)
    fake = FakeEspn(feed, teams=12)

    fd, cfg_path = tempfile.mkstemp(prefix="espn-replay-", suffix=".yaml")
    with os.fdopen(fd, "w") as fh:
        fh.write(LEAGUE_YAML)

    clean_saves()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = espn_cli.live(league_path=cfg_path, espn_mod=fake,
                               poll_seconds=0, max_polls=len(feed))
        out = buf.getvalue()

        print("\n1. LIVE LOOP TRANSCRIPT")
        print("\n".join("   |%s" % ln for ln in out.rstrip().splitlines()))

        print("\n2. LOOP MECHANICS")
        check(rc == 0, "live() exited 0")
        check(fake.polls == len(feed), "all %d scripted polls consumed" % len(feed))
        check("resumed" not in out, "started from a clean board (no stale resume)")
        check(out.count("poll failed") == 1
              and "poll failed (RuntimeError: injected feed failure)" in out,
              "poll 4's exception was caught and the loop kept going")

        path = save_state.latest_save(LEAGUE_ID)
        check(path is not None, "a save file was written for %s" % LEAGUE_ID)
        if path is None:
            raise AssertionError("no save file - cannot audit the board")
        with open(path) as fh:
            saved = json.load(fh)
        by_overall = dict((int(r["overall"]), r) for r in saved["picks"])

        print("\n3. BOARD INTEGRITY (from the saved snapshot)")
        fed = set(range(1, 14)) | {100}
        check(set(by_overall) == fed,
              "every fed overall occupies exactly that overall (%d picks)"
              % len(fed))
        check(len(saved["picks"]) == len(by_overall),
              "no overall was double-applied after the repeat poll")
        real_overalls = [n for n in sorted(fed) if n not in (6, 7)]
        placed = [n for n in real_overalls
                  if by_overall.get(n, {}).get("player_key") == players[n - 1].key]
        check(placed == real_overalls,
              "all %d matched picks landed on their own overall" % len(real_overalls))
        check(by_overall.get(8, {}).get("player_key") == players[7].key,
              "no board shift: pick 8 still holds %s" % players[7].name)
        check(by_overall.get(6, {}).get("player_key") == "__skipped__"
              and by_overall[6].get("raw") == "Zzyzx Fakeplayer",
              "overall 6 held as a placeholder with ESPN's name in raw")
        check(by_overall.get(7, {}).get("player_key") == "__skipped__",
              "overall 7 (nameless pick) held as a placeholder")
        check(by_overall.get(100, {}).get("player_key") == players[99].key,
              "keeper sits at overall 100 (%s)" % players[99].name)
        check(" [keeper]" in out, "keeper pick was tagged on screen")

        print("\n4. INGEST LINES AND ON-CLOCK BEHAVIOR")
        ok_lines = re.findall(r"^\s+ok\s+\d+\.\d\d\s", out, re.M)
        check(len(ok_lines) == 10,
              "10 rival picks printed once each (got %d)" % len(ok_lines))
        check(out.count("YOU >>") == 2,
              "both of my snake-turn picks (12, 13) printed as YOU >>")
        check(out.count("held as placeholder") == 2,
              "exactly two placeholder lines (no re-ingest on the repeat poll)")
        check(out.count("ON THE CLOCK") == 2,
              "on-clock block printed twice for the back-to-back turn")

        print("\n5. PLACEHOLDERS DON'T BREAK RENDERING")
        st = rebuild_board(cfg_path, players, saved)
        check(st.current_pick() == 14, "rebuilt board is on pick 14")
        block = on_clock_block(st, StrategyTree.empty(), [], color=False)
        check(block and "ON THE CLOCK" in block,
              "on_clock_block renders over a board holding placeholders")
    finally:
        clean_saves()
        os.remove(cfg_path)

    print("\n" + "=" * 74)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
