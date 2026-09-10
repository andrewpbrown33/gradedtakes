#!/usr/bin/env python3
"""Fantasy Draft War Room - live snake-draft decision engine.

    python3 warroom.py --league yahoo-main
    python3 warroom.py --league yahoo-main --resume

Paste picks as they happen (one line or a whole block). When you are on the
clock the recommendation block prints itself.
"""

import argparse
import os
import select
import sys
import time
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import state as save_state           # noqa: E402
from engine.ingest import Matcher, ingest_text   # noqa: E402
from engine.models import (DraftState, LeagueConfig, fmt_pick,  # noqa: E402
                           load_players, POSITIONS)
from engine.recommend import (Ansi, board_shift, board_text,  # noqa: E402
                              on_clock_block, strategy_brief, survival_odds,
                              team_needs_pos)
from engine.intel import Intel                   # noqa: E402
from engine.exposure import Exposure             # noqa: E402
from engine.strategy import StrategyTree         # noqa: E402

COMMANDS = {"quit", "exit", "q", "help", "?", "h", "me", "board", "roster",
            "needs", "status", "slot", "pivot", "undo", "skip", "find", "sync",
            "save", "plan", "notes", "brief", "expo"}

HELP = """
COMMANDS  (anything else is treated as pasted picks)
  <paste>          one pick or a whole block: "Pick 14: CeeDee Lamb", "1.05 Lamb",
                   "Bijan Robinson RB - ATL", or Yahoo's draft-results panel
  sync             bulk-paste mode: paste many lines, then a blank line
  me               show the on-clock recommendation block
  plan             strategy brief: what shifted, targets lost/alive, my next
                   picks, key decisions (also: notes / brief)
  expo             cross-league exposure: coverage + my picks also rostered
                   in my other leagues (flags are positive-only)
  board [pos]      best available (board wr / board rb / board te / board qb)
  roster [n]       my roster, or team n's roster
  needs            what every team still needs to start
  status           draft state, branch, and script adherence
  slot <n>         set my draft slot (1-10)
  pivot <branch>   switch strategy branch (pivot B)
  undo             undo the last pick
  skip             advance one pick with no player (rare)
  find <name>      look a player up
  save             force a save
  help             this list
  quit             exit (state is saved after every pick)

Also: strip.html (project root) is a one-line on-clock card that re-renders
after every applied pick - park a narrow browser window over the draft client
and it self-refreshes every few seconds.
"""


