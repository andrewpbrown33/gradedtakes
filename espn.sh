#!/bin/bash
# ESPN connection helper.
#   ./espn.sh check    verify cookies, print league settings and teams
#   ./espn.sh draft    live draft: auto-pulls picks, prints your on-clock block
cd "$(dirname "$0")"
exec .venv/bin/python -m engine.espn_cli "$@"
