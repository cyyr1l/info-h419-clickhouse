# Benchmark protocol: Part I (TPC-DS on ClickHouse)

**Status:** decided on 17 Oct (decision log in section 10), open for comments in the PR · **Owner:** ② Benchmark & Measurement
**Source:** TPC-DS v4.0.0 specification (`tools/DSGen-software-code-4.0.0/specification/specification_4.0.0.pdf`), mainly Clause 7 "Performance Metrics and Execution Rules" (pp. 69–79). The § numbers below refer to the spec.

Our results are *derived from TPC-DS*, not official TPC results. Every deviation from the spec is listed in section 9.

## 1. System under test
- **Machine:** ②'s desktop PC. The harness also records the machine as seen from WSL2 in `environment.json` (section 8).
  - CPU: Intel Core i5-12600KF, 10 cores (6 performance + 4 efficiency cores), 16 threads.
  - RAM: 32 GB (31.8 GB usable).
  - Disk: Kingston NV2 1 TB NVMe SSD (SNV2S1000G), the only internal disk; it holds the WSL2 and Docker virtual disks.
  - OS: Windows 11 Pro 25H2, build 26200.9711.
- **Software:** ClickHouse **26.8.24.9** (pinned) in Docker Desktop 4.56.0 (Docker Engine 29.1.3) with the WSL2 backend (WSL 2.6.1, kernel 6.6.87.2, Ubuntu 24.04.4 LTS); TPC-DS kit 4.0.0 (`dsdgen`, `dsqgen`); Python 3.12.3 for the harness.
- **WSL2 resources:** Docker Desktop gives WSL2 only 50% of the RAM by default (a 16 GB laptop shows 8 GB in Docker). Create `%UserProfile%\.wslconfig` with 24 GB and all 16 logical cores:
  ```ini
  [wsl2]
  memory=24GB
  processors=16
  ```
  then run `wsl --shutdown` and restart Docker Desktop.
- **Data location:** clone the repo inside the WSL2 filesystem (e.g. `~/info-h419-clickhouse` in Ubuntu), so `data/` is not on a Windows drive.
- **No other containers during runs.** ClickHouse 26.8 adjusts its memory limit to the memory that is free at that moment (memory worker, `memory_worker_dynamic_hard_limit = 1` by default). On the 16 GB dev laptop with 14 other containers running, the limit dropped from 6.84 GiB to about 3 GiB. `docker ps` must list only `infoh419-clickhouse`. The harness records the effective limit and the running containers, and warns if other containers are up.
- **During runs:** on AC power, Windows power mode "Best performance", other apps closed, Windows Update paused.

## 2. Scale factors
- **Reference SF:** the largest SF that (1) loads successfully, (2) fits on disk, and (3) completes one power run of the 99 queries in **under 1 hour**, with every failure explained. Try 100, then 50, then 30.
- **Why 1 hour:** one SF costs about T_Load + 9 × T_Power: the power test, the throughput test (4 streams on the same cores ≈ 4 × T_Power) and 4 extra power runs (section 5). The four SFs add up to 1.8 × the reference. With T_Power ≤ 1 h, the whole campaign takes about 17 h plus the loads, i.e. two nights on the benchmark machine.
- **Series:** 0.1×, 0.2×, 0.5× and 1× the reference (e.g. 10, 20, 50, 100). The reference is a multiple of 10 so that every SF is an integer.
- **Decision: reference SF 50**, so the series is 5, 10, 25 and 50. Trial run on the benchmark machine on 24–25 Oct (`gen_data.py` with 16 processes, then `harness.py load` and `harness.py power`):
  - **SF 100 does not fit on disk.** Generation took 10 min (102 GB of `.dat` files), and the data loaded in 19.9 min with every row count correct. During `OPTIMIZE … FINAL`, the free space on the partition that holds the virtual disks (D:) fell from 265 GB to 20 GB: the Docker virtual disk grew to 174 GB for 58 GiB of data, because merges rewrite the data, old parts are kept for 8 min, and a WSL2 virtual disk never shrinks by itself. We stopped the last merges before the partition was full, so the power run was not tried.
  - **SF 50 meets the three conditions.** Generation took 4 min (47 GB). T_Load = 980 s (load 413 s + optimize 567 s), with every row count correct and never less than 69 GB free on D:. One power run on stream 0 took T_Power = 650 s (10.8 min) with no failure; the slowest queries are Q72 (214 s), Q93 (95 s) and Q69 (61 s).
  - With T_Power ≈ 11 min, the whole campaign takes about 3 h plus about 30 min of loads. Each load makes the Docker virtual disk grow by about 3.5 times the size of the data (100 GB for SF 50), so we compact the virtual disks before the campaign, and between scale factors if needed.

## 3. Test sequence (§7.4.2)
For each SF, in this order, without restarting ClickHouse between the start of the power test and the end of the throughput test (§7.4.1.3):

1. Load test
2. Power test
3. Throughput test 1

