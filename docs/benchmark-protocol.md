# Benchmark protocol: Part I (TPC-DS on ClickHouse)

**Status:** draft for review at the meeting on Tue 13 Oct · **Owner:** ② Benchmark & Measurement
**Source:** TPC-DS v4.0.0 specification, Clause 7 "Performance Metrics and Execution Rules" (pp. 69–79 of `tools/DSGen-software-code-4.0.0/specification/specification_4.0.0.pdf`). The § numbers below refer to that clause.

Our results are *derived from TPC-DS*, not official TPC results. Every deviation from the spec is listed in section 9.

## 1. System under test
- **Machine:** ②'s main machine, Windows, 32 GB RAM. *To fill in: CPU model, cores/threads, disk model and type, free space, Windows build.*
- **Software:** ClickHouse **26.8.24.9** (pinned) in Docker Desktop with the WSL2 backend; TPC-DS kit 4.0.0 (`dsdgen`, `dsqgen`).
- **WSL2 resources:** Docker Desktop gives WSL2 only 50% of the RAM by default (checked on a 16 GB laptop: Docker sees 8 GB). Create `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  memory=24GB
  processors=<number of logical cores>
  ```
  then run `wsl --shutdown` and restart Docker Desktop.
- **Data location:** clone the repo inside the WSL2 filesystem (e.g. `~/info-h419-clickhouse` in Ubuntu), so `data/` is not on a Windows drive.
- **During runs:** on AC power, Windows power mode "Best performance", other apps closed, no other Docker containers running, Windows Update paused.

## 2. Scale factors
- **Reference SF:** the largest SF that (1) loads successfully, (2) fits on disk, and (3) completes one power run of the 99 queries in under 2 hours, with every failure explained. Try 100, then 50, then 30.
- **Series:** 0.1×, 0.2×, 0.5× and 1× the reference (e.g. 10, 20, 50, 100).
- Decided by Sun 18 Oct, after a trial run on the benchmark machine.

## 3. Test sequence (§7.4.2)
For each SF, in this order, without restarting ClickHouse between the start of the power test and the end of the last test (§7.4.1.3):

1. Load test
2. Power test
3. Throughput test 1
4. *Data maintenance test 1 → throughput test 2 → data maintenance test 2, only if we implement data maintenance (decision at the end of week 2).*

The extra repetitions of section 5 run after this sequence. All timings use a clock with a resolution of at least 0.01 s (§7.4.1.6): `time.perf_counter()` in the Python harness.

### 3.1 Load test (§7.4.3)
- We load from flat files generated beforehand by `dsdgen`. Generation time is not part of T_Load (§7.4.3.8.1a), but we record it anyway.
- **T_Load** starts at the first `CREATE TABLE` and ends when the database is ready for queries: all inserts done **and** background merges finished. Proposal: run `OPTIMIZE TABLE … FINAL` on every table and count it in T_Load, so that every run starts from the same part layout. The alternative is to wait until `system.merges` is empty.
- We also record, per table: load time, row count, and on-disk size compressed and uncompressed (from `system.parts`).
- Row counts are checked against the `dsdgen` files before the power test. This check is not timed (§7.4.3.8.1f).

### 3.2 Power test (§7.4.4–7.4.5)
- One session runs stream 0: the 99 queries in the stream-0 order produced by `dsqgen` (spec Appendix D), one at a time.
- **Query elapsed time** = client wall time from sending the query text to receiving the last row of the result (§7.4.7.1). Queries 14, 23, 24 and 39 contain two SQL statements; both count towards that query's time.
- **T_Power** runs from sending the first query to receiving the last result.

### 3.3 Throughput test (§7.4.6–7.4.7)
- **Sq = 4 streams.** The spec requires an even number ≥ 4 (§7.4.6.9). Streams 1–4 come from `dsqgen`, each a different permutation of the 99 queries.
- Each stream has its own session and runs its queries one after another. The 4 streams start together.
- **T_TT1** runs from the first query sent by any stream to the last result received by any stream. Every query's elapsed time is recorded per stream.

