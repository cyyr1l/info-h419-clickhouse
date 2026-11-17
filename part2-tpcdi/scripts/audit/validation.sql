-- TPC-DI Appendix B (v1.1.0): batch validation query, ported to ClickHouse.
-- Run at the end of every batch, including "batch 0" (empty DW, before Batch1).
-- Statement 1 writes the 24 'Validation' messages; statement 2 writes the Phase Complete Record.
--
-- Changes from the original:
--   * CURRENT_TIMESTAMP -> now64(3) (0.1 s precision required; constant within one statement).
--   * "x join y on 1=1" -> CROSS JOIN; "FROM DUMMY TABLE" removed.
--   * UNION -> UNION ALL (every row has a different MessageSource/MessageText, so same result).
--   * count(*) cast to String, because MessageData is a string column.
--   * max(BatchID) of an empty DImessages returns 0 in ClickHouse, which is the batch-0 value.
--   * SETTINGS final = 1, so ReplacingMergeTree tables (DimTrade) are counted after deduplication.

INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
SELECT
    now64(3)     AS MessageDateAndTime,
    x.BatchID    AS BatchID,
    y.MessageSource,
    y.MessageText,
    'Validation' AS MessageType,
    toString(y.MessageData) AS MessageData
FROM (SELECT max(BatchID) AS BatchID FROM DImessages) AS x
CROSS JOIN
(
    /* Basic row counts */
              SELECT 'DimAccount'        AS MessageSource, 'Row count' AS MessageText, count() AS MessageData FROM DimAccount
    UNION ALL SELECT 'DimBroker',         'Row count', count() FROM DimBroker
    UNION ALL SELECT 'DimCompany',        'Row count', count() FROM DimCompany
    UNION ALL SELECT 'DimCustomer',       'Row count', count() FROM DimCustomer
    UNION ALL SELECT 'DimDate',           'Row count', count() FROM DimDate
    UNION ALL SELECT 'DimSecurity',       'Row count', count() FROM DimSecurity
    UNION ALL SELECT 'DimTime',           'Row count', count() FROM DimTime
    UNION ALL SELECT 'DimTrade',          'Row count', count() FROM DimTrade
    UNION ALL SELECT 'FactCashBalances',  'Row count', count() FROM FactCashBalances
    UNION ALL SELECT 'FactHoldings',      'Row count', count() FROM FactHoldings
    UNION ALL SELECT 'FactMarketHistory', 'Row count', count() FROM FactMarketHistory
    UNION ALL SELECT 'FactWatches',       'Row count', count() FROM FactWatches
    UNION ALL SELECT 'Financial',         'Row count', count() FROM Financial
    UNION ALL SELECT 'Industry',          'Row count', count() FROM Industry
    UNION ALL SELECT 'Prospect',          'Row count', count() FROM Prospect
    UNION ALL SELECT 'StatusType',        'Row count', count() FROM StatusType
    UNION ALL SELECT 'TaxRate',           'Row count', count() FROM TaxRate
    UNION ALL SELECT 'TradeType',         'Row count', count() FROM TradeType
    /* Joined row counts for fact tables */
    UNION ALL SELECT 'FactCashBalances', 'Row count joined', count()
        FROM FactCashBalances f
        INNER JOIN DimAccount  a ON f.SK_AccountID  = a.SK_AccountID
        INNER JOIN DimCustomer c ON f.SK_CustomerID = c.SK_CustomerID
        INNER JOIN DimBroker   b ON a.SK_BrokerID   = b.SK_BrokerID
        INNER JOIN DimDate     d ON f.SK_DateID     = d.SK_DateID
    UNION ALL SELECT 'FactHoldings', 'Row count joined', count()
        FROM FactHoldings f
        INNER JOIN DimAccount  a ON f.SK_AccountID  = a.SK_AccountID
        INNER JOIN DimCustomer c ON f.SK_CustomerID = c.SK_CustomerID
        INNER JOIN DimBroker   b ON a.SK_BrokerID   = b.SK_BrokerID
        INNER JOIN DimDate     d ON f.SK_DateID     = d.SK_DateID
        INNER JOIN DimTime     t ON f.SK_TimeID     = t.SK_TimeID
        INNER JOIN DimCompany  m ON f.SK_CompanyID  = m.SK_CompanyID
        INNER JOIN DimSecurity s ON f.SK_SecurityID = s.SK_SecurityID
    UNION ALL SELECT 'FactMarketHistory', 'Row count joined', count()
        FROM FactMarketHistory f
        INNER JOIN DimDate     d ON f.SK_DateID     = d.SK_DateID
        INNER JOIN DimCompany  m ON f.SK_CompanyID  = m.SK_CompanyID
        INNER JOIN DimSecurity s ON f.SK_SecurityID = s.SK_SecurityID
    UNION ALL SELECT 'FactWatches', 'Row count joined', count()
        FROM FactWatches f
        INNER JOIN DimCustomer c  ON f.SK_CustomerID        = c.SK_CustomerID
        INNER JOIN DimDate     dp ON f.SK_DateID_DatePlaced = dp.SK_DateID
        -- (cannot join on SK_DateID_DateRemoved because that field can be null)
        INNER JOIN DimSecurity s  ON f.SK_SecurityID        = s.SK_SecurityID
    /* Additional information used at audit time */
    UNION ALL SELECT 'DimCustomer', 'Inactive customers', count()
        FROM DimCustomer WHERE IsCurrent = 1 AND Status = 'Inactive'
    UNION ALL SELECT 'FactWatches', 'Inactive watches', count()
        FROM FactWatches WHERE SK_DateID_DateRemoved IS NOT NULL
) AS y
SETTINGS final = 1;

/* Phase Complete Record */
INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
SELECT
    now64(3),
    max(BatchID),
    'Phase Complete Record',
    'Batch Complete',
    'PCR',
    NULL
FROM DImessages;
