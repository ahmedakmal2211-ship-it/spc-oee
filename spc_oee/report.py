"""One-page, fully self-contained HTML report (inline CSS + hand-drawn SVG).

``build_report(spc, oee, meta) -> str`` returns a complete HTML document with
no external scripts, fonts, images or network references. Every user-derived
string is passed through :func:`html.escape`.

``spc`` is an SpcResult, ``oee`` an OeeResult or None, ``meta`` a dict (read
with ``.get``): title, lsl, usl, measurements_file, production_file, version,
synthetic.
"""

from __future__ import annotations

import html
import math
import os

DASH = "—"
SIGMA = "σ"

_LIGHT = """--bg:#ffffff;--card:#f6f7f9;--ink:#1b1f24;--ink2:#4a525c;--muted:#6b7480;
--grid:#d9dde3;--line:#9aa3ae;--data:#0b5cad;--bad:#c2410c;--bad-bg:#fdeee6;
--good:#0b5cad;--c-down:#c2410c;--c-speed:#b07a00;--c-qual:#7b3fa0;--c-prod:#0b5cad;
--warn-bg:#fff4d6;--warn-bd:#b07a00;"""
_DARK = """--bg:#14171b;--card:#1d2127;--ink:#e8ebef;--ink2:#b4bcc6;--muted:#8d97a3;
--grid:#363c45;--line:#7b8591;--data:#5aa9f0;--bad:#ff9a62;--bad-bg:#3a2417;
--good:#5aa9f0;--c-down:#ff9a62;--c-speed:#e8b93c;--c-qual:#c39be6;--c-prod:#5aa9f0;
--warn-bg:#3a3014;--warn-bd:#e8b93c;"""

_CSS = (
    ":root{" + _LIGHT + "color-scheme:light dark}"
    "@media (prefers-color-scheme:dark){:root{" + _DARK + "}}"
    """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.2em 0 .1em;line-height:1.25;overflow-wrap:anywhere}
h2{font-size:1.1rem;margin:1.6em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--grid)}
h3{font-size:.95rem;margin:1em 0 .3em;color:var(--ink2)}
p{margin:.4em 0}
.summary{font-size:1.02rem;color:var(--ink2)}
.pill{display:inline-block;padding:0 .5em;border-radius:.8em;font-weight:600;border:1px solid currentColor}
.pill.ok{color:var(--good)}.pill.bad{color:var(--bad)}
.note{font-size:.85rem;color:var(--muted)}
.warn{background:var(--warn-bg);border-left:4px solid var(--warn-bd);padding:.5em .8em;margin:.6em 0;border-radius:4px}
.warn.strong{font-weight:600}
.chart{background:var(--card);border-radius:8px;padding:6px;margin:.4em 0 1em}
svg{display:block;width:100%;height:auto;font-family:inherit}
svg text{fill:var(--ink2);font-size:13px}
svg .t-muted{fill:var(--muted)}
svg .t-bad{fill:var(--bad);font-weight:700;font-size:11px}
svg .t-ink{fill:var(--ink)}
svg .halo{stroke:var(--card);stroke-width:3;paint-order:stroke}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{padding:.35em .6em;border-bottom:1px solid var(--grid);text-align:right;vertical-align:top}
th{color:var(--ink2);font-weight:600;white-space:nowrap}
th:first-child,td:first-child,td.l,th.l{text-align:left}
tr.total td{font-weight:700;border-top:2px solid var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:.3em 1.2em;margin:.3em 0;padding:0;list-style:none;font-size:.88rem}
.legend li{display:flex;align-items:center;gap:.4em}
.sw{display:inline-block;width:12px;height:12px;border-radius:2px}
.key svg{display:inline-block;width:14px;height:14px;vertical-align:-2px}
footer{margin-top:2em;padding-top:.6em;border-top:1px solid var(--grid);font-size:.82rem;color:var(--muted);overflow-wrap:anywhere}
@media (max-width:520px){svg text{font-size:15px}svg .t-bad{font-size:14px}.halo{stroke-width:4}}
@media print{
:root{""" + _LIGHT + """}
body{font-size:11px}main{max-width:none;padding:0}
.chart,.warn{break-inside:avoid}h2{break-after:avoid}
}
"""
)


