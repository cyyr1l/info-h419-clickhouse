# Cluster C: DimTrade, FactCashBalances, FactHoldings

**Owner:** ② · **Source:** TPC-DI v1.1.0 specification; the § numbers refer to it.
These are reading notes for the historical load (weeks 6–7) and the incremental batches (weeks 8–9). The measurement rules are in `docs/benchmark-protocol-part2.md`.

## 1. Source files (§2.2.2)
- **Format:** the files are `|`-delimited text, without a header row. An empty field is NULL.
- **Batch2 and Batch3:** each row starts with two extra fields, `CDC_FLAG` and `CDC_DSN`, and the rows are ordered by `CDC_DSN`.

| File | Batches | Fields (after `CDC_FLAG`, `CDC_DSN` in Batch2/3) | Notes |
|---|---|---|---|
| `Trade.txt` (§2.2.2.17) | 1, 2, 3 | T_ID, T_DTS, T_ST_ID, T_TT_ID, T_IS_CASH, T_S_SYMB, T_QTY, T_BID_PRICE, T_CA_ID, T_EXEC_NAME, T_TRADE_PRICE, T_CHRG, T_COMM, T_TAX | `CDC_FLAG` is 'I' or 'U'. Price, fee, commission and tax are NULL except in CMPT (completed) rows. Batch1 is ordered by T_ID. |
| `TradeHistory.txt` (§2.2.2.16) | 1 only | TH_T_ID, TH_DTS, TH_ST_ID | One row per status change of a trade, ordered by TH_T_ID. |
| `CashTransaction.txt` (§2.2.2.3) | 1, 2, 3 | CT_CA_ID, CT_DTS, CT_AMT, CT_NAME | `CDC_FLAG` is always 'I'. |
| `HoldingHistory.txt` (§2.2.2.9) | 1, 2, 3 | HH_H_T_ID, HH_T_ID, HH_BEFORE_QTY, HH_AFTER_QTY | HH_H_T_ID is the trade that opened the holding, HH_T_ID the current trade. `CDC_FLAG` is always 'I'. |
| `BatchDate.txt` (§2.2.2.2) | 1, 2, 3 | BatchDate | Gives SK_DateID of FactCashBalances in Batch2/3. |

**Types (Table 2.2.2):**

| Fields | Spec type | Meaning |
|---|---|---|
| T_ID, TH_T_ID, HH_H_T_ID, HH_T_ID | TRADE_T = NUM(15) | trade ids |
| T_CA_ID, CT_CA_ID | IDENT_T = NUM(11) | account ids |
| T_QTY, HH_*_QTY | S_QTY_T = NUM(6) | quantities |
| prices | S_PRICE_T = SNUM(8,2) | |
| fees, CT_AMT | VALUE_T = SNUM(10,2) | |
| T_DTS, CT_DTS | DATETIME | `YYYY-MM-DD HH:MM:SS` |

**Lookups from other clusters:**
- cluster A: StatusType (ST_ID → ST_NAME), TradeType (TT_ID → TT_NAME), DimDate (DateValue), DimTime (TimeValue) and DimSecurity;
- cluster B: DimAccount.

## 2. Target tables (Clause 3.2)
- **DimTrade** (§3.2.7.1, Table 3.2.10):
  - Columns: TradeID, SK_BrokerID, SK_CreateDateID, SK_CreateTimeID, SK_CloseDateID, SK_CloseTimeID, Status, Type, CashFlag, SK_SecurityID, SK_CompanyID, Quantity, BidPrice, SK_CustomerID, SK_AccountID, ExecutedBy, TradePrice, Fee, Commission, Tax, BatchID.
  - It is not history-tracking: one row per trade, with the create and close date/time, updated in place.
  - There is no surrogate key: TradeID is the key.
- **FactCashBalances** (§3.2.9): SK_CustomerID, SK_AccountID, SK_DateID, Cash (SNUM(15,2)), BatchID.
- **FactHoldings** (§3.2.10):
  - Columns: TradeID, CurrentTradeID, SK_CustomerID, SK_AccountID, SK_SecurityID, SK_CompanyID, SK_DateID, SK_TimeID, CurrentPrice (> 0), CurrentHolding (SNUM(6), may be negative), BatchID.
  - The dependency table of §4.3.3 names the first two columns SK_TradeID and SK_CurrentTradeID. Table 3.2.13 calls them TradeID and CurrentTradeID, with trade ids as values. We follow Table 3.2.13.
- **Columns:** none may be added or removed (§3.4.5). BatchID is the batch that created the row.

## 3. Dependencies (§4.3.3)
- DimTrade needs:
  - DimDate, DimTime, StatusType, TradeType and DimSecurity (cluster A);
  - DimAccount (cluster B).

  The dimension updates of the same batch must be finished first (§4.5.8.2, §4.6.7.2).
