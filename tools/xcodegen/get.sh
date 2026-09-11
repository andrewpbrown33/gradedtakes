#!/bin/zsh
# Download the pinned XcodeGen release into tools/xcodegen/ (no Homebrew).
# The binary and zip are gitignored; this script is the record of which
# version the project was generated with. Re-run any time; it is idempotent.
#
#   tools/xcodegen/get.sh            # fetch 2.46.0, verify checksum, unzip
#   tools/xcodegen/xcodegen/bin/xcodegen --version
set -euo pipefail
VERSION="2.46.0"
SHA256="4d9e34b62172d645eed6457cac13fc222569974098ef4ee9c3368bedf0196806"
URL="https://github.com/yonaskolb/XcodeGen/releases/download/${VERSION}/xcodegen.zip"
HERE="${0:A:h}"
cd "$HERE"
if [[ -x xcodegen/bin/xcodegen ]] && [[ "$(xcodegen/bin/xcodegen --version)" == "Version: ${VERSION}" ]]; then
  echo "xcodegen ${VERSION} already present"; exit 0
fi
echo "downloading XcodeGen ${VERSION} ..."
curl -sS -L --fail -o xcodegen.zip "$URL"
echo "${SHA256}  xcodegen.zip" | shasum -a 256 -c -
rm -rf xcodegen
unzip -q -o xcodegen.zip
xattr -d com.apple.quarantine xcodegen/bin/xcodegen 2>/dev/null || true
xcodegen/bin/xcodegen --version
