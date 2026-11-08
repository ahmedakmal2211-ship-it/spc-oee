"""SPC tests: hand-computed or textbook-formula checks (no textbook dataset)."""
import math

import pytest

from spc_oee.spc import analyse, check_location_rules, check_spread_rules, compute_capability


def test_xbar_r_limits_hand_computed():
    # n = 2, three subgroups: [10,12], [11,15], [9,12]
    # means = 11, 13, 10.5 -> xbarbar = 34.5/3 = 11.5
    # ranges = 2, 4, 3     -> Rbar = 9/3 = 3
    # UCL = 11.5 + 1.880*3 = 17.14 ; LCL = 11.5 - 5.64 = 5.86
    # R chart: UCL = 3.267*3 = 9.801 ; LCL = 0*3 = 0
    # sigma_within = 3/1.128
    r = analyse([[10, 12], [11, 15], [9, 12]])
    assert r.chart_type == "xbar-r" and r.n == 2
    assert r.location_cl == pytest.approx(11.5)
    assert r.location_ucl == pytest.approx(17.14)
    assert r.location_lcl == pytest.approx(5.86)
    assert r.spread_cl == pytest.approx(3.0)
    assert r.spread_ucl == pytest.approx(9.801)
    assert r.spread_lcl == 0.0
    assert r.sigma_within == pytest.approx(3 / 1.128)
    assert r.location_sigma == pytest.approx((17.14 - 11.5) / 3)


def test_imr_limits_hand_computed():
    # values 10,12,11,13,14 -> xbar = 60/5 = 12
    # MR = 2,1,2,1 -> MRbar = 6/4 = 1.5
    # UCL = 12 + 2.660*1.5 = 15.99 ; LCL = 8.01 ; MR UCL = 3.267*1.5 = 4.9005
    r = analyse([[10], [12], [11], [13], [14]])
    assert r.chart_type == "imr" and r.n == 1
    assert r.spread_points == [2, 1, 2, 1] and r.spread_offset == 1
    assert r.location_cl == pytest.approx(12)
    assert r.location_ucl == pytest.approx(15.99)
    assert r.location_lcl == pytest.approx(8.01)
    assert r.spread_cl == pytest.approx(1.5)
    assert r.spread_ucl == pytest.approx(4.9005)
    assert r.spread_lcl == 0
    assert r.sigma_within == pytest.approx(1.5 / 1.128)


def test_sigma_overall_uses_n_minus_1():
    r = analyse([[1, 3], [5, 7]])
    # values 1,3,5,7 mean 4, SS = 9+1+1+9 = 20, s = sqrt(20/3)
    assert r.sigma_overall == pytest.approx(math.sqrt(20 / 3))
    assert r.grand_mean == 4


# ---- capability ---------------------------------------------------------

def test_cp_cpk_centered():
    # (62-38)/(6*2) = 2.0 ; CPU = (62-50)/6 = 2.0 ; CPL = 2.0
    c = compute_capability(50, 2, 2, lsl=38, usl=62)
    assert c.cp == pytest.approx(2.0) and c.cpk == pytest.approx(2.0)
    assert c.pp == pytest.approx(2.0) and c.ppk == pytest.approx(2.0)


def test_cpk_off_centre():
    # mean 53: CPU = 9/6 = 1.5 ; CPL = 15/6 = 2.5 ; Cpk = 1.5 ; Cp unchanged
    c = compute_capability(53, 2, 2.5, lsl=38, usl=62)
    assert c.cp == pytest.approx(2.0)
    assert c.cpu == pytest.approx(1.5) and c.cpl == pytest.approx(2.5)
    assert c.cpk == pytest.approx(1.5)
    # Ppk uses overall sigma 2.5: CPU = 9/7.5 = 1.2
    assert c.ppk == pytest.approx(1.2)


def test_one_sided():
    c = compute_capability(50, 2, 2, usl=62)
    assert c.cp is None and c.cpl is None and c.pp is None
    assert c.cpu == pytest.approx(2.0) and c.cpk == pytest.approx(2.0)
    c = compute_capability(50, 2, 2, lsl=44)
    assert c.cpk == pytest.approx(1.0) and c.cpu is None


def test_zero_sigma_guard():
    c = compute_capability(50, 0.0, 0.0, lsl=38, usl=62)
    assert c.cp is None and c.cpk is None and c.pp is None and c.ppk is None
    assert c.ppm_total is None
    assert c.warnings
    r = analyse([[5, 5], [5, 5], [5, 5]], lsl=0, usl=10)  # no ZeroDivisionError
    assert r.capability.cpk is None


