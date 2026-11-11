-- Fresh, empty DimAccount only. Batch 1. Complete states are the input.
-- tuple() makes argMax preserve explicit NULL values in nullable fields.
INSERT INTO DimAccount
WITH daily AS
(
    SELECT AccountID, toDate32(ActionTS) AS day,
        argMax(tuple(SK_BrokerID, SK_CustomerID, Status, AccountDesc, TaxStatus),
               tuple(ActionTS, SourceOrder)) AS state
    FROM stg_AccountState
    GROUP BY AccountID, day
), periods AS
(
    SELECT *, leadInFrame(day, 1, toDate32('9999-12-31')) OVER
        (PARTITION BY AccountID ORDER BY day
         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS next_day
    FROM daily
)
SELECT row_number() OVER (ORDER BY AccountID, day), AccountID,
    state.1, state.2, state.3, state.4, state.5,
    next_day = toDate32('9999-12-31'), toUInt32(1), day, next_day
FROM periods;
