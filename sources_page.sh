#!/bin/bash
# THE RECEIPTS - one card per source: weight, form, the decay-blended hit
# rate with what it is made of, sample, streak, a weekly sparkline, the
# per-position and start/sit splits, and the archive phase-out schedule.
# Writes sources.html to the project root and opens it when run by hand.
#
# NOT the same thing as ./sources.sh - that is Model Settings, the local
# panel that EDITS the registry (weights, on/off, paste). This page only
# READS: the registry, data/performance_history.jsonl and the ledger, and
# writes nothing but sources.html. ./board.sh refreshes this page after
# every board render too, because the board links here.
#   ./sources_page.sh                 -> current NFL week, espn-1 basis
#   ./sources_page.sh 3               -> week 3
#   ./sources_page.sh 3 --league yahoo-main   (grade by that league's
#                                              replacement level instead)
cd "$(dirname "$0")"

week=()
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

out="$(.venv/bin/python -m engine.sources_page "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.sources_page prints the written path as its LAST stdout line.
page="$(printf '%s\n' "$out" | tail -n 1)"
if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
