#!/usr/bin/env python3
"""Practice mode: a full mock draft against 9 ADP-driven bots.

    ./practice.sh            # fresh 10-team mock, your real league settings
    ./practice.sh --resume   # continue the last practice draft

Bots pick with ADP + roster-need logic and a different random temperament each
run, so every practice draft plays out differently. Your picks work exactly
like the real war room: type a name, read the block, go. Practice state lives
in its own save file - the real draft is never touched.
"""

import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine import state as save_state
from engine.ingest import Matcher, ingest_text
from engine.intel import Intel
from engine.models import DraftState, LeagueConfig, fmt_pick, load_players
from engine.recommend import (Ansi, board_text, on_clock_block, strategy_brief,
                              team_needs_pos)
from engine.strategy import StrategyTree

HELP = """
PRACTICE COMMANDS
  <name>       make your pick (e.g. gibbs / nacua / bowers)
  me           reprint the on-clock block     plan    strategy brief
  board [pos]  best available                 roster  your roster so far
  undo         rewind your last pick (bot picks after it rewind too)
  fast         auto-pick the engine's #1 for you, one round
  quit         exit (resume later with ./practice.sh --resume)
"""


def bot_choice(state, team, rng, temperament):
    pool = sorted(state.available(), key=lambda p: p.rank)[:20]
    rounds_left = state.league.rounds - state.current_round() + 1
    best, best_score = None, -1e9
    for p in pool:
        if p.pos in ("K", "DEF") and rounds_left > 2:
            continue
        score = -p.rank + rng.uniform(0, temperament[team])
        if team_needs_pos(state, team, p.pos):
            score += 14
        counts = state.pos_counts(team)
        if p.pos == "QB" and counts.get("QB", 0) >= 1:
            score -= 40
        if p.pos == "TE" and counts.get("TE", 0) >= 1:
            score -= 30
        if score > best_score:
            best, best_score = p, score
    return best or pool[0]


