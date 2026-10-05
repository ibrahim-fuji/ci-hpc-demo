"""Validation helpers for heat1d CSV output (standard library only).

Command line:
    check_results.py analytic RESULT.csv --alpha 1.0 --t 0.1 --tol 1e-4
    check_results.py compare A.csv B.csv --tol 1e-10

Exit status: 0 = within tolerance, 1 = tolerance exceeded, 2 = unreadable input.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections.abc import Iterable
from pathlib import Path


def parse_csv(lines: Iterable[str]) -> tuple[list[float], list[float]]:
    """Parse the 'x,u' CSV produced by heat1d and return (xs, us)."""
    reader = csv.reader(lines)
    header = next(reader, None)
    if header != ["x", "u"]:
        raise ValueError(f"unexpected CSV header: {header!r}")
    xs: list[float] = []
    us: list[float] = []
    for row in reader:
        if len(row) != 2:
            raise ValueError(f"malformed CSV row: {row!r}")
        xs.append(float(row[0]))
        us.append(float(row[1]))
    if not xs:
        raise ValueError("CSV contains no data")
    return xs, us


def read_csv(path: str | Path) -> tuple[list[float], list[float]]:
    with Path(path).open(newline="") as handle:
        return parse_csv(handle)


def analytic(x: float, alpha: float, t: float) -> float:
    """Exact solution of u_t = alpha u_xx with u(x,0) = sin(pi x), u(0)=u(1)=0."""
    return math.exp(-alpha * math.pi**2 * t) * math.sin(math.pi * x)


def max_error_vs_analytic(xs: list[float], us: list[float], alpha: float, t: float) -> float:
    return max(abs(u - analytic(x, alpha, t)) for x, u in zip(xs, us, strict=True))


def max_abs_diff(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} != {len(b)}")
    return max(abs(p - q) for p, q in zip(a, b, strict=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_an = sub.add_parser("analytic", help="compare a result with the exact solution")
    p_an.add_argument("csv")
    p_an.add_argument("--alpha", type=float, required=True)
    p_an.add_argument("--t", type=float, required=True)
    p_an.add_argument("--tol", type=float, required=True)

    p_cmp = sub.add_parser("compare", help="compare two result files")
    p_cmp.add_argument("a")
    p_cmp.add_argument("b")
    p_cmp.add_argument("--tol", type=float, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "analytic":
            xs, us = read_csv(args.csv)
            err = max_error_vs_analytic(xs, us, args.alpha, args.t)
        else:
            _, ua = read_csv(args.a)
            _, ub = read_csv(args.b)
            err = max_abs_diff(ua, ub)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    status = "OK" if err <= args.tol else "FAIL"
    print(f"{status}: max error = {err:.3e} (tolerance {args.tol:.1e})")
    return 0 if err <= args.tol else 1


if __name__ == "__main__":
    sys.exit(main())
