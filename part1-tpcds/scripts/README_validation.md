# Query validation (role ④)

## What is here

| Path | Content |
|---|---|
| `queries/original/q01.sql … q99.sql` | The 99 queries generated with `scripts/gen_queries.sh` (kit 4.0.0, netezza dialect, SF 1). Never edit these. |
| `reference/sf1/*.csv` | Reference answers: the 99 queries run on DuckDB over the same SF 1 `.dat` files. Q14, Q23, Q24, Q39 have two parts (`q14_1.csv`, `q14_2.csv`). 103 files. |
| `scripts/build_reference.py` | Rebuilds the reference answers. |
| `scripts/compare.py` | Compares ClickHouse results with the reference. |
| `query_status.md` | Status of the 99 queries. |

## How to validate your queries

1. Run your query on ClickHouse and save the result as CSV **with a header row**, named like the
   reference (`q76.csv`, or `q14_1.csv` / `q14_2.csv` for two-part queries), in e.g. `results/clickhouse_sf1/`.
2. Run:
   ```bash
   python part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1 results/clickhouse_sf1
   ```
3. Possible statuses: `OK`, `OK (different order)`, `MISMATCH values`, `MISMATCH rows/cols`, `MISSING`, `CHECK (empty)`.
   Numbers are rounded to 2 decimals; column names are ignored.
4. Update your rows in `query_status.md` and log any query change in `queries/CHANGES.md`.

A `MISMATCH` is not always a bug: with `LIMIT 100` and ties in the `ORDER BY`, two engines can return
different rows at the cut-off. Check those by hand and note it.

## How the reference was built

```bash
# in tpcds-kit/tools (built with -fcommon)
./dsdgen -SCALE 1 -DIR <data>/sf1 -TERMINATE N
./gen_queries.sh <repo>/part1-tpcds/queries/original 1
# from the repo root (needs: pip install duckdb pandas)
python part1-tpcds/scripts/build_reference.py <data>/sf1 part1-tpcds/queries/original \
       part1-tpcds/reference/sf1 <tpcds-kit>/tools/tpcds.sql
```

Load check: all 24 tables have the expected SF 1 row counts (e.g. `store_sales` 2,880,404).

**Sanity check against the official `answer_sets/`.** In kit 4.0.0, `dsqgen -QUALIFY Y` only orders the
queries; it does **not** use the qualification parameter values, so our queries have different
parameters from the official answer sets. This does not affect validation: ClickHouse and DuckDB run
exactly the same SQL text. To check the DuckDB setup itself, Q96 and Q3 were run with the official
qualification values (Q96: `t_hour = 20`, `hd_dep_count = 7`; Q3: `i_manufact_id = 128`, `d_moy = 11`)
and both match `answer_sets/` exactly (Q96 = 870).

## Known limitation: 10 empty reference results

With these parameters, 10 results are empty at SF 1: `q08`, `q23_2`, `q24_1`, `q24_2`, `q25`, `q29`,
`q37`, `q41`, `q54`, `q58`. An empty result is a weak check: a broken ClickHouse query that also returns
nothing would still show `OK`. Other seeds (`-RNGSEED`) give 8–11 empty results, so changing the seed
does not solve it. With the official qualification parameters these queries do return rows, so the
plan is to validate them separately with those values (spec, qualification parameters).
