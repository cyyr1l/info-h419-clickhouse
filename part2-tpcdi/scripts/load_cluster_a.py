#!/usr/bin/env python3
"""Historical Load of cluster A at one scale factor, with checks.

Creates (or recreates) the cluster A tables and their staging tables in the database
(default tpcdi_sf<SF>), runs etl/cluster_a_historical.sql on Batch1, then checks the row
counts against the source files and DIGen's *_audit.csv, and the SCD2 versions of
DimCompany and DimSecurity (unique keys, one current version, contiguous dates).

Usage (from the repository root, ClickHouse running):
  python3 part2-tpcdi/scripts/load_cluster_a.py --sf 10

DImessages belongs to cluster D. If it does not exist yet, it is created with the
definition used by the cluster C test, so that the DimCompany alerts can be written.

Standard library only.
"""

import argparse
import csv
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PART2 = REPO / "part2-tpcdi"

TABLES = ["DimDate", "DimTime", "Industry", "StatusType", "TaxRate", "TradeType", "DimBroker",
          "DimCompany", "DimSecurity", "Financial",
          "stg_FinWire", "stg_FinWire_CMP", "stg_FinWire_SEC", "stg_FinWire_FIN"]

DIMESSAGES = """CREATE TABLE IF NOT EXISTS DImessages (MessageDateAndTime DateTime64(3), BatchID UInt32,
    MessageSource Nullable(String), MessageText String, MessageType String, MessageData Nullable(String))
ENGINE = MergeTree ORDER BY (BatchID, MessageDateAndTime)"""

# Reference tables: same number of rows as their source file.
REFERENCE_FILES = {"DimDate": "Date.txt", "DimTime": "Time.txt", "Industry": "Industry.txt",
                   "StatusType": "StatusType.txt", "TaxRate": "TaxRate.txt", "TradeType": "TradeType.txt"}


class ClickHouse:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/")
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}

    def query(self, sql, database=None, params=None):
        args = {"database": database} if database else {}
        args.update({"param_" + k: str(v) for k, v in (params or {}).items()})
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(args),
                                         data=sql.encode(), headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                return response.read().decode().strip()
        except urllib.error.HTTPError as error:
            message = error.read().decode().strip()
            raise RuntimeError(f"{message}\n--- in query:\n{sql[:1500]}") from None
        except urllib.error.URLError as error:
            raise SystemExit(f"cannot reach ClickHouse at {self.url}/ ({error.reason}): "
                             "start it with 'cd docker && docker compose up -d'") from None


def statements(text):
    """Split SQL on ';'. Full-line '--' comments are dropped; no literal may contain ';'."""
    kept = [line for line in text.splitlines() if not line.lstrip().startswith("--")]
    return [part.strip() for part in "\n".join(kept).split(";") if part.strip()]


def audit_sums(batch_dir):
    """{(DataSet, Attribute): sum of Value} over the *_audit.csv files of one batch
    (the FINWIRE counts are split over one audit file per quarter)."""
    sums = {}
    for path in sorted(batch_dir.glob("*_audit.csv")):
        with path.open(newline="") as handle:
            rows = csv.reader(handle)
            header = [name.strip() for name in next(rows)]
            for row in rows:
                record = dict(zip(header, (cell.strip() for cell in row)))
                if record.get("Value", "") == "":
                    continue
                key = (record["DataSet"], record["Attribute"])
                sums[key] = sums.get(key, 0) + int(float(record["Value"]))
    return sums


def line_count(path):
    with path.open("rb") as handle:
        return sum(1 for line in handle if line.strip())


