-- Historical load of FactMarketHistory (spec 4.5.6). Run in the DW database (e.g. tpcdi_sf10).
-- Needs DimSecurity, DimCompany, Financial and DimDate (cluster A) and DImessages.

-- 1. Staging: DailyMarket.txt is '|'-separated with CRLF line endings.
TRUNCATE TABLE stg_DailyMarket;
INSERT INTO stg_DailyMarket
SELECT * FROM file('data/tpcdi/sf10/Batch1/DailyMarket.txt', 'CSV',
                   'DM_DATE Date32, DM_S_SYMB String, DM_CLOSE Decimal(8, 2), DM_HIGH Decimal(8, 2), DM_LOW Decimal(8, 2), DM_VOL Int64')
SETTINGS format_csv_delimiter = '|';

-- 2. FactMarketHistory.
-- 52-week high/low: highest DM_HIGH (lowest DM_LOW) from DM_DATE back to, but not including, the same date
-- one year earlier, and the earliest date on which it occurred. A window frame has a fixed size, so both a
-- 365-day and a 366-day frame are computed and the 366-day one is used when the year contains a 29 February.
-- max((price, -day)) gives the highest price and, among ties, the earliest day; min((price, day)) the lowest.
-- PERatio: DM_CLOSE / sum of FI_BASIC_EPS of the company over the 4 quarters before the quarter of DM_DATE.
-- Financial is keyed by SK_CompanyID, which changes with each DimCompany version, so the quarters are
-- grouped by CompanyID.
INSERT INTO FactMarketHistory
WITH
    dm AS (
        SELECT
            DM_DATE, DM_S_SYMB, DM_CLOSE, DM_HIGH, DM_LOW, DM_VOL,
            max((DM_HIGH, -toInt32(DM_DATE))) OVER w365 AS hi365,
            max((DM_HIGH, -toInt32(DM_DATE))) OVER w366 AS hi366,
            min((DM_LOW,   toInt32(DM_DATE))) OVER w365 AS lo365,
            min((DM_LOW,   toInt32(DM_DATE))) OVER w366 AS lo366,
            toInt32(DM_DATE) - toInt32(DM_DATE - INTERVAL 1 YEAR) = 366 AS leap
        FROM stg_DailyMarket
        WINDOW
            w365 AS (PARTITION BY DM_S_SYMB ORDER BY toInt32(DM_DATE) RANGE BETWEEN 364 PRECEDING AND CURRENT ROW),
            w366 AS (PARTITION BY DM_S_SYMB ORDER BY toInt32(DM_DATE) RANGE BETWEEN 365 PRECEDING AND CURRENT ROW)
    ),
    -- Sum of EPS of the 4 quarters before each quarter: every Financial row counts for the next 4 quarters.
    eps AS (
        SELECT c.CompanyID AS CompanyID,
               toInt32(f.FI_YEAR) * 4 + f.FI_QTR - 1 + k AS QtrIdx,
               sum(f.FI_BASIC_EPS) AS EPS4
        FROM Financial AS f
        INNER JOIN DimCompany AS c ON c.SK_CompanyID = f.SK_CompanyID
        ARRAY JOIN [1, 2, 3, 4] AS k
        GROUP BY CompanyID, QtrIdx
    )
SELECT
    s.SK_SecurityID,
    s.SK_CompanyID,
    d.SK_DateID,
    if(e.EPS4 IS NULL OR e.EPS4 = 0, NULL,
       toDecimal64(round(toFloat64(dm.DM_CLOSE) / toFloat64(e.EPS4), 2), 2))            AS PERatio,
    toDecimal64(round(toFloat64(s.Dividend) / toFloat64(dm.DM_CLOSE) * 100, 2), 2)       AS Yield,
    (if(dm.leap, dm.hi366, dm.hi365)).1                                                  AS FiftyTwoWeekHigh,
    hd.SK_DateID                                                                         AS SK_FiftyTwoWeekHighDate,
    (if(dm.leap, dm.lo366, dm.lo365)).1                                                  AS FiftyTwoWeekLow,
    ld.SK_DateID                                                                         AS SK_FiftyTwoWeekLowDate,
    dm.DM_CLOSE, dm.DM_HIGH, dm.DM_LOW, dm.DM_VOL,
    1 AS BatchID
FROM dm
INNER JOIN DimSecurity AS s
        ON s.Symbol = dm.DM_S_SYMB AND s.EffectiveDate <= dm.DM_DATE AND dm.DM_DATE < s.EndDate
INNER JOIN DimCompany  AS c  ON c.SK_CompanyID = s.SK_CompanyID
INNER JOIN DimDate     AS d  ON d.DateValue = dm.DM_DATE
INNER JOIN DimDate     AS hd ON hd.DateValue = toDate32(-(if(dm.leap, dm.hi366, dm.hi365)).2)
INNER JOIN DimDate     AS ld ON ld.DateValue = toDate32((if(dm.leap, dm.lo366, dm.lo365)).2)
LEFT JOIN eps AS e
       ON e.CompanyID = c.CompanyID AND e.QtrIdx = toYear(dm.DM_DATE) * 4 + toQuarter(dm.DM_DATE) - 1
SETTINGS join_use_nulls = 1;

-- 3. Alert for every row without earnings (spec 4.5.6).
INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
SELECT now64(3), 1, 'FactMarketHistory', 'No earnings for company', 'Alert', concat('DM_S_SYMB = ', s.Symbol)
FROM FactMarketHistory AS f
INNER JOIN DimSecurity AS s ON s.SK_SecurityID = f.SK_SecurityID
WHERE f.BatchID = 1 AND f.PERatio IS NULL;
