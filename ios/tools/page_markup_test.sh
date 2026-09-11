#!/bin/zsh
# Fixture test for PageMarkup.stamp - the <html data-app="ios" data-theme=...>
# injection the scheme handler applies to every page it serves.
#
# Needs only the command-line Swift compiler (xcode-select --install is
# enough; no Xcode project, no simulator). Compiles the pure function in
# ios/GradedTakes/Web/PageMarkup.swift together with the fixtures in
# ios/tools/page_markup_test/main.swift, runs the binary, and exits with its
# status: 0 and "CHECKS PASSED" when every fixture matches.
set -euo pipefail
HERE="${0:A:h}"                       # ios/tools
IOS="$HERE/.."
OUT="$(mktemp -d "${TMPDIR:-/tmp}/page_markup_test.XXXXXX")"
trap 'rm -rf "$OUT"' EXIT

xcrun swiftc -swift-version 6 -O \
  "$IOS/GradedTakes/Web/PageMarkup.swift" \
  "$HERE/page_markup_test/main.swift" \
  -o "$OUT/page_markup_test"

"$OUT/page_markup_test"
