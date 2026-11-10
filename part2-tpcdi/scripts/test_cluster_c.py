#!/usr/bin/env python3
"""Run the cluster C historical load on DIGen data and check it against DIGen's audit values.

The script works in a throwaway database. The dimensions of clusters A and B are replaced by
stand-ins: DimDate, DimTime, StatusType and TradeType come from the real Batch1 files, while
DimSecurity and DimAccount are synthetic history-tracking tables built from the keys of the
trades and cash transactions. A quarter of the symbols and a third of the accounts get a second
version, so the ASOF joins and the running cash balance are tested across a surrogate-key change.

It then runs the cluster C DDL and ETL files, and checks the result with the expected values of
DIGen's audit files and with the tests of tpcdi_audit.sql that concern cluster C.

Usage, from anywhere:  python3 part2-tpcdi/scripts/test_cluster_c.py [--sf 10] [--keep]
Needs the ClickHouse container (docker/docker-compose.yml) and DIGen output in data/tpcdi/sf<SF>/.
Standard library only.
"""
import argparse
import csv
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

PART2 = Path(__file__).resolve().parents[1]   # part2-tpcdi/
REPO = PART2.parent

# Stand-ins for the tables of clusters A and B, with the columns cluster C uses.
REFERENCE_FIXTURES = """
CREATE TABLE DimDate (SK_DateID UInt64, DateValue Date32) ENGINE = MergeTree ORDER BY DateValue;
INSERT INTO DimDate SELECT c1, c2 FROM file(concat({batch_dir:String}, '/Date.txt'), 'CSV', 'c1 UInt64, c2 Date32')
SETTINGS format_csv_delimiter = '|', input_format_csv_allow_variable_number_of_columns = 1;
CREATE TABLE DimTime (SK_TimeID UInt64, TimeValue Time64(3)) ENGINE = MergeTree ORDER BY TimeValue;
INSERT INTO DimTime SELECT c1, c2 FROM file(concat({batch_dir:String}, '/Time.txt'), 'CSV', 'c1 UInt64, c2 Time64(3)')
SETTINGS format_csv_delimiter = '|', input_format_csv_allow_variable_number_of_columns = 1;
CREATE TABLE StatusType (ST_ID String, ST_NAME String) ENGINE = MergeTree ORDER BY ST_ID;
INSERT INTO StatusType SELECT * FROM file(concat({batch_dir:String}, '/StatusType.txt'), 'CSV', 'ST_ID String, ST_NAME String')
SETTINGS format_csv_delimiter = '|';
CREATE TABLE TradeType (TT_ID String, TT_NAME String, TT_IS_SELL UInt8, TT_IS_MRKT UInt8) ENGINE = MergeTree ORDER BY TT_ID;
INSERT INTO TradeType SELECT * FROM file(concat({batch_dir:String}, '/TradeType.txt'), 'CSV', 'TT_ID String, TT_NAME String, TT_IS_SELL UInt8, TT_IS_MRKT UInt8')
SETTINGS format_csv_delimiter = '|';
CREATE TABLE DImessages (MessageDateAndTime DateTime64(3), BatchID UInt32, MessageSource Nullable(String),
    MessageText String, MessageType String, MessageData Nullable(String))
ENGINE = MergeTree ORDER BY (BatchID, MessageDateAndTime);
"""

