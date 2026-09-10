"""Contingency tree: branches, round plans, and pivot triggers.

The tree is authored before the draft. During the draft this module tracks
which branch we are on, whether we are on script, and evaluates triggers that
say the board has changed enough to pivot.
"""

import os
from typing import Dict, List, Optional

import yaml

from .models import norm_name, norm_pos


class Alert(object):
    LEVELS = {"info": 0, "warn": 1, "pivot": 2}

    def __init__(self, level: str, text: str, goto: Optional[str] = None,
                 trigger_id: str = "", auto: bool = False):
        self.level = level
        self.text = text
        self.goto = goto
        self.trigger_id = trigger_id
        self.auto = auto

    def __repr__(self):
        return "<Alert %s %s>" % (self.level, self.text)


class PlanRound(object):
    def __init__(self, data: Dict):
        rounds = data.get("rounds")
        if rounds:
            if isinstance(rounds, list) and len(rounds) == 2 and rounds[0] < rounds[1]:
                self.rounds = list(range(int(rounds[0]), int(rounds[1]) + 1))
            elif isinstance(rounds, list):
                self.rounds = [int(r) for r in rounds]
            else:
                self.rounds = [int(rounds)]
        else:
            self.rounds = [int(data.get("round", 0))]
        self.targets = list(data.get("targets", []) or [])
        self.prefer = [norm_pos(p) for p in (data.get("prefer", []) or [])]
        self.avoid = [norm_pos(p) for p in (data.get("avoid", []) or [])]
        self.reach_ok = bool(data.get("reach_ok", False))
        self.notes = data.get("notes", "") or ""
        self.target_keys = set()   # filled in by resolve_names

    def describe(self) -> str:
        bits = []
        if self.prefer:
            bits.append("prefer " + "/".join(self.prefer))
        if self.targets:
            bits.append("targets: " + ", ".join(self.targets[:4]))
        if self.avoid:
            bits.append("avoid " + "/".join(self.avoid))
        if self.reach_ok:
            bits.append("reach OK")
        return "; ".join(bits) if bits else "best available"


class Branch(object):
    def __init__(self, bid: str, data: Dict):
        self.id = bid
        self.name = data.get("name", bid)
        self.entry = data.get("entry", {}) or {}
        self.plan = [PlanRound(p) for p in (data.get("plan", []) or [])]
        self.pivots = list(data.get("pivots", []) or [])

    def plan_for(self, rnd: int) -> Optional[PlanRound]:
        for pr in self.plan:
            if rnd in pr.rounds:
                return pr
        return None


