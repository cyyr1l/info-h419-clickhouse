# Role 3 — TPC-DI first implementation

Prepared from the supplied TPC-DI Standard Specification, revision 1.1.0.
This is a starting package for Anabelle's branch `role3/tpcdi-schema`.

## What is implemented

* `ddl/cluster_b.sql`: the 11 DimAccount, 33 DimCustomer and 27 Prospect
  columns from clauses 3.2.1, 3.2.4 and 3.2.15, in specification order.
* `ddl/prototype_staging.sql`: auxiliary, resolved account-state input.
* `etl/dimaccount_historical.sql`: INSERT-only historical SCD2, one state per
  account/day, latest timestamp then source-file order, new surrogate keys,
  next effective date as the previous end date, current end date 9999-12-31.
* `etl/dimaccount_incremental.sql`: rebuild history plus changed/new accounts.
  Old surrogate keys and original BatchIDs are retained. The caller validates
  the candidate and then executes `EXCHANGE TABLES` in an Atomic database.
* `scripts/prototype_dimaccount.py`: disposable synthetic demonstration of
  all three batches, including customer-key changes and account closure.

No extra columns are introduced in these DW tables. Helpers belong to staging.
Numeric identifiers use UInt64 because NUM(11) exceeds UInt32. BatchID uses
UInt32 because NUM(5) exceeds UInt16. Tax rates are exact Decimal(6,5).
String stores variable-length text; source/transformation validation must enforce
the specification's field lengths and business domains. MergeTree sorting keys
do not enforce uniqueness or foreign keys; ETL validation must enforce them.
The two other DW tables are created and checked structurally; their transforms
are not part of this prototype. Prospect updates will require a rebuild strategy.

## Shared ClickHouse types

| TPC-DI type | ClickHouse type |
| --- | --- |
| SK_T, IDENT_T, TRADE_T | UInt64 |
| BatchID | UInt32 |
| DATE | Date32 |
| DATETIME | DateTime64(3) |
| NUM(m,n), SNUM(m,n) with fractional scale | Decimal(m,n) |
| Integer NUM / SNUM fields | Unsigned / signed integer wide enough for the specified range |
| CHAR(n) | String |
| BOOLEAN | Bool |

Use Nullable only where the specification allows NULL. In ETL, use
toDate32() for dates. Avoid Date, DateTime and toDate(), which can silently
clamp values. Use the exact StatusType names Active and Inactive for
DimAccount and DimCustomer to match the audit.

## Run the prototype

With the infoh419-clickhouse container running, run from the repository root:

```sh
python3 part2-tpcdi/scripts/prototype_dimaccount.py
```

Only Python's standard library and Docker CLI are required. It creates a unique
`tpcdi_role3_demo_<id>` database; it does not modify existing project databases.
On success it removes that demo database. On failure it retains it for debugging.
Use `--keep` to retain a successful demo, too.

Expected final message:

```text
SUCCESS: cluster B DDL and DimAccount SCD2 prototype
```

The runner checks Date32 round-trips for 1800-01-01 and 9999-12-31 **before**
creating tables. Date handling must preserve the actual sentinel, not silently
clamp it. If that guard fails on the team's pinned server, stop and revise the
shared date mapping before integrating these DDL files. The guard does not
automatically change the server version or substitute another sentinel.

## Scope still to implement

This is **not the complete role 3 deliverable** or a benchmark-ready ETL:

1. Add DDL for the other clusters and agree raw staging contracts with Cyril.
2. Implement XML parsing and account-state reconstruction. This prototype's
   input contains COMPLETE states, not raw XML patches. Missing properties must
   retain their previous values; explicit empty properties must become NULL.
   Do not use a blanket COALESCE that loses this distinction.
3. Resolve broker/customer surrogate keys at the event date; expand customer
   UPDCUST/INACT events to affected accounts, including accounts with no account
   event on that date. The fixture supplies already resolved keys and expanded
   states: it demonstrates SCD2 storage, not those upstream operations.
4. Apply the remaining DimCustomer/Prospect transformation rules and DImessages
   error logging. Full DimBroker/DimCustomer foreign-key validation is absent
   from the synthetic demonstration.
5. Integrate official audit/validation queries and the team's timed orchestrator.

For historical input, `(AccountID, ActionTS, SourceOrder)` must uniquely order
events and input states must include all relevant account changes. For an
incremental invocation, staging contains only the current batch's resolved
states; source events are collapsed to one version per account at BatchDate.
BatchDate must be strictly later than the current row's EffectiveDate. The
orchestrator must reject duplicate/replayed batches and prevent concurrent
writers. Do not rerun the historical INSERT into a populated target.

The prototype validates exact expected rows, unique surrogate keys, one current
row per account, nonempty consecutive intervals, preserved old keys/BatchIDs,
NULL values, source ordering and both swaps. It also verifies that the old
table stays unchanged while its replacement is being constructed. It does not
test crash recovery, concurrent readers, real generated data or benchmark speed.

## Validation

The synthetic scenario passed on the team's ClickHouse 26.8.24.9 Docker
image, covering historical loading and both incremental batches.
Validation with generated TPC-DI data and the official audit is still pending.

References: TPC-DI 1.1.0 clauses 3.2.1, 3.2.4, 3.2.15, 3.4.5,
4.4.1–4.4.2 and 4.5.1; ClickHouse EXCHANGE documentation:
https://clickhouse.com/docs/sql-reference/statements/exchange
