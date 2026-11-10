-- Historical Load: load the Batch1 files of cluster C into staging. This step reads the
-- Staging Area, so it is part of the timed phase (7.2.3.4).
-- Parameter {batch_dir:String}: the Batch1 folder relative to ClickHouse's user_files,
-- e.g. data/tpcdi/sf10/Batch1.
-- The files are |-delimited, unquoted, with CRLF line endings: the CSV format reads them
-- correctly. An empty field is NULL. Any row that does not parse makes the load fail.

TRUNCATE TABLE stg_Trade;
INSERT INTO stg_Trade (T_ID, T_DTS, T_ST_ID, T_TT_ID, T_IS_CASH, T_S_SYMB, T_QTY, T_BID_PRICE,
    T_CA_ID, T_EXEC_NAME, T_TRADE_PRICE, T_CHRG, T_COMM, T_TAX)
SELECT T_ID, toDateTime64(T_DTS, 3, 'UTC'), T_ST_ID, T_TT_ID, T_IS_CASH, T_S_SYMB, T_QTY,
    T_BID_PRICE, T_CA_ID, T_EXEC_NAME, T_TRADE_PRICE, T_CHRG, T_COMM, T_TAX
FROM file(concat({batch_dir:String}, '/Trade.txt'), 'CSV',
    'T_ID UInt64, T_DTS String, T_ST_ID String, T_TT_ID String, T_IS_CASH Bool, T_S_SYMB String, T_QTY UInt32, T_BID_PRICE Decimal(8, 2), T_CA_ID UInt64, T_EXEC_NAME String, T_TRADE_PRICE Nullable(Decimal(8, 2)), T_CHRG Nullable(Decimal(10, 2)), T_COMM Nullable(Decimal(10, 2)), T_TAX Nullable(Decimal(10, 2))')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0,
    format_csv_allow_double_quotes = 0, input_format_csv_empty_as_default = 1,
    input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

TRUNCATE TABLE stg_TradeHistory;
INSERT INTO stg_TradeHistory (TH_T_ID, TH_DTS, TH_ST_ID)
SELECT TH_T_ID, toDateTime64(TH_DTS, 3, 'UTC'), TH_ST_ID
FROM file(concat({batch_dir:String}, '/TradeHistory.txt'), 'CSV',
    'TH_T_ID UInt64, TH_DTS String, TH_ST_ID String')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0,
    format_csv_allow_double_quotes = 0, input_format_csv_empty_as_default = 1,
    input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

TRUNCATE TABLE stg_CashTransaction;
INSERT INTO stg_CashTransaction (CT_CA_ID, CT_DTS, CT_AMT, CT_NAME)
SELECT CT_CA_ID, toDateTime64(CT_DTS, 3, 'UTC'), CT_AMT, CT_NAME
FROM file(concat({batch_dir:String}, '/CashTransaction.txt'), 'CSV',
    'CT_CA_ID UInt64, CT_DTS String, CT_AMT Decimal(10, 2), CT_NAME String')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0,
    format_csv_allow_double_quotes = 0, input_format_csv_empty_as_default = 1,
    input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;

TRUNCATE TABLE stg_HoldingHistory;
INSERT INTO stg_HoldingHistory (HH_H_T_ID, HH_T_ID, HH_BEFORE_QTY, HH_AFTER_QTY)
SELECT HH_H_T_ID, HH_T_ID, HH_BEFORE_QTY, HH_AFTER_QTY
FROM file(concat({batch_dir:String}, '/HoldingHistory.txt'), 'CSV',
    'HH_H_T_ID UInt64, HH_T_ID UInt64, HH_BEFORE_QTY Int32, HH_AFTER_QTY Int32')
SETTINGS format_csv_delimiter = '|', format_csv_allow_single_quotes = 0,
    format_csv_allow_double_quotes = 0, input_format_csv_empty_as_default = 1,
    input_format_csv_trim_whitespaces = 0, input_format_csv_detect_header = 0,
    input_format_allow_errors_num = 0, input_format_allow_errors_ratio = 0;
