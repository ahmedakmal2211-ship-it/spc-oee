"""Statistical process control: control charts, run rules and capability.

All limits are **Phase I** limits: they are estimated from the same data that
is plotted, so they describe "was the process stable over this sample?" and
are not fixed limits for monitoring future production.

Public API
----------
analyse(...)            -> SpcResult
validate_subgroups(...) -> raises ValueError on bad subgroup structure
compute_capability(...) -> Capability
check_location_rules(), check_spread_rules() -> list[Violation]
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import NamedTuple, Optional, Sequence

from . import constants as C

PPM_NOTE = "estimated, assumes normality and stability"


class Violation(NamedTuple):
    """One run-rule violation: rule id (e.g. "R1"), point index, description.

    ``index`` is 0-based into the plotted series of the chart it was found on.
    """

    rule: str
    index: int
    description: str


@dataclass
class Capability:
    """Process capability indices.

    ``sigma_within`` is Rbar/d2 (or MRbar/1.128); ``sigma_overall`` is the
    sample standard deviation (n-1) of all individual values. Any index that
    cannot be computed (missing spec limit, zero sigma) is None.
    """

    lsl: Optional[float]
    usl: Optional[float]
    mean: float
    sigma_within: float
    sigma_overall: float
    cp: Optional[float] = None      # two-sided spec only
    cpu: Optional[float] = None
    cpl: Optional[float] = None
    cpk: Optional[float] = None     # min of available CPU/CPL
    pp: Optional[float] = None
    ppu: Optional[float] = None
    ppl: Optional[float] = None
    ppk: Optional[float] = None
    ppm_below_lsl: Optional[float] = None
    ppm_above_usl: Optional[float] = None
    ppm_total: Optional[float] = None
    ppm_note: str = PPM_NOTE
    warnings: list = field(default_factory=list)


@dataclass
class SpcResult:
    """Result of :func:`analyse`. Field set is intended to be stable.

    chart_type        "xbar-r" (n in 2..10) or "imr" (n == 1)
    n                 constant subgroup size
    labels            subgroup labels in order of first appearance
    subgroups         raw values per subgroup
    location_points   subgroup means (xbar-r) or the individual values (imr)
    spread_points     subgroup ranges (xbar-r) or moving ranges (imr, len k-1)
    spread_offset     0 for xbar-r; 1 for imr (spread point j sits between
                      location points j and j+1, i.e. it belongs to j+1)
    location_cl/ucl/lcl, spread_cl/ucl/lcl   chart centre lines and limits
    sigma_within      Rbar/d2 or MRbar/1.128
    sigma_overall     sample standard deviation of all values (n-1)
    grand_mean        mean of all individual values
    location_violations, spread_violations   lists of Violation
    capability        Capability, or None when no spec limits were given
    warnings          human-readable warnings
    """

    chart_type: str
    n: int
    labels: list
    subgroups: list
    location_points: list
    spread_points: list
    spread_offset: int
    location_cl: float
    location_ucl: float
    location_lcl: float
    spread_cl: float
    spread_ucl: float
    spread_lcl: float
    sigma_within: float
    sigma_overall: float
    grand_mean: float
    location_violations: list = field(default_factory=list)
    spread_violations: list = field(default_factory=list)
    capability: Optional[Capability] = None
    warnings: list = field(default_factory=list)

    @property
    def location_sigma(self) -> float:
        """Sigma of the plotted location statistic, (UCL - CL) / 3."""
        return (self.location_ucl - self.location_cl) / 3.0

    @property
    def flagged_location_indices(self) -> list:
        return sorted({v.index for v in self.location_violations})

    @property
    def flagged_spread_indices(self) -> list:
        return sorted({v.index for v in self.spread_violations})

    @property
    def is_stable(self) -> bool:
        return not self.location_violations and not self.spread_violations


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_subgroups(labels: Sequence[str], groups: Sequence[Sequence[float]]) -> int:
    """Check subgroup structure and return the constant subgroup size n.

    Raises ValueError naming the offending subgroup for: no data, fewer than
    2 subgroups, non-constant size, n > 10, non-finite values.
    """
    if not groups:
        raise ValueError("no measurement data")
    if len(groups) < 2:
        raise ValueError(
            f"need at least 2 subgroups, found {len(groups)} (subgroup '{labels[0]}')")
    n = len(groups[0])
    for lab, g in zip(labels, groups):
        if len(g) != n:
            raise ValueError(
                f"subgroup '{lab}' has {len(g)} values but subgroup '{labels[0]}' "
                f"has {n}; subgroup size must be constant")
        for v in g:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"subgroup '{lab}' contains a non-finite value: {v!r}")
    if n < 1:
        raise ValueError("subgroups are empty")
    if n > C.MAX_SUBGROUP:
        raise ValueError(
            f"subgroup size {n} (subgroup '{labels[0]}') is above {C.MAX_SUBGROUP}; "
            f"Xbar-R supports n = 2..{C.MAX_SUBGROUP} and I-MR supports n = 1")
    return n


# --------------------------------------------------------------------------
# Run rules (Western Electric / Nelson)
# --------------------------------------------------------------------------

def check_location_rules(points: Sequence[float], cl: float, ucl: float,
                         lcl: float) -> list:
    """Apply rules R1-R4 to a location chart; return sorted Violations.

    sigma = (UCL - CL) / 3. Zone A is 2-3 sigma, B 1-2, C 0-1 from CL.
      R1  one point beyond 3 sigma (outside UCL/LCL)
      R2  two of three consecutive points beyond 2 sigma, same side
      R3  four of five consecutive points beyond 1 sigma, same side
      R4  eight consecutive points on one side of CL (a point exactly on CL
          breaks the run); flagged from the 8th point of the run onward
    For R2/R3 windows are also evaluated at the start of the series with fewer
    points than the full window (e.g. 2 of the first 2 points), so early points
    can be flagged before a full window exists. The points beyond the threshold in every qualifying window are
    flagged (including the point that completes the pattern).
    """
    sigma = (ucl - cl) / 3.0
    out: list = []

    # R1
    for i, x in enumerate(points):
        if x > ucl:
            out.append(Violation("R1", i, "R1: point above UCL (beyond 3 sigma)"))
        elif x < lcl:
            out.append(Violation("R1", i, "R1: point below LCL (beyond 3 sigma)"))

    def windowed(rule: str, size: int, need: int, k: float, text: str) -> None:
        above = [x > cl + k * sigma for x in points]
        below = [x < cl - k * sigma for x in points]
        flagged: dict = {}
        for end in range(len(points)):
            start = max(0, end - size + 1)
            for flags, side in ((above, "above"), (below, "below")):
                idx = [j for j in range(start, end + 1) if flags[j]]
                if len(idx) >= need:
                    for j in idx:
                        flagged[j] = side
        for j in sorted(flagged):
            out.append(Violation(rule, j, f"{rule}: {text} on the {flagged[j]}-CL side"))

    windowed("R2", 3, 2, 2.0, "2 of 3 consecutive points beyond 2 sigma")
    windowed("R3", 5, 4, 1.0, "4 of 5 consecutive points beyond 1 sigma")

    # R4
    run = 0
    side = 0
    for i, x in enumerate(points):
        s = 1 if x > cl else (-1 if x < cl else 0)
        if s == 0:
            run, side = 0, 0
            continue
        run = run + 1 if s == side else 1
        side = s
        if run >= 8:
            out.append(Violation(
                "R4", i,
                f"R4: {run} consecutive points {'above' if s > 0 else 'below'} CL"))

    out.sort(key=lambda v: (v.index, v.rule))
    return out


def check_spread_rules(points: Sequence[float], cl: float, ucl: float,
                       lcl: float) -> list:
    """R1 only on the range / moving-range chart (above UCL, or below LCL if LCL > 0)."""
    out = []
    for i, x in enumerate(points):
        if x > ucl:
            out.append(Violation("R1", i, "R1: point above UCL"))
        elif lcl > 0 and x < lcl:
            out.append(Violation("R1", i, "R1: point below LCL"))
    return out


# --------------------------------------------------------------------------
# Capability
# --------------------------------------------------------------------------

def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_capability(mean: float, sigma_within: float, sigma_overall: float,
                       lsl: Optional[float] = None,
                       usl: Optional[float] = None) -> Capability:
    """Capability indices from a mean and two sigma estimates.

    Cp  = (USL - LSL) / (6 sigma_within)         (two-sided only)
    CPU = (USL - mean) / (3 sigma_within),  CPL = (mean - LSL) / (3 sigma_within)
    Cpk = min of the available CPU / CPL
    Pp/Ppk: same with sigma_overall. A zero sigma gives None (no division).
    PPM out of spec uses the normal CDF with sigma_within ("estimated, assumes
    normality and stability"). Raises ValueError if LSL >= USL.
    """
    for name, v in (("LSL", lsl), ("USL", usl)):
        if v is not None and not math.isfinite(v):
            raise ValueError(f"{name} must be a finite number, got {v}")
    if lsl is None and usl is None:
        raise ValueError("at least one of lsl / usl is required for capability")
    if lsl is not None and usl is not None and lsl >= usl:
        raise ValueError(f"LSL ({lsl}) must be less than USL ({usl})")

    cap = Capability(lsl=lsl, usl=usl, mean=mean,
                     sigma_within=sigma_within, sigma_overall=sigma_overall)

    def indices(sigma: float):
        if not sigma > 0:
            return None, None, None, None
        spread = (usl - lsl) / (6 * sigma) if lsl is not None and usl is not None else None
        up = (usl - mean) / (3 * sigma) if usl is not None else None
        lo = (mean - lsl) / (3 * sigma) if lsl is not None else None
        avail = [v for v in (up, lo) if v is not None]
        return spread, up, lo, min(avail)

    cap.cp, cap.cpu, cap.cpl, cap.cpk = indices(sigma_within)
    cap.pp, cap.ppu, cap.ppl, cap.ppk = indices(sigma_overall)

    if not sigma_within > 0:
        cap.warnings.append(
            "Within-subgroup sigma is zero: Cp/Cpk and PPM are undefined.")
    else:
        below = _norm_cdf((lsl - mean) / sigma_within) * 1e6 if lsl is not None else None
        above = (1.0 - _norm_cdf((usl - mean) / sigma_within)) * 1e6 if usl is not None else None
        cap.ppm_below_lsl, cap.ppm_above_usl = below, above
        cap.ppm_total = (below or 0.0) + (above or 0.0)
    if not sigma_overall > 0:
        cap.warnings.append("Overall sigma is zero: Pp/Ppk are undefined.")
    return cap


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def analyse(groups: Sequence[Sequence[float]], labels: Optional[Sequence[str]] = None,
            lsl: Optional[float] = None, usl: Optional[float] = None) -> SpcResult:
    """Build the control charts, apply the run rules and (optionally) capability.

    Phase I only: limits are computed from all supplied data.
    Subgroup size n in 2..10 gives Xbar-R; n == 1 gives I-MR.
    """
    groups = [list(map(float, g)) for g in groups]
    if labels is None:
        labels = [str(i + 1) for i in range(len(groups))]
    labels = list(labels)
    if len(labels) != len(groups):
        raise ValueError(
            f"got {len(labels)} labels for {len(groups)} subgroups")
    n = validate_subgroups(labels, groups)

    all_values = [v for g in groups for v in g]
    grand_mean = statistics.fmean(all_values)
    sigma_overall = statistics.stdev(all_values)  # n-1 denominator

    if n == 1:
        chart = "imr"
        loc = all_values
        spread = [abs(loc[i] - loc[i - 1]) for i in range(1, len(loc))]
        offset = 1
        mrbar = statistics.fmean(spread)
        cl = statistics.fmean(loc)
        ucl, lcl = cl + C.IMR_E2 * mrbar, cl - C.IMR_E2 * mrbar
        s_cl, s_ucl, s_lcl = mrbar, C.IMR_D4 * mrbar, C.IMR_D3 * mrbar
        sigma_within = mrbar / C.IMR_D2
    else:
        chart = "xbar-r"
        loc = [statistics.fmean(g) for g in groups]
        spread = [max(g) - min(g) for g in groups]
        offset = 0
        rbar = statistics.fmean(spread)
        cl = statistics.fmean(loc)
        ucl, lcl = cl + C.A2[n] * rbar, cl - C.A2[n] * rbar
        s_cl, s_ucl, s_lcl = rbar, C.D4[n] * rbar, C.D3[n] * rbar
        sigma_within = rbar / C.D2[n]

    res = SpcResult(
        chart_type=chart, n=n, labels=labels, subgroups=groups,
        location_points=loc, spread_points=spread, spread_offset=offset,
        location_cl=cl, location_ucl=ucl, location_lcl=lcl,
        spread_cl=s_cl, spread_ucl=s_ucl, spread_lcl=s_lcl,
        sigma_within=sigma_within, sigma_overall=sigma_overall,
        grand_mean=grand_mean)
    if s_cl == 0 and len({round(x, 12) for x in loc}) > 1:
        res.warnings.append(
            "Within-subgroup sigma is zero (Rbar/MRbar = 0) but the plotted "
            "points differ: the control limits collapse onto the centre line, "
            "so many points will be flagged.")
    res.location_violations = check_location_rules(loc, cl, ucl, lcl)
    res.spread_violations = check_spread_rules(spread, s_cl, s_ucl, s_lcl)

    if lsl is not None or usl is not None:
        res.capability = compute_capability(grand_mean, sigma_within, sigma_overall,
                                            lsl, usl)
        if not res.is_stable:
            msg = ("Process shows rule violations (not in statistical control): "
                   "capability indices are only meaningful for a stable process.")
            res.capability.warnings.append(msg)
            res.warnings.append(msg)
    return res
