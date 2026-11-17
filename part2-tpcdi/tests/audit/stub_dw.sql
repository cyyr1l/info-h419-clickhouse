-- Minimal stand-in DW tables for testing the audit/validation SQL before the real DDL is merged.
-- Only the columns used by Appendix B/C, with the group type rule (SK -> UInt64, BOOLEAN -> Bool). Do NOT use in the pipeline.
CREATE TABLE DimAccount  (SK_AccountID UInt64, SK_BrokerID UInt64) ENGINE = MergeTree ORDER BY SK_AccountID;
CREATE TABLE DimBroker   (SK_BrokerID UInt64) ENGINE = MergeTree ORDER BY SK_BrokerID;
CREATE TABLE DimCompany  (SK_CompanyID UInt64) ENGINE = MergeTree ORDER BY SK_CompanyID;
CREATE TABLE DimCustomer (SK_CustomerID UInt64, IsCurrent Bool, Status String) ENGINE = MergeTree ORDER BY SK_CustomerID;
CREATE TABLE DimDate     (SK_DateID UInt64) ENGINE = MergeTree ORDER BY SK_DateID;
CREATE TABLE DimSecurity (SK_SecurityID UInt64) ENGINE = MergeTree ORDER BY SK_SecurityID;
CREATE TABLE DimTime     (SK_TimeID UInt64) ENGINE = MergeTree ORDER BY SK_TimeID;
-- ReplacingMergeTree without version column, like the planned DimTrade
CREATE TABLE DimTrade    (TradeID UInt64, Status String) ENGINE = ReplacingMergeTree ORDER BY TradeID;
CREATE TABLE FactCashBalances (SK_AccountID UInt64, SK_CustomerID UInt64, SK_DateID UInt64) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE FactHoldings (SK_AccountID UInt64, SK_CustomerID UInt64, SK_DateID UInt64, SK_TimeID UInt64,
                           SK_CompanyID UInt64, SK_SecurityID UInt64) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE FactMarketHistory (SK_DateID UInt64, SK_CompanyID UInt64, SK_SecurityID UInt64) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE FactWatches (SK_CustomerID UInt64, SK_SecurityID UInt64, SK_DateID_DatePlaced UInt64,
                          SK_DateID_DateRemoved Nullable(UInt64)) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE Financial   (SK_CompanyID UInt64) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE Industry    (IN_ID String) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE Prospect    (AgencyID String) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE StatusType  (ST_ID String) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE TaxRate     (TX_ID String) ENGINE = MergeTree ORDER BY tuple();
CREATE TABLE TradeType   (TT_ID String) ENGINE = MergeTree ORDER BY tuple();
