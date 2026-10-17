# Query changes log

Every change made to a TPC-DS query goes here. This file becomes an appendix of the Part I report.

| Query | What changed | Why | Author | Date |
|---|---|---|---|---|
| All with `N days` (18 templates) | `+ N days` → `+ INTERVAL N DAY`, rewritten after generation (protocol, section 7) | ClickHouse has no `N days` interval syntax. | ② | 17/10 |
| Q35 | The three correlated `exists (select … where c.c_customer_sk = <key> …)` become `c.c_customer_sk in (select <key> …)`. Template: `queries/templates/query35.tpl` | ClickHouse needs more than 4.5 GiB for the correlated EXISTS already at SF 1 and fails (known issue, listed in the README of ClickHouse's own TPC-DS benchmark); the approved TPC variant `query35a` fails the same way. Same result because `c_customer_sk` is never NULL. SF 1: 0.41 s and 16 MiB, same 100 rows as the reference. | ② | 17/10 |
| Q47 | Explicit aliases for the columns of `v2` (`v1.d_year d_year`, …). Template: `queries/templates/query47.tpl` | ClickHouse names these columns `v1.d_year`, … instead of `d_year` (ClickHouse issue #94858), so the outer query cannot find them. Same parameters; same result as the reference (to 1e-12). | ② | 17/10 |
| | | | | |
