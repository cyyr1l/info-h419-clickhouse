# Status of the 99 queries (SF 1)

Status: `pending` / `OK` / `OK (fixed)` / `failing`. Fixes are logged in `queries/CHANGES.md`.

ClickHouse column: SF 1 generated with `gen_data.py` and loaded with `load.py`, queries from `gen_queries.py validation` (and `gen_qualify.py` for the 9 queries whose reference result is empty), run with `harness.py validate` and compared with `compare.py` (24/10, on the benchmark machine).

| Query | Owner | Reference (DuckDB) | ClickHouse | Notes |
|---|---|---|---|---|
| Q1 | ① | OK | OK (fixed) | Template fixed: lowercase column names (CHANGES.md). |
| Q2 | ① | OK | OK |  |
| Q3 | ① | OK | OK |  |
| Q4 | ① | OK | OK |  |
| Q5 | ① | OK | OK |  |
| Q6 | ① | OK | OK |  |
| Q7 | ① | OK | OK |  |
| Q8 | ① | OK | OK | **Empty result at SF 1** (q08): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q9 | ① | OK | OK |  |
| Q10 | ① | OK | OK |  |
| Q11 | ① | OK | OK |  |
| Q12 | ① | OK | OK |  |
| Q13 | ① | OK | OK |  |
| Q14 | ① | OK | OK | 2 statements |
| Q15 | ① | OK | OK |  |
| Q16 | ① | OK | OK |  |
| Q17 | ① | OK | OK (fixed) | Template fixed by ③: stddev_samp gives NULL instead of nan for fewer than 2 values (CHANGES.md). |
| Q18 | ① | OK | OK |  |
| Q19 | ① | OK | OK |  |
| Q20 | ① | OK | OK |  |
| Q21 | ① | OK | OK |  |
| Q22 | ① | OK | OK |  |
| Q23 | ① | OK | OK | 2 statements; **Empty result at SF 1** (q23_2): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q24 | ① | OK | OK | 2 statements; **Empty result at SF 1** (q24_1, q24_2): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q25 | ① | OK | OK | **Empty result at SF 1** (q25): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q26 | ② | OK | OK |  |
| Q27 | ② | OK | OK |  |
| Q28 | ② | OK | OK |  |
| Q29 | ② | OK | OK | **Empty result at SF 1** (q29): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q30 | ② | OK | OK (fixed) | Reference needed a fix (see CHANGES.md); the ClickHouse template has the same fix. |
| Q31 | ② | OK | OK | Same rows in another order (ties in the ORDER BY). |
| Q32 | ② | OK | OK |  |
| Q33 | ② | OK | OK |  |
| Q34 | ② | OK | OK |  |
| Q35 | ② | OK | OK (fixed) | Template fixed: correlated EXISTS → IN (CHANGES.md). |
| Q36 | ② | OK | OK |  |
| Q37 | ② | OK | OK | **Empty result at SF 1** (q37): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q38 | ② | OK | OK |  |
| Q39 | ② | OK | OK | 2 statements |
| Q40 | ② | OK | OK |  |
| Q41 | ② | OK | OK | **Empty result at SF 1** (q41): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q42 | ② | OK | OK |  |
| Q43 | ② | OK | OK |  |
| Q44 | ② | OK | OK |  |
| Q45 | ② | OK | OK |  |
| Q46 | ② | OK | OK |  |
| Q47 | ② | OK | OK (fixed) | Template fixed: explicit column aliases (CHANGES.md). |
| Q48 | ② | OK | OK |  |
| Q49 | ② | OK | OK |  |
| Q50 | ② | OK | OK |  |
| Q51 | ③ | OK | OK |  |
| Q52 | ③ | OK | OK |  |
| Q53 | ③ | OK | OK |  |
| Q54 | ③ | OK | OK | **Empty result at SF 1** (q54): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q55 | ③ | OK | OK |  |
| Q56 | ③ | OK | OK |  |
| Q57 | ③ | OK | OK (fixed) | Template fixed by ③: explicit column aliases, as for Q47 (CHANGES.md). |
| Q58 | ③ | OK | OK (fixed) | Template fixed by ③: qualified ORDER BY key (CHANGES.md). **Empty result at SF 1** (q58): weak check. With the official parameters, reference/sf1_qualify matches answer_sets and ClickHouse matches reference/sf1_qualify. |
| Q59 | ③ | OK | OK |  |
| Q60 | ③ | OK | OK |  |
| Q61 | ③ | OK | OK |  |
| Q62 | ③ | OK | OK |  |
| Q63 | ③ | OK | OK |  |
| Q64 | ③ | OK | OK |  |
| Q65 | ③ | OK | OK |  |
| Q66 | ③ | OK | OK (fixed) | Template fixed by ③: qualified aggregate inputs (CHANGES.md). |
| Q67 | ③ | OK | OK |  |
| Q68 | ③ | OK | OK |  |
| Q69 | ③ | OK | OK |  |
| Q70 | ③ | OK | OK |  |
| Q71 | ③ | OK | OK | Same rows in another order (ties in the ORDER BY). |
| Q72 | ③ | OK | OK |  |
| Q73 | ③ | OK | OK |  |
| Q74 | ③ | OK | OK |  |
| Q75 | ③ | OK | OK (fixed) | Template fixed by ③: integer COALESCE defaults (CHANGES.md). |
| Q76 | ④ | OK | OK |  |
| Q77 | ④ | OK | OK | Reference needed a fix (see CHANGES.md) |
| Q78 | ④ | OK | OK (fixed) | Template fixed: the ratio is rounded half away from zero, as in the reference (CHANGES.md). |
| Q79 | ④ | OK | OK |  |
| Q80 | ④ | OK | OK |  |
| Q81 | ④ | OK | OK |  |
| Q82 | ④ | OK | OK |  |
| Q83 | ④ | OK | OK |  |
| Q84 | ④ | OK | OK |  |
| Q85 | ④ | OK | OK |  |
| Q86 | ④ | OK | OK |  |
| Q87 | ④ | OK | OK |  |
| Q88 | ④ | OK | OK |  |
| Q89 | ④ | OK | OK |  |
| Q90 | ④ | OK | OK | Reference needed a fix (see CHANGES.md) |
| Q91 | ④ | OK | OK |  |
| Q92 | ④ | OK | OK |  |
| Q93 | ④ | OK | OK |  |
| Q94 | ④ | OK | OK |  |
| Q95 | ④ | OK | OK |  |
| Q96 | ④ | OK | OK |  |
| Q97 | ④ | OK | OK |  |
| Q98 | ④ | OK | OK |  |
| Q99 | ④ | OK | OK |  |