### 3.4 Data maintenance (§7.4.8), only if implemented
- Each data maintenance test runs Sq/2 = 2 refresh runs, each with its own refresh data set from `dsdgen`.

## 4. Settings and failures
- **One global settings profile** for all queries, all SFs and all runs: the SQL-compatibility profile from ③, plus `use_query_cache = 0` set explicitly. If a setting must change to make a query run, it changes for everyone and all SFs are re-run. No per-query tuning.
- **Timeout:** `max_execution_time = 1800` s per query, to be adjusted after the SF trial.
- **Memory:** ClickHouse defaults (server limit = 90% of the RAM visible to WSL2). A query that runs out of memory is recorded as failed.
- **Failures:** a failed or timed-out query is recorded with its error, and the stream moves on to the next query. Any failure makes the run non-compliant with §7.4.1.1. We report it; we never hide it.
- **Correctness first:** no timed run before all 99 queries are validated at SF 1 against the answer sets (④).

## 5. Extra repetitions (our addition, not in the spec)
The spec runs each test once. To get stable per-query numbers, we add for each SF, after the spec sequence:
- **1 cold power run:** restart the ClickHouse container, drop the OS page cache (`docker run --rm --privileged alpine sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"`), then run `SYSTEM DROP MARK CACHE`, `SYSTEM DROP UNCOMPRESSED CACHE` and `SYSTEM DROP QUERY CACHE`.
- **3 warm power runs** right after, without restarting.
- Per query we report the median of the 3 warm runs with min/max, and the cold run separately.

## 6. Metric (§7.6.3)
QphDS@SF = ⌊ SF · Q / ⁴√(T_PT · T_TT · T_DM · T_LD) ⌋, where Q = 99 · Sq, T_PT = Sq · T_Power, T_TT = T_TT1 + T_TT2, T_DM = T_DM1 + T_DM2 and T_LD = 0.01 · Sq · T_Load, all times in hours.

The formula is an image in the PDF. We checked it against a published result (Tencent TDSQL at SF 10000): the inputs reproduce the reported 72,603,042 QphDS exactly.

Without data maintenance there is no T_DM and no T_TT2, so the official metric cannot be computed. In that case we report T_Load, T_Power and T_TT1 directly, plus a clearly labelled simplified metric: ⌊ SF · Q / ∛(T_PT · T_TT1 · T_LD) ⌋.

## 7. Query generation
- **Validation set (SF 1):** `dsqgen -QUALIFY Y`, so that the kit's `answer_sets/` apply.
- **Benchmark streams 0–4:** `dsqgen -STREAMS 5 -SCALE <SF>` with a fixed `-RNGSEED`, so that every rerun uses the same queries.
- **Dialect:** `netezza` (it uses `LIMIT`), then the ClickHouse fixes, each logged in `queries/CHANGES.md`.

## 8. Output files
- **One CSV per test** in `part1-tpcds/results/`, one row per query execution: `run_id, sf, test, stream, position, query, query_id, start_ts, elapsed_s, server_ms, read_rows, read_bytes, peak_memory_bytes, result_rows, status, error`. Server-side values come from `system.query_log`, matched on `query_id`.
- **One `environment.json` per run:** machine specs, `.wslconfig`, Docker and ClickHouse versions, changed settings (`system.settings WHERE changed`), git commit, `dsqgen` seed.
- Charts are generated from these files by scripts only.

## 9. Deviations from the spec
- We fix the `dsqgen` seed for reproducibility; the spec seeds it from the load end time (comment under §7.4.3.8).
- Data maintenance and throughput test 2 are skipped unless we implement data maintenance, so there is no official QphDS.
- The extra cold/warm repetitions (section 5) are outside the spec sequence.
- Single machine, no audit, no pricing, so there is no price-performance metric.

## 10. To decide at the meeting
1. T_Load: `OPTIMIZE … FINAL`, or wait for merges?
2. Timeout per query (1800 s proposed).
3. Data maintenance: yes or no, at the end of week 2.
4. Cold-run reset method, to align with ①'s reset script.
