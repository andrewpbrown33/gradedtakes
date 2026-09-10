#!/bin/bash
# Yahoo connection helper.
#   ./yahoo.sh check    verify the connection and print your league + roster
cd "$(dirname "$0")"
exec .venv/bin/python -m engine.yahoo_cli "$@"