# Synthetic history-tracking dimensions, built once the staging tables are loaded.
SCD2_FIXTURES = """
CREATE TABLE DimSecurity (SK_SecurityID UInt64, Symbol String, SK_CompanyID UInt64, IsCurrent Bool,
    EffectiveDate Date32, EndDate Date32) ENGINE = MergeTree ORDER BY (Symbol, EffectiveDate);
INSERT INTO DimSecurity
WITH s AS (SELECT Symbol, row_number() OVER (ORDER BY Symbol) AS n FROM (SELECT DISTINCT T_S_SYMB AS Symbol FROM stg_Trade))
SELECT n * 10, Symbol, n, n % 4 != 0, toDate32('1950-01-01'),
    if(n % 4 = 0, toDate32('2015-01-01'), toDate32('9999-12-31')) FROM s
UNION ALL
SELECT n * 10 + 1, Symbol, n, true, toDate32('2015-01-01'), toDate32('9999-12-31') FROM s WHERE n % 4 = 0;
CREATE TABLE DimAccount (SK_AccountID UInt64, AccountID UInt64, SK_BrokerID UInt64, SK_CustomerID UInt64,
    IsCurrent Bool, EffectiveDate Date32, EndDate Date32) ENGINE = MergeTree ORDER BY (AccountID, EffectiveDate);
INSERT INTO DimAccount
WITH a AS (SELECT DISTINCT AccountID FROM (SELECT T_CA_ID AS AccountID FROM stg_Trade UNION ALL SELECT CT_CA_ID FROM stg_CashTransaction))
SELECT AccountID * 10, AccountID, 1 + AccountID % 7, 100000 + AccountID, AccountID % 3 != 0,
    toDate32('1950-01-01'), if(AccountID % 3 = 0, toDate32('2016-01-01'), toDate32('9999-12-31')) FROM a
UNION ALL
SELECT AccountID * 10 + 1, AccountID, 1 + AccountID % 7, 200000 + AccountID, true,
    toDate32('2016-01-01'), toDate32('9999-12-31') FROM a WHERE AccountID % 3 = 0;
"""

ETL_STEPS = [
    "etl/dimtrade_historical.sql",
    "etl/factcashbalances_historical.sql",
    "etl/factholdings_historical.sql",
]

DIMTRADE = "(SELECT * FROM DimTrade FINAL)"


