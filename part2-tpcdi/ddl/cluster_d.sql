-- Cluster D tables (role 4): staging for DailyMarket and FactMarketHistory.
-- Types follow the group rule: SK_T -> UInt64, BatchID -> UInt32, DATE -> Date32, NUM(m,n) -> Decimal(m,n).

-- Staging for Batch1/DailyMarket.txt (historical format, no CDC columns).
CREATE TABLE IF NOT EXISTS stg_DailyMarket
(
    DM_DATE   Date32,
    DM_S_SYMB String,
    DM_CLOSE  Decimal(8, 2),
    DM_HIGH   Decimal(8, 2),
    DM_LOW    Decimal(8, 2),
    DM_VOL    Int64           -- NUM(12); Int64 like SharesOutstanding in DimSecurity
)
ENGINE = MergeTree
ORDER BY (DM_S_SYMB, DM_DATE);

-- FactMarketHistory (spec 3.2.17).
CREATE TABLE IF NOT EXISTS FactMarketHistory
(
    SK_SecurityID           UInt64,
    SK_CompanyID            UInt64,
    SK_DateID               UInt64,
    PERatio                 Nullable(Decimal(10, 2)),  -- NULL when the company has no earnings
    Yield                   Decimal(5, 2),
    FiftyTwoWeekHigh        Decimal(8, 2),
    SK_FiftyTwoWeekHighDate UInt64,
    FiftyTwoWeekLow         Decimal(8, 2),
    SK_FiftyTwoWeekLowDate  UInt64,
    ClosePrice              Decimal(8, 2),
    DayHigh                 Decimal(8, 2),
    DayLow                  Decimal(8, 2),
    Volume                  Int64,
    BatchID                 UInt32
)
ENGINE = MergeTree
ORDER BY (SK_SecurityID, SK_DateID);