class WarRoom(object):
    def __init__(self, league_path: str, resume: bool = False, color: bool = True,
                 fresh: bool = False):
        self.c = Ansi(color)
        self.color = color

        league = LeagueConfig.load(league_path)
        csv_path = os.path.join(HERE, league.rankings_csv)
        if not os.path.exists(csv_path):
            # Never auto-seed: the seeder's defaults are one league's format,
            # and a silently mis-seeded board is worse than no board.
            from engine.models import missing_rankings_message
            print(self.c.red(missing_rankings_message(league, csv_path)))
            raise SystemExit(1)

        players = load_players(csv_path)
        self.state = DraftState(league, players)
        self.matcher = Matcher(players)

        self.tree = StrategyTree.empty()
        if league.strategy_file:
            spath = os.path.join(HERE, league.strategy_file)
            if os.path.exists(spath):
                self.tree = StrategyTree.load(spath)
                self.tree.resolve_names(self.matcher)

        self.intel = Intel.empty()
        ipath = os.path.join(HERE, "data", "player_intel.yaml")
        if os.path.exists(ipath):
            self.intel = Intel.load(ipath)
            self.intel.resolve(self.matcher)
        # Mined rival tendencies for THIS league (RUNBOOK E2 emits them).
        # Merge order is the contract in engine/tendencies.py: after the
        # research, BEFORE my_calls, so an explicit my_calls read on a slot
        # still replaces the mined one.
        self.tendencies_loaded = False
        tpath = os.path.join(HERE, "data", "tendencies.%s.yaml" % league.id)
        if os.path.exists(tpath):
            self.intel.merge(Intel.load(tpath), self.matcher)
            self.tendencies_loaded = True
        # My own calls load last and win over the research.
        self.my_overrides = 0
        mypath = os.path.join(HERE, "data", "my_calls.yaml")
        if os.path.exists(mypath):
            self.my_overrides = self.intel.merge(Intel.load(mypath), self.matcher)

        # My holdings in OTHER leagues; this league's own file is excluded.
        self.exposure = Exposure.load(self.matcher, exclude_league_id=league.id)

        print(self.c.cyan("=" * 74))
        print(self.c.bold("  FANTASY DRAFT WAR ROOM   %s" % league.name))
        print("  %d teams | %d rounds | %s | %d players loaded"
              % (league.teams, league.rounds,
                 "full PPR" if league.ppr >= 1 else ("%.1f PPR" % league.ppr),
                 len(players)))
        print("  strategy: %s | branches: %s"
              % (self.tree.name, ", ".join(sorted(self.tree.branches)) or "none"))
        if len(self.intel):
            extras = []
            if self.my_overrides:
                extras.append("%d overridden by my_calls" % self.my_overrides)
            if self.intel.never_draft:
                extras.append("%d never-draft" % len(self.intel.never_draft))
            if self.intel.managers:
                extras.append("%d manager reads%s"
                              % (len(self.intel.managers),
                                 " incl. mined" if self.tendencies_loaded
                                 else ""))
            print("  intel: %d player theses%s"
                  % (len(self.intel),
                     (" (" + ", ".join(extras) + ")") if extras else ""))
        if self.intel.unresolved:
            print(self.c.yellow("  ! intel names not in rankings: %s"
                                % ", ".join(sorted(set(self.intel.unresolved))[:5])))
        if self.tree.unresolved:
            print(self.c.yellow("  ! strategy names not found in rankings: %s"
                                % ", ".join(sorted(set(self.tree.unresolved))[:6])))
        if self.exposure.available and self.exposure.partial():
            print(self.c.yellow("  ! " + self.exposure.banner_text()))
        print(self.c.cyan("=" * 74))

        # Warm every network-backed cache NOW, before anyone is on the clock -
        # the injury dump alone is ~16MB and must never fetch mid-pick.
        print(self.c.dim("  warming data caches..."))
        try:
            from engine.recommend import warm_caches
            warm_caches()
        except Exception:
            pass   # warming is a nicety; the war room starts regardless

        if resume:
            path = save_state.latest_save(league.id)
            if path:
                n = save_state.restore(self.state, path)
                print(self.c.green("  resumed %d picks from %s"
                                   % (n, os.path.basename(path))))
            else:
                print(self.c.yellow("  no save found - starting fresh"))
        else:
            # Same-day saves resume BY DEFAULT. A fresh session's first save
            # (quit, slot, or any pick) atomically replaces today's file, so
            # a panicked mid-draft restart without --resume - crash recovery's
            # exact target scenario - used to destroy the draft it was meant
            # to recover. `--fresh` opts out and moves today's file aside.
            today = save_state.save_path(league.id)
            if os.path.exists(today) and not fresh:
                n = save_state.restore(self.state, today)
                if n:
                    print(self.c.green(
                        "  resumed today's save (%d picks) from %s"
                        % (n, os.path.basename(today))))
                    print(self.c.dim(
                        "  (use --fresh to start this league over for today)"))
            elif os.path.exists(today) and fresh:
                backup = today + time.strftime(".%H%M%S.bak")
                os.replace(today, backup)
                print(self.c.yellow("  --fresh: today's save moved to %s"
                                    % os.path.basename(backup)))

        if not self.state.my_slot:
            print(self.c.yellow(
                "  ! DRAFT SLOT NOT SET - type `slot <n>` as soon as Yahoo shows the order"))
        print(HELP)
        self.show_status()
        self.render_strip()
        self.maybe_auto_clock()

    # --- helpers -----------------------------------------------------------
    def save(self):
        save_state.save(self.state)

    def render_strip(self):
        """Re-render strip.html; guarded so it can NEVER break the draft loop."""
        try:
            from engine.strip import render as strip_render
            strip_render(self.state, self.tree, self.intel,
                         self.exposure, self.matcher)
        except Exception:
            pass   # the strip is a convenience; the terminal is the war room

    def ensure_branch(self):
        if not self.tree.branches:
            return
        if self.state.active_branch:
            return
        bid = self.tree.choose_branch(self.state, self.matcher)
        if bid:
            self.state.active_branch = bid
            self.state.branch_log.append(
                (self.state.current_pick(), bid, "entry conditions"))

    def run_triggers(self):
        alerts = self.tree.evaluate(self.state, self.matcher)
        for a in alerts:
            self.state.fired_triggers.append(a.trigger_id)
            if a.goto and a.auto and a.goto in self.tree.branches:
                self.state.active_branch = a.goto
                self.state.branch_log.append(
                    (self.state.current_pick(), a.goto, a.text))
                print(self.c.red("  >> AUTO-PIVOT to branch %s: %s" % (a.goto, a.text)))
            else:
                self.state.pending_alerts.append(a)
                if not self.state.is_my_turn():
                    prefix = ">> PIVOT FLAG: " if a.level == "pivot" else "! "
                    print(self.c.yellow("  " + prefix + a.text))

    def maybe_auto_clock(self):
        if self.state.is_complete():
            print(self.c.green("  DRAFT COMPLETE"))
            return
        if self.state.is_my_turn():
            self.show_clock()
        elif self.state.my_slot:
            until = self.state.picks_until_mine()
            nxt = self.state.next_my_pick()
            if until is not None and nxt is not None:
                print(self.c.dim("  on the clock: %s | my next pick %s in %d picks"
                                 % (self.state.team_label(self.state.on_the_clock()),
                                    fmt_pick(nxt, self.state.teams), until)))

    def show_clock(self):
        self.ensure_branch()
        alerts = list(self.state.pending_alerts)
        print(on_clock_block(self.state, self.tree, alerts, color=self.color,
                             intel=self.intel, matcher=self.matcher,
                             exposure=self.exposure))
        self.state.pending_alerts = []
        self.render_strip()

    def show_status(self):
        s = self.state
        cur = s.current_pick()
        print(self.c.bold("  STATUS"))
        if s.is_complete():
            print("   draft complete - %d picks made" % len(s.picks))
        else:
            print("   pick %d (%s), round %d | on the clock: %s"
                  % (cur, fmt_pick(cur, s.teams), s.current_round(),
                     s.team_label(s.on_the_clock())))
        if s.my_slot:
            nxt = s.next_my_pick()
            if nxt:
                print("   my slot %d | next pick %s (%d away)"
                      % (s.my_slot, fmt_pick(nxt, s.teams), nxt - cur))
            roster = s.my_roster()
            if roster:
                print("   my roster: " + ", ".join(
                    "%s(%s)" % (p.name, p.pos) for p in roster))
            else:
                print("   my roster: empty")
        else:
            print(self.c.yellow("   my slot: NOT SET - type `slot <n>`"))
        if self.tree.branches:
            b = self.tree.active(s)
            print("   branch: %s | %s"
                  % ((b.id + " - " + b.name) if b else "not chosen yet",
                     self.tree.script_status(s)))

    def show_needs(self):
        s = self.state
        print(self.c.bold("  WHAT EACH TEAM STILL NEEDS TO START"))
        for t in range(1, s.teams + 1):
            needs = [p for p in POSITIONS if team_needs_pos(s, t, p)]
            roster = s.roster(t)
            print("   %-14s (%d picks) needs: %s"
                  % (s.team_label(t), len(roster),
                     ", ".join(needs) if needs else "starters full"))

    def show_roster(self, team: Optional[int]):
        s = self.state
        team = team or s.my_slot
        if not team:
            print("  No slot set. Use `roster <n>` or `slot <n>`.")
            return
        print(self.c.bold("  %s" % s.team_label(team)))
        roster = s.roster(team)
        if not roster:
            print("   (empty)")
            return
        for pick in sorted([p for p in s.picks.values() if p.team == team],
                           key=lambda x: x.overall):
            pl = s.by_key.get(pick.player_key)
            if pl is None:   # '__skipped__' placeholder - board slot, no player
                print("   %-6s %s" % (fmt_pick(pick.overall, s.teams),
                                      self.c.dim("(unmatched pick: %s)"
                                                 % (pick.raw or "skipped"))))
                continue
            print("   %-6s %-24s %-4s %-4s bye %s"
                  % (fmt_pick(pick.overall, s.teams), pl.name, pl.pos,
                     pl.team, pl.bye or "-"))

    def show_exposure(self):
        exp = self.exposure
        if not exp.available:
            print("  no roster data for my OTHER leagues (this league's own"
                  "\n  file is excluded) - add data/rosters/<league>.yaml files")
            return
        print(self.c.bold("  CROSS-LEAGUE EXPOSURE"))
        for name, known, size in exp.coverage():
            print("   %-24s known %d/%d" % (name, known, size))
        pairs = exp.overlap(self.state)
        if pairs:
            for pl, leagues in pairs:
                print("   %-24s %-4s drafted - also yours in %s"
                      % (pl.name, pl.pos, ", ".join(leagues)))
        else:
            print("   no KNOWN overlaps on my roster (flags are positive-only:"
                  "\n   an unflagged player is unknown, never 'not rostered')")
        banner = exp.banner_text()
        if banner:
            print(self.c.yellow("   ! " + banner))
        for name, misses in exp.unresolved():
            print(self.c.yellow("   ! %s names not in rankings: %s"
                                % (name, ", ".join(misses[:5]))))

    def find(self, text: str):
        m = self.matcher.match(text)
        if not m:
            print("  no match for '%s'" % text)
            return
        p = m.player
        taken = self.state.drafted.get(p.key)
        where = ("DRAFTED %s by %s" % (fmt_pick(taken.overall, self.state.teams),
                                       self.state.team_label(taken.team))
                 if taken else "available")
        surv = ""
        if not taken and self.state.my_slot:
            surv = " | %d%% to reach my next pick" % round(
                survival_odds(self.state, p) * 100)
        print("  %-24s %-4s %-4s rank %-4d tier %-3d ADP %-6s %s%s"
              % (p.name, p.pos, p.team, p.rank, p.tier,
                 ("%.1f" % p.adp) if p.adp else "-", where, surv))
        hit = self.intel.for_player(p.key)
        if hit:
            pts, note = hit
            print("     %s%+.0f  %s" % ("BUY  " if pts > 0 else "FADE ", pts, note))

    # --- input -------------------------------------------------------------
    def read_block(self, prompt: str) -> Optional[str]:
        """Read a line, then grab any further lines a paste delivered with it."""
        try:
            first = input(prompt)
        except EOFError:
            return None
        lines = [first]
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.12)
            if not ready:
                break
            more = sys.stdin.readline()
            if not more:
                break
            lines.append(more.rstrip("\n"))
        return "\n".join(lines)

    def sync_mode(self):
        print("  paste the draft results now; finish with an empty line")
        lines = []
        while True:
            try:
                ln = input()
            except EOFError:
                break
            if not ln.strip():
                break
            lines.append(ln)
        if lines:
            self.handle_picks("\n".join(lines))

    def handle_picks(self, text: str):
        s = self.state
        before = s.current_pick()
        result = ingest_text(text, s, self.matcher)

        my_pick_made = False
        for pick, player in result.applied:
            if pick.team == s.my_slot:
                my_pick_made = True
                print(self.c.green("  YOU >> %-6s %s"
                                   % (fmt_pick(pick.overall, s.teams),
                                      player.label())))
            else:
                print("  %s %-6s %-14s %s"
                      % (self.c.green("OK"), fmt_pick(pick.overall, s.teams),
                         s.team_label(pick.team), player.label()))
            save_state.log_event(s.league.id,
                                 {"type": "pick", "overall": pick.overall,
                                  "team": pick.team, "player": player.name,
                                  "raw": pick.raw})
        for w in result.warnings:
            print(self.c.yellow("  ! " + w))
        if result.duplicates:
            print(self.c.dim("  (%d already-known pick(s) ignored)"
                             % len(result.duplicates)))
        for u in result.unmatched:
            print(self.c.red("  ? no player matched: %s" % u))

        if result.applied:
            self.ensure_branch()
            self.save()
            self.render_strip()
            self.run_triggers()
            after = s.current_pick()
            if len(result.applied) > 1:
                print(self.c.dim("  synced %d picks (%d -> %d)"
                                 % (len(result.applied), before, after)))
            if my_pick_made and s.my_slot:
                roster = s.my_roster()
                print(self.c.bold("  my roster (%d): %s"
                                  % (len(roster), ", ".join(
                                      "%s(%s)" % (p.surname(), p.pos)
                                      for p in roster))))
            elif len(result.applied) >= 3 and s.my_slot and not s.is_my_turn():
                counts, notable = board_shift(s)
                if counts:
                    parts = ["%s x%d" % (pos, n) for pos, n in
                             sorted(counts.items(), key=lambda kv: -kv[1])]
                    line = "  shift since my pick: " + ", ".join(parts)
                    if notable:
                        line += " | gone: " + ", ".join(
                            p.surname() for p in notable[:5])
                    print(self.c.dim(line + "  (`plan` for detail)"))
            self.maybe_auto_clock()
        elif not result.duplicates and not result.unmatched:
            print("  nothing to do")
        elif result.duplicates and not result.applied:
            self.maybe_auto_clock()

    # --- command loop ------------------------------------------------------
    def loop(self):
        while True:
            s = self.state
            tag = "ME" if (s.my_slot and s.is_my_turn()) else "  "
            prompt = "\n[%s %s] > " % (fmt_pick(min(s.current_pick(),
                                                    s.total_picks()), s.teams), tag)
            block = self.read_block(prompt)
            if block is None:
                print("\n  bye - state saved")
                return
            if not block.strip():
                continue

            # Classify every line before anything is matched. A command line
            # must never reach the player matcher - typing `undo` once drafted a
            # random defense because the whole block was treated as picks.
            buffer = []
            for line in block.splitlines():
                line = line.strip()
                if not line:
                    continue
                token = line.split()[0].lower()
                if token in COMMANDS:
                    if buffer:
                        self.handle_picks("\n".join(buffer))
                        buffer = []
                    if self.run_command(token, line[len(token):].strip()):
                        return
                else:
                    buffer.append(line)
            if buffer:
                self.handle_picks("\n".join(buffer))

    def run_command(self, cmd: str, arg: str) -> bool:
        """Execute one command. Returns True when the app should exit."""
        try:
            if cmd in ("quit", "exit", "q"):
                self.save()
                print("  saved. good luck.")
                return True
            elif cmd in ("help", "?", "h"):
                print(HELP)
            elif cmd == "me":
                self.show_clock()
            elif cmd in ("plan", "notes", "brief"):
                self.ensure_branch()
                print(strategy_brief(self.state, self.tree, self.intel,
                                     color=self.color,
                                     exposure=self.exposure))
            elif cmd == "expo":
                self.show_exposure()
            elif cmd == "board":
                pos = arg.upper() if arg else None
                print(board_text(self.state, pos, 18, self.color))
            elif cmd == "roster":
                self.show_roster(int(arg) if arg.isdigit() else None)
            elif cmd == "needs":
                self.show_needs()
            elif cmd == "status":
                self.show_status()
            elif cmd == "slot":
                if not arg.isdigit() or not (1 <= int(arg) <= self.state.teams):
                    print("  usage: slot <1-%d>" % self.state.teams)
                else:
                    self.state.league.my_slot = int(arg)
                    # Re-key existing picks to the new slot alignment.
                    print(self.c.green("  my slot set to %s" % arg))
                    self.save()
                    self.show_status()
                    self.maybe_auto_clock()
            elif cmd == "pivot":
                bid = arg.strip().upper()
                if bid in self.tree.branches:
                    self.state.active_branch = bid
                    self.state.branch_log.append(
                        (self.state.current_pick(), bid, "manual"))
                    self.save()
                    print(self.c.green("  branch -> %s (%s)"
                                       % (bid, self.tree.branches[bid].name)))
                    if self.state.is_my_turn():
                        self.show_clock()
                else:
                    print("  branches: %s" % ", ".join(sorted(self.tree.branches)))
            elif cmd == "undo":
                pick = self.state.undo_last()
                if not pick:
                    print("  nothing to undo")
                else:
                    pl = self.state.by_key.get(pick.player_key)
                    print(self.c.yellow("  undid %s %s"
                                        % (fmt_pick(pick.overall, self.state.teams),
                                           pl.name if pl else pick.player_key)))
                    self.save()
                    self.render_strip()
                    self.maybe_auto_clock()
            elif cmd == "skip":
                from engine.models import Pick
                n = self.state.current_pick()
                self.state.picks[n] = Pick(n, self.state.team_at(n),
                                           "__skipped__", "skip")
                self.save()
                self.render_strip()
                print("  skipped pick %d" % n)
                self.maybe_auto_clock()
            elif cmd == "find":
                self.find(arg)
            elif cmd == "sync":
                self.sync_mode()
            elif cmd == "save":
                print("  saved -> %s" % save_state.save(self.state))
        except Exception as exc:  # never die mid-draft
            print(self.c.red("  error: %s: %s" % (type(exc).__name__, exc)))
        return False


