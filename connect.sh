#!/bin/bash
# Platform connections - one place to hook up Sleeper, ESPN, and Yahoo.
#   ./connect.sh           interactive wizard: status board, then per-platform
#                          connect (Sleeper needs only a username; ESPN/Yahoo
#                          point at their SETUP docs until secrets exist)
#   ./connect.sh status    just print the status board and exit
cd "$(dirname "$0")"
exec .venv/bin/python -m engine.connections "$@"
