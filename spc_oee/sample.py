"""Deterministic synthetic data for demos and tests (no real data involved).

Measurements: 30 subgroups of n = 5, nominal 10.00 mm, sigma 0.04 mm, with
  * a spike of +0.18 mm on the mean of subgroup 12, and
  * a sustained shift of +1.5 sigma-of-the-mean (1.5 * 0.04 / sqrt(5)) from
    subgroup 22 onward,
so the Xbar chart shows rule violations. Spec limits: LSL 9.85, USL 10.15.

Production: 7 days x 2 shifts, 480 planned min, 20-90 min downtime, ideal
cycle 0.5 min/unit.
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass

from .oee import ProductionRecord

NOMINAL = 10.00
SIGMA = 0.04
SUBGROUP_SIZE = 5
N_SUBGROUPS = 30
SPIKE_SUBGROUP = 12          # 1-based label
SPIKE_SIZE = 0.18
SHIFT_START_SUBGROUP = 22    # 1-based label
SHIFT_SIGMAS_OF_MEAN = 1.5
DEFAULT_LSL = 9.85
DEFAULT_USL = 10.15

MEASUREMENTS_FILE = "sample_measurements.csv"
PRODUCTION_FILE = "sample_production.csv"
REPORT_FILE = "sample_report.html"


@dataclass
class SampleData:
    measurements: list      # [(subgroup_label, value), ...]
    production: list        # [ProductionRecord, ...]
    lsl: float = DEFAULT_LSL
    usl: float = DEFAULT_USL


def _build_measurements(rng: random.Random) -> list:
    shift = SHIFT_SIGMAS_OF_MEAN * SIGMA / math.sqrt(SUBGROUP_SIZE)
    meas = []
    for s in range(1, N_SUBGROUPS + 1):
        offset = 0.0
        if s == SPIKE_SUBGROUP:
            offset += SPIKE_SIZE
        if s >= SHIFT_START_SUBGROUP:
            offset += shift
        for _ in range(SUBGROUP_SIZE):
            meas.append((str(s), round(rng.gauss(NOMINAL, SIGMA) + offset, 4)))
    return meas


def _shows_patterns(meas: list) -> bool:
    """True if the spike fires R1 at its subgroup and the shift fires R4."""
    from .spc import analyse  # local import keeps module import light

    groups = [[v for _, v in meas[i:i + SUBGROUP_SIZE]]
              for i in range(0, len(meas), SUBGROUP_SIZE)]
    res = analyse(groups)
    r1 = any(v.rule == "R1" and v.index == SPIKE_SUBGROUP - 1
             for v in res.location_violations)
    r4 = any(v.rule == "R4" and v.index >= SHIFT_START_SUBGROUP - 1
             for v in res.location_violations)
    return r1 and r4


def _measurements_showing_patterns(rng: random.Random) -> list:
    """Draw noise from the seeded generator until the injected spike and shift
    are both detected. Random noise alone can hide a 1.5-sigma shift because
    the spike drags the Phase I centre line upward, so the draw is repeated
    (deterministically, from the same seeded stream) until the demo is
    illustrative. Gives up after 500 draws and returns the last one."""
    meas = _build_measurements(rng)
    for _ in range(500):
        if _shows_patterns(meas):
            break
        meas = _build_measurements(rng)
    return meas


def generate_sample(seed: int = 42) -> SampleData:
    """Generate the demo data set. Same seed gives identical output."""
    rng = random.Random(seed)
    meas = _measurements_showing_patterns(rng)

    prod = []
    for day in range(1, 8):
        for shift_name in ("Early", "Late"):
            downtime = rng.randint(20, 90)
            run = 480 - downtime
            max_units = run / 0.5
            total = int(max_units * rng.uniform(0.78, 0.88))
            good = int(total * rng.uniform(0.92, 0.97))
            prod.append(ProductionRecord(f"Day{day}-{shift_name}", 480, downtime,
                                         0.5, total, good))
    return SampleData(measurements=meas, production=prod)


def write_sample_csvs(folder: str, seed: int = 42):
    """Write the sample CSVs into ``folder`` (created if needed).

    Returns (measurements_path, production_path, SampleData).
    """
    data = generate_sample(seed)
    os.makedirs(folder, exist_ok=True)
    mpath = os.path.join(folder, MEASUREMENTS_FILE)
    ppath = os.path.join(folder, PRODUCTION_FILE)
    with open(mpath, "w", newline="", encoding="utf-8") as fh:
        fh.write("subgroup,value\n")
        for label, v in data.measurements:
            fh.write(f"{label},{v:.4f}\n")
    with open(ppath, "w", newline="", encoding="utf-8") as fh:
        fh.write("period,planned_time_min,downtime_min,ideal_cycle_time_min,"
                 "total_count,good_count\n")
        for r in data.production:
            fh.write(f"{r.period},{r.planned_time_min:g},{r.downtime_min:g},"
                     f"{r.ideal_cycle_time_min:g},{r.total_count},{r.good_count}\n")
    return mpath, ppath, data
