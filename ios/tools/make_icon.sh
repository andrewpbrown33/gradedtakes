#!/bin/zsh
# Rebuild the App Store icon from design/icon.svg. Run after any change to
# the mark; nothing else in the app needs regenerating.
#
#   ios/tools/make_icon.sh
#
# How: the SVG is 512x512, so a copy with width/height rewritten to 1024 is
# rasterised natively at 1024 by `sips` (ships with macOS, reads SVG via
# libxml2 - keep the SVG valid XML, no "--" inside comments). sips writes
# RGBA; strip_alpha.py rewrites it as RGB because App Store Connect rejects
# a large app icon with an alpha channel even when every pixel is opaque.
# Xcode derives every other icon size from this one file at build time.
set -euo pipefail
HERE="${0:A:h}"
ROOT="$HERE/../.."
SRC="$ROOT/design/icon.svg"
OUT="$ROOT/ios/GradedTakes/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sed 's/width="512" height="512"/width="1024" height="1024"/' "$SRC" > "$TMP/icon-1024.svg"
grep -q 'width="1024" height="1024"' "$TMP/icon-1024.svg" || { echo "icon.svg no longer declares width=\"512\" height=\"512\" - update this script" >&2; exit 1; }
sips -s format png "$TMP/icon-1024.svg" --out "$TMP/rgba.png" >/dev/null
python3 "$HERE/strip_alpha.py" "$TMP/rgba.png" "$OUT"
sips -g pixelWidth -g pixelHeight -g hasAlpha "$OUT"
