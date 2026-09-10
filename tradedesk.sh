#!/bin/bash
# THE TRADE DESK - one page per league: every known roster as a column
# (starters over bench, my team first), the needs matrix (teams x positions,
# one depth meter per cell), ranked rival-aware trade targets with both
# valuations and both sides' pts/wk, waiver competition as stacks of rival
# names, and needs over time from the weekly snapshot in data/cache. Opens
# in your browser when run by hand.
#   ./tradedesk.sh                    -> espn-1, current NFL week
#   ./tradedesk.sh yahoo-main         -> named league, current week
#   ./tradedesk.sh espn-1 3           -> named league, week 3
#   ./tradedesk.sh espn-1 3 --force   -> extra flags pass through to engine.tradedesk
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
# fresh; a warm failure never blocks the desk, whose cards degrade honestly
# on their own.
echo "warming data caches..."
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
  2>/dev/null || true

out="$(.venv/bin/python -m engine.tradedesk --league "$league" "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.tradedesk prints the written path as its LAST stdout line by contract.
page="$(printf '%s\n' "$out" | tail -n 1)"
if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
