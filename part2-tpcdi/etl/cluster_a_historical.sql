-- Historical Load of cluster A (TPC-DI 1.1.0, 4.5): reference tables, DimBroker, then
-- FINWIRE -> DimCompany, DimSecurity, Financial. Run in this order.
-- Parameter {batch_dir:String}: the Batch1 folder relative to ClickHouse's user_files,
-- e.g. data/tpcdi/sf10/Batch1.
-- The |-delimited files are unquoted with CRLF line endings: the CSV format reads them.
-- HR.csv is comma-separated, without quotes. Values are not trimmed. Any row that does not
-- parse makes the load fail.

-- 1. Reference tables: direct copies of the source files (4.5.1 to 4.5.6).
INSERT INTO DimDate
SELECT * FROM file(concat({batch_dir:String}, '/Date.txt'), 'CSV',
    'SK_DateID UInt64, DateValue Date32, DateDesc String, CalendarYearID UInt16, CalendarYearDesc String, CalendarQtrID UInt32, CalendarQtrDesc String, CalendarMonthID UInt32, CalendarMonthDesc String, CalendarWeekID UInt32, CalendarWeekDesc String, DayOfWeekNum UInt8, DayOfWeekDesc String, FiscalYearID UInt16, FiscalYearDesc String, FiscalQtrID UInt32, FiscalQtrDesc String, HolidayFlag Bool')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

INSERT INTO DimTime
SELECT * FROM file(concat({batch_dir:String}, '/Time.txt'), 'CSV',
    'SK_TimeID UInt64, TimeValue Time64(3), HourID UInt8, HourDesc String, MinuteID UInt8, MinuteDesc String, SecondID UInt8, SecondDesc String, MarketHoursFlag Bool, OfficeHoursFlag Bool')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

INSERT INTO Industry
SELECT * FROM file(concat({batch_dir:String}, '/Industry.txt'), 'CSV', 'IN_ID String, IN_NAME String, IN_SC_ID String')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

INSERT INTO StatusType
SELECT * FROM file(concat({batch_dir:String}, '/StatusType.txt'), 'CSV', 'ST_ID String, ST_NAME String')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

INSERT INTO TaxRate
SELECT * FROM file(concat({batch_dir:String}, '/TaxRate.txt'), 'CSV', 'TX_ID String, TX_NAME String, TX_RATE Decimal(6, 5)')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

INSERT INTO TradeType
SELECT * FROM file(concat({batch_dir:String}, '/TradeType.txt'), 'CSV', 'TT_ID String, TT_NAME String, TT_IS_SELL UInt8, TT_IS_MRKT UInt8')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

-- 2. DimBroker (4.5.7): the employees of HR.csv with job code 314. One version each,
-- valid from the earliest date of DimDate.
INSERT INTO DimBroker
SELECT row_number() OVER (ORDER BY EmployeeID), EmployeeID, ManagerID, EmployeeFirstName,
    EmployeeLastName, EmployeeMI, EmployeeBranch, EmployeeOffice, EmployeePhone,
    true, 1, (SELECT min(DateValue) FROM DimDate), toDate32('9999-12-31')
FROM file(concat({batch_dir:String}, '/HR.csv'), 'CSV',
    'EmployeeID UInt64, ManagerID Nullable(UInt64), EmployeeFirstName String, EmployeeLastName String, EmployeeMI Nullable(String), EmployeeJobCode Nullable(UInt32), EmployeeBranch Nullable(String), EmployeeOffice Nullable(String), EmployeePhone Nullable(String)')
WHERE EmployeeJobCode = 314
SETTINGS format_csv_delimiter = ',', format_csv_allow_single_quotes = 0, format_csv_allow_double_quotes = 0,
    input_format_csv_empty_as_default = 1, input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

-- 3. FINWIRE: raw lines of all the quarterly files (FINWIRE<YYYY>Q<n>, not the _audit.csv files).
TRUNCATE TABLE stg_FinWire;
INSERT INTO stg_FinWire
SELECT File, substring(Line, 1, 15), substring(Line, 16, 3), Line
FROM
(
    SELECT _file AS File, if(endsWith(line, '\r'), substring(line, 1, length(line) - 1), line) AS Line
    FROM file(concat({batch_dir:String}, '/FINWIRE????Q?'), 'LineAsString', 'line String')
);

