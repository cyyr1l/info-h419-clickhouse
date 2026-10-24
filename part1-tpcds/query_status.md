# Status of the 99 queries (SF 1)

Status: `pending` / `OK` / `OK (fixed)` / `failing`. Fixes are logged in `queries/CHANGES.md`.

| Query | Owner | Reference (DuckDB) | ClickHouse | Notes |
|---|---|---|---|---|
| Q1 | ① | OK | pending |  |
| Q2 | ① | OK | pending |  |
| Q3 | ① | OK | pending |  |
| Q4 | ① | OK | pending |  |
| Q5 | ① | OK | pending |  |
| Q6 | ① | OK | pending |  |
| Q7 | ① | OK | pending |  |
| Q8 | ① | OK | pending | **Empty result at SF 1** (q08): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q9 | ① | OK | pending |  |
| Q10 | ① | OK | pending |  |
| Q11 | ① | OK | pending |  |
| Q12 | ① | OK | pending |  |
| Q13 | ① | OK | pending |  |
| Q14 | ① | OK | pending | 2 statements |
| Q15 | ① | OK | pending |  |
| Q16 | ① | OK | pending |  |
| Q17 | ① | OK | pending | ③: NULL/sample-size fix prepared; synthetic comparison passed; SF1 pending. |
| Q18 | ① | OK | pending |  |
| Q19 | ① | OK | pending |  |
| Q20 | ① | OK | pending |  |
| Q21 | ① | OK | pending |  |
| Q22 | ① | OK | pending |  |
| Q23 | ① | OK | pending | 2 statements; **Empty result at SF 1** (q23_2): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q24 | ① | OK | pending | 2 statements; **Empty result at SF 1** (q24_1, q24_2): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q25 | ① | OK | pending | **Empty result at SF 1** (q25): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q26 | ② | OK | pending |  |
| Q27 | ② | OK | pending |  |
| Q28 | ② | OK | pending |  |
| Q29 | ② | OK | pending | **Empty result at SF 1** (q29): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q30 | ② | OK | pending | Reference needed a fix (see CHANGES.md) |
| Q31 | ② | OK | pending |  |
| Q32 | ② | OK | pending |  |
| Q33 | ② | OK | pending |  |
| Q34 | ② | OK | pending |  |
| Q35 | ② | OK | pending |  |
| Q36 | ② | OK | pending |  |
| Q37 | ② | OK | pending | **Empty result at SF 1** (q37): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q38 | ② | OK | pending |  |
| Q39 | ② | OK | pending | 2 statements |
| Q40 | ② | OK | pending |  |
| Q41 | ② | OK | pending | **Empty result at SF 1** (q41): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q42 | ② | OK | pending |  |
| Q43 | ② | OK | pending |  |
| Q44 | ② | OK | pending |  |
| Q45 | ② | OK | pending |  |
| Q46 | ② | OK | pending |  |
| Q47 | ② | OK | pending |  |
| Q48 | ② | OK | pending |  |
| Q49 | ② | OK | pending |  |
| Q50 | ② | OK | pending |  |
| Q51 | ③ | OK | pending |  |
| Q52 | ③ | OK | pending |  |
| Q53 | ③ | OK | pending |  |
| Q54 | ③ | OK | pending | **Empty result at SF 1** (q54): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets) |
| Q55 | ③ | OK | pending |  |
| Q56 | ③ | OK | pending |  |
| Q57 | ③ | OK | pending | Explicit v2 aliases prepared; synthetic comparison passed; SF1 pending. |
| Q58 | ③ | OK | pending | **Empty result at SF 1** (q58): weak check. Checked with the official parameters instead (reference/sf1_qualify, matches answer_sets). Qualified ordering fix prepared; non-empty synthetic comparison passed; SF1 pending. |
| Q59 | ③ | OK | pending |  |
| Q60 | ③ | OK | pending |  |
| Q61 | ③ | OK | pending |  |
| Q62 | ③ | OK | pending |  |
| Q63 | ③ | OK | pending |  |
| Q64 | ③ | OK | pending |  |
| Q65 | ③ | OK | pending |  |
| Q66 | ③ | OK | pending | Qualified aggregate inputs prepared; synthetic comparison passed; SF1 pending. |
| Q67 | ③ | OK | pending |  |
| Q68 | ③ | OK | pending |  |
| Q69 | ③ | OK | pending |  |
| Q70 | ③ | OK | pending |  |
| Q71 | ③ | OK | pending |  |
| Q72 | ③ | OK | pending |  |
| Q73 | ③ | OK | pending |  |
| Q74 | ③ | OK | pending |  |
| Q75 | ③ | OK | pending | Decimal-compatible COALESCE defaults prepared; synthetic comparison passed; SF1 pending. |
| Q76 | ④ | OK | pending |  |
| Q77 | ④ | OK | pending | Reference needed a fix (see CHANGES.md) |
| Q78 | ④ | OK | pending | Template fixed: round() on Decimal instead of Float64 (see CHANGES.md). SF1 validation pending. |
| Q79 | ④ | OK | pending |  |
| Q80 | ④ | OK | pending |  |
| Q81 | ④ | OK | pending |  |
| Q82 | ④ | OK | pending |  |
| Q83 | ④ | OK | pending |  |
| Q84 | ④ | OK | pending |  |
| Q85 | ④ | OK | pending |  |
| Q86 | ④ | OK | pending |  |
| Q87 | ④ | OK | pending |  |
| Q88 | ④ | OK | pending |  |
| Q89 | ④ | OK | pending |  |
| Q90 | ④ | OK | pending | Reference needed a fix (see CHANGES.md) |
| Q91 | ④ | OK | pending |  |
| Q92 | ④ | OK | pending |  |
| Q93 | ④ | OK | pending |  |
| Q94 | ④ | OK | pending |  |
| Q95 | ④ | OK | pending |  |
| Q96 | ④ | OK | pending |  |
| Q97 | ④ | OK | pending |  |
| Q98 | ④ | OK | pending |  |
| Q99 | ④ | OK | pending |  |
