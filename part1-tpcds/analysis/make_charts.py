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
- Scaling charts only use the queries that are `ok` at every SF.
- Concurrency efficiency = Sq * T_Power / T_TT1 (Sq = 1: no gain; Sq = perfect overlap).

Figures (--out, default report/part1/figures), one question each:
  load_by_sf.png           stacked bars  how long does the load take (INSERT + OPTIMIZE FINAL)?
  query_times_sf<REF>.png  bars          how long does each query take? (15 slowest + the rest)
  scaling_total.png        line          does the total time grow like the data?
  scaling_queries.png      bars          which queries grow faster than the data? (15 that grow most)
  concurrency.png          line          how much faster are the streams in parallel?
  cold_warm_sf<REF>.png    dumbbell      how much faster are the slowest queries with the data in memory?
Every title states the conclusion; axes are in plain seconds (no log scales).
Tables (--out/tables): summary_by_sf.csv (with size on disk and compression), per_query.csv,
failures.csv. Size, failures and run-to-run spread go in tables and text, not in charts.
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
    stmts["error"] = stmts["error"].fillna("").astype(str)
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
        ax.text(i, v / 60, duration(v), ha="center", va="bottom", color=INK2, fontsize=8)
    ax.set_xticks(x, [sf_label(v) for v in s.sf])
    narrow(ax, len(s))
    ax.set_ylim(0, s.t_load_s.max() / 60 * 1.15)
    ax.set_ylabel("T_Load (min)")
    last = s.iloc[-1]
    ax.set_title(f"Loading {sf_label(last.sf)} takes {duration(last.t_load_s)}, "
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
        ax.text(v, yi, f"  {duration(v)} ({v / total:.0%})", va="center", fontsize=8, color=INK2)
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


def common_queries(pq):
    wide = pq.pivot(index="query", columns="sf", values="time_s")
    return wide.dropna()


def fig_scaling_total(pq, out):
    """Line: measured total time per SF against the dashed grey line of growth exactly like the data."""
    common = common_queries(pq)
    sfs = list(common.columns)
    total = common.sum()
    linear = total.iloc[0] * pd.Series(sfs) / sfs[0]
    fig, ax = plt.subplots(figsize=(5.2, 3.5))
    ax.plot(sfs, linear, "--", color=MUTED, linewidth=1.2, label="if time grew exactly like the data")
    ax.plot(sfs, total, "o-", color=BLUE, linewidth=2, markersize=6, label="measured")
    for sf, v in zip(sfs, total):
        ax.annotate(duration(v), (sf, v), xytext=(4, -12), textcoords="offset points", ha="left",
                    fontsize=8, color=INK2)
    ax.set_xticks(sfs, [f"SF {v:g}" for v in sfs])
    ax.set_ylim(0, max(total.max(), linear.max()) * 1.15)
    ax.set_ylabel("Sum of the query times (s)")
    growth, k = total.iloc[-1] / total.iloc[0], sfs[-1] / sfs[0]
    ax.set_title(f"{k:g}x more data, {growth:.1f}x more time ({len(common)} queries ok at every SF)")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left")
    save(fig, out / "scaling_total.png")


def fig_scaling_queries(pq, out, worse=1.2, top_n=15):
    """Bars: the queries whose time grows the most from the smallest to the largest SF, against the
    dashed line of growth exactly like the data. Blue = clearly faster than the data (> 20% above)."""
    common = common_queries(pq)
    lo, hi = common.columns[0], common.columns[-1]
    k = hi / lo
    ratio = (common[hi] / common[lo]).sort_values(ascending=False)
    bad = ratio[ratio > k * worse]
    g = ratio.head(top_n)[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 0.3 * len(g) + 1.4))
    y = list(range(len(g)))
    ax.barh(y, g, color=[BLUE if v > k * worse else MUTED for v in g], height=0.65)
    ax.axvline(k, color=MUTED, linestyle="--", linewidth=1.2)
    ax.text(k, len(g) - 0.4, f" data x{k:g}", color=INK2, fontsize=8, va="bottom")
    for yi, v in zip(y, g):
        ax.text(v, yi, f"  x{v:.1f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [f"Q{q}" for q in g.index])
    ax.set_xlim(0, g.max() * 1.18)
    ax.set_ylim(-0.6, len(g) + 0.4)
    ax.set_xlabel(f"Time at SF {hi:g} / time at SF {lo:g}")
    ax.set_title(f"The {len(g)} queries whose time grows the most from SF {lo:g} to SF {hi:g}")
    ax.grid(axis="y", visible=False)
    save(fig, out / "scaling_queries.png")
    return ratio.sort_values(), bad


def fig_concurrency(summary, out):
    """Line: how many times faster the streams run in parallel than one after another, per SF,
    between the two reference values 1 (no gain) and Sq (best possible)."""
    s = summary.dropna(subset=["concurrency_efficiency"]).sort_values("sf")
    if s.empty:
        print("  concurrency.png skipped: no throughput test in summary.json")
        return
    sq = int(s.streams.iloc[0])
    fig, ax = plt.subplots(figsize=(5.2, 3.3))
    edge = ax.get_yaxis_transform()   # x in axes fraction, y in data units
    for yv, txt in ((1, "1 = no gain"), (sq, f"{sq} = best possible")):
        ax.axhline(yv, color=MUTED, linestyle="--", linewidth=1.1)
        ax.text(0.01, yv + 0.05, txt, transform=edge, fontsize=8, color=INK2)
    x = [sf_label(v) for v in s.sf]
    ax.plot(x, s.concurrency_efficiency, "o-", color=BLUE, linewidth=2, markersize=6)
    for i, e in enumerate(s.concurrency_efficiency):
        ax.annotate(f"x{e:.1f} faster", (i, e), xytext=(0, 8), textcoords="offset points", ha="center",
                    fontsize=8, color=INK)
    ax.set_ylim(0, sq + 0.7)
    ax.set_ylabel(f"Speed-up of {sq} streams in parallel")
    ax.set_title(f"Running {sq} streams at once is about x{s.concurrency_efficiency.median():.1f} faster")
    ax.grid(axis="x", visible=False)
    save(fig, out / "concurrency.png")


def fig_cold_warm(pq, ref, out, n=10):
    """Dumbbell: cold (blue, first run) and warm (orange, data already in memory) per query,
    joined by a grey line; the label is how much faster the warm run is."""
    d = pq[(pq.sf == ref) & pq.cold_s.notna() & pq.warm_median_s.notna()]
    if d.empty:
        print(f"  cold_warm_sf{ref:g}.png skipped: needs cold and warm runs")
        return
    d = d.nlargest(n, "warm_median_s").iloc[::-1]
    fig, ax = plt.subplots(figsize=(6.3, 0.36 * len(d) + 1.5))
    y = list(range(len(d)))
    ax.hlines(y, d[["cold_s", "warm_median_s"]].min(axis=1), d[["cold_s", "warm_median_s"]].max(axis=1),
              color=GRID_DARK, linewidth=3, zorder=1)
    ax.scatter(d.cold_s, y, s=45, color=BLUE, zorder=3, label="cold (first run)")
    ax.scatter(d.warm_median_s, y, s=45, color=ORANGE, zorder=3, label="warm (data already in memory)")
    right = d[["cold_s", "warm_median_s"]].max(axis=1)
    for yi, r, c, w in zip(y, right, d.cold_s, d.warm_median_s):
        txt = f"{(c - w) / c:.0%} faster warm" if w < c else f"{(w - c) / c:.0%} slower warm"
        ax.text(r, yi, f"   {txt}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [f"Q{q}" for q in d["query"]])
    ax.set_xlim(0, right.max() * 1.45)
    ax.set_xlabel("Time (s)")
    gain = ((d.cold_s - d.warm_median_s) / d.cold_s).median()
    ax.set_title(f"With the data in memory, the slowest queries run about {gain:.0%} faster "
                 f"({sf_label(ref)})", pad=24)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, borderaxespad=0.2)
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
    if len(common_queries(pq).columns) >= 2:
        fig_scaling_total(pq, out)
        ratio, bad = fig_scaling_queries(pq, out)
    else:
        print("  scaling_total.png, scaling_queries.png skipped: need at least 2 SFs")
    fig_concurrency(summary, out)
    fig_cold_warm(pq, ref, out)

    fails = ex[ex.status != "ok"][["sf", "test", "repeat", "stream", "query", "status", "error"]]
    summary.to_csv(out / "tables" / "summary_by_sf.csv", index=False)
    pq.to_csv(out / "tables" / "per_query.csv", index=False, float_format="%.4f")
    fails.to_csv(out / "tables" / "failures.csv", index=False)
    print(f"tables: {out / 'tables'} (summary_by_sf, per_query, failures)")

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
        print(f"growth from the smallest to the largest SF: median x{ratio.median():.1f}, "
              f"range x{ratio.min():.1f} (Q{ratio.index[0]}) to x{ratio.max():.1f} (Q{ratio.index[-1]})")
        print(f"growing clearly faster than the data: {len(bad)} queries "
              f"({', '.join(f'Q{q}' for q in bad.sort_values(ascending=False).index)})")
    if loads is not None:
        print("size on disk: " + ", ".join(f"{sf_label(a)} {b:.1f} GiB (x{c:.1f} compression)" for a, b, c in
                                           zip(summary.sf, summary.size_on_disk_gib, summary.compression_ratio)))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
