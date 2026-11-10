# Benchmark protocol: Part II (TPC-DI on ClickHouse)

**Status:** draft, 6 Nov · **Owner:** ② Benchmark & Measurement
**Source:** TPC-DI v1.1.0 specification (https://www.tpc.org/TPC_Documents_Current_Versions/pdf/TPC-DI_v1.1.0.pdf), mainly Clause 7 "Execution Rules & Metrics" (pp. 84–90). The § numbers below refer to the spec.

Our results are *derived from TPC-DI*, not official TPC results. Every deviation from the spec is listed in section 7.

## 1. System under test
- **Machine and software:** the same as in Part I (`docs/benchmark-protocol.md`, section 1): ②'s desktop, WSL2 with 24 GB and 16 CPUs, Docker Desktop, ClickHouse 26.8.24.9. The rules during runs are also the same: only `infoh419-clickhouse` running, AC power, power mode "Best performance", other apps closed, Windows Update paused.
- **Data generator:** DIGen 1.1.0 from the TPC-DI tools. The spec requires the DIGen version to match the spec version (§6.2.3), here both 1.1.0. It needs Java SE 7 or later (§6.2.6); we run it on Java 8 in ①'s Docker image.
- **DI system:** our own, decided on 6 Nov. A Python orchestrator runs SQL files in ClickHouse (ELT), on the same machine.

### 1.1 Clock
§0.3 asks for calibrated measuring equipment. On this machine, every clock of the WSL2 VM runs about 8% fast against the Windows clock. We read Windows time with `[DateTimeOffset]::UtcNow` and compared, on 6 Nov:

| Clocksource of the VM | Monotonic / Windows | Cost of one clock read |
|---|---|---|
| `tsc` (default) | 1.084 | ~60 ns |
| `hyperv_clocksource_tsc_page` | 1.083 | – |
| `hyperv_clocksource_msr` | 1.079 | ~1 µs |
| `acpi_pm` | 1.088 | ~1.8 µs |

- We measured the same factor on 26 Oct (1.084), so Part I's durations are about 8% too long (Part I report, section 4.1).
- All four clocksources drift, so the cause is outside the VM (the Hyper-V time base; a BIOS clock setting is only a guess). It cannot be fixed from WSL. We keep `tsc`, the fastest to read.
- `CLOCK_REALTIME` is pulled back to Windows time by Hyper-V time sync: over one minute it moved 55.73 s while Windows moved 55.74 s. The pull-back happens in steps, though. Once, right after a clocksource switch, it fell 1.9 s behind within 5 s.
- **Consequences:**
  - The official phase times (section 4.1) come from ClickHouse timestamps (`now64()`, which reads the realtime clock). So they follow Windows time, up to the size of one step.
  - Our step durations (section 4.2) use `time.perf_counter()`, which is monotonic and never steps, divided by the drift factor. The run script measures this factor against the Windows clock before and after every run (60 s each) and stores both values in `environment.json`.
  - ClickHouse's `query_duration_ms` is monotonic as well. Divide it by the same factor before comparing it with wall times.

## 2. Scale factors
- **DIGen:** `java -jar DIGen.jar -sf <SF> -o data/tpcdi/sf<SF>`, with SF ≥ 3. It writes `Batch1/`, `Batch2/`, `Batch3/` and `digen_report.txt`.
  - The row counts per batch in `digen_report.txt` feed the metric (§6.3). The file must not be modified.
  - Generation is not timed (§1.2.2.1.1), but we record its time and the size of the files.
- **Limits from the spec:** each incremental update phase must take at most 3600 s (§7.2.1.1.1, §7.2.2). All batches of a run use the same SF (§7.2.1.1.3).
- **Reference SF:** the largest SF that meets all of these:
  1. the raw files and the database fit on disk;
  2. a full run passes the audit;
  3. both incremental phases stay under 3600 s;
  4. the historical load is short enough for 3 runs per SF (section 4.5).

  Roadmap: try SF 100 at the end of week 7 (historical load only), and decide by Sun 6 Dec.
- **Series:** the reference SF and three smaller SFs (0.1×, 0.2× and 0.5× the reference), all ≥ 3. Part I taught us to check the generator before fixing the series. Using `digen_report.txt` and the audit files, check that every table grows with the SF.
- **Generation (measured on 10 Nov):**
  - PDGF, the engine behind DIGen, is multi-threaded. SF 3 (267 MiB) and SF 10 (960 MiB) each take about 12 s, so generation is not a bottleneck.
  - Batch2 and Batch3 are tiny, about 0.4% of the Batch1 rows (SF 10: 15,980,433 / 67,451 / 67,381).
- **DIGen on Linux:** four traps.
  1. DIGen runs PDGF from a lowercase `pdgf` folder, while the zip has `PDGF`; a symlink `pdgf -> PDGF` fixes it.
  2. PDGF's licence prompt needs ENTER, then `YES`.
  3. stdin must stay open until `digen_report.txt` exists. At EOF, DIGen feeds "null" commands to PDGF's shell, which aborts.
  4. DIGen exits 0 even when it fails, so check `digen_report.txt` instead of the exit code.
- **Licence:** the PDGF licence forbids redistribution, so DIGen and PDGF stay out of the repository (unlike the TPC-DS kit). People who reproduce our results download the TPC-DI tools from tpc.org.

## 3. Benchmark run (§7.2)
One command starts a Benchmark Run, and the run needs no manual intervention (§7.2.2.2). Each phase starts when the previous one ends (§7.2.2):

| Phase | BatchID | Reads | Timed | Ends with |
|---|---|---|---|---|
| Initialization | 0 | no source files (§7.2.3.4) | no | batch validation + PCR → CT0 |
| Historical Load (HL) | 1 | `Batch1/` | yes: EH | batch validation + PCR → CT1 |
| Incremental Update 1 (IU1) | 2 | `Batch2/` | yes: EI1 ≤ 3600 s | batch validation + PCR → CT2 |
| Incremental Update 2 (IU2) | 3 | `Batch3/` | yes: EI2 ≤ 3600 s | batch validation + PCR → CT3 |
| Automated Audit | – | `*_audit.csv` of the 3 batches | no | audit query, every test "OK" |

PCR is the phase completion record that the batch validation query writes into DImessages.

- **Preparation (before the run, not timed, §7.2.1):** the DIGen output sits in `data/tpcdi/sf<SF>/`. This folder is the Staging Area: no file may be added to it or changed (§2.4.4–2.4.5).
- **Clean start (§7.1, §3.4.9.1, §4.3.7):** no tables, data structures or caches may be left from an earlier run. Before Initialization, the run script:
  - drops the TPC-DI database;
  - restarts the ClickHouse container;
  - drops the page cache of the WSL2 VM (the cold reset of Part I).

  So every run is a cold run.
- **Initialization:**
  - Create the database with all staging and DW tables (Clause 3). ③ writes the DDL of the dimensions; ④ writes DImessages and Audit.
  - Write a 'Status' message with BatchID 0.
  - Run the batch validation query, which writes the PCR.
  - The audit checks that every count at BatchID 0 is 0 ("DImessages initial condition"). So every DW table stays empty here, the reference tables included (DimDate, DimTime, StatusType…): they are loaded in the Historical Load.
- **Everything that reads source files is timed**, because Initialization may not read the Staging Area (§7.2.3.4). This covers loading the files into staging tables, converting `CustomerMgmt.xml` and cutting the FINWIRE records. The XML converter streams its rows into ClickHouse, or writes them outside the Staging Area.
- **Order (§4.3.3):** within a phase, the steps follow the data dependencies. For example, DimSecurity and DimAccount come before DimTrade, and DimTrade before FactHoldings. No phase reads a later batch (§4.3.5.5).
- **From IU1 on, the data warehouse stays queryable (§4.3.5.8):** committed rows must stay visible to other sessions. Section 4.4 explains what this means for our update strategy.
- **Automated Audit (§7.2.6):**
  - Load the audit files of all batches into the Audit table, without their header row.
  - Run data visibility 1 one last time.
  - Run the audit query (Appendix A, ported by ④).

  The run is valid only if every test is "OK" (§7.2.6.7). Otherwise we report the failing tests.

## 4. Timing
### 4.1 Official phase times (§7.5)
- **CT of a phase:** the `MessageDateAndTime` of its PCR row in DImessages (MessageType 'PCR', the BatchID of the phase). The batch validation query writes this row at the end of the phase (Appendix B), and its own run time is part of the phase (§7.4.2).
- **EH = CT1 − CT0, EI1 = CT2 − CT1 and EI2 = CT3 − CT2**, in seconds, reported to 0.1 s and rounded up (§7.1.1).
- **Precision:** in ClickHouse, the spec's `CURRENT_TIMESTAMP` is a `DateTime`, which only has 1-second resolution (checked on 26.8). So `MessageDateAndTime` is a `DateTime64(3)` and the ported queries use `now64(3)` (④, who also writes the DImessages DDL).
- **BatchID of the PCR:** Appendix B takes `max(BatchID)` from DImessages as the BatchID of the phase. A phase that logged no alert would therefore get the BatchID of the previous phase. To avoid this, the orchestrator writes a 'Status' message with the new BatchID at the start of each phase. 'Status' is one of the message types the spec defines (§3.2.8).
- **What the audit checks in DImessages:**
  - 4 distinct BatchIDs (0–3), each with one PCR;
  - exactly 24 'Validation' rows per batch, so the ported validation query keeps all 24 counts and runs once per phase;
  - alerts are counted by exact `MessageText` with MessageType 'Alert', e.g. 'Invalid trade commission'.

### 4.2 Step times (our addition)
The spec only times phases. To see which steps dominate, the orchestrator also times every step:
- **A step** is one loader (one file into a staging table), one SQL file (one target table), the XML conversion, or the batch validation.
- **What we record per step:**
  - phase, BatchID, step name and target table;
  - start time (realtime);
  - duration (monotonic, divided by the drift factor of section 1.1);
  - status;
  - from `system.query_log`, matched on `query_id`: rows and bytes read and written, and peak memory.
- **Check:** per phase, the step times plus the gaps between steps must add up to EH or EI, within 1% or 1 s, whichever is larger. A larger gap means a clock or orchestrator problem.

### 4.3 Metric (§7.5–7.6)
- **Rows:** RH, RI1 and RI2 are the row counts of Batch1, Batch2 and Batch3 in `digen_report.txt` (§7.5.2.2, §7.5.3.2).
- **Throughputs:** TH = RH / EH, TI1 = RI1 / max(EI1, 1800) and TI2 = RI2 / max(EI2, 1800) (§7.5).
- **TPC_DI_RPS = trunc( √(TH × min(TI1, TI2)) ):** the geometric mean of TH and the slower incremental throughput (§7.6.1).
- **The 1800-second floor:** an incremental phase shorter than 30 minutes counts as 1800 s. The spec's rationale is that the benchmark targets incremental phases of at least 1800 s.
  - Batch2 and Batch3 hold about 0.4% of the rows of Batch1, so our incremental phases will take seconds. Then min(TI1, TI2) = RI/1800, and TPC_DI_RPS ≈ √(TH × RI / 1800). The metric then grows with the SF however fast the updates run.
  - We therefore also report RI1/EI1 and RI2/EI2, labelled as our own unfloored throughputs, as well as the phase times themselves.
- **No price/performance metric** (§7.6.2), since there is no pricing.

### 4.4 Data visibility queries (§7.3)
- **When they run:** from the start of IU1 to the end of IU2, a separate thread with its own ClickHouse session (§7.3.7) runs:
  1. data visibility 1 when IU1 starts;
  2. data visibility 2 right after it;
  3. data visibility 2 every 60 s until IU2 ends.

  The spec only requires gaps of at most 5 minutes (§7.3.3–7.3.6). The run right after data visibility 1 guarantees at least one data visibility 2, even when both phases are short.
- These queries run during the timed phases and slow them down a little. The spec intends this.
- **What the audit checks on these rows, and what it means for our design:**
  - **"Row counts must be non-decreasing over time"**, for every table. So committed rows may never disappear, not even for a moment (§4.3.5.8, §3.4.7.2).
    - Rebuilding a dimension is fine: `EXCHANGE TABLES` swaps two tables atomically (checked on 26.8).
    - DimTrade is a `ReplacingMergeTree`. Without FINAL, `count()` also counts the old versions of updated rows until a background merge removes them, and then the count drops. Checked on 26.8: 3 rows without FINAL, 2 with `final = 1`.
    - So the validation, visibility and audit sessions run with the setting `final = 1`.
  - **"Row counts match when joined to dimensions":** a fact row may only become visible after the dimension rows it references. So dimensions are always written before the facts that use them.

### 4.5 Repetitions (our addition)
- The spec runs once. We run each SF 3 times; the roadmap says 2–3 if time allows. Each run is a full Benchmark Run from a clean start.
- We report the median of EH, EI1, EI2 and TPC_DI_RPS with their min and max, and the median time of each step.
- There are no warm runs, because §7.1 forbids caches left from an earlier run.

## 5. Settings and failures
- **Settings:** one settings profile for the whole DI application, the same for every SF and every run, and versioned in git.
  - Settings inside a SQL file (e.g. `SETTINGS join_algorithm = …`) are part of the DI application. They are the same at every SF and are listed in the report.
- **Caches:** the query cache and the query condition cache are off, as in Part I.
- **Timeouts:** there is no per-query timeout. An incremental phase over 3600 s makes the run invalid (section 2), which means the SF is too large.
- **Failures:** a failed step stops the run, because its phase can no longer complete (§4.3.5.1). The error is recorded. Any fix to the DI application means re-running every SF.

## 6. Output files
For each run, the orchestrator writes these files to `part2-tpcdi/results/sf<SF>/<run_id>/`:
- **`steps.csv`:** one row per step (section 4.2), with the columns `run_id, sf, phase, batch_id, step, target_table, query_id, start_ts, elapsed_s, elapsed_raw_s, read_rows, read_bytes, written_rows, written_bytes, peak_memory_bytes, status, error`. `elapsed_raw_s` is the monotonic value before the clock correction.
- **`dimessages.csv`:** the whole DImessages table at the end of the run.
- **`audit.csv`:** the output of the audit query.
- **`summary.json`:**
  - CT0–CT3, EH, EI1 and EI2;
  - RH, RI1 and RI2;
  - TH, TI1, TI2 and TPC_DI_RPS, plus the unfloored throughputs;
  - the audit result (number of tests OK and failed).
- **`digen_report.txt`:** a copy of DIGen's report for this SF.
- **`environment.json`:** the same as in Part I (host, versions, memory limit, other containers, settings, git commit), plus the clocksource and the drift factor before and after the run.

Charts are generated from these files by scripts only (④).

## 7. Deviations from the spec (expected so far)
- **DI system:** our own Python and SQL, not a commercially available DI product (§4.2.1).
- **Durability and ACID:** we run no durability tests (§2.4.1, §3.4.6, §8.4) and demonstrate no ACID compliance. A result would therefore belong to the OPEN class (§3.4.10.3).
- **Formal requirements:** no pricing (Clause 9), no full disclosure report (Clause 10), no independent auditor (Clause 11).
- **Commits:** ClickHouse has no multi-statement transactions. While a large INSERT runs, its rows become visible part by part. §4.3.5.2 allows this, as long as the visible rows are complete. A phase is complete when all its statements have returned.
- **Ported queries:** the queries of Appendices A–C are ported to ClickHouse (§3.4.11). One change is `now64(3)` instead of `CURRENT_TIMESTAMP`, to get 0.1 s precision. Every change is disclosed.
- **Our additions:** step timing, the clock correction of step times, the unfloored throughputs and 3 runs per SF.
- **Single machine:** the orchestrator, ClickHouse and the Staging Area all run on one machine.

## 8. Decision log
Decided on 6 Nov (group chat):
1. **ETL architecture: ELT inside ClickHouse.** Raw files are loaded into staging tables. One SQL file per target table transforms them. A Python orchestrator runs and times the steps.
2. **SCD2 and updates:**
   - The historical load computes EffectiveDate, EndDate and IsCurrent with window functions.
   - In the incremental batches, a changed dimension is rebuilt into a new table and swapped in with `EXCHANGE TABLES`.
   - DimTrade is a `ReplacingMergeTree` read with FINAL. It has no version column, because §3.4.5 forbids extra columns. Without one, ReplacingMergeTree keeps the last inserted row (checked on 26.8, with FINAL and after a merge).
3. **Report:** LaTeX on OpenAI Prism.

Proposed in this protocol:
4. **Clean start** before every run: drop the database, restart ClickHouse and drop the page cache (section 3).
5. **Timestamps:** `MessageDateAndTime` is a `DateTime64(3)`, written with `now64(3)` (section 4.1).
6. **Status message:** a 'Status' message with the BatchID at the start of every phase (section 4.1).
7. **Data visibility schedule:** data visibility 1 at the start of IU1, data visibility 2 right after it, then data visibility 2 every 60 s (section 4.4).
8. **FINAL reads:** `final = 1` in the validation, visibility and audit sessions (section 4.4).
9. **Step times:** measured with the monotonic clock and divided by the drift factor measured at each run (section 1.1).
10. **Repetitions:** 3 runs per SF, reported as the median with min and max (section 4.5).

Still to decide: the reference SF and the series (section 2).

## 9. Sources
- TPC-DI Standard Specification, revision 1.1.0, November 2014. TPC now lists TPC-DI among its obsolete workloads.
- Appendices A–C (the audit, batch validation and data visibility queries):
  - The spec says these come as a separate archive from the TPC website.
  - The TPC page now lists only the specification and `TPC-DI_Tools_v1.1.0.zip`. That zip holds DIGen and PDGF, not these files.
  - We use the copy in `shannon-barrow/databricks-tpc-di`, folder `src/incremental_batches/audit_validation/Appendix_v1.1.0/`: `tpcdi_audit.sql`, `tpcdi_validation.sql`, `tpcdi_visibility_1.sql` and `tpcdi_visibility_2.sql`. Several other public TPC-DI implementations have files with the same names.
- Part I protocol: `docs/benchmark-protocol.md`.
- Cluster C reading notes: `docs/tpcdi-cluster-c.md`.
