#!/usr/bin/env python3
"""Load the cluster B source files of one TPC-DI batch into staging.

  Batch1:      CustomerMgmt.xml -> stg_CustomerMgmt   (converted here, ClickHouse cannot read XML)
               Prospect.csv     -> stg_Prospect       (etl/staging_prospect.sql)
  Batch2 / 3:  Prospect.csv     -> stg_Prospect

Usage (from the repository root, ClickHouse running):
  python3 part2-tpcdi/scripts/load_staging_cluster_b.py --sf 10 --init
  python3 part2-tpcdi/scripts/load_staging_cluster_b.py --sf 10 --batch 2

--init creates the database (default tpcdi_sf<SF>) if needed and (re)creates the two
staging tables from ddl/staging_cluster_b.sql. Without it, the tables must exist.

The XML is streamed (iterparse): one row per <TPCDI:Action>, in file order (ActionSeq),
sent to ClickHouse as JSONEachRow, so NULL (absent) and '' (present but empty) stay
distinct. Values are never trimmed. Any element or attribute the loader does not know
makes it fail. After loading, the row counts are checked against DIGen's *_audit.csv.

Standard library only.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PART2 = REPO / "part2-tpcdi"
NS = "{http://www.tpc.org/tpc-di}"

# Columns of stg_CustomerMgmt after ActionSeq, ActionType, ActionTS (same order as the DDL).
PHONE_FIELDS = ["C_CTRY_CODE", "C_AREA_CODE", "C_LOCAL", "C_EXT"]
COLUMNS = (
    ["C_ID", "C_TAX_ID", "C_GNDR", "C_TIER", "C_DOB",
     "C_L_NAME", "C_F_NAME", "C_M_NAME",
     "C_ADLINE1", "C_ADLINE2", "C_ZIPCODE", "C_CITY", "C_STATE_PROV", "C_CTRY",
     "C_PRIM_EMAIL", "C_ALT_EMAIL"]
    + [f"C_PHONE_{n}_{f}" for n in (1, 2, 3) for f in PHONE_FIELDS]
    + ["C_LCL_TX_ID", "C_NAT_TX_ID", "CA_ID", "CA_TAX_ST", "CA_B_ID", "CA_NAME"]
)
KNOWN = set(COLUMNS)
# Elements that only group other fields; their attributes are fields (C_ID, CA_ID, ...).
CONTAINERS = {"Customer", "Name", "Address", "ContactInfo", "TaxInfo", "Account",
              "C_PHONE_1", "C_PHONE_2", "C_PHONE_3"}

# ActionType -> (DataSet, Attribute) in CustomerMgmt_audit.csv.
AUDIT_ACTIONS = {
    "NEW": ("DimCustomer", "C_NEW"), "UPDCUST": ("DimCustomer", "C_UPDCUST"),
    "INACT": ("DimCustomer", "C_INACT"), "ADDACCT": ("DimAccount", "CA_ADDACCT"),
    "UPDACCT": ("DimAccount", "CA_UPDACCT"), "CLOSEACCT": ("DimAccount", "CA_CLOSEACCT"),
}


class ClickHouse:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/")
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}

    def query(self, sql, database=None, params=None, data=None):
        """Run one statement. With data, sql is an INSERT ... FORMAT and data the rows."""
        args = {"database": database} if database else {}
        args.update({"param_" + k: str(v) for k, v in (params or {}).items()})
        if data is None:
            body = sql.encode()
        else:
            args["query"] = sql
            body = data
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(args),
                                         data=body, headers=self.headers)
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


def audit_values(batch_dir):
    """{(DataSet, Attribute): Value} from DIGen's *_audit.csv files of one batch."""
    values = {}
    for path in sorted(batch_dir.glob("*_audit.csv")):
        with path.open(newline="") as handle:
            rows = csv.reader(handle)
            header = [name.strip() for name in next(rows)]
            for row in rows:
                record = dict(zip(header, (cell.strip() for cell in row)))
                values[(record["DataSet"], record["Attribute"])] = record["Value"]
    return values


def action_row(seq, action):
    """One <TPCDI:Action> -> dict of the stg_CustomerMgmt columns (None = absent)."""
    row = {"ActionSeq": seq, "ActionType": action.get("ActionType"),
           "ActionTS": action.get("ActionTS")}
    if row["ActionType"] is None or row["ActionTS"] is None:
        raise ValueError(f"Action {seq}: missing ActionType or ActionTS")
    row.update(dict.fromkeys(COLUMNS))

    def put(name, value):
        if name not in KNOWN:
            raise ValueError(f"Action {seq}: unknown field {name}")
        if row[name] is not None:
            raise ValueError(f"Action {seq}: field {name} appears twice")
        row[name] = value

    def walk(element, prefix):
        for name, value in element.attrib.items():
            put(name, value)
        for child in element:
            tag = child.tag
            if tag in CONTAINERS:
                walk(child, tag + "_" if tag.startswith("C_PHONE_") else "")
            elif len(child):
                raise ValueError(f"Action {seq}: unexpected element <{tag}> with children")
            else:
                put(prefix + tag, child.text or "")   # <X/> -> '', text kept untrimmed

    customers = [child for child in action if child.tag == "Customer"]
    if len(customers) != 1 or len(action) != 1:
        raise ValueError(f"Action {seq}: expected exactly one <Customer>")
    walk(customers[0], "")
    return row


