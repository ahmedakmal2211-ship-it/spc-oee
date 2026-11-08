"""Constants are checked against the textbook table (Montgomery, Intro to
Statistical Quality Control, Appendix VI) as transcribed in the task spec."""
from spc_oee import constants as C

N = range(2, 11)


def test_a2():
    exp = [1.880, 1.023, 0.729, 0.577, 0.483, 0.419, 0.373, 0.337, 0.308]
    assert [C.A2[n] for n in N] == exp


def test_d3():
    exp = [0, 0, 0, 0, 0, 0.076, 0.136, 0.184, 0.223]
    assert [C.D3[n] for n in N] == exp


def test_d4():
    exp = [3.267, 2.574, 2.282, 2.114, 2.004, 1.924, 1.864, 1.816, 1.777]
    assert [C.D4[n] for n in N] == exp


def test_d2():
    exp = [1.128, 1.693, 2.059, 2.326, 2.534, 2.704, 2.847, 2.970, 3.078]
    assert [C.D2[n] for n in N] == exp


def test_imr_constants():
    assert C.IMR_E2 == 2.660
    assert abs(C.IMR_E2 - 3 / C.IMR_D2) < 1e-3  # 3/1.128 = 2.6596
    assert C.IMR_D4 == 3.267 and C.IMR_D3 == 0


def test_world_class_reference():
    assert C.WORLD_CLASS_OEE == 0.85
    assert "Nakajima" in C.WORLD_CLASS_OEE_NOTE