def main():
    ap = argparse.ArgumentParser(description="Fantasy Draft War Room")
    ap.add_argument("--league", default="yahoo-main",
                    help="league config name in leagues/ (default: yahoo-main)")
    ap.add_argument("--resume", action="store_true",
                    help="restore the most recent save for this league "
                         "(any date; same-day saves resume automatically)")
    ap.add_argument("--fresh", action="store_true",
                    help="do NOT auto-resume today's save; move it aside "
                         "and start this league's draft over")
    ap.add_argument("--slot", type=int, help="my draft slot (overrides config)")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    path = args.league
    if not os.path.exists(path):
        path = os.path.join(HERE, "leagues", args.league)
        if not path.endswith((".yaml", ".yml")):
            path += ".yaml"
    if not os.path.exists(path):
        print("No league config at %s" % path)
        return 1

    color = (not args.no_color) and sys.stdout.isatty()
    room = WarRoom(path, resume=args.resume, color=color, fresh=args.fresh)
    if args.slot:
        room.state.league.my_slot = args.slot
        print("  my slot set to %d" % args.slot)
        room.maybe_auto_clock()
    try:
        room.loop()
    except KeyboardInterrupt:
        room.save()
        print("\n  interrupted - state saved. restart with --resume")
    return 0


if __name__ == "__main__":
    sys.exit(main())
