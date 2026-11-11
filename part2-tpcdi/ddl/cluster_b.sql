-- TPC-DI 1.1.0, sections 3.2.1, 3.2.4 and 3.2.15.
-- Execute with a selected Atomic database. No source data is read here.
-- Date32 requires the range check in scripts/prototype_dimaccount.py.
CREATE TABLE DimAccount
(
    SK_AccountID UInt64,
    AccountID UInt64,
    SK_BrokerID UInt64,
    SK_CustomerID UInt64,
    Status String,
    AccountDesc Nullable(String),
    TaxStatus Nullable(UInt8),
    IsCurrent Bool,
    BatchID UInt32,
    EffectiveDate Date32,
    EndDate Date32,
    CONSTRAINT account_tax CHECK isNull(TaxStatus) OR TaxStatus IN (0, 1, 2),
    CONSTRAINT account_period CHECK EffectiveDate < EndDate
)
ENGINE = MergeTree ORDER BY (AccountID, EffectiveDate, SK_AccountID);

CREATE TABLE DimCustomer
(
    SK_CustomerID UInt64,
    CustomerID UInt64,
    TaxID String,
    Status String,
    LastName String,
    FirstName String,
    MiddleInitial Nullable(String),
    Gender Nullable(String),
    Tier Nullable(UInt8),
    DOB Date32,
    AddressLine1 String,
    AddressLine2 Nullable(String),
    PostalCode String,
    City String,
    StateProv String,
    Country Nullable(String),
    Phone1 Nullable(String),
    Phone2 Nullable(String),
    Phone3 Nullable(String),
    Email1 Nullable(String),
    Email2 Nullable(String),
    NationalTaxRateDesc Nullable(String),
    NationalTaxRate Nullable(Decimal(6, 5)),
    LocalTaxRateDesc Nullable(String),
    LocalTaxRate Nullable(Decimal(6, 5)),
    AgencyID Nullable(String),
    CreditRating Nullable(UInt32),
    NetWorth Nullable(Int64),
    MarketingNameplate Nullable(String),
    IsCurrent Bool,
    BatchID UInt32,
    EffectiveDate Date32,
    EndDate Date32
)
ENGINE = MergeTree ORDER BY (CustomerID, EffectiveDate, SK_CustomerID);

CREATE TABLE Prospect
(
    AgencyID String,
    SK_RecordDateID UInt64,
    SK_UpdateDateID UInt64,
    BatchID UInt32,
    IsCustomer Bool,
    LastName String,
    FirstName String,
    MiddleInitial Nullable(String),
    Gender Nullable(String),
    AddressLine1 Nullable(String),
    AddressLine2 Nullable(String),
    PostalCode Nullable(String),
    City String,
    State String,
    Country Nullable(String),
    Phone Nullable(String),
    Income Nullable(UInt32),
    NumberCars Nullable(UInt8),
    NumberChildren Nullable(UInt8),
    MaritalStatus Nullable(String),
    Age Nullable(UInt16),
    CreditRating Nullable(UInt16),
    OwnOrRentFlag Nullable(String),
    Employer Nullable(String),
    NumberCreditCards Nullable(UInt8),
    NetWorth Nullable(UInt64),
    MarketingNameplate Nullable(String)
)
ENGINE = MergeTree ORDER BY AgencyID;
