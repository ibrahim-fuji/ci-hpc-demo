"""Tests for the heat1d solver.

They exercise the compiled binary (build/heat1d, or $HEAT1D_BIN) as a black box, the way a
CI pipeline would, and compare floating-point results with explicit tolerances.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import check_results as cr
import pytest

ROOT = Path(__file__).resolve().parent.parent
BIN = Path(os.environ.get("HEAT1D_BIN", ROOT / "build" / "heat1d"))
REFERENCE = ROOT / "tests" / "reference" / "heat_nx51.csv"

# Keep in sync with scripts/make_reference.sh
REFERENCE_ARGS = ["--nx", "51", "--tmax", "0.05"]


def run(args: list[str], threads: int | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if threads is not None:
        env["OMP_NUM_THREADS"] = str(threads)
    return subprocess.run(
        [str(BIN), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


def solve(args: list[str], threads: int | None = None) -> tuple[list[float], list[float]]:
    result = run(args, threads)
    assert result.returncode == 0, result.stderr
    return cr.parse_csv(result.stdout.splitlines())


def error_vs_exact(nx: int) -> float:
    xs, us = solve(["--nx", str(nx), "--alpha", "1.0", "--tmax", "0.1"])
    return cr.max_error_vs_analytic(xs, us, alpha=1.0, t=0.1)


# --- numerical correctness ---------------------------------------------------------------


def test_accuracy_against_exact_solution():
    assert error_vs_exact(101) < 1e-4


def test_second_order_convergence():
    e21, e41, e81 = error_vs_exact(21), error_vs_exact(41), error_vs_exact(81)
    # halving dx (and dt ~ dx^2) should divide the error by ~4
    assert 3.5 < e21 / e41 < 4.5
    assert 3.5 < e41 / e81 < 4.5


def test_boundaries_stay_at_zero():
    _, us = solve(["--nx", "51"])
    assert us[0] == 0.0
    assert us[-1] == 0.0


def test_regression_against_reference():
    """Numerical non-regression: compare with a stored result, with a tolerance."""
    _, expected = cr.read_csv(REFERENCE)
    _, actual = solve(REFERENCE_ARGS, threads=1)
    assert cr.max_abs_diff(actual, expected) < 1e-10


# --- parallel behaviour ------------------------------------------------------------------


@pytest.mark.parametrize("threads", [2, 4])
def test_results_do_not_depend_on_thread_count(threads):
    _, serial = solve(["--nx", "401"], threads=1)
    _, parallel = solve(["--nx", "401"], threads=threads)
    assert cr.max_abs_diff(serial, parallel) < 1e-12


# --- robustness --------------------------------------------------------------------------


def test_unstable_time_step_is_rejected():
    result = run(["--nx", "101", "--dt", "1e-3"])  # limit is dx^2/2 = 5e-5
    assert result.returncode == 2
    assert "unstable" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["--nx", "2"],
        ["--nx", "abc"],
        ["--alpha", "-1"],
        ["--tmax", "0"],
        ["--bogus", "1"],
        ["--nx"],
    ],
)
def test_invalid_arguments_are_rejected(args):
    result = run(args)
    assert result.returncode == 1
    assert "heat1d:" in result.stderr


def test_help_exits_successfully():
    result = run(["--help"])
    assert result.returncode == 0
    assert "usage" in result.stdout


# --- the Python validation helpers ---------------------------------------------------------


def test_compare_detects_differences():
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
        a.write_text("x,u\n0,0\n1,1\n")
        b.write_text("x,u\n0,0\n1,1.5\n")
        assert cr.main(["compare", str(a), str(a), "--tol", "1e-12"]) == 0
        assert cr.main(["compare", str(a), str(b), "--tol", "1e-12"]) == 1


def test_malformed_csv_is_reported():
    with pytest.raises(ValueError, match="header"):
        cr.parse_csv(["a,b", "1,2"])
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.csv"
        bad.write_text("not a csv\n")
        assert cr.main(["analytic", str(bad), "--alpha", "1", "--t", "0.1", "--tol", "1"]) == 2
