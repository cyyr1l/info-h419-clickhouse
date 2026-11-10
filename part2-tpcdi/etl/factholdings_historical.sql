-- FactHoldings, Historical Load (4.5.10): one row per HoldingHistory row. The keys, the price and
-- the date and time come from the current trade (HH_T_ID) in DimTrade, read with FINAL.
-- Needs DimTrade of the same phase. Every current trade is completed, so it has a close date;
-- the CAST to UInt64 fails loudly if one does not.

INSERT INTO FactHoldings (TradeID, CurrentTradeID, SK_CustomerID, SK_AccountID, SK_SecurityID,
    SK_CompanyID, SK_DateID, SK_TimeID, CurrentPrice, CurrentHolding, BatchID)
SELECT hh.HH_H_T_ID, hh.HH_T_ID, t.SK_CustomerID, t.SK_AccountID, t.SK_SecurityID, t.SK_CompanyID,
    CAST(t.SK_CloseDateID AS UInt64), CAST(t.SK_CloseTimeID AS UInt64),
    t.TradePrice, hh.HH_AFTER_QTY, toUInt32(1)
FROM stg_HoldingHistory AS hh
INNER JOIN
(
    SELECT TradeID, SK_CustomerID, SK_AccountID, SK_SecurityID, SK_CompanyID,
        SK_CloseDateID, SK_CloseTimeID, TradePrice
    FROM DimTrade FINAL
) AS t ON t.TradeID = hh.HH_T_ID;
