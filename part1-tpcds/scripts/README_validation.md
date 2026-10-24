# Query validation (role ④)

## What is here

| Path | Content |
|---|---|
| `queries/original/q01.sql … q99.sql` | The 99 queries as the kit generates them (netezza dialect, SF 1, default seed): the source of the reference answers. Never edit these. |
| `queries/templates/` | Our ClickHouse templates: the `clickhouse.tpl` dialect and fixed copies of kit templates (protocol, section 7). |
| `reference/sf1/*.csv` | Reference answers: the 99 original queries run on DuckDB over the same SF 1 `.dat` files. Q14, Q23, Q24, Q39 have two parts (`q14_1.csv`, `q14_2.csv`). 103 files. |
| `scripts/gen_queries.py` | Generates the queries with dsqgen in Docker: `validation`, `streams --sf N`, `original`. |
| `scripts/build_reference.py` | Rebuilds the reference answers. |
| `scripts/compare.py` | Compares ClickHouse results with the reference (standard library only). |
| `scripts/test_compare.py` | Tests for `compare.py`. |
| `query_status.md` | Status of the 99 queries. |

## How to validate your queries

1. Fix queries in templates, never in generated SQL. Copy the kit template into `queries/templates/`,
   edit it there, and log the change in `queries/CHANGES.md`:
   ```bash
   cp tools/DSGen-software-code-4.0.0/query_templates/query30.tpl part1-tpcds/queries/templates/
   ```
2. Generate the ClickHouse queries (SF 1, same parameters as the reference answers):
   ```bash
   python3 part1-tpcds/scripts/gen_queries.py validation     # writes data/queries/validation/qNN.sql
   ```
3. Run them on ClickHouse with role ②'s harness, then compare:
   ```bash
   python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/validation --only 26-50 --out data/validation/sf1
   python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1 data/validation/sf1
   ```
4. Update your rows in `query_status.md`.

`data/` is ignored by git, so these outputs never end up in a commit.

### Statuses

| Status | Meaning |
|---|---|
| `OK` | same values in the same order |
| `OK (different order)` | same rows in another order (fine when the ORDER BY has ties) |
| `OK (both empty)` | both results are empty: a weak check (see the limitation below) |
| `MISMATCH values` | at least one value differs; the first difference is printed |
| `MISMATCH rows/cols` | different number of rows or columns |
| `MISSING` | no result file (the query failed or was not run) |
| `CHECK (empty file)` | the result file has no header row |

### Comparison rules
- Column names are ignored. An empty field is NULL; `nan` and `inf` are values of their own, so a `nan` is never taken for a NULL (Q17).
- In a one-column result, a blank line is a NULL row (Q23 part 1).
- Integers must match exactly. Other numbers may differ by 1e-4 (absolute) or 1e-9 (relative). That covers float noise (e.g. 5212.355 vs 5212.3550000000005) and the `decimal(15,4)` casts written in some templates (Q49, Q90), and it still catches truncation to 2 decimals and another rounding mode (Q78: 2.12 instead of 2.13).
- The spec's own precision rules (§7.5.3: ratios and averages within 1%, money sums within $100) are looser. We stay stricter on purpose, because the reference runs exactly the same SQL.

`python3 part1-tpcds/scripts/test_compare.py` checks these rules.

## How the reference was built

```bash
python3 part1-tpcds/scripts/gen_queries.py original --out part1-tpcds/queries/original
pip install duckdb pandas
python3 part1-tpcds/scripts/build_reference.py data/tpcds/sf1 part1-tpcds/queries/original \
        part1-tpcds/reference/sf1 tools/DSGen-software-code-4.0.0/tools/tpcds.sql
```

`gen_queries.py original` reproduces `queries/original/` byte for byte. Rebuilding the answers with DuckDB 1.5.6 gives the same results: 99 of the 103 files are byte-identical. The other 4 have the same rows, in another order (Q31, Q77: ties in the ORDER BY) or with differences below 1e-9 (Q39).

Load check: all 24 tables have the expected SF 1 row counts (e.g. `store_sales` 2,880,404).

**Sanity check against the official `answer_sets/`.** In kit 4.0.0, `dsqgen -QUALIFY Y` only orders the
queries; it does **not** use the qualification parameter values, so our queries have different
parameters from the official answer sets. This does not affect validation: ClickHouse and DuckDB run
exactly the same SQL text. To check the DuckDB setup itself, Q96 and Q3 were run with the official
qualification values (Q96: `t_hour = 20`, `hd_dep_count = 7`; Q3: `i_manufact_id = 128`, `d_moy = 11`)
and both match `answer_sets/` exactly (Q96 = 870).

## Empty reference results: checked with the official parameters

With our parameters (default seed), 10 results are empty at SF 1: `q08`, `q23_2`, `q24_1`, `q24_2`, `q25`,
`q29`, `q37`, `q41`, `q54`, `q58`. An empty result is a weak check: a broken ClickHouse query that also
returns nothing would still pass, which is why `compare.py` reports them as `OK (both empty)`. Other seeds
(`-RNGSEED`) give 8–11 empty results, so changing the seed does not solve it.

So these 9 templates are also run with the official qualification parameters (spec 4.0.0, Appendix B),
with which they return rows:

| Path | Content |
|---|---|
| `scripts/gen_qualify.py` | Writes the qualification values into copies of the 9 templates and runs dsqgen in Docker. Output: `queries/qualify/` and `data/queries/qualify/`. |
| `queries/qualify/qNN.sql` | The 9 queries with the qualification parameters (netezza dialect, kit templates): the source of the answers below. Never edit these. |
| `data/queries/qualify/qNN.sql` | The same 9 queries for ClickHouse (clickhouse dialect, our templates, `INTERVAL` rewrite). Not in git. |
| `reference/sf1_qualify/*.csv` | DuckDB answers for these 9 queries at SF 1 (11 files: Q23 and Q24 have two parts). |

**Check against the official answers.** All 11 files match the kit's `answer_sets/` (`8`, `23_NULLS_LAST`,
`24`, `25`, `29`, `37`, `41`, `54`, `58`): same rows and same values (`8.ans` shows the sums rounded).
Q23 part 2 has a NULL last name, sorted last, hence `23_NULLS_LAST.ans`. For Q29 the spec gives
`MONTH = 9`, although the kit template draws the month with `random(4,4,uniform)`; `29.ans` matches `MONTH = 9`.

Only the parameter values differ from `queries/original/`. The rest of each query is unchanged.

To validate them on ClickHouse (SF 1 loaded):
```bash
python3 part1-tpcds/scripts/gen_qualify.py
python3 part1-tpcds/scripts/harness.py validate --sf 1 --queries data/queries/qualify --out data/validation/sf1_qualify
python3 part1-tpcds/scripts/compare.py part1-tpcds/reference/sf1_qualify data/validation/sf1_qualify
```

To rebuild the answers:
```bash
python3 part1-tpcds/scripts/build_reference.py data/tpcds/sf1 part1-tpcds/queries/qualify \
        part1-tpcds/reference/sf1_qualify tools/DSGen-software-code-4.0.0/tools/tpcds.sql
```
