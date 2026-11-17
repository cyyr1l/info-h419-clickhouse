"""Load every *_audit.csv produced by DIGen into the Audit table (standard library only).

DIGen writes audit files in the output root (Batch1_audit.csv, ..., Generator_audit.csv)
and inside each batch folder (Batch1/HR_audit.csv, Batch2/Customer_audit.csv, ...).
Each file has a header row (with stray spaces) and the columns
DataSet, BatchID, Date, Attribute, Value, DValue. Empty fields become NULL.
The rows are sent to ClickHouse over HTTP as TabSeparated, after a TRUNCATE, so a reload
does not duplicate them.

Usage:
    python3 part2-tpcdi/scripts/audit/load_audit.py --sf 10
        reads data/tpcdi/sf10 and loads tpcdi_sf10.Audit
    options: --data-dir DIR  --database DB  --url http://localhost:8123  --user default  --password infoh419
The orchestrator can also import load_audit(url, user, password, database, data_dir).
"""
import argparse
import csv
import datetime as dt
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path


def _none_if_empty(value: str):
    value = value.strip()
    return value if value else None


def _parse_row(row: list[str], path: Path, line_no: int) -> list:
    """Check and normalise one CSV row. Raises ValueError with the file and line on bad data."""
    if len(row) != 6:
        raise ValueError(f"{path}:{line_no}: expected 6 fields, got {len(row)}: {row}")
    dataset, batch_id, date, attribute, value, dvalue = map(_none_if_empty, row)
    if dataset is None or attribute is None:
        raise ValueError(f"{path}:{line_no}: DataSet and Attribute are mandatory")
    try:
        return [
            dataset,
            str(int(batch_id)) if batch_id is not None else None,
            dt.date.fromisoformat(date).isoformat() if date is not None else None,
            attribute,
            str(int(value)) if value is not None else None,
            str(Decimal(dvalue)) if dvalue is not None else None,
        ]
    except ValueError as e:
        raise ValueError(f"{path}:{line_no}: {e}: {row}") from None


def read_audit_files(data_dir: Path) -> list[list]:
    files = sorted(Path(data_dir).rglob("*_audit.csv"))
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


def to_tsv(rows: list[list]) -> bytes:
    """TabSeparated with \\N for NULL. Audit values never contain tabs, newlines or backslashes."""
    lines = ("\t".join("\\N" if v is None else v for v in row) for row in rows)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _query(url: str, user: str, password: str, database: str, sql: str, data: bytes | None = None) -> str:
    full_url = f"{url}/?" + urllib.parse.urlencode({"database": database, "query": sql})
    request = urllib.request.Request(full_url, data=data if data is not None else b"", method="POST",
                                     headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password})
    try:
        with urllib.request.urlopen(request) as response:
            return response.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ClickHouse error for {sql[:60]!r}: {e.read().decode().strip()}") from None


def load_audit(url: str, user: str, password: str, database: str, data_dir: str | Path) -> int:
    """Replace the content of Audit with the audit files under data_dir. Returns the row count."""
    rows = read_audit_files(Path(data_dir))
    _query(url, user, password, database, "TRUNCATE TABLE IF EXISTS Audit")
    _query(url, user, password, database,
           "INSERT INTO Audit (DataSet, BatchID, Date, Attribute, Value, DValue) FORMAT TabSeparated",
           to_tsv(rows))
    loaded = int(_query(url, user, password, database, "SELECT count() FROM Audit"))
    if loaded != len(rows):
        raise RuntimeError(f"Audit has {loaded} rows, expected {len(rows)}")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sf", type=int, required=True, help="scale factor, e.g. 10")
    parser.add_argument("--data-dir", help="DIGen output folder (default: data/tpcdi/sf<SF>)")
    parser.add_argument("--database", help="target database (default: tpcdi_sf<SF>)")
    parser.add_argument("--url", default="http://localhost:8123")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="infoh419")
    args = parser.parse_args()

    data_dir = args.data_dir or f"data/tpcdi/sf{args.sf}"
    database = args.database or f"tpcdi_sf{args.sf}"
    n = load_audit(args.url, args.user, args.password, database, data_dir)
    print(f"Loaded {n} rows into {database}.Audit from {data_dir}")


if __name__ == "__main__":
    main()