-- CMP records (543 characters).
TRUNCATE TABLE stg_FinWire_CMP;
INSERT INTO stg_FinWire_CMP
SELECT PTS, File,
    toDate32(concat(substring(PTS, 1, 4), '-', substring(PTS, 5, 2), '-', substring(PTS, 7, 2))),
    trimRight(substring(Line, 19, 60)),
    toUInt64(trimBoth(substring(Line, 79, 10))),
    trimRight(substring(Line, 89, 4)),
    trimRight(substring(Line, 93, 2)),
    trimRight(substring(Line, 95, 4)),
    toDate32OrNull(concat(substring(Line, 99, 4), '-', substring(Line, 103, 2), '-', substring(Line, 105, 2))),
    trimRight(substring(Line, 107, 80)),
    nullIf(trimRight(substring(Line, 187, 80)), ''),
    trimRight(substring(Line, 267, 12)),
    trimRight(substring(Line, 279, 25)),
    trimRight(substring(Line, 304, 20)),
    nullIf(trimRight(substring(Line, 324, 24)), ''),
    trimRight(substring(Line, 348, 46)),
    trimRight(substring(Line, 394, 150))
FROM stg_FinWire
WHERE RecType = 'CMP';

-- SEC records (170 characters with a CIK, 220 with a company name).
TRUNCATE TABLE stg_FinWire_SEC;
INSERT INTO stg_FinWire_SEC
SELECT PTS, File,
    toDate32(concat(substring(PTS, 1, 4), '-', substring(PTS, 5, 2), '-', substring(PTS, 7, 2))),
    trimRight(substring(Line, 19, 15)),
    trimRight(substring(Line, 34, 6)),
    trimRight(substring(Line, 40, 4)),
    trimRight(substring(Line, 44, 70)),
    trimRight(substring(Line, 114, 6)),
    toInt64(trimBoth(substring(Line, 120, 13))),
    toDate32(concat(substring(Line, 133, 4), '-', substring(Line, 137, 2), '-', substring(Line, 139, 2))),
    toDate32(concat(substring(Line, 141, 4), '-', substring(Line, 145, 2), '-', substring(Line, 147, 2))),
    toDecimal64(trimBoth(substring(Line, 149, 12)), 2),
    if(length(Line) = 170,
       concat('CIK:', toString(toUInt64(trimBoth(substring(Line, 161, 10))))),
       concat('NAME:', trimRight(substring(Line, 161, 60))))
FROM stg_FinWire
WHERE RecType = 'SEC';

-- FIN records (196 characters with a CIK, 246 with a company name).
TRUNCATE TABLE stg_FinWire_FIN;
INSERT INTO stg_FinWire_FIN
SELECT PTS, File,
    toDate32(concat(substring(PTS, 1, 4), '-', substring(PTS, 5, 2), '-', substring(PTS, 7, 2))),
    toUInt16(substring(Line, 19, 4)),
    toUInt8(substring(Line, 23, 1)),
    toDate32(concat(substring(Line, 24, 4), '-', substring(Line, 28, 2), '-', substring(Line, 30, 2))),
    toDate32(concat(substring(Line, 32, 4), '-', substring(Line, 36, 2), '-', substring(Line, 38, 2))),
    toDecimal64(trimBoth(substring(Line, 40, 17)), 2),
    toDecimal64(trimBoth(substring(Line, 57, 17)), 2),
    toDecimal64(trimBoth(substring(Line, 74, 12)), 2),
    toDecimal64(trimBoth(substring(Line, 86, 12)), 2),
    toDecimal64(trimBoth(substring(Line, 98, 12)), 2),
    toDecimal64(trimBoth(substring(Line, 110, 17)), 2),
    toDecimal64(trimBoth(substring(Line, 127, 17)), 2),
    toDecimal64(trimBoth(substring(Line, 144, 17)), 2),
    toInt64(trimBoth(substring(Line, 161, 13))),
    toInt64(trimBoth(substring(Line, 174, 13))),
    if(length(Line) = 196,
       concat('CIK:', toString(toUInt64(trimBoth(substring(Line, 187, 10))))),
       concat('NAME:', trimRight(substring(Line, 187, 60))))
FROM stg_FinWire
WHERE RecType = 'FIN';

