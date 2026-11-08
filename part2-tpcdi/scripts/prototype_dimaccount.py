#!/usr/bin/env python3
"""Exercise SCD2 in a fresh, disposable Atomic database using synthetic states.

Default backend: the already running infoh419-clickhouse Docker container.
No Python dependencies. --backend chdb is for optional embedded validation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def statements(relative):
    # These SQL files contain only line comments, no semicolons in literals.
    sql = "\n".join(line.split("--", 1)[0]
                    for line in (ROOT / relative).read_text().splitlines())
    return [part.strip() for part in sql.split(";") if part.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="infoh419-clickhouse")
    parser.add_argument("--password", default="infoh419")
    parser.add_argument("--keep", action="store_true", help="keep the demo database")
    parser.add_argument("--backend", choices=["docker", "chdb"], default="docker")
    args = parser.parse_args()
    db = "tpcdi_role3_demo_" + uuid.uuid4().hex[:12]
    session = None
    if args.backend == "chdb":
        from chdb import session as embedded
        session = embedded.Session()

    def query(sql, selected=True):
        if session is not None:
            prefix = "USE " + db + "; " if selected else ""
            return str(session.query(prefix + sql, "TSV"))
        command = ["docker", "exec", "-i", args.container,
                   "clickhouse-client", "--password", args.password]
        if selected:
            command += ["--database", db]
        command += ["--query", sql]
        result = subprocess.run(command, input="", text=True, capture_output=True, check=True)
        return result.stdout

    def run_file(relative, **params):
        for sql in statements(relative):
            for name, value in params.items():
                type_name = "UInt32" if isinstance(value, int) else "String"
                literal = str(value) if isinstance(value, int) else "'" + value + "'"
                sql = sql.replace("{" + name + ":" + type_name + "}", literal)
            query(sql)

    def load(rows):
        query("TRUNCATE TABLE stg_AccountState")
        keys = ["AccountID", "ActionTS", "SourceOrder", "SK_BrokerID",
                "SK_CustomerID", "Status", "AccountDesc", "TaxStatus"]
        data = "\n".join(json.dumps(dict(zip(keys, row))) for row in rows)
        query("INSERT INTO stg_AccountState FORMAT JSONEachRow\n" + data)

    def contents(table):
        return json.loads(query(
            "SELECT SK_AccountID, AccountID, SK_BrokerID, SK_CustomerID, "
            "Status, AccountDesc, TaxStatus, toUInt8(IsCurrent) AS IsCurrent, "
            "BatchID, toString(EffectiveDate) AS EffectiveDate, "
            "toString(EndDate) AS EndDate FROM " + table
            + " ORDER BY AccountID, EffectiveDate FORMAT JSON"))["data"]

    def check(table, expected):
        rows = contents(table)
        fields = ["SK_AccountID", "AccountID", "SK_BrokerID", "SK_CustomerID",
                  "Status", "AccountDesc", "TaxStatus", "IsCurrent", "BatchID",
                  "EffectiveDate", "EndDate"]
        # JSON encodes UInt64 as strings by default. Normalize numeric fields.
        numeric = {"SK_AccountID", "AccountID", "SK_BrokerID", "SK_CustomerID",
                   "TaxStatus", "IsCurrent", "BatchID"}
        actual = [tuple(int(row[f]) if f in numeric and row[f] is not None
                        else row[f] for f in fields) for row in rows]
        if actual != expected:
            raise AssertionError(f"{table}:\nexpected {expected}\nactual {actual}")
        assert len({row[0] for row in actual}) == len(actual), "duplicate SK"
        by_account = {}
        for row in actual:
            assert row[9] < row[10], "invalid interval"
            by_account.setdefault(row[1], []).append(row)
        for history in by_account.values():
            assert sum(row[7] for row in history) == 1, "current-row count"
            assert history[-1][10] == "9999-12-31", "current sentinel"
            for previous, current in zip(history, history[1:]):
                assert previous[10] == current[9], "gap or overlap"
        return len(rows)

    version = query("SELECT version()", selected=False).strip()
    print("ClickHouse:", version)
    # Fail before creating any table if this server cannot preserve the spec dates.
    dates = query("SELECT toString(toDate32('1800-01-01')), "
                  "toString(toDate32('9999-12-31'))", selected=False).strip()
    if dates != "1800-01-01\t9999-12-31":
        raise RuntimeError("Date32 range mismatch: " + dates
                           + ". Stop here; the DDL date mapping needs review.")
    query("CREATE DATABASE " + db + " ENGINE = Atomic", selected=False)
    print("Demo database:", db)
    completed = False
    try:
        run_file("ddl/cluster_b.sql")
        run_file("ddl/prototype_staging.sql")
        for table, expected_columns in [("DimAccount", 11), ("DimCustomer", 33),
                                         ("Prospect", 27)]:
            count = int(query("SELECT count() FROM system.columns WHERE database = '"
                              + db + "' AND table = '" + table + "'"))
            assert count == expected_columns, (table, count)

        load([
            [1001, "2015-01-01 09:00:00.000", 1, 11, 101, "ACTIVE", "Initial", 0],
            [1001, "2015-01-02 10:00:00.000", 2, 11, 101, "ACTIVE", "Morning", 0],
            [1001, "2015-01-02 10:00:00.000", 3, 12, 101, "ACTIVE", None, 1],
            [1001, "2015-01-03 11:00:00.000", 4, 12, 102, "ACTIVE", None, 1],
            [1002, "2015-01-01 09:00:00.000", 5, 11, 201, "ACTIVE", "Other", None],
        ])
        run_file("etl/dimaccount_historical.sql")
        expected = [
            (1, 1001, 11, 101, "ACTIVE", "Initial", 0, 0, 1, "2015-01-01", "2015-01-02"),
            (2, 1001, 12, 101, "ACTIVE", None, 1, 0, 1, "2015-01-02", "2015-01-03"),
            (3, 1001, 12, 102, "ACTIVE", None, 1, 1, 1, "2015-01-03", "9999-12-31"),
            (4, 1002, 11, 201, "ACTIVE", "Other", None, 1, 1, "2015-01-01", "9999-12-31"),
        ]
        check("DimAccount", expected)
        print("PASS historical: daily grain, timestamp ties, NULL, customer-key change")

        load([
            [1001, "2015-01-04 09:00:00.000", 1, 12, 103, "ACTIVE", None, 1],
            [1001, "2015-01-04 15:00:00.000", 2, 12, 103, "ACTIVE", "Updated", 2],
            [1003, "2015-01-04 10:00:00.000", 3, 11, 301, "ACTIVE", "New", 0],
        ])
        run_file("etl/dimaccount_incremental.sql", batch=2, batch_date="2015-01-04")
        # The old table must still be readable and identical before the swap.
        check("DimAccount", expected)
        expected = expected[:2] + [
            (3, 1001, 12, 102, "ACTIVE", None, 1, 0, 1, "2015-01-03", "2015-01-04"),
            (5, 1001, 12, 103, "ACTIVE", "Updated", 2, 1, 2, "2015-01-04", "9999-12-31"),
            expected[3],
            (6, 1003, 11, 301, "ACTIVE", "New", 0, 1, 2, "2015-01-04", "9999-12-31"),
        ]
        check("DimAccount_next", expected)
        query("EXCHANGE TABLES DimAccount AND DimAccount_next")
        check("DimAccount", expected)
        query("DROP TABLE DimAccount_next")
        print("PASS batch 2: preserved history/keys, new account, checked rebuild, EXCHANGE")

        load([[1002, "2015-01-05 10:00:00.000", 1, 11, 201, "INACTIVE", "Other", None]])
        run_file("etl/dimaccount_incremental.sql", batch=3, batch_date="2015-01-05")
        check("DimAccount", expected)
        expected = expected[:4] + [
            (4, 1002, 11, 201, "ACTIVE", "Other", None, 0, 1, "2015-01-01", "2015-01-05"),
            (7, 1002, 11, 201, "INACTIVE", "Other", None, 1, 3, "2015-01-05", "9999-12-31"),
            expected[5],
        ]
        check("DimAccount_next", expected)
        query("EXCHANGE TABLES DimAccount AND DimAccount_next")
        check("DimAccount", expected)
        query("DROP TABLE DimAccount_next")
        print("PASS batch 3: closure, one current row per account, consecutive intervals")
        print("SUCCESS: cluster B DDL and DimAccount SCD2 prototype")
        completed = True
    finally:
        if completed and not args.keep:
            query("DROP DATABASE " + db + " SYNC", selected=False)
            print("Demo database removed.")
        else:
            print("Database retained for inspection:", db)
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
