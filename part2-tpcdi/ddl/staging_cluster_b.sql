-- Staging tables of cluster B, named stg_<File> like the other clusters.
-- Created in the Initialization phase. Each phase truncates them and loads its own batch
-- (scripts/load_staging_cluster_b.py).
--
-- Every source field is kept as a raw Nullable(String): the casts and the spec rules
-- (3.2.4, 3.2.15, 4.4.2) are applied by the cluster B SQL, not by the loader.

-- CustomerMgmt.xml (Batch1 only): one row per <TPCDI:Action>, in file order.
-- NULL = the element or attribute is absent (keep the previous value),
-- ''   = present but empty. Values are never trimmed.
-- The 4 phone sub-fields are prefixed with their phone number: C_PHONE_1_C_LOCAL, ...
CREATE TABLE stg_CustomerMgmt
(
    ActionSeq UInt64,              -- position of the Action in the file, 1, 2, ...
    ActionType String,             -- NEW, ADDACCT, UPDACCT, UPDCUST, CLOSEACCT, INACT
    ActionTS String,               -- e.g. 2007-07-07T02:56:25
    C_ID Nullable(String),
    C_TAX_ID Nullable(String),
    C_GNDR Nullable(String),
    C_TIER Nullable(String),
    C_DOB Nullable(String),
    C_L_NAME Nullable(String),
    C_F_NAME Nullable(String),
    C_M_NAME Nullable(String),
    C_ADLINE1 Nullable(String),
    C_ADLINE2 Nullable(String),
    C_ZIPCODE Nullable(String),
    C_CITY Nullable(String),
    C_STATE_PROV Nullable(String),
    C_CTRY Nullable(String),
    C_PRIM_EMAIL Nullable(String),
    C_ALT_EMAIL Nullable(String),
    C_PHONE_1_C_CTRY_CODE Nullable(String),
    C_PHONE_1_C_AREA_CODE Nullable(String),
    C_PHONE_1_C_LOCAL Nullable(String),
    C_PHONE_1_C_EXT Nullable(String),
    C_PHONE_2_C_CTRY_CODE Nullable(String),
    C_PHONE_2_C_AREA_CODE Nullable(String),
    C_PHONE_2_C_LOCAL Nullable(String),
    C_PHONE_2_C_EXT Nullable(String),
    C_PHONE_3_C_CTRY_CODE Nullable(String),
    C_PHONE_3_C_AREA_CODE Nullable(String),
    C_PHONE_3_C_LOCAL Nullable(String),
    C_PHONE_3_C_EXT Nullable(String),
    C_LCL_TX_ID Nullable(String),
    C_NAT_TX_ID Nullable(String),
    CA_ID Nullable(String),
    CA_TAX_ST Nullable(String),
    CA_B_ID Nullable(String),
    CA_NAME Nullable(String)
)
ENGINE = MergeTree ORDER BY ActionSeq;

-- Prospect.csv (every batch, full snapshot): the 22 fields of 2.2.2.11, in file order.
-- An empty field is NULL.
CREATE TABLE stg_Prospect
(
    AgencyID Nullable(String),
    LastName Nullable(String),
    FirstName Nullable(String),
    MiddleInitial Nullable(String),
    Gender Nullable(String),
    AddressLine1 Nullable(String),
    AddressLine2 Nullable(String),
    PostalCode Nullable(String),
    City Nullable(String),
    State Nullable(String),
    Country Nullable(String),
    Phone Nullable(String),
    Income Nullable(String),
    NumberCars Nullable(String),
    NumberChildren Nullable(String),
    MaritalStatus Nullable(String),
    Age Nullable(String),
    CreditRating Nullable(String),
    OwnOrRentFlag Nullable(String),
    Employer Nullable(String),
    NumberCreditCards Nullable(String),
    NetWorth Nullable(String)
)
ENGINE = MergeTree ORDER BY tuple();
