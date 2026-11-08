-- One invocation per incremental batch, with parameters batch UInt32,
-- batch_date String. Source input contains COMPLETE states for that batch.
-- The orchestrator must validate the rebuilt table before EXCHANGE.
CREATE TABLE DimAccount_next AS DimAccount;

-- Preserve old keys and old BatchIDs. Expire only affected current rows.
INSERT INTO DimAccount_next
SELECT SK_AccountID, AccountID, SK_BrokerID, SK_CustomerID,
    Status, AccountDesc, TaxStatus,
    if(IsCurrent AND AccountID IN (SELECT AccountID FROM stg_AccountState),
       false, IsCurrent),
    BatchID, EffectiveDate,
    if(IsCurrent AND AccountID IN (SELECT AccountID FROM stg_AccountState),
       toDate32({batch_date:String}), EndDate)
FROM DimAccount;

-- One new surrogate key per changed/new account, above the old maximum.
INSERT INTO DimAccount_next
WITH updates AS
(
    SELECT AccountID,
        argMax(tuple(SK_BrokerID, SK_CustomerID, Status, AccountDesc, TaxStatus),
               tuple(ActionTS, SourceOrder)) AS state
    FROM stg_AccountState GROUP BY AccountID
)
SELECT (SELECT coalesce(max(SK_AccountID), toUInt64(0)) FROM DimAccount)
        + row_number() OVER (ORDER BY AccountID),
    AccountID, state.1, state.2, state.3, state.4, state.5,
    true, {batch:UInt32}, toDate32({batch_date:String}), toDate32('9999-12-31')
FROM updates;
