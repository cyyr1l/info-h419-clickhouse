#!/usr/bin/env python3
"""Charts and tables for the Results section (Part I), from the harness output.

Reads part1-tpcds/results/sf<SF>/<run_id>/ (power.csv, throughput.csv, power_cold.csv,
power_warm.csv, load.csv, summary.json; see scripts/README_harness.md) and writes PNG figures
and CSV tables. Every figure is generated here, never edited by hand.

  pip install pandas matplotlib
  python3 part1-tpcds/analysis/make_charts.py                  # latest run of every SF
  python3 part1-tpcds/analysis/make_charts.py --run 50=20261024-235925 --ref-sf 50

Rules (agreed in issue #5):
- A query's time is the sum of its statements (Q14, Q23, Q24, Q39 have two).
- Failed or timed-out executions are left out of every time and median, and listed in failures.csv.
- Warm time = median of the warm power runs (min and max shown as whiskers). Without warm runs,
  the single power run is used instead, and the output says so.
- Scaling charts only use the queries that are `ok` at every SF, and leave out the queries that
  return 0 rows in stream 0 at some SFs but not at others (their times are not comparable); the
  output and a note under each chart name them.
- Concurrency efficiency = Sq * T_Power / T_TT1 (Sq = 1: no gain; Sq = perfect overlap).

Figures (--out, default report/part1/figures), one question each:
  load_by_sf.png           stacked bars  how long does the load take (INSERT + OPTIMIZE FINAL)?
  query_times_sf<REF>.png  bars          how long does each query take? (15 slowest + the rest)
  scaling_total.png        line          does the total time grow like the data?
  scaling_queries.png      bars          which queries grow faster than the data? (15 that grow most)
  concurrency.png          grouped bars  how much faster are the streams at the same time than one after another?
  cold_warm_sf<REF>.png    bars (+/- %)  do the slowest queries run faster in the warm runs than in the cold run?
Every title states the conclusion; axes are in plain seconds (no log scales).
Tables (--out/tables): summary_by_sf.csv (with size on disk and compression), per_query.csv,
failures.csv, row_checks.csv (methodology 6.6: same row count in every run of stream 0; 0-row
statements flagged). Size, failures and run-to-run spread go in tables and text, not in charts.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TESTS = ["power", "throughput", "power_cold", "power_warm"]

# Colors (each one means something, the same in every figure):
#   grey  = context (all queries, reference lines)   blue = what the text talks about / cold
#   orange = warm (temperature metaphor)             red  = failure only, always with an x marker
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, CRITICAL = "#2a78d6", "#eb6834", "#d03b3b"
BLUE_DARK, BLUE_LIGHT = "#1c5cab", "#86b6ef"   # two steps of the blue ramp: two phases of one process
GRID_DARK = "#c3c2b7"                          # connecting lines and min-max ranges

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
    "figure.facecolor": "white", "axes.facecolor": "white",
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "legend.frameon": False, "legend.fontsize": 8.5,
})


def seconds(v, _=None):
    """Tick label for a log time axis: 0.1 s, 10 s, 1000 s."""
    return f"{v:g} s"


def duration(v):
    """Value label next to a mark: 0.42 s, 61.0 s, 3.6 min."""
    if v >= 120:
        return f"{v / 60:.1f} min"
    return f"{v:.2f} s" if v < 1 else f"{v:.1f} s"


def secs(v):
    """Value label in seconds, whatever the size: 0.42 s, 9.6 s, 205.8 s."""
    return f"{v:.2f} s" if v < 1 else f"{v:.1f} s"


def factor(k):
    """Scale-factor ratio: x4.17, x2.5 (no 4.16667)."""
    return f"x{k:.2f}".rstrip("0").rstrip(".")


def note(ax, text, y=-0.16):
    """Small grey note under the plot, e.g. which queries were left out and why. Wrapped to the
    width of the plot, so it never sticks out on the right of the figure."""
    import textwrap
    width_in = ax.get_position().width * ax.figure.get_figwidth()
    chars = int(width_in * 18)              # about 18 characters per inch at 7.5 pt
    lines = [textwrap.fill(par, chars) for par in " ".join(text.split("\n")).split("\n\n")]
    ax.text(0, y, "\n".join(lines), transform=ax.transAxes, va="top", ha="left", fontsize=7.5, color=INK2)


def narrow(ax, n, horizontal=False):
    """Keep bars thin when there are only 1-2 categories."""
    lim = (-0.8, max(n, 3) - 0.2)
    (ax.set_ylim if horizontal else ax.set_xlim)(*lim)


def sf_label(sf):
    return f"SF {sf:g}"


# ---------------------------------------------------------------- loading

def pick_runs(results, chosen):
    """{sf: run directory}. Default: the latest run_id (by name) of each SF that has a power.csv."""
    runs = {}
    for d in sorted(results.glob("sf*")):
        try:
            sf = float(d.name[2:])
        except ValueError:
            continue
        cands = sorted(r for r in d.iterdir() if r.is_dir() and (r / "power.csv").exists())
        if sf in chosen:
            match = [r for r in cands if r.name == chosen[sf]]
            if not match:
                sys.exit(f"run {chosen[sf]} not found in {d}")
            runs[sf] = match[0]
        elif cands:
            runs[sf] = cands[-1]
    if not runs:
        sys.exit(f"no run with a power.csv under {results}")
    return runs


def load_runs(runs):
    stmts, loads, summaries = [], [], {}
    for sf, d in runs.items():
        for t in TESTS:
            f = d / f"{t}.csv"
            if f.exists():
                df = pd.read_csv(f)
                df["sf"] = sf
                stmts.append(df)
        if (d / "load.csv").exists():
            df = pd.read_csv(d / "load.csv")
            df["sf"] = sf
            loads.append(df)
        summaries[sf] = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    stmts = pd.concat(stmts, ignore_index=True)
    stmts["error"] = stmts["error"].astype(object).fillna("").astype(str)
    return stmts, (pd.concat(loads, ignore_index=True) if loads else None), summaries


def executions(stmts):
    """One row per execution of a query (its statements summed)."""
    g = stmts.groupby(["sf", "test", "repeat", "stream", "query"], as_index=False)
    ex = g.agg(elapsed_s=("elapsed_s", "sum"), server_ms=("server_ms", "sum"),
               read_bytes=("read_bytes", "sum"), peak_memory_bytes=("peak_memory_bytes", "max"),
               parts=("part", "count"), n_ok=("status", lambda s: (s == "ok").sum()),
               status=("status", lambda s: "ok" if (s == "ok").all() else s[s != "ok"].iloc[0]),
               error=("error", lambda s: next((e for e in s if e), "")))
    return ex


def per_query(ex):
    """Per (sf, query): power, cold, warm median/min/max and spread, over ok executions only."""
    ok = ex[ex.status == "ok"]
    out = ex[["sf", "query"]].drop_duplicates().set_index(["sf", "query"]).sort_index()
    for test, col in (("power", "power_s"), ("power_cold", "cold_s")):
        s = ok[ok.test == test].groupby(["sf", "query"]).elapsed_s.median()
        out[col] = s
    w = ok[ok.test == "power_warm"].groupby(["sf", "query"]).elapsed_s
    out["warm_median_s"], out["warm_min_s"], out["warm_max_s"] = w.median(), w.min(), w.max()
    out["warm_runs_ok"] = w.count()
    out["warm_spread"] = (out.warm_max_s - out.warm_min_s) / out.warm_median_s
    srv = ok[ok.test.isin(["power_warm", "power"])].groupby(["sf", "query"])
    out["server_ms_median"] = srv.server_ms.median()
    out["peak_memory_gib"] = srv.peak_memory_bytes.max() / 2**30
    bad = ex[ex.status != "ok"].groupby(["sf", "query"]).test.apply(lambda s: ",".join(sorted(set(s))))
    out["failed_in"] = bad
    out["failed_in"] = out["failed_in"].fillna("")
    # the time used in the charts: warm median, else the power run
    out["time_s"] = out.warm_median_s.fillna(out.power_s)
    return out.reset_index()


def summary_table(runs, summaries, ex, sq_default=4):
    rows = []
    for sf in sorted(runs):
        s = summaries.get(sf, {})
        load = s.get("load") or {}
        power = (s.get("power") or [{}])[0]
        tput = (s.get("throughput") or [{}])[0]
        t_power = power.get("t_power_s")
        if t_power is None:   # no summary.json: the sum of the power run (no gaps between queries)
            p = ex[(ex.sf == sf) & (ex.test == "power")]
            t_power = p.elapsed_s.sum() if len(p) else None
        sq, t_tt = tput.get("streams", sq_default), tput.get("t_tt1_s")
        eff = sq * t_power / t_tt if (t_power and t_tt) else None
        fails = ex[(ex.sf == sf) & (ex.status != "ok")]
        rows.append({"sf": sf, "run_id": runs[sf].name,
                     "t_load_s": load.get("t_load_s"), "load_s": load.get("load_s"),
                     "optimize_s": load.get("optimize_s"),
                     "t_power_s": t_power, "t_tt1_s": t_tt, "streams": sq if t_tt else None,
                     "concurrency_efficiency": eff, "failed_executions": len(fails),
                     "metric": (s.get("simplified_metric") or {}).get("value")
                     if isinstance(s.get("simplified_metric"), dict) else s.get("simplified_metric")})
    return pd.DataFrame(rows)


def row_checks(stmts):
    """Row-count checks of the methodology (section 6.6), per SQL statement, ok executions only:
    - rows_differ: stream 0 (power, cold and warm runs) must return the same result_rows in every
      run; the throughput streams use other parameters, so they are not compared;
    - zero_rows: a statement that returns 0 rows in a measured stream is flagged.
    Returns one row per flagged (sf, query, part)."""
    ok = stmts[stmts.status == "ok"].dropna(subset=["result_rows"])
    out = []
    s0 = ok[ok.stream == 0].groupby(["sf", "query", "part"]).result_rows
    diff = s0.agg(["min", "max", "count"])
    for (sf, q, part), r in diff[diff["min"] != diff["max"]].iterrows():
        out.append({"sf": sf, "query": q, "part": part, "issue": "rows_differ",
                    "detail": f"stream 0: {int(r['min'])} to {int(r['max'])} rows over {int(r['count'])} runs"})
    zero = ok[ok.result_rows == 0].groupby(["sf", "query", "part"])
    for (sf, q, part), g in zero:
        where = ", ".join(sorted({f"{t} s{int(s)}" for t, s in zip(g.test, g.stream)}))
        out.append({"sf": sf, "query": q, "part": part, "issue": "zero_rows", "detail": f"0 rows in {where}"})
    cols = ["sf", "query", "part", "issue", "detail"]
    return pd.DataFrame(out, columns=cols).sort_values(["issue", "sf", "query", "part"]) if out \
        else pd.DataFrame(columns=cols)


def mixed_zero_rows(stmts):
    """Queries that return 0 rows in stream 0 at some SFs but not at others ({query: [those SFs]}).
    An empty result is cheap to compute, so their time is not comparable across SFs: the query does
    different work. The scaling charts leave them out and say so. A query that is empty at every SF
    (e.g. Q8) stays in, since it is compared with itself."""
    ok = stmts[(stmts.status == "ok") & (stmts.stream == 0)].dropna(subset=["result_rows"])
    empty = ok.groupby(["sf", "query"]).result_rows.min().eq(0).unstack("sf").fillna(False)
    mixed = empty[empty.any(axis=1) & ~empty.all(axis=1)]
    return {int(q): [sf for sf in mixed.columns if mixed.loc[q, sf]] for q in mixed.index}


def excluded_text(excl):
    """Short note for under the scaling charts; the SFs of each query are in the output and in
    tables/row_checks.csv."""
    if not excl:
        return ""
    names = ", ".join(f"Q{q}" for q in excl)
    return (f"Left out: {names}. They return 0 rows at some scale factors but not at others, "
            f"so their times are not comparable across scale factors (see tables/row_checks.csv).")


# ---------------------------------------------------------------- figures

def save(fig, path):
    fig.savefig(path)
    plt.close(fig)
    print(f"  {path}")


def log_seconds(ax, axis="y"):
    """Log time axis: ticks at 1-2-5 steps, or only at powers of 10 when the range is wide."""
    a = ax.yaxis if axis == "y" else ax.xaxis
    lo, hi = (ax.get_ylim() if axis == "y" else ax.get_xlim())
    wide = hi / max(lo, 1e-9) > (1e4 if axis == "y" else 1e3)
    a.set_major_locator(LogLocator(subs=(1,) if wide else (1, 2, 5)))
    a.set_major_formatter(FuncFormatter(seconds))
    a.set_minor_formatter(NullFormatter())


def fig_load(summary, out):
    """Stacked bars: two phases of one process, two shades of one hue."""
    s = summary.dropna(subset=["t_load_s"]).sort_values("sf")
    if s.empty:
        print("  load_by_sf.png skipped: no T_Load in summary.json")
        return
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    x = list(range(len(s)))
    ld, op = s.load_s.fillna(0) / 60, s.optimize_s.fillna(0) / 60
    ax.bar(x, ld, width=0.55, color=BLUE_DARK, label="Load (INSERT)")
    ax.bar(x, op, width=0.55, bottom=ld, color=BLUE_LIGHT, edgecolor="white", linewidth=1.5,
           label="OPTIMIZE FINAL")
    for i, v in zip(x, s.t_load_s):
        ax.text(i, v / 60, f"{v / 60:.1f} min", ha="center", va="bottom", color=INK2, fontsize=8)
    ax.set_xticks(x, [sf_label(v) for v in s.sf])
    narrow(ax, len(s))
    ax.set_ylim(0, s.t_load_s.max() / 60 * 1.15)
    ax.set_ylabel("Load time (min)")
    last = s.iloc[-1]
    ax.set_title(f"Loading {sf_label(last.sf)} takes {last.t_load_s / 60:.1f} min, "
                 f"{last.optimize_s / last.t_load_s:.0%} of it in OPTIMIZE")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left")   # same order as the stack
    ax.grid(axis="x", visible=False)
    save(fig, out / "load_by_sf.png")


def fig_query_times(pq, ref, warm, out, top_n=15):
    """Horizontal bars: the slowest queries one by one (blue), all the others together (grey).
    Linear seconds and the share of the total, so it reads without knowing log scales."""
    d = pq[pq.sf == ref]
    ok = d[d.time_s.notna()].sort_values("time_s", ascending=False)
    failed = d[d.time_s.isna()]
    top, rest = ok.head(top_n), ok.iloc[top_n:]
    total = ok.time_s.sum()
    share = top.time_s.sum() / total
    labels = [f"Q{q}" for q in top["query"]] + ([f"the other {len(rest)} queries"] if len(rest) else [])
    values = list(top.time_s) + ([rest.time_s.sum()] if len(rest) else [])
    colors = [BLUE] * len(top) + [MUTED] * (len(values) - len(top))
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(values) + 1.4))
    y = list(range(len(values)))[::-1]
    ax.barh(y, values, color=colors, height=0.65)
    for yi, v in zip(y, values):
        ax.text(v, yi, f"  {secs(v)} ({v / total:.0%})", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(values) * 1.3)
    ax.set_xlabel("Time (s)")
    what = "median of the warm runs" if warm else "single power run"
    ax.set_title(f"{len(top)} of the {len(d)} queries take {share:.0%} of the total time "
                 f"({sf_label(ref)}, {what})")
    if len(failed):
        ax.text(0, -0.1, "Failed (no time): " + ", ".join(f"Q{q}" for q in failed["query"]),
                transform=ax.transAxes, va="top", fontsize=8.5, color=CRITICAL)
    ax.grid(axis="y", visible=False)
    save(fig, out / f"query_times_sf{ref:g}.png")
    return share


def common_queries(pq, exclude=()):
    """Queries with a time at every SF, minus the excluded ones (see mixed_zero_rows)."""
    wide = pq.pivot(index="query", columns="sf", values="time_s")
    return wide.dropna().drop(index=list(exclude), errors="ignore")


def fig_scaling_total(pq, excl, out):
    """Line: measured total time per SF against the dashed grey line of growth exactly like the data."""
    common = common_queries(pq, excl)
    sfs = list(common.columns)
    total = common.sum() / 60                       # minutes, like the point labels
    linear = total.iloc[0] * pd.Series(sfs) / sfs[0]
    fig, ax = plt.subplots(figsize=(5.6, 3.5))
    ax.plot(sfs, linear, "--", color=MUTED, linewidth=1.2, label="if the time grew like the data")
    ax.plot(sfs, total, "o-", color=BLUE, linewidth=2, markersize=6, label="measured")
    for i, (sf, v) in enumerate(zip(sfs, total)):
        # above-left of each point, away from both lines; the first one below-right (axis on its left)
        xy, ha, va = ((6, -6), "left", "top") if i == 0 else ((-6, 6), "right", "bottom")
        ax.annotate(f"{v:.1f} min", (sf, v), xytext=xy, textcoords="offset points",
                    ha=ha, va=va, fontsize=8, color=INK2)
    ax.set_xticks(sfs, [sf_label(v) for v in sfs])
    ax.set_xlim(sfs[0] - (sfs[-1] - sfs[0]) * 0.12, sfs[-1] + (sfs[-1] - sfs[0]) * 0.05)
    ax.set_ylim(0, max(total.max(), linear.max()) * 1.15)
    ax.set_ylabel(f"Total time of the {len(common)} queries (min)")
    growth, k = total.iloc[-1] / total.iloc[0], sfs[-1] / sfs[0]
    ax.set_title(f"{factor(k)[1:]}x more data, {growth:.1f}x more time ({sf_label(sfs[0])} to {sf_label(sfs[-1])})")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left")
    if excl:
        note(ax, excluded_text(excl), y=-0.13)
    save(fig, out / "scaling_total.png")
    return growth


def fig_scaling_queries(pq, excl, out, worse=1.2, top_n=15, min_s=1.0):
    """Bars: the queries whose time grows the most from the smallest to the largest SF, against the
    dashed line of growth exactly like the data. Each label also gives the two times, because a large
    factor on a tiny time does not matter. Blue = takes at least `min_s` at the largest SF (it weighs
    in the total time); grey = shorter, so a large factor adds little time."""
    common = common_queries(pq, excl)
    lo, hi = common.columns[0], common.columns[-1]
    k = hi / lo
    ratio = (common[hi] / common[lo]).sort_values(ascending=False)
    bad = ratio[ratio > k * worse]
    g = ratio.head(top_n)[::-1]
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(g) + 1.9))
    y = list(range(len(g)))
    heavy = [common.loc[q, hi] >= min_s for q in g.index]
    ax.barh(y, g, color=[BLUE if h else MUTED for h in heavy], height=0.65)
    ax.axvline(k, color=INK2, linestyle="--", linewidth=1.2)
    ax.text(k, len(g) - 0.4, f" same growth as the data ({factor(k)})", color=INK2, fontsize=8, va="bottom")
    for yi, q, v in zip(y, g.index, g):
        ax.text(v, yi, f"  x{v:.1f}  ({secs(common.loc[q, lo])} → {secs(common.loc[q, hi])})",
                va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [f"Q{q}" for q in g.index])
    ax.set_xlim(0, g.max() * 1.45)
    ax.set_ylim(-0.6, len(g) + 0.6)
    ax.set_xlabel(f"How many times longer the query takes at {sf_label(hi)} than at {sf_label(lo)}")
    top = g.index[-1]
    ax.set_title(f"{len(bad)} queries grow clearly faster than the data; Q{top} the most (x{g.iloc[-1]:.0f})")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label=f"takes {min_s:g} s or more at {sf_label(hi)}"),
                       Patch(color=MUTED, label=f"under {min_s:g} s at {sf_label(hi)}: large factor, little time")],
              loc="lower right")
    ax.grid(axis="y", visible=False)
    if excl:
        note(ax, excluded_text(excl), y=-0.1)
    save(fig, out / "scaling_queries.png")
    return ratio.sort_values(), bad


def fig_concurrency(summary, out):
    """Grouped bars, in minutes: the Sq streams run one after another (estimated as Sq x T_Power,
    light grey, since it is not measured) against the same streams run at the same time (T_TT1,
    measured, blue). The label above the blue bar is how many times faster that is."""
    s = summary.dropna(subset=["concurrency_efficiency"]).sort_values("sf")
    if s.empty:
        print("  concurrency.png skipped: no throughput test in summary.json")
        return
    sq = int(s.streams.iloc[0])
    seq, par = sq * s.t_power_s / 60, s.t_tt1_s / 60
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    x = list(range(len(s)))
    w = 0.38
    ax.bar([i - w / 2 for i in x], seq, width=w, color=GRID_DARK,
           label=f"one after another (estimated: {sq} x power test)")
    ax.bar([i + w / 2 for i in x], par, width=w, color=BLUE, label="at the same time (measured)")
    mins = lambda v: f"{v:.1f}" if v < 10 else f"{v:.0f}"
    for i, a, b in zip(x, seq, par):
        ax.text(i - w / 2, a, mins(a), ha="center", va="bottom", fontsize=8, color=INK2)
        ax.text(i + w / 2, b, mins(b), ha="center", va="bottom", fontsize=8, color=INK)
    # the speed-up goes under each SF, where it cannot collide with the bar labels
    ax.set_xticks(x, [f"{sf_label(v)}\nx{e:.1f} faster" for v, e in zip(s.sf, s.concurrency_efficiency)])
    ax.set_ylim(0, seq.max() * 1.2)
    ax.set_ylabel(f"Time to run the {sq} query streams (min)")
    last = s.iloc[-1]
    ax.set_title(f"Running the {sq} streams at the same time: {last.t_tt1_s / 60:.0f} min instead of "
                 f"{sq * last.t_power_s / 60:.0f} at {sf_label(last.sf)}")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    note(ax, f"Each stream runs the 99 queries. 'One after another' is estimated from the power test (stream 0);\n"
             f"streams 1-{sq} use other query parameters, so the speed-up is an approximation.", y=-0.2)
    save(fig, out / "concurrency.png")


def fig_cold_warm(pq, ref, out, n=10):
    """Diverging bars: for the slowest queries, the warm median compared with the cold run, in %,
    around 0 (same time); the grey line is the range of the warm runs."""
    d = pq[(pq.sf == ref) & pq.cold_s.notna() & pq.warm_median_s.notna()]
    if d.empty:
        print(f"  cold_warm_sf{ref:g}.png skipped: needs cold and warm runs")
        return
    d = d.nlargest(n, "warm_median_s").iloc[::-1]
    # the message is the difference, so the difference is what is drawn: warm vs cold in %,
    # around a 0 line (0 = same time). Orange bar = warm median; grey line = range of the warm runs.
    pct = (d.warm_median_s - d.cold_s) / d.cold_s * 100
    lo = (d.warm_min_s - d.cold_s) / d.cold_s * 100
    hi = (d.warm_max_s - d.cold_s) / d.cold_s * 100
    fig, ax = plt.subplots(figsize=(6.3, 0.36 * len(d) + 1.7))
    y = list(range(len(d)))
    ax.barh(y, pct, color=ORANGE, height=0.55, zorder=2)
    ax.hlines(y, lo, hi, color=INK2, linewidth=1.2, zorder=3)
    ax.axvline(0, color=INK2, linewidth=1)
    lim = max(abs(lo).max(), abs(hi).max(), 10) * 1.35
    for yi, p, a, b, c in zip(y, pct, lo, hi, d.cold_s):
        edge = max(b, p) if p >= 0 else min(a, p)
        ax.text(edge, yi, f"  {p:+.0f}%  " if p >= 0 else f"  {p:+.0f}%  ", va="center",
                ha="left" if p >= 0 else "right", fontsize=8, color=INK2)
    ax.set_yticks(y, [f"Q{q} ({secs(c)} cold)" for q, c in zip(d["query"], d.cold_s)])
    ax.set_xlim(-lim, lim)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%" if v else "0"))
    ax.set_xlabel("Warm time compared with the cold time\n← faster when warm        slower when warm →")
    med = pct.median()
    ax.set_title(f"Cold and warm runs take almost the same time (median {med:+.0f}%, {sf_label(ref)})")
    nw = int(d.warm_runs_ok.max())
    note(ax, f"The {len(d)} slowest queries. Bar: median of the {nw} warm runs compared with the cold run. "
             f"Line: range of the {nw} warm runs.",
         y=-0.2)
    ax.grid(axis="y", visible=False)
    save(fig, out / f"cold_warm_sf{ref:g}.png")


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default=str(REPO / "part1-tpcds" / "results"))
    p.add_argument("--out", default=str(REPO / "report" / "part1" / "figures"))
    p.add_argument("--run", action="append", default=[], metavar="SF=RUN_ID",
                   help="use this run for this SF (default: the latest run of each SF)")
    p.add_argument("--ref-sf", type=float, help="reference SF (default: the largest)")
    args = p.parse_args(argv)

    chosen = {}
    for item in args.run:
        sf, _, rid = item.partition("=")
        chosen[float(sf)] = rid
    runs = pick_runs(Path(args.results), chosen)
    out = Path(args.out)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    print("runs used:")
    for sf, d in sorted(runs.items()):
        print(f"  {sf_label(sf):7s} {d}")

    stmts, loads, summaries = load_runs(runs)
    ex = executions(stmts)
    pq = per_query(ex)
    summary = summary_table(runs, summaries, ex)
    ref = args.ref_sf or max(runs)
    if ref not in runs:
        sys.exit(f"no run for the reference SF {ref:g}")
    warm = (ex.test == "power_warm").any()
    if not warm:
        print("note: no warm runs (power_warm.csv): the charts use the single power run")

    if loads is not None:
        size = loads.groupby("sf")[["bytes_on_disk", "uncompressed_bytes"]].sum()
        summary["size_on_disk_gib"] = summary.sf.map(size.bytes_on_disk / 2**30)
        summary["compression_ratio"] = summary.sf.map(size.uncompressed_bytes / size.bytes_on_disk)

    print("figures:")
    fig_load(summary, out)
    share = fig_query_times(pq, ref, warm, out)
    ratio = bad = None
    excl = mixed_zero_rows(stmts)
    if len(common_queries(pq).columns) >= 2:
        fig_scaling_total(pq, excl, out)
        ratio, bad = fig_scaling_queries(pq, excl, out)
    else:
        print("  scaling_total.png, scaling_queries.png skipped: need at least 2 SFs")
    fig_concurrency(summary, out)
    fig_cold_warm(pq, ref, out)

    fails = ex[ex.status != "ok"][["sf", "test", "repeat", "stream", "query", "status", "error"]]
    summary.to_csv(out / "tables" / "summary_by_sf.csv", index=False)
    pq.to_csv(out / "tables" / "per_query.csv", index=False, float_format="%.4f")
    fails.to_csv(out / "tables" / "failures.csv", index=False)
    checks = row_checks(stmts)
    checks.to_csv(out / "tables" / "row_checks.csv", index=False)
    print(f"tables: {out / 'tables'} (summary_by_sf, per_query, failures, row_checks)")

    # numbers to quote in the text
    r = pq[pq.sf == ref]
    print(f"\nat {sf_label(ref)}: {r.time_s.notna().sum()} queries with a time, "
          f"{(r.failed_in != '').sum()} with a failure; failed executions in total: {len(fails)}")
    top = r.nlargest(5, "time_s")
    print("slowest: " + ", ".join(f"Q{q} {t:.1f} s" for q, t in zip(top["query"], top.time_s)))
    print(f"share of the 15 slowest in the total: {share:.0%}")
    if r.warm_spread.notna().any():
        print(f"warm spread (max-min)/median: median {r.warm_spread.median():.1%}, "
              f"max {r.warm_spread.max():.1%} (Q{int(r.loc[r.warm_spread.idxmax(), 'query'])})")
    if ratio is not None:
        if excl:
            print("left out of the scaling charts (0 rows in stream 0 at some SFs only): " +
                  "; ".join(f"Q{q} at {', '.join(sf_label(x) for x in sfs)}" for q, sfs in excl.items()))
        print(f"growth from the smallest to the largest SF: median x{ratio.median():.1f}, "
              f"range x{ratio.min():.1f} (Q{ratio.index[0]}) to x{ratio.max():.1f} (Q{ratio.index[-1]})")
        print(f"growing clearly faster than the data: {len(bad)} queries "
              f"({', '.join(f'Q{q}' for q in bad.sort_values(ascending=False).index)})")
    if loads is not None:
        print("size on disk: " + ", ".join(f"{sf_label(a)} {b:.1f} GiB (x{c:.1f} compression)" for a, b, c in
                                           zip(summary.sf, summary.size_on_disk_gib, summary.compression_ratio)))
    n_diff, n_zero = (checks.issue == "rows_differ").sum(), (checks.issue == "zero_rows").sum()
    print(f"row checks (methodology 6.6): {n_diff} statements with different row counts in stream 0, "
          f"{n_zero} returning 0 rows" + (" -> see tables/row_checks.csv" if len(checks) else ""))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
