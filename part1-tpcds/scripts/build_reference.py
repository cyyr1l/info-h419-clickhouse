"""Build the TPC-DS reference answers with DuckDB.

Loads the same dsdgen .dat files that ClickHouse uses, runs the original
qualification queries and saves one CSV per query (q01.csv, q14_1.csv, ...).

Usage:  python build_reference.py <dat_dir> <queries_dir> <output_dir>
  dat_dir      folder with the 24 .dat files (dsdgen -TERMINATE N)
  queries_dir  folder with q01.sql ... q99.sql (dsqgen -QUALIFY Y, netezza dialect)
  output_dir   where the reference CSVs are written
  ddl          (optional) the kit's tools/tpcds.sql; default: tpcds.sql next to this script
"""
import re
import sys
import time
from pathlib import Path

import duckdb

dat_dir, q_dir, out = map(Path, sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)

ddl = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(__file__).with_name("tpcds.sql")
con = duckdb.connect()                      # in-memory database
# create the 24 tables from the official kit DDL (constraints dropped: not needed, slower load)
ddl_sql = re.sub(r",\s*primary key\s*\([^)]*\)", "", ddl.read_text(), flags=re.I)
con.execute(ddl_sql)
tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}

# --- load: dsdgen -TERMINATE N, so no trailing '|' on each line
for f in sorted(dat_dir.glob("*.dat")):
    t = re.sub(r"_\d+_\d+$", "", f.stem)    # in case data was generated with -PARALLEL
    if t not in tables:
        continue
    spec = {c[0]: c[1] for c in con.execute(f"DESCRIBE {t}").fetchall()}
    con.execute(f"INSERT INTO {t} SELECT * FROM read_csv('{f}', delim='|', header=false, "
                f"quote='', escape='', columns={spec})")
for t in sorted(tables):
    print(f"{t:25s} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>10,}")

# --- minimal fixes so the original queries run on DuckDB (documented in queries/CHANGES.md)
FIXES = {
    # kit 4.0.0 template says c_last_review_date_sk, but the kit DDL column is c_last_review_date
    "q30": [(r"\bc_last_review_date_sk\b", "c_last_review_date")],
    # 'returns' is a reserved word in DuckDB -> rename the alias
    "q77": [(r"\breturns\b", "returns_")],
    # 'at' is a reserved word in DuckDB -> rename the subquery alias
    "q90": [(r"\)\s+at,", ") at_,")],
}

# --- run the queries
failed = []
for qf in sorted(q_dir.glob("q*.sql")):
    sql = qf.read_text()
    for pattern, repl in FIXES.get(qf.stem, []):
        sql = re.sub(pattern, repl, sql)
    sql = re.sub(r"(?<![\w'])(\d+) days\b", r"INTERVAL \1 DAY", sql)
    stmts = [s.strip() for s in sql.split(";") if s.strip()]
    for i, s in enumerate(stmts, 1):        # Q14, Q23, Q24, Q39 have 2 statements
        name = qf.stem + (f"_{i}" if len(stmts) > 1 else "")
        try:
            t0 = time.time()
            con.execute(s).df().to_csv(out / f"{name}.csv", index=False)
            print(f"{name:7s} OK     {time.time() - t0:6.2f}s")
        except Exception as e:
            failed.append(name)
            print(f"{name:7s} ERROR  {str(e).splitlines()[0]}")
print(f"\n{len(failed)} failed: {failed}")
