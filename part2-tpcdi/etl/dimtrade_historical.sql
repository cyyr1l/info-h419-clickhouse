-- DimTrade, Historical Load (4.5.8): one row per trade, from stg_Trade and stg_TradeHistory.
-- Needs, loaded earlier in the phase: DimDate, DimTime, StatusType, TradeType and DimSecurity
-- (cluster A), DimAccount (cluster B).
-- Mandatory lookups are INNER joins: a failed lookup drops the trade, and the row count no
-- longer matches the audit value T_NEW, instead of a silent 0 key.

INSERT INTO DimTrade (TradeID, SK_BrokerID, SK_CreateDateID, SK_CreateTimeID, SK_CloseDateID,
    SK_CloseTimeID, Status, Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice,
    SK_CustomerID, SK_AccountID, ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID)
WITH history AS
(
    -- Created: the PNDG row, or the SBMT row of a market order (TMB, TMS).
    -- Closed: the CMPT or CNCL row; NULL while the trade is open.
    -- First seen: the earliest row; the dimension keys are the ones valid at that time.
    SELECT h.TH_T_ID AS TradeID,
        minIfOrNull(h.TH_DTS, h.TH_ST_ID = 'PNDG'
                              OR (h.TH_ST_ID = 'SBMT' AND t.T_TT_ID IN ('TMB', 'TMS'))) AS create_ts,
        minIfOrNull(h.TH_DTS, h.TH_ST_ID IN ('CMPT', 'CNCL')) AS close_ts,
        min(h.TH_DTS) AS first_ts
    FROM stg_TradeHistory AS h
    INNER JOIN stg_Trade AS t ON t.T_ID = h.TH_T_ID
    GROUP BY h.TH_T_ID
)
SELECT t.T_ID, a.SK_BrokerID,
    cd.SK_DateID, ct.SK_TimeID,
    xd.SK_DateID, xt.SK_TimeID,
    st.ST_NAME, tt.TT_NAME, t.T_IS_CASH,
    s.SK_SecurityID, s.SK_CompanyID,
    t.T_QTY, t.T_BID_PRICE,
    a.SK_CustomerID, a.SK_AccountID,
    t.T_EXEC_NAME, t.T_TRADE_PRICE, t.T_CHRG, t.T_COMM, t.T_TAX,
    toUInt32(1)
FROM stg_Trade AS t
INNER JOIN history AS hi ON hi.TradeID = t.T_ID
INNER JOIN StatusType AS st ON st.ST_ID = t.T_ST_ID
INNER JOIN TradeType AS tt ON tt.TT_ID = t.T_TT_ID
INNER JOIN DimDate AS cd ON cd.DateValue = toDate32(hi.create_ts)
INNER JOIN DimTime AS ct ON ct.TimeValue = toTime64(toStartOfSecond(hi.create_ts), 3)
LEFT JOIN DimDate AS xd ON xd.DateValue = toDate32(hi.close_ts)
LEFT JOIN DimTime AS xt ON xt.TimeValue = toTime64(toStartOfSecond(hi.close_ts), 3)
ASOF JOIN DimSecurity AS s ON s.Symbol = t.T_S_SYMB AND toDate32(hi.first_ts) >= s.EffectiveDate
ASOF JOIN DimAccount AS a ON a.AccountID = t.T_CA_ID AND toDate32(hi.first_ts) >= a.EffectiveDate
SETTINGS join_use_nulls = 1;

-- Alerts (4.5.8.3, 4.5.8.4). The audit counts them by exact MessageText.
INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
SELECT now64(3), toUInt32(1), 'DimTrade', 'Invalid trade commission', 'Alert',
    concat('T_ID = ', toString(T_ID), ', T_COMM = ', toString(T_COMM))
FROM stg_Trade
WHERE T_COMM IS NOT NULL AND T_COMM > T_TRADE_PRICE * T_QTY
UNION ALL
SELECT now64(3), toUInt32(1), 'DimTrade', 'Invalid trade fee', 'Alert',
    concat('T_ID = ', toString(T_ID), ', T_CHRG = ', toString(T_CHRG))
FROM stg_Trade
WHERE T_CHRG IS NOT NULL AND T_CHRG > T_TRADE_PRICE * T_QTY;
