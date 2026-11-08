# spc-oee

Control charts (Xbar-R and I-MR), Cp/Cpk/Pp/Ppk and an OEE breakdown from two CSV files, written to a single HTML report. Python standard library only.

## Run the demo

Needs Python 3.10 or newer. Nothing to install.

```
git clone https://github.com/ahmedakmal2211-ship-it/spc-oee.git
cd spc-oee
python -m spc_oee --demo
```

Example output (paths are shown with forward slashes; on Windows they print with backslashes):

```
Xbar-R chart, 30 subgroups, n = 5
  location CL 10.0114  UCL 10.0705  LCL 9.9524
  spread   CL 0.1023  UCL 0.2162  LCL 0.0000
  sigma within 0.0440, overall 0.0542
  Cp 1.137  Cpk 1.050  Pp 0.922  Ppk 0.852  PPM 935 (estimated, assumes normality and stability)
  Flagged location points (subgroup): 12, 14, 15, 16, 17, 18, 19, 20, 24, 26, 27, 28, 29, 30  [rules R1, R2, R3, R4]
  WARNING: Process shows rule violations (not in statistical control): capability indices are only meaningful for a stable process.
OEE total: 69.7%  (A 88.9%, P 82.8%, Q 94.7%) over 14 periods; reference 85%
Wrote examples/sample_measurements.csv
Wrote examples/sample_production.csv
Report written to examples/sample_report.html
```

The demo writes two sample CSV files and the report into `examples/` (change the folder with `--out-dir`).

## Sample report

[examples/sample_report.html](examples/sample_report.html) is the report the demo produces. It is a self-contained HTML file: download it and open it in a web browser. It needs no server and no internet connection.

## Use your own data

```
python -m spc_oee MEASUREMENTS.csv [PRODUCTION.csv] [--lsl X] [--usl X] [--out report.html] [--title "My report"]
```

The production file is optional. Without it the report has no OEE section.

### Measurements CSV

Header exactly `subgroup,value`. One row per measurement. Rows with the same subgroup label form one subgroup (subgroups are ordered by first appearance).

```
subgroup,value
1,9.9529
1,10.0950
2,10.0102
2,9.9871
```

- All subgroups must be the same size, and there must be at least 2 subgroups.
- Subgroup size 2 to 10 gives an Xbar-R chart. Size 1 gives an I-MR chart. Larger than 10 is rejected.

### Production CSV

Header exactly `period,planned_time_min,downtime_min,ideal_cycle_time_min,total_count,good_count`. One row per shift or period.

```
period,planned_time_min,downtime_min,ideal_cycle_time_min,total_count,good_count
Mon-AM,480,45,0.5,780,741
```

- `ideal_cycle_time_min` is minutes per unit.
- `total_count` and `good_count` must be whole numbers, and `good_count` cannot exceed `total_count`.
- `downtime_min` must be between 0 and `planned_time_min`. Period names must be unique.

Bad input stops with a one-line error naming the file and row, and exit code 2.

### Flags

| Flag | Meaning |
|---|---|
| `--lsl X` | Lower specification limit. Enables capability indices. |
| `--usl X` | Upper specification limit. Enables capability indices. |
| `--out FILE` | HTML report path. Default `report.html` (with `--demo`: `<out-dir>/sample_report.html`). |
| `--title TEXT` | Report title. |
| `--demo` | Generate synthetic sample CSVs and a report. |

Also available: `--out-dir DIR` (folder for `--demo` output, default `examples`) and `--version`.

Give one or both of `--lsl` and `--usl`. With only one, Cp and Pp are not reported (n/a) and Cpk/Ppk use the side you gave. If both are given, LSL must be less than USL.

## Definitions

### Control limits

Limits are set at plus and minus 3 sigma of the plotted statistic.

Xbar-R chart (subgroup size n = 2 to 10), with Xbar-bar the mean of subgroup means and Rbar the mean subgroup range:

- Xbar chart: CL = Xbar-bar, UCL/LCL = Xbar-bar +/- A2 x Rbar
- R chart: CL = Rbar, UCL = D4 x Rbar, LCL = D3 x Rbar
- sigma within = Rbar / d2

I-MR chart (n = 1), with MRbar the mean moving range of span 2:

- I chart: CL = mean, UCL/LCL = mean +/- 2.660 x MRbar (2.660 = 3 / 1.128)
- MR chart: CL = MRbar, UCL = 3.267 x MRbar, LCL = 0
- sigma within = MRbar / 1.128

The constants A2, D3, D4 and d2 are the standard tabulated factors in Montgomery, *Introduction to Statistical Quality Control*, Appendix VI. They are in `spc_oee/constants.py`.

### Run rules

Western Electric / Nelson rules, as implemented. Sigma here is (UCL - CL) / 3 of the location chart.

| Rule | Signal |
|---|---|
| R1 | One point beyond 3 sigma (outside UCL or LCL). |
| R2 | Two of three consecutive points beyond 2 sigma, same side of CL. |
| R3 | Four of five consecutive points beyond 1 sigma, same side of CL. |
| R4 | Eight consecutive points on one side of CL. A point exactly on CL breaks the run. Flagged from the 8th point onward. |

R1 to R4 are applied to the Xbar (or I) chart. The R and MR charts use R1 only (above UCL, or below LCL when LCL is above 0).

### Capability

With specification limits LSL and USL and the grand mean:

- Cp = (USL - LSL) / (6 x sigma within)
- Cpk = min[(USL - mean) / (3 x sigma within), (mean - LSL) / (3 x sigma within)]
- Pp and Ppk: the same formulas using sigma overall, the sample standard deviation of all values (n - 1 denominator)
- PPM out of spec: normal distribution tail areas outside the limits, using sigma within and the grand mean

### OEE

Per period:

- Run time = planned time - downtime
- Availability = run time / planned time
- Performance = (ideal cycle time x total count) / run time
- Quality = good count / total count
- OEE = Availability x Performance x Quality

The TOTAL row sums times and counts over all periods and then forms the ratios. It does not average the per-period ratios.

The 85% "world-class" figure shown as a reference is an industry convention associated with TPM. It is not a standard. Use it as a rough guide only.

## Limitations

- Rules R2 and R3 are also evaluated on partial windows at the start of the series (for example 2 of the first 2 points), so early points can be flagged before a full 3- or 5-point window exists.

- Limits are Phase I limits: calculated from all the data you supply, including any out-of-control points. They are not fixed limits from a prior stable baseline.
- PPM is an estimate that assumes the data is normally distributed (and stable).
- Capability indices are only meaningful for a stable process. The tool prints a warning when any rule fires.
- Performance above 100% is flagged with a warning and is not capped. It usually means the ideal cycle time is set too slow.
- The sample data is synthetic. The generator is tuned so the demo shows the run rules firing. The demo numbers are not a benchmark for any real process.

## Tests

```
python -m pip install pytest
python -m pytest -q
```

Current result: 89 passed.

## Licence

MIT. See [LICENSE](LICENSE).

## Author

Akmal Azeem
