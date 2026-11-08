-- Auxiliary input for the SCD2 prototype, NOT a raw XML loader contract.
-- Every input row must be a COMPLETE resolved account state after an event.
-- Missing XML fields must already have retained their preceding values;
-- explicitly empty fields must already have become NULL.
-- UPDCUST/INACT must already have produced states for affected accounts.
CREATE TABLE stg_AccountState
(
    AccountID UInt64,
    ActionTS DateTime64(3, 'UTC'),
    SourceOrder UInt64,
    SK_BrokerID UInt64,
    SK_CustomerID UInt64,
    Status String,
    AccountDesc Nullable(String),
    TaxStatus Nullable(UInt8)
)
ENGINE = MergeTree ORDER BY (AccountID, ActionTS, SourceOrder);
