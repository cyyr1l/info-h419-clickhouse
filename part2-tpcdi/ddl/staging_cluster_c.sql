-- Staging tables of cluster C: one auxiliary table per source file (3.4.8, 4.3.7), named stg_<File>.
-- Run in the Initialization phase. Each phase truncates them and loads its own batch.
-- Batch1 files have no CDC_FLAG and CDC_DSN fields: their rows get 'I' and 0.
-- Timestamps are read as UTC, so toDate32() and toTime64() never shift them.

CREATE TABLE stg_Trade
(
    CDC_FLAG String DEFAULT 'I',
    CDC_DSN UInt64 DEFAULT 0,
    T_ID UInt64,
    T_DTS DateTime64(3, 'UTC'),
    T_ST_ID String,
    T_TT_ID String,
    T_IS_CASH Bool,
    T_S_SYMB String,
    T_QTY UInt32,
    T_BID_PRICE Decimal(8, 2),
    T_CA_ID UInt64,
    T_EXEC_NAME String,
    T_TRADE_PRICE Nullable(Decimal(8, 2)),
    T_CHRG Nullable(Decimal(10, 2)),
    T_COMM Nullable(Decimal(10, 2)),
    T_TAX Nullable(Decimal(10, 2))
)
ENGINE = MergeTree ORDER BY (T_ID, CDC_DSN);

-- Historical Load only (2.2.2.16).
CREATE TABLE stg_TradeHistory
(
    TH_T_ID UInt64,
    TH_DTS DateTime64(3, 'UTC'),
    TH_ST_ID String
)
ENGINE = MergeTree ORDER BY (TH_T_ID, TH_DTS);

CREATE TABLE stg_CashTransaction
(
    CDC_FLAG String DEFAULT 'I',
    CDC_DSN UInt64 DEFAULT 0,
    CT_CA_ID UInt64,
    CT_DTS DateTime64(3, 'UTC'),
    CT_AMT Decimal(10, 2),
    CT_NAME String
)
ENGINE = MergeTree ORDER BY (CT_CA_ID, CT_DTS);

-- Quantities are S_QTY_T (unsigned) in the file, but FactHoldings.CurrentHolding is signed.
CREATE TABLE stg_HoldingHistory
(
    CDC_FLAG String DEFAULT 'I',
    CDC_DSN UInt64 DEFAULT 0,
    HH_H_T_ID UInt64,
    HH_T_ID UInt64,
    HH_BEFORE_QTY Int32,
    HH_AFTER_QTY Int32
)
ENGINE = MergeTree ORDER BY (HH_T_ID, CDC_DSN);
