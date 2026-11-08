"""Command-line interface.

    python -m spc_oee MEAS.csv [PROD.csv] [--lsl X] [--usl X] [--out report.html]
    python -m spc_oee --demo [--out-dir examples]

Exit code 0 on success, 2 on bad input (one-line message, no traceback).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Optional, Sequence

from . import __version__
from .io import load_measurements, load_production
from .oee import compute_oee
from .report import build_report
from .sample import MEASUREMENTS_FILE, PRODUCTION_FILE, REPORT_FILE, write_sample_csvs
from .spc import analyse


def _f(v: Optional[float], digits: int = 3) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _finite(text: str) -> float:
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: '{text}'") from None
    if not math.isfinite(v):
        raise argparse.ArgumentTypeError(f"must be finite: '{text}'")
    return v


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spc-oee",
        description="Control charts, Cp/Cpk and OEE from CSV files.")
    p.add_argument("measurements", nargs="?",
                   help="measurements CSV (header: subgroup,value)")
    p.add_argument("production", nargs="?",
                   help="production-times CSV (optional)")
    p.add_argument("--lsl", type=_finite, help="lower specification limit")
    p.add_argument("--usl", type=_finite, help="upper specification limit")
    p.add_argument("--out", help="HTML report path (default: report.html, "
                   "or <out-dir>/sample_report.html with --demo)")
    p.add_argument("--title", default="SPC and OEE report", help="report title")
    p.add_argument("--demo", action="store_true",
                   help="generate synthetic sample CSVs and a report")
    p.add_argument("--out-dir", default="examples",
                   help="folder for --demo output (default: examples)")
    p.add_argument("--version", action="version", version=f"spc-oee {__version__}")
    return p


def summarise(spc, oee) -> str:
    lines = []
    kind = "Xbar-R" if spc.chart_type == "xbar-r" else "I-MR"
    lines.append(f"{kind} chart, {len(spc.labels)} subgroups, n = {spc.n}")
    lines.append(f"  location CL {_f(spc.location_cl, 4)}  UCL {_f(spc.location_ucl, 4)}  "
                 f"LCL {_f(spc.location_lcl, 4)}")
    lines.append(f"  spread   CL {_f(spc.spread_cl, 4)}  UCL {_f(spc.spread_ucl, 4)}  "
                 f"LCL {_f(spc.spread_lcl, 4)}")
    lines.append(f"  sigma within {_f(spc.sigma_within, 4)}, overall {_f(spc.sigma_overall, 4)}")
    if spc.capability:
        c = spc.capability
        lines.append(f"  Cp {_f(c.cp)}  Cpk {_f(c.cpk)}  Pp {_f(c.pp)}  Ppk {_f(c.ppk)}  "
                     f"PPM {_f(c.ppm_total, 0)} ({c.ppm_note})")
    flagged = spc.flagged_location_indices
    if flagged:
        names = ", ".join(spc.labels[i] for i in flagged)
        rules = ", ".join(sorted({v.rule for v in spc.location_violations}))
        lines.append(f"  Flagged location points (subgroup): {names}  [rules {rules}]")
    else:
        lines.append("  No location-chart rule violations")
    if spc.spread_violations:
        idx = [i + spc.spread_offset for i in spc.flagged_spread_indices]
        lines.append("  Flagged spread points (subgroup): "
                     + ", ".join(spc.labels[i] for i in idx))
    for w in spc.warnings:
        lines.append(f"  WARNING: {w}")
    if oee is not None:
        t = oee.total
        lines.append(f"OEE total: {_pct(t.oee)}  (A {_pct(t.availability)}, "
                     f"P {_pct(t.performance)}, Q {_pct(t.quality)}) over "
                     f"{len(oee.rows)} periods; reference {oee.world_class_reference:.0%}")
        for w in oee.warnings:
            lines.append(f"  WARNING: {w}")
    return "\n".join(lines)


def _run(args) -> int:
    if args.demo:
        mpath, ppath, data = write_sample_csvs(args.out_dir)
        out = args.out or os.path.join(args.out_dir, REPORT_FILE)
        lsl = args.lsl if args.lsl is not None else data.lsl
        usl = args.usl if args.usl is not None else data.usl
        title = args.title if args.title != "SPC and OEE report" else "Demo: synthetic SPC and OEE report"
    else:
        if not args.measurements:
            raise ValueError("a measurements CSV is required (or use --demo)")
        mpath, ppath = args.measurements, args.production
        out = args.out or "report.html"
        lsl, usl, title = args.lsl, args.usl, args.title

    labels, groups, _n = load_measurements(mpath)
    spc = analyse(groups, labels, lsl=lsl, usl=usl)
    oee = compute_oee(load_production(ppath)) if ppath else None

    meta = {"title": title, "lsl": lsl, "usl": usl, "measurements_file": mpath,
            "production_file": ppath, "version": __version__,
            "synthetic": bool(args.demo)}
    html = build_report(spc, oee, meta)
    folder = os.path.dirname(out)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(summarise(spc, oee))
    if args.demo:
        print(f"Wrote {mpath}\nWrote {ppath}")
    print(f"Report written to {out}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (ValueError, OSError) as exc:  # FileNotFoundError is an OSError
        print(f"spc-oee: error: {exc}", file=sys.stderr)
        return 2