- FactCashBalances needs DimAccount and DimDate.
- FactHoldings needs DimTrade of the same batch.
- So cluster C runs last in every phase. Until clusters A and B exist, we develop against a few dummy dimension rows.

## 4. Historical load (Batch1)
### DimTrade (§4.5.8)
- **Source:** one row per trade, from `Trade.txt` joined with `TradeHistory.txt` on T_ID = TH_T_ID. The history rows of a trade are its status changes.
- **Create:** SK_CreateDateID and SK_CreateTimeID come from the TH_DTS of one history row. That is the 'PNDG' row, or the 'SBMT' row when T_TT_ID is 'TMB' or 'TMS'. The time is truncated to the second.
- **Close:** SK_CloseDateID and SK_CloseTimeID come from the TH_DTS of the 'CMPT' or 'CNCL' row. They stay NULL while the trade is open.
- **Copied fields:** TradeID ← T_ID, CashFlag ← T_IS_CASH, Quantity ← T_QTY, BidPrice ← T_BID_PRICE, ExecutedBy ← T_EXEC_NAME, TradePrice ← T_TRADE_PRICE, Fee ← T_CHRG, Commission ← T_COMM, Tax ← T_TAX.
- **Lookups:** Status ← StatusType.ST_NAME for T_ST_ID; Type ← TradeType.TT_NAME for T_TT_ID.
- **Dimension keys, taken at the first time the trade appears** (its earliest TH_DTS):
  - SK_SecurityID and SK_CompanyID come from the DimSecurity row with Symbol = T_S_SYMB that is valid at that time.
  - SK_AccountID, SK_CustomerID and SK_BrokerID come from the DimAccount row with AccountID = T_CA_ID that is valid at that time.
  - A row is valid when EffectiveDate ≤ date < EndDate.
  - These keys do not change when the trade closes later.
- **BatchID** = 1.
- **Alerts** to DImessages, with MessageSource 'DimTrade' and MessageType 'Alert':
  - 'Invalid trade commission' when T_COMM is not NULL and > T_TRADE_PRICE × T_QTY. MessageData is `T_ID = <T_ID>, T_COMM = <T_COMM>`.
  - 'Invalid trade fee' when T_CHRG is not NULL and > T_TRADE_PRICE × T_QTY. MessageData is `T_ID = <T_ID>, T_CHRG = <T_CHRG>`.
- **ClickHouse sketch:** a single `INSERT … SELECT`:
  1. aggregate `TradeHistory` per TH_T_ID, taking the create, close and first times with `minIf(TH_DTS, …)`;
  2. join the result to `Trade` and to the two lookup tables;
  3. find the valid versions of the two history-tracking dimensions with `ASOF JOIN` on (natural key, EffectiveDate ≤ date).

### FactCashBalances (§4.5.9)
- **Rows:** one row per account and day with transactions: the sum of CT_AMT per (CT_CA_ID, date of CT_DTS).
- **Cash:** a running total per account, the previous Cash of the account plus the day's sum (0 before the first row): `sum(day_amount) OVER (PARTITION BY CT_CA_ID ORDER BY day)`.
  - Partition on the natural key, not on SK_AccountID, because the account may get a new surrogate key in between (note of §4.5.9.2).
- **Keys:**
  - SK_CustomerID and SK_AccountID come from the DimAccount row with AccountID = CT_CA_ID that is valid on that day.
  - SK_DateID comes from DimDate, for the date of CT_DTS.
- **BatchID** = 1.

### FactHoldings (§4.5.10)
- **Rows:** one row per `HoldingHistory` row.
- **From DimTrade, where TradeID = HH_T_ID:** SK_CustomerID, SK_AccountID, SK_SecurityID, SK_CompanyID, CurrentPrice ← TradePrice, SK_DateID ← SK_CloseDateID, SK_TimeID ← SK_CloseTimeID.
- **From the file:** TradeID ← HH_H_T_ID, CurrentTradeID ← HH_T_ID, CurrentHolding ← HH_AFTER_QTY.
- **BatchID** = 1.

## 5. Incremental updates (Batch2, Batch3)
### DimTrade (§4.6.7)
- **Source:** `Trade.txt` only. `CDC_FLAG` 'I' is a new trade. 'U' updates the DimTrade row with TradeID = T_ID.
- **New trade:** SK_CreateDateID and SK_CreateTimeID come from T_DTS, and the close keys are NULL.
- **Close:** when T_ST_ID is 'CMPT' or 'CNCL' (in an 'I' or 'U' row), SK_CloseDateID and SK_CloseTimeID come from T_DTS.
- **Copied fields and lookups:** as in the historical load.
- **Dimension keys of a new trade:**
  - SK_SecurityID and SK_CompanyID come from DimSecurity where Symbol = T_S_SYMB and IsCurrent = 1.
  - SK_AccountID, SK_CustomerID and SK_BrokerID come from DimAccount where AccountID = T_CA_ID and IsCurrent = 1.
