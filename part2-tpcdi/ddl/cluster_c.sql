-- TPC-DI 1.1.0, cluster C: DimTrade (3.2.7.1), FactCashBalances (3.2.9), FactHoldings (3.2.10).
-- Run in the Initialization phase, in a fresh Atomic database. No source data is read here.
-- Types follow the team mapping of PR #11: SK_T, IDENT_T, TRADE_T -> UInt64, BatchID -> UInt32,
-- NUM/SNUM(m,n) -> Decimal(m,n), integer NUM/SNUM -> the smallest (U)Int that holds the range,
-- CHAR(n) -> String, BOOLEAN -> Bool, Nullable only where the spec has no NOT NULL.
-- No column is added or removed (3.4.5).

-- DimTrade is updated in place in the incremental batches. Without a version column,
-- ReplacingMergeTree keeps the last inserted row of each TradeID, so an update inserts the
-- complete new row. Every reader uses FINAL (or the setting final = 1).
CREATE TABLE DimTrade
(
    TradeID UInt64,
    SK_BrokerID Nullable(UInt64),
    SK_CreateDateID UInt64,
    SK_CreateTimeID UInt64,
    SK_CloseDateID Nullable(UInt64),
    SK_CloseTimeID Nullable(UInt64),
    Status String,
    Type String,
    CashFlag Bool,
    SK_SecurityID UInt64,
    SK_CompanyID UInt64,
    Quantity UInt32,
    BidPrice Decimal(8, 2),
    SK_CustomerID UInt64,
    SK_AccountID UInt64,
    ExecutedBy String,
    TradePrice Nullable(Decimal(8, 2)),
    Fee Nullable(Decimal(10, 2)),
    Commission Nullable(Decimal(10, 2)),
    Tax Nullable(Decimal(10, 2)),
    BatchID UInt32
)
ENGINE = ReplacingMergeTree ORDER BY TradeID;

CREATE TABLE FactCashBalances
(
    SK_CustomerID UInt64,
    SK_AccountID UInt64,
    SK_DateID UInt64,
    Cash Decimal(15, 2),
    BatchID UInt32
)
ENGINE = MergeTree ORDER BY (SK_AccountID, SK_DateID);

CREATE TABLE FactHoldings
(
    TradeID UInt64,
    CurrentTradeID UInt64,
    SK_CustomerID UInt64,
    SK_AccountID UInt64,
    SK_SecurityID UInt64,
    SK_CompanyID UInt64,
    SK_DateID UInt64,
    SK_TimeID UInt64,
    CurrentPrice Nullable(Decimal(8, 2)),
    CurrentHolding Int32,
    BatchID UInt32
)
ENGINE = MergeTree ORDER BY (CurrentTradeID, TradeID);
