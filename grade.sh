#!/bin/bash
# Grade a draft (completed or in progress) from a save JSON.
#   ./grade.sh                                  -> latest save for $LEAGUE (default yahoo-main)
#   ./grade.sh saves/yahoo-main-20260829.json   -> that specific save
#   ./grade.sh --league espn-1                  -> latest save for another league
cd "$(dirname "$0")"
exec .venv/bin/python -m engine.grader ${LEAGUE:+--league "$LEAGUE"} "$@"
