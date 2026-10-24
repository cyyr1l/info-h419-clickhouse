#!/usr/bin/env python3
"""Load one TPC-DS scale factor into ClickHouse (role 1).

  python3 part1-tpcds/scripts/load.py --sf 1

Steps:
  1. read data/tpcds/sf<SF>/manifest.json, written by gen_data.py (files and row counts);
  2. drop and recreate the database tpcds_sf<SF> (the name the harness expects), so every
     load starts from empty tables (schema.sql uses CREATE TABLE IF NOT EXISTS, which would
     silently keep old tables);
  3. run part1-tpcds/ddl/schema.sql (role 3) in that database;
  4. load the 24 tables: ClickHouse reads the .dat files itself with the file() table
     function (data/ is mounted read-only in the container, see docker-compose.yml), so the
     load time is ClickHouse's parsing and writing time, not Python's;
  5. check that every table has exactly the row count of the manifest.

To time it as the load test (T_Load, followed by OPTIMIZE ... FINAL on every table):

  python3 part1-tpcds/scripts/harness.py load --sf 1 -- python3 part1-tpcds/scripts/load.py --sf 1

How the .dat files are parsed (dsdgen -TERMINATE N): CSV with '|' as delimiter, no quoting
(the data contains no quotes), spaces kept as they are, and an empty field becomes NULL in a
Nullable column (its default value). Standard library only.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "part1-tpcds" / "ddl" / "schema.sql"

# Settings sent with every INSERT (as URL parameters of the HTTP interface).
CSV_SETTINGS = {
    "format_csv_delimiter": "|",
    "format_csv_allow_double_quotes": 0,      # the data has no quoting
    "format_csv_allow_single_quotes": 0,
    "input_format_csv_trim_whitespaces": 0,   # keep the raw values, trailing spaces included
    "input_format_csv_empty_as_default": 1,   # empty field -> column default (NULL if Nullable)
    "input_format_csv_detect_header": 0,      # the files have no header line
    "input_format_allow_errors_num": 0,       # any bad row fails the load
    "input_format_allow_errors_ratio": 0,
}


def fmt_sf(sf):
    return str(int(sf)) if float(sf).is_integer() else str(sf)


class ClickHouse:
    """Minimal client for ClickHouse's HTTP interface."""

    def __init__(self, host, port, user, password, timeout=24 * 3600):
        self.url = f"http://{host}:{port}/"
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}
        self.timeout = timeout

    def query(self, sql, database=None, settings=None):
        params = {"wait_end_of_query": 1}       # errors come back as an HTTP error status
        if database:
            params["database"] = database
        params.update(settings or {})
        req = urllib.request.Request(self.url + "?" + urllib.parse.urlencode(params),
                                     data=sql.encode(), headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace").strip()) from None
        except urllib.error.URLError as e:
            sys.exit(f"cannot reach ClickHouse at {self.url} ({e.reason}): "
                     "start it with  cd docker && docker compose up -d")


def schema_statements(path):
    """CREATE TABLE statements of schema.sql (comment lines removed, split on ';')."""
    text = "\n".join(l for l in path.read_text().splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sf", type=int, required=True, help="scale factor, e.g. 10")
    p.add_argument("--database", help="default: tpcds_sf<SF>")
    p.add_argument("--schema", type=Path, default=SCHEMA, help="default: part1-tpcds/ddl/schema.sql")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8123)
    p.add_argument("--user", default="default")
    p.add_argument("--password", default="infoh419")
    p.add_argument("--allow-failed-manifest", action="store_true",
                   help="load even if gen_data.py reported problems (not for measured runs)")
    args = p.parse_args(argv)

    sf = fmt_sf(args.sf)
    db = args.database or f"tpcds_sf{sf}"
    data_rel = f"data/tpcds/sf{sf}"                 # relative to the container's user_files/
    manifest_path = REPO / data_rel / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"{manifest_path} not found: run  python3 part1-tpcds/scripts/gen_data.py --sf {sf}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "ok" and not args.allow_failed_manifest:
        sys.exit(f"gen_data.py reported problems for SF {sf} (see {manifest_path}): regenerate first")
    tables = manifest["tables"]

    ch = ClickHouse(args.host, args.port, args.user, args.password)
    version = ch.query("SELECT version()").strip()
    print(f"== ClickHouse {version}: loading SF {sf} into {db}")

    t_start = time.perf_counter()
    ch.query(f"DROP DATABASE IF EXISTS {db} SYNC")
    ch.query(f"CREATE DATABASE {db}")
    for stmt in schema_statements(args.schema):
        ch.query(stmt, database=db)
    created = set(ch.query(f"SELECT name FROM system.tables WHERE database = '{db}'").split())
    if created != set(tables):
        sys.exit(f"schema.sql created {sorted(created)}, but the manifest has {sorted(tables)}")
    t_ddl = time.perf_counter()

    # smallest tables first, so a format problem shows up quickly
    timings = {}
    for t in sorted(tables, key=lambda t: tables[t]["bytes"]):
        files = tables[t]["files"]
        pattern = f"{data_rel}/{files[0]}" if len(files) == 1 else \
            f"{data_rel}/{{{','.join(files)}}}"
        structure = ch.query(
            "SELECT arrayStringConcat(groupArray(concat(name, ' ', type)), ', ') "
            f"FROM (SELECT name, type FROM system.columns WHERE database = '{db}' "
            f"AND table = '{t}' ORDER BY position)").strip()
        t0 = time.perf_counter()
        try:
            ch.query(f"INSERT INTO {t} SELECT * FROM file('{pattern}', 'CSV', '{structure}')",
                     database=db, settings=CSV_SETTINGS)
        except RuntimeError as e:
            sys.exit(f"!! loading {t} failed:\n{e}")
        timings[t] = time.perf_counter() - t0
        print(f"   {t:24s} {tables[t]['rows']:>13,} rows  {timings[t]:8.1f} s  ({len(files)} file(s))")
    t_end = time.perf_counter()

    # row counts (not part of the load time, spec 7.4.3.8.1f)
    problems = []
    for t in sorted(tables):
        n = int(ch.query(f"SELECT count() FROM {t}", database=db))
        if n != tables[t]["rows"]:
            problems.append(f"{t}: {n:,} rows in ClickHouse, {tables[t]['rows']:,} in the files")
    print(f"== DDL {t_ddl - t_start:.1f} s, data {t_end - t_ddl:.1f} s, "
          f"total {t_end - t_start:.1f} s (OPTIMIZE FINAL is run by the harness)")
    if problems:
        print(f"!! {len(problems)} row count mismatch(es):")
        for pr in problems:
            print(f"   - {pr}")
        sys.exit(1)
    print(f"== OK: 24 tables loaded into {db}, all row counts match the manifest")


if __name__ == "__main__":
    main()
