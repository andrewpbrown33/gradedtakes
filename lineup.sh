#!/bin/bash
# THE LINEUP BUILDER - one page per league: every starting slot in your
# league's own order with the starter, his flags, game and kickoff, his
# projection, the model's verdict chip, and the matchup meter; a challenger
# line under any slot a bench player genuinely contests; the hold-vs-stream
# read on K and D/ST; the bench (competitors first, the rest behind an
# expander); and a footer strip with the projected total, every proposed
# swap's delta, and the "Set lineup on ESPN/Yahoo" deep link. Opens in your
# browser when run by hand. Read-only: never advances the %owned baseline,
# never writes the streaming log.
#   ./lineup.sh                    -> espn-1, current NFL week
#   ./lineup.sh yahoo-main         -> named league, current week
#   ./lineup.sh espn-1 3           -> named league, week 3
#   ./lineup.sh espn-1 3 --force   -> extra flags pass through to engine.lineup_page
cd "$(dirname "$0")"

league="${LEAGUE:-espn-1}"
week=()
if [ $# -ge 1 ] && [ "${1#-}" = "$1" ]; then league="$1"; shift; fi
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

# Warm the shared feed caches first (same warm path board.sh and home.sh
# use) so a cold run never stalls mid-render. Instant when caches are
# fresh; a warm failure never blocks the page, whose rows degrade honestly
# on their own.
echo "warming data caches..."
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
  2>/dev/null || true

out="$(.venv/bin/python -m engine.lineup_page --league "$league" "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.lineup_page prints the written path as its LAST stdout line by contract.
page="$(printf '%s\n' "$out" | tail -n 1)"
if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
