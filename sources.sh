#!/bin/bash
# Model Settings - the local panel for data/sources.yaml: your inputs, your
# weights, your formula. Enable/disable model inputs, drag weight sliders
# (live share readout), bulk toggle, add a source, paste creator content,
# and fetch-now with honest inline errors. Serves on 127.0.0.1 ONLY and
# writes nothing but the source registry, data/cache/, and the
# creator-calls paste store.
#   ./sources.sh              -> port 8787 (falls back if taken), opens browser
#   ./sources.sh --port 9000  -> extra flags pass through to engine.sources_ui
cd "$(dirname "$0")"

echo "Model Settings - your inputs, your weights, your formula"
exec .venv/bin/python -m engine.sources_ui "$@"
