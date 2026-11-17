# Audit, validation and DImessages (role 4, cluster D)

Ports of the TPC-DI v1.1.0 appendices to ClickHouse 26.8, plus the `Audit` loader.
The original SQL comes from github.com/shannon-barrow/databricks-tpc-di
(`src/incremental_batches/audit_validation/Appendix_v1.1.0`).

| File | What it does | When the orchestrator runs it |
|---|---|---|
| `../../ddl/dimessages_audit.sql` | Creates `DImessages` and `Audit` | Once, with the rest of the DW DDL |
| `load_audit.py` | Loads every `*_audit.csv` from the DIGen output into `Audit` | Once, before the audit (it truncates `Audit` first) |
| `validation.sql` | Appendix B: 24 `Validation` messages + the Phase Complete Record (PCR) | At the end of every batch, **including batch 0** (empty DW, before Batch1) |
| `visibility_1.sql`, `visibility_2.sql` | Appendix C: row counts during a load | Periodically while a batch loads |
| `audit.sql` | Appendix A: the final audit | *Not ported yet* |

## Rules the rest of the pipeline must follow

- **Batch 0.** The audit expects BatchIDs 0, 1, 2 and 3 in `DImessages`. Run `validation.sql` once on the empty DW before Batch1 (`max(BatchID)` of an empty table is 0).
- **Status message first.** At the start of each batch, insert a `Status` message with the new BatchID, because the queries take `max(BatchID)` from `DImessages`.
  ```sql
  INSERT INTO DImessages SELECT now64(3), 1, 'Orchestrator', 'Batch started', 'Status', NULL;
  ```
- **One statement per query.** Each file is a single `INSERT … SELECT` (plus the PCR in `validation.sql`). The audit pairs `Row count` with `Row count joined` by identical `MessageDateAndTime`, and `now64(3)` is only constant inside one statement. Do not split them.
- **Alert texts.** The audit counts alerts by exact `MessageText`: `DOB out of range`, `Invalid customer tier` (DimCustomer), `Invalid trade commission`, `Invalid trade fee` (DimTrade). Use `MessageType = 'Alert'`.
- **Dates.** Use `Date32`, not `Date`: ClickHouse `Date` starts in 1970, and TPC-DI dates start in 1950 (Batch1 `FirstDay` = 1950-01-01, `DimBroker.EffectiveDate` = 1950-01-01).
- **Column names are case-sensitive in ClickHouse**, e.g. `SK_DateID_DateRemoved` (the original Appendix B writes `SK_DATEID_DATEREMOVED`).

## Changes from the original SQL

- `CURRENT_TIMESTAMP` → `now64(3)` (0.1 s precision required).
- `x join y on 1=1` → `CROSS JOIN`; `FROM DUMMY TABLE` removed.
- `UNION` → `UNION ALL` (each row has a different source/text, so the result is the same).
- `count(*)` → `toString(count())`, since `MessageData` is a string.
- `SETTINGS final = 1`, so `DimTrade` (ReplacingMergeTree) is counted after deduplication. Tested: without it, a trade with two versions is counted twice.

## Tests

```bash
part2-tpcdi/tests/audit/run_tests.sh                     # uses "clickhouse client"
part2-tpcdi/tests/audit/run_tests.sh "docker exec -i <container> clickhouse-client"
```
It creates a throwaway database `role4_test` with stub DW tables (only the key columns), runs batch 0 and a toy Batch1, checks 20 expected values, then drops the database. `load_audit.py` was also tested on real DIGen SF 10 audit files (124 rows, reload does not duplicate).
