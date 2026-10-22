# TPC-DS Schema Notes

## Project

INFO-H419 — TPC-DS on ClickHouse

## Schema source

The ClickHouse schema is defined in `part1-tpcds/ddl/schema.sql`.

It was adapted from the official `tpcds.sql` distributed with the TPC-DS 4.0.0 tools.

The schema contains **24 tables** and **425 columns**.

## Data types and nullability

The schema uses the following ClickHouse data types:

- `Int32` for integer fields.
- `Int64` for transaction numbers.
- `String` for character fields.
- `Decimal` for fixed-point numeric fields.
- `Date32` for date fields.

Nullability is explicitly defined for each column using nullable or non-nullable types.

## Storage engine

All 24 tables use the `MergeTree` engine.

No partitioning is configured.

## Sorting keys

### Dimension tables

Dimension tables are sorted by their respective keys.

### Sales and returns tables

Sales and returns tables are sorted by:

1. The date surrogate key, using `ifNull(date_sk, -1)` with the corresponding date column.
2. The item surrogate key.
3. The transaction number.

The `ifNull` expression maps null date keys to `-1` in the sorting key.

### Inventory

The `inventory` table is sorted by:

1. Date.
2. Item.
3. Warehouse.

## Verification status

Completed:

- Creation of all 24 tables in ClickHouse.
- Verification of column counts, totalling 425 columns.

Still to be completed:

- Data loading.
- Query validation.