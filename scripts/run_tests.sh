#!/usr/bin/env bash
# Run the test-suite against a compiled binary (default: build/heat1d, or $HEAT1D_BIN).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

bin="${HEAT1D_BIN:-build/heat1d}"
if [[ ! -x "$bin" ]]; then
    echo "error: binary '$bin' not found; run 'make build' first" >&2
    exit 1
fi

HEAT1D_BIN="$(cd "$(dirname "$bin")" && pwd)/$(basename "$bin")" # no realpath on older macOS
export HEAT1D_BIN
echo "Testing $HEAT1D_BIN (OMP_NUM_THREADS=${OMP_NUM_THREADS:-unset})"
exec python3 -m pytest "$@"
