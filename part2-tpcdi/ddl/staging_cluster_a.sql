-- Staging tables of cluster A, named stg_<File> like the other clusters.
-- FINWIRE files are fixed-width: they are first loaded as raw lines (stg_FinWire), then cut
-- into one typed table per record type (stg_FinWire_CMP, _SEC, _FIN) with substring().
-- Text fields are right-padded with spaces: trimRight() removes the padding only.
-- An empty optional field becomes NULL.

CREATE TABLE stg_FinWire
(
    File String,         -- e.g. FINWIRE1967Q1, tie-breaker after PTS
    PTS String,          -- YYYYMMDD-HHMMSS, sorts in time order as text
    RecType String,      -- CMP, SEC or FIN
    Line String          -- the whole line, without the trailing CR
)
ENGINE = MergeTree ORDER BY (RecType, PTS, File);

CREATE TABLE stg_FinWire_CMP
(
    PTS String,
    File String,
    EffectiveDate Date32,            -- date part of PTS
    CompanyName String,
    CIK UInt64,
    Status String,                   -- ST_ID, e.g. ACTV
    IndustryID String,
    SPrating String,
    FoundingDate Nullable(Date32),
    AddrLine1 String,
    AddrLine2 Nullable(String),
    PostalCode String,
    City String,
    StateProvince String,
    Country Nullable(String),
    CEOname String,
    Description String
)
ENGINE = MergeTree ORDER BY (CIK, PTS, File);

CREATE TABLE stg_FinWire_SEC
(
    PTS String,
    File String,
    EffectiveDate Date32,
    Symbol String,
    IssueType String,
    Status String,
    Name String,
    ExID String,
    ShOut Int64,
    FirstTradeDate Date32,
    FirstTradeExchg Date32,
    Dividend Decimal(10, 2),
    CoKey String                     -- 'CIK:<n>' or 'NAME:<company name>' (CoNameOrCIK)
)
ENGINE = MergeTree ORDER BY (Symbol, PTS, File);

CREATE TABLE stg_FinWire_FIN
(
    PTS String,
    File String,
    EffectiveDate Date32,
    Year UInt16,
    Quarter UInt8,
    QtrStartDate Date32,
    PostingDate Date32,
    Revenue Decimal(15, 2),
    Earnings Decimal(15, 2),
    EPS Decimal(10, 2),
    DilutedEPS Decimal(10, 2),
    Margin Decimal(10, 2),
    Inventory Decimal(15, 2),
    Assets Decimal(15, 2),
    Liabilities Decimal(15, 2),
    ShOut Int64,
    DilutedShOut Int64,
    CoKey String
)
ENGINE = MergeTree ORDER BY (CoKey, PTS, File);