def checks(audit):
    """(name, query returning one value, expected value as text). The quoted names are the
    tests of tpcdi_audit.sql that each check reproduces."""
    t_new = audit[("DimTrade", "1", "T_NEW")]
    hh = audit[("FactHoldings", "1", "HH_RECORDS")]
    return [
        ("DimTrade rows = T_NEW ('DimTrade row count')",
         f"SELECT count() FROM {DIMTRADE}", t_new),
        ("DimTrade TradeID unique ('DimTrade distinct keys')",
         f"SELECT count() - uniqExact(TradeID) FROM {DIMTRADE}", "0"),
        ("canceled trades = T_CanceledTrades ('DimTrade canceled trades')",
         f"SELECT countIf(Status = 'Canceled') FROM {DIMTRADE}", audit[("DimTrade", "1", "T_CanceledTrades")]),
        ("commission alerts = T_InvalidCommision ('DimTrade commission alerts')",
         "SELECT count() FROM DImessages WHERE BatchID = 1 AND MessageType = 'Alert' "
         "AND MessageText = 'Invalid trade commission'", audit[("DimTrade", "1", "T_InvalidCommision")]),
        ("fee alerts = T_InvalidCharge ('DimTrade charge alerts')",
         "SELECT count() FROM DImessages WHERE BatchID = 1 AND MessageType = 'Alert' "
         "AND MessageText = 'Invalid trade fee'", audit[("DimTrade", "1", "T_InvalidCharge")]),
        ("Status values ('DimTrade Status')",
         f"SELECT countIf(Status NOT IN ('Canceled', 'Pending', 'Submitted', 'Active', 'Completed')) FROM {DIMTRADE}", "0"),
        ("Type values ('DimTrade Type')",
         f"SELECT countIf(Type NOT IN ('Market Buy', 'Market Sell', 'Stop Loss', 'Limit Sell', 'Limit Buy')) FROM {DIMTRADE}", "0"),
        ("close keys set exactly for completed and canceled trades",
         f"SELECT countIf((SK_CloseDateID IS NULL) != (Status IN ('Pending', 'Submitted'))) "
         f"+ countIf((SK_CloseTimeID IS NULL) != (SK_CloseDateID IS NULL)) FROM {DIMTRADE}", "0"),
        ("close date not before create date (part of 'DimTrade date check')",
         f"SELECT countIf(SK_CloseDateID < SK_CreateDateID) FROM {DIMTRADE}", "0"),
        ("DimAccount version valid on the create date, keys copied from it ('DimTrade SK_AccountID')",
         f"SELECT count() FROM {DIMTRADE} AS t INNER JOIN DimDate AS d ON d.SK_DateID = t.SK_CreateDateID "
         "INNER JOIN DimAccount AS a ON a.SK_AccountID = t.SK_AccountID "
         "WHERE a.EffectiveDate <= d.DateValue AND d.DateValue < a.EndDate "
         "AND t.SK_CustomerID = a.SK_CustomerID AND t.SK_BrokerID = a.SK_BrokerID", t_new),
        ("DimSecurity version valid on the create date ('DimTrade SK_SecurityID', 'SK_CompanyID')",
         f"SELECT count() FROM {DIMTRADE} AS t INNER JOIN DimDate AS d ON d.SK_DateID = t.SK_CreateDateID "
         "INNER JOIN DimSecurity AS s ON s.SK_SecurityID = t.SK_SecurityID "
         "WHERE s.EffectiveDate <= d.DateValue AND d.DateValue < s.EndDate AND t.SK_CompanyID = s.SK_CompanyID", t_new),
        ("some trades use the second version of their account (the ASOF test is not empty)",
         f"SELECT countIf(SK_AccountID % 10 = 1) > 0 FROM {DIMTRADE}", "1"),
        ("FactHoldings rows = HH_RECORDS ('FactHoldings row count')",
         "SELECT count() FROM FactHoldings", hh),
        ("FactHoldings date and time = close of the current trade ('FactHoldings CurrentTradeID')",
         f"SELECT count() FROM FactHoldings AS f INNER JOIN {DIMTRADE} AS t ON f.CurrentTradeID = t.TradeID "
         "AND f.SK_DateID = t.SK_CloseDateID AND f.SK_TimeID = t.SK_CloseTimeID", hh),
        ("FactCashBalances: one row per account and day",
         "SELECT (SELECT count() FROM FactCashBalances) "
         "- (SELECT uniqExact(CT_CA_ID, toDate32(CT_DTS)) FROM stg_CashTransaction)", "0"),
        ("FactCashBalances: Cash of the last day = sum of all the account's transactions",
         "SELECT count() FROM (SELECT a.AccountID AS AccountID, argMax(f.Cash, f.SK_DateID) AS last_cash "
         "FROM FactCashBalances AS f INNER JOIN DimAccount AS a ON a.SK_AccountID = f.SK_AccountID GROUP BY a.AccountID) AS x "
         "INNER JOIN (SELECT CT_CA_ID AS AccountID, sum(CT_AMT) AS total FROM stg_CashTransaction GROUP BY CT_CA_ID) AS y "
         "ON x.AccountID = y.AccountID WHERE x.last_cash != y.total", "0"),
        ("FactCashBalances: DimAccount version valid on the day ('FactCashBalances SK_AccountID')",
         "SELECT count() FROM FactCashBalances AS f INNER JOIN DimDate AS d ON d.SK_DateID = f.SK_DateID "
         "INNER JOIN DimAccount AS a ON a.SK_AccountID = f.SK_AccountID "
         "WHERE NOT (a.EffectiveDate <= d.DateValue AND d.DateValue < a.EndDate) OR f.SK_CustomerID != a.SK_CustomerID", "0"),
        ("some balances continue across a surrogate-key change of their account",
         "SELECT count() > 0 FROM (SELECT a.AccountID FROM FactCashBalances AS f "
         "INNER JOIN DimAccount AS a ON a.SK_AccountID = f.SK_AccountID GROUP BY a.AccountID "
         "HAVING uniqExact(f.SK_AccountID) = 2)", "1"),
        ("BatchID = 1 everywhere",
         f"SELECT (SELECT countIf(BatchID != 1) FROM {DIMTRADE}) + (SELECT countIf(BatchID != 1) FROM FactHoldings) "
         "+ (SELECT countIf(BatchID != 1) FROM FactCashBalances)", "0"),
    ]


