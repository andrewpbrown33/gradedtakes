#!/bin/bash
# THE BOARD - one page per league: my roster matrix (every player x every
# enabled source), the divergence panel (where the room disagrees), waiver
# adds and named trade targets in the same matrix shape, and the league view
# with every other team's roster and shape. Opens in your browser when run
# by hand.
#   ./board.sh                    -> espn-1, current NFL week
#   ./board.sh yahoo-main         -> named league, current week
#   ./board.sh espn-1 3           -> named league, week 3
#   ./board.sh espn-1 3 --force   -> extra flags pass through to engine.board
#
# The board's scoreboard links to sources.html (The Receipts - the full
# per-source record). That page is refreshed here after every board render
# so the link never dangles; ./sources_page.sh regenerates it on its own.
cd "$(dirname "$0")"

league="${LEAGUE:-espn-1}"
week=()
if [ $# -ge 1 ] && [ "${1#-}" = "$1" ]; then league="$1"; shift; fi
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

# Warm the shared feed caches first (same warm path the draft CLIs and
# season.sh use) so a cold run never stalls mid-render. Instant when caches
# are fresh; a warm failure never blocks the board, whose sections degrade
# honestly on their own.
echo "warming data caches..."
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
  2>/dev/null || true

out="$(.venv/bin/python -m engine.board --league "$league" "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.board prints the written path as its LAST stdout line by contract.
page="$(printf '%s\n' "$out" | tail -n 1)"

# Refresh The Receipts (sources.html) beside the board, on the same league
# basis and week. Read-only like the board; a failure here never blocks
# the board, it just says so.
.venv/bin/python -m engine.sources_page --league "$league" "${week[@]}" \
  >/dev/null 2>&1 || echo "note: sources.html not refreshed - run ./sources_page.sh"

if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