def esc(v) -> str:
    return html.escape(str(v), quote=True)


def _n(v, dp: int) -> str:
    """Format a number with dp decimals, em dash for None/non-finite."""
    if v is None:
        return DASH
    try:
        if not math.isfinite(v):
            return DASH
    except TypeError:
        return esc(v)
    return f"{v:.{dp}f}"


def _pct(v, dp: int = 1) -> str:
    if v is None or not math.isfinite(v):
        return DASH
    return f"{v * 100:.{dp}f}%"


def _min(v) -> str:
    return DASH if v is None else f"{v:,.1f}"


def _fx(v: float) -> str:
    return f"{v:.1f}"


# --------------------------------------------------------------------------
# Control chart SVG
# --------------------------------------------------------------------------

def _nice_ticks(lo: float, hi: float, target: int = 5):
    span = hi - lo
    if not span > 0:
        return [lo]
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=mag)
    start = math.ceil(lo / step - 1e-9) * step
    ticks, v = [], start
    while v <= hi + 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _tick_fmt(ticks) -> int:
    if len(ticks) < 2:
        return 2
    step = abs(ticks[1] - ticks[0])
    if step <= 0:
        return 2
    return max(0, min(6, int(math.ceil(-math.log10(step) - 1e-9)) + (0 if step >= 1 else 0)))


