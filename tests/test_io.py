"""CSV loading and validation errors."""
import pytest

from spc_oee.io import load_measurements, load_production


def write(tmp_path, text, name="f.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_load_measurements_ok(tmp_path):
    p = write(tmp_path, "subgroup,value\nA,1\nA,2\nB,3\nB,4\nC,5\nC,6\n")
    labels, groups, n = load_measurements(p)
    assert labels == ["A", "B", "C"] and groups == [[1, 2], [3, 4], [5, 6]] and n == 2


def test_individuals_n1(tmp_path):
    _, groups, n = load_measurements(write(tmp_path, "subgroup,value\n1,5\n2,6\n3,7\n"))
    assert n == 1 and len(groups) == 3


@pytest.mark.parametrize("text,fragment", [
    ("", "empty"),
    ("subgroup,value\n", "no data rows"),
    ("a,b\n1,2\n", "header"),
    ("subgroup,value\nA,1\nA,2\n", "at least 2 subgroups"),
    ("subgroup,value\nA,1\nA,2\nB,3\n", "subgroup 'B'"),
    ("subgroup,value\nA,x\nB,2\n", "row 2"),
    ("subgroup,value\nA,nan\nB,2\n", "row 2"),
    ("subgroup,value\nA,inf\nB,2\n", "row 2"),
    ("subgroup,value\nA,\nB,2\n", "row 2"),
    ("subgroup,value\n,1\nB,2\n", "row 2"),
    ("subgroup,value\n" + "".join(f"A,{i}\nB,{i}\n" for i in range(11)), "above 10"),
])
def test_measurement_errors(tmp_path, text, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_measurements(write(tmp_path, text))


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_measurements("does-not-exist.csv")


HDR = "period,planned_time_min,downtime_min,ideal_cycle_time_min,total_count,good_count\n"


def test_load_production_ok(tmp_path):
    recs = load_production(write(tmp_path, HDR + "S1,480,60,1.0,380,361\n"))
    assert recs[0].total_count == 380 and recs[0].good_count == 361


@pytest.mark.parametrize("row,fragment", [
    ("S1,480,60,1.0,380.5,361", "integer"),
    ("S1,480,60,1.0,380,abc", "row 2"),
    ("S1,0,0,1.0,10,5", "planned_time_min"),
    ("S1,480,500,1.0,10,5", "downtime_min"),
    ("S1,480,60,0,10,5", "ideal_cycle_time_min"),
    ("S1,480,60,1.0,10,11", "good_count"),
    ("S1,480,60,1.0,-1,0", "total_count"),
    ("S1,480,60,nan,10,5", "row 2"),
    ("S1,480,60,1.0,10", "fields"),
])
def test_production_errors(tmp_path, row, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_production(write(tmp_path, HDR + row + "\n"))


def test_production_duplicate_period(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_production(write(tmp_path, HDR + "S1,480,60,1,10,5\nS1,480,60,1,10,5\n"))


def test_bad_utf8_names_file(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(b"subgroup,value\n\xff\xfe,1\n")
    with pytest.raises(ValueError, match="bad.csv"):
        load_measurements(str(p))


def test_csv_error_wrapped(tmp_path):
    p = tmp_path / "nul.csv"
    p.write_bytes(b'subgroup,value\n"A,1\nB,2\n')  # unterminated quote
    try:
        load_measurements(str(p))
    except ValueError as exc:
        assert "nul.csv" in str(exc)
    else:  # csv module may be lenient; then the failure is a data error elsewhere
        pytest.fail("expected ValueError")
