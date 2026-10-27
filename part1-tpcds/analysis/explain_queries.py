#!/usr/bin/env python3
"""Execution plans of the slowest queries, for the Discussion (section 8).

For each query: EXPLAIN (plan with index usage), the join and aggregation steps found in it, and
one run with the values ClickHouse records in system.query_log (time, rows and bytes read, peak
memory). Uses the same settings profile as the harness (part1-tpcds/settings.json).

  python3 part1-tpcds/analysis/explain_queries.py --sf 50                       # Q72 Q93 Q69 Q23 Q67
  python3 part1-tpcds/analysis/explain_queries.py --sf 50 --only 72,93 --no-run   # plans only

Needs ClickHouse running, the SF loaded (load.py) and its query streams (gen_queries.py streams
--sf <SF>). By default it runs stream 0, data/queries/sf<SF>/query_0.sql, i.e. the queries with the
parameters measured in the power test. Writes data/explain/sf<SF>/:
  qNN_plan.txt   EXPLAIN indexes = 1 of each statement (how many parts/granules the primary key keeps)
  summary.csv    one row per statement: time, rows read, bytes read, peak memory, result rows,
                 number of joins, largest estimated join result (rows), tables read
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "part1-tpcds" / "scripts"))
from harness import ClickHouse, load_queries, load_settings, new_query_id  # noqa: E402

SLOWEST = [72, 93, 69, 23, 67]   # the 5 slowest at SF 50 in the trial run (power test)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sf", type=float, default=1)
    p.add_argument("--only", help="templates, e.g. 72,93 (default: %s)" % ",".join(map(str, SLOWEST)))
    p.add_argument("--queries", help="stream file or folder of qNN.sql (default: data/queries/sf<SF>/query_0.sql)")
    p.add_argument("--out", help="default: data/explain/sf<SF>")
    p.add_argument("--no-run", action="store_true", help="only EXPLAIN, do not run the queries")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8123)
    p.add_argument("--user", default="default")
    p.add_argument("--password", default=os.environ.get("CLICKHOUSE_PASSWORD", "infoh419"))
    p.add_argument("--settings", default=str(REPO / "part1-tpcds" / "settings.json"))
    args = p.parse_args()

    wanted = [int(x) for x in args.only.split(",")] if args.only else SLOWEST
    db = f"tpcds_sf{args.sf:g}"
    out = Path(args.out or REPO / "data" / "explain" / f"sf{args.sf:g}")
    out.mkdir(parents=True, exist_ok=True)
    ch = ClickHouse(args.host, args.port, args.user, args.password, db, load_settings(args.settings), 3600)

    source = args.queries or REPO / "data" / "queries" / f"sf{args.sf:g}" / "query_0.sql"
    if not Path(source).exists():
        sys.exit(f"{source} not found (run gen_queries.py streams --sf {args.sf:g} first)")
    queries = {q.template: q for q in load_queries([source])}
    missing = [n for n in wanted if n not in queries]
    if missing:
        sys.exit(f"not found in {source}: {missing}")

    rows = []
    for n in wanted:
        q = queries[n]
        plans = []
        for part, sql in enumerate(q.statements, 1):
            name = f"q{n:02d}" + (f"_{part}" if len(q.statements) > 1 else "")
            r = ch.execute(f"EXPLAIN indexes = 1\n{sql}", new_query_id("explain", name), keep_body=True)
            if r.status != "ok":
                print(f"{name}: EXPLAIN failed: {r.error}")
                continue
            plan = r.body.decode("utf-8")
            plans.append(f"===== {name}\n{plan}")
            joins = len(re.findall(r"Join \(JOIN", plan))
            tables = sorted(set(re.findall(r"ReadFromMergeTree \((?:\w+\.)?(\w+)\)", plan)))
            est = [int(x) for x in re.findall(r"Result rows: (\d+)", plan)]
            row = {"statement": name, "joins": joins, "tables_read": " ".join(tables),
                   "largest_join_estimate": max(est) if est else None}
            if not args.no_run:
                qid = new_query_id("explain-run", name)
                res = ch.execute(sql, qid)
                stats = ch.server_stats([qid]).get(qid, {})
                row.update({"status": res.status, "elapsed_s": round(res.elapsed_s, 3),
                            "read_rows": stats.get("read_rows"), "read_bytes": stats.get("read_bytes"),
                            "peak_memory_mib": round(stats["peak_memory_bytes"] / 2**20, 1)
                            if stats.get("peak_memory_bytes") else None,
                            "result_rows": stats.get("result_rows"), "error": res.error})
            rows.append(row)
            print(f"{name:7s} joins={joins:2d}  " + "  ".join(
                f"{k}={row[k]}" for k in ("elapsed_s", "peak_memory_mib", "read_rows") if k in row))
        (out / f"q{n:02d}_plan.txt").write_text("\n".join(plans), encoding="utf-8")

    fields = ["statement", "status", "elapsed_s", "read_rows", "read_bytes", "peak_memory_mib",
              "result_rows", "joins", "largest_join_estimate", "tables_read", "error"]
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nplans and summary.csv in {out}")


if __name__ == "__main__":
    main()