- **An update keeps:** these keys, SK_CreateDateID/SK_CreateTimeID and BatchID.
- **Alerts:** as in the historical load.
- **Our approach (decision 2 of the protocol):**
  - DimTrade is a `ReplacingMergeTree ORDER BY TradeID` without a version column, so the last inserted row of a TradeID wins.
  - An update inserts the full new row: the new values from the file, plus the kept columns from the current row, read with FINAL.
  - If a T_ID appears more than once in one batch, first build one row per T_ID in `CDC_DSN` order, then insert.
- **Readers:** everything that reads DimTrade does so with FINAL (`final = 1`). That covers FactHoldings of the same batch and the validation, visibility and audit queries.

### FactCashBalances (§4.6.8)
- **Rows:** a batch is one day, so there is one row per account with transactions in the batch: the sum of CT_AMT per CT_CA_ID.
- **Cash:** the account's last Cash plus the batch's sum (0 if the account has no row yet).
  - The last Cash is the latest FactCashBalances row of the same AccountID. Find it through DimAccount, because the surrogate key may have changed.
- **Keys:**
  - SK_CustomerID and SK_AccountID come from DimAccount where AccountID = CT_CA_ID and IsCurrent = 1.
  - SK_DateID is the DimDate row of the Batch Date (`BatchDate.txt`).
- **BatchID** = 2 or 3.

### FactHoldings (§4.6.9)
- **Rules:** as in the historical load, from `HoldingHistory.txt` and DimTrade (read with FINAL). Rows are only appended, with BatchID 2 or 3.
- **SK_DateID and SK_TimeID:** §4.6.9.2 says they come "from DimTrade", but DimTrade only has the create and close keys. As in §4.5.10.2, we use SK_CloseDateID and SK_CloseTimeID. The audit test "FactHoldings CurrentTradeID" confirms this.

## 6. To check on the SF 10 data
- Every trade has a creating history row ('PNDG', or 'SBMT' for TMB/TMS), because Table 3.2.10 declares SK_CreateDateID NOT NULL.
- Can a T_ID appear more than once in one incremental batch?
- Can a dimension have two versions on the same day (EffectiveDate = EndDate)? An `ASOF JOIN` may then pick the zero-length version, so drop those versions from the right side of the join.
- Can HH_AFTER_QTY be negative? S_QTY_T is unsigned, but CurrentHolding may be negative, so use signed types in staging.
- Does every HH_T_ID have a DimTrade row with a close date? FactHoldings needs one, because its SK_DateID is NOT NULL.

## 7. What the audit checks (`tpcdi_audit.sql`)
- **DimTrade:**
  - The validation 'Row count' of DimTrade equals the sum of `T_NEW` up to the batch, and `count(distinct TradeID) = count(*)`. Both need FINAL on the ReplacingMergeTree (`final = 1`).
  - Status values: 'Canceled', 'Pending', 'Submitted', 'Active', 'Completed'. Type values: 'Market Buy', 'Market Sell', 'Stop Loss', 'Limit Sell', 'Limit Buy'. The comparison is exact and ClickHouse is case-sensitive, so copy the StatusType and TradeType names as they are.
  - The number of 'Canceled' trades equals `T_CanceledTrades`.
  - Alerts (MessageType 'Alert'): the count of 'Invalid trade commission' equals `T_InvalidCommision`, and the count of 'Invalid trade fee' equals `T_InvalidCharge`.
  - SK_BrokerID, SK_CompanyID, SK_SecurityID, SK_CustomerID and SK_AccountID point to a dimension version valid on the create date (EffectiveDate ≤ create date ≤ EndDate). So every trade needs SK_CreateDateID.
  - Create and close dates fall inside the batch window. Limit orders may have create dates back to the first day of Batch1. SK_CloseDateID ≥ SK_CreateDateID.
  - Three distinct BatchIDs.
- **FactHoldings:**
  - The row count grows by `HH_RECORDS` in every batch: append only, one row per HoldingHistory row.
  - `CurrentTradeID` joins DimTrade with SK_DateID = SK_CloseDateID and SK_TimeID = SK_CloseTimeID.
  - Each dimension version has EffectiveDate ≤ the holding date, and SK_DateID lies inside the batch window.
  - Three distinct BatchIDs.
- **FactCashBalances:**
  - SK_CustomerID and SK_AccountID point to versions valid on the SK_DateID date.
  - SK_DateID lies inside the batch window.
  - Three distinct BatchIDs.
