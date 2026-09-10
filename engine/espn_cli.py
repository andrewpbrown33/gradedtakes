"""`./espn.sh check` and `./espn.sh draft` - ESPN connection and live draft."""

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore", message=".*OpenSSL.*")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import espn                                    # noqa: E402
from engine.recommend import Ansi                          # noqa: E402

POLL_SECONDS = 4


def check() -> int:
    print("Connecting to ESPN...")
    try:
        lg = espn.connect()
    except espn.EspnError as exc:
        print("\n  %s" % exc)
        return 1
    except Exception as exc:
        print("\n  Connection failed: %s: %s" % (type(exc).__name__, exc))
        print("  See SETUP_ESPN.md - 'What can go wrong'.")
        return 1

    import datetime
    f = espn.league_facts(lg)
    c = Ansi(sys.stdout.isatty())
    expected = datetime.date.today().year
    print("\n  League  : %s" % f["name"])
    print(c.bold("  Season  : %s" % f["year"])
          + " | %d teams | scoring: %s" % (f["teams"], f["scoring_type"]))
    if f["year"] != expected:
        print(c.yellow("  WARNING : connected to the %s season, not %d - ESPN "
                       "may not have opened the new season yet" % (f["year"], expected)))
    if f["roster_slots"]:
        slots = ", ".join("%s x%d" % (k, v) for k, v in f["roster_slots"].items() if v)
        print("  Roster  : %s  (slot mapping approximate)" % slots)
    if f["reception_points"] is not None:
        print("  Receptions: %s pts" % f["reception_points"])
    else:
        print("  Receptions: not found")
    print("\n  TEAMS (ESPN team_id order - NOT draft order; get your slot "
          "from the draft room)")
    for i, n in enumerate(f["team_names"], start=1):
        print("   %2d. %s" % (i, n))

    picks = espn.draft_picks(lg)
    if picks:
        print("\n  Draft has %d picks recorded already." % len(picks))
    else:
        print("\n  Draft has not started yet (expected before draft day).")

    print(c.green("\n  Connection works. Nothing was modified - this is read-only."))
    print("  On draft day run:  ./espn.sh draft")
    return 0


