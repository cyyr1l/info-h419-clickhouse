# Query changes log

Every change made to a TPC-DS query goes here. This file becomes an appendix of the Part I report.

| Query | What changed | Why | Author | Date |
|---|---|---|---|---|
| | | | | |

## Reference answers (DuckDB)

The originals in `queries/original/` are never edited. These three rewrites are applied by
`scripts/build_reference.py` so the original queries run on DuckDB. They do not change the meaning of the queries.

| Query | Change | Reason |
|---|---|---|
| Q30 | `c_last_review_date_sk` → `c_last_review_date` | Inconsistency in kit 4.0.0: the template uses `c_last_review_date_sk`, but the kit DDL (`tools/tpcds.sql`) names the column `c_last_review_date`. |
| Q77 | alias `returns` → `returns_` | `returns` is a reserved word in DuckDB. |
| Q90 | subquery alias `at` → `at_` | `at` is a reserved word in DuckDB. |
