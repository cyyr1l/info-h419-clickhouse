-- FactCashBalances, Historical Load (4.5.9): one row per account and day with cash transactions.
-- Needs DimDate (cluster A) and DimAccount (cluster B).
-- Cash is the running balance of the account. The window runs over the natural key AccountID,
-- because the account may get a new surrogate key between two days (note of 4.5.9.2).

INSERT INTO FactCashBalances (SK_CustomerID, SK_AccountID, SK_DateID, Cash, BatchID)
WITH daily AS
(
    SELECT CT_CA_ID AS AccountID, toDate32(CT_DTS) AS Day, sum(CT_AMT) AS DayAmount
    FROM stg_CashTransaction
    GROUP BY AccountID, Day
)
SELECT a.SK_CustomerID, a.SK_AccountID, d.SK_DateID,
    CAST(sum(daily.DayAmount) OVER (PARTITION BY daily.AccountID ORDER BY daily.Day
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
         AS Decimal(15, 2)),
    toUInt32(1)
FROM daily
INNER JOIN DimDate AS d ON d.DateValue = daily.Day
ASOF JOIN DimAccount AS a ON a.AccountID = daily.AccountID AND daily.Day >= a.EffectiveDate;
