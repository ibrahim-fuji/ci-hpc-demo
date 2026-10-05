#!/usr/bin/env bash
# Regenerate the numerical regression reference used by tests/test_heat.py.
# Only do this when a numerical change is intended, and review the diff before committing!
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

bin="${HEAT1D_BIN:-build/heat1d}"
if [[ ! -x "$bin" ]]; then
    echo "error: binary '$bin' not found; run 'make build' first" >&2
    exit 1
fi

mkdir -p tests/reference
# Keep these arguments in sync with REFERENCE_ARGS in tests/test_heat.py
OMP_NUM_THREADS=1 "$bin" --nx 51 --tmax 0.05 --out tests/reference/heat_nx51.csv
echo "wrote tests/reference/heat_nx51.csv"
