"""Sample generator and CLI end-to-end tests."""
import pytest

from spc_oee.cli import main
from spc_oee.io import load_measurements, load_production
from spc_oee.oee import compute_oee
from spc_oee.sample import generate_sample, write_sample_csvs
from spc_oee.spc import analyse


def spc_of(data):
    groups = [[v for _, v in data.measurements[i:i + 5]] for i in range(0, 150, 5)]
    return analyse(groups, lsl=data.lsl, usl=data.usl)


def test_deterministic():
    a, b = generate_sample(42), generate_sample(42)
    assert a.measurements == b.measurements and a.production == b.production
    assert generate_sample(7).measurements != a.measurements


def test_shape():
    d = generate_sample()
    assert len(d.measurements) == 150 and len(d.production) == 14
    assert (d.lsl, d.usl) == (9.85, 10.15)
    assert all(r.planned_time_min == 480 and 20 <= r.downtime_min <= 90
               and r.ideal_cycle_time_min == 0.5 for r in d.production)


def test_triggers_expected_rules():
    r = spc_of(generate_sample())
    rules = {(v.rule, v.index) for v in r.location_violations}
    assert ("R1", 11) in rules                        # spike at subgroup 12
    assert any(rule == "R4" and i >= 21 for rule, i in rules)   # sustained shift
    assert r.capability is not None and r.capability.warnings


def test_sample_oee_range():
    res = compute_oee(generate_sample().production)
    assert 0.55 <= res.total.oee <= 0.80
    assert all(0.45 <= r.oee <= 0.90 for r in res.rows)


def test_csv_roundtrip(tmp_path):
    m, p, data = write_sample_csvs(str(tmp_path / "out"))
    labels, groups, n = load_measurements(m)
    assert n == 5 and len(labels) == 30
    assert load_production(p) == data.production


def test_cli_demo(tmp_path, capsys):
    out_dir = tmp_path / "ex"
    assert main(["--demo", "--out-dir", str(out_dir)]) == 0
    assert (out_dir / "sample_report.html").read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert (out_dir / "sample_measurements.csv").exists()
    text = capsys.readouterr().out
    assert "Cpk" in text and "OEE total" in text and "Flagged" in text


def test_cli_files(tmp_path, capsys):
    m, p, _ = write_sample_csvs(str(tmp_path))
    out = tmp_path / "r.html"
    assert main([m, p, "--lsl", "9.85", "--usl", "10.15", "--out", str(out), "--title", "T"]) == 0
    assert "<title>T</title>" in out.read_text(encoding="utf-8")


def test_cli_measurements_only(tmp_path, capsys):
    m, _, _ = write_sample_csvs(str(tmp_path))
    assert main([m, "--out", str(tmp_path / "r.html")]) == 0
    assert "OEE total" not in capsys.readouterr().out


def test_cli_errors_exit_2(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("spc-oee: error:") and "Traceback" not in err
    bad = tmp_path / "bad.csv"
    bad.write_text("subgroup,value\nA,x\nB,1\n")
    assert main([str(bad)]) == 2
    assert "row 2" in capsys.readouterr().err


def test_cli_no_args_exit_2(capsys):
    assert main([]) == 2


def test_cli_bad_args():
    with pytest.raises(SystemExit) as e:
        main(["--lsl", "abc"])
    assert e.value.code == 2


@pytest.mark.parametrize("flag", ["--lsl", "--usl"])
@pytest.mark.parametrize("val", ["nan", "inf", "-inf"])
def test_cli_rejects_non_finite_spec(tmp_path, flag, val, capsys):
    m, _, _ = write_sample_csvs(str(tmp_path))
    with pytest.raises(SystemExit) as e:
        main([m, flag, val])
    assert e.value.code == 2


def test_report_footer_has_base_names_only(tmp_path):
    m, p, _ = write_sample_csvs(str(tmp_path / "secretdir"))
    out = tmp_path / "r.html"
    assert main([m, p, "--out", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "sample_measurements.csv" in html and "secretdir" not in html


def test_loss_bar_never_overflows_when_performance_above_one():
    import re
    from spc_oee.oee import ProductionRecord
    from spc_oee.report import loss_bar_svg
    t = compute_oee([ProductionRecord("P", 480, 60, 1.2, 400, 400)]).total
    assert t.speed_loss < 0
    svg = loss_bar_svg(t)
    right = max(float(x) + float(w) + 2 for x, w in
                re.findall(r'<rect x="([\d.]+)" y="10" width="([\d.]+)"', svg))
    assert right <= 600 - 8 + 0.6
