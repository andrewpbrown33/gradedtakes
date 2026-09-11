#!/bin/zsh
# Regenerate ios/GradedTakes.xcodeproj from ios/project.yml with the vendored
# XcodeGen. Run this after editing project.yml (or after adding Swift files
# and Xcode does not see them). Safe to run any time; it only rewrites the
# .xcodeproj and the two generated Info.plist files.
set -euo pipefail
HERE="${0:A:h}"                      # this script's directory (ios/), resolved
XCODEGEN="$HERE/../tools/xcodegen/xcodegen/bin/xcodegen"
if [[ ! -x "$XCODEGEN" ]]; then
  echo "xcodegen is not downloaded yet - run  tools/xcodegen/get.sh  first" >&2
  exit 1
fi
cd "$HERE"
"$XCODEGEN" generate --spec project.yml --use-cache "$@"
echo
echo "Open it:  open \"$HERE/GradedTakes.xcodeproj\""