def test_ppm_normal_cdf():
    # mean 50, sigma 2, USL 56 = 3 sigma -> upper tail 0.00134990 = 1349.9 ppm
    c = compute_capability(50, 2, 2, usl=56)
    assert c.ppm_above_usl == pytest.approx(1349.898, rel=1e-4)
    assert c.ppm_below_lsl is None
    assert "assumes normality" in c.ppm_note


def test_bad_spec_limits():
    with pytest.raises(ValueError):
        compute_capability(5, 1, 1, lsl=10, usl=5)


def test_capability_warns_when_unstable():
    groups = [[10.0, 10.1], [10.0, 10.1], [10.0, 10.1], [10.0, 10.1], [50.0, 50.1]]
    r = analyse(groups, lsl=0, usl=60)
    assert not r.is_stable
    assert any("stable" in w for w in r.capability.warnings)


def test_no_capability_without_spec():
    assert analyse([[1, 2], [2, 3]]).capability is None


# ---- rules --------------------------------------------------------------
# Crafted series with CL=0, UCL=3, LCL=-3 so sigma = 1.

def rules(pts):
    return {v.rule for v in check_location_rules(pts, 0, 3, -3)}


def test_r1():
    v = check_location_rules([0, 0.5, 3.5, 0, -3.2], 0, 3, -3)
    assert [(x.rule, x.index) for x in v if x.rule == "R1"] == [("R1", 2), ("R1", 4)]
    assert "R1" not in rules([0, 2.9, -2.9, 1, -1])


def test_r2():
    v = check_location_rules([0, 2.5, 0, 2.5, 0], 0, 3, -3)
    assert [x.index for x in v if x.rule == "R2"] == [1, 3]
    # opposite sides do not count
    assert "R2" not in rules([2.5, 0, -2.5, 0, 0])
    # two beyond 2 sigma but 3 apart (window of 3 too short)
    assert "R2" not in rules([2.5, 0, 0, 2.5, 0])


def test_r3():
    v = check_location_rules([1.5, 1.5, 0.5, 1.5, 1.5], 0, 3, -3)
    assert [x.index for x in v if x.rule == "R3"] == [0, 1, 3, 4]
    assert "R3" not in rules([1.5, 1.5, 0.5, 1.5, 0.5, 1.5])  # only 3 of 5


def test_r4():
    v = check_location_rules([0.5] * 8, 0, 3, -3)
    assert [x.index for x in v if x.rule == "R4"] == [7]
    assert "R4" not in rules([0.5] * 7)
    assert "R4" not in rules([0.5] * 4 + [0.0] + [0.5] * 4)  # on-CL point breaks the run
    assert "R4" not in rules([0.5] * 7 + [-0.5])


def test_clean_series_fires_nothing():
    clean = [0.5, -0.5, 0.2, -0.3, 0.8, -0.9, 0.1, -0.1, 0.4, -0.6] * 2
    assert check_location_rules(clean, 0, 3, -3) == []


def test_spread_rules_r1_only():
    assert [v.index for v in check_spread_rules([1, 5, 1], 1, 3, 0)] == [1]
    assert check_spread_rules([0, 1, 2], 1, 3, 0) == []        # LCL = 0: never below
    assert [v.index for v in check_spread_rules([0.1, 1], 1, 3, 0.5)] == [0]  # LCL > 0
    # a long run on one side is not flagged on a spread chart
    assert check_spread_rules([1.5] * 10, 1, 3, 0) == []


# ---- red-team regressions ----------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_spec_limits(bad):
    with pytest.raises(ValueError, match="finite"):
        compute_capability(5, 1, 1, lsl=bad)
    with pytest.raises(ValueError, match="finite"):
        compute_capability(5, 1, 1, usl=bad)


def test_label_count_mismatch():
    with pytest.raises(ValueError, match="labels"):
        analyse([[1, 2], [2, 3]], labels=["a"])


def test_zero_range_with_differing_means_warns():
    # every subgroup has range 0 but means differ -> Rbar = 0, limits collapse
    r = analyse([[1, 1], [2, 2], [3, 3]])
    assert any("sigma is zero" in w.lower() for w in r.warnings)
    assert not analyse([[1, 2], [2, 3], [1, 3]]).warnings


def test_r2_flags_partial_window_at_start():
    # documented behaviour: 2 of the first 2 points beyond 2 sigma is flagged
    v = check_location_rules([2.5, 2.5, 0, 0], 0, 3, -3)
    assert [x.index for x in v if x.rule == "R2"] == [0, 1]