class ClickHouse:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/")
        self.headers = {"X-ClickHouse-User": user, "X-ClickHouse-Key": password}

    def query(self, sql, database=None, params=None):
        args = {"database": database} if database else {}
        args.update({"param_" + name: str(value) for name, value in (params or {}).items()})
        request = urllib.request.Request(self.url + "/?" + urllib.parse.urlencode(args),
                                         data=sql.encode(), headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                return response.read().decode().strip()
        except urllib.error.HTTPError as error:
            message = error.read().decode().strip()
            raise RuntimeError(f"{message}\n--- in query:\n{sql[:1500]}") from None


def statements(text):
    """Split SQL on ';'. Full-line '--' comments are dropped; no literal may contain ';'."""
    kept = [line for line in text.splitlines() if not line.lstrip().startswith("--")]
    return [part.strip() for part in "\n".join(kept).split(";") if part.strip()]


def audit_values(batch_dir):
    """{(DataSet, BatchID, Attribute): Value} from DIGen's *_audit.csv files of one batch."""
    values = {}
    for path in sorted(batch_dir.glob("*_audit.csv")):
        with path.open(newline="") as handle:
            rows = csv.reader(handle)
            header = [name.strip() for name in next(rows)]
            for row in rows:
                record = dict(zip(header, (cell.strip() for cell in row)))
                values[(record["DataSet"], record["BatchID"], record["Attribute"])] = record["Value"]
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sf", type=int, default=10)
    parser.add_argument("--url", default="http://localhost:8123")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="infoh419")
    parser.add_argument("--keep", action="store_true", help="keep the test database")
    args = parser.parse_args()

    batch1 = REPO / "data" / "tpcdi" / f"sf{args.sf}" / "Batch1"
    if not (batch1.parent / "digen_report.txt").is_file():
        raise SystemExit(f"No DIGen output in {batch1.parent}: generate SF {args.sf} first.")
    params = {"batch_dir": f"data/tpcdi/sf{args.sf}/Batch1"}   # relative to ClickHouse's user_files
    audit = audit_values(batch1)

    ch = ClickHouse(args.url, args.user, args.password)
    print("ClickHouse", ch.query("SELECT version()"), "| SF", args.sf)
    db = "tpcdi_clusterc_test_" + uuid.uuid4().hex[:8]
    ch.query(f"CREATE DATABASE {db} ENGINE = Atomic")
    print("Test database:", db)

    def run(label, text):
        start = time.perf_counter()
        for sql in statements(text):
            ch.query(sql, db, params)
        print(f"  {label:45s} {time.perf_counter() - start:7.2f} s")

    passed = False
    try:
        run("DDL: staging + cluster C", (PART2 / "ddl/staging_cluster_c.sql").read_text()
            + ";\n" + (PART2 / "ddl/cluster_c.sql").read_text())
        run("fixtures: DimDate, DimTime, StatusType...", REFERENCE_FIXTURES)
        run("etl/staging_cluster_c_historical.sql", (PART2 / "etl/staging_cluster_c_historical.sql").read_text())
        run("fixtures: DimSecurity, DimAccount (SCD2)", SCD2_FIXTURES)
        for step in ETL_STEPS:
            run(step, (PART2 / step).read_text())
        print("Durations above are development timings, not measurements (see the protocol, 1.1).")

        failures = 0
        for name, sql, expected in checks(audit):
            actual = ch.query(sql, db)
            ok = actual == expected
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name}: {actual}" + ("" if ok else f" (expected {expected})"))
        if failures:
            raise SystemExit(f"{failures} check(s) failed; database {db} kept for inspection.")
        print("SUCCESS: cluster C historical load")
        passed = True
    finally:
        if passed and not args.keep:
            ch.query(f"DROP DATABASE {db} SYNC")
            print("Test database removed.")
        elif not passed:
            print("Test database kept:", db)


if __name__ == "__main__":
    main()
