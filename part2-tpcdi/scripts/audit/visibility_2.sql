-- TPC-DI Appendix C (v1.1.0): data visibility query 2, ported to ClickHouse.
-- Plain row counts only (no joins). Run periodically while a batch is loading.
-- Same changes as validation.sql (now64(3), CROSS JOIN, UNION ALL, toString, SETTINGS final = 1).

INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
SELECT
    now64(3)       AS MessageDateAndTime,
    x.BatchID      AS BatchID,
    y.MessageSource,
    y.MessageText,
    'Visibility_2' AS MessageType,
    toString(y.MessageData) AS MessageData
FROM (SELECT max(BatchID) AS BatchID FROM DImessages) AS x
CROSS JOIN
(
              SELECT 'DimAccount'        AS MessageSource, 'Row count' AS MessageText, count() AS MessageData FROM DimAccount
    UNION ALL SELECT 'DimBroker',         'Row count', count() FROM DimBroker
    UNION ALL SELECT 'DimCompany',        'Row count', count() FROM DimCompany
    UNION ALL SELECT 'DimCustomer',       'Row count', count() FROM DimCustomer
    UNION ALL SELECT 'DimDate',           'Row count', count() FROM DimDate
    UNION ALL SELECT 'DimSecurity',       'Row count', count() FROM DimSecurity
    UNION ALL SELECT 'DimTime',           'Row count', count() FROM DimTime
    UNION ALL SELECT 'DimTrade',          'Row count', count() FROM DimTrade
    UNION ALL SELECT 'Financial',         'Row count', count() FROM Financial
    UNION ALL SELECT 'Industry',          'Row count', count() FROM Industry
    UNION ALL SELECT 'Prospect',          'Row count', count() FROM Prospect
    UNION ALL SELECT 'StatusType',        'Row count', count() FROM StatusType
    UNION ALL SELECT 'TaxRate',           'Row count', count() FROM TaxRate
    UNION ALL SELECT 'TradeType',         'Row count', count() FROM TradeType
    UNION ALL SELECT 'FactCashBalances',  'Row count', count() FROM FactCashBalances
    UNION ALL SELECT 'FactHoldings',      'Row count', count() FROM FactHoldings
    UNION ALL SELECT 'FactMarketHistory', 'Row count', count() FROM FactMarketHistory
    UNION ALL SELECT 'FactWatches',       'Row count', count() FROM FactWatches
) AS y
SETTINGS final = 1;