class StrategyTree(object):
    def __init__(self, data: Dict, path: str = ""):
        self.path = path
        self.meta = data.get("meta", {}) or {}
        self.name = self.meta.get("name", os.path.basename(path))
        self.default_branch = self.meta.get("default_branch")
        # Explicit tie-break order when several branches qualify at once.
        self.priority = [str(b) for b in (self.meta.get("branch_priority") or [])]
        self.do_not_draft = list(data.get("do_not_draft", []) or [])
        self.watch = list(data.get("watch", []) or [])
        self.branches = dict(
            (str(k), Branch(str(k), v))
            for k, v in (data.get("branches", {}) or {}).items())
        self.dnd_keys = {}       # player_key -> reason
        self.unresolved = []     # names that did not match the player pool

    @classmethod
    def load(cls, path: str) -> "StrategyTree":
        with open(path, "r") as fh:
            return cls(yaml.safe_load(fh) or {}, path)

    @classmethod
    def empty(cls) -> "StrategyTree":
        return cls({"meta": {"name": "(no strategy loaded)"}})

    # --- name resolution ---------------------------------------------------
    def resolve_names(self, matcher):
        """Bind every named player in the tree to the player pool."""
        def resolve(name):
            m = matcher.match(name)
            if m is None or m.score < 70:
                self.unresolved.append(name)
                return None
            return m.player

        for entry in self.do_not_draft:
            nm = entry.get("name") if isinstance(entry, dict) else str(entry)
            p = resolve(nm)
            if p:
                reason = entry.get("reason", "") if isinstance(entry, dict) else ""
                self.dnd_keys[p.key] = reason or "do-not-draft list"

        for branch in self.branches.values():
            for pr in branch.plan:
                for nm in pr.targets:
                    p = resolve(nm)
                    if p:
                        pr.target_keys.add(p.key)
            for cond in list(branch.entry.get("any_available", []) or []) + \
                    list(branch.entry.get("all_gone", []) or []):
                resolve(cond)

    def _keys_for(self, names, matcher) -> List[str]:
        out = []
        for nm in names or []:
            m = matcher.match(nm)
            if m:
                out.append(m.player.key)
        return out

    # --- branch selection --------------------------------------------------
    def qualifying_branches(self, state, matcher) -> List[str]:
        """Every branch whose entry conditions the board currently satisfies."""
        rnd = state.current_round()
        out = []
        for bid in sorted(self.branches.keys()):
            branch = self.branches[bid]
            entry = branch.entry or {}
            if not entry:
                continue
            if rnd != int(entry.get("round", 1)):
                continue
            any_av = self._keys_for(entry.get("any_available"), matcher)
            all_gone = self._keys_for(entry.get("all_gone"), matcher)
            ok = True
            if any_av:
                ok = ok and any(not state.is_drafted(k) for k in any_av)
            if all_gone:
                ok = ok and all(state.is_drafted(k) for k in all_gone)
            if ok and (any_av or all_gone):
                out.append(bid)
        return out

    def choose_branch(self, state, matcher) -> Optional[str]:
        """Pick the entry branch whose conditions the board satisfies.

        When several qualify - which is normal at pick 1.01, where an elite RB
        and an elite WR are both on the board - honor `meta.branch_priority`
        rather than falling back to alphabetical order. Sorting silently made
        "A" beat "B" and buried a real opening-round choice.
        """
        matches = self.qualifying_branches(state, matcher)
        if matches:
            for bid in self.priority:
                if bid in matches:
                    return bid
            return matches[0]
        return self.default_branch or (sorted(self.branches.keys())[0]
                                       if self.branches else None)

    def rival_branches(self, state, matcher) -> List[str]:
        """Other branches that also qualify right now, for surfacing a choice."""
        return [b for b in self.qualifying_branches(state, matcher)
                if b != state.active_branch]

    def active(self, state) -> Optional[Branch]:
        if state.active_branch and state.active_branch in self.branches:
            return self.branches[state.active_branch]
        return None

    def plan_now(self, state) -> Optional[PlanRound]:
        branch = self.active(state)
        if not branch:
            return None
        return branch.plan_for(state.current_round())

    # --- trigger evaluation ------------------------------------------------
    def evaluate(self, state, matcher) -> List[Alert]:
        """Run global watches plus the active branch's pivots."""
        alerts = []
        rules = [(w, None) for w in self.watch]
        branch = self.active(state)
        if branch:
            for i, pv in enumerate(branch.pivots):
                pv = dict(pv)
                pv.setdefault("id", "%s-pivot-%d" % (branch.id, i + 1))
                rules.append((pv, branch))

        for rule, owner in rules:
            rid = str(rule.get("id") or "rule-%d" % len(alerts))
            if rid in state.fired_triggers:
                continue
            cond = rule.get("when", {}) or {}
            if not self._test(cond, state, matcher, owner):
                continue
            then = rule.get("then", {}) or {}
            goto = then.get("goto")
            text = then.get("alert") or ("switch to branch %s" % goto if goto
                                         else "trigger fired: %s" % rid)
            level = "pivot" if goto else "warn"
            alerts.append(Alert(level, text, goto, rid,
                                bool(then.get("auto", False))))
        return alerts

    def _test(self, cond: Dict, state, matcher, branch) -> bool:
        ctype = (cond.get("type") or "").strip()

        if ctype == "position_gone":
            pos = norm_pos(cond.get("position", ""))
            need = int(cond.get("at_least", 1))
            by = int(cond.get("by_overall_pick", state.total_picks()))
            if state.current_pick() > by + 1:
                # Window has passed; only fire while still relevant.
                return False
            gone = sum(1 for k, pk in state.drafted.items()
                       if pk.overall <= by
                       and getattr(state.by_key.get(k), "pos", None) == pos)
            return gone >= need

        if ctype == "position_run":
            pos = norm_pos(cond.get("position", ""))
            window = int(cond.get("window", 5))
            need = int(cond.get("at_least", 3))
            recent = state.recent_picks(window)
            # Placeholder picks ('__skipped__') resolve to no player and add
            # nothing to a run.
            got = sum(1 for pk in recent
                      if getattr(state.by_key.get(pk.player_key), "pos", None) == pos)
            return got >= need

        if ctype == "targets_gone":
            rnd = int(cond.get("round", state.current_round()))
            if branch is None:
                return False
            pr = branch.plan_for(rnd)
            if not pr or not pr.target_keys:
                return False
            return all(state.is_drafted(k) for k in pr.target_keys)

        if ctype == "player_gone":
            keys = self._keys_for([cond.get("name")], matcher)
            return bool(keys) and all(state.is_drafted(k) for k in keys)

        if ctype == "players_gone":
            keys = self._keys_for(cond.get("names", []), matcher)
            need = int(cond.get("at_least", len(keys) or 1))
            return sum(1 for k in keys if state.is_drafted(k)) >= need

        if ctype == "tier_break":
            pos = norm_pos(cond.get("position", ""))
            tier = int(cond.get("tier", 1))
            at_most = int(cond.get("remaining_at_most", 1))
            left = [p for p in state.available(pos) if p.tier == tier]
            return len(left) <= at_most

        if ctype == "player_available":
            keys = self._keys_for([cond.get("name")], matcher)
            at_pick = cond.get("at_overall_pick")
            if at_pick is not None and state.current_pick() < int(at_pick):
                return False
            return bool(keys) and all(not state.is_drafted(k) for k in keys)

        return False

    # --- script adherence --------------------------------------------------
    def script_status(self, state) -> str:
        """Compare my roster so far against the active branch's plan."""
        branch = self.active(state)
        if not branch or not state.my_slot:
            return "no branch set"
        off = []
        for overall in sorted(pk.overall for pk in state.picks.values()
                              if pk.team == state.my_slot):
            rnd = (overall - 1) // state.teams + 1
            pr = branch.plan_for(rnd)
            if not pr:
                continue
            player = state.by_key.get(state.picks[overall].player_key)
            if player is None:
                # Placeholder pick ('__skipped__') - nothing to judge.
                continue
            if pr.target_keys and player.key in pr.target_keys:
                continue
            if pr.prefer and player.pos not in pr.prefer:
                off.append("R%d took %s (plan: %s)" % (rnd, player.pos,
                                                       "/".join(pr.prefer)))
        if not off:
            return "ON SCRIPT"
        return "OFF SCRIPT - " + "; ".join(off[-2:])
