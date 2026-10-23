# TPC-DS Schema Notes

## Project

INFO-H419 — TPC-DS on ClickHouse

## Schema source

The ClickHouse schema is defined in `part1-tpcds/ddl/schema.sql`.

It was adapted from the official `tpcds.sql` distributed with the TPC-DS 4.0.0 tools.

The schema contains **24 tables** and **425 columns**.

The existing project spelling `store.s_tax_percentage` corrects the kit DDL typo `s_tax_precentage`; it is retained here. Column order and nullability follow the supplied kit.

## Data types and nullability

The schema uses the following ClickHouse data types:

- `Int32` for integer fields.
- `Int64` for transaction numbers.
- `String` for character fields.
- `Decimal` for fixed-point numeric fields.
- `Date32` for date fields.

Nullability is explicitly defined for each column using `Nullable(T)` or `T NOT NULL`. The DDL therefore does not depend on the query-only `data_type_default_nullable` setting.

### Decimal precision correction (PR #6 review)

All 80 source `Decimal(P,2)` columns use `Decimal(P+4,6)`:

| Source | ClickHouse | Columns |
|---|---|---|
| `Decimal(5,2)` | `Decimal(9,6)` | 8 |
| `Decimal(7,2)` | `Decimal(11,6)` | 71 |
| `Decimal(15,2)` | `Decimal(19,6)` | 1 |

These include 72 monetary columns, five GMT offsets and three tax percentages. The conversion is applied consistently to every instance of each source decimal type.

ClickHouse decimal division retains the dividend's scale and discards excess fractional digits. Scale 2 truncated ratios and changed comparisons: Bao Anh's SF1 review identified failures in Q2, Q11, Q12, Q20, Q31, Q36, Q59 and Q98. For example, Q12 returned 3.71 instead of approximately 3.715557804. Scale 6 retains four additional fractional digits; it is still finite precision, so larger scale factors require validation.

The change preserves exact input cents and the original integer-digit capacity: `(P+4)-6 = P-2`. TPC-DS 4.0.0 clauses 2.2.2.1(c), 2.2.2.2 and 2.2.2.3 describe decimal representability, allow suitable implementation types and require consistent mappings. Applying the same mapping to offsets and percentages follows this consistency rule. This rationale is not a claim of full TPC compliance.

The wider types have a storage and computation cost: `Decimal(11,6)` uses Decimal64 and `Decimal(19,6)` uses Decimal128. Bao Anh measured approximately 27% more on-disk space for `store_sales` at SF1; that is a reviewer-reported observation, not a general estimate for other tables or scale factors.

## Storage engine

All 24 tables use the `MergeTree` engine.

No partitioning is configured. This is the initial benchmark baseline, avoiding many small partitions and keeping parts eligible to merge together. It provides no partition-based pruning; performance must be measured before claiming a benefit.

## Sorting keys

### Dimension tables

Dimension tables are sorted by their non-null surrogate keys. MergeTree uses the sorting key for its sparse primary index; it does not enforce relational uniqueness or foreign keys.

### Sales and returns tables

Sales and returns tables are sorted by:

1. The date surrogate key, using `ifNull(date_sk, -1)` with the corresponding date column.
2. The item surrogate key.
3. The transaction number.

The `ifNull` expression maps null date keys to `-1` in the sorting expression while preserving NULL in the stored column. Date-first sorting is an initial locality choice, not a measured optimum; date filters through joins do not guarantee index pruning.

### Inventory

The `inventory` table is sorted by:

1. Date.
2. Item.
3. Warehouse.

## Loading and schema changes

The loader chooses the target database and executes this single SQL file with multi-statement support. It must retain raw field values, including trailing spaces, and decode missing fields as NULL where permitted.

`CREATE TABLE IF NOT EXISTS` does not migrate existing columns. Execute the corrected DDL in a fresh validation database or explicitly plan a migration before loading. Re-running the file over the old tables is not sufficient.

The schema adapts the supplied kit. Integer counts remain `Int32`, and character columns use `String`; full official integer-range and fixed-width character semantics are not established by these choices. Check identifier/count ranges at the selected maximum SF and record these implementation limitations.

## Verification status

Completed:

- Creation of all 24 tables in ClickHouse.
- Verification of column counts, totalling 425 columns.

Reviewer-reported SF1 checks (Bao Anh, PR #6, 23 October 2026):

- The original schema loaded with the exact row counts for all 24 tables.
- His wider-decimal experiment improved matching statements from 87/103 to 95/103 and fixed the eight precision failures, without a new failure.
- These results predate the five template corrections delivered here.

Local correction checks:

- All 24 corrected CREATE TABLE statements execute, with 425 columns.
- Synthetic, non-empty fixtures for Q17, Q57, Q58, Q66 and Q75 match the original SQL executed in DuckDB. Q17 covers zero, one and multiple non-null observations.
- These focused checks used embedded ClickHouse 26.9.2.1 and DuckDB 2.0.0, not the project's pinned server.

Still pending: regenerate queries with dsqgen, load/reload the corrected schema, validate the five fixes and Q51–75 against the SF1 references on ClickHouse 26.8.24.9, and test larger SFs. In particular, Q58 also needs the separate official-parameter check because its normal SF1 reference is empty.

## References

- TPC-DS 4.0.0, clauses 2.2.2.1–2.2.2.3: https://www.tpc.org/TPC_Documents_Current_Versions/pdf/TPC-DS_v4.0.0.pdf
- ClickHouse Decimal types and arithmetic: https://clickhouse.com/docs/reference/data-types/decimal
- Reviewer test evidence: https://github.com/cyyr1l/info-h419-clickhouse/pull/6
