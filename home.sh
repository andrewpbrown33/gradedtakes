#!/bin/bash
# THE LANDING PAGE - every league, every roster, the week's game windows, and
# the handful of things that need you before lock, each with a link to the
# host page where you fix it. The full breakdown is one tap away on each
# league's board. Opens in your browser when run by hand. Read-only: the
# %owned baseline is never advanced by this page.
#   ./home.sh                -> current NFL week, every league in leagues/
#   ./home.sh 3              -> week 3
#   ./home.sh 3 --force      -> extra flags pass through to engine.home
#   ./home.sh --league espn-1
#   ./home.sh --skip-waivers -> faster: the waiver wire is not read
cd "$(dirname "$0")"

week=()
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

# Warm the shared feed caches first, exactly as board.sh does, so a cold run
# never stalls mid-render. Instant when caches are fresh; a warm failure never
# blocks the page, whose sections degrade honestly on their own.
echo "warming data caches..."
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
  2>/dev/null || true

out="$(.venv/bin/python -m engine.home "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.home prints the written path as its LAST stdout line by contract.
page="$(printf '%s\n' "$out" | tail -n 1)"
if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
