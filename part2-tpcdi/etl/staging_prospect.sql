-- Load Prospect.csv of one batch into stg_Prospect.
-- Parameter {batch_dir:String}: the batch folder relative to ClickHouse's user_files,
-- e.g. data/tpcdi/sf10/Batch1.
-- Prospect.csv is the only source file that is real CSV: comma-separated, with quoted
-- fields such as "Toys ""R"" Us", so double quotes are on here (they are off for the
-- |-delimited files). Values are not trimmed. An empty field is NULL. Any row that does
-- not parse makes the load fail.

TRUNCATE TABLE stg_Prospect;
INSERT INTO stg_Prospect
SELECT *
FROM file(concat({batch_dir:String}, '/Prospect.csv'), 'CSV',
    'AgencyID Nullable(String), LastName Nullable(String), FirstName Nullable(String), MiddleInitial Nullable(String), Gender Nullable(String), AddressLine1 Nullable(String), AddressLine2 Nullable(String), PostalCode Nullable(String), City Nullable(String), State Nullable(String), Country Nullable(String), Phone Nullable(String), Income Nullable(String), NumberCars Nullable(String), NumberChildren Nullable(String), MaritalStatus Nullable(String), Age Nullable(String), CreditRating Nullable(String), OwnOrRentFlag Nullable(String), Employer Nullable(String), NumberCreditCards Nullable(String), NetWorth Nullable(String)')
SETTINGS format_csv_delimiter = ',', format_csv_allow_double_quotes = 1,
    format_csv_allow_single_quotes = 0, input_format_csv_empty_as_default = 1,
    input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;
