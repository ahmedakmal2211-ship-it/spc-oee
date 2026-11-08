"""Overall Equipment Effectiveness (OEE) and time-loss breakdown.

Per period (shift/day):
    run_time     = planned - downtime
    ideal_time   = ideal_cycle_time * total_count
    Availability = run_time / planned
    Performance  = ideal_time / run_time
    Quality      = good_count / total_count
    OEE          = Availability * Performance * Quality

The TOTAL row sums times and counts across periods and then forms the ratios
(it does not average per-period ratios).

Time-loss breakdown (minutes), always summing to planned time:
    downtime_loss   = downtime
    speed_loss      = run_time - ideal_time        (negative if Performance > 1)
    quality_loss    = ideal_cycle_time * (total - good)
    productive_time = ideal_cycle_time * good
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .constants import WORLD_CLASS_OEE, WORLD_CLASS_OEE_NOTE

OEE_COLUMNS = ["period", "planned_time_min", "downtime_min",
               "ideal_cycle_time_min", "total_count", "good_count"]


@dataclass(frozen=True)
class ProductionRecord:
    """One input row: a shift/period. ideal_cycle_time_min is per unit."""

    period: str
    planned_time_min: float
    downtime_min: float
    ideal_cycle_time_min: float
    total_count: int
    good_count: int


@dataclass
class OeeRow:
    """OEE figures for one period, or the TOTAL row (period == "TOTAL").

    Ratios are fractions (0.875 = 87.5%) and are None when undefined
    (zero run time or zero units); the reason is in ``warnings``.
    """

    period: str
    planned_time: float
    downtime: float
    run_time: float
    ideal_time: float          # ideal_cycle_time * total_count
    total_count: int
    good_count: int
    availability: Optional[float]
    performance: Optional[float]
    quality: Optional[float]
    oee: Optional[float]
    downtime_loss: float
    speed_loss: float
    quality_loss: float
    productive_time: float
    warnings: list = field(default_factory=list)


@dataclass
class OeeResult:
    """Result of :func:`compute_oee`.

    rows       one OeeRow per input period, in input order
    total      aggregate OeeRow (sums, then ratios)
    warnings   all row warnings, prefixed with the period name
    world_class_reference / world_class_note   informational 85% reference
    """

    rows: list
    total: OeeRow
    warnings: list = field(default_factory=list)
    world_class_reference: float = WORLD_CLASS_OEE
    world_class_note: str = WORLD_CLASS_OEE_NOTE


def validate_record(rec: ProductionRecord) -> None:
    """Raise ValueError (naming the period) if a record breaks the OEE rules."""
    p = f"period '{rec.period}'"
    for name in ("planned_time_min", "downtime_min", "ideal_cycle_time_min"):
        v = getattr(rec, name)
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{p}: {name} must be a finite number, got {v!r}")
    for name in ("total_count", "good_count"):
        v = getattr(rec, name)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"{p}: {name} must be an integer, got {v!r}")
    if not rec.planned_time_min > 0:
        raise ValueError(f"{p}: planned_time_min must be > 0, got {rec.planned_time_min}")
    if not 0 <= rec.downtime_min <= rec.planned_time_min:
        raise ValueError(
            f"{p}: downtime_min must be between 0 and planned_time_min "
            f"({rec.planned_time_min}), got {rec.downtime_min}")
    if not rec.ideal_cycle_time_min > 0:
        raise ValueError(
            f"{p}: ideal_cycle_time_min must be > 0, got {rec.ideal_cycle_time_min}")
    if rec.total_count < 0:
        raise ValueError(f"{p}: total_count must be >= 0, got {rec.total_count}")
    if not 0 <= rec.good_count <= rec.total_count:
        raise ValueError(
            f"{p}: good_count must be between 0 and total_count "
            f"({rec.total_count}), got {rec.good_count}")


def _build_row(period: str, planned: float, downtime: float, ideal_time: float,
               total: int, good: int, scrap_time: float, productive: float) -> OeeRow:
    run = planned - downtime
    warnings: list = []
    availability = run / planned
    performance: Optional[float] = None
    quality: Optional[float] = None
    if run > 0:
        performance = ideal_time / run
    else:
        warnings.append("No run time (downtime equals planned time): "
                        "Performance and OEE are undefined.")
    if total > 0:
        quality = good / total
    else:
        warnings.append("No units produced: Quality and OEE are undefined.")
    oee = None
    if performance is not None and quality is not None:
        oee = availability * performance * quality
    if performance is not None and performance > 1.0:
        warnings.append(
            f"Performance is {performance * 100:.1f}% (above 100%): "
            "ideal cycle time may be too slow. Value kept as calculated.")
    return OeeRow(period=period, planned_time=planned, downtime=downtime,
                  run_time=run, ideal_time=ideal_time, total_count=total,
                  good_count=good, availability=availability,
                  performance=performance, quality=quality, oee=oee,
                  downtime_loss=downtime, speed_loss=run - ideal_time,
                  quality_loss=scrap_time, productive_time=productive,
                  warnings=warnings)


def compute_oee(records: Sequence[ProductionRecord]) -> OeeResult:
    """Compute per-period and total OEE. Raises ValueError on invalid records
    or when ``records`` is empty."""
    if not records:
        raise ValueError("no production data")
    rows = []
    for rec in records:
        validate_record(rec)
        ideal = rec.ideal_cycle_time_min
        rows.append(_build_row(
            rec.period, float(rec.planned_time_min), float(rec.downtime_min),
            ideal * rec.total_count, rec.total_count, rec.good_count,
            ideal * (rec.total_count - rec.good_count), ideal * rec.good_count))

    total = _build_row(
        "TOTAL",
        math.fsum(r.planned_time for r in rows),
        math.fsum(r.downtime for r in rows),
        math.fsum(r.ideal_time for r in rows),
        sum(r.total_count for r in rows),
        sum(r.good_count for r in rows),
        math.fsum(r.quality_loss for r in rows),
        math.fsum(r.productive_time for r in rows))

    result = OeeResult(rows=rows, total=total)
    for r in rows + [total]:
        for w in r.warnings:
            result.warnings.append(f"{r.period}: {w}")
    return result
