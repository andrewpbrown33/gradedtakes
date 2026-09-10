#!/bin/bash
# Practice mock draft against 9 bots - free, offline, your exact league.
# Fresh draft each run; ./practice.sh --resume continues the last one.
cd "$(dirname "$0")"
exec .venv/bin/python rehearse.py "$@"