class Practice(object):
    def __init__(self, resume=False):
        self.c = Ansi(sys.stdout.isatty())
        league = LeagueConfig.load(os.path.join(HERE, "leagues", "yahoo-main.yaml"))
        league.id = "rehearsal"
        players = load_players(os.path.join(HERE, league.rankings_csv))
        self.state = DraftState(league, players)
        self.matcher = Matcher(players)
        self.tree = StrategyTree.load(os.path.join(HERE, league.strategy_file))
        self.tree.resolve_names(self.matcher)
        self.intel = Intel.load(os.path.join(HERE, "data", "player_intel.yaml"))
        self.intel.resolve(self.matcher)

        if resume:
            path = save_state.latest_save("rehearsal")
            if path:
                n = save_state.restore(self.state, path)
                print(self.c.green("  resumed practice draft (%d picks in)" % n))

        self.rng = random.Random()
        # Each bot gets its own noise level: low = drafts chalk, high = chaotic.
        self.temperament = dict(
            (t, self.rng.uniform(2, 11)) for t in range(1, league.teams + 1))

        print(self.c.cyan("=" * 74))
        print(self.c.bold("  PRACTICE DRAFT   %s  |  you are slot %d of %d  |  full PPR"
                          % (league.name, league.my_slot, league.teams)))
        print("  Bots use live ADP + roster need, with a fresh temperament each run.")
        print(self.c.cyan("=" * 74))
        print(HELP)

    # -- engine hooks --------------------------------------------------------
    def ensure_branch(self):
        if self.tree.branches and not self.state.active_branch:
            bid = self.tree.choose_branch(self.state, self.matcher)
            if bid:
                self.state.active_branch = bid

    def run_triggers(self):
        for a in self.tree.evaluate(self.state, self.matcher):
            self.state.fired_triggers.append(a.trigger_id)
            self.state.pending_alerts.append(a)

    def bots_to_my_turn(self):
        lines = []
        while (not self.state.is_complete()) and not self.state.is_my_turn():
            team = self.state.on_the_clock()
            p = bot_choice(self.state, team, self.rng, self.temperament)
            pick = self.state.apply_pick(p)
            lines.append("%s %s" % (fmt_pick(pick.overall, self.state.teams),
                                    p.surname()))
            self.ensure_branch()
            self.run_triggers()
        if lines:
            print(self.c.dim("  bots: " + "  ".join(lines)))
        save_state.save(self.state)

    def show_clock(self):
        self.ensure_branch()
        alerts = list(self.state.pending_alerts)
        self.state.pending_alerts = []
        print(on_clock_block(self.state, self.tree, alerts,
                             color=self.c.on, intel=self.intel,
                             matcher=self.matcher))

    def my_pick(self, text):
        result = ingest_text(text, self.state, self.matcher)
        if not result.applied:
            if result.duplicates:
                for pl in result.duplicates:
                    pk = self.state.drafted.get(pl.key)
                    where = (" at %s by Team %d" % (fmt_pick(pk.overall, self.state.teams),
                                                    pk.team)) if pk else ""
                    print(self.c.yellow("  %s is already drafted%s" % (pl.name, where)))
            else:
                print("  no match for '%s' - try adding position or team" % text)
            return False
        pick, pl = result.applied[0]
        for w in result.warnings:
            print(self.c.yellow("  ! " + w))
        print(self.c.green("  YOU >> %-6s %s"
                           % (fmt_pick(pick.overall, self.state.teams), pl.label())))
        roster = self.state.my_roster()
        print(self.c.bold("  my roster (%d): %s" % (len(roster), ", ".join(
            "%s(%s)" % (p.surname(), p.pos) for p in roster))))
        self.ensure_branch()
        self.run_triggers()
        save_state.save(self.state)
        return True

    def rewind(self):
        removed_mine = False
        guard = 0
        while self.state.picks and guard < 40:
            guard += 1
            pick = self.state.undo_last()
            if pick and pick.team == self.state.my_slot:
                removed_mine = True
            if removed_mine and self.state.is_my_turn():
                break
        save_state.save(self.state)
        print(self.c.yellow("  rewound to your pick %d"
                            % self.state.current_pick()))

    def finish(self):
        print(self.c.green("\n  PRACTICE DRAFT COMPLETE - your roster:"))
        for pk in sorted((p for p in self.state.picks.values()
                          if p.team == self.state.my_slot),
                         key=lambda x: x.overall):
            pl = self.state.by_key[pk.player_key]
            print("   %-6s %s" % (fmt_pick(pk.overall, self.state.teams),
                                  pl.label()))
        counts = self.state.pos_counts(self.state.my_slot)
        print("   mix: " + "  ".join("%s x%d" % (p, n)
                                     for p, n in counts.items() if n))
        print("\n  run ./practice.sh again for a different draft.")

    # -- main loop -----------------------------------------------------------
    def loop(self):
        while True:
            self.bots_to_my_turn()
            if self.state.is_complete():
                self.finish()
                return
            self.show_clock()

            while self.state.is_my_turn():
                try:
                    text = input("\n[%s YOUR PICK] > " % fmt_pick(
                        self.state.current_pick(), self.state.teams)).strip()
                except EOFError:
                    print("\n  practice saved - resume with ./practice.sh --resume")
                    return
                if not text:
                    continue
                cmd = text.split()[0].lower()
                arg = text[len(cmd):].strip()
                if cmd in ("quit", "exit", "q"):
                    print("  practice saved - resume with ./practice.sh --resume")
                    return
                elif cmd in ("help", "?", "h"):
                    print(HELP)
                elif cmd == "me":
                    self.show_clock()
                elif cmd in ("plan", "notes", "brief"):
                    print(strategy_brief(self.state, self.tree, self.intel,
                                         color=self.c.on))
                elif cmd == "board":
                    print(board_text(self.state, arg.upper() if arg else None,
                                     18, self.c.on))
                elif cmd == "roster":
                    for pk in sorted((p for p in self.state.picks.values()
                                      if p.team == self.state.my_slot),
                                     key=lambda x: x.overall):
                        pl = self.state.by_key[pk.player_key]
                        print("   %-6s %s" % (
                            fmt_pick(pk.overall, self.state.teams), pl.label()))
                elif cmd == "undo":
                    self.rewind()
                    self.show_clock()
                elif cmd == "fast":
                    from engine.recommend import recommend
                    recs = recommend(self.state, self.tree, top_n=1,
                                     intel=self.intel)
                    if recs:
                        self.my_pick(recs[0].player.name)
                else:
                    self.my_pick(text)


def main():
    ap = argparse.ArgumentParser(description="Practice mock draft")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    try:
        Practice(resume=args.resume).loop()
    except KeyboardInterrupt:
        print("\n  practice saved - resume with ./practice.sh --resume")


if __name__ == "__main__":
    main()