def control_chart_svg(points, x_index, labels, cl, ucl, lcl, flagged, *,
                      zones: bool, y_title: str, aria: str, n_total: int,
                      sigma: float = 0.0) -> str:
    """Hand-drawn SVG. ``x_index[j]`` is the subgroup position of point j.
    ``flagged`` maps point index -> sorted list of rule ids."""
    W, H = 600, 300
    ml, mr, mt, mb = 56, 104, 16, 44
    pw, ph = W - ml - mr, H - mt - mb

    vals = list(points) + [cl, ucl, lcl]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad

    def X(i):
        if n_total <= 1:
            return ml + pw / 2
        return ml + pw * i / (n_total - 1)

    def Y(v):
        return mt + ph * (hi - v) / (hi - lo)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'role="img" aria-label="{esc(aria)}">']
    out.append(f"<title>{esc(aria)}</title>")

    # y ticks + grid
    ticks = _nice_ticks(lo, hi)
    dp = _tick_fmt(ticks)
    for t in ticks:
        y = Y(t)
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{_fx(y)}" y2="{_fx(y)}" '
                   f'stroke="var(--grid)" stroke-width="0.6" opacity="0.7"/>')
        out.append(f'<text class="t-muted" x="{ml - 6}" y="{_fx(y + 4)}" text-anchor="end">'
                   f'{t:.{dp}f}</text>')
    # axes
    out.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt + ph}" stroke="var(--line)"/>')
    out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="var(--line)"/>')

    # x ticks (thinned)
    max_ticks = 10
    step = max(1, math.ceil(n_total / max_ticks))
    for i in range(0, n_total, step):
        x = X(i)
        out.append(f'<line x1="{_fx(x)}" x2="{_fx(x)}" y1="{mt + ph}" y2="{mt + ph + 4}" stroke="var(--line)"/>')
        lab = str(labels[i])
        if len(lab) > 8:
            lab = lab[:7] + "…"
        out.append(f'<text class="t-muted" x="{_fx(x)}" y="{mt + ph + 18}" text-anchor="middle">{esc(lab)}</text>')
    out.append(f'<text x="{ml + pw / 2}" y="{H - 6}" text-anchor="middle">Subgroup</text>')
    out.append(f'<text x="14" y="{mt + ph / 2}" text-anchor="middle" '
               f'transform="rotate(-90 14 {mt + ph / 2})">{esc(y_title)}</text>')

    # zone lines (dashed 1 and 2 sigma)
    if zones and sigma > 0:
        for k in (1, 2):
            for sgn in (1, -1):
                v = cl + sgn * k * sigma
                sgnch = "+" if sgn > 0 else "−"
                y = Y(v)
                out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{_fx(y)}" y2="{_fx(y)}" '
                           f'stroke="var(--muted)" stroke-width="1" stroke-dasharray="4 4"/>')
                out.append(f'<text class="t-muted" x="{ml + pw + 6}" y="{_fx(y + 4)}" '
                           f'font-size="11">{sgnch}{k}{SIGMA}</text>')

    # CL / UCL / LCL
    for name, v, dash, col in (("UCL", ucl, "", "var(--bad)"),
                               ("CL", cl, "", "var(--ink2)"),
                               ("LCL", lcl, "", "var(--bad)")):
        y = Y(v)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{_fx(y)}" y2="{_fx(y)}" '
                   f'stroke="{col}" stroke-width="1.5"{da}/>')
        ty = y - 5 if name == "LCL" else (y + 14 if name == "UCL" else y + 4)
        out.append(f'<text class="t-ink" x="{ml + pw + 6}" y="{_fx(ty)}">{name} {v:.4f}</text>')

    # data line
    pts = " ".join(f"{_fx(X(x_index[j]))},{_fx(Y(p))}" for j, p in enumerate(points))
    out.append(f'<polyline points="{pts}" fill="none" stroke="var(--data)" stroke-width="1.5" '
               f'stroke-linejoin="round"/>')

    # markers
    for j, p in enumerate(points):
        x, y = X(x_index[j]), Y(p)
        lab = labels[x_index[j]]
        if j in flagged:
            rules = ", ".join(flagged[j])
            r = 7.5
            d = f"{_fx(x)},{_fx(y - r)} {_fx(x + r)},{_fx(y)} {_fx(x)},{_fx(y + r)} {_fx(x - r)},{_fx(y)}"
            out.append(f'<polygon class="flag" points="{d}" fill="var(--card)" stroke="var(--bad)" '
                       f'stroke-width="2.5"><title>Subgroup {esc(lab)}: {p:.4f} ({esc(rules)})</title></polygon>')
            stag = 13 * (j % 2)
            ty = y - 12 - stag if p >= cl else y + 22 + stag
            rl = ",".join(flagged[j])
            out.append(f'<text class="t-bad halo" x="{_fx(x)}" y="{_fx(ty)}" text-anchor="middle" '
                       f'font-size="11">{esc(rl)}</text>')
        else:
            out.append(f'<circle cx="{_fx(x)}" cy="{_fx(y)}" r="3.5" fill="var(--data)" '
                       f'stroke="var(--card)" stroke-width="1.5"><title>Subgroup {esc(lab)}: {p:.4f}</title></circle>')
    out.append("</svg>")
    return "".join(out)


def _flag_map(violations, offset: int = 0) -> dict:
    m: dict = {}
    for v in violations:
        m.setdefault(v.index, set()).add(v.rule)
    return {k: sorted(s) for k, s in m.items()}


# --------------------------------------------------------------------------
# OEE SVGs
# --------------------------------------------------------------------------

