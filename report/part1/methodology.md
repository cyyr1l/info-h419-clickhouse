# 6. Benchmark methodology (draft)

**Status:** draft of 18 Oct, revised with ④'s review (issue #5), derived from [`docs/benchmark-protocol.md`](../../docs/benchmark-protocol.md), open for comments. To be pasted into the Part I report (Google Docs). Section numbers follow the Part I report outline in `docs/ROADMAP.md` · **Owner:** ② Benchmark & Measurement

This section describes how we measure: the tests run at each scale factor, the definition of every time we report, the controls that keep the runs comparable, the data we record and the metric. The machine, the software versions, the settings profile and the choice of scale factors are described in Section 4; query generation, query changes and the validation of results in Section 5. Our results are derived from TPC-DS v4.0.0 (Clause 7, "Performance Metrics and Execution Rules") and are not official TPC results. Section 6.9 lists every deviation from the specification.

## 6.1 Test sequence

At each of the four scale factors, we run the following tests in this order (TPC-DS §7.4.2):

1. the load test (Section 6.2);
2. the power test (Section 6.3);
3. the first throughput test (Section 6.4).

ClickHouse is not restarted between the start of the power test and the end of the throughput test (§7.4.1.3). We do not implement data maintenance, so the sequence has neither data maintenance tests nor a second throughput test (Section 6.9). After the sequence, we add one cold and three warm power runs to obtain stable per-query timings (Section 6.5).

The query streams are generated for each scale factor with `dsqgen -STREAMS 5` and a fixed seed: stream 0 for the power test and streams 1 to 4 for the throughput test. The kit fixes the order of the queries in each stream (specification, Appendix D); the seed only sets the parameter values. Each scale factor needs its own streams, because 15 templates derive some of their parameters from the table sizes.

A single command of our benchmark harness (`harness.py campaign`) runs the whole sequence for one scale factor, so every scale factor follows exactly the same procedure.

## 6.2 Load test

The data is generated beforehand with `dsdgen` into flat files. Generation is timed separately and is not part of the load time (§7.4.3.8.1a). The load time $T_{Load}$ runs from the first `CREATE TABLE` to the end of `OPTIMIZE TABLE … FINAL` on every table.

`OPTIMIZE … FINAL` is part of the load for two reasons. Every insert into a ClickHouse table creates new data parts, which the server merges in the background during the following minutes. Forcing these merges leaves each table with one part per partition, so (i) every run starts from the same physical layout, and (ii) no background merge competes with the queries of the power test. We report the time of the load phase and of the optimize phase, as well as their sum.

After the load, we record for every table its number of rows and parts and its size on disk, compressed and uncompressed (from `system.parts`). Before the power test starts, the row counts are checked against the counts expected by the kit; this check is not timed (§7.4.3.8.1f).

## 6.3 Power test

The power test runs stream 0 in a single session: the 99 queries, one after the other. The elapsed time of a query is the client wall-clock time from sending the query text to receiving the last byte of its result (§7.4.7.1). It is measured with Python's `time.perf_counter()`, whose resolution is far finer than the 0.01 s required by §7.4.1.6. Queries 14, 23, 24 and 39 consist of two SQL statements; the elapsed time of the query is the sum of both. $T_{Power}$ runs from sending the first query of the stream to receiving the last result.

## 6.4 Throughput test

The throughput test runs $S_q = 4$ query streams at the same time, the smallest number the specification allows (an even number of at least four, §7.4.6.9). Each of streams 1 to 4 is a different permutation of the 99 queries, with its own parameter values. Each stream has its own session and runs its queries one after the other; the four streams are released at the same instant. $T_{TT1}$ runs from the first query sent by any stream to the last result received by any stream. The elapsed time of every query is recorded per stream.

## 6.5 Additional cold and warm power runs

The specification runs each test once. A single measurement per query cannot separate a real difference from noise, so after the specification sequence we add four power runs on stream 0 at each scale factor (our addition, outside the specification):

- **One cold run.** The harness stops the ClickHouse container, drops the Linux page cache of the WSL2 virtual machine, starts the container again and waits until the server answers queries. Restarting the server empties all its in-memory caches (mark cache, primary index, …). The page cache is dropped from a privileged container, which shares the kernel of the WSL2 virtual machine.
- **Three warm runs**, immediately after the cold run, without restarting the server.

For each query, we report the median of the three warm runs with their minimum and maximum and the relative spread (max − min) / median, and the cold run separately. For very short queries, the client time is dominated by the HTTP round trip, so we also report the server-side duration recorded in `system.query_log` (Section 6.7). One limitation remains: Windows may keep parts of the WSL2 virtual disk file in its own cache, which cannot be cleared from inside WSL2, so a cold run may be slightly warmer than a cold start of the whole machine.

## 6.6 Controls

**Same environment for every run.** All measurements, at every scale factor, run on the same machine with the same ClickHouse version and the same settings (Section 4). The machine runs in the Windows "Best performance" power mode, with other applications closed and Windows Update paused.

**No other containers.** During measured runs, the ClickHouse server is the only running container. ClickHouse 26.8 adapts its memory limit to the memory that is free at the moment, so other containers would reduce the memory available to the queries. The harness records the running containers in every run and warns if any other container is up.

**One global settings profile.** The harness sends the same settings profile (Section 4) with every query of every run. If a setting had to change to make a query run, it would change for all queries and every scale factor would be measured again: there is no per-query tuning.

**Result caches disabled.** The query cache (`use_query_cache = 0`, the default) and the query condition cache (`use_query_condition_cache = 0`, enabled by default in 26.8) are disabled. The query condition cache remembers which granules matched a filter in an earlier execution. Since the warm runs repeat identical queries, it would turn them into a measurement of that cache rather than of query processing. Data caches (the mark cache and the page cache of the operating system) stay enabled, as they are the normal warm state of a database server.

