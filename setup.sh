#!/bin/bash
# One-time setup. Run once, then use ./start.sh on draft night.
set -e
cd "$(dirname "$0")"

echo "Setting up Graded Takes..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "  created .venv"
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "  installed dependencies"

if [ ! -f data/rankings.csv ]; then
  .venv/bin/python engine/adp.py
fi

echo ""
echo "Ready. Start the war room with:"
echo "  ./start.sh"
echo ""
echo "Run the self-test any time with:"
echo "  .venv/bin/python tests/mock_draft.py"