def oee_bars_svg(total, reference: float) -> str:
    rows = [("Availability", total.availability), ("Performance", total.performance),
            ("Quality", total.quality), ("OEE", total.oee)]
    vmax = max([1.0, reference] + [v for _, v in rows if v is not None])
    W, rowh = 600, 34
    ml, mr, mt = 100, 60, 26
    H = mt + rowh * len(rows) + 6
    pw = W - ml - mr

    def X(v):
        return ml + pw * v / vmax

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Availability, performance, quality and OEE bars with 85% reference">']
    out.append(f'<line x1="{ml}" x2="{ml}" y1="{mt - 4}" y2="{H - 4}" stroke="var(--line)"/>')
    for i, (name, v) in enumerate(rows):
        y = mt + i * rowh
        fw = ' font-weight="700"' if name == "OEE" else ""
        out.append(f'<text class="t-ink" x="{ml - 8}" y="{y + 17}" text-anchor="end"{fw}>{name}</text>')
        out.append(f'<rect x="{ml}" y="{y + 4}" width="{pw * 1.0 / vmax:.1f}" height="18" rx="3" '
                   f'fill="var(--grid)" opacity="0.5"/>')
        if v is None:
            out.append(f'<text class="t-muted" x="{ml + 6}" y="{y + 18}">{DASH} (undefined)</text>')
        else:
            w = max(0.0, X(v) - ml)
            op = "" if name == "OEE" else ' opacity="0.72"'
            out.append(f'<rect x="{ml}" y="{y + 4}" width="{w:.1f}" height="18" rx="3" '
                       f'fill="var(--c-prod)"{op}/>')
            out.append(f'<text class="t-ink halo" x="{X(v) + 6:.1f}" y="{y + 18}">{_pct(v)}</text>')
    # reference line across the whole group
    rx = X(reference)
    out.append(f'<line x1="{rx:.1f}" x2="{rx:.1f}" y1="{mt - 6}" y2="{H - 4}" stroke="var(--bad)" '
               f'stroke-width="1.5" stroke-dasharray="5 3"/>')
    anchor = "end" if reference > 0.6 * vmax else "start"
    out.append(f'<text class="t-bad" x="{rx + (-4 if anchor == "end" else 4):.1f}" y="{mt - 10}" '
               f'text-anchor="{anchor}" font-size="12">{reference * 100:.0f}% reference (convention)</text>')
    out.append("</svg>")
    return "".join(out)


def _loss_segments(total):
    segs = [("Productive time", total.productive_time, "var(--c-prod)"),
            ("Downtime loss", total.downtime_loss, "var(--c-down)"),
            ("Speed loss", total.speed_loss, "var(--c-speed)"),
            ("Quality loss", total.quality_loss, "var(--c-qual)")]
    return segs