**Timeout and memory.** Each query may run for at most 1,800 s (`max_execution_time`, with `timeout_overflow_mode = 'throw'`). The reference scale factor is chosen so that a whole power run takes less than one hour (Section 4), and a single 30-minute query would already use half of that budget. Under four concurrent streams, a heavy query can take up to about four times longer than alone, so this limit only stops runaway queries. Memory limits are left at the ClickHouse defaults: the server may use 90 % of the memory visible to WSL2, adjusted dynamically.

**Failures are results.** Every statement receives a status: `ok`, `timeout` (ClickHouse error codes 159 and 160, or no answer within the time limit plus 60 s), `memory` (code 241) or `error` (any other code). A failed statement is recorded with its error code and message, and the stream continues with the next query. A run with any failure does not comply with §7.4.1.1; we report such failures in Section 7 rather than hide them. In the analysis, failed and timed-out statements are excluded from the medians and listed in a table of their own, and the scaling curves only use the queries that succeed at all four scale factors.

**Correctness before speed.** No timed run starts before all 99 queries have been validated at SF 1 against reference answers computed with DuckDB from the same SQL text (Section 5). A timing is only meaningful for a query whose result is correct. The validation set uses the default `dsqgen` seed at SF 1, whereas the measured streams use our fixed seed at every scale factor: validation therefore checks the logic of each query and of our ClickHouse changes, not every result produced during the measured runs. As a cheap check at the larger scale factors, a query must return the same number of rows in every run of stream 0 (the power test and the cold and warm runs), and the queries that return no rows in the measured streams are flagged.

## 6.7 Data collected

The harness talks to ClickHouse over its HTTP interface, with one keep-alive session per stream. It asks the server to hold each result until the query has finished, so that an error raised late in a query is never recorded as a success. Every statement gets a unique query identifier, which links the client-side measurement to the server's own record in `system.query_log`. After each test, the harness reads from this log, for every statement, the server-side duration, the number of rows and bytes read, the peak memory usage and the number of result rows.

Each run writes the following files to `part1-tpcds/results/sf<SF>/<run_id>/`:

- one CSV file per test (load, power, throughput, cold and warm power runs), with one row per SQL statement: start time, client elapsed time, server-side values, status and error message;
- `environment.json`: the hardware as seen from WSL2, the Docker and ClickHouse versions, the effective memory limit of the server, the other running containers, the settings profile, the git commit of the code and a SHA-256 hash of every query file used;
- `summary.json`: $T_{Load}$, $T_{Power}$, $T_{TT1}$, the number of failures and the simplified metric of Section 6.8.

These raw files are committed with the code, and every chart in Section 7 is generated from them by a script.

## 6.8 Metric

The primary performance metric of TPC-DS (§7.6.3) is

$$
\text{QphDS@SF} = \left\lfloor \frac{SF \cdot Q}{\sqrt[4]{T_{PT} \cdot T_{TT} \cdot T_{DM} \cdot T_{LD}}} \right\rfloor
$$

where $Q = 99 \cdot S_q$, $T_{PT} = S_q \cdot T_{Power}$, $T_{TT} = T_{TT1} + T_{TT2}$, $T_{DM} = T_{DM1} + T_{DM2}$ and $T_{LD} = 0.01 \cdot S_q \cdot T_{Load}$, with all times in hours. We checked our implementation of this formula against a published result: the input times of the Tencent TDSQL result at SF 10,000 give exactly the reported 72,603,042 QphDS.

Without data maintenance, $T_{DM}$ and $T_{TT2}$ do not exist, and the official metric cannot be computed. We therefore report $T_{Load}$, $T_{Power}$ and $T_{TT1}$ directly. As a single summary figure, we also compute a simplified metric that keeps the three terms we measure:

$$
\text{QphDS}_{\text{simplified}}\text{@SF} = \left\lfloor \frac{SF \cdot Q}{\sqrt[3]{T_{PT} \cdot T_{TT1} \cdot T_{LD}}} \right\rfloor
$$

This simplified metric is our own. It is not a QphDS value and cannot be compared with published TPC-DS results.

To compare the power and throughput tests directly, we also report the concurrency efficiency

$$
E = \frac{S_q \cdot T_{Power}}{T_{TT1}}
$$

$E = S_q = 4$ would mean that the four streams overlap perfectly, each running as fast as it does alone; $E = 1$ means that running them concurrently brings no gain over running them one after the other. Streams 1 to 4 use other parameter values than stream 0, so $E$ is an approximation.

## 6.9 Deviations from the specification

- **Query parameters.** In kit 4.0.0, `dsqgen -QUALIFY Y` does not use the qualification parameters, so our queries cannot be checked against the answer sets shipped with the kit. We validate them instead against DuckDB answers for exactly the same SQL text (Section 5).
- **Query changes.** Some queries were modified to run on ClickHouse. The specification only allows minor modifications (§4.2.3) and approved query variants (§4.2.6); every change is disclosed and justified in the appendix that lists the modified queries.
- **Fixed seed.** We fix the `dsqgen` seed (20261101), so that every rerun uses the same queries. The specification derives the seed from the end time of the load test (comment under §7.4.3.8).
- **No data maintenance**, hence no second throughput test and no official QphDS (Section 6.8).
- **Query condition cache disabled** (Section 6.6); the specification has no rule about such a cache.
- **Additional cold and warm runs** (Section 6.5) outside the specification sequence. The cold run restarts the server after the sequence, a case that §7.4.1.3 does not cover.
- **Single machine, no audit and no pricing**, hence no price/performance metric.
