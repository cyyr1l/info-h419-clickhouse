-- Cluster A: reference tables, DimBroker, DimCompany, DimSecurity, Financial (TPC-DI 1.1.0, 3.2).
-- Type mapping of PR #11: SK/IDENT -> UInt64, BatchID -> UInt32, DATE -> Date32, TIME -> Time64(3),
-- NUM(m,n) -> Decimal(m,n), CHAR -> String, BOOLEAN -> Bool. Optional columns are Nullable.
-- Created in the Initialization phase; loaded in the Historical Load (etl/cluster_a_historical.sql).

CREATE TABLE DimDate
(
    SK_DateID UInt64,
    DateValue Date32,
    DateDesc String,
    CalendarYearID UInt16,
    CalendarYearDesc String,
    CalendarQtrID UInt32,
    CalendarQtrDesc String,
    CalendarMonthID UInt32,
    CalendarMonthDesc String,
    CalendarWeekID UInt32,
    CalendarWeekDesc String,
    DayOfWeekNum UInt8,
    DayOfWeekDesc String,
    FiscalYearID UInt16,
    FiscalYearDesc String,
    FiscalQtrID UInt32,
    FiscalQtrDesc String,
    HolidayFlag Bool
)
ENGINE = MergeTree ORDER BY DateValue;

CREATE TABLE DimTime
(
    SK_TimeID UInt64,
    TimeValue Time64(3),
    HourID UInt8,
    HourDesc String,
    MinuteID UInt8,
    MinuteDesc String,
    SecondID UInt8,
    SecondDesc String,
    MarketHoursFlag Bool,
    OfficeHoursFlag Bool
)
ENGINE = MergeTree ORDER BY TimeValue;

CREATE TABLE Industry (IN_ID String, IN_NAME String, IN_SC_ID String)
ENGINE = MergeTree ORDER BY IN_ID;

CREATE TABLE StatusType (ST_ID String, ST_NAME String)
ENGINE = MergeTree ORDER BY ST_ID;

CREATE TABLE TaxRate (TX_ID String, TX_NAME String, TX_RATE Decimal(6, 5))
ENGINE = MergeTree ORDER BY TX_ID;

CREATE TABLE TradeType (TT_ID String, TT_NAME String, TT_IS_SELL UInt8, TT_IS_MRKT UInt8)
ENGINE = MergeTree ORDER BY TT_ID;

CREATE TABLE DimBroker
(
    SK_BrokerID UInt64,
    BrokerID UInt64,
    ManagerID Nullable(UInt64),
    FirstName String,
    LastName String,
    MiddleInitial Nullable(String),
    Branch Nullable(String),
    Office Nullable(String),
    Phone Nullable(String),
    IsCurrent Bool,
    BatchID UInt32,
    EffectiveDate Date32,
    EndDate Date32
)
ENGINE = MergeTree ORDER BY (BrokerID, EffectiveDate);

CREATE TABLE DimCompany
(
    SK_CompanyID UInt64,
    CompanyID UInt64,
    Status String,                  -- 'Active' / 'Inactive' (ST_NAME)
    Name String,
    Industry String,                -- IN_NAME
    SPrating Nullable(String),      -- NULL when the rating is not valid (alert in DImessages)
    isLowGrade Nullable(Bool),
    CEO String,
    AddressLine1 String,
    AddressLine2 Nullable(String),
    PostalCode String,
    City String,
    StateProv String,
    Country Nullable(String),
    Description String,
    FoundingDate Nullable(Date32),
    IsCurrent Bool,
    BatchID UInt32,
    EffectiveDate Date32,
    EndDate Date32
)
ENGINE = MergeTree ORDER BY (CompanyID, EffectiveDate);

CREATE TABLE DimSecurity
(
    SK_SecurityID UInt64,
    Symbol String,
    Issue String,
    Status String,
    Name String,
    ExchangeID String,
    SK_CompanyID UInt64,
    SharesOutstanding Int64,
    FirstTrade Date32,
    FirstTradeOnExchange Date32,
    Dividend Decimal(10, 2),
    IsCurrent Bool,
    BatchID UInt32,
    EffectiveDate Date32,
    EndDate Date32
)
ENGINE = MergeTree ORDER BY (Symbol, EffectiveDate);

CREATE TABLE Financial
(
    SK_CompanyID UInt64,
    FI_YEAR UInt16,
    FI_QTR UInt8,
    FI_QTR_START_DATE Date32,
    FI_REVENUE Decimal(15, 2),
    FI_NET_EARN Decimal(15, 2),
    FI_BASIC_EPS Decimal(10, 2),
    FI_DILUT_EPS Decimal(10, 2),
    FI_MARGIN Decimal(10, 2),
    FI_INVENTORY Decimal(15, 2),
    FI_ASSETS Decimal(15, 2),
    FI_LIABILITY Decimal(15, 2),
    FI_OUT_BASIC Int64,
    FI_OUT_DILUT Int64
)
ENGINE = MergeTree ORDER BY (SK_CompanyID, FI_YEAR, FI_QTR);
