"""OEE tests: hand-computed values."""
import pytest

from spc_oee.oee import ProductionRecord, compute_oee


def rec(period="P", planned=480, down=60, ideal=1.0, total=380, good=361):
    return ProductionRecord(period, planned, down, ideal, total, good)


def test_hand_case():
    # run = 480-60 = 420 ; A = 420/480 = 0.875 ; ideal time = 1.0*380 = 380
    # P = 380/420 ; Q = 361/380 = 0.95 ; OEE = A*P*Q
    r = compute_oee([rec()]).rows[0]
    assert r.run_time == 420
    assert r.availability == pytest.approx(0.875)
    assert r.performance == pytest.approx(380 / 420)
    assert r.quality == pytest.approx(0.95)
    assert r.oee == pytest.approx(0.875 * (380 / 420) * 0.95)
    assert r.warnings == []


def test_loss_breakdown_sums_to_planned():
    # downtime 60 + speed 40 + quality 19 + productive 361 = 480
    r = compute_oee([rec()]).rows[0]
    assert (r.downtime_loss, r.speed_loss, r.quality_loss, r.productive_time) == (60, 40, 19, 361)
    assert r.downtime_loss + r.speed_loss + r.quality_loss + r.productive_time == pytest.approx(480)


def test_totals_sum_not_average():
    a = rec("A", planned=480, down=60, ideal=1.0, total=380, good=361)
    b = rec("B", planned=240, down=0, ideal=0.5, total=400, good=300)
    res = compute_oee([a, b])
    t = res.total
    # planned 720, downtime 60, run 660, ideal time 380 + 200 = 580
    # total 780, good 661
    assert (t.planned_time, t.downtime, t.run_time, t.ideal_time) == (720, 60, 660, 580)
    assert t.availability == pytest.approx(660 / 720)
    assert t.performance == pytest.approx(580 / 660)
    assert t.quality == pytest.approx(661 / 780)
    mean_oee = (res.rows[0].oee + res.rows[1].oee) / 2
    assert t.oee != pytest.approx(mean_oee)
    for r in res.rows + [t]:
        assert r.downtime_loss + r.speed_loss + r.quality_loss + r.productive_time == pytest.approx(r.planned_time)


def test_performance_above_one_warns_and_is_not_capped():
    res = compute_oee([rec(ideal=1.2, total=400, good=400)])  # ideal time 480 vs run 420
    r = res.rows[0]
    assert r.performance == pytest.approx(480 / 420) and r.performance > 1
    assert any("ideal cycle time may be too slow" in w for w in r.warnings)
    assert res.warnings
    assert r.downtime_loss + r.speed_loss + r.quality_loss + r.productive_time == pytest.approx(480)


def test_zero_run_time():
    r = compute_oee([rec(down=480, total=0, good=0)]).rows[0]
    assert r.availability == 0 and r.performance is None and r.oee is None
    assert any("No run time" in w for w in r.warnings)


def test_zero_units():
    r = compute_oee([rec(total=0, good=0)]).rows[0]
    assert r.performance == 0 and r.quality is None and r.oee is None
    assert any("No units" in w for w in r.warnings)


@pytest.mark.parametrize("kw", [
    dict(planned=0), dict(planned=-5), dict(down=-1), dict(down=481),
    dict(ideal=0), dict(ideal=-1), dict(total=-1), dict(good=-1),
    dict(total=10, good=11), dict(total=10.5, good=5),
])
def test_validation_errors(kw):
    with pytest.raises(ValueError):
        compute_oee([rec(**kw)])


def test_empty():
    with pytest.raises(ValueError):
        compute_oee([])
