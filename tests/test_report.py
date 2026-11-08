"""HTML report tests: structure, self-containment, escaping, None handling."""
import re

from spc_oee.oee import ProductionRecord, compute_oee
from spc_oee.report import build_report
from spc_oee.spc import analyse

XMLNS = "http://www.w3.org/2000/svg"


def _spc(lsl=9.85, usl=10.15, imr=False):
    groups = [[10.0, 10.02, 9.98, 10.01, 9.99] for _ in range(14)]
    groups[6] = [10.3, 10.28, 10.31, 10.29, 10.3]   # R1 on location
    groups[9] = [9.8, 10.2, 10.0, 10.0, 10.0]       # wide range
    if imr:
        groups = [[g[0]] for g in groups]
    labels = [f"S{i + 1}" for i in range(len(groups))]
    return analyse(groups, labels, lsl=lsl, usl=usl)


def _oee(periods=("A", "B")):
    return compute_oee([ProductionRecord(p, 480, 60, 1.0, 380, 361) for p in periods])


def _meta(**kw):
    m = {"title": "T", "lsl": 9.85, "usl": 10.15, "measurements_file": "m.csv",
         "production_file": "p.csv", "version": "1.2.3"}
    m.update(kw)
    return m


def test_structure():
    h = build_report(_spc(), _oee(), _meta())
    assert h.startswith("<!DOCTYPE html>")
    assert h.count("<svg xmlns") >= 2
    assert "prefers-color-scheme" in h and "viewport" in h
    assert "OEE" in h and "Capability" in h and "Violations" in h


def test_one_svg_per_chart_without_oee():
    h = build_report(_spc(), None, _meta())
    # two control charts + two legend-key glyph svgs (aria-hidden)
    assert h.count('role="img"') == 2


def test_self_contained():
    h = build_report(_spc(), _oee(), _meta())
    assert "<script" not in h.lower()
    stripped = h.replace(XMLNS, "")
    assert "http://" not in stripped and "https://" not in stripped
    assert "<link" not in h and "@import" not in h and "url(" not in h


def test_escaping():
    evil = "<script>alert(1)</script>"
    h = build_report(_spc(), _oee(("<b>x</b>",)),
                     _meta(title=evil, measurements_file=evil, production_file='"><img src=x>'))
    assert evil not in h and "<script" not in h.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h
    assert "<b>x</b>" not in h and "<img" not in h


def test_escapes_labels():
    spc = _spc()
    spc.labels[6] = "<i>bad</i>"
    h = build_report(spc, None, _meta())
    assert "<i>bad</i>" not in h and "&lt;i&gt;bad&lt;/i&gt;" in h


def test_none_handling_and_no_capability():
    spc = _spc(lsl=None, usl=10.15)
    h = build_report(spc, None, {})
    assert "nan" not in h.lower().replace("finance", "")
    assert "—" in h  # CPL undefined with one-sided spec
    spc2 = _spc(lsl=None, usl=None)
    h2 = build_report(spc2, None, _meta())
    assert "not computed" in h2


def test_oee_none_values():
    oee = compute_oee([ProductionRecord("Z", 480, 480, 1.0, 0, 0)])
    h = build_report(_spc(), oee, _meta())
    assert "—" in h and "No run time" in h


def test_oee_absent_omits_section():
    h = build_report(_spc(), None, _meta())
    assert "<h2>OEE</h2>" not in h and "reference (convention)" not in h


def test_oee_present_has_reference_and_losses():
    h = build_report(_spc(), _oee(), _meta())
    assert "85% reference (convention)" in h
    assert "Downtime loss" in h and "Speed loss" in h and "Quality loss" in h


def test_flagged_points_have_marker_and_rule_label():
    spc = _spc()
    h = build_report(spc, None, _meta())
    n_flag = len(spc.flagged_location_indices) + len(spc.flagged_spread_indices)
    assert n_flag >= 2
    assert h.count('<polygon class="flag"') == n_flag
    assert re.search(r">R1</text>", h)


def test_imr_chart():
    h = build_report(_spc(imr=True), None, _meta())
    assert "Individuals" in h and "Moving range" in h


def test_instability_caveat_and_synthetic_note():
    h = build_report(_spc(), None, _meta(synthetic=True))
    assert "not in statistical control" in h
    assert "Synthetic demo data" in h
    assert "Synthetic demo data" not in build_report(_spc(), None, _meta())


def test_deterministic():
    a = build_report(_spc(), _oee(), _meta())
    b = build_report(_spc(), _oee(), _meta())
    assert a == b
