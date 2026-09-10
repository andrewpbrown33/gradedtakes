#!/bin/bash
# One-shot ESPN draft prep. Run with the league's REAL numbers:
#   ./prep_espn.sh <teams> <scoring> [slot] [rounds]
#   ./prep_espn.sh 12 half-ppr 7 16
# scoring: ppr | half-ppr | standard
# Re-run any time settings change - every step overwrites cleanly.
set -e
cd "$(dirname "$0")"
TEAMS="${1:?usage: ./prep_espn.sh <teams> <ppr|half-ppr|standard> [slot] [rounds]}"
SCORING="${2:?scoring required: ppr | half-ppr | standard}"
SLOT="${3:-}"
ROUNDS="${4:-16}"

echo "== seeding ADP for ${TEAMS}-team ${SCORING} =="
.venv/bin/python - "$TEAMS" "$SCORING" <<'PY'
import sys
from engine.adp import seed_rankings_csv
n = seed_rankings_csv("data/rankings-espn.csv", scoring=sys.argv[2], teams=int(sys.argv[1]))
print("  %s players seeded" % n)
PY

echo "== projections =="
.venv/bin/python - "$SCORING" <<'PY'
import sys
from engine.projections import apply_to_csv
label = {"ppr": "ppr", "half-ppr": "half", "standard": "std"}[sys.argv[1]]
print("  %s rows filled" % apply_to_csv("data/rankings-espn.csv", scoring=label))
PY

echo "== tiers =="
.venv/bin/python - "$SCORING" <<'PY'
import sys
from engine.tiers import apply_to_csv
s = sys.argv[1]
if s == "standard":
    print("  no Chen feed for standard scoring - ADP-gap tiers stand")
else:
    print("  %s rows tiered" % apply_to_csv("data/rankings-espn.csv", scoring=s))
PY

echo "== consensus (ECR - full PPR feed, applied only when scoring matches) =="
.venv/bin/python - "$SCORING" <<'PY'
import sys
if sys.argv[1] == "ppr":
    from engine.nflverse import apply_ecr_to_csv
    print("  %s rows" % apply_ecr_to_csv("data/rankings-espn.csv"))
else:
    print("  skipped: ECR feed is full-PPR consensus; blending it into %s"
          " scoring would import the wrong market" % sys.argv[1])
PY

echo "== updating leagues/espn-1.yaml =="
.venv/bin/python - "$TEAMS" "$SCORING" "$SLOT" "$ROUNDS" <<'PY'
import sys, yaml
teams, scoring, slot, rounds = int(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
with open("leagues/espn-1.yaml") as fh:
    cfg = yaml.safe_load(fh)
cfg["teams"] = teams
cfg["rounds"] = rounds
cfg.setdefault("scoring", {})["reception"] = {"ppr": 1, "half-ppr": 0.5, "standard": 0}[scoring]
if slot:
    cfg["my_slot"] = int(slot)
cfg["rankings_csv"] = "data/rankings-espn.csv"
with open("leagues/espn-1.yaml", "w") as fh:
    yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)
print("  teams=%s scoring=%s slot=%s rounds=%s" % (teams, scoring, slot or "(set in room)", rounds))
PY

echo "== warming caches =="
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" || true

echo
echo "READY. Draft with auto-ingest:   ./espn.sh draft ${SLOT:+--slot $SLOT}"
echo "   or manual paste fallback:     LEAGUE=espn-1 ./start.sh"
