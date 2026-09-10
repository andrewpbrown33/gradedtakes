#!/bin/bash
# Tuesday digest - the week ahead as one self-contained HTML page: waiver
# shortlist + FAAB bands, lineup verdicts, DEF/K streaming plan, trade
# constructs, and injury flags. Opens in your browser when run by hand.
#   ./season.sh                    -> yahoo-main, current NFL week
#   ./season.sh yahoo-main         -> named league, current week
#   ./season.sh yahoo-main 1       -> named league, week 1
#   ./season.sh espn-1 3 --force   -> extra flags pass through to engine.digest
cd "$(dirname "$0")"

league="${LEAGUE:-yahoo-main}"
week=()
if [ $# -ge 1 ] && [ "${1#-}" = "$1" ]; then league="$1"; shift; fi
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

# Warm the shared feed caches first (the same warm path the draft CLIs run at
# startup - engine.recommend.warm_caches) so a cold morning run never stalls
# mid-render. Instant when caches are fresh; a warm failure never blocks the
# digest, whose sections degrade honestly on their own.
echo "warming data caches..."
.venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
  2>/dev/null || true

out="$(.venv/bin/python -m engine.digest --league "$league" "${week[@]}" "$@")"
code=$?
[ -n "$out" ] && printf '%s\n' "$out"
[ $code -ne 0 ] && exit $code

# engine.digest prints the written path as its LAST stdout line by contract.
page="$(printf '%s\n' "$out" | tail -n 1)"
if [ -t 1 ] && [ -f "$page" ] && command -v open >/dev/null 2>&1; then
  open "$page"
fi
