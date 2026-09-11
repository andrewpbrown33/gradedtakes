#!/bin/bash
# THE PUBLISH PIPELINE - one private copy of Graded Takes per person in
# users.yaml. Renders THEIR leagues, assembles public/<token>/, asserts that
# nothing in it belongs to anybody else, and publishes. If any assertion
# fails, nothing is published for ANYONE and the exit code is 2.
#
#   ./publish.sh                        -> everyone, current NFL week
#   ./publish.sh 7                      -> everyone, week 7
#   ./publish.sh --dry-run              -> render, assert, print the manifest,
#                                          write nothing
#   ./publish.sh --plan                 -> print each person's allowlist, run
#                                          no renderer at all (instant)
#   ./publish.sh --person "Sam Rivera"  -> just that person
#   ./publish.sh --prune                -> also delete published directories
#                                          that belong to nobody
#   ./publish.sh check                  -> the CONTENT heartbeat: exits
#                                          non-zero if a publish is stale
#   ./publish.sh token                  -> print one unguessable token
#   ./publish.sh who                    -> who is configured (no tokens shown)
#
# Read the manifest before you trust a first run. Every line of it is a file
# that is about to become reachable on the internet.
#
# Full walkthrough, including Cloudflare Access and launchd: docs/DEPLOY.md
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "no .venv/bin/python - run ./setup.sh first" >&2
  exit 1
fi

cmd=publish
case "${1:-}" in
  check|check-heartbeat) cmd=check-heartbeat; shift;;
  token|new-token)       cmd=new-token; shift;;
  who|list)              cmd=list; shift;;
esac

# A bare leading number is the week, exactly as board.sh and season.sh read it.
week=()
case "${1:-}" in
  ''|*[!0-9]*) ;;
  *) week=(--week "$1"); shift;;
esac

# Warm the shared feed caches first, the same warm path every renderer's
# wrapper uses, so a cold overnight run never stalls mid-render. Instant when
# caches are fresh; a warm failure never blocks the run - the pages degrade
# honestly on their own and the heartbeat records that they did.
skip_warm=0
for a in "$@"; do case "$a" in --plan) skip_warm=1;; esac; done
if [ "$cmd" = "publish" ] && [ $skip_warm -eq 0 ]; then
  echo "warming data caches..."
  .venv/bin/python -c "from engine.recommend import warm_caches; warm_caches()" \
    2>/dev/null || true
fi

.venv/bin/python publish.py "$cmd" "${week[@]}" "$@"
code=$?

# 0 = published and clean. 1 = published but incomplete, or the heartbeat is
# stale - something needs a human. 2 = REFUSED, nothing was published.
case $code in
  0) ;;
  1) echo "" >&2
     echo "exit 1: the run finished but something needs you - read the lines" >&2
     echo "above. Nothing here is a crash; it is the pipeline refusing to be" >&2
     echo "quietly wrong." >&2;;
  2) echo "" >&2
     echo "exit 2: REFUSED. Nothing was published, for anyone. The reason is" >&2
     echo "printed above in full." >&2;;
esac
exit $code