There is no data maintenance (decision 3 in section 10), so there are no data maintenance tests and no throughput test 2. The extra repetitions of section 5 run after this sequence. All timings use a clock with a resolution of at least 0.01 s (§7.4.1.6): `time.perf_counter()` in the harness.

### 3.1 Load test (§7.4.3)
- We load from flat files generated beforehand by `dsdgen`. Generation time is not part of T_Load (§7.4.3.8.1a), but we record it anyway.
- **T_Load** runs from the first `CREATE TABLE` to the end of `OPTIMIZE TABLE … FINAL` on every table. `OPTIMIZE … FINAL` merges each table into one part per partition, so every run starts from the same layout and no background merge competes with the queries. We also report the load and optimize times separately.
- We record, per table: rows, parts, and on-disk size compressed and uncompressed (from `system.parts`).
- Row counts are checked against the kit's expected counts before the power test. This check is not timed (§7.4.3.8.1f).

### 3.2 Power test (§7.4.4–7.4.5)
- One session runs stream 0: the 99 queries in the stream-0 order of the kit (spec Appendix D), one at a time.
- **Query elapsed time** = client wall time from sending the query text to receiving the last byte of the result (§7.4.7.1). Queries 14, 23, 24 and 39 contain two SQL statements; both count towards that query's time.
- **T_Power** runs from sending the first query to receiving the last result.

### 3.3 Throughput test (§7.4.6–7.4.7)
- **Sq = 4 streams.** The spec requires an even number ≥ 4 (§7.4.6.9). Streams 1–4 come from `dsqgen`, each a different permutation of the 99 queries with its own parameters.
- Each stream has its own session and runs its queries one after another. The 4 streams start together.
- **T_TT1** runs from the first query sent by any stream to the last result received by any stream. Every query's elapsed time is recorded per stream.

