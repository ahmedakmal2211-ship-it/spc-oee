"""CSV loading and validation.

Measurements CSV (long format), header ``subgroup,value``.
Production CSV, header ``period,planned_time_min,downtime_min,
ideal_cycle_time_min,total_count,good_count``.

Row numbers in error messages are file line numbers (the header is line 1).
Every problem raises ValueError (or FileNotFoundError for a missing file).
"""

from __future__ import annotations

import csv
import math
from typing import Optional

from .oee import OEE_COLUMNS, ProductionRecord, validate_record
from .spc import validate_subgroups

MEASUREMENT_COLUMNS = ["subgroup", "value"]


def _read(path: str, columns: list) -> list:
    """Return [(line_number, row_dict), ...] after checking the header."""
    try:
        return _read_rows(path, columns)
    except csv.Error as exc:
        raise ValueError(f"{path}: malformed CSV: {exc}") from None
    except UnicodeDecodeError:
        raise ValueError(f"{path}: file is not valid UTF-8 text") from None


def _read_rows(path: str, columns: list) -> list:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: file is empty") from None
        header = [h.strip() for h in header]
        if header != columns:
            raise ValueError(
                f"{path}: header must be '{','.join(columns)}', got '{','.join(header)}'")
        rows = []
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue  # skip blank lines
            line = reader.line_num
            if len(row) != len(columns):
                raise ValueError(
                    f"{path}: row {line} has {len(row)} fields, expected {len(columns)}")
            rows.append((line, dict(zip(columns, (c.strip() for c in row)))))
    if not rows:
        raise ValueError(f"{path}: no data rows")
    return rows


def _number(text: str, path: str, line: int, name: str) -> float:
    try:
        v = float(text)
    except ValueError:
        raise ValueError(f"{path}: row {line}: {name} is not numeric: '{text}'") from None
    if not math.isfinite(v):
        raise ValueError(f"{path}: row {line}: {name} must be finite, got '{text}'")
    return v


def _integer(text: str, path: str, line: int, name: str) -> int:
    v = _number(text, path, line, name)
    if v != int(v):
        raise ValueError(f"{path}: row {line}: {name} must be an integer, got '{text}'")
    return int(v)


def load_measurements(path: str):
    """Load a measurements CSV. Returns (labels, groups, n).

    Subgroups are ordered by first appearance. Raises ValueError for
    non-numeric/NaN/inf values, empty file, <2 subgroups, non-constant
    subgroup size or n > 10.
    """
    rows = _read(path, MEASUREMENT_COLUMNS)
    order: dict = {}
    for line, r in rows:
        label = r["subgroup"]
        if not label:
            raise ValueError(f"{path}: row {line}: subgroup label is empty")
        order.setdefault(label, []).append(_number(r["value"], path, line, "value"))
    labels = list(order)
    groups = [order[k] for k in labels]
    try:
        n = validate_subgroups(labels, groups)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from None
    return labels, groups, n


def load_production(path: str) -> list:
    """Load a production-times CSV into a list of ProductionRecord."""
    out = []
    seen = set()
    for line, r in _read(path, OEE_COLUMNS):
        if not r["period"]:
            raise ValueError(f"{path}: row {line}: period is empty")
        if r["period"] in seen:
            raise ValueError(f"{path}: row {line}: duplicate period '{r['period']}'")
        seen.add(r["period"])
        rec = ProductionRecord(
            period=r["period"],
            planned_time_min=_number(r["planned_time_min"], path, line, "planned_time_min"),
            downtime_min=_number(r["downtime_min"], path, line, "downtime_min"),
            ideal_cycle_time_min=_number(r["ideal_cycle_time_min"], path, line,
                                         "ideal_cycle_time_min"),
            total_count=_integer(r["total_count"], path, line, "total_count"),
            good_count=_integer(r["good_count"], path, line, "good_count"))
        try:
            validate_record(rec)
        except ValueError as exc:
            raise ValueError(f"{path}: row {line}: {exc}") from None
        out.append(rec)
    return out