def customer_mgmt_rows(path, counts):
    """Stream the XML; yield JSONEachRow lines (bytes) and count the actions by type."""
    seq = 0
    context = ET.iterparse(path, events=("start", "end"))
    _, root = next(context)
    if root.tag != NS + "Actions":
        raise ValueError(f"{path}: root element is {root.tag}, expected TPCDI:Actions")
    for event, element in context:
        if event == "end" and element.tag == NS + "Action":
            seq += 1
            row = action_row(seq, element)
            counts[row["ActionType"]] = counts.get(row["ActionType"], 0) + 1
            yield (json.dumps(row, ensure_ascii=False) + "\n").encode()
            root.clear()        # keep memory flat at large SFs


def batched(lines, size=1 << 20):
    """Group small lines into ~1 MB chunks for the HTTP body."""
    buffer, length = [], 0
    for line in lines:
        buffer.append(line)
        length += len(line)
        if length >= size:
            yield b"".join(buffer)
            buffer, length = [], 0
    if buffer:
        yield b"".join(buffer)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sf", type=int, required=True)
    parser.add_argument("--batch", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--database", help="default: tpcdi_sf<SF>")
    parser.add_argument("--init", action="store_true",
                        help="create the database if needed and (re)create the staging tables")
    parser.add_argument("--url", default="http://localhost:8123")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="infoh419")
    args = parser.parse_args(argv)

    db = args.database or f"tpcdi_sf{args.sf}"
    rel_dir = f"data/tpcdi/sf{args.sf}/Batch{args.batch}"   # relative to ClickHouse's user_files
    batch_dir = REPO / rel_dir
    if not (batch_dir.parent / "digen_report.txt").is_file():
        raise SystemExit(f"No DIGen output in {batch_dir.parent}: generate SF {args.sf} first.")
    audit = audit_values(batch_dir)
    ch = ClickHouse(args.url, args.user, args.password)

    if args.init:
        ch.query(f"CREATE DATABASE IF NOT EXISTS {db}")
        for table in ("stg_CustomerMgmt", "stg_Prospect"):
            ch.query(f"DROP TABLE IF EXISTS {table} SYNC", db)
        for sql in statements((PART2 / "ddl" / "staging_cluster_b.sql").read_text()):
            ch.query(sql, db)
        print(f"Created stg_CustomerMgmt and stg_Prospect in {db}")

    failures = []

    def check(name, actual, expected):
        ok = str(actual) == str(expected)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {actual}"
              + ("" if ok else f" (expected {expected})"))
        if not ok:
            failures.append(name)

    if args.batch == 1:
        xml = batch_dir / "CustomerMgmt.xml"
        start = time.perf_counter()
        counts = {}
        ch.query("TRUNCATE TABLE stg_CustomerMgmt", db)
        ch.query("INSERT INTO stg_CustomerMgmt FORMAT JSONEachRow", db,
                 data=batched(customer_mgmt_rows(xml, counts)))
        total = sum(counts.values())
        print(f"CustomerMgmt.xml -> stg_CustomerMgmt: {total} actions "
              f"in {time.perf_counter() - start:.2f} s")
        check("stg_CustomerMgmt rows", ch.query("SELECT count() FROM stg_CustomerMgmt", db), total)
        for action_type, key in AUDIT_ACTIONS.items():
            check(f"{action_type} actions", counts.get(action_type, 0), audit.get(key, "missing"))
        unknown = set(counts) - set(AUDIT_ACTIONS)
        if unknown:
            check("unknown action types", sorted(unknown), [])

    start = time.perf_counter()
    for sql in statements((PART2 / "etl" / "staging_prospect.sql").read_text()):
        ch.query(sql, db, {"batch_dir": rel_dir})
    rows = ch.query("SELECT count() FROM stg_Prospect", db)
    print(f"Prospect.csv -> stg_Prospect: {rows} rows in {time.perf_counter() - start:.2f} s")
    check("stg_Prospect rows", rows, audit.get(("Prospect", "P_RECORDS"), "missing"))

    if failures:
        raise SystemExit(f"FAILED: {len(failures)} check(s)")
    print(f"OK  batch {args.batch} of SF {args.sf} staged in {db}")


if __name__ == "__main__":
    sys.exit(main())