## 4. Settings and failures
- **One global settings profile:** `part1-tpcds/settings.json`, sent by the harness with every query, for all SFs and all runs. It contains:
  - the SQL-compatibility settings (owned by ③; starting point: the profile of ClickHouse's own TPC-DS benchmark, e.g. `join_use_nulls = 1`, `data_type_default_nullable = 1`);
  - the benchmark settings below (owned by ②).

  If a setting must change to make a query run, it changes for every query and every SF is re-run. No per-query tuning.
- **Result caches off:** `use_query_cache = 0` (already the default) and `use_query_condition_cache = 0`. The query condition cache is on by default in 26.8: it remembers which granules matched a filter in an earlier execution. Our warm repetitions re-run identical queries, so it would measure a cache of earlier results rather than query processing. The spec has no rule on this; it is our choice and is reported as such. Caches of *data* (mark cache, OS page cache) stay on: they are the normal warm state.
- **Timeout:** `max_execution_time = 1800` s with `timeout_overflow_mode = 'throw'`. A 30-minute query would already be half of the 1-hour power budget, and under 4 concurrent streams heavy queries take up to ~4× longer, so this limit only stops runaway queries.
- **Memory:** ClickHouse defaults (server limit = 90% of the RAM visible to WSL2, adjusted dynamically, see section 1). A query that runs out of memory is recorded as failed (status `memory`).
- **Failures:** a failed or timed-out query is recorded with its error code, and the stream moves on to the next query. Any failure makes the run non-compliant with §7.4.1.1. We report it; we never hide it.
- **Correctness first:** no timed run before the 99 queries are validated at SF 1 against ④'s DuckDB reference answers with `scripts/compare.py`. The 10 queries whose reference result is empty at SF 1 are also checked with the official qualification parameters (④).

## 5. Extra repetitions (our addition, not in the spec)
The spec runs each test once. To get stable per-query numbers, we add for each SF, after the spec sequence:
- **1 cold power run:** stop the ClickHouse container, drop the Linux page cache of the WSL2 VM, start the container and wait until it is healthy. Restarting clears every in-memory cache of ClickHouse (marks, primary index, query condition…). The page cache is dropped from a privileged container, which shares the WSL2 kernel: `docker run --rm --privileged alpine:3.20 sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"`. Tested on the dev laptop: the page cache went from 3.6 GB to 1.6 GB, and the restart took 11 s. The harness does all of this itself (`--cold`). Limitation: Windows may still cache the WSL2 virtual disk file, which we cannot control.
- **3 warm power runs** right after, without restarting.
- Per query we report the median of the 3 warm runs with min/max, and the cold run separately.

## 6. Metric (§7.6.3)
QphDS@SF = ⌊ SF · Q / ⁴√(T_PT · T_TT · T_DM · T_LD) ⌋, where Q = 99 · Sq, T_PT = Sq · T_Power, T_TT = T_TT1 + T_TT2, T_DM = T_DM1 + T_DM2 and T_LD = 0.01 · Sq · T_Load, all times in hours.

The formula is an image in the PDF. We checked it against a published result (Tencent TDSQL at SF 10000): the inputs reproduce the reported 72,603,042 QphDS exactly.

Without data maintenance there is no T_DM and no T_TT2, so the official metric cannot be computed. We report T_Load, T_Power and T_TT1 directly, plus a clearly labelled simplified metric: ⌊ SF · Q / ∛(T_PT · T_TT1 · T_LD) ⌋.

## 7. Query generation
- **Kit 4.0.0 limitation (found by ④):** `dsqgen -QUALIFY Y` only puts the queries in template order; it does not use the qualification parameters. Our queries therefore cannot be checked against the kit's `answer_sets/`. Instead, ④ computed reference answers with DuckDB from exactly the same SQL text, and checked the DuckDB setup itself with the official parameter values for Q3 and Q96 (both match `answer_sets/`).
- **Dialect:** `part1-tpcds/queries/templates/clickhouse.tpl`. It has the same `LIMIT` syntax as `netezza`, plus a `-- start query … / -- end query …` marker around each query, which kit 4.0.0 no longer defines. The harness uses the markers to split a stream into queries. With the same seed it produces exactly the same SQL as ④'s netezza files (checked: 99/99).
- **ClickHouse fixes go into templates, never into generated SQL.** To fix a query, copy the kit template to `part1-tpcds/queries/templates/queryNN.tpl` and edit it; generation overlays this folder on the kit's templates. Fixing generated SQL would only work for one set of parameters, but every SF and every stream has different parameters: 15 templates even draw them from table sizes (e.g. `rowcount("store")`). One global rewrite is applied after generation: `+ N days` → `+ INTERVAL N DAY` (18 templates). Every change is logged in `queries/CHANGES.md`.
- **Validation set (SF 1):** one file per template, `dsqgen -TEMPLATE queryNN.tpl -QUALIFY Y -SCALE 1` with the default seed, as in ④'s `queries/original/`.
- **Benchmark streams, generated for each SF:** `dsqgen -INPUT templates.lst -STREAMS 5 -SCALE <SF> -RNGSEED 20261101 -DIALECT clickhouse`. Stream 0 is the power test; streams 1–4 are the throughput test. The kit fixes the order of each stream (spec Appendix D; stream 0 starts with 96, 7, 75, 44…, checked), and the seed only sets the parameters, so every rerun uses the same queries.

## 8. Output files
For each run, the harness writes to `part1-tpcds/results/sf<SF>/<run_id>/`:
- **One CSV per test** (`load`, `power`, `throughput`, `power_cold`, `power_warm`), one row per SQL statement: `run_id, sf, test, repeat, stream, position, query, part, query_id, start_ts, elapsed_s, server_ms, read_rows, read_bytes, peak_memory_bytes, result_rows, status, error`. `part` is 1 or 2 for the two-statement queries (14, 23, 24, 39); a query's elapsed time is the sum of its parts. Server-side values come from `system.query_log`, matched on `query_id`.
- **`environment.json`:** host CPU, RAM and kernel, Docker and ClickHouse versions, effective server memory limit, other running containers, the settings profile, the git commit, and the SHA-256 of every query file used.
- **`summary.json`:** T_Load, T_Power, T_TT1, failure counts and the simplified metric.

Charts are generated from these files by scripts only.

## 9. Deviations from the spec
- The qualification parameters are not used (kit 4.0.0 limitation, section 7). Queries are validated against DuckDB reference answers for the same SQL, not against `answer_sets/`.
- ClickHouse-specific query changes. The spec only allows minor modifications (§4.2.3) and approved variants (§4.2.6); larger rewrites would need approval. Every change is disclosed and justified in `queries/CHANGES.md` and in the report (§4.2.3.3).
- We fix the `dsqgen` seed for reproducibility; the spec seeds it from the load end time (comment under §7.4.3.8).
- No data maintenance, so no throughput test 2 and no official QphDS (section 6).
- The query condition cache is disabled (section 4).
- The extra cold/warm repetitions (section 5) are outside the spec sequence; the cold runs restart the server after the sequence, which §7.4.1.3 does not cover.
- Single machine, no audit, no pricing, so there is no price-performance metric.

## 10. Decision log
Decided on 17 Oct. Comments go in the PR.
1. **T_Load** includes `OPTIMIZE TABLE … FINAL` on every table (section 3.1).
2. **Timeout:** 1800 s per query (section 4).
3. **No data maintenance.** Week 2 ended with the DDL and the loader still pending, so we are not ahead of schedule. To be revisited only if the lecturer requires it.
4. **Cold runs:** stop the container, drop the page cache, start the container; implemented in the harness (section 5).
5. **Reference SF:** the power run must take under 1 hour, instead of 2 (section 2).
6. **Query condition cache disabled** (section 4).
7. **Queries:** fixes are made in templates; ClickHouse dialect with query markers; benchmark seed 20261101 (section 7).
8. **No other containers** during runs (section 1).
9. **Reference SF 50** (25 Oct, after the trial run): SF 100 does not fit on disk, SF 50 meets the three conditions (section 2).