def contiguity_sql(table, key, sk):
    """Number of versions whose EndDate is not the EffectiveDate of the next version."""
    return (f"SELECT count() FROM (SELECT EndDate, leadInFrame(EffectiveDate, 1, toDate32('9999-12-31')) "
            f"OVER (PARTITION BY {key} ORDER BY EffectiveDate, {sk} "
            f"ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS next FROM {table}) WHERE EndDate != next")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sf", type=int, required=True)
    parser.add_argument("--database", help="default: tpcdi_sf<SF>")
    parser.add_argument("--url", default="http://localhost:8123")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="infoh419")
    args = parser.parse_args(argv)

    db = args.database or f"tpcdi_sf{args.sf}"
    rel_dir = f"data/tpcdi/sf{args.sf}/Batch1"     # relative to ClickHouse's user_files
    batch_dir = REPO / rel_dir
    if not (batch_dir.parent / "digen_report.txt").is_file():
        raise SystemExit(f"No DIGen output in {batch_dir.parent}: generate SF {args.sf} first.")
    audit = audit_sums(batch_dir)
    ch = ClickHouse(args.url, args.user, args.password)

    # Fresh tables: the Historical Load starts from empty tables.
    ch.query(f"CREATE DATABASE IF NOT EXISTS {db}")
    for table in TABLES:
        ch.query(f"DROP TABLE IF EXISTS {table} SYNC", db)
    for name in ("ddl/staging_cluster_a.sql", "ddl/cluster_a.sql"):
        for sql in statements((PART2 / name).read_text()):
            ch.query(sql, db)
    ch.query(DIMESSAGES, db)
    ch.query("DELETE FROM DImessages WHERE BatchID = 1 AND MessageSource = 'DimCompany'", db)
    print(f"Created the cluster A tables in {db}")

    total = time.perf_counter()
    for sql in statements((PART2 / "etl" / "cluster_a_historical.sql").read_text()):
        label = " ".join(sql.split()[:3])
        start = time.perf_counter()
        ch.query(sql, db, {"batch_dir": rel_dir})
        print(f"  {label:40s} {time.perf_counter() - start:7.2f} s")
    print(f"Historical Load of cluster A: {time.perf_counter() - total:.2f} s "
          "(development timing, not a measurement)")

    failures = []

    def check(name, actual, expected):
        ok = str(actual) == str(expected)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {actual}"
              + ("" if ok else f" (expected {expected})"))
        if not ok:
            failures.append(name)

    def count(table, where="1"):
        return ch.query(f"SELECT count() FROM {table} WHERE {where}", db)

    print("Checks:")
    for table, source in REFERENCE_FILES.items():
        check(f"{table} rows = lines of {source}", count(table), line_count(batch_dir / source))
    check("DimBroker rows = HR_BROKERS", count("DimBroker"), audit.get(("DimBroker", "HR_BROKERS"), "missing"))
    check("DimCompany rows = FW_CMP", count("DimCompany"), audit.get(("DimCompany", "FW_CMP"), "missing"))
    check("DimSecurity rows = FW_SEC", count("DimSecurity"), audit.get(("DimSecurity", "FW_SEC"), "missing"))
    check("Financial rows = FW_FIN", count("Financial"), audit.get(("Financial", "FW_FIN"), "missing"))

    for table, key, sk in (("DimCompany", "CompanyID", "SK_CompanyID"),
                           ("DimSecurity", "Symbol", "SK_SecurityID")):
        check(f"{table} {sk} unique", ch.query(f"SELECT count() - uniqExact({sk}) FROM {table}", db), 0)
        check(f"{table} one current version per {key}",
              ch.query(f"SELECT count() FROM (SELECT {key} FROM {table} GROUP BY {key} "
                       f"HAVING countIf(IsCurrent) != 1)", db), 0)
        check(f"{table} IsCurrent = (EndDate = 9999-12-31)",
              count(table, "IsCurrent != (EndDate = toDate32('9999-12-31'))"), 0)
        check(f"{table} versions contiguous", ch.query(contiguity_sql(table, key, sk), db), 0)
        check(f"{table} Status in Active/Inactive", count(table, "Status NOT IN ('Active', 'Inactive')"), 0)

    print("Information:")
    print("  invalid SPrating alerts in DImessages:",
          count("DImessages", "BatchID = 1 AND MessageSource = 'DimCompany'"))
    for table in ("DimCompany", "DimSecurity"):
        print(f"  {table} versions with EffectiveDate = EndDate (same-day changes):",
              count(table, "EffectiveDate = EndDate"))

    if failures:
        raise SystemExit(f"FAILED: {len(failures)} check(s)")
    print(f"OK  cluster A historical load of SF {args.sf} in {db}")


if __name__ == "__main__":
    sys.exit(main())