def loss_bar_svg(total) -> str:
    segs = _loss_segments(total)
    planned = total.planned_time
    W, H = 600, 64
    ml = mr = 8
    pw = W - ml - mr
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Planned time split into productive time, downtime, speed loss and quality loss">']
    # Scale by the sum of positive segments so the bar never overflows when
    # speed loss is negative (Performance > 100%).
    scale = math.fsum(max(0.0, m) for _, m, _ in segs)
    x = float(ml)
    for name, minutes, col in segs:
        w = max(0.0, minutes) / scale * pw if scale > 0 else 0.0
        if w <= 0:
            continue
        out.append(f'<rect x="{x:.1f}" y="10" width="{max(w - 2, 0.5):.1f}" height="28" rx="3" fill="{col}">'
                   f'<title>{esc(name)}: {minutes:,.1f} min ({minutes / planned * 100:.1f}%)</title></rect>')
        if w > 46:
            out.append(f'<text x="{x + (w - 2) / 2:.1f}" y="29" text-anchor="middle" '
                       f'style="fill:#fff;font-weight:700">{minutes / planned * 100:.0f}%</text>')
        x += w
    out.append(f'<text class="t-muted" x="{ml}" y="58">0</text>')
    out.append(f'<text class="t-muted" x="{W - mr}" y="58" text-anchor="end">'
               f'{planned:,.0f} min planned</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

def _summary(spc, oee) -> str:
    stable = spc.is_stable
    nviol = len({(v.rule, v.index) for v in spc.location_violations}) + \
        len({(v.rule, v.index) for v in spc.spread_violations})
    if stable:
        s = '<span class="pill ok">&#10003; Stable</span> no run-rule violations'
    else:
        s = f'<span class="pill bad">&#9888; Not stable</span> {nviol} rule violation(s)'
    parts = [s]
    cap = spc.capability
    if cap is not None:
        parts.append(f"Cpk {_n(cap.cpk, 2)}" + ("" if stable else " (indicative only)"))
    else:
        parts.append("no spec limits given, capability not computed")
    if oee is not None:
        parts.append(f"OEE {_pct(oee.total.oee)}")
    return "<p class=\"summary\">" + "; ".join(parts) + ".</p>"


def _charts(spc) -> str:
    n = len(spc.labels)
    kind = "Xbar" if spc.chart_type == "xbar-r" else "Individuals"
    skind = "Range (R)" if spc.chart_type == "xbar-r" else "Moving range (MR)"
    loc_flag = _flag_map(spc.location_violations)
    spr_flag = _flag_map(spc.spread_violations)
    loc = control_chart_svg(
        spc.location_points, list(range(n)), spc.labels,
        spc.location_cl, spc.location_ucl, spc.location_lcl, loc_flag,
        zones=True, y_title=("Subgroup mean" if spc.chart_type == "xbar-r" else "Individual value"),
        aria=f"{kind} chart with centre line, control limits and 1 and 2 sigma zones",
        n_total=n, sigma=spc.location_sigma)
    spr = control_chart_svg(
        spc.spread_points, [i + spc.spread_offset for i in range(len(spc.spread_points))],
        spc.labels, spc.spread_cl, spc.spread_ucl, spc.spread_lcl, spr_flag,
        zones=False, y_title=("Range" if spc.chart_type == "xbar-r" else "Moving range"),
        aria=f"{skind} chart with centre line and control limits", n_total=n)
    key = ('<p class="note key"><svg viewBox="0 0 14 14" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
           '<circle cx="7" cy="7" r="3.5" fill="var(--data)"/></svg> in control &nbsp; '
           '<svg viewBox="0 0 14 14" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
           '<polygon points="7,1 13,7 7,13 1,7" fill="none" stroke="var(--bad)" stroke-width="2.5"/></svg> '
           'rule violation (labelled R1&ndash;R4). Phase I limits, estimated from this same data. '
           'Dashed grey lines are 1&sigma; and 2&sigma; zones.</p>')
    return (f"<h2>Control charts</h2>{key}"
            f"<h3>{kind} chart (location)</h3><div class=\"chart\">{loc}</div>"
            f"<h3>{skind} chart (spread)</h3><div class=\"chart\">{spr}</div>")


def _violations(spc) -> str:
    rows = []
    for chart, vs, off in (("Location", spc.location_violations, 0),
                           ("Spread", spc.spread_violations, spc.spread_offset)):
        for v in vs:
            i = v.index + off
            lab = spc.labels[i] if 0 <= i < len(spc.labels) else DASH
            rows.append(f'<tr><td class="l">{esc(v.rule)}</td><td class="l">{chart}</td>'
                        f'<td class="l">{esc(lab)}</td><td class="l">{esc(v.description)}</td></tr>')
    if not rows:
        return "<h2>Violations</h2><p>No run-rule violations (R1&ndash;R4 on location, R1 on spread).</p>"
    return ("<h2>Violations</h2><div class=\"tablewrap\"><table><thead><tr>"
            "<th class=\"l\">Rule</th><th class=\"l\">Chart</th><th class=\"l\">Subgroup</th>"
            "<th class=\"l\">Description</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def _capability(spc) -> str:
    cap = spc.capability
    if cap is None:
        return ("<h2>Capability</h2><p>No specification limits were supplied, so capability "
                "indices were not computed.</p>")
    parts = ["<h2>Capability</h2>"]
    if not spc.is_stable:
        parts.append('<div class="warn strong" role="alert">Process is not in statistical control. '
                     'Capability indices are only meaningful for a stable process; treat these '
                     'values as indicative only.</div>')
    parts.append(f'<p class="note">LSL {_n(cap.lsl, 4)}, USL {_n(cap.usl, 4)}; mean {_n(cap.mean, 4)}; '
                 f'{SIGMA} within {_n(cap.sigma_within, 4)}, {SIGMA} overall {_n(cap.sigma_overall, 4)}.</p>')
    cells = [("Cp", _n(cap.cp, 2)), ("CPU", _n(cap.cpu, 2)), ("CPL", _n(cap.cpl, 2)),
             ("Cpk", _n(cap.cpk, 2)), ("Pp", _n(cap.pp, 2)), ("Ppk", _n(cap.ppk, 2)),
             ("Est. PPM", DASH if cap.ppm_total is None else f"{cap.ppm_total:,.0f}")]
    head = "".join(f"<th>{esc(k)}</th>" for k, _ in cells)
    body = "".join(f"<td>{v}</td>" for _, v in cells)
    parts.append(f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
                 f'<tbody><tr>{body}</tr></tbody></table></div>')
    parts.append(f'<p class="note">PPM: {esc(cap.ppm_note)}.</p>')
    for w in cap.warnings:
        parts.append(f'<div class="warn">{esc(w)}</div>')
    return "".join(parts)


def _oee(oee) -> str:
    t = oee.total
    parts = ["<h2>OEE</h2>",
             "<h3>Availability, Performance, Quality (all periods)</h3>",
             f'<div class="chart">{oee_bars_svg(t, oee.world_class_reference)}</div>',
             f'<p class="note">{esc(oee.world_class_note)}</p>',
             "<h3>Where the planned time went</h3>",
             f'<div class="chart">{loss_bar_svg(t)}</div>']
    planned = t.planned_time
    items = []
    for name, minutes, col in _loss_segments(t):
        pct = f"{minutes / planned * 100:.1f}%" if planned > 0 else DASH
        extra = " (negative: performance above 100%)" if minutes < 0 else ""
        items.append(f'<li><span class="sw" style="background:{col}"></span>'
                     f'{esc(name)}: {minutes:,.1f} min, {pct}{extra}</li>')
    parts.append('<ul class="legend">' + "".join(items) + "</ul>")

    head = ("<th class=\"l\">Period</th><th>Planned (min)</th><th>Downtime (min)</th>"
            "<th>Avail.</th><th>Perf.</th><th>Qual.</th><th>OEE</th><th class=\"l\">Warnings</th>")
    body = []
    for r in list(oee.rows) + [t]:
        cls = ' class="total"' if r is t else ""
        w = "; ".join(esc(x) for x in r.warnings) if r.warnings else ""
        body.append(f"<tr{cls}><td>{esc(r.period)}</td><td>{_min(r.planned_time)}</td>"
                    f"<td>{_min(r.downtime)}</td><td>{_pct(r.availability)}</td>"
                    f"<td>{_pct(r.performance)}</td><td>{_pct(r.quality)}</td>"
                    f"<td>{_pct(r.oee)}</td><td class=\"l\">{w}</td></tr>")
    parts.append("<h3>Per period</h3><div class=\"tablewrap\"><table><thead><tr>" + head +
                 "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")
    return "".join(parts)


def _footer(meta) -> str:
    bits = []
    mf, pf = meta.get("measurements_file"), meta.get("production_file")
    if mf:
        bits.append(f"Measurements: {esc(os.path.basename(str(mf)))}")
    if pf:
        bits.append(f"Production: {esc(os.path.basename(str(pf)))}")
    ver = meta.get("version")
    bits.append(f"spc-oee {esc(ver)}" if ver else "spc-oee")
    if meta.get("synthetic"):
        bits.append("Synthetic demo data")
    return "<footer>" + " &middot; ".join(bits) + "</footer>"


def build_report(spc, oee, meta) -> str:
    meta = meta or {}
    title = esc(meta.get("title") or "SPC and OEE report")
    sections = [f"<h1>{title}</h1>", _summary(spc, oee)]
    for w in spc.warnings:
        # the capability warning is shown prominently in the capability section
        if spc.capability is not None and w in spc.capability.warnings:
            continue
        sections.append(f'<div class="warn">{esc(w)}</div>')
    sections += [_charts(spc), _violations(spc), _capability(spc)]
    if oee is not None:
        sections.append(_oee(oee))
    sections.append(_footer(meta))
    body = "\n".join(sections)
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<meta name=\"color-scheme\" content=\"light dark\">"
            f"<title>{title}</title><style>{_CSS}</style></head>\n"
            f"<body><main>\n{body}\n</main></body></html>\n")