def live(league_path=None, espn_mod=None, poll_seconds=None,
         max_polls=None, slot=None, resume=False) -> int:
    """Poll ESPN for new picks and feed them into the war room.

    The keyword arguments exist for tests: a fake espn module can be injected
    and the loop bounded. Defaults preserve the CLI behavior exactly.
    """
    import datetime
    from engine.ingest import Matcher
    from engine.models import (LeagueConfig, load_players, DraftState,
                               fmt_pick, Pick)
    from engine.intel import Intel
    from engine.exposure import Exposure
    from engine.strategy import StrategyTree
    from engine.recommend import on_clock_block
    from engine import state as save_state

    if espn_mod is None:
        espn_mod = espn
    if poll_seconds is None:
        poll_seconds = POLL_SECONDS

    cfg = league_path or os.path.join(HERE, "leagues", "espn-1.yaml")
    if not os.path.exists(cfg):
        print("  leagues/espn-1.yaml not found.")
        return 1

    league = LeagueConfig.load(cfg)
    if slot:
        league.my_slot = int(slot)
    csv_path = os.path.join(HERE, league.rankings_csv)
    if not os.path.exists(csv_path):
        # Same guard as warroom.py: a missing per-league CSV must fail loudly
        # with the reseed commands, never crash or inherit another league's file.
        from engine.models import missing_rankings_message
        print(missing_rankings_message(league, csv_path))
        return 1
    players = load_players(csv_path)
    st = DraftState(league, players)
    matcher = Matcher(players)
    c = Ansi(sys.stdout.isatty())

    tree = StrategyTree.empty()
    spath = os.path.join(HERE, league.strategy_file or "")
    if league.strategy_file and os.path.exists(spath):
        tree = StrategyTree.load(spath)
        tree.resolve_names(matcher)

    intel = Intel.empty()
    ipath = os.path.join(HERE, "data", "player_intel.yaml")
    if os.path.exists(ipath):
        intel = Intel.load(ipath)
        intel.resolve(matcher)
    # Mined rival tendencies for THIS league (RUNBOOK E2 emits them).
    # Merge order per engine/tendencies.py: after the research, BEFORE
    # my_calls, so an explicit my_calls read on a slot still wins.
    tpath = os.path.join(HERE, "data", "tendencies.%s.yaml" % league.id)
    if os.path.exists(tpath):
        intel.merge(Intel.load(tpath), matcher)
        print("  mined tendencies loaded: %s" % os.path.basename(tpath))
    mypath = os.path.join(HERE, "data", "my_calls.yaml")
    if os.path.exists(mypath):
        intel.merge(Intel.load(mypath), matcher)

    # My holdings in OTHER leagues; this league's own file is excluded.
    exposure = Exposure.load(matcher, exclude_league_id=league.id)

    # Resume is EXPLICIT (--resume) and SAME-DAY only. Auto-resuming the
    # mtime-latest save across dates replayed stale boards: yesterday's
    # rehearsal made real feed picks look already-known (silently skipped via
    # the dedupe filter), and a completed old save exited before polling
    # even started. The feed is cumulative, so a fresh start rebuilds the
    # full board from ESPN on the first poll anyway.
    if resume:
        saved = save_state.save_path(league.id)
        if os.path.exists(saved):
            n = save_state.restore(st, saved)
            print(c.green("  resumed %d picks from today's save" % n))
        else:
            print(c.yellow("  --resume: no save for %s dated today - "
                           "starting fresh" % league.id))

    try:
        lg = espn_mod.connect()
    except espn.EspnError as exc:
        print("  %s" % exc)
        return 1

    # Hard guards - a live draft with any of these wrong drafts the wrong board.
    if not league.my_slot:
        print(c.red("  my_slot is not set in %s. Add it there, or rerun with "
                    "--slot N (your 1-based draft position)." % cfg))
        return 1
    expected = datetime.date.today().year
    if getattr(lg, "year", None) != expected:
        print(c.red("  ESPN returned the %s season but this draft is %d - the "
                    "league for the new season may not exist yet. Aborting."
                    % (getattr(lg, "year", None), expected)))
        return 1
    espn_teams = len(getattr(lg, "teams", []) or [])
    if espn_teams != league.teams:
        print(c.red("  Team count mismatch: ESPN has %d teams but %s says %d. "
                    "Fix the config before drafting." % (espn_teams, cfg, league.teams)))
        return 1

    print(c.cyan("=" * 74))
    print(c.bold("  ESPN LIVE DRAFT   %s   slot %s of %d"
                 % (league.name, league.my_slot or "?", league.teams)))
    print("  Polling every %ds. Ctrl-C to stop; manual paste still works in"
          % poll_seconds)
    print("  ./start.sh --league espn-1 if the connection drops.")
    print("  strip.html re-renders after every pick - park a narrow browser")
    print("  window on it for the always-glanceable on-clock card.")
    if exposure.available and exposure.partial():
        print(c.yellow("  ! " + exposure.banner_text()))
    print(c.cyan("=" * 74))

    # Warm every network-backed cache NOW - the injury dump alone is ~16MB
    # and must never fetch mid-pick. Guarded: warming is a nicety.
    print(c.dim("  warming data caches..."))
    try:
        from engine.recommend import warm_caches
        warm_caches()
    except Exception:
        pass

    def render_strip():
        """Re-render strip.html; guarded so it can NEVER break the poll loop."""
        try:
            from engine.strip import render as strip_render
            strip_render(st, tree, intel, exposure, matcher)
        except Exception:
            pass

    render_strip()
    seen = set(p.overall for p in st.picks.values())
    last_blocked_pick = None
    failures = 0
    polls = 0
    try:
        while not st.is_complete():
            if max_polls is not None and polls >= max_polls:
                break
            polls += 1
            try:
                picks = espn_mod.draft_picks(lg)

                new = [p for p in picks
                       if p["overall"] not in seen and p["overall"] not in st.picks]
                for p in new:
                    overall, name, keeper = p["overall"], p["name"], p["keeper"]
                    if overall in seen or overall in st.picks:
                        # Two entries in one payload shared an overall - the
                        # first claimed the slot. Applying another would ghost
                        # a player off the pool or overwrite the real pick.
                        continue
                    m = matcher.match(name) if name else None
                    if m and not st.is_drafted(m.player.key):
                        pick = st.apply_pick(m.player, overall)
                        mine = pick.team == st.my_slot
                        line = "  %s %-6s %s%s" % (
                            "YOU >>" if mine else "  ok  ",
                            fmt_pick(overall, st.teams), m.player.label(),
                            " [keeper]" if keeper else "")
                        print(c.green(line) if mine else line)
                        if m.ambiguous:
                            alt = m.runner_up.name if m.runner_up else "?"
                            print(c.yellow("  ? ambiguous: ESPN said %r, took "
                                           "%s over %s" % (name, m.player.name, alt)))
                    else:
                        # Same placeholder the `skip` command uses - the slot is
                        # held so ESPN's overall numbering stays authoritative.
                        st.picks[overall] = Pick(overall, st.team_at(overall),
                                                 "__skipped__", name)
                        why = ("no name from ESPN" if not name else
                               "matched player already drafted" if m else
                               "no match")
                        print(c.yellow("  ? %-6s held as placeholder (%s): %s"
                                       % (fmt_pick(overall, st.teams), why,
                                          name or "-")))
                    seen.add(overall)

                if new:
                    if tree.branches and not st.active_branch:
                        bid = tree.choose_branch(st, matcher)
                        if bid:
                            st.active_branch = bid
                    # Mirrors warroom.run_triggers: auto pivots apply, the
                    # rest queue for the next on-clock block.
                    for a in tree.evaluate(st, matcher):
                        st.fired_triggers.append(a.trigger_id)
                        if a.goto and a.auto and a.goto in tree.branches:
                            st.active_branch = a.goto
                            st.branch_log.append(
                                (st.current_pick(), a.goto, a.text))
                            print(c.red("  >> AUTO-PIVOT to branch %s: %s"
                                        % (a.goto, a.text)))
                        else:
                            st.pending_alerts.append(a)
                            if not st.is_my_turn():
                                prefix = (">> PIVOT FLAG: "
                                          if a.level == "pivot" else "! ")
                                print(c.yellow("  " + prefix + a.text))
                    save_state.save(st)
                    render_strip()

                if st.is_my_turn() and st.current_pick() != last_blocked_pick:
                    # Mirrors warroom.ensure_branch: the first block can land
                    # before any feed pick (slot 1, or a same-day resume), so
                    # branch selection cannot live only in the `if new:` path.
                    if tree.branches and not st.active_branch:
                        bid = tree.choose_branch(st, matcher)
                        if bid:
                            st.active_branch = bid
                            st.branch_log.append(
                                (st.current_pick(), bid, "entry conditions"))
                    last_blocked_pick = st.current_pick()
                    alerts = list(st.pending_alerts)
                    st.pending_alerts = []
                    print(on_clock_block(st, tree, alerts, color=c.on,
                                         intel=intel, matcher=matcher,
                                         exposure=exposure))
                    render_strip()
                failures = 0
            except Exception as exc:  # never die mid-draft
                failures += 1
                print(c.red("  poll failed (%s: %s) - retrying"
                            % (type(exc).__name__, exc)))
                if failures >= 5 and failures % 5 == 0:
                    print(c.red("  AUTO-INGEST FAILING - switch to manual: "
                                "Ctrl-C, then LEAGUE=espn-1 ./start.sh --resume"))
            if poll_seconds:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        save_state.save(st)
        print("\n  stopped - state saved (%d picks)" % len(st.picks))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="./espn.sh",
                                 description="ESPN connection and live draft")
    ap.add_argument("cmd", nargs="?", default="check",
                    choices=["check", "draft", "live"])
    ap.add_argument("--slot", type=int, default=None,
                    help="override my_slot: your 1-based draft position "
                         "(shown in the ESPN draft room)")
    ap.add_argument("--resume", action="store_true",
                    help="restore today's save for this league before "
                         "polling (crash recovery; never a cross-date save)")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.cmd == "check":
        return check()
    return live(slot=args.slot, resume=args.resume)


if __name__ == "__main__":
    sys.exit(main())
