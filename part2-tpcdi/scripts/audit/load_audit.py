"""Load every *_audit.csv produced by DIGen into the Audit table.

DIGen writes audit files in the output root (Batch1_audit.csv, ..., Generator_audit.csv)
and inside each batch folder (Batch1/HR_audit.csv, Batch2/Customer_audit.csv, ...).
Each file has a header row (with stray spaces) and the columns
DataSet, BatchID, Date, Attribute, Value, DValue. Empty fields become NULL.

Usage:
    python load_audit.py <digen_output_dir> [--host localhost] [--port 8123]
                         [--database default] [--user default] [--password ""]
The orchestrator can also import load_audit(client, data_dir).
"""
import argparse
import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path

import clickhouse_connect

COLUMNS = ["DataSet", "BatchID", "Date", "Attribute", "Value", "DValue"]


def _none_if_empty(value: str):
    value = value.strip()
    return value if value else None


def _parse_row(row: list[str], path: Path, line_no: int) -> list:
    if len(row) != 6:
        raise ValueError(f"{path}:{line_no}: expected 6 fields, got {len(row)}: {row}")
    dataset, batch_id, date, attribute, value, dvalue = map(_none_if_empty, row)
    if dataset is None or attribute is None:
        raise ValueError(f"{path}:{line_no}: DataSet and Attribute are mandatory")
    return [
        dataset,
        int(batch_id) if batch_id is not None else None,
        dt.date.fromisoformat(date) if date is not None else None,
        attribute,
        Decimal(value) if value is not None else None,
        Decimal(dvalue) if dvalue is not None else None,
    ]


def read_audit_files(data_dir: Path) -> list[list]:
    files = sorted(data_dir.rglob("*_audit.csv"))
    if not files:
        raise FileNotFoundError(f"No *_audit.csv found under {data_dir}")
    rows = []
    for path in files:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header row
            for line_no, row in enumerate(reader, start=2):
                if not row or all(not field.strip() for field in row):
                    continue
                rows.append(_parse_row(row, path, line_no))
    return rows


def load_audit(client, data_dir: str | Path) -> int:
    """Replace the content of Audit with the audit files under data_dir. Returns the row count."""
    rows = read_audit_files(Path(data_dir))
    client.command("TRUNCATE TABLE IF EXISTS Audit")
    client.insert("Audit", rows, column_names=COLUMNS)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("data_dir")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--database", default="default")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    client = clickhouse_connect.get_client(
        host=args.host, port=args.port, database=args.database,
        username=args.user, password=args.password,
    )
    n = load_audit(client, args.data_dir)
    print(f"Loaded {n} rows into Audit")


if __name__ == "__main__":
    main()
