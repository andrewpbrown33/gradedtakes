#!/bin/bash
# Start the war room. Draft night: just run ./start.sh
# To restart mid-draft without losing anything: ./start.sh --resume
cd "$(dirname "$0")"
exec .venv/bin/python warroom.py --league "${LEAGUE:-yahoo-main}" "$@"