-- 4. DimCompany (4.5.9): one version per CMP record, in PTS order per CIK. EndDate is the
-- EffectiveDate of the next version, so the versions are contiguous. An invalid SPrating
-- becomes NULL (with isLowGrade) and is reported in DImessages below.
INSERT INTO DimCompany
WITH ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-',
      'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D'] AS ratings
SELECT row_number() OVER (ORDER BY c.CIK, c.PTS, c.File),
    c.CIK, st.ST_NAME, c.CompanyName, ind.IN_NAME,
    if(has(ratings, c.SPrating), c.SPrating, NULL),
    if(has(ratings, c.SPrating), NOT (startsWith(c.SPrating, 'A') OR startsWith(c.SPrating, 'BBB')), NULL),
    c.CEOname, c.AddrLine1, c.AddrLine2, c.PostalCode, c.City, c.StateProvince, c.Country,
    c.Description, c.FoundingDate,
    c.NextDate = toDate32('9999-12-31'), 1, c.EffectiveDate, c.NextDate
FROM
(
    SELECT *, leadInFrame(EffectiveDate, 1, toDate32('9999-12-31'))
        OVER (PARTITION BY CIK ORDER BY PTS, File ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS NextDate
    FROM stg_FinWire_CMP
) AS c
INNER JOIN StatusType AS st ON st.ST_ID = c.Status
INNER JOIN Industry AS ind ON ind.IN_ID = c.IndustryID;

-- Alerts for the invalid ratings (4.5.9). DImessages belongs to cluster D.
INSERT INTO DImessages (MessageDateAndTime, BatchID, MessageSource, MessageText, MessageType, MessageData)
WITH ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-',
      'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D'] AS ratings
SELECT now64(3), 1, 'DimCompany', 'Invalid SPRating', 'Alert',
    concat('CO_ID = ', toString(CIK), ', CO_SP_RATE = ', SPrating)
FROM stg_FinWire_CMP
WHERE NOT has(ratings, SPrating);

-- 5. DimSecurity (4.5.10): one version per SEC record, in PTS order per Symbol, contiguous.
-- SK_CompanyID: the DimCompany version (matched by CIK or by name) valid on the record's date.
INSERT INTO DimSecurity
SELECT row_number() OVER (ORDER BY s.Symbol, s.PTS, s.File),
    s.Symbol, s.IssueType, st.ST_NAME, s.Name, s.ExID, c.SK_CompanyID, s.ShOut,
    s.FirstTradeDate, s.FirstTradeExchg, s.Dividend,
    s.NextDate = toDate32('9999-12-31'), 1, s.EffectiveDate, s.NextDate
FROM
(
    SELECT *, leadInFrame(EffectiveDate, 1, toDate32('9999-12-31'))
        OVER (PARTITION BY Symbol ORDER BY PTS, File ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS NextDate
    FROM stg_FinWire_SEC
) AS s
ASOF INNER JOIN
(
    SELECT SK_CompanyID, EffectiveDate, concat('CIK:', toString(CompanyID)) AS CoKey FROM DimCompany
    UNION ALL
    SELECT SK_CompanyID, EffectiveDate, concat('NAME:', Name) AS CoKey FROM DimCompany
) AS c ON c.CoKey = s.CoKey AND s.EffectiveDate >= c.EffectiveDate
INNER JOIN StatusType AS st ON st.ST_ID = s.Status;

-- 6. Financial (4.5.11): one row per FIN record, with the DimCompany version valid on its date.
INSERT INTO Financial
SELECT c.SK_CompanyID, f.Year, f.Quarter, f.QtrStartDate, f.Revenue, f.Earnings, f.EPS,
    f.DilutedEPS, f.Margin, f.Inventory, f.Assets, f.Liabilities, f.ShOut, f.DilutedShOut
FROM stg_FinWire_FIN AS f
ASOF INNER JOIN
(
    SELECT SK_CompanyID, EffectiveDate, concat('CIK:', toString(CompanyID)) AS CoKey FROM DimCompany
    UNION ALL
    SELECT SK_CompanyID, EffectiveDate, concat('NAME:', Name) AS CoKey FROM DimCompany
) AS c ON c.CoKey = f.CoKey AND f.EffectiveDate >= c.EffectiveDate;
